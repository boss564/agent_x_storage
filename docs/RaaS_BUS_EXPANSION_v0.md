# RaaS — Bus & Sub-Swarm Expansion Gate v0

**Status:** GATE v0 (2026-08-27) · bindend vor jeder Bus-Migration  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false`  
**Serie:** `docs/STATEFUL_GRAPH_SERIE_v0.md` (topology FALSIFIED · async_verify CONFIRMED unter Pipeline-Modell)  
**Basis:** `docs/RaaS_HYBRID_KI_ROADMAP_v0.md` · `docs/RaaS_P9_MAPPING_v2.md` · `docs/RaaS_SUPRANODE_v0.md`

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

**Status:** Sondierung ✅ · Generator-Anbindung ✅ · gepaarter Vergleich **FAIL** (2026-08-27) · kein DEFAULT_ON  
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

**Folgerung:** Public-Ingest-Profile sind nutzbar als Artefakte; aktuelle Kalibrierung
rechtfertigt **kein** DEFAULT_ON und keinen Fortschritts-Claim. Phase-4A-Cutover bleibt
Default OFF; n=5k-Unkalibriert ist die belegte Queue-Baseline.

**Reihenfolge (bindend):** Gate-Map (§4.2/§4.3) → Seed-Spread-Check →
Sondierungs-Skript → Generator. Nicht umgekehrt.

---

## 5. Nicht jetzt

| Arbeit | Status |
|--------|--------|
| NATS JetStream Cutover für RaaS-P9 | Gate 0 PASS · **Ring-Bus Pilot+9 Kanten** — Gateway-Cutover = Stufe 2 (offen) |
| Stufe 2 Gateway/Shell-Bus Implementierung | **gesperrt** bis §4 Sequenz 3c + §4.1 Kriterien + **Topologie-Re-Screen** (~16 s) |
| Phase 4A `risk_prefilter` Cutover | ✅ Facade-Batch · Default OFF · FIFO-Fallback · kein Skip |
| Phase 4A Modell-Optimierung (mehr Synth) | **optional** — erst nach Seed-Spread (§4.2) |
| Public-Ingest (Kalibrierungsprofile) | **§4.3** — nach Seed-Spread; Rohdaten ≠ Trainingslabels |
| Phase 4B LLM-LoRA | **nach** 4A · eigener Bedarf |
| Broadcast-Subjects als Steuerpfad | **gesperrt** (Serie + `forbid_broadcast`) |
| „Echtzeit-Insolvenz“ in Pitch/Map | **erlaubt nur mit Live-Zahlen** (p50≈1,2 ms wall, 2026-08-27) — nicht Mock |
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
| `agents_b2g/protocol.py` | `broadcast`-Pfad |
| `services/fail_closed_gate/d_suite_enforcer.py` | D1–D4 app layer2 |
| `prototypes/raas_hybrid_shell/` | Facade + Gateway (sync Pilot) |
| `plugins/mev_latency_redteam/` · `plugins/oracle_anomaly_swarm/` | Sub-Schwarm-Muster |
