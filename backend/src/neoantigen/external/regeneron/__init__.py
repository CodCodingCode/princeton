"""Registry of Regeneron-sponsored oncology trials - one ``.py`` per trial.

Each ``nct<id>.py`` module in this package exports a module-level ``TRIAL``
constant bound to a ``TrialRule`` instance. This ``__init__`` globs the
directory, imports every trial module, and exposes the union as
``REGENERON_TRIALS: dict[str, TrialRule]``.

Regenerate the per-trial files with ``scripts/scrape_regeneron_trials.py``.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from ..regeneron_rules import TrialRule


def _load() -> dict[str, TrialRule]:
    here = Path(__file__).parent
    out: dict[str, TrialRule] = {}
    for p in sorted(here.glob("nct*.py")):
        module = import_module(f".{p.stem}", __package__)
        trial = getattr(module, "TRIAL", None)
        if isinstance(trial, TrialRule):
            out[trial.nct_id] = trial
    return out


REGENERON_TRIALS: dict[str, TrialRule] = _load()


__all__ = ["REGENERON_TRIALS"]
