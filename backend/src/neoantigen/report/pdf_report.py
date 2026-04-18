"""Oncologist-facing consult-note PDF builder (ReportLab).

One public call: ``build_report_pdf(case, *, chat_messages=None, events=None,
narrative_cache=None) -> bytes``. Renders a full oncology consultation summary
from the live case state, in the register of a real written consult note.

Section order:

    1.  Header                            (case id, timestamp, cancer type)
    2.  Reason for Consultation           (one-line framing)
    3.  History of Present Illness        (template narrative)
    4.  Source Documents Reviewed
    5.  Pathology Review                  (microscopic + staging sub-blocks)
    6.  Molecular & Biomarker Profile
    7.  Data Quality & Provenance
    8.  Assessment                        (LLM or template)
    9.  Treatment Plan                    (LLM or template)
    10. NCCN Reasoning Trail              (audit appendix with rationale + evidence)
    11. Clinical Trial Options            (expanded — contacts, url, Regeneron badge)
    12. Consultation Q&A Transcript      (post-case chat history)
    13. Reasoning Appendix               (railway <think> + chat thinking)
    14. Disclaimer + Signature block

Degrades gracefully: missing LLM keys, empty events list, empty chat history
and empty case fields all fall through to a short empty-state line without
failing the build.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from ..agent.events import AgentEvent, EventKind
from ..models import PatientCase, RailwayStep, TrialMatch, TrialSite
from . import narrative


# ─────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────


def _escape(s: str | None) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_UNKNOWN_TOKENS = {"unknown", "", "none", "n/a", "na"}


def _pretty_enum(val: str | None) -> str:
    if val is None:
        return "Unknown"
    s = str(val).strip()
    if not s or s.lower() in _UNKNOWN_TOKENS:
        return "Unknown"
    s = s.replace("_", " ")
    return s[:1].upper() + s[1:]


def _pretty_bool(val: bool | None) -> str:
    if val is None:
        return "Unknown"
    return "Yes" if val else "No"


def _pretty_number(val: float | int | None, suffix: str = "") -> str:
    if val is None:
        return "Unknown"
    return f"{val}{suffix}" if suffix else str(val)


def _pretty_stage(val: str | None) -> str:
    if val is None or str(val).strip().lower() in _UNKNOWN_TOKENS:
        return "Unknown"
    return str(val).strip()


def _P(text: str, styles, style_key: str = "BodyText"):
    from reportlab.platypus import Paragraph

    return Paragraph(_escape(text), styles[style_key])


def _P_raw(markup: str, styles, style_key: str = "BodyText"):
    """Paragraph where the caller has already escaped user data and is passing
    ReportLab <b>/<i>/<br/> markup through intentionally."""
    from reportlab.platypus import Paragraph

    return Paragraph(markup, styles[style_key])


# ─────────────────────────────────────────────────────────────
# Section renderers
# ─────────────────────────────────────────────────────────────


def _render_header(case: PatientCase, styles) -> list:
    from reportlab.platypus import Paragraph, Spacer

    out: list = []
    out.append(Paragraph("NeoVax Automated Oncology Consult Summary", styles["Title"]))
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    ctype = (case.primary_cancer_type or case.pathology.primary_cancer_type or "unknown").replace("_", " ")
    out.append(_P_raw(
        f"<b>Case ID:</b> {_escape(case.case_id)} · <b>Generated:</b> {_escape(ts)} · "
        f"<b>Primary cancer type:</b> {_escape(ctype)}",
        styles,
    ))
    out.append(Spacer(1, 6))
    return out


def _render_reason(case: PatientCase, styles) -> list:
    from reportlab.platypus import Spacer

    stage = _pretty_stage(case.intake.ajcc_stage)
    ctype = (case.primary_cancer_type or case.pathology.primary_cancer_type or "unknown").replace("_", " ")
    muts = ", ".join(m.full_label for m in case.mutations[:3]) if case.mutations else ""
    mut_clause = f" with {muts}" if muts else ""
    line = (
        f"Treatment planning for {stage} {ctype}{mut_clause}. "
        f"Automated NCCN railway walk, trial matching, and post-case Q&A summary."
    )
    out: list = [_P("Reason for Consultation", styles, "Heading2"), _P(line, styles), Spacer(1, 8)]
    return out


def _render_hpi(case: PatientCase, styles) -> list:
    from reportlab.platypus import Spacer

    i = case.intake
    enr = case.enrichment
    path = case.pathology

    age_phrase = (
        f"a {i.age_years}-year-old patient"
        if i.age_years is not None else "an adult patient"
    )
    stage_phrase = _pretty_stage(i.ajcc_stage)
    ctype = (case.primary_cancer_type or path.primary_cancer_type or "cancer").replace("_", " ")
    ecog_phrase = f"ECOG {i.ecog}" if i.ecog is not None else "ECOG not documented"

    prior_clauses: list[str] = []
    if enr and enr.prior_systemic_therapies:
        prior_clauses.append(
            "prior systemic therapy including " + ", ".join(enr.prior_systemic_therapies)
        )
    elif i.prior_systemic_therapy is True:
        prior_clauses.append("prior systemic therapy (agents not specified)")
    elif i.prior_systemic_therapy is False:
        prior_clauses.append("treatment-naive")

    if i.prior_anti_pd1 is True and not (enr and "anti" in " ".join(enr.prior_systemic_therapies).lower()):
        prior_clauses.append("prior anti–PD-1 exposure")
    elif i.prior_anti_pd1 is False:
        prior_clauses.append("anti–PD-1 naive")

    measurable = (
        "measurable disease by RECIST"
        if i.measurable_disease_recist is True
        else "no clearly measurable disease by RECIST"
        if i.measurable_disease_recist is False
        else "RECIST measurability not documented"
    )

    p1 = (
        f"{age_phrase.capitalize()} presents with {stage_phrase} {ctype}, {ecog_phrase}. "
        f"{(' '.join(c[0].upper() + c[1:] + '.' for c in prior_clauses)) if prior_clauses else ''} "
        f"On current records, {measurable}."
    ).strip()

    # Grab first informative lines from the raw PDF excerpt, if the structured
    # fields leave us little to say.
    excerpt = (case.pdf_text_excerpt or "").strip()
    snippet = ""
    if excerpt:
        lines = [ln.strip() for ln in excerpt.splitlines() if ln.strip()]
        snippet = " ".join(lines[:4])
        if len(snippet) > 600:
            snippet = snippet[:597] + "..."

    out: list = [_P("History of Present Illness", styles, "Heading2"), _P(p1, styles)]
    if snippet:
        out.append(_P_raw(f"<i>From submitted records:</i> {_escape(snippet)}", styles))
    out.append(Spacer(1, 8))
    return out


def _render_documents(case: PatientCase, styles) -> list:
    from reportlab.platypus import Spacer

    out: list = [_P("Source Documents Reviewed", styles, "Heading2")]
    if not case.documents:
        out.append(_P("No source documents recorded on this case.", styles))
        out.append(Spacer(1, 8))
        return out
    for d in case.documents:
        kind = _pretty_enum(d.document_kind)
        vision = " · VLM fallback" if d.used_vision_fallback else ""
        out.append(_P_raw(
            f"• <b>{_escape(d.filename)}</b> — {_escape(kind)}, "
            f"{d.page_count} page(s){_escape(vision)}",
            styles,
        ))
    out.append(Spacer(1, 8))
    return out


def _render_pathology_v2(case: PatientCase, styles) -> list:
    from reportlab.platypus import Spacer

    p = case.pathology
    i = case.intake
    out: list = [_P("Pathology Review", styles, "Heading2")]

    # Microscopic findings
    out.append(_P("Microscopic findings", styles, "Heading3"))
    micro_rows = [
        ("Histology", _pretty_enum(p.histology) if p.histology else "Unknown"),
        ("Primary site", _pretty_enum(p.primary_site) if p.primary_site else "Unknown"),
        ("Melanoma subtype", _pretty_enum(p.melanoma_subtype)),
        ("Breslow thickness", _pretty_number(p.breslow_thickness_mm, " mm")),
        ("Ulceration", _pretty_bool(p.ulceration)),
        ("Mitoses per mm²", _pretty_number(p.mitotic_rate_per_mm2)),
        ("TILs", _pretty_enum(p.tils_present)),
        ("PD-L1", _pretty_enum(p.pdl1_estimate)),
        (
            "LAG-3 IHC",
            f"{p.lag3_ihc_percent:.0f}%" if p.lag3_ihc_percent is not None else "Unknown",
        ),
        ("Extraction confidence", f"{p.confidence:.0%}" if p.confidence is not None else "Unknown"),
    ]
    for k, v in micro_rows:
        out.append(_P_raw(f"<b>{_escape(k)}:</b> {_escape(str(v))}", styles))

    # Staging
    out.append(Spacer(1, 6))
    out.append(_P("Staging & constitutional", styles, "Heading3"))
    staging_rows = [
        ("Derived T-stage", _pretty_stage(p.t_stage)),
        ("AJCC stage", _pretty_stage(i.ajcc_stage)),
        ("Age", _pretty_number(i.age_years)),
        ("ECOG", _pretty_number(i.ecog)),
        ("Measurable disease (RECIST)", _pretty_bool(i.measurable_disease_recist)),
        ("Prior systemic therapy", _pretty_bool(i.prior_systemic_therapy)),
        ("Prior anti-PD-1", _pretty_bool(i.prior_anti_pd1)),
        (
            "Life expectancy",
            _pretty_number(i.life_expectancy_months, " months")
            if i.life_expectancy_months is not None else "Unknown",
        ),
    ]
    for k, v in staging_rows:
        out.append(_P_raw(f"<b>{_escape(k)}:</b> {_escape(str(v))}", styles))

    if p.notes:
        out.append(Spacer(1, 6))
        out.append(_P_raw(f"<b>Pathology notes:</b> {_escape(p.notes)}", styles))

    out.append(Spacer(1, 8))
    return out


def _render_molecular(case: PatientCase, styles) -> list:
    from reportlab.platypus import Spacer

    out: list = [_P("Molecular & Biomarker Profile", styles, "Heading2")]
    if case.mutations:
        out.append(_P("Point mutations detected", styles, "Heading3"))
        for m in case.mutations:
            out.append(_P_raw(f"• <b>{_escape(m.gene)}</b> {_escape(m.label)}", styles))
    else:
        out.append(_P("No point mutations reported.", styles))

    enr = case.enrichment
    if enr:
        out.append(Spacer(1, 6))
        out.append(_P("Enrichment", styles, "Heading3"))
        rows = [
            ("TMB (mut/Mb)", _pretty_number(enr.tmb_mut_per_mb)),
            (
                "UV signature fraction",
                f"{enr.uv_signature_fraction:.0%}"
                if enr.uv_signature_fraction is not None else "Unknown",
            ),
            ("SNVs scored", _pretty_number(enr.total_snvs_scored)),
            (
                "Prior systemic therapies",
                ", ".join(enr.prior_systemic_therapies) if enr.prior_systemic_therapies else "Unknown",
            ),
            ("Prior anti-PD-1", _pretty_bool(enr.prior_anti_pd1)),
        ]
        for k, v in rows:
            out.append(_P_raw(f"<b>{_escape(k)}:</b> {_escape(str(v))}", styles))
        if enr.source_notes:
            notes_line = "; ".join(f"{k}: {v}" for k, v in enr.source_notes.items())
            out.append(_P_raw(f"<i>Source notes:</i> {_escape(notes_line)}", styles))
    out.append(Spacer(1, 8))
    return out


def _render_provenance(case: PatientCase, styles) -> list:
    from reportlab.platypus import Spacer

    out: list = [_P("Data Quality & Provenance", styles, "Heading2")]
    if case.conflicts:
        out.append(_P("Conflicts flagged during intake", styles, "Heading3"))
        for c in case.conflicts:
            out.append(_P_raw(f"⚠ {_escape(c)}", styles))
        out.append(Spacer(1, 4))

    if case.provenance:
        out.append(_P("Field provenance", styles, "Heading3"))
        # Compact table-like rows. Keeping text layout avoids a ReportLab Table
        # dependency and looks fine for consult-note purposes.
        for p in case.provenance[:40]:
            page = f", p.{p.page_number}" if p.page_number is not None else ""
            out.append(_P_raw(
                f"<b>{_escape(p.field)}</b> = {_escape(p.value)} "
                f"<i>({_escape(p.filename)}{_escape(page)})</i>",
                styles,
            ))
        if len(case.provenance) > 40:
            out.append(_P(f"(+{len(case.provenance) - 40} more provenance entries)", styles))
    if not case.conflicts and not case.provenance:
        out.append(_P("No conflicts or provenance records on this case.", styles))
    out.append(Spacer(1, 8))
    return out


def _render_narrative_section(
    title: str, paragraphs: list[str], styles
) -> list:
    from reportlab.platypus import Spacer

    out: list = [_P(title, styles, "Heading2")]
    if not paragraphs:
        out.append(_P("Narrative unavailable.", styles))
    for para in paragraphs:
        # Preserve inline newlines by converting to <br/>; escape everything else.
        escaped = _escape(para).replace("\n", "<br/>")
        out.append(_P_raw(escaped, styles))
        out.append(Spacer(1, 4))
    out.append(Spacer(1, 6))
    return out


def _render_railway_v2(case: PatientCase, styles) -> list:
    from reportlab.platypus import Spacer

    out: list = [_P("NCCN Reasoning Trail", styles, "Heading2")]
    if not case.railway or not case.railway.steps:
        out.append(_P("No railway walked for this case.", styles))
        out.append(Spacer(1, 8))
        return out

    current_phase = object()  # sentinel
    for i, step in enumerate(case.railway.steps, 1):
        step: RailwayStep
        phase_key = (step.phase_id, step.phase_title)
        if phase_key != current_phase:
            current_phase = phase_key
            if step.phase_title or step.phase_id:
                out.append(Spacer(1, 4))
                out.append(_P_raw(
                    f"<b>Phase: {_escape(step.phase_title or step.phase_id)}</b>",
                    styles,
                ))

        out.append(Spacer(1, 4))
        out.append(_P_raw(
            f"<b>Step {i}. [{_escape(step.node_id)}] {_escape(step.title)}</b>",
            styles,
        ))
        if step.question:
            out.append(_P_raw(f"<i>Question:</i> {_escape(step.question)}", styles))
        out.append(_P_raw(
            f"<b>Chosen:</b> {_escape(step.chosen_option_label)}",
            styles,
        ))
        if step.chosen_option_description:
            out.append(_P_raw(
                f"<i>Definition:</i> {_escape(step.chosen_option_description)}",
                styles,
            ))
        if step.chosen_rationale:
            out.append(_P_raw(
                f"<i>Rationale:</i> {_escape(step.chosen_rationale)}",
                styles,
            ))
        if step.reasoning:
            reasoning = step.reasoning.strip()
            if len(reasoning) > 600:
                reasoning = reasoning[:597] + "..."
            out.append(_P_raw(
                f"<i>Reasoning:</i> {_escape(reasoning)}",
                styles,
            ))
        if step.evidence:
            evid_bits = [f"{k}: {v}" for k, v in list(step.evidence.items())[:6]]
            out.append(_P_raw(
                f"<i>Evidence:</i> {_escape('; '.join(evid_bits))}",
                styles,
            ))
        if step.alternatives:
            out.append(_P_raw("<i>Alternatives considered:</i>", styles))
            for alt in step.alternatives:
                reason = (alt.reason_not_chosen or "").strip()
                if reason:
                    reason = reason[:1].upper() + reason[1:]
                    if reason[-1] not in ".!?":
                        reason += "."
                    out.append(_P_raw(
                        f"&nbsp;&nbsp;• <b>{_escape(alt.option_label)}.</b> {_escape(reason)}",
                        styles,
                    ))
                else:
                    out.append(_P_raw(
                        f"&nbsp;&nbsp;• <b>{_escape(alt.option_label)}.</b>",
                        styles,
                    ))
        if step.citations:
            out.append(_P_raw("<i>Literature:</i>", styles))
            for c in step.citations:
                journal_year = ", ".join(x for x in (c.journal, c.year) if x)
                out.append(_P_raw(
                    f"&nbsp;&nbsp;• {_escape(c.title)} "
                    f"(PMID {_escape(c.pmid)}{', ' + _escape(journal_year) if journal_year else ''})",
                    styles,
                ))

    if case.railway.final_recommendation:
        out.append(Spacer(1, 6))
        out.append(_P_raw(
            f"<b>Final recommendation (railway):</b> {_escape(case.railway.final_recommendation)}",
            styles,
        ))
    out.append(Spacer(1, 8))
    return out


def _render_trials_v2(case: PatientCase, styles) -> list:
    from reportlab.platypus import Spacer

    out: list = [_P("Clinical Trial Options", styles, "Heading2")]
    if not case.trial_matches:
        out.append(_P("No clinical trials were matched for this case.", styles))
        out.append(Spacer(1, 8))
        return out

    sites_by_nct: dict[str, list[TrialSite]] = {}
    for s in case.trial_sites:
        sites_by_nct.setdefault(s.nct_id, []).append(s)

    status_label = {
        "eligible": "Eligible",
        "ineligible": "Not eligible",
        "needs_more_data": "Needs more data",
        "unscored": "Not scored",
    }

    for m in case.trial_matches:
        m: TrialMatch
        out.append(Spacer(1, 6))
        badge = " · <b>REGENERON</b>" if m.is_regeneron else ""
        header = (
            f"<b>{_escape(m.nct_id)}</b> — {_escape(m.title)}{badge}"
        )
        out.append(_P_raw(header, styles))
        meta_bits = [
            f"<i>Eligibility:</i> {_escape(status_label.get(m.status, m.status))}",
            f"<i>Phase:</i> {_escape(m.phase or 'Unknown')}",
            f"<i>Sponsor:</i> {_escape(m.sponsor or 'Unknown')}",
        ]
        if m.overall_status:
            meta_bits.append(f"<i>Status:</i> {_escape(m.overall_status)}")
        if m.url:
            meta_bits.append(f"<i>Link:</i> {_escape(m.url)}")
        out.append(_P_raw(" · ".join(meta_bits), styles))

        if m.passing_criteria:
            out.append(_P_raw(
                "<i>Passing:</i> " + "; ".join(_escape(x) for x in m.passing_criteria),
                styles,
            ))
        if m.failing_criteria:
            out.append(_P_raw(
                "<i>Failing:</i> " + "; ".join(_escape(x) for x in m.failing_criteria),
                styles,
            ))
        if m.unknown_criteria:
            out.append(_P_raw(
                "<i>Need more data:</i> " + "; ".join(_escape(x) for x in m.unknown_criteria),
                styles,
            ))

        sites = sites_by_nct.get(m.nct_id, [])
        if sites:
            out.append(_P_raw("<i>Recruiting sites:</i>", styles))
            for s in sites[:15]:
                city_line = ", ".join(part for part in (s.city, s.state, s.country) if part)
                status = _pretty_enum(s.status)
                contact_bits: list[str] = []
                if s.contact_name:
                    contact_bits.append(s.contact_name)
                if s.contact_phone:
                    contact_bits.append(s.contact_phone)
                if s.contact_email:
                    contact_bits.append(s.contact_email)
                contact_line = f" — contact: {', '.join(contact_bits)}" if contact_bits else ""
                out.append(_P_raw(
                    f"&nbsp;&nbsp;• {_escape(s.facility or 'Unknown site')} — "
                    f"{_escape(city_line or 'Unknown location')} "
                    f"[{_escape(status)}]{_escape(contact_line)}",
                    styles,
                ))
            if len(sites) > 15:
                out.append(_P(f"    (+{len(sites) - 15} additional site(s) not shown)", styles))
    out.append(Spacer(1, 8))
    return out


def _render_chat_transcript(chat_messages, styles) -> list:
    from reportlab.platypus import Spacer

    out: list = [_P("Consultation Q&A Transcript", styles, "Heading2")]
    if not chat_messages:
        out.append(_P("No post-case questions were recorded for this patient.", styles))
        out.append(Spacer(1, 8))
        return out

    shown = 0
    for msg in chat_messages:
        role = getattr(msg, "role", None)
        content = (getattr(msg, "content", "") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        prefix = "<b>Q.</b>" if role == "user" else "<b>A.</b>"
        out.append(Spacer(1, 3))
        out.append(_P_raw(
            f"{prefix} {_escape(content)}",
            styles,
        ))
        citations = getattr(msg, "citations", None) or []
        if role == "assistant" and citations:
            cite_lines = []
            for c in citations[:5]:
                if isinstance(c, dict):
                    title = c.get("title") or c.get("pmid") or ""
                    pmid = c.get("pmid") or ""
                    if title or pmid:
                        cite_lines.append(f"{title} (PMID {pmid})")
            if cite_lines:
                out.append(_P_raw(
                    "&nbsp;&nbsp;<i>Citations:</i> " + _escape("; ".join(cite_lines)),
                    styles,
                ))
        shown += 1
    if shown == 0:
        out.append(_P("No post-case questions were recorded for this patient.", styles))
    out.append(Spacer(1, 8))
    return out


def _reasoning_chunks_from_events(events: list[AgentEvent]) -> list[str]:
    """Collapse THINKING_DELTA events into a single <think> transcript, grouped
    by consecutive-same-label runs (the label is the emitting phase/node)."""
    if not events:
        return []
    blocks: list[tuple[str, list[str]]] = []
    for ev in events:
        if ev.kind != EventKind.THINKING_DELTA:
            continue
        delta = (ev.payload or {}).get("delta") or ""
        if not delta:
            continue
        label = ev.label or "thinking"
        if blocks and blocks[-1][0] == label:
            blocks[-1][1].append(delta)
        else:
            blocks.append((label, [delta]))
    return ["[" + label + "]\n" + "".join(parts) for label, parts in blocks]


def _render_reasoning_appendix(
    events: list[AgentEvent] | None,
    chat_messages: list[Any] | None,
    styles,
) -> list:
    from reportlab.platypus import PageBreak, Spacer

    out: list = [PageBreak(), _P("Reasoning Appendix", styles, "Heading2"),
                  _P("Model reasoning captured during case build and chat. "
                     "Included for audit; not part of the clinical note.",
                     styles)]

    rail_chunks = _reasoning_chunks_from_events(events or [])
    if rail_chunks:
        out.append(Spacer(1, 4))
        out.append(_P("Railway walker <think> stream", styles, "Heading3"))
        for block in rail_chunks:
            text = block.strip()
            if len(text) > 4000:
                text = text[:3997] + "..."
            # Preserve newlines without blowing up the layout.
            escaped = _escape(text).replace("\n", "<br/>")
            out.append(_P_raw(escaped, styles))
            out.append(Spacer(1, 4))

    if chat_messages:
        thinking_msgs = [
            m for m in chat_messages
            if getattr(m, "role", None) == "assistant"
            and (getattr(m, "thinking", "") or "").strip()
        ]
        if thinking_msgs:
            out.append(Spacer(1, 6))
            out.append(_P("Chat agent <think> stream", styles, "Heading3"))
            for i, m in enumerate(thinking_msgs, 1):
                text = (m.thinking or "").strip()
                if len(text) > 3000:
                    text = text[:2997] + "..."
                escaped = _escape(text).replace("\n", "<br/>")
                out.append(_P_raw(f"<b>Turn {i}:</b> {escaped}", styles))
                out.append(Spacer(1, 3))

    if not rail_chunks and not (chat_messages and any(
        getattr(m, "thinking", "") for m in chat_messages
    )):
        out.append(_P("No reasoning traces were captured for this case.", styles))
    return out


def _render_signature(styles) -> list:
    from reportlab.platypus import Spacer

    out: list = [Spacer(1, 14)]
    out.append(_P_raw(
        "<i>This report is research-grade output from an automated copilot. "
        "Clinical decisions require board-certified oncologist review.</i>",
        styles,
    ))
    out.append(Spacer(1, 10))
    out.append(_P_raw(
        "— Generated by NeoVax. Not a substitute for a licensed oncologist.",
        styles,
    ))
    return out


# ─────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────


def build_report_pdf(
    case: PatientCase,
    *,
    chat_messages: list[Any] | None = None,
    events: list[AgentEvent] | None = None,
    narrative_cache: dict[str, list[str]] | None = None,
) -> bytes:
    """Render a PatientCase (plus optional session data) into a consult-note PDF.

    ``chat_messages``: list[ChatMessage] from the per-case chat agent. Drives
    the Q&A transcript section and the chat portion of the reasoning appendix.

    ``events``: optional list[AgentEvent] — typically ``CaseRecord.replay``.
    THINKING_DELTA entries drive the railway-reasoning appendix.

    ``narrative_cache``: optional dict (typically ``CaseRecord.narrative_cache``)
    used to memoize Assessment + Treatment Plan prose across re-downloads so we
    only hit the LLM once per case.
    """
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        title=f"NeoVax consult summary — case {case.case_id}",
        author="NeoVax",
        leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54,
    )
    styles = getSampleStyleSheet()

    # Memoized narrative generation — cache is keyed by section name so
    # re-downloads of the same case are zero-cost.
    cache = narrative_cache if narrative_cache is not None else {}
    if "assessment" not in cache:
        cache["assessment"] = narrative.assessment_paragraphs(case)
    if "plan" not in cache:
        cache["plan"] = narrative.treatment_plan_paragraphs(case)
    assessment = cache["assessment"]
    plan = cache["plan"]

    story: list = []
    story.extend(_render_header(case, styles))
    story.append(Spacer(1, 6))
    story.extend(_render_reason(case, styles))
    story.extend(_render_hpi(case, styles))
    story.extend(_render_documents(case, styles))
    story.extend(_render_pathology_v2(case, styles))
    story.extend(_render_molecular(case, styles))
    story.extend(_render_provenance(case, styles))
    story.extend(_render_narrative_section("Assessment", assessment, styles))
    story.extend(_render_narrative_section("Treatment Plan", plan, styles))
    story.extend(_render_railway_v2(case, styles))
    story.extend(_render_trials_v2(case, styles))
    story.extend(_render_chat_transcript(chat_messages or [], styles))
    story.extend(_render_reasoning_appendix(events, chat_messages, styles))
    story.extend(_render_signature(styles))

    doc.build(story)
    return buf.getvalue()


__all__ = ["build_report_pdf"]
