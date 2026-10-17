# Tag-7-Abnahme — Shadow Execution Engine (Messperiode 04.10.–01.11.2026)

Stand: 17.10.2026. Dieses Dokument ist **vorab** festgeschrieben. Wird später
etwas anders gelesen, gilt die hier stehende Nummer, nicht eine neue Lesart.

## 1. Festschreibung des Kriteriums (Variante C)

> Tag 7 gilt als bestanden, wenn (a) der Replay-Positivfall einen Fill mit
> `fill_ratio > 0` und `vwap` innerhalb des konstruierten Spreads erzeugt,
> (b) der Replay-Negativfall `INVALID_PRICE` statt Fill erzeugt, (c) beide am
> 31.10. 23:59 grün sind. Reale Fills bis 01.11. sind Beobachtung und gehen
> nicht in das Urteil ein.

**Frist: offen.** Die Festschreibung ist ohne Datum gültig, bis die in §5
genannte Vorbedingung (Provenienz je Run-Start) geklärt ist. Ein Datum vor der
Auskunft wäre das nächste Kriterium, das nachher angepasst wird.

| Variante | Status | Begründung |
|---|---|---|
| C — Pfad gegen Replay | **Kriterium** | unabhängig vom Markt, bis 31.10. erreichbar |
| A — `n ≥ 1` Fill | Beobachtung | bei ~1,1 erwarteten Fills nicht von Zufall zu trennen |
| B — `n ≥ 5` Fills | verworfen | rechnerisch unerreichbar ⇒ garantiert rot |

Tests: `order_execution_engine/tests/test_fill_replay.py`

* `test_c1_positive_fill_inside_spread` — Book mit Bid/Ask ⇒ Fill,
  `fill_ratio > 0`, VWAP zwischen `best_bid` und Walk-Obergrenze,
  `telemetry_fill_metrics`-Zeile geschrieben.
* `test_c2_negative_no_book_rejects_invalid_price` — leeres Book ⇒
  `INVALID_PRICE`, kein Fill, keine Fill-Metrik.
* `test_c3_replay_does_not_touch_measurement_db` — Replay schreibt unter
  eigenem `user_id`; Zeilenzahlen der Mess-DB vor/nach gleich.

Ersetzt wird ausschließlich die **Datenquelle** (der Snapshot). Engine und
Fill-Handler sind unverändert — kein Mock der Entscheidungslogik.

## 2. Urteilstabelle (6 Zeilen, je Beobachtung ein Verdikt)

| # | Beobachtung (Quelle) | Verdikt bei Tag 7 |
|---|---|---|
| 1 | C-Positivfall grün (`test_c1`) | **Pflicht** — rot ⇒ Tag 7 nicht bestanden |
| 2 | C-Negativfall grün (`test_c2`) | **Pflicht** — Pfad diskriminiert nicht ⇒ nicht bestanden |
| 3 | C-Isolation grün (`test_c3`) | **Pflicht** — sonst urteilt der Replay über fremde Zeilen |
| 4 | `filled` > 0 in den Terminalklassen | **Beobachtung**, kein Urteil |
| 5 | `unattributed` = 0 | **Beobachtung**; > 0 ⇒ Lücke benennen, nicht wegrechnen |
| 6 | Gate-Lauf am 31.10. ohne neue RED-Klasse | **Pflicht** — neue RED ⇒ Ursache vor Urteil |

## 3. Nenner-Regel

`claims_total ≠ claims_mit_telemetrie`. Ein Erfolgs-Dispatch ohne
Telemetriezeile ist eine **unklassifizierte Terminalentscheidung**, keine
unbedenkliche Lücke. `TELEMETRY_RECONCILIATION` prüft daher Gleichheit und
Vollständigkeit, nicht `<`.

Verifikation (live, 17.10.2026):

| Lauf | claims | success | telemetry | klassifiziert | unattributed | Gate |
|---|---|---|---|---|---|---|
| 8 | 358 | 34 | 34 | 34 | **4** | **RED** |
| 9 | 59 | 4 | 4 | 4 | 0 | GREEN |

Achte auf die Spalte `telemetry`: sie zählt **Zeilen**, nicht **Herkunft**.
Run 8 hat 34 Zeilen, davon 30 mit eigener Entscheidung und 4, die
zu einem Dispatch ohne eigene Zeile gehören. Als Herkunftszähler ist
`telemetry_rows` wertlos — sie ist auf Run-Ebene identisch mit der
Ausgangssumme. Gezählt wird `success − unattributed`.

Verknüpfung der 4 unklassifizierten Fälle über `decision_seq` (Reihenfolge der
Erfolgs-Dispatches). `signal_id` ist **nicht** joinbar: `item_id` aus der Bridge
ist ein MD5-Hash, `telemetry.signal_id` eine UUID-Sub5.

**Korrektur der Join-Assertion (17.10., vor Commit):** Die frühere
Form `count(*) = count(DISTINCT item_id)` bewies die Eindeutigkeit einer
Spalte, nicht die Kardinalität des Joins. Gültig ist das Paar
`(run_id, decision_seq)` — der Zähler startet je Prozess neu (Run 9
beginnt wieder bei 1). Geprüft wird je `run_id`:
`count(*) = count(DISTINCT decision_seq)`. `item_id` bleibt als
Eindeutigkeitsbefund (`item_id_is_unique`) im Report, nicht unter dem
Namen des Joins.

## 4. Terminalklassen — zwei Achsen, nicht eine Summe

`Erfolgspfad` ist **deprecated**: es zählte Ablehnungen mit.

```
outcome (Σ=claims_mit_telemetrie): {filled, rejected, stale}
origin  (Σ=dispatched_success):    {telemetry, unattributed}
```

Run 8: `outcome {filled: 1, rejected: 26, stale: 7}` = **34** ·
`origin {telemetry: 30, unattributed: 4}` = **34**
Run 9: `outcome {filled: 0, rejected: 4, stale: 0}` = **4** ·
`origin {telemetry: 4, unattributed: 0}` = **4**

**Die Ein-Achsen-View war falsch.** `filled/rejected/stale` klassifiziert
nach **Ausgang**, `unattributed` nach **Herkunft** — zwei orthogonale
Dimensionen. Zusammengelegt ergab sich 1 + 26 + 7 + 4 = **38 gegen 34**.
Die 38 ist eine Abweichung, keine Rundung. Der Zeuge
`test_terminal_view_is_two_axes_not_one_sum` hält die 38 als Negativkontrolle
fest; `partition_ok` prüft, dass beide Achsen einzeln auf `success` schließen.

Die zugrunde liegenden Spalten (`telemetry.reject_reason`, `status`) bleiben
unverändert — eine Spaltenumbenennung würde Alarme stillschweigend verschieben.

## 5. Vorbedingung mit Eigentümer (nicht mit Docs erledigt)

Der Runner lädt aus dem **Working Tree**, nicht aus einem gepinnten Commit.
`-dirty` hätte die Messperiode entwertet, ohne dass eine Zeile es sagt.

* Eigentümer: Messbetrieb.
* Regel: **keine Änderung im Working Tree während der Messperiode**;
  `git status` vor jedem Neustart prüfen, Ergebnis im Bericht.

### 5.1 Zeitstempel-Auskunft (17.10.2026, gemessen — nicht behauptet)

Eine Rücknahme des Codes ist keine Messung. Deshalb hier die drei Fragen
mit Belegen statt mit `git diff`:

| Frage | Befund | Beleg |
|---|---|---|
| Läuft der Prozess seit Run-9-Start? | **ja**, PID 962 seit `Wed Oct 14 21:23:32` | `ps -o lstart -p 962`; Run 9 `started_at` = 21:23:36 |
| Wurde der Runner zwischendurch neu gestartet? | **nein**, `runs = 1`, `last exit code = (never exited)` | `launchctl print gui/501/…shadow-runner` |
| Welchen Code lädt der laufende Prozess? | **HEAD `5c5bc364`**, byte-gleich | `sha256` Working Tree == `HEAD:shadow_runner.py`; `lsof -p 962` zeigt **keine** offene Quelldatei |

Zur mtime von `shadow_runner.py` (17.10. 16:50): Sie stammt von meiner
Rücknahme (Schreiben + Rückschreiben), **nicht** von einem Prozessstart. Der
`__pycache__/shadow_runner.cpython-314.pyc` trägt denselben Zeitstempel —
importiert wurde er nie (kein Neustart, keine offene `.pyc`). Der laufende
Prozess hält sein Modul im RAM.

**Ergebnis:** `integrate_news_index` war zu keinem Zeitpunkt im laufenden
Prozess aktiv. Run 8 und Run 9 sind unter demselben Runner-Code gelaufen;
der `config_json`-Diff ist ausschließlich `git_commit` (`9556b1d7` →
`5c5bc364`), kein `-dirty`. Die Freeze hat gehalten, weil der Baum zufällig
sauber war — nicht, weil der Neustart kontrolliert war.

**Grenze der Auskunft:** Das belegt den *Prozess*, nicht die *Zukunft*. Die
Vorbedingung „keine Änderung im Working Tree" bleibt bestehen, mit Eigentümer.

## 6. `telemetry_seq` — tot, kein Backfill

`dispatched_signals.telemetry_seq` ist zu 0/358 gefüllt. Sie wird **nicht**
nachträglich befüllt: ein Backfill wäre erfundene Provenienz und würde den
einzigen vorhandenen Beweis (den `decision_seq`-Join) scheinbar überflüssig
machen. Die Spalte bleibt als tot dokumentiert.

## 7. Offener Punkt: Symbolkonzentration

`invalid_price_by_asset` steht im Preflight, liefert aber `unknown`, solange
kein `news_index.jsonl` existiert (item_id → `target_assets`). Den Index
müsste der **Runner** schreiben — das ist während der Messperiode
ausgeschlossen und daher ein Folgepunkt nach 01.11.

**Gestrichen (17.10.):** Die Aussage, die Verteilung der **Erfolgs-Claims**
(BTC 17, ETH 8, Kombis 8) spräche für Datenanbindung statt Universum. Erfolge
sind die **Gegenmenge** der Frage: eine gestreute Erfolgsverteilung ist mit
einem einzigen toten Symbol genauso vereinbar wie mit zwanzig. Es gibt derzeit
**kein** Indiz zur Konzentration der `INVALID_PRICE`-Fälle.

## 8. Tests dieser Runde

| Datei | Zeugen |
|---|---|
| `tests/test_fill_replay.py` | C-Positiv, C-Negativ, C-Isolation (3) |
| `tests/test_telemetry_reconciliation.py` | Vollständigkeit, `<`→Gleichheit, zwei Achsen, `decision_seq`-Kollision, Zeile ohne Key, Neustart je Run, `item_id` ≠ Join-Schlüssel |

Suite: 155 passed. **Grün heißt „die Tests laufen", nicht „die Tests prüfen
das Richtige"** — die erste Fassung dieser Runde war grün über einem falschen
Join-Schlüssel. Deshalb sind die beiden Negativkontrollen (38 vs. 34,
`decision_seq`-Kollision) ausdrücklich Teil der Suite.
