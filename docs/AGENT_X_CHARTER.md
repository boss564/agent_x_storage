# Agent X — Defensive Charter (Ebene 4)

**Status:** Bindend für Wave 39 Ethical Boundary Enforcement  
**Version:** 1.0 (2026-08-23)  
**Geltungsbereich:** Agent X Core, B2G, Wave 38 (Diagnostic), Wave 28 (Defense), Wave 39 (Enforcement)

---

## 1. Zweck

Agent X ist ein **defensives** Risiko- und Signal-System. Es liefert Kausal-Analyse,
Risikomanagement und Rausch-Eliminierung — **keine** offensive Wertabschöpfung.

Diese Charta ist die normative Quelle für Wave 39 `CharterEnforcerAgent` und
`AirGapValidator`. Verstöße invalidieren operative Freigaben (`BLOCKED`).

---

## 2. Vierfach-Sperre (bindend)

| Ebene | Mechanismus | Durchsetzung (Wave 39) |
|-------|-------------|------------------------|
| **1 — Wissenschaftlich** | Pre-Reg-Negativklauseln; Protokollbruch → Gültigkeit erlischt | `PreRegFirewallAgent` |
| **2 — Programmatisch** | Runtime-Assertions, fail-closed | `EthicalAssertionAgent`, `ScopeEnforcerAgent` |
| **3 — Auditierbar** | GoBD-WORM, `OBSERVATION_AND_DEFENSE` | `AuditTrailAgent`, `IntegrityViolationDetector` |
| **4 — Architektonisch** | Air-Gap zu Gewinn-Systemen; Identitätsschutz | `CharterEnforcerAgent` |

---

## 3. Negativ-Klausel (§1.0.E)

**Verboten** (nicht erschöpfend):

- Aktive MEV-Extraktion (Frontrunning, Sandwiching, Backrunning zur Gewinnmaximierung)
- Offensive Liquidationen (Execution zur Gewinn-Umleitung, nicht defensive Risiko-Analyse)
- Gewinn-Umleitung aus Kausalsignalen oder Gatekeeper-Outputs
- Clone-Architect: Nachbau angreifender Strategien zur Replikation
- Nutzung versiegelter Pre-Reg-Siegel oder Agent-X-Identität durch Drittsysteme ohne Charter

**Erlaubt:**

- Defensive Kausal-Analyse, Signalfilterung, `BLOCKED`/`RELEASED`-Gatekeeping
- Censorship-resilientes Routing ohne Extraktion (Wave 28 Variante A)
- Operatives Monitoring (Wave 38) ohne neue wissenschaftliche Evidenz

---

## 4. Scope-Flag (immutable)

Jede Data-Matrix und jedes operative Artefakt trägt:

```json
"scope": "DEFENSIVE_CAUSAL_GROUNDING"
```

Manipulation oder Entfernen des Flags ist ein Integritätsverstoß → `EthicalBoundaryException`.

---

## 5. Air-Gap (Ebene 4)

Agent X darf **keine** direkten Execution-Pfade zu:

- Titan-Vault / Gewinn-Optimierungs-Stacks
- Offensive Searcher-/Builder-Pipelines
- Systemen, die Kausalsignale in Trade-Execution ohne defensive Pre-Reg umleiten

Erlaubte Kopplung: Wave 38 `RELEASED`/`BLOCKED` als **Input** für Wave 28 Defense
(rein defensiv) und Wave 24 Trading **nur** über explizite, charter-geprüfte Schnittstellen
(Wave 39 Zertifikat erforderlich).

---

## 6. Identitätsschutz

Drittsysteme dürfen ohne schriftliche Charter-Anerkennung nicht:

- Den Namen „Agent X" für offensive Produkte führen
- Pre-Registration-Siegel oder versiegelte Bridge-Artefakte als Legitimation nutzen
- Forschungs-Identität (Methodik, Dossiers) für nicht-defensive Zwecke beanspruchen

---

## 7. Violation → BLOCKED

Bei Charter- oder Integritätsverstoß:

- `EthicalBoundaryException` (Wave 39)
- Gatekeeper-Status: `BLOCKED`
- `block_cause`: `ETHICAL_BOUNDARY` (Wave 38 `BlockCause`)
- EventBus: `ethical.boundary.violation`

Fail-closed: Assertion-Fehler = `BLOCKED`, nicht `RELEASED`.

---

## 9. Registrierte Schwellen (Wave 39)

| Parameter | Wert | Quelle | Änderung |
|-----------|------|--------|----------|
| `ETHICAL_BLOCKING_SEVERITY_THRESHOLD` | **50** | `agents_b2g/ethical_boundary/config.py` | Nur via Charter-Amendment |
| `OFFENSIVE_MARKER_REGISTRY.version` | **1.0** | `config.py` | Marker-Liste versioniert, §1.0.E-Beleg pro Marker |

**Blocking-Regel:** `ViolationSeverity.value >= 50` → orchestrator `BLOCKED` (sofern kein auto-block-Typ).

**Marker-Registry:** Sieben Marker decken Charter §1.0.E(a–e) ab; Erweiterung nur mit
Registry-Versions-Bump und Charter-Verweis.

---

## 10. Versionierung

| Version | Datum | Änderung |
|---------|-------|----------|
| 1.0 | 2026-08-23 | Erstfassung — Vierfach-Sperre, Air-Gap, Scope-Flag |
| 1.0 | 2026-08-23 | §9 — Blocking-Schwelle 50 + Marker-Registry 1.0 |
