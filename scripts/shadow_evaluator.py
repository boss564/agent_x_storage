#!/usr/bin/env python3
"""Strang B.1 shadow evaluator — read-only replay, append shadow_eval.jsonl.

Pre-Reg: docs/SHADOW_EVALUATOR_PREREG.md · G1: SHADOW_EVAL_G1_PASS=1 for /data/* reads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.paper_edge_sample import (  # noqa: E402
    DEFAULT_FREEZE_K,
    DEFAULT_HOLD_CLEAN_MAX_DELTA_S,
    edge_sample_eligible,
    load_edges,
)
from prototypes.raas_paper_trading.position_sizing.config import resolve_gamma  # noqa: E402

SCHEMA, SCOPE = "shadow_evaluator_v0", "DEFENSIVE_CAUSAL_GROUNDING"
VALID_DECISIONS = frozenset(
    {"BLOCKED", "INSUFFICIENT_HISTORY", "LIMIT_OK", "LIMIT_EXCEEDED", "Z3_BLOCKED", "KELLY_SIGN_UNCERTAIN"}
)
N_MIN, W_MIN, L_MIN, B_BOOT, K_CAP, RISK = 50, 5, 5, 1000, 0.25, 0.02
CAPITAL, ENTRY_NOTIONAL = 1000.0, 100.0


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.strip().replace("Z", "+00:00")).timestamp()


def _hash_obj(o: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def _hash_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _jsonl(p: Path) -> List[Dict[str, Any]]:
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _guard_g1(paths: Sequence[Path]) -> None:
    if os.environ.get("SHADOW_EVAL_G1_PASS") == "1":
        return
    for p in paths:
        if str(p.resolve()).startswith("/data/"):
            raise SystemExit("G1: live exports blocked until NEWS_24H gate PASS")


def _profit_frac(edge: Dict[str, Any], notional: float = ENTRY_NOTIONAL) -> Optional[float]:
    try:
        pnl, n = float(edge.get("pnl_eur") or 0), float(notional)
    except (TypeError, ValueError):
        return None
    return pnl / n if n > 0 else None


def _stats(rets: Sequence[float]) -> Dict[str, Any]:
    n = len(rets)
    w, l = [r for r in rets if r > 0], [r for r in rets if r < 0]
    nw, nl = len(w), len(l)
    if n < N_MIN or nw < W_MIN or nl < L_MIN:
        return {"ok": False, "n": n, "nw": nw, "nl": nl}
    p, b = nw / n, (sum(w) / nw) / abs(sum(l) / nl)
    return {"ok": b > 0, "n": n, "nw": nw, "nl": nl, "p": p, "b": b}


def _kelly(p: float, b: float) -> float:
    return (p * b - (1 - p)) / b


def _bootstrap(rets: Sequence[float], gamma: float, seed: int = 42) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    st = _stats(rets)
    if not st["ok"]:
        return None, None, None, None
    unc = max(0.0, gamma * _kelly(st["p"], st["b"]))
    pt = min(unc, K_CAP)
    rng, draws, n = random.Random(seed), [], len(rets)
    for _ in range(B_BOOT):
        s = _stats([rets[rng.randrange(n)] for _ in range(n)])
        if s["ok"]:
            draws.append(min(max(0.0, gamma * _kelly(s["p"], s["b"])), K_CAP))
    if not draws:
        return pt, unc, None, None
    draws.sort()
    return pt, unc, draws[int(0.05 * len(draws))], draws[int(0.95 * len(draws))]


def check_z3(
    news: Sequence[Dict[str, Any]],
    gap: Sequence[Dict[str, Any]],
    as_of: str,
    *,
    require_markers: bool = False,
    daily_frac: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    t0 = _ts(as_of)
    if require_markers and (not any(r.get("kind") == "run_marker" for r in news) or not any(r.get("kind") == "run_marker" for r in gap)):
        return True, "PHASE_SOURCE_STALE"
    for r in news:
        if r.get("kind") == "run_marker" or not r.get("ts") or _ts(str(r["ts"])) < t0 - 86400:
            continue
        if float(r.get("impact_score", 0)) >= 0.70 and float(r.get("sentiment", r.get("sentiment_score", 0))) < -0.30:
            return True, "NEWS_DEFENSIVE"
    for r in gap:
        if r.get("kind") == "run_marker" or not r.get("ts") or _ts(str(r["ts"])) < t0 - 3600:
            continue
        if r.get("signal_type") == "COVERAGE_GAP":
            return True, "GAP_DEFENSIVE"
    if daily_frac is not None and daily_frac <= -0.02:
        return True, "DAILY_LOSS"
    return False, None


def _charter(edge: Dict[str, Any], regime_flag: int, gamma: float, src: str) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ts": datetime.now(timezone.utc).isoformat(),
        "edge_id": edge.get("edge_id"),
        "regime_flag": int(regime_flag),
        "gamma": gamma,
        "gamma_source": src,
        "execution_mode": "post_only_limit",
        "source_hashes": {"edge": _hash_obj(edge)},
        "diagnostic_only": True,
        "live_execution": False,
        "order_send": False,
        "not_investment_advice": True,
        "scope": SCOPE,
        "kelly_sign_uncertain": False,
    }


def _null_kelly(row: Dict[str, Any], decision: str, rets: Sequence[float], **extra: Any) -> Dict[str, Any]:
    row.update(
        {
            "shadow_gate_decision": decision,
            "stats_count": len(rets),
            "n_wins": sum(1 for r in rets if r > 0),
            "n_losses": sum(1 for r in rets if r < 0),
            "p": None,
            "b": None,
            "kelly_fraction_gamma_uncapped": None,
            "kelly_fraction_computed": None,
            "kelly_fraction_p05": None,
            "kelly_fraction_p95": None,
            "shadow_pnl_eur": None,
            "shadow_would_size": None,
            **extra,
        }
    )
    return row


def evaluate_edge(
    edge: Dict[str, Any],
    *,
    regime_flag: int,
    classified_regime: Optional[str] = None,
    returns: Sequence[float] = (),
    news_rows: Optional[Sequence[Dict[str, Any]]] = None,
    gap_rows: Optional[Sequence[Dict[str, Any]]] = None,
    require_phase_markers: bool = False,
    daily_pnl_fraction: Optional[float] = None,
) -> Dict[str, Any]:
    gamma, gsrc = resolve_gamma(classified_regime)
    row = _charter(edge, regime_flag, gamma, gsrc)
    as_of = str(edge.get("exit_tick_ts") or edge.get("ts") or row["ts"])
    z3, zr = check_z3(news_rows or [], gap_rows or [], as_of, require_markers=require_phase_markers, daily_frac=daily_pnl_fraction)
    if z3:
        return _null_kelly(row, "Z3_BLOCKED", returns, z3_gate_reason=zr, z3_blocked=True, phase_gate=zr)
    if regime_flag < 1:
        return _null_kelly(row, "BLOCKED", returns)
    st = _stats(returns)
    if not st["ok"]:
        return _null_kelly(row, "INSUFFICIENT_HISTORY", returns, stats_count=st["n"], n_wins=st["nw"], n_losses=st["nl"])
    pt, unc, p05, p95 = _bootstrap(returns, gamma)
    would = (pt or 0) * CAPITAL
    pf = _profit_frac(edge)
    spnl = float(pf * ENTRY_NOTIONAL) if pf is not None else None
    if p05 is None or p05 <= 0:
        row.update(
            {
                "shadow_gate_decision": "KELLY_SIGN_UNCERTAIN",
                "kelly_sign_uncertain": True,
                "stats_count": st["n"],
                "n_wins": st["nw"],
                "n_losses": st["nl"],
                "p": round(st["p"], 6),
                "b": round(st["b"], 6),
                "kelly_fraction_gamma_uncapped": round(unc, 6) if unc else None,
                "kelly_fraction_computed": round(pt, 6) if pt else None,
                "kelly_fraction_p05": round(p05, 6) if p05 is not None else None,
                "kelly_fraction_p95": round(p95, 6) if p95 is not None else None,
                "bootstrap_B": B_BOOT,
                "shadow_pnl_eur": spnl,
                "shadow_would_size": would,
            }
        )
        return row
    dec = "LIMIT_OK" if would <= CAPITAL * RISK else "LIMIT_EXCEEDED"
    row.update(
        {
            "shadow_gate_decision": dec,
            "stats_count": st["n"],
            "n_wins": st["nw"],
            "n_losses": st["nl"],
            "p": round(st["p"], 6),
            "b": round(st["b"], 6),
            "kelly_fraction_gamma_uncapped": round(unc, 6),
            "kelly_fraction_computed": round(pt, 6),
            "kelly_fraction_p05": round(p05, 6),
            "kelly_fraction_p95": round(p95, 6) if p95 else None,
            "bootstrap_B": B_BOOT,
            "shadow_pnl_eur": spnl,
            "shadow_would_size": would,
        }
    )
    return row


class ShadowEvalWriter:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prev = "0" * 64

    def append(self, row: Dict[str, Any]) -> Dict[str, Any]:
        if row.get("order_send") or row.get("live_execution"):
            raise RuntimeError("charter violation")
        if row.get("shadow_gate_decision") not in VALID_DECISIONS:
            raise RuntimeError("invalid shadow_gate_decision")
        out = {**row, "prev_hash": self._prev}
        digest = hashlib.sha256((self._prev + json.dumps(out, sort_keys=True, default=str)).encode()).hexdigest()
        out["hash"] = digest
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(out, default=str) + "\n")
        self._prev = digest
        return out


def eligible_returns(edges: Sequence[Dict[str, Any]], idx: int, *, freeze_k: int, max_delta: float) -> List[float]:
    out: List[float] = []
    for e in edges[:idx]:
        if edge_sample_eligible(e, freeze_k=freeze_k, max_delta_s=max_delta)[0]:
            pf = _profit_frac(e)
            if pf is not None:
                out.append(pf)
    return out[-N_MIN:] if len(out) > N_MIN else out


def run_once(
    *,
    edges_path: Path,
    out_path: Path,
    news_path: Path,
    gap_path: Path,
    regime_flag: int = 0,
    classified_regime: Optional[str] = None,
    freeze_k: int = DEFAULT_FREEZE_K,
    max_delta: float = DEFAULT_HOLD_CLEAN_MAX_DELTA_S,
    require_phase_markers: bool = False,
) -> Dict[str, Any]:
    _guard_g1([edges_path, news_path, gap_path])
    edges = load_edges(edges_path)
    if not edges:
        raise SystemExit("no edges")
    idx = len(edges) - 1
    row = evaluate_edge(
        edges[idx],
        regime_flag=regime_flag,
        classified_regime=classified_regime,
        returns=eligible_returns(edges, idx, freeze_k=freeze_k, max_delta=max_delta),
        news_rows=_jsonl(news_path),
        gap_rows=_jsonl(gap_path),
        require_phase_markers=require_phase_markers,
    )
    return ShadowEvalWriter(out_path).append(row)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--edges", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("data/audit/shadow_eval.jsonl"))
    p.add_argument("--news", type=Path, default=Path("data/phase_signals/news_sentiment.jsonl"))
    p.add_argument("--gap", type=Path, default=Path("data/phase_signals/price_gap.jsonl"))
    p.add_argument("--regime-flag", type=int, default=0)
    p.add_argument("--classified-regime", default=None)
    args = p.parse_args()
    if not args.once:
        p.error("--once required")
    print(json.dumps(run_once(edges_path=args.edges, out_path=args.out, news_path=args.news, gap_path=args.gap,
                             regime_flag=args.regime_flag, classified_regime=args.classified_regime), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
