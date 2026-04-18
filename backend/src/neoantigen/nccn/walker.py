"""NCCN walker — drives the medical model through the decision graph.

At each node, the walker constructs a prompt containing (a) the node's question
and option labels, and (b) the slice of `PatientState` listed in
`evidence_required`. It streams the model's `<think>` block live as
`THINKING_DELTA` events, then parses the post-think JSON to pick the next
option, emits `NCCN_NODE_VISITED`, and advances.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

from pydantic import BaseModel, Field

from ..agent._llm import has_api_key, split_thinking, stream_with_thinking
from ..agent.events import EventKind, emit
from ..models import Mutation, NCCNStep, PathologyFindings
from .melanoma_v2024 import GRAPH, ROOT, NCCNNode


@dataclass
class PatientState:
    pathology: PathologyFindings
    mutations: list[Mutation] = field(default_factory=list)
    tumor_mutational_burden: float | None = None

    @property
    def braf_status(self) -> str:
        for m in self.mutations:
            if m.gene.upper() == "BRAF" and m.position == 600:
                return f"V600{m.alt_aa}"
        return "wild-type"

    def evidence_for(self, fields: tuple[str, ...]) -> dict[str, str]:
        out: dict[str, str] = {}
        for f in fields:
            if f == "mutations":
                out[f] = ", ".join(m.full_label for m in self.mutations) or "none reported"
            elif f == "braf_status":
                out[f] = self.braf_status
            elif f == "tumor_mutational_burden":
                out[f] = f"{self.tumor_mutational_burden:.1f} mut/Mb" if self.tumor_mutational_burden else "unknown"
            elif f == "t_stage":
                out[f] = self.pathology.t_stage
            elif hasattr(self.pathology, f):
                v = getattr(self.pathology, f)
                out[f] = "unknown" if v is None else str(v)
        return out


class _DecisionResponse(BaseModel):
    chosen_option_index: int = Field(ge=0)
    one_sentence_rationale: str = ""


SYSTEM_PROMPT = (
    "You are an oncologist reasoning through the NCCN cutaneous melanoma "
    "guideline. At each node you will be given the question, the available "
    "options, and the relevant patient evidence. Think step-by-step inside "
    "<think>...</think> and then output a JSON object with the chosen option "
    "index and a one-sentence rationale. Be honest when evidence is missing — "
    "default to the safest standard-of-care option."
)


def _build_user_prompt(node: NCCNNode, evidence: dict[str, str]) -> str:
    options = "\n".join(
        f"  [{i}] {opt.label} — {opt.description}" for i, opt in enumerate(node.options)
    )
    ev_lines = "\n".join(f"  - {k}: {v}" for k, v in evidence.items()) or "  (none)"
    return (
        f"Node: {node.title}\n"
        f"Question: {node.question}\n\n"
        f"Patient evidence:\n{ev_lines}\n\n"
        f"Options:\n{options}\n\n"
        "Respond with: <think>your reasoning</think>\n"
        '{"chosen_option_index": <int>, "one_sentence_rationale": "..."}'
    )


def _parse_decision(answer: str, n_options: int) -> _DecisionResponse:
    """Best-effort JSON extraction from the model's post-think answer."""
    m = re.search(r"\{[\s\S]*?\}", answer)
    if m:
        try:
            data = json.loads(m.group(0))
            return _DecisionResponse.model_validate(data)
        except Exception:
            pass
    m2 = re.search(r"\b(\d+)\b", answer)
    if m2:
        idx = max(0, min(int(m2.group(1)), n_options - 1))
        return _DecisionResponse(chosen_option_index=idx, one_sentence_rationale=answer.strip()[:200])
    return _DecisionResponse(chosen_option_index=0, one_sentence_rationale="defaulted")


def _heuristic_decision(node: NCCNNode, state: PatientState) -> tuple[int, str]:
    """Fallback when no API key is configured — picks the safest standard option."""
    if node.id == "START":
        return 0, "Heuristic: assume primary cutaneous melanoma confirmed."
    if node.id == "STAGE_T":
        b = state.pathology.breslow_thickness_mm or 0.0
        if b <= 1.0:
            return 0, "Heuristic: T1 by Breslow."
        if b <= 2.0:
            return 1, "Heuristic: T2 by Breslow."
        if b <= 4.0:
            return 2, "Heuristic: T3 by Breslow."
        return 3, "Heuristic: T4 by Breslow."
    if node.id == "SLNB_DECISION":
        b = state.pathology.breslow_thickness_mm or 0.0
        if b > 0.8:
            return 0, "Heuristic: SLNB indicated for >0.8mm; assume positive for demo."
        return 2, "Heuristic: thin lesion, skip nodal staging."
    if node.id == "STAGE_I_II":
        return 1, "Heuristic: assume high-risk II → adjuvant IO."
    if node.id == "STAGE_III":
        return 0, "Heuristic: adjuvant anti-PD-1 is standard of care."
    if node.id == "STAGE_IV":
        return 1, "Heuristic: no CNS mets information provided."
    if node.id == "BRAIN_METS":
        return 0, "Heuristic: continue to systemic selection."
    if node.id == "BRAF_TEST":
        return 0 if state.braf_status != "wild-type" else 1, f"Heuristic: BRAF status {state.braf_status}."
    if node.id == "BRAF_MUT_TX":
        return 0, "Heuristic: anti-PD-1 first; reserve targeted for progression."
    if node.id == "BRAF_WT_TX":
        return 0, "Heuristic: anti-PD-1 monotherapy."
    if node.id == "VACCINE_CANDIDATE":
        return 0, "Heuristic: design vaccine if mutations are available."
    return 0, "Heuristic default."


@dataclass
class NCCNWalker:
    state: PatientState

    async def walk(self) -> AsyncIterator[NCCNStep]:
        current_id: str | None = ROOT
        visited: set[str] = set()

        while current_id is not None and current_id not in visited:
            visited.add(current_id)
            node = GRAPH[current_id]
            evidence = self.state.evidence_for(node.evidence_required)

            if node.is_terminal or not node.options:
                step = NCCNStep(
                    node_id=node.id,
                    node_title=node.title,
                    chosen_option=node.question,
                    next_node_id=None,
                    reasoning="Terminal node reached.",
                    evidence=evidence,
                )
                await emit(
                    EventKind.NCCN_NODE_VISITED,
                    f"NCCN ▸ {node.title} (terminal)",
                    {"step": step.model_dump()},
                )
                yield step
                break

            interrupt = await _consume_interrupt()
            user_prompt = _build_user_prompt(node, evidence)
            if interrupt:
                user_prompt += f"\n\nDoctor interjected: {interrupt!r}\nReconsider in light of this."

            await emit(
                EventKind.TOOL_START,
                f"NCCN ▸ deciding at {node.id}",
                {"node_id": node.id, "node_title": node.title, "evidence": evidence},
            )

            answer_buf = ""
            think_buf = ""
            mode: Literal["api", "heuristic"] = "api" if has_api_key() else "heuristic"
            try:
                if mode == "api":
                    async for kind, chunk in stream_with_thinking(SYSTEM_PROMPT, user_prompt, max_tokens=600):
                        if kind == "thinking":
                            think_buf += chunk
                            await emit(
                                EventKind.THINKING_DELTA,
                                "thinking",
                                {"node_id": node.id, "delta": chunk},
                            )
                        else:
                            answer_buf += chunk
                            await emit(
                                EventKind.ANSWER_DELTA,
                                "answer",
                                {"node_id": node.id, "delta": chunk},
                            )
            except Exception as e:
                await emit(EventKind.LOG, f"NCCN model call failed at {node.id}: {e}; using heuristic")
                mode = "heuristic"

            if mode == "heuristic":
                idx, rationale = _heuristic_decision(node, self.state)
                think_buf = think_buf or rationale
                answer_buf = json.dumps({"chosen_option_index": idx, "one_sentence_rationale": rationale})

            if not think_buf and answer_buf:
                think_part, answer_part = split_thinking(answer_buf)
                think_buf = think_buf or think_part
                answer_buf = answer_part or answer_buf

            decision = _parse_decision(answer_buf, len(node.options))
            chosen = node.options[decision.chosen_option_index]
            reasoning = (think_buf or decision.one_sentence_rationale).strip()

            step = NCCNStep(
                node_id=node.id,
                node_title=node.title,
                chosen_option=chosen.label,
                next_node_id=chosen.next_id,
                reasoning=reasoning,
                evidence=evidence,
            )
            await emit(
                EventKind.NCCN_NODE_VISITED,
                f"NCCN ▸ {node.title} → {chosen.label}",
                {"step": step.model_dump()},
            )
            yield step
            current_id = chosen.next_id


async def _consume_interrupt() -> str | None:
    from ..agent.events import current_bus

    bus = current_bus()
    if bus is None:
        return None
    return bus.consume_interrupt()
