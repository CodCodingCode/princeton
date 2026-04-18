"""Panel 0 · VLM pathology — slide image + findings card + reasoning expander.

Renders inside the left column of the Pathology + NCCN tab. Drops the previous
2-column inner layout because the parent tab already does that split.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from . import theme

_SUBTYPE_LABEL = {
    "superficial_spreading": "Superficial spreading",
    "nodular": "Nodular",
    "lentigo_maligna": "Lentigo maligna",
    "acral_lentiginous": "Acral lentiginous",
    "desmoplastic": "Desmoplastic",
    "other": "Other",
    "unknown": "Unknown",
}


def _ajcc_t_stage(breslow: float | None, ulceration: bool | None) -> str | None:
    """Compute AJCC 8th-edition T-stage from Breslow thickness + ulceration.

    Used as a client-side fallback when the VLM doesn't populate ``t_stage``
    directly. AJCC 8 ranges:

    * T1a: <0.8 mm, no ulceration
    * T1b: <0.8 mm ulcerated OR 0.8-1.0 mm (either)
    * T2a/b: 1.01-2.0 mm · a=no ulceration, b=ulcerated
    * T3a/b: 2.01-4.0 mm
    * T4a/b: >4.0 mm
    """
    if breslow is None:
        return None
    if breslow < 0.8:
        return "T1b" if ulceration else "T1a"
    if breslow <= 1.0:
        return "T1b"
    if breslow <= 2.0:
        return "T2b" if ulceration else "T2a"
    if breslow <= 4.0:
        return "T3b" if ulceration else "T3a"
    return "T4b" if ulceration else "T4a"


def _compose_summary(path: dict, t_stage: str) -> str:
    """Build a one-sentence clinical narrative from the structured findings."""
    subtype_key = path.get("melanoma_subtype") or "unknown"
    subtype_label = _SUBTYPE_LABEL.get(subtype_key, subtype_key.replace("_", " "))
    breslow = path.get("breslow_thickness_mm")
    ulc = path.get("ulceration")
    mit = path.get("mitotic_rate_per_mm2")
    tils = path.get("tils_present")
    pdl1 = path.get("pdl1_estimate")

    if subtype_key == "unknown" and breslow is None:
        return "VLM could not confidently identify melanoma features in this field."

    head_parts: list[str] = []
    head_parts.append(f"{subtype_label} melanoma" if subtype_key != "unknown" else "Melanoma (subtype unclear)")
    if breslow is not None:
        head_parts.append(f"{breslow} mm Breslow")
    if ulc is True:
        head_parts.append("with ulceration")
    elif ulc is False:
        head_parts.append("without ulceration")
    headline = ", ".join(head_parts)
    if t_stage and t_stage != "—":
        headline += f" (AJCC {t_stage})"

    bio_parts: list[str] = []
    if mit is not None:
        if mit >= 5:
            bio_parts.append(f"elevated mitotic rate ({mit}/mm²)")
        elif mit >= 1:
            bio_parts.append(f"{mit}/mm² mitoses")
    if tils == "brisk":
        bio_parts.append("brisk TIL response")
    elif tils == "non_brisk":
        bio_parts.append("non-brisk TILs")
    elif tils == "absent":
        bio_parts.append("no TIL infiltrate")
    if pdl1 and pdl1 != "unknown":
        bio_parts.append(f"PD-L1 {pdl1}")

    if bio_parts:
        bio_sentence = ", ".join(bio_parts)
        # Uppercase only the first character to form a proper sentence — don't
        # use str.capitalize() because it would lowercase "PD-L1" and "TIL".
        bio_sentence = bio_sentence[:1].upper() + bio_sentence[1:]
        return f"{headline}. {bio_sentence}."
    return f"{headline}."


def render_panel() -> None:
    path = st.session_state.pathology or {}
    slide = st.session_state.pathology_slide_path
    thinking = st.session_state.pathology_thinking
    raw = st.session_state.pathology_raw

    if not path and not slide:
        st.markdown(
            theme.empty_state(
                "🔬",
                "MediX reading the slide…",
                "Pathology findings will appear here once the VLM completes its analysis.",
            ),
            unsafe_allow_html=True,
        )
        return

    if slide and Path(slide).exists():
        st.image(slide, caption=Path(slide).name, use_container_width=True)

    subtype_key = path.get("melanoma_subtype") or "unknown"
    subtype_label = _SUBTYPE_LABEL.get(subtype_key, subtype_key.replace("_", " "))
    breslow = path.get("breslow_thickness_mm")
    breslow_str = f"{breslow} mm" if breslow is not None else "—"
    # Prefer the VLM's t_stage if it gave one; otherwise derive from AJCC 8th rules.
    t_stage = path.get("t_stage") or _ajcc_t_stage(breslow, path.get("ulceration")) or "—"
    summary = _compose_summary(path, t_stage)

    chips = ""
    ulc = path.get("ulceration")
    if ulc is True:
        chips += theme.chip("ulceration", "warn")
    elif ulc is False:
        chips += theme.chip("no ulceration")
    tils = path.get("tils_present")
    if tils and tils != "absent":
        chips += theme.chip(f"TILs · {str(tils).replace('_', ' ')}", "ok")
    elif tils == "absent":
        chips += theme.chip("no TILs", "bad")
    pdl1 = path.get("pdl1_estimate")
    if pdl1:
        chips += theme.chip(f"PD-L1 {pdl1}", "info")
    mit = path.get("mitotic_rate_per_mm2")
    if mit is not None:
        chips += theme.chip(f"{mit}/mm² mitoses")

    conf = float(path.get("confidence") or 0.0)
    conf_str = f"{conf:.0%}" if conf else "—"
    notes = path.get("notes") or ""
    notes_html = (
        f'<div style="margin-top:10px;font-size:12px;color:var(--text-dim);line-height:1.5;">{notes}</div>'
        if notes else ""
    )

    summary_html = (
        f'<div style="margin-top:10px;padding:10px 12px;border-left:3px solid var(--accent);'
        f'background:var(--surface-2);border-radius:4px;font-size:13px;line-height:1.55;color:var(--text);">'
        f'{summary}</div>'
    )

    st.markdown(
        f'<div class="nv-card">'
        f'<div class="nv-card-title">Pathology read · VLM</div>'
        f'<div class="nv-card-headline">{subtype_label}</div>'
        f'<div style="display:flex;gap:18px;margin-top:6px;font-size:13px;color:var(--text-dim);">'
        f'<div><b style="color:var(--text);">{t_stage}</b> · T-stage <span style="font-size:11px;opacity:0.7;">(AJCC 8)</span></div>'
        f'<div><b style="color:var(--text);">{breslow_str}</b> · Breslow</div>'
        f'<div><b style="color:var(--text);">{conf_str}</b> · model confidence</div>'
        f'</div>'
        + summary_html
        + (f'<div class="nv-chip-row" style="margin-top:10px;">{chips}</div>' if chips else "")
        + notes_html
        + '</div>',
        unsafe_allow_html=True,
    )

    with st.expander("📄 Findings JSON", expanded=False):
        st.code(json.dumps(path, indent=2, default=str), language="json")

    if thinking or raw:
        with st.expander("🧠 Model reasoning (raw `<think>` block)", expanded=False):
            if thinking:
                st.markdown(
                    f'<div class="nv-think">{thinking}</div>',
                    unsafe_allow_html=True,
                )
            if raw and raw != thinking:
                st.caption("Full raw response:")
                st.code(raw, language="markdown")
