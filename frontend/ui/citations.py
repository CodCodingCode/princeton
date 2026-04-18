"""Shared PubMed citation renderer — used by the NCCN panel and the chat sidebar."""

from __future__ import annotations

import streamlit as st


def render_citations(
    citations: list[dict] | None,
    heading: str = "📚 Supporting literature (PubMed)",
) -> None:
    if not citations:
        return
    st.markdown(f"**{heading}**")
    for c in citations:
        pmid = c.get("pmid", "")
        title = c.get("title", "")
        year = c.get("year", "")
        journal = c.get("journal", "")
        snippet = c.get("snippet", "")
        rel = c.get("relevance", 0.0)
        tail = f"· {journal} {year} · PMID {pmid}"
        if rel:
            tail += f" · relevance {rel:.2f}"
        st.markdown(
            f"- [{title}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/) "
            f"<span style='color:#94a3b8'>{tail}</span>",
            unsafe_allow_html=True,
        )
        if snippet:
            st.caption(snippet)
