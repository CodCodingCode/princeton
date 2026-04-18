"""NCCN cutaneous melanoma decision tree (simplified, v2.2024).

This is a lossy encoding suitable for a hackathon demo, not a clinical reference.
Real NCCN guidelines have hundreds of conditional branches; we keep the spine
that drives the most consequential treatment decisions and let the medical
reasoning model fill in the nuance per node.

Each node represents one decision point. The walker (walker.py) traverses the
graph by asking the model — given the patient's pathology + mutation profile —
which option fits best at each step. The node's `evidence_required` list tells
the walker which fields from `PatientState` to surface in the prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NCCNOption:
    label: str
    next_id: str | None
    description: str = ""


@dataclass(frozen=True)
class NCCNNode:
    id: str
    title: str
    question: str
    options: tuple[NCCNOption, ...]
    evidence_required: tuple[str, ...] = field(default_factory=tuple)
    is_terminal: bool = False


ROOT = "START"


def _node(
    id: str,
    title: str,
    question: str,
    options: list[tuple[str, str | None, str]],
    evidence: list[str] | None = None,
    terminal: bool = False,
) -> NCCNNode:
    return NCCNNode(
        id=id,
        title=title,
        question=question,
        options=tuple(NCCNOption(label=l, next_id=n, description=d) for l, n, d in options),
        evidence_required=tuple(evidence or ()),
        is_terminal=terminal,
    )


GRAPH: dict[str, NCCNNode] = {n.id: n for n in [
    _node(
        "START",
        "Initial pathology review",
        "Has melanoma been confirmed on the H&E slide and what is the primary descriptor?",
        [
            ("Confirmed primary cutaneous melanoma", "STAGE_T", "Proceed to T-stage assignment"),
            ("Insufficient material — re-biopsy", "REBIOPSY", "Diagnostic tissue inadequate"),
        ],
        evidence=["melanoma_subtype", "confidence"],
    ),
    _node(
        "REBIOPSY",
        "Re-biopsy required",
        "Recommend wider biopsy and pause downstream workup.",
        [],
        evidence=["notes"],
        terminal=True,
    ),
    _node(
        "STAGE_T",
        "T category (Breslow + ulceration)",
        "Using Breslow thickness and ulceration status, what is the primary T category?",
        [
            ("T1 (≤1.0 mm)", "SLNB_DECISION", "Thin melanoma"),
            ("T2 (>1.0–2.0 mm)", "SLNB_DECISION", "Intermediate"),
            ("T3 (>2.0–4.0 mm)", "SLNB_DECISION", "Thick"),
            ("T4 (>4.0 mm)", "SLNB_DECISION", "Very thick"),
        ],
        evidence=["breslow_thickness_mm", "ulceration", "t_stage"],
    ),
    _node(
        "SLNB_DECISION",
        "Sentinel lymph node biopsy",
        "Is sentinel lymph node biopsy indicated? (Generally yes for T1b+, discuss for T1a with high-risk features.)",
        [
            ("SLNB indicated and positive → Stage III", "STAGE_III", "Nodal involvement found"),
            ("SLNB indicated and negative → Stage I/II", "STAGE_I_II", "No nodal disease"),
            ("SLNB not indicated (T1a, low risk) → Stage I", "STAGE_I_II", "Skip nodal staging"),
            ("Distant metastases present → Stage IV", "STAGE_IV", "M1 disease on imaging"),
        ],
        evidence=["t_stage", "ulceration", "mitotic_rate_per_mm2", "notes"],
    ),
    _node(
        "STAGE_I_II",
        "Stage I/II — local disease",
        "What is the post-resection plan for localized disease?",
        [
            ("Wide local excision + observation", "FOLLOWUP", "Stage IA / low risk"),
            ("Wide local excision + adjuvant immunotherapy", "BRAF_TEST", "Stage IIB/IIC — high risk"),
        ],
        evidence=["t_stage", "ulceration"],
    ),
    _node(
        "STAGE_III",
        "Stage III — regional disease",
        "What is the adjuvant therapy plan?",
        [
            ("Adjuvant anti-PD-1 (nivolumab or pembrolizumab)", "BRAF_TEST", "Standard of care for IIIA-IIID"),
            ("Adjuvant BRAF/MEK inhibitor (if BRAF V600+)", "BRAF_TEST", "Alternative for BRAF mutant"),
            ("Clinical trial enrollment", "BRAF_TEST", "Patient eligible for trial"),
        ],
        evidence=["t_stage", "tils_present", "pdl1_estimate"],
    ),
    _node(
        "STAGE_IV",
        "Stage IV — metastatic disease",
        "Are CNS metastases present?",
        [
            ("Yes — CNS-directed therapy first", "BRAIN_METS", "Brain mets change drug selection"),
            ("No — proceed to systemic therapy", "BRAF_TEST", "Standard systemic workflow"),
        ],
        evidence=["notes"],
    ),
    _node(
        "BRAIN_METS",
        "CNS-directed therapy",
        "Combine local CNS therapy (SRS/surgery) with systemic options that have CNS activity (ipilimumab+nivolumab; dabrafenib+trametinib if BRAF+).",
        [
            ("Proceed to systemic therapy selection", "BRAF_TEST", ""),
        ],
        evidence=["notes"],
    ),
    _node(
        "BRAF_TEST",
        "BRAF mutation testing",
        "Does the tumor harbor a targetable BRAF V600 mutation (V600E or V600K)?",
        [
            ("BRAF V600 mutant — both targeted and IO are options", "BRAF_MUT_TX", ""),
            ("BRAF wild-type — IO is preferred", "BRAF_WT_TX", ""),
        ],
        evidence=["mutations", "braf_status"],
    ),
    _node(
        "BRAF_MUT_TX",
        "BRAF-mutant systemic therapy",
        "For BRAF V600+ disease, choose the first-line systemic regimen.",
        [
            ("Anti-PD-1 monotherapy (preferred for high TMB / PD-L1+)", "VACCINE_CANDIDATE", "Hold targeted in reserve"),
            ("Ipilimumab + nivolumab combo IO", "VACCINE_CANDIDATE", "Aggressive disease, no contraindication"),
            ("BRAF + MEK inhibitor (dabrafenib + trametinib)", "VACCINE_CANDIDATE", "Rapid response needed; symptomatic"),
            ("Nivolumab + relatlimab (anti-LAG-3) combo", "VACCINE_CANDIDATE", "LAG-3 IHC positive — Regeneron fianlimab thesis"),
        ],
        evidence=["mutations", "tils_present", "pdl1_estimate", "tumor_mutational_burden", "lag3_ihc_percent"],
    ),
    _node(
        "BRAF_WT_TX",
        "BRAF wild-type systemic therapy",
        "For BRAF wild-type disease, choose the first-line immunotherapy regimen.",
        [
            ("Anti-PD-1 monotherapy (nivolumab or pembrolizumab)", "VACCINE_CANDIDATE", "Standard first line"),
            ("Ipilimumab + nivolumab combo IO", "VACCINE_CANDIDATE", "Higher response, more toxicity"),
            ("Nivolumab + relatlimab (anti-LAG3) combo", "VACCINE_CANDIDATE", "Approved alternative combo (RELATIVITY-047)"),
        ],
        evidence=["mutations", "tils_present", "pdl1_estimate", "tumor_mutational_burden", "lag3_ihc_percent"],
    ),
    _node(
        "VACCINE_CANDIDATE",
        "Personalized neoantigen vaccine candidacy",
        "Is the patient a candidate for an investigational personalized neoantigen mRNA vaccine adjunct?",
        [
            ("Yes — design vaccine and add to systemic therapy", "FINAL", "Triggers Panel 3 vaccine pipeline"),
            ("No — sufficient response expected from chosen systemic therapy alone", "FOLLOWUP", "Skip vaccine workup"),
        ],
        evidence=["mutations", "tumor_mutational_burden", "t_stage"],
    ),
    _node(
        "FOLLOWUP",
        "Surveillance and follow-up",
        "Schedule clinical follow-up per AJCC stage. Imaging interval depends on stage and risk.",
        [],
        terminal=True,
    ),
    _node(
        "FINAL",
        "Final treatment plan",
        "Combine the chosen systemic therapy with the personalized vaccine and route to clinical pathway.",
        [],
        terminal=True,
    ),
]}


def graph_to_payload() -> dict:
    """Serialize the graph for the frontend (used to render the static layout)."""
    return {
        "nodes": [
            {
                "id": n.id,
                "title": n.title,
                "question": n.question,
                "is_terminal": n.is_terminal,
            }
            for n in GRAPH.values()
        ],
        "edges": [
            {"src": n.id, "dst": opt.next_id, "label": opt.label}
            for n in GRAPH.values()
            for opt in n.options
            if opt.next_id is not None
        ],
        "root": ROOT,
    }
