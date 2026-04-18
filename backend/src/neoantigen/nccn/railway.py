"""Railway-map rendering for a walked NCCN path.

A railway map = the chosen treatment path as a solid chain, with the siblings
at each branching node drawn as dashed spurs labelled with a one-line reason
they were not chosen.

We render to Mermaid flowchart syntax so the Next.js client can paste it into
``<mermaid>`` without a layout engine of its own.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..models import RailwayAlternative, RailwayMap, RailwayStep


_ID_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _safe_id(raw: str) -> str:
    return _ID_SAFE.sub("_", raw).strip("_") or "N"


def _mermaid_label(s: str, max_len: int = 80) -> str:
    """Mermaid label — escape quotes + truncate. Double-quoted so spaces/punct survive."""
    s = s.replace('"', "'").replace("\n", " ").strip()
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def to_mermaid(rmap: RailwayMap) -> str:
    """Render the railway as a Mermaid ``flowchart LR`` string."""
    lines: list[str] = ["flowchart TD"]
    step_ids: list[str] = []

    # Main chosen path — solid rectangles linked top-to-bottom.
    for s in rmap.steps:
        step_id = _safe_id(s.node_id)
        step_ids.append(step_id)
        label = f"<b>{_mermaid_label(s.title, 60)}</b><br/>{_mermaid_label(s.chosen_option_label, 80)}"
        lines.append(f'    {step_id}["{label}"]:::chosen')

    for i in range(len(step_ids) - 1):
        lines.append(f"    {step_ids[i]} ==> {step_ids[i + 1]}")

    # Alternatives — dashed spurs branching off the main line.
    alt_counter = 0
    for s in rmap.steps:
        parent = _safe_id(s.node_id)
        for alt in s.alternatives:
            alt_counter += 1
            alt_id = f"{parent}_alt{alt_counter}"
            alt_label = f"<i>{_mermaid_label(alt.option_label, 60)}</i>"
            if alt.reason_not_chosen:
                alt_label += f"<br/><small>{_mermaid_label(alt.reason_not_chosen, 90)}</small>"
            lines.append(f'    {alt_id}("{alt_label}"):::alt')
            lines.append(f"    {parent} -.-> {alt_id}")

    # Final recommendation node when available.
    if rmap.final_recommendation and step_ids:
        final_id = "FINAL_PLAN"
        label = f"<b>Recommended</b><br/>{_mermaid_label(rmap.final_recommendation, 120)}"
        lines.append(f'    {final_id}["{label}"]:::final')
        lines.append(f"    {step_ids[-1]} ==> {final_id}")

    # Styling classes — consumed by the frontend's mermaid theme.
    lines.extend(
        [
            "    classDef chosen fill:#0ea5a4,stroke:#0d9488,color:#ffffff,stroke-width:2px;",
            "    classDef alt fill:#1f2937,stroke:#4b5563,color:#d1d5db,stroke-dasharray:4 3;",
            "    classDef final fill:#14b8a6,stroke:#0f766e,color:#ffffff,stroke-width:3px;",
        ]
    )
    return "\n".join(lines)


def build_map(
    steps: Iterable[RailwayStep],
    *,
    final_recommendation: str = "",
) -> RailwayMap:
    step_list = list(steps)
    rmap = RailwayMap(
        steps=step_list,
        final_recommendation=final_recommendation,
    )
    rmap.mermaid = to_mermaid(rmap)
    return rmap


__all__ = ["to_mermaid", "build_map", "RailwayMap", "RailwayStep", "RailwayAlternative"]
