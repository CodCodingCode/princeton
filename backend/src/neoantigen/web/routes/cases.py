"""Case routes - upload, read, stream events, download report, list trial sites."""

from __future__ import annotations

import asyncio
import io
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse

from ...agent.audit import audit
from ...agent.patient_orchestrator import InputPDF, PatientOrchestrator
from ...models import PathologyFindings, PatientCase
from ...report.pdf_report import build_report_pdf
from ..case_cache import (
    cache_dir as _cache_dir,
    compute_input_hash,
    load_cached_entry,
    save_cached_entry,
)
from ..sse import queue_to_sse
from ..storage import CaseRecord, store

try:
    from sse_starlette.sse import EventSourceResponse  # type: ignore
except ImportError:  # pragma: no cover
    EventSourceResponse = None  # type: ignore


router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_case(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    """Upload a folder of pathology / clinical PDFs, kick off the orchestrator.

    Accepts multiple files in a single multipart request (key ``files``). The
    orchestrator runs asynchronously and streams events to anyone subscribed
    to ``GET /api/cases/{case_id}/stream``.
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one PDF is required.")

    # Accept the messy mix real clinicians send us - PDFs, text notes,
    # spreadsheets, JSON exports, images. The extractor routes by extension.
    # Only reject the OS junk (.DS_Store, AppleDouble shards).
    supported_exts = {
        ".pdf", ".txt", ".md", ".csv", ".json", ".html", ".htm", ".log", ".rtf",
        ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp", ".gif",
    }
    inputs: list[InputPDF] = []
    for f in files:
        name = f.filename or "unknown"
        lname = name.lower()
        if lname == ".ds_store" or lname.startswith("._"):
            continue
        if not any(lname.endswith(ext) for ext in supported_exts):
            continue
        data = await f.read()
        if not data:
            continue
        inputs.append(InputPDF(filename=name, data=data))

    if not inputs:
        raise HTTPException(
            status_code=400,
            detail="No supported files in upload (expected PDFs, text, or images).",
        )

    s = store()
    case_id = s.new_case_id()
    input_hash = compute_input_hash(inputs)

    # Demo fast-path: if this exact file bundle has been processed before,
    # skip the ~90s orchestrator and rehydrate the cached PatientCase
    # straight into a new CaseRecord. Emit a single "done" so any SSE
    # subscriber immediately transitions to the ready phase.
    cached = load_cached_entry(input_hash)
    audit(
        "cache", "lookup",
        case_id=case_id, input_hash=input_hash,
        hit=cached is not None, cache_dir=str(_cache_dir()),
        file_count=len(inputs),
    )
    if cached is not None:
        from ...agent.events import EventKind  # avoid module-level cycle
        try:
            case = PatientCase.model_validate(cached["case"])
        except Exception:
            case = None  # fall through to fresh run
        if case is not None:
            case.case_id = case_id
            record = CaseRecord(
                case_id=case_id,
                case=case,
                input_hash=input_hash,
                done=True,
            )
            if cached.get("patient_guide"):
                from .patient_guide import PatientGuide
                try:
                    record.patient_guide = PatientGuide.model_validate(
                        cached["patient_guide"],
                    )
                except Exception:
                    pass
            s.put(record)

            async def _replay_cached() -> None:
                await record.bus.emit(
                    EventKind.LOG,
                    "Loaded cached case (content-hash hit) — skipping pipeline.",
                    {"cached": True, "input_hash": input_hash},
                )
                await record.bus.emit(
                    EventKind.CASE_UPDATE, "cached case", case.model_dump(mode="json"),
                )
                await record.bus.emit(EventKind.DONE, "done", {"cached": True})
                await record.bus.close()

            asyncio.create_task(_replay_cached())
            return {"case_id": case_id, "cached": True}

    # Fresh run: kick off the orchestrator, persist to cache on completion.
    shell = PatientCase(case_id=case_id, pathology=PathologyFindings())
    record = CaseRecord(case_id=case_id, case=shell, input_hash=input_hash)
    s.put(record)

    orch = PatientOrchestrator(
        case_id=case_id,
        pdfs=inputs,
        bus=record.bus,
    )

    async def _run() -> None:
        try:
            case = await orch.run()
        except Exception as e:  # noqa: BLE001
            audit(
                "cache", "skip_save_orch_crashed",
                case_id=case_id, input_hash=input_hash,
                error_type=type(e).__name__, error=str(e)[:400],
            )
            from ...agent.events import EventKind
            try:
                await record.bus.emit(
                    EventKind.TOOL_ERROR, f"orchestrator crashed: {e}",
                )
                await record.bus.close()
            except Exception:
                pass
            return
        s.update_case(case_id, case)
        # Persist to the on-disk cache so the next upload of the same
        # bundle is instant. Best-effort: never let a cache-write failure
        # crash the run — but DO surface the error in the audit log so we
        # can diagnose why the cache stays empty.
        try:
            save_cached_entry(input_hash, case, record.patient_guide)
            audit(
                "cache", "save_ok",
                case_id=case_id, input_hash=input_hash,
                cache_dir=str(_cache_dir()),
            )
        except Exception as e:
            audit(
                "cache", "save_failed",
                case_id=case_id, input_hash=input_hash,
                error_type=type(e).__name__, error=str(e)[:400],
                cache_dir=str(_cache_dir()),
            )

    asyncio.create_task(_run())

    return {"case_id": case_id, "cached": False}


@router.get("/{case_id}")
async def get_case(case_id: str) -> dict[str, Any]:
    rec = store().get(case_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return rec.case.model_dump()


@router.get("/{case_id}/stream")
async def stream_case(case_id: str):
    rec = store().get(case_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    if EventSourceResponse is None:
        raise HTTPException(status_code=500, detail="sse-starlette not installed.")

    queue = await rec.subscribe()
    # sse-starlette drains the async generator. When the client disconnects,
    # the generator raises CancelledError, which we catch inside queue_to_sse
    # via normal iteration termination. We unsubscribe after the generator
    # ends so the fanout stops pushing to a dead queue.
    return EventSourceResponse(_stream_and_cleanup(queue, rec))


async def _stream_and_cleanup(queue, rec):
    try:
        async for event in queue_to_sse(queue):
            yield event
    finally:
        rec.unsubscribe(queue)


@router.get("/{case_id}/trial-sites")
async def get_trial_sites(case_id: str) -> dict[str, Any]:
    rec = store().get(case_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return {"sites": [s.model_dump() for s in rec.case.trial_sites]}


@router.get("/{case_id}/report.pdf")
async def get_report_pdf(case_id: str):
    rec = store().get(case_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    onc_agent = rec.chat_agents.get("oncologist")
    chat_messages = list(onc_agent.messages) if onc_agent is not None else []
    pdf = build_report_pdf(
        rec.case,
        chat_messages=chat_messages,
        events=list(rec.replay),
        narrative_cache=rec.narrative_cache,
    )
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="onkos-case-{case_id}.pdf"',
        },
    )


@router.get("")
async def list_cases() -> dict[str, Any]:
    return {"cases": store().list_cases()}
