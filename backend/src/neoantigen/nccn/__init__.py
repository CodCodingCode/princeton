"""NCCN melanoma decision tree + walker.

`melanoma_v2024.GRAPH` encodes the decision graph used to drive Panel 1 in the
UI. `walker.NCCNWalker` runs through it node-by-node, calling the medical model
for each branching decision and emitting events as it goes.
"""

from .melanoma_v2024 import GRAPH, NCCNNode, ROOT
from .walker import NCCNWalker, PatientState

__all__ = ["GRAPH", "NCCNNode", "ROOT", "NCCNWalker", "PatientState"]
