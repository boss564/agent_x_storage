# Post-MEV Diagnostic Extension (PM1–PM3)

**Status:** Spezifikation **versiegelt** — S0–S5 implementiert · Tests 27/27 · CLAUDE.md 0.25.1  
 
**Datum:** 2026-08-24  
**Modul:** `agents_b2g/diagnostic/post_mev/`  
**Charakter:** Additive Post-Gatekeeper-Stufe (Beobachtung/Diagnose)  
**Wellen-Nummer:** **keine** (kein Wave 41; Erweiterung von Wave 38, nicht Ersatz)  
**E2E-Ziel:** `scripts/test_post_mev_diagnostic.py` — **27/27** (3 Agenten × 9 Subagenten)  
**Abgrenzung:** Wave-39-Spec **§5.4** unberührt · Wave-40/K8 unberührt (keine zweite Execution-Härte)

---

## 0. Rolle im Stack

```
Wave 38 Data Plane (1–5) → Analysis (6–8) → Gatekeeper (9)
         ↓
   DiagnosticSignalEnvelope (RELEASED | BLOCKED)  ← unverändert (append-only)
         ↓
   Event / Checkpoint: mev_tail_completed (Gnosis)
         ↓
   Post-MEV Stufe: PM1 → PM2 → PM3     ← diese Spec
         ↓
   PostMEVDiagnosticEnvelope (additive Annotationen)
```

**Semantik von „6→9“:** bleibt die Wave-38-**Analyse-Pipeline-Stufe** (Agenten 6–9).  
Post-MEV ist **nicht** `extend(6→9)` und **nicht** Reuse von A7–A9.

---

## 1. Abgrenzung (bindend)

| System | Verantwortung | Post-MEV darf … |
|--------|---------------|-----------------|
| Wave 38 Agents 1–9 | Capture, CTE, FDR, Gatekeeper | …lesen, nicht ersetzen |
| Wave 39 §5.4 | Ethical Hook-Härte | …**nicht** anfassen |
| Wave 40 / K8 | Finality, Private-Only, Gas-BHO, Confounder-Quarantäne (Execution), Black-Swan, Fiscal, Forensic-WORM | …**nicht** duplizieren |
| Bridge-Serie (versiegelt) | Read-only Referenz | …laden, nicht neu berechnen |
| **Post-MEV (diese Spec)** | Diagnose **nach** MEV-Tail an Capture-Artefakten | …append-only annotieren |

**vs. Wave 40:** K8 schützt **Ausführung**. Post-MEV bewertet **bereits erfasste** Signale/Occupancy nach MEV-Tail — rein diagnostisch, kein Execution-Circuit.

---

## 2. Trigger & Position

| Feld | Wert |
|------|------|
| Trigger | `mev_tail_completed` (Gnosis-Checkpoint `status=completed`) |
| Vorbedingung | Wave-38-Gatekeeper-Lauf abgeschlossen (Envelope existiert) |
| Parallelität | **verboten** — keine Analyse parallel zum MEV-Tail-Capture |
| Erstlauf-Envelope | **byte-unverändert**; Post-MEV hängt nur Zusatzartefakte an |

---

## 3. Drei Agenten (PM1–PM3)

### 3.1 Übersicht

| ID | Klasse | Funktion |
|----|--------|----------|
| **PM1** | `PostMEVCausalConsistencyValidator` | Kausalkonsistenz nach MEV-Tail — Signale durch MEV verzerrt? |
| **PM2** | `AdversarialSignalQuarantiner` | Sandwich/Frontrun-Footprints in Capture → diagnostische Quarantäne (24 h) |
| **PM3** | `CausalGraphPostMEVReconciler` | Kausalgraph-Amendments **append-only**; sealed Pre-Reg unverändert |

### 3.2 Modul-Layout

```
agents_b2g/diagnostic/post_mev/
├── __init__.py
├── config.py
├── types.py                         # PostMEVDiagnosticEnvelope, AmendmentEntry, …
├── logging_utils.py                 # JSONLogger, _safe_call
├── post_mev_orchestrator.py         # Root: PM1 → PM2 → PM3
├── post_mev_causal_consistency_validator.py   # PM1
├── adversarial_signal_quarantiner.py          # PM2
└── causal_graph_post_mev_reconciler.py        # PM3
```

Optional: Subagenten in `post_mev/subagents/{pm1,pm2,pm3}/` (je 9).

---

## 4. Pre-Reg-Freeze (harte Invariante)

Sealed Pre-Registration-Hashes sind **unveränderlich**.

| Erlaubt | Verboten |
|---------|----------|
| Amendment-Eintrag append-only | Überschreiben / Löschen sealed Pre-Reg |
| Referenz `original_pre_reg_hash` | Mutation von `WAVE38_LIVE_PREREG` / Bridge-Pre-Regs |
| Neuer `amendment_hash` | Stilles Rewriting der Negativ-Klauseln |

### 4.1 Amendment-Schema (append-only)

```text
original_pre_reg_hash  ‖  amendment_id  ‖  amendment_payload  ‖  prev_amendment_hash
        →  amendment_hash = SHA-256(...)
        →  neue Zeile im Audit-Log / Amendment-Register
```

### 4.2 BLOCKING-Gate

Jeder Versuch, sealed Pre-Reg zu überschreiben:

```text
VERDICT: BLOCKED
cause: PRE_REG_MUTATION_ATTEMPT
+ Forensic-Stamp (GoBD-WORM append)
```

PM3 liefert bei sauberem Pfad nur `AMENDMENT_PROPOSED` / `NO_AMENDMENT` — nie eine Mutation.

---

## 5. Agent-Details & Subagenten (je 9)

### 5.1 PM1 — PostMEVCausalConsistencyValidator

**Eingabe:** Gatekeeper-Envelope (read-only) + MEV-Tail-Artefakte + Occupancy-Snapshot  
**Ausgabe:** `consistency_ok: bool`, `distorted_signal_ids: list`, Subagent-Reports

| # | Subagent | Rolle |
|---|----------|-------|
| 1 | TailCompletionGuard | Trigger nur bei `mev_tail_completed` |
| 2 | EnvelopeImmutabilityChecker | Erstlauf-Envelope Hash unverändert |
| 3 | PreFinalityRejector | Deskriptiv: Signale ohne ≥12 L1-Conf. markieren (keine Execution) |
| 4 | OccupancyDriftComparator | Occupancy vor/nach Tail |
| 5 | CTEStabilityProbe | CTE-Δ vs. Schwelle (deskriptiv) |
| 6 | DirectionConsistencyChecker | AB/BA-Konsistenz |
| 7 | MEVInterferenceScorer | Interferenz-Score 0–1 |
| 8 | SignalIntegrityHasher | Content-Hashes der geprüften Signale |
| 9 | ConsistencyVerdictComposer | Aggregat → `consistency_ok` |

### 5.2 PM2 — AdversarialSignalQuarantiner

**Eingabe:** Capture-Events mit Sandwich/Frontrun-Footprints (Beobachtung)  
**Ausgabe:** `quarantined_ids`, `cooldown_h=24`, Quarantäne-Register (append-only)

| # | Subagent | Rolle |
|---|----------|-------|
| 1 | SandwichFootprintScanner | Front+Back-Legs in Capture |
| 2 | FrontrunFootprintScanner | Competing nonce/target |
| 3 | BotDensityHeuristics | Cluster-Dichte |
| 4 | LeakageObservationLinker | Beobachtete Public-Mempool-Leaks (deskriptiv; K8 bleibt Execution-Gate) |
| 5 | QuarantineRegistryWriter | Append-only Register |
| 6 | CooldownScheduler | 24 h Kühlphase |
| 7 | SignalInvalidationMarker | Markierung ohne Envelope-Rewrite |
| 8 | FalsePositiveAuditor | FP-Schätzung |
| 9 | QuarantineVerdictComposer | Aggregat |

**Hinweis:** PM2-Quarantäne ist **diagnostisch** (Signal-Markierung für Reports). Wave-40-Confounder/MEVShield bleiben die Execution-Härte.

### 5.3 PM3 — CausalGraphPostMEVReconciler

**Eingabe:** PM1/PM2-Ergebnisse + sealed `original_pre_reg_hash`  
**Ausgabe:** Amendment-Liste oder `NO_AMENDMENT`; bei Mutationsversuch → `BLOCKED`

| # | Subagent | Rolle |
|---|----------|-------|
| 1 | PreRegHashLoader | Lädt sealed Hash (read-only) |
| 2 | PreRegMutationGuard | BLOCKING bei Schreibversuch |
| 3 | CausalEdgeDiffBuilder | Diff Ist-Graph vs. Pre-Reg-Erwartung |
| 4 | NovelFactorAnnotator | Novel-Faktoren nur als Annotation |
| 5 | AmendmentPayloadBuilder | Baut `amendment_payload` |
| 6 | AmendmentHasher | SHA-256-Kette |
| 7 | AmendmentAppendWriter | Append-only Persistenz |
| 8 | GraphSnapshotExporter | Snapshot für Auditoren |
| 9 | ReconcileVerdictComposer | `AMENDMENT_PROPOSED` / `NO_AMENDMENT` / `BLOCKED` |

---

## 6. Envelope-Vertrag

```python
@dataclass(frozen=True)
class AmendmentEntry:
    amendment_id: str
    original_pre_reg_hash: str      # 64 hex, sealed reference
    amendment_payload: dict
    prev_amendment_hash: str
    amendment_hash: str
    created_at: str                 # ISO-8601 UTC

@dataclass(frozen=True)
class PostMEVDiagnosticEnvelope:
    status: Literal["COMPLETED", "BLOCKED", "SKIPPED"]
    job_id: str
    trigger: Literal["mev_tail_completed"]
    gatekeeper_envelope_hash: str   # hash of first-run envelope (immutability proof)
    consistency_ok: bool
    quarantined_count: int
    amendments: tuple[AmendmentEntry, ...]
    block_cause: str | None         # PRE_REG_MUTATION_ATTEMPT | …
    pm_results: dict                # pm1/pm2/pm3 artifacts
```

**Regel:** `PostMEVDiagnosticEnvelope` ersetzt **nie** `DiagnosticSignalEnvelope`.  
Beide können im Live-Result **nebeneinander** liegen (`post_mev` Key additiv).

---

## 7. Standard-Verträge

- JSONLogger / `_safe_call` / Multi-Tenancy unter `{data_root}/{user_id}/wave38/post_mev/`
- Agent-JSON: `status`, `job_id`, `artifacts`, `error`, `logs`
- GoBD: Amendment- und Quarantäne-Register append-only (eigene Hash-Kette; **kein** Ersatz für Wave-40-Forensic-WORM)

---

## 8. Tests (Phase E der Extension)

**Datei:** `scripts/test_post_mev_diagnostic.py` — Ziel **27/27**

| Gruppe | n | Inhalt |
|--------|---|--------|
| PM1 | 9 | Tail-Guard, Envelope-Immutability, Drift, Verdict |
| PM2 | 9 | Sandwich/Frontrun-Footprint, 24 h Quarantäne, Register |
| PM3 | 9 | Pre-Reg-Freeze, Amendment-Append, Mutation→BLOCKED |

---

## 9. Implementierungsreihenfolge

| Schritt | Deliverable | Status |
|---------|-------------|--------|
| **S0** | Modulgerüst (`__init__`, config, types, logging) | ✅ |
| **S1** | PM1 + 9 Subagenten | ✅ |
| **S2** | PM2 + 9 Subagenten | ✅ |
| **S3** | PM3 + 9 Subagenten + Pre-Reg-Guard | ✅ |
| **S4** | Orchestrator + Hook `mev_tail_completed` | ✅ |
| **S5** | 27 Tests | ✅ 27/27 |

**CLAUDE.md / Version-Bump:** erledigt nach finaler Freigabe → **0.25.1** (Patch, additive Extension).

---

## 10. Explizit nicht in Scope

- Keine neue Wave-Nummer
- Kein Rewrite von Gatekeeper / Wave-39-Hook / §5.4
- Keine Mutation sealed Pre-Regs
- Keine Duplikation von Wave-40-Execution-Gates
- Keine Neuinterpretation versiegelter Bridge-Ergebnisse
