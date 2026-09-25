from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from orod.domain.models import utc_now


class EventLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class EventType(StrEnum):
    RUN = "run"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    FINDING = "finding"
    PATCH = "patch"
    VALIDATION = "validation"
    REVIEW = "review"
    PULL_REQUEST = "pull_request"
    HEARTBEAT = "heartbeat"


class RunEvent(BaseModel):
    schema_version: str = "1"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    sequence: int = 0
    run_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    agent: str = "system"
    event_type: EventType = EventType.RUN
    level: EventLevel = EventLevel.INFO
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
