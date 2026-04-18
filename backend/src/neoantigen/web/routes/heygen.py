"""LiveAvatar session-token minting.

HeyGen's legacy Streaming Avatar API (/v1/streaming.*) was retired and returns
401 with a deprecation notice. The replacement is LiveAvatar — a separate
product on api.liveavatar.com with its own keys.

The API key never leaves the backend. The frontend calls
`POST /api/heygen/token`; we exchange the long-lived API key for a short-lived
session token via LiveAvatar's `/v1/sessions/token` and return it to the
browser. The browser then uses `@heygen/liveavatar-web-sdk` with the token.
"""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/heygen", tags=["heygen"])

LIVEAVATAR_BASE = "https://api.liveavatar.com"


def has_liveavatar_key() -> bool:
    return bool(os.environ.get("LIVEAVATAR_API_KEY"))


@router.post("/token")
async def create_session_token() -> dict:
    api_key = os.environ.get("LIVEAVATAR_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="LIVEAVATAR_API_KEY not set")

    avatar_id = os.environ.get("LIVEAVATAR_AVATAR_ID")
    if not avatar_id:
        raise HTTPException(status_code=503, detail="LIVEAVATAR_AVATAR_ID not set")

    body = {
        "mode": "FULL",
        "avatar_id": avatar_id,
        "avatar_persona": {"language": "en"},
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{LIVEAVATAR_BASE}/v1/sessions/token",
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
            },
            json=body,
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"liveavatar token mint failed: {resp.status_code} {resp.text[:300]}",
        )
    data = resp.json().get("data") or {}
    session_token = data.get("session_token")
    if not session_token:
        raise HTTPException(status_code=502, detail="liveavatar session_token missing in response")
    return {"token": session_token}
