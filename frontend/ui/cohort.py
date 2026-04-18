"""Panel 4 — TCGA-SKCM twin cohort + Kaplan-Meier survival curve."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


def render_panel() -> None:
    cohort = st.session_state.cohort
    if not cohort:
        st.info(
            "Twin matching runs after the NCCN walker when the demo is launched on a TCGA "
            "patient. Build the cohort with `python backend/scripts/fetch_tcga_skcm.py`."
        )
        return

    cohort_size = cohort.get("cohort_size", 0)
    twins = cohort.get("twins", [])
    overall = cohort.get("overall_curve", [])
    twin_curve = cohort.get("twin_curve", [])
    median_overall = cohort.get("median_survival_days")
    median_twins = cohort.get("twin_median_survival_days")

    cols = st.columns(3)
    cols[0].metric("Cohort size", cohort_size)
    cols[1].metric("Median OS (cohort)", f"{median_overall}d" if median_overall else "—")
    cols[2].metric("Median OS (twins)", f"{median_twins}d" if median_twins else "—")

    fig = go.Figure()
    if overall:
        fig.add_trace(go.Scatter(
            x=[p["days"] for p in overall],
            y=[p["survival"] for p in overall],
            mode="lines",
            line=dict(color="#94a3b8", width=2, shape="hv"),
            name=f"Full TCGA-SKCM (n={cohort_size})",
            hovertemplate="day %{x}<br>survival %{y:.2%}<extra></extra>",
        ))
    if twin_curve:
        fig.add_trace(go.Scatter(
            x=[p["days"] for p in twin_curve],
            y=[p["survival"] for p in twin_curve],
            mode="lines",
            line=dict(color="#10b981", width=3, shape="hv"),
            name=f"Top {len(twins)} twins",
            hovertemplate="day %{x}<br>survival %{y:.2%}<extra></extra>",
        ))
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title="Days from diagnosis", gridcolor="#e5e7eb"),
        yaxis=dict(title="Overall survival", tickformat=".0%", gridcolor="#e5e7eb", range=[0, 1.02]),
        plot_bgcolor="#ffffff",
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig, use_container_width=True, key="km_curve")

    if twins:
        rows = []
        for t in twins:
            rows.append({
                "Submitter ID": t.get("submitter_id"),
                "Similarity": t.get("similarity"),
                "Matching": ", ".join(t.get("matching_features", [])),
                "Stage": t.get("stage") or "—",
                "Age": t.get("age_at_diagnosis"),
                "Vital status": t.get("vital_status"),
                "Survival (days)": t.get("survival_days"),
                "Drivers": ", ".join(t.get("mutated_drivers", [])),
            })
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.caption("No twin candidates found.")
