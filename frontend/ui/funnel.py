"""Portfolio funnel tab — reads ``out/cases/funnel_summary.json`` and renders
the Regeneron trial-screening portfolio view.

Produced by ``neoantigen funnel --input-dir out/cases``. The tab renders an
empty-state prompt when the file isn't present.
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from . import theme
from .paths import BACKEND_DIR


def _summary_path() -> Path:
    # Default location produced by `neoantigen funnel` when run from repo root
    # — backend/out/cases/funnel_summary.json — plus a user override via
    # session_state["funnel_summary_path"].
    override = st.session_state.get("funnel_summary_path")
    if override:
        p = Path(override)
        if p.exists():
            return p
    return BACKEND_DIR / "out" / "cases" / "funnel_summary.json"


def render() -> None:
    st.markdown(
        '<div class="nv-section-h">Regeneron trial funnel · portfolio view</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Aggregate of every case processed by `neoantigen melanoma-batch` + "
        "`neoantigen funnel`. Shows what fraction of the cohort clears each "
        "Regeneron trial today, and what criteria drive the drop-off."
    )

    path = _summary_path()
    if not path.exists():
        st.markdown(
            theme.empty_state(
                "📊",
                "No funnel summary yet",
                "Run <code>neoantigen melanoma-batch --dataset data/tcga_skcm/cases --limit 20</code> "
                "then <code>neoantigen funnel --input-dir out/cases</code> to populate this view.",
            ),
            unsafe_allow_html=True,
        )
        return

    import json as _json
    try:
        data = _json.loads(path.read_text())
    except Exception as e:
        st.error(f"Could not read funnel summary: {e}")
        return

    cohort_size = int(data.get("cohort_size") or 0)
    any_eligible = int(data.get("at_least_one_regeneron_eligible") or 0)
    per_trial: dict = data.get("per_trial") or {}
    per_title: dict = data.get("per_trial_title") or {}
    drop_off: dict = data.get("drop_off_by_criterion") or {}
    coverage: dict = data.get("enrichment_coverage") or {}

    # ── Headline metrics ──────────────────────────────────
    pct = (any_eligible / cohort_size * 100) if cohort_size else 0.0
    m_html = theme.metric_grid([
        theme.metric("Cohort size", str(cohort_size), "patients in this batch"),
        theme.metric(
            "Regeneron eligible",
            f"{any_eligible}",
            f"≥1 trial · {pct:.0f}% of cohort",
        ),
        theme.metric(
            "Trials scored",
            str(len(per_trial)),
            "Regeneron registry",
        ),
    ])
    st.markdown(m_html, unsafe_allow_html=True)

    # ── Stacked-bar funnel per trial ──────────────────────
    nct_ids = sorted(per_trial.keys())
    if nct_ids:
        eligible = [per_trial[n].get("eligible", 0) for n in nct_ids]
        unknown = [per_trial[n].get("needs_more_data", 0) for n in nct_ids]
        ineligible = [per_trial[n].get("ineligible", 0) for n in nct_ids]
        labels = [
            f"{n}<br><span style='font-size:10px;color:#94A3B8;'>{(per_title.get(n) or '')[:46]}</span>"
            for n in nct_ids
        ]
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=labels, x=eligible, orientation="h",
            name="Eligible",
            marker=dict(color=theme.COLORS["success"]),
            text=eligible, textposition="inside",
        ))
        fig.add_trace(go.Bar(
            y=labels, x=unknown, orientation="h",
            name="Needs more data",
            marker=dict(color=theme.COLORS["warning"]),
            text=unknown, textposition="inside",
        ))
        fig.add_trace(go.Bar(
            y=labels, x=ineligible, orientation="h",
            name="Ineligible",
            marker=dict(color=theme.COLORS["danger"]),
            text=ineligible, textposition="inside",
        ))
        fig.update_layout(
            **theme.plotly_theme(
                barmode="stack",
                height=max(220, 80 * len(nct_ids)),
                xaxis=dict(title="cohort patients", gridcolor=theme.COLORS["border"]),
                yaxis=dict(autorange="reversed"),
                legend=dict(orientation="h", y=-0.2),
            )
        )
        st.plotly_chart(fig, use_container_width=True, key="funnel_stacked")

    # ── Top drop-off per trial ─────────────────────────────
    if drop_off:
        st.markdown(
            '<div class="nv-section-h" style="margin-top:18px;">Drop-off attribution</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "For each Regeneron trial, the criteria that most commonly blocked "
            "an eligibility verdict across the cohort. Criteria listed as 'ECOG 0–1' "
            "etc. are `unknown` until the clinician intake fills them."
        )
        trial_pick = st.selectbox(
            "Trial",
            nct_ids,
            index=0,
            format_func=lambda n: f"{n} — {(per_title.get(n) or '')[:60]}",
            key="funnel_trial_pick",
        )
        criteria = drop_off.get(trial_pick) or {}
        if not criteria:
            st.info("No drop-off recorded for this trial — everyone cleared it or it wasn't scored.")
        else:
            items = sorted(criteria.items(), key=lambda x: -x[1])[:8]
            labels = [c for c, _ in items]
            counts = [n for _, n in items]
            fig2 = go.Figure(go.Bar(
                y=labels, x=counts, orientation="h",
                marker=dict(color=theme.COLORS["warning"]),
                text=counts, textposition="outside",
            ))
            fig2.update_layout(
                **theme.plotly_theme(
                    height=max(200, 40 * len(items)),
                    xaxis=dict(title="n cases blocked", gridcolor=theme.COLORS["border"]),
                    yaxis=dict(autorange="reversed"),
                )
            )
            st.plotly_chart(fig2, use_container_width=True, key="funnel_dropoff")

    # ── Enrichment coverage strip ──────────────────────────
    if coverage:
        st.markdown(
            '<div class="nv-section-h" style="margin-top:18px;">Enrichment coverage</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Percent of the cohort where each field is auto-filled by the "
            "enrichment layer (TMB/UV from the VCF, prior therapy from "
            "cBioPortal) or by the clinician intake form."
        )
        chips_html = ""
        for field_name, frac in sorted(coverage.items()):
            kind = "ok" if frac >= 0.9 else "warn" if frac >= 0.1 else "bad"
            pretty = field_name.replace("intake_", "(clinician) ").replace("_", " ")
            chips_html += theme.chip(f"{pretty} · {frac * 100:.0f}%", kind)
        st.markdown(
            '<div class="nv-card" style="padding:12px 14px;">'
            '<div class="nv-chip-row" style="flex-wrap:wrap;">' + chips_html + "</div></div>",
            unsafe_allow_html=True,
        )
