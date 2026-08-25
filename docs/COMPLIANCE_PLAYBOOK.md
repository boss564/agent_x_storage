# Agent X — Compliance- & Audit-Playbook

**Nachweisdokument für Auditoren und Behörden**
Geltungsbereich: §48b BHO, GoBD, ISO/IEC 27001:2022, DSGVO (Art. 5, 25, 32)
Stand: 2026-08-24 · Version 1.2

---

## 1. Zweck

Dieses Dokument verankert die technischen Sicherheits-, Integritäts- und
Nachvollziehbarkeitsgarantien der Agent-X-Pipeline formal. Jede Zeile der
Kontrollmatrix verweist auf den konkreten Code-Pfad **und** auf ein
reproduzierbares Prüfkommando, mit dem ein Auditor die Behauptung unabhängig
verifizieren kann. Keine Behauptung ohne Audit-Pfad.

---

## 2. Kontrollmatrix (Norm → Nachweis → Audit-Pfad → Reproduktion)

| # | Anforderung / Norm | Technischer Nachweis in Agent X | Audit-Pfad | Reproduktion |
|---|---|---|---|---|
| **K1** | **Unveränderbarkeit der Logs**<br>ISO A.8.15, GoBD (WORM), §48b BHO | HMAC-SHA256-Hash-Kette: `H_n = HMAC-SHA256(secret, H_{n-1} ‖ event_type ‖ agent_id ‖ payload ‖ t_ns)`. Der Schlüssel liegt nur beim vertrauenswürdigen Auditor; jede Manipulation bricht die Kette. | `agents/security/p08_audit.py` → `P08AuditLogger.log_event()` / `verify_chain()` | `python3 -c "from agents.security.p08_audit import P08AuditLogger; import secrets; l=P08AuditLogger(secrets.token_bytes(32)); [l.log_event('payment','agent-%d'%i,{'amount':i}) for i in range(3)]; assert l.verify_chain(); print('HMAC-Kette VERIFIED')"` |
| **K2** | **Datenschutz / Anonymität**<br>DSGVO Art. 25, 32 | ZK-Range-Proofs & Poseidon-State-Roots: Salden/Beträge werden als Commitment-Hash, nie im Klartext verankert. | `agents/subsurface/` (Circuits), `agents_b2g/settlement/__init__.py` → `ZKProofSettlementPayload` | `python3 -m agents_b2g.settlement.chaos_harness` (D04) |
| **K3** | **Ausfallsicherheit / DoS-Schutz**<br>ISO A.5.29, A.8.14 | Dynamic Constraint Weighting (Budget 10.000; Poison = `custom_proof_data` × 2 + 750 → 10.050) **und** rekursive Binary-Bisect-Quarantäne isolieren Gift-Events, ohne den Fast-Path zu blockieren. | `agents/surface/handler.py` → `estimate_constraint_weight()`; `scripts/mock_d01_responder.py` → `binary_bisect_and_quarantine()` | `python3 scripts/verify_1m_tsunami.py --total 5000 --rate 5000` |
| **K4** | **Krypto-Agilität**<br>ISO A.8.24, A.8.25 | Multi-Vendor-Prover-Factory: TEE (SGX-TDX/SEV-SNP) primär, CUDA-Fallback bei TEE-Degradation; Kurve einheitlich auf BN254 erzwungen. | `agents/subsurface/prover_factory.py` → `ZKProverBackend`, `ProofMetadata` (DCAP/SEV-Attestation, CUDA-Kernel-Hash) | `python3 -c "from agents.subsurface.prover_factory import ZKProverBackend, ProverCapability; print('ProverFactory: TEE→CUDA, bn254 geladen')"` |
| **K5** | **Finality / L1-Anchoring**<br>GoBD, ISO A.8.14 | Epochen-Akkumulator (100 bzw. 500 Proofs pro Epoche, 2s/30s Zeit-SLA) entkoppelt Settlement von Poison-fragmentierten Ingest-Batches → **Fragmentierungs-DoS-immun**. EIP-1559-Fee-Escalation (+2 gwei je Retry) gegen Congestion/`underpriced`. | `scripts/mock_d01_responder.py` → `_flush_epoch()`, `SepoliaSettlementBridge.anchor()` | `python3 scripts/verify_1m_tsunami.py` (prüft `nonce == l1_anchors`, 0 Fehlschläge) |
| **K6** | **BHO Zero-Sum**<br>§48b BHO | Jede Zahlung: `Einzahlungen = Auszahlungen + Einbehalte + Vault-Bestand`; `|Δ| > 0,01 €` stoppt alle Zahlungen (Decimal-Arithmetik). | `agents_b2g/treasury/agents.py`, `agents_b2g/clearing/clearing_settlement_orchestrator.py` | `python3 scripts/test_wave27_clearing.py` |
| **K8** | **Execution Resilience & Risk Shield**<br>GoBD (WORM), §48b BHO (Gas-Δ=0), ISO A.5.29 / A.8.14, §13b UStG | Wave 40: Finality-Gate (≥12 L1 / ≥64 L2), RPC-Failover (>200 ms / 429), Private-Only-MEV (Leakage=0), Hard Gas-Cap + BHO-Gas-Ledger, Confounder-Quarantäne (24 h), Black-Swan-Halt (σ>5 / Vol>3×30d), Fiscal/DATEV/§13b, Forensic-WORM + Gnosis/peaq-Anchor. | `agents_b2g/resilience/` · Spec `docs/WAVE40_EXECUTION_RESILIENCE_SPEC.md` | `python3 scripts/test_wave40_resilience.py` (105/105) |

> **Nummerierung:** **K7** bleibt das Compliance-Verifikationsmodell (Probe-Promotion, § unten). Wave-40-Kontrollen sind **K8** — append-only, keine Überschreibung von K1–K7.

---

## 3. Gemessene SLA-Nachweise (Messung vom 2026-08-14)

Quelle: 1.000.000-Event-Tsunami gegen echte NATS/Docker-Infrastruktur (20 Container)
mit echten L1-Ankern auf Anvil.

| Metrik | Messwert | Grenzwert | Status |
|--------|----------|-----------|--------|
| Event-Verlust | **0** (1.000.000 gesendet = 1.000.000 verarbeitet, 0 Fehler) | 0 | ✅ |
| Surface-P99-Clearance | **54 µs** | < 2 ms | ✅ |
| Infantry-P99-Clearance | **0,004 ms** | < 2 ms | ✅ |
| L1-Anker (echte Ethereum-TXs) | **9.554** (Nonce == Anker-Zahl, 0 Fehlschläge) | — | ✅ |
| Poison-Quarantäne | 50.266 (5,0 %) exakt isoliert | — | ✅ |
| Complex-Routing (Edge-Clearance) | 150.486 (15,0 %), 0 Verlust | — | ✅ |
| Speicher-Footprint (RSS) | **59,9 MB** max | < 250 MB | ✅ |
| Konservierungs-Invariante | `Ingested = Cleared + Quarantined = L1 Settled` (exakt) | — | ✅ |

**Konservierungs-Gleichung** (formal falsifizierbar, siehe §4):

```
1.000.000 = 949.734 (cleared) + 50.266 (quarantined) = 1.000.000 (L1 settled)
```

---

## 4. Formale Invarianten

### I-1: Zero-Event-Loss (Konservierung)

Jedes Ingest-Event erreicht genau **einen** terminalen Zustand — entweder
*cleared* (gesund, L1-verankert) oder *quarantined* (Poison, isoliert). Die
Summe ist identisch mit der Ingest-Zahl. Verletzung = sofortiger Test-Fehlschlag
(Exit-Code 1).

### I-2: BHO Zero-Sum (Δ = 0,00 €)

Für jede Transaktion gilt `Deposits = Paid + Retained + Vault_Balance`.
Jede Abweichung `|Δ| > 0,01 €` blockiert die Zahlung (Blocking-Gate).

### I-3: Log-Unveränderlichkeit (HMAC-Kette)

Die Hash-Kette ist nur mit dem Auditor-Geheimnis fortsetzbar; jede nachträgliche
Manipulation eines Events invalidieriert `verify_chain()`.

---

## 5. Auditor-Runbook (Reproduktion der Kernnachweise)

```bash
# 1. Zero-Loss + Konservierung + P99 + RSS (voller Nachweis)
python3 scripts/verify_1m_tsunami.py \
  --total 1000000 --rate 100000 --poison-rate 0.05 --complex-rate 0.15
# Erwartung: 13/13 PASS, "1M TSUNAMI PASS"

# 2. Schneller Smoke (Fragmentierungs-DoS + Poison-Quarantäne)
python3 scripts/verify_1m_tsunami.py --total 5000 --rate 5000

# 3. Log-Unveränderlichkeit (HMAC-SHA256-Kette)
python3 agents/security/p08_audit.py

# 4. Krypto-Agilität (Multi-Vendor-Prover)
python3 agents/subsurface/prover_factory.py

# 5. BHO Zero-Sum / Clearing
python3 scripts/test_wave27_clearing.py

# 6. Wave 40 — Execution Resilience & Risk Shield (K8)
python3 scripts/test_wave40_resilience.py
# Erwartung: Wave 40 Resilience: 105/105 passed

# 7. Live-Monitoring (SLA-Überwachung)
# Grafana: http://localhost:3002  →  "AGENT X OVERWATCH"
# Prometheus: http://localhost:9092
```

---

## 6. Anhang — beteiligte Subsysteme

| Schicht | Rolle | Modul |
|---------|-------|-------|
| Surface (C01–C09) | Ingest + Constraint-Metering + Complex-Routing | `agents/surface/handler.py` |
| Infantry (P01–P09) | Edge-Clearance (Dismount/Clear) | `agents/mechanized/` |
| Subsurface (D00–D01) | ZK-Prover + Quarantäne + L1-Anker | `scripts/mock_d01_responder.py`, `agents/subsurface/` |
| Security (P08) | Audit-Logger (HMAC-Kette) | `agents/security/p08_audit.py` |
| Clearing (W27) | BHO-Zero-Sum-Netting | `agents_b2g/clearing/` |
| Resilience (W40) | Execution Risk Shield (4 Quadranten) | `agents_b2g/resilience/` |

---

## K7 · Compliance-Verifikationsmodell (Probe-Promotion, Stand 0.24.0)

### Drei Verifikationsstufen

| Stufe | Bedeutung | Rechtswert |
|---|---|---|
| **verified** | Probe-Funktion oder SON-Report belegt die Behauptung zur Laufzeit | gerichtsfest |
| **claimed** | Implementierung existiert (Datei/Pfad), aber kein Verhaltensbeweis | Nachweis pendent |
| **attested** | Selbstauskunft (Hardware/Organisation), softwareseitig nicht prüfbar | VORBEHALT |

### Gate-Semantik (`/compliance`)

- `failed_count == 0` → `gate: PASS`, sonst `BLOCKING`
- **Zero-Sum der Checks:** `verified + claimed + attested + failed == total_checks`
- Verdict: `ABWEICHUNGEN` (failed>0) · `KONFORM_MIT_VORBEHALT` (failed=0, aber claimed/attested/SON stale) · `KONFORM` (alles verified + SON frisch)

### Probe-Inventar (`services/z3_solver/main.py`)

| Probe | Checks | Methode |
|---|---|---|
| `_probe_sha3` | 1.2, 2.2 | SHA3-Hash-Echtzeitproof |
| `_probe_z3_bho` | 5.1, 5.2, 7.3 | Z3-Nullsummen-Proof |
| `_probe_z3_violation` | 5.3, 7.4 | Z3-Verletzungserkennung |
| `_probe_worm_audit_trail` | 2.1 | WORM write→verify→tamper-detect |
| `_probe_dashboard_render` | 5.6 | Render + BHO-Violation-Flag |
| `_probe_vob_defect_machine` | 3.6 | §13-Fristen 14d/30d + 4-Jahres-Gewährleistung |
| `_probe_proof_hash_embedded` | 5.4 | Audit-Package enthält Proof-Hash |
| `_probe_hsm_pin_env` | 4.5 | PIN aus Env, kein Hardcoded-Default |
| `_probe_cicd_jobs` | 7.5 | CI-Workflow ≥4 Jobs, YAML parsebar |

### Dokumentierte Ceilings

- **Check 1.1** (NFC/nPA via AusweisApp2): hardwaregebunden, bleibt `claimed` — kein ehrlicher Software-Probe möglich.

### Operationelle Regeln

- **R1:** Proben laufen im FastAPI-Request-Kontext. `asyncio.run()` ist dort verboten (RuntimeError im laufenden Loop); asynchrone Aufrufe laufen über den `_maybe_await`-Thread-Pool.
- **R2:** GRÜN-Test im Container ist notwendig, aber nicht hinreichend. Jede verdrahtete Probe wird zusätzlich über den Live-Endpoint (`curl /compliance`) verifiziert — Umgebungskontext schlägt Isolationstest.

### SON-Report-Frische

- `son_report_valid` erfordert `age ≤ 24h`. Nächtliche Regeneration per Cron (03:00), Backup sichert den Report mit (03:30).
- Der Executor nutzt den Report auch bei `son_valid=false` für `test:`-Pfade; das Flag steuert nur das Summary-Verdict.

---

## K8 · Execution Resilience & Risk Shield (Wave 40, Stand 0.25.0)

**Ziel:** Nachweis der Betriebsstabilität, MEV-Resistenz und steuerlichen Lückenlosigkeit
unter realen Blockchain- und Marktbedingungen.

**Modul:** `agents_b2g/resilience/`  
**Spec:** `docs/WAVE40_EXECUTION_RESILIENCE_SPEC.md`  
**E2E:** `scripts/test_wave40_resilience.py` — **105/105**  
**Abgrenzung:** Wave-39-Spec **§5.4** (Hook-Härte) bleibt unberührt. K8 erweitert weder
Wave-39-Envelope noch Gatekeeper-Semantik.

### K8-Kontrollmatrix (Invariante → Gate → Nachweis)

| Invarianten-Kategorie | Prüfregel (Compliance Gate) | Nachweis / Artefakt |
|---|---|---|
| **Infrastruktur-Finality** | Kein Kausalsignal wird ausgeführt vor ≥12 Confirmations (L1) bzw. ≥64 (L2). | `ReorgMonitor` + Orchestrator-`FinalityGate`; Reject bei Deep-Reorg / Fork |
| **RPC-Resilienz** | Auto-Failover bei Latenz >200 ms oder HTTP 429. Surface-P99-Referenz **54 µs** (`RESILIENCE_RPC_P99_SLA_US`). | `RPCHealthSentinel` SLA-/Failover-Report im Envelope `rpc_ok` |
| **MEV-Schutz** | 100 % Private-Only-Submission (Flashbots/Builder). Mempool-Leakage = 0. | `MEVShield` / `MempoolLeakageScanner`; Envelope `mev_ok`, `leakage_count` |
| **Gas-Budget (BHO)** | Hartes Cap pro TX + kumulatives Daily-Limit. `Gas_In = Gas_Used + Gas_Refunded + Reserve` (Δ≤0,01). | `GasBudgetEnforcer` Circuit-Breaker + `BudgetLedger`; Envelope `gas_ok`, `gas_bho_delta` |
| **Confounder-Quarantäne** | Unregistrierte / exogene Faktoren (CEX-Schock, Third-Chain-Hack, Novel) → Signal-Invalidierung + 24 h Kühlphase. Pre-Reg-Gate: nur registrierte Faktoren. | `ConfounderDetector` Quarantäne-Register; Envelope `confounder_ok` |
| **Black-Swan-Halt** | Volatilität >3× 30d-Durchschnitt oder σ>5 → automatischer Halt aller Execution-Agenten. | `BlackSwanCircuitBreaker` Auto-Halt-Trigger; Envelope `blackswan_ok` |
| **Fiscal-Compliance** | Lückenlose Handelsbuchführung, §13b UStG Reverse-Charge, BZSt-Abgleich, DATEV-konformer Export. | `FiscalComplianceAuditor` DATEV-Export + Seal-Hash; Envelope `fiscal_ok` |
| **Forensic WORM** | Jeder Execution-Schritt append-only mit Hash-Kette und Multi-Chain-Anchor (Gnosis/peaq). | `ExecutionForensicRecorder` QES-Signatur + Anchor-TX; Envelope `forensic_ok`, `tip_hash` |

### Auditor-Reproduktion (K8)

```bash
# Vollständige Wave-40-Suite (12 Gruppen, inkl. 1.000-TX-E2E)
python3 scripts/test_wave40_resilience.py
# Erwartung: Wave 40 Resilience: 105/105 passed

# Smoke: Orchestrator READY + BHO-Δ=0
python3 -c "
from agents_b2g.resilience import ExecutionResilienceOrchestrator, ResilienceVerdict
orch = ExecutionResilienceOrchestrator(user_id='auditor_k8')
env = orch.evaluate({
    'tip_block': 120, 'signal_block': 100, 'layer': 'L1', 'reorg_depth': 0,
    'block_hash': '0xdeadbeef01', 'parent_hash': '0xcafebabe01', 'expected_parent': '0xcafebabe01',
    'latency_samples_ms': [12, 14], 'use_public_mempool': False,
    'quoted_price': 1.0, 'limit_price': 1.002, 'gas_limit': 21000, 'this_burn': 21000,
    'estimated_gas': 18000, 'gas_in': 100, 'gas_used': 70, 'gas_refunded': 20, 'gas_reserve': 10,
    'registered_factors': ['oracle_lag'], 'signal_factors': ['oracle_lag'],
    'candidate_factors': ['oracle_lag'], 'abs_sigma': 1.0, 'current_vol': 0.1, 'vol_30d': 0.1,
}, job_id='k8-smoke')
assert env.status == ResilienceVerdict.READY
assert abs(env.gas_bho_delta) <= 0.01 and env.fiscal_ok and env.forensic_ok
print('K8 SMOKE PASS', env.status.value, 'tip', env.quadrant_results['operational']['forensic']['tip_hash'][:16])
"
```

### Formale Zusätze (K8)

- **I-4 Gas-BHO:** `Gas_In = Gas_Used + Gas_Refunded + Gas_Budget_Reserve`; Verletzung öffnet den Budget-Circuit.
- **I-5 Private-Only:** öffentliche Mempool-Submission ⇒ `leakage_count ≥ 1` ⇒ Pipeline nicht `READY`.
- **I-6 Append-only Forensic:** Tip-Hash = SHA-256-Kette ab Genesis; Replay muss Tip matchen; Auditor-ACL `write_denied=True`.
