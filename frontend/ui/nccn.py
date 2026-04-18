"""Panel 1 — NCCN guideline walker flowchart + node detail."""

from __future__ import annotations

import networkx as nx
import plotly.graph_objects as go
import streamlit as st

from neoantigen.nccn.melanoma_v2024 import GRAPH, graph_to_payload

from . import theme
from .citations import render_citations


@st.cache_data
def _graph_layout() -> dict:
    """Top-to-bottom hierarchical tree layout.

    Prefers graphviz's `dot` when available (best crossing-minimization). Falls
    back to a pure-Python BFS-layered layout so the flowchart reads as a
    decision tree regardless of the system graphviz install. The old
    ``spring_layout`` fallback gave the scatter-with-crossings view.
    """
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
        pass

    # Pure-Python hierarchical fallback — BFS depth = layer, sort within layer
    # in the order the walker would visit them (preserves source-node insertion
    # order from the GRAPH definition so BRAF→right, ulceration→left, etc).
    from collections import deque

    roots = [n for n, d in g.in_degree() if d == 0] or [next(iter(g.nodes))]
    depth: dict[str, int] = {}
    q: deque = deque()
    for r in roots:
        depth[r] = 0
        q.append(r)
    while q:
        n = q.popleft()
        for succ in g.successors(n):
            new_d = depth[n] + 1
            if succ not in depth or new_d > depth[succ]:
                depth[succ] = new_d
                q.append(succ)
    for n in g.nodes:
        depth.setdefault(n, max(depth.values(), default=0) + 1)

    by_layer: dict[int, list[str]] = {}
    for n, d in depth.items():
        by_layer.setdefault(d, []).append(n)
    # Stable order: original node order in the payload (preserves author intent)
    node_order = {n["id"]: i for i, n in enumerate(payload["nodes"])}
    for layer_nodes in by_layer.values():
        layer_nodes.sort(key=lambda n: node_order.get(n, 0))

    max_width = max(len(layer) for layer in by_layer.values())
    pos: dict[str, tuple[float, float]] = {}
    for d, nodes in by_layer.items():
        span = max(1, len(nodes) - 1)
        for i, n in enumerate(nodes):
            # Centre each layer in [-1, 1]; scale by layer fullness so sparse
            # layers don't bunch to the centre.
            x = (i / span - 0.5) * (len(nodes) / max_width) if len(nodes) > 1 else 0.0
            y = -d  # roots on top, leaves at the bottom
            pos[n] = (x, y)
    return pos


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
            node_color.append(theme.COLORS["success"])
        elif n["id"] in visited:
            node_color.append(theme.COLORS["accent"])
        elif n["is_terminal"]:
            node_color.append(theme.COLORS["warning"])
        else:
            node_color.append(theme.COLORS["border"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(width=1.2, color=theme.COLORS["border_st"]), hoverinfo="none", showlegend=False,
    ))
    if edge_chosen_x:
        fig.add_trace(go.Scatter(
            x=edge_chosen_x, y=edge_chosen_y, mode="lines",
            line=dict(width=3, color=theme.COLORS["success"]), hoverinfo="none", showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        marker=dict(size=42, color=node_color, line=dict(color=theme.COLORS["text"], width=1.2)),
        text=node_text,
        textposition="middle center",
        textfont=dict(size=10, color=theme.COLORS["text"], family="Inter"),
        customdata=node_ids,
        hovertemplate="<b>%{text}</b><br>%{customdata}<extra></extra>",
        showlegend=False,
    ))
    fig.update_layout(
        **theme.plotly_theme(
            height=460,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        )
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

    if not matching:
        st.markdown(
            f'<div class="nv-card">'
            f'<div class="nv-card-title">NCCN node · {node_id}</div>'
            f'<div class="nv-card-headline">{node.title}</div>'
            f'<div style="margin-top:6px;font-size:13px;color:var(--text-dim);">{node.question}</div>'
            f'<div style="margin-top:10px;font-size:12px;color:var(--text-faint);">'
            f'Node not yet visited by the agent.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    step = matching[-1]
    chosen = step.get("chosen_option", "—")
    st.markdown(
        f'<div class="nv-card nv-card--accent">'
        f'<div class="nv-card-title">NCCN node · {node_id}</div>'
        f'<div class="nv-card-headline">{node.title}</div>'
        f'<div style="margin-top:6px;font-size:13px;color:var(--text-dim);">{node.question}</div>'
        f'<div style="margin-top:12px;">Decision · {theme.chip(chosen, "accent")}</div>',
        unsafe_allow_html=True,
    )

    ev = step.get("evidence") or {}
    if ev:
        chips = " ".join(theme.chip(f"{k}: {v}") for k, v in ev.items())
        st.markdown(
            f'<div class="nv-section-h" style="margin-top:14px;">Evidence consulted</div>'
            f'<div class="nv-chip-row">{chips}</div>',
            unsafe_allow_html=True,
        )

    # Suppress the reasoning block for stub strings the walker emits at terminal
    # nodes — they're noise, not insight.
    reasoning = (step.get("reasoning") or "").strip()
    _STUBS = {"terminal node reached.", "(no reasoning recorded)"}
    if reasoning and reasoning.lower() not in _STUBS:
        st.markdown('<div class="nv-section-h" style="margin-top:14px;">Model reasoning</div>', unsafe_allow_html=True)
        st.code(reasoning, language="markdown")

    citations = (step.get("citations") or []) or st.session_state.citations_by_node.get(node_id, [])
    if citations:
        render_citations(citations)

    st.markdown('</div>', unsafe_allow_html=True)
