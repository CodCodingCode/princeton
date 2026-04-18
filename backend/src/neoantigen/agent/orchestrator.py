"""Main agent orchestrator.

Uses Claude Agent SDK to run an agent with an in-process MCP server of our custom
tools. Tools emit events to an EventBus; the external consumer (Streamlit UI or
CLI) is responsible for consuming the stream and reconstructing the CaseFile.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    query,
)

from ..models import CaseFile, EmailDraft, LabMatch, PathologyReport, PipelineResult, StructurePose, TimelineEvent
from .events import AgentEvent, EventBus, EventKind, set_current_bus
from .tools import ALL_TOOLS


SYSTEM_PROMPT = """You are NeoVax — an autonomous veterinary cancer-treatment coordinator.

Your job: given a tumor VCF and pathology PDF, produce a complete treatment package end-to-end.

**Required workflow** (call tools in this order, using parallel calls where noted):

1. Call `read_pathology` with the PDF path. Extract patient details + location.

2. Call `run_neoantigen_pipeline` with the VCF. Use species="canine" and allele="DLA-88*50101"
   unless the pathology specifies otherwise. Top 15 candidates, max_nm=500.

3. In PARALLEL (call in a single response), run:
   - `find_sequencing_labs` with the owner's location
   - `find_vet_oncologists` with the owner's location
   - `find_synthesis_vendors` with the mRNA length from step 2
   - `find_drug_interactions` with the genes from step 2
   - `find_clinical_trials` with the genes + cancer type

4. Call `validate_structure_3d` on the TOP candidate peptide with the DLA allele. Also do this
   for the #2 candidate if time permits.

5. Call `draft_email` four times (can be parallel):
   - recipient_type="sequencing_lab" to the top sequencing lab found
   - recipient_type="synthesis_vendor" to TriLink BioTechnologies
   - recipient_type="vet_oncologist" to the top vet oncologist found
   - recipient_type="ethics_board" for the compassionate use application

6. Call `generate_timeline`.

7. Call `explain_case_to_owner` with the patient details and top mutation.

8. Respond with a final summary: number of candidates, top candidate, estimated cost + timeline,
   and emphasize this is a proposed plan requiring veterinary sign-off.

Be efficient. Prefer parallel tool calls. Each tool emits progress events — the UI is watching
live. Do NOT re-call tools with the same arguments."""


@dataclass
class CaseOrchestrator:
    """One-shot orchestrator: runs the agent end-to-end for a single case."""

    vcf_path: Path
    pdf_path: Path
    bus: EventBus = field(default_factory=EventBus)
    case: CaseFile | None = None

    async def run(self) -> None:
        """Run the agent loop. Emits events to self.bus; external consumer assembles CaseFile."""
        set_current_bus(self.bus)

        mcp_server = create_sdk_mcp_server(name="neovax-tools", version="0.1.0", tools=ALL_TOOLS)

        tool_names = [f"mcp__neovax-tools__{t.name}" for t in ALL_TOOLS]

        model = os.environ.get("NEOVAX_MODEL", "claude-sonnet-4-5")

        options = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            model=model,
            mcp_servers={"neovax-tools": mcp_server},
            allowed_tools=tool_names,
            permission_mode="bypassPermissions",
            max_turns=30,
        )

        user_prompt = (
            f"New case to process.\n\n"
            f"Pathology PDF: {self.pdf_path.resolve()}\n"
            f"Tumor VCF: {self.vcf_path.resolve()}\n\n"
            f"Execute the full workflow. The UI is streaming events live — keep moving."
        )

        try:
            async for message in query(prompt=user_prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            await self.bus.emit(EventKind.LOG, block.text[:500])
                elif isinstance(message, ResultMessage):
                    await self.bus.emit(EventKind.DONE, "✅ Case complete")
                    break
        except Exception as e:
            await self.bus.emit(EventKind.TOOL_ERROR, f"Agent error: {e}")
        finally:
            await self.bus.close()
            set_current_bus(None)


def build_case_file(events: list[AgentEvent]) -> CaseFile | None:
    """Reconstruct a CaseFile from a captured list of CASE_UPDATE events."""
    pathology_data: dict | None = None
    pipeline_data: dict | None = None
    structures: list[dict] = []
    seq_labs: list[dict] = []
    vets: list[dict] = []
    vendors: list[dict] = []
    emails: list[dict] = []
    timeline_data: list[dict] = []
    plain_english = ""

    for ev in events:
        if ev.kind != EventKind.CASE_UPDATE:
            continue
        p = ev.payload
        if "pathology" in p:
            pathology_data = p["pathology"]
        if "pipeline_result" in p:
            pipeline_data = p["pipeline_result"]
        if "pose" in p:
            structures.append(p["pose"])
        if "labs" in p:
            seq_labs = p["labs"]
        if "vets" in p:
            vets = p["vets"]
        if "vendors" in p:
            vendors = p["vendors"]
        if "email" in p:
            emails.append(p["email"])
        if "timeline" in p:
            timeline_data = p["timeline"]
        if "plain_english" in p:
            plain_english = p["plain_english"]

    if pathology_data is None:
        return None

    pipeline = PipelineResult(**pipeline_data) if pipeline_data else PipelineResult(mutations=[], candidates=[])
    return CaseFile(
        pathology=PathologyReport(**pathology_data),
        pipeline=pipeline,
        structures=[StructurePose(**s) for s in structures],
        sequencing_labs=[LabMatch(**l) for l in seq_labs],
        synthesis_vendors=[LabMatch(**v) for v in vendors],
        vet_oncologists=[LabMatch(**v) for v in vets],
        emails=[EmailDraft(**e) for e in emails],
        timeline=[TimelineEvent(**t) for t in timeline_data],
        plain_english=plain_english,
    )


async def run_case(vcf_path: Path, pdf_path: Path, bus: EventBus | None = None) -> CaseOrchestrator:
    """Create and start a case orchestration. Caller consumes bus.stream() for live events."""
    bus = bus or EventBus()
    orchestrator = CaseOrchestrator(vcf_path=vcf_path, pdf_path=pdf_path, bus=bus)
    return orchestrator
