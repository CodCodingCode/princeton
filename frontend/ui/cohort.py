"""Panel 4 — TCGA-SKCM twin cohort + Kaplan-Meier survival curve."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from . import theme


def render_panel() -> None:
    cohort = st.session_state.cohort
    if not cohort:
        st.markdown(
            theme.empty_state(
                "🧑‍🤝‍🧑",
                "No cohort data yet",
                "Twin matching runs after the NCCN walker for TCGA patients. "
                "Build with <code>python backend/scripts/fetch_tcga_skcm.py</code>.",
            ),
            unsafe_allow_html=True,
        )
        return

    cohort_size = cohort.get("cohort_size", 0)
    twins = cohort.get("twins", [])
    overall = cohort.get("overall_curve", [])
    twin_curve = cohort.get("twin_curve", [])
    median_overall = cohort.get("median_survival_days")
    median_twins = cohort.get("twin_median_survival_days")

    _render_hero(median_overall, median_twins, len(twins), cohort_size)
    _render_metric_strip(cohort_size, len(twins), median_overall, median_twins)
    _render_km_chart(overall, twin_curve, cohort_size, len(twins), median_overall, median_twins)
    _render_twin_section(twins)


# ─────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────


def _render_hero(median_overall, median_twins, n_twins: int, cohort_size: int) -> None:
    if median_overall and median_twins:
        delta = median_twins - median_overall
        if delta >= 0:
            kind = "ok"
            arrow = "▲"
            verb = "longer"
        else:
            kind = "bad"
            arrow = "▼"
            verb = "shorter"
        delta_years = abs(delta) / 365.25
        headline = f"{arrow} {delta_years:.1f} years {verb} median OS vs full cohort"
        sub = (
            f"Patients clinically similar to this case (n={n_twins} of {cohort_size}) "
            f"survived a median of <b>{_yrs(median_twins)}</b> from diagnosis, "
            f"compared to <b>{_yrs(median_overall)}</b> across the entire TCGA-SKCM cohort."
        )
        chip_html = theme.chip(f"{'+' if delta >= 0 else ''}{delta} d", kind)
    else:
        kind = "info"
        headline = "Twin cohort assembled"
        sub = (
            f"Top {n_twins} most similar TCGA-SKCM patients out of {cohort_size}. "
            "Median OS not yet estimable (insufficient events)."
        )
        chip_html = theme.chip("pending", "info")

    st.markdown(
        f"""
        <div class="nv-card nv-card--{'accent' if kind == 'ok' else 'info'}" style="margin-bottom:18px">
          <div class="nv-card-title">Prognostic anchor · TCGA-SKCM</div>
          <div class="nv-card-headline">{headline}</div>
          <div style="color:var(--text-dim); font-size:13px; line-height:1.55; margin-top:6px">{sub}</div>
          <div style="margin-top:10px">{chip_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# Metric strip
# ─────────────────────────────────────────────────────────────


def _render_metric_strip(cohort_size: int, n_twins: int, median_overall, median_twins) -> None:
    twin_pct = (n_twins / cohort_size * 100) if cohort_size else 0.0
    delta_sub = ""
    if median_twins and median_overall:
        d = median_twins - median_overall
        sign = "+" if d >= 0 else ""
        delta_sub = f"{sign}{d}d · {sign}{d/365.25:.1f} yr"

    metrics = [
        theme.metric("Cohort", f"{cohort_size}", "TCGA-SKCM patients"),
        theme.metric("Twins", f"{n_twins}", f"top {twin_pct:.1f}% of cohort"),
        theme.metric(
            "Cohort median OS",
            _yrs(median_overall) if median_overall else "—",
            f"{median_overall} days" if median_overall else "—",
        ),
        theme.metric(
            "Twin median OS",
            _yrs(median_twins) if median_twins else "—",
            delta_sub or ("—" if not median_twins else f"{median_twins} days"),
        ),
    ]
    st.markdown(theme.metric_grid(metrics), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Kaplan–Meier chart
# ─────────────────────────────────────────────────────────────


def _render_km_chart(
    overall, twin_curve, cohort_size: int, n_twins: int, median_overall, median_twins
) -> None:
    st.markdown('<div class="nv-section-h">Overall survival</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="nv-section-sub">Kaplan–Meier estimate. '
        'Vertical drop lines mark median survival (50% surviving).</div>',
        unsafe_allow_html=True,
    )

    fig = go.Figure()

    if overall:
        fig.add_trace(go.Scatter(
            x=[p["days"] for p in overall],
            y=[p["survival"] for p in overall],
            mode="lines",
            line=dict(color=theme.COLORS["text_faint"], width=2, shape="hv"),
            name=f"Full cohort (n={cohort_size})",
            hovertemplate="day %{x}<br>survival %{y:.1%}<extra>cohort</extra>",
        ))
    if twin_curve:
        fig.add_trace(go.Scatter(
            x=[p["days"] for p in twin_curve],
            y=[p["survival"] for p in twin_curve],
            mode="lines",
            line=dict(color=theme.COLORS["accent"], width=3, shape="hv"),
            name=f"Twins (n={n_twins})",
            hovertemplate="day %{x}<br>survival %{y:.1%}<extra>twins</extra>",
        ))

    # 50% reference line
    fig.add_hline(
        y=0.5, line_width=1, line_dash="dot",
        line_color=theme.COLORS["border_st"],
        annotation_text="50% surviving",
        annotation_position="right",
        annotation=dict(font=dict(size=10, color=theme.COLORS["text_faint"])),
    )

    # Median drop-lines
    if median_overall:
        fig.add_shape(
            type="line",
            x0=median_overall, x1=median_overall, y0=0, y1=0.5,
            line=dict(color=theme.COLORS["text_faint"], width=1, dash="dash"),
        )
        fig.add_annotation(
            x=median_overall, y=0.04,
            text=f"cohort: {_yrs(median_overall)}",
            showarrow=False,
            font=dict(size=10, color=theme.COLORS["text_dim"]),
            bgcolor=theme.COLORS["surface"],
            bordercolor=theme.COLORS["border"], borderwidth=1, borderpad=3,
        )
    if median_twins:
        fig.add_shape(
            type="line",
            x0=median_twins, x1=median_twins, y0=0, y1=0.5,
            line=dict(color=theme.COLORS["accent"], width=1.5, dash="dash"),
        )
        fig.add_annotation(
            x=median_twins, y=0.12,
            text=f"twins: {_yrs(median_twins)}",
            showarrow=False,
            font=dict(size=10, color=theme.COLORS["accent"]),
            bgcolor=theme.COLORS["accent_soft"],
            bordercolor=theme.COLORS["accent"], borderwidth=1, borderpad=3,
        )

    fig.update_layout(
        **theme.plotly_theme(
            height=400,
            xaxis=dict(title="Days from diagnosis", gridcolor=theme.COLORS["border"]),
            yaxis=dict(
                title="Overall survival",
                tickformat=".0%",
                gridcolor=theme.COLORS["border"],
                range=[0, 1.02],
            ),
            legend=dict(orientation="h", y=-0.18, x=0),
            margin=dict(l=10, r=70, t=10, b=10),
        )
    )
    st.plotly_chart(fig, use_container_width=True, key="km_curve")


# ─────────────────────────────────────────────────────────────
# Twin cards + full-table expander
# ─────────────────────────────────────────────────────────────


def _render_twin_section(twins: list) -> None:
    if not twins:
        st.caption("No twin candidates found.")
        return

    st.markdown(
        '<div class="nv-section-h" style="margin-top:18px">Closest twins</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="nv-section-sub">Top matches by similarity score. '
        'Hover the chips to see which clinical features drove the match.</div>',
        unsafe_allow_html=True,
    )

    top_n = min(5, len(twins))
    cols = st.columns(top_n)
    for col, twin in zip(cols, twins[:top_n]):
        with col:
            st.markdown(_twin_card_html(twin), unsafe_allow_html=True)

    if len(twins) > top_n:
        with st.expander(f"All {len(twins)} twin matches", expanded=False):
            rows = [{
                "Submitter": t.get("submitter_id"),
                "Similarity": round(t.get("similarity", 0), 3),
                "Matching": ", ".join(t.get("matching_features", [])),
                "Stage": t.get("stage") or "—",
                "Age": t.get("age_at_diagnosis") or "—",
                "Vital": t.get("vital_status") or "—",
                "Survival": _yrs(t.get("survival_days")) if t.get("survival_days") else "—",
                "Drivers": ", ".join(t.get("mutated_drivers", [])) or "—",
            } for t in twins]
            st.dataframe(rows, hide_index=True, use_container_width=True)


def _twin_card_html(twin: dict) -> str:
    sim = float(twin.get("similarity") or 0.0)
    sim_pct = max(0.0, min(1.0, sim)) * 100
    submitter = twin.get("submitter_id") or "—"
    short_id = submitter.replace("TCGA-", "")  # save horizontal space
    stage = twin.get("stage") or "—"
    age = twin.get("age_at_diagnosis")
    vital = (twin.get("vital_status") or "").lower()
    surv_days = twin.get("survival_days")

    if vital == "alive":
        vital_chip = theme.chip("alive", "ok")
    elif vital == "dead":
        vital_chip = theme.chip("deceased", "bad")
    else:
        vital_chip = theme.chip("unknown", "")

    surv_html = (
        f'<div style="font-size:18px; font-weight:600; color:var(--text); margin-top:4px">{_yrs(surv_days)}</div>'
        f'<div style="font-size:11px; color:var(--text-faint)">{surv_days} days from diagnosis</div>'
    ) if surv_days else (
        '<div style="font-size:13px; color:var(--text-faint); margin-top:4px">survival n/a</div>'
    )

    feature_chips = "".join(theme.chip(f, "info") for f in twin.get("matching_features", []))
    if not feature_chips:
        feature_chips = '<span style="font-size:11px; color:var(--text-faint)">no shared drivers</span>'

    drivers = twin.get("mutated_drivers", [])
    drivers_html = ""
    if drivers:
        drivers_html = (
            '<div style="font-size:10px; color:var(--text-faint); text-transform:uppercase; '
            'letter-spacing:0.05em; margin-top:10px">drivers</div>'
            '<div style="font-size:11px; color:var(--text-dim); font-family:JetBrains Mono, monospace">'
            f"{' · '.join(drivers)}</div>"
        )

    age_str = f"{age}y" if age else "age —"

    return f"""
    <div class="nv-card" style="margin-bottom:0; padding:14px">
      <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:6px">
        <div style="font-size:12px; font-weight:600; color:var(--text); font-family:JetBrains Mono, monospace">{short_id}</div>
        {vital_chip}
      </div>
      <div style="font-size:11px; color:var(--text-faint); margin-top:2px">stage {stage} · {age_str}</div>
      {surv_html}
      <div style="margin-top:10px">
        <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--text-faint); text-transform:uppercase; letter-spacing:0.05em">
          <span>similarity</span><span>{sim:.2f}</span>
        </div>
        <div class="nv-affinity-bar" style="margin-top:4px">
          <div class="nv-affinity-fill" style="width:{sim_pct:.1f}%"></div>
        </div>
      </div>
      <div style="margin-top:10px; line-height:1.9">{feature_chips}</div>
      {drivers_html}
    </div>
    """


# ─────────────────────────────────────────────────────────────
# Format helpers
# ─────────────────────────────────────────────────────────────


def _yrs(days) -> str:
    """Render a day-count as a human-readable duration."""
    if days is None:
        return "—"
    days = int(days)
    if days < 60:
        return f"{days} d"
    if days < 365:
        return f"{days / 30.4375:.1f} mo"
    return f"{days / 365.25:.1f} yr"
