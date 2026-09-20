# Shadow Execution Engine — Offene Follow-ups

**Status:** offen (bewusst nicht in `d5fe4c8d` mitgeliefert)
**Datum:** 2026-09-20
**Modul:** `order_execution_engine/`
**Basis:** Commit `35160b77` (Absorption), `d5fe4c8d` (Telemetrie-Härtung)
**Test-Stand bei Anlage:** 43/43 (10 Modelle + 13 Engine + 11 Feed + 9 Persistenz)
**Charter unberührt:** `diagnostic_only=true` · `live_execution=false` · `order_send=false`

---

## F1 — Sizing und Positions-Schranke ausrichten

**Schwere:** hoch (Schichtverletzung, nicht Ausfallrisiko)
**Ort:** `order_execution_engine/shadow_execution_engine.py` —
`ShadowExecutionEngine.on_signal()` (Sizing) vs. `RiskController.check()`

### Befund (korrigiert, verifiziert am 2026-09-20)

Eine frühere Fassung dieses Tickets behauptete, *der* `MAX_POSITION_SIZE`-Check
sei unerreichbar. Das war falsch zugeschnitten. `RiskController.check()` enthält
**vier** Prüfungen, die `MAX_POSITION_SIZE` zurückgeben — zwei sind tot, zwei
arbeiten, aber auf unterschiedlicher Granularität:

| Zeile | Prüfung | Granularität | Status | Warum |
|---|---|---|---|---|
| ~116 | `order.size > max_order_size_shares` | Order | **tot** | `on_signal` setzt `size = risk.config.max_order_size_shares` — die Order ist per Konstruktion *exakt* das Limit, nie darüber |
| ~118 | `order.notional > max_position_size_usdc` | Order | **tot** unter F1-Regime | folgt aus der Config-Invariante `per_order_cap ≤ max_position_size`; heute nur bei fehlerhafter Config erreichbar |
| ~122 | `current_notional + order.notional > max_position_size_usdc` | **Position** | **funktioniert** | aggregiert über bestehende Position — zweiter Kauf erreicht sie |
| ~130 | `available <= 0 or order.size > available` (SELL) | Position | funktioniert | Short-Verbot |

Empirischer Nachweis für Zeile 122 (`max_position_size_usdc=100`,
Kaufs-Erinnerung auf dasselbe Token):

```
Fill 1: approved=True   position=100 shares / 61.00 USDC
Fill 2: approved=False  reason=MAX_POSITION_SIZE   ← greift
Fill 3: approved=False  reason=MAX_POSITION_SIZE
```

Isoliert mit vorbelegter Position (90 USDC) + Order (~61 USDC) = 151 USDC:
`approved=False, reason=MAX_POSITION_SIZE`.

**Korrigierte Implikation:** Der Risk-Layer ist nicht zahnlos. Er hat genau
**eine** funktionierende aggregierte Pre-Trade-Bremse auf Positionsebene
(Zeile 122) plus das Short-Verbot — und **zwei tote Order-Level-Checks**.
Was fehlt, ist die Order-/Positions-Granularität als *bewusste* Ausrichtung,
nicht der Schutz selbst. „Teilweise tot" erfordert Chirurgie; „ganz tot" hätte
Neubau erfordert. Das ist eine andere Schwere und eine andere Geschichte für
den nächsten Leser.

Beide toten Checks tragen dasselbe `RejectReason.MAX_POSITION_SIZE` wie der
funktionierende — deshalb sahen sie im Review wie derselbe Check aus. Die
Unterscheidung ist nicht im Code sichtbar; sie gehört in Kommentar oder Ticket.

### Entscheidung, die zu treffen ist: Sizing-Quelle

**Option A — Signal-getriebenes Sizing (empfohlen).**
Die Conviction gehört zum Signal (NewsBank/NewsBot liefert sie als Confidence).
Die Umrechnung in eine Größe gehört in eine explizite, konfigurierbare
Sizing-Funktion auf **Strategy-Ebene** — nicht in die `RiskConfig`.
`RiskConfig` enthält Schranken, keine Sizing-Logik.

Damit bleibt die Engine, was sie sein soll: Execution. Eine Engine, die sich
ihre Ordergrößen aus dem Risikolimit ableitet, misst nicht die Strategie,
sondern ihre eigene Konstante — genau der Zustand, der abgeschafft werden soll.

**Option B — Config-abgeleitet belassen (ehrlich deklarieren).**
Wenn `size` immer aus der Config kommt, ist Zeile 116 eine *Invariante*,
kein Check. Dann als Config-Validierung ausdrücken oder streichen — und nicht
als „Risikobremse" stehen lassen.

### Entscheidung vom 2026-09-20 (ersetzt die frühere Vorab-Position)

**1. Sizing-Quelle: das Signal, nicht die Config.**
Sizing-Funktion auf Strategy-Ebene, konfigurierbar. `RiskConfig` bleibt
schranken-only.

**2. Clamp: ja — aber im Sizing, niemals im Risk-Layer.**
`size = min(desired, per_order_cap)`. Bedingung: Telemetrie führt
`requested_size` und `executed_size` **getrennt**, damit Kappung messbar ist
statt still. Produktionsnahe Variante ohne Informationsverlust.

**3. Reject: ausschließlich am Risk-Layer, auf kumulierter Ebene.**
Semantik: `current_position + order_size > max_position_size →
RejectReason.MAX_POSITION_SIZE`. Mit dem funktionierenden Zeile-122-Check ist
das **teilweise bereits Realität** — F1 führt die Semantik nicht neu ein,
sondern richtet sie aus: Event-Exposure existiert, Per-Token-Position kommt
dazu, Order-Level fällt weg.

Beim Feuern: Order wird nicht ausgeführt, Telemetrie zeichnet den Versuch auf.
„Die Strategie wollte über das Limit" ist ein Befund über die Strategie.

**4. Config-Invariante beim Laden:** `per_order_cap (Sizing) ≤
max_position_size (Risk)`, validiert beim Start. Verletzung ist ein
Config-Fehler, kein Laufzeitverhalten. Schichtung damit explizit:
**Sizing kappt weich, Risk rejectet hart**, keiner kommt dem anderen still
ins Gehege.

### Akzeptanzkriterien (Regressionsanker, heute unmöglich)

- [ ] (a) Zwei Orders auf dasselbe Token — erste füllt, zweite kippt die
      Position über das Limit → Reject.
- [ ] (b) `requested > per_order_cap` → Ausführung am Cap, Telemetrie zeigt
      **beide** Größen.
- [ ] (c) Config mit `per_order_cap > max_position_size` → Start scheitert.
- [ ] Mutationsnachweis: Wird die Sizing-Quelle auf „immer Limit" zurückgedreht
      oder der Positions-Check entfernt, stirbt der jeweilige Test.

---

## F1b — Tote Order-Level-Checks entfernen (Zeilen ~116 und ~118)

**Schwere:** niedrig (mechanisch)
**Abhängigkeit:** **blocked by F1-Umsetzung.**
**Ort:** `order_execution_engine/shadow_execution_engine.py`,
`RiskController.check()`

Eigener Commit, weil er **nachweislich kein Verhalten ändert** — reine
Löschung, mechanisch reviewbar, sauber revertbar. Wer Löschung in den
Verhaltens-Commit mischt, verwischt genau die Linie, an der ein Reviewer
„ändert etwas" von „kann nichts ändern" unterscheidet.

### Warum die Kopplung an F1 zwingend ist

Die Löschung von 116/118 ist nur **unter dem F1-Regime** gerechtfertigt:
Sizing-Clamp plus Config-Invariante `per_order_cap ≤ max_position_size`
machen die Order-Level-Checks *per Konstruktion* unerreichbar, nicht nur
empirisch. Ohne diese Kopplung liegt das Ticket im Backlog, und in sechs
Monaten liest jemand 116/118 wieder als funktionierenden Schutz.

### Streich-Kriterium

> Unerreichbar **per Konstruktion**, Nachweis über die Config-Invariante —
> nicht „unerreichbar, weil wir es nie getestet haben".

### Akzeptanzkriterien

- [ ] Vor der Löschung: je ein Mutationstest, der zeigt, dass die Zeilen in
      keinem Szenario feuern (auch nicht bei Grenzwerten).
- [ ] Nach der Löschung: 43/43 + die neuen F1-Tests unverändert grün →
      beweist „kein Verhaltensänderung".
- [ ] Kommentar an der verbleibenden Positions-Prüfung, dass sie die
      *einzige* Position-Level-Schranke ist (Abgrenzung zu Event-Exposure).

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
