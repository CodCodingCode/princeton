"""Oncologist-facing PDF report builder — reportlab-based.

One call: ``build_report_pdf(case) -> bytes``. Sections in order:

  1. Case header + extracted pathology + intake.
  2. NCCN railway — text outline of the chosen path, rationale, and the
     alternative branches considered with reasons against.
  3. Matched clinical trials — eligibility verdict + nearest sites.
  4. PubMed citations attached to any walked node.

Keeps it print-friendly. No branding art, just typography.
"""

from __future__ import annotations

import io
from datetime import datetime

from ..models import PatientCase, RailwayStep, TrialMatch, TrialSite


def _escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _paragraph(text: str, style):
    from reportlab.platypus import Paragraph

    return Paragraph(_escape(text), style)


def _render_pathology(case: PatientCase, styles) -> list:
    from reportlab.platypus import Paragraph, Spacer

    p = case.pathology
    i = case.intake
    rows = [
        ("Melanoma subtype", p.melanoma_subtype or "unknown"),
        ("Breslow thickness", f"{p.breslow_thickness_mm} mm" if p.breslow_thickness_mm is not None else "unknown"),
        ("Ulceration", str(p.ulceration) if p.ulceration is not None else "unknown"),
        ("Derived T-stage", p.t_stage),
        ("AJCC stage", i.ajcc_stage or "unknown"),
        ("Mitoses per mm²", str(p.mitotic_rate_per_mm2) if p.mitotic_rate_per_mm2 is not None else "unknown"),
        ("TILs", p.tils_present),
        ("PD-L1", p.pdl1_estimate),
        ("LAG-3 IHC", f"{p.lag3_ihc_percent:.0f}%" if p.lag3_ihc_percent is not None else "unknown"),
        ("Age", str(i.age_years) if i.age_years is not None else "unknown"),
        ("ECOG", str(i.ecog) if i.ecog is not None else "unknown"),
        ("Measurable disease (RECIST)", str(i.measurable_disease_recist) if i.measurable_disease_recist is not None else "unknown"),
        ("Prior systemic therapy", str(i.prior_systemic_therapy) if i.prior_systemic_therapy is not None else "unknown"),
        ("Prior anti-PD-1", str(i.prior_anti_pd1) if i.prior_anti_pd1 is not None else "unknown"),
    ]
    out: list = [Paragraph("Extracted pathology + intake", styles["Heading2"])]
    for k, v in rows:
        out.append(Paragraph(f"<b>{_escape(k)}:</b> {_escape(str(v))}", styles["BodyText"]))
    if p.notes:
        out.append(Spacer(1, 6))
        out.append(Paragraph(f"<b>Notes:</b> {_escape(p.notes)}", styles["BodyText"]))

    if case.mutations:
        out.append(Spacer(1, 8))
        out.append(Paragraph("Point mutations detected", styles["Heading3"]))
        for m in case.mutations:
            out.append(Paragraph(f"• {m.gene} {m.label}", styles["BodyText"]))
    return out


def _render_railway(case: PatientCase, styles) -> list:
    from reportlab.platypus import Paragraph, Spacer

    out: list = [Paragraph("NCCN treatment railway", styles["Heading2"])]
    if not case.railway or not case.railway.steps:
        out.append(Paragraph("No railway walked.", styles["BodyText"]))
        return out

    for i, step in enumerate(case.railway.steps, 1):
        step: RailwayStep
        out.append(Spacer(1, 6))
        out.append(Paragraph(
            f"<b>Step {i}. [{_escape(step.node_id)}] {_escape(step.title)}</b>",
            styles["BodyText"],
        ))
        out.append(Paragraph(f"<i>Question:</i> {_escape(step.question)}", styles["BodyText"]))
        out.append(Paragraph(
            f"<b>Chosen:</b> {_escape(step.chosen_option_label)}", styles["BodyText"],
        ))
        if step.chosen_rationale:
            out.append(Paragraph(
                f"<i>Rationale:</i> {_escape(step.chosen_rationale)}", styles["BodyText"],
            ))
        if step.alternatives:
            out.append(Paragraph("<i>Alternatives considered:</i>", styles["BodyText"]))
            for alt in step.alternatives:
                out.append(Paragraph(
                    f"&nbsp;&nbsp;• <b>{_escape(alt.option_label)}</b> — "
                    f"{_escape(alt.reason_not_chosen or '—')}",
                    styles["BodyText"],
                ))
        if step.citations:
            out.append(Paragraph("<i>Literature:</i>", styles["BodyText"]))
            for c in step.citations:
                out.append(Paragraph(
                    f"&nbsp;&nbsp;• {_escape(c.title)} "
                    f"(PMID {_escape(c.pmid)}, {_escape(c.journal or '')} {_escape(c.year or '')})",
                    styles["BodyText"],
                ))

    if case.railway.final_recommendation:
        out.append(Spacer(1, 8))
        out.append(Paragraph(
            f"<b>Final recommendation:</b> {_escape(case.railway.final_recommendation)}",
            styles["BodyText"],
        ))
    return out


def _render_trials(case: PatientCase, styles) -> list:
    from reportlab.platypus import Paragraph, Spacer

    out: list = [Paragraph("Matched clinical trials", styles["Heading2"])]
    if not case.trial_matches:
        out.append(Paragraph("No matched trials.", styles["BodyText"]))
        return out

    sites_by_nct: dict[str, list[TrialSite]] = {}
    for s in case.trial_sites:
        sites_by_nct.setdefault(s.nct_id, []).append(s)

    for m in case.trial_matches:
        m: TrialMatch
        out.append(Spacer(1, 6))
        out.append(Paragraph(
            f"<b>{_escape(m.nct_id)}</b> — {_escape(m.title)}",
            styles["BodyText"],
        ))
        out.append(Paragraph(
            f"<i>Status:</i> {_escape(m.status)} · "
            f"<i>Phase:</i> {_escape(m.phase or '')} · "
            f"<i>Sponsor:</i> {_escape(m.sponsor)}",
            styles["BodyText"],
        ))
        if m.passing_criteria:
            out.append(Paragraph(
                "<i>Passing:</i> " + "; ".join(_escape(x) for x in m.passing_criteria),
                styles["BodyText"],
            ))
        if m.failing_criteria:
            out.append(Paragraph(
                "<i>Failing:</i> " + "; ".join(_escape(x) for x in m.failing_criteria),
                styles["BodyText"],
            ))
        if m.unknown_criteria:
            out.append(Paragraph(
                "<i>Need more data:</i> " + "; ".join(_escape(x) for x in m.unknown_criteria),
                styles["BodyText"],
            ))

        sites = sites_by_nct.get(m.nct_id, [])
        if sites:
            out.append(Paragraph("<i>Recruiting sites:</i>", styles["BodyText"]))
            for s in sites[:8]:
                out.append(Paragraph(
                    f"&nbsp;&nbsp;• {_escape(s.facility)} — "
                    f"{_escape(s.city)}, {_escape(s.state)}, {_escape(s.country)} "
                    f"[{_escape(s.status)}]",
                    styles["BodyText"],
                ))
    return out


def build_report_pdf(case: PatientCase) -> bytes:
    """Render a PatientCase into an oncologist-facing PDF."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        title=f"NeoVax case {case.case_id}",
        author="NeoVax",
        leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54,
    )
    styles = getSampleStyleSheet()

    story: list = []
    story.append(Paragraph(f"NeoVax case {case.case_id}", styles["Title"]))
    story.append(Paragraph(
        f"Generated {datetime.utcnow().isoformat(timespec='seconds')}Z — "
        f"oncologist-facing treatment summary",
        styles["BodyText"],
    ))
    story.append(Spacer(1, 12))
    story.extend(_render_pathology(case, styles))
    story.append(Spacer(1, 12))
    story.extend(_render_railway(case, styles))
    story.append(Spacer(1, 12))
    story.extend(_render_trials(case, styles))
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "<i>This report is research-grade output from an automated copilot. "
        "Clinical decisions require board-certified oncologist review.</i>",
        styles["BodyText"],
    ))
    doc.build(story)
    return buf.getvalue()


__all__ = ["build_report_pdf"]
