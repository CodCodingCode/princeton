"""Optional bearer-token auth for /api/* endpoints.

Behaviour driven by a single env var:

  NEOVAX_API_TOKEN unset (or empty after trim): dependency is a no-op. Demos
                                                and dev loops work unchanged.
  NEOVAX_API_TOKEN=<token>:                      every protected request must
                                                 carry `Authorization: Bearer <token>`.

The comparison uses ``secrets.compare_digest`` so a malicious caller cannot
time-probe the token by measuring mismatch latency.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, status


def _configured_token() -> str | None:
    raw = os.environ.get("NEOVAX_API_TOKEN", "").strip()
    return raw or None


def api_token_enabled() -> bool:
    """True when a non-empty NEOVAX_API_TOKEN is configured."""
    return _configured_token() is not None


async def require_api_token(
    authorization: str | None = Header(default=None),
) -> None:
    """FastAPI dependency. No-op when auth is disabled; 401s otherwise."""
    expected = _configured_token()
    if expected is None:
        return
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected 'Authorization: Bearer <token>'.",
        )
    if not secrets.compare_digest(token.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token.",
        )
