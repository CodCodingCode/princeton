"""HeyGen streaming-avatar token minting.

The API key never leaves the backend. The frontend calls
`POST /api/heygen/token`; we exchange the long-lived API key for a short-lived
session token via HeyGen's `/v1/streaming.create_token` and return that to the
browser. The browser then uses `@heygen/streaming-avatar` with the token.
"""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/heygen", tags=["heygen"])

HEYGEN_BASE = "https://api.heygen.com"


def has_heygen_key() -> bool:
    return bool(os.environ.get("HEYGEN_API_KEY"))


@router.post("/token")
async def create_session_token() -> dict:
    api_key = os.environ.get("HEYGEN_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="HEYGEN_API_KEY not set")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{HEYGEN_BASE}/v1/streaming.create_token",
            headers={"x-api-key": api_key},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"heygen token mint failed: {resp.status_code} {resp.text[:200]}",
        )
    data = resp.json().get("data") or {}
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=502, detail="heygen token missing in response")
    return {"token": token}
