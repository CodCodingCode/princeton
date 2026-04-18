"""Regeneron cohort funnel — portfolio-level trial screening view.

Reads the per-case JSON bundles written by ``neoantigen melanoma-batch``
and aggregates:

  * Per-trial eligibility counts (eligible / needs_more_data / ineligible).
  * Drop-off-by-criterion histogram (which gate fails most often per trial).
  * Enrichment coverage: what fraction of the cohort has TMB / UV / prior-Rx
    auto-filled vs. still needing clinician input.

Output is a single ``funnel_summary.json`` consumable by the CLI Rich
renderer and the Streamlit portfolio page.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class FunnelStats:
    cohort_size: int = 0
    # nct_id -> {eligible, ineligible, needs_more_data, total}
    per_trial: dict[str, dict[str, int]] = field(default_factory=dict)
    per_trial_title: dict[str, str] = field(default_factory=dict)
    # nct_id -> criterion_label -> count of cases where it was blocking
    drop_off_by_criterion: dict[str, dict[str, int]] = field(default_factory=dict)
    # field_name -> fraction of cohort where it's non-null
    enrichment_coverage: dict[str, float] = field(default_factory=dict)
    # "eligible for at least one Regeneron trial"
    at_least_one_regeneron_eligible: int = 0

    def to_json(self) -> dict:
        return asdict(self)


def compute_funnel(case_jsons: Iterable[Path]) -> FunnelStats:
    """Aggregate a directory of per-case case JSONs."""
    stats = FunnelStats()
    per_trial: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_trial_title: dict[str, str] = {}
    drop_off: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cov_counts: dict[str, int] = defaultdict(int)

    total = 0
    for path in case_jsons:
        try:
            case = json.loads(path.read_text())
        except Exception:
            continue
        total += 1

        # Enrichment coverage
        enrichment = case.get("enrichment") or {}
        if enrichment.get("tmb_mut_per_mb") is not None:
            cov_counts["tmb"] += 1
        if enrichment.get("uv_signature_fraction") is not None:
            cov_counts["uv_signature"] += 1
        if enrichment.get("prior_anti_pd1") is not None:
            cov_counts["prior_anti_pd1"] += 1
        if enrichment.get("prior_systemic_therapies"):
            cov_counts["prior_systemic_therapies"] += 1

        intake = case.get("intake") or {}
        for fld in ("ecog", "lag3_ihc_percent", "measurable_disease_recist", "life_expectancy_months"):
            if intake.get(fld) is not None:
                cov_counts[f"intake_{fld}"] += 1

        trials = case.get("trials") or []
        any_regeneron_eligible = False
        for t in trials:
            if not t.get("is_regeneron"):
                continue
            nct = t.get("nct_id")
            status = t.get("status") or "unscored"
            per_trial[nct][status] += 1
            per_trial[nct]["total"] += 1
            per_trial_title[nct] = t.get("title") or per_trial_title.get(nct, "")
            if status == "eligible":
                any_regeneron_eligible = True

            # Drop-off attribution
            if status == "ineligible":
                for label in t.get("failing_criteria") or []:
                    drop_off[nct][label] += 1
            elif status == "needs_more_data":
                for label in t.get("unknown_criteria") or []:
                    drop_off[nct][label] += 1

        if any_regeneron_eligible:
            stats.at_least_one_regeneron_eligible += 1

    stats.cohort_size = total
    stats.per_trial = {k: dict(v) for k, v in per_trial.items()}
    stats.per_trial_title = per_trial_title
    stats.drop_off_by_criterion = {k: dict(v) for k, v in drop_off.items()}
    stats.enrichment_coverage = {
        k: round(v / total, 3) if total else 0.0 for k, v in cov_counts.items()
    }
    return stats


def write_summary(stats: FunnelStats, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(stats.to_json(), indent=2))


def load_summary(path: Path) -> FunnelStats:
    data = json.loads(path.read_text())
    return FunnelStats(
        cohort_size=data.get("cohort_size", 0),
        per_trial=data.get("per_trial", {}),
        per_trial_title=data.get("per_trial_title", {}),
        drop_off_by_criterion=data.get("drop_off_by_criterion", {}),
        enrichment_coverage=data.get("enrichment_coverage", {}),
        at_least_one_regeneron_eligible=data.get("at_least_one_regeneron_eligible", 0),
    )


def top_drop_off(stats: FunnelStats, nct_id: str, top_k: int = 5) -> list[tuple[str, int]]:
    """Return the top-k most-common drop-off criteria for a single trial."""
    criteria = stats.drop_off_by_criterion.get(nct_id, {})
    return sorted(criteria.items(), key=lambda x: -x[1])[:top_k]
