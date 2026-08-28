# Chaos Engineering — 9-Agent Shadow Schwarm (Pre-Reg v1)

**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · Shadow-Mode only · `live_execution=false`  
**Ziel:** Fail-Closed-Eigenschaft des **P6-Trading** Gates (`gate_core`) unter toxischer Injektion  
**Config:** `config/chaos_engineering/chaos_matrix_v1.json` · Schema: `chaos_matrix_v1.schema.json`  
**Runtime:** *nicht Teil dieser Pre-Reg* — nur Contract, Schema, Fixtures

---

## Namenskonvention: P6-Infra vs. P6-Trading

| Kennung | Schicht | Invariante | Code / Tests |
|---------|---------|------------|--------------|
| **P6-Infra** | Infra-Guardian | **I1** — `leaders_count ≤ 1` (Lease / Ordinal) | `leader_fsm_z3.py`, `test_regime_leader_z3.py` |
| **P6-Trading** | RaaS Fail-Closed Gate | **Fail-Closed** — keine Order-Freigabe bei toxischem Input | `services/fail_closed_gate/gate_core.py` |

Beide dürfen nicht unter derselben „P6“-Überschrift im Runbook gemischt werden.

---

## 1. Probe-Contract (A5)

**Reihenfolge:** Dieser Contract steht **vor** allen Erwartungen in der Chaos-Matrix. Tests sind nur falsifizierbar, wenn die Sonde dieselben Größen meldet, die `gate_core` im Betrieb liefert.

### 1.1 Quelle der Wahrheit

Die Shadow-Sonde liest **ausschließlich** das Ergebnis von `evaluate_gate()` / `POST /v1/evaluate`:

```python
# services/fail_closed_gate/gate_core.py
GateVerdict(decision, reasons, checks, scope, live_execution)
```

Kein paralleles `order_send`-Feld im Gate — die Sonde **leitet** ab.

### 1.2 Ableitung `order_send`

```text
order_send ≡ (decision == "RELEASED")
```

| `decision` | `order_send` | Bedeutung |
|------------|--------------|-----------|
| `BLOCKED` | `false` | Fail-Closed — Gate verweigert Ausführungspfad |
| `RELEASED` | `true` | Gate würde freigeben (nur mit `human_gate_open` + alle Checks) |

**Charter:** `live_execution=false` bleibt auf dem Verdict; Paper-Ledger `order_send_count` muss **0** bleiben — das Chaos-Experiment prüft die **Gate-Entscheidung**, nicht den Exchange-POST.

### 1.3 Probe-Paket (`chaos_gate_probe_v1`)

Wall-clock an der Sonde (A5), nicht im `GateVerdict`:

```json
{
  "schema": "chaos_gate_probe_v1",
  "ts": "2026-08-28T15:00:00.000Z",
  "case_id": "CHAOS-02",
  "probe_status": "OK",
  "processing_latency_ms": 1.4,
  "gate_verdict": {
    "decision": "BLOCKED",
    "reasons": ["M7_LATENCY_POISON"],
    "checks": { },
    "scope": "DEFENSIVE_CAUSAL_GROUNDING",
    "live_execution": false
  },
  "derived": {
    "order_send": false
  }
}
```

#### `probe_status` (Pflicht — trennt Block von Crash)

| Wert | Bedeutung | Chaos-Test |
|------|-----------|------------|
| `OK` | Gate antwortete, Verdict parsebar | Assertion A6 darf laufen |
| `GATE_UNAVAILABLE` | HTTP/Timeout, kein Verdict | **FAIL** — kein Fail-Closed-Nachweis |
| `DESERIALIZE_ERROR` | Antwort nicht parsebar | **FAIL** |
| `PROBE_ERROR` | Sonde intern | **FAIL** |

**Wichtig:** `order_send=false` bei `probe_status≠OK` ist **kein PASS** — das wäre „Absturz = Block“. A6 verlangt `probe_status=OK` **und** `order_send=false`.

### 1.4 Zulässige `reasons` (aus `gate_core`)

Vollständige Aufzählung (Stand `gate_core.py`):

| Reason | Auslöser in `evaluate_gate` |
|--------|----------------------------|
| `SIGNAL_INVALID` | `oracle_ok=false` oder `scenario_ok=false` |
| `P3_EXEC_RISK` | `exec_risk ≥ 0.80` |
| `P8_CASCADE_RISK` | `cascade_risk ≥ 0.75` |
| `M7_LATENCY_POISON` | M7 MAD-Gate (`latency_spike`) |
| `Z3_CASCADE_UNSAFE` | Z3-Cascade-Check (additiv) |
| `BHO_DELTA` | \|`bho_delta`\| > 0.01 |
| `HUMAN_GATE_CLOSED` | Default: Human-Gate zu, keine Block-Reasons |
| `HUMAN_GATE_OPEN` | Nur bei `RELEASED` |
| `ALL_CHECKS_PASS` | Nur bei `RELEASED` |

Chaos-Fälle erwarten **`decision=BLOCKED`** mit **`required_reasons_any`** und **`allowed_reasons_only`** — keine pauschale `gate_error_state_allowed: true`.

### 1.5 A6 Assertion (Fail-Closed)

Für jeden Fall mit `injection_active=true`:

```text
PASS iff:
  probe_status == OK
  AND decision == BLOCKED
  AND derived.order_send == false
  AND reasons ∩ required_reasons_any ≠ ∅
  AND reasons ⊆ allowed_reasons_only
  AND processing_latency_ms ≤ max_probe_latency_ms (A8, default 10 ms)
```

`RELEASED` oder fehlende Reasons bei `probe_status=OK` → **FAIL_OPEN** / **FAIL_REASON**.

---

## 2. Laufpolitik (A1 / A7)

| Regel | Wert | Begründung |
|-------|------|------------|
| `complete_matrix` | `true` | Alle 9 Fälle laufen — korrelierte Ausfälle sichtbar |
| `fail_if_any_case_fails` | `true` | Gesamturteil FAIL wenn ≥1 Fall FAIL |
| `reset_between_cases` | `true` | A7 isoliert Shadow-State; kein Early-Abort nötig |

**Explizit verboten:** `abort_on_first_failure: true` — würde A7 untergraben und CHAOS-02…09 bei erstem Fehler verstecken.

---

## 3. Die 9 Chaos-Agenten (Übersicht)

| ID | Agent | Rolle |
|----|-------|-------|
| A1 | Chaos-Orchestrator | Matrix aus Config, Laufpolitik, Lifecycle |
| A2 | Synthetischer Marktgenerator | OHLCV / Orderbuch-Fehler → `GateInput` |
| A3 | Fault-Injection-Driver | Shadow-Queue, kein Produktions-Touch |
| A4 | Netzwerk-Latenz- & Frame-Simulator | Latenz, Korruption, Sequenz |
| A5 | Z3-Gate-Interceptor (Probe) | §1 Probe-Contract |
| A6 | Assertion-Engine | §1.5 Fail-Closed |
| A7 | State-Isolation- & Resetter | Reset zwischen Fällen |
| A8 | Golden-Reference-Comparator | `processing_latency_ms` Schwellwert |
| A9 | Chaos-Audit- & Zertifizierungsagent | JSONL + Alert bei Matrix-FAIL |

---

## 4. Chaos-Matrix (CHAOS-01…09)

| ID | Fault | `required_reasons_any` (mindestens einer) | Fixture |
|----|-------|-------------------------------------------|---------|
| CHAOS-01 | Orderbuch-Lücke | `SIGNAL_INVALID` | `fixtures/CHAOS-01.json` |
| CHAOS-02 | Latenz >500 ms | `M7_LATENCY_POISON` | `fixtures/CHAOS-02.json` |
| CHAOS-03 | Flash −15 % | `P8_CASCADE_RISK` \| `P3_EXEC_RISK` \| `SIGNAL_INVALID` | `fixtures/CHAOS-03.json` |
| CHAOS-04 | Flash +25 % | `P8_CASCADE_RISK` \| `P3_EXEC_RISK` \| `SIGNAL_INVALID` | `fixtures/CHAOS-04.json` |
| CHAOS-05 | Frame-Checksum | `SIGNAL_INVALID` | `fixtures/CHAOS-05.json` |
| CHAOS-06 | Frame-Trunkierung | `SIGNAL_INVALID` | `fixtures/CHAOS-06.json` |
| CHAOS-07 | Sequenz-Sprung | `SIGNAL_INVALID` | `fixtures/CHAOS-07.json` |
| CHAOS-08 | Zero-Price | `SIGNAL_INVALID` | `fixtures/CHAOS-08.json` |
| CHAOS-09 | Volumen-Spike | `P3_EXEC_RISK` \| `P8_CASCADE_RISK` | `fixtures/CHAOS-09.json` |

Fixtures mappen Injektion auf **`gate_input`**-Felder, die `evaluate_gate()` heute versteht. A3-Adapter (WebSocket-Rohframes) sind **Phase 2** — Pre-Reg fixiert nur die Gate-Grenze.

---

## 5. Gate-Kriterien (vor Implementierung)

| Gate | Kriterium |
|------|-----------|
| **G0** | Probe-Contract §1 implementiert; keine parallelen Felder |
| **G1** | Alle 9 Fixtures gegen `gate_core.evaluate_gate` offline: erwartete `reasons` ⊆ Contract |
| **G2** | Shadow-Run: `complete_matrix`, `failed=0`, `fail_closed_rate=100%` |
| **G3** | Ein künstliches FAIL_OPEN (Mock `RELEASED` bei Injektion) wird von A6 erkannt |

---

## 6. A9 Audit-Zeile (Zielschema)

```json
{
  "schema": "chaos_engineering_report_v1",
  "experiment_id": "REGATTA_FUZZ_2026",
  "p6_layer": "P6-Trading",
  "total_tests": 9,
  "passed": 9,
  "failed": 0,
  "fail_closed_rate": "100.00%",
  "run_policy": { "complete_matrix": true, "fail_if_any_case_fails": true },
  "cases": [
    {
      "id": "CHAOS-02",
      "passed": true,
      "probe_status": "OK",
      "decision": "BLOCKED",
      "order_send": false,
      "reasons": ["M7_LATENCY_POISON"],
      "processing_latency_ms": 1.2
    }
  ],
  "certification": "Z3_GATE_CHAOS_PRE_REG_READY",
  "live_execution": false
}
```

---

## 7. Referenzen

| Artefakt | Pfad |
|----------|------|
| Gate-Core | `services/fail_closed_gate/gate_core.py` |
| HTTP-Gate | `services/fail_closed_gate/main.py` |
| Proto-Screen | `prototypes/v5_fail_closed_gate/` |
| Matrix-Config | `config/chaos_engineering/chaos_matrix_v1.json` |
| JSON-Schema | `config/chaos_engineering/chaos_matrix_v1.schema.json` |
| Infra P6 (nicht verwechseln) | `docs/INFRA_GUARDIAN_P6_Z3_ENTWURF.md` |

---

## 8. Nächste Phase (nach Pre-Reg)

1. Offline-Harness G1: Fixtures × `evaluate_gate` (kein HTTP)
2. A1/A6/A9 Skeleton + JSONL
3. Shadow `fail-closed-gate` Deployment + A3/A4 Adapter
4. CI-Gate `CHAOS_MATRIX_PASS` (9/9)

**Kein Runtime-Code in dieser Pre-Reg-Commit-Phase.**
