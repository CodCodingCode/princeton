"""Tools the patient-facing chat agent can call.

Each tool:
  * is registered with a JSON schema in ``TOOL_SCHEMAS`` for K2's tool-call API
  * emits a ``CHAT_*`` event so the UI can react (scroll, highlight, open pane)
  * returns a short JSON string so K2 can keep reasoning

Tools never mutate the underlying ``PatientCase`` — UI side-effects only.
"""

from __future__ import annotations

import json

from ..agent.events import EventKind, emit
from ..rag import has_store as _rag_available, query_papers


TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "highlight_section",
            "description": (
                "Scroll the patient's dashboard to a specific section. Use when "
                "the user asks to 'show me' or 'open' a pane."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": ["pathology", "railway", "trials", "map", "report"],
                    },
                    "focus": {
                        "type": "string",
                        "description": "Optional sub-element key (node id, NCT id, ...)",
                    },
                },
                "required": ["section"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pubmed_search",
            "description": (
                "Run a fresh PubMed semantic search over the pre-built RAG store. "
                "Use when the user asks for 'recent papers', 'evidence', or wants to "
                "verify a claim against literature."
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
            "name": "explain_node",
            "description": (
                "Return the agent's recorded reasoning for a specific NCCN node on "
                "the railway. Use when the user asks 'why did you pick X at node Y?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                },
                "required": ["node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_branch",
            "description": (
                "Explain why a specific sibling option was NOT chosen at a decision "
                "node. Use when the user asks 'what about the other branch' or "
                "'why not option X?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "option_label": {
                        "type": "string",
                        "description": "Label of the sibling option the user is asking about",
                    },
                },
                "required": ["node_id", "option_label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_trial",
            "description": (
                "Focus the trials panel + map on one NCT. Use when the user asks "
                "about a specific clinical trial or 'where is this trial running?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nct_id": {"type": "string"},
                },
                "required": ["nct_id"],
            },
        },
    },
]


async def execute_tool(name: str, arguments: dict, case: dict) -> str:
    if name == "highlight_section":
        return await _highlight_section(arguments)
    if name == "pubmed_search":
        return await _pubmed_search(arguments)
    if name == "explain_node":
        return await _explain_node(arguments, case)
    if name == "explain_branch":
        return await _explain_branch(arguments, case)
    if name == "show_trial":
        return await _show_trial(arguments, case)
    return json.dumps({"error": f"unknown tool: {name}"})


async def _highlight_section(args: dict) -> str:
    section = str(args.get("section", "railway"))
    focus = args.get("focus") or ""
    await emit(
        EventKind.CHAT_UI_FOCUS,
        f"Focus {section}" + (f" → {focus}" if focus else ""),
        {"section": section, "focus": focus},
    )
    return json.dumps({"ok": True, "section": section, "focus": focus})


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
        f"pubmed_search({query[:48]!r}) → {len(payload)} hits",
        {"tool": "pubmed_search", "query": query, "results": payload},
    )
    return json.dumps({"query": query, "results": payload})


def _find_step(case: dict, node_id: str) -> dict | None:
    node_id_upper = node_id.upper()
    railway = case.get("railway") or {}
    for step in railway.get("steps") or []:
        if str(step.get("node_id", "")).upper() == node_id_upper:
            return step
    return None


async def _explain_node(args: dict, case: dict) -> str:
    node_id = str(args.get("node_id", "")).strip()
    step = _find_step(case, node_id)
    if not step:
        available = [
            s.get("node_id") for s in (case.get("railway") or {}).get("steps") or []
        ]
        return json.dumps({
            "error": f"node {node_id!r} not on railway",
            "available": available,
        })
    await emit(
        EventKind.CHAT_UI_FOCUS,
        f"Open NCCN node {step.get('node_id')}",
        {"section": "railway", "focus": step.get("node_id")},
    )
    return json.dumps({
        "node_id": step.get("node_id"),
        "title": step.get("title"),
        "chosen_option": step.get("chosen_option_label"),
        "rationale": step.get("chosen_rationale"),
        "reasoning": step.get("reasoning"),
        "evidence": step.get("evidence"),
        "citations": [
            f"{c.get('title')} (PMID {c.get('pmid')})"
            for c in step.get("citations") or []
        ],
    })


async def _explain_branch(args: dict, case: dict) -> str:
    node_id = str(args.get("node_id", "")).strip()
    option_label = str(args.get("option_label", "")).strip()
    step = _find_step(case, node_id)
    if not step:
        return json.dumps({"error": f"node {node_id!r} not on railway"})
    alternatives = step.get("alternatives") or []
    match = next(
        (
            a for a in alternatives
            if option_label.lower() in str(a.get("option_label", "")).lower()
            or str(a.get("option_label", "")).lower() in option_label.lower()
        ),
        None,
    )
    if not match:
        return json.dumps({
            "error": f"no sibling option matching {option_label!r} at {node_id}",
            "available": [a.get("option_label") for a in alternatives],
        })
    await emit(
        EventKind.CHAT_UI_FOCUS,
        f"Branch {node_id} / {match.get('option_label')}",
        {"section": "railway", "focus": node_id},
    )
    return json.dumps({
        "node_id": node_id,
        "option_label": match.get("option_label"),
        "option_description": match.get("option_description"),
        "reason_not_chosen": match.get("reason_not_chosen"),
    })


async def _show_trial(args: dict, case: dict) -> str:
    nct_id = str(args.get("nct_id", "")).strip().upper()
    matches = case.get("trial_matches") or []
    match = next((m for m in matches if str(m.get("nct_id", "")).upper() == nct_id), None)
    if not match:
        return json.dumps({
            "error": f"{nct_id} not in matched trials",
            "available": [m.get("nct_id") for m in matches],
        })
    sites = [s for s in (case.get("trial_sites") or []) if str(s.get("nct_id", "")).upper() == nct_id]
    await emit(
        EventKind.CHAT_UI_FOCUS,
        f"Focus trial {nct_id}",
        {"section": "trials", "focus": nct_id},
    )
    return json.dumps({
        "nct_id": match.get("nct_id"),
        "title": match.get("title"),
        "status": match.get("status"),
        "passing": match.get("passing_criteria"),
        "failing": match.get("failing_criteria"),
        "unknown": match.get("unknown_criteria"),
        "sites": [
            {
                "facility": s.get("facility"),
                "city": s.get("city"),
                "state": s.get("state"),
                "lat": s.get("lat"),
                "lng": s.get("lng"),
            }
            for s in sites
        ],
        "url": match.get("url"),
    })
