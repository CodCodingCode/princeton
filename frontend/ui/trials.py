"""Panel 5 — Clinical trial matches (Regeneron-first, with ClinicalTrials.gov fallback)."""

from __future__ import annotations

import streamlit as st

from . import theme


_STATUS_PILL = {
    "eligible":        ("done",  "Eligible"),
    "needs_more_data": ("warn",  "Needs data"),
    "ineligible":      ("idle",  "Ineligible"),
    "unscored":        ("idle",  "Unscored"),
}


def _render_trial_card(trial: dict) -> None:
    pill_kind, pill_label = _STATUS_PILL.get(trial.get("status", "unscored"), _STATUS_PILL["unscored"])
    phase = trial.get("phase") or "—"
    sponsor = trial.get("sponsor", "Unknown")
    nct = trial.get("nct_id", "")
    title = (trial.get("title") or "—").replace("<", "&lt;")
    url = trial.get("url") or (f"https://clinicaltrials.gov/study/{nct}" if nct else "")

    nct_html = (
        f'<div style="margin-top:4px;"><a href="{url}" target="_blank" '
        f'style="font-size:12px;color:var(--accent);text-decoration:none;">{nct} ↗</a></div>'
        if url else
        f'<div style="margin-top:4px;font-size:12px;color:var(--text-faint);">{nct}</div>'
    )

    st.markdown(
        f'<div class="nv-card">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">'
        f'<div style="flex:1;min-width:0;">'
        f'<div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;'
        f'letter-spacing:.04em;margin-bottom:4px;">{phase} · {sponsor}</div>'
        f'<div style="font-size:15px;font-weight:600;color:var(--text);line-height:1.3;">{title}</div>'
        f'{nct_html}'
        f'</div>'
        f'{theme.pill(pill_kind, pill_label)}'
        f'</div>',
        unsafe_allow_html=True,
    )

    passing = trial.get("passing_criteria") or []
    failing = trial.get("failing_criteria") or []
    unknown = trial.get("unknown_criteria") or []

    chip_html = ""
    for c in passing:
        chip_html += theme.chip(f"✓ {c}", "ok")
    for c in failing:
        chip_html += theme.chip(f"✗ {c}", "bad")
    for c in unknown:
        chip_html += theme.chip(f"? {c}", "warn")
    if chip_html:
        st.markdown(f'<div class="nv-chip-row" style="margin-top:10px;">{chip_html}</div>', unsafe_allow_html=True)

    contacts = trial.get("site_contacts") or []
    if contacts:
        with st.expander("Site contacts"):
            for c in contacts:
                parts = [c.get("name"), c.get("role"), c.get("email"), c.get("phone")]
                st.caption(" · ".join(p for p in parts if p))

    st.markdown('</div>', unsafe_allow_html=True)


def render_panel() -> None:
    trials = st.session_state.trials or []
    if not trials:
        st.markdown(
            theme.empty_state(
                "🧪",
                "Querying ClinicalTrials.gov…",
                "Recruiting melanoma trials will appear here.",
            ),
            unsafe_allow_html=True,
        )
        return

    regeneron = [t for t in trials if t.get("is_regeneron")]
    others = [t for t in trials if not t.get("is_regeneron")]

    eligible = [t for t in regeneron if t.get("status") == "eligible"]
    needs_data = [t for t in regeneron if t.get("status") == "needs_more_data"]
    ineligible = [t for t in regeneron if t.get("status") == "ineligible"]

    st.markdown(
        theme.metric_grid([
            theme.metric("Regeneron trials", str(len(regeneron))),
            theme.metric("Eligible", str(len(eligible)), "patient passes all gates"),
            theme.metric("Needs data", str(len(needs_data)), "verify with clinician"),
            theme.metric("Other recruiting", str(len(others)), "from ClinicalTrials.gov"),
        ]),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="nv-section-h" style="margin-top:6px;">Regeneron programs</div>', unsafe_allow_html=True)
    if not regeneron:
        st.caption("No Regeneron trials returned from ClinicalTrials.gov.")
    else:
        for t in eligible + needs_data:
            _render_trial_card(t)
        if ineligible:
            with st.expander(f"Ineligible ({len(ineligible)})"):
                for t in ineligible:
                    _render_trial_card(t)

    if others:
        with st.expander(f"Additional recruiting trials ({len(others)})"):
            for t in others[:25]:
                _render_trial_card(t)
