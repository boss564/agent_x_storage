"""Panzergrenadier — mechanized infantry edge-clearance layer (P01–P09).

9 agents in 3 platoons:
  Leaders:     P01 Cross-Shard, P02 State-Conflict, P03 Compliance
  Subagents:   P04 Isolation, P05 Forensics, P06 Correction, P07 Reintegration
  Support:     P08 Security, P09 Reconnaissance

The main batch stays "mounted" (fast path); only complex edge cases
"dismount" into a slow, careful reconciliation path.
"""

from .base import PanzergrenadierAgent, PanzergrenadierCoordinator, DeploymentState, ClearanceResult
from .p01_cross_shard import P01CrossShardLeader
from .p02_state_conflict import P02StateConflictLeader
from .p03_compliance import P03ComplianceLeader
from .p04_isolation import P04Isolation
from .p05_forensics import P05Forensics
from .p06_correction import P06Correction
from .p07_reintegration import P07Reintegration
from .p08_security import P08Security
from .p09_reconnaissance import P09Reconnaissance

__all__ = [
    "PanzergrenadierAgent",
    "PanzergrenadierCoordinator",
    "DeploymentState",
    "ClearanceResult",
    "P01CrossShardLeader",
    "P02StateConflictLeader",
    "P03ComplianceLeader",
    "P04Isolation",
    "P05Forensics",
    "P06Correction",
    "P07Reintegration",
    "P08Security",
    "P09Reconnaissance",
]
