from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────
# Core mutation / peptide / vaccine types (pipeline reuses)
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


class Peptide(BaseModel):
    sequence: str
    length: int
    mutation: Mutation
    mutation_index: int = Field(description="0-based index of the mutated residue within the peptide")
    score_nm: float | None = None

    @property
    def contains_mutation(self) -> bool:
        return 0 <= self.mutation_index < self.length


class Candidate(BaseModel):
    peptide: Peptide
    rank: int
    binding_rank_percentile: float | None = None


class VaccineConstruct(BaseModel):
    epitopes: list[str]
    linker: str
    nucleotide_sequence: str
    amino_acid_sequence: str

    @property
    def length_bp(self) -> int:
        return len(self.nucleotide_sequence)

    @property
    def estimated_cost_usd(self) -> float:
        return round(self.length_bp * 0.07, 2)


class PipelineResult(BaseModel):
    mutations: list[Mutation]
    candidates: list[Candidate]
    vaccine: VaccineConstruct | None = None
    scorer_name: str = ""
    scorer_is_heuristic: bool = False


# ─────────────────────────────────────────────────────────────
# VLM pathology output
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
    """Output from the VLM after looking at an H&E pathology slide image."""

    melanoma_subtype: MelanomaSubtype = "unknown"
    breslow_thickness_mm: float | None = Field(
        default=None, description="Breslow depth in millimetres, if estimable from the slide"
    )
    ulceration: bool | None = None
    mitotic_rate_per_mm2: float | None = None
    tils_present: Literal["absent", "non_brisk", "brisk", "unknown"] = "unknown"
    pdl1_estimate: Literal["negative", "low", "high", "unknown"] = "unknown"
    # LAG-3 IHC is not extractable from H&E slides — populated from the
    # ClinicianIntake form, copied onto PathologyFindings by the orchestrator
    # so existing evidence-resolution pathways (NCCN walker hasattr lookup,
    # molecular panel chips) read one canonical location.
    lag3_ihc_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    notes: str = ""

    @property
    def t_stage(self) -> str:
        """AJCC 8th edition T category derived from Breslow + ulceration."""
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
    """One step of the NCCN walker — node visited, decision made, reasoning shown."""

    node_id: str
    node_title: str
    chosen_option: str
    next_node_id: str | None
    reasoning: str = ""
    evidence: dict[str, str] = Field(default_factory=dict)
    citations: list[CitationRef] = Field(default_factory=list)


class TwinMatchRef(BaseModel):
    submitter_id: str
    similarity: float
    matching_features: list[str] = Field(default_factory=list)
    stage: str | None = None
    age_at_diagnosis: int | None = None
    vital_status: str | None = None
    survival_days: int | None = None
    mutated_drivers: list[str] = Field(default_factory=list)


class SurvivalPoint(BaseModel):
    days: int
    survival: float
    at_risk: int
    events_so_far: int


class CohortSnapshot(BaseModel):
    cohort_size: int = 0
    twins: list[TwinMatchRef] = Field(default_factory=list)
    overall_curve: list[SurvivalPoint] = Field(default_factory=list)
    twin_curve: list[SurvivalPoint] = Field(default_factory=list)
    median_survival_days: int | None = None
    twin_median_survival_days: int | None = None


# ─────────────────────────────────────────────────────────────
# Panel 2 — molecular landscape
# ─────────────────────────────────────────────────────────────


class MoleculeView(BaseModel):
    """A single mutated protein with optional drug co-crystal complex."""

    gene: str
    mutation_label: str
    mutation_position: int
    wt_pdb_text: str | None = None
    mut_pdb_text: str | None = None
    fold_method: Literal["esmfold", "alphafold", "template"] = "esmfold"
    drug_complex_pdb_id: str | None = None
    drug_name: str | None = None
    drug_complex_pdb_text: str | None = None


class BiomarkerChip(BaseModel):
    """One non-mutational biomarker rendered above the protein viewers.

    Merges VLM findings (e.g. PD-L1 from slide) and TCGA/VCF enrichment
    (e.g. TMB, UV-signature %) into one normalized payload. ``source`` is
    surfaced to the clinician so the provenance of each datum is visible.
    """

    label: str  # short name shown on the chip, e.g. "TMB"
    value: str  # formatted value, e.g. "12.4 mut/Mb"
    source: Literal["vlm", "vcf", "tcga", "cbioportal", "intake", "curated_demo", "computed"] = "computed"
    tooltip: str | None = None


# ─────────────────────────────────────────────────────────────
# Panel 3 — peptide-HLA pose (reused from pipeline)
# ─────────────────────────────────────────────────────────────


class StructurePose(BaseModel):
    peptide_sequence: str
    mutation_label: str
    hla_allele: str
    pdb_path: str | None = None
    pdb_text: str | None = None
    method: Literal["pandora", "esmfold", "alphafold", "template"] = "esmfold"
    binding_energy_kcal_mol: float | None = None
    tcr_facing_residues: list[int] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Clinical trial matching
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# Enriched biomarkers + clinician intake (Regeneron track)
# ─────────────────────────────────────────────────────────────


class EnrichedBiomarkers(BaseModel):
    """Computed / fetched biomarkers that supplement the VLM pathology read.

    Populated by ``neoantigen.enrichment`` before the NCCN walker runs.
    Provenance is tracked in ``source_notes`` so the UI can display who said
    what. All fields are independently optional — the run never fails when a
    source is unavailable, it just degrades silently (TMB always works from
    the VCF; UV signature needs real genomic coords; cBioPortal only covers
    TCGA ids and requires network).
    """

    # Computed from the mutation list / VCF
    tmb_mut_per_mb: float | None = None
    uv_signature_fraction: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraction of SNVs matching SBS7 UV signature (C→T at dipyrimidine)",
    )
    total_snvs_scored: int | None = None

    # Fetched from cBioPortal when submitter_id is known
    prior_systemic_therapies: list[str] = Field(default_factory=list)
    prior_anti_pd1: bool | None = None

    # Canonical provenance / notes — one short string per populated field,
    # e.g. {"tmb": "computed from VCF", "prior_therapy": "cBioPortal skcm_tcga"}
    source_notes: dict[str, str] = Field(default_factory=dict)


class ClinicianIntake(BaseModel):
    """Fields that no public data source can fill — must come from the clinician.

    Values here override any inference from :class:`EnrichedBiomarkers` during
    :func:`neoantigen.external.regeneron_rules.evaluate`. Any ``None`` field
    falls back to the enriched record, then to ``unknown_criteria``.
    """

    ecog: int | None = Field(default=None, ge=0, le=4)
    lag3_ihc_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    measurable_disease_recist: bool | None = None
    life_expectancy_months: int | None = Field(default=None, ge=0, le=240)
    prior_systemic_therapy: bool | None = None  # override for enrichment
    prior_anti_pd1: bool | None = None  # override for enrichment


# ─────────────────────────────────────────────────────────────
# Clinical trial matching
# ─────────────────────────────────────────────────────────────


TrialMatchStatus = Literal["eligible", "ineligible", "needs_more_data", "unscored"]


class TrialMatch(BaseModel):
    """One clinical trial paired with a structured eligibility verdict.

    `unscored` = the trial is shown as context but we don't have hand-coded
    predicates for it (applies to every non-Regeneron trial today).
    """

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


# ─────────────────────────────────────────────────────────────
# Aggregate case file
# ─────────────────────────────────────────────────────────────


class MelanomaCase(BaseModel):
    """Everything the agent produces for one patient."""

    pathology: PathologyFindings
    mutations: list[Mutation] = Field(default_factory=list)
    nccn_path: list[NCCNStep] = Field(default_factory=list)
    final_recommendation: str = ""
    molecules: list[MoleculeView] = Field(default_factory=list)
    pipeline: PipelineResult | None = None
    poses: list[StructurePose] = Field(default_factory=list)
    cohort: CohortSnapshot | None = None
    trials: list[TrialMatch] = Field(default_factory=list)
    # Regeneron-track additions — both are optional and do not affect the
    # pure-pipeline CLI, only the full agent + Streamlit UI.
    enrichment: EnrichedBiomarkers | None = None
    intake: ClinicianIntake | None = None
    biomarker_chips: list[BiomarkerChip] = Field(default_factory=list)
