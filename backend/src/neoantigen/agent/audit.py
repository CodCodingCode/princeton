"""Structured JSONL audit log for every LLM call in the pipeline.

Writes one JSON line per call to ``out/llm_audit.jsonl`` (overridable via
``NEOVAX_AUDIT_PATH``). Every line auto-includes ``ts``, ``case_id``
(from a contextvar the orchestrator sets at run-start), ``stage``, ``event``,
plus whatever stage-specific fields the caller passes via kwargs.

Design notes:
- Best-effort: never raises. Silently no-ops on IO failure so the pipeline
  never crashes because of logging.
- Long string fields (>8000 chars) are truncated with a marker so a single
  multi-megabyte response can't blow up the file.
- 50 MB soft cap: when the file exceeds that size, the next write rotates it
  to a timestamped suffix (``llm_audit.jsonl.20260418_165342``) and starts a
  fresh file. No background thread needed.
- Unlike ``k2.log`` (human tail format), this is JSONL intended to be queried
  with ``jq`` — e.g. ``jq 'select(.stage=="walker" and .event=="phase_parse")'``.
"""

from __future__ import annotations

import json
import os
import time
from contextvars import ContextVar
from pathlib import Path

_CASE_ID: ContextVar[str | None] = ContextVar("case_id", default=None)

_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "out" / "llm_audit.jsonl"
_MAX_FIELD_CHARS = 8000
_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


def set_case_id(case_id: str | None) -> None:
    """Bind the current asyncio task (and its descendants) to a case_id."""
    _CASE_ID.set(case_id)


def _audit_path() -> Path:
    return Path(os.environ.get("NEOVAX_AUDIT_PATH", str(_DEFAULT_PATH)))


def _truncate(value: object) -> object:
    if isinstance(value, str) and len(value) > _MAX_FIELD_CHARS:
        return value[:_MAX_FIELD_CHARS] + "...<TRUNCATED>"
    return value


def _maybe_rotate(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size >= _MAX_FILE_BYTES:
            suffix = time.strftime("%Y%m%d_%H%M%S")
            path.rename(path.with_suffix(path.suffix + f".{suffix}"))
    except OSError:
        pass


def audit(stage: str, event: str, **fields: object) -> None:
    """Append one structured JSONL line. Never raises."""
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _maybe_rotate(path)
        record = {
            "ts": time.time(),
            "case_id": _CASE_ID.get(),
            "stage": stage,
            "event": event,
        }
        for k, v in fields.items():
            record[k] = _truncate(v)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


__all__ = ["audit", "set_case_id"]
