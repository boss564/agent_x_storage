# Tag-7-Abnahme — Shadow Execution Engine (Messperiode 04.10.–01.11.2026)

Stand: 17.10.2026. Dieses Dokument ist **vorab** festgeschrieben. Wird später
etwas anders gelesen, gilt die hier stehende Nummer, nicht eine neue Lesart.

**Grundlage (Code, gegen den abgenommen wird):** `01fdbb1d`
(Reconciliation, Join-Schlüssel, zwei Achsen) · `bd241b1a` (dieses Dokument).
Das Kriterium beurteilt genau diesen Stand.

## 0. Termin

| Datum | Rolle |
|---|---|
| **Montag, 20.10.2026, 10:00** | **Tag 7 — Abnahme** (Code, heute entscheidbar) |
| **Montag, 03.11.2026** | **Berichtstermin Marktbeobachtung** (Daten, entscheidbar irgendwann) |
| 01.11.2026 | **kein Termin** — Samstag, niemand zuständig |

Das Datum ist **unbedingt**, nicht bedingt auf §5.1: Variante C ist
synthetisch und hängt weder an Run 8/9 noch am Markt noch an
`integrate_news_index`. §5.1 entscheidet eine Zeile im Bericht
(„Basis: Run 8 / Run 8+9"), nicht das Urteil.

## 1. Festschreibung des Kriteriums (Variante C)

> Tag 7 gilt als bestanden, wenn (a) der Replay-Positivfall einen Fill mit
> `fill_ratio > 0` und `vwap` innerhalb des konstruierten Spreads erzeugt,
> (b) der Replay-Negativfall `INVALID_PRICE` statt Fill erzeugt, (c) beide am
> 31.10. 23:59 grün sind. Reale Fills bis 01.11. sind Beobachtung und gehen
> nicht in das Urteil ein.

**Frist: 20.10.2026, 10:00 — unbedingt.** Die vorige Fassung führte die Frist
offen; die Begründung dafür (Sorge um einen Handler-Umbau vor 01.11.) ist mit
`01fdbb1d` entfallen, weil C synthetisch ist.

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

**Abnahmeprotokoll 20.10.2026, 10:00** — jede Zeile wird vor Ort ausgeführt,
nicht zitiert.

| # | Beobachtung | Befehl / Quelle | Erwartung |
|---|---|---|---|
| 1 | Suite auf `01fdbb1d` | `pytest order_execution_engine/tests/` | 157 grün |
| 2a | Replay-Positiv | `pytest -k test_c1` | Fill im Spread, `fill_ratio > 0` |
| 2b | Replay-Negativ | `pytest -k test_c2` | `INVALID_PRICE`, keine Metrik |
| 3 | Mess-DB unberührt | `pytest -k test_c3` | 0 Diff |
| 4 | Join-Schlüssel | `gate_snapshot` | `join_is_one_to_one: True` über `(run_id, decision_seq)` — **nicht `item_id`** |
| 5 | Run 8 | `gate_snapshot(min_run_id=8)` | `historical: RED`, `unattributed = 4`, Ausgangsachse **34** |
| 6 | §5.1 | dieses Dokument, §5.1 | Zeitstempel vorhanden — Zeitstempel, nicht Urteil |

## 2a. Was am 20.10. ausdrücklich **nicht** abgenommen wird

| Posten | Status | Warum nicht abnehmbar |
|---|---|---|
| realer Fill-Pfad | **unbelegt** (1 Fill in 13,2 d) | Markt, nicht Code — C belegt den Handler, nicht die Anbindung |
| Symbolkonzentration `INVALID_PRICE` | **offen** | kein Index (§7), Aussage gestrichen |
| run-9-Baseline | **bedingt** auf §5.1 | eine Zeile im Bericht, kein Urteil |

Diese drei gehören ins Protokoll, nicht in die Fußnote. Abnahme ist Code und
heute entscheidbar; Beobachtung ist Markt und entscheidbar irgendwann. Ein
Termin, der beides trägt, verschiebt das Entscheidbare auf das Unentscheidbare.

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

Zitiert mit Zeitstempeln, damit sie nicht als Verweis auf ein Gespräch im
Dokument fehlt. Eine Rücknahme des Codes ist keine Messung.

| Frage | Befund | Beleg (Befehl · Zeitstempel) |
|---|---|---|
| Läuft der Prozess seit Run-9-Start? | **ja** | `ps -o lstart -p 962` → `Wed Oct 14 21:23:32 2026`; Run 9 `started_at` → `2026-10-14T21:23:36` |
| Neustart zwischendurch? | **nein** | `launchctl print gui/501/…shadow-runner` → `runs = 1`, `last exit code = (never exited)`, `state = running` |
| Welchen Code lädt der Prozess? | **HEAD `5c5bc364`**, byte-gleich | `sha256(HEAD:shadow_runner.py) == sha256(worktree)` → `1a71c15f…ac4`; `lsof -p 962` zeigt **keine** offene `.py` und keine `.pyc` aus dem Paket |
| Warum mtime 16:50? | meine Rücknahme, kein Start | Schreiben + Rückschreiben; `__pycache__/shadow_runner.cpython-314.pyc` trägt denselben Stempel und wurde nie importiert |

**Ergebnis:** `integrate_news_index` war zu keinem Zeitpunkt im laufenden
Prozess aktiv. Run 8 und Run 9 liefen unter demselben Runner-Code; der
`config_json`-Diff ist ausschließlich `git_commit` (`9556b1d7` →
`5c5bc364`), kein `-dirty`. Die Freeze hat gehalten, weil der Baum zufällig
sauber war — nicht, weil der Neustart kontrolliert war.

**Basis der Auswertung:** Run 8 **und** Run 9 (nicht Run 8 allein).

### 5.2 Sauberkeit: geprüfter Raum

Die Aussage „Arbeitsbaum sauber" gilt für **die Repo-Wurzel**, nicht nur für
`order_execution_engine/` — der Runner liest den Tree, in dem er läuft
(`lsof -p 962 -d cwd` → `/Volumes/THX_OS_ULTRA/.../agent_x_storage`).

| Prüfung | Ergebnis (17.10.2026) |
|---|---|
| `git status --porcelain` (Wurzel) | **1 Eintrag**: `?? scripts/address_register_0r.py` |
| tracked, modifiziert | **0** |
| `git diff --quiet` | **0** (clean) |

**Blindstelle, die dabei sichtbar wurde:** `git_commit_short()` im Runner
prüft `git diff --quiet` — **untracked Dateien zählen dort nicht**. Die
untracked Datei ist bewusst „kein Commit"-Utensil (Kopfzeile: *„read-only ·
kein Commit"*), mtime 10.10. 15:38, also **vor** dem Run-9-Start (14.10.
21:23). Sie wurde nicht von diesem Prozess geladen und ist nicht Teil des
Imports. Der `-dirty`-Suffix im Run-Fingerprint ist jedoch **strukturell blind
gegenüber untracked Dateien** — ein Befund für die Provenienz-Regel, kein
Defekt dieses Laufs.

## 5.3 Zwei Verdikte statt eines

Ein dauerhaft roter abgeschlossener Lauf macht das Gate zur Tapete: rot, das
erwartet ist, wird nach zwei Wochen nicht mehr gelesen. Die Ausgabe führt
deshalb zwei Verdikte:

```
verdict current:    GREEN                        (letzter Lauf, blockierend)
verdict historical: RED (run 8, unattributed=4)  (abgeschlossen, nicht blockierend)
```

`current` blockiert (`FAIL` in `errors`), `historical` wird als `WARN`
protokolliert. **Die Trennung schluckt nichts:** ist der *jüngste* Lauf rot,
ist `current: RED` und blockiert — Zeuge `test_current_red_still_blocks`.
Der zweite Zeuge (`test_historical_red_does_not_block_current_green`) hält
fest, dass Run 8 dokumentiert und nicht blockierend erscheint.

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
| `tests/test_telemetry_reconciliation.py` | Vollständigkeit, `<`→Gleichheit, zwei Achsen, `decision_seq`-Kollision, Zeile ohne Key, Neustart je Run, `item_id` ≠ Join-Schlüssel, historical-rot-blockiert-nicht, current-rot-blockiert |

Suite: **157 passed** auf `01fdbb1d`-Stand. **Grün heißt „die Tests laufen",
nicht „die Tests prüfen das Richtige"** — die erste Fassung dieser Runde war
grün über einem falschen Join-Schlüssel. Deshalb sind die Negativkontrollen
(38 vs. 34, `decision_seq`-Kollision, current-RED) ausdrücklich Teil der Suite.
