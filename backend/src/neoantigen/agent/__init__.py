"""Agent orchestration layer for the neoantigen pipeline.

Drives the existing pipeline + external integrations (Google, PANDORA, email)
through a deterministic 8-step workflow. LLM reasoning uses PydanticAI agents
backed by K2 Think V2. Progress events stream to the Streamlit UI via EventBus.
"""

from .events import AgentEvent, EventBus, EventKind
from .orchestrator import CaseOrchestrator, build_case_file, run_case

__all__ = ["AgentEvent", "EventBus", "EventKind", "CaseOrchestrator", "build_case_file", "run_case"]
