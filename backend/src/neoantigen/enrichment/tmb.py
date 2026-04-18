"""Tumour mutational burden from the mutation list.

The pipeline parser only surfaces missense variants, so the numerator is
``len(mutations)``. The denominator uses the exome-equivalent size (~3 Mb
after assuming roughly 30 Mb × 10% coding capture, but in practice melanoma
TMB is reported on the ~30 Mb exome, giving ``count / 30``). We pick **30 Mb**
to match the FDA companion-diagnostic convention (FoundationOne CDx, MSK-IMPACT)
so thresholds like "TMB-high ≥ 10 mut/Mb" are comparable.
"""

from __future__ import annotations

from ..models import Mutation

EXOME_MB = 30.0


def compute_tmb(mutations: list[Mutation]) -> float | None:
    """Return TMB in mutations/Mb, or ``None`` when no mutations were called."""
    if not mutations:
        return None
    return round(len(mutations) / EXOME_MB, 2)
