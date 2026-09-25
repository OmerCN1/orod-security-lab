from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends

from orod.adapters.llm.anthropic import SUPPORTED_MODELS
from orod.adapters.llm.ollama import list_installed_models
from orod.api.dependencies import get_settings
from orod.config import Settings
from orod.domain.models import ModelOption

router = APIRouter(tags=["models"])


@router.get("/models", response_model=list[ModelOption])
async def list_models(settings: Annotated[Settings, Depends(get_settings)]) -> list[ModelOption]:
    """Models the dashboard can offer, each flagged with whether it is actually reachable.

    Unavailable models are still listed so the UI can explain why one cannot be picked
    rather than silently hiding it.
    """
    installed = await list_installed_models(settings.ollama_base_url)
    options = [
        ModelOption(
            id=name,
            provider="ollama",
            available=True,
            detail="installed locally",
            is_default=name == settings.chat_model,
        )
        for name in installed
    ]
    if settings.chat_model not in installed and not settings.chat_model.startswith("claude-"):
        options.insert(
            0,
            ModelOption(
                id=settings.chat_model,
                provider="ollama",
                available=False,
                detail="configured but not pulled - run `ollama pull` first",
                is_default=True,
            ),
        )

    has_key = bool(settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
    options.extend(
        ModelOption(
            id=name,
            provider="anthropic",
            available=has_key,
            detail="ready" if has_key else "set OROD_ANTHROPIC_API_KEY to enable",
            is_default=name == settings.chat_model,
        )
        for name in SUPPORTED_MODELS
    )
    return options
