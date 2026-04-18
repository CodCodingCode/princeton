"""Top bar: logo + brand on the left, model badge + status pill on the right."""

from __future__ import annotations

import os

import streamlit as st

from . import theme


def render() -> None:
    model = os.environ.get("NEOVAX_MODEL", "MBZUAI-IFM/K2-Think-v2")
    model_short = model.split("/")[-1]
    status_pill = theme.pill(st.session_state.run_status)
    st.markdown(
        f'<div class="nv-topbar">'
        f'<div class="nv-brand">'
        f'<span class="nv-brand-mark">🩺</span>'
        f'<span>NeoVax</span>'
        f'<span class="nv-brand-sub">· Melanoma Copilot</span>'
        f'</div>'
        f'<div class="nv-topbar-right">'
        f'<span class="nv-pill"><span class="nv-pill-dot"></span>model · {model_short}</span>'
        f'{status_pill}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
