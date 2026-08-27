# RaaS — Bus & Sub-Swarm Expansion Gate v0

**Status:** GATE v0 (2026-08-27) · bindend vor jeder Bus-Migration  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false`  
**Serie:** `docs/STATEFUL_GRAPH_SERIE_v0.md` (topology FALSIFIED · async_verify CONFIRMED unter Pipeline-Modell)  
**Basis:** `docs/RaaS_HYBRID_KI_ROADMAP_v0.md` · `docs/RaaS_P9_MAPPING_v2.md` · `docs/RaaS_P9_MAPPING_v3.md` · `docs/RaaS_SUPRANODE_v0.md`

Roh-Ausbaustufen (Core-Bus → Gateway-Bus → Inter-Swarm) sind **plausibel**,
aber Stufe 1 berührt zwei **gemessene** Eigenschaften der Serie. Dieses Dokument
legt die Reihenfolge fest, bevor Code den Ring oder „Echtzeit“ beansprucht.

---

## 1. Was der Roh-Pfad richtig sieht

| Idee | Haltung |
|------|---------|
| NATS JetStream / Queue-Groups | Kann Sticky-/1-von-N-Semantik abbilden — **wenn so entworfen** |
| Gateway/Shell-Bus hinter D1–D4 | Passt zu Facade + `DSuiteEnforcer` (layer 2 app) |
| Sub-Schwärme als steckbare Module | Passt zu v2 Overlay (Red = Szenario, Sandbox) |
| Sandwich/MEV **simulieren** | Charter-OK unter v2 / D2 |

---

## 2. Drei Korrekturen (bindend)

### 2.1 Bus-Topologie kann den Ring zerstören

Topology-Screen (`HYPOTHESIS_FALSIFIED`):

| Graph | ⟨k⟩ | Margin | Verdict |
|-------|-----|--------|---------|
| sparse Ring | 1,0 | ≈0,52 | `STRUCTURE_RELATIONAL` |
| complete | 8,0 | ≈0 | `STRUCTURE_BREAKS` |
| hub | 1,8 | ≈−0,11 | `STRUCTURE_BREAKS` |

Ein Bus, auf dem jeder publiziert und viele subskribieren, ist strukturell
**complete**. Im Protokoll existiert `receiver == "broadcast"`
(`agents_b2g/protocol.py`) — Migration darauf wäre vorhersagbar negativ.

**Rettung:** NATS **Queue-Groups** = 1-von-N (wie `StickySelector`), nicht Fan-out.
Das ist eine **Entwurfsentscheidung**, keine NATS-Eigenschaft.

**Gate vor Stufe 1:** Topologie-Screen gegen das **tatsächliche
Zustellmuster** des geplanten Bus (Subjects + Queue-Groups). Verdict muss
zeigen: Muster zählt als Ring (⟨k⟩≈1 / 1-von-N), nicht als complete.
Dauer: Minuten, nicht Wochen.

**Runner:** `scripts/test_topology_bus_queuegroups.py` · `make raas-bus-topology-gate`  
**Messung (2026-08-27, NATS `nats-gate0` :4222):**

| Muster | exact_one | multi | mean receivers | Lesart |
|--------|-----------|-------|----------------|--------|
| Queue-Group (pro Kante) | 270/270 | 0 | 1,0 | **Ring-like 1-von-N** |
| Broadcast-Subscribe (Kontrolle) | 0/270 | 270 | 3,0 | **complete-like Fan-out** |

Verdict: **`QUEUEGROUP_RING_PASS`** · `gate0=PASS` · `stage1_allowed=true`  
Bindung: Stufe 1 **nur** mit Queue-Group-Subjects — Broadcast als Steuerpfad bleibt gesperrt.  
Artefakt: `prototypes/v2_stateful_graph/bus_topology_gate_results.json`

### 2.2 „Kern bleibt unangetastet“ gilt für Stufe 1 nicht

Stufe 1 ersetzt synchrone Aufrufe durch asynchrone Events — das **ist** der Kern.

`async_verify` (`HYPOTHESIS_CONFIRMED`, Margin_Δ=0, ≈4× tps) gilt für ein
**Pipeline-Parallelitätsmodell** mit **identischer Ereignisreihenfolge** und
gemessenen Per-Txn-ms — **nicht** für Netzlatenz und Umordnung unter NATS.

Dokumentation darf Stufe 1 nicht als „Overlay ohne Kernänderung“ verkaufen.

### 2.3 „Echtzeit-Insolvenz-Prüfung“ — Live-Messung liegt vor

`wall_clock_verify` nutzt `mock_z3_bho_verify` — Mock SAT/BHO, **kein** Live-HTTP
zu `infra-z3`. Die dortigen ms sind CPU-Proxy und bleiben als Struktur-Screen gültig.

**Live-Messung (2026-08-27):** `scripts/test_live_z3_latency.py` · `make raas-live-z3-latency`  
Service: `infra-z3` Z3 5.1.0 · Host `http://127.0.0.1:8001` · `POST /prove_bho_invariant`  
Payload: BHO-OK Beispiel (45 000 / 36 000 / 6 750 / 2 250) · N=50 · Warmup=5 · seed_tag=`20260827`

| Metrik | Wert |
|--------|------|
| wall_ms min | 0,92 |
| wall_ms median (p50) | 1,18 |
| wall_ms p95 | 1,48 |
| wall_ms p99 | 1,71 |
| wall_ms max | 1,86 |
| ok | 50/50 |
| server `proof_time_us` median | ≈20 µs |

Artefakt: `prototypes/v2_stateful_graph/live_z3_latency_results.json` · Verdict `LIVE_Z3_LATENCY_PASS`

**Regel (aktualisiert):** „Echtzeit“ darf nur mit Bezug auf **diese Live-Zahlen** (oder neuere,
gleichermaßen dokumentierte Wiederholungen) erscheinen — nicht mit Verweis auf den Mock-Screen.
Parallel-Sub-Schwarm (Z3) bleibt optional; bei p95 ≪ 10 ms ist er kein Notfall.

---

## 3. Sub-Schwärme (nach dem Gate)

| Sub-Schwarm | v1-Anbindung (kein Remap) | Aufgabe |
|-------------|---------------------------|---------|
| MEV & Latency Red-Team | P₄ MEV-Szenario · P₂ Latenz | Sandwich/Jitter **simulieren** — `/sandbox/` |
| Oracle Anomaly | P₅ Oracle-Stress | Stale/Fat-Finger/Flash **injizieren** (Szenario) |
| Multi-Chain Liquidity | P₁ Intake · P₃ Pressure | Bridge/De-Peg **Exposition** modellieren |
| Z3 Parallel Solver | P₆ Z3 Auditor | SMT skalieren — erst nach Live-Latenz-Messung |

Orchestrierung der Sub-Schwärme = **Shell/Plugin außerhalb** (v2), nicht P₂-Umbenennung.
`execute_*` bleibt verboten; `run_attack_scenario` / `report_scenario`.

**D2:** App-layer2 existiert (`DSuiteEnforcer`). Sub-Schwarm-Piloten:
`plugins/mev_latency_redteam/` · `plugins/oracle_anomaly_swarm/` — Sandbox-IO +
Dockerfile (`USER redteam`, `--read-only` / `--cap-drop ALL` Runtime-Intent).

---

## 4. Sequenz (verbindlich)

```text
0.  Topologie-Screen gegen geplantes Bus-Zustellmuster
      └─ PASS 2026-08-27 QUEUEGROUP_RING_PASS
1.  Stufe 1: Core-Bus — **Ring-Kanten auf Queue-Groups**
      └─ Adapter `prototypes/raas_hybrid_shell/edge_bus.py`
      └─ Pilot P1→P2 · Ring P1→…→P9→P1 (9 Subjects + Queue-Groups)
      └─ `RingOrchestrator` = request/reply, feste Sequenz
      └─ Sync-Default `TrustedCoreGateway` unverändert (kein Full-Cutover)
      └─ Runner: `test_stage1_edge_bus_pilot.py` · `test_stage1_edge_bus_ring.py`
2.  Live-Z3-Latenz messen (infra-z3) → **PASS 2026-08-27** (p50≈1,2 ms wall)
3.  Red-Team-Plugin (MEV/Latency) unter /sandbox/ + D2 OS-Isolation
      └─ `plugins/mev_latency_redteam/` · Subject `edge.P2.redteam.sandbox`
      └─ Runner `scripts/test_mev_latency_redteam.py` · `make raas-mev-redteam`
3b. Oracle Anomaly Swarm (P5) — **PASS-Muster**
      └─ `plugins/oracle_anomaly_swarm/` · Subject `edge.P5.oracle.sandbox`
      └─ STALE_PRICE / FAT_FINGER / FLASH_CRASH · `make raas-oracle-anomaly`
3c. Konsolidierung — **OS-Isolationstest** (Voraussetzung vor Stufe 2)
      └─ `scripts/test_os_isolation_subswarms.py` · `make raas-os-isolation`
      └─ Dockerfile-Intent: USER≠root · --read-only · --cap-drop ALL · kein Core/WORM-Mount
4.  Stufe 2 — Gateway/Shell-Bus (**geplant, noch nicht implementiert**)
      └─ siehe §4.1 — Abbruchkriterien bindend vor Cutover
4A. Phase 4A — Schnellfilter (**Priorisierung**) — **IMPLEMENTIERT 2026-08-27**
      └─ siehe §4.2 — Queue unter Rückstau; Default FIFO; kein Kern-Skip
      └─ Synth · Train · Plugin · Facade-Cutover (`PREFILTER_ENABLED`)
5.  Liquidity Plugin nach Bedarf (wenn Cross-Chain-Strategien anstehen)
6.  Inter-Swarm (WSS/Libp2p) — zuletzt; P₉-Signatur + Z3-Header Intent
```

**Stufe-1-Regeln:** Orchestrator wartet auf Antwort der Kante (request/reply)
→ feste Sequenz, kein Broadcast. D1–D4 bleiben an der Facade. Gateway bleibt
sync bis Stufe 2 bewusst freigegeben ist; Bus-Ring ist die gemessene
Kern-Nachbarschaft vor Cutover.

### 4.1 Stufe 2 — Gateway/Shell-Bus (geplant)

**Status:** nicht implementiert · kein „mal eben“-Cutover  
**Voraussetzung:** Sequenz 0–3c grün (`OS_ISOLATION_PASS` + bestehende Smokes)

**Vor Cutover (bindend):** Topologie-Screen erneut gegen das **tatsächliche**
Zustellmuster des Bus (§2.1 / `make raas-bus-topology-gate`, ~16 s). Verdict
entscheidet, ob NATS den Ring erhält (`QUEUEGROUP_RING_PASS`, ⟨k⟩≈1) oder ihn zu
`complete` macht (Fan-out — dort lag die Serie-Marge bei null). Ohne PASS kein
Stufe-2-Cutover.

| Ziel | Inhalt |
|------|--------|
| Außenhülle auf Bus | Ingress/Egress-Events über NATS Queue-Groups (1-von-N), kein Broadcast |
| Kern unangetastet wo möglich | `TrustedCoreGateway`-Logik bleibt; Transport wechselt, Rollen (P₁…P₉) nicht |
| Fail-closed bleibt vorne | `DSuiteEnforcer` (D1–D4) **vor** jedem Kernaufruf — auch nach Bus-Hop |

| Komponente | Rolle in Stufe 2 |
|------------|------------------|
| `SupranodeFacade` | Bleibt Außenhaut; publiziert/empfängt nur erlaubte Subjects |
| `DSuiteEnforcer` | Weiter vor Core; Bus ersetzt den Enforcer **nicht** |
| `TrustedCoreGateway` | Sync-Default bis Cutover; danach Request/Reply hinter Facade |
| NATS | Nur Queue-Group Subjects (z. B. `edge.facade.core.*`); Broadcast gesperrt |

**Fail-Closed-Bedingungen (Abbruch → Stufe 2 stoppen):**

1. Jede neue Kante muss 1-von-N liefern (wie Gate 0); Fan-out = BLOCKED.  
2. Red/Plugin-Pfade schreiben weiter nur unter `data/raas/sandbox/`; Decision-Felder verboten.  
3. Exterior ohne Ingress/Egress/Evaluate = D4-Verletzung.  
4. `live_execution` bleibt `false`; keine `execute_*`-APIs.  
5. Determinismus-Test: gleiche Eingabe → gleiches Envelope/Seal über den Bus.  
6. `HYBRID_SHELL_PASS` · `SUPRANODE_FACADE_PASS` · `D_SUITE_PASS` · Bus-Gates bleiben grün.

Stufe 2 ersetzt **nicht** Gate 0 und nicht die Plugin-Isolation.

### 4.2 Phase 4A — Schnellfilter (GBT) — Priorisierung · **IMPLEMENTIERT**

**Status:** ✅ implementiert (2026-08-27) · Default `PREFILTER_ENABLED=false` · **kein** LLM · **kein** Kern-Skip  
**Abgrenzung:** Parallel zu Stufe 2 (weiterhin gesperrt). Prefilter = Untrusted Hülle (D1–D4).

| Deliverable | Artefakt / Runner |
|-------------|-------------------|
| Synth-Corpus | `data/synthetic/prefilter/` · `make raas-prefilter-batch-extremes` |
| Label-Qualität | `PREFILTER_SYNTH_QUALITY_PASS` (nur `severity_proxy`) |
| Training + Queue-Metrik | `make raas-prefilter-train` · `PREFILTER_TRAINING_PASS` / `PREFILTER_QUEUE_METRIC_*` |
| Plugin | `plugins/risk_prefilter/` · Subject `edge.gateway.prefilter.request` |
| Facade-Cutover | `handle_external_batch` · `make raas-gateway-prefilter-cutover` |
| Cutover-Tests | `GATEWAY_CUTOVER_PASS` · `GATEWAY_FALLBACK_PASS` |

Erstes Queue-Ergebnis (Holdout-Sim, ein Seed): riskante Wartezeit ≈ **−5,2 % vs FIFO**.
**Seed-Spread (2026-08-27, n=6):** mean **4,48 %** · σ **1,47 %** · Range 2,2–6,1 % ·
`PREFILTER_QUEUE_SEED_SPREAD_PASS` (mean > 2σ) — Einzellauf war am oberen Rand;
Artefakt `models/prefilter/prefilter_queue_seed_spread.json`.

#### Deklarierter Zweck (bindend)

**Priorisierung unter Rückstau** — nicht Abkürzung, nicht Freigabe.

**Satz (bindend):** *Das Modell approximiert das Gate-Verdict, es prognostiziert
kein Marktrisiko.* Es sortiert; Freigabe bleibt allein beim deterministischen Kern.

- Jede Anfrage wird **vollständig** vom deterministischen Kern geprüft.  
- Der Score bestimmt nur die **Reihenfolge** in der Warteschlange (riskante zuerst).  
- Wenn kein Rückstau existiert, ist der Prefilter optional und darf **keine** Latenz
  als „Ersparnis“ verkaufen (er addiert dann nur Overhead).  
- **Verboten zu zitieren:** „spart Rechenzeit / überspringt Simulation“ ·
  „Risikovorhersage“ · „Marktrisiko erkannt“ — das ist nicht der Zweck.

#### Label-Herkunft (eigene Zeile — vor jedem Trainingslauf ausfüllen)

| Mode / Quelle | Was steckt im Label? | Für überwachtes Lernen? | Zirkularität |
|---------------|----------------------|-------------------------|--------------|
| `severity_proxy` | Plugin-Severity → Pseudo-Verdict | Training erlaubt (Sortierhelfer) | **verschoben, nicht aufgehoben** — Zielgröße = deterministische Funktion der Eingänge; Kalibrierung ändert Abdeckung, nicht Label-Unabhängigkeit |
| `gateway` | `TrustedCoreGateway` / `evaluate_gate` | lernt die **eigene Gate-Funktion** | **ja** — AUC vs. denselben Gate ist Vanity |
| öffentlich (roh) | Klines/MEV ohne Verdict | **kein** Trainingslabel | unlabeled; direkt trainieren = Proxy-Label-Risiko → **verboten** |
| Public-Ingest (§4.3) | Verteilungsprofile → Synth-Generator | Labels bleiben `severity_proxy` | Kalibrierung der **Eingänge**, nicht der Labels |

Gate-Labels (`gateway`) dürfen Feature-Pipelines und Ranking-Proxies speisen, aber
**nicht** als Beweis gelten, dass das Modell „Risiko“ gelernt hat.

#### Erfolgskriterien (müssen scheitern können)

1. `PREFILTER_DATAGEN_PASS` — Synth-Export reproduzierbar (fester Seed).  
2. **Warteschlangen-Metrik (primär):** In einem dokumentierten Rückstau-Sim
   (FIFO vs. Score-Priorität, gleicher Kern-Durchsatz) sinkt die mittlere Wartezeit
   der als riskant markierten Anfragen; der Effekt muss gegen eine **Null-Baseline**
   (zufällige Reihenfolge / FIFO) getestet werden und darf **fehlschlagen**.  
   Artefakt: `PREFILTER_QUEUE_METRIC_PASS|FAIL` in `models/prefilter/prefilter_train_report.json`.  
   *(Kein* „AUC &gt; 0,95 auf Synth-Extrems“ *als Erfolg.)*  
   **Seed-Spread (vor Kalibrierungs-Claims):** ≥6 Trainings-Seeds →
   `improvement_vs_fifo` Mittelwert **und** Streuung (`seeds`-Feld im Report).
   Ein Einzellauf (% vs FIFO) ist **kein** Erfolgskriterium.  
   Runner: `make raas-prefilter-queue-seed-spread`.  
3. `PREFILTER_TRAINING_PASS` — Trainingspipeline auf `severity_proxy`-Corpus
   (`scripts/train_prefilter_model.py` · GBT: LightGBM falls vorhanden, sonst
   sklearn HistGradientBoosting).  
4. Inferenzen-Latenz p95 &lt;5 ms (CPU) — gemessen, notiert; bei Überschreitung FAIL.  
5. Semantik-Check: Score ändert nur Queue-Ordnung; Kern-Pfad unverändert; kein Skip.  
6. D1–D4: Prefilter emittiert keine `gate_verdict`/`envelope_id`; Rolle Untrusted.  
7. Bestehende Smokes bleiben grün.

Runner: `make raas-prefilter-train` · Plugin `plugins/risk_prefilter/`
(Subject `edge.gateway.prefilter.request`).

#### Gateway-Cutover (lastabhängige Priorisierung)

| Element | Festlegung |
|---------|------------|
| Default | `PREFILTER_ENABLED=false` → FIFO wie bisher |
| Aktiv | `PREFILTER_ENABLED=true` **und** Pending ≥ `PREFILTER_BACKLOG_THRESHOLD` (Default 3) |
| Ablauf | Score → Sortierung absteigend → **sequentiell** voller Kern (kein Skip) |
| Fallback | Prefilter unerreichbar / Score fehlt → **FIFO**; Anfragen gehen nicht verloren |
| Oberfläche | `SupranodeFacade.handle_external_batch` + `prefilter_backlog.py` |
| Kern | `TrustedCoreGateway` unverändert |
| Tests | `GATEWAY_CUTOVER_PASS` · `GATEWAY_FALLBACK_PASS` |

**Verbot:** Score ersetzt Freigabe · Skip · „spart Kern-Rechenzeit“ als Claim.

#### Daten & Modell (nach Zweck)

| Element | Festlegung |
|---------|------------|
| Synth | MEV/Oracle-Plugins → Feature-Matrix (`generate_prefilter_synthetic_data.py`) |
| Öffentlich | **eigenes Arbeitspaket** (RPCs/403, kein Verdict) — parallel, nicht Schritt 2 der Liste |
| Modell | LightGBM/XGBoost Intent als **Ranking-/Prioritätssignal** |
| Integration | später `risk_prefilter` NATS Queue-Group → Facade-Warteschlange |
| Verbot | Modell-only RELEASED · Z3-Ersatz · Kern-Skip · AUC-gegen-Gate als Pitch |

**Nicht jetzt:** LoRA/LLM (4B) · Live-Exchange-Ingest als Freigabekriterium ·
„gesparte Simulationszeit“ ohne Skip (widerspricht Zweck).

### 4.3 Arbeitspaket Public-Ingest — Kalibrierung (nicht Trainingslabels)

**Status:** **Konsolidiert · Referenz A aktiv** (2026-08-27) · Sondierung ✅ ·
Generator ✅ · Composition CONFIRMED · Multi-Holdout-Freeze+Baseline ✅ ·
**Haltepunkt** — keine Neukalibrierung / kein Pfad‑2 ohne Auslöser · kein DEFAULT_ON  
**Zweck der öffentlichen Daten:** Verteilungsquelle für den Synth-Generator —
**nicht** unlabeled Trainingszeilen, **kein** Proxy-Verdict aus Klines/MEV.

| Schritt | Inhalt | Nicht |
|---------|--------|-------|
| 1 Sondierung | Binance-Klines / Flashbots-Stichprobe → `exports/open_data/` · `make raas-public-ingest-sondierung` | Terabytes · Live-Trading · Trainingslabels |
| 2 Profile | Latenz-/Vol-/MEV-/Oracle-Perzentile als JSON/YAML | Training auf Rohzeilen |
| 3 Generator | Profile → `generate_prefilter_synthetic_data.py` | Label-Mode ändern |
| 4 Re-Train | 20k–50k Synth · Quality-Gate · Queue-Metrik | Claim ohne gepaarten Seed-Vergleich |
| 5 DEFAULT_ON | nur wenn mean(Δ) > 2·SEM(Δ) (gleiche Seeds) | nackte %-Zahl · 2σ-Einzellauf als Cut |

**Zweck-Satz (wie §4.2):** Modell approximiert Gate zum **Sortieren**; prognostiziert
kein Marktrisiko. Kalibrierung verbessert **Abdeckung** (realistischere Ränder),
nicht Label-Unabhängigkeit (Zirkularität bleibt benannt).

**Label-Herkunft:** Training weiter nur `severity_proxy` aus dem Simulator.
Öffentliche Rohdaten → Parameterprofile → Synth → dieselben Label-Regeln.

**Erfolgskriterium (muss scheitern können):**

1. **Baseline (Einzellauf-Streuung):** `make raas-prefilter-queue-seed-spread`
   (≥6 Seeds) → `improvement_vs_fifo_mean` / `_std` / Feld `seeds`.
   Das 2σ-Kriterium dort prüft nur: *ist der Effekt von null unterscheidbar?*
   (Ist-Stand 2026-08-27: mean 4,48 % · σ 1,47 % · mean/SEM≈7,5 · PASS).  
2. **Public-Ingest-Vergleich = gepaart (bindend):** dieselben sechs Seeds
   vor und nach Kalibrierung; je Seed Δ = improvement_after − improvement_before;
   Erfolg nur wenn  
   `mean(Δ) > 2 · SEM(Δ)` mit `SEM(Δ) = std(Δ)/√n` (n=6).  
   *Nicht* Δmean ≳ 2·σ_Einzellauf (≈2,94 pp) — das wäre zu streng für zwei
   Mittelwerte und würde reale ~2 pp-Gewinne als Rauschen verwerfen.  
   Orientierung ungepaart: 2·SEM_diff ≈ 1,7 pp; gepaart typisch darunter.
   Nebenbei sichtbar: wirkt die Kalibrierung gleichmäßig über Seeds oder nur
   auf Ausreißern?  
3. Quality-Gate `PREFILTER_SYNTH_QUALITY_PASS` bleibt grün.  
4. Kein Kern-Skip · D1–D4 unverändert · kein Risk-Claim aus öffentlichen Daten.

**Messung 2026-08-27 (Artefakt `prefilter_queue_profile_calibrated.json`):**

| Versuch | Ergebnis |
|---------|----------|
| Feature-Replace (Binance+Flashbots) | mean(Δ) ≈ **−15,9 pp** · FAIL — Severity↔Feature entkoppelt |
| Soft-Blend Slip/Vol/Oracle | mean(Δ) ≈ **−4,5 pp** · FAIL |
| Nur Gas/MEV-Kalibrierung vs. unkalibriert n=20k | mean(Δ) ≈ **+0,58 pp** · SEM≈0,35 · 2·SEM≈0,70 · **FAIL** (knapp unter Schwelle) |
| Unkalibriert n=20k allein | improvement mean **−1,8 %** · Seed-Spread FAIL (Baseline n=5k bleibt +4,5 %) |

**Diagnostik Risiko-Anteil (`severity_score ≥ 0.85`) — Confound-Check:**

| Charge | n | n_risky | share | Holdout share (train_frac=0.8) |
|--------|---|---------|-------|--------------------------------|
| extremes 5k | 5000 | 2992 | **59,8 %** | 581/1000 = **58,1 %** |
| extremes 20k (unkalibriert) | 20000 | 12130 | **60,6 %** | 2445/4000 = **61,1 %** |
| calibrated 20k | 20000 | 12130 | **60,6 %** | 61,1 % (Labels unverändert) |

Kind-Mix (DEPEG/FAT 100 % risky, JITTER 0 %, Rest dazwischen) ist über 5k/20k
strukturell gleich. **Δshare Holdout ≈ +3 pp** — nicht 80 %, kein Hebel-Kollaps.
Damit ist `−1,8 %` **kein** Zusammensetzungs-Effekt der hypothetischen Art
„zu viele Riskante → Priorisierung schlechter als FIFO“. Vorzeichen-Kipp 5k→20k
bleibt **unerklärt** (Modell-/Holdout-n-/Sim-Skalierung); `+4,5 %` und `−1,8 %`
sind **nicht** als gleiche Baseline vergleichbar, solange die Ursache offen ist.
Weitere Feature-Kopplungsversuche gegen diese Referenz: **gestoppt**.

**Folgerung:** Public-Ingest-Profile sind nutzbar als Artefakte; aktuelle Kalibrierung
rechtfertigt **kein** DEFAULT_ON und keinen Fortschritts-Claim. Phase-4A-Cutover bleibt
Default OFF. Halt: Pipeline + Profile + gepaartes Kriterium stehen; Gewissheit über
die Referenz (warum 5k≠20k) fehlt noch — nicht ein vierter Kalibrierungsversuch.

#### 4.3.1 Arbeitspaket Referenzklärung & Holdout-N-Stabilisierung

**Status:** R1/R3/R5 ✅ · N-robust Bootstrap ✅ · Harrell-Davis / Rang-Kohärenz = Intent  
**Ziel (erreicht für Referenz):** Vorzeichen-Kipp `+4,5 %` (n=5k) → `−1,8 %` (n=20k)
als **Holdout-n-Effekt** ausgewiesen; Primär-Referenz eingefroren.

| Schritt | Prüfung | Isoliert |
|---------|---------|----------|
| R1 Reproduzierbarkeit | Seed-Spread 5k erneut → gleiche mean/σ wie Report? | Nicht-Determiniertheit |
| R2 Eval-Parität | Gleiche Sim-Parameter (`service_time`, `arrival_interval`, Seeds) | Eval-Confound |
| R3 5k-Subset aus 20k | Gleiche Kind-Verteilung + gleicher n → Spread vs Original-5k | **Datenmenge vs. Charge** |
| R4 Feature-Diff | Perzentile Holdout 5k vs 20k (Latenz, Slip, Oracle, …) | Feature-Shift |
| R5 Sim-Skalierung | Identisches Modell, Holdout n=1000 vs 4000 | Sim-n-Effekt |

**Gesperrt bis bewusste neue Referenz:** weitere Feature-Kopplung,
Public-Ingest-Re-Train als Erfolg, DEFAULT_ON (Cutover bleibt Default OFF).

##### Prefilter-Evaluierung & Holdout-N-Stabilisierung (formal)

- **Holdout-N-Invarianz (Fixed-Size Bootstrapping) — implementiert:**  
  Metrik-Berechnung über **B=40** Bootstrap-Ziehungen fester Referenzgröße
  **n₀=1000** (`queue_metric_n_robust`, stratifiziert risky/non-risky).  
  Entkoppelt Cross-N-Vergleiche von schwankendem Holdout-N (R5).  
  Primär-Claims bleiben **raw** `improvement_vs_fifo` @ Holdout=1000.
- **Quantil-Robustheit (Harrell-Davis) — Intent:**  
  Tail-Metriken (P95/P99 der Wartezeit) als beta-gewichtete Ordnungstatistiken —
  noch nicht im Runner; erst bei Bedarf an Wait-Quantilen, nicht Pflicht für Cutover.
- **Gepaarte Rang-Kohärenz — Intent (Label-ehrlich):**  
  Relative Priorisierungsgüte vs. **`severity_proxy`** (Sortier-Approximation des
  Gates) — **nicht** vs. Live-Z3/BHO-Ground-Truth (wäre Zirkel / falscher Claim).  
  Modell approximiert Gate-Verdict zum Sortieren; prognostiziert kein Marktrisiko.
- **Invarianz-Schwelle für künftige Cutover-Diskussion:**  
  Prefilter-Variante vs. FIFO-Fallback erst freigabefähig diskutieren, wenn
  Bootstrap-Streuung der robusten Metrik **σ_robust < 0,02** (über Seeds/Boots)
  dokumentiert ist — **zusätzlich** zu den bestehenden Cutover-Tests
  (`GATEWAY_CUTOVER_PASS` / Fallback) und Default OFF. Kein Automatismus.  
  **Hinweis:** Aktuell Seed‑σ_robust @ nested‑random n=1000 ≈ **4,18 pp** —
  Schwelle dort unerreichbar, bis fester vs. random Holdout geklärt ist
  (siehe „Widerspruch σ @ n=1000“ unten). Kein Pfad‑1‑Lauf gegen diese Zahl.

Runner: `scripts/diagnose_prefilter_reference.py` · `make raas-prefilter-reference-diagnosis`  
Artefakt: `models/prefilter/prefilter_reference_diagnosis.json`.

**Stand 2026-08-27:**

| Schritt | Ergebnis |
|---------|----------|
| R1 Repro | **PASS** — mean/σ bitgleich zum Report (0,044788 / 0,014705) |
| R3 5k-Subset aus 20k | **Δmean = 0** vs. 5k-Rerun (gleiche Kind-Counts) → Charge ≡ 5k |
| R5 Train-n vs Holdout-n | **Holdout-n dominant** — siehe unten |

**R5 (2026-08-27, `prefilter_r5_train_vs_holdout.json`):**

| Bedingung | mean(improvement) |
|-----------|-------------------|
| A: Train 5k · Holdout 1000 | **+3,92 %** |
| A: Train 5k · Holdout 4000 (nested) | **+0,55 %** |
| B: Train 5k · Holdout 1000 (last) | **+1,43 %** |
| B: Train 19k (20k−H) · gleiches Holdout | **+1,62 %** |

- ΔHoldout (4k−1k, Train fest): **−3,38 pp**  
- ΔTrain (large−5k, Holdout fest): **+0,19 pp**  
- **Dominant: Evaluations-/Holdout-Größe**, nicht Trainingsmenge.  
  Der frühere 20k-Kipp (−1,8 %) ist mit größerem Holdout (n=4000) konsistent erklärbar;
  mehr Trainingsdaten allein verschlechtern die Metrik hier nicht.

**Referenz (eingefroren, bestätigt):** n_train=5k · n_holdout=**1000** · mean **4,48 %** (σ 1,47 %).  
**Geltungsbereich:** gilt für den **fixierten** Holdout (seed_split, n_risky=581),
**nicht** für beliebige Ziehungen gleicher Größe — σ_raw=1,47 pp misst dort nur
Modellvarianz; Zusammensetzungsvarianz bleibt ausgeblendet.  
Claims und gepaarte Vergleiche nur mit diesem fixierten Holdout=1000 (oder explizit neu geeicht).  
Feature-Kopplung / DEFAULT_ON weiter gesperrt, bis bewusst eine neue Referenz gewählt wird.

**N-robuste Sekundärmetrik (2026-08-27):** `queue_metric_n_robust` in
`scripts/train_prefilter_model.py` — Fixed-Subsample-Bootstrap bei **n₀=1000**,
B=40, stratifiziert nach risky/non-risky. Entkoppelt den Score von Holdout-N
(R5-Befund), **ohne** die eingefrorene Primär-Referenz zu ersetzen.

| Check (nested random pools N=1000→4000, Train 5k) | Δ |
|--------------------------------------------------|---|
| raw `improvement_vs_fifo` | **−1,11 pp** |
| robust bootstrap n₀=1000 | **+0,44 pp** |
| Verdict | `PREFILTER_N_ROBUST_PASS` (|Δrob| < ½|Δraw|) |

Artefakt: `models/prefilter/prefilter_n_robust_metric.json` ·
`make raas-prefilter-n-robust-metric`  
**Claims:** weiter raw @ Holdout=1000. **Cross-N-Vergleiche:** robust n₀.

##### Widerspruch σ @ n=1000 (offen — vor Pfad‑1‑Kalibrierung)

Aus `prefilter_n_robust_metric.json` (nested **random** pools, Train 5k, 6 Seeds)
gegenüber der eingefrorenen Referenz (seed_split‑**fester** Holdout):

| Quelle | n | mean | σ (über Seeds) | Seeds negativ |
|--------|---|------|----------------|---------------|
| **Eingefroren raw** (fester Holdout, n_risky=581) | 1000 | **+4,48 %** | **1,47 pp** | **0/6** |
| Nested-random raw/robust (N=n₀ → identisch) | 1000 | **+0,33 %** | **4,18 pp** | **2/6** |
| Nested-random robust | 2000 | +1,52 % | 0,80 pp | 0/6 |
| Nested-random robust | 4000 | +0,77 % | 0,55 pp | 0/6 |

**Lesart (Hypothese, ungeprüft):** Der eingefrorene Lauf hält die Holdout‑Zusammensetzung
konstant → Seed‑Streuung ≈ nur Modellvarianz. Nested‑random @ n=1000 zieht jedes Mal
eine andere Zusammensetzung → höhere σ und Vorzeichenkipps. Bei N=n₀ gibt es **keinen**
Bootstrap (rob = raw); die 4,18 pp sind also **Pool‑/Zusammensetzungs‑Unsicherheit**,
nicht Bootstrap‑σ. Ob +4,48 % bei fester Zusammensetzung die Unsicherheit **unterschätzt**,
ist offen — Referenz wird **nicht** geändert, aber Claims dürfen den Widerspruch nicht
überschreiben.

**Folgerungen für geplante Läufe:**

1. **Kein Pfad‑1‑Kalibrierungslauf**, solange dieser Widerspruch ungeklärt ist.  
2. Ziel `σ_robust < 0,02` ist bei aktuell **4,18 pp @ n=1000** unerreichbar als
   Seed‑σ auf random Pools — nicht als Kalibrierungs‑Fail missverstehen.  
   Bei n=2000/4000 liegt Seed‑σ bereits unter 0,02 **ohne** Kalibrierung.  
3. Stabilitätskriterium für Cross‑N: gleiches Vorzeichen / stabile Rangfolge
   **über Holdout‑n**, nicht nur über Seeds.  
4. Gate‑Map‑Erfolgskriterien für Neukalibrierung erst **nach** Klärung dieses Punkts
   (fester vs. random Holdout @ 1000) formulieren.

**Nächster Diagnose‑Schritt (vor Pfad 1):** Isolieren — fester Holdout (n_risky=581)
vs. repeated random Holdouts der Größe 1000, gleiches Modell/Seeds → misst, wie viel
der 1,47 pp vs. 4,18 pp‑Lücke Zusammensetzung ist.

**Isolation 2026-08-27 (`prefilter_fixed_vs_random_holdout.json`) — CONFIRMED:**

| Größe | mean | σ | Negativ |
|-------|------|---|---------|
| Fester Holdout (über 6 Modell‑Seeds) | +4,48 % | **1,47 pp** (nur Modell) | 0/6 |
| Zufalls‑Holdouts à 1000 (Modell fix je Seed, 6×6 Draws) | +1,97 % | **within‑model 2,55 pp** · pooled 2,65 pp | 8/36 |

Ein Faktor variiert (Zusammensetzung), Modell fest → σ steigt klar über die
Modell‑only‑σ. Zusammensetzung ist bestätigt. Die 4,18 pp aus nested‑random
mischen zusätzliche Faktoren und müssen nicht bitgleich getroffen werden.

Runner: `make raas-prefilter-fixed-vs-random-holdout`  

##### Umgang mit Zusammensetzungs-σ — **Entscheidung A** (2026-08-27)

| Option | Inhalt | Status |
|--------|--------|--------|
| **A** Mehrere feste Holdouts | 5–10 stratifizierte feste Sets à 1000; Claim = Mittel ± Streuung über Sets | **gewählt** |
| **B** Ursachenanalyse (Pfad 2) | SHAP/Tail auf kippende Zusammensetzungen | zurückgestellt — sinnvoll **nach** A (stabiles Ziel) |
| **C** Mit σ leben (> 2·σ_composition ≈ 5,1 pp) | Keine Extra-Arbeit | **abgelehnt** — wäre Einstellung des Pakets unter Kriterium-Tarnung (Effekt ~4,5 pp, Kalibrierung ≤ +0,58 pp) |

**Begründung A:** Die Singularität von 4,48 % ist kein zu bewahrender Wert, sondern der Mangel —
eine Aussage über eine Ziehung, bei der 8/36 vergleichbarer Ziehungen negativ sind.
Mehrere feste, versionierbare Sets ersetzen Genauigkeits-Illusion durch ausgewiesene Streuung;
Determinismus bleibt (fixe Indizes + Hash), wird aber nicht mit Reichweite verwechselt.

**Historische raw-Referenz:** `+4,48 % ± 1,47 pp` @ fixiertem Holdout (n_risky=581) bleibt
als historischer Wert stehen (Geltungsbereich §4.3.1 oben). A stellt eine **Referenz mit
Reichweite** daneben — widerruft die Historie nicht.

**Bindende Bedingungen (Bridge-Siegel-Disziplin):**

1. **Freeze-vor-Lauf:** Sets werden **vor** dem ersten Evaluationslauf gezogen und im
   Manifest gehasht (`manifest_sha256` über kanonische Indexlisten). Kein Nachziehen
   der Referenzmenge nach erstem Claim. Überschreiben nur mit `--force` (invalidiert
   vorherige A-Claims ausdrücklich).
2. **Claim-Form:** immer **Mittel ± Streuung über Sets** — nie das beste Set.
   (Sonst wird A wieder zu C mit Cherry-Pick.)

Artefakte / Runner:

| Schritt | Befehl / Datei |
|---------|----------------|
| Freeze (nur ziehen + hashen) | `make raas-prefilter-multi-holdout-freeze` → `config/prefilter/prefilter_multi_holdout_manifest.json` (git-tracked) |
| Baseline-Eval (nach Freeze) | `make raas-prefilter-multi-holdout-eval` → `models/prefilter/prefilter_multi_holdout_baseline.json` |
| Hash-Verify | Eval verweigert Lauf bei Manifest-Mismatch |

**A-Baseline (2026-08-27, nach Freeze):** 8 Sets à 1000 · stratifiziert ·
`manifest_sha256=ae893a5b…` · Claim **+2,12 % ± 1,21 pp** über Sets
(nie best: H05 forensic +3,90 %). Historische Singularität +4,48 % bleibt separat.

**Pfad 1:** freigabefähig **nur** gegen diese A-Referenz (gepaart: mean(Δ) über dieselben
Sets; nie vs. bestes Set / nie vs. historischer Singularität allein). DEFAULT_ON weiter
gesperrt, bis A-Claim und Freigaberegel explizit gesetzt sind.

**Haltepunkt (2026-08-27):** Kein sofortiger Pfad‑1‑Lauf und kein Pfad‑2.
Zusammensetzungsvarianz ist kontrolliert; Claim belastbar. Neukalibrierung oder
Ursachenanalyse erst bei konkretem Auslöser (z. B. DEFAULT_ON-Bedarf, neue Daten,
explizite Ursachenfrage) — Schutz vor Daten-Fishing.

Runner (Diagnose): `make raas-prefilter-r5-train-vs-holdout` · `make raas-prefilter-n-robust-metric`

**Reihenfolge (bindend):** Gate-Map (§4.2/§4.3) → Seed-Spread-Check →
Sondierungs-Skript → Generator. Nicht umgekehrt.  
**Kalibrierung / Pfad 1:** gegen A-Baseline freigabefähig, **derzeit Pause** (Haltepunkt);
DEFAULT_ON weiter gesperrt.

---

## 5. Nicht jetzt

| Arbeit | Status |
|--------|--------|
| NATS JetStream Cutover für RaaS-P9 | Gate 0 PASS · **Ring-Bus Pilot+9 Kanten** — Gateway-Cutover = Stufe 2 (offen) |
| Stufe 2 Gateway/Shell-Bus Implementierung | **gesperrt** bis §4 Sequenz 3c + §4.1 Kriterien + **Topologie-Re-Screen** (~16 s) |
| Phase 4A `risk_prefilter` Cutover | ✅ Facade-Batch · Default OFF · FIFO-Fallback · kein Skip |
| Phase 4A Modell-Optimierung (mehr Synth) | **optional** — erst nach Seed-Spread (§4.2) |
| Public-Ingest (Kalibrierungsprofile) | **Konsolidiert · Referenz A aktiv** · Haltepunkt · DEFAULT_ON gesperrt |
| Zusammensetzungs-σ Umgang | **A gewählt** · Claim +2,12 % ± 1,21 pp · Pfad 1/2 **Pause** bis Auslöser · C abgelehnt |
| Referenzklärung 5k↔20k Queue-Baseline | Composition **CONFIRMED** · Historie 4,48 % · A-Reichweite 2,12 % ± 1,21 pp · **geschlossen** |
| Phase 4B LLM-LoRA | **nach** 4A · eigener Bedarf |
| Broadcast-Subjects als Steuerpfad | **gesperrt** (Serie + `forbid_broadcast`) |
| „Echtzeit-Insolvenz“ in Pitch/Map | **erlaubt nur mit Live-Zahlen** (p50≈1,2 ms wall, 2026-08-27) — nicht Mock |
| Multi-Schwarm-Schiedsrichter (v3) | Map ✅ · §4 gewählt (Verzeichnis · **M1** · Envelope nur Einreicher) · Betrieb bis M1-Bau gesperrt |
| Multi-Chain Liquidity Sub-Schwarm | **zurückgestellt** bis Kundenbedarf Cross-Chain |
| 9 neue Remap-Microservices | **abgelehnt** (v1/v2) |
| Libp2p Inter-Swarm | Intent only |

---

## 6. Verweise

| Dokument / Artefakt | Rolle |
|---------------------|-------|
| `docs/STATEFUL_GRAPH_SERIE_v0.md` | topology · async_verify · wall_clock |
| `docs/RaaS_HYBRID_KI_ROADMAP_v0.md` | Phase 4A/4B |
| `prototypes/v2_stateful_graph/` | Screen-Runner · `live_z3_latency_results.json` |
| `scripts/test_live_z3_latency.py` | Live HTTP → infra-z3 |
| `scripts/test_os_isolation_subswarms.py` | D2 OS-Isolation Intent (Dockerfiles) |
| `scripts/generate_prefilter_synthetic_data.py` | Phase-4A Synth-Datengen |
| `scripts/check_prefilter_queue_seed_spread.py` | Queue-Metrik Seed-Spread (≥6) |
| `scripts/ingest_public_distributions.py` | §4.3 Sondierung → Profile unter `exports/open_data/` |
| `scripts/compare_prefilter_queue_paired.py` | §4.3 gepaarter Queue-Vergleich mean(Δ)>2·SEM(Δ) |
| `scripts/diagnose_prefilter_reference.py` | §4.3.1 R1 Repro + R3 5k-Subset-from-20k |
| `scripts/diagnose_prefilter_r5_train_vs_holdout.py` | §4.3.1 R5 Train-n vs Holdout-n |
| `scripts/diagnose_prefilter_n_robust_metric.py` | §4.3.1 N-robuste Queue-Metrik (Bootstrap n₀) |
| `scripts/diagnose_prefilter_fixed_vs_random_holdout.py` | §4.3.1 fester vs. random Holdout (Composition) |
| `scripts/freeze_prefilter_multi_holdout.py` | §4.3.1 A — Sets ziehen + Manifest-Hash (vor Eval) |
| `scripts/eval_prefilter_multi_holdout.py` | §4.3.1 A — Baseline Mittel±σ über Sets (nie best) |
| `config/prefilter/prefilter_multi_holdout_manifest.json` | A-Siegel: fixe Holdout-Indizes + `manifest_sha256` |
| `agents_b2g/protocol.py` | `broadcast`-Pfad |
| `services/fail_closed_gate/d_suite_enforcer.py` | D1–D4 app layer2 |
| `prototypes/raas_hybrid_shell/` | Facade + Gateway (sync Pilot) |
| `plugins/mev_latency_redteam/` · `plugins/oracle_anomaly_swarm/` | Sub-Schwarm-Muster |
