# RaaS — Multi-Tenant Prefilter M1 Proto v0

**Status:** PROTO v0 (2026-08-27) · **implementiert** (Pfad · Envelope · Screen · E2E) · Map-Schuld `docs/RaaS_P9_MAPPING_v3.md` §4  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · kein DEFAULT_ON  
**Nicht:** Wave-8-Isolator verdrahten · M2-Shared-Modell · Cross-Party-Envelopes · DEFAULT_ON  
**Make:** `raas-prefilter-m1-isolation-screen` · `raas-prefilter-m1-e2e`  
**Basis:** v3 §4.1–§4.3 · Bus-Expansion §4.3 (Referenz A · Haltepunkt) ·
`prototypes/raas_hybrid_shell/prefilter_backlog.py` · `services/raas_portal/`

M2 bleibt **abgelehnt**: „schützt alle Mandanten“ wäre ein falsches Versprechen —
ein Shared-Prefilter *ist* der Leckkanal. Diese Ablehnung ist Schuld-Dokumentation,
keine technische Schwäche.

---

## 1. Ziel (eine Zeile)

**Pro Mandant eigener Prefilter-Pfad + Envelope nur für den Einreicher;
Screen beweist, dass M1 den Cross-Tenant-Informationsfluss stoppt, den M2 öffnet.**

---

## 2. Ist-Zustand (Wahrheit vor Optik)

| Schicht | Heute |
|---------|--------|
| Portal | `tenant_id` → `{data_root}/{tenant_id}/…` (Verzeichnis-Schuld, §4.1) |
| Prefilter | ein globales `PREFILTER_MODEL_PATH` (Default `models/prefilter/prefilter_gbt.pkl`) |
| Facade | `SupranodeFacade(tenant_id=…)` · `PREFILTER_ENABLED` Default false |
| Envelope/Zertifikat | `tenant_id` im Cert · keine `subjects[]`-Schuld · kein Cross-Tenant-Screen |
| Referenz A | 8 Holdouts, Claim Mittel±σ — **nicht** mandantengebunden |

---

## 3. Bau-Schritte (Reihenfolge bindend)

### 3.1 M1-Pfad — Prefilter je Mandant

```text
{data_root}/{tenant_id}/prefilter/
  prefilter_gbt.pkl              # Gewichte nur dieses Mandanten
  prefilter_gbt.pkl.meta.json
  manifest.json                  # optional: train corpus hash, freeze ref
```

| Regel | Inhalt |
|-------|--------|
| Resolve | `model_path = data_root / tenant_id / "prefilter" / "prefilter_gbt.pkl"` |
| Fallback | fehlt Artefakt → **FIFO** (wie heutiger Outage-Pfad) · kein stilles Global-Modell |
| Env | `PREFILTER_MODEL_PATH` nur noch Dev-Override; Produktion M1 = tenant-Pfad |
| Train | nur Läufe/Synth **dieses** `tenant_id`; kein Mix A∪B |
| Eval | bei Queue-Claims unter Multi-Tenant: Referenz-A-Disziplin **pro** Mandanten-Artefakt |
| Verbot | ein Prozess lädt Mandant-A-Gewichte für Requests von B |

Pilot-Ort: `prefilter_backlog.py` + Facade — `tenant_id` bereits am Gateway.

**Exit:** Request mit `tenant_id=A` liest nie `…/B/prefilter/…` (Unit + Pfad-Assert).

### 3.2 Envelope-Schuld — nur Einreicher

| Feld / Regel | Inhalt |
|--------------|--------|
| `tenant_id` | Pflicht · = Run-Owner |
| `subjects` | genau `[{ "role": "submitter", "tenant_id": <run.tenant_id> }]` |
| `counterparties_mentioned` | **immer leer** in diesem Proto (oder Feld fehlt) |
| Cross-Tenant-Inhalt | Fail-Closed: Export **verweigern**, wenn Stress/Summary fremde `tenant_id` enthält |
| Ausgabe | Envelope/Cert nur an Aufrufer mit Matching-`tenant_id` (Query-Param = Run-Owner) |

Pilot-Ort: `services/raas_portal/exporter.py` (+ GET Envelope/Cert).

**Exit:** Cert für Run(A) enthält keine Keys/IDs von B; Abruf mit `tenant_id=B` → 404/deny.

### 3.3 Proto-Screen — Cross-Tenant-Leckkanal (M1 vs. M2)

Synthetischer Vergleich, **kein** Live-Kunden-Train:

| Arm | Setup | Erwartung |
|-----|--------|-----------|
| **M2-Sim** | Ein Modell auf Synth-A trainiert, Score auf Holdout-B | messbarer Informationsfluss (Score/Rank-Verschiebung vs. Blind-Baseline) |
| **M1** | Modell-A nur auf Synth-A; Modell-B nur auf Synth-B; A scored B-Holdout mit **B-Gewichten** | kein Train-Signal von A in B-Scores |

| Metrik (Skizze) | Pass wenn |
|-----------------|-----------|
| Rank-/Score-Korrelation Train-A-Features → Scores-unter-B | unter vorab gesetzter Schwelle **nur** im M1-Arm |
| Verdict | `PREFILTER_M1_ISOLATION_PASS` / `_FAIL` |

Artefakt: `models/prefilter/prefilter_m1_isolation_screen.json` (gitignored) ·
Runner Intent: `scripts/screen_prefilter_m1_isolation.py` · `make raas-prefilter-m1-isolation-screen`

M2-Arm nur als **Negativkontrolle** im Screen — nicht als Betriebsmodus.

### 3.4 E2E Smoke — GoBD-Audit-Trail mit M1

```text
tenant=A: enable prefilter (A-weights) → backlog reorder → core run → WORM + Cert
tenant=B: parallel/FIFO oder B-weights → eigener WORM-Pfad
Assert:   worm/cert paths disjoint · cert.subjects submitter-only · no shared pkl read
```

Make Intent: Erweiterung `raas-gateway-prefilter-cutover` oder
`scripts/test_prefilter_m1_e2e.py` → `PREFILTER_M1_E2E_PASS`.

---

## 4. Nicht in diesem Proto

| Thema | Haltung |
|-------|---------|
| Wave-8 AES/DB-Isolator | separate Ebene (v3 §4.1) — **nach** M1-Pfad-Schuld |
| DEFAULT_ON | weiter gesperrt (Bus-Expansion Haltepunkt) |
| Shared Prefilter (M2) | **abgelehnt** — Screen darf ihn nur als FAIL-Referenz zeigen |
| Aussagen über Nichteinreicher | **verboten** bis Policy+Proof (v3 §4.3) |
| Public-Ingest Pfad 1 | Pause; wenn doch: Train-Corpus je Mandant |

---

## 5. Abnahmekette

```text
3.1 M1-Pfad Resolve + FIFO-Fallback
  → 3.2 Envelope subjects/deny
    → 3.3 Isolation-Screen PASS (M1 vs M2-Negativ)
      → 3.4 E2E WORM/Cert PASS
        → erst dann: Multi-Schwarm-Bau-Claim „M1-Schuld im Proto“
```

Kein Schritt überspringen. Screen FAIL → kein E2E-Grün umdeuten.

---

## 6. Verweise

| Dokument / Code | Rolle |
|-----------------|-------|
| `docs/RaaS_P9_MAPPING_v3.md` §4 | Policy: Verzeichnis · M1 · Envelope-Isolation |
| `docs/RaaS_BUS_EXPANSION_v0.md` §4.3 | Referenz A · Prefilter-Haltepunkt |
| `prototypes/raas_hybrid_shell/prefilter_backlog.py` | heutiger Global-Pfad |
| `services/raas_portal/exporter.py` · `store.py` | Cert / tenant dirs |
| `docs/RaaS_P9_MAPPING_v1.md` §6 | Safety Envelope Schema |
