# RaaS — Multi-Schwarm-Schiedsrichter Mapping (P₁…P₉) v3

**Status:** MAP v3 (2026-08-27) · additiv zu v0/v1/v2 · bindend unter Charter Option 1  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · keine Order-Execution · `live_execution=false`  
**Nicht:** Searcher-/Bundle-Send, Auto-Patch on-chain, Anlageberatung, geteilte Modellgewichte ohne Mandantenentscheid  
**Basis:** `docs/RaaS_P9_MAPPING_v2.md` · v1 · v0 · `docs/AGENT_X_CHARTER.md` ·
`docs/RaaS_BUS_EXPANSION_v0.md` §4.3 (Referenz A · Haltepunkt)

v0/v1/v2 bleiben **unberührt**. v3 ist keine Umbenennung der P-Funktionen und kein
Code. Es fasst eine **Lesart** (vier Rollen) und den **Multi-Schwarm-Betrieb** —
Policy in §4 **entschieden** (2026-08-27); Bau gesperrt bis M1/Envelope-Schuld.

---

## 1. Produkt (eine Zeile)

**Als Schiedsrichter für mehrere Schwärme prüft Agent X eingereichte Strategien
unter simulierten Lasten und liefert Safety Envelopes — ohne Ausführung, ohne
Empfehlung, ohne stilles Lernen über Mandantengrenzen.**

Ein-Kunden-RaaS (v0–v2) bleibt gültig. Multi-Schwarm ist die **Erweiterung der
Betriebsannahme**, nicht vier neue Bausteine.

---

## 2. Was sich ändert / was nicht

| | v2 | v3 |
|--|----|----|
| P₁…P₉ Funktionen | unverändert (v0/v1) | **unverändert** |
| Red/Blue / Sub-Schwärme | Overlay v2 | **unverändert** — hier nur referenziert |
| Neu | — | Vier Rollen = **Sichtweise** auf Vorhandenes |
| Neu | — | Multi-Schwarm: drei Punkte (§4) — **entschieden** (2026-08-27) |
| Portal / Prefilter / Wave-8 Isolator | Proto / Default OFF / B2G-Welle | **kein Code-Wechsel in dieser Map** |
| Charter | Option 1 | Option 1 |

Wahrheit vor Optik: Wer v3 in sechs Monaten als „vier neue Module“ liest, liest
falsch. Die Rollen benennen, was schon da ist; die Arbeit liegt in §4.

---

## 3. Vier Rollen — Sichtweise auf Vorhandenes

Keine neue Fähigkeit. Mapping auf bestehende Schichten:

| Rolle (Lesart) | Was sie meint | Bereits vorhanden |
|----------------|---------------|-------------------|
| **Immunsystem-Auditor** | Formale Prüfung, Safety Envelope | **P₆** Z3 / `infra-z3` · Invarianten · Envelope-Inhalt (v1) |
| **Hazard Specialist** | Signal vs. Rauschen unter Extremlast | **P₂** Latenz-Simulator · Gate **M7**-Filter · Red-Szenarien P₅/P₇/P₈ (v2) |
| **Kryptografischer Notar** | Nachweisbare Archivierung | **P₉** Audit-Anchor · GoBD-WORM · Z3-Proof-Header im Zertifikat/Exporter |
| **Fail-Closed Shield** | Schnittstelle kappt bei Invarianten-Bruch | Gate-Logik · `DEFENSIVE_CAUSAL_GROUNDING` · Human-Latch · ScopeEnforcer (`live_execution=false`) |

**Regel:** Diese Tabelle ist Glossar, keine Roadmap-Lieferung. Implementierungsstand
bleibt der von v0–v2 und den Gate-/Portal-Artefakten — nicht der Rollenname.

Red/Blue (v2) ordnet dieselben P-Rollen Teams zu; die vier Lesarten schneiden
**quer** dazu (Blue trägt Auditor/Notar/Shield-Anteile, Red/Mixed den Hazard-Anteil).
Kein Widerspruch, keine zweite Hierarchie.

---

## 4. Multi-Schwarm — drei Punkte (entschieden 2026-08-27)

Der Ein-Einreicher-Pfad (v1) analysiert *eine* Strategie. Als Schiedsrichter für
**mehrere** Schwärme gelten die Wahlen unten. Haltung: konservativ, defensiv —
`DEFENSIVE_CAUSAL_GROUNDING` · Fail-Closed · Wahrheit vor Optik.

### 4.1 Mandantentrennung — **Wahl: Verzeichnis-Schuld akzeptieren**

| Heute | Lücke |
|-------|--------|
| `services/raas_portal/` kennt `tenant_id` (Default `"demo"`) und legt Runs unter `{data_root}/{tenant_id}/…` ab | Pfad-Präfix ≠ kryptografische / DB-Isolation |
| Wave-8 `MultiTenantIsolatorAgent` (AES-256 je Tenant, DB-Routing, Cross-Tenant-Leak-Detection) | **nicht** an RaaS-Portal / Hybrid-Shell / Prefilter verdrahtet |
| Hybrid-Shell `TrustedCoreGateway(tenant_id=…)` | ein String pro Prozess, kein Isolator-Gate |

**Entscheidung:** `tenant_id` als **Verzeichnis-Schuld** (Default `demo`) belassen —
methodische Präzisierung, kein Isolator-Versprechen. Wave-8-Isolation bleibt eine
**separate Ebene** (eigener Bau-Schritt, nicht stillschweigend mitclaimen).

Multi-Schwarm-Betrieb **nicht** als „kryptografisch mandantenfähig“ claimen.
Claim-Form: Pfad-Trennung ja · Isolator nein, bis Wave-8 (oder Äquivalent) verdrahtet ist.

### 4.2 Prefilter als Leckkanal — **Wahl: M1**

| Heute | Risiko |
|-------|--------|
| Ein geteiltes GBT (`PREFILTER_MODEL_PATH`, Default OFF) | Trainingsläufe von Mandant A fließen in Gewichte, die Mandant B priorisieren |
| Referenz A: 8 feste Holdouts, Claim Mittel ± σ über Sets (`docs/RaaS_BUS_EXPANSION_v0.md` §4.3) | Zusammensetzung der Eval-Menge = **wessen Daten** |
| Haltepunkt Public-Ingest | Keine Neukalibrierung ohne Auslöser |

| Option | Inhalt | Status |
|--------|--------|--------|
| **M1** Prefilter je Mandant | eigene Gewichte / eigenes Manifest | **gewählt** |
| **M2** gemeinsames Modell | ein Artefakt für alle | **abgelehnt** — Leakkanal; „schützt alle Mandanten“ wäre falsch |
| **M3** kein Prefilter im Multi-Schwarm | FIFO bis Isolationsentscheid | Reserve, falls M1 nicht gebaut |

**Begründung M1:** Passt zu Fail-Closed und GoBD-Audit-Integrität; verhindert
Cross-Tenant-Lernen in den Gewichten (Kaskaden/Priorisierung). Ops-Kosten bewusst
akzeptiert. Referenz A bleibt Eval-Disziplin **pro** Mandanten-Artefakt — ersetzt
keine Mandantenentscheidung.

Bis M1 gebaut ist: Multi-Schwarm + geteilter Prefilter **gesperrt** (Default OFF
reicht nicht als Dauerlösung, wenn Mandanten-Train startet).

### 4.3 Aussagen über Nichteinreicher — **Wahl: strikt isoliert**

Ein Envelope für Schwarm A kann Bedingungen nennen, unter denen A bricht. Entstehen
diese Bedingungen aus dem **Verhalten oder den Daten von B**, ist das eine Aussage
über B ohne B's Einreichung.

| Ebene | Haltung (bindend) |
|-------|-------------------|
| Default | Envelope spricht **nur** über den Einreicher (`tenant_id` des Runs) |
| Shared-State / Cross-Party | **verboten**, bis ein Screen/Proof zeigt, dass relationale Struktur nicht bricht — und Policy schriftlich nachzieht |
| Technik | Schema-Schuld später: keine stillen Counterparties; ggf. `subjects[]` nur Einreicher |
| Charter | Option 1 + `not_investment_advice` reichen **nicht** als Cross-Party-Freigabe |

**Entscheidung:** konservativ — Mandantentrennung strikt; keine Shared-State-Annahmen
ohne expliziten Proof. Isolation ist die Default-Haltung, nicht die Ausnahme.

---

## 5. Abgrenzung zu v2 Sub-Schwärmen

v2 §4: Sub-Schwarm = Kopie P₁…P₉ je `chain_id` **innerhalb eines Tenant-Runs**.  
v3 Multi-Schwarm = **mehrere Mandanten / konkurrierende Parteien** auf dem Marktplatz.

```text
v2:  ein Tenant-Run  →  Sub-Schwärme je Chain     (Intent, nicht gebaut)
v3:  viele Tenants   →  Schiedsrichter-Rolle      (Intent; §4.1–§4.3 gewählt · Bau offen)
```

Beides orthogonal. Chain-Hierarchie löst keine Mandanten- oder Prefilter-Leak-Frage.

---

## 6. Gate & Charter (unverändert)

```text
DEFENSIVE_CAUSAL_GROUNDING · live_execution=false · Fail-Closed
not_investment_advice=true (v1 Schema-Schuld → Scope-Kette bei Strategie-Intake)
Red schreibt nur Sandbox · Blue allein zeichnet (v2 Ebene-1; Runtime-Schuld offen)
```

Kein Multi-Schwarm-Claim ändert die Negativklausel. Schiedsrichter ≠ Ausführungsagent.

---

## 7. Nicht jetzt / Auslöser

| Arbeit | Status |
|--------|--------|
| Vier Rollen als Code-Module | **abgelehnt** — nur Lesart (§3) |
| §4.1 / §4.2 / §4.3 Policy | **entschieden** — Verzeichnis-Schuld · **M1** · Envelope nur Einreicher |
| Multi-Schwarm-Betrieb produktiv | **gesperrt** bis M1-Prefilter + Envelope-Schuld im Proto (Policy steht) |
| Prefilter DEFAULT_ON | **gesperrt** (Bus-Expansion Haltepunkt; Multi-Tenant nur unter M1) |
| Prefilter geteilt (M2) | **abgelehnt** |
| Pfad 1 Kalibrierung gegen Referenz A | Pause bis Auslöser (Bus-Expansion); bei Multi-Tenant je Mandant |
| Pfad 2 Ursachenanalyse Holdouts | nach A; optional |
| Wave-8 Isolator → RaaS-Pfad | Intent · **separate** Ebene (§4.1); nicht Voraussetzung für M1-Pfad-Schuld |
| v0/v1/v2 überschreiben | **verboten** |

**Auslöser für v3-Bau:** M1-Artefaktpfad (`…/{tenant_id}/prefilter/`) · Envelope
nur-Einreicher-Schuld im Exporter · optional Wave-8-Verdrahtung als eigene Stufe.

---

## 8. Verweise

| Dokument / Artefakt | Rolle |
|---------------------|-------|
| `docs/RaaS_P9_MAPPING_v0.md` | Contract-RaaS Proto |
| `docs/RaaS_P9_MAPPING_v1.md` | Strategie · Envelope · Advice-Schuld |
| `docs/RaaS_P9_MAPPING_v2.md` | Red/Blue · Sub-Schwärme je Chain |
| `docs/RaaS_BUS_EXPANSION_v0.md` §4.3 | Referenz A · Prefilter-Haltepunkt |
| `docs/RaaS_HYBRID_KI_ROADMAP_v0.md` | Phase 4A/4B |
| `docs/AGENT_X_CHARTER.md` | Negativklausel |
| `agents_b2g/ops/pilot_agents.py` | `MultiTenantIsolatorAgent` (Welle 8, nicht RaaS-verdrahtet) |
| `services/raas_portal/` | `tenant_id` Pfad-Schuld |
| `plugins/risk_prefilter/` · `prototypes/raas_hybrid_shell/` | geteiltes Modell · Default OFF |
