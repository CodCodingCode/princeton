"""Security utilities: log redaction + optional bearer-token auth.

Both pieces are purely additive to the existing request flow and opt-in via
env vars so the demo path keeps working without configuration:

  NEOVAX_LOG_REDACTION   on by default. Set to 0 to disable PII scrubbing in
                         k2.log and llm_audit.jsonl.
  NEOVAX_API_TOKEN       off by default. When set, every /api/* request
                         except /api/health must carry
                           Authorization: Bearer <token>

Neither change is a substitute for a full HIPAA compliance program; both are
defense-in-depth primitives that make the architecture HIPAA-aligned.
"""

from .auth import api_token_enabled, require_api_token
from .redact import log_redaction_enabled, redact_text, redact_value

__all__ = [
    "api_token_enabled",
    "log_redaction_enabled",
    "redact_text",
    "redact_value",
    "require_api_token",
]
