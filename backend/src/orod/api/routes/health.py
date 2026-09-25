from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from orod import __version__
from orod.api.dependencies import get_llm, get_runner, get_settings
from orod.config import Settings
from orod.domain.models import HealthComponent, HealthResponse
from orod.ports.llm import LLMProvider

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
    llm: Annotated[LLMProvider, Depends(get_llm)],
    runner: Annotated[Any, Depends(get_runner)],
) -> HealthResponse:
    workspace = settings.workspace_root.resolve()
    git_result = await runner.run(["git", "--version"], workspace)
    gh_result = await runner.run(["gh", "auth", "status"], workspace)
    ollama_ok, ollama_detail = await llm.health()
    components = {
        "database": HealthComponent(ok=settings.database_path.exists(), detail="SQLite ready"),
        "chroma": HealthComponent(
            ok=settings.chroma_path.exists(), detail="local cache directory ready"
        ),
        "ollama": HealthComponent(ok=ollama_ok, detail=ollama_detail),
        "git": HealthComponent(ok=git_result.return_code == 0, detail="Git ready"),
        "github": HealthComponent(
            ok=gh_result.return_code == 0,
            detail="authenticated" if gh_result.return_code == 0 else "authentication required",
        ),
    }
    required_ok = components["database"].ok and components["git"].ok
    all_ok = all(component.ok for component in components.values())
    return HealthResponse(
        status="ok" if all_ok else "degraded" if required_ok else "unavailable",
        components=components,
        models={"chat": settings.chat_model, "embedding": settings.embedding_model},
        version=__version__,
    )
