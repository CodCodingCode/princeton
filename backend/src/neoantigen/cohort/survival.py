"""Kaplan-Meier estimator for the twin cohort.

Pure-Python implementation — avoids pulling in lifelines/scipy for what's
ultimately a few-hundred-row computation. Returns a list of step-function
points that the frontend renders as a Plotly survival curve.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tcga import TCGAPatient


@dataclass
class KMPoint:
    days: int
    survival: float
    at_risk: int
    events_so_far: int


def kaplan_meier(patients: list[TCGAPatient]) -> list[KMPoint]:
    """Standard Kaplan-Meier product-limit estimator. Censoring = vital_status Alive."""
    rows: list[tuple[int, int]] = []
    for p in patients:
        days = p.survival_days
        ev = p.event
        if days is None or ev is None or days < 0:
            continue
        rows.append((days, ev))
    if not rows:
        return []

    rows.sort(key=lambda x: x[0])
    n = len(rows)
    survival = 1.0
    points: list[KMPoint] = [KMPoint(days=0, survival=1.0, at_risk=n, events_so_far=0)]
    events_so_far = 0

    by_day: dict[int, list[int]] = {}
    for d, e in rows:
        by_day.setdefault(d, []).append(e)

    at_risk = n
    for day in sorted(by_day):
        events_today = sum(by_day[day])
        if at_risk > 0 and events_today > 0:
            survival *= 1.0 - (events_today / at_risk)
        events_so_far += events_today
        points.append(KMPoint(
            days=day,
            survival=round(survival, 4),
            at_risk=at_risk,
            events_so_far=events_so_far,
        ))
        at_risk -= len(by_day[day])
    return points


def split_kaplan_meier(
    patients: list[TCGAPatient],
    *,
    label: str = "treatment",
) -> dict[str, list[KMPoint]]:
    """Split the cohort by a labelled subgroup and return one curve per group.

    For now we expose two splits: ``stage`` (I+II vs III+IV) and ``braf``
    (BRAF V600E vs not). TCGA-SKCM clinical data pre-dates modern IO so
    treatment-by-class splits aren't reliable.
    """
    groups: dict[str, list[TCGAPatient]] = {}
    for p in patients:
        if label == "stage":
            key = "Stage III/IV" if p.stage_bucket in {"III", "IV"} else "Stage I/II"
        elif label == "braf":
            key = "BRAF V600E" if p.braf_v600e else "BRAF wild-type"
        else:
            key = "all"
        groups.setdefault(key, []).append(p)
    return {k: kaplan_meier(v) for k, v in groups.items() if v}
