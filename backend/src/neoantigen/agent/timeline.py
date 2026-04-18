"""Treatment timeline generation + ICS export."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from icalendar import Calendar, Event

from ..models import TimelineEvent


BASE_MILESTONES = [
    (0, "Tumor biopsy shipped", "Overnight to sequencing lab with cold-chain packaging"),
    (1, "WES + RNA-seq complete", "Raw data returned from lab; pipeline re-runs with patient-specific VCF"),
    (2, "DLA typing returned", "Patient's DLA alleles confirmed; top candidates re-scored with real alleles"),
    (3, "Candidate review + synthesis order placed", "Vet oncologist signs off on top 15 epitopes; mRNA ordered"),
    (5, "mRNA received + LNP formulation", "QC: RNA integrity, endotoxin, sterility, particle size"),
    (6, "First vaccination (prime)", "Intramuscular injection; baseline bloodwork + imaging"),
    (7, "Patient monitoring week 1", "Owner-reported symptoms + bloodwork check"),
    (9, "Second vaccination (boost)", "Intramuscular boost; ELISpot + TCR-seq if available"),
    (12, "Response imaging", "CT or MRI to measure tumor response vs baseline"),
    (16, "ctDNA re-sequencing (optional)", "Check for subclonal escape; trigger booster design if needed"),
]


def generate_timeline(start_week: int = 1, species: str = "canine", start_date: date | None = None) -> list[TimelineEvent]:
    anchor = start_date or date.today()
    out: list[TimelineEvent] = []
    for wk, title, desc in BASE_MILESTONES:
        d = anchor + timedelta(weeks=wk)
        out.append(
            TimelineEvent(
                week=start_week + wk,
                date_iso=d.isoformat(),
                title=title,
                description=desc,
            )
        )
    return out


def to_ics(events: list[TimelineEvent], out_path: Path, patient_name: str = "Luna") -> Path:
    cal = Calendar()
    cal.add("prodid", "-//NeoVax Treatment Coordinator//EN")
    cal.add("version", "2.0")
    for ev in events:
        e = Event()
        e.add("summary", f"{patient_name} — {ev.title}")
        e.add("description", ev.description)
        d = date.fromisoformat(ev.date_iso)
        e.add("dtstart", d)
        e.add("dtend", d + timedelta(days=1))
        cal.add_component(e)
    out_path.write_bytes(cal.to_ical())
    return out_path
