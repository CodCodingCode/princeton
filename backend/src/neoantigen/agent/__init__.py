"""Agent orchestration layer for the neoantigen pipeline.

Wraps the existing pipeline + external integrations (Google, PANDORA, email) as
Claude Agent SDK tools, and streams progress events to a Streamlit UI.
"""

from .events import AgentEvent, EventBus, EventKind
from .orchestrator import CaseOrchestrator, build_case_file, run_case

__all__ = ["AgentEvent", "EventBus", "EventKind", "CaseOrchestrator", "build_case_file", "run_case"]
