"""NeoVax — live agent demo.

Upload a tumor VCF + pathology PDF. An agent runs the neoantigen pipeline,
searches labs/vets/vendors, drafts emails, validates structures in 3D — all
while the activity feed streams live on the left and the treatment package
fills in on the right.

Run: streamlit run app_agent.py
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from neoantigen.agent import AgentEvent, EventBus, EventKind, build_case_file
from neoantigen.agent import gmail_auth
from neoantigen.agent.emails import send_via_gmail
from neoantigen.agent.orchestrator import CaseOrchestrator

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
SAMPLE_DIR = BACKEND_DIR / "sample_data"
OUT_DIR = BACKEND_DIR / "out"

st.set_page_config(
    page_title="NeoVax — Autonomous Cancer Vaccine Pipeline",
    page_icon="🧬",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────
if "events" not in st.session_state:
    st.session_state.events = []
if "event_queue" not in st.session_state:
    st.session_state.event_queue = None
if "agent_thread" not in st.session_state:
    st.session_state.agent_thread = None
if "running" not in st.session_state:
    st.session_state.running = False
if "done" not in st.session_state:
    st.session_state.done = False
if "started_at" not in st.session_state:
    st.session_state.started_at = None
if "gmail_signed_in" not in st.session_state:
    st.session_state.gmail_signed_in = gmail_auth.is_signed_in()
if "gmail_sender_email" not in st.session_state:
    st.session_state.gmail_sender_email = (
        gmail_auth.get_sender_email() if st.session_state.gmail_signed_in else None
    )
if "sent_email_keys" not in st.session_state:
    st.session_state.sent_email_keys = {}


# ─────────────────────────────────────────────────────────────
# Background agent runner
# ─────────────────────────────────────────────────────────────
def run_agent_in_background(vcf_path: Path, pdf_path: Path, event_q: queue.Queue) -> None:
    """Run the orchestrator in a background thread. Events flow: async bus → sync queue."""

    async def _bridge() -> None:
        bus = EventBus()
        orch = CaseOrchestrator(vcf_path=vcf_path, pdf_path=pdf_path, bus=bus)

        async def _drain() -> None:
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
        event_q.put(
            AgentEvent(
                kind=EventKind.TOOL_ERROR,
                label=f"Fatal agent error: {e}",
                payload={"error": str(e)},
            )
        )
        event_q.put(None)


# ─────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.markdown("## 🧬")
with col_title:
    st.markdown("### NeoVax — Autonomous Cancer Vaccine Pipeline")
    st.caption(
        "Upload a tumor VCF and pathology PDF. One agent handles the rest: neoantigen pipeline, 3D validation, "
        "lab discovery, email drafts, and scheduling."
    )

st.divider()

# ─────────────────────────────────────────────────────────────
# Gmail sign-in panel
# ─────────────────────────────────────────────────────────────
with st.container(border=True):
    if st.session_state.gmail_signed_in and st.session_state.gmail_sender_email:
        col_status, col_action = st.columns([5, 1])
        with col_status:
            st.markdown(
                f"**Gmail:** signed in as `{st.session_state.gmail_sender_email}` — "
                "drafted emails can be sent directly."
            )
        with col_action:
            if st.button("Sign out", key="gmail_sign_out", use_container_width=True):
                gmail_auth.sign_out()
                st.session_state.gmail_signed_in = False
                st.session_state.gmail_sender_email = None
                st.session_state.sent_email_keys = {}
                st.rerun()
    else:
        col_status, col_action = st.columns([5, 1])
        with col_status:
            st.markdown(
                "**Gmail:** not signed in. Drafts will still generate, but you "
                "won't be able to send them."
            )
            st.caption(
                f"Needs a Desktop-app OAuth client JSON at "
                f"`{gmail_auth.default_client_secret_path()}` "
                "(or set `NEOVAX_GOOGLE_CLIENT_SECRET`)."
            )
        with col_action:
            if st.button("Sign in with Google", key="gmail_sign_in", use_container_width=True):
                try:
                    with st.spinner("Complete Google sign-in in the browser tab that just opened…"):
                        _, sender = gmail_auth.run_sign_in_flow()
                    st.session_state.gmail_signed_in = True
                    st.session_state.gmail_sender_email = sender
                    st.toast(f"Signed in as {sender}", icon="✅")
                    st.rerun()
                except FileNotFoundError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Sign-in failed: {type(e).__name__}: {e}")

# ─────────────────────────────────────────────────────────────
# Input section
# ─────────────────────────────────────────────────────────────
if not st.session_state.running and not st.session_state.done:
    with st.container(border=True):
        st.markdown("#### New case")
        c1, c2 = st.columns(2)
        with c1:
            pdf_file = st.file_uploader("Pathology report (PDF)", type=["pdf"], key="pdf_up")
            if pdf_file is None and (SAMPLE_DIR / "luna_pathology.pdf").exists():
                st.caption("No file? Try the bundled demo case →")
        with c2:
            vcf_file = st.file_uploader("Tumor VCF / TSV", type=["vcf", "tsv"], key="vcf_up")
            if vcf_file is None and (SAMPLE_DIR / "luna_tumor.vcf").exists():
                st.caption("Bundled: `backend/sample_data/luna_tumor.vcf` (10 mutations)")

        demo_btn = st.button("🐕 Run bundled demo (Luna)", type="primary", use_container_width=True)
        custom_btn = st.button("▶ Run on uploaded files", disabled=(pdf_file is None or vcf_file is None), use_container_width=True)

        if demo_btn or custom_btn:
            if demo_btn:
                pdf_path = (SAMPLE_DIR / "luna_pathology.pdf").resolve()
                vcf_path = (SAMPLE_DIR / "luna_tumor.vcf").resolve()
            else:
                upload_dir = OUT_DIR / "uploads"
                upload_dir.mkdir(parents=True, exist_ok=True)
                pdf_path = upload_dir / pdf_file.name
                vcf_path = upload_dir / vcf_file.name
                pdf_path.write_bytes(pdf_file.read())
                vcf_path.write_bytes(vcf_file.read())

            event_q: queue.Queue = queue.Queue()
            st.session_state.event_queue = event_q
            st.session_state.events = []
            st.session_state.running = True
            st.session_state.done = False
            st.session_state.started_at = time.time()
            thread = threading.Thread(
                target=run_agent_in_background,
                args=(vcf_path, pdf_path, event_q),
                daemon=True,
            )
            thread.start()
            st.session_state.agent_thread = thread
            st.rerun()


# ─────────────────────────────────────────────────────────────
# Live feed layout
# ─────────────────────────────────────────────────────────────
def _drain_queue() -> bool:
    """Pull all available events from queue to session state. Returns True if DONE received."""
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
        st.session_state.events.append(ev)
        if ev.kind == EventKind.DONE:
            done = True
    return done


def _kind_style(kind: EventKind) -> tuple[str, str]:
    """Return (icon, color) for event rendering."""
    return {
        EventKind.TOOL_START: ("⏳", "#0ea5e9"),
        EventKind.TOOL_RESULT: ("✅", "#10b981"),
        EventKind.TOOL_ERROR: ("❌", "#ef4444"),
        EventKind.STRUCTURE_READY: ("🔭", "#8b5cf6"),
        EventKind.EMAIL_DRAFTED: ("📧", "#f59e0b"),
        EventKind.EMAIL_SENT: ("🚀", "#10b981"),
        EventKind.CASE_UPDATE: ("📋", "#6b7280"),
        EventKind.LOG: ("💬", "#64748b"),
        EventKind.DONE: ("🎉", "#10b981"),
    }.get(kind, ("•", "#6b7280"))


def _render_feed(container) -> None:
    with container:
        if not st.session_state.events:
            st.info("Waiting for agent…")
            return
        for ev in st.session_state.events[-60:]:  # last 60
            icon, color = _kind_style(ev.kind)
            ts = datetime.fromtimestamp(ev.timestamp).strftime("%H:%M:%S")
            st.markdown(
                f"<div style='padding:6px 10px; border-left:3px solid {color}; margin:2px 0; background:#f8fafc; border-radius:0 6px 6px 0;'>"
                f"<span style='color:{color}; font-weight:600;'>{icon}</span> "
                f"<span style='color:#64748b; font-size:0.8em;'>{ts}</span> &nbsp; "
                f"<span>{ev.label}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )


def _render_package(container, case) -> None:
    """Fill in the right-side treatment package from the accumulated case."""
    with container:
        if case is None:
            elapsed = int(time.time() - (st.session_state.started_at or time.time()))
            st.metric("Elapsed", f"{elapsed}s")
            st.caption("The treatment package will populate here as the agent progresses.")
            return

        # Pathology summary
        with st.container(border=True):
            st.markdown(f"#### 📋 {case.pathology.patient_name}")
            cols = st.columns(4)
            cols[0].metric("Species", case.pathology.species.title())
            cols[1].metric("Breed", case.pathology.breed or "—")
            cols[2].metric("Age", f"{case.pathology.age_years}y" if case.pathology.age_years else "—")
            cols[3].metric("Grade", case.pathology.grade or "—")
            st.write(f"**Cancer:** {case.pathology.cancer_type}")
            if case.pathology.owner_location:
                st.caption(f"📍 {case.pathology.owner_location}")

        # Top candidates + construct
        if case.pipeline and case.pipeline.candidates:
            with st.container(border=True):
                st.markdown("#### 💊 Top vaccine candidates")
                rows = []
                for c in case.pipeline.candidates[:8]:
                    rows.append(
                        {
                            "#": c.rank,
                            "Peptide": c.peptide.sequence,
                            "Gene/Mut": c.peptide.mutation.full_label,
                            "nM": f"{c.peptide.score_nm:.2f}" if c.peptide.score_nm else "—",
                        }
                    )
                st.dataframe(rows, hide_index=True, use_container_width=True)
                if case.pipeline.vaccine:
                    v = case.pipeline.vaccine
                    st.caption(
                        f"**Construct:** {len(v.epitopes)} epitopes · {v.length_bp} bp · ~${v.estimated_cost_usd:.0f}"
                    )

        # 3D structures
        if case.structures:
            with st.container(border=True):
                st.markdown("#### 🔭 3D structure validation")
                for s in case.structures[:3]:
                    st.caption(f"**{s.peptide_sequence}** — {s.mutation_label} in {s.dla_allele} (method: {s.method})")
                    if s.pdb_text:
                        try:
                            import py3Dmol

                            view = py3Dmol.view(width=500, height=260)
                            view.addModel(s.pdb_text, "pdb")
                            view.setStyle({"cartoon": {"color": "spectrum"}})
                            view.addStyle({"hetflag": False}, {"stick": {"radius": 0.2}})
                            view.zoomTo()
                            html = view._make_html()
                            st.components.v1.html(html, height=280)
                        except Exception as e:
                            st.warning(f"3D render failed: {e}")

        # Labs
        if case.sequencing_labs or case.vet_oncologists or case.synthesis_vendors:
            with st.container(border=True):
                st.markdown("#### 🏥 Real-world resources")
                tabs = st.tabs(["Sequencing labs", "Vet oncologists", "Synthesis vendors"])
                for tab, labs, empty in [
                    (tabs[0], case.sequencing_labs, "No sequencing labs found."),
                    (tabs[1], case.vet_oncologists, "No vet oncologists found."),
                    (tabs[2], case.synthesis_vendors, "No synthesis vendors listed."),
                ]:
                    with tab:
                        if not labs:
                            st.caption(empty)
                            continue
                        for lab in labs[:6]:
                            st.markdown(f"**{lab.name}**")
                            line_parts = []
                            if lab.address:
                                line_parts.append(f"📍 {lab.address}")
                            if lab.phone:
                                line_parts.append(f"📞 {lab.phone}")
                            if lab.email:
                                line_parts.append(f"✉️ {lab.email}")
                            if lab.website:
                                line_parts.append(f"🌐 [{lab.website}]({lab.website})")
                            st.caption(" · ".join(line_parts))
                            if lab.estimated_cost_usd or lab.turnaround_days:
                                cost = f"${lab.estimated_cost_usd:.0f}" if lab.estimated_cost_usd else "—"
                                days = f"{lab.turnaround_days}d" if lab.turnaround_days else "—"
                                st.caption(f"💰 {cost} · ⏱ {days}")
                            if lab.notes:
                                st.caption(lab.notes)
                            st.markdown("---")

        # Emails
        if case.emails:
            with st.container(border=True):
                st.markdown("#### 📧 Drafted correspondence")
                for i, email in enumerate(case.emails):
                    with st.expander(f"**{email.subject}** → {email.recipient_name}", expanded=(i == 0)):
                        st.text(f"To: {email.recipient_email or '(not resolved)'}")
                        st.text(f"Subject: {email.subject}")
                        st.code(email.body, language="text")

                        sent_key = f"{email.subject}|{email.recipient_email or ''}"
                        already_sent = email.sent or sent_key in st.session_state.sent_email_keys

                        if already_sent:
                            sent_id = (
                                email.sent_message_id
                                or st.session_state.sent_email_keys.get(sent_key, "—")
                            )
                            st.success(f"✓ Sent (message id: {sent_id})")
                        elif not st.session_state.gmail_signed_in:
                            st.button(
                                "📤 Send via Gmail",
                                key=f"send_{i}",
                                disabled=True,
                                help="Sign in with Google above to enable sending.",
                            )
                        elif st.button(
                            "📤 Send via Gmail",
                            key=f"send_{i}",
                            disabled=not email.recipient_email,
                        ):
                            with st.spinner(f"Sending to {email.recipient_email}…"):
                                result = send_via_gmail(email)
                            if "message_id" in result:
                                st.session_state.sent_email_keys[sent_key] = result["message_id"]
                                st.toast(f"Sent to {email.recipient_email}", icon="✅")
                                st.rerun()
                            else:
                                st.error(f"Send failed: {result.get('error', 'unknown')}")

        # Timeline
        if case.timeline:
            with st.container(border=True):
                st.markdown("#### 📅 Treatment timeline")
                for ev in case.timeline:
                    st.markdown(f"**Week {ev.week}** · _{ev.date_iso}_ — **{ev.title}**")
                    st.caption(ev.description)

        # Plain-English explanation
        if case.plain_english:
            with st.container(border=True):
                st.markdown("#### 📝 For the owner — in plain English")
                st.write(case.plain_english)


# ─────────────────────────────────────────────────────────────
# Main layout
# ─────────────────────────────────────────────────────────────
if st.session_state.running or st.session_state.done:
    elapsed = int(time.time() - (st.session_state.started_at or time.time()))
    st.caption(
        f"{'▶ Running' if st.session_state.running else '✅ Complete'} · {elapsed}s elapsed · "
        f"{len(st.session_state.events)} events"
    )

    feed_col, pkg_col = st.columns([3, 4])
    feed_container = feed_col.container(height=800)
    pkg_container = pkg_col.container(height=800)

    done_now = _drain_queue()
    if done_now:
        st.session_state.running = False
        st.session_state.done = True

    _render_feed(feed_container)

    # Try to reconstruct case from events
    case = build_case_file(st.session_state.events)
    _render_package(pkg_container, case)

    # Keep polling while running
    if st.session_state.running:
        time.sleep(0.4)
        st.rerun()

    # Reset button
    if st.session_state.done:
        if st.button("↻ New case", type="secondary"):
            for k in ["events", "event_queue", "agent_thread", "running", "done", "started_at", "sent_email_keys"]:
                st.session_state.pop(k, None)
            st.rerun()
