"""Scrape every active Regeneron oncology trial from ClinicalTrials.gov v2 and
emit one structured ``TrialRule`` ``.py`` file per trial.

Flow:
  1. Fetch all studies with ``leadSponsorName=Regeneron Pharmaceuticals`` +
     ``overallStatus ∈ {RECRUITING, NOT_YET_RECRUITING}`` + ``studyType=INTERVENTIONAL``.
  2. Filter to oncology (condition text contains cancer/carcinoma/melanoma/
     lymphoma/leukemia/myeloma/sarcoma/glioma/tumor/neoplasm).
  3. Map CT.gov conditions → our ``cancer_type`` taxonomy (union over all
     listed conditions; basket trials get multiple cancer_types).
  4. For each trial, call K2 (via ``call_for_json``) with the raw eligibility
     text and ask for a structured predicate payload.
  5. Render one ``backend/src/neoantigen/external/regeneron/nct<id>.py`` per
     trial. Every run wipes + regenerates the directory so it stays in sync
     with CT.gov.

Run once per refresh. Requires ``K2_API_KEY`` and internet.

    python backend/scripts/scrape_regeneron_trials.py
    python backend/scripts/scrape_regeneron_trials.py --dry-run
    python backend/scripts/scrape_regeneron_trials.py --limit 5   # debug
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

# Load .env early so KIMI / K2 keys are present when we boot the LLM client.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# Inject the backend src onto the path so we can import the neoantigen package
# without installing it (script is intended to be run from the repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from neoantigen.agent._llm import call_for_json, has_api_key  # noqa: E402


CTGOV_URL = "https://clinicaltrials.gov/api/v2/studies"
OUT_DIR = _REPO_ROOT / "src" / "neoantigen" / "external" / "regeneron"


# Condition substring → cancer_type taxonomy key. Lowercase match after
# stripping punctuation. Add new mappings here when the scraper logs
# "unmapped condition" for something relevant.
CONDITION_TO_CANCER_TYPE: dict[str, str] = {
    # Melanoma
    "cutaneous melanoma": "cutaneous_melanoma",
    "unresectable melanoma": "cutaneous_melanoma",
    "metastatic melanoma": "cutaneous_melanoma",
    "advanced melanoma": "cutaneous_melanoma",
    "melanoma": "cutaneous_melanoma",
    # Lung
    "non-small cell lung cancer": "lung_adenocarcinoma",
    "non small cell lung cancer": "lung_adenocarcinoma",
    "nsclc": "lung_adenocarcinoma",
    "lung adenocarcinoma": "lung_adenocarcinoma",
    "lung squamous cell": "lung_squamous",
    "squamous cell lung": "lung_squamous",
    # Breast
    "her2-positive breast": "breast_carcinoma",
    "her2 positive breast": "breast_carcinoma",
    "her2-low breast": "breast_carcinoma",
    "triple negative breast": "breast_carcinoma",
    "breast cancer": "breast_carcinoma",
    "breast carcinoma": "breast_carcinoma",
    # Colorectal
    "colorectal adenocarcinoma": "colorectal_adenocarcinoma",
    "colorectal cancer": "colorectal_adenocarcinoma",
    "colon cancer": "colorectal_adenocarcinoma",
    "rectal cancer": "colorectal_adenocarcinoma",
    # Other solid tumors
    "gastric cancer": "gastric_carcinoma",
    "stomach cancer": "gastric_carcinoma",
    "gastroesophageal": "gastric_carcinoma",
    "pancreatic cancer": "pancreatic_carcinoma",
    "pancreatic adenocarcinoma": "pancreatic_carcinoma",
    "prostate cancer": "prostate_carcinoma",
    "castration-resistant prostate": "prostate_carcinoma",
    "ovarian cancer": "ovarian_carcinoma",
    "ovarian carcinoma": "ovarian_carcinoma",
    "renal cell carcinoma": "renal_cell_carcinoma",
    "kidney cancer": "renal_cell_carcinoma",
    "hepatocellular": "hepatocellular_carcinoma",
    "liver cancer": "hepatocellular_carcinoma",
    "urothelial": "bladder_carcinoma",
    "bladder cancer": "bladder_carcinoma",
    "head and neck squamous": "head_neck_scc",
    "head and neck cancer": "head_neck_scc",
    "oropharyngeal": "head_neck_scc",
    "glioblastoma": "glioblastoma",
    # Hematologic
    "diffuse large b-cell": "lymphoma_dlbcl",
    "diffuse large b cell": "lymphoma_dlbcl",
    "dlbcl": "lymphoma_dlbcl",
    "multiple myeloma": "multiple_myeloma",
    # Out-of-taxonomy - explicitly bucket as "other" so we still surface the trial.
    "basal cell carcinoma": "other",
    "cutaneous squamous cell": "other",
    "follicular lymphoma": "other",
    "b-cell lymphoma": "other",
    "endometrial": "other",
    "cervical cancer": "other",
    "mesothelioma": "other",
    "sarcoma": "other",
}


_ONCOLOGY_TERMS = (
    "cancer", "carcinoma", "melanoma", "lymphoma", "leukemia", "myeloma",
    "sarcoma", "glioma", "glioblastoma", "tumor", "neoplasm", "adenocarcinoma",
    "mesothelioma",
)


# ─────────────────────────────────────────────────────────────
# Kimi structuring schema
# ─────────────────────────────────────────────────────────────


class StructuredPredicates(BaseModel):
    requires_advanced_disease: bool = False
    requires_resectable_high_risk: bool = False
    requires_braf_v600: bool | None = None
    min_age_years: int | None = None
    max_age_years: int | None = None
    eligible_stage_buckets: list[str] = Field(default_factory=list)
    requires_ecog_0_1: bool = False
    requires_no_prior_systemic_advanced: bool = False
    requires_prior_anti_pd1: bool = False
    requires_measurable_disease: bool = False
    requires_lag3_ihc_result: bool = False
    min_life_expectancy_months: int | None = None
    biomarker_gates: dict[str, str] = Field(default_factory=dict)
    pdl1_min_tps: int | None = None
    setting_one_liner: str = ""
    notes: list[str] = Field(default_factory=list)


STRUCTURE_SYSTEM_PROMPT = """You are an oncology clinical-trial eligibility
normalizer. Given the raw free-text eligibility criteria from
ClinicalTrials.gov for a Regeneron-sponsored trial, plus the trial's
structured metadata (NCT ID, phase, conditions, age bounds), fill this JSON
schema exactly:

{
  "requires_advanced_disease": bool,
  "requires_resectable_high_risk": bool,
  "requires_braf_v600": bool | null,
  "min_age_years": int | null,
  "max_age_years": int | null,
  "eligible_stage_buckets": [str],  // subset of ["I","II","III","IV"]
  "requires_ecog_0_1": bool,
  "requires_no_prior_systemic_advanced": bool,
  "requires_prior_anti_pd1": bool,
  "requires_measurable_disease": bool,
  "requires_lag3_ihc_result": bool,
  "min_life_expectancy_months": int | null,
  "biomarker_gates": {
    // include ONLY keys the text explicitly mentions, value ∈ {"required","excluded","any"}
    // supported keys: BRAF_V600, EGFR_mutation, EGFR_T790M, ALK_fusion,
    //   ROS1_fusion, MET_exon14, KRAS_G12C, HER2_positive, HER2_low,
    //   BRCA_mutation, MSI_high, PDL1_positive
  },
  "pdl1_min_tps": int | null,
  "setting_one_liner": str,          // ≤120 chars, describe line/setting
  "notes": [str]                     // criteria you couldn't structure
}

Rules:
* If the text doesn't mention something, leave it at its default (false/null/[]).
* When ambiguous, prefer the stricter interpretation.
* Stage buckets: map "Stage IIIA / IIIB / IIIC / IIID" → "III", etc.
* Output ONLY the JSON object. No prose. No markdown fences. Start with `{`.
"""


# ─────────────────────────────────────────────────────────────
# CT.gov fetch
# ─────────────────────────────────────────────────────────────


async def fetch_regeneron_studies(client: httpx.AsyncClient) -> list[dict]:
    """Pull every active Regeneron study from CT.gov v2 API."""
    out: list[dict] = []
    next_token: str | None = None
    while True:
        params: dict[str, Any] = {
            "query.lead": "Regeneron Pharmaceuticals",
            "filter.overallStatus": "RECRUITING,NOT_YET_RECRUITING",
            "filter.advanced": "AREA[StudyType]INTERVENTIONAL",
            "pageSize": 100,
            "countTotal": "true",
        }
        if next_token:
            params["pageToken"] = next_token
        r = await client.get(CTGOV_URL, params=params, timeout=60.0)
        r.raise_for_status()
        payload = r.json()
        out.extend(payload.get("studies", []))
        next_token = payload.get("nextPageToken")
        if not next_token:
            break
    return out


def is_oncology(conditions: list[str]) -> bool:
    joined = " ".join(conditions).lower()
    return any(term in joined for term in _ONCOLOGY_TERMS)


def map_conditions(conditions: list[str]) -> list[str]:
    """Return the union of matched cancer_types across every listed condition.

    Falls back to ``["other"]`` when the trial is oncology but none of the
    conditions match a taxonomy key.
    """
    seen: set[str] = set()
    for cond in conditions:
        lower = re.sub(r"[^a-z0-9\s]", " ", cond.lower()).strip()
        for needle, ct in CONDITION_TO_CANCER_TYPE.items():
            if needle in lower:
                seen.add(ct)
    return sorted(seen) if seen else ["other"]


def _parse_min_age(text: str | None) -> int | None:
    if not text:
        return None
    m = re.match(r"(\d+)\s*Years?", text)
    return int(m.group(1)) if m else None


# ─────────────────────────────────────────────────────────────
# Per-study normalisation
# ─────────────────────────────────────────────────────────────


def _coerce_study(study: dict) -> dict | None:
    """Pull out the fields we care about. Returns None if the study is missing
    required identifiers or isn't oncology."""
    protocol = study.get("protocolSection") or {}
    id_module = protocol.get("identificationModule") or {}
    status_module = protocol.get("statusModule") or {}
    conditions_module = protocol.get("conditionsModule") or {}
    design_module = protocol.get("designModule") or {}
    eligibility_module = protocol.get("eligibilityModule") or {}
    descr_module = protocol.get("descriptionModule") or {}

    nct_id = id_module.get("nctId")
    if not nct_id:
        return None

    conditions: list[str] = conditions_module.get("conditions") or []
    if not is_oncology(conditions):
        return None

    phases = design_module.get("phases") or []
    phase_str = "/".join(p.replace("PHASE", "Phase ").strip() for p in phases) or "Unknown"

    return {
        "nct_id": nct_id,
        "title_short": id_module.get("briefTitle") or id_module.get("officialTitle") or nct_id,
        "title": id_module.get("officialTitle") or id_module.get("briefTitle") or nct_id,
        "phase": phase_str,
        "conditions": conditions,
        "cancer_types": map_conditions(conditions),
        "overall_status": status_module.get("overallStatus") or "UNKNOWN",
        "brief_summary": descr_module.get("briefSummary") or "",
        "eligibility_text": eligibility_module.get("eligibilityCriteria") or "",
        "min_age_years": _parse_min_age(eligibility_module.get("minimumAge")),
        "max_age_years": _parse_min_age(eligibility_module.get("maximumAge")),
    }


# ─────────────────────────────────────────────────────────────
# Kimi structuring
# ─────────────────────────────────────────────────────────────


async def structure_predicates(meta: dict) -> StructuredPredicates:
    """Call Kimi with the trial's raw eligibility text. Returns a best-effort
    structured payload; defaults on LLM failure."""
    if not has_api_key():
        return StructuredPredicates(
            notes=["K2_API_KEY unset - eligibility could not be structured"]
        )

    user_prompt = (
        f"NCT ID: {meta['nct_id']}\n"
        f"Phase: {meta['phase']}\n"
        f"CT.gov conditions: {', '.join(meta['conditions'])}\n"
        f"Mapped cancer_types: {', '.join(meta['cancer_types'])}\n"
        f"Min age: {meta['min_age_years']}\n"
        f"Max age: {meta['max_age_years']}\n"
        f"\nBrief summary:\n{meta['brief_summary'][:1500]}\n"
        f"\nRaw eligibility criteria:\n{meta['eligibility_text'][:6000]}\n"
        f"\nReturn the structured JSON now."
    )

    try:
        return await call_for_json(
            schema=StructuredPredicates,
            system_prompt=STRUCTURE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=1200,
        )
    except Exception as e:  # noqa: BLE001
        return StructuredPredicates(
            notes=[f"Kimi structuring failed: {type(e).__name__}: {e}"]
        )


# ─────────────────────────────────────────────────────────────
# Render per-trial .py file
# ─────────────────────────────────────────────────────────────


def _py_repr(v: Any) -> str:
    """Deterministic, diff-friendly Python repr."""
    if isinstance(v, frozenset):
        return f"frozenset({_py_repr(sorted(v))})"
    if isinstance(v, set):
        return f"{{{', '.join(_py_repr(x) for x in sorted(v))}}}"
    if isinstance(v, dict):
        if not v:
            return "{}"
        items = ", ".join(f"{_py_repr(k)}: {_py_repr(val)}" for k, val in sorted(v.items()))
        return "{" + items + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_py_repr(x) for x in v) + "]"
    return repr(v)


def render_trial_file(meta: dict, pred: StructuredPredicates, today: str) -> str:
    cancer_types = frozenset(meta["cancer_types"])
    eligible_stage_buckets = set(pred.eligible_stage_buckets) if pred.eligible_stage_buckets else set()
    min_age = pred.min_age_years if pred.min_age_years is not None else meta.get("min_age_years")
    max_age = pred.max_age_years if pred.max_age_years is not None else meta.get("max_age_years")

    fields: list[tuple[str, Any]] = [
        ("nct_id", meta["nct_id"]),
        ("title", meta["title_short"]),
        ("phase", meta["phase"]),
        ("setting", pred.setting_one_liner or meta["title_short"]),
        ("cancer_types", cancer_types),
    ]
    if pred.requires_advanced_disease:
        fields.append(("requires_advanced_disease", True))
    if pred.requires_resectable_high_risk:
        fields.append(("requires_resectable_high_risk", True))
    if pred.requires_braf_v600 is not None:
        fields.append(("requires_braf_v600", pred.requires_braf_v600))
    if min_age is not None:
        fields.append(("min_age_years", min_age))
    if max_age is not None:
        fields.append(("max_age_years", max_age))
    if eligible_stage_buckets:
        fields.append(("eligible_stage_buckets", eligible_stage_buckets))
    if pred.requires_ecog_0_1:
        fields.append(("requires_ecog_0_1", True))
    if pred.requires_no_prior_systemic_advanced:
        fields.append(("requires_no_prior_systemic_advanced", True))
    if pred.requires_prior_anti_pd1:
        fields.append(("requires_prior_anti_pd1", True))
    if pred.requires_measurable_disease:
        fields.append(("requires_measurable_disease", True))
    if pred.requires_lag3_ihc_result:
        fields.append(("requires_lag3_ihc_result", True))
    if pred.min_life_expectancy_months is not None:
        fields.append(("min_life_expectancy_months", pred.min_life_expectancy_months))
    if pred.biomarker_gates:
        fields.append(("biomarker_gates", pred.biomarker_gates))
    if pred.pdl1_min_tps is not None:
        fields.append(("pdl1_min_tps", pred.pdl1_min_tps))
    if pred.notes:
        fields.append(("never_in_tcga_gates", pred.notes))
    fields.append(("scraped_at", today))

    body = ",\n    ".join(f"{k}={_py_repr(v)}" for k, v in fields)

    raw = (meta.get("eligibility_text") or "").strip()
    raw_block = raw.replace('"""', '\\"\\"\\"')

    return (
        f'"""{meta["title_short"]}\n'
        f"\n"
        f"NCT: {meta['nct_id']}\n"
        f"Phase: {meta['phase']}\n"
        f"CT.gov conditions: {meta['conditions']}\n"
        f"Mapped cancer_types: {meta['cancer_types']}\n"
        f"Overall status: {meta['overall_status']}\n"
        f"Generated: {today} by scripts/scrape_regeneron_trials.py\n"
        f"\"\"\"\n"
        f"\n"
        f"from ..regeneron_rules import TrialRule\n"
        f"\n"
        f"TRIAL = TrialRule(\n"
        f"    {body},\n"
        f")\n"
        f"\n"
        f"_RAW_ELIGIBILITY = \"\"\"\n"
        f"{raw_block}\n"
        f"\"\"\"\n"
    )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


async def amain(limit: int | None, dry_run: bool) -> int:
    today = _dt.date.today().isoformat()

    async with httpx.AsyncClient() as client:
        print("→ Fetching Regeneron studies from ClinicalTrials.gov…")
        studies = await fetch_regeneron_studies(client)
        print(f"  ← {len(studies)} studies returned")

    coerced = [s for s in (_coerce_study(s) for s in studies) if s]
    print(f"  ← {len(coerced)} oncology trials after filtering")

    if limit is not None:
        coerced = coerced[:limit]
        print(f"  (limited to {limit} trials)")

    if dry_run:
        print("\nDRY RUN - trials that would be written:")
        for m in coerced:
            print(f"  {m['nct_id']} · {m['phase']} · {m['cancer_types']} · {m['title_short'][:70]}")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Wipe old per-trial files - the subpackage is the source of truth.
    for p in OUT_DIR.glob("nct*.py"):
        p.unlink()
        print(f"  removed stale {p.name}")

    unmapped: set[str] = set()
    written = 0
    for meta in coerced:
        if meta["cancer_types"] == ["other"]:
            unmapped.update(meta["conditions"])

        print(f"→ {meta['nct_id']}: structuring eligibility with K2…")
        pred = await structure_predicates(meta)
        body = render_trial_file(meta, pred, today)
        out_path = OUT_DIR / f"{meta['nct_id'].lower()}.py"
        out_path.write_text(body)
        written += 1
        print(f"  wrote {out_path.relative_to(_REPO_ROOT)}")

    print(f"\n✓ wrote {written} trial files to {OUT_DIR.relative_to(_REPO_ROOT)}")
    if unmapped:
        print(
            f"⚠ {len(unmapped)} conditions bucketed as 'other' - "
            f"consider extending CONDITION_TO_CANCER_TYPE:"
        )
        for c in sorted(unmapped):
            print(f"   - {c}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="debug: only scrape N trials")
    ap.add_argument("--dry-run", action="store_true", help="print what would be written without writing")
    args = ap.parse_args()
    sys.exit(asyncio.run(amain(limit=args.limit, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
