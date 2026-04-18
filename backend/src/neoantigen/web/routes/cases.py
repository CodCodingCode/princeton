"""Case routes — upload, read, stream events, download report, list trial sites."""

from __future__ import annotations

import asyncio
import io
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse

from ...agent.patient_orchestrator import InputPDF, PatientOrchestrator
from ...models import PathologyFindings, PatientCase
from ...report.pdf_report import build_report_pdf
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

    inputs: list[InputPDF] = []
    for f in files:
        name = f.filename or "unknown.pdf"
        ctype = (f.content_type or "").lower()
        if "pdf" not in ctype and not name.lower().endswith(".pdf"):
            # Silently skip non-PDFs (e.g. a stray .DS_Store from a folder drop)
            continue
        data = await f.read()
        if not data:
            continue
        inputs.append(InputPDF(filename=name, data=data))

    if not inputs:
        raise HTTPException(
            status_code=400,
            detail="No valid PDF files in upload (expected PDFs by extension or mime type).",
        )

    s = store()
    case_id = s.new_case_id()
    shell = PatientCase(case_id=case_id, pathology=PathologyFindings())
    record = CaseRecord(case_id=case_id, case=shell)
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

    asyncio.create_task(_run())

    return {"case_id": case_id}


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
    pdf = build_report_pdf(rec.case)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="neovax-case-{case_id}.pdf"',
        },
    )


@router.get("")
async def list_cases() -> dict[str, Any]:
    return {"cases": store().list_cases()}
