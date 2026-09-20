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
      Position über das Limit → Reject. **Der manuelle Beleg vom 2026-09-20
      (vorbelegte Position 90 USDC + Order 61 USDC bei Limit 100 → Reject)
      gehört hier als automatisierter Test hinein**, damit der heute manuelle
      Nachweis dauerhaft wird.
- [ ] (b) `requested > per_order_cap` → Ausführung am Cap, Telemetrie zeigt
      **beide** Größen.
- [ ] (c) Config mit `per_order_cap > max_position_size` → Start scheitert.
- [ ] (d) Jede Ablehnungsursache hat einen **unterscheidbaren** RejectReason
      (Addendum unten).
- [ ] (e) **Test-Sensitivität, nicht Engine-Eigenschaft:** Ersetzt man die
      neue Sizing-Logik durch die Legacy-Konstante `max_order_size_shares`,
      muss mindestens ein Anker-Test **rot** werden. Bleibt alles grün, ist
      der Anker an den alten Pfad gekoppelt und beweist das neue Verhalten
      nicht. Gleicher Mutationsstandard wie bei `TelemetryRecord`, hier auf
      Testebene: Der Test muss am Mutanten sterben, sonst bewacht er nichts.
- [ ] Mutationsnachweis: Wird die Sizing-Quelle auf „immer Limit" zurückgedreht
      oder der Positions-Check entfernt, stirbt der jeweilige Test.

### Schema-Migration: `requested_size` vs. `executed_size`

**Korrektur einer früheren Annahme:** „keine Schema-Änderung" gilt für die
getrennten `RejectReasons` (neue Enum-Werte in derselben Spalte) — **nicht**
für die getrennte Größen-Telemetrie. Die heutige `telemetry`-Tabelle
(`persistence.py:121`) hat **gar kein Größen-Feld**:

```sql
CREATE TABLE IF NOT EXISTS telemetry (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT NOT NULL,
    order_id TEXT,
    latency_ms REAL NOT NULL,
    approved INTEGER NOT NULL,
    reject_reason TEXT,
    status TEXT
);
```

`executed_size` liegt heute ausschließlich in `fills` (`persistence.py:130`)
und ist dort die *Ausführungsmenge*, nicht die angeforderte. Die angeforderte
Größe existiert nur flüchtig im `PaperOrder`-Objekt.

F1 braucht damit eine Migration auf zwei Tabellen:

| Tabelle | Änderung | Backfill |
|---|---|---|
| `telemetry` | neue Spalte `requested_size TEXT` | nicht möglich — Größe wurde nie persistiert; `NULL` für Althistorie |
| `fills` | neue Spalte `requested_size TEXT` | `requested_size := executed_size` |

**Backfill-Regel für `fills`:** `requested_size := executed_size` ist für die
Vergangenheit **wahr**, weil beide historisch identisch waren — die Order war
per Konstruktion exakt das Limit, es gab keine Kappung. Der Backfill ist
deshalb keine Näherung, sondern eine korrekte Rekonstruktion.

**Backfill-Regel für `telemetry`:** `NULL` statt eines erfundenen Werts.
Eine aus `fills` abgeleitete Größe wäre bei abgelehnten Orders (kein Fill)
nicht rekonstruierbar und bei gefüllten Orders eine Scheingenauigkeit.
`NULL` heißt hier ehrlich „vor der Messung".

- [ ] `SCHEMA_VERSION` erhöhen (`1` → `2`), Migration idempotent.
- [ ] Test, der eine v1-DB öffnet und die Migration prüft (inkl. Backfill).
- [ ] `fills.requested_size = executed_size` in Altdaten nachgewiesen.
- [ ] **`NULL`-Semantik im Schema dokumentieren, nicht nur im Migrationscode:**
      `NULL = vor Messbeginn`, nicht `fehlend`. Ein undokumentiertes `NULL`
      lädt den nächsten dazu ein, es per Join aus `fills` zu „reparieren" —
      und die Scheingenauigkeit, die der Backfill bewusst vermieden hat, wäre
      wieder da. Der Spaltenkommentar gehört in die DDL
      (`requested_size TEXT,  -- NULL = vor Messbeginn (v1), nicht: fehlend`),
      damit er an der Stelle steht, an der jemand die Spalte liest.

### Schema-Migration v2: drei Felder, zwei Backfill-Semantiken

Die Migration umfasst **drei** Felder, nicht zwei — und die Backfill-Regeln
sind bewusst asymmetrisch. Was historisch wahr war, wird wahr
fortgeschrieben; was nie gemessen wurde, bleibt sichtbar ungemessen.

| Feld | Tabelle | Backfill | Begründung |
|---|---|---|---|
| `requested_size` | `telemetry` | `NULL` | nie persistiert, nicht rekonstruierbar |
| `decision_seq` | `telemetry` | `NULL` | existierte nicht; Semantik „vor der Messung" |
| `requested_size` | `fills` | `:= executed_size` | historisch **wahr**, keine Kappung |

**Zur dritten Zeile:** In der Vergangenheit wurde nur eine Größe erfasst, und
sie war definitionsgemäß die ausgeführte (die Engine orderte die Konstante,
alles über dem Limit wurde abgelehnt statt gekappt). `executed_size` ist also
der korrekte historische Wert für `requested_size` — keine Näherung.

**`NULL` explizit dokumentieren.** In den Migrationskommentar und ins Schema,
nicht nur ins Ticket: `NULL = vor Messbeginn, nicht: fehlend`. Ein
undokumentiertes `NULL` lädt den nächsten dazu ein, es per Join aus `fills`
zu „reparieren" — und genau die Scheingenauigkeit, die diese Entscheidung
vermeidet, wäre wieder da.

**Zähler-Lebensdauer = Entscheidungs-Historie.** `decision_seq` ist nur
solange replaysicher, wie der Zähler die Historie kennt. Beim Start muss
`TelemetryLogger` aus `max(decision_seq)` der Datenbank initialisiert werden —
sonst beginnt jeder Prozessneustart wieder bei 1 und die Korrelation
über Sessions hinweg kollidiert still. Eine Zeile in der Migration, aber der
Unterschied zwischen „replayfähig pro Run" und „replayfähig, Punkt".

**Zur Platzierung des Zählers am Logger (Charter-Begründung).** Das Argument
„der Logger ist der einzige Ort, den beide Seiten sehen" ist zu schwach — die
Engine sieht beide Seiten ebenfalls, sie konstruiert Snapshot *und* Record.
Der tragfähige Grund ist die Charter: In einer `diagnostic_only`-Engine ist
Telemetrie kein optionales Subsystem, es gibt keine Konfiguration ohne Logger.
Damit ist der Logger ein *garantierter* Ort, und „Identität gehört zum
Aufzeichnungsinstrument" ist hier keine Layer-Frage, sondern Charter-Folge.

### Nachtrag (2026-09-20): `requested_size` — Erwartungstabelle als Zeuge

Die `NULL`-Doktrin lebte bis hier nur in der DDL. Ihr Zeuge muss die
**Datenbank** prüfen, nicht das In-Memory-Record — und die vollständige
Erwartungstabelle pinnen, nicht nur die zwei `None`-Pfade:

| Pfad | `requested_size` | Begründung |
|---|---|---|
| ungültiger Preis | `NULL` | Sizing lief nie (keine Order-Seite) |
| leere Buchseite | `NULL` | derselbe `INVALID_PRICE`-Pfad |
| **Drawdown-Lockout** | **gesetzt** | Lockout sitzt in `RiskController.check()` — **nach** dem Sizing |
| Risk-Reject | gesetzt | Strategie hat angefragt, Betrag bleibt sichtbar |
| Approved | gesetzt | — |

**Der Lockout ist der interessante Fall.** Die Reihenfolge im Code
(`on_signal`: Sizing in Zeile 652, `risk.check()` danach) entschied die
Semantik implizit. Der Test macht sie zur behaupteten: Eine künftige
Pipeline-Umordnung, die den Lockout vor das Sizing zieht, wird rot statt
still. Das ist der Unterschied zwischen „konsistent zufällig" und
„konsistent vertraglich".

**Verifiziert:** `test_requested_size_null_table` prüft alle vier Pfade am
persistierten Zustand (eine DB, vier Engines). Mutationsnachweis: Lockout-Pfad
schreibt `NULL` → `AssertionError: None` in Zeile 525. Auch die rohe
Pipeline-Umordnung (Lockout vor Sizing) wird rot.

### Warum `telemetry.requested_size` der Kern der Messung ist

Kein Nice-to-have. Die Engine konnte bisher nicht einmal die Frage beantworten,
**wie groß die Order war, die sie abgelehnt hat**: Die angeforderte Größe wurde
nirgends persistiert, sie existierte nur flüchtig im `PaperOrder`-Objekt.

`fills` sieht nur die Überlebenden. Ausgerechnet die Rejects — die für die
Strategiebewertung interessantesten Ereignisse — waren datenlos. In einer
Engine mit Charter `diagnostic_only` ist das der teuerste blinde Fleck: Der
Trockenmodus soll Strategieverhalten messen, und die Absicht hinter einer
Ablehnung ist die reinste Form dieses Signals.

Zusammen mit dem Addendum (unterscheidbare RejectReasons) beantwortet die
Telemetrie nach F1 erstmals beide Fragen: *warum* wurde abgelehnt und *wie groß*
war die abgelehnte Absicht.

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

### Addendum (2026-09-20): RejectReason-Mehrdeutigkeit als Diagnostik-Lücke

Die Ursache der ursprünglichen Fehldiagnose ist selbst ein Design-Befund:
Alle vier `MAX_POSITION_SIZE`-Rejects tragen **denselben** `RejectReason`.
Ein `MAX_POSITION_SIZE` in der Telemetrie sagt damit nicht, *welcher* Check
gefeuert hat — Ordergröße, Order-Notional oder kumulierte Position.

In einer Engine, deren Charter `diagnostic_only` ist, ist das eine echte
Lücke: Aus den Daten lässt sich nicht rekonstruieren, warum eine Order
abgelehnt wurde. Und sie ist nicht bloß kosmetisch — sie hat den falschen
Befund dieses Tickets erst möglich gemacht (im Review sahen vier Checks wie
einer aus).

**Beim F1-Umbau zu beheben, nicht nur zu dokumentieren:**

Option 1 — RejectReasons pro Semantik trennen:

| Semantik | Neuer Wert |
|---|---|
| Ordergröße (Zeile ~116) | `MAX_ORDER_SIZE` |
| Order-Notional (Zeile ~118) | `MAX_ORDER_NOTIONAL` |
| Kumulierte Position (Zeile ~122) | `MAX_POSITION_SIZE` (bleibt) |

Option 2 — `check_id`/`check_name`-Feld im Telemetrie-Record, das den
feuernden Check benennt. Robuster bei künftigen Checks, aber Schema-Änderung.

Empfehlung: **Option 1**, weil sie ohne Schema-Änderung auskommt und der
RejectReason bereits im Persistenzschema steht. Option 2 wird attraktiv,
sobald mehr als ~6 Checks existieren.

Akzeptanzkriterium: Ein Test, der für jede Ablehnungsursache den
*unterscheidbaren* RejectReason prüft. Die Mehrdeutigkeit, die den falschen
Befund ermöglichte, ist dann strukturell beseitigt.

### F1b-Ausführung (2026-09-20): definiert statt rein — die Falle war das Erbe von VM1

**Korrektur der F1b-Prämisse.** Das Ticket sagte „116/118 per Konstruktion
unerreichbar". Verifiziert stimmt das für 118, **nicht** für 116:

```
RiskConfig(max_order_size_shares=50, per_order_cap_shares=200, max_position_size_usdc=500)
size_fn -> 200
reject_reason: MAX_ORDER_SIZE   ← 116 feuert
```

Ursache: VM4 hat `max_order_size_shares` die Schranken-Semantik genommen. Es
ist nur noch die Größe, die der Default-Adapter ordert (Strategie-Platzhalter),
keine Obergrenze. Die Obergrenze ist `per_order_cap_shares`. **116 ist damit
keine tote Leiche, sondern eine Fehl-Reject-Falle:** `cap=300`, Strategy will
250, legacy-const 100 → Clamp lässt 250 durch, 116 rejectet. Der Check bestraft
eine Order, die das Cap explizit erlaubt hat — das Cap-Feature wäre nach oben
unbenutzbar.

**Der subtilste Befund des Zyklus:** Der F1-Zeuge für `MAX_ORDER_SIZE` bewies
mechanisch korrekt, dass 116 feuert — und kanonisierte damit die Falle als
erwartetes Verhalten. Ein Test, der grün ist, einen Mutanten tötet und trotzdem
Unsinn dokumentiert: Er beantwortete „feuert der Check?" mit ja, ohne „sollte
er?" zu fragen. **Mechanisch richtig, semantisch falsch.**

**F1b, definiert (vier Zuordnungen, nicht mehr „reine Löschung"):**

| # | Änderung | Begründung |
|---|---|---|
| Z1 | 116 + 118 entfernt | 116 = Falle (bestraft legitimes Cap); 118 = Tautologie (`notional ≤ size ≤ cap ≤ max_position`) |
| Z2 | `MAX_ORDER_SIZE`, `MAX_ORDER_NOTIONAL` entfernt | produzentenlos — Scheinschutz im Enum |
| Z3 | F1-Zeugen für beide gelöscht, nicht umgeschrieben | ihr Gegenstand existiert nicht mehr |
| Z4 | **Meta-Anker (d)** ersetzt den alten Anker (d) | jeder `RejectReason`-Wert hat einen lebenden Produzenten |

**DB-Gate vor Z2:** `COUNT(*) FROM telemetry WHERE reject_reason IN
('MAX_ORDER_SIZE','MAX_ORDER_NOTIONAL')` → **0**. Es existiert keine
persistierte Shadow-Telemetrie (`find . -name shadow.db` leer), das Enum ist
rein intern (kein Konsument außerhalb `order_execution_engine/`). Die
Entfernung ist non-breaking.

> **Das DB-Gate gab mehr her als gefragt.** Es gibt **keine** persistierte
> Shadow-Telemetrie — die Engine lief bisher ausschließlich in-memory bzw. in
> Tests. Konsequenz für die v2-Migration: Die `NULL`-Doktrin hat **keine
> Bestandsdaten zu schützen**; sie ist von Tag 1 an *vorausschauend*. Das macht
> sie nicht weniger wertvoll — der erste echte Run erbt ein Schema, dessen
> Lücken ehrlich benannt sind, statt nachträglich rekonstruierter
> Scheingenauigkeit. Wer später nach Altdaten sucht: es gibt keine.

> **Löschung ist ein Urteil über die Gegenwart, nicht über das Konzept.**
> Order-Expiry ist ein echtes CLOB-Feature (GTD). Wenn die Simulation je
> Expiry abbildet, kehrt `EXPIRED` zurück — dann mit Produzent *und* Zeuge.
> Löschen heißt „existiert nicht", nicht „darf nie existieren".
>
> **Der Auslöser ist präzise benennbar:** `EXPIRED` bekommt seinen Produzenten
> genau dann, wenn die Match-Simulation **resting orders** lernt. Solange
> Orders nur im Moment des Signals gegen das Buch laufen, kann nichts altern.
> Sobald virtuelle Orders im Buch liegen und Ticks sie altern lassen, ist
> Expiry ein echter Zustandsübergang — und der Konstruktor-Guard allein reicht
> nicht mehr, weil „gültig bei Erstellung" und „gültig bei Fill"
> auseinanderfallen. Das ist der natürliche Wiedereintrittspunkt, und er kommt
> mit dem realistischsten Teil der CLOB-Simulation, nicht als Laune.

**Zwei zusätzliche Waisen, vom Meta-Anker gefunden.** Er feuerte beim ersten
Lauf und meldete `['EXPIRED', 'SAFETY_GUARD']` — beide produzentenlos,
`is_expired()` wird nie im Engine-Pfad aufgerufen. Sie fielen unter dieselbe
Regel und gingen mit. Das ist der Anker bei seiner ersten Amtshandlung.

**Die Leiche neben der Tür (`is_expired()`).** Der Enum-Wert ging, die
zugehörige Maschinerie musste separat geprüft werden — tote Maschinerie neben
einem gelöschten Label ist derselbe Befund einen Meter weiter. Ergebnis:
`is_expired()` war vollständig verwaist (ein Caller: ein Assert in
`test_order_validation`). Nach derselben Regel entfernt, mit Protokollzeile.
**Was bleibt und weiterhin gilt:** Die Altersgrenze wird am Konstruktor
durchgesetzt (`_reject_expired`) — abgelaufene Orders können nicht entstehen.
Sie *wurden* nie im Bestand geprüft, weil der Zustand unerreichbar ist. Auch
`expiration` bleibt als Feld (Konstruktor-Grenze + CLOB-Standardfeld).

**`SAFETY_GUARD` ist die reinste Form des Musters.** Ein Reject-Reason, der
Sicherheit *verspricht* und nie feuern kann — in einer Engine, deren
Existenzberechtigung die Vertrauenswürdigkeit ihrer Telemetrie ist. Ein Leser,
der das Enum als Dokumentation liest, muss eine letzte Schutzinstanz annehmen.
Das ist schlimmer als der tote 116: Der sah nur *aus* wie Schutz, dieser
*heißt* so.

**Was von VM1 überlebt: nur `MAX_POSITION_SIZE`** — die ursprüngliche eine
Reason. War die Trennung umsonst? Nein: Sie war der **Zwischenschritt, der die
Sites sichtbar machte.** Erst als jeder Check sein eigenes Label trug, wurde
überprüfbar, welche Sites feuern können und welche nicht. VM1 löste die
Mehrdeutigkeit durch Benennung, F1b endgültig durch Entfernen der
Phantom-Referenten.

**Verifiziert:**
```
Falle entschärft:  cap 300, Strategy 250, legacy 100
                   vorher: approved=False (MAX_ORDER_SIZE)
                   nachher: approved=True, Order=250, requested=250
Enum:              NONE, MAX_POSITION_SIZE, MAX_EVENT_EXPOSURE,
                   DRAWDOWN_LOCKOUT, INSUFFICIENT_CASH, INVALID_PRICE
Meta-Anker:        PHANTOM_CHECK-Mutant -> rot
Anker (a)-(e):     alle fünf leben, (a) stirbt weiter am Mutanten
Tests: 53/53
```

**Offen (F2-Nachbarschaft):** `max_order_size_shares` ist Strategie-
Konfiguration in `RiskConfig`-Kleidung. Wenn das Strategy-Package landet,
wandert das Feld dorthin oder wird umbenannt.

---

## F1c — Sizing-Schnittstelle auf Engine-Seite definieren

**Schwere:** hoch (Voraussetzung dafür, dass F1 ohne das Strategy-Package
lieferbar ist)
**Ort:** `order_execution_engine/` (neuer Seam), `ShadowExecutionEngine.on_signal()`

F1 darf **nicht** auf ein Strategie-Package warten, das außerhalb dieses
Repos liegt. Die Schnittstelle gehört jetzt definiert, auf Engine-Seite:

```python
SizeFn = Callable[[SignalPayload, PortfolioState], Decimal]

def sizing(signal, portfolio_state) -> desired_size
```

- **Injizierbar:** `ShadowExecutionEngine(..., size_fn=...)`.
- **Default-Adapter:** fixe Bankroll-Fraktion, damit die Engine ohne
  Strategie-Package lauffähig bleibt.
- **Das Strategy-Package implementiert später** die echte Conviction-Logik
  (NewsBot-Confidence) gegen dieselbe Schnittstelle — ohne Engine-Änderung.

Damit liefert F1 den kompletten Verhaltens-Commit: Seam, Clamp,
Telemetrie-Felder `requested_size`/`executed_size`, getrennte RejectReasons
(Addendum), Config-Invariante. F1b bleibt ausschließlich `blocked by F1`.

### Akzeptanzkriterien

| Messlatte | Scharfe Fassung |
|---|---|
| **1** | `git diff` auf `tests/` **nur additiv** — keine modifizierte oder gelöschte Zeile in bestehenden Tests. Alle 43 bisherigen laufen unverändert grün. |
| **2** | Coverage auf den neuen Zeilen: `PositionSnapshot`, `PortfolioSnapshot`, `VirtualPortfolio.snapshot()` und der Seam-Block in `on_signal` werden tatsächlich ausgeführt. |
| **3** | Neuer Zeugen-Test mit **unterscheidbarer** `size_fn`; der Legacy-Mutant (Konstante statt Seam) macht ihn rot. |

**Präzisierung vom 2026-09-20 (ersetzt die frühere Fassung von Messlatte 1):**
Messlatte 1 lautete ursprünglich „`git diff` auf `tests/` leer" und kollidierte
damit mit Messlatte 3. Der Default-Adapter ist per Definition verhaltensgleich
mit der Legacy-Konstante — **kein existierender Test kann den Mutanten also
unterscheiden**. Ein Zeuge für den Seam ist zwingend ein *neuer* Test.

Aufgelöst durch **Präzisierung, nicht Lockerung**: Der Beweisgehalt von
Messlatte 1 steckt nie in der Abwesenheit neuer Tests, sondern in der
**Unverändertheit der bestehenden**. „Alle 43 bisherigen Tests laufen
unmodifiziert grün" ist der Nachweis, dass Verhalten erhalten blieb. Ein
hinzugefügter Test, der den neuen Seam beobachtet, schwächt diesen Beweis um
null — er verändert kein einziges bestehendes Ergebnis.

#### Warum der Zeuge im selben Commit stehen muss

Der F1c-Commit behauptet „der Seam lebt" — sein Zeuge gehört in denselben
Commit, sonst liegt die Behauptung an einem Punkt der Historie unbewiesen im
Baum. Und F1 würde sonst eine Verhaltensänderung auf einer unverifizierten
Schnittstelle aufbauen: Ist der Seam falsch verdrahtet, will man das wissen,
*bevor* Sizing-Logik darauf läuft.

#### Warum der Zeuge sich vom Default unterscheiden muss

Ein Test, der den Default-Adapter benutzt, kann die Injektion nie belegen
(Verhaltensgleichheit!). Der Zeuge injiziert eine **unterscheidbare** Funktion
(z. B. halbierte Größe) und prüft, dass die Order die injizierte Größe trägt.
Selbstreferenziell: Legacy-Mutant eingesetzt → genau dieser Test wird rot.

#### Warum der Snapshot tief eingefroren sein muss

Pydantics `frozen=True` schützt nur die Attribut-Zuweisung; ein `dict`-Inhalt
bliebe über `snapshot.positions["x"] = ...` änderbar. Ohne
`MappingProxyType` wäre Option 3 nur Option 1 mit Umweg — der Punkt, an dem
diese Option in der Umsetzung typischerweise kippt. Eigener Test:
`test_portfolio_snapshot_is_deeply_frozen`.

### Nachtrag (2026-09-20): `as_of_seq` — Korrelationsrichtung korrigiert

Ein Review-Befund unmittelbar nach F1c, **vor** F1, weil F1 sonst Daten gegen
eine geratene Sequenz persistiert hätte.

**Befund.** F1c baute den Snapshot mit
`as_of_seq=len(self.telemetry._records)`. Drei Probleme, aufsteigend:

1. **Privatattribut-Zugriff.** `telemetry._records` ist die Implementierung
   der In-Memory-Senke. Der Seam, der gerade die Strategie vom Engine-Inneren
   entkoppelt hatte, koppelte sich selbst ans Innere der Senke. Eine DB-backed
   Senke hat kein `_records` — beim ersten Sink-Wechsel bricht das, oder
   schlimmer: Es liefert still falsche Werte.
2. **Die Seq ist vorhersagend, nicht zugewiesen.** `telemetry.seq` ist
   `INTEGER PRIMARY KEY AUTOINCREMENT` (`persistence.py:122`), wird also beim
   INSERT vergeben. Der Snapshot entsteht *vor* dem Schreiben und rät die
   nächste Nummer. Korrekt nur unter vier ungeschriebenen Invarianten: genau
   eine Senke, genau ein Record pro Signal, keine Lücken, keine parallelen
   Writer. Keine davon ist im Code erzwungen.
3. **Korrelationsrichtung rückwärts.** Der Snapshot soll nicht die künftige
   Telemetrie-Seq erraten — die Engine soll die Identität vergeben, und beide
   Seiten tragen sie.

**Fix.** Eigener monotoner Zähler der Engine:
`TelemetryLogger.next_decision_seq()`. `TelemetryRecord` hat ein neues Feld
`decision_seq`; der Sizing-Snapshot und der zugehörige Record teilen denselben
Wert. Die Datenbank-`seq` bleibt davon unberührt und wird durch die
Storage-Schicht übernommen.

**Verifiziert:**
```
Record decision_seqs:      [1, 2]   # Pre-Order-Reject, Fill
Snapshot-Ids (Sizing):     [2]      # derselbe Wert wie der Fill-Record
monoton + luecklos:        True
```
Mutationsnachweis: Rückkehr zu `len(self.telemetry._records)` →
`AssertionError: [1, 0]`.
Test: `test_decision_seq_correlates_snapshot_and_record`.

**Nicht in F1c:** `decision_seq` ist noch nicht im Persistenzschema. Das
gehört in F1 zusammen mit `requested_size`/`executed_size` in die
Schema-Migration auf v2 — die Korrelation ist erst dann dauerhaft, wenn sie
die DB erreicht.

### Akzeptanzkriterien (ursprüngliche Fassung, historisch)

- [x] `size_fn` injizierbar, Default-Adapter funktioniert ohne Strategie.
      → `test_size_fn_injection_is_observable`,
      `test_default_size_fn_preserves_legacy_behaviour`
- [x] Mutationsnachweis: Ersetzt man die neue Sizing-Logik durch die
      Legacy-Konstante, wird mindestens ein Anker-Test rot.
      → verifiziert: `AssertionError: size_fn wurde nie aufgerufen`

**Reihenfolge im Verhältnis zu F1:** F1c ist „make the change easy", F1 ist
„make the easy change". Der Seam-Commit ändert kein Verhalten, F1 ändert
Verhalten als erster Commit seit Entstehung der Engine, F1b löscht unter
Beweislast.

---

## F2 — Modellbasis-Drift: `TelemetryRecord` (Dataclass) vs. `PaperOrder` (Pydantic)

**Schwere:** mittel (strukturell, nicht akut)
**Auslöser:** das Muster lag eine Klasse weiter — `PaperOrder` (`models.py:168`)
hatte bereits `reject_reason: RejectReason = Field(default=RejectReason.NONE)`.

Das war nie fehlendes Wissen, sondern **Drift**: zwei Modellbasen koexistieren,
und neue Klassen werden im Stil ihrer Nachbarschaft geschrieben, nicht im Stil
des Systems. `TelemetryRecord` (`shadow_execution_engine.py:368`) ist eine
`@dataclass`, `PaperOrder` ein `BaseModel`.

### Messlatte: F1c-Maßstab, mit einem vorprogrammierten Unterschied

Die Modellbasis-Migration ist verhaltensneutral **im selben Sinne wie F1c**:
Test-Diff **nur additiv**, Bestand grün. Das ist die Messlatte.

**Der Unterschied gehört vorher benannt:** Pydantic-Validation kann Dinge
ablehnen, die die Dataclass geschluckt hat. Das eigene Beispiel steht schon im
Ticket: `Decimal("1.5")` für `latency_ms` (ein Feld, das `int` erwartet). Die
Dataclass ist permissiv, weil sie nichts erzwingt; Pydantic erzwingt.

> **Wenn F2 also einen Bestandstest rot macht, ist das kein
> Messlatten-Bruch, sondern ein Fund:** latenter Typ-Schlamm, den die
> Dataclass nie bemerkt hat.

**Die Regel für jeden so gefundenen Fall:**

1. **Klassifizieren** — *Produzent reparieren* (der Aufrufer liefert den
   falschen Typ) **oder** *Feld bewusst lockern* (der Typ war zu eng gewählt,
   etwa `int`, wo `float` korrekt ist).
2. **Die Entscheidung steht in der nummerierten Zuordnung** — wie in F1b:
   jede Teständerung hat eine Nummer und eine Begründung.

**Was nicht passiert:** Der Validator wird weitergestellt, bis die Tests wieder
grün sind. Sonst migriert F2 nicht die Modelle, sondern nur die
**Schweigepflicht** — von der Dataclass, die nichts sagte, zur Pydantic-Konfig,
die nichts sagt, aber so aussieht, als würde sie etwas sagen. Das wäre
Scheinschutz in seiner fünften Geschmacksrichtung.

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

## Der Selbstfang der Invariante (2026-09-20)

Der stärkste Einzelbeleg des F1-Pakets, und er kam vor dem ersten Testlauf:

`max_order_size_shares = 1000` gegen `max_position_size_usdc = 500` heißt:
Die Engine hätte bei jedem Preis über 0,50 ihre **eigene Default-Order**
abgelehnt — `notional = 1000 × p > 500` für `p > 0,5`, Check 122, erster
Trade, garantiert. Der tote Check 116 hätte es nie gefangen (`1000 > 1000`
ist false); es wäre zur Laufzeit als rätselhafter `MAX_POSITION_SIZE`-Reject
aufgetreten, und niemand hätte die Defaults verdächtigt, weil „Default" sich
wie „harmlos" liest.

Die Invariante hat einen latenten Widerspruch von „mysteriöser Reject
irgendwann" nach „lauter Startfehler sofort" verlegt — und zwar beim
allerersten `RiskConfig()`-Aufruf, bevor irgendein Test lief. Das ist genau
die Begründung, mit der Anker (c) ins Ticket kam; sie hat sich an den eigenen
Defaults bewiesen.

Behoben durch `DEFAULT_MAX_ORDER_SIZE_SHARES = 100.0` (konsistent zum
Positionslimit und als Order-Level-Cap realistisch).

## Review-Standard (aus diesem Zyklus übernommen)

Für safety-relevante Module (Risk, Telemetry, Storage-Boundaries) gilt:
**ein Mutant pro gehärteter Invariante.**

Der Anlass war ein negativer Mutationsnachweis: Der 4-Pfade-Test lief grün
durch, obwohl `None.value` wieder eingebaut war — alle vier `on_signal`-Zweige
setzen ein Enum, der `None`-Fall war im Produktivpfad **unerreichbar**.
Erst Wache + Boundary-Test töten den Mutanten (an Konstruktion und Boundary).

Das ist der Unterschied zwischen „Tests sind grün" und „Tests bewachen etwas".

### Der Standard in Aktion (Commit-Historie)

Dieser Zyklus enthält zwei dokumentierte Kehrtwenden. Sie sind bewusst nicht
weggeglättet — für eine Engine, die später fremdes Geld bewegen soll, ist
„wir dokumentieren unsere Irrtümer nicht weg" keine Sentimentalität, sondern
Kultur:

| Commit | Was widerrufen wurde | Wie es auffiel |
|---|---|---|
| `43a2f9a8` | F1-Befund „der `MAX_POSITION_SIZE`-Check ist unerreichbar" | Verifikation am Code: Zeile 122 **funktioniert**; es sind zwei tote Order-Level-Checks, nicht der Check |
| `5b6280fd` | Zusage „keine Schema-Änderung" | Prüfung der DDL: die `telemetry`-Tabelle hat gar kein Größen-Feld |

Beide Korrekturen stammen nicht aus einem Review durch Dritte, sondern aus
der Aufforderung, eine Behauptung zu belegen, bevor Code darauf gebaut wird.
Lehrstück für den nächsten Fall: **Ein Befund, der im Ticket plausibel klingt,
ist noch nicht verifiziert.**

### Dritter Fall derselben Krankheit: Scheinschutz

**Ein fehlender Check fällt auf; ein scheinender nicht.**

Der schärfste Beleg kam zum Schluss, aus den F1-Defaults: `max_order_size_shares
= 1000` gegen `max_position_size_usdc = 500` hieße, die Engine hätte bei jedem
Preis über 0,50 ihre eigene Default-Order abgelehnt. Der tote Check 116 hätte
genau das **nicht** gefangen (`1000 > 1000` ist false). Der Check sah also nicht
nur *aus* wie Schutz — er sah aus wie **genau der** Schutz für genau diesen
Fehler, und hätte ihn trotzdem durchgelassen.

Dasselbe Muster trat in diesem Zyklus **dreimal** auf, in drei verschiedenen
Schichten — es ist ein wiederkehrender Modus, kein Einzelfall:

| Fall | Schicht | Wie der tote Pfad aussah |
|---|---|---|
| Zeile ~116 (`order.size > max_order_size_shares`) | Produktionscode | sah wie eine Risikobremse aus, war eine Tautologie |
| F1c-Seam, wenn von keinem Test gekreuzt | Refactoring | sieht wie eine Schnittstelle aus, ist eine leere Zuweisung |
| `reject_reason=None`-Test (erste Fassung) | Testsuite | sah wie ein Regressionstest aus, färbte nie |

**Name: Scheinschutz.** Benannte Muster sind im Review aufrufbar — „das ist
wieder Scheinschutz" ist schneller gesagt als die ganze Analyse.

Gemeinsame Form: **Etwas existiert, sieht nach Schutz aus und kann nie
feuern.**

#### Die Gegenmaßnahme in einem Satz

> **Jede Schutzbehauptung braucht einen Zeugen.** Ein konkretes Ereignis, das
> sie auslöst. Kann kein Zeuge konstruiert werden, ist es kein Schutz, sondern
> Dekoration — und Dekoration im Risk-Pfad ist schlimmer als Abwesenheit, weil
> sie Vertrauen besetzt, das der Code nicht einlöst.

Ein Prinzip, vier Schichten:

| Angewandt auf | Zeuge |
|---|---|
| Risk-Check | Anker-Test: zweiter Fill kippt die Position über das Limit → Reject |
| Test | Sensitivitäts-Kriterium (e): der Test **muss rot werden**, wenn der Mutant eingebaut wird |
| Refactoring / Seam | Coverage auf den neuen Zeilen: der Seam wird tatsächlich durchlaufen |
| **Prädikat** | **Erreichbarkeits-Nachweis: der Wahr-Zweig muss erzeugbar sein.** `is_expired()` konnte nie `True` liefern, weil `_reject_expired` den Zustand am Konstruktor unerzeugbar macht. |

Die vierte Schicht ist die subtilste: Ein Prädikat, dessen Wahr-Zweig
**unerreichbar** ist, sieht wie eine Zusicherung aus und ist eine Behauptung.
Sie ist dieselbe Architektur-Philosophie wie bei `TelemetryRecord` —
*unmöglich schlägt prüfbar* — nur dass hier die Altlast die Philosophie schon
kannte und das Werkzeug der alten Denkweise stehen ließ.

**Reihenfolge ist Teil des Befunds:** Die Maschinerie überlebte ihr Label um
exakt einen Commit. Das ist richtig so — F1b musste zuerst beweisen, dass das
Label keinen Produzenten hat; die Frage „was ruft diese Methode?" war erst
danach scharf zu stellen.

Die Frage ist nie „ist es vorhanden?", sondern **„kann es feuern, und beweist
ein Test das?"**. Deshalb zwei komplementäre Nachweise in F1c (Unverändertheit
*plus* Durchlaufung): Einer allein deckt nur die halbe Krankheit ab.

### Herkunft dieses Standards

Der Zyklus begann mit einer falschen Alarmmeldung („der Bug hätte beim ersten
Fill zugeschlagen") und endete mit einem Review-Standard, der aus der Praxis
geboren statt dekretiert wurde. Für eine Engine, die später fremdes Geld
bewegen soll, ist das der wertvollere Ertrag: nicht drei gehärtete Checks,
sondern ein Präzedenzfall dafür, wie mit Unsicherheit umgegangen wird —
**verifizieren, korrigieren, stehen lassen.**

### Historie verdichten: Widerrufe bleiben, Zwischenstände dürfen weg

Aus zwei konkreten Squash-Entscheidungen dieses Zyklus:

> **Widerrufe sind Stationen. Vervollständigungen sind Zwischenstände.**

- **Widerruf → behalten.** Eine Station, die einen falsifizierten Befund oder
  eine korrigierte Zusage zeigt, beweist, dass der Prozess funktioniert. Sie
  zu squashen produziert eine Geschichte, in der die Behauptung nie falsch
  war — und entwertet das Lehrstück.
  Beispiele: `43a2f9a8` (F1-Befund falsifiziert), `5b6280fd` (Schema-Zusage
  korrigiert).
- **Vervollständigung → darf verdichtet werden.** Ein Commit, der einen
  bestehenden Text ergänzt und dessen Inhalt der Endzustand selbst trägt,
  verliert beim Squash nichts.
  Beispiel: `08a2b8cb`/`375cdb0d` (Standard plus seine dritte Instanz).

**Prüffrage vor jedem Squash:** Trägt der Endzustand die Information selbst,
oder lebt sie nur in der Commit-Message? Nur im ersten Fall ist der Squash
verlustfrei. Wird gesquasht, obwohl die Message der einzige Träger ist, muss
die kombinierte Message den widerrufenen Inhalt explizit benennen.

---

## F1-Cluster: geschlossen (2026-09-20)

**F1c** (Seam, verhaltensneutral, bezeugt) → **F1** (signal-getriebenes Sizing,
engine-seitiger Clamp, getrennte Reject-Reasons, Schema v2 — fünf
Mutanten-Leichen, ein Selbstfang der Invariante) → **F1b** (Falle entschärft:
`SAFETY_GUARD`/`MAX_ORDER_SIZE`/`MAX_ORDER_NOTIONAL` weg, Enum ehrlich,
Meta-Anker installiert) → **F1b-Nachlauf** (`is_expired()` und seine Maschinerie
entfernt).

### Endzustand des Enums

```
NONE, MAX_POSITION_SIZE, MAX_EVENT_EXPOSURE,
DRAWDOWN_LOCKOUT, INSUFFICIENT_CASH, INVALID_PRICE
```

Das Enum ist eine **garantiert wahre Spezifikation** dessen, was die Engine
ablehnen kann. Der Meta-Anker
(`test_ankerd_meta_every_reject_reason_has_a_producer`) prüft das bei jedem
Lauf: **kein Label ohne Produzenten.** Er hat sich an Tag 1 bezahlt — zwei
Waisen (`EXPIRED`, `SAFETY_GUARD`), die auf keiner Liste standen, plus die
verwaiste Maschinerie dahinter (`is_expired()`).

### Was der Zyklus über den Prozess sagt

Der Zyklus begann mit einer falschen Alarmmeldung und endete mit einem
Review-Standard, der aus der Praxis geboren statt dekretiert wurde. Der
wertvollste Ertrag sind nicht die gehärteten Checks, sondern der **Präzedenzfall
dafür, wie mit Unsicherheit umgegangen wird**: verifizieren, korrigieren,
stehen lassen. Zeugen werden gelöscht, nicht umgeschrieben, wenn ihr Gegenstand
stirbt; Enum-Werte brauchen einen Produzenten; tote Maschinerie neben einem
gelöschten Label ist derselbe Befund einen Meter weiter.

### Offen

**F2** (Pydantic-Parität — jetzt mit dem dokumentierten
`max_order_size_shares`-Umzug als Anhängsel; Messlatte und Fund-Regel oben),
**F3**, Strategy-Package.

**Der aktuelle Merksatz gilt bis dahin:** Die Engine kann nicht mehr lügen,
ohne dass es jemand merkt — und sie kann es ab jetzt **beweisen**.



