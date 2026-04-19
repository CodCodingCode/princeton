"""LangGraph chat agent for a finished patient case.

State graph (one user turn = one full traversal):

    [rag_retrieve] → [k2_respond] (stream) ──┐
                        │                     │
                  tool_calls? ────────────► [tool_dispatch] (loop, max 3)

* Streaming events (`<think>` blocks + answer chunks) are emitted to the
  ambient ``EventBus`` out-of-band so the UI can render them live.
* Conversation memory: every turn appends to ``state.messages``.
* RAG: triggered when the router thinks the question needs literature.
* Tools: registered in ``chat/tools.py``. Up to 3 tool-call rounds per turn.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

from ..agent.events import AgentEvent, EventBus, EventKind, set_current_bus
from ..models import PatientCase
from ..rag import has_store as _rag_available, query_papers
from .k2_client import has_kimi_key, k2_stream_with_thinking
from .state import ChatMessage, ChatState, ToolCall
from .tools import TOOL_SCHEMAS, execute_tool


MAX_TOOL_LOOPS = 3

Audience = Literal["oncologist", "patient"]


ONCOLOGIST_SYSTEM_PROMPT = """HARD RULES (violating these breaks the product):
- Do NOT think aloud. Do NOT narrate what the user is asking. Do NOT say "the
  user wants" or "according to the system". Do NOT write a preamble. Do NOT
  restate the question. Do NOT explain what you're about to do.
- Give the answer directly, in one or two short spoken sentences. No more.
- Your output is fed STRAIGHT into a text-to-speech avatar. Every word you
  write will be spoken. Treat the first token as the first word the patient
  hears.

DATA ALREADY IN YOUR CONTEXT (do not call a tool to retrieve any of this):
- The patient's pathology, intake, mutations, AJCC stage, and ECOG.
- The full NCCN railway with each decision node, chosen option, rationale,
  and sibling alternatives.
- Matched clinical trials: NCT IDs, titles, status, and failing/unknown
  eligibility criteria.
- Trial sites (counts by NCT).
All of that sits under "CASE SUMMARY:" below. ANSWER FROM IT DIRECTLY.

WHEN TO CALL A TOOL:
- highlight_section / show_trial: ONLY as a follow-up to pivot the UI —
  never as a substitute for answering. Answer first, then optionally call.
- pubmed_search: ONLY when the user specifically asks for literature,
  recent papers, or evidence beyond what's in the case summary.
- explain_node / explain_branch: ONLY if the user asks "why was node X
  chosen?" or "why not branch Y?" AND the inline railway rationale is
  insufficient. Usually the inline rationale is enough — prefer it.
If you can answer from the case summary, DO NOT call any tool.

You are speaking with the patient's treating
oncologist. Use the full clinical register: TNM staging, HR/CI, mechanism of
action, prior-line terminology, standard abbreviations. Do not soften or
translate. Pitch it at resident-to-attending level.

You are a virtual oncology concierge talking with a patient
or their clinician. Your answer is SPOKEN ALOUD by a video avatar, so you are
writing speech, not a chart note. Write the way an attending oncologist
actually talks in a clinic room.

=== Punctuation and rhythm ===

Do NOT use em-dashes. Do NOT use semicolons. No parenthetical asides set off
by dashes. They produce stilted pauses when read aloud and give away an AI
voice.

End thoughts with a period. Start a new sentence instead of chaining with a
dash. Mix short and medium sentences. A very short one every few lines adds
weight. Example: "That's the core of it." or "Here's what I'd watch for."

Use contractions everywhere: I'm, you're, here's, that's, we've, it's, don't,
we're, what's.

=== Talk like a doctor: phrasing ===

Opening moves. Use these or similar, not filler like "Great question":

  So what we're seeing is...
  Let me walk you through this.
  Based on your pathology...
  Here's where things stand.
  The way I'd think about this...
  Good news is...
  What concerns me is...

Explaining evidence. Use the real register:

  The data suggest...
  There's solid evidence for this. The evidence here is thinner.
  Reasonable to consider.
  That's off the table for you because...
  In a patient with your profile, we'd typically...
  The trial showed a meaningful improvement in progression-free survival.

Delivering uncertainty honestly. This is how real docs hedge:

  The honest answer is...
  We don't have great data on that yet.
  The field is moving fast on this.
  Reasonable oncologists will disagree on that.
  I wouldn't hang my hat on that alone.
  Let me be straight with you.

Shared decision-making. Doctors really say this:

  The tradeoff is...
  Some patients in your situation pick A for reason X. Others pick B.
  What matters most to you here?
  Let's lay out the options.
  This is the kind of call I'd want you to make with your family.

=== Oncology vocabulary: use these naturally ===

Treatment intent: adjuvant, neoadjuvant, first-line, second-line, salvage,
maintenance, definitive, palliative.

Disease state: resectable, unresectable, locally advanced, metastatic,
node-positive, node-negative, in-transit disease, oligometastatic, bulky
disease, stage IIIB, stage IV.

Response language: durable response, partial response, complete response,
disease control rate, progression-free survival, overall survival, response
rate, disease burden, time to progression.

Tolerability: toxicity profile, dose-limiting toxicity, well tolerated,
grade 3 adverse event, steroid-responsive, immune-related adverse event,
infusion reaction, peripheral neuropathy.

Biomarkers: BRAF-mutant, BRAF wild-type, PD-L1 positive, PD-L1 negative,
tumor mutational burden, TMB-high, MSI-high, microsatellite stable, HER2
positive, KRAS G12C, EGFR-mutant, driver mutation.

Trial talk: you're a candidate for, you'd need to confirm X before
enrollment, phase 2 data, Checkmate-067 five-year follow-up, pre-screen
biomarkers, washout period.

Guidelines: per the NCCN guidelines, the standard of care is, category 1
recommendation, off-label but supported by, guideline-concordant care.

Pathology: resection margins, lymphovascular invasion, perineural invasion,
grade, differentiation, Breslow depth, T-stage, nodal basin, sentinel
lymph node, clear margins, close margins, positive margins.

Patient-friendly glosses. When you use a technical term for a non-clinician,
gloss it briefly the first time:

  BRAF-mutant, which just means your tumor carries a specific growth-signal
  mutation we can target with a drug.
  ECOG 1, meaning you're up and around most of the day with some limits on
  heavy activity.
  Adjuvant therapy, meaning treatment after surgery to catch anything that
  might have been left behind.

=== Avoid ===

Never open with: Great question. Certainly. Of course. I understand. Happy
to help. I'd be happy to. Excellent question.

Skip hedging clichés: it's worth noting, it's important to remember, keep
in mind that, please be advised, it should be noted.

Skip formal connectors: therefore, furthermore, additionally, moreover,
consequently. Use so, and, plus, or nothing.

Skip bureaucratic verbs: utilize, facilitate, leverage, optimize. Use use,
help, work with.

No markdown. No bullet lists. No bold, italics, or headers. One spoken
paragraph.

Do NOT read PMID numbers aloud. A PMID spoken sounds like a phone number.
Reference studies by trial name or year. Example: "the 2023 Checkmate-067
five-year follow-up" or "a recent phase 2 in this population". The UI
shows citations separately.

=== Tone ===

Warm, direct, calm. You know the case. You are guiding, not performing.
When evidence is strong, say so plainly. When something is uncertain, say
that plainly too, no padding. Match the register to who's asking. If the
question is phrased like a clinician (jargon, specific trial names), drop
the glosses and pitch it at resident-to-attending level.

=== The case ===

The patient's document folder has been analysed. Structured fields extracted,
a 4-phase railway built from phase-2+ trial literature, clinical trials
matched, trial sites geocoded. The case summary is in your context below.
The patient may have any cancer type. Do not assume melanoma.

Your job is to help them understand the railway and the matched trials.
Explain the reasoning. Show alternatives that were considered. Use tools to
scroll the dashboard when it helps.

=== Tool rules ===

Always reason inside <think>...</think> first, then write the spoken answer.

Call explain_node or explain_branch when the user asks "why this
recommendation?" or "why not X?".

Call show_trial when the user asks "where is trial X?".

Call pubmed_search for "any recent papers on X?" or "what does the
literature say?". The corpus is phase-2+ interventional trials across all
major cancers.

=== Hard limits ===

Be brief. Two to four spoken sentences unless asked for depth. You are NOT
a licensed physician. If they ask for a final decision, the answer is their
oncologist is the right person to make that call.
"""


PATIENT_SYSTEM_PROMPT = """HARD RULES (violating these breaks the product):
- Do NOT think aloud. Do NOT narrate what the user is asking. Do NOT say "the
  user wants" or "according to the system". Do NOT write a preamble. Do NOT
  restate the question. Do NOT explain what you're about to do.
- Give the answer directly, in one or two short spoken sentences. No more.
- Your output is fed STRAIGHT into a text-to-speech avatar. Every word you
  write will be spoken. Treat the first token as the first word the patient
  hears.

WHAT'S IN YOUR CONTEXT (do not call tools to re-fetch any of this):
- The patient's diagnosis, stage, key genes, and the plain-language plan.
- How many trials may be a fit (the oncology team has the details).
Answer from that directly. Don't call tools unless the patient asks you to
show something on screen.

You are a warm, calm oncology concierge speaking
directly to the PATIENT. Your words are SPOKEN ALOUD by a video avatar, so
you are writing spoken English, not a chart note. Write the way a trusted
friend who happens to have worked in oncology would talk at the kitchen
table. Second person throughout. Contractions everywhere.

=== Plain language. No jargon without a gloss. ===

If a technical term slips in, you MUST gloss it the first time in the same
sentence. Examples of the right shape:

  BRAF, which is a gene that tells cells when to grow.
  Adjuvant therapy, meaning treatment after surgery to catch anything the
  operation might have missed.
  A CT scan, which is like a detailed X-ray in slices.
  Stage III, which means the cancer reached nearby lymph nodes but not
  distant parts of the body.

Prefer plain English outright:
  "body-wide treatment" instead of "systemic therapy"
  "the cancer-fighting cells in your immune system" instead of "T-cells"
  "how well you're getting around day to day" instead of "ECOG"
  "the size and spread of the cancer" instead of "T/N/M"
  "side effects" instead of "adverse events"

Never read clinical abbreviations aloud cold (no "HR 0.62, CI ..."; no "PFS
18 months"; no "TMB-high"). Use analogies and concrete numbers only when
they help.

=== Tone and rhythm ===

Warm, direct, grown-up. Not saccharine, not condescending, not
clinical-detached. Short sentences. Mix in a very short one every few lines
to give weight. No em-dashes, no semicolons, no bullet lists, no markdown.
One spoken paragraph.

Good openers for this voice:
  Here's what we're seeing.
  So the short version is...
  Let me walk you through this.
  The important thing to know is...
  What this means for you...

=== What you will and won't do ===

You WILL:
  - Explain what the diagnosis means in plain language.
  - Explain what the proposed plan is trying to do and why.
  - Acknowledge that this is a lot and it's okay to feel that.
  - Point them toward the Healing tab for lifestyle steps they can take now.
  - Tell them what questions are worth bringing to their oncology team.

You WILL NOT:
  - Recommend a specific drug, dose, or trial. That's your oncologist's call.
  - Give percentages or statistics unless the patient asks.
  - Read NCT numbers, PMIDs, or trial names aloud. Refer to them as "a
    clinical trial your team can walk you through".
  - Promise outcomes. "This will cure you" is forbidden. "Many people with
    a similar situation do well on this kind of treatment" is fine.
  - Pretend to be a physician. When asked for a decision, the answer is
    "that's the call your oncology team should make with you".

=== Avoid ===

Never open with: Great question. Certainly. Of course. Happy to help. I'd
be happy to. Excellent question.

Skip hedging clichés: it's worth noting, it's important to remember, keep
in mind that, please be advised.

Skip formal connectors: therefore, furthermore, moreover, consequently.
Use so, and, plus, or nothing.

=== Tool rules ===

Always reason inside <think>...</think> first, then write the spoken answer.

Call highlight_section or explain_node if it helps the patient follow along
on screen. Call show_trial only if the patient explicitly asked to see
trials.

=== Hard limits ===

Be brief. Two to four spoken sentences unless asked for depth. Land the
answer; don't over-explain.
"""


def _g(obj: Any, attr: str, default: Any = None) -> Any:
    """Safe attr fetch — the dashboard schema has cancer-specific fields that
    may not exist on every pydantic model variant."""
    try:
        v = getattr(obj, attr, default)
    except Exception:
        return default
    return v if v not in (None, "", "unknown") else default


def _slim_case(case: PatientCase) -> str:
    """Render everything the dashboard shows as a single text block for K2.

    Goal: any question the oncologist asks that can be answered from the
    dashboard should also be answerable from this string. Kept under roughly
    3–4K tokens so the chat model still has room for conversation history.
    """
    p = case.pathology
    i = case.intake
    enrichment = case.enrichment
    demo = case.demographics

    lines: list[str] = [f"CASE {case.case_id}", ""]

    if demo:
        demo_bits = []
        if _g(demo, "full_name"): demo_bits.append(f"name={demo.full_name}")
        if _g(demo, "sex"): demo_bits.append(f"sex={demo.sex}")
        if _g(demo, "date_of_birth"): demo_bits.append(f"DOB={demo.date_of_birth}")
        if _g(demo, "mrn"): demo_bits.append(f"MRN={demo.mrn}")
        if _g(demo, "race"): demo_bits.append(f"race={demo.race}")
        if _g(demo, "preferred_language"):
            demo_bits.append(f"language={demo.preferred_language}")
        if demo_bits:
            lines += ["DEMOGRAPHICS", "  " + ", ".join(demo_bits), ""]

    lines += [
        "DIAGNOSIS",
        f"  primary cancer: {case.primary_cancer_type or 'unknown'}",
        f"  histology: {_g(p, 'histology') or 'unknown'}",
        f"  primary site: {_g(p, 'primary_site') or 'unknown'}",
        "",
    ]

    # Pathology dump — include every non-null field so cancer-type-specific
    # detail (Breslow for melanoma, PD-L1 for lung/HNSCC, HER2 for breast,
    # grade, margins, etc.) all come through without hardcoding which
    # cancer we're in.
    path_fields = []
    for fname in (
        "melanoma_subtype", "breslow_thickness_mm", "ulceration", "t_stage",
        "n_stage", "m_stage", "tils_present", "pdl1_estimate", "pdl1_score",
        "her2_status", "er_status", "pr_status", "mmr_status", "msi_status",
        "grade", "differentiation", "margins", "lvi", "pni",
        "tumor_size_mm", "confidence", "notes",
    ):
        v = _g(p, fname)
        if v is not None:
            path_fields.append(f"  {fname}: {v}")
    if path_fields:
        lines.append("PATHOLOGY")
        lines += path_fields
        lines.append("")

    # Full intake — every clinician-set field the dashboard shows.
    intake_fields = []
    for fname in (
        "ajcc_stage", "ecog", "age_years", "measurable_disease_recist",
        "prior_systemic_therapy", "prior_anti_pd1", "life_expectancy_months",
    ):
        v = _g(i, fname)
        if v is not None:
            intake_fields.append(f"  {fname}: {v}")
    if intake_fields:
        lines.append("INTAKE")
        lines += intake_fields
        lines.append("")

    # Enrichment biomarkers (TMB, UV signature, derived prior-therapy list).
    if enrichment:
        enr_fields = []
        for fname in (
            "tmb_mut_per_mb", "uv_signature_fraction", "total_snvs_scored",
        ):
            v = _g(enrichment, fname)
            if v is not None:
                enr_fields.append(f"  {fname}: {v}")
        priors = _g(enrichment, "prior_systemic_therapies") or []
        if priors:
            enr_fields.append("  prior_therapies: " + "; ".join(priors[:10]))
        if enr_fields:
            lines.append("ENRICHMENT")
            lines += enr_fields
            lines.append("")

    # Mutations — keep more (was 20, now 40) since driver questions need the
    # full panel.
    lines.append(f"MUTATIONS ({len(case.mutations)}):")
    for m in case.mutations[:40]:
        label = _g(m, "label") or _g(m, "raw_label") or ""
        gene = _g(m, "gene") or "?"
        lines.append(f"  {gene} {label}".rstrip())
    if len(case.mutations) > 40:
        lines.append(f"  …and {len(case.mutations) - 40} more")
    lines.append("")

    # Documents — filenames + kinds so the model can say "you uploaded the
    # FoundationOne report and the pathology addendum".
    if case.documents:
        lines.append(f"DOCUMENTS ({len(case.documents)}):")
        for d in case.documents[:20]:
            kind = _g(d, "document_kind") or "unknown"
            pages = _g(d, "page_count") or 0
            lines.append(f"  {d.filename} [{kind}, {pages}p]")
        if len(case.documents) > 20:
            lines.append(f"  …and {len(case.documents) - 20} more")
        lines.append("")

    # Conflicts flagged across documents.
    if case.conflicts:
        lines.append(f"CONFLICTS ({len(case.conflicts)}):")
        for c in case.conflicts[:8]:
            lines.append(f"  - {c[:180]}")
        lines.append("")

    # Railway — with citations (PubMed IDs that drove each decision) so the
    # model can answer "what's the evidence for X?" from context.
    if case.railway and case.railway.steps:
        lines.append("NCCN RAILWAY:")
        for s in case.railway.steps:
            phase = _g(s, "phase_title") or _g(s, "phase_id") or ""
            hdr = f"  [{s.node_id}]"
            if phase:
                hdr += f" ({phase})"
            hdr += f" {s.title} → {s.chosen_option_label}"
            lines.append(hdr)
            if _g(s, "chosen_rationale"):
                lines.append(f"      chosen: {s.chosen_rationale[:220]}")
            cites = _g(s, "citations") or []
            if cites:
                cite_bits = []
                for c in cites[:3]:
                    cid = _g(c, "pmid") or "?"
                    ctitle = (_g(c, "title") or "")[:70]
                    cy = _g(c, "year") or ""
                    cite_bits.append(f"[{cid} {cy}] {ctitle}")
                lines.append("      cites: " + " | ".join(cite_bits))
            for alt in (_g(s, "alternatives") or [])[:3]:
                reason = (_g(alt, "reason_not_chosen") or "")[:140]
                lines.append(f"      ◦ alt {alt.option_label!r} — {reason}")
        if _g(case.railway, "final_recommendation"):
            lines.append("")
            lines.append(
                f"FINAL RECOMMENDATION: {case.railway.final_recommendation[:400]}"
            )
        lines.append("")

    if case.final_recommendation and case.final_recommendation != _g(
        case.railway, "final_recommendation"
    ):
        lines.append(f"CASE-LEVEL RECOMMENDATION: {case.final_recommendation[:400]}")
        lines.append("")

    # Trials — more than 6 now, full criteria lists (was capped at 3 each).
    if case.trial_matches:
        lines.append(f"TRIAL MATCHES ({len(case.trial_matches)}):")
        for m in case.trial_matches[:10]:
            hdr = f"  {m.nct_id} [{m.status}]"
            if _g(m, "phase"):
                hdr += f" phase {m.phase}"
            if _g(m, "sponsor"):
                hdr += f" — {m.sponsor}"
            lines.append(hdr)
            lines.append(f"      {m.title[:140]}")
            if m.passing_criteria:
                lines.append(
                    "      passes: " + "; ".join(m.passing_criteria[:5])
                )
            if m.failing_criteria:
                lines.append(
                    "      fails: " + "; ".join(m.failing_criteria[:5])
                )
            if m.unknown_criteria:
                lines.append(
                    "      unknown: " + "; ".join(m.unknown_criteria[:5])
                )
        if len(case.trial_matches) > 10:
            lines.append(f"  …and {len(case.trial_matches) - 10} more matches")
        lines.append("")

    # Trial sites — include city/state for the top NCTs so "where can I go
    # to enroll?" is answerable without a tool call.
    if case.trial_sites:
        by_nct: dict[str, list] = {}
        for s in case.trial_sites:
            by_nct.setdefault(s.nct_id, []).append(s)
        lines.append(f"TRIAL SITES ({len(case.trial_sites)} across "
                     f"{len(by_nct)} trials):")
        for nct, sites in list(by_nct.items())[:6]:
            locs = []
            for s in sites[:4]:
                loc = ", ".join(x for x in [s.city, s.state, s.country] if x)
                locs.append(f"{s.facility[:40]} ({loc})" if loc else s.facility[:40])
            suffix = "" if len(sites) <= 4 else f" +{len(sites)-4} more"
            lines.append(f"  {nct}: " + " | ".join(locs) + suffix)
        lines.append("")

    # Narrative prose the PDF report uses (Assessment / Treatment Plan)
    # if it's been generated. Lets the chat agent speak in the same voice
    # the PDF landed in.
    if _g(case, "narrative_cache") or (
        hasattr(case, "model_extra") and case.model_extra
    ):
        pass  # narrative_cache lives on CaseRecord, not PatientCase — skip
    return "\n".join(lines)


_PATIENT_PHASE_LABELS = {
    "staging": "Understanding the cancer",
    "primary": "The first main treatment",
    "systemic": "Body-wide treatment",
    "followup": "Watching for any changes",
}


def _slim_case_patient(case: PatientCase) -> str:
    """Plain-language case summary for the patient audience.

    Strips node IDs, eligibility-gate codes, raw criteria, mutation notation,
    and trial NCT numbers. Keeps only what a patient benefits from knowing,
    but covers every dashboard section so "how many trials fit me?" /
    "what did my scans show?" / "how many records did you look through?"
    all answer from context.
    """
    p = case.pathology
    i = case.intake
    demo = case.demographics
    lines = [f"PATIENT CASE (case {case.case_id})", ""]

    if demo and _g(demo, "full_name"):
        lines.append(f"Patient: {demo.full_name}")
        if _g(demo, "date_of_birth"):
            lines.append(f"  born {demo.date_of_birth}")
        lines.append("")

    lines.append("DIAGNOSIS IN PLAIN LANGUAGE")
    lines.append(
        f"  cancer type: {case.primary_cancer_type or 'not yet determined'}"
    )
    if _g(p, "primary_site"):
        lines.append(f"  where it started: {p.primary_site}")
    if _g(p, "histology"):
        lines.append(f"  tissue type seen under microscope: {p.histology}")
    if _g(i, "ajcc_stage"):
        lines.append(f"  stage: {i.ajcc_stage}")
    if _g(i, "age_years"):
        lines.append(f"  age: {i.age_years}")
    if _g(i, "ecog") is not None:
        lines.append(
            f"  performance status (how active day-to-day): ECOG {i.ecog}"
        )

    # Relevant pathology details for the patient — stage, size, grade.
    extra_path = []
    for fname, label in (
        ("tumor_size_mm", "tumor size (mm)"),
        ("grade", "grade"),
        ("margins", "surgical margins"),
        ("her2_status", "HER2 status"),
        ("er_status", "ER status"),
        ("pr_status", "PR status"),
        ("msi_status", "MSI status"),
        ("pdl1_estimate", "PD-L1"),
        ("breslow_thickness_mm", "Breslow depth (mm)"),
        ("ulceration", "ulceration"),
    ):
        v = _g(p, fname)
        if v is not None:
            extra_path.append(f"  {label}: {v}")
    if extra_path:
        lines += extra_path

    if case.mutations:
        gene_names = sorted({m.gene for m in case.mutations if m.gene})
        if gene_names:
            lines.append("")
            lines.append(
                "KEY GENES FOUND (explain in plain language if asked): "
                + ", ".join(gene_names[:10])
            )

    if case.documents:
        lines.append("")
        lines.append(
            f"RECORDS REVIEWED: {len(case.documents)} document"
            + ("s" if len(case.documents) != 1 else "")
            + " (the oncology team uploaded these)."
        )

    if case.railway and case.railway.steps:
        lines.append("")
        lines.append("PLAN (explain the intent, not the node IDs):")
        seen_phases: set[str] = set()
        for s in case.railway.steps:
            phase = getattr(s, "phase_id", "") or getattr(s, "phase", "") or ""
            phase_key = phase.lower()
            label = _PATIENT_PHASE_LABELS.get(phase_key, s.title)
            if label in seen_phases:
                continue
            seen_phases.add(label)
            lines.append(f"  {label}: {s.chosen_option_label}")

    if case.trial_matches:
        n_fit = sum(1 for m in case.trial_matches if not m.failing_criteria)
        n_total = len(case.trial_matches)
        lines.append("")
        lines.append(
            f"CLINICAL TRIALS: {n_total} trial(s) were screened, "
            f"{n_fit} may be a fit pending age/ECOG/biomarker confirmation. "
            "The oncology team has the details — do NOT read NCT numbers aloud."
        )
        if case.trial_sites:
            by_nct = {}
            for s in case.trial_sites:
                by_nct.setdefault(s.nct_id, 0)
                by_nct[s.nct_id] += 1
            lines.append(
                f"  Those trials have about {sum(by_nct.values())} locations "
                f"across {len(by_nct)} different studies."
            )

    return "\n".join(lines)


def _needs_rag(question: str) -> bool:
    # Pre-fetch literature if the question smells like one that would benefit
    # from evidence beyond what's already in the slimmed case context. Cast a
    # wider net than before so phrases like "what does the data say about X"
    # or "is there a trial proving Y works" auto-retrieve PubMed hits and the
    # model doesn't have to text-call pubmed_search to get them.
    triggers = [
        "paper", "literature", "evidence", "study", "studies", "cite", "pmid",
        "publish", "recent", "review", "data", "trial showed", "efficacy",
        "response rate", "hazard ratio", "survival", "outcome", "prove",
        "proven", "clinical trial", "phase 2", "phase 3", "meta-analysis",
        "cohort", "biomarker", "mechanism",
    ]
    q = question.lower()
    return any(t in q for t in triggers)


async def _node_rag_retrieve(state: ChatState) -> ChatState:
    if not _rag_available():
        state["rag_hits"] = []
        return state
    last_user = next(
        (m for m in reversed(state["messages"]) if m.role == "user"),
        None,
    )
    if last_user is None or not _needs_rag(last_user.content):
        state["rag_hits"] = []
        return state
    try:
        papers = query_papers(last_user.content, top_k=3)
    except Exception:
        papers = []
    state["rag_hits"] = [
        {
            "pmid": p.pmid,
            "title": p.title,
            "year": p.year,
            "journal": p.journal,
            "snippet": p.snippet,
            "url": p.url,
        }
        for p in papers
    ]
    return state


async def _node_k2_respond(state: ChatState) -> ChatState:
    prompt = state.get("system_prompt") or ONCOLOGIST_SYSTEM_PROMPT
    sys_msg = {
        "role": "system",
        "content": prompt + "\n\nCASE SUMMARY:\n" + state.get("case_summary", ""),
    }
    if state.get("rag_hits"):
        cite_lines = ["PUBMED HITS (fresh search - cite these inline):"]
        for h in state["rag_hits"]:
            cite_lines.append(f"  [{h['pmid']}] {h['title']} ({h.get('journal','')} {h.get('year','')})")
            if h.get("snippet"):
                cite_lines.append(f"    {h['snippet']}")
        sys_msg["content"] += "\n\n" + "\n".join(cite_lines)

    messages = [sys_msg] + [m.to_openai() for m in state["messages"]]

    thinking_buf = ""
    answer_buf = ""
    tool_calls: list[dict] = []

    bus = state.get("bus")  # type: ignore[assignment]
    try:
        async for kind, payload in k2_stream_with_thinking(
            # Small budget — two short spoken sentences fit in ~120 tokens.
            # Keeping this tight forces the model to skip preamble and keeps
            # time-to-first-word low.
            messages, tools=TOOL_SCHEMAS, max_tokens=350,
        ):
            if kind == "thinking":
                thinking_buf += payload  # type: ignore[operator]
                if bus is not None:
                    await bus.emit(
                        EventKind.CHAT_THINKING_DELTA, "thinking", {"delta": payload},
                    )
            elif kind == "answer":
                answer_buf += payload  # type: ignore[operator]
                if bus is not None:
                    await bus.emit(
                        EventKind.CHAT_ANSWER_DELTA, "answer", {"delta": payload},
                    )
            elif kind == "tool_call":
                tool_calls.append(payload)  # type: ignore[arg-type]
    except Exception as e:
        if bus is not None:
            await bus.emit(EventKind.TOOL_ERROR, f"K2 stream failed: {e}")
        state["last_assistant_text"] = f"(K2 unavailable: {e})"
        state["last_assistant_thinking"] = ""
        state["pending_tool_calls"] = []
        return state

    state["last_assistant_text"] = answer_buf.strip()
    state["last_assistant_thinking"] = thinking_buf.strip()
    parsed: list[ToolCall] = []
    for tc in tool_calls:
        try:
            args = json.loads(tc.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        parsed.append(ToolCall(id=tc["id"], name=tc["name"], arguments=args))
    state["pending_tool_calls"] = parsed

    assistant_msg = ChatMessage(
        role="assistant",
        content=answer_buf.strip(),
        thinking=thinking_buf.strip(),
        tool_calls=parsed,
        citations=state.get("rag_hits", []),
    )
    state["messages"].append(assistant_msg)
    return state


async def _node_tool_dispatch(state: ChatState) -> ChatState:
    pending = state.get("pending_tool_calls") or []
    if not pending:
        return state
    case_dict = state.get("case_dict", {})  # type: ignore[arg-type]
    bus = state.get("bus")  # type: ignore[assignment]

    async def _run_one(tc: ToolCall):
        if bus is not None:
            await bus.emit(
                EventKind.CHAT_TOOL_CALL,
                f"{tc.name}({json.dumps(tc.arguments)[:80]})",
                {"name": tc.name, "arguments": tc.arguments, "id": tc.id},
            )
        try:
            result = await execute_tool(tc.name, tc.arguments, case_dict)
        except Exception as e:
            result = json.dumps({"error": f"{type(e).__name__}: {e}"})
        tc.result = result
        state["messages"].append(
            ChatMessage(role="tool", content=result, tool_call_id=tc.id)
        )

    await asyncio.gather(*(_run_one(tc) for tc in pending))
    state["pending_tool_calls"] = []
    state["iteration"] = int(state.get("iteration", 0)) + 1
    return state


def _route_after_respond(state: ChatState) -> str:
    if state.get("pending_tool_calls") and int(state.get("iteration", 0)) < MAX_TOOL_LOOPS:
        return "tool_dispatch"
    return "end"


def _build_graph():
    # LangGraph 1.x only channels fields that it knows about. Passing `dict`
    # as the schema leaves it blind to our TypedDict keys — node outputs get
    # merged into an empty dict and the initial state (messages, bus, etc.)
    # never reaches the first node. Using ChatState registers every key as a
    # channel with last-write-wins semantics.
    from langgraph.graph import StateGraph, END

    g: StateGraph = StateGraph(ChatState)
    g.add_node("rag_retrieve", _node_rag_retrieve)
    g.add_node("k2_respond", _node_k2_respond)
    g.add_node("tool_dispatch", _node_tool_dispatch)
    g.set_entry_point("rag_retrieve")
    g.add_edge("rag_retrieve", "k2_respond")
    g.add_conditional_edges(
        "k2_respond",
        _route_after_respond,
        {"tool_dispatch": "tool_dispatch", "end": END},
    )
    g.add_edge("tool_dispatch", "k2_respond")
    return g.compile()


@dataclass
class CaseChatAgent:
    case: PatientCase
    bus: EventBus = field(default_factory=EventBus)
    audience: Audience = "oncologist"
    messages: list[ChatMessage] = field(default_factory=list)
    _graph: Any = None
    _case_summary: str = ""
    _case_dict: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._refresh_case_summary()
        self._case_dict = self.case.model_dump()

    def _refresh_case_summary(self) -> None:
        if self.audience == "patient":
            self._case_summary = _slim_case_patient(self.case)
        else:
            self._case_summary = _slim_case(self.case)

    @property
    def system_prompt(self) -> str:
        return (
            PATIENT_SYSTEM_PROMPT
            if self.audience == "patient"
            else ONCOLOGIST_SYSTEM_PROMPT
        )

    @property
    def available(self) -> bool:
        return has_kimi_key()

    async def send(self, user_msg: str) -> ChatMessage:
        from .k2_client import logger as _chat_logger
        if not self.available:
            await self.bus.emit(
                EventKind.CHAT_ANSWER_DELTA,
                "answer",
                {"delta": "Chat disabled - KIMI_API_KEY not configured."},
            )
            await self.bus.emit(EventKind.CHAT_DONE, "done", {})
            return ChatMessage(role="assistant", content="Chat disabled.")

        if self._graph is None:
            self._graph = _build_graph()

        self.messages.append(ChatMessage(role="user", content=user_msg))
        state: ChatState = {
            "messages": self.messages,
            "case_summary": self._case_summary,
            "system_prompt": self.system_prompt,
            "pending_tool_calls": [],
            "rag_hits": [],
            "last_assistant_text": "",
            "last_assistant_thinking": "",
            "iteration": 0,
        }
        state["bus"] = self.bus           # type: ignore[typeddict-unknown-key]
        state["case_dict"] = self._case_dict  # type: ignore[typeddict-unknown-key]

        set_current_bus(self.bus)
        try:
            await self._graph.ainvoke(state)
        except Exception as _exc:
            # Surface the full traceback — silent LangGraph failures otherwise
            # look like "empty chat response" on the frontend.
            _chat_logger.exception("chat graph crashed: %s", _exc)
            raise
        finally:
            last = self.messages[-1] if self.messages else None
            citations = (
                list(last.citations)
                if last is not None and last.role == "assistant"
                else []
            )
            await self.bus.emit(
                EventKind.CHAT_DONE, "done", {"citations": citations},
            )

        return self.messages[-1]

    async def stream_events(self) -> AsyncIterator[AgentEvent]:
        async for ev in self.bus.stream():
            yield ev
