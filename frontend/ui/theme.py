"""Single source of truth for the NeoVax visual system.

Exports:
    COLORS         — semantic palette (HEX strings)
    CSS            — single stylesheet string injected once on page load
    inject_css()   — call once near the top of app.py
    plotly_theme() — layout dict to apply to every Plotly figure
    pill / chip / metric / empty_state — small HTML helpers returning strings
                    for st.markdown(..., unsafe_allow_html=True)

All Streamlit-specific selectors live here, isolated. Panel modules should
never reach for hardcoded hex codes — pull from COLORS or call helpers.
"""

from __future__ import annotations

import streamlit as st

COLORS = {
    "bg":         "#FAFAFA",
    "surface":    "#FFFFFF",
    "surface_2":  "#F5F5F4",
    "border":     "#E5E7EB",
    "border_st":  "#D1D5DB",
    "text":       "#0F172A",
    "text_dim":   "#64748B",
    "text_faint": "#94A3B8",
    "accent":     "#0F766E",
    "accent_soft":"#CCFBF1",
    "success":    "#10B981",
    "success_soft":"#D1FAE5",
    "warning":    "#F59E0B",
    "warning_soft":"#FEF3C7",
    "danger":     "#EF4444",
    "danger_soft":"#FEE2E2",
    "info":       "#3B82F6",
    "info_soft":  "#DBEAFE",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg: #FAFAFA;
  --surface: #FFFFFF;
  --surface-2: #F5F5F4;
  --border: #E5E7EB;
  --border-strong: #D1D5DB;
  --text: #0F172A;
  --text-dim: #64748B;
  --text-faint: #94A3B8;
  --accent: #0F766E;
  --accent-soft: #CCFBF1;
  --success: #10B981;
  --success-soft: #D1FAE5;
  --warning: #F59E0B;
  --warning-soft: #FEF3C7;
  --danger: #EF4444;
  --danger-soft: #FEE2E2;
  --info: #3B82F6;
  --info-soft: #DBEAFE;
  --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.04);
  --shadow-md: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
  --radius: 12px;
  --radius-sm: 6px;
}

html, body, [class*="css"], .stApp, .stMarkdown, .stCaption {
  font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
  color: var(--text);
}
.stApp { background: var(--bg); }

/* Trim Streamlit chrome */
header[data-testid="stHeader"] { background: transparent; height: 0; }
.block-container { padding-top: 1.2rem !important; padding-bottom: 5rem; max-width: 100% !important; }
#MainMenu, footer { visibility: hidden; }

/* Sidebar */
section[data-testid="stSidebar"] {
  background: var(--surface);
  border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] > div { padding-top: 0.5rem; }

/* Top bar */
.nv-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 18px; margin: -8px 0 18px 0;
  background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
}
.nv-brand { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 16px; }
.nv-brand-mark {
  width: 28px; height: 28px; border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), #0EA5A4);
  display: inline-flex; align-items: center; justify-content: center;
  color: white; font-size: 16px;
}
.nv-brand-sub { color: var(--text-dim); font-weight: 400; margin-left: 6px; }
.nv-topbar-right { display: flex; align-items: center; gap: 10px; }

/* Status pill */
.nv-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 500;
  background: var(--surface-2); color: var(--text-dim);
  border: 1px solid var(--border);
}
.nv-pill-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--text-faint); }
.nv-pill--idle .nv-pill-dot { background: var(--text-faint); }
.nv-pill--running { background: var(--info-soft); color: #1E40AF; border-color: #BFDBFE; }
.nv-pill--running .nv-pill-dot {
  background: var(--info);
  animation: nv-pulse 1.4s ease-in-out infinite;
}
.nv-pill--done { background: var(--success-soft); color: #065F46; border-color: #A7F3D0; }
.nv-pill--done .nv-pill-dot { background: var(--success); }
.nv-pill--warn { background: var(--warning-soft); color: #92400E; border-color: #FDE68A; }
.nv-pill--accent { background: var(--accent-soft); color: var(--accent); border-color: #99F6E4; }
@keyframes nv-pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.5; transform: scale(1.4); } }

/* Cards */
.nv-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
  box-shadow: var(--shadow-sm);
  margin-bottom: 14px;
}
.nv-card--accent { border-left: 3px solid var(--accent); }
.nv-card--info { border-left: 3px solid var(--info); }
.nv-card-title { font-size: 12px; font-weight: 600; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
.nv-card-headline { font-size: 22px; font-weight: 600; color: var(--text); margin: 0 0 4px 0; line-height: 1.2; }

/* Metrics */
.nv-metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 14px; }
.nv-metric {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  box-shadow: var(--shadow-sm);
}
.nv-metric-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; font-weight: 500; }
.nv-metric-value { font-size: 24px; font-weight: 600; color: var(--text); margin-top: 4px; line-height: 1.1; }
.nv-metric-sub { font-size: 12px; color: var(--text-faint); margin-top: 2px; }

/* Chips */
.nv-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px; margin: 2px 4px 2px 0;
  border-radius: 6px; font-size: 12px; font-weight: 500;
  background: var(--surface-2); color: var(--text-dim);
  border: 1px solid var(--border);
}
.nv-chip--ok    { background: var(--success-soft); color: #065F46; border-color: #A7F3D0; }
.nv-chip--warn  { background: var(--warning-soft); color: #92400E; border-color: #FDE68A; }
.nv-chip--bad   { background: var(--danger-soft);  color: #991B1B; border-color: #FECACA; }
.nv-chip--info  { background: var(--info-soft);    color: #1E40AF; border-color: #BFDBFE; }
.nv-chip--accent{ background: var(--accent-soft);  color: var(--accent); border-color: #99F6E4; }
.nv-chip--curated {
  background: repeating-linear-gradient(135deg, var(--surface-2) 0 6px, var(--bg) 6px 12px);
  color: var(--text-dim);
  border: 1px dashed var(--border-strong);
}
.nv-chip-row { margin-top: 6px; line-height: 1.9; }

/* Right rail */
.nv-rail-wrap {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  min-height: 600px;
  box-shadow: var(--shadow-sm);
}
.nv-rail-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.nv-rail-title { font-size: 12px; font-weight: 600; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.06em; }
.nv-rail-step { font-size: 12px; color: var(--info); font-weight: 500; margin-bottom: 8px; }

/* Live thinking box */
.nv-think {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px; line-height: 1.55;
  color: var(--text-dim);
  background: var(--bg);
  padding: 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  border-left: 3px solid var(--info);
  white-space: pre-wrap;
  max-height: 480px; overflow-y: auto;
  margin-top: 6px;
}
.nv-think--idle { border-left-color: var(--border-strong); color: var(--text-faint); }

/* Empty state */
.nv-empty {
  text-align: center; padding: 36px 16px; color: var(--text-faint);
  border: 1px dashed var(--border-strong); border-radius: var(--radius);
  background: var(--surface);
  margin-bottom: 14px;
}
.nv-empty-icon { font-size: 28px; margin-bottom: 8px; }
.nv-empty-title { font-size: 14px; font-weight: 500; color: var(--text-dim); }
.nv-empty-sub { font-size: 12px; color: var(--text-faint); margin-top: 4px; line-height: 1.5; }

/* Section heading inside tabs / cards */
.nv-section-h { font-size: 14px; font-weight: 600; color: var(--text); margin: 4px 0 10px 0; }
.nv-section-sub { font-size: 12px; color: var(--text-dim); margin-bottom: 14px; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
  gap: 2px;
  background: var(--surface);
  padding: 4px;
  border-radius: 10px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}
.stTabs [data-baseweb="tab"] {
  height: 36px; padding: 0 16px;
  background: transparent;
  border-radius: 7px;
  color: var(--text-dim);
  font-weight: 500; font-size: 13px;
}
.stTabs [aria-selected="true"] {
  background: var(--bg) !important;
  color: var(--text) !important;
  box-shadow: var(--shadow-sm);
}

/* Buttons */
.stButton > button {
  border-radius: 8px;
  font-weight: 500;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  transition: all 0.12s ease;
}
.stButton > button:hover {
  border-color: var(--border-strong);
  background: var(--surface-2);
}
.stButton > button[kind="primary"] {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}
.stButton > button[kind="primary"]:hover {
  background: #115E59;
  border-color: #115E59;
}

/* Misc */
[data-testid="stFileUploaderDropzone"] {
  background: var(--surface-2);
  border-color: var(--border);
  border-radius: 8px;
}
.stExpander { border: 1px solid var(--border); border-radius: 8px; }
.stCodeBlock { border-radius: 8px; }
hr { border-color: var(--border) !important; }

/* Peptide hero card */
.nv-peptide {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px; box-shadow: var(--shadow-sm);
  margin-bottom: 0;
}
.nv-peptide-seq { font-family: 'JetBrains Mono', monospace; font-size: 16px; font-weight: 600; color: var(--text); }
.nv-peptide-meta { font-size: 12px; color: var(--text-dim); margin-top: 4px; }
.nv-affinity-bar {
  height: 4px; border-radius: 2px; background: var(--surface-2); margin-top: 8px; overflow: hidden;
}
.nv-affinity-fill { height: 100%; background: linear-gradient(90deg, var(--success), var(--accent)); }

/* Timeline */
.nv-timeline { padding: 0; margin: 0 0 14px 0; list-style: none; }
.nv-timeline li {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 0; font-size: 13px; color: var(--text);
}
.nv-timeline-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--success); flex-shrink: 0;
}
.nv-timeline-time { color: var(--text-faint); font-size: 11px; margin-left: auto; }

/* User chat bubble in rail */
.nv-chat-user {
  margin: 8px 0; padding: 8px 12px;
  background: var(--surface-2); border-radius: 8px;
  font-size: 13px; color: var(--text);
}
.nv-chat-user b { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .04em; }
</style>
"""


def inject_css() -> None:
    """Inject the global stylesheet. Call once near the top of app.py."""
    st.markdown(CSS, unsafe_allow_html=True)


def plotly_theme(**overrides) -> dict:
    """Return a Plotly ``layout=`` dict matching the NeoVax theme.

    Pass any plotly layout key as a keyword to override a default.
    Example: ``fig.update_layout(**theme.plotly_theme(height=380))``.
    """
    layout = dict(
        font=dict(family="Inter, system-ui, sans-serif", size=12, color=COLORS["text"]),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"]),
        yaxis=dict(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"]),
        hoverlabel=dict(bgcolor=COLORS["surface"], bordercolor=COLORS["border"], font=dict(family="Inter")),
        legend=dict(font=dict(size=11)),
    )
    layout.update(overrides)
    return layout


# ─────────────────────────────────────────────────────────────
# Small HTML helpers — return strings for st.markdown(unsafe_allow_html=True)
# ─────────────────────────────────────────────────────────────

def pill(status: str, label: str | None = None) -> str:
    """Status pill. ``status`` is one of: idle, running, done, warn, accent."""
    if label is None:
        label = {"idle": "Idle", "running": "Running", "done": "Complete"}.get(status, status.title())
    return (
        f'<span class="nv-pill nv-pill--{status}">'
        f'<span class="nv-pill-dot"></span>{label}</span>'
    )


def chip(text: str, kind: str = "") -> str:
    """Small inline chip. ``kind`` is one of: '' (neutral), ok, warn, bad, info, accent."""
    cls = f"nv-chip nv-chip--{kind}" if kind else "nv-chip"
    return f'<span class="{cls}">{text}</span>'


def metric(label: str, value: str, sub: str = "") -> str:
    """One metric tile. Wrap a list of these in <div class="nv-metric-grid">…</div>."""
    sub_html = f'<div class="nv-metric-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="nv-metric">'
        f'<div class="nv-metric-label">{label}</div>'
        f'<div class="nv-metric-value">{value}</div>'
        f'{sub_html}</div>'
    )


def metric_grid(metrics: list[str]) -> str:
    """Wrap metric() outputs in the responsive grid container."""
    return '<div class="nv-metric-grid">' + "".join(metrics) + '</div>'


def empty_state(icon: str, title: str, sub: str = "") -> str:
    """Calm empty placeholder for panels with no data yet."""
    return (
        f'<div class="nv-empty">'
        f'<div class="nv-empty-icon">{icon}</div>'
        f'<div class="nv-empty-title">{title}</div>'
        f'<div class="nv-empty-sub">{sub}</div></div>'
    )
