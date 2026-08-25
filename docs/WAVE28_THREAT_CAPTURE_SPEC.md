# Wave 28 Threat Capture — Spezifikation (Variante A)

**Status:** Bindend für Erfassung in `wave28_threat_signatures`  
**Charakter:** Defensiv · objektiv (nicht normativ stigmatisierend)  
**Schema:** `agents_b2g/defense/wave28_threat_engine.sql`  
**Leitplanken:** keine Gewinn-Umleitung · kein Clone-Architect · keine normative Stigmatisierung

---

## 1. Was „objektiv“ hier heißt

„Objektiv“ bedeutet **nicht** „wertfrei ohne Designentscheidung“. Es bedeutet:

1. Erfasst werden nur **messbare On-Chain-/Protokoll-Metriken**, keine Zuschreibungen
   zu Personen, Intent oder Moral.
2. Schwellen sind **vorab festgelegt** (diese Spez), nicht ad-hoc nach Blick auf eine Adresse.
3. Labels (`pattern_label`) sind **deskriptiv** (z. B. `high_priority_fee_burst`), nicht
   pejorativ (kein `attacker`, `bad_actor`, `sybil_person`).

Die Wahl der Schwellen ist eine Designentscheidung und wird hier dokumentiert, damit
sie nachprüfbar und änderbar bleibt (Änderungen = Spec-Version, nicht stiller Code-Pfad).

---

## 1.1 Tenant-Modell: globale Schwarm-Immunität

**Entscheidung (bindend):** Signaturen, Embeddings und Incidents sind
**mandantenübergreifend** sichtbar. Ein erkanntes Muster schützt alle Mandanten
(Wave-28-Schwarm). Adapter setzen **keinen** `tenant_id`-Filter auf Queries.

| Artefakt | Isolation | Begründung |
|----------|-----------|------------|
| `wave28_threat_signatures` | global | kollektives Muster-Gedächtnis |
| `wave28_behavior_embeddings` | global | ANN über Pseudonyme, kein PII im Standardpfad |
| `wave28_causal_incidents` | global | Audit der defensiven Kopplung |
| `wave28_eoa_raw_vault` | **tenant-isoliert** (`tenant_user_id`) | Roh-Adresse = Identifikator; nur bei Incident-Response |

**Provenance (kein Filter):** `observed_by_user_id` speichert, welcher Mandant die
Beobachtung eingespeist hat — nur Audit, nicht Sichtbarkeitsgrenze.

Damit bleibt Multi-Tenancy für PII (Wave 8 / Raw-Vault) gewahrt, ohne den
Schwarm-Lerneffekt zu opfern. Pseudonym-Pfad ist der Default; Raw-Auflösung
nur über Vault + `tenant_user_id`.

---

## 1.2 Orchestrierung und Adapter-DI

Adapter werden in **Subagenten** injiziert (nicht in neue Agenten):

| Adapter | Subagent | Wirt |
|---------|----------|------|
| `RadarThreatStoreAdapter` | `swarm_signature_database` | SwarmDetectionRadar |
| `LearningEmbeddingAdapter` | `feature_extractor` / `model_version_manager` | SwarmLearningAdapter |
| `ClassifierIncidentAdapter` | `confidence_scorer` / Gate-Pfad | ThreatClassifierEngine |

Lebenszyklus (bindend): `SENSITIVITY_RAISED` → K-Fold/S(τ)-Proxy → Gatekeeper-Coupling →
`SENSITIVITY_CLEARED`. `SensitivityLifecycle` erzwingt 1:1-Paarung; offene Raises
sind ein Orchestrierungsfehler.

Test: `python3 scripts/test_wave28_threat_engine.py` (MemoryBackend; optional
`WAVE28_THREAT_DSN` für Live-pgvector).

---

## 2. Erfassungskriterien (v1.0)

| Feld | Erfasst wenn | Schwelle v1.0 | Nicht erfasst |
|------|--------------|---------------|---------------|
| `latency_ms_p50` / `p99` | Mempool→Inclusion-Latenz im Beobachtungsfenster | Fenster ≥ 5 min, ≥ 3 TXs | Einzel-TX ohne Fenster |
| `gas_priority_gwei` | `maxPriorityFeePerGas` (oder Äquivalent) | > 3× Median der letzten 100 Blocks derselben Chain | Absolute „teuer“-Urteile |
| `interaction_type` | Event-/Call-Klasse aus Allowlist | siehe §2.1 | Beliebige Calldata-Heuristik ohne Allowlist |
| `tx_count` | Anzahl TXs der Pseudonym-Adresse im Fenster | Fenster 5–60 min | Lebenszeit-Historie |
| `peer_cluster_size` | Adressen mit korrelierter Occupancy (±1 min) | ≥ 3 Peers | Soziale Graph-Labels |
| `entropy_score` | Shannon-Entropie über Interaktionstypen im Fenster | rein deskriptiv, 0–1 | „verdächtig“-Schwelle als Urteil |

### 2.1 Allowlist `interaction_type`

Nur diese Werte (weitere nur per Spec-Amendment):

- `bridge_transfer`
- `oracle_update`
- `liquidation_call`
- `dex_swap`
- `intent_fill`
- `contract_create`
- `other_allowlisted` (explizit freigegebene Signaturen)

---

## 3. Pseudonymisierung (DSGVO)

- Radar und Learning arbeiten auf `eoa_pseudonym = SHA-256(lower(address))`.
- Roh-Adresse nur optional in `wave28_eoa_raw_vault`, getrennt, bei konkretem
  Handlungsbedarf (Incident-Response), nicht für Routine-Ähnlichkeitssuche.

---

## 4. Defensive Kopplung (kein Angriff)

```
Muster (Signature) → optional SENSITIVITY_RAISED (auditiert)
                   → bei S(τ) ≤ 0: Gatekeeper BLOCKED + block_cause
                   → sonst RELEASED
```

- `SENSITIVITY_RAISED` / `SENSITIVITY_CLEARED` **müssen** in `wave28_causal_incidents`
  stehen (kein stilles Targeting).
- `BLOCKED` ohne `block_cause` ist schema-seitig verboten (Wave-38-Invariant).
- Keine Umleitung von Gas-/MEV-Wert; Aktion = Schutz des eigenen Schwarm-Kapitals
  (z. B. Dispatch stoppen), nicht Extraktion.

---

## 5. Retention

| Stufe | Default | Wirkung |
|-------|---------|---------|
| Soft | 30 Tage Inaktivität | `is_active = FALSE` |
| Hard | 365 Tage | physisches Löschen (Partitionen / Rows) |

Aufruf: `SELECT * FROM wave28_apply_retention(30, 365);`

---

## 6. Embedding-Kompatibilität

Ähnlichkeitssuche **nur** innerhalb gleicher `(embedding_model, embedding_dim)`.
Default v1.0: `all-MiniLM-L6-v2`, dim `384`. Modellwechsel = neue Spec-Version und
kein Cross-Model-ANN.

---

## 7. Version

| Version | Datum | Änderung |
|---------|-------|----------|
| 1.0 | 2026-08-23 | Erstfassung zu Variante A + Schema |
| 1.1 | 2026-08-23 | §1.1 Tenant: global swarm + tenant-isoliertes Raw-Vault |
| 1.2 | 2026-08-23 | §1.2 DI + SENSITIVITY lifecycle + Testskript |
