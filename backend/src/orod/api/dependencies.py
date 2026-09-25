from __future__ import annotations

from typing import Any, cast

from fastapi import Request

from orod.application.run_analysis import RunCoordinator
from orod.config import Settings
from orod.ports.llm import LLMProvider
from orod.ports.repository import RepositoryProvider
from orod.ports.scanners import VulnerabilityProvider
from orod.ports.storage import RunStore


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_store(request: Request) -> RunStore:
    return cast(RunStore, request.app.state.store)


def get_coordinator(request: Request) -> RunCoordinator:
    return cast(RunCoordinator, request.app.state.coordinator)


def get_vulnerability_provider(request: Request) -> VulnerabilityProvider:
    return cast(VulnerabilityProvider, request.app.state.vulnerabilities)


def get_llm(request: Request) -> LLMProvider:
    return cast(LLMProvider, request.app.state.llm)


def get_runner(request: Request) -> Any:
    return request.app.state.runner


def get_repository(request: Request) -> RepositoryProvider:
    return cast(RepositoryProvider, request.app.state.repository)
