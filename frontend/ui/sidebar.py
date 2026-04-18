"""Sidebar layout: inputs (CTA + expanders) + patient at-a-glance + run-time interrupt.

Live thinking + post-run chat moved out to ``ui/rail.py``. The chat input itself
is owned by ``app.py`` (Streamlit pins ``st.chat_input`` to the page bottom).
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import streamlit as st

from . import bridge, theme
from .paths import BACKEND_DIR, CASES_ROOT, DEMO_SLIDE, DEMO_VCF, OUT_DIR
from .state import DEFAULTS


def start_run(slide_path: Path, vcf_path: Path, tcga_patient_id: str | None = None) -> None:
    event_q: queue.Queue = queue.Queue()
    bus_holder: dict = {"bus": None}
    st.session_state.event_queue = event_q
    st.session_state.events = []
    st.session_state.live_thinking = ""
    st.session_state.live_thinking_node = None
    st.session_state.live_step_label = "Starting"
    st.session_state.nccn_steps = []
    st.session_state.molecules = []
    st.session_state.poses = []
    st.session_state.pipeline = None
    st.session_state.pathology = None
    st.session_state.pathology_slide_path = None
    st.session_state.pathology_thinking = ""
    st.session_state.pathology_raw = ""
    st.session_state.mutations = []
    st.session_state.chat_messages = []
    st.session_state.citations_by_node = {}
    st.session_state.cohort = None
    st.session_state.trials = []
    st.session_state.enrichment = None
    st.session_state.biomarker_chips = []
    st.session_state.focus_panel = None
    st.session_state.focus_target = None
    st.session_state.running = True
    st.session_state.done = False
    st.session_state.run_status = "running"
    st.session_state.started_at = time.time()

    intake = _build_intake_from_session()
    if intake is not None:
        st.session_state.intake = intake.model_dump()
    else:
        st.session_state.intake = None

    thread = threading.Thread(
        target=bridge.run_agent_in_background,
        args=(slide_path, vcf_path, event_q, bus_holder, tcga_patient_id, intake),
        daemon=True,
    )
    thread.start()
    st.session_state.agent_thread = thread
    st.session_state.active_bus = bus_holder
    st.rerun()


def _build_intake_from_session():
    """Assemble a ``ClinicianIntake`` from the sidebar form fields.

    Returns ``None`` when every field is blank — callers pass that through to
    the orchestrator so the trial evaluator falls back to enrichment +
    ``unknown_criteria`` exactly as before.
    """
    from neoantigen.models import ClinicianIntake

    fields = {
        "ecog": st.session_state.get("intake_form_ecog"),
        "lag3_ihc_percent": st.session_state.get("intake_form_lag3"),
        "measurable_disease_recist": st.session_state.get("intake_form_recist"),
        "life_expectancy_months": st.session_state.get("intake_form_life_exp"),
        "prior_systemic_therapy": st.session_state.get("intake_form_prior_sys"),
        "prior_anti_pd1": st.session_state.get("intake_form_prior_pd1"),
    }
    if all(v is None for v in fields.values()):
        return None
    return ClinicianIntake(**fields)


def _section_label(text: str) -> None:
    st.markdown(
        f'<div style="padding:8px 4px 4px 4px;font-size:11px;color:var(--text-dim);'
        f'text-transform:uppercase;letter-spacing:.06em;font-weight:600;">{text}</div>',
        unsafe_allow_html=True,
    )


def _render_inputs() -> None:
    is_running = st.session_state.running

    _section_label("New case")

    if st.button(
        "▶  Run TCGA demo",
        type="primary",
        disabled=is_running,
        use_container_width=True,
        key="btn_run_demo",
    ):
        tcga_id: str | None = None
        slide_for_demo = DEMO_SLIDE
        try:
            from neoantigen.cohort import demo_patient_id, has_cohort
            if has_cohort():
                tcga_id = demo_patient_id()
                tcga_slide = BACKEND_DIR / "data" / "tcga_skcm" / "demo_slide.jpg"
                if tcga_slide.exists():
                    slide_for_demo = tcga_slide
        except Exception:
            pass
        start_run(slide_for_demo, DEMO_VCF, tcga_patient_id=tcga_id)

    with st.expander("Or upload your own", expanded=False):
        slide_up = st.file_uploader("Pathology slide", type=["jpg", "jpeg", "png", "tif", "tiff"])
        vcf_up = st.file_uploader("Tumour VCF / TSV", type=["vcf", "tsv"])
        if st.button(
            "Run uploads",
            disabled=(slide_up is None or vcf_up is None or is_running),
            use_container_width=True,
            key="btn_run_uploads",
        ):
            upload_dir = OUT_DIR / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            slide_path = upload_dir / slide_up.name
            vcf_path = upload_dir / vcf_up.name
            slide_path.write_bytes(slide_up.read())
            vcf_path.write_bytes(vcf_up.read())
            start_run(slide_path, vcf_path)

    if CASES_ROOT.exists():
        dataset_cases = sorted(
            p.name for p in CASES_ROOT.iterdir()
            if p.is_dir() and (p / "slide.jpg").exists() and (p / "tumor.vcf").exists()
        )
        if dataset_cases:
            with st.expander(f"Pick from dataset · {len(dataset_cases)}", expanded=False):
                selected_sid = st.selectbox(
                    "TCGA-SKCM cases",
                    dataset_cases,
                    index=0,
                    disabled=is_running,
                    label_visibility="collapsed",
                )
                if st.button(
                    f"Run {selected_sid}",
                    disabled=is_running,
                    use_container_width=True,
                    key="btn_run_dataset",
                ):
                    case_dir = CASES_ROOT / selected_sid
                    start_run(
                        case_dir / "slide.jpg",
                        case_dir / "tumor.vcf",
                        tcga_patient_id=selected_sid,
                    )

    if st.session_state.done and st.button("↻  New case", use_container_width=True, key="btn_reset"):
        for k in list(DEFAULTS.keys()):
            st.session_state[k] = DEFAULTS[k]
        st.rerun()


def _bool_tri(label: str, key: str, disabled: bool) -> None:
    """Tri-state selector that writes None / True / False into session_state[key]."""
    options = ["—", "Yes", "No"]
    current = st.session_state.get(key)
    default_idx = 0 if current is None else (1 if current else 2)
    choice = st.selectbox(
        label,
        options,
        index=default_idx,
        disabled=disabled,
        key=f"widget_{key}",
    )
    st.session_state[key] = None if choice == "—" else (choice == "Yes")


def _render_intake_form() -> None:
    """Regeneron trial screener intake. Every field is optional; the trial
    evaluator falls back to cBioPortal enrichment, then ``unknown_criteria``.

    Fields marked ★ have **no public data source** — only the clinician can
    supply them. Filling them flips Regeneron trial rows from
    ``needs_more_data`` to ``eligible``/``ineligible``.
    """
    is_running = st.session_state.running
    enrich = st.session_state.get("enrichment") or {}

    with st.expander("Clinician intake (Regeneron screener)", expanded=False):
        st.caption(
            "Fields with ★ have no public-data source. Filling them turns "
            "`needs_more_data` into a real eligibility verdict."
        )

        ecog_opts = ["—", "0", "1", "2", "3", "4"]
        current_ecog = st.session_state.get("intake_form_ecog")
        ecog_idx = 0 if current_ecog is None else ecog_opts.index(str(current_ecog))
        ecog_choice = st.selectbox(
            "★ ECOG performance status",
            ecog_opts,
            index=ecog_idx,
            disabled=is_running,
            key="widget_intake_ecog",
        )
        st.session_state["intake_form_ecog"] = None if ecog_choice == "—" else int(ecog_choice)

        lag3 = st.number_input(
            "★ LAG-3 IHC %",
            min_value=0.0,
            max_value=100.0,
            value=st.session_state.get("intake_form_lag3"),
            step=1.0,
            format="%.1f",
            placeholder="—",
            disabled=is_running,
            key="widget_intake_lag3",
        )
        st.session_state["intake_form_lag3"] = lag3 if lag3 is not None and lag3 > 0 else None

        _bool_tri(
            "★ Measurable disease (RECIST 1.1)",
            "intake_form_recist",
            disabled=is_running,
        )

        life_exp = st.number_input(
            "Life expectancy (months)",
            min_value=0,
            max_value=240,
            value=st.session_state.get("intake_form_life_exp"),
            step=1,
            placeholder="—",
            disabled=is_running,
            key="widget_intake_life_exp",
        )
        st.session_state["intake_form_life_exp"] = int(life_exp) if life_exp is not None and life_exp > 0 else None

        _bool_tri(
            "Prior systemic therapy (advanced)",
            "intake_form_prior_sys",
            disabled=is_running,
        )
        _bool_tri(
            "Prior anti-PD-1 therapy",
            "intake_form_prior_pd1",
            disabled=is_running,
        )

        if enrich.get("prior_systemic_therapies"):
            st.caption(
                "🧪 cBioPortal enrichment — prior therapy on record: "
                + ", ".join(enrich["prior_systemic_therapies"])
            )


def _render_patient_card() -> None:
    path = st.session_state.pathology or {}
    if not (path or st.session_state.mutations):
        return

    _section_label("Patient")
    subtype = (path.get("melanoma_subtype") or "—").replace("_", " ")
    t_stage = path.get("t_stage") or "—"
    n_mut = len(st.session_state.mutations)

    chips = ""
    top_genes = []
    seen = set()
    for m in st.session_state.mutations[:8]:
        g = m.get("gene")
        if g and g not in seen:
            seen.add(g)
            top_genes.append(g)
        if len(top_genes) >= 5:
            break
    for g in top_genes:
        chips += theme.chip(g)

    st.markdown(
        f'<div class="nv-card" style="padding:12px;margin-bottom:0;">'
        f'<div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:2px;">{subtype}</div>'
        f'<div style="font-size:12px;color:var(--text-dim);">{t_stage} · {n_mut} mutations</div>'
        + (f'<div class="nv-chip-row" style="margin-top:8px;">{chips}</div>' if chips else "")
        + '</div>',
        unsafe_allow_html=True,
    )


def render() -> None:
    with st.sidebar:
        _render_inputs()
        _render_intake_form()
        _render_patient_card()
