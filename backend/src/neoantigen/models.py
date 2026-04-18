from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────
# Mutations
# ─────────────────────────────────────────────────────────────


class Mutation(BaseModel):
    gene: str
    ref_aa: str
    position: int
    alt_aa: str

    @property
    def label(self) -> str:
        return f"{self.ref_aa}{self.position}{self.alt_aa}"

    @property
    def full_label(self) -> str:
        return f"{self.gene} {self.label}"


# ─────────────────────────────────────────────────────────────
# Pathology (now populated from PDF extractor, not VLM)
# ─────────────────────────────────────────────────────────────


MelanomaSubtype = Literal[
    "superficial_spreading",
    "nodular",
    "lentigo_maligna",
    "acral_lentiginous",
    "desmoplastic",
    "other",
    "unknown",
]


class PathologyFindings(BaseModel):
    """Structured oncology pathology findings (extracted from PDFs).

    Cancer-agnostic primary fields drive the dynamic railway; melanoma-specific
    fields remain here for back-compat and as additional evidence when the case
    is melanoma. For non-melanoma cases they simply stay at their defaults.
    """

    # Cancer-agnostic primaries (used by the dynamic walker to seed RAG queries)
    primary_cancer_type: str = "unknown"   # e.g. "cutaneous_melanoma",
                                            # "lung_adenocarcinoma",
                                            # "breast_ductal_carcinoma",
                                            # "colorectal_adenocarcinoma",
                                            # "other", "unknown"
    histology: str = ""                     # free-text histology, e.g. "adenocarcinoma"
    primary_site: str = ""                  # free-text site, e.g. "right upper lobe lung"

    # Melanoma-specific evidence (populated when the case is melanoma)
    melanoma_subtype: MelanomaSubtype = "unknown"
    breslow_thickness_mm: float | None = None
    ulceration: bool | None = None
    mitotic_rate_per_mm2: float | None = None
    tils_present: Literal["absent", "non_brisk", "brisk", "unknown"] = "unknown"
    pdl1_estimate: Literal["negative", "low", "high", "unknown"] = "unknown"
    lag3_ihc_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    notes: str = ""

    @property
    def t_stage(self) -> str:
        b = self.breslow_thickness_mm
        if b is None:
            return "Tx"
        u = bool(self.ulceration)
        if b < 0.8 and not u:
            return "T1a"
        if b < 0.8 and u:
            return "T1b"
        if b < 1.0:
            return "T1b"
        if b < 2.0:
            return "T2b" if u else "T2a"
        if b < 4.0:
            return "T3b" if u else "T3a"
        return "T4b" if u else "T4a"


# ─────────────────────────────────────────────────────────────
# NCCN walker output
# ─────────────────────────────────────────────────────────────


class CitationRef(BaseModel):
    pmid: str
    title: str
    year: str = ""
    journal: str = ""
    snippet: str = ""
    relevance: float = 0.0

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"


class NCCNStep(BaseModel):
    """Legacy per-node summary (kept for simple chat tool-call reuse)."""

    node_id: str
    node_title: str
    chosen_option: str
    next_node_id: str | None
    reasoning: str = ""
    evidence: dict[str, str] = Field(default_factory=dict)
    citations: list[CitationRef] = Field(default_factory=list)


class RailwayAlternative(BaseModel):
    """A sibling option at a decision node that was considered but not chosen."""

    option_label: str
    option_description: str = ""
    reason_not_chosen: str = ""
    next_id: str | None = None


class RailwayStep(BaseModel):
    """One node on the railway — the chosen path plus siblings."""

    node_id: str
    title: str
    question: str
    chosen_option_label: str
    chosen_option_description: str = ""
    chosen_next_id: str | None = None
    chosen_rationale: str = ""
    reasoning: str = ""
    evidence: dict[str, str] = Field(default_factory=dict)
    citations: list[CitationRef] = Field(default_factory=list)
    alternatives: list[RailwayAlternative] = Field(default_factory=list)
    is_terminal: bool = False
    phase_id: str = ""                         # dynamic-railway phase grouping
    phase_title: str = ""                      # human label for the phase


class RailwayMap(BaseModel):
    steps: list[RailwayStep] = Field(default_factory=list)
    mermaid: str = ""
    final_recommendation: str = ""


# ─────────────────────────────────────────────────────────────
# Clinician intake + enrichment (fed from PDF extractor)
# ─────────────────────────────────────────────────────────────


class EnrichedBiomarkers(BaseModel):
    tmb_mut_per_mb: float | None = None
    uv_signature_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    total_snvs_scored: int | None = None
    prior_systemic_therapies: list[str] = Field(default_factory=list)
    prior_anti_pd1: bool | None = None
    source_notes: dict[str, str] = Field(default_factory=dict)


class ClinicianIntake(BaseModel):
    ecog: int | None = Field(default=None, ge=0, le=4)
    lag3_ihc_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    measurable_disease_recist: bool | None = None
    life_expectancy_months: int | None = Field(default=None, ge=0, le=240)
    prior_systemic_therapy: bool | None = None
    prior_anti_pd1: bool | None = None
    ajcc_stage: str | None = None
    age_years: int | None = Field(default=None, ge=0, le=120)


# ─────────────────────────────────────────────────────────────
# Clinical trials
# ─────────────────────────────────────────────────────────────


TrialMatchStatus = Literal["eligible", "ineligible", "needs_more_data", "unscored"]


class TrialMatch(BaseModel):
    nct_id: str
    title: str
    sponsor: str
    phase: str | None = None
    status: TrialMatchStatus = "unscored"
    passing_criteria: list[str] = Field(default_factory=list)
    failing_criteria: list[str] = Field(default_factory=list)
    unknown_criteria: list[str] = Field(default_factory=list)
    is_regeneron: bool = False
    site_contacts: list[dict[str, str]] = Field(default_factory=list)
    overall_status: str | None = None
    url: str | None = None


class TrialSite(BaseModel):
    """A recruiting / active location for a matched trial, geocoded."""

    nct_id: str
    facility: str
    city: str = ""
    state: str = ""
    country: str = ""
    lat: float | None = None
    lng: float | None = None
    status: str = ""
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None


# ─────────────────────────────────────────────────────────────
# Aggregate patient case
# ─────────────────────────────────────────────────────────────


class PageFinding(BaseModel):
    """Per-page VLM output — structured findings pulled from one PDF page image."""

    page_number: int
    description: str = ""
    primary_cancer_type: str | None = None
    histology: str | None = None
    primary_site: str | None = None
    melanoma_subtype: str | None = None
    breslow_thickness_mm: float | None = None
    ulceration: bool | None = None
    mitotic_rate_per_mm2: float | None = None
    tils_present: str | None = None
    pdl1_estimate: str | None = None
    lag3_ihc_percent: float | None = None
    ajcc_stage: str | None = None
    age_years: int | None = None
    ecog: int | None = None
    measurable_disease_recist: bool | None = None
    life_expectancy_months: int | None = None
    prior_systemic_therapy: bool | None = None
    prior_anti_pd1: bool | None = None
    mutations_text: list[str] = Field(default_factory=list)
    notes: str = ""


class DocumentExtraction(BaseModel):
    """One PDF's worth of extracted content — text + per-page VLM findings."""

    filename: str
    document_kind: str = "unknown"
    page_count: int = 0
    text_excerpt: str = ""
    pages: list[PageFinding] = Field(default_factory=list)
    used_vision_fallback: bool = False


class ProvenanceEntry(BaseModel):
    """Which source document + page a datum came from, for reviewable audit trails."""

    field: str
    value: str
    filename: str
    page_number: int | None = None


class PatientCase(BaseModel):
    """Everything the patient orchestrator produces for one patient's document folder."""

    case_id: str
    pathology: PathologyFindings
    primary_cancer_type: str = "unknown"        # detected from pathology + mutations
    intake: ClinicianIntake = Field(default_factory=ClinicianIntake)
    enrichment: EnrichedBiomarkers | None = None
    mutations: list[Mutation] = Field(default_factory=list)
    documents: list[DocumentExtraction] = Field(default_factory=list)
    provenance: list[ProvenanceEntry] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    pdf_text_excerpt: str = ""  # legacy — first doc's text, kept for report compatibility
    railway: RailwayMap | None = None
    trial_matches: list[TrialMatch] = Field(default_factory=list)
    trial_sites: list[TrialSite] = Field(default_factory=list)
    final_recommendation: str = ""
