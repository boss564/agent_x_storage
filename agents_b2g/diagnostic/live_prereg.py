"""Load bindende Wave 38 Live thresholds from WAVE38_LIVE_PREREG.md."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from agents_b2g.diagnostic.config import CANDIDATE_IDS, DiagnosticConfig


class LivePreRegNotBoundError(FileNotFoundError):
    """Raised when live pre-reg is missing or not marked bindend."""


@dataclass(frozen=True)
class Wave38Thresholds:
    """Operative Schwellen — unabhängig von Bridge-Pre-Reg-Konstanten."""

    eps_inert: float = 0.001
    tau_cleansing: float = 0.05
    rho_collapse: float = 0.50
    occ_sat: float = 0.90
    alpha_perm: float = 0.05
    fdr_q: float = 0.05
    p_sign_min: float = 0.95
    rho_spearman_min: float = 0.90
    k_folds: int = 9
    n_unstable_folds_max: int = 1
    tau_fn: float = 0.10
    tau_fp: float = 0.15
    n_perm_shifts: int = 100
    seed_default: int = 20260822
    candidate_ids: tuple[str, ...] = CANDIDATE_IDS
    min_distinct_tertile_bins: int = 2

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "EPS_INERT": self.eps_inert,
            "TAU_CLEANSING": self.tau_cleansing,
            "RHO_COLLAPSE": self.rho_collapse,
            "OCC_SAT": self.occ_sat,
            "ALPHA_PERM": self.alpha_perm,
            "FDR_Q": self.fdr_q,
            "P_SIGN_MIN": self.p_sign_min,
            "RHO_SPEARMAN_MIN": self.rho_spearman_min,
            "K_FOLDS": self.k_folds,
            "N_UNSTABLE_FOLDS_MAX": self.n_unstable_folds_max,
            "TAU_FN": self.tau_fn,
            "TAU_FP": self.tau_fp,
            "N_PERM_SHIFTS": self.n_perm_shifts,
            "SEED_DEFAULT": self.seed_default,
        }


_THRESHOLD_ROW = re.compile(
    r"^\|\s*`([A-Z_0-9]+)`\s*\|\s*([0-9.]+)\s*\|",
    re.MULTILINE,
)


def load_wave38_thresholds(path: Path | None = None) -> Wave38Thresholds:
    """Parse §3 table from live pre-reg; fall back to frozen defaults."""
    pre_reg_path = path or DiagnosticConfig.LIVE_PRE_REG
    if not pre_reg_path.is_file():
        raise LivePreRegNotBoundError(f"Missing live pre-reg: {pre_reg_path}")

    text = pre_reg_path.read_text(encoding="utf-8")
    if "**bindend**" not in text.lower() and "bindend" not in text.lower():
        raise LivePreRegNotBoundError(f"Live pre-reg not marked bindend: {pre_reg_path}")

    overrides: dict[str, float | int] = {}
    _INT_KEYS = {
        "SEED_DEFAULT",
        "N_PERM_SHIFTS",
        "K_FOLDS",
        "N_UNSTABLE_FOLDS_MAX",
    }
    for match in _THRESHOLD_ROW.finditer(text):
        key, raw = match.group(1), match.group(2)
        if key in _INT_KEYS:
            overrides[key] = int(float(raw))
        else:
            overrides[key] = float(raw)

    base = Wave38Thresholds()
    return Wave38Thresholds(
        eps_inert=float(overrides.get("EPS_INERT", base.eps_inert)),
        tau_cleansing=float(overrides.get("TAU_CLEANSING", base.tau_cleansing)),
        rho_collapse=float(overrides.get("RHO_COLLAPSE", base.rho_collapse)),
        occ_sat=float(overrides.get("OCC_SAT", base.occ_sat)),
        alpha_perm=float(overrides.get("ALPHA_PERM", base.alpha_perm)),
        fdr_q=float(overrides.get("FDR_Q", base.fdr_q)),
        p_sign_min=float(overrides.get("P_SIGN_MIN", base.p_sign_min)),
        rho_spearman_min=float(overrides.get("RHO_SPEARMAN_MIN", base.rho_spearman_min)),
        k_folds=int(overrides.get("K_FOLDS", base.k_folds)),
        n_unstable_folds_max=int(
            overrides.get("N_UNSTABLE_FOLDS_MAX", base.n_unstable_folds_max)
        ),
        tau_fn=float(overrides.get("TAU_FN", base.tau_fn)),
        tau_fp=float(overrides.get("TAU_FP", base.tau_fp)),
        n_perm_shifts=int(overrides.get("N_PERM_SHIFTS", base.n_perm_shifts)),
        seed_default=int(overrides.get("SEED_DEFAULT", base.seed_default)),
    )


def live_pre_reg_hash(path: Path | None = None) -> str:
    pre_reg_path = path or DiagnosticConfig.LIVE_PRE_REG
    if not pre_reg_path.is_file():
        return ""
    return hashlib.sha3_256(pre_reg_path.read_bytes()).hexdigest()[:32]
