#!/usr/bin/env python3
"""R_ij response layer — v0.1 threshold / v0.2 sensitivity; Layer A/B/C.

docs/R_IJ_SCREEN_v0_DRAFT.md
No type-pair matrix. γ_ij acquired from ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from kanten_ledger import screen_ledger_component

EPS = 1e-9
EdgeKey = Tuple[str, str]

FORMULA_V01 = "threshold_gamma_v01"
FORMULA_V02 = "sensitivity_gamma_v02"
# Default for imports that expect a single constant: latest candidate
FORMULA_VERSION = FORMULA_V02


@dataclass(frozen=True)
class AgentP:
    """Intrinsic P_i = (g, theta, sat) → a_i=g, b-scale=theta. Index 1..9."""

    index: int
    g: float
    theta: float
    sat: float

    @property
    def a(self) -> float:
        return float(self.g)

    def b(self, sigma_s: float) -> float:
        """Working point in S-units (agent-intrinsic × σ)."""
        return float(self.theta) * float(sigma_s)

    def as_dict(self) -> Dict[str, float]:
        return {
            "P_index": self.index,
            "g": round(self.g, 6),
            "theta": round(self.theta, 6),
            "sat": round(self.sat, 6),
            "a": round(self.a, 6),
        }


def derive_p_bank() -> Dict[int, AgentP]:
    from agents_b2g.gas.gas_profiles import AGENT_GAS_PROFILES

    keys = [f"A{i}" for i in range(1, 10)]
    fees = [AGENT_GAS_PROFILES[k].fee_per_action for k in keys]
    mean_fee = sum(fees) / len(fees)
    bank: Dict[int, AgentP] = {}
    for i, key in enumerate(keys, start=1):
        fee = AGENT_GAS_PROFILES[key].fee_per_action
        init = AGENT_GAS_PROFILES[key].initial_balance
        g = float(fee / (mean_fee + EPS))
        theta = float(1.0 / (1.0 + init / 10.0))
        sat = float(min(1.0, init / 100.0))
        bank[i] = AgentP(index=i, g=g, theta=theta, sat=sat)
    return bank


def assign_p(
    agent_ids: Sequence[str], bank: Optional[Mapping[int, AgentP]] = None
) -> Dict[str, AgentP]:
    bank = dict(bank or derive_p_bank())
    out: Dict[str, AgentP] = {}
    for n, aid in enumerate(sorted(agent_ids)):
        out[aid] = bank[(n % 9) + 1]
    return out


def gamma_from_ledger(ell: float, sigma: float) -> float:
    return float(max(0.0, float(ell) / (float(sigma) + EPS)))


def r_ij(
    s: float,
    gamma_ij: float,
    p: AgentP,
    sigma_s: float,
    *,
    formula: str,
) -> float:
    """Edge response under chosen formula."""
    gij = float(gamma_ij)
    if formula == FORMULA_V01:
        # v0.1: constant offset — ΔR = θ·|γ_j−γ_k|, independent of S
        f_s = float(p.g) * (float(s) / (float(sigma_s) + EPS))
        return float(f_s - float(p.theta) * (1.0 + gij))
    if formula == FORMULA_V02:
        # v0.2: sensitivity — R = a_i(1+γ)·(S−b_i); ΔR ∝ |S−b|
        return float(p.a * (1.0 + gij) * (float(s) - p.b(sigma_s)))
    raise ValueError(f"unknown formula: {formula}")


def _sender_mean_ell(snap: Dict[EdgeKey, float], sender: str) -> float:
    vals = [v for (i, _j), v in snap.items() if i == sender]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _median(xs: List[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else 0.5 * (s[m - 1] + s[m])


def build_r_hist(
    *,
    ell_hist: List[Dict[EdgeKey, float]],
    sigma: float,
    p_of: Mapping[str, AgentP],
    formula: str,
) -> List[Dict[EdgeKey, float]]:
    out: List[Dict[EdgeKey, float]] = []
    for snap in ell_hist:
        r_snap: Dict[EdgeKey, float] = {}
        for (i, j), ell in snap.items():
            p = p_of.get(i)
            if p is None:
                continue
            s_i = _sender_mean_ell(snap, i)
            gij = gamma_from_ledger(ell, sigma)
            r_snap[(i, j)] = r_ij(s_i, gij, p, sigma, formula=formula)
        out.append(r_snap)
    return out


def screen_r_layer_a(
    *,
    sticky_map_b: Mapping[Tuple[str, str], str],
    sticky_map_c: Mapping[Tuple[str, str], str],
    r_hist: List[Dict[EdgeKey, float]],
    sigma: float,
    formula: str,
) -> Dict[str, Any]:
    raw = screen_ledger_component(
        sticky_map_b=sticky_map_b,
        sticky_map_c=sticky_map_c,
        edge_hist=r_hist,
        component="R_ij",
        mae_min=0.05,
        rho_max=0.90,
    )
    mae_raw = float(raw.get("mae") or 0.0)
    mae_norm = mae_raw / (float(sigma) + EPS)
    flag_s = bool(mae_norm >= 0.05)
    flag_g = bool(raw.get("flags", {}).get("S_G"))
    n_corr = int(raw.get("n_corr") or 0)
    if n_corr < 14:
        flag_g = False
    return {
        "layer": "A",
        "formula": formula,
        "mae_raw": round(mae_raw, 6),
        "mae_norm": round(mae_norm, 6),
        "median_abs_rho": raw.get("median_abs_rho"),
        "n_corr": n_corr,
        "flags": {"S_S_norm": flag_s, "S_G": flag_g},
        "pass": bool(flag_s and flag_g),
        "screen_raw": raw,
    }


def _partner_gammas(
    sid: str,
    entries: List[Tuple[Tuple[str, str], str]],
    sticky_map_c: Mapping[Tuple[str, str], str],
    ell_hist: List[Dict[EdgeKey, float]],
    sigma: float,
) -> List[float]:
    gammas: List[float] = []
    for sk_role, pid in entries:
        ek = (sid, pid)
        ell_med = _median([float(snap.get(ek, 0.0)) for snap in ell_hist])
        gammas.append(gamma_from_ledger(ell_med, sigma))
        pid_c = sticky_map_c.get(sk_role)
        if pid_c is not None:
            ek_c = (sid, pid_c)
            ell_c = _median([float(snap.get(ek_c, 0.0)) for snap in ell_hist])
            gammas.append(gamma_from_ledger(ell_c, sigma))
    return gammas


def _delta_r_at_s(
    s: float,
    gammas: List[float],
    p: AgentP,
    sigma: float,
    formula: str,
) -> float:
    if len(gammas) < 2:
        return 0.0
    rs = [r_ij(s, g, p, sigma, formula=formula) for g in gammas]
    pairs = [
        abs(rs[a] - rs[b])
        for a in range(len(rs))
        for b in range(a + 1, len(rs))
    ]
    return sum(pairs) / len(pairs) if pairs else 0.0


def identical_s_probe(
    *,
    sticky_map_b: Mapping[Tuple[str, str], str],
    sticky_map_c: Mapping[Tuple[str, str], str],
    ell_hist: List[Dict[EdgeKey, float]],
    sigma: float,
    p_of: Mapping[str, AgentP],
    formula: str,
    delta_min: float = 0.05,
) -> Dict[str, Any]:
    """Layer B: fixed S_i (sender median), vary γ via B vs π(M)."""
    if not ell_hist or not sticky_map_b:
        return {
            "layer": "B",
            "formula": formula,
            "pass": False,
            "mean_delta_r": 0.0,
            "error": "empty",
        }

    by_sender: Dict[str, List[Tuple[Tuple[str, str], str]]] = {}
    for sk_role, pid in sticky_map_b.items():
        sid = sk_role[0].split(":")[0]
        by_sender.setdefault(sid, []).append((sk_role, pid))

    per_agent: List[Dict[str, Any]] = []
    deltas: List[float] = []

    for sid, entries in by_sender.items():
        p = p_of.get(sid)
        if p is None:
            continue
        s_i = _median([_sender_mean_ell(snap, sid) for snap in ell_hist])
        gammas = _partner_gammas(sid, entries, sticky_map_c, ell_hist, sigma)
        d = _delta_r_at_s(s_i, gammas, p, sigma, formula)
        deltas.append(d)
        per_agent.append({
            "agent_id": sid,
            "P_index": p.index,
            "S_i": round(s_i, 6),
            "n_gamma": len(gammas),
            "gamma_span": round(max(gammas) - min(gammas), 6) if gammas else 0.0,
            "delta_r": round(d, 6),
        })

    mean_d = sum(deltas) / len(deltas) if deltas else 0.0
    return {
        "layer": "B",
        "formula": formula,
        "mean_delta_r": round(mean_d, 6),
        "delta_min": delta_min,
        "n_agents": len(per_agent),
        "pass": bool(mean_d >= delta_min),
        "per_agent": per_agent,
    }


def signal_slope_probe(
    *,
    sticky_map_b: Mapping[Tuple[str, str], str],
    sticky_map_c: Mapping[Tuple[str, str], str],
    ell_hist: List[Dict[EdgeKey, float]],
    sigma: float,
    p_of: Mapping[str, AgentP],
    formula: str,
    delta_min: float = 0.05,
) -> Dict[str, Any]:
    """Layer C: does ΔR vary with signal level? |ΔR(S1)−ΔR(S2)| ≥ δ.

    v0.1 analytic: ΔR = θ·|Δγ| → independent of S → diff ≡ 0.
    v0.2 analytic: ΔR ∝ |S−b| → diff ≠ 0 when |S1−b| ≠ |S2−b|.
    """
    if not ell_hist or not sticky_map_b:
        return {
            "layer": "C",
            "formula": formula,
            "pass": False,
            "mean_abs_diff": 0.0,
            "error": "empty",
        }

    by_sender: Dict[str, List[Tuple[Tuple[str, str], str]]] = {}
    for sk_role, pid in sticky_map_b.items():
        sid = sk_role[0].split(":")[0]
        by_sender.setdefault(sid, []).append((sk_role, pid))

    # Global S levels from all sender-mean series (fixed before per-agent ΔR)
    all_s = [
        _sender_mean_ell(snap, sid)
        for snap in ell_hist
        for sid in by_sender
    ]
    if len(all_s) < 2:
        return {
            "layer": "C",
            "formula": formula,
            "pass": False,
            "mean_abs_diff": 0.0,
            "error": "too_few_S",
        }
    s_sorted = sorted(all_s)
    s1 = s_sorted[len(s_sorted) // 4]  # Q1
    s2 = s_sorted[(3 * len(s_sorted)) // 4]  # Q3

    per_agent: List[Dict[str, Any]] = []
    diffs: List[float] = []

    for sid, entries in by_sender.items():
        p = p_of.get(sid)
        if p is None:
            continue
        gammas = _partner_gammas(sid, entries, sticky_map_c, ell_hist, sigma)
        d1 = _delta_r_at_s(s1, gammas, p, sigma, formula)
        d2 = _delta_r_at_s(s2, gammas, p, sigma, formula)
        diff = abs(d1 - d2)
        diffs.append(diff)
        per_agent.append({
            "agent_id": sid,
            "P_index": p.index,
            "delta_r_S1": round(d1, 6),
            "delta_r_S2": round(d2, 6),
            "abs_diff": round(diff, 6),
            "b_i": round(p.b(sigma), 6),
        })

    mean_diff = sum(diffs) / len(diffs) if diffs else 0.0
    return {
        "layer": "C",
        "formula": formula,
        "S1": round(s1, 6),
        "S2": round(s2, 6),
        "mean_abs_diff": round(mean_diff, 6),
        "delta_min": delta_min,
        "n_agents": len(per_agent),
        "pass": bool(mean_diff >= delta_min),
        "per_agent": per_agent,
        "note": (
            "v0.1: expect ≈0 (offset); v0.2: expect >0 (sensitivity)"
        ),
    }


def verdict(
    layer_a: Mapping[str, Any],
    layer_b: Mapping[str, Any],
    layer_c: Mapping[str, Any],
) -> Dict[str, Any]:
    a_ok = bool(layer_a.get("pass"))
    b_ok = bool(layer_b.get("pass"))
    c_ok = bool(layer_c.get("pass"))
    if a_ok and b_ok and c_ok:
        label = "RESPONSE_HETEROGENEOUS"
    elif a_ok and b_ok and not c_ok:
        label = "OFFSET_ONLY"  # v0.1 fingerprint: B yes, C no
    elif not a_ok:
        label = "RESPONSE_SCREEN_FAIL"
    else:
        label = "TRANSFER_PARTNERBLIND"
    return {
        "label": label,
        "formula": layer_a.get("formula") or layer_b.get("formula"),
        "layer_a_pass": a_ok,
        "layer_b_pass": b_ok,
        "layer_c_pass": c_ok,
        "pre_reg_allowed": bool(a_ok and b_ok and c_ok),
    }
