"""Melanoma Oncologist Copilot — three-panel live UI.

Panel 1 — NCCN guideline walker (flowchart that lights up node by node).
Panel 2 — Molecular landscape (WT vs mutant 3D, drug co-crystals).
Panel 3 — Vaccine designer (top peptides, mRNA construct, HLA poses).

Sidebar streams the model's <think> reasoning live and accepts chat interrupts.

Run from /frontend with the GH200 vLLM tunnel up:
    streamlit run app.py
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from pathlib import Path

import networkx as nx
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from neoantigen.agent import AgentEvent, EventBus, EventKind
from neoantigen.agent.melanoma_orchestrator import MelanomaOrchestrator
from neoantigen.nccn.melanoma_v2024 import GRAPH, graph_to_payload

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
SAMPLE_DIR = BACKEND_DIR / "sample_data"
OUT_DIR = BACKEND_DIR / "out"

DEMO_VCF = SAMPLE_DIR / "tcga_skcm_demo.vcf"
DEMO_SLIDE = SAMPLE_DIR / "tcga_skcm_demo_slide.jpg"

load_dotenv(dotenv_path=BACKEND_DIR / ".env")

st.set_page_config(
    page_title="Melanoma Oncologist Copilot",
    page_icon="🩺",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────
DEFAULTS = {
    "events": [],
    "event_queue": None,
    "agent_thread": None,
    "running": False,
    "done": False,
    "started_at": None,
    "live_thinking": "",
    "live_thinking_node": None,
    "active_bus": None,
    "chat_messages": [],
    "nccn_steps": [],
    "molecules": [],
    "poses": [],
    "pipeline": None,
    "pathology": None,
    "mutations": [],
    "selected_node": None,
    "citations_by_node": {},
    "cohort": None,
    "trials": [],
}
for key, default in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ─────────────────────────────────────────────────────────────
# Background agent runner
# ─────────────────────────────────────────────────────────────
def run_agent_in_background(
    slide_path: Path,
    vcf_path: Path,
    event_q: queue.Queue,
    bus_holder: dict,
    tcga_patient_id: str | None = None,
) -> None:
    async def _bridge():
        bus = EventBus()
        bus_holder["bus"] = bus
        orch = MelanomaOrchestrator(
            slide_path=slide_path,
            vcf_path=vcf_path,
            bus=bus,
            tcga_patient_id=tcga_patient_id,
        )

        async def _drain():
            async for ev in bus.stream():
                event_q.put(ev)
            event_q.put(None)

        drain_task = asyncio.create_task(_drain())
        try:
            await orch.run()
        finally:
            await drain_task

    try:
        asyncio.run(_bridge())
    except Exception as e:
        event_q.put(AgentEvent(kind=EventKind.TOOL_ERROR, label=f"Fatal: {e}", payload={"error": str(e)}))
        event_q.put(None)


def _drain_queue() -> bool:
    q = st.session_state.event_queue
    if q is None:
        return False
    done = False
    while True:
        try:
            ev = q.get_nowait()
        except queue.Empty:
            break
        if ev is None:
            done = True
            break
        _ingest_event(ev)
        st.session_state.events.append(ev)
        if ev.kind == EventKind.DONE:
            done = True
    return done


def _ingest_event(ev: AgentEvent) -> None:
    """Route event into the right pieces of session state for live rendering."""
    p = ev.payload
    if ev.kind == EventKind.THINKING_DELTA:
        node = p.get("node_id")
        if node != st.session_state.live_thinking_node:
            st.session_state.live_thinking = ""
            st.session_state.live_thinking_node = node
        st.session_state.live_thinking += p.get("delta", "")
    elif ev.kind == EventKind.NCCN_NODE_VISITED:
        st.session_state.nccn_steps.append(p.get("step", {}))
        st.session_state.live_thinking = ""
        st.session_state.live_thinking_node = None
    elif ev.kind == EventKind.VLM_FINDING:
        st.session_state.pathology = p.get("findings")
    elif ev.kind == EventKind.MOLECULE_READY:
        st.session_state.molecules.append(p.get("view"))
    elif ev.kind == EventKind.PIPELINE_RESULT:
        st.session_state.pipeline = p.get("pipeline")
    elif ev.kind == EventKind.STRUCTURE_READY:
        st.session_state.poses.append(p.get("pose"))
    elif ev.kind == EventKind.CASE_UPDATE and "mutations" in p:
        st.session_state.mutations = p.get("mutations", [])
    elif ev.kind == EventKind.RAG_CITATIONS:
        nid = p.get("node_id")
        if nid:
            st.session_state.citations_by_node[nid] = p.get("citations", [])
    elif ev.kind == EventKind.COHORT_TWINS_READY:
        cohort = dict(st.session_state.cohort or {})
        cohort["twins"] = p.get("twins", [])
        st.session_state.cohort = cohort
    elif ev.kind == EventKind.SURVIVAL_CURVE_READY:
        cohort = dict(st.session_state.cohort or {})
        cohort["overall_curve"] = p.get("overall_curve", [])
        cohort["twin_curve"] = p.get("twin_curve", [])
        cohort["median_survival_days"] = p.get("median_survival_days")
        cohort["twin_median_survival_days"] = p.get("twin_median_survival_days")
        cohort["cohort_size"] = p.get("cohort_size", 0)
        st.session_state.cohort = cohort
    elif ev.kind == EventKind.TRIAL_MATCHES_READY:
        st.session_state.trials = p.get("trials", [])


# ─────────────────────────────────────────────────────────────
# NCCN flowchart rendering (Panel 1)
# ─────────────────────────────────────────────────────────────
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


def _render_nccn_flowchart() -> None:
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


def _node_detail(node_id: str) -> None:
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
            if citations:
                st.markdown("**📚 Supporting literature (PubMed)**")
                for c in citations:
                    pmid = c.get("pmid", "")
                    title = c.get("title", "")
                    year = c.get("year", "")
                    journal = c.get("journal", "")
                    snippet = c.get("snippet", "")
                    rel = c.get("relevance", 0.0)
                    st.markdown(
                        f"- [{title}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/) "
                        f"<span style='color:#94a3b8'>· {journal} {year} · PMID {pmid} · "
                        f"relevance {rel:.2f}</span>",
                        unsafe_allow_html=True,
                    )
                    if snippet:
                        st.caption(snippet)
        else:
            st.info("Node not yet visited by the agent.")


# ─────────────────────────────────────────────────────────────
# Panel 2 — molecular landscape
# ─────────────────────────────────────────────────────────────
def _render_molecule(mol: dict) -> None:
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


# ─────────────────────────────────────────────────────────────
# Panel 3 — vaccine designer
# ─────────────────────────────────────────────────────────────
def _render_vaccine_panel() -> None:
    pipeline = st.session_state.pipeline
    poses = st.session_state.poses

    if not pipeline:
        st.info("Vaccine pipeline runs once the NCCN walker reaches the personalized vaccine endpoint.")
        return

    candidates = pipeline.get("candidates", [])
    if not candidates:
        st.warning("No candidate peptides survived filtering.")
        return

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


# ─────────────────────────────────────────────────────────────
# Panel 4 — twin cohort + Kaplan-Meier survival
# ─────────────────────────────────────────────────────────────
def _render_cohort_panel() -> None:
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


# ─────────────────────────────────────────────────────────────
# Panel 5 — Clinical trial matches
# ─────────────────────────────────────────────────────────────

_STATUS_BADGES = {
    "eligible": ("🟢", "Eligible"),
    "needs_more_data": ("🟡", "Needs more data"),
    "ineligible": ("🔴", "Ineligible"),
    "unscored": ("⚪", "Unscored"),
}


def _render_trial_card(trial: dict) -> None:
    emoji, status_label = _STATUS_BADGES.get(trial.get("status", "unscored"), _STATUS_BADGES["unscored"])
    phase = trial.get("phase") or "—"
    sponsor = trial.get("sponsor", "Unknown")
    nct = trial.get("nct_id", "")
    title = trial.get("title", "—")
    url = trial.get("url") or (f"https://clinicaltrials.gov/study/{nct}" if nct else None)

    header = f"{emoji} **{status_label}** · {phase} · {sponsor}"
    if url:
        st.markdown(f"{header} · [{nct}]({url})")
    else:
        st.markdown(f"{header} · {nct}")
    st.markdown(f"**{title}**")

    passing = trial.get("passing_criteria") or []
    failing = trial.get("failing_criteria") or []
    unknown = trial.get("unknown_criteria") or []

    if passing:
        st.markdown("✅ **Passing**")
        for c in passing:
            st.markdown(f"- {c}")
    if failing:
        st.markdown("❌ **Failing**")
        for c in failing:
            st.markdown(f"- {c}")
    if unknown:
        st.markdown("❓ **Clinician to verify**")
        for c in unknown:
            st.markdown(f"- {c}")

    contacts = trial.get("site_contacts") or []
    if contacts:
        with st.expander("Site contacts"):
            for c in contacts:
                parts = [c.get("name"), c.get("role"), c.get("email"), c.get("phone")]
                st.caption(" · ".join(p for p in parts if p))


def _render_trials_panel() -> None:
    trials = st.session_state.trials or []
    if not trials:
        st.caption("Querying ClinicalTrials.gov for recruiting melanoma trials…")
        return

    regeneron = [t for t in trials if t.get("is_regeneron")]
    others = [t for t in trials if not t.get("is_regeneron")]

    eligible = [t for t in regeneron if t.get("status") == "eligible"]
    needs_data = [t for t in regeneron if t.get("status") == "needs_more_data"]
    ineligible = [t for t in regeneron if t.get("status") == "ineligible"]

    cols = st.columns(4)
    cols[0].metric("Regeneron trials", len(regeneron))
    cols[1].metric("Eligible", len(eligible))
    cols[2].metric("Needs data", len(needs_data))
    cols[3].metric("Other recruiting", len(others))

    st.markdown("#### Regeneron programs")
    if not regeneron:
        st.caption("No Regeneron trials returned from ClinicalTrials.gov.")
    else:
        for t in eligible + needs_data:
            with st.container(border=True):
                _render_trial_card(t)
        if ineligible:
            with st.expander(f"Ineligible ({len(ineligible)})"):
                for t in ineligible:
                    with st.container(border=True):
                        _render_trial_card(t)

    if others:
        with st.expander(f"Additional recruiting trials ({len(others)})"):
            for t in others[:25]:
                with st.container(border=True):
                    _render_trial_card(t)


# ─────────────────────────────────────────────────────────────
# Sidebar — inputs + thinking feed + chat
# ─────────────────────────────────────────────────────────────
def _start_run(slide_path: Path, vcf_path: Path, tcga_patient_id: str | None = None) -> None:
    event_q: queue.Queue = queue.Queue()
    bus_holder: dict = {"bus": None}
    st.session_state.event_queue = event_q
    st.session_state.events = []
    st.session_state.live_thinking = ""
    st.session_state.live_thinking_node = None
    st.session_state.nccn_steps = []
    st.session_state.molecules = []
    st.session_state.poses = []
    st.session_state.pipeline = None
    st.session_state.pathology = None
    st.session_state.mutations = []
    st.session_state.chat_messages = []
    st.session_state.citations_by_node = {}
    st.session_state.cohort = None
    st.session_state.running = True
    st.session_state.done = False
    st.session_state.started_at = time.time()
    thread = threading.Thread(
        target=run_agent_in_background,
        args=(slide_path, vcf_path, event_q, bus_holder, tcga_patient_id),
        daemon=True,
    )
    thread.start()
    st.session_state.agent_thread = thread
    st.session_state.active_bus = bus_holder
    st.rerun()


with st.sidebar:
    st.markdown("## 🩺 Patient inputs")
    slide_up = st.file_uploader("Pathology slide (image)", type=["jpg", "jpeg", "png", "tif", "tiff"])
    vcf_up = st.file_uploader("Tumour VCF / TSV", type=["vcf", "tsv"])

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(
            "Run uploads",
            disabled=(slide_up is None or vcf_up is None or st.session_state.running),
            use_container_width=True,
        ):
            upload_dir = OUT_DIR / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            slide_path = upload_dir / slide_up.name
            vcf_path = upload_dir / vcf_up.name
            slide_path.write_bytes(slide_up.read())
            vcf_path.write_bytes(vcf_up.read())
            _start_run(slide_path, vcf_path)
    with col_b:
        if st.button("Run TCGA demo", type="primary", disabled=st.session_state.running, use_container_width=True):
            tcga_id: str | None = None
            slide_for_demo = DEMO_SLIDE
            try:
                from neoantigen.cohort import has_cohort, demo_patient_id
                if has_cohort():
                    tcga_id = demo_patient_id()
                    tcga_slide = BACKEND_DIR / "data" / "tcga_skcm" / "demo_slide.jpg"
                    if tcga_slide.exists():
                        slide_for_demo = tcga_slide
            except Exception:
                pass
            _start_run(slide_for_demo, DEMO_VCF, tcga_patient_id=tcga_id)

    if st.session_state.done and st.button("↻ New case", use_container_width=True):
        for k in list(DEFAULTS.keys()):
            st.session_state[k] = DEFAULTS[k]
        st.rerun()

    st.divider()
    st.markdown("### 💭 Live thinking")
    if st.session_state.live_thinking:
        st.caption(f"Node: {st.session_state.live_thinking_node or '—'}")
        st.markdown(
            "<div style='font-family: ui-monospace, SFMono-Regular, monospace; font-size:0.78em; "
            "color:#475569; max-height:280px; overflow-y:auto; background:#f1f5f9; padding:8px; "
            f"border-radius:6px; white-space:pre-wrap;'>{st.session_state.live_thinking}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Reasoning will stream here while the agent walks the guideline.")

    st.divider()
    st.markdown("### 💬 Ask / interrupt")
    for msg in st.session_state.chat_messages:
        role_icon = "🧑‍⚕️" if msg["role"] == "user" else "🤖"
        st.markdown(f"{role_icon} {msg['content']}")
    user_msg = st.chat_input("Interject…", disabled=not st.session_state.running)
    if user_msg:
        st.session_state.chat_messages.append({"role": "user", "content": user_msg})
        bus_holder = st.session_state.get("active_bus") or {}
        bus = bus_holder.get("bus")
        if bus is not None:
            bus.push_interrupt(user_msg)
            st.session_state.chat_messages.append(
                {"role": "agent", "content": "Acknowledged — will reconsider at the next NCCN node."}
            )


# ─────────────────────────────────────────────────────────────
# Main column
# ─────────────────────────────────────────────────────────────
st.markdown("# Melanoma Oncologist Copilot")
st.caption("VLM pathology · NCCN guideline walker · 3D molecular landscape · personalized neoantigen vaccine")

if not st.session_state.running and not st.session_state.done:
    st.info("Choose inputs in the sidebar and start a run.")
    st.stop()

done_now = _drain_queue()
if done_now:
    st.session_state.running = False
    st.session_state.done = True

header_cols = st.columns(5)
path = st.session_state.pathology or {}
header_cols[0].metric("T-stage", path.get("t_stage") if path else "—")
header_cols[1].metric("Subtype", (path.get("melanoma_subtype") or "—").replace("_", " ") if path else "—")
header_cols[2].metric("Breslow", f"{path.get('breslow_thickness_mm')} mm" if path.get("breslow_thickness_mm") else "—")
header_cols[3].metric("Mutations", len(st.session_state.mutations))
elapsed = int(time.time() - (st.session_state.started_at or time.time()))
header_cols[4].metric("Elapsed", f"{elapsed}s")

st.markdown("### Panel 1 · NCCN melanoma guideline walker")
_render_nccn_flowchart()
if st.session_state.selected_node:
    _node_detail(st.session_state.selected_node)
elif st.session_state.nccn_steps:
    _node_detail(st.session_state.nccn_steps[-1]["node_id"])
st.divider()

st.markdown("### Panel 2 · Molecular landscape")
if not st.session_state.molecules:
    st.caption("Folding mutated driver proteins and pulling drug co-crystals…")
else:
    for mol in st.session_state.molecules:
        with st.container(border=True):
            _render_molecule(mol)
st.divider()

st.markdown("### Panel 3 · Vaccine designer")
with st.container(border=True):
    _render_vaccine_panel()
st.divider()

st.markdown("### Panel 4 · Twin cohort & survival (TCGA-SKCM)")
with st.container(border=True):
    _render_cohort_panel()
st.divider()

st.markdown("### Panel 5 · Clinical trial matches")
with st.container(border=True):
    _render_trials_panel()

status_label = "▶ Running" if st.session_state.running else "✅ Complete"
st.caption(f"{status_label} · {len(st.session_state.events)} events · NCCN nodes walked: {len(st.session_state.nccn_steps)}")

if st.session_state.running:
    time.sleep(0.4)
    st.rerun()
