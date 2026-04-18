"""ClinicalTrials.gov v2 client - cancer-type-agnostic trial search.

One async call, disk-cached, returns lightly-normalised `CTGovStudy` rows.
Structured eligibility evaluation lives in :mod:`regeneron_rules` (Regeneron
tier) and :mod:`trials_global` (everyone else) - this file just fetches raw
trial records.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field


CTGOV_BASE = "https://clinicaltrials.gov/api/v2/studies"


class CTGovStudy(BaseModel):
    nct_id: str
    brief_title: str
    phase: str | None = None
    sponsor: str = "Unknown"
    conditions: list[str] = Field(default_factory=list)
    eligibility_text: str = ""
    min_age: str | None = None
    site_contacts: list[dict[str, str]] = Field(default_factory=list)
    overall_status: str = "UNKNOWN"

    @property
    def url(self) -> str:
        return f"https://clinicaltrials.gov/study/{self.nct_id}"


def _cache_dir() -> Path:
    root = Path(os.environ.get("NEOANTIGEN_CACHE", Path.home() / ".cache" / "neoantigen"))
    path = root / "trials"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _normalise(raw: dict[str, Any]) -> CTGovStudy | None:
    """Flatten a v2 `studies[*]` record into our slim model.

    v2 shape: study.protocolSection.{identificationModule,statusModule,
    sponsorCollaboratorsModule,designModule,conditionsModule,eligibilityModule,
    contactsLocationsModule}.
    """
    try:
        ps = raw["protocolSection"]
        ident = ps.get("identificationModule", {})
        status = ps.get("statusModule", {})
        sponsors = ps.get("sponsorCollaboratorsModule", {})
        design = ps.get("designModule", {})
        cond = ps.get("conditionsModule", {})
        elig = ps.get("eligibilityModule", {})
        locs = ps.get("contactsLocationsModule", {})
    except (KeyError, TypeError):
        return None

    phases = design.get("phases") or []
    phase = ", ".join(phases) if phases else None

    contacts: list[dict[str, str]] = []
    for c in (locs.get("centralContacts") or [])[:3]:
        contacts.append(
            {
                "name": c.get("name", ""),
                "email": c.get("email", ""),
                "phone": c.get("phone", ""),
                "role": c.get("role", ""),
            }
        )

    return CTGovStudy(
        nct_id=ident.get("nctId", ""),
        brief_title=ident.get("briefTitle", ""),
        phase=phase,
        sponsor=(sponsors.get("leadSponsor") or {}).get("name", "Unknown"),
        conditions=cond.get("conditions") or [],
        eligibility_text=elig.get("eligibilityCriteria", "") or "",
        min_age=elig.get("minimumAge"),
        site_contacts=contacts,
        overall_status=status.get("overallStatus", "UNKNOWN"),
    )


def _cache_slug(condition: str, status_key: str) -> str:
    """Filesystem-safe cache key for a (condition, status) pair."""
    safe = "".join(c.lower() if c.isalnum() else "_" for c in condition)
    safe = safe.strip("_") or "any"
    return f"{safe}_{status_key}"


async def fetch_trials_by_condition(
    condition: str,
    *,
    recruiting_only: bool = True,
    page_size: int = 50,
    use_cache: bool = True,
) -> list[CTGovStudy]:
    """Hit CT.gov v2 ``/studies`` for a free-text condition query.

    ``condition`` is any string CT.gov accepts as ``query.cond`` -
    "Melanoma", "Lung Adenocarcinoma", "Breast Cancer", etc. Whole-response
    results are cached under ``~/.cache/neoantigen/trials/<slug>_<status>.json``
    so repeated searches for the same cancer type are free.
    """
    status_key = "recruiting" if recruiting_only else "all"
    cache = _cache_dir() / f"{_cache_slug(condition, status_key)}.json"
    if use_cache and cache.exists():
        try:
            raw_studies = json.loads(cache.read_text())
        except json.JSONDecodeError:
            raw_studies = None
        if raw_studies:
            return [s for s in (_normalise(r) for r in raw_studies) if s and s.nct_id]

    params: dict[str, str | int] = {
        "query.cond": condition,
        "pageSize": page_size,
        "format": "json",
    }
    if recruiting_only:
        params["filter.overallStatus"] = "RECRUITING"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(CTGOV_BASE, params=params)
            resp.raise_for_status()
            body = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    raw_studies = body.get("studies") or []
    if raw_studies:
        try:
            cache.write_text(json.dumps(raw_studies))
        except OSError:
            pass

    return [s for s in (_normalise(r) for r in raw_studies) if s and s.nct_id]


async def fetch_melanoma_trials(
    *,
    condition: str = "Melanoma",
    recruiting_only: bool = True,
    page_size: int = 50,
    use_cache: bool = True,
) -> list[CTGovStudy]:
    """Back-compat wrapper around :func:`fetch_trials_by_condition`.

    Kept so the scraper + older call sites keep working. New code should use
    ``fetch_trials_by_condition`` directly.
    """
    return await fetch_trials_by_condition(
        condition,
        recruiting_only=recruiting_only,
        page_size=page_size,
        use_cache=use_cache,
    )
