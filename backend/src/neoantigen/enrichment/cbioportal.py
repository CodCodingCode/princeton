"""cBioPortal REST client for TCGA-SKCM prior-therapy enrichment.

cBioPortal overlays curated clinical annotations on top of TCGA ids, sometimes
including prior-treatment history that GDC's open-access clinical export
doesn't carry. Coverage is sparse (~20% of TCGA-SKCM) but each hit removes
one "unknown" criterion from the Regeneron eligibility check.

Design:
  * Public API, no auth, small disk cache.
  * Wrapped in ``fetch_prior_therapies`` which *never raises* — silent failure
    matches the rest of the pipeline's "degrade gracefully" contract.

Environment:
  * ``NEOVAX_CBIOPORTAL_BASE`` — override base URL (default public instance).
  * ``NEOVAX_CBIOPORTAL_DISABLED=1`` — hard-skip (e.g. CI offline).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

STUDY_ID = "skcm_tcga"
DEFAULT_BASE = "https://www.cbioportal.org/api"
CACHE_DIR = Path.home() / ".cache" / "neoantigen" / "cbioportal"

# Attribute IDs that historically carry prior-systemic-therapy strings in the
# skcm_tcga study. cBioPortal's clinical-attribute schema varies per project;
# we probe each one and concatenate what we find.
_THERAPY_ATTRIBUTE_IDS: tuple[str, ...] = (
    "TREATMENT_OUTCOME_FIRST_COURSE",
    "SYSTEMIC_THERAPY",
    "PHARMACEUTICAL_TX_ADJUVANT",
    "RADIATION_THERAPY",  # false positive risk; filter below
)


def has_cbioportal_access() -> bool:
    """Return False when the client is explicitly disabled."""
    return os.getenv("NEOVAX_CBIOPORTAL_DISABLED", "") not in {"1", "true", "True"}


async def fetch_prior_therapies(
    submitter_id: str,
    *,
    timeout_s: float = 5.0,
) -> list[str] | None:
    """Return a list of prior-therapy agent strings, or ``None`` on any failure.

    Cache hit returns cached list even if the network is down.
    """
    cache_path = CACHE_DIR / f"{submitter_id}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            pass

    base = os.getenv("NEOVAX_CBIOPORTAL_BASE", DEFAULT_BASE).rstrip("/")
    url = f"{base}/studies/{STUDY_ID}/patients/{submitter_id}/clinical-data"

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    therapies = _extract_therapies(data)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(therapies))
    except Exception:
        pass
    return therapies


def _extract_therapies(records: list[dict]) -> list[str]:
    """Pull therapy-name strings out of a cBioPortal clinical-data response."""
    out: list[str] = []
    for rec in records or []:
        attr = (rec.get("clinicalAttributeId") or "").upper()
        val = (rec.get("value") or "").strip()
        if not val or val.lower() in {"not available", "unknown", "none"}:
            continue
        if attr in _THERAPY_ATTRIBUTE_IDS and attr != "RADIATION_THERAPY":
            # Some records are free-text like "CISPLATIN + DTIC"; split on
            # common separators so the list comes back as individual agents.
            for tok in _split_agents(val):
                if tok and tok.lower() not in (t.lower() for t in out):
                    out.append(tok)
    return out


def _split_agents(val: str) -> list[str]:
    for sep in ("+", ",", ";", "/"):
        if sep in val:
            return [p.strip() for p in val.split(sep) if p.strip()]
    return [val.strip()]
