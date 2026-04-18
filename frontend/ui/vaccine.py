"""Panel 3 — vaccine designer (top peptides hero + ranked table + mRNA construct + HLA poses)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from . import theme

# BNT111 (Regeneron + BioNTech partnership, NCT04526899) is a fixed-antigen
# mRNA vaccine targeting these four shared melanoma antigens. Peptides whose
# source gene is in this set flag the patient as a combination-arm candidate.
BNT111_ANTIGENS: frozenset[str] = frozenset({"TYR", "MAGEA3", "CTAG1B", "TPTE"})


def render_panel() -> None:
    pipeline = st.session_state.pipeline
    poses = st.session_state.poses

    if not pipeline:
        st.markdown(
            theme.empty_state(
                "💉",
                "Vaccine pipeline not yet started",
                "Runs once the NCCN walker reaches the personalized vaccine endpoint.",
            ),
            unsafe_allow_html=True,
        )
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

    # ── Top-3 peptide hero cards ─────────────────────────────
    st.markdown('<div class="nv-section-h">Top candidates</div>', unsafe_allow_html=True)
    hero_cols = st.columns(min(3, len(candidates)))
    for i, c in enumerate(candidates[:3]):
        p = c["peptide"]
        m = p["mutation"]
        nm = p.get("score_nm")
        if nm is not None:
            quality = max(0.0, min(1.0, 1.0 - (nm / 1000.0)))
            nm_str = f"{nm:.1f} nM"
        else:
            quality = 0.0
            nm_str = "— nM"
        with hero_cols[i]:
            st.markdown(
                f'<div class="nv-peptide">'
                f'<div style="display:flex;justify-content:space-between;align-items:baseline;">'
                f'<div class="nv-peptide-seq">{p["sequence"]}</div>'
                f'<div style="font-size:11px;color:var(--text-faint);">#{c["rank"]}</div>'
                f'</div>'
                f'<div class="nv-peptide-meta">{m["gene"]} {m["ref_aa"]}{m["position"]}{m["alt_aa"]} · '
                f'{p["length"]} aa · {nm_str}</div>'
                f'<div class="nv-affinity-bar">'
                f'<div class="nv-affinity-fill" style="width:{quality * 100:.0f}%;"></div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── BNT111 overlap banner (Regeneron + BioNTech combo candidacy) ─────
    bnt111_hits = [
        c for c in candidates
        if c["peptide"]["mutation"]["gene"].upper() in BNT111_ANTIGENS
    ]
    if bnt111_hits:
        hit_genes = sorted({c["peptide"]["mutation"]["gene"].upper() for c in bnt111_hits})
        st.info(
            f"🧬 **{len(bnt111_hits)} of {len(candidates)} peptides target BNT111 shared antigens** "
            f"({', '.join(hit_genes)}) — flagged as candidate for NCT04526899 "
            f"(cemiplimab + BNT111 combination arm, Regeneron × BioNTech)."
        )

    # ── Full ranked table ────────────────────────────────────
    st.markdown('<div class="nv-section-h" style="margin-top:18px;">Ranked peptides</div>', unsafe_allow_html=True)
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
            "BNT111": "✓" if m["gene"].upper() in BNT111_ANTIGENS else "",
        })
    st.dataframe(rows, hide_index=True, use_container_width=True)

    # ── Top peptide-HLA poses ────────────────────────────────
    if poses:
        st.markdown('<div class="nv-section-h" style="margin-top:18px;">Top peptide-HLA poses</div>', unsafe_allow_html=True)
        cols = st.columns(min(3, len(poses)))
        import py3Dmol
        for i, pose in enumerate(poses[:3]):
            with cols[i]:
                st.caption(f"{pose['peptide_sequence']} · {pose['hla_allele']} ({pose['method']})")
                if pose.get("pdb_text"):
                    v = py3Dmol.view(width=300, height=220)
                    v.addModel(pose["pdb_text"], "pdb")
                    v.setStyle({"cartoon": {"color": "spectrum"}})
                    v.addStyle({"hetflag": False}, {"stick": {"radius": 0.18}})
                    v.zoomTo()
                    st.components.v1.html(v._make_html(), height=230)

    # ── mRNA construct ───────────────────────────────────────
    vaccine = pipeline.get("vaccine")
    if vaccine:
        st.markdown('<div class="nv-section-h" style="margin-top:18px;">mRNA construct</div>', unsafe_allow_html=True)
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
    palette = [
        theme.COLORS["accent"], theme.COLORS["success"], theme.COLORS["warning"],
        theme.COLORS["danger"], "#8B5CF6", "#EC4899", "#14B8A6", "#84CC16", "#F97316", "#6366F1",
    ]
    segments = [("5' Kozak", "GCCGCCACC", theme.COLORS["text_faint"]), ("ATG", "M", "#475569")]
    for i, ep in enumerate(epitopes):
        if i > 0:
            segments.append(("linker", linker, theme.COLORS["border_st"]))
        segments.append((f"epitope {i + 1}", ep, palette[i % len(palette)]))
    segments.append(("STOP", "TAA", theme.COLORS["text"]))

    fig = go.Figure()
    cursor = 0
    for label, seq, color in segments:
        width = max(1, len(seq))
        fig.add_trace(go.Bar(
            x=[width], y=["mRNA"], orientation="h",
            marker=dict(color=color, line=dict(color=theme.COLORS["surface"], width=0.5)),
            base=cursor, hovertemplate=f"<b>{label}</b><br>{seq}<extra></extra>",
            showlegend=False,
        ))
        cursor += width
    fig.update_layout(
        **theme.plotly_theme(
            barmode="stack",
            height=110,
            xaxis=dict(showgrid=False, title="Residues"),
            yaxis=dict(showgrid=False, showticklabels=False),
        )
    )
    st.plotly_chart(fig, use_container_width=True, key="construct_bar")
