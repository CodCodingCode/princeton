"""Pattern-based PII redaction for operational logs.

Targets identifiers from the HIPAA Safe Harbor list that are plausibly regex-
catchable on free-form text: email, phone, SSN, MRN labels, dates, and long
bare digit runs. Names and free-text addresses are intentionally NOT touched
because regex false-positive rates are too high and name stripping needs
list-based or NER-based de-identification to be useful.

The goal is defense-in-depth on logs, not a de-identification substitute.

Toggle with NEOVAX_LOG_REDACTION (default: on).
"""

from __future__ import annotations

import os
import re
from typing import Any

# Patterns run top-to-bottom. Order matters only when two patterns could match
# the same substring; keep the more specific one (SSN, DOB-label) above the
# looser long-digit catch-all.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # SSN with dashes
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED-SSN]"),
    # Email
    (re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[REDACTED-EMAIL]"),
    # US phone: (555) 555-5555, 555-555-5555, 555.555.5555, +1 555 555 5555
    (re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
     "[REDACTED-PHONE]"),
    # MRN / chart / account labels plus digits
    (re.compile(
        r"\b(?:MRN|Medical\s*Record(?:\s*Number)?|Chart(?:\s*No\.?)?|Account(?:\s*No\.?)?)"
        r"[:#\s]*\d{4,}\b", re.IGNORECASE
    ), "[REDACTED-MRN]"),
    # DOB / "Date of Birth" / "Born" plus a date in any common format
    (re.compile(
        r"\b(?:DOB|Date\s*of\s*Birth|Born)[:\s]*"
        r"(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b",
        re.IGNORECASE
    ), "[REDACTED-DOB]"),
    # Bare calendar dates with a 4-digit year anchor
    (re.compile(r"\b\d{1,2}[/]\d{1,2}[/](?:19|20)\d{2}\b"), "[REDACTED-DATE]"),
    (re.compile(r"\b(?:19|20)\d{2}-\d{1,2}-\d{1,2}\b"), "[REDACTED-DATE]"),
    # Long bare digit runs (10-14). Catches most ID shapes including NPIs.
    (re.compile(r"\b\d{10,14}\b"), "[REDACTED-ID]"),
]


def log_redaction_enabled() -> bool:
    raw = os.environ.get("NEOVAX_LOG_REDACTION", "1").strip().lower()
    return raw not in {"0", "false", "no", ""}


def redact_text(s: str) -> str:
    """Return ``s`` with all known PII patterns replaced by labeled placeholders.

    No-op when NEOVAX_LOG_REDACTION is disabled.
    """
    if not s or not log_redaction_enabled():
        return s
    out = s
    for pat, repl in _PATTERNS:
        out = pat.sub(repl, out)
    return out


def redact_value(value: Any) -> Any:
    """Recursively redact strings inside dict / list / tuple containers."""
    if not log_redaction_enabled():
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_value(v) for v in value)
    return value
