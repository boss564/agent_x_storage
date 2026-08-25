#!/usr/bin/env python3
"""Honor signal for KOPPLUNG_REPUTATION_v1 (BINDEND Pre-Reg).

s(H) = min(1, H / H_cap), H_cap = 200.
Events → HonorCalculator.calc per role (§2.1.1).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from agents_b2g.valhalla.valhalla import HonorCalculator

H_CAP = 200.0


def s_honor(h: float, h_cap: float = H_CAP) -> float:
    """Pre-Reg §2.3: s(H) = min(1.0, H / H_cap)."""
    if h_cap <= 0:
        return 0.0
    return min(1.0, max(0.0, float(h)) / float(h_cap))


def evaluate_i1(
    *,
    agent_ids: list[str],
    honor_hist: list[list[float]],
    map_b: dict,
    map_c: dict,
    changed: dict[str, bool],
    run_seed: int,
    warmup: int,
    cycles: int,
    sigma_min: float = 10.0,
    mae_min: float = 0.05,
    upd_min: float = 0.40,
    rho_max: float = 0.90,
) -> Dict[str, Any]:
    """Binary I1 criteria V/S/U/G — Pre-Reg KOPPLUNG_REPUTATION_v1 §4.2."""
    import math

    n = len(agent_ids)
    if not honor_hist:
        return {
            "verdict": "SIGNAL_BLIND",
            "i1_pass": False,
            "error": "empty honor_hist",
            "run_seed": run_seed,
        }

    # I1-V: σ(H) at last measure tick
    last = [float(x) for x in honor_hist[-1]]
    mean_h = sum(last) / n
    var = sum((x - mean_h) ** 2 for x in last) / n  # population σ as Stichproben over N=27
    # Pre-Reg: Stichproben-σ — use sample std (ddof=1) when n>1
    if n > 1:
        var_s = sum((x - mean_h) ** 2 for x in last) / (n - 1)
        sigma = math.sqrt(var_s)
    else:
        sigma = 0.0
    i1_v = bool(sigma >= sigma_min)

    # I1-S: mean over senders of MAE_t(s(H_pB), s(H_pC))
    id_to_idx = {aid: i for i, aid in enumerate(agent_ids)}
    maes: list[float] = []
    for key, pid_b in (map_b or {}).items():
        pid_c = (map_c or {}).get(key)
        if pid_c is None:
            continue
        ib = id_to_idx.get(pid_b)
        ic = id_to_idx.get(pid_c)
        if ib is None or ic is None:
            continue
        errs = []
        for row in honor_hist:
            sb = s_honor(row[ib])
            sc = s_honor(row[ic])
            errs.append(abs(sb - sc))
        if errs:
            maes.append(sum(errs) / len(errs))
    mean_mae = sum(maes) / len(maes) if maes else 0.0
    i1_s = bool(mean_mae >= mae_min)

    # I1-U: fraction with ≥1 honor change in measure window
    n_changed = sum(1 for aid in agent_ids if changed.get(aid, False))
    frac_u = n_changed / n if n else 0.0
    i1_u = bool(frac_u >= upd_min)

    # I1-G: median |corr_t(H_i, H̄)| ≤ rho_max
    T = len(honor_hist)
    hbar = [sum(honor_hist[t][i] for i in range(n)) / n for t in range(T)]
    corrs: list[float] = []
    for i in range(n):
        xs = [honor_hist[t][i] for t in range(T)]
        ys = hbar
        mx = sum(xs) / T
        my = sum(ys) / T
        num = sum((xs[t] - mx) * (ys[t] - my) for t in range(T))
        dx = math.sqrt(sum((xs[t] - mx) ** 2 for t in range(T)))
        dy = math.sqrt(sum((ys[t] - my) ** 2 for t in range(T)))
        if dx < 1e-12 or dy < 1e-12:
            continue  # constant — excluded from median pool
        corrs.append(abs(num / (dx * dy)))
    if len(corrs) < 14:
        i1_g = False
        median_rho = None
    else:
        sc = sorted(corrs)
        mid = len(sc) // 2
        median_rho = sc[mid] if len(sc) % 2 else 0.5 * (sc[mid - 1] + sc[mid])
        i1_g = bool(median_rho <= rho_max)

    i1_pass = bool(i1_v and i1_s and i1_u and i1_g)
    return {
        "pre_reg": "docs/KOPPLUNG_REPUTATION_v1_PREREG.md",
        "status": "BINDEND",
        "check": "I1",
        "run_seed": run_seed,
        "warmup": warmup,
        "cycles": cycles,
        "kappa": 0.0,
        "criteria": {
            "I1-V": {"value": round(sigma, 6), "threshold": sigma_min, "pass": i1_v},
            "I1-S": {
                "value": round(mean_mae, 6),
                "threshold": mae_min,
                "pass": i1_s,
                "n_edges": len(maes),
            },
            "I1-U": {
                "value": round(frac_u, 6),
                "threshold": upd_min,
                "pass": i1_u,
                "n_changed": n_changed,
            },
            "I1-G": {
                "value": None if median_rho is None else round(median_rho, 6),
                "threshold": rho_max,
                "pass": i1_g,
                "n_corr": len(corrs),
            },
        },
        "i1_pass": i1_pass,
        "verdict": "I1_PASS" if i1_pass else "SIGNAL_BLIND",
        "honor_final": {aid: last[i] for i, aid in enumerate(agent_ids)},
    }


class SwarmHonorBook:
    """Per-agent cumulative honor for the 27-agent ABM."""

    def __init__(self, agent_ids: list[str]):
        self._h: Dict[str, float] = {aid: 0.0 for aid in agent_ids}
        self._changed: Dict[str, bool] = {aid: False for aid in agent_ids}

    def get(self, agent_id: Optional[str]) -> float:
        if agent_id is None:
            return 0.0
        return float(self._h.get(agent_id, 0.0))

    def s(self, agent_id: Optional[str]) -> float:
        return s_honor(self.get(agent_id))

    def apply_event(
        self,
        agent_id: str,
        *,
        z3_sat: bool,
        tps: float = 1.0,
        unsat_attempts: int = 0,
    ) -> float:
        score = float(
            HonorCalculator.calc(z3_sat, float(tps), int(unsat_attempts))["score"]
        )
        prev = self._h.get(agent_id, 0.0)
        nxt = max(0.0, prev + score)
        if nxt != prev:
            self._changed[agent_id] = True
        self._h[agent_id] = nxt
        return score

    def snapshot_counters(self, agent: Any) -> Dict[str, Any]:
        return {
            "milestone_count": int(getattr(agent, "milestone_count", 0) or 0),
            "checks_passed": int(getattr(agent, "checks_passed", 0) or 0),
            "checks_failed": int(getattr(agent, "checks_failed", 0) or 0),
            "settlements": int(getattr(agent, "settlements", 0) or 0),
        }

    def update_after_tick(self, agent: Any, before: Dict[str, Any], role: str) -> None:
        """Apply §2.1.1 events from counter deltas + provider decision."""
        aid = str(agent.id)
        if role == "provider":
            d_ms = int(getattr(agent, "milestone_count", 0) or 0) - int(
                before["milestone_count"]
            )
            if d_ms <= 0:
                return
            decision = "idle"
            log = getattr(agent, "decision_log", None) or []
            if log:
                decision = str(log[-1].get("decision", "idle"))
            inflated = decision == "report_inflated"
            for _ in range(d_ms):
                if inflated:
                    self.apply_event(aid, z3_sat=False, tps=1.0, unsat_attempts=1)
                else:
                    self.apply_event(aid, z3_sat=True, tps=1.0, unsat_attempts=0)
            return
        if role == "evaluator":
            dp = int(getattr(agent, "checks_passed", 0) or 0) - int(
                before["checks_passed"]
            )
            df = int(getattr(agent, "checks_failed", 0) or 0) - int(
                before["checks_failed"]
            )
            for _ in range(max(0, dp)):
                self.apply_event(aid, z3_sat=True, tps=1.0, unsat_attempts=0)
            for _ in range(max(0, df)):
                self.apply_event(aid, z3_sat=False, tps=1.0, unsat_attempts=1)
            return
        if role == "economic":
            ds = int(getattr(agent, "settlements", 0) or 0) - int(before["settlements"])
            for _ in range(max(0, ds)):
                self.apply_event(aid, z3_sat=True, tps=1.0, unsat_attempts=0)

    def as_dict(self) -> Dict[str, float]:
        return dict(self._h)

    def any_change(self, agent_id: str) -> bool:
        return bool(self._changed.get(agent_id, False))

    def reset_change_flags(self) -> None:
        for k in self._changed:
            self._changed[k] = False
