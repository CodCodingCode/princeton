"""ClinicalTrials.gov v2 API adapter."""

from __future__ import annotations

import httpx

from ..models import ClinicalTrial

BASE = "https://clinicaltrials.gov/api/v2/studies"


async def search_trials(client: httpx.AsyncClient, gene: str, *, page_size: int = 5) -> list[ClinicalTrial]:
    params = {
        "query.cond": gene,
        "pageSize": page_size,
        "format": "json",
    }
    try:
        response = await client.get(BASE, params=params, timeout=15.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    data = response.json()
    trials: list[ClinicalTrial] = []
    for study in data.get("studies", []):
        protocol = study.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        status = protocol.get("statusModule", {})
        design = protocol.get("designModule", {})
        nct_id = ident.get("nctId", "")
        if not nct_id:
            continue
        trials.append(
            ClinicalTrial(
                nct_id=nct_id,
                title=ident.get("briefTitle", ""),
                status=status.get("overallStatus", ""),
                phase=(design.get("phases") or [None])[0],
                url=f"https://clinicaltrials.gov/study/{nct_id}",
            )
        )
    return trials
