"""Panel 5 — Clinical trial matches (Regeneron-first, with ClinicalTrials.gov fallback)."""

from __future__ import annotations

import streamlit as st


_STATUS_BADGES = {
    "eligible": ("🟢", "Eligible"),
    "needs_more_data": ("🟡", "Needs more data"),
    "ineligible": ("🔴", "Ineligible"),
    "unscored": ("⚪", "Unscored"),
}


def _render_trial_card(trial: dict) -> None:
    emoji, status_label = _STATUS_BADGES.get(trial.get("status", "unscored"), _STATUS_BADGES["unscored"])
    phase = trial.get("phase") or "—"
    sponsor = trial.get("sponsor", "Unknown")
    nct = trial.get("nct_id", "")
    title = trial.get("title", "—")
    url = trial.get("url") or (f"https://clinicaltrials.gov/study/{nct}" if nct else None)

    header = f"{emoji} **{status_label}** · {phase} · {sponsor}"
    if url:
        st.markdown(f"{header} · [{nct}]({url})")
    else:
        st.markdown(f"{header} · {nct}")
    st.markdown(f"**{title}**")

    passing = trial.get("passing_criteria") or []
    failing = trial.get("failing_criteria") or []
    unknown = trial.get("unknown_criteria") or []

    if passing:
        st.markdown("✅ **Passing**")
        for c in passing:
            st.markdown(f"- {c}")
    if failing:
        st.markdown("❌ **Failing**")
        for c in failing:
            st.markdown(f"- {c}")
    if unknown:
        st.markdown("❓ **Clinician to verify**")
        for c in unknown:
            st.markdown(f"- {c}")

    contacts = trial.get("site_contacts") or []
    if contacts:
        with st.expander("Site contacts"):
            for c in contacts:
                parts = [c.get("name"), c.get("role"), c.get("email"), c.get("phone")]
                st.caption(" · ".join(p for p in parts if p))


def render_panel() -> None:
    trials = st.session_state.trials or []
    if not trials:
        st.caption("Querying ClinicalTrials.gov for recruiting melanoma trials…")
        return

    regeneron = [t for t in trials if t.get("is_regeneron")]
    others = [t for t in trials if not t.get("is_regeneron")]

    eligible = [t for t in regeneron if t.get("status") == "eligible"]
    needs_data = [t for t in regeneron if t.get("status") == "needs_more_data"]
    ineligible = [t for t in regeneron if t.get("status") == "ineligible"]

    cols = st.columns(4)
    cols[0].metric("Regeneron trials", len(regeneron))
    cols[1].metric("Eligible", len(eligible))
    cols[2].metric("Needs data", len(needs_data))
    cols[3].metric("Other recruiting", len(others))

    st.markdown("#### Regeneron programs")
    if not regeneron:
        st.caption("No Regeneron trials returned from ClinicalTrials.gov.")
    else:
        for t in eligible + needs_data:
            with st.container(border=True):
                _render_trial_card(t)
        if ineligible:
            with st.expander(f"Ineligible ({len(ineligible)})"):
                for t in ineligible:
                    with st.container(border=True):
                        _render_trial_card(t)

    if others:
        with st.expander(f"Additional recruiting trials ({len(others)})"):
            for t in others[:25]:
                with st.container(border=True):
                    _render_trial_card(t)
