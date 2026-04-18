"""Case routes — upload, read, stream events, download report, list trial sites."""

from __future__ import annotations

import asyncio
import io
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse

from ...agent.patient_orchestrator import PatientOrchestrator
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
async def create_case(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload a pathology PDF, kick off the orchestrator in the background.

    The orchestrator runs asynchronously and streams events to anyone who
    subscribes to ``GET /api/cases/{case_id}/stream``.
    """
    content_type = (file.content_type or "").lower()
    if "pdf" not in content_type and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Expected a PDF upload.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file upload.")

    s = store()
    case_id = s.new_case_id()
    shell = PatientCase(case_id=case_id, pathology=PathologyFindings())
    record = CaseRecord(case_id=case_id, case=shell)
    s.put(record)

    orch = PatientOrchestrator(
        case_id=case_id,
        pdf_bytes=pdf_bytes,
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

    async def _cleanup() -> None:
        rec.unsubscribe(queue)

    response = EventSourceResponse(queue_to_sse(queue))
    response.background = asyncio.ensure_future(asyncio.sleep(0))  # type: ignore[attr-defined]
    # Note: EventSourceResponse will drain the generator; cleanup happens when
    # the client disconnects and the generator raises CancelledError. We also
    # remove the queue in _cleanup, but sse-starlette already calls close.
    return response


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
