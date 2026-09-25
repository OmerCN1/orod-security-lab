from __future__ import annotations

from orod.agents.base import TeamDefinition


class TeamRegistry:
    def __init__(self) -> None:
        self._teams: dict[str, TeamDefinition] = {}

    def register(self, team: TeamDefinition) -> None:
        if team.name in self._teams:
            raise ValueError(f"team already registered: {team.name}")
        self._teams[team.name] = team

    def get(self, name: str) -> TeamDefinition:
        try:
            return self._teams[name]
        except KeyError as exc:
            raise ValueError(f"unknown team: {name}") from exc


DEFAULT_SECURITY_TEAM = TeamDefinition(
    name="code-security",
    agent_names=("architect", "security", "developer"),
)
