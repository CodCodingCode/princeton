"""Summary tab — landing view with hero + metric grid + final rec + activity timeline."""

from __future__ import annotations

import time

import streamlit as st

from . import theme


def render() -> None:
    path = st.session_state.pathology or {}
    pipeline = st.session_state.pipeline or {}
    candidates = (pipeline.get("candidates") or []) if pipeline else []
    cohort = st.session_state.cohort or {}
    trials = st.session_state.trials or []
    nccn_steps = st.session_state.nccn_steps or []
    started = st.session_state.started_at
    elapsed = int(time.time() - started) if started else 0

    final_rec = None
    if st.session_state.final_case:
        final_rec = (st.session_state.final_case or {}).get("final_recommendation")
    if not final_rec and nccn_steps:
        last = nccn_steps[-1]
        if (last.get("node_id") or "").upper().startswith("FINAL"):
            final_rec = last.get("chosen_option")

    # ── Hero card ────────────────────────────────────────────
    subtype = (path.get("melanoma_subtype") or "Awaiting pathology").replace("_", " ")
    t_stage = path.get("t_stage") or "—"
    n_mut = len(st.session_state.mutations)
    elapsed_str = f"{elapsed}s" if started else "—"
    st.markdown(
        f'<div class="nv-card nv-card--accent">'
        f'<div class="nv-card-title">Patient at a glance</div>'
        f'<div class="nv-card-headline">{subtype}</div>'
        f'<div style="display:flex;gap:18px;margin-top:6px;font-size:13px;color:var(--text-dim);">'
        f'<div><b style="color:var(--text);">{t_stage}</b> · T-stage</div>'
        f'<div><b style="color:var(--text);">{n_mut}</b> mutations</div>'
        f'<div><b style="color:var(--text);">{elapsed_str}</b> elapsed</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── Metric grid ──────────────────────────────────────────
    top_pep_nm = "—"
    top_pep_sub = ""
    if candidates:
        top = candidates[0].get("peptide", {})
        if top.get("score_nm") is not None:
            top_pep_nm = f"{top['score_nm']:.1f} nM"
        top_pep_sub = f"{len(candidates)} candidates"
    twin_med = cohort.get("twin_median_survival_days")
    twin_str = f"{twin_med}d" if twin_med else "—"
    eligible = sum(1 for t in trials if t.get("status") == "eligible")
    needs_data = sum(1 for t in trials if t.get("status") == "needs_more_data")

    st.markdown(
        theme.metric_grid([
            theme.metric("Mutations", str(n_mut)),
            theme.metric("NCCN nodes walked", str(len(nccn_steps))),
            theme.metric("Top peptide affinity", top_pep_nm, top_pep_sub),
            theme.metric("Twin median OS", twin_str),
            theme.metric(
                "Eligible trials",
                str(eligible),
                f"+{needs_data} need data" if needs_data else "",
            ),
        ]),
        unsafe_allow_html=True,
    )

    # ── Final recommendation ─────────────────────────────────
    if final_rec:
        st.markdown(
            f'<div class="nv-card nv-card--accent">'
            f'<div class="nv-card-title">Final recommendation</div>'
            f'<div style="font-size:18px;font-weight:600;color:var(--text);margin-top:4px;line-height:1.3;">{final_rec}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif st.session_state.run_status == "idle":
        st.markdown(
            theme.empty_state(
                "🎯",
                "No run yet",
                "Use the sidebar to run the TCGA demo or upload a case.",
            ),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            theme.empty_state(
                "🎯",
                "Final recommendation pending",
                "The agent will surface a final NCCN recommendation once the walk completes.",
            ),
            unsafe_allow_html=True,
        )

    # ── Activity timeline ────────────────────────────────────
    items: list[str] = []
    if path:
        items.append("Pathology read")
    if st.session_state.mutations:
        items.append(f"Mutations parsed ({n_mut})")
    if nccn_steps:
        items.append(f"NCCN walk ({len(nccn_steps)} nodes)")
    if st.session_state.molecules:
        items.append(f"Molecular landscape ({len(st.session_state.molecules)} drivers)")
    if pipeline:
        items.append(f"Vaccine pipeline ({len(candidates)} peptides)")
    if cohort.get("twins"):
        items.append(f"Twin matching ({len(cohort['twins'])} twins)")
    if trials:
        items.append(f"Trial matching ({len(trials)} trials)")
    if st.session_state.run_status == "done":
        items.append("Run complete")

    if items:
        st.markdown('<div class="nv-section-h" style="margin-top:18px;">Activity</div>', unsafe_allow_html=True)
        items_html = "".join(
            f'<li><span class="nv-timeline-dot"></span>{label}<span class="nv-timeline-time">✓</span></li>'
            for label in items
        )
        st.markdown(f'<ul class="nv-timeline">{items_html}</ul>', unsafe_allow_html=True)
