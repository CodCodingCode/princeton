"""Reflect the NCCN graph's evidence requirements for UI + telemetry.

The walker already slices `evidence_required` out of each `NCCNNode` at runtime.
This module just surfaces the *schema* of that evidence map so the frontend can
render "this extracted field blocks nodes X and Y" without duplicating the
mapping manually.

Everything derives from `melanoma_v2024.GRAPH` - adding a node there
automatically flows through to the UI hints.
"""

from __future__ import annotations

from .melanoma_v2024 import GRAPH


# Fields the walker asks about somewhere in the graph, minus the always-filled
# pathology free-text bucket `notes` (which is rendered elsewhere and never
# meaningfully "missing"). Derived fields (`t_stage`, `braf_status`) stay in -
# they can still be "unknown" if their source fields weren't extracted.
_EXCLUDED = frozenset({"notes"})


def _collect_fields() -> frozenset[str]:
    fields: set[str] = set()
    for node in GRAPH.values():
        for f in node.evidence_required:
            if f not in _EXCLUDED:
                fields.add(f)
    return frozenset(fields)


NCCN_EVIDENCE_FIELDS: frozenset[str] = _collect_fields()


def blocking_nodes(field: str) -> list[tuple[str, str]]:
    """Return `(node_id, node_title)` pairs that list `field` in their evidence."""
    return [
        (node.id, node.title)
        for node in GRAPH.values()
        if field in node.evidence_required
    ]


_DISPLAY_LABELS: dict[str, str] = {
    "melanoma_subtype": "Subtype",
    "confidence": "Extraction confidence",
    "breslow_thickness_mm": "Breslow",
    "ulceration": "Ulceration",
    "mitotic_rate_per_mm2": "Mitoses/mm²",
    "tils_present": "TILs",
    "pdl1_estimate": "PD-L1",
    "lag3_ihc_percent": "LAG-3 IHC",
    "t_stage": "Derived T-stage",
    "mutations": "Mutations",
    "braf_status": "BRAF status",
    "tumor_mutational_burden": "TMB",
}


def field_display_label(field: str) -> str:
    return _DISPLAY_LABELS.get(field, field)


def evidence_map_payload() -> dict[str, list[dict[str, str]]]:
    """Shape the frontend consumes on the `pdf_extracted` event."""
    return {
        field: [
            {"node_id": nid, "node_title": title}
            for nid, title in blocking_nodes(field)
        ]
        for field in sorted(NCCN_EVIDENCE_FIELDS)
    }


__all__ = [
    "NCCN_EVIDENCE_FIELDS",
    "blocking_nodes",
    "field_display_label",
    "evidence_map_payload",
]
