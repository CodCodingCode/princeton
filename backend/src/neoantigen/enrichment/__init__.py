"""Free enrichment layer - compute/fetch biomarkers before the clinician types.

Populates :class:`neoantigen.models.EnrichedBiomarkers` from three sources:

1. :mod:`.tmb` - tumour mutational burden from the mutation list (always works).
2. :mod:`.signatures` - UV mutational-signature fraction from the VCF
   (needs real genomic ref/alt bases; degrades to ``None`` on synthetic VCFs).
3. :mod:`.cbioportal` - prior systemic therapies for known TCGA submitter ids
   (network call, silently skipped when offline or unknown id).

The orchestrator calls :func:`enrich` once per case, in parallel with the VLM
and molecular stages. Nothing here raises - every failure path returns a
partial :class:`EnrichedBiomarkers` with the relevant fields left as ``None``.
"""

from __future__ import annotations

from pathlib import Path

from ..models import EnrichedBiomarkers, Mutation
from .cbioportal import fetch_prior_therapies, has_cbioportal_access
from .signatures import compute_uv_signature
from .tmb import compute_tmb


async def enrich(
    mutations: list[Mutation],
    vcf_path: Path | None = None,
    tcga_submitter_id: str | None = None,
    *,
    timeout_s: float = 5.0,
) -> EnrichedBiomarkers:
    """Run every enrichment source. Safe to call with any subset of inputs."""
    enriched = EnrichedBiomarkers()

    # --- TMB (always works when mutations is non-empty) ---
    tmb = compute_tmb(mutations)
    if tmb is not None:
        enriched.tmb_mut_per_mb = tmb
        enriched.source_notes["tmb"] = "computed from mutation count (missense / 3 Mb)"

    # --- UV signature (needs real VCF coords) ---
    if vcf_path is not None and vcf_path.exists():
        uv = compute_uv_signature(vcf_path)
        if uv is not None:
            enriched.uv_signature_fraction = uv.fraction
            enriched.total_snvs_scored = uv.total_scored
            enriched.source_notes["uv_signature"] = (
                f"computed from {uv.total_scored} SNVs with genomic coords"
            )

    # --- cBioPortal prior therapies (only for known TCGA ids) ---
    if tcga_submitter_id and has_cbioportal_access():
        therapies = await fetch_prior_therapies(tcga_submitter_id, timeout_s=timeout_s)
        if therapies is not None:
            enriched.prior_systemic_therapies = therapies
            enriched.prior_anti_pd1 = any(
                t.lower() in _ANTI_PD1_AGENTS for t in therapies
            )
            enriched.source_notes["prior_therapy"] = f"cBioPortal skcm_tcga ({len(therapies)} records)"

    return enriched


_ANTI_PD1_AGENTS: frozenset[str] = frozenset(
    {
        "nivolumab", "pembrolizumab", "cemiplimab", "dostarlimab",
        "opdivo", "keytruda", "libtayo", "jemperli",
    }
)


__all__ = ["enrich", "compute_tmb", "compute_uv_signature", "fetch_prior_therapies"]
