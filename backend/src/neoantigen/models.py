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


class NCCNStep(BaseModel):
    """One step of the NCCN walker — node visited, decision made, reasoning shown."""

    node_id: str
    node_title: str
    chosen_option: str
    next_node_id: str | None
    reasoning: str = ""
    evidence: dict[str, str] = Field(default_factory=dict)


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
