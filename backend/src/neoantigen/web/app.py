"""NeoVax FastAPI app - patient flow + chat SSE."""

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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    title="NeoVax",
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


app.include_router(cases.router)
app.include_router(chat.router)
app.include_router(heygen.router)
app.include_router(patient_guide.router)


@app.get("/api/health")
async def health() -> dict:
    from ..chat.k2_client import has_kimi_key
    from ..agent._llm import has_api_key
    from ..rag import has_store as rag_available
    from .routes.heygen import has_liveavatar_key

    return {
        "ok": True,
        "k2_api_key": has_api_key(),
        "kimi_api_key": has_kimi_key(),
        "rag_store": rag_available(),
        "google_maps_api_key": bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
        "liveavatar_api_key": has_liveavatar_key(),
    }
