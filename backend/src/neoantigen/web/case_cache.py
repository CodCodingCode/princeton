"""Disk-backed cache of completed cases, keyed by uploaded-file content hash.

Motivation: during demos the same test_fixtures folder gets uploaded over
and over. The orchestrator takes ~90s per run, which is dead demo time. If
the exact same files have been processed before, short-circuit and return
the cached ``PatientCase`` (plus any generated ``PatientGuide``) instantly.

The cache is content-addressed: SHA-256 of (sorted filename, SHA-256 of
file bytes) pairs. Cache file lives at::

    backend/out/case_cache/<hash>.json

and contains ``{"case": {...}, "patient_guide": {...} | null}``. Survives
backend restarts - the entire point of persisting it.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ..agent.patient_orchestrator import InputPDF
from ..models import PatientCase


def _out_root() -> Path:
    """Resolve the ``out/`` directory robustly.

    ``Path("out")`` is relative to the current working directory — which is
    ``backend/`` when the user runs ``neoantigen serve`` from that folder
    but something else when the server is launched from the repo root or an
    IDE integration. If the env var isn't set, walk up from this file to
    find ``backend/out`` regardless of CWD.
    """
    env = os.environ.get("NEOVAX_OUT_DIR")
    if env:
        return Path(env)
    # case_cache.py lives at backend/src/neoantigen/web/case_cache.py.
    # parents[3] is the backend/ directory.
    return Path(__file__).resolve().parents[3] / "out"


def cache_dir() -> Path:
    root = _out_root() / "case_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def compute_input_hash(files: list[InputPDF]) -> str:
    """Stable hash of the uploaded set. Reordering doesn't invalidate."""
    h = hashlib.sha256()
    for f in sorted(files, key=lambda x: x.filename):
        h.update(f.filename.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(hashlib.sha256(f.data).digest())
    return h.hexdigest()[:20]


def _path_for(input_hash: str) -> Path:
    return cache_dir() / f"{input_hash}.json"


def load_cached_entry(input_hash: str) -> dict[str, Any] | None:
    p = _path_for(input_hash)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_cached_entry(
    input_hash: str,
    case: PatientCase,
    patient_guide: Any | None = None,
) -> None:
    payload = {
        "case": case.model_dump(mode="json"),
        "patient_guide": (
            patient_guide.model_dump(mode="json") if patient_guide is not None else None
        ),
    }
    _path_for(input_hash).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )


def update_cached_guide(input_hash: str, patient_guide: Any) -> None:
    """Patch a cache entry's patient_guide in place without re-writing the case."""
    entry = load_cached_entry(input_hash)
    if entry is None:
        return
    entry["patient_guide"] = patient_guide.model_dump(mode="json")
    _path_for(input_hash).write_text(
        json.dumps(entry, indent=2), encoding="utf-8",
    )


__all__ = [
    "cache_dir",
    "compute_input_hash",
    "load_cached_entry",
    "save_cached_entry",
    "update_cached_guide",
]
