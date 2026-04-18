"""Tools the post-run chat agent can call.

Each tool:
  * is registered with a JSON schema in ``TOOL_SCHEMAS`` for K2's tool-call API
  * emits a ``CHAT_TOOL_*`` event before returning so the UI can render the
    side-effect (highlight a panel, re-rank a table, …)
  * returns a short string back to K2 so it can keep reasoning

Tools never mutate the underlying ``MelanomaCase`` — UI side-effects only.
"""

from __future__ import annotations

import json
from typing import Any

from ..agent.events import EventKind, emit
from ..rag import has_store as _rag_available, query_papers


# ──────────────────────────────────────────────────────────────────
# Tool schemas (OpenAI tool-call format, what K2 expects)
# ──────────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "highlight_panel",
            "description": (
                "Scroll the doctor's UI to a specific panel and optionally "
                "highlight a sub-element. Use when the doctor asks to 'show me' "
                "or 'open' a part of the case (a protein structure, a peptide, "
                "an NCCN node, the survival curve)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "panel": {
                        "type": "integer",
                        "enum": [1, 2, 3, 4],
                        "description": "1=NCCN walker, 2=molecular, 3=vaccine, 4=cohort",
                    },
                    "focus": {
                        "type": "string",
                        "description": "Optional sub-element key (gene name, peptide, node id, twin id)",
                    },
                },
                "required": ["panel"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pubmed_search",
            "description": (
                "Run a fresh PubMed semantic search over the pre-built RAG store. "
                "Use when the doctor asks for 'recent papers', 'evidence', or "
                "wants to verify a claim against literature. Returns the top "
                "matches with PMIDs and snippets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 3, "minimum": 1, "maximum": 8},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_twin",
            "description": (
                "Open a specific twin patient's full record in Panel 4. Use when "
                "the doctor asks about a particular submitter id or 'tell me more "
                "about that patient'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "submitter_id": {"type": "string", "description": "TCGA submitter id, e.g. TCGA-EE-A2GU"},
                },
                "required": ["submitter_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rerank_peptides",
            "description": (
                "Re-sort the vaccine candidate table in Panel 3 by an alternative "
                "criterion. Use when the doctor asks 'which is the longest?', "
                "'sort by gene', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "by": {
                        "type": "string",
                        "enum": ["binding", "length", "gene", "rank"],
                        "description": "binding=affinity nM ascending, length=peptide length descending, gene=alphabetical, rank=original",
                    },
                },
                "required": ["by"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_node",
            "description": (
                "Return the agent's recorded reasoning for a specific NCCN node "
                "the walker visited. Use when the doctor asks 'why did you pick X "
                "at the BRAF test step?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "NCCN node id like START, STAGE_T, BRAF_TEST, BRAF_MUT_TX, FINAL",
                    },
                },
                "required": ["node_id"],
            },
        },
    },
]


# ──────────────────────────────────────────────────────────────────
# Tool dispatch
# ──────────────────────────────────────────────────────────────────


async def execute_tool(name: str, arguments: dict, case: dict) -> str:
    """Run one tool by name. ``case`` is the slim MelanomaCase dict."""
    if name == "highlight_panel":
        return await _highlight_panel(arguments)
    if name == "pubmed_search":
        return await _pubmed_search(arguments)
    if name == "show_twin":
        return await _show_twin(arguments, case)
    if name == "rerank_peptides":
        return await _rerank_peptides(arguments, case)
    if name == "explain_node":
        return await _explain_node(arguments, case)
    return json.dumps({"error": f"unknown tool: {name}"})


async def _highlight_panel(args: dict) -> str:
    panel = int(args.get("panel", 1))
    focus = args.get("focus") or ""
    label_map = {1: "NCCN walker", 2: "molecular landscape", 3: "vaccine designer", 4: "twin cohort"}
    label = label_map.get(panel, f"Panel {panel}")
    await emit(
        EventKind.CHAT_UI_FOCUS,
        f"🎯 Highlight Panel {panel} ({label})" + (f" → {focus}" if focus else ""),
        {"panel": panel, "focus": focus},
    )
    return json.dumps({"ok": True, "panel": panel, "label": label, "focus": focus})


async def _pubmed_search(args: dict) -> str:
    query = str(args.get("query", "")).strip()
    top_k = int(args.get("top_k", 3))
    if not query:
        return json.dumps({"error": "empty query"})
    if not _rag_available():
        return json.dumps({"error": "RAG store unavailable", "query": query})
    try:
        papers = query_papers(query, top_k=top_k)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}", "query": query})
    payload = [
        {
            "pmid": p.pmid,
            "title": p.title,
            "year": p.year,
            "journal": p.journal,
            "snippet": p.snippet,
            "url": p.url,
            "relevance": p.relevance,
        }
        for p in papers
    ]
    await emit(
        EventKind.CHAT_TOOL_RESULT,
        f"📚 pubmed_search('{query[:48]}') → {len(payload)} hits",
        {"tool": "pubmed_search", "query": query, "results": payload},
    )
    return json.dumps({"query": query, "results": payload})


async def _show_twin(args: dict, case: dict) -> str:
    sid = str(args.get("submitter_id", "")).strip()
    twins = ((case.get("cohort") or {}).get("twins")) or []
    match = next((t for t in twins if t.get("submitter_id") == sid), None)
    if not match:
        return json.dumps({"error": f"twin {sid!r} not in current cohort"})
    await emit(
        EventKind.CHAT_UI_FOCUS,
        f"🧑‍🤝‍🧑 Open twin {sid}",
        {"panel": 4, "focus": sid},
    )
    return json.dumps({"twin": match})


async def _rerank_peptides(args: dict, case: dict) -> str:
    by = str(args.get("by", "binding"))
    pipeline = case.get("pipeline") or {}
    candidates = pipeline.get("candidates") or []
    if not candidates:
        return json.dumps({"error": "no candidates available"})

    def _key(c: dict):
        p = c.get("peptide") or {}
        if by == "length":
            return -int(p.get("length") or 0)
        if by == "gene":
            return ((p.get("mutation") or {}).get("gene") or "")
        if by == "rank":
            return int(c.get("rank") or 0)
        return float(p.get("score_nm") if p.get("score_nm") is not None else 1e9)

    sorted_view = sorted(candidates, key=_key)[:10]
    summary = [
        {
            "rank": c.get("rank"),
            "sequence": (c.get("peptide") or {}).get("sequence"),
            "score_nm": (c.get("peptide") or {}).get("score_nm"),
            "gene": ((c.get("peptide") or {}).get("mutation") or {}).get("gene"),
        }
        for c in sorted_view
    ]
    await emit(
        EventKind.CHAT_RERANK,
        f"🔁 Re-ranked peptides by {by}",
        {"by": by, "ordered": summary},
    )
    return json.dumps({"by": by, "top": summary})


async def _explain_node(args: dict, case: dict) -> str:
    node_id = str(args.get("node_id", "")).upper()
    path = case.get("nccn_path") or []
    step = next((s for s in path if str(s.get("node_id", "")).upper() == node_id), None)
    if not step:
        return json.dumps({
            "error": f"node {node_id!r} not in walked path",
            "available": [s.get("node_id") for s in path],
        })
    await emit(
        EventKind.CHAT_UI_FOCUS,
        f"🩺 Open NCCN node {node_id}",
        {"panel": 1, "focus": node_id},
    )
    return json.dumps({
        "node_id": step.get("node_id"),
        "node_title": step.get("node_title"),
        "chosen_option": step.get("chosen_option"),
        "reasoning": step.get("reasoning"),
        "evidence": step.get("evidence"),
        "citations": [c.get("title") + f" (PMID {c.get('pmid')})" for c in (step.get("citations") or [])],
    })
