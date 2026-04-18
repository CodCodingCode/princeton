"""NeoVax FastAPI app — patient flow + chat SSE."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import cases, chat, heygen


def _allowed_origins() -> list[str]:
    raw = os.environ.get("NEOVAX_CORS_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    # Dev defaults — Next.js on :3000 and Vite fallback on :5173.
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


app = FastAPI(
    title="NeoVax",
    description="Pathology PDF → NCCN railway → Kimi chat → oncologist report + trial sites",
    version="0.2.0",
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


@app.get("/api/health")
async def health() -> dict:
    from ..chat.k2_client import has_kimi_key
    from ..agent._llm import has_api_key
    from ..rag import has_store as rag_available
    from .routes.heygen import has_heygen_key

    return {
        "ok": True,
        "k2_api_key": has_api_key(),
        "kimi_api_key": has_kimi_key(),
        "rag_store": rag_available(),
        "google_maps_api_key": bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
        "heygen_api_key": has_heygen_key(),
    }
