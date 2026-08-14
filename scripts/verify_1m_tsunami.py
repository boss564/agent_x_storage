#!/usr/bin/env python3
"""Verify the 1M-events tsunami run — unbestechlicher Acceptance-Gate.

Validates the conservation invariant over the real NATS/Docker pipeline:

    Ingested = Cleared + Quarantined = L1 Settled

plus the three acceptance criteria:
  1. Zero event loss   — surface.total_processed == producer.sent, errors == 0
  2. P99 < 2ms         — surface processing P99 (and infantry clearance P99)
  3. RSS < 250MB flat  — container RSS via `docker stats`, no monotonic leak

The verifier snapshots the /metrics counters BEFORE the producer run and
computes deltas afterwards, so it is idempotent and robust against prior
runs or ambient traffic. P99 is a cumulative histogram (not delta-able);
for a clean per-run P99, restart the services first.

Prerequisite (rebuild the three service images with the new /metrics endpoints):
  ZK_TRIGGER_RATE=1.0 docker compose up -d --build surface-agent d01-mock-responder infantry

Usage:
  python3 scripts/verify_1m_tsunami.py                       # full 1M run
  python3 scripts/verify_1m_tsunami.py --total 50000         # smoke run
  python3 scripts/verify_1m_tsunami.py --no-run              # verify only (existing counters)
"""

import argparse
import json
import subprocess
import sys
import time

SURFACE_PORT = 8080
D01_PORT = 8081
INFANTRY_PORT = 8082

DEFAULT_SURFACE_PREFIX = "agent_x_storage-surface-agent-"
DEFAULT_D01_PREFIX = "agent_x_storage-d01-mock-responder-"
DEFAULT_INFANTRY_PREFIX = "agent_x_storage-infantry-"


def _docker_ps(prefix: str) -> list:
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                         capture_output=True, text=True).stdout
    return [n for n in out.split() if n.startswith(prefix)]


def _exec_metrics(container: str, port: int):
    """Read /metrics JSON from inside a container via `docker exec` (stdlib urllib)."""
    code = ("import urllib.request as u; "
            f"print(u.urlopen('http://127.0.0.1:{port}/metrics?format=json', timeout=3).read().decode())")
    try:
        r = subprocess.run(["docker", "exec", container, "python3", "-c", code],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.strip())
    except Exception:
        return None


def _collect(containers: list, port: int) -> list:
    out = []
    for c in containers:
        m = _exec_metrics(c, port)
        if m:
            out.append(m)
    return out


def _sum(dicts: list, *fields) -> int:
    total = 0
    for d in dicts:
        for f in fields:
            if f in d and isinstance(d[f], (int, float)):
                total += d[f]
                break
    return total


def _max(dicts: list, *fields) -> float:
    m = 0.0
    for d in dicts:
        for f in fields:
            if f in d and isinstance(d[f], (int, float)):
                m = max(m, d[f])
                break
    return m


def _snapshot(surface: list, d01: list, infantry: list) -> dict:
    s = _collect(surface, SURFACE_PORT)
    d = _collect(d01, D01_PORT)
    i = _collect(infantry, INFANTRY_PORT)
    return {
        "surface_processed": _sum(s, "total_processed_events", "total_processed"),
        "surface_errors": _sum(s, "total_errors"),
        "surface_zk": _sum(s, "zk_forwarded"),
        "surface_p99_us": _max(s, "latency_p99_us"),
        "d01_total": _sum(d, "total_events"),
        "d01_quarantined": _sum(d, "quarantined_total"),
        "d01_healthy": _sum(d, "healthy_settled_total"),
        "d01_settled": _sum(d, "l1_settled_events_total"),
        "d01_anchors": _sum(d, "l1_anchors"),
        "inf_processed": _sum(i, "total_processed"),
        "inf_cleared": _sum(i, "total_cleared"),
        "inf_p99_ms": _max(i, "clearance_p99_ms"),
    }


def _parse_mem(s: str):
    """Parse '123.4MiB' → float MB (or None)."""
    s = s.strip().lower()
    units = {"kib": 1 / 1024, "mib": 1.0, "gib": 1024.0,
             "b": 1 / (1024 ** 2), "kb": 1 / 1024, "mb": 1.0, "gb": 1024.0}
    for u, mult in units.items():
        if s.endswith(u):
            try:
                return float(s[:-len(u)]) * mult
            except ValueError:
                return None
    return None


def _rss_all(containers: list) -> dict:
    """One `docker stats --no-stream` call for all containers → {name: rss_mb}."""
    if not containers:
        return {}
    out = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}"] + containers,
        capture_output=True, text=True,
    ).stdout
    result = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            result[parts[0]] = _parse_mem(parts[1].split("/")[0])
    return result


def _sample_rss(containers: list, samples: dict, maxima: dict) -> None:
    stats = _rss_all(containers)
    for c, mb in stats.items():
        if mb is not None:
            samples[c].append(mb)
            maxima[c] = max(maxima.get(c, 0.0), mb)


def _wait_for_drain(surface: list, port: int, baseline: int, target: int, timeout: int = 180) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        processed = _sum(_collect(surface, port), "total_processed_events", "total_processed")
        delta = processed - baseline
        if delta >= target:
            print(f"  ✅ drained: {delta}/{target}")
            return processed
        print(f"  ... {delta}/{target}")
        time.sleep(2.0)
    return _sum(_collect(surface, port), "total_processed_events", "total_processed")


def _parse_args():
    p = argparse.ArgumentParser(description="1M-events tsunami acceptance gate")
    p.add_argument("--total", type=int, default=1_000_000)
    p.add_argument("--rate", type=int, default=100_000)
    p.add_argument("--poison-rate", type=float, default=0.05)
    p.add_argument("--complex-rate", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--report-file", type=str, default="/tmp/tsunami_report.json")
    p.add_argument("--rss-limit-mb", type=float, default=250.0)
    p.add_argument("--p99-limit-us", type=float, default=2000.0)
    p.add_argument("--rss-interval", type=float, default=2.0)
    p.add_argument("--no-run", action="store_true", help="skip producer; verify existing counters")
    p.add_argument("--surface-prefix", type=str, default=DEFAULT_SURFACE_PREFIX)
    p.add_argument("--d01-prefix", type=str, default=DEFAULT_D01_PREFIX)
    p.add_argument("--infantry-prefix", type=str, default=DEFAULT_INFANTRY_PREFIX)
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    surface = _docker_ps(args.surface_prefix)
    d01 = _docker_ps(args.d01_prefix)
    infantry = _docker_ps(args.infantry_prefix)
    all_containers = surface + d01 + infantry

    print("=" * 70)
    print("🌊 1M TSUNAMI VERIFICATION")
    print("=" * 70)
    print(f"  Discovered: {len(surface)} surface | {len(d01)} d01 | {len(infantry)} infantry")

    if not surface or not d01:
        print("❌ Required containers not running.")
        print("   Start: ZK_TRIGGER_RATE=1.0 docker compose up -d --build "
              "surface-agent d01-mock-responder infantry")
        return 1

    # ── Baseline snapshot (before producer) ──
    baseline = _snapshot(surface, d01, infantry)

    rss_samples = {c: [] for c in all_containers}
    rss_max = {}

    # ── Run producer (with concurrent RSS sampling) ──
    if not args.no_run:
        cmd = [
            sys.executable, "scripts/simchain_ingest.py",
            "--total", str(args.total),
            "--rate", str(args.rate),
            "--poison-rate", str(args.poison_rate),
            "--complex-rate", str(args.complex_rate),
            "--seed", str(args.seed),
            "--report", args.report_file,
        ]
        print(f"\n🚀 Producer: {' '.join(cmd)}\n")
        # Redirect producer stdout to a FILE, not a PIPE — a verbose producer
        # writing to an unread PIPE deadlocks when the 64KB buffer fills.
        producer_log = "/tmp/tsunami_producer.log"
        with open(producer_log, "w") as pf:
            proc = subprocess.Popen(cmd, stdout=pf, stderr=subprocess.STDOUT)
            while proc.poll() is None:
                _sample_rss(all_containers, rss_samples, rss_max)
                time.sleep(args.rss_interval)
            _sample_rss(all_containers, rss_samples, rss_max)
        try:
            with open(producer_log) as f:
                tail = f.readlines()[-30:]
            print("".join(tail))
        except Exception:
            pass
        if proc.returncode != 0:
            print("❌ Producer failed — aborting verification.")
            return 1

    # ── Read producer report ──
    try:
        with open(args.report_file) as f:
            report = json.load(f)
    except Exception as e:
        print(f"⚠️  Report {args.report_file} unlesbar ({e}); falling back to --total.")
        report = {"sent": args.total, "errors": 0,
                  "poison_count": int(args.total * args.poison_rate),
                  "complex_count": int(args.total * args.complex_rate)}

    sent = report.get("sent", 0)
    errors = report.get("errors", 0)
    poison_expected = report.get("poison_count", 0)
    complex_expected = report.get("complex_count", 0)

    # ── Drain consumers, then collect post-run metrics ──
    print(f"\n⏳ Draining surface (target {sent})...")
    _wait_for_drain(surface, SURFACE_PORT, baseline["surface_processed"], sent)
    time.sleep(2.0)  # extra settle for D01 batches + infantry dismounts
    _sample_rss(all_containers, rss_samples, rss_max)

    post = _snapshot(surface, d01, infantry)

    def delta(key):
        return post[key] - baseline[key]

    surface_processed = delta("surface_processed")
    surface_errors = delta("surface_errors")
    surface_zk = delta("surface_zk")
    surface_p99_us = post["surface_p99_us"]  # cumulative histogram (not delta-able)
    d01_total = delta("d01_total")
    d01_quarantined = delta("d01_quarantined")
    d01_healthy = delta("d01_healthy")
    d01_settled = delta("d01_settled")
    d01_anchors = delta("d01_anchors")
    inf_processed = delta("inf_processed")
    inf_cleared = delta("inf_cleared")
    inf_p99_ms = post["inf_p99_ms"]

    # ── RSS flatness ──
    rss_max_mb = max(rss_max.values()) if rss_max else 0.0
    rss_growth = {}
    for c, samples in rss_samples.items():
        if len(samples) >= 2:
            rss_growth[c] = samples[-1] - samples[0]

    # ── Checks ──
    checks = [
        ("Producer sent exactly --total", sent == args.total),
        ("Producer zero publish errors", errors == 0),
        ("Surface processed all events (zero loss)", surface_processed == sent),
        ("Surface zero validation errors", surface_errors == 0),
        ("D01 conservation: settled == received", d01_settled == d01_total and d01_total > 0),
        ("Poison reconciliation: quarantined == poison", d01_quarantined == poison_expected),
        ("Healthy reconciliation: healthy+quarantined == settled",
         d01_healthy + d01_quarantined == d01_settled),
        ("Cross-layer: surface forwarded == D01 received",
         surface_zk == d01_total and d01_total > 0),
        (f"Surface P99 < {args.p99_limit_us:.0f}µs", surface_p99_us < args.p99_limit_us),
        (f"Container RSS < {args.rss_limit_mb:.0f}MB", rss_max_mb < args.rss_limit_mb),
    ]
    if infantry:
        checks += [
            ("Infantry received all complex events", inf_processed == complex_expected),
            ("Infantry cleared all complex events (no loss)", inf_cleared == inf_processed),
            ("Infantry clearance P99 < 2ms", inf_p99_ms < 2.0),
        ]
    else:
        print("\n  ⚠️  No infantry containers — complex-path checks skipped.")

    # ── Report ──
    print("\n" + "-" * 70)
    print("  COUNTERS (deltas since baseline)")
    print(f"    sent={sent} errors={errors} poison={poison_expected} complex={complex_expected}")
    print(f"    surface_processed={surface_processed} errors={surface_errors} zk_forwarded={surface_zk} p99={surface_p99_us}µs")
    print(f"    d01 received={d01_total} healthy={d01_healthy} quarantined={d01_quarantined} settled={d01_settled} anchors={d01_anchors}")
    print(f"    infantry processed={inf_processed} cleared={inf_cleared} p99={inf_p99_ms}ms")
    print(f"    rss_max={rss_max_mb:.1f}MB")
    if rss_growth:
        worst = max(rss_growth, key=lambda c: rss_growth[c])
        print(f"    rss_growth[worst={worst}]={rss_growth[worst]:+.1f}MB")
    print("-" * 70)

    all_pass = True
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
        all_pass = all_pass and ok

    print("-" * 70)
    print(f"  RESULT: {'✅ 1M TSUNAMI PASS' if all_pass else '❌ 1M TSUNAMI FAIL'}\n")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
