"""Local API access control: a bearer token plus a same-origin rule for writes.

The API runs on loopback, but any page open in the operator's browser can send requests
to it, and it acts with the operator's GitHub credentials. Host validation (in
``create_app``) defeats DNS rebinding; the token makes every request prove it comes from
the operator's own tooling; the origin rule stops another site from driving the
dashboard's proxy.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from orod.config import Settings

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

bearer = HTTPBearer(auto_error=False, description="Contents of data/api-token")


def load_or_create_api_token(settings: Settings) -> str:
    """The configured token, or the one persisted on disk, created on first use.

    The file is created with ``O_EXCL`` and mode 0600, so it is never readable by other
    users and two processes starting together cannot overwrite each other's token.
    """
    configured = settings.api_token.get_secret_value().strip()
    if configured:
        return configured
    path = settings.api_token_path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _read_existing(path)
    token = secrets.token_urlsafe(32)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"{token}\n")
    return token


def _read_existing(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"API token path is not a regular file: {path}")
    if path.stat().st_mode & 0o077:
        path.chmod(0o600)
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError(f"API token file is empty or too short: {path}")
    return token


async def require_api_access(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected: str = request.app.state.api_token
    supplied = credentials.credentials if credentials is not None else ""
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    origin = request.headers.get("origin")
    allowed: frozenset[str] = request.app.state.allowed_origins
    if request.method not in SAFE_METHODS and origin is not None and origin not in allowed:
        # Browsers send Origin on cross-site writes; the dashboard's proxy forwards it.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="origin not allowed")
