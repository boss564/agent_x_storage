# Wave 39 — Ethical Boundary Enforcement & Defensive Charter

**Status:** Implementierungs-Spezifikation (2026-08-23)  
**Modul:** `agents_b2g/ethical_boundary/`  
**Charter:** `docs/AGENT_X_CHARTER.md` (bindend, Ebene 4)  
**Charakter:** Querliegende Enforcement-Welle (analog Wave 38 Diagnostic, Compliance)  
**Skala:** 9 Hauptagenten × 9 Subagenten = **81 Subagenten**  
**Wellen-Nummer:** 39 (neben Hauptwellen 1–33; nicht in ×9-Hauptwellen-Zählung 277)

---

## 0. Rolle im Stack

Wave 39 **erzwingt** die defensive Ausrichtung strukturell — nicht nur dokumentarisch.
Sie sitzt **vor** operativem Output und **quer** zu Wave 38 (Gatekeeper) und Wave 28 (Defense).

```
Pre-Reg / Charter / Scope
         ↓
   Wave 39 (81 Subagenten) — Ethical Boundary Pipeline
         ↓
   Wave 38 Gatekeeper (RELEASED/BLOCKED + cause)
         ↓
   Wave 28 Defense (nur defensive Kopplung)
```

**Invariante:** Ohne Wave-39-`CERTIFIED`-Envelope darf Agent 9 (Wave 38) kein `RELEASED` emittieren
(wenn `ETHICAL_BOUNDARY_MANDATORY=true`, Default in Pilot).

---

## 1. Die 9 Hauptagenten

| # | Agent | Ebene | Verantwortung |
|---|-------|-------|---------------|
| 1 | `PreRegFirewallAgent` | 1 | Pre-Reg-Validierung, Negativ-Klausel, WORM-Hashes |
| 2 | `EthicalAssertionAgent` | 2 | Runtime-Assertions, `NonExtractionAssertion` |
| 3 | `ScopeEnforcerAgent` | 2/3 | Immutable `DEFENSIVE_CAUSAL_GROUNDING` |
| 4 | `AuditTrailAgent` | 3 | GoBD-WORM, `OBSERVATION_AND_DEFENSE` |
| 5 | `IntegrityViolationDetector` | 3 | Offensive-Execution-Call-Detection |
| 6 | `CharterEnforcerAgent` | 4 | `AGENT_X_CHARTER.md`, Air-Gap |
| 7 | `BoundaryViolationReporter` | 1–4 | Aggregation, Eskalation Wave 28 |
| 8 | `DefensiveScopeCertifier` | 1–4 | Output-Zertifikat (PDF/A-3 optional) |
| 9 | `EthicalBoundaryOrchestrator` | Root | Pipeline, finale BLOCKED/RELEASED |

Subagenten-Details: siehe User-Entwurf (9×9-Tabelle); Implementierung folgt 1:1-Namensschema
`{agent}_{subagent}` in `agents_b2g/ethical_boundary/subagents/`.

---

## 2. Python-Typen (`agents_b2g/ethical_boundary/types.py`)

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Literal

SCOPE_DEFENSIVE: Literal["DEFENSIVE_CAUSAL_GROUNDING"] = "DEFENSIVE_CAUSAL_GROUNDING"

class EthicalVerdict(str, Enum):
    CERTIFIED = "CERTIFIED"           # alle Ebenen grün
    BLOCKED = "BLOCKED"             # Violation → fail-closed
    INCONCLUSIVE = "INCONCLUSIVE"   # Assertion/Pre-Reg nicht prüfbar

class ViolationKind(str, Enum):
    PREREG_NEGATION = "PREREG_NEGATION"
    OFFENSIVE_EXECUTION = "OFFENSIVE_EXECUTION"
    PROFIT_EXTRACTION = "PROFIT_EXTRACTION"
    SCOPE_TAMPER = "SCOPE_TAMPER"
    CHARTER_AIRGAP = "CHARTER_AIRGAP"
    AUDIT_INTEGRITY = "AUDIT_INTEGRITY"

class EthicalBoundaryException(Exception):
    """Fail-closed: maps to Gatekeeper BLOCKED + cause=ETHICAL_BOUNDARY."""

    def __init__(
        self,
        message: str,
        *,
        kind: ViolationKind,
        agent: str,
        evidence: dict[str, Any] | None = None,
    ): ...

@dataclass(frozen=True)
class ScopeFlag:
    scope: Literal["DEFENSIVE_CAUSAL_GROUNDING"]
    attached_at: str          # ISO-8601 UTC
    attached_by: str          # agent id
    content_hash: str         # SHA-256 of payload ohne scope-Feld

@dataclass(frozen=True)
class NonExtractionAssertion:
    """Runtime check: signal receiver metadata must not target profit extraction."""

    receiver_id: str
    allowed_purposes: tuple[str, ...]  # subset of DEFENSIVE_PURPOSES
    metadata: dict[str, Any]

DEFENSIVE_PURPOSES = frozenset({
    "RISK_MANAGEMENT",
    "SIGNAL_DENOISING",
    "CAUSAL_GROUNDING",
    "PERIMETER_DEFENSE",
    "AUDIT_OBSERVATION",
})

@dataclass(frozen=True)
class EthicalBoundaryEnvelope:
    """Wave 39 output — consumed by Wave 38 Gatekeeper pre-flight."""

    status: EthicalVerdict
    job_id: str
    scope: ScopeFlag
    violations: tuple[ViolationRecord, ...] = ()
    prereg_hashes: dict[str, str] = field(default_factory=dict)
    charter_version: str = "1.0"
    certified_at: str | None = None
    block_cause: str | None = None  # ETHICAL_BOUNDARY when BLOCKED

@dataclass(frozen=True)
class ViolationRecord:
    kind: ViolationKind
    severity: int              # 0–100
    source_agent: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
```

**Wave-38-Erweiterung** (`agents_b2g/diagnostic/types.py`):

```python
class BlockCause(str, Enum):
    ...
    ETHICAL_BOUNDARY = "ETHICAL_BOUNDARY"  # Wave 39 Violation
```

---

## 3. Standard-Agenten-Vertrag (alle 81 Subagenten)

Identisch zu Wave 28/38:

```python
def run(...) -> dict[str, Any]:
    """
    Returns:
        {
          "status": "completed" | "failed" | "blocked" | "skipped",
          "job_id": str,
          "artifacts": [...],
          "error": str | None,
          "logs": [...],
        }
    """
```

- `JSONLogger` + `_safe_call` auf jedem Subagenten
- Multi-Tenancy: `{data_root}/{user_id}/ethical_boundary/`
- Fail-closed: unhandled Exception → `blocked` + `EthicalBoundaryException`

---

## 4. Orchestrator-Pipeline (Agent 9)

```python
class EthicalBoundaryOrchestrator:
    def __init__(self, user_id: str = "default"): ...

    def enforce(
        self,
        payload: dict[str, Any],
        *,
        job_id: str,
        wave38_gate_context: dict[str, Any] | None = None,
    ) -> EthicalBoundaryEnvelope:
        """
        Stages (sequential, short-circuit on BLOCKED):
          1. PreRegFirewallAgent.enforce_prereg()
          2. ScopeEnforcerAgent.attach_and_validate(payload)
          3. EthicalAssertionAgent.assert_non_extraction(metadata)
          4. IntegrityViolationDetector.scan_execution_calls(payload)
          5. CharterEnforcerAgent.validate_air_gap(payload)
          6. AuditTrailAgent.classify_and_write(stages 1–5)
          7. BoundaryViolationReporter.aggregate()
          8. DefensiveScopeCertifier.certify()  # nur wenn 1–7 grün
          9. BLOCKEDDecisionMaker | RELEASEDDecisionMaker
        """
```

**BLOCKED-Regel:** Mindestens eine Violation mit `severity >= 50` **oder**
`ViolationKind` ∈ {`OFFENSIVE_EXECUTION`, `PROFIT_EXTRACTION`, `SCOPE_TAMPER`} → `BLOCKED`.

---

## 5. Verdrahtung Wave 38 (Diagnostic)

### 5.1 Pre-Flight vor Gatekeeper

In `GatekeeperDispatcherAgent.run()` (Wave 38 Agent 9):

```python
if os.getenv("ETHICAL_BOUNDARY_MANDATORY", "true").lower() == "true":
    ethical = self.ethical_orchestrator.enforce(
        payload={"run_input": run_input, "artifacts": cte_by_candidate, ...},
        job_id=job_id,
    )
    if ethical.status == EthicalVerdict.BLOCKED:
        return self._blocked_envelope(
            job_id, cause=BlockCause.ETHICAL_BOUNDARY, ethical=ethical
        )
    # attach ethical.scope to DiagnosticSignalEnvelope metadata
```

### 5.2 Scope-Propagation

Jedes Occupancy-Bundle und `DiagnosticSignalEnvelope` erhält:

```json
{
  "scope": "DEFENSIVE_CAUSAL_GROUNDING",
  "ethical_boundary_job_id": "<uuid>",
  "charter_version": "1.0"
}
```

`ScopeEnforcerAgent.ScopeTamperDetector` prüft vor Persistenz (SQLite, JSONL, EventBus).

### 5.3 Live Pre-Reg

`PreRegFirewallAgent` lädt bindend:

- `docs/BRIDGE_STUFE_A_V3_PREREG.md`
- `docs/BRIDGE_DIAGNOSTIC_PREREG.md`
- `docs/WAVE38_LIVE_PREREG.md`

Versiegelte Bridge-Artefakte (`bridge_manifest.json`) werden gehasht, nicht reinterpretiert.

### 5.4 Hook-Härteanforderungen & Regression-Normalisierung

Drei harte Anforderungen an den Wave-38×39-Hook (`ethical_boundary_hook.py`):

1. **Additiv, nicht überschreibend** — bei `CERTIFIED` bleibt die methodische Wave-38-Verdict-Priorität (Pre-Reg §6) unverändert.
2. **Byte-identische Regression bei Compliance** — methodische Felder des `DiagnosticSignalEnvelope` sind bei Compliance byte-identisch zur Baseline ohne Hook.
3. **Fail-closed bei Hook-Fehler** — Exception → `BLOCKED` + `ETHICAL_BOUNDARY`, niemals `RELEASED`.

**Serialisierung (Produktion):** Gatekeeper hängt `ethical_boundary` bei **jedem** Preflight-Ergebnis an (sowohl `CERTIFIED` als auch `BLOCKED`). Bei `CERTIFIED` enthält das Envelope-`to_dict()` zwingend `certificate_id` (SHA-256 über Job+Scope, identisch zum Audit-Trail-`certification_pass`). Live-Results spiegeln das auf Root-Ebene. Ohne diese Marker ist die Vierfach-Sperre GoBD-technisch nicht nachvollziehbar.

**Normalisierung (nur Regression):** `normalize_envelope_metadata_for_regression()` strippt `ethical_boundary` und `timestamp_utc` **ausschließlich** für Unit-/Regression-Vergleiche der methodischen Envelope-Identität. Sie darf **nicht** in Produktionspfaden (Gatekeeper-Persistenz, `live_result_*.json`, EventBus, GoBD-Report) aufgerufen werden.

| Kontext | `ethical_boundary` in Metadata | Begründung |
|---------|--------------------------------|------------|
| Regression (`normalize_envelope_metadata_for_regression`) | gestrippt vor Compare | testet Wave-38-Verdicts ohne additive Wave-39-Marker |
| Produktion (Gatekeeper / Live-Result) | **vorhanden** | Vierfach-Sperre nachvollziehbar; GoBD |

---

## 6. Verdrahtung Wave 28 (Defense)

### 6.1 Violation → Defense

`BoundaryViolationReporter.ViolationEscalationManager` publiziert:

```python
event_bus.publish("ethical.boundary.violation", {
    "user_id": user_id,
    "kind": violation.kind.value,
    "severity": violation.severity,
    "recommended_action": "PERIMETER_BLOCK",  # deskriptiv
})
```

Wave 28 `PerimeterGatewayDefender` **darf** auf dieses Event reagieren (Throttle/Ban),
**darf nicht** Kausalsignale in offensive Execution umleiten.

### 6.2 Censorship-Stack (Wave 28 Threat Engine)

Censorship-Resilience (Variante A) bleibt **defensiv** — Wave 39 prüft, dass
`CensorshipBypassAdapter` nur `defensive_only: true`-Routen emittiert (Charter §3).

---

## 7. Konfiguration (Env)

| Variable | Default | Zweck |
|----------|---------|-------|
| `ETHICAL_BOUNDARY_MANDATORY` | `true` | Wave 38 Gatekeeper pre-flight |
| `ETHICAL_ASSERTION_ENABLED` | `true` | Agent 2 Runtime-Assertions |
| `DEFENSIVE_SCOPE_MANDATORY` | `true` | Agent 3 Scope-Flag erzwingen |
| `AGENT_X_CHARTER_PATH` | `docs/AGENT_X_CHARTER.md` | Agent 6 |
| `ETHICAL_BOUNDARY_DATA_ROOT` | `data` | Multi-Tenancy |

---

## 8. Artefakte

| Pfad | Inhalt |
|------|--------|
| `{data_root}/{user_id}/ethical_boundary/audit/*.jsonl` | GoBD-WORM-Kette |
| `{data_root}/{user_id}/ethical_boundary/certificates/*.json` | Zertifikate Agent 8 |
| `{data_root}/{user_id}/ethical_boundary/prereg_hashes.json` | SHA-256 Pre-Reg-Stand |
| `docs/AGENT_X_CHARTER.md` | Normative Quelle Ebene 4 |

---

## 9. Implementierungs-Reihenfolge

```
1. docs/AGENT_X_CHARTER.md                    ✅
2. docs/WAVE39_ETHICAL_BOUNDARY_SPEC.md       ✅ (dieses Dokument)
3. agents_b2g/ethical_boundary/types.py
4. agents_b2g/ethical_boundary/orchestrator.py  (Agent 9)
5. Agents 2 + 3 (Runtime-Constraints)
6. Agents 1 + 4 (Pre-Reg + Audit)
7. Agents 5 + 6 (Detection + Charter)
8. Agents 7 + 8 (Reporting + Certification)
9. Wave 38 Gatekeeper-Hook + BlockCause.ETHICAL_BOUNDARY
10. scripts/test_wave39_ethical_boundary.py (81 Subagenten smoke)
11. Integration E2E: Wave 39 → Wave 38 → Wave 28
```

---

## 10. Tests (Ziel)

| Gruppe | Prüfung |
|--------|---------|
| Pre-Reg | Negativ-Klausel blockiert offensive Metadata |
| Assertion | `NonExtractionAssertion` fail → `EthicalBoundaryException` |
| Scope | Tamper auf `scope` → BLOCKED |
| Charter | Simulierter Titan-Vault-Pfad → Air-Gap-Violation |
| Wave 38 | Gatekeeper ohne Wave-39-Cert → BLOCKED (mandatory) |
| Wave 38 Hook | Produktion: `ethical_boundary` bei CERTIFIED/BLOCKED im Artifact; Regression: `normalize_envelope_metadata_for_regression` strippt nur im Test-Compare (§5.4) |
| Wave 28 | Violation-Event empfangen, kein Profit-Routing |

---

## 11. Version

| Version | Datum | Änderung |
|---------|-------|----------|
| 1.2 | 2026-08-24 | `certificate_id` Pflichtfeld in `EthicalBoundaryEnvelope.to_dict()` bei CERTIFIED (identisch Audit-Trail) |
| 1.1 | 2026-08-24 | §5.4 Hook-Härteanforderungen; Regression-Normalisierung explizit produktionsfern; CERTIFIED-Marker in Gatekeeper-Serialisierung |
| 1.0 | 2026-08-23 | Erstfassung: 9 Agenten, Typen, Wave 38/28-Verdrahtung |
