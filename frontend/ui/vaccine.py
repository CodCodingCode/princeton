"""Panel 3 — vaccine designer (peptide table + mRNA construct bar + HLA poses)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


def render_panel() -> None:
    pipeline = st.session_state.pipeline
    poses = st.session_state.poses

    if not pipeline:
        st.info("Vaccine pipeline runs once the NCCN walker reaches the personalized vaccine endpoint.")
        return

    candidates = pipeline.get("candidates", [])
    if not candidates:
        st.warning("No candidate peptides survived filtering.")
        return

    if pipeline.get("scorer_is_heuristic"):
        st.warning(
            "⚠ **Heuristic-only scoring** — NOT a real MHC predictor. "
            "Reported nM values are hand-rolled anchor-residue math, not ML predictions. "
            "Run `mhcflurry-downloads fetch` to enable the default real scorer."
        )
    elif pipeline.get("scorer_name"):
        st.caption(f"Scorer: `{pipeline['scorer_name']}`")

    rows = []
    for c in candidates[:10]:
        p = c["peptide"]
        m = p["mutation"]
        rows.append({
            "#": c["rank"],
            "Peptide": p["sequence"],
            "Len": p["length"],
            "Gene/Mut": f"{m['gene']} {m['ref_aa']}{m['position']}{m['alt_aa']}",
            "Score (nM)": round(p["score_nm"], 2) if p.get("score_nm") is not None else None,
        })
    st.dataframe(rows, hide_index=True, use_container_width=True)

    if poses:
        st.markdown("##### Top peptide-HLA poses")
        cols = st.columns(min(3, len(poses)))
        import py3Dmol
        for i, pose in enumerate(poses[:3]):
            with cols[i]:
                st.caption(f"{pose['peptide_sequence']} · {pose['hla_allele']} ({pose['method']})")
                if pose.get("pdb_text"):
                    v = py3Dmol.view(width=300, height=240)
                    v.addModel(pose["pdb_text"], "pdb")
                    v.setStyle({"cartoon": {"color": "spectrum"}})
                    v.addStyle({"hetflag": False}, {"stick": {"radius": 0.18}})
                    v.zoomTo()
                    st.components.v1.html(v._make_html(), height=250)

    vaccine = pipeline.get("vaccine")
    if vaccine:
        st.markdown("##### mRNA construct")
        _render_construct_bar(vaccine)
        st.caption(
            f"{len(vaccine['epitopes'])} epitopes · {len(vaccine['nucleotide_sequence'])} bp · "
            f"~${round(len(vaccine['nucleotide_sequence']) * 0.07, 2)} synthesis"
        )
        with st.expander("Amino acid sequence"):
            st.code(vaccine["amino_acid_sequence"], language="text")


def _render_construct_bar(vaccine: dict) -> None:
    epitopes = vaccine["epitopes"]
    linker = vaccine["linker"]
    palette = ["#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#84cc16", "#f97316", "#6366f1"]
    segments = [("5' Kozak", "GCCGCCACC", "#94a3b8"), ("ATG", "M", "#475569")]
    for i, ep in enumerate(epitopes):
        if i > 0:
            segments.append(("linker", linker, "#cbd5e1"))
        segments.append((f"epitope {i + 1}", ep, palette[i % len(palette)]))
    segments.append(("STOP", "TAA", "#0f172a"))

    fig = go.Figure()
    cursor = 0
    for label, seq, color in segments:
        width = max(1, len(seq))
        fig.add_trace(go.Bar(
            x=[width], y=["mRNA"], orientation="h",
            marker=dict(color=color, line=dict(color="#0f172a", width=0.5)),
            base=cursor, hovertemplate=f"<b>{label}</b><br>{seq}<extra></extra>",
            showlegend=False,
        ))
        cursor += width
    fig.update_layout(
        barmode="stack",
        height=110,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, title="Residues"),
        yaxis=dict(showgrid=False, showticklabels=False),
        plot_bgcolor="#ffffff",
    )
    st.plotly_chart(fig, use_container_width=True, key="construct_bar")
