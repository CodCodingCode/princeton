"""Discovery tools for sequencing labs, vet oncologists, and synthesis vendors.

Uses Google Places API (New) for geo queries. Falls back to a curated static list
when no GOOGLE_PLACES_API_KEY is present (demo still works offline).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import httpx

from ..models import LabMatch

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


# ─────────────────────────────────────────────────────────────
# Static fallback data
# ─────────────────────────────────────────────────────────────

STATIC_SEQUENCING_LABS: list[dict[str, Any]] = [
    {
        "name": "Vidium Animal Health",
        "address": "Phoenix, AZ, USA",
        "website": "https://vidiumah.com",
        "email": "info@vidiumah.com",
        "notes": "Canine tumor WES + RNA-seq. Established veterinary oncology sequencing provider.",
        "estimated_cost_usd": 800,
        "turnaround_days": 21,
    },
    {
        "name": "ImpriMed",
        "address": "Palo Alto, CA, USA",
        "website": "https://imprimedicine.com",
        "email": "support@imprimedicine.com",
        "notes": "AI-guided canine lymphoma diagnostics; expanding to solid tumors.",
        "estimated_cost_usd": 950,
        "turnaround_days": 14,
    },
    {
        "name": "Fidocure",
        "address": "Mountain View, CA, USA",
        "website": "https://fidocure.com",
        "email": "hello@fidocure.com",
        "notes": "Canine tumor genomic profiling + drug recommendation platform.",
        "estimated_cost_usd": 700,
        "turnaround_days": 14,
    },
    {
        "name": "UC Davis Veterinary Genetics Lab",
        "address": "Davis, CA, USA",
        "website": "https://vgl.ucdavis.edu",
        "email": "vgl@ucdavis.edu",
        "notes": "Research-grade sequencing + DLA typing. Academic pricing.",
        "estimated_cost_usd": 400,
        "turnaround_days": 28,
    },
    {
        "name": "Cornell Animal Health Diagnostic Center",
        "address": "Ithaca, NY, USA",
        "website": "https://www.vet.cornell.edu/animal-health-diagnostic-center",
        "email": "ahdc@cornell.edu",
        "notes": "Academic diagnostic center with NGS capabilities.",
        "estimated_cost_usd": 550,
        "turnaround_days": 21,
    },
]

STATIC_VET_ONCOLOGISTS: list[dict[str, Any]] = [
    {
        "name": "Ontario Veterinary College — Mona Campbell Centre",
        "address": "Guelph, ON, Canada",
        "phone": "+1-519-823-8830",
        "website": "https://ovc.uoguelph.ca/oncology",
        "notes": "Academic oncology service with active immunotherapy trials.",
    },
    {
        "name": "VCA Canada 404 Veterinary Emergency & Referral Hospital",
        "address": "Newmarket, ON, Canada",
        "phone": "+1-905-953-9500",
        "website": "https://vcacanada.com/404",
        "notes": "Board-certified oncologists; referral-based.",
    },
    {
        "name": "Flint Animal Cancer Center — Colorado State University",
        "address": "Fort Collins, CO, USA",
        "phone": "+1-970-297-1234",
        "website": "https://www.csuanimalcancercenter.org",
        "notes": "Largest academic veterinary cancer center; runs NCI Comparative Oncology trials.",
    },
    {
        "name": "PennVet Ryan Veterinary Hospital Oncology",
        "address": "Philadelphia, PA, USA",
        "phone": "+1-215-746-8911",
        "website": "https://www.vet.upenn.edu/veterinary-hospitals/ryan-veterinary-hospital",
        "notes": "Mason lab immunotherapy trials (HER2 listeria vaccine for osteosarcoma).",
    },
    {
        "name": "Animal Medical Center NYC Oncology Service",
        "address": "New York, NY, USA",
        "phone": "+1-212-838-7053",
        "website": "https://www.amcny.org/oncology",
        "notes": "Comprehensive oncology service; clinical trials program.",
    },
]

STATIC_DLA_TYPING_LABS: list[dict[str, Any]] = [
    {
        "name": "UC Davis Veterinary Genetics Laboratory",
        "address": "Davis, CA, USA",
        "website": "https://vgl.ucdavis.edu",
        "email": "vgl@ucdavis.edu",
        "notes": "DLA class I + II typing via sequencing.",
        "estimated_cost_usd": 120,
        "turnaround_days": 10,
    },
    {
        "name": "Genoscoper / Wisdom Panel",
        "address": "Helsinki, Finland",
        "website": "https://www.wisdompanel.com",
        "notes": "Commercial DLA typing integrated with breed testing.",
        "estimated_cost_usd": 180,
        "turnaround_days": 14,
    },
]


# ─────────────────────────────────────────────────────────────
# Google Places API (New) — real geo queries
# ─────────────────────────────────────────────────────────────


async def _places_text_search(query: str, location: str) -> list[dict[str, Any]]:
    """Call Places API (New) — Text Search endpoint."""
    api_key = os.environ.get("PLACES_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return []

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.internationalPhoneNumber,places.websiteUri,places.location,places.rating,places.userRatingCount",
    }
    body = {"textQuery": f"{query} near {location}", "pageSize": 10}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            return resp.json().get("places", [])
        except Exception:
            return []


def _place_to_labmatch(place: dict[str, Any], category: str, notes: str = "") -> LabMatch:
    return LabMatch(
        name=place.get("displayName", {}).get("text", "Unknown"),
        category=category,  # type: ignore[arg-type]
        address=place.get("formattedAddress", ""),
        phone=place.get("internationalPhoneNumber"),
        website=place.get("websiteUri"),
        notes=notes or f"Rating: {place.get('rating', 'N/A')} ({place.get('userRatingCount', 0)} reviews)",
    )


async def find_sequencing_labs(location: str, radius_km: int = 50) -> list[LabMatch]:
    places = await _places_text_search("veterinary genomics sequencing laboratory", location)
    real = [_place_to_labmatch(p, "sequencing") for p in places]
    static = [LabMatch(category="sequencing", **d) for d in STATIC_SEQUENCING_LABS]
    return (real + static)[:8]


async def find_vet_oncologists(location: str, radius_km: int = 50) -> list[LabMatch]:
    places = await _places_text_search("veterinary oncologist board certified", location)
    real = [_place_to_labmatch(p, "vet_oncology") for p in places]
    static = [LabMatch(category="vet_oncology", **d) for d in STATIC_VET_ONCOLOGISTS]
    return (real + static)[:8]


def find_synthesis_vendors(mrna_length_bp: int = 600) -> list[LabMatch]:
    """Load curated vendor list and synthesize LabMatch objects."""
    vendors_file = DATA_DIR / "vendors.json"
    data = json.loads(vendors_file.read_text())
    results: list[LabMatch] = []
    for v in data["vendors"]:
        cost = None
        if "price_per_bp_usd" in v:
            cost = round(v["price_per_bp_usd"] * mrna_length_bp, 2)
        elif "price_per_mg_usd" in v:
            cost = v["price_per_mg_usd"]
        cost = max(cost or 0, v.get("min_order_usd", 0)) or None
        results.append(
            LabMatch(
                name=v["name"],
                category="synthesis",
                address=v.get("location", ""),
                email=v.get("email"),
                website=v.get("website"),
                notes=v.get("notes", v.get("service", "")),
                estimated_cost_usd=cost,
                turnaround_days=v.get("turnaround_days"),
            )
        )
    return results


async def find_dla_typing_labs() -> list[LabMatch]:
    return [LabMatch(category="dla_typing", **d) for d in STATIC_DLA_TYPING_LABS]
