"""Agent layer for the melanoma copilot.

Import the orchestrator directly from its module to avoid circular imports:

    from neoantigen.agent.melanoma_orchestrator import MelanomaOrchestrator
"""

from .events import AgentEvent, EventBus, EventKind

__all__ = ["AgentEvent", "EventBus", "EventKind"]
