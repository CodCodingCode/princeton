from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


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


class DrugInteraction(BaseModel):
    gene: str
    drug_name: str
    interaction_types: list[str] = []
    sources: list[str] = []


class ClinicalTrial(BaseModel):
    nct_id: str
    title: str
    status: str
    phase: str | None = None
    url: str


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
    drugs: list[DrugInteraction] = []
    trials: list[ClinicalTrial] = []
    vaccine: VaccineConstruct | None = None


class PathologyReport(BaseModel):
    patient_name: str
    species: Literal["canine", "feline", "human"] = "canine"
    breed: str | None = None
    age_years: float | None = None
    weight_kg: float | None = None
    sex: Literal["M", "F", "MN", "FS"] | None = None
    cancer_type: str
    grade: str | None = None
    stage: str | None = None
    location: str = Field(description="Anatomical site of tumor")
    owner_location: str | None = Field(default=None, description="City/region for lab search")
    prior_treatments: list[str] = []
    clinical_notes: str = ""
    dla_alleles: list[str] = Field(default_factory=list, description="Known DLA alleles if HLA-typed")


class LabMatch(BaseModel):
    name: str
    category: Literal["sequencing", "synthesis", "vet_oncology", "dla_typing"]
    address: str = ""
    distance_km: float | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    notes: str = ""
    estimated_cost_usd: float | None = None
    turnaround_days: int | None = None


class EmailDraft(BaseModel):
    recipient_type: Literal["sequencing_lab", "synthesis_vendor", "vet_oncologist", "ethics_board", "owner"]
    recipient_name: str
    recipient_email: str | None = None
    subject: str
    body: str
    attachments: list[str] = Field(default_factory=list, description="Paths to attachment files")
    sent: bool = False
    sent_message_id: str | None = None


class TimelineEvent(BaseModel):
    week: int
    date_iso: str
    title: str
    description: str
    location: str | None = None


class StructurePose(BaseModel):
    peptide_sequence: str
    mutation_label: str
    dla_allele: str
    pdb_path: str | None = None
    pdb_text: str | None = None
    method: Literal["pandora", "esmfold", "alphafold"] = "pandora"
    binding_energy_kcal_mol: float | None = None
    tcr_facing_residues: list[int] = Field(default_factory=list, description="1-based residue indices")


class CaseFile(BaseModel):
    """Complete treatment package — everything the agent produces."""

    pathology: PathologyReport
    pipeline: PipelineResult
    structures: list[StructurePose] = []
    sequencing_labs: list[LabMatch] = []
    synthesis_vendors: list[LabMatch] = []
    vet_oncologists: list[LabMatch] = []
    dla_typing_labs: list[LabMatch] = []
    emails: list[EmailDraft] = []
    timeline: list[TimelineEvent] = []
    plain_english: str = ""
    drive_folder_url: str | None = None
