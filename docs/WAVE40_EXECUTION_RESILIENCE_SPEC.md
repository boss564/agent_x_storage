# Wave 40 — Execution Resilience & Risk Shield

**Status:** Produktionsreif (2026-08-24) — Phasen A–E abgeschlossen, 105/105  
**Modul:** `agents_b2g/resilience/`  
**Wellen-Nummer:** **40** (kanonisch; Wave 38 = Diagnostic, Wave 39 = Ethical Boundary)  
**Charakter:** Operative Ausführungs-Resilienz (4 Risiko-Quadranten)  
**Skala:** 9 Hauptagenten × 9 Subagenten = **81 Subagenten**  
**E2E:** `scripts/test_wave40_resilience.py` — **105/105**  
**Version:** **0.25.0** (Minor, neue Hauptwelle)  
**CLAUDE.md:** eingetragen

---

## 0. Abgrenzung (bindend)

| Welle | Name | Modul | Spec |
|-------|------|-------|------|
| 38 | Causal Audit & Signal Guard | `agents_b2g/diagnostic/` | `WAVE38_DIAGNOSTIC_SPEC.md` |
| 39 | Ethical Boundary (Vierfach-Sperre) | `agents_b2g/ethical_boundary/` | `WAVE39_ETHICAL_BOUNDARY_SPEC.md` |
| **40** | **Execution Resilience & Risk Shield** | `agents_b2g/resilience/` | **diese Datei** |

**Invariante:** `docs/WAVE39_ETHICAL_BOUNDARY_SPEC.md` **§5.4** (Hook-Härte) bleibt **unberührt**.
Wave 40 erweitert weder Wave-39-Envelope noch Gatekeeper-Hook-Semantik.
Execution-Resilience-Gates leben ausschließlich in diesem Modul und dieser Spec.

---

## 1. Rolle im Stack

```
Wave 39 Ethical Boundary (CERTIFIED / BLOCKED)
         ↓
Wave 38 Gatekeeper (RELEASED / BLOCKED)
         ↓
Wave 40 Execution Resilience (4-Quadrant-Pipeline)   ← diese Spec
         ↓
ExecutionForensicRecorder (GoBD-WORM)
```

Wave 40 schützt **Ausführung** (Finality, RPC, MEV-Privatheit, Gas, Confounder,
Black-Swan, Fiscal, Forensic) — nicht Signal-Diagnose (38) und nicht Ethik-Sperre (39).

---

## 2. Architektur

```
agents_b2g/resilience/
 ├── __init__.py
 ├── config.py
 ├── logging_utils.py
 ├── agents.py
 ├── types.py
 ├── execution_resilience_orchestrator.py   # Root: 4-Quadrant-Pipeline
 └── subagents/
     ├── __init__.py
     ├── reorg_monitor.py                   # A1
     ├── rpc_health_sentinel.py             # A2
     ├── mev_shield.py                      # A3 (Phase B)
     ├── gas_budget_enforcer.py             # A4 (Phase B)
     ├── confounder_detector.py             # A5 (Phase C)
     ├── black_swan_breaker.py              # A6 (Phase C)
     ├── fiscal_compliance_auditor.py       # A7 (Phase D)
     └── execution_forensic_recorder.py     # A8 (Phase D)
```

### 2.1 Neun Hauptagenten

| # | Agent | Quadrant | Verantwortung |
|---|-------|----------|---------------|
| Root | `ExecutionResilienceOrchestrator` | alle | 4-Quadrant-Pipeline, BHO-Δ=0 Gas |
| A1 | `ReorgMonitor` | Infra | Chain-Reorgs, Finality-Gate |
| A2 | `RPCHealthSentinel` | Infra | Multi-RPC-Failover, SLA |
| A3 | `MEVShield` | MEV | Private-Only-Submission |
| A4 | `GasBudgetEnforcer` | MEV | Hard Gas-Cap + Daily-Limit |
| A5 | `ConfounderDetector` | Modell | Novel-Faktor-Quarantäne |
| A6 | `BlackSwanCircuitBreaker` | Modell | Auto-Halt + Recovery |
| A7 | `FiscalComplianceAuditor` | Operativ | Handelsbuchführung, §13b |
| A8 | `ExecutionForensicRecorder` | Operativ | GoBD-WORM + Multi-Chain-Anchor |

### 2.2 Subagenten (9×9)

| Agent | Subagenten (je 9) |
|-------|-------------------|
| **Orchestrator** | QuadrantRouter, FinalityGate, BudgetLedger, CircuitBreakerCoordinator, TelemetryAggregator, PolicyEngine, MultiTenantIsolator, GoBDExporter, HealthReporter |
| **ReorgMonitor** | BlockDepthTracker, FinalityThresholdEvaluator, AncestorHashVerifier, ReorgSeverityScorer, SignalInvalidator, RollbackCascader, ConfirmationWaiter, ChainForkDetector, RecoveryObserver |
| **RPCHealthSentinel** | LatencyProbe, HTTP429Backoff, FallbackRouter, MultiRPCEndpointBalancer, TimeoutCircuitBreaker, EventLogDriftDetector, StalenessMonitor, JitterFilter, SLAEnforcer |
| **MEVShield** | FlashbotsRelayClient, PrivateTxSubmitter, SandwichDetector, FrontRunningGuard, SlippageEnforcer, BundlePricer, BuilderReputationTracker, MempoolLeakageScanner, ExecutionPrivacyEnforcer |
| **GasBudgetEnforcer** | PerTxCapValidator, CumulativeBurnTracker, DailyLimitEnforcer, PriorityFeeOptimizer, EIP1559Estimator, OutOfGasPreventer, RefundAggregator, BudgetCircuitBreaker, CostAllocationLogger |
| **ConfounderDetector** | ExogenousSignalScanner, CEXShockDetector, ThirdChainHackMonitor, NovelFactorClassifier, PreRegistrationValidator, SpuriousCorrelationFilter, CausalGraphUpdater, AnomalyZScorer, SignalQuarantineManager |
| **BlackSwanCircuitBreaker** | RegimeChangeDetector, VolatilitySpikeMonitor, PanicSellIdentifier, LatencyOverlayAnalyzer, AutoHaltTrigger, ManualOverrideGate, RecoveryRampUp, StressTestRunner, PostMortemGenerator |
| **FiscalComplianceAuditor** | GewerbesteuerCalculator, HandelsbuchführungsValidator, GoBDTransactionTagger, DatevExporter, TaxLotTracker, RealizedGainLossAggregator, AuditTrailSealer, BZStReporter, JahresabschlussGenerator |
| **ExecutionForensicRecorder** | WORMWriter, HashChainBuilder, EventLogArchiver, AuditIndexer, RetentionEnforcer, QESSigner, MultiChainAnchor, ReplayValidator, AuditorAccessManager |

---

## 3. 4-Quadrant-Pipeline

```
Quadrant 1 (Infra)     →  A1 Reorg + A2 RPC
Quadrant 2 (MEV)       →  A3 MEV-Shield + A4 Gas-Budget
Quadrant 3 (Modell)    →  A5 Confounder + A6 Black-Swan
Quadrant 4 (Operativ)  →  A7 Fiscal + A8 Forensic
              ↓
        Orchestrator (BHO-Δ=0 für Gas-Budget)
              ↓
        ExecutionForensicRecorder (WORM)
```

**Implementierungsphasen:** A (Q1) → B (Q2) → C (Q3) → D (Q4) → E (105 Tests).

---

## 4. Kern-Invarianten (Wave 40)

| Invariante | Regel |
|------------|-------|
| **Finality-Gate** | Kein Kausalsignal vor ≥12 Block-Confirmations (L1) / ≥64 (L2) |
| **Private-Only-Submission** | Alle TXs via Flashbots/private Builder — Mempool-Leakage = 0 |
| **Hard Gas-Cap** | `MAX_GAS_PER_TX` + `DAILY_BURN_LIMIT` — Überschreitung → Circuit-Open |
| **Confounder-Quarantäne** | Novel-Faktor → Signal-Invalidierung + 24h-Kühlphase |
| **Black-Swan-Halt** | σ>5 oder Vol>3×30d → Auto-Halt aller Execution-Agenten |
| **BHO-Δ=0 für Gas** | `Gas_In = Gas_Used + Gas_Refunded + Gas_Budget_Reserve` |
| **GoBD-WORM** | Jeder Execution-Schritt → Hash-Kette + Multi-Chain-Anchor |
| **Fiscal-Compliance** | Lückenlose Handelsbuchführung, §13b UStG, DATEV-Export |

Diese Invarianten stehen **neben** Wave-39-§5.4; sie ersetzen oder schwächen sie nicht.

---

## 5. Standard-Verträge

### 5.1 Agent-JSON

Jeder Agent/Subagent liefert:

```json
{
  "status": "started|completed|failed|blocked|skipped",
  "job_id": "<uuid-fragment>",
  "artifacts": [],
  "error": null,
  "logs": []
}
```

### 5.2 Infrastruktur

- **JSONLogger** — JSONL unter `logs/`, kein `print()`
- **`_safe_call`** — try/except + Retry mit Backoff
- **Multi-Tenancy** — Artefakte unter `{data_root}/{user_id}/resilience/`
- **Config** — Env-Defaults, failsafe Validation (`ResilienceConfig`)

### 5.3 Orchestrator-Envelope

```python
@dataclass(frozen=True)
class ResilienceEnvelope:
    status: ResilienceVerdict   # READY | HALTED | DEGRADED | BLOCKED
    job_id: str
    quadrant_results: dict[str, Any]
    finality_ok: bool
    rpc_ok: bool
    mev_ok: bool                # Phase B — Private-Only + Threat-Gate
    gas_ok: bool                # Phase B — Hard Cap + BHO
    confounder_ok: bool         # Phase C — Pre-Reg + Quarantäne
    blackswan_ok: bool          # Phase C — σ/Vol Auto-Halt
    fiscal_ok: bool             # Phase D — Handelsbuch + DATEV + §13b
    forensic_ok: bool           # Phase D — WORM-Hash-Kette + Anchor
    gas_bho_delta: float        # muss |Δ| ≤ 0.01 sein wenn Gas-Ledger aktiv
    halt_reason: str | None
```

---

## 6. Konfiguration (Env)

| Variable | Default | Bedeutung |
|----------|---------|-----------|
| `RESILIENCE_DATA_ROOT` | `data` | Multi-Tenant-Root |
| `RESILIENCE_LOG_DIR` | `logs` | JSONL-Logs |
| `RESILIENCE_FINALITY_L1` | `12` | L1 Confirmations |
| `RESILIENCE_FINALITY_L2` | `64` | L2 Confirmations |
| `RESILIENCE_RPC_SWITCH_MS` | `200` | Latency-Switch-Schwelle |
| `RESILIENCE_RPC_P99_SLA_US` | `54` | Surface-P99-Referenz (µs) |
| `RESILIENCE_MAX_GAS_PER_TX` | `500000` | Hard Cap pro TX |
| `RESILIENCE_DAILY_BURN_LIMIT` | `50000000` | Kumulatives Daily-Limit |
| `RESILIENCE_MAX_RETRIES` | `3` | `_safe_call`-Retries |
| `RESILIENCE_BLACK_SWAN_SIGMA` | `5.0` | Halt-Schwelle σ |
| `RESILIENCE_VOL_SPIKE_FACTOR` | `3.0` | Vol vs. 30d |

---

## 7. E2E-Test-Suite (Phase E)

**Datei:** `scripts/test_wave40_resilience.py`  
**Ziel:** 105/105, 12 Gruppen

1. Reorg-Simulation (5 Szenarien)
2. RPC-Failover (429, Timeout, Staleness, Jitter, Multi-Endpoint)
3. MEV-Shield
4. Gas-Budget
5. Confounder-Detection
6. Black-Swan
7. Fiscal-Compliance
8. Forensic-WORM
9. Orchestrator-Integration (4-Quadrant, BHO-Δ=0)
10. Multi-Tenancy
11. Config-Failsafe
12. Full-E2E (1.000 TXs, 0 Loss, WORM-verified)

---

## 8. Implementierungsstand

| Phase | Inhalt | Status |
|-------|--------|--------|
| **A** | Spec + Orchestrator + A1 Reorg + A2 RPC | ✅ |
| **B** | A3 MEV + A4 Gas (Q2 aktiv, Q3–4 skipped) | ✅ |
| **C** | A5 Confounder + A6 Black-Swan (Q3 aktiv, Q4 skipped) | ✅ |
| **D** | A7 Fiscal + A8 Forensic (Q4 aktiv, alle Quadranten) | ✅ |
| **E** | 105 Tests + CLAUDE.md + 0.25.0 | ✅ |

---

## 9. Explizit nicht in Scope

- Keine Änderung an Wave-38-Diagnostic-Verdicts
- Keine Änderung an Wave-39-§5.4 / Envelope / Hook
- Kein CLAUDE.md-Eintrag vor Phase-E-Abschluss
- Keine offensive Execution / Profit-Extraction (Charter gilt unverändert)
