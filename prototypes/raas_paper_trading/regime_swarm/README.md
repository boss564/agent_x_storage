# Regime Drift Schwarm (A0–A9)

Monitoring-only Regime-Drift-Erkennung auf Paper-WORMs. Charter: `DEFENSIVE_CAUSAL_GROUNDING`, `live_execution=false` — kein Order-Send, A8 nur Advisory.

## Architektur-Überblick

```text
┌─────────────────┐     JSONL-WORM      ┌──────────────────────────────┐
│ Paper-Collect   │ ──────────────────► │ RegimeSwarmOrchestrator (A1) │
│ (Runner/Feed)   │   SIGNAL.mark_price │  A0 → A2.5 → A2…A9           │
└─────────────────┘                     └──────────────┬───────────────┘
                                                       │
                       ┌───────────────────────────────┼───────────────────────────────┐
                       ▼                               ▼                               ▼
              regime_drift_audit.jsonl      regime_drift_latest.json          /metrics (Daemon)
              cooling / stuck state         webhook alerts (optional)         Prometheus scrape
```

**Produktions-Daemon:** `scripts/run_regime_swarm_daemon.py` — liest WORMs vom Volume, führt Zyklen im festen Intervall aus, schreibt Audit + Report. Kubernetes: Helm-Chart `charts/regime-swarm/` mit Lease-basiertem Leader (nur Leader mutiert Cooling/Adaptation).

## Agenten

| ID | Modul | Rolle |
|----|-------|-------|
| **A0** | `gates/core_sanity_adapter.py` | Infra-Gate: Preis/Spread/Flash-Move (`evaluate_gate()` Kernel) |
| **A2.5** | `gates/transport_boundary.py` | Infra-Gate: Latenz-Budget, Sequenz-Lücken |
| **A1** | `orchestrator.py` | Pipeline-Takt, adaptives Cooling, Stuck-Tracker |
| **A2** | `agents.py` → `DataIngestorAgent` | WORM-Ingest (`SIGNAL.mark_price`) |
| **A3** | `agents.py` → `FeatureEngineerAgent` | log/abs/down/rolling_vol, Z-Score vs. Baseline |
| **A4** | `agents.py` → `WindowManagerAgent` | Referenz/Current-Fenster, ρ-Monitor, dynamische Fenstergröße |
| **A5** | `agents.py` → `KSTestAgent` | Univariater KS (Permutation, m=4 Features) |
| **A6** | `agents.py` → `WassersteinAgent` | W₁ pro Feature |
| **A7** | `agents.py` → `DriftClassifierAgent` | RSI, `regime_flag`, Bonferroni, `DRIFT_IID_UNRELIABLE` |
| **A8** | `agents.py` → `StrategyAdapterAgent` | Soft-Adapt / Advisory (`risk_multiplier`), kein Live-Execute |
| **A9** | `agents.py` → `AuditAlertAgent` | Hash-gesichertes JSONL-Audit, Stuck-Telemetrie (>4 h) |

Schema-Version: `raas_regime_swarm_v2` (`types.SWARM_SCHEMA`). Parameter und v1→v2-Wechsel: siehe Pre-Reg.

### Gate-Pipeline (fail-closed)

1. A2 Ingest abgeschlossen.
2. **A0** prüft letzten Tick (Referenz = vorheriger Tick im selben WORM).
3. **A2.5** prüft Transport-Metadaten (`transport_meta`, `m7_latency_ms`, `seq_num`).
4. Bei Block: `status=INFRASTRUCTURE_BLOCKED`, `drift_summary=NOT_COMPUTED`, A5–A8 werden **nicht** ausgeführt.

Beide Gates nutzen `services/fail_closed_gate/gate_core.py` — keine duplizierten Regeln.

## Datenfluss WORM ↔ Daemon

| Stufe | Pfad / Artefakt | Inhalt |
|-------|-----------------|--------|
| **Schreiben** | `{data_root}/{tenant}/paper/runs/{run_id}/paper_trades.worm.jsonl` | Paper-Runner (`runner.py`) + `worm_log.py`; jede Zeile `live_execution=false` |
| **Lesen** | `regime_drift.discover_worm_files()` | Daemon/Orchestrator findet SIGNAL-Zeilen pro Symbol |
| **Zyklus** | `RegimeSwarmOrchestrator.run_cycle()` | A0→A2.5→A2…A9 pro Symbol |
| **Audit** | `logs/…/regime_drift_audit.jsonl` | A9-Zeilen inkl. `infrastructure`, `drift_summary`, `pre_reg_intervention` |
| **Report** | `regime_drift_latest.json` | Aggregiertes letztes Ergebnis |
| **State** | `regime_swarm_cooling.jsonl`, `SwarmStateStore` | Adaptives Cooling, Soft-Adapt, Leader-Persistenz |

**Live-Pfad:** `LIVE_FEED_ENABLED=true` startet `LivePaperBridge` (`paper_runner.py`) im Daemon-Prozess: Binance-WebSocket (oder Mock) → `PaperTradingRunner` → `{data_root}/worm/live/…/paper_trades.worm.jsonl`. Der Daemon liest dasselbe Verzeichnis im nächsten Zyklus. `live_execution` bleibt hardcodiert `false`. Tests: `make raas-live-feed-prometheus-smoke` (kein Netz).

## Modul-Landkarte

```text
regime_swarm/
├── orchestrator.py      # A1 — Haupt-Pipeline
├── agents.py            # A2–A9
├── adaptive.py          # Cooling, Soft-Adapt, dynamisches Fenster, Stuck-Tracker
├── types.py             # Schema, Schwellen, Dataclasses
├── state_store.py       # Persistenter Schwarm-State
├── leader.py            # K8s-Lease / Ordinal-Leader
├── leader_fsm_z3.py     # Z3-Invarianten (P6)
├── gates/               # A0, A2.5 + InfraGatesConfig
├── lease_harness.py     # Lease-Test-Harness
└── worm_fixtures.py     # Test-Fixtures
```

## Schnellstart (lokal)

```bash
# Unit + Schwarm-Smoke (A1–A9, adaptive v2)
make raas-regime-drift-smoke

# Infra-Gates A0/A2.5
make raas-regime-swarm-infra-gates
make raas-regime-swarm-infra-smoke

# Daemon (Vordergrund, WORM-Verzeichnis via Env)
export SWARM_WORM_ROOT=logs/worm
make raas-regime-swarm-daemon

# Live-Feed Mock + Prometheus-Counter (kein Netz)
make raas-live-feed-prometheus-smoke

# Helm / Cluster
make raas-regime-swarm-helm-lint
make raas-regime-swarm-helm-pod-smoke      # lokal
make raas-regime-swarm-cluster-smoke       # Kind-Cluster
make raas-regime-swarm-live-shadow-install # Live Shadow (Helm-Overlay, siehe Runbook)
```

Metriken (Daemon): `GET /metrics` auf `SWARM_METRICS_PORT` (Default 8080) — `swarm_cycles_total`, `drift_counter{regime,type}`, `risk_multiplier`, `gate_block_counter{gate}`.

## Weiterführende Dokumentation

| Dokument | Inhalt |
|----------|--------|
| [`docs/RaaS_REGIME_DRIFT_PREREG.md`](../../../docs/RaaS_REGIME_DRIFT_PREREG.md) | Pre-Reg v0/v2, Bonferroni, Soft-Adapt v1→v2, 30-Tage-Eval |
| [`docs/REGIME_SWARM_INFRA_GATES.md`](../../../docs/REGIME_SWARM_INFRA_GATES.md) | A0/A2.5, ConfigMap, Cluster-Runbook, Chaos-Mapping |
| [`docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](../../../docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) | Live Shadow (`LIVE_FEED_ENABLED`), Metriken, Rollback |
| [`charts/regime-swarm/`](../../../charts/regime-swarm/) | Helm-Values, Smoke-Job, Infrastructure-Gates |

## Charter (kurz)

- **Monitoring only** — Drift-Warnung und Advisory, keine automatische Strategieausführung.
- **`live_execution=false`** auf jeder WORM-Zeile und im Daemon-Config.
- **Pre-Reg-Freeze** — Schwellenänderungen nur via dokumentiertem Amendment (v1/v2-Tabelle in Pre-Reg).
- **Fail-closed** — Infra-Fehler blockieren die Statistik-Pipeline vollständig.
