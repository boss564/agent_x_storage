# RaaS — Hybrid KI Roadmap v0 (Core/Shell)

**Status:** ROADMAP v0 (2026-08-27) · additiv zu RaaS-Maps v0–v2 · Charter Option 1  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · KI = untrusted Shell  
**Nicht:** LLM-Freigabe, Searcher-Send, Auto-Rebalance on-chain, Anlageberatung  
**Basis:** `docs/RaaS_P9_MAPPING_v2.md` · `docs/RaaS_P9_MAPPING_v1.md` · `docs/AGENT_X_CHARTER.md`

Die vier Strategien (**Core/Shell**, **Tool-Augmented Reasoning**, **Adapter/Plugin**,
**Synthetic Data**) sind **kombinierbar** und stufenweise — nicht alternativ.

---

## 1. Zielbild (eine Zeile)

**Deterministischer 9-Agenten-Kern entscheidet und archiviert; stochastische KI-Hülle
schlägt vor und filtert; Kommunikation nur über validierte APIs; Sub-Schwärme als
Plugins; synthetische Daten trainieren eine schnelle Zweitmeinung — nie die Freigabe.**

---

## 2. Leitplanken

| Prinzip | Umsetzung | Bindung an Bestand |
|---------|-----------|-------------------|
| **Core/Shell** | P₁…P₉ + `infra-gate` + WORM = Trusted Core. KI-Hülle sandboxed, Zugang nur über Validierungs-Gateway. | Charter · Wave 39 ScopeEnforcer · v2 Blue zeichnet allein |
| **Tool-Augmented Reasoning** | Kern als Tools mit Schema (OpenAPI). Orchestrator **außerhalb** des Kerns. | `api/v1/raas/*` Proto · kein Direktzugriff auf Kernel-State |
| **Adapter/Plugin** | Red/Chain-Adapter als eigene Services; Kern unverändert. | v2 Sub-Schwarm-Intent · Compose/Helm separat |
| **Synthetic Data** | Gelabelte Runs aus P₃/P₄/P₅/P₈ → kleines Modell als **Vorfilter**. | Envelope-Labels · Kern bleibt letzte Instanz |

### Korrekturen gegenüber Roh-Entwurf (bindend)

| Roh-Formulierung | Hier |
|------------------|------|
| „Red-Team-Orchestrator (P₂)“ | **P₂ bleibt Latenz-Simulator (v1/v2).** Red-Orchestrierung = **Shell/Plugin außerhalb** des Kerns — Overlay abziehbar |
| Plugin-Methode `execute_attack` | **`run_attack_scenario` / `report_scenario`** — Simulation, kein Exploit-Send |
| Phase 5 „automatische Parameter-Korrekturen / gepatchter Code“ | Nur **Gegenmaßnahme-Kandidaten** → Kern validiert → Envelope. Kein Auto-Deploy, kein on-chain Patch |
| „Echtzeit-Risiko**entscheidungen**“ der Schnell-KI | Nur **Vorhersage / Vorfilter**; Freigabe ausschließlich deterministisch |
| Kong/Kafka/Feast/Nitro als Ist | **Intent.** Bestand: NATS (Surface), `raas-portal` Datei+HTTP, Helm Surface/D01, SoftHSM/Bunker — nicht RaaS-KI-Runtime |

---

## 2.1 Schuld — D1–D4 (layer 2 aktiv)

`live_execution=false` setzt `ScopeEnforcerAgent` (Wave 39) durch.
Zusätzlich erzwingt `services/fail_closed_gate/d_suite_enforcer.py` die
Zusagen auf Schnittstellenebene (Facade ruft vor dem Kern auf):

| ID | Zusage | Herkunft | Ist | Ergänzung später |
|----|--------|----------|-----|------------------|
| D1 | `not_investment_advice=true` | RaaS v1 | **layer2** Stamp + Free-Text-Filter | Wave-39 ScopeEnforcer komplementär |
| D2 | Red nur Sandbox; keine Gate-Felder | RaaS v2 | **layer2** Pfad + Decision-Block | OS/Container-Isolation (`test_os_isolation_subswarms.py`; Live optional `OS_ISOLATION_LIVE=1`) |
| D3 | Shell nur über Gateway-Targets | Hybrid roadmap | **layer2** Allow-List + Facade | Netz-Segmentierung |
| D4 | Ingress/Egress-only exterior | Supranode | **layer2** Exterior-Allow-List | Bus weiterhin Intent |

**Ebene 1 (sichtbar, noch nicht ScopeEnforcer):** Gateway-`health` meldet
`D1_not_investment_advice`, `D2_red_sandbox`, `D3_gateway` (siehe
`TrustedCoreGateway.health` / Facade). Sobald Code für Intake, Red-Sandbox oder
Gateway-Härtung entsteht, gehören diese drei in **dieselbe Durchsetzungskette**
wie `live_execution=false` über `ScopeEnforcerAgent` — nicht nur layer2-Stamp.

WORM-Hash-Stempel (`_worm_anchor_sha256` + `WormAnchorStore`) ist **quer** zu D1–D4
(GoBD-Anker), keine Umnummerierung von D4.

---

## 3. Phases (Roadmap, keine Schätzung als Vertrag)

Wochenangaben sind Planungsfiction. Jede Phase liefert Mehrwert; Abbruch ohne
Kern-Refactor möglich.

### Phase 0 — API-Inventur & Gateway (Fundament)

**Ziel:** Kern als versionierte Tools dokumentieren und erreichbar machen.

- Inventar P₁…P₉: Intake, Stress-Run, Gate-Evaluate, Certificate/Envelope, WORM-Append  
- Bestehend nutzen: `services/raas_portal/` (`/api/v1/raas/…`), `infra-gate` (`/v1/evaluate`)  
- Gateway-Intent: ein Zugang, Audit jedes Aufrufs → P₉-fähig (**Schuld D3**, §2.1)  
- **Ergebnis:** Kern tool-fähig; kein LLM nötig

### Phase 1 — Tool-Augmented Reasoning

**Ziel:** Externes Framework (z. B. LangGraph) ruft Tools auf; interpretiert nur strukturierte Results.

- Tool-Wrapper pro Endpoint (Schema = Vertrag)  
- Orchestrator **außerhalb** des Kerns; natürliche Sprache → Tool-Sequenz  
- Kein Zugriff auf interne Kernel-Zustände  
- **Ergebnis:** „Kern rechnet, Shell interpretiert“

### Phase 2 — Core/Shell für Strategie-Entwurf

**Ziel:** LLM-Shell schlägt Parameter vor; Kern simuliert + Z3/Gate; nur dann Markierung
„KI-vorgeschlagen, deterministisch verifiziert“.

- Vorschläge = `untrusted` bis Blue/Gate bestätigt  
- Self-Patching-**Vorschläge** = Envelope-`countermeasures`, keine Execution  
- Shell: Ressourcen-Cap, isolierter Container  
- Schuld v1: `not_investment_advice` → ScopeEnforcer-Kette beim Intake

### Phase 3 — Adversarial Sub-Swarms als Plugins

**Ziel:** Red-Szenarien (MEV/Latenz/Oracle/Shock) als ladbare Plugins.

- Interface skizze: `initialize_scenario` · `run_attack_scenario` · `report_scenario`  
- Plugins = Microservices; Kern unverändert  
- Orchestrierung der Plugins: **Shell-Adapter**, nicht Umdefinition von P₂  
- Schuld v2: Red schreibt nur Sandbox — Ebene 2 = ScopeEnforcer beim Bau

### Phase 4 — Synthetic Data & schnelles Modell

**Ziel:** Features + Labels aus Simulationsläufen → leichtes Modell (z. B. GBT) als Vorfilter.

#### Phase 4A — Schnellfilter (GBT) — **Priorisierung · IMPLEMENTIERT**

| Element | Festlegung |
|---------|------------|
| Zweck | Score = **Queue-Priorität unter Rückstau**; jede Anfrage geht trotzdem voll durch den Kern |
| Kern | unverändert; Prefilter = Untrusted Hülle (D1–D4); **kein Skip**, kein Z3-Ersatz |
| Label-Herkunft | Gate-Map §4.2 — Training nur `severity_proxy` |
| Erfolg | Warteschlangen-Metrik vs. FIFO/Null (kann FAIL) · **nicht** AUC-gegen-Gate |
| Stand | Synth · Train · Plugin · Facade-Cutover (`PREFILTER_ENABLED`, Default false) |
| Make | `raas-prefilter-batch-extremes` · `raas-prefilter-train` · `raas-gateway-prefilter-cutover` |
| Nicht jetzt | LLM-LoRA (4B) · Public-Ingest · Stufe-2 Bus-Cutover |

Training: `scripts/train_prefilter_model.py` · Plugin `plugins/risk_prefilter/`  
Details: `docs/RaaS_BUS_EXPANSION_v0.md` §4.2

#### Phase 4B — LLM Fine-Tuning (LoRA) — **nach 4A**

- Verbesserte Untrusted-Shell-Vorschläge; Output-Schema erzwingen  
- Erst wenn Feature-Pipeline und Prefilter-Integration stehen  

- Labels an Envelope/Gate-Verdict koppeln (`risk_blocked`, `breaks_at`, …)  
- Model Registry Intent; Confidence-Schwelle; bei Unsicherheit → voller Kernlauf  
- **Nie** reine Modell-Freigabe

### Phase 5 — Kontinuierlicher Zyklus (Clearance-Loop)

**Ziel:** Angriff → Verifikation → Kandidaten → erneuter Kernlauf → Envelope/WORM.

- Permanent neue **Szenario-Kampagnen** (nicht Live-Bedrohungs-Execution)  
- P₆/Gate: Beweis / BLOCKED|RELEASED; P₉: Archiv  
- LLM darf Varianten vorschlagen; Kern testet  
- Abbruchkriterium: dokumentierte Clearance, nicht „alle Angriffe besiegt“ als Marketing

---

## 4. Sicherheitsrisiken (Kurz)

| Risiko | Gegenmaßnahme |
|--------|----------------|
| LLM-Halluzination | Nur Schema-Vorschläge; Kern verwirft + Audit-Event |
| Stochastik im Safety-Pfad | Seeded RNG nur im Kern; KI keine Safety-Zufallsentscheidung |
| Modell-Bias / OOD | Synthetische Coverage + Unsicherheit → voller Lauf |
| Latenz-Druck | Score priorisiert unter Rückstau; Freigabe = Kern; kein Skip als „Ersparnis“ |
| Compliance | Jeder Shell-/Plugin-Schritt gateway-protokolliert → WORM |

---

## 5. Nächste Schritte (konkret, klein)

1. **API-Inventur** gegen bestehenden Proto (`raas-portal`, `infra-gate`) — keine Parallel-API erfinden  
2. **Ein** Tool-Wrapper + ein Shell-Orchestrator (Phase 1 Pilot) — Simulation anstoßen, Result lesen  
3. Kein Phase-5-Auto-Patch-Code, bevor Schuld **D1–D3** in ScopeEnforcer/Gateway sitzt  
4. Red-Plugins erst nach Interface-Namen ohne `execute_*`-Send-Semantik

---

## 6. Implementierungsstand

| Schicht | Stand |
|---------|--------|
| Trusted Core (P-Rollen, Gate, Proto) | ✅ Maps v0–v2 + `services/raas_portal/` |
| Diese Roadmap | ✅ Dokument |
| Phase-1 Pilot Core/Shell | ✅ `prototypes/raas_hybrid_shell/` · `scripts/test_raas_hybrid_shell.py` |
| Neues `agents/p1…p9` Remap | **abgelehnt** — v1-Rollen bleiben; `agents/` = Air/Surface/Mechanized |
| Tool-Wrapper / LangGraph / LLM-Shell | Pilot: synthetische Shell; echtes LLM **nicht gebaut** |
| Adversarial Plugins / Feature-Store / Schnell-Modell | ✅ MEV+Oracle Plugins · Synth-Prefilter · Queue-Cutover (Phase 4A) |
| Validierungs-Gateway (D3) | Facade + `DSuiteEnforcer` layer2 · Wave-39 ScopeEnforcer komplementär |
| D-Suite barriers | ✅ `d_suite_enforcer.py` · `make raas-d-suite` |
| Phase 4A Prefilter | ✅ Train + `GATEWAY_CUTOVER_PASS` / `GATEWAY_FALLBACK_PASS` · Default OFF |
| Phase 4B LLM-LoRA / Public-Ingest | Public-Ingest = §4.3 Kalibrierung (nach Seed-Spread); 4B eigener Bedarf |
| Order-Send / Searcher / Auto-Rebalance | **gesperrt** |
| D1–D3 → ScopeEnforcer (Ebene 2) | **offen** — Health zeigt Schuld; Kette analog `live_execution` bei Intake/Red/Gateway |
| Vor Stufe 2: Topologie-Re-Screen | **bindend** — Bus-Expansion §4.1 · ~16 s · Ring vs. complete |

---

## 7. Verweise

| Dokument | Rolle |
|----------|-------|
| `docs/RaaS_BUS_EXPANSION_v0.md` | Bus/Sub-Schwarm — Topologie-Gate vor Stufe 1 |
| `docs/RaaS_SUPRANODE_v0.md` | Ingress/Egress-Facade · kein P-Remap |
| `docs/RaaS_P9_MAPPING_v2.md` | Red/Blue Overlay · Sandbox-Schuld |
| `docs/RaaS_P9_MAPPING_v1.md` | Strategie · Envelope · Advice-Schuld |
| `docs/RaaS_P9_MAPPING_v0.md` | Contract-RaaS Proto |
| `docs/AGENT_X_CHARTER.md` | Negativklausel |
| `services/fail_closed_gate/` | Gate Core |
| `services/raas_portal/` | Laufender Tool-Kern (Contract-shaped) |
| `prototypes/raas_hybrid_shell/` | Phase-1 Pilot: Untrusted Shell → TrustedCoreGateway |
