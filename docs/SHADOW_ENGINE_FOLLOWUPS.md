# Shadow Execution Engine — Offene Follow-ups

**Status:** offen (bewusst nicht in `d5fe4c8d` mitgeliefert)
**Datum:** 2026-09-20
**Modul:** `order_execution_engine/`
**Basis:** Commit `35160b77` (Absorption), `d5fe4c8d` (Telemetrie-Härtung)
**Test-Stand bei Anlage:** 43/43 (10 Modelle + 13 Engine + 11 Feed + 9 Persistenz)
**Charter unberührt:** `diagnostic_only=true` · `live_execution=false` · `order_send=false`

---

## F1 — `MAX_POSITION_SIZE` in `RiskController.check()` ist strukturell unerreichbar

**Schwere:** hoch (simulierte Sicherheit, kein Ausfallrisiko)
**Ort:** `order_execution_engine/shadow_execution_engine.py`
`RiskController.check()` (~Z. 116) vs. `ShadowExecutionEngine.on_signal()` (~Z. 500)

### Befund

`on_signal()` leitet die Ordergröße direkt aus dem Risiko-Limit ab:

```python
size = self.risk.config.max_order_size_shares  # Max-Größe als Test-Default
```

Die Order ist damit **immer exakt das Limit**, nie darüber. Die nachfolgenden
Prüfungen in `check()` können nicht greifen:

| Check | Zeile | Warum unerreichbar |
|---|---|---|
| `order.size > max_order_size_shares` | ~116 | `size` ist per Konstruktion `== limit` |
| `order.notional > max_position_size_usdc` | ~118 | `≤` per Konstruktion, solange `max_order_size_shares` klein genug |
| `current_notional + order.notional > max_position_size_usdc` | ~122 | dito |

Reproduziert: `max_order_size_shares` von `100` über `1` bis `0.001` gesetzt —
alle drei Läufe `approved=True`, `RejectReason.NONE`.

Eine Pre-Trade-Regel, die nie greifen kann, ist schlechter als keine Regel:
Im Review wirkt sie wie eine Risikobremse, ist aber eine Tautologie.

### Entscheidung, die zu treffen ist: Sizing-Quelle

Das ist die Wurzel — sie entscheidet, ob der Check ein Check bleibt.

**Option A — Signal-getriebenes Sizing (empfohlen).**
`size = f(confidence, bankroll_fraction, book_depth)`, geklemmt durch
`min(..., max_order_size_shares)`. Dann ist das Limit ein echter Clamp und
der Check wird beobachtbar. Erfordert die Policy-Entscheidung unten.

**Option B — Config-abgeleitet belassen (ehrlich deklarieren).**
Wenn `size` immer aus der Config kommt, ist die Regel eine *Invariante*,
kein Check. Dann als Config-Validierung ausdrücken
(`max_order_size_shares <= max_position_size`) oder den Check streichen.

### Policy bei Überschreitung (Vorab-Position, im Ticket zu bestätigen)

**Reject am Risk-Layer; Clamp nur als expliziter Sizing-Schritt.**

Begründung aus der Charter: Der Trockenmodus existiert, um das
*Strategieverhalten* zu messen. „Die Strategie wollte das Limit überschreiten"
ist ein Signal **über die Strategie** — ein stiller Clamp löscht genau die
Ereignisse, die ausgewertet werden sollen. Ein Reject mit Telemetrie-Eintrag
bewahrt die Information vollständig.

Wenn eine spätere Live-Engine Capping braucht, gehört das als **sichtbarer
Sizing-Schritt mit eigenem Telemetrie-Event** modelliert — nicht als
Nebenwirkung des Risk-Layers.

### Akzeptanzkriterien

- [ ] Ein Test, der eine Order **über** dem Limit erzeugt und einen
      `RejectReason` prüft (heute unmöglich — das ist der Regressionsanker).
- [ ] Mutationsnachweis: Wird die Sizing-Quelle auf „immer Limit" zurückgedreht,
      stirbt der neue Test.
- [ ] Entscheidung A oder B im Dokument festgehalten, nicht nur im Code.

---

## F2 — Modellbasis-Drift: `TelemetryRecord` (Dataclass) vs. `PaperOrder` (Pydantic)

**Schwere:** mittel (strukturell, nicht akut)
**Auslöser:** das Muster lag eine Klasse weiter — `PaperOrder` (`models.py:168`)
hatte bereits `reject_reason: RejectReason = Field(default=RejectReason.NONE)`.

Das war nie fehlendes Wissen, sondern **Drift**: zwei Modellbasen koexistieren,
und neue Klassen werden im Stil ihrer Nachbarschaft geschrieben, nicht im Stil
des Systems. `TelemetryRecord` (`shadow_execution_engine.py:368`) ist eine
`@dataclass`, `PaperOrder` ein `BaseModel`.

### Teil 1 — Konvention (wichtiger als die Migration)

> **Neue Records grundsätzlich Pydantic. Dataclass nur mit begründeter Ausnahme.**

Ohne diese Regel migriert das Ticket nur den Schaden von gestern, nicht den
von morgen. Die Konvention gehört dort verankert, wo neue Klassen entstehen
(CLAUDE.md-Abschnitt oder Modul-Docstring des Packages).

### Teil 2 — Migration `TelemetryRecord` auf `BaseModel`

Mit `ConfigDict(strict=True)` und Feld-Validierung statt `__post_init__`-Wache.
**Nicht** als Beifang: Blast Radius umfasst

- alle Konstruktionsstellen (4 in `on_signal`, durchweg keyword-args — geprüft)
- `asdict` vs. `model_dump` in `persistence.py`
- Gleichheitssemantik (`frozen`/`slots` → `model_config`)
- Serialisierung Richtung Storage

### Auslöser und Akzeptanzkriterien

- [ ] **Auslöser:** ein zweiter Record braucht dieselbe Typprüfung.
- [ ] Audit aller `asdict`-Aufrufe auf `Position`/`VirtualPortfolio` (Pydantic)
      — dort war bereits ein `AttributeError` (`persistence.py`, behoben).
- [ ] `strict=True` wirkt global: `latency_ms: float` lehnt dann
      `Decimal("1.5")` ab. Bewusst entscheiden, nicht beiläufig.

Heute abgedeckt durch `@dataclass(frozen=True, slots=True)` + `__post_init__`
mit `isinstance`-Check (`test_record_rejects_none_at_construction`).

---

## F3 — `with_risk_overrides(**kwargs)` an der Engine

**Schwere:** niedrig (Ergonomie)
**Ort:** `ShadowExecutionEngine`

`RiskConfig` ist `frozen` — korrekt. Tests, die ein Override brauchen, rufen
derzeit `engine.risk.config = engine.risk.config.model_copy(update={...})`.
Eine Engine-Methode würde das kapseln, dann mutiert kein Test mehr versehentlich
am Risiko-Layer vorbei.

### Akzeptanzkriterien

- [ ] Methode setzt `model_copy(update=...)`, kein In-Place-Schreiben.
- [ ] `test_telemetry_all_production_paths` auf die Methode umstellen.
- [ ] Docstring benennt, dass es ein **Test-/Diagnose**-Werkzeug ist
      (`diagnostic_only=true`), kein Produktiv-Pfad.

---

## Review-Standard (aus diesem Zyklus übernommen)

Für safety-relevante Module (Risk, Telemetry, Storage-Boundaries) gilt:
**ein Mutant pro gehärteter Invariante.**

Der Anlass war ein negativer Mutationsnachweis: Der 4-Pfade-Test lief grün
durch, obwohl `None.value` wieder eingebaut war — alle vier `on_signal`-Zweige
setzen ein Enum, der `None`-Fall war im Produktivpfad **unerreichbar**.
Erst Wache + Boundary-Test töten den Mutanten (an Konstruktion und Boundary).

Das ist der Unterschied zwischen „Tests sind grün" und „Tests bewachen etwas".
