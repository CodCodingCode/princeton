"""Onkos FastAPI app - patient flow + chat SSE."""

from __future__ import annotations

import asyncio
import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..security.auth import require_api_token
from .routes import cases, chat, heygen, patient_guide


def _allowed_origins() -> list[str]:
    raw = os.environ.get("NEOVAX_CORS_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    # Dev defaults - Next.js on :3000 and Vite fallback on :5173.
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Warm the slow-to-cold-start pieces in parallel at server boot so the
    first case doesn't pay ~5–15s of model-load + Chroma-open latency.

    We preload:
      - the RAG store + sentence-transformers MiniLM embedder
      - the Chroma collection handle

    Each warm-up is best-effort and logged; failure never blocks startup.
    """

    async def _warm_rag() -> None:
        from ..rag.store import _client_and_collection, has_store

        if not has_store():
            print("[warmup] rag: no store on disk - skipping", flush=True, file=sys.stderr)
            return
        t0 = asyncio.get_event_loop().time()
        try:
            # sentence-transformers model load is blocking - run in a thread so
            # the event loop doesn't stall while chroma opens.
            await asyncio.to_thread(_client_and_collection)
            dt = asyncio.get_event_loop().time() - t0
            print(f"[warmup] rag: ready ({dt:.2f}s)", flush=True, file=sys.stderr)
        except Exception as e:
            print(f"[warmup] rag: failed - {e!r}", flush=True, file=sys.stderr)

    # Kick off all warmups in parallel - they return immediately on missing deps.
    await asyncio.gather(_warm_rag(), return_exceptions=True)
    yield


app = FastAPI(
    title="Onkos",
    description="Pathology PDF → NCCN railway → Kimi chat → oncologist report + trial sites",
    version="0.2.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Protected routers. When NEOVAX_API_TOKEN is set the dependency rejects
# unauthenticated callers; when unset (the dev / demo default) it is a no-op
# so nothing breaks. /api/health is declared below the include_router calls
# and stays unprotected so orchestrators and monitors can probe without a token.
_api_guard = [Depends(require_api_token)]
app.include_router(cases.router, dependencies=_api_guard)
app.include_router(chat.router, dependencies=_api_guard)
app.include_router(heygen.router, dependencies=_api_guard)
app.include_router(patient_guide.router, dependencies=_api_guard)


@app.get("/api/health")
async def health() -> dict:
    from ..agent._llm import has_api_key
    from ..chat.k2_client import has_kimi_key
    from ..rag import has_store as rag_available
    from ..security import api_token_enabled, log_redaction_enabled
    from .routes.heygen import has_liveavatar_key

    return {
        "ok": True,
        "k2_api_key": has_api_key(),
        "kimi_api_key": has_kimi_key(),
        "rag_store": rag_available(),
        "google_maps_api_key": bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
        "liveavatar_api_key": has_liveavatar_key(),
        "api_token_enabled": api_token_enabled(),
        "log_redaction_enabled": log_redaction_enabled(),
    }
