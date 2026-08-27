# RaaS — Strategy Stress Mapping (P₁…P₉) v1

**Status:** MAP v1 (2026-08-27) · additiv zu v0 · bindend unter Charter Option 1  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · keine Order-Execution · `live_execution=false`  
**Nicht:** Anlageberatung, Portfolio-Steuerung, Searcher-/Bundle-Send  
**Basis:** `docs/RaaS_P9_MAPPING_v0.md` · `docs/AGENT_SWARM_P9_MAP_v0.md` · `docs/AGENT_X_CHARTER.md`

v0 bleibt gültig (Contract-Intake). v1 ändert **nur die Eingabe** — gleiche 9 Rollen,
gleicher Runner, gleiches Gate, gleicher Exporter.

---

## 1. Produkt (eine Zeile)

**Strategie einreichen → P₂–P₈ simulieren Belastungsgrenzen → Safety Envelope
(Gutachten, keine Prognose).**  
Agent X führt die Strategie nicht aus.

---

## 2. Was sich ändert / was nicht

| | v0 | v1 |
|--|----|----|
| Eingabe | Smart Contract (Bytecode/ABI) | Strategie-Deskriptor (Regeln, Limits, Intervall) |
| P₁ | Contract-Parser | Strategie-Parser |
| P₉ Output | Audit-Zertifikat | **Safety Envelope** (Zertifikat bleibt Hülle) |
| P₂–P₈ | unverändert defensiv | unverändert defensiv |
| Portal / Runner / Gate | `services/raas_portal/` | **kein Code-Wechsel in dieser Map** |
| Charter | Option 1 | Option 1 |

Zahlen in Beispiel-Envelopes sind **erkennbar synthetisch** (runde Unmöglichkeiten),
keine Messwerte. Ein Etikett „Illustrator“ allein reicht nicht — die Werte selbst
dürfen nicht als Labormessung zitierbar sein.

---

## 3. Regulatorische Einordnung (Produkt, kein Rechtsgutachten)

| Aspekt | Haltung in dieser Map |
|--------|------------------------|
| BaFin / MiCA | Risk Analytics / Simulations-Software — **keine** Anlageberatung, kein Vermögensverwaltung, kein Handel für den Kunden |
| Kundenfrage | „Unter welchen simulierten Bedingungen bricht *diese* Strategie?“ |
| Nachweisform | Safety Envelope = harte Belastungsgrenzen + Gegenmaßnahme-**Kandidaten** |
| Was fehlt bewusst | Kauf-/Verkaufsempfehlung, Soll-Rendite, Auto-Rebalance on-chain |

Wahrheit vor Optik: Zulassungsfreiheit ist eine **Produktabsicht**, keine
bescheinigte BaFin-Auskunft. Jeder Envelope trägt `not_investment_advice=true`.

**Schuld (v1):** `not_investment_advice` ist hier **Ebene 1** (Deklaration in der Map).
`live_execution=false` läuft bereits durch `ScopeEnforcerAgent` (Wave 39) — angehängt,
validiert, weitergereicht. Sobald Strategie-Intake gebaut wird, gehört
`not_investment_advice=true` in **dieselbe Durchsetzungskette** (sonst hängt die
Abgrenzung an der Disziplin des Exporters). Bis dahin: Feld im Schema, keine Runtime-Gate.

---

## 4. Agent ↔ Strategie-Kalkulation

Rollen identisch zu v0; nur der Intake-Typ wechselt.

| Agent | Strategie-Kalkulation | v0-Rolle |
|-------|----------------------|----------|
| **P₁** | Strategie-Parser (z. B. Rebalancing-Intervall, max. Slippage) | Contract-Parser |
| **P₂** | Latenz-Jitter (Netzwerkstau bei *simulierter* Ausführung) | Latenz-Simulator |
| **P₃** | Order-Sprünge belasten die Regel (Execution-Pressure, simuliert) | Execution-Pressure |
| **P₄** | MEV-Szenarien gegen die Regel (Sandwich/Frontrun — **kein** Bundle-Send) | MEV Scout |
| **P₅** | Verrauschte Oracle-Signale | Oracle-Stress |
| **P₆** | Z3: Break-Even / Unsat der Safety-Invarianten | Z3 Auditor |
| **P₇** | Schock-Szenarien (z. B. De-Peg in n Blöcken, simuliert) | Shock Injector |
| **P₈** | Kaskaden-Liquidationen modellieren | Kaskaden-Modellierer |
| **P₉** | Safety Envelope exportieren (JSON/Markdown, WORM) | Audit-Anchor |

---

## 5. Ablauf

```text
Input:         Strategie (Deskriptor + Tenant + Profil)
Durchrechnung: P₂–P₈ — Markt-/Latenz-/MEV-/Oracle-/Schock-/Kaskaden-Simulation
Gate:          infra-gate · M7 ∧ Z3 ∧ BHO · human latch CLOSED · live_execution=false
Output:        Safety Envelope (Risikoprofil + Gegenmaßnahme-Kandidat)
```

### 5.1 Beispiel-Envelope (synthetisch — nicht zitierbar als Messung)

Werte absichtlich unmöglich: 1 ms bei 99,99 % „Stabilität“ plus Totalverlust.
Wer das als Labormessung weiterleitet, zitiert Unfug, nicht ein Etikett.

```text
Risikoprofil:    SYNTHETIC_EXAMPLE — bricht bei Latenz > 1 ms;
                 simultaner Totalverlust 99,99 % und Stabilität 99,99 %.
Gegenmaßnahme:   Kandidat „M7-Filter an 1-ms-Spike“ — keine Empfehlung,
                 keine Execution, kein behaupteter Live-Ertrag.
```

Kunden-Satz: **Bedingungen des Bruchs**, nicht „die Strategie wird gewinnen“.

---

## 6. Safety Envelope (P₉-Format)

Mindestfelder — Erweiterung des v0-Zertifikats, keine zweite Pipeline:

| Feld | Inhalt |
|------|--------|
| `envelope_id` | SHA-256 über kanonisches JSON (wie `certificate_id`) |
| `input_kind` | `strategy` (v1) \| `contract` (v0) |
| `strategy_hash` / `contract_sha256` | Intake-Bindung |
| `holds_under` | Szenario-Cluster, in denen Gate-Risiko unter Schwelle |
| `breaks_at` | erste verletzte Dimension (Latenz, Oracle, Cascade, Shock, …) |
| `countermeasures` | Kandidaten (Filter, Intervall, Limit) — **keine** Execution |
| `gate_verdict` / `audit_verdict` | wie v0 (`risk_block_rate` vs Human-Latch) |
| `scope` | `DEFENSIVE_CAUSAL_GROUNDING` |
| `live_execution` | `false` |
| `not_investment_advice` | `true` — **Schuld:** Durchsetzung wie `live_execution` erst beim Intake (Wave 39) |
| `worm_tail_hash` | P₉ Hash-Kette |

JSON + Markdown zuerst (bestehender Exporter). PDF/A-3 später wie v0.

---

## 7. Intake-Skizze (additiv, nicht gebaut)

Bestehende Routen (`/contracts/upload`, `/runs`, `/certificate`) bleiben.
Strategie ist ein zweiter Intake — gleiches Run-/Gate-/Export-Gerüst:

| Methode | Pfad | Rolle |
|---------|------|-------|
| `POST` | `/strategies/upload` | P₁ — Deskriptor (Intervall, Slippage-Cap, Universe-ID) |
| `POST` | `/runs` | wie v0; `input_kind=strategy` + `strategy_id` |
| `GET` | `/runs/{id}/envelope` | Alias auf Zertifikat mit Envelope-Feldern |

Kein Code in dieser Map. Proto bleibt Contract-shaped, bis Intake explizit erweitert wird.

---

## 8. Gate & Charter (unverändert)

```text
Default:         Gate CLOSED · live_execution=false
Kunden-Output:   Envelope / Zertifikat — keine Trade-Freigabe
Freigabe:        Mensch + Token (infra-gate) — nie Auto-Exec der Strategie
Wave 39:         ScopeEnforcer · fail-closed
```

Strategie-Kalkulation **erweitert nicht** den Execution-Pfad. P₄/P₈ bleiben Szenario,
nicht Searcher.

---

## 9. Geschäftsmodell (ROI, nicht Implementation)

| Zielgruppe | Frage, die das Envelope beantwortet |
|------------|--------------------------------------|
| Fonds / Desk | Wo bricht *unsere* Regel unter Latenz/MEV/Oracle? |
| Market-Maker | Ab welchem Jitter kippt Rebalancing in Gift? |
| Protokoll-Treasury | Kaskade vs. eigene Parameter — simuliert |

Abrechnung weiter außerhalb dieses Repos.

---

## 10. Implementierung

| Schicht | Stand |
|---------|--------|
| v0 Portal / Runner / Exporter / Smoke | ✅ unverändert (`make raas-smoke`, `:8020`) |
| Strategie-Parser (P₁) | **nicht gebaut** — Map only |
| Envelope-Felder im Exporter | **nicht gebaut** — Schema oben |
| `not_investment_advice` Runtime-Gate | **Schuld** — Ebene 1 in dieser Map; Ebene 2 = ScopeEnforcer analog `live_execution` |
| Live-Rebalancing / Order-Send | **gesperrt** (Charter) |

---

## 11. Verweise

| Dokument | Rolle |
|----------|-------|
| `docs/RaaS_P9_MAPPING_v0.md` | Contract-RaaS, API, Proto-Stand |
| `docs/AGENT_SWARM_P9_MAP_v0.md` | P-Agenten, Compose, Gate |
| `docs/AGENT_X_CHARTER.md` | Negativklausel |
| `services/raas_portal/` | Laufender Proto (Contract-Intake) |
