from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OROD_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    frontend_origin: str = "http://localhost:5173"

    database_path: Path = Path("../data/orod.sqlite3")
    checkpoint_path: Path = Path("../data/checkpoints.sqlite3")
    chroma_path: Path = Path("../data/chroma")
    workspace_root: Path = Path("../workspaces")
    fixture_root: Path = Field(
        default_factory=lambda: Path(__file__).parents[2] / "tests" / "fixtures"
    )

    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "qwen2.5-coder:14b"
    embedding_model: str = "nomic-embed-text"
    anthropic_api_key: str = ""
    llm_max_output_tokens: int = 16_000
    llm_timeout_seconds: int = 180
    use_llm: bool = True
    # When true the graph pauses before publishing and waits for a human decision.
    # Headless callers (test suite, evaluation harness) turn this off explicitly.
    require_human_approval: bool = True
    enable_github_publish: bool = False
    enable_external_scanners: bool = True

    max_file_bytes: int = 1_000_000
    max_diff_lines: int = 800
    command_timeout_seconds: int = 120
    event_poll_interval_seconds: float = 0.2

    def ensure_directories(self) -> None:
        for path in (
            self.database_path.parent,
            self.checkpoint_path.parent,
            self.chroma_path,
            self.workspace_root,
        ):
            path.expanduser().resolve().mkdir(parents=True, exist_ok=True)
