from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from orod.config import Settings
from orod.ports.llm import LLMProvider, LLMProviderRegistry
from orod.ports.repository import PullRequestPublisher, RepositoryProvider
from orod.ports.scanners import SecurityScanner, VulnerabilityProvider
from orod.ports.storage import RunStore, VectorStore


@dataclass(slots=True)
class AgentServices:
    settings: Settings
    store: RunStore
    repository: RepositoryProvider
    scanners: list[SecurityScanner]
    vulnerabilities: VulnerabilityProvider
    vector_store: VectorStore
    llm: LLMProvider
    llms: LLMProviderRegistry
    publisher: PullRequestPublisher


class AgentPlugin(Protocol):
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]

    def build_subgraph(self, services: AgentServices) -> Any: ...


@dataclass(frozen=True, slots=True)
class TeamDefinition:
    name: str
    agent_names: tuple[str, ...]
