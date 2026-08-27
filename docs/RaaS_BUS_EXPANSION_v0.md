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

**Gate vor Stufe 1:** Topologie-Screen (oder Äquivalent) gegen das **tatsächliche
Zustellmuster** des geplanten Bus (Subjects + Queue-Groups). Verdict muss
zeigen: Muster zählt als Ring (⟨k⟩≈1 / Margin hält), nicht als complete.
Dauer: Minuten, nicht Wochen.

### 2.2 „Kern bleibt unangetastet“ gilt für Stufe 1 nicht

Stufe 1 ersetzt synchrone Aufrufe durch asynchrone Events — das **ist** der Kern.

`async_verify` (`HYPOTHESIS_CONFIRMED`, Margin_Δ=0, ≈4× tps) gilt für ein
**Pipeline-Parallelitätsmodell** mit **identischer Ereignisreihenfolge** und
gemessenen Per-Txn-ms — **nicht** für Netzlatenz und Umordnung unter NATS.

Dokumentation darf Stufe 1 nicht als „Overlay ohne Kernänderung“ verkaufen.

### 2.3 „Echtzeit-Insolvenz-Prüfung“ ist nicht belegt

`wall_clock_verify` nutzt `mock_z3_bho_verify` — Mock SAT/BHO, **kein** Live-HTTP
zu `infra-z3`. Die gemessenen ms sind CPU-Proxy.

**Regel:** Das Wort „Echtzeit“ (Z3/Insolvenz) erscheint in Maps/Roadmaps erst nach
gemessener **Live**-Latenz gegen `infra-z3` (p50/p99, N-Läufe, Seeds fest).

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
      └─ FAIL (complete/hub-Semantik) → Entwurf ändern, kein JetStream-Cutover
1.  Stufe 1: Core-Bus nur wenn Gate 0 PASS (Queue-Group-Ring)
2.  Live-Z3-Latenz messen (infra-z3) → erst dann „Echtzeit“-Sprache
3.  Red-Team-Plugin (MEV/Latency) unter /sandbox/ + D2 OS-Isolation
4.  Oracle / Liquidity Plugins nach Bedarf
5.  Inter-Swarm (WSS/Libp2p) — zuletzt; P₉-Signatur + Z3-Header Intent
```

Stufe 2 (Gateway/Shell-Bus) kann parallel zur Facade bleiben; sie ersetzt nicht Gate 0.

---

## 5. Nicht jetzt

| Arbeit | Status |
|--------|--------|
| NATS JetStream Cutover für RaaS-P9 | **gesperrt** bis Gate 0 |
| Broadcast-Subjects als Steuerpfad | **gesperrt** (Serie) |
| „Echtzeit-Insolvenz“ in Pitch/Map | **gesperrt** bis Live-Z3 |
| 9 neue Remap-Microservices | **abgelehnt** (v1/v2) |
| Libp2p Inter-Swarm | Intent only |

---

## 6. Verweise

| Dokument / Artefakt | Rolle |
|---------------------|-------|
| `docs/STATEFUL_GRAPH_SERIE_v0.md` | topology · async_verify · wall_clock |
| `prototypes/v2_stateful_graph/` | Screen-Runner |
| `agents_b2g/protocol.py` | `broadcast`-Pfad |
| `services/fail_closed_gate/d_suite_enforcer.py` | D1–D4 app layer2 |
| `prototypes/raas_hybrid_shell/` | Facade + Gateway (sync Pilot) |
