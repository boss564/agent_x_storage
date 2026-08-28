# Regime Swarm — Infrastructure Gates (A0 / A2.5)

Monitoring-only privileged sub-agents that veto the A3–A8 drift pipeline when tick or transport integrity fails. Charter: `DEFENSIVE_CAUSAL_GROUNDING`, `live_execution=false`.

## Purpose

| Gate | Agent ID | Role |
|------|----------|------|
| Core sanity | **A0** | Last WORM tick → `GateInput` → `evaluate_gate()` (price, spread, flash move) |
| Transport boundary | **A2.5** | Latency budget, optional frame checksum, sequence gaps |

Both adapters call `services/fail_closed_gate/gate_core.py` — **no duplicated gate rules**.

## Mapping: Chaos strand vs production

| Chaos (P6-Trading) | Production swarm | Notes |
|--------------------|------------------|-------|
| G1 offline harness | A0 (core sanity) | Same `evaluate_gate()` kernel |
| G2 HTTP harness | A2.5 (transport) | Latency → `latency_spike` (CHAOS-02 pattern) |
| CHAOS-03 flash | A0 flash mapping | `exec_risk` / `cascade_risk` elevation |

Audit field names use `g0_core_sanity` and `g25_transport_boundary` to avoid confusion with Chaos G1/G2 labels.

## Fail-closed expectation

1. A2 ingest completes.
2. A0 runs on the last `mark_price` (reference = previous tick in the same WORM).
3. A2.5 runs when `transport_meta` is present on the latest SIGNAL row (or derived from `m7_latency_ms` / `seq_num`).
4. On any infrastructure fault: `status=INFRASTRUCTURE_BLOCKED`, `drift_summary=NOT_COMPUTED`, A5–A8 **not** executed, `order_send` remains false.
5. `evaluate_gate()` always returns `BLOCKED` for monitoring (`human_gate_open=false`). Infrastructure **pass** means reasons contain only `HUMAN_GATE_CLOSED` (no `INFRA_BLOCK_REASONS`).

## Audit schema (A9 extension)

```json
{
  "status": "INFRASTRUCTURE_BLOCKED",
  "infrastructure": {
    "g0_core_sanity": "PASSED | A0_BLOCKED: …",
    "g25_transport_boundary": "PASSED | SKIPPED (…) | A25_BLOCKED: …",
    "infrastructure_healthy": false
  },
  "drift_summary": "NOT_COMPUTED"
}
```

Complete cycles add the same `infrastructure` block with `infrastructure_healthy: true`.

## ConfigMap / environment

Helm `values.yaml`:

```yaml
infrastructureGates:
  enabled: true
  G0_MAX_PRICE_CHANGE_PCT: 20
  G0_MAX_SPREAD_PCT: 5
  G25_MAX_LATENCY_MS: 500
```

Rendered env (via `charts/regime-swarm/templates/configmap.yaml`):

| Key | Default |
|-----|---------|
| `SWARM_INFRA_GATES_ENABLED` | `true` |
| `SWARM_G0_MAX_PRICE_CHANGE_PCT` | `20` |
| `SWARM_G0_MAX_SPREAD_PCT` | `5` |
| `SWARM_G25_MAX_LATENCY_MS` | `500` |

Legacy aliases `G0_*` / `G25_*` / `INFRA_GATES_ENABLED` are also read by `InfraGatesConfig.from_env()`.

## Tests

```bash
PYTHONPATH=. python3 scripts/test_infrastructure_gates.py
# INFRASTRUCTURE_GATES_PASS
```

WORM fixture: 69 stable ticks + −50% flash on the last tick → A0 blocks; optional `m7_latency_ms: 600` on last SIGNAL → A2.5 blocks (M7 path).

## Code layout

```
prototypes/raas_paper_trading/regime_swarm/gates/
├── core_sanity_adapter.py   # A0
├── transport_boundary.py    # A2.5
├── config.py
└── common.py                # INFRA_BLOCK_REASONS, InfraGateResult
```

Orchestrator hook: `RegimeSwarmOrchestrator._run_infrastructure_gates()` before A3 in `run_cycle()`.
