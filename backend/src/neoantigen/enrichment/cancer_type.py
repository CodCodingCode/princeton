"""Deterministic primary-cancer detection from extracted evidence.

The dynamic railway walker seeds its RAG queries with ``primary_cancer_type``,
so we need a stable string even when the VLM didn't extract one directly.
Order of precedence (first match wins):

1. Explicit ``pathology.primary_cancer_type`` from the VLM / aggregator.
2. ``pathology.melanoma_subtype`` ≠ "unknown"  → "cutaneous_melanoma".
3. Free-text hints in ``pathology.histology`` + ``pathology.primary_site``.
4. Driver-mutation signatures (e.g. EGFR exon 19 del → lung_adenocarcinoma).
5. Fallback: "unknown".

All checks are case-insensitive; nothing here raises.
"""

from __future__ import annotations

from ..models import Mutation, PathologyFindings


# Supported tokens — must match the cancer_type metadata used by the Chroma
# corpus (see scripts/build_pubmed_rag.py CANCER_TOPICS keys).
SUPPORTED: frozenset[str] = frozenset(
    {
        "cutaneous_melanoma",
        "lung_adenocarcinoma",
        "lung_squamous",
        "breast_ductal_carcinoma",
        "breast_carcinoma",
        "colorectal_adenocarcinoma",
        "colorectal_carcinoma",
        "gastric_carcinoma",
        "pancreatic_carcinoma",
        "prostate_carcinoma",
        "ovarian_carcinoma",
        "renal_cell_carcinoma",
        "hepatocellular_carcinoma",
        "bladder_carcinoma",
        "head_neck_scc",
        "glioblastoma",
        "lymphoma_dlbcl",
        "multiple_myeloma",
        "other",
        "unknown",
    }
)


# (substring in histology/site, mapped cancer_type)
# Order matters — more specific substrings first.
_TEXT_HINTS: tuple[tuple[str, str], ...] = (
    ("melanoma", "cutaneous_melanoma"),
    ("lung adenocarcinoma", "lung_adenocarcinoma"),
    ("adenocarcinoma of the lung", "lung_adenocarcinoma"),
    ("adenocarcinoma of lung", "lung_adenocarcinoma"),
    ("nsclc", "lung_adenocarcinoma"),
    ("non-small cell lung", "lung_adenocarcinoma"),
    ("non small cell lung", "lung_adenocarcinoma"),
    ("squamous cell carcinoma of the lung", "lung_squamous"),
    ("lung squamous", "lung_squamous"),
    ("ductal carcinoma", "breast_ductal_carcinoma"),
    ("lobular carcinoma", "breast_carcinoma"),
    ("breast cancer", "breast_carcinoma"),
    ("colorectal adenocarcinoma", "colorectal_adenocarcinoma"),
    ("colorectal", "colorectal_adenocarcinoma"),
    ("colon adenocarcinoma", "colorectal_adenocarcinoma"),
    ("rectal adenocarcinoma", "colorectal_adenocarcinoma"),
    ("gastric", "gastric_carcinoma"),
    ("stomach", "gastric_carcinoma"),
    ("pancreatic", "pancreatic_carcinoma"),
    ("prostate", "prostate_carcinoma"),
    ("ovarian", "ovarian_carcinoma"),
    ("renal cell", "renal_cell_carcinoma"),
    ("clear cell carcinoma of the kidney", "renal_cell_carcinoma"),
    ("hepatocellular", "hepatocellular_carcinoma"),
    ("liver cancer", "hepatocellular_carcinoma"),
    ("urothelial", "bladder_carcinoma"),
    ("bladder cancer", "bladder_carcinoma"),
    ("head and neck squamous", "head_neck_scc"),
    ("oropharyngeal squamous", "head_neck_scc"),
    ("glioblastoma", "glioblastoma"),
    ("gbm", "glioblastoma"),
    ("diffuse large b-cell", "lymphoma_dlbcl"),
    ("dlbcl", "lymphoma_dlbcl"),
    ("multiple myeloma", "multiple_myeloma"),
)


# Driver-mutation → cancer type. Heavily approximate; used only as a last
# resort when histology/site gave nothing.
def _infer_from_mutations(mutations: list[Mutation]) -> str | None:
    genes = {m.gene.upper() for m in mutations}
    positions = {(m.gene.upper(), m.position) for m in mutations}

    # EGFR on lung is the canonical lung-adeno driver.
    if "EGFR" in genes:
        return "lung_adenocarcinoma"
    # ALK fusions mostly present as "ALK" rearrangements which our parser
    # won't capture as an AA change. If we ever see ALK here, assume lung.
    if "ALK" in genes or "ROS1" in genes or "MET" in genes:
        return "lung_adenocarcinoma"
    # KRAS G12C — lung > CRC prevalence, but mixed. Don't assume.
    # BRCA1/2 — breast/ovarian/pancreatic/prostate, don't assume.
    # HER2 amp — breast/gastric, don't assume.
    # BRAF V600E — melanoma > CRC > thyroid > NSCLC. Assume melanoma only if
    # melanoma_subtype already hinted.
    return None


def _canonicalise(token: str | None) -> str | None:
    """Snap a loose token to a supported cancer type, or None if off-map."""
    if not token:
        return None
    t = token.strip().lower().replace(" ", "_").replace("-", "_")
    if t in SUPPORTED:
        return t
    # A couple of common aliases.
    aliases = {
        "melanoma": "cutaneous_melanoma",
        "nsclc": "lung_adenocarcinoma",
        "lung_cancer": "lung_adenocarcinoma",
        "breast": "breast_carcinoma",
        "crc": "colorectal_adenocarcinoma",
        "rcc": "renal_cell_carcinoma",
        "hcc": "hepatocellular_carcinoma",
        "gbm": "glioblastoma",
        "dlbcl": "lymphoma_dlbcl",
    }
    return aliases.get(t)


def _scan_text(*chunks: str) -> str | None:
    blob = " ".join(chunks).lower()
    for needle, cancer_type in _TEXT_HINTS:
        if needle in blob:
            return cancer_type
    return None


def detect_primary_cancer(
    pathology: PathologyFindings,
    mutations: list[Mutation],
) -> str:
    """Return a supported cancer_type token for RAG routing."""
    # 1. Explicit extracted value.
    explicit = _canonicalise(pathology.primary_cancer_type)
    if explicit and explicit not in {"unknown", "other"}:
        return explicit

    # 2. Melanoma subtype shortcut.
    if pathology.melanoma_subtype not in {"unknown", None}:
        return "cutaneous_melanoma"

    # 3. Free-text scan of histology + primary_site + notes.
    hit = _scan_text(pathology.histology, pathology.primary_site, pathology.notes)
    if hit:
        return hit

    # 4. Mutation signature heuristic.
    inferred = _infer_from_mutations(mutations)
    if inferred:
        return inferred

    return "unknown"


__all__ = ["detect_primary_cancer", "SUPPORTED"]
