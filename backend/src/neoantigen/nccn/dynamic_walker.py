"""Cancer-agnostic railway walker - grounded in the phase-2+ RAG corpus.

Replaces the static melanoma graph ([melanoma_v2024.py]) with a dynamic,
literature-driven walker that works for any oncology case.

Flow per case:

  For each of 4 fixed phases (staging → primary → systemic → followup):
    1. Build a RAG query from primary_cancer_type + driver mutations +
       phase focus.
    2. Retrieve top-K phase-2+ citations, filtered by cancer_type.
    3. Prompt the medical model with (a) extracted patient evidence,
       (b) retrieved paper titles + snippets + PMIDs, (c) this phase's
       scope. Model returns a JSON list of 2-4 decisions.
    4. Parse → list[RailwayStep] for this phase (phase_id + phase_title
       stamped on every step). Emit RAILWAY_STEP per step.

When the model / RAG are unavailable we emit a single "needs more data"
placeholder step per phase so the UI never looks broken.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from ..agent._llm import (
    _extract_json,
    has_api_key,
    split_thinking,
    stream_with_thinking,
)
from ..agent.audit import audit
from ..agent.events import EventKind, emit
from ..models import (
    CitationRef,
    Mutation,
    PathologyFindings,
    RailwayAlternative,
    RailwayStep,
)
from ..rag import Citation, has_store as _rag_available, query_papers


# ─────────────────────────────────────────────────────────────
# Phases
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Phase:
    id: str
    title: str
    focus: str           # one-line scope description included in the prompt
    query_suffix: str    # appended to the RAG query to bias retrieval


PHASES: tuple[Phase, ...] = (
    Phase(
        id="staging",
        title="Staging & workup",
        focus=(
            "Imaging, biopsy adequacy, molecular testing, and pathology "
            "re-review decisions - the work needed to lock in the diagnosis "
            "and stage before therapy is picked."
        ),
        query_suffix="staging workup diagnosis biomarker testing",
    ),
    Phase(
        id="primary",
        title="Primary / local therapy",
        focus=(
            "Surgery, radiation, and other local control of the primary "
            "tumor or regional disease."
        ),
        query_suffix="surgery resection radiation adjuvant local therapy",
    ),
    Phase(
        id="systemic",
        title="Systemic therapy",
        focus=(
            "First-line and subsequent systemic regimens - targeted "
            "therapy, immunotherapy, chemotherapy. Line of therapy matters."
        ),
        query_suffix="first-line second-line systemic targeted immunotherapy",
    ),
    Phase(
        id="followup",
        title="Follow-up & adjuvant",
        focus=(
            "Surveillance, survivorship, adjuvant monitoring, response "
            "assessment cadence, and long-term toxicity management."
        ),
        query_suffix="surveillance follow-up adjuvant monitoring response",
    ),
)


# ─────────────────────────────────────────────────────────────
# State carried through the walk
# ─────────────────────────────────────────────────────────────


@dataclass
class PatientState:
    """Minimal patient state the walker reasons over.

    Kept separate from the legacy melanoma walker's `PatientState` so we can
    delete that file later without disturbing this module.
    """

    pathology: PathologyFindings
    mutations: list[Mutation] = field(default_factory=list)
    tumor_mutational_burden: float | None = None

    @property
    def driver_tokens(self) -> list[str]:
        out: list[str] = []
        for m in self.mutations[:6]:
            out.append(f"{m.gene} {m.label}")
        return out

    def evidence_summary(self) -> dict[str, str]:
        p = self.pathology
        fields: dict[str, str] = {
            "primary_cancer_type": p.primary_cancer_type or "unknown",
            "histology": p.histology or "unknown",
            "primary_site": p.primary_site or "unknown",
            "mutations": ", ".join(self.driver_tokens) or "none reported",
            "tumor_mutational_burden": (
                f"{self.tumor_mutational_burden:.1f} mut/Mb"
                if self.tumor_mutational_burden is not None
                else "unknown"
            ),
        }
        # Include melanoma-specific fields when populated (they naturally
        # collapse to "unknown" for non-melanoma cases).
        if p.melanoma_subtype not in {"unknown", None}:
            fields["melanoma_subtype"] = p.melanoma_subtype
        if p.breslow_thickness_mm is not None:
            fields["breslow_thickness_mm"] = f"{p.breslow_thickness_mm} mm"
        if p.ulceration is not None:
            fields["ulceration"] = "present" if p.ulceration else "absent"
        if p.mitotic_rate_per_mm2 is not None:
            fields["mitotic_rate_per_mm2"] = f"{p.mitotic_rate_per_mm2}/mm²"
        if p.tils_present != "unknown":
            fields["tils_present"] = p.tils_present
        if p.pdl1_estimate != "unknown":
            fields["pdl1_estimate"] = p.pdl1_estimate
        if p.lag3_ihc_percent is not None:
            fields["lag3_ihc_percent"] = f"{p.lag3_ihc_percent}%"
        return fields


# ─────────────────────────────────────────────────────────────
# Prompt + schema
# ─────────────────────────────────────────────────────────────


SYSTEM_PROMPT = (
    "You are an oncologist reasoning about a patient's treatment plan, "
    "grounded strictly in the phase-2+ clinical-trial literature you are "
    "given per phase. For each phase you will emit 2-4 decision steps. "
    "Every recommendation must cite at least one PMID from the retrieved "
    "papers - unless the literature genuinely doesn't cover the decision, "
    "in which case say so and mark citations as empty. Think step-by-step "
    "inside <think>...</think>, then output the JSON object."
)


class _DecisionAlt(BaseModel):
    option_label: str
    option_description: str = ""
    reason_not_chosen: str = ""


class _PhaseDecision(BaseModel):
    # Only chosen_option_label is strictly required - that's the answer.
    # Everything else defaults so a truncated or alias-drifted payload still
    # validates as a partial-but-useful decision. The walker's placeholder
    # kicks in only when there's not even a chosen_option_label.
    title: str = Field(
        default="",
        description="Short decision question, e.g. 'Choose first-line systemic therapy'",
    )
    chosen_option_label: str = Field(description="The recommended action")
    chosen_option_description: str = ""
    chosen_rationale: str = Field(
        default="",
        description="One-sentence rationale tied to patient evidence",
    )
    citation_pmids: list[str] = Field(
        default_factory=list,
        description="PMIDs from the retrieved papers that support this recommendation",
    )
    alternatives: list[_DecisionAlt] = Field(default_factory=list)


class _PhaseResponse(BaseModel):
    decisions: list[_PhaseDecision] = Field(default_factory=list)


def _build_phase_prompt(
    phase: Phase,
    cancer_type: str,
    state: PatientState,
    citations: list[Citation],
) -> str:
    ev_lines = "\n".join(f"  - {k}: {v}" for k, v in state.evidence_summary().items())
    cite_block = ""
    if citations:
        cite_lines: list[str] = []
        for i, c in enumerate(citations, 1):
            head = (
                f"  [{i}] PMID {c.pmid} · {c.title} ({c.journal} {c.year}"
                f"{', phase ' + c.trial_phase if c.trial_phase and c.trial_phase not in ('unknown', '') else ''})"
            )
            cite_lines.append(head)
            cite_lines.append(f"      {c.snippet}")
        cite_block = "Retrieved phase-2+ trial literature:\n" + "\n".join(cite_lines) + "\n\n"
    else:
        cite_block = (
            "Retrieved literature: (none - RAG store is empty or filtered out "
            "everything for this cancer type). State that the literature is "
            "thin in your rationales and leave citation_pmids empty.\n\n"
        )
    return (
        f"Phase: {phase.title}\n"
        f"Scope: {phase.focus}\n"
        f"Primary cancer type: {cancer_type}\n\n"
        f"Patient evidence:\n{ev_lines}\n\n"
        f"{cite_block}"
        "Emit a JSON object with 2-4 decision steps relevant to THIS phase. "
        "Do not re-cover decisions from other phases. Each step must have: "
        "title, chosen_option_label, chosen_option_description, chosen_rationale, "
        "citation_pmids (at least one PMID from the retrieved literature when "
        "possible), alternatives (1-3 short alternative options with "
        "reason_not_chosen).\n\n"
        "Respond with: <think>your reasoning</think>\n"
        "{\n"
        '  "decisions": [\n'
        "    {\n"
        '      "title": "…",\n'
        '      "chosen_option_label": "…",\n'
        '      "chosen_option_description": "…",\n'
        '      "chosen_rationale": "…",\n'
        '      "citation_pmids": ["12345678"],\n'
        '      "alternatives": [\n'
        '        {"option_label": "…", "option_description": "…", "reason_not_chosen": "…"}\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}"
    )


# Key aliases the model sometimes emits instead of our canonical field names.
# Empirically observed on K2-Think V2 + various Kimi checkpoints. Applied
# before pydantic validation so a single rename doesn't reject the whole
# response.
_TOP_LEVEL_LIST_ALIASES = (
    "decisions",
    "recommendations",
    "steps",
    "options",
    "plan",
    "actions",
)

_DECISION_FIELD_ALIASES: dict[str, str] = {
    "recommendation": "chosen_option_label",
    "recommended_action": "chosen_option_label",
    "recommended_option": "chosen_option_label",
    "option": "chosen_option_label",
    "action": "chosen_option_label",
    "rationale": "chosen_rationale",
    "reasoning": "chosen_rationale",
    "justification": "chosen_rationale",
    "why": "chosen_rationale",
    "description": "chosen_option_description",
    "option_description": "chosen_option_description",
    "pmids": "citation_pmids",
    "citations": "citation_pmids",
    "evidence": "citation_pmids",
    "references": "citation_pmids",
    "decision_title": "title",
    "question": "title",
    "alts": "alternatives",
    "other_options": "alternatives",
}


def _normalize_decision(d: object) -> object:
    """Rename alias keys on a single decision dict to canonical names."""
    if not isinstance(d, dict):
        return d
    out = dict(d)
    for src, dst in _DECISION_FIELD_ALIASES.items():
        if src in out and dst not in out:
            out[dst] = out.pop(src)
    # If a model emitted only chosen_option_label but no title, reuse it so
    # the schema's required-title field passes.
    if "title" not in out and "chosen_option_label" in out:
        out["title"] = out["chosen_option_label"]
    # citation_pmids sometimes comes as a comma-separated string.
    if isinstance(out.get("citation_pmids"), str):
        out["citation_pmids"] = [
            s.strip() for s in out["citation_pmids"].split(",") if s.strip()
        ]
    return out


def _unwrap_decisions(data: object) -> object:
    """Find the ``decisions`` list inside a potentially-wrapped response.

    Handles shapes like:
      * ``{"decisions": [...]}`` - canonical
      * ``{"recommendations": [...]}`` - aliased top-level key
      * ``[...]`` - bare list at the root
      * ``{"response": {"decisions": [...]}}`` - nested wrapper
    Returns a dict with a canonical ``decisions`` key, or the original data
    if no recognisable shape was found.
    """
    if isinstance(data, list):
        return {"decisions": data}
    if not isinstance(data, dict):
        return data
    # Direct alias at the top level.
    for key in _TOP_LEVEL_LIST_ALIASES:
        if key in data and isinstance(data[key], list):
            return {"decisions": data[key]}
    # One level down (e.g. {"response": {"decisions": [...]}}).
    for v in data.values():
        if isinstance(v, dict):
            for key in _TOP_LEVEL_LIST_ALIASES:
                if key in v and isinstance(v[key], list):
                    return {"decisions": v[key]}
    return data


def _parse_phase_response(answer: str) -> tuple[_PhaseResponse, str]:
    """Parse the walker's post-``</think>`` JSON into ``_PhaseResponse``.

    Returns ``(parsed, reason_if_empty)``. Reuses ``_llm._extract_json`` so
    truncated JSON (the most common failure mode on K2-Think when ``<think>``
    eats most of the token budget) gets repaired before validation. Also
    applies key aliasing so a model that wrote ``recommendations`` or
    ``rationale`` doesn't get tossed wholesale. The ``reason_if_empty``
    string is surfaced in the placeholder RailwayStep so the UI shows an
    honest reason instead of the generic "Could not parse..." message.
    """
    if not answer.strip():
        return _PhaseResponse(decisions=[]), "Model returned no answer content."
    try:
        extracted = _extract_json(answer)
    except Exception:
        return (
            _PhaseResponse(decisions=[]),
            "Model output contained no parseable JSON.",
        )
    try:
        data = json.loads(extracted)
    except json.JSONDecodeError as e:
        return _PhaseResponse(decisions=[]), f"JSON parse failed: {e.msg}."

    # Normalize: unwrap wrapper shapes and alias keys on each decision.
    data = _unwrap_decisions(data)
    if isinstance(data, dict) and isinstance(data.get("decisions"), list):
        data = {
            **data,
            "decisions": [_normalize_decision(d) for d in data["decisions"]],
        }

    try:
        return _PhaseResponse.model_validate(data), ""
    except Exception as e:
        return (
            _PhaseResponse(decisions=[]),
            f"Model JSON did not match the decision schema ({type(e).__name__}).",
        )


async def _call_phase_structured_retry(
    phase: "Phase",
    cancer_type: str,
    state: "PatientState",
    citations: list[Citation],
) -> tuple[_PhaseResponse, str]:
    """Non-streaming structured retry when the streamed walk failed to parse.

    Uses ``call_for_json`` which:
      * picks a fresh client from the round-robin key pool
      * applies lenient coercion before pydantic validation
      * retries once internally with a stronger 'just JSON' prompt

    Loses the live ``<think>`` stream on the UI, but that was already gone
    by the time we fell into this path - so it's a net win.
    """
    from ..agent._llm import call_for_json

    strict_prompt = (
        SYSTEM_PROMPT
        + " Output ONLY a valid JSON object. No prose. No markdown fences. "
        "No <think> block. Start with `{` and end with `}`."
    )
    try:
        resp = await call_for_json(
            schema=_PhaseResponse,
            system_prompt=strict_prompt,
            user_prompt=_build_phase_prompt(phase, cancer_type, state, citations),
            max_tokens=3000,
        )
        return resp, ""
    except Exception as e:
        return (
            _PhaseResponse(decisions=[]),
            f"Structured retry failed: {type(e).__name__}",
        )


# ─────────────────────────────────────────────────────────────
# RAG query assembly
# ─────────────────────────────────────────────────────────────


def _rag_query(phase: Phase, cancer_type: str, state: PatientState) -> str:
    drivers = " ".join(state.driver_tokens) or ""
    cancer_pretty = cancer_type.replace("_", " ") if cancer_type else ""
    return f"{cancer_pretty} {drivers} {phase.query_suffix}".strip()


async def _fetch_phase_citations(
    phase: Phase, cancer_type: str, state: PatientState,
) -> list[Citation]:
    if not _rag_available():
        return []
    try:
        return query_papers(
            _rag_query(phase, cancer_type, state),
            top_k=3,
            cancer_type=cancer_type if cancer_type not in {"", "unknown"} else None,
        )
    except Exception:
        return []


def _citation_ref(c: Citation) -> CitationRef:
    return CitationRef(
        pmid=c.pmid, title=c.title, year=c.year, journal=c.journal,
        snippet=c.snippet, relevance=c.relevance,
    )


def _resolve_citations(
    wanted_pmids: list[str], pool: list[Citation],
) -> list[CitationRef]:
    """Map model-emitted PMIDs back to full Citation records from the phase
    retrieval pool. Silently drops PMIDs the model hallucinated that aren't
    in the pool."""
    by_pmid = {c.pmid: c for c in pool}
    out: list[CitationRef] = []
    for pmid in wanted_pmids:
        c = by_pmid.get(str(pmid).strip())
        if c is not None:
            out.append(_citation_ref(c))
    return out


# ─────────────────────────────────────────────────────────────
# Walker
# ─────────────────────────────────────────────────────────────


@dataclass
class DynamicRailwayWalker:
    state: PatientState
    cancer_type: str = "unknown"

    async def walk(self) -> list[RailwayStep]:
        steps: list[RailwayStep] = []
        node_counter = 0

        for phase in PHASES:
            citations = await _fetch_phase_citations(phase, self.cancer_type, self.state)
            rag_query = _rag_query(phase, self.cancer_type, self.state)
            audit(
                "walker", "phase_start",
                phase_id=phase.id, cancer_type=self.cancer_type,
                citation_count=len(citations),
                citation_pmids=[c.pmid for c in citations],
                rag_query=rag_query,
            )
            if citations:
                await emit(
                    EventKind.RAG_CITATIONS,
                    f"📚 {len(citations)} phase-2+ citations for {phase.id}",
                    {
                        "phase_id": phase.id,
                        "citations": [_citation_ref(c).model_dump() for c in citations],
                    },
                )

            user_prompt = _build_phase_prompt(phase, self.cancer_type, self.state, citations)
            await emit(
                EventKind.TOOL_START,
                f"Railway ▸ {phase.title}",
                {"phase_id": phase.id, "cancer_type": self.cancer_type},
            )

            answer_buf = ""
            think_buf = ""
            mode: Literal["api", "heuristic"] = "api" if has_api_key() else "heuristic"
            call_error: str | None = None
            try:
                if mode == "api":
                    # K2-Think's <think> block routinely eats 500-1500 tokens
                    # before emitting the post-think JSON. On the current
                    # vLLM server max_total_tokens=8192 and our prompt is
                    # roughly 1000-2000 tokens, so giving the model 5500 of
                    # output headroom lets it finish <think> and still emit
                    # a complete decision JSON. Override via env when the
                    # model server changes. Too small → every phase fell
                    # back to "Needs clinician review" because the JSON
                    # block never got emitted.
                    walker_max_tokens = int(
                        os.environ.get("NEOVAX_WALKER_MAX_TOKENS", "5500")
                    )
                    # Assistant-prefill jailbreak: MediX-R1 is a reasoning
                    # model that ignores "return only JSON" instructions and
                    # writes 10,000 chars of prose before hitting max_tokens
                    # without ever emitting a `{`. By pre-populating the
                    # assistant turn with the opening of the JSON object,
                    # vLLM forces the model to continue from mid-structure:
                    # it can't escape into free-form reasoning.
                    _PREFILL = '{"decisions": ['
                    async for kind, chunk in stream_with_thinking(
                        SYSTEM_PROMPT, user_prompt,
                        max_tokens=walker_max_tokens,
                        assistant_prefill=_PREFILL,
                    ):
                        if kind == "thinking":
                            think_buf += chunk
                            await emit(
                                EventKind.THINKING_DELTA, "thinking",
                                {"phase_id": phase.id, "delta": chunk},
                            )
                        else:
                            answer_buf += chunk
                            await emit(
                                EventKind.ANSWER_DELTA, "answer",
                                {"phase_id": phase.id, "delta": chunk},
                            )
            except Exception as e:
                call_error = f"{type(e).__name__}: {e}"
                await emit(
                    EventKind.LOG,
                    f"Railway model call failed for {phase.id}: {call_error}",
                )
                audit(
                    "walker", "phase_error",
                    phase_id=phase.id, error=call_error,
                    think_so_far=think_buf[:2000],
                )

            if not think_buf and answer_buf:
                think_part, answer_part = split_thinking(answer_buf)
                think_buf = think_buf or think_part
                answer_buf = answer_part or answer_buf

            phase_steps: list[RailwayStep] = []
            parse_error: str = ""

            if mode == "api" and answer_buf:
                parsed, parse_error = _parse_phase_response(answer_buf)
                # Crucial visibility: dump the full post-<think> answer so we
                # can finally see what MediX-R1 actually returned when the
                # parse fails or yields zero decisions.
                audit(
                    "walker", "phase_parse",
                    phase_id=phase.id,
                    decisions=len(parsed.decisions),
                    parse_error=parse_error,
                    answer_len=len(answer_buf),
                    think_len=len(think_buf),
                    answer_slice=answer_buf,
                    think_slice=think_buf[:4000],
                )
                # Second-chance: if the streamed parse produced zero decisions,
                # fire a non-streaming structured retry. `call_for_json` uses
                # lenient coercion + an internal validation-error retry, and
                # picks a fresh key from the round-robin pool. Lose the live
                # <think> UI for this phase but recover the decisions.
                if not parsed.decisions and parse_error:
                    await emit(
                        EventKind.LOG,
                        f"Railway ▸ {phase.title}: streamed parse failed "
                        f"({parse_error}); retrying with structured call",
                        {"phase_id": phase.id, "retry": "structured"},
                    )
                    parsed, retry_error = await _call_phase_structured_retry(
                        phase, self.cancer_type, self.state, citations,
                    )
                    audit(
                        "walker", "phase_retry",
                        phase_id=phase.id,
                        decisions=len(parsed.decisions),
                        retry_error=retry_error,
                    )
                    if parsed.decisions:
                        parse_error = ""  # recovered
                    elif retry_error:
                        parse_error = f"{parse_error} | {retry_error}"
                for d in parsed.decisions:
                    node_counter += 1
                    step = RailwayStep(
                        node_id=f"{phase.id.upper()}_{node_counter}",
                        title=d.title or phase.title,
                        question=phase.focus,
                        chosen_option_label=d.chosen_option_label,
                        chosen_option_description=d.chosen_option_description,
                        chosen_next_id=None,
                        chosen_rationale=d.chosen_rationale,
                        reasoning=think_buf.strip(),
                        evidence=self.state.evidence_summary(),
                        citations=_resolve_citations(d.citation_pmids, citations),
                        alternatives=[
                            RailwayAlternative(
                                option_label=a.option_label,
                                option_description=a.option_description,
                                reason_not_chosen=a.reason_not_chosen,
                                next_id=None,
                            )
                            for a in d.alternatives
                        ],
                        is_terminal=False,
                        phase_id=phase.id,
                        phase_title=phase.title,
                    )
                    phase_steps.append(step)

            # Fallback: single placeholder step for this phase so the UI still
            # renders the four swim-lanes with an actionable message.
            if not phase_steps:
                node_counter += 1
                if mode == "heuristic":
                    reason = "Medical reasoning endpoint unavailable (KIMI_API_KEY unset)."
                elif call_error:
                    reason = f"Model call failed ({call_error}). Retry or reduce context."
                elif parse_error:
                    reason = parse_error
                else:
                    reason = "Model produced no decisions for this phase."
                phase_steps.append(
                    RailwayStep(
                        node_id=f"{phase.id.upper()}_{node_counter}",
                        title=phase.title,
                        question=phase.focus,
                        chosen_option_label="Needs clinician review",
                        chosen_option_description=reason,
                        chosen_next_id=None,
                        chosen_rationale=reason,
                        reasoning=think_buf.strip(),
                        evidence=self.state.evidence_summary(),
                        citations=[_citation_ref(c) for c in citations[:3]],
                        alternatives=[],
                        is_terminal=False,
                        phase_id=phase.id,
                        phase_title=phase.title,
                    )
                )

            for step in phase_steps:
                await emit(
                    EventKind.RAILWAY_STEP,
                    f"{phase.title} ▸ {step.chosen_option_label}",
                    {"step": step.model_dump()},
                )
                steps.append(step)

        return steps


_PLACEHOLDER_LABELS = {
    "needs clinician review",
    "needs more data",
    "insufficient data",
    "pending",
}


def _is_placeholder(step: RailwayStep) -> bool:
    return (step.chosen_option_label or "").strip().lower() in _PLACEHOLDER_LABELS


def _synthesize_from_evidence(
    pathology: PathologyFindings | None,
    mutations: list[Mutation],
    cancer_type: str,
) -> str:
    """Last-resort recommendation built from whatever we do know.

    Triggered only when the model walk produced nothing usable. Never
    returns an empty string, so the UI always has something to render.
    """
    bits: list[str] = []

    cancer_pretty = (cancer_type or "").replace("_", " ").strip()
    if pathology is not None and pathology.primary_site:
        site = pathology.primary_site.strip()
        bits.append(
            f"Work-up completed for {cancer_pretty or 'primary malignancy'}"
            f" (primary site: {site})."
            if cancer_pretty
            else f"Primary site: {site}."
        )
    elif cancer_pretty:
        bits.append(f"Work-up completed for {cancer_pretty}.")

    # Mutation-driven hint, phrased as a guideline direction rather than a
    # specific drug recommendation (keeps us honest about being upstream of
    # the clinician's own call).
    drivers = [m for m in mutations if m.gene]
    if drivers:
        braf_v600 = any(
            m.gene.upper() == "BRAF" and m.position == 600 for m in drivers
        )
        egfr = any(m.gene.upper() == "EGFR" for m in drivers)
        kras_g12c = any(
            m.gene.upper() == "KRAS" and m.ref_aa == "G" and m.position == 12
            for m in drivers
        )
        if braf_v600:
            bits.append(
                "BRAF V600-mutant disease - BRAF/MEK targeted therapy and"
                " anti-PD-1 immunotherapy are both on the table; sequencing"
                " is the decision point."
            )
        elif egfr:
            bits.append(
                "EGFR-mutant disease - EGFR TKI (e.g., osimertinib-class)"
                " is the guideline-directed first-line path."
            )
        elif kras_g12c:
            bits.append(
                "KRAS G12C - targeted inhibitor options (sotorasib,"
                " adagrasib) should be weighed against standard systemic"
                " therapy."
            )
        else:
            gene_list = ", ".join(
                sorted({m.gene.upper() for m in drivers[:3] if m.gene})
            )
            if gene_list:
                bits.append(
                    f"Driver mutations flagged ({gene_list}); confirm"
                    " actionability against current targeted-therapy"
                    " guidelines."
                )

    # Always close with a clinician hand-off directive so the strip never
    # reads as a prescription.
    bits.append(
        "Refer to medical oncology for guideline-directed systemic therapy"
        " selection and clinical-trial screening."
    )
    return " ".join(bits)


def final_recommendation_from_steps(
    steps: list[RailwayStep],
    *,
    pathology: PathologyFindings | None = None,
    mutations: list[Mutation] | None = None,
    cancer_type: str = "",
) -> str:
    """Compose the final-recommendation strip shown under the treatment plan.

    Priority:
      1. First real systemic-phase decision (skips placeholders).
      2. Last real non-terminal decision from any phase.
      3. Evidence-based synthesis from pathology + mutations + cancer type.
      4. Generic hand-off directive.

    Always returns a non-empty string so the UI strip has something to
    display even if every phase fell back to a placeholder.
    """
    muts = mutations or []

    real = [s for s in steps if not _is_placeholder(s) and not s.is_terminal]

    if real:
        systemic = [s for s in real if s.phase_id == "systemic"]
        head = systemic[0] if systemic else real[-1]
        return f"{head.title}: {head.chosen_option_label}"

    synthesized = _synthesize_from_evidence(pathology, muts, cancer_type)
    if synthesized:
        return synthesized

    return (
        "Refer to medical oncology for guideline-directed treatment"
        " planning and trial screening."
    )


__all__ = ["DynamicRailwayWalker", "PatientState", "PHASES", "final_recommendation_from_steps"]
