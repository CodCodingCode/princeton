"""Panel 2 — molecular landscape (WT / mutant folds + drug co-crystals)."""

from __future__ import annotations

import streamlit as st

from . import theme


# Maps EnrichedBiomarkers/BiomarkerChip `source` → theme chip `kind`.
# Clinician-supplied values flag `warn` so they stand out visually from
# everything the system derived on its own. ``curated_demo`` uses the
# dashed/hatched ``curated`` variant so hand-authored demo data is never
# confused with a real patient record.
_SOURCE_KIND = {
    "vlm": "accent",
    "vcf": "info",
    "tcga": "info",
    "cbioportal": "info",
    "intake": "warn",
    "curated_demo": "curated",
    "computed": "ok",
}

_SOURCE_LABEL = {
    "vlm": "slide",
    "vcf": "VCF",
    "tcga": "TCGA",
    "cbioportal": "cBioPortal",
    "intake": "clinician",
    "curated_demo": "demo data",
    "computed": "computed",
}


def render_biomarker_chips(chips: list[dict]) -> None:
    """Render a normalized biomarker strip above the molecular viewers.

    Merges VLM (PD-L1, TILs), VCF-computed (TMB, UV signature), cBioPortal
    (prior anti-PD-1), and clinician intake (LAG-3 IHC, ECOG) into one
    colour-coded row. Each chip is tagged with its provenance.
    """
    if not chips:
        return

    parts: list[str] = []
    for chip in chips:
        label = chip.get("label", "")
        value = chip.get("value", "")
        src = chip.get("source", "computed")
        kind = _SOURCE_KIND.get(src, "info")
        src_label = _SOURCE_LABEL.get(src, src)
        text = (
            f'<strong>{label}</strong>&nbsp;{value} '
            f'<span style="opacity:.55;font-size:10px;">· {src_label}</span>'
        )
        parts.append(theme.chip(text, kind))

    st.markdown(
        '<div class="nv-card" style="padding:10px 14px;margin-bottom:12px;">'
        '<div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:6px;">Biomarker strip · normalised across VLM + VCF + intake</div>'
        '<div class="nv-chip-row" style="flex-wrap:wrap;">'
        + "".join(parts)
        + '</div></div>',
        unsafe_allow_html=True,
    )


def render_molecule(mol: dict) -> None:
    import py3Dmol

    chips = theme.chip(mol["mutation_label"], "accent")
    if mol.get("drug_complex_pdb_id"):
        chips += theme.chip(f"co-crystal {mol['drug_complex_pdb_id']}", "info")
    if mol.get("drug_name"):
        chips += theme.chip(mol["drug_name"])

    st.markdown(
        f'<div class="nv-card">'
        f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:10px;flex-wrap:wrap;">'
        f'<div style="font-size:18px;font-weight:600;color:var(--text);">{mol["gene"]}</div>'
        f'<div>{chips}</div></div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(3 if mol.get("drug_complex_pdb_text") else 2)

    with cols[0]:
        st.caption("Wild-type · ESMFold")
        if mol.get("wt_pdb_text"):
            v = py3Dmol.view(width=320, height=220)
            v.addModel(mol["wt_pdb_text"], "pdb")
            v.setStyle({"cartoon": {"color": "spectrum"}})
            v.addStyle({"resi": str(mol["mutation_position"])}, {"stick": {"colorscheme": "greenCarbon"}})
            v.zoomTo()
            st.components.v1.html(v._make_html(), height=230)

    with cols[1]:
        st.caption(f"Mutant · residue {mol['mutation_position']} highlighted")
        if mol.get("mut_pdb_text"):
            v = py3Dmol.view(width=320, height=220)
            v.addModel(mol["mut_pdb_text"], "pdb")
            v.setStyle({"cartoon": {"color": "spectrum"}})
            v.addStyle({"resi": str(mol["mutation_position"])}, {"stick": {"colorscheme": "redCarbon"}})
            v.zoomTo()
            st.components.v1.html(v._make_html(), height=230)

    if mol.get("drug_complex_pdb_text"):
        with cols[2]:
            st.caption(f"Drug bound · RCSB {mol['drug_complex_pdb_id']}")
            v = py3Dmol.view(width=320, height=220)
            v.addModel(mol["drug_complex_pdb_text"], "pdb")
            v.setStyle({"cartoon": {"color": "lightgray"}})
            v.addStyle({"hetflag": True}, {"stick": {"colorscheme": "magentaCarbon"}})
            v.zoomTo()
            st.components.v1.html(v._make_html(), height=230)

    st.markdown('</div>', unsafe_allow_html=True)
