"""Frozen Bridge Diagnostic pre-reg constants (Wave 38).

Do not edit after 2026-08-22 without a new pre-reg.
See docs/BRIDGE_DIAGNOSTIC_PREREG.md
"""

from __future__ import annotations

import os
from pathlib import Path

# Pre-reg §7
BRIDGE_DIAGNOSTIC_SEED = 20260822
N_SURROGATES = 1000
N_PERM_SHIFTS = 100
FDR_Q = 0.05

# Pre-reg §3.1 — ablation roles
EPS_INERT = 0.001
TAU_CLEANSING = 0.05
RHO_COLLAPSE = 0.50
OCC_SAT = 0.90

# Pre-reg §3.2 — permutation
ALPHA_PERM = 0.05

# Pre-reg §3.3 — k-fold (sign-based; see Leserhinweise §6)
P_SIGN_MIN = 0.95
N_BREAK_FOLDS_MAX = 1
EVENT_DENSITY_RATIO = 2.0
RPC_GAP_RATE = 0.10

# Pre-reg §5.2 — ex-post
TAU_FN = 0.10
TAU_FP = 0.15
TAU_RPC_GAP = 0.20

PRE_REG_PATH = "docs/BRIDGE_DIAGNOSTIC_PREREG.md"
LIVE_PRE_REG_PATH = "docs/WAVE38_LIVE_PREREG.md"
LESERHINWEISE_PATH = "docs/BRIDGE_DIAGNOSTIC_LESERHINWEISE.md"
SPEC_PATH = "docs/BRIDGE_DIAGNOSTIC_SPEC.md"
WAVE38_SPEC_PATH = "docs/WAVE38_DIAGNOSTIC_SPEC.md"

V3_ERGEBNIS_DEFAULT = "bridge_stufe_a_v3_ergebnis.json"
V3_INTEGRITY_GATE_DEFAULT = "bridge_stufe_a_v3_integrity_gate.json"
V3_COVERAGE_GATE_DEFAULT = "bridge_stufe_a_v3_coverage_gate.json"

CANDIDATE_IDS: tuple[str, ...] = (
    "chainlink",
    "intent_relayers",
    "liquidations",
    "stablecoin_mint_burn",
    "mev_cluster",
)

PIPELINE_STEPS: tuple[str, ...] = (
    "gate",
    "ablation",
    "permutation",
    "kfold",
    "onchain_fetch",
    "attribution_matrix",
    "error_classification",
    "threshold_tuning",
    "report",
    "verdict",
)


class DiagnosticConfig:
    """Runtime paths — env-overridable, no hardcoded tenant roots in agents."""

    DATA_ROOT: Path = Path(os.getenv("DIAGNOSTIC_DATA_ROOT", "archive_b2g/diagnostic"))
    LOG_DIR: Path = Path(os.getenv("DIAGNOSTIC_LOG_DIR", "logs"))
    PRE_REG: Path = Path(os.getenv("DIAGNOSTIC_PRE_REG", PRE_REG_PATH))
    LIVE_PRE_REG: Path = Path(os.getenv("WAVE38_LIVE_PRE_REG", LIVE_PRE_REG_PATH))
    PROJECT_ROOT: Path = Path(
        os.getenv("AGENT_X_PROJECT_ROOT", Path(__file__).resolve().parents[2])
    )
    MAX_RETRIES: int = int(os.getenv("WAVE38_MAX_RETRIES", "3"))
    RETRY_BACKOFF_BASE_S: float = float(os.getenv("WAVE38_RETRY_BACKOFF_S", "0.5"))

    @classmethod
    def user_root(cls, user_id: str) -> Path:
        return cls.DATA_ROOT / user_id / "diagnostic"

    @classmethod
    def wave38_live_root(cls, user_id: str) -> Path:
        return cls.DATA_ROOT / user_id / "wave38" / "live"

    @classmethod
    def wave38_reference_root(cls, user_id: str) -> Path:
        return cls.DATA_ROOT / user_id / "wave38" / "reference"
