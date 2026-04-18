"""Load the pre-built TCGA-SKCM cohort produced by ``scripts/fetch_tcga_skcm.py``."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..models import Mutation

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "tcga_skcm"
HGVS_SHORT_RE = re.compile(r"p\.([A-Z*])(\d+)([A-Z*])")


@dataclass
class TCGAPatient:
    submitter_id: str
    sex: str | None
    age_at_diagnosis: int | None
    stage: str | None
    vital_status: str | None
    days_to_death: int | None
    days_to_last_follow_up: int | None
    primary_diagnosis: str | None = None
    biopsy_site: str | None = None
    mutated_genes: set[str] = field(default_factory=set)
    braf_v600e: bool = False
    nras_q61: bool = False
    kit_mutant: bool = False
    nf1_mutant: bool = False
    mutation_count: int = 0

    @property
    def survival_days(self) -> int | None:
        return self.days_to_death if self.vital_status == "Dead" else self.days_to_last_follow_up

    @property
    def event(self) -> int | None:
        if self.vital_status == "Dead":
            return 1
        if self.vital_status == "Alive":
            return 0
        return None

    @property
    def stage_bucket(self) -> str:
        s = (self.stage or "").upper()
        if "IV" in s:
            return "IV"
        if "III" in s:
            return "III"
        if "II" in s:
            return "II"
        if "I" in s:
            return "I"
        return "Unknown"


def has_cohort() -> bool:
    return (DATA_DIR / "clinical.csv").exists() and (DATA_DIR / "mutations.parquet").exists()


def demo_patient_id() -> str | None:
    f = DATA_DIR / "demo_patient.txt"
    return f.read_text().strip() if f.exists() else None


@lru_cache(maxsize=1)
def load_cohort() -> list[TCGAPatient]:
    """Read clinical.csv + mutations.parquet and return one TCGAPatient per case."""
    if not has_cohort():
        return []

    patients: dict[str, TCGAPatient] = {}
    with (DATA_DIR / "clinical.csv").open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row["submitter_id"]
            if not sid:
                continue
            patients[sid] = TCGAPatient(
                submitter_id=sid,
                sex=row.get("sex") or None,
                age_at_diagnosis=_to_int(row.get("age_at_diagnosis")),
                stage=row.get("stage") or None,
                vital_status=row.get("vital_status") or None,
                days_to_death=_to_int(row.get("days_to_death")),
                days_to_last_follow_up=_to_int(row.get("days_to_last_follow_up")),
                primary_diagnosis=row.get("primary_diagnosis") or None,
                biopsy_site=row.get("biopsy_site") or None,
            )

    # Mutations parquet is optional (loads only if pandas+pyarrow available)
    try:
        import pandas as pd
        df = pd.read_parquet(DATA_DIR / "mutations.parquet")
    except Exception:
        return list(patients.values())

    for sid, group in df.groupby("submitter_id"):
        p = patients.get(sid)
        if p is None:
            continue
        genes = set(group["gene"].dropna().astype(str))
        p.mutated_genes = genes
        p.mutation_count = int(len(group))
        # Cheap label fields used by the twin-matcher feature vector.
        for hgvs in group["hgvs_p"].dropna().astype(str):
            if "V600E" in hgvs and ("BRAF" in genes):
                p.braf_v600e = True
            if hgvs.startswith("p.Q61") and ("NRAS" in genes):
                p.nras_q61 = True
        p.kit_mutant = "KIT" in genes
        p.nf1_mutant = "NF1" in genes

    return list(patients.values())


def _to_int(v: str | None) -> int | None:
    if v is None or v == "" or v.lower() in {"none", "null", "nan"}:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def mutations_for_patient(submitter_id: str) -> list[Mutation]:
    """Return missense mutations for a TCGA submitter id as ``Mutation`` objects.

    Designed for the demo path: the orchestrator can drive the existing
    neoantigen pipeline directly off a TCGA case without any MAF→VCF round trip.
    """
    if not has_cohort():
        return []
    try:
        import pandas as pd
    except ImportError:
        return []

    df = pd.read_parquet(DATA_DIR / "mutations.parquet")
    rows = df[df.submitter_id == submitter_id]
    out: list[Mutation] = []
    seen: set[tuple[str, int, str, str]] = set()
    for _, r in rows.iterrows():
        gene = str(r.get("gene") or "").strip()
        hgvs = str(r.get("hgvs_p") or "").strip()
        m = HGVS_SHORT_RE.search(hgvs)
        if not gene or not m:
            continue
        ref, pos, alt = m.group(1), int(m.group(2)), m.group(3)
        if ref == "*" or alt == "*":  # nonsense / stop-gain — pipeline expects missense
            continue
        key = (gene, pos, ref, alt)
        if key in seen:
            continue
        seen.add(key)
        out.append(Mutation(gene=gene, ref_aa=ref, position=pos, alt_aa=alt))
    return out
