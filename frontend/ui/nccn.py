"""Panel 1 — NCCN guideline walker flowchart + node detail."""

from __future__ import annotations

import networkx as nx
import plotly.graph_objects as go
import streamlit as st

from neoantigen.nccn.melanoma_v2024 import GRAPH, graph_to_payload

from .citations import render_citations


@st.cache_data
def _graph_layout() -> dict:
    payload = graph_to_payload()
    g = nx.DiGraph()
    for n in payload["nodes"]:
        g.add_node(n["id"])
    for e in payload["edges"]:
        if e["dst"] is not None:
            g.add_edge(e["src"], e["dst"])
    try:
        from networkx.drawing.nx_agraph import graphviz_layout
        return graphviz_layout(g, prog="dot")
    except Exception:
        return nx.spring_layout(g, seed=42, k=2.0)


def render_flowchart() -> None:
    payload = graph_to_payload()
    pos = _graph_layout()
    visited = {s["node_id"] for s in st.session_state.nccn_steps}
    last_id = st.session_state.nccn_steps[-1]["node_id"] if st.session_state.nccn_steps else None
    chosen_edges: set[tuple[str, str]] = set()
    for s in st.session_state.nccn_steps:
        if s.get("next_node_id"):
            chosen_edges.add((s["node_id"], s["next_node_id"]))

    edge_x: list = []
    edge_y: list = []
    edge_chosen_x: list = []
    edge_chosen_y: list = []
    for e in payload["edges"]:
        if e["dst"] is None or e["src"] not in pos or e["dst"] not in pos:
            continue
        x0, y0 = pos[e["src"]]
        x1, y1 = pos[e["dst"]]
        if (e["src"], e["dst"]) in chosen_edges:
            edge_chosen_x.extend([x0, x1, None])
            edge_chosen_y.extend([y0, y1, None])
        else:
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

    node_ids: list[str] = []
    node_x: list[float] = []
    node_y: list[float] = []
    node_text: list[str] = []
    node_color: list[str] = []
    for n in payload["nodes"]:
        if n["id"] not in pos:
            continue
        x, y = pos[n["id"]]
        node_ids.append(n["id"])
        node_x.append(x)
        node_y.append(y)
        node_text.append(n["title"])
        if n["id"] == last_id:
            node_color.append("#10b981")
        elif n["id"] in visited:
            node_color.append("#3b82f6")
        elif n["is_terminal"]:
            node_color.append("#f59e0b")
        else:
            node_color.append("#e5e7eb")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(width=1, color="#cbd5e1"), hoverinfo="none", showlegend=False,
    ))
    if edge_chosen_x:
        fig.add_trace(go.Scatter(
            x=edge_chosen_x, y=edge_chosen_y, mode="lines",
            line=dict(width=3, color="#10b981"), hoverinfo="none", showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        marker=dict(size=42, color=node_color, line=dict(color="#0f172a", width=1.5)),
        text=node_text,
        textposition="middle center",
        textfont=dict(size=10, color="#0f172a"),
        customdata=node_ids,
        hovertemplate="<b>%{text}</b><br>%{customdata}<extra></extra>",
        showlegend=False,
    ))
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=440,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor="#ffffff",
    )
    selection = st.plotly_chart(fig, key="nccn_chart", use_container_width=True, on_select="rerun")
    sel_points = []
    try:
        sel_points = selection.selection["points"] if selection else []
    except Exception:
        sel_points = []
    if sel_points:
        st.session_state.selected_node = sel_points[0].get("customdata")


def render_node_detail(node_id: str) -> None:
    matching = [s for s in st.session_state.nccn_steps if s["node_id"] == node_id]
    node = GRAPH.get(node_id)
    if node is None:
        return
    with st.container(border=True):
        st.markdown(f"#### 🩺 {node.title}")
        st.caption(node.question)
        if matching:
            step = matching[-1]
            st.markdown(f"**Decision:** {step.get('chosen_option', '—')}")
            ev = step.get("evidence") or {}
            if ev:
                st.markdown("**Evidence consulted**")
                for k, v in ev.items():
                    st.markdown(f"- `{k}`: {v}")
            reasoning = step.get("reasoning") or "(no reasoning recorded)"
            st.markdown("**Model reasoning**")
            st.code(reasoning, language="markdown")

            citations = (step.get("citations") or []) or st.session_state.citations_by_node.get(node_id, [])
            render_citations(citations)
        else:
            st.info("Node not yet visited by the agent.")
