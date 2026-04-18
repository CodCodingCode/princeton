"""Panel 2 — molecular landscape (WT / mutant folds + drug co-crystals)."""

from __future__ import annotations

import streamlit as st


def render_molecule(mol: dict) -> None:
    import py3Dmol

    title = f"##### 🧬 {mol['gene']} {mol['mutation_label']}"
    if mol.get("drug_complex_pdb_id"):
        title += f" · drug co-crystal {mol['drug_complex_pdb_id']} ({mol['drug_name']})"
    st.markdown(title)

    cols = st.columns(3 if mol.get("drug_complex_pdb_text") else 2)

    with cols[0]:
        st.caption("Wild-type (ESMFold)")
        if mol.get("wt_pdb_text"):
            v = py3Dmol.view(width=320, height=240)
            v.addModel(mol["wt_pdb_text"], "pdb")
            v.setStyle({"cartoon": {"color": "spectrum"}})
            v.addStyle({"resi": str(mol["mutation_position"])}, {"stick": {"colorscheme": "greenCarbon"}})
            v.zoomTo()
            st.components.v1.html(v._make_html(), height=250)

    with cols[1]:
        st.caption(f"Mutant — residue {mol['mutation_position']} highlighted")
        if mol.get("mut_pdb_text"):
            v = py3Dmol.view(width=320, height=240)
            v.addModel(mol["mut_pdb_text"], "pdb")
            v.setStyle({"cartoon": {"color": "spectrum"}})
            v.addStyle({"resi": str(mol["mutation_position"])}, {"stick": {"colorscheme": "redCarbon"}})
            v.zoomTo()
            st.components.v1.html(v._make_html(), height=250)

    if mol.get("drug_complex_pdb_text"):
        with cols[2]:
            st.caption(f"Drug bound — RCSB {mol['drug_complex_pdb_id']}")
            v = py3Dmol.view(width=320, height=240)
            v.addModel(mol["drug_complex_pdb_text"], "pdb")
            v.setStyle({"cartoon": {"color": "lightgray"}})
            v.addStyle({"hetflag": True}, {"stick": {"colorscheme": "magentaCarbon"}})
            v.zoomTo()
            st.components.v1.html(v._make_html(), height=250)
