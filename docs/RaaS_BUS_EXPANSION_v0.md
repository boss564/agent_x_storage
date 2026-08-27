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

**D2:** App-layer2 existiert (`DSuiteEnforcer`). Sub-Schwarm ist der erste Ort, an dem
**OS/Container-Sandbox** (read-only root, eigener User) praktisch wird — weiterhin Schuld.

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
4.  Oracle / Liquidity Plugins nach Bedarf
5.  Inter-Swarm (WSS/Libp2p) — zuletzt; P₉-Signatur + Z3-Header Intent
```

**Stufe-1-Regeln:** Orchestrator wartet auf Antwort der Kante (request/reply)
→ feste Sequenz, kein Broadcast. D1–D4 bleiben an der Facade. Gateway bleibt
sync; Bus-Ring ist die gemessene Kern-Nachbarschaft vor Cutover.

Stufe 2 (Gateway/Shell-Bus) kann parallel zur Facade bleiben; sie ersetzt nicht Gate 0.

---

## 5. Nicht jetzt

| Arbeit | Status |
|--------|--------|
| NATS JetStream Cutover für RaaS-P9 | Gate 0 PASS · **Ring-Bus Pilot+9 Kanten** — Gateway-Cutover offen |
| Broadcast-Subjects als Steuerpfad | **gesperrt** (Serie + `forbid_broadcast`) |
| „Echtzeit-Insolvenz“ in Pitch/Map | **erlaubt nur mit Live-Zahlen** (p50≈1,2 ms wall, 2026-08-27) — nicht Mock |
| 9 neue Remap-Microservices | **abgelehnt** (v1/v2) |
| Libp2p Inter-Swarm | Intent only |

---

## 6. Verweise

| Dokument / Artefakt | Rolle |
|---------------------|-------|
| `docs/STATEFUL_GRAPH_SERIE_v0.md` | topology · async_verify · wall_clock |
| `prototypes/v2_stateful_graph/` | Screen-Runner · `live_z3_latency_results.json` |
| `scripts/test_live_z3_latency.py` | Live HTTP → infra-z3 |
| `agents_b2g/protocol.py` | `broadcast`-Pfad |
| `services/fail_closed_gate/d_suite_enforcer.py` | D1–D4 app layer2 |
| `prototypes/raas_hybrid_shell/` | Facade + Gateway (sync Pilot) |
