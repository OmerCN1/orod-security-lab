from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from orod import __version__
from orod.adapters.execution.container import ContainerCommandRunner
from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.adapters.github.cli import GitHubCLIPublisher
from orod.adapters.llm.factory import CachingLLMProviderRegistry
from orod.adapters.persistence.sqlite import SQLiteRunStore
from orod.adapters.repository.git import GitRepositoryAdapter
from orod.adapters.scanners.bandit import BanditScanner
from orod.adapters.scanners.builtin import BuiltinPythonScanner
from orod.adapters.scanners.osv import OSVVulnerabilityAdapter
from orod.adapters.scanners.semgrep import SemgrepScanner
from orod.adapters.vector.chroma import ChromaAdvisoryStore
from orod.agents.base import AgentServices
from orod.api.routes import health, models, runs, vulnerabilities
from orod.api.security import load_or_create_api_token, require_api_access
from orod.application.run_analysis import RunCoordinator
from orod.config import Settings
from orod.graph.builder import build_security_team
from orod.ports.scanners import SecurityScanner


def local_frontend_origins(configured_origin: str) -> list[str]:
    """Allow both conventional loopback hostnames during local development."""
    origins = [configured_origin]
    aliases = {
        "http://localhost:5173": "http://127.0.0.1:5173",
        "http://127.0.0.1:5173": "http://localhost:5173",
    }
    alternate = aliases.get(configured_origin)
    if alternate:
        origins.append(alternate)
    return origins


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configured.ensure_directories()
        app.state.api_token = load_or_create_api_token(configured)
        store = SQLiteRunStore(configured.database_path)
        await store.initialize()
        semgrep_executable = str(Path(sys.executable).parent / "semgrep")
        allowed_executables = {sys.executable, "git", "gh", semgrep_executable}
        runner = SafeCommandRunner(
            allowed_executables=allowed_executables,
            workspace_root=configured.workspace_root,
            default_timeout_seconds=configured.command_timeout_seconds,
        )
        repository = GitRepositoryAdapter(
            configured, runner, validation_runner=ContainerCommandRunner(configured)
        )
        vector_store = ChromaAdvisoryStore(
            configured.chroma_path,
            configured.ollama_base_url,
            configured.embedding_model,
        )
        vulnerabilities_adapter = OSVVulnerabilityAdapter(vector_store)
        llm_registry = CachingLLMProviderRegistry(configured)
        llm = llm_registry.default()
        scanners: list[SecurityScanner] = [
            BuiltinPythonScanner(configured.max_file_bytes, configured.workspace_root),
            BanditScanner(runner),
        ]
        if configured.enable_external_scanners:
            scanners.append(SemgrepScanner(runner))
        publisher = GitHubCLIPublisher(runner)

        async with AsyncSqliteSaver.from_conn_string(
            str(configured.checkpoint_path)
        ) as checkpointer:
            services = AgentServices(
                settings=configured,
                store=store,
                repository=repository,
                scanners=scanners,
                vulnerabilities=vulnerabilities_adapter,
                vector_store=vector_store,
                llm=llm,
                llms=llm_registry,
                publisher=publisher,
            )
            graph = build_security_team(services, checkpointer)
            coordinator = RunCoordinator(
                graph,
                store,
                max_concurrent_runs=configured.max_concurrent_runs,
                cancel_grace_seconds=configured.cancel_grace_seconds,
            )
            # Before accepting requests: runs a previous process left mid-flight are
            # failed rather than shown as running forever.
            await coordinator.reconcile_interrupted_runs()
            app.state.settings = configured
            app.state.store = store
            app.state.runner = runner
            app.state.repository = repository
            app.state.scanners = scanners
            app.state.vulnerabilities = vulnerabilities_adapter
            app.state.llm = llm
            app.state.llm_registry = llm_registry
            app.state.coordinator = coordinator
            yield
            await coordinator.shutdown()

    app = FastAPI(
        title="OROD API",
        version=__version__,
        description="Local-first autonomous code security and refactoring team",
        lifespan=lifespan,
    )
    origins = local_frontend_origins(configured.frontend_origin)
    app.state.allowed_origins = frozenset(origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )
    # Outermost: a request whose Host is not loopback is refused before anything else,
    # which is what defeats DNS rebinding.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=configured.allowed_hosts)
    protected = [Depends(require_api_access)]
    for router in (health.router, models.router, runs.router, vulnerabilities.router):
        app.include_router(router, prefix="/api/v1", dependencies=protected)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"name": "OROD", "docs": "/docs", "health": "/api/v1/health"}

    return app


app = create_app()
