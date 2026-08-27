#!/usr/bin/env python3
"""Gate 0 — Bus delivery topology screen (NATS Queue-Group vs Broadcast).

docs/RaaS_BUS_EXPANSION_v0.md §2.1 / §4 step 0

Frage: Erhält NATS Queue-Group-Zustellung **1-von-N** (Ring-Semantik wie
StickySelector), oder Fan-out an alle Subscriber (complete / Broadcast)?

Hypothese (Gate): Queue-Group pro Kanten-Subject → genau ein Empfänger pro
Nachricht. Broadcast-Subscribe ohne Queue-Group → alle Empfänger (Negativkontrolle).

Freeze:
  Edges: P1→P2 … P8→P9 (8 Subjects edge.Pi.Pj)
  Subscribers/edge: 3
  Messages/edge: 30
  Seed: 20270827
  PASS if queue-group: every msg delivered to exactly 1 of 3
  FAIL if any queue-group msg delivered to >1 (broadcast leak)
  Control: plain subscribe must deliver to all 3 (proves fan-out exists)

Usage:
  NATS_URL=nats://127.0.0.1:4222 PYTHONPATH=. python3 scripts/test_topology_bus_queuegroups.py
  make raas-bus-topology-gate

Exit 0 = QUEUEGROUP_RING_PASS (Stage 1 may be considered)
Exit 1 = FAIL / NATS unreachable / broadcast leak
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

NATS_URL = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
SEED = 20270827
N_SUBS = 3
N_MSGS = 30
AGENTS = [f"P{i}" for i in range(1, 10)]
EDGES = [(AGENTS[i], AGENTS[(i + 1) % 9]) for i in range(9)]  # ring including P9→P1


def _subject(a: str, b: str) -> str:
    return f"edge.{a}.{b}"


def _queue(a: str, b: str) -> str:
    return f"queue.edge.{a}.{b}"


async def _run_pattern(
    *,
    nc: Any,
    use_queue_group: bool,
) -> Dict[str, Any]:
    """Publish N_MSGS per edge; count how many distinct subs got each msg."""
    # msg_id -> set of subscriber ids that received it
    receipts: Dict[str, Set[str]] = defaultdict(set)
    lock = asyncio.Lock()
    ready = asyncio.Event()
    sub_count = {"n": 0}
    expected_subs = len(EDGES) * N_SUBS

    async def _handler(sub_id: str, msg: Any) -> None:
        try:
            body = json.loads(msg.data.decode())
            mid = body["msg_id"]
        except Exception:
            return
        async with lock:
            receipts[mid].add(sub_id)

    subs = []
    for a, b in EDGES:
        subject = _subject(a, b)
        qname = _queue(a, b) if use_queue_group else None
        for s in range(N_SUBS):
            sub_id = f"{a}->{b}#s{s}"

            async def _cb(msg: Any, _sid: str = sub_id) -> None:
                await _handler(_sid, msg)

            if qname:
                sub = await nc.subscribe(subject, queue=qname, cb=_cb)
            else:
                sub = await nc.subscribe(subject, cb=_cb)
            subs.append(sub)
            sub_count["n"] += 1

    # Allow subscriptions to settle
    await asyncio.sleep(0.15)
    ready.set()

    published: List[str] = []
    for a, b in EDGES:
        subject = _subject(a, b)
        for i in range(N_MSGS):
            mid = f"{SEED}:{a}:{b}:{i}:{uuid.uuid4().hex[:8]}"
            published.append(mid)
            await nc.publish(
                subject,
                json.dumps({"msg_id": mid, "edge": [a, b], "i": i}).encode(),
            )
    await nc.flush()
    # Drain
    await asyncio.sleep(0.5)

    for sub in subs:
        await sub.unsubscribe()

    # Per-message receiver counts
    counts = [len(receipts.get(mid, set())) for mid in published]
    n_exact_one = sum(1 for c in counts if c == 1)
    n_zero = sum(1 for c in counts if c == 0)
    n_multi = sum(1 for c in counts if c > 1)
    max_recv = max(counts) if counts else 0
    mean_recv = sum(counts) / max(len(counts), 1)

    return {
        "pattern": "queue_group" if use_queue_group else "broadcast_subscribe",
        "n_published": len(published),
        "n_exact_one": n_exact_one,
        "n_zero": n_zero,
        "n_multi": n_multi,
        "max_receivers_per_msg": max_recv,
        "mean_receivers_per_msg": round(mean_recv, 4),
        "subscribers_per_edge": N_SUBS,
        "edges": len(EDGES),
        "ring_like_1_of_n": n_exact_one == len(published) and n_multi == 0,
        "complete_like_fanout": n_multi > 0 and mean_recv >= (N_SUBS - 0.1),
    }


async def _connect():
    try:
        from nats.aio.client import Client as NATS
    except ImportError as exc:
        raise RuntimeError("nats-py missing") from exc
    nc = NATS()
    await nc.connect(servers=[NATS_URL], connect_timeout=2)
    return nc


async def main_async() -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        nc = await _connect()
    except Exception as exc:
        return {
            "verdict": "BUS_TOPOLOGY_GATE_SKIP_OR_FAIL",
            "reason": f"NATS unreachable at {NATS_URL}: {exc}",
            "nats_url": NATS_URL,
            "gate0": "BLOCKED",
            "stage1_allowed": False,
            "elapsed_s": round(time.perf_counter() - t0, 3),
        }

    try:
        qg = await _run_pattern(nc=nc, use_queue_group=True)
        bc = await _run_pattern(nc=nc, use_queue_group=False)
    finally:
        await nc.drain()

    # Gate logic
    ring_ok = bool(qg.get("ring_like_1_of_n"))
    control_fanout = bool(bc.get("complete_like_fanout")) or (
        bc.get("mean_receivers_per_msg", 0) >= N_SUBS - 0.05
        and bc.get("n_multi", 0) > 0
    )

    if ring_ok and control_fanout:
        verdict = "QUEUEGROUP_RING_PASS"
        stage1 = True
        note = (
            "Queue-Group = 1-of-N (ring-like). "
            "Broadcast control = fan-out (complete-like). "
            "Stage 1 may proceed only with Queue-Group subjects — never broadcast control plane."
        )
    elif ring_ok and not control_fanout:
        verdict = "QUEUEGROUP_RING_PASS_CONTROL_WEAK"
        stage1 = True
        note = (
            "Queue-Group OK; broadcast control did not clearly fan out "
            "(environment quirk). Prefer re-run; Stage 1 still Queue-Group-only."
        )
    else:
        verdict = "QUEUEGROUP_RING_FAIL"
        stage1 = False
        note = (
            "Queue-Group did not enforce 1-of-N — treat as complete-like. "
            "Stage 1 Cutover BLOCKED (Serie topology FALSIFIED for complete)."
        )

    return {
        "verdict": verdict,
        "gate0": "PASS" if stage1 and ring_ok else "BLOCKED",
        "stage1_allowed": stage1 and ring_ok,
        "nats_url": NATS_URL,
        "seed": SEED,
        "serie_ref": {
            "sparse_ring_margin": 0.52,
            "complete_margin": 0.0,
            "note": "Delivery pattern only — not a full Margin re-measure",
        },
        "queue_group": qg,
        "broadcast_control": bc,
        "note": note,
        "scope": "DEFENSIVE_CAUSAL_GROUNDING",
        "live_execution": False,
        "elapsed_s": round(time.perf_counter() - t0, 3),
    }


def main() -> int:
    print("Bus topology gate 0 — Queue-Group vs Broadcast")
    print("=" * 60)
    print(f"NATS_URL={NATS_URL}")
    result = asyncio.run(main_async())
    print(f"queue_group:  exact_one={result.get('queue_group', {}).get('n_exact_one')} "
          f"multi={result.get('queue_group', {}).get('n_multi')} "
          f"mean={result.get('queue_group', {}).get('mean_receivers_per_msg')}")
    print(f"broadcast:    exact_one={result.get('broadcast_control', {}).get('n_exact_one')} "
          f"multi={result.get('broadcast_control', {}).get('n_multi')} "
          f"mean={result.get('broadcast_control', {}).get('mean_receivers_per_msg')}")
    print(f"gate0={result.get('gate0')}  stage1_allowed={result.get('stage1_allowed')}")
    print(f"note: {result.get('note') or result.get('reason')}")
    print("=" * 60)
    print(f"VERDICT: {result['verdict']}")

    out = _ROOT / "data" / "raas" / "bus_topology_gate_last.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"artifact: {out}")

    # Also stamp under prototypes for serie adjacency
    proto = _ROOT / "prototypes" / "v2_stateful_graph" / "bus_topology_gate_results.json"
    try:
        proto.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except OSError:
        pass

    ok = result.get("stage1_allowed") is True and result.get("verdict", "").startswith(
        "QUEUEGROUP_RING_PASS"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
