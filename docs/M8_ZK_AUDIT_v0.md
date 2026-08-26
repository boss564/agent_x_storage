# M8 — ZK Soundness Audit v0 (SNARK → STARK)

**Status:** **AUDIT ABSCHLOSSEN** — 2026-08-26 · Migration **nicht relevant** in aktueller Architektur  
**Freigabe:** Inventur → Klassifikation → Priorität → Aufwand · **nicht** STARK-Implementierung  
**Threat-Anker:** `docs/THREAT_MODEL_POST_QUANTUM_v0.md` §4.3 / Roadmap M8  
**Commits Kontext:** M7 `829e6b00` · M9 `e730f14e`

```text
Typ:      Audit (Analyse) — abgeschlossen
Befund:  Keine SNARK-Circuits im Repo · Groth16 = Label/Mock (+ S6 Pairing-Logik ohne VK)
          Produktiver BHO-Nachweis = Z3 SMT (nicht ZK) → Shor-SNARK-Soundness trifft nicht
M8-Migration: NICHT RELEVANT solange keine pairing-SNARKs produktiv gebunden werden
Policy:   Prio 0 bleibt — keine neuen Langzeit-Invarianten an pairing-SNARKs
Architektur-Empfehlung (falls später ZK kommt):
          STARK off-chain · on-chain nur Commitment / Nullifier / Root
```

---

## 0. Meta-Befund (ehrlich)

| Frage | Ist-Zustand im Repo |
|-------|---------------------|
| Circom / R1CS / `.zkey` / `.ptau` | **Keine** (`.wasm` = Paratrooper F01–F03, **kein** zk) |
| Echte Groth16-Proofs in Python | **Nein** — strukturelle / SHA256-Mocks mit Label `Groth16_BN254` |
| On-chain Pairing-Logik | **S6 echt** (Precompile `0x08`, vollständiger 24-Wort-Input) — **VK fehlt** |
| STARK/FRI | **Simuliert** — `zk_compression.py` (SHA3 + FRI-Runden-Label) |
| Echter BHO-Beweis heute | **Z3 SMT** (`services/z3_solver`) — **kein** ZK-Circuit |

**Konsequenz:** Die Threat-Model-Annahme „Z3-Schaltkreise / produktive Groth16-SNARKs
müssen migriert werden“ trifft **nicht** zu. M8 als Migrationsprojekt ist in der
**aktuellen** Architektur **nicht relevant**. Was bleibt:

1. **Policy Prio 0** — keine neuen pairing-only Langzeit-Gates (kostenlos, sofort).  
2. **S6** — Pairing-Verifier ist schon verdrahtet; sobald eine VK gesetzt wird, ist
   die Fläche **voll** Shor-soundness-exponiert → VK/Proof-Pfad nur mit PQ-Strategie.  
3. **Z1** — BHO bleibt Z3; Angriffsfläche = Artefakt-Signatur → **PQC (M5)**, nicht M8.  
4. **S4 Label-Lüge** — Kommentar behauptete „arkworks / valid“, Code hasht → korrigiert.

---

## Phase 1 — Inventur (Circuit / Beweisflächen)

### 1.1 Soundness-nahe Settlement-Pipeline

| ID | Ort | Label heute | Realität | Rolle |
|----|-----|-------------|----------|-------|
| **S1** | `agents_b2g/settlement/__init__.py` | `Groth16_BN254` / PLONK | Strukturcheck `pi_a/b/c`; injizierbarer `_pairing_engine` | D01→C09 Settlement, Nullifier, State-Root |
| **S2** | `agents_b2g/protocol.py` | `Groth16_BN254`, ProtoGalaxy-Fold | Payload-Typen / Demo | NATS ZK-Settlement, Tick-Drift |
| **S3** | `scripts/mock_d01_responder.py` | mock Groth16 | Explizit Mock + Hash | Last-/Pipeline-Tests |
| **S4** | `agents/subsurface/prover_factory.py` | bn254 TEE/CUDA/CPU | **SHA256-Mock**; früher Kommentar „arkworks / valid“ (**gefährliche Beschriftung**, korrigiert) | Multi-Backend-Abstraktion |
| **S5** | `agents/surface/handler.py` | `dummy_pairing` | Flag in Telemetrie | Surface-Durchsatz |
| **S6** | `shadow_contract_pilot/contract/ValhallaVerifier.sol` | Groth16 BN254 | **Echte** Pairing-Verifikation (`staticcall` 0x08, π-Negation, 24-Wort-Input); **VK Platzhalter** | On-chain Verify + Nullifier — **pairing-ready** |
| **S7** | `shadow_contract_pilot/contract/ProtoGalaxyVerifier.sol` | Folded Decider | Nur Hash/non-empty — **kein** Pairing | Epoch-State-Root-Anker (schwächer als S6) |

### 1.1.1 Sonderfund S4 — Mock mit Lügen-Kommentar

```text
Vorher:  "# Pure Python/arkworks CPU proof — slow but valid"
Ist:     return hashlib.sha256(witness + state).digest()
```

Das ist die gefährlichste Mock-Sorte: beim Lesen wirkt der Pfad kryptographisch
sound. Unabhängig von jeder M8-Migration: Kommentar korrigiert auf
`ENGINEERING MOCK — not arkworks, not a valid SNARK`.

### 1.2 Privacy / Reputation (nicht BHO-Gate)

| ID | Ort | Label heute | Realität | Rolle |
|----|-----|-------------|----------|-------|
| **P1** | `agents_b2g/wallet/smart_wallet_orchestrator.py` (`ZKPrivacyShield`) | Groth16 | Hash als `zk_proof` | Salden/TX-Shield (Demo) |
| **P2** | `agents_b2g/public_portal/agents.py` (`ZKPrivacyShield`) | „ZK“ im Namen | **DSGVO-Maskierung, kein ZK** | Wave-15 Bürgerportal |
| **P3** | `agents_b2g/valhalla/valhalla.py` | SNARK-Gruppen | SHA256-Mitgliedschaft | Anonyme Honor-Stamps |
| **P4** | `agents_b2g/survival/subagents/rationing.py` | Groth16/STARK-Label | SHAKE256-Mock | ZK-eID-Rationierung |

### 1.3 PQ-Pfad / STARK-Anker (Wave 33)

| ID | Ort | Label heute | Realität | Rolle |
|----|-----|-------------|----------|-------|
| **T1** | `agents_b2g/survival/subagents/zk_compression.py` | STARK/FRI SHA3 | FRI-Runden **simuliert** | Off-Grid State-Kompression |
| **T2** | `agents_b2g/survival/subagents/state_sync.py` | optional STARK | nutzt T1 | Sync-Integrität |
| **T3** | `scripts/test_wave33_survival.py` | STARK gen/verify | Regression auf Simulation | Test |

### 1.4 Z3 SMT (explizit **außerhalb** M8-SNARK-Scope)

| ID | Ort | System | Hinweis |
|----|-----|--------|---------|
| **Z1** | `services/z3_solver/main.py` | **echter** z3-solver | BHO-Invariante UNSAT — **behalten**; M8 ersetzt das nicht |
| **Z2** | Clearing / CertiK / SimChain „Z3_PROOF“ | oft SHA256-Label | nicht mit Z1 verwechseln |

### 1.5 PoPW / Shadow / Tendering (Hash-Stubs)

| ID | Ort | Realität |
|----|-----|----------|
| **H1–H4** | Telemetry `PoPWProofGenerator`, Shadow Milestone, Tendering `generate_zkp`, Execution ZKP-Wrap | Merkle/Hash — **kein** pairing SNARK |

**Inventur-Summe:** 7 Settlement-nahe Flächen (S1–S7) · 4 Privacy (P1–P4) ·
3 STARK-Anker (T1–T3) · Z3 separat · diverse Hash-Stubs ohne Circuit.

---

## Phase 2 — Klassifikation (Kritikalitäts-Matrix)

| ID | Soundness-Klasse | Warum | Shor-Schaden |
|----|------------------|-------|--------------|
| **S6** | **PAIRING-READY (VK-gated)** | Verifier-Logik **vollständig**; ohne VK noch wirkungslos, mit VK sofort pairing-exponiert | Soundness-Bruch sobald produktiv |
| **S1, S2** | **LABEL / MOCK** (Settlement-Pfad) | Sollen Transitions schützen; heute Struktur/Hash | Niedrig bis echtes Format |
| **S7** | Scaffold (Hash only) | **Kein** Pairing — schwächer als S6 | Niedrig |
| **S3–S5** | Engineering / Mock | S4 = Mock + (korrigierte) Beschriftung | Niedrig |
| **Z1** | **BHO-kritisch, nicht SNARK** | Arithmetische Invariante | Shor trifft Z3-SMT nicht; PQC für Artefakt-Signatur |
| **P1, P3, P4** | **PRIVACY** | Salden / Identität / Honor | Vertraulichkeit, nicht Kassen-Fälschung |
| **P2** | Privacy **ohne ZK** | DSGVO — kein M8-Circuit | — |
| **T1–T3** | Integrität Off-Grid | PQ-freundlich spezifiziert, Simulation | Optionaler Ausbau |
| **H\*** | Ops-Integrität | PoPW-Hashes | Kein pairing-Risiko |

```text
Produktiver BHO:     Z1 (Z3 SMT) — nicht M8
Pairing-Falle:       S6 (Logik echt, VK fehlt) — strenger als S7
Keine Circuits:      nichts zu „migrieren“ im Circom-Sinne
```

---

## Phase 3 — Priorität (nach Audit-Befund)

| Prio | Maßnahme | Status |
|-----:|----------|--------|
| **0** | Keine neuen Langzeit-Invarianten an pairing-SNARKs | **bindend / sofort** |
| **0b** | S4-Kommentar-Lüge korrigieren | **erledigt** (dieser Stand) |
| **0c** | S6: keine produktive VK ohne PQ-/STARK-ADR | Policy |
| **—** | SNARK→STARK Circuit-Migration | **NICHT RELEVANT** (keine Circuits) |
| **opt.** | Falls später ZK: T1 produktiv → S1 off-chain STARK → on-chain nur Root | eigenes WP nach ADR |
| **M5-Nähe** | Z1-Artefakte PQC signieren | parallel, nicht M8 |

**S6 ≠ S7 in der Priorität:** S6 ist die einzige Fläche mit **echter**
Pairing-Verifikation. S7 bleibt Hash-Scaffold. Nicht in einem Bullet zusammenwerfen.

---

## Phase 4 — Aufwand (nur falls ZK später eingeführt wird)

| Arbeitspaket | Aufwand | Bemerkung |
|--------------|--------:|-----------|
| ADR Settlement-Beweisformat | 1–2 W | Voraussetzung |
| T1 echte FRI-Lib | 6–12 W | optional |
| S1 an T1 | 4–8 W | nach T1 |
| S6 → Root/L2 statt L1-FRI | 8–16 W | Gas: ~230k Pairing vs. FRI 10²–10³ KB |
| Groth16 „fertigmachen“ | **vermeiden** | erhöht Shor-Schuld |

**Architektur (bestätigt):** STARK **off-chain**; on-chain nur Commitment /
Nullifier / Root — nicht jeden FRI-Proof gasen.

---

## Audit-Verdict

```text
M8 Circuit-Migration:  NICHT RELEVANT (aktueller Stand)
Grund:                 keine SNARK-Circuits; BHO = Z3 SMT
Bleibt wirksam:        Prio 0 Policy · S6 VK-Sperre · S4 Wahrheits-Kommentar · Z1≠M8
Nützlichkeit:          verhindert Wochen Circuit-Arbeit am falschen Format
```

---

## Verweise

| Ressource | Rolle |
|-----------|-------|
| `docs/THREAT_MODEL_POST_QUANTUM_v0.md` §4.3 | Threat + M8-Status |
| `shadow_contract_pilot/contract/ValhallaVerifier.sol` | S6 Pairing-ready |
| `shadow_contract_pilot/contract/ProtoGalaxyVerifier.sol` | S7 Hash-only |
| `agents/subsurface/prover_factory.py` | S4 Mock (Kommentar korrigiert) |
| `services/z3_solver/main.py` | Z1 BHO SMT |

---

## Änderungsprotokoll

| Datum | Änderung |
|-------|----------|
| 2026-08-26 | Audit v0 — Inventur · Matrix · Priorität · Aufwand |
| 2026-08-26 | Verdict **NICHT RELEVANT**; S6≠S7; S4 Label-Lüge; Threat-Model-Korrektur |
