# RaaS — Red/Blue Overlay Mapping (P₁…P₉) v2

**Status:** MAP v2 (2026-08-27) · additiv zu v0/v1 · bindend unter Charter Option 1  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · keine Order-Execution · `live_execution=false`  
**Nicht:** Searcher-/Bundle-Send, Auto-Patch on-chain, Anlageberatung  
**Basis:** `docs/RaaS_P9_MAPPING_v1.md` · `docs/RaaS_P9_MAPPING_v0.md` · `docs/AGENT_X_CHARTER.md`

v0/v1 bleiben die **Rollen-Quelle**. v2 legt Teams und Sub-Schwärme **darüber** —
keine Umbenennung der P-Funktionen, kein Code in dieser Map.

---

## 1. Produkt (eine Zeile)

**Red simuliert Belastungsangriffe gegen die eingereichte Strategie/Contract;
Blue prüft Invarianten und archiviert; Output bleibt Safety Envelope.**

Red **führt nicht aus**. Blue **empfiehlt nicht**. Mixed **stellt die Bühne**.

---

## 2. Was sich ändert / was nicht

| | v1 | v2 |
|--|----|----|
| P₁…P₉ Funktionen | Strategie-/Contract-RaaS | **unverändert** |
| Neu | — | Team-Overlay Red / Blue / Mixed |
| Neu | — | Sub-Schwarm-Hierarchie (Multi-Chain, Map only) |
| Neu | — | 6-Schritte-Zyklus (Protokoll-Skizze) |
| Portal / Runner / Gate | Contract-shaped Proto | **kein Code-Wechsel** |
| Charter | Option 1 | Option 1 |

P-Funktionen nicht neu zuordnen. „MEV-Bot“ / „Oracle-Manipulator“ in der
Team-Spalte heißt **Szenario-Generator**, nicht Live-Exploit.

---

## 3. Team-Overlay (bestehende Rollen)

| Team | Agenten | v1-Funktion | Team-Lesart |
|------|---------|-------------|-------------|
| **Blue** | P₁, P₆, P₉ | Parser · Z3 Auditor · Audit-Anchor | Intake-Invarianten, fail-closed Beweis, WORM/Envelope |
| **Red** | P₂, P₅, P₇, P₈ | Latenz · Oracle-Stress · Shock · Kaskade | simulierte Angriffe / Schocks gegen die Regel |
| **Mixed** | P₃, P₄ | Execution-Pressure · MEV-Scout | Markt- und Netzwerk**bedingungen** — von Red und Blue gelesen |

P₄ bleibt MEV-**Szenario** (v1), nicht Mixed-„Netzwerk“ als neue Funktion.
P₂ bleibt Latenz-Simulator, nicht ein zweiter Orchestrator.

**Regel:** Red darf nur in die Sandbox schreiben (Szenario-Telemetrie).
Blue allein darf Gate-Verdict und Envelope zeichnen. Mixed schreibt keine
Freigabe.

**Schuld (v2):** Diese Gewaltenteilung ist **Ebene 1** (Regel im Dokument).
`live_execution=false` setzt `ScopeEnforcerAgent` (Wave 39) zur Laufzeit durch.
Beim Bau des Intake gehört „Red schreibt nur Sandbox / Blue allein zeichnet“
in **dieselbe Kette** — sonst ist die Trennung so belastbar wie die Disziplin
der Implementierung. Bis dahin: Map-Regel, kein Runtime-Gate.

---

## 4. Sub-Schwärme (neue Ebene, nicht gebaut)

Ein Sub-Schwarm = **Kopie der 9 Rollen** gebunden an `chain_id` (z. B. Gnosis,
peaq, Anvil). Keine neuen P-Nummern.

```text
Root (Tenant-Run)
 ├── Sub-Schwarm chain=A   P1…P9  + Team-Overlay
 ├── Sub-Schwarm chain=B   P1…P9  + Team-Overlay
 └── Envelope-Merge (P₉ root) — eine Hülle, chain-lokale breaks_at[]
```

Dynamische Hierarchie: Root startet Sub-Schwärme nach Universe/Chain-Liste
im Intake. Skalierung ist **Intent** (`charts/agent-x/` = Surface/D01/KEDA,
nicht RaaS-P9-Runtime). RaaS-Compose bleibt `podman-compose.p9.yml`.

Schuld: kein per-chain Runner im Proto; ein Run = ein Intake, eine Chain-Fiction.

---

## 5. Kommunikationsfluss (Skizze, nicht implementiert)

```text
1. Initialisierung   Blue P1 parst · Invarianten-Vorfilter
2. Angriff           Red P2/P5/P7/P8 + Mixed P3/P4 injizieren Szenarien
3. Verifikation      Blue P6 (Z3/BHO) + infra-gate (M7, Human-Latch CLOSED)
4. Patch             Gegenmaßnahme-Kandidaten ins Envelope — keine Execution
5. Iteration         nächster Szenario-Cluster (gleicher run_id) oder Halt
6. Audit             Blue P9 WORM + Envelope (not_investment_advice Schuld v1)
```

Schritt 4 ist **Dokumentation von Kandidaten**, kein Auto-Rebalance.
NATS/Message-Queue: bestehend für Surface (C01–C09), nicht verdrahtet mit
`services/raas_portal/`. Z3: `infra-z3` / P₆ — optional für RaaS-Portal-Start.

---

## 6. Gate & Charter (unverändert, verschärfte Lesart)

```text
Red:             Simulation only · kein Bundle · kein Liquidation-Send
Blue:            Gate + Archiv · live_execution=false immer
Mixed:           Umwelt, keine Freigabe
Human latch:     CLOSED · Token nur Operator
Wave 39:         ScopeEnforcer
not_investment_advice:  Schuld v1 — Ebene 1 bis Intake (gleiche Kette wie live_execution)
Red-Sandbox-only:       Schuld v2 — Ebene 1 bis Intake (gleiche Kette wie live_execution)
```

Ein Red-Schritt, der Execution andeutet, ist Map-Verstoß, kein Feature.

---

## 7. Technische Zuordnung (Wahrheit vor Optik)

| Behauptung | Ist-Zustand |
|------------|-------------|
| Message-Queue | NATS im P9-/Surface-Stack; RaaS-Portal = Datei-Store + HTTP |
| Z3 | `services/z3_solver/` · Gate-Score lokal; HTTP-Z3 additiv |
| Kubernetes | Helm `charts/agent-x/` (KEDA/Surface) — **nicht** RaaS-Red/Blue |
| WORM | Proto `audit.worm.jsonl` + P₉-Rolle; GoBD-PDF/A-3 später |

v2 beschreibt **wer darf was**, nicht dass Sub-Schwärme laufen.

---

## 8. Implementierung

| Schicht | Stand |
|---------|--------|
| v0/v1 Maps + Contract-Proto | ✅ unverändert |
| Team-Overlay im Runner | **nicht gebaut** — Map only |
| Sub-Schwarm-Spawn | **nicht gebaut** |
| 6-Schritte-Orchestrierung | **nicht gebaut** (Smoke bleibt linear) |
| Red-Sandbox / Blue-Zeichnung Runtime-Gate | **Schuld** — Ebene 1 in dieser Map; Ebene 2 = ScopeEnforcer analog `live_execution` |
| Order-Send / Searcher | **gesperrt** |

---

## 9. Verweise

| Dokument | Rolle |
|----------|-------|
| `docs/RaaS_P9_MAPPING_v1.md` | Strategie, Envelope, Advice-Schuld |
| `docs/RaaS_P9_MAPPING_v0.md` | Contract-RaaS, API, Proto |
| `docs/AGENT_SWARM_P9_MAP_v0.md` | P-Artefakte, Compose, Gate |
| `charts/agent-x/` | K8s Intent (nicht diese Map als Runtime) |
| `services/raas_portal/` | Laufender Proto |
