"""Fetch + geocode recruiting sites for matched clinical trials.

ClinicalTrials.gov v2 exposes locations in
``protocolSection.contactsLocationsModule.locations``. We pull the first N
locations per NCT, geocode each via the Google Maps Geocoding API when
``GOOGLE_MAPS_API_KEY`` is set, and cache the lookup table on disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

import httpx

from ..models import TrialSite


CTGOV_STUDY = "https://clinicaltrials.gov/api/v2/studies/{nct_id}"
GEOCODE_API = "https://maps.googleapis.com/maps/api/geocode/json"


def _cache_root() -> Path:
    root = Path(
        os.environ.get(
            "NEOANTIGEN_CACHE",
            Path.home() / ".cache" / "neoantigen",
        )
    )
    path = root / "trial_sites"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_cached(nct_id: str) -> list[dict] | None:
    path = _cache_root() / f"{nct_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _save_cached(nct_id: str, data: list[dict]) -> None:
    try:
        (_cache_root() / f"{nct_id}.json").write_text(json.dumps(data))
    except OSError:
        pass


def _extract_locations(raw_study: dict[str, Any], nct_id: str) -> list[TrialSite]:
    try:
        locs = (
            raw_study.get("protocolSection", {})
            .get("contactsLocationsModule", {})
            .get("locations", [])
        )
    except AttributeError:
        locs = []
    out: list[TrialSite] = []
    for loc in locs:
        status = loc.get("status") or ""
        facility = loc.get("facility") or loc.get("name") or ""
        city = loc.get("city") or ""
        state = loc.get("state") or ""
        country = loc.get("country") or ""
        geo = loc.get("geoPoint") or {}
        lat = geo.get("lat")
        lng = geo.get("lon") or geo.get("lng")
        contacts = loc.get("contacts") or []
        first = contacts[0] if contacts else {}
        out.append(
            TrialSite(
                nct_id=nct_id,
                facility=facility,
                city=city,
                state=state,
                country=country,
                lat=float(lat) if lat is not None else None,
                lng=float(lng) if lng is not None else None,
                status=str(status),
                contact_name=first.get("name"),
                contact_phone=first.get("phone"),
                contact_email=first.get("email"),
            )
        )
    return out


async def _fetch_study(client: httpx.AsyncClient, nct_id: str) -> dict | None:
    try:
        resp = await client.get(
            CTGOV_STUDY.format(nct_id=nct_id),
            params={"format": "json"},
        )
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError):
        return None


async def _geocode(
    client: httpx.AsyncClient, site: TrialSite, api_key: str
) -> None:
    """Populate ``site.lat`` / ``site.lng`` via the Google Geocoding API."""
    if site.lat is not None and site.lng is not None:
        return
    query = ", ".join(x for x in [site.facility, site.city, site.state, site.country] if x)
    if not query:
        return
    try:
        resp = await client.get(
            GEOCODE_API,
            params={"address": query, "key": api_key},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return
    results = data.get("results") or []
    if not results:
        return
    loc = results[0].get("geometry", {}).get("location", {})
    site.lat = loc.get("lat")
    site.lng = loc.get("lng")


async def fetch_trial_sites(
    nct_ids: Iterable[str],
    *,
    max_sites_per_trial: int = 12,
    use_cache: bool = True,
) -> list[TrialSite]:
    """Fetch + geocode recruiting sites for every NCT in ``nct_ids``.

    Returns a flat ``list[TrialSite]``. Safe to call offline - returns cached
    data when available and an empty list when the network + cache both fail.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    out: list[TrialSite] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        for nct_id in nct_ids:
            cached = _load_cached(nct_id) if use_cache else None
            if cached is not None:
                out.extend(TrialSite.model_validate(c) for c in cached)
                continue

            raw = await _fetch_study(client, nct_id)
            if raw is None:
                continue
            sites = _extract_locations(raw, nct_id)[:max_sites_per_trial]
            # Prefer recruiting > active > other for display priority
            sites.sort(
                key=lambda s: 0 if "RECRUITING" in s.status.upper()
                else 1 if "ACTIVE" in s.status.upper() else 2
            )
            if api_key:
                for site in sites:
                    await _geocode(client, site, api_key)
            _save_cached(nct_id, [s.model_dump() for s in sites])
            out.extend(sites)

    return out
