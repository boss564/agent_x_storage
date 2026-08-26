#!/usr/bin/env python3
"""Failover / Least-Loaded load-trap — 16s SCREEN (sandbox).

Strang: System-Resilienzen & Failover
Sandbox: prototypes/v4_failover_loadtrap/

═══════════════════════════════════════════════════════════════════
Strukturbefund (vor Metriken)
═══════════════════════════════════════════════════════════════════
Es gibt **kein** Hop-Pfad P1→P9 und keinen Totlock über „Pfad-Länge“.
Zustellung im ABM-Emergence-Pfad ist **1-von-9**:
  StickySelector + Least-Loaded (`partner_select.py`,
  `adapter_agentx.deliver`, `demo_producer_cluster`).
Fan-Out aller Evaluatoren existiert dort **nicht**.

Messbar ist nur: **Anteil der Sticky-Zuweisungen / Deliveries** pro Agent.

═══════════════════════════════════════════════════════════════════
Hypothese H1 (falsifizierbar)
═══════════════════════════════════════════════════════════════════
Bei Ausfall von Evaluator E5 (bleibt Kandidat, Blackhole/leere Inbox)
steigt sein Anteil am zugewiesenen Verkehr, sobald lebende Partner Last
aufbauen — weil ``load_of = recv_load + len(inbox)`` Untätigkeit als
Kapazität liest.

Kontrollarm H0: E5 aus der Kandidatenliste **entfernen** → Anteil → 0.

Gate: 3 Seeds · < 16 s Wandzeit.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents_b2g.emergence.partner_select import StickySelector

N_EVAL = 9
N_SENDERS = 27
ROLE = "evaluator"
WARMUP_ROUNDS = 40
POST_ROUNDS = 40
THRESHOLD = 8
STRESS_INBOX = THRESHOLD + 4  # forces hysteresis break toward idle zombie
SEEDS = (20270501, 20270502, 20270503)
VICTIM = "E5"


@dataclass
class FakeEval:
    id: str
    inbox: List[Any] = field(default_factory=list)
    mode: str = "live"  # live | zombie | removed


def _load_of(recv_load: Dict[str, int], a: FakeEval) -> int:
    return int(recv_load.get(a.id, 0) + len(a.inbox))


def _candidates(evals: List[FakeEval]) -> List[FakeEval]:
    return [e for e in evals if e.mode != "removed"]


def _deliver(
    sticky: StickySelector,
    recv_load: Dict[str, int],
    delivers: Counter,
    evals: List[FakeEval],
    sender_id: str,
    *,
    drain_live: bool,
) -> str:
    cands = _candidates(evals)
    partner = sticky.select(
        sender_id, ROLE, cands, lambda a: _load_of(recv_load, a)
    )
    if partner.mode == "zombie":
        # Blackhole: no inbox growth → looks light on len(inbox)
        pass
    else:
        partner.inbox.append({"from": sender_id})
    recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
    delivers[partner.id] += 1
    if drain_live and partner.mode == "live":
        partner.inbox.clear()
    return partner.id


def _share(delivers: Counter, agent_id: str) -> float:
    total = sum(delivers.values())
    if total <= 0:
        return 0.0
    return delivers[agent_id] / total


def run_arm(*, seed: int, kill_mode: str) -> Dict[str, Any]:
    evals = [FakeEval(id=f"E{i}") for i in range(1, N_EVAL + 1)]
    sticky = StickySelector(threshold=THRESHOLD)
    recv_load: Dict[str, int] = {e.id: 0 for e in evals}
    senders = [f"S{i:02d}" for i in range(N_SENDERS)]

    pre: Counter = Counter()
    post: Counter = Counter()

    for r in range(WARMUP_ROUNDS):
        for s in senders:
            _deliver(
                sticky,
                recv_load,
                pre,
                evals,
                f"{s}:r{r % 3}",
                drain_live=True,
            )

    share_pre = _share(pre, VICTIM)
    load_pre = {e.id: _load_of(recv_load, e) for e in evals}

    if kill_mode == "zombie":
        for e in evals:
            if e.id == VICTIM:
                e.mode = "zombie"
                e.inbox.clear()
            else:
                # Live backlog: hysterese can break toward empty zombie
                e.inbox.extend({"stress": i} for i in range(STRESS_INBOX))
    elif kill_mode == "removed":
        for e in evals:
            if e.id == VICTIM:
                e.mode = "removed"
                for k, v in list(sticky.snapshot().items()):
                    if v == VICTIM:
                        del sticky._last[k]  # noqa: SLF001 — screen only
    elif kill_mode != "none":
        raise ValueError(kill_mode)

    drain_post = kill_mode == "none"
    for r in range(POST_ROUNDS):
        for s in senders:
            try:
                _deliver(
                    sticky,
                    recv_load,
                    post,
                    evals,
                    f"{s}:post{r % 5}",
                    drain_live=drain_post,
                )
            except RuntimeError as exc:
                return {
                    "seed": seed,
                    "kill_mode": kill_mode,
                    "error": str(exc),
                    "pass": False,
                }

    share_post = _share(post, VICTIM)
    load_post = {e.id: _load_of(recv_load, e) for e in evals}

    return {
        "seed": seed,
        "kill_mode": kill_mode,
        "victim": VICTIM,
        "share_pre": round(share_pre, 6),
        "share_post": round(share_post, 6),
        "delta_share": round(share_post - share_pre, 6),
        "deliveries_pre": int(pre[VICTIM]),
        "deliveries_post": int(post[VICTIM]),
        "load_pre_victim": load_pre[VICTIM],
        "load_post_victim": load_post[VICTIM],
        "load_post": load_post,
        "n_pre": int(sum(pre.values())),
        "n_post": int(sum(post.values())),
    }


def classify_h1(zombie_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    deltas = [r["delta_share"] for r in zombie_rows]
    mean_d = sum(deltas) / len(deltas)
    n_pos = sum(1 for d in deltas if d > 0.02)
    if n_pos >= 2 and mean_d > 0.0:
        verdict = "H1_CONFIRMED"
    elif all(d <= 0.0 for d in deltas):
        verdict = "H1_FALSIFIED"
    else:
        verdict = "H1_INCONCLUSIVE"
    return {
        "verdict": verdict,
        "mean_delta_share": round(mean_d, 6),
        "n_positive": n_pos,
        "n": len(deltas),
        "deltas": deltas,
    }


def classify_h0(removed_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    posts = [r["share_post"] for r in removed_rows]
    ok = all(p < 0.01 for p in posts)
    return {
        "verdict": "H0_REMOVAL_OK" if ok else "H0_REMOVAL_FAIL",
        "share_posts": posts,
    }


def run_screen() -> Dict[str, Any]:
    t0 = time.perf_counter()
    zombie_rows: List[Dict[str, Any]] = []
    removed_rows: List[Dict[str, Any]] = []
    baseline_rows: List[Dict[str, Any]] = []

    print("Failover load-trap SCREEN")
    print("=" * 72)
    print("Structural: 1-of-9 Sticky/Least-Loaded — no P1→P9 hop path")
    print(f"Victim={VICTIM}  seeds={list(SEEDS)}  stress_inbox={STRESS_INBOX}")
    print("-" * 72)

    for seed in SEEDS:
        b = run_arm(seed=seed, kill_mode="none")
        z = run_arm(seed=seed, kill_mode="zombie")
        r = run_arm(seed=seed, kill_mode="removed")
        baseline_rows.append(b)
        zombie_rows.append(z)
        removed_rows.append(r)
        print(
            f"seed={seed}  zombie Δshare={z['delta_share']:+.4f} "
            f"(pre={z['share_pre']:.3f}→post={z['share_post']:.3f})  "
            f"removed post={r['share_post']:.4f}"
        )

    h1 = classify_h1(zombie_rows)
    h0 = classify_h0(removed_rows)
    elapsed = time.perf_counter() - t0

    payload = {
        "screen": "failover_loadtrap_v0",
        "elapsed_s": round(elapsed, 3),
        "budget_ok": elapsed < 16.0,
        "structural": {
            "hop_path_p1_p9": False,
            "totlock_via_path_length": "NOT_APPLICABLE",
            "reroute_layer": "StickySelector+Least-Loaded (1-of-9)",
            "load_of": "recv_load + len(inbox); recv_load never decays",
        },
        "hypothesis_h1": (
            "Dead E5 (zombie, still candidate, empty inbox) attracts more "
            "sticky traffic once live partners carry backlog — load_of reads "
            "idleness as capacity."
        ),
        "scenario_note": (
            f"Post-kill: live inboxes stressed to {STRESS_INBOX} + no drain; "
            "zombie blackhole keeps empty inbox."
        ),
        "h1": h1,
        "h0_control": h0,
        "baseline": baseline_rows,
        "zombie": zombie_rows,
        "removed": removed_rows,
        "verdict": h1["verdict"],
        "next": (
            "If H1_CONFIRMED: introduce completion_load (bind load to "
            "processing/Δ, class M7/M9) and/or two-choice tie-break under "
            "near-ties. If FALSIFIED: document why."
        ),
    }

    out = _HERE / "FAILOVER_PROTO.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("-" * 72)
    print(f"H1: {h1['verdict']}  mean Δshare={h1['mean_delta_share']:+.4f}")
    print(f"H0: {h0['verdict']}")
    print(f"elapsed={elapsed:.3f}s  budget_ok={payload['budget_ok']}")
    print(f"wrote {out}")
    return payload


if __name__ == "__main__":
    run_screen()
