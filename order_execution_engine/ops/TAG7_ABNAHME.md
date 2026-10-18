# Tag-7-Abnahme — Shadow Execution Engine

**Abnahme: Dienstag, 20.10.2026, 10:00** · Berichtstermin: Dienstag, 03.11.2026

Stand: 17.10.2026. Dieses Dokument ist **vorab** festgeschrieben. Wird später
etwas anders gelesen, gilt die hier stehende Nummer, nicht eine neue Lesart.

**Grundlage (Code, gegen den abgenommen wird):** `01fdbb1d`
(Reconciliation, Join-Schlüssel, zwei Achsen) · `bd241b1a` (dieses Dokument).
Das Kriterium beurteilt genau diesen Stand.

## 0. Termin

**Tag 7 = Dienstag, 20.10.2026, 10:00.**

**Jahrgang — vier Zeugen, die übereinstimmen müssen** (17.10.2026, 17:40:37):

```
date                2026-10-17T17:40:37+0200 (Saturday)
git log -1 %cI      2026-10-17T17:38:19+02:00
ps -o lstart= -p    Wed Oct 14 21:23:32 2026
find -newermt       muß dieselben Treffer liefern wie `ps`-Start
```

Alle vier sagen **2026**. Bis sie übereinstimmen, keine Abnahme — das ist
die erste Zeile des Protokolls, nicht eine Vorrede.

**Auflösung per Befehl, Ausgaben eingefügt, nicht eingetippt:**

| Datum | Ist-Ausgabe | Rolle |
|---|---|---|
| **2026-10-20** | `Tuesday` | **Tag 7 — Abnahme** (Jahrgang des Prozesses) |
| 2026-11-03 | `Tuesday` | Berichtstermin Marktbeobachtung |
| 2026-10-17 | `Saturday` | dieser Arbeitsstand (nicht Freitag) |
| 2026-10-14 | `Wednesday` | Prozessstart (`ps lstart`) |
| 2025-10-20 | `Monday` | **nicht** der Abnahmetag — Jahreszahl-Falle |

> **Der Befund hinter dieser Tabelle:** Frühere Fassungen zertifizierten
> `2025-10-20 → Monday`, während der Prozeszeuge `Wed Oct 14 2026` sagte.
> Beides stimmt für sich — und zusammen heißt es: **Zeile 0 prüfte die
> Wochentage von 2025, der Prozeß läuft seit 2026.** Eine Tabelle, die für
> 2025 stimmt, ist kein Beleg für ein Dokument aus 2026. Das ist keine
> Rechenungenauigkeit, sondern eine **nicht anwendbare Prüfung** — und sie
> fällt nicht auf, weil jede Zeile für sich korrekt ist.
>
> In dieser Akte sind damit **fünf** Zeitangaben nachträglich aufgelöst
> worden, keine beim ersten Schreiben. Die Fehlerform bleibt dieselbe: ein
> Etikett, das nie gegen seinen Gegenstand gehalten wurde — hier gegen das
> **Jahr**, das in keiner der früheren Tabellen stand.

Das Datum ist **unbedingt**, nicht bedingt auf §5.1: Variante C ist
synthetisch und hängt weder an Run 8/9 noch am Markt noch an
`integrate_news_index`. §5.1 entscheidet eine Zeile im Bericht
(„Basis: Run 8 / Run 8+9"), nicht das Urteil.

**Basis-Zeile (Code je Run, nicht nur Run-Nummern):**

| Gegenstand | Commit / Hash | Rolle |
|---|---|---|
| Run 8 + 9 (Daten) | `5c5bc364` · Runner `92338139e8…` | **erzeugt** von diesem Stand |
| Gate (Urteil) | **`146b4be4`** · `3dad796a…` | **erzeugt** die Verdikte `current`/`historical` |
| Gate (Kopfzeile) | **`ce80e9a9`** · `7ef57c49…` | **erzeugt** `gate:` und `blocking:` |
| Gate im Betrieb | — | **kein Dienstbestandteil**, nur manueller Aufruf |
| Ab `Run 10` | `e91916bd` (Runner identisch) | belastbare Basis des neuen Stands |

> **„Run 8 + 9" ist richtig als Datengrundlage und falsch als
> Codegrundlage.** Wer in drei Wochen Run 9 mit Run 11 vergleicht, vergleicht
> Daten aus `5c5bc364` mit Daten aus `e91916bd` — bei identischem Runner, aber
> neuem Prüfer. Ohne diese Zeile sieht das aus wie dasselbe Programm.

**Korrektur (`01fdbb1d` → `146b4be4`).** Frühere Fassungen nannten
`01fdbb1d` als Prüfer-Commit. Der Blob dieser Fassung ist dort aber
`50769715…`; `3dad796a…` entsteht erst in `146b4be4` — dem Commit, der die
zwei Verdikte einführte. Die Verdikte stammen also weder aus `01fdbb1d`
(Gate/Join/zwei Achsen) noch aus dem Commit, den die alte Basis-Zeile nannte:

```
git rev-parse 01fdbb1d:…/preflight_check.py  → 50769715b52f5f745436c0949e9202d18dd0fcc2
git rev-parse 146b4be4:…/preflight_check.py  → 3dad796a30149f1b089807921bbd46b3aef10164
git hash-object  …/preflight_check.py        → (Fassung nach dieser Runde)
```

Ein Commit-Etikett, das nicht aufgelöst wurde — dieselbe Form wie die
Kalenderangaben, nur heißt das Etikett diesmal Commit.

## 1. Festschreibung des Kriteriums (Variante C)

> Tag 7 gilt als bestanden, wenn (a) der Replay-Positivfall einen Fill mit
> `fill_ratio > 0` und `vwap` innerhalb des konstruierten Spreads erzeugt,
> (b) der Replay-Negativfall `INVALID_PRICE` statt Fill erzeugt, (c) beide am
> 31.10. 23:59 grün sind. Reale Fills bis 01.11. sind Beobachtung und gehen
> nicht in das Urteil ein.

**Frist: Dienstag, 20.10.2026, 10:00 — unbedingt.** Die frühere Fassung trug
diese Frist noch als „offen"; die Begründung dafür (Sorge um einen
Handler-Umbau vor dem Periodenende) ist mit `01fdbb1d` entfallen, weil C
synthetisch ist.

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

**Abnahmeprotokoll Dienstag, 20.10.2026, 10:00** — jede Zeile hat Befehl,
**erwartete Ausgabe** und **Verdikt bei Abweichung**.

**Regel für `NICHT ENTSCHEIDBAR`:** zulässig **nur** in Zeilen 5 und 6 —
dort hängt die Wahrheit an Daten, die noch nicht existieren (Markt,
Symbolindex). Bei allen deterministischen Zeilen (0–4) ist eine Abweichung
**NICHT BESTANDEN**. „Nicht entscheidbar" wäre dort kein Befund, sondern ein
Freifahrtschein für die einzige Zeile, die den Termin selbst trägt.

| # | Befehl | Erwartete Ausgabe | Verdikt bei Abweichung |
|---|---|---|---|
| 0 | `date -j -f "%Y-%m-%d" 2026-10-20 "+%A"` | `Tuesday` (**Ist, eingefügt**) | **NICHT BESTANDEN** |
| 1 | `pytest order_execution_engine/tests/` | `168 passed` | **NICHT BESTANDEN** |
| 2a | `pytest -k test_c1_positive` | `1 passed, 2 deselected`; Fill im Spread | **NICHT BESTANDEN** |
| 2b | `pytest -k test_c2_negative` | `1 passed, 2 deselected`; `INVALID_PRICE`, keine Metrik | **NICHT BESTANDEN** |
| 3 | `pytest -k test_c3_replay_does_not_touch` | `1 passed, 2 deselected`; Mess-DB 0 Diff | **NICHT BESTANDEN** |
| 4 | `gate_snapshot` | `join_is_one_to_one: True` über `(run_id, decision_seq)` | **NICHT BESTANDEN** |
| 5 | `gate_snapshot(min_run_id=8)` | `historical: RED (run 8, unattributed=4)`; Ausgangsachse **34**; `current: GREEN` | **NICHT ENTSCHEIDBAR** (Abweichung benennen, nicht glätten) |
| 6 | §5.1 + §5.4, dieses Dokument | Zeitstempel, Sweep- und Import-Graph-Ausgabe vorhanden | **NICHT ENTSCHEIDBAR** |
| 7 | §5.4d, pyc-Inhalt gegen `5c5bc364` | 9/9 Module `OK`; `flags = 0x00000000` dokumentiert | **NICHT BESTANDEN** |
| 8 | `gate_snapshot` | Etikett `LEDGER_CONSISTENT`, (0)–(4) == RED-Zweige, (5) Warnung | **NICHT BESTANDEN** |
| 9 | §5.4f–§5.4ab | eine `pyc`, Schwelle beidseitig, `etime`, Blob↔Commit, `delivered` datiert, `DERIVED` definiert, `INVALID_PRICE` aufgelöst | **NICHT BESTANDEN** |

**Regel gegen den Haken-Fehler:** Ein Haken bedeutete bisher „ausgeführt",
nicht „getroffen". Deshalb steht in jeder Zeile die erwartete **Ausgabe**;
weicht sie ab, ohne dass `NICHT ENTSCHEIDBAR` zulässig ist, ist die Zeile
`NICHT BESTANDEN` — nicht „im Wesentlichen wie erwartet".

## 2a. Was am 20.10. ausdrücklich **nicht** abgenommen wird

| Posten | Status | Warum nicht abnehmbar |
|---|---|---|
| realer Fill-Pfad | **unbelegt** (1 Fill in 13,2 d) | Markt, nicht Code — C belegt den Handler, nicht die Anbindung |
| Symbolkonzentration `INVALID_PRICE` | **offen** | kein Index (§7), Aussage gestrichen |
| run-9-Baseline | **bedingt** auf §5.1 | eine Zeile im Bericht, kein Urteil |

Diese drei gehören ins Protokoll, nicht in die Fußnote. Abnahme ist Code und
heute entscheidbar; Beobachtung ist Markt und entscheidbar irgendwann. Ein
Termin, der beides trägt, verschiebt das Entscheidbare auf das Unentscheidbare.

## 2b. Ablauf am 20.10. — die Abfrage, die den Gegenstand vom Etikett trennt

| Zeit | Schritt | Erwartung |
|---|---|---|
| 09:40 | `git diff 5c5bc364 e91916bd -- order_execution_engine/shadow_runner.py` | **Ist-Ausgabe ins Protokoll** (17.10. vorab: leer) |
| 09:42 | `rg -n "preflight_check" --glob '!tests/**' --glob '!*.md' .` | **Ist-Ausgabe** (17.10. vorab: leer → Gate ist kein Dienstbestandteil) |
| 09:50 | Preflight **manuell** aufrufen | `current:`/`historical:` vom Werkzeug, nicht vom Dienst |
| 10:00 | Zeilen 0–8 | `Tuesday`, `168 passed`, `historical: RED`, Wurzel leer |
| 10:05 | Basis-Zeile | Code je Run, nicht nur Run-Nummern |

**Neustart: entfällt** — solange der Runner-Diff leer bleibt. Der Befund vom
17.10. lautet: Runner byte-identisch, Gate nicht im Ladepfad. Die beiden
Abfragen bleiben trotzdem im Protokoll, weil sie die einzigen sind, die den
Abnahmegegenstand vom Etikett trennen. Fällt der Diff am 20.10. **nicht** leer
aus, ist ein Neustart Vorbedingung und der Termin verschiebt sich — nicht die
Messung, sondern das Urteil.

**Die zwei Verdikte kommen aus einem manuellen Aufruf.** Das ist die
Konstruktion (Daten durch Dienst, Urteil post hoc), aber es heißt: der Beleg
ist eine vorzeigbare Terminalausgabe, kein Logauszug des Dienstes.

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

## 5. Dienst vs. Abnahmegegenstand — die Grenze vor den Einzelprüfungen

**Der Abnahmegegenstand ist ein Werkzeug. `preflight_check.py` ist kein
Dienstbestandteil.** Die Plist `com.agentx.shadow-runner.plist` startet
ausschließlich `-m order_execution_engine.shadow_runner`; `rg preflight_check`
über das Repo ohne Tests/Doku liefert 0 Treffer.

Daraus folgt für die folgenden Abschnitte:

| Abschnitt | prüft | Gegenstand |
|---|---|---|
| §5.1 `lstart`, `runs=1` | den Dienst | **Runner** |
| §5.2 `git status --porcelain` | den Tree | **beide** (Werkzeug + Dienst) |
| §5.4 mtime-Sweep | geladenen Code | **Runner** |
| §5.4b Objekt-Hash | geladenen Code | **Runner** |
| §5.4c Aufrufer-Suche | ob es einen gibt | **Werkzeug** |
| §5.3 `gate:`-Hash | die urteilende Fassung | **Werkzeug** |

**§5.1, §5.4 und §5.4b sind Beweise über den Dienst, nicht über das Gate.**
Sie stehen hier, weil eine Abnahme ohne intakten Datenlieferanten (Run 8/9)
nicht beurteilbar wäre — aber sie zertifizieren nicht den Prüfer. Wer am
20.10. 168 Tests, leere Wurzel und unveränderten Prozess liest und sie für
Beweise über das Gate hält, liest drei grüne Prüfungen am falschen Ziel.
Das ist die schlechteste Variante und deshalb steht die Grenze hier oben und
nicht in einer Fußnote.

### 5.0 Vorbedingung mit Eigentümer (nicht mit Docs erledigt)


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

**Laufzeit — Ist-Ausgabe, nicht abgeschrieben** (17.10.2026, 17:36:05):

```
$ ps -o pid=,lstart=,etime= -p 962
  962 Wed Oct 14 21:23:32 2026     02-20:12:33
```

Das Format `02-20:12:33` ist `[[DD-]hh:]mm:ss`; ausgeschrieben „2 Tage 20
Stunden 12 Minuten 33 Sekunden". **Jede Fassung dieses Dokuments, die hier
„2 d 20 h" o. Ä. schreibt, ist falsch** — nicht weil die Größenordnung
danebenläge, sondern weil `etime` monoton ist und zwei verschiedene Zeitpunkte
keine gleiche Laufzeit haben können. Die Zahl wächst mit jeder Minute, in der
dieses Dokument liegt; nur die Ausgabe des Befehls ist wahr, und sie ist mit
Zeitstempel zu zitieren.

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

### 5.3 Zwei Verdikte statt eines

Ein dauerhaft roter abgeschlossener Lauf macht das Gate zur Tapete: rot, das
erwartet ist, wird nach zwei Wochen nicht mehr gelesen. Die Ausgabe führt
deshalb zwei Verdikte:

```
gate:               <blob>  (git hash-object)
verdict current:    GREEN  (letzter Lauf)
verdict historical: RED (run 8, unattributed=4)  (abgeschlossen, dokumentiert)
blocking:           kein Aufrufer verdrahtet — wer diesen Befehl startet,
                    blockiert; das Urteil selbst bricht nichts ab
```

`current` landet bei RED in `errors`, `historical` wird als `WARN`
protokolliert. **Die Trennung schluckt nichts:** ist der *jüngste* Lauf rot,
ist `current: RED` — Zeuge `test_current_red_still_blocks`. Der zweite Zeuge
(`test_historical_red_does_not_block_current_green`) hält fest, dass Run 8
dokumentiert erscheint.

> **Korrektur 17.10. 18:22 — dieser Absatz stimmte erst seit 18:20.**
> Bis `146b4be4` (17.10., 17:21) gab es **kein** `current`: der Prüfer schrieb
> jeden RED-Befund unbedingt via `_fail` in `errors` (Zeuge:
> `9556b1d7:preflight_check.py`, 04.10.). `146b4be4` führte `current` ein —
> und setzte es auf das **Literal** `"GREEN"`:
>
> ```python
> return {"current": "GREEN", "historical": historical}   # 146b4be4
> ```
>
> Von 17:21 bis 18:20 konnte das Gate deshalb **nicht rot werden**: jeder
> rote Befund wurde über `historical = current == "GREEN"` zur Warnung
> degradiert. Der Satz oben („schluckt nichts") war in diesem Fenster falsch.
> Seit `162a89e7` wird `current` gemessen.
>
> **Der Vorfall, mit dem diese Akte beginnt, wurde also nicht von diesem
> Code geschrieben** — jedenfalls nicht von der Fassung mit dem Literal.
> Die Ursprungsfassung (04.10.) schrieb ihn korrekt; ein zweiter Schreiber
> in `errors` hat nie existiert. Die Frage „wer schrieb `current: RED`"
> beantwortet sich damit: **niemand schrieb das Etikett — geschrieben wurde
> der Befund, und das Etikett kam erst später und hat ihn dann verschluckt.**

> **Abnahme-Folge:** es gibt **kein archiviertes Urteil** dieses Werkzeugs.
> Alle `GREEN`, die zwischen 17:21 und 18:20 gedruckt wurden, waren eine
> Konstante. Das erste echte Verdikt ist das über Run 9, gefällt seit
> `162a89e7` — datiert in §5.4m.

> **Korrektur: „blockierend" ist keine Eigenschaft des Verdikts, sondern des
> Aufrufers.** Der Prüfer ist ein Werkzeug — er setzt seinen Exit-Code, wenn
> jemand ihn startet. Es gibt **keinen verdrahteten Aufrufer** (kein
> launchd-Job, kein Hook; `rg preflight_check` ohne Tests/Doku = 0 Treffer).
> Bei `current: RED` bricht nichts von selbst ab. Das Wort stand im Output,
> ohne dass irgendwo etwas abbrechen konnte — **ein Gegenstand ohne
> Referenten**, die vierte Form in dieser Akte. Behoben ist es, sobald
> dasteht, wer blockiert: am 20.10. um 10:00 ist das der Mensch, der
> Zeile 0–6 abhakt.
>
> **Verdrahtung nicht vor dem 20.10.** Ein launchd-Job mit Exit ≠ 0 bei RED
> macht aus dem Beobachter ein Teilsystem mit eigener Ausfallart: ein
> falsches RED hält dann den Betrieb an, und ein veralteter Prüfer blockiert
> wegen eines längst behobenen Fehlers. Wenn, dann mit der Ausfallart im
> Text — und mit `gate:`-Hash im Log, damit ein Block den Richter nennt.

**Der Prüfer datiert sich selbst.** Jede Ausgabe trägt den Blob-Hash der
urteilenden Fassung (`git hash-object`, 40 Hex SHA-1 — derselbe Wert wie in
`git rev-parse <commit>:<path>`). Ein Verdikt ohne Prüfer-Hash nennt den Run,
aber nicht den Richter: derselbe Befehl auf denselben Daten könnte nach dem
nächsten Werkzeug-Commit anders lauten, und das Protokoll merkt es nicht.
Ohne git fällt die Zeile auf SHA-256 zurück und **sagt das**
(`sha256 (git unavailable)`), statt eine falsche Form vorzutäuschen.

**Zwei Adressen, ein Auflöser.** Das Dokument nennt den **Commit**, das
Werkzeug nennt den **Blob**, `git rev-parse <commit>:<path>` löst den Commit
in den Blob auf:

```
git rev-parse <commit>:order_execution_engine/ops/preflight_check.py
  → muß dem `gate:`-Wert der vorgelegten Ausgabe entsprechen
```

**Das Dokument sagt nie „aktueller Prüfer", immer „Prüfer des gezeigten
Laufs".** Ein `Stand` ist per Definition historisch: der Kommentar, der vor
dem Eintippen des Hashs warnt, hat den Hash selbst verändert — der Satz, der
vor dem Fehler warnt, ist das Beispiel für den Fehler. Wer den Prüfer als
„aktuell" zitiert, zitiert beim nächsten Commit eine Fassung, die die
gezeigten Zahlen nicht gerechnet hat.

Der umgekehrte Weg (Blob → Commit) ist nicht eindeutig. Deshalb steht in der
Basis-Zeile kein Blob, sondern der Commit des Laufs, dessen Ausgabe vorgelegt
wird — und diese Ausgabe trägt ihren eigenen Blob. Wer beides nebeneinander
hält und `rev-parse` laufen lässt, hat die Probe, die das Dokument nicht
leisten kann: **eine Wahrheit, zwei Adressen, ein Auflöser.** Ohne den
Auflöser müßte das Dokument bei jedem Werkzeug-Commit nachgezogen werden —
und genau dieses Nachziehen ist in sechs Runden fünfmal schiefgegangen.

### 5.4 mtime-Sweep — der Beweis für „Basis Run 8+9"

`sha256(Datei) == HEAD` belegt den Tree von **heute**, nicht den von
`14.10. 21:23:32`. Zwischen beiden liegt genau das Fenster, in dem
`integrate_news_index` im Tree gestanden haben könnte; `lsof` hilft nicht, weil
es offene Dateien zählt, nicht geladene Module. Die Lücke schließt allein der
mtime-Sweep:

> **Korrektur (§5.4b):** Der richtige Referent ist nicht `HEAD`, sondern
> `5c5bc364`. Der Satz oben muss heißen: „`sha256` **gegen `5c5bc364`**
> belegt den Tree von damals, nicht den von heute." Gegen HEAD gemessen
> beantwortet der Vergleich die falsche Frage.

```
find order_execution_engine -name '*.py' -newermt '2026-10-14 21:23:32'
```

**Der Threshold ist der Prozeszeuge — nicht ein Datum der Akte.** Er muß
denselben Jahrgang tragen wie `ps -o lstart= -p 962` (`Wed Oct 14 21:23:32
2026`). Die Gegenprobe gehört dazu, weil ein zu weites Fenster mehr fängt
und damit *nicht* widerlegt, was es prüfen soll:

```
find … -newermt '2026-10-14 21:23:32'  →  4 Treffer   (Prozessstart 2026)
find … -newermt '2025-10-14 21:23:32'  → 26 Treffer   (Fenster ein Jahr zu weit)
```

Die 26 wären **kein** Befund über den geladenen Code — sie sind der Beweis,
daß das Fenster den Start nicht beschreibt. Nur die 4 sind die Messung.

**Ausgabe 17.10.2026 — nicht leer. Vier Treffer, einzeln verhandelt:**

| Treffer | mtime | Befund | Tragweite |
|---|---|---|---|
| `shadow_runner.py` | 17.10. 16:50:15 | Inhalt **== HEAD** (`git diff --quiet` → 0), shasum `1a71c15f…ac4` beidseitig | nur mtime berührt (Datei wurde gelesen und neu geschrieben; `atime` 16:50:16). Kein Ladepfad: Prozess lief seit 14.10. |
| `ops/preflight_check.py` | 17.10. 17:20:31 | in `146b4be4` committet | nicht vom Runner geladen (kein Import im Runner) |
| `tests/test_telemetry_reconciliation.py` | 17.10. 17:20:52 | in `146b4be4` committet | nicht geladen |
| `tests/test_fill_replay.py` | 17.10. 16:49:59 | in `01fdbb1d` committet | nicht geladen |

**Bewertung:** Kein Treffer liegt im Fenster zwischen Start (14.10. 21:23:32)
und dem ersten heutigen Schreibvorgang (17.10. 16:49). Kein Treffer ist
Runner-Code im Ladepfad. `shadow_runner.py` ist inhaltlich unverändert —
byte-gleich HEAD.

**Grenze dieser Auskunft:** mtime ist ein Metadatum, das sich setzen lässt;
sie ist ein Zeuge, kein Beweis im mathematischen Sinn. Sie schließt die Lücke
für den Fall „jemand hat eine Datei geändert und gelassen" — nicht für
„jemand hat eine Datei geändert, geladen und die mtime zurückgesetzt". Für
Letzteres gibt es keinen Beleg, und es gibt auch kein Indiz dafür.

### 5.4a Label vs. Prozess — Import-Graph-Abfrage

**Das Label beschreibt den Tree, gelaufen ist das Gedächtnis.** `git_commit_short()`
liest HEAD; der Prozess hat seine Module am 14.10. 21:23:32 geladen. Zwischen
beidem liegen die vier Schreibvorgänge vom 17.10. (16:49–17:20). Ob das
deckungsgleich ist, entscheidet allein der Import-Graph:

```
rg -n "preflight_check|test_fill_replay|test_telemetry_reconciliation" \
   order_execution_engine --glob '!tests/**'
```

**Ausgabe (17.10.2026, 17:27) — kein einziger Treffer im Ladepfad:**

| Treffer | Datei | Art |
|---|---|---|
| `TAG7_ABNAHME.md:53, 243–245, 336–337` | Doku | Text, kein Import |
| `START.md:59, 90, 111` | Doku | Aufrufzeile, kein Import |
| `tests/test_telemetry_reconciliation.py:12` | Test | `from …preflight_check import …` |

`shadow_runner.py` importiert ausschließlich
`allowlist_freeze`, `fill_simulator`, `hub_wiring`, `market_data_feed`,
`models`, `news_bridge`, `persistence`, `shadow_execution_engine` —
**keine** der vier berührten Dateien.

**Ergebnis: Label und Prozess sind deckungsgleich.** Der laufende Code ist
`5c5bc364`, und der Tree an diesem Datum ist ebenfalls `5c5bc364`. Kein
Neustart nötig, keine Neumessung.

**Grenze:** Die Abfrage ist statisch. Ein dynamischer Import (`importlib`,
`__import__`) wäre unsichtbar — im Runner gibt es keinen; das ist gelesen,
nicht gesucht.

### 5.4d Die Bytecode-Frage — welches Glied fehlte

Die Kette lautet: *Blob der `.py` == Blob in `5c5bc364` ⇒ geladener Code ==
`5c5bc364`*. **Geladen wird aber Bytecode**, und CPython entscheidet über
`(mtime, size)` der Quelle, nicht über ihren Inhalt. Eine Bearbeitung, die
mtime und Größe erhält, bliebe unsichtbar. Das war der eine Zeuge, den diese
Akte nicht hatte.

**Erster Befund: `git status --ignored` war nie gelaufen.** Die „0 Zeilen"
aus Runde 1 stammten ohne `--ignored`; mit `--ignored` sind es **11 Zeilen**.
Und `__pycache__` existiert:

```
find order_execution_engine -name '*.pyc' | wc -l   → 44
git status --porcelain --ignored order_execution_engine | wc -l → 11
```

**Zweiter Befund: Bytecode ist nicht abgeschaltet.**

```
ps -ww -o command= -p 962   → kein -B
plist                       → kein PYTHONDONTWRITEBYTECODE
```

**Dritter Befund: der pyc ist mtime-basiert, nicht inhaltlich geprüft.**

```
shadow_runner.cpython-314.pyc   header flags = 0x00000000
pyc speichert (mtime=1792248615, size=16358)
Quelle jetzt  (mtime=1792248615, size=16358)   → CPython würde laden: True
```

`True` heißt hier nur **„mtime und Größe passen"**. Es heißt nicht „der Code
ist derselbe". Die Probe, die das entscheidet, wurde deshalb nachgezogen —
Vergleich der Code-Objekte (`co_code`, `co_consts`, Namen je Funktion)
zwischen dem gespeicherten `pyc` und frisch kompiliertem Quelltext aus
`5c5bc364`:

| Modul im Ladepfad | pyc == kompiliert | pyc == `5c5bc364` |
|---|---|---|
| `shadow_runner` (32 Codes) | ✅ | ✅ |
| `shadow_execution_engine` (124) | ✅ | ✅ |
| `fill_simulator` (38) | ✅ | ✅ |
| `hub_wiring` (17) | ✅ | ✅ |
| `market_data_feed` (47) | ✅ | ✅ |
| `models` (69) | ✅ | ✅ |
| `news_bridge` (49) | ✅ | ✅ |
| `persistence` (79) | ✅ | ✅ |
| `allowlist_freeze` (12) | ✅ | ✅ |

**Die Kette ist damit inhaltlich geschlossen, nicht über mtime.** Der
laufende Bytecode ist der von `5c5bc364` — geprüft am Code-Objekt, nicht am
Zeitstempel.

> Ein Zwischenschritt war falsch und bleibt hier stehen: der erste Vergleich
> (`marshal.dumps` der Objekte) meldete **neunmal `False`**. Das war ein
> Artefakt des Marshalling (Adressen, Docstring-Objekte), kein Befund —
> auffällig war, daß **alle** Module abwichen, was bei echtem Drift
> unwahrscheinlich ist. Uniforme Abweichung ist ein Werkzeugfehler, keine
> Messung.

**Warum kein `-B` gesetzt wird:** Das ändert die Startzeile und verlangt einen
Neustart — und ein Neustart aus diesem Anlaß ist der Neustart aus falschem
Anlaß. Der Befund genügt; die Plist bleibt unberührt. Für die Zukunft wäre
`PYTHONDONTWRITEBYTECODE=1` in der Plist die ehrlichere Konfiguration (kein
Bytecode, kein Cache, keine Frage) — **nach** dem 20.10.

### 5.4e Das Kriterium — „GREEN" trägt jetzt seinen Maßstab

Ein Verdikt ohne Kriterium ist ein Etikett für eine Prüfung, die anders
hieß. Die Schwelle ist der **einzige** Teil dieser Akte, der sich nachträglich
ändern läßt, ohne daß es auffällt: von `unattributed == 0` auf `== 1` gesetzt,
wäre jedes archivierte RED nachträglich ein GRÜN — und der `Stand`-Hash zeigt
auf ein Werkzeug, das die alte Schwelle nicht mehr enthält. Der datierte
Richter datiert den **Code**, nicht die **Regel**.

Deshalb gibt das Werkzeug seine Regel selbst aus:

```
criterion: GREEN nur wenn (0) telemetry_rows >= 4 (Untergrenze aus Run 9)
           (1) telemetry_rows == decision_seq-keyed
           (2) keyed == distinct(run_id, decision_seq) und je run eindeutig
           (3) unattributed == 0
           (4) dispatched_success == Σ reject_reasons
           scope = run_id >= 8
```

Die Bedingungen sind `_gate_criterion` und spiegeln die `RED`-Rückgaben
von `gate_telemetry_reconciliation` in derselben Reihenfolge.

> **Der Docstring sagte, ein Test könne diese Kongruenz nicht prüfen.**
> Das war falsch — und der Satz war die Erlaubnis, vier Kopien zu behalten.
> Sechs Zeugen prüfen die Kopplung jetzt (`test_criterion_*`,
> `test_branch_0…4`). Wird ein fünfter Zweig eingefügt, bricht der Test an
> der Stelle, an der die Zeile nicht mitwächst.

> **Erster Anlauf, ehrlich nachgetragen:** Die vier Fixtures prüfen, daß
> jeder **existierende** Zweig rot wird. Sie prüfen **nicht**, daß kein
> weiterer dazukommt — Probe: ein fünfter `return GateResult(RED)` ohne
> `criterion`-Ergänzung eingefügt → **20 passed**. Der Test war grün, wo er
> brechen sollte. Ergänzt wurde `test_criterion_count_matches_red_branches_in_source`,
> das die RED-Rückgaben im Quelltext zählt und mit der Anzahl der
> Bedingungen in der gedruckten Zeile vergleicht. Zweite Probe: 5 Zweige →
> 21 passed, 6 Zweige → **Bruch**. Erst dieser Befund macht den Satz oben
> wahr.

**Bedingung (0): die Untergrenze — ohne sie ist das Gate eine Tautologie.**

Bei einem leeren Lauf sind (1)–(4) sämtlich erfüllt: `0 == 0`, `0 == 0`,
Nichtexistenz über einer leeren Menge, `0 == 0`. **Ein stiller Ausfall liest
sich dann als GREEN** — und „nichts da" ist genau der Zustand, in dem man
wissen will, ob der Dienst arbeitet.

Die Untergrenze stammt aus dem dokumentierten Lauf, nicht aus der Absicht:

```
run 8: 30 Zeilen / 30 decisions
run 9:  4 Zeilen /  4 decisions   (started_at 2026-10-14T19:23:36)
→ MIN_TELEMETRY_ROWS = 4
```

Die Zahl steht im **selben Blob** wie das Kriterium, das sie verwendet —
das ist die Bedingung dafür, daß sie keine nachträgliche Anpassung ist.
Stünde sie in einem späteren Commit, wäre sie eine Schwelle, die sich der
Messung angepaßt hat.

> **Nebenbefund beim Einbau:** `test_gate_green_when_idle` hieß so und
> erwartete `GREEN` mit der Begründung „nicht unterscheidbar von
> Inaktivität — erwartet". **Der Test kodifizierte die Tautologie als
> Erwartung.** Er heißt jetzt `test_gate_red_when_idle_underrun` und erwartet
> `RED` mit `underrun: True`.

**Die drei angehobenen Bestandstests — und ihre Prüfung von beiden Seiten.**

Drei Bestandstests wurden auf `MIN_TELEMETRY_ROWS` Zeilen angehoben, weil
sie die Gleichheitslogik prüfen und sonst am falschen Zweig gebrochen wären.
Das ist strukturell dasselbe wie „die Schwelle an die Daten anpassen" —
deshalb die Gegenprobe:

```
Untergrenze auf 5 gesetzt, Cache geleert:
  21 passed (vor dem Beidseiten-Test)   →  die Tests folgen der Schwelle
```

**Sie prüften die Untergrenze nicht, sie lasen `MIN_TELEMETRY_ROWS`.** Bei
jeder Schwelle grün — derselbe Fehler wie `test_gate_green_when_idle`, nur
an einer Stelle, an der niemand mehr hinsieht. Ergänzt:

```python
PINNED_MIN_TELEMETRY_ROWS = 4      # Literal, nicht die Konstante
test_threshold_constant_is_the_pinned_value   # Schwelle == gepinnte Zahl
test_threshold_exact_boundary_is_green        # n = 4  -> LEDGER_CONSISTENT
test_threshold_one_below_is_red_underrun      # n = 3  -> RED/underrun
```

Gegenprobe mit geleertem `__pycache__`:

| Schwelle | Ergebnis |
|---|---|
| 3 | `one_below_is_red_underrun` **bricht** (erwartet rot, Gate grün) |
| 4 | 168 passed |
| 5 | `exact_boundary_is_green` **bricht** (erwartet grün, Gate rot) |

> **Nebenbefund:** Der erste Lauf dieser Probe war bei 3 und 5 grün — weil
> pytest ein veraltetes `.pyc` las. Erst `__pycache__` leeren ließ die Probe
> greifen. **Derselbe mtime-blind Bytecode, der in §5.4d das Thema war,
> hat hier die Messung verfälscht.** Das ist der stärkste Beleg für den
> `checked-hash`-Nachtrag, den diese Akte hat.

### 5.4g `GREEN` heißt jetzt `LEDGER_CONSISTENT` — und `delivered` steht daneben

**Die Frage, die diese Sektion erzwingt: was prüft Bedingung (4) auf Run 9?**

```
run 9:  telemetry_rows = 4    reasons = {INVALID_PRICE: 4}
        dispatched_success = 4 (Zeilen in dispatched_signals ab started_at,
                               nicht in bridge_discards)
        delivered = 0          (approved = 1 in keiner Zeile)
        (4) 4 == 4             → erfüllt
```

**`dispatched_success` zählt Angebote an die Bridge, nicht Auslieferungen.**
Der Name trägt „success"; der Wert zählt Zeilen. Auf Run 9 besteht das Gate
alle Bedingungen über einem Lauf, in dem **nichts gefüllt wurde** — vier
Zeilen, vier `INVALID_PRICE`, null Lieferungen.

Die drei Lesungen, geprüft:

| Lesung von (4) | Run 9 | Urteil |
|---|---|---|
| `approved`-Zeilen == `Σ reasons` | `0 == 4` | hätte Run 9 rot gemacht — er war grün, Also nicht die Lesung |
| `dispatched` (Fenster) == `Σ reasons` | `4 == 4` | **ist die Lesung** — Ledger-Identität, keine Funktionsaussage |
| „Erfolg" = Auslieferung | `0` | nicht gemessen, bis jetzt |

**Entscheidung: Etikett ändern, nicht Bedingung hinzufügen.** `GREEN`
verspricht Funktion; vier Identitäten über einer Menge können nur
Konsistenz belegen. Also:

```
GREEN            → LEDGER_CONSISTENT
RED              → RED (unverändert: rot bleibt rot)
detail["delivered"]                      neu, gemessen (approved = 1)
criterion (5)    WARNUNG, kein Blocker: delivered == 0
```

`delivered = 0` ist **keine** Gate-Bedingung. Begründung: am 20.10. soll
nichts rot werden, weil das Gate zum ersten Mal etwas gemessen hat — die
Entscheidung, ob ein Lauf ohne Auslieferung die Abnahme sperrt, gehört
vor die Abnahme und nicht in ein Werkzeug, das sie nachträglich kippt.
`criterion:` druckt die Warnung mit, damit sie nicht übersehen wird.

> **Der Etikett-Tausch ist die zehnte Form dieser Akte:** ein Etikett, das
> mehr verspricht als sein Referent. Der Unterschied zu den neun davor:
> diesmal steht der Referent daneben, in fünf Zeilen, und sagt es selbst.

#### 5.4h Der Befund hinter dem Befund — zwei Stellen lasen ihren eigenen Ausgang

Beim Umbau gefunden, nicht gesucht:

```python
# vorher, an zwei Stellen:
historical = snapshot["verdicts"]["current"] == "GREEN"
...
if snapshot["verdicts"]["current"] == "GREEN":
    _warn(...)          # statt _fail(...)
```

**`verdicts["current"]` war ein Literal.** Der Docstring sagt „current
(letzter Lauf)", der Code hat den letzten Lauf nie angesehen:

```python
return {"current": "GREEN", "historical": historical}   # vorher
```

Damit degradierte **jeder** rote Befund zur Warnung — die Blockade konnte
strukturell nie greifen. Nach dem Umbau auf eine gemessene `current`:

```
Aufruf mit min_run_id=8, Run 9 kaputt:
  vorher:  current=GREEN  errors=[]            (nichts blockiert)
  nachher: current=RED    errors=["latest run 9: RED (blockierend)"]
```

Zweiter Teil des Befunds: `recon` mißt **nur** `min_run_id`. Ein Aufruf mit
einer alten `min_run_id` sah den jüngsten Lauf nie als blockierend. Ergänzt
ist ein eigener Zweig für den jüngsten Lauf; Zeugen:
`test_latest_run_failure_blocks_even_when_called_with_old_min_run_id`
(beide Seiten: kaputt → blockiert, intakt → nicht).

### 5.4k `delivered` braucht einen Referenten — sonst ist die Warnung keine

`delivered = 0` neben einem Urteil ist die Ursprungsform dieser Akte: eine
Zahl ohne Bezugszeit. Der Unterschied, der alles entscheidet, ist die
**Dauer** — `0` in der letzten Minute ist ein Nicht-Ereignis, `0` seit
Tagen ist der Befund.

`telemetry` hat **keine Zeitspalte**, und `dispatched_signals.telemetry_seq`
ist NULL in allen 360 Zeilen (offener Punkt §6). Eine Punktzeit ist also
nicht ermittelbar. Deshalb druckt die Ausgabe die Herkunft statt einer
erfundenen Zeit:

```
delivered:          0 — unverändert seit ≤ 2026-10-04 11:12:39
                    (letzte approved=1 in run 8, seq 12;
                     außerhalb des Beobachtungsfensters)
```

Die Zeit ist eine **Obergrenze**: `telemetry_runs.started_at` des Laufs, der
die letzte genehmigte Zeile trägt. Das `≤` ist Absicht — eine Lieferung lag
irgendwann in diesem Lauf, nicht zu seinem Beginn.

**Der Nullpunkt liegt vor dem Zeugen.** Erste Zeile der Tabelle:
04.10. 08:00:08. Letzter Erfolg: 04.10. 11:12:39 (`run 8`, `seq 12`,
`PARTIALLY_FILLED`). Der Erfolg liegt **innerhalb** der Tabelle, nicht an
ihrem Anfang — es ist also ein echter Nullpunkt und kein Tabellenanfang:

> „kein Erfolg verzeichnet" wäre falsch. Ein Erfolg ist verzeichnet — nur
> liegt er 10,4 Tage vor dem Fenster, das der laufende Runner beobachtet.
> **Run 9 hat nie einen Erfolg gesehen und nie einen Mißerfolg der
> Auslieferung.** Die Null ist im Fenster nicht gemessen, sondern geerbt.

Ist gar keine Lieferung vorhanden, lautet die Ausgabe
`kein Zeitstempel — nicht ermittelbar (nie delivered > 0)`.

### 5.4l `-B` beim Testlauf kostet nichts — und deshalb steht es da

`PYTHONDONTWRITEBYTECODE` beim *Dienst* verlangt einen Neustart aus falschem
Anlaß und ist nach der Abnahme gebucht. Beim *Testlauf* verlangt es nichts.
Solange es nicht in der Invokation steht, fälscht jeder zweite Lauf seine
eigene Probe — und zwar **grün**, die einzige Richtung, die niemandem
auffällt.

`order_execution_engine/run_tests.py` trägt die Regel:

```python
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True        # wirkt auch im laufenden Interpreter
sys.path.insert(0, repo_root)         # unabhängig vom Startverzeichnis
os.chdir(repo_root)                   # Tests lesen Quellen relativ
pytest.main([tests, "-q", "-p", "no:cacheprovider"])
```

`-p no:cacheprovider` zusätzlich: `lastfailed` überlebt sonst eine
Schwellenänderung und ändert, welche Tests laufen. `sys.path` und `chdir`
kamen beim ersten Lauf aus `/tmp` hinzu — vorher hing das Ergebnis davon ab,
**wer** den Test startet. Dieselbe Form von Abhängigkeit wie `etime` und
`pyc`.

**Die 170 — vor oder nach dem Leeren von `__pycache__`?** Beides:

| Lauf | Ergebnis |
|---|---|
| mit vorhandenem Cache (der damalige Commit-Lauf) | 168 passed |
| `PYTHONDONTWRITEBYTECODE=1`, Cache vorhanden | 168 passed |
| Cache geleert, `PYTHONDONTWRITEBYTECODE=1` | 168 passed |
| nach 5.4k–5.4n, `run_tests.py`, Cache geleert, aus `/tmp` | **170 passed** |

Die 168 sind cache-unabhängig. **Aber das war Glück, kein Verfahren** —
der Schwellen-Probe-Lauf davor war bei 3 und 5 grün, bis der Cache weg war.

### 5.4m Das erste echte Verdikt — Run 9, datiert, mit Nenner

Es gibt kein archiviertes Urteil dieses Werkzeugs: im Fenster 17:21–18:20
war `current` eine Konstante. Das erste Urteil, das eine Messung trägt, ist
das über **Run 9**.

```
Gate:       162a89e7 (LEDGER_CONSISTENT, current gemessen)
Run 9:      started_at 2026-10-14 21:23:36  commit 5c5bc364
Runner:     PID 962, lstart Wed Oct 14 21:23:32 2026
Konfig:     diagnostic_only=true, live_execution=false
Fenster:    69,1 h (2,88 d) bis 17.10. 18:25
```

```
verdict:    LEDGER_CONSISTENT (4 Zeilen, 0 Auslieferungen)
observed:   69,1 h — eine Zeile alle 17,3 h; erwartet: unbekannt
dispatched_signals im Fenster      60
  davon verworfen (bridge_discards) 56
    mapping_miss                    33
    no_book                         23
    empty_list                      17   (Überschneidung: mehrere Gründe je Item)
  dispatched_success                 4
telemetry_rows                       4
unattributed                         0
reasons            {INVALID_PRICE: 4}
delivered                            0   seit ≤ 04.10. 11:12 (außerhalb)
```

**Was `LEDGER_CONSISTENT` belegt und was nicht:**

| belegt | nicht belegt |
|---|---|
| die vier Zeilen sind vollständig, eindeutig, attribuiert, bilanzieren | Erreichbarkeit des Dienstes |
| | Verarbeitung jenseits des Ledgers |
| | daß je etwas ausgeliefert wurde |
| | daß die Signalquelle lebt |

Das Urteil ist ein Urteil über **einen Ledger, nicht über einen Dienst**.

### 5.4n `DERIVED` — Definition in einer Zeile

```
DERIVED := git hash-object <datei>  !=  git rev-parse HEAD:<datei>
```

Nicht `git status`. Begründung aus §5.4d: `--porcelain` **ohne** `--ignored`
hätte den `__pycache__` nie gezeigt (die 0 war keine Antwort), und **mit**
`--ignored` feuert es immer, solange ignorierte Artefakte im Tree liegen
(heute: 8). Die Frage ist nicht „ist der Baum sauber", sondern „ist genau
dieser Text committet".

### 5.4o `INVALID_PRICE` ist dreimal dasselbe Wort für drei Ursachen

Das `SELECT` auf die vier Zeilen ist der billigste Schritt dieser Runde — und
der einzige, der nicht das Gate betrifft, sondern das, was es beobachtet.

Die vier Zeilen tragen: `order_id = NULL`, `requested_size = NULL`,
`status = NULL`, `latency_ms` zwischen 0,0046 und 0,0167 (echte ms),
`approved = 0`. Es wurde also **nie eine Order gebaut** — die Entscheidung
fiel davor. (Zum Vergleich: die einzige `approved = 1`-Zeile aus `run 8` hat
`requested_size = 100`, `status = PARTIALLY_FILLED`, `latency_ms = 0,48`.)

Im Validator (`shadow_execution_engine.py`) führen **drei** verschiedene
Bedingungen zum selben Etikett:

| Zeile | Bedingung | Bedeutung | Etikett richtig? |
|---|---|---|---|
| 1160 | `side is None` (`Direction.NEUTRAL`) | kein BUY/SELL ableitbar — **das Signal ist unbrauchbar, kein Preis im Spiel** | **nein** |
| 1175 | Snapshot fehlt oder `token_id` ≠ Signal | **kein Marktbild** — es gab keinen Preis zu prüfen | **nein** |
| 1187 | `best_ask()` / `best_bid()` ist `None` | Buch vorhanden, aber **eine Seite leer** | ja |

Zwei von drei Fällen tragen einen Namen, der die Ursache verschweigt:
`INVALID_PRICE` behauptet, es habe einen Preis gegeben und der sei falsch
gewesen. Bei `NEUTRAL` und fehlendem Snapshot gab es **keinen**.

> **Ein Validator, der 4/4 mit demselben Grund ablehnt, ist entweder richtig
> (die Quelle ist kaputt) oder falsch (der Validator ist es) — und `INVALID_PRICE`
> unterscheidet die beiden nicht.** Diese Frage ist in elf Runden nicht
> gestellt worden, weil alle elf Runden dem Zeugen galten.

**Nicht entschieden, weil nicht entscheidbar mit den vorhandenen Daten:**
die vier `signal_id`s stehen in **keiner** JSONL — der Signalpfad wird nicht
protokolliert. Welche der drei Bedingungen griff, ist aus der Datenbank allein
**nicht** rekonstruierbar. Vermutbar ist es: `direction = NEUTRAL` entsteht
bei `confidence` unter der Schwelle, und alle vier Zeilen liegen in einem
Fenster, in dem 56 von 60 Dispatches an `no_book`/`mapping_miss` scheiterten —
das spricht für die Quelle, nicht für den Validator. **Vermutung ist aber
kein Befund**, und sie wird hier nicht als einer eingetragen.

**Buchung für den 20.10.:** ein Grund pro Ursache (`NO_SIDE`,
`NO_SNAPSHOT`, `EMPTY_SIDE`) statt eines Sammelnamens. Das ist keine
Verhaltensänderung, nur ein ehrlicherer String — und sie macht die nächste
Frage in einer Zeile beantwortbar.

### 5.4p Zählliste dieser Runde — aus dem Lauf abgeschrieben

Alle vier Zahlen stammen aus **einem** Lauf dieses Baumes, in dieser
Reihenfolge erhoben (Sektionen zuerst, Zahl danach):

```
$ cd /tmp && python3 .../order_execution_engine/run_tests.py
170 passed in 1.19s                     # kein __pycache__ danach: 0 Verzeichnisse

$ python3 order_execution_engine/ops/preflight_check.py --min-run-id 9
verdict:    LEDGER_CONSISTENT (4 Zeilen, 0 Auslieferungen)
observed:   69.1 h (2.88 d) — eine alle 17.3 h; erwartet: unbekannt
delivered:  0 — unverändert seit ≤ 2026-10-04 11:12:39 (...)
gate commit: 653f5bf1:325f71f655ea  DERIVED (Datei != HEAD-Blob)
```

`DERIVED` ist an dieser Stelle **korrekt und gewollt**: der Blob, der die
Zahlen erzeugt, enthält die Sektionen, die sie beschreiben — er ist noch
nicht committet. Nach dem Commit muß dieselbe Zeile `DERIVED` verlieren;
tut sie das nicht, ist der Commit ein anderer Baum.

```
$ python3 .../preflight_check.py --min-run-id 9     # nach dem Commit
gate commit: b69b163b:a77abb536433                   # ohne DERIVED
```

Der Zeuge zitiert sich jetzt selbst: Commit `b69b163b`, Blob `a77abb536433`.

### 5.4q `MIN_TELEMETRY_ROWS = 4` war auf den Filter kalibriert, nicht auf das System

Drei Zahlen, die sich nicht versöhnen ließen — sie versöhnen sich so:

```
telemetry gesamt            34      (run 8: 30, run 9: 4)
dispatched_signals gesamt  360
Run-9-Fenster: 60 Dispatches -> 56 verworfen -> 4 Erfolgs-Dispatches -> 4 Zeilen
```

Das Verhältnis ist **exakt 1 : 1**, in beiden Läufen:

| Lauf | Erfolgs-Dispatches | telemetry-Zeilen |
|---|---|---|
| run 8 | 30 | 30 |
| run 9 | 4 | 4 |

Also: `telemetry_rows` zählt nichts Eigenes — es ist eine Kopie von
`dispatched_success`. Und `MIN_TELEMETRY_ROWS = 4` ist der Wert von Run 9,
also **100 % der überlebenden Teilmenge** dieses einen Laufs.

> **Eine Untergrenze, die genau auf dem beobachteten Wert einer gefilterten
> Menge sitzt, ist auf den Filter kalibriert, nicht auf das System.** Sie
> war fünfzehnfach übererfüllt gegen die Gesamtmenge (34) und exakt erfüllt
> gegen die gefilterte (4). Sie hat nie etwas geprüft, was nicht schon durch
> (1) geprüft war: `telemetry_rows == decision_seq_keyed`.

Die Herkunft ist datierbar — und es war diese Unterhaltung:
`git log -S 'MIN_TELEMETRY_ROWS'` → `e88f6d07`, **17.10. 18:04**, mit dem
Kommentar „Herkunft: Run 9 … hat 4 Zeilen". Der Wert wurde aus dem
Gegenstand abgeleitet, den er prüfen sollte.

**Was in `START.md` steht — und was davon gilt:**

> `TELEMETRY_RECONCILIATION` | GREEN: erfolgreiche Dispatches ≥1 ⇒
> `telemetry_rows >= dispatched_success` (sonst RED: stiller Write-Ausfall)

Das ist die Originalabsicht: eine **Identität**, keine Untergrenze. Sie ist
in Bedingung (1) enthalten. Der eigentliche Zweck war „stiller
Write-Ausfall": wenn die Engine entscheidet und die Zeile nie ankommt.

Und der Tag-1-Gate daneben:

> `no_book` | nahe 0 (2 Freeze-Märkte subscribed); sonst WS

**Run 8: 101. Run 9: 23.** Der Tag-1-Gate ist an der ersten Messung
gescheitert, und niemand hat es notiert. `START.md` selbst nennt in der
Tag-7-Tabelle „1 Dispatch vs. 11 Verwürfe ≈ 8 %" — die Daten von heute
sagen 30 vs. 269. Beide Zahlen sind echt; sie gehören zu verschiedenen
Zeitpunkten, und dazwischen hat niemand nachgesehen.

### 5.4r Um 11:12:39 am 04.10. begann Run 8 — und endete die Auslieferung

Keine Logdatei im Datenverzeichnis (nur `shadow.db` + Tail-Offset; Logs
liegen laut `START.md` unter `~/Library/Logs/agentx-shadow/`). Die
Chronologie kommt deshalb aus der Datenbank:

```
09:03 – 09:06   run 1–7 (Restart-Spam, START.md: ausgeschlossen)
10:00:08        dispatch → unresolved_asset
11:12:39        RUN 8 START          ← und in denselben Sekunden 30 Zeilen
12:00:10        dispatch → no_book
16:00, 17:00    dispatch → mapping_miss
21:00           dispatch → mapping_miss
```

Run 8 begann um **11:12:39** und schrieb **sofort 30 Entscheidungen** —
`decision_seq` 1–30, lückenlos, mit einem Erfolg (`seq 12`,
`PARTIALLY_FILLED`, `requested_size=100`). Danach: nur noch stündliche
Dispatches, **alle verworfen**.

`decision_seq` beginnt in Run 9 wieder bei 1 → Run 9 war ein **echter
Neustart** (PID 962, 14.10. 21:23:32), kein fortgesetzter Prozeß.

> **Der Vorfall hat jetzt eine Uhrzeit.** 04.10. 11:12:39 ist der letzte
> Moment, in dem etwas ausgeliefert wurde. Nicht „ein Dienst, der nichts
> tut" — ein Dienst, der **3 h 12 min nach Tabellenbeginn funktioniert hat
> und dann stehengeblieben ist**. Ein Ausfall mit Uhrzeit ist ein Vorfall;
> einer ohne ist ein Zustand. Diese Akte führte den Zustand seit Runde 1.

**Nicht ermittelbar:** was in den 3 848 Sekunden zwischen 11:12:39 und
12:00:10 passierte. Kein Log, kein WS-Status, kein Deployment-Commit in
diesem Fenster (`git log` 04.10.: letzter Commit 11:11:58 `9556b1d7`, 41 s
vor Run-8-Start — das ist Koinzidenz, nicht Ursache).

### 5.4s Die vier Zeilen sind nicht mehr feststellbar, nicht „unbekannt"

Ihre vier `signal_id`s stehen in **keiner** JSONL — der Signalpfad wird
nicht protokolliert. Welche der drei `INVALID_PRICE`-Ursachen griff, ist
**nicht mehr feststellbar**. Das ist ein Zustand, keine Lücke im Wissen:

> „Grund unbekannt" wäre eine Beschreibung der Akte. „Grund nicht mehr
> feststellbar" ist eine Beschreibung der Daten. Nur die zweite bleibt wahr,
> wenn jemand später nachsieht.

**Der Split ist eine Schemaänderung mit Datenverlust an genau diesen vier
Zeilen.** `NO_SIDE` / `NO_SNAPSHOT` / `EMPTY_SIDE` verkürzt den Sammelnamen
für alles, was *nach* der Umstellung geschrieben wird. Die vier Zeilen aus
Run 9 bleiben `INVALID_PRICE` und erscheinen in jedem Zähler danach als
Rest. Nicht rückdatierbar heißt nicht überschreibbar.

### 5.4t `Σ reject_reasons = 4` ist exakt und sagt nichts

Bedingung (4) prüft `dispatched_success == Σ reject_reasons`. Das ist wahr
und scharf — über einer Taxonomie, die nicht partitioniert: **ein Ledger
ist konsistent über Namen, die verschiedene Dinge bedeuten.** Keine der
fünf Bedingungen verletzt das; keine kann es.

Die Bedingung mißt **Bilanz**, nicht **Bedeutung**. Das war nie ihr Auftrag
— aber es stand auch nirgends, bis jetzt.

### 5.4u Zählliste dieser Runde — aus dem Lauf abgeschrieben

```
$ python3 order_execution_engine/run_tests.py            # aus /tmp
173 passed in 1.19s                                       # 0 __pycache__

$ python3 .../pytest order_execution_engine/tests -q     # direkt, ohne -B
2 failed, 171 passed                                      # beide Hygiene-Zeugen
                                                          # (Starter-Eigenschaft,
                                                          #  nicht Code-Eigenschaft)

$ python3 .../preflight_check.py --min-run-id 9
verdict:    LEDGER_CONSISTENT (4 Zeilen, 0 Auslieferungen)
observed:   69.4 h (2.89 d) — eine alle 17.4 h; erwartet: unbekannt
delivered:  0 — unverändert seit ≤ 2026-10-04 11:12:39 (außerhalb des Fensters)
```

### 5.4v Die Untergrenze ist gestrichen — sie war in beide Richtungen falsch

`MIN_TELEMETRY_ROWS = 4` ist weg. Nicht angepaßt — **gestrichen**, mit Grund:

| Richtung | Verhalten der Untergrenze |
|---|---|
| 1.000 Zeilen, 1 Dispatch | besteht (und sagt nichts) |
| 3 Dispatches, alle ausgeliefert, alle korrekt | **RED** bei erfüllter Identität |

Eine Schwelle, die den oberen Fall durchläßt und den unteren bricht, ist
keine Schwelle. Sie war der Wert von Run 9 — 100 % einer gefilterten Menge.

**Was sie eigentlich tragen sollte, bleibt richtig und ist jetzt eine andere
Bedingung:**

```
rows == dispatched_success   gilt perfekt, wenn beide 0 sind.
```

Ein leerer Dienst hat einen vollständig konsistenten Ledger. Die Antwort
darauf ist keine Zahl, sondern die Frage „hat der Dienst seit seinem Start
überhaupt etwas erzeugt":

```
(0) dispatched_success > 0 oder telemetry_rows > 0
```

das fängt `0 == 0`, erfindet keine Rate und macht den gefrorenen Wert
streichbar. **Der Brichtest ist derselbe, nur ohne Gegenstand**: drei
Bestandstests hingen an der Konstante und wurden zu dem, was sie prüfen
sollten —

| vorher | jetzt |
|---|---|
| `test_threshold_constant_is_the_pinned_value` | `test_fixture_size_is_the_pinned_value` (Aufbau, keine Regel) |
| `test_threshold_exact_boundary_is_green` | `test_three_rows_all_delivered_is_ledger_consistent` — **die Gegenrichtung** |
| `test_threshold_one_below_is_red_underrun` | `test_empty_traffic_is_red_not_ledger_consistent` |

`FIXTURE_ROWS` heißt jetzt, was es ist: wieviele Zeilen die Fixtures bauen.
Ein Name, der nach einer Regel klingt, wird irgendwann als Regel gelesen.

### 5.4w Der Ledger spricht über 6,7 % — und das steht in der Zeile

```
coverage:  4/60 Dispatches = 6.7 % — der Ledger spricht über diesen Ausschnitt
```

Über die ganze Tabelle: `telemetry 34` gegen `dispatched 360` = **9,4 %**.
Die 56 von 60 sind nicht „abgelehnt" — sie haben den Ledger **nie
erreicht**. Damit ist `LEDGER_CONSISTENT` wahr und der Gegenstand der
Abnahme ein Ausschnitt. Das gehört in dieselbe Zeile, nicht in eine Fußnote.

### 5.4x `START.md` gegen den Code — zum ersten Mal gehalten

`START.md` sagte seit 04.10.:

> `TELEMETRY_RECONCILIATION` | GREEN: erfolgreiche Dispatches ≥1 ⇒
> `telemetry_rows >= dispatched_success`

Der Code sagt seit `162a89e7` `LEDGER_CONSISTENT` und seit heute fünf
Bedingungen. **Das Dokument war vor der Sache da und wurde nie diffed.**
Zwölf Runden lang wurde jeder Zeuge gegen seinen Gegenstand gehalten —
Commit, Blob, `etime`, `pyc`, Schwelle — die Spezifikation gegen die
Implementierung nie.

Behoben und bewacht: `test_start_md_gate_line_matches_criterion` liest die
Zeile **aus der Datei** (kein Duplikat im Test) und vergleicht Label und
Bedingungsnummern mit `_gate_criterion()`. Die Tabelle in `START.md` ist
korrigiert. Die Divergenz ist damit nicht „aufgeräumt", sondern prüfbar.

### 5.4y `no_book` 101 → 23 ist ein Verkehrseffekt, kein Fortschritt

| | Dispatches | `no_book` | Anteil |
|---|---|---|---|
| Run 8 | 299 | 101 | **33,8 %** |
| Run 9 | 60 | 23 | **38,3 %** |

Absolut −77 %, anteilig **+4,5 Punkte**. Der Rückgang ist Stillstand: weniger
Verkehr, gleicher Anteil. Der Tag-1-Gate „`no_book` nahe 0" ist an der ersten
Messung gescheitert und danach nicht mehr gemessen worden — **aber er ist
nicht gescheitert, weil er unerreichbar war, sondern weil er kein Prädikat
war.** „nahe" hat keinen Nenner und keine Schwelle. Ein Gate, der nicht in
Zahlen ausgedrückt ist, kann nur durch Nichtlesen bestehen.

### 5.4z Getrennt geschrieben — (1) ist eine echte Prüfung

Die Frage: entstehen `dispatched_signals` und `telemetry` im selben
Schreibvorgang? 30 Zeilen in derselben Sekunde wie `RUN 8 START` legten das
nahe. Dann verglich (1) zwei Variablen aus einer Transaktion und wäre eine
Zusicherung an sich selbst.

`persistence.py`, `SQLiteShadowStorage`:

> „Transaktionsgrenze: ein COMMIT pro geschriebenem Datensatz (Autocommit)."

`write_telemetry` committet **pro Zeile** (`self._conn.commit()` nach dem
INSERT, `telemetry_seq = cur.lastrowid`), `open_run` separat. `log()` in der
Engine schreibt nur in eine In-Memory-Liste; die DB-Zeile entsteht im
Storage-Layer.

**Also: getrennt geschrieben — (1) und (4) sind echte Prüfungen.** Die 30
Zeilen in derselben Sekunde sind kein gemeinsamer Schreibvorgang, sondern 30
Entscheidungen in einem Burst; sie gehen einzeln durch dieselbe Funktion.

### 5.4aa Drei Fehlerbilder, eine Richtung

```
10:00:08  unresolved_asset        Token nicht auflösbar
12:00:10  no_book                 Token aufgelöst, Buch leer
16:00–21:00  unresolved_asset:mapping_miss   Mapping fehlt ganz
```

Das sind keine drei Vorfälle, sondern **eine Richtung**: jede Stufe löst
weniger auf als die vorige. 93 % aller Fehlschläge liegen im
Mapping-Layer (`mapping_miss` 33, `empty_list` 17, `no_book` 23 von 73).
Die 3 848 Sekunden sind nicht ermittelbar — **die Richtung ist es.**

### 5.4ab Zählliste dieser Runde — aus dem Lauf abgeschrieben

```
$ python3 order_execution_engine/run_tests.py            # aus /tmp
175 passed in 1.22s                                       # 0 __pycache__

$ python3 -m pytest .../tests -q -k hygiene              # direkt, ohne -B
2 failed, 173 deselected
E  AssertionError: direkt gestartet (pytest statt run_tests.py):
   PYTHONDONTWRITEBYTECODE ist nicht gesetzt ...

$ python3 .../preflight_check.py --min-run-id 9
verdict:   LEDGER_CONSISTENT (4 Zeilen, 0 Auslieferungen)
coverage:  4/60 Dispatches = 6.7 % — der Ledger spricht über diesen Ausschnitt
observed:  69.5 h (2.90 d) — eine alle 17.4 h; erwartet: unbekannt
delivered: 0 — unverändert seit ≤ 2026-10-04 11:12:39 (außerhalb des Fensters)
```

### 5.4f Eine Kopie, nicht zwei

Der `pyc`-Vergleich aus §5.4d prüft **einen** Pfad. Geladen wird der, den
`sys.path` zuerst findet:

```
find . -name 'shadow_runner*.pyc' -not -path './.git/*'
  → ./order_execution_engine/__pycache__/shadow_runner.cpython-314.pyc
Plist: WorkingDirectory = Repo-Wurzel, PYTHONPATH = Repo-Wurzel
```

**Genau eine Kopie.** Die Frage ist damit geschlossen — und zwar billiger als
über einen Zeugen aus dem laufenden Prozeß.

**Modul-Ebene mitgeprüft (§5.4d, verfeinert):** `co_consts` je Funktion zu
vergleichen übersieht die eine Änderung, die zählt — Schwellen und `scope`
stehen im **Modulkörper**, nicht in einer Funktion. Nachgezogen:

```
9/9 Module: module-level co_code = OK, module-level co_consts = OK
```

**Nachträglich, nicht jetzt:** `--invalidation-mode=checked-hash` (PEP 552,
`flags = 0x1`) schließt die mtime-Lücke dauerhaft. Es verlangt Neukompilat
und Neustart — derselbe falsche Anlaß wie `-B`. **Gebucht, datiert,
liegengelassen.**

> **Nachtrag mit Gewicht:** Die Schwellen-Probe aus §5.4e war bei 3 und 5
> zunächst grün, weil pytest ein veraltetes `.pyc` las. Ein Testlauf, der
> gegen Bytecode von vorgestern mißt, ist genau die Lücke, die `checked-hash`
> schließt — und sie ist in dieser Runde **nicht theoretisch** gewesen.

### 5.4i `etime` in der Kopfzeile — die Zeile, die nicht rückdatierbar ist

§5.1 hat `etime` als stehende Ist-Ausgabe eingeführt, weil sie monoton
wächst: ein Lauf läßt sich nicht nachträglich altern. Sie war zuletzt aus
dem Bericht gefallen. Wieder drin, gemessen im Moment des Aufrufs:

```
Pre-Flight @ /Volumes/.../order_execution_engine
runner etime:        962 Wed Oct 14 21:23:32 2026     02-20:56:00  (gemessen jetzt)
```

Der Hook kann diese Zeile nicht vergessen — die Kopfzeile konnte es.

### 5.4j Blob ↔ Commit — `f86a7901fb5b` gehört zu zwei Commits

Die Selbstauskunft nannte einen Blob und keinen Commit. Nachgezogen:

```
e88f6d07:order_execution_engine/ops/preflight_check.py = f86a7901fb5b
08ad2454:order_execution_engine/ops/preflight_check.py = f86a7901fb5b
```

**`f86a7901` steht in beiden.** Der Prüfer wurde in keinem der beiden
Commits geändert — `08ad2454` trug nur Tests und Dokument. Die Zeile
„identisch in Datei und Commit" war also richtig, aber nur für den Blob,
nicht für einen Commit; das war die alte Form.

Die Ausgabe nennt jetzt beides und markiert die Abweichung:

```
gate:         df1e024fa8146e68c354970a235226e58a2d1943  (git hash-object)
gate commit:  08ad2454:f86a7901fb5b  DERIVED (nicht im HEAD-Commit)
```

`DERIVED` heißt: der laufende Prüfer ist **nicht** der committete. Genau
der Zustand vor dem Abnahme-Commit — und jetzt sichtbar statt behauptet.

### 5.4b Der Referent hat sich bewegt — Korrektur von §5.4a

**§5.4a verglich gegen `HEAD` (= `e91916bd`), geladen wurde am 14.10. aber
`5c5bc364`.** „Inhalt == HEAD" beweist „aktuellster Stand", nicht „geladener
Stand". Die Abfrage mit dem richtigen Referenten (17.10.2026, 17:30):

```
git diff 5c5bc364 e91916bd -- order_execution_engine/shadow_runner.py
  → leer
```

Belegt über Objekt-Hashes statt über die Arbeitsdatei:

| Gegenstand | Wert |
|---|---|
| `5c5bc364:…/shadow_runner.py` | `92338139e8850f05a9a7334e8dc3d4ca599cd874` |
| `e91916bd:…/shadow_runner.py` | `92338139e8850f05a9a7334e8dc3d4ca599cd874` |
| `sha256` Arbeitsdatei | `1a71c15f…ac4` |

**Was sich zwischen `5c5bc364` und `e91916bd` tatsächlich ändert:**

```
ops/TAG7_ABNAHME.md                         | 423 ++++
ops/preflight_check.py                      | 344 +++-
tests/test_fill_replay.py                   | 180 +++
tests/test_telemetry_reconciliation.py      | 245 +++-
```

**Der Prüfer ist neu, die Daten sind alt** — `preflight_check.py`
`af801db1…` → `3dad796a…`. Das ist zulässig (post-hoc-Beurteilung), aber es
muss in der Basis-Zeile stehen, sonst wird Run 9 in drei Wochen für einen
Lauf des neuen Prüfers gehalten.

**Beschriftungsfehler (korrigiert):** In Runde 3 stand „`sha256` Tree == HEAD
(`1a71c15f…ac4`)". Das war ein **Datei**-Hash (`shadow_runner.py`), kein
Tree-Hash. Der Tree-Hash ist `5c5bc364` (die Commit-ID, kein Messwert).
Werkzeug richtig, Etikett falsch — dieselbe Bauform wie `git diff --quiet`
bei untracked Dateien.

### 5.4c Das Gate ist kein Dienstbestandteil

Die Plist `com.agentx.shadow-runner.plist` startet ausschließlich

```
.venv/bin/python3 -u -m order_execution_engine.shadow_runner --data-root … --tail-from-end
```

`rg preflight_check` über das Repo **ohne Tests und ohne Doku**: **null
Treffer**. Es gibt keinen Aufrufer im Betrieb.

| Aussage | Befund |
|---|---|
| Läuft das Gate im Dienst? | **nein, nie** |
| Erzeugt der Dienst `current:`/`historical:`? | **nein** — diese Ausgabe kommt aus einem manuellen Aufruf |
| Neustart nötig, um das Gate zu laden? | **nein** — es ist nicht im Ladepfad |
| Neustart nötig für Run-8/9-Daten? | **nein** — Runner-Code identisch |

**Kein Neustart.** Ein Neustart würde den Runner neu starten, um ein Werkzeug
zu laden, das er nicht lädt — eine Nachbereitung ohne Gegenstand. Ein
Neustart aus falschem Anlass ist derselbe Fehler wie eine Ausnahme ohne Fall.

**Konsequenz für den 20.10.:** Die Trennung *Daten erzeugen* (Dienst) vs.
*Daten beurteilen* (manuell) ist die Konstruktion, nicht ein Mangel. Sie macht
aber den Aufrufer zum Prüfer — genau deshalb steht Zeile 5 im Protokoll und
wird mit vorzeigbarer Ausgabe belegt.

### 5.5 Provenienz-Regel (Korrektur)

Die frühere Formulierung prüfte `git diff --quiet`. Das ist **blind gegenüber
untracked Dateien** — ein Befund aus §5.2. Gültig ist:

```
git status --porcelain   → muß leer sein (oder jede Zeile benannt)
```

Untracked ist dabei kein Sonderfall, sondern die Aussage **„unbekannt"**.
Ein unbenanntes untracked bleibt RED.

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

**Nachtrag: der Überschriften-Check prüft den Stand, nicht die Historie.**
Ein `StrReplace` hatte beim Schreiben eine Überschrift verschluckt; der Check,
der ihn fing, ist jünger als der Fehler. Die Abfrage, die die drei früheren
Commits einschließt:

```
git log -p --follow -- ops/TAG7_ABNAHME.md | rg '^[-+]#{1,4} '
```

**Ausgabe (17.10.2026, 17:27):** genau **eine** Zeile mit `-`:

| entfernt | Gegenstück | bewertet |
|---|---|---|
| `-## 5.3 Zwei Verdikte statt eines` | `+### 5.3 Zwei Verdikte statt eines` | Ebenenwechsel (`##`→`###`), keine Löschung |

Alle übrigen `+`-Zeilen sind Neuzugänge derselben Runde. Keine Überschrift
ist ohne Gegenstück verlorengegangen — die drei früheren Commits haben
nichts stillschweigend gelöscht.

**Grenze:** Die Abfrage zeigt Überschriften, nicht Absätze. Eine gelöschte
Zusage ohne Überschrift (ein Satz in der Mitte) bliebe unsichtbar; dafür
wäre ein zeilenweiser Vergleich nötig, der bei fünf Rewrites nicht mehr
lesbar ist. Er ist nicht geführt — und das ist benannt, nicht behoben.

## 6. `telemetry_seq` — tot, kein Backfill

`dispatched_signals.telemetry_seq` ist zu 0/358 gefüllt. Sie wird **nicht**
nachträglich befüllt: ein Backfill wäre erfundene Provenienz und würde den
einzigen vorhandenen Beweis (den `decision_seq`-Join) scheinbar überflüssig
machen. Die Spalte bleibt als tot dokumentiert.

## 7.1 `scripts/address_register_0r.py` — aus dem Tree heraus (Weg A)

Die Datei stand 17.10. als **untracked** in der Repo-Wurzel (17.425 B,
mtime 10.10. 15:38 — vor dem Run-9-Start, nicht importiert, nicht geladen,
read-only, Kopfzeile „kein Commit").

**Entscheidung: nicht committen, aus dem geladenen Tree heraus.**

| Zustand | Aussage | Rücknehmbar |
|---|---|---|
| untracked | „**unbekannt**" | ja |
| committet | „**zugehörig**" | nein — dauerhaft in der Provenienz |

Committen, damit `untracked: 0` dasteht, wäre die Entscheidung über die Farbe
des Gates statt über die Zugehörigkeit der Datei — der Alarm verschwindet,
weil man seinen Auslöser weggeräumt hat. `.gitignore` ist kein Ersatz: `git diff`
war blind gegen untracked, `gitignore` macht `git status` blind gegen dieselbe
Datei. Dieselbe Blindstelle, eine Ebene höher.

**Ausgeführt:** `mv scripts/address_register_0r.py ~/notes/address_register_0r.py`.
Inhalt und mtime erhalten. `git status --porcelain` in der Wurzel: **leer**.

**Beleg des zitierten Satzes (unabhängig vom Pfad):**

```
sha256  42f29ebe581cfe36bf3d2ac53da9da10607e3dd1006c307a4c0bd6bd821943e3
bytes   17425
mtime   2026-10-10 15:38:18
pfad    ~/notes/address_register_0r.py
```

Der Satz, der hier zitiert wird: *„Ein Alarm wird nicht dadurch quittiert,
dass er sich nicht wiederholt."* Er ist über den Hash belegt, nicht über den
Pfad — die Datei kann verschwinden, das Zitat bleibt prüfbar.

**Weg B entfällt.** Er war eine Alternative für eine Datei **im** Tree; nach
`mv` liegt sie außerhalb. Eine benannte Ausnahme für einen Pfad, der nicht im
Gate-Bereich liegt, ist eine Ausnahme ohne Fall — ein Loch mit unbesetztem
Platzhalter, das wie eine geprüfte Freigabe aussieht. Kommt die Datei zurück,
ist das korrekte Verhalten bereits implementiert: `untracked`, unbenannt,
**RED**. Eine Ausnahme wird gebaut, wenn der Fall eintritt, nicht bevor.
Weg C (committen) wäre eine Zugehörigkeitsentscheidung mit eigenem Commit —
nicht vorbereitet.

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

**Prüfungen dieser Runde, mit ihrem Gegenstand:**

| Prüfung | Gegenstand | Aufrufer |
|---|---|---|
| `gate:`-Hash in der Ausgabe | Werkzeug | Dienst-Werkzeug selbst |
| `criterion:` in der Ausgabe | Regel, nicht Code | Werkzeug selbst |
| `blocking: … (Stand <blob>)` | Werkzeug, datiert | Werkzeug selbst |
| pyc-Inhalt == `5c5bc364` (§5.4d) | geladener Bytecode | Mensch, bei Abnahme |
| Kopfzeilen-Regel im pre-commit | Doku | **Hook** (nicht mehr von Hand) |
| `git rev-parse <commit>:<path>` | Adressauflösung Doc↔Werkzeug | Mensch, bei Abnahme |

**Die Handprüfung nach dem Commit war vakuum-grün.** `git diff | rg '^[-+]##'`
vergleicht Arbeitsstand gegen Index — nach `git commit` sind beide identisch,
und leer hat dann zwei Ursachen: sauber, oder nichts mehr zu prüfen. Die
Form, die den Commit prüft:

```
git show <commit> -- <datei> | rg '^[-+]#{2} '
```

Das ist dieselbe Bauform wie `git diff --quiet` bei untracked (Runde 1): das
Werkzeug stimmt, der Zeitpunkt war der falsche. Der Hook prüft `--cached` und
greift dort richtig; die Handprüfung daneben tat es nicht.

## 8. Tests dieser Runde

| Datei | Zeugen |
|---|---|
| `tests/test_fill_replay.py` | C-Positiv, C-Negativ, C-Isolation (3) |
| `tests/test_telemetry_reconciliation.py` | Vollständigkeit, `<`→Gleichheit, zwei Achsen, `decision_seq`-Kollision, Zeile ohne Key, Neustart je Run, `item_id` ≠ Join-Schlüssel, historical-rot-blockiert-nicht, current-rot-blockiert |

Suite: **168 passed** (157 vor der Untergrenze + 11 Kopplungs-/Schwellenzeugen). **Grün heißt „die Tests laufen",
nicht „die Tests prüfen das Richtige"** — die erste Fassung dieser Runde war
grün über einem falschen Join-Schlüssel. Deshalb sind die Negativkontrollen
(38 vs. 34, `decision_seq`-Kollision, current-RED) ausdrücklich Teil der Suite.

## 9. §5.4ac — Die Richtung, die (1) durchließ

`(1)` lautete `telemetry_rows == decision_seq_keyed` und `unattributed == 0`.
`unattributed` = Erfolg ohne Zeile. **Das Gegenstück fehlte.** Autocommit pro
Zeile (`persistence.py`) macht beide Brüche real, aber nur einer war rot:

| Bruch | Zustand | vorher | jetzt |
|---|---|---|---|
| Erfolg gezählt, Zeile verloren | `rows < success` | RED ✓ | RED ✓ |
| Zeile geschrieben, Erfolg fehlt | `rows > success` | **GREEN ✗** | **RED ✓** |

`(4)` konnte das nicht fangen: die Bilanz `Σ = n` gilt *innerhalb* des Ledgers.
Die Überbehauptung liegt *zwischen* Ledger und Dispatcher — genau die Grenze,
für die (1) zuständig ist. Neu: `telemetry_without_dispatch()` und Bedingung
`(3b) orphan_rows == 0` mit `detail["overclaim"] = True`.

### §5.4ad — Der offene Lauf

`PRAGMA table_info(telemetry_runs)` → `run_id, started_at, git_commit,
config_json`. **Es gibt keine Spalte für ein Ende.** Run 9 ist damit per
Definition offen; `observed: 69,8 h` hat einen Anfang und eine gemessene
Länge, aber kein aufgeschriebenes Ende.

Konsequenz: das Etikett lautet **`PROVISIONAL_LEDGER_CONSISTENT`**, solange
der Lauf offen ist. Ein offener Lauf ist keine Beobachtung, sondern ein
Bruchstück — `delivered = 0` ist dort ein *Stand*, keine *Tatsache*; die vier
Zeilen können fünf werden, ohne daß der Ledger sich verschlechtert hat.

`latest_run_is_closed()` gibt heute konstant `False` zurück und **das ist die
Aussage**, nicht ein Platzhalter. Der Zeuge
`test_closed_run_would_be_judged_ledger_consistent` prüft beide Seiten: keine
Ende-Spalte ⇒ `False`, und wenn eine dazukommt, muß die Funktion sie lesen.

**Für den 20.10. sind das zwei verschiedene Abnahmen**, und die Akte sagt
jetzt, welche: wird Run 9 am 17.10. geschlossen, liegen die 13 Tage Stille
*hinter* der Messung; ist er am 20.10. seit sechs Tagen offen, ist das Urteil
ein Stand über einem laufenden Lauf. Bisher stand dazu nichts.

### §5.4ae — 360 vs. 359: die eine Zeile

```
gesamt 360 = 1 vor dem Fenster + 299 (run 8) + 60 (run 9)
```

Die fehlende Zeile: `9f568b38fd2b46b9`, **2026-10-04 08:00:08**,
`unresolved_asset` — ein Warmup-Dispatch *vor* `started_at(run 8)`. `START.md`
schließt `run_id` 1–6 aus, diesen Dispatch nicht. Er liegt außerhalb jedes
Urteils, war aber unsichtbar, weil nichts ihn zählte.

Neu im Detail: `dispatched_before_scope`, und eine Zeile in der Ausgabe:

```
traffic:            300 vor dem Fenster + 60 im Fenster = der Rest liegt außerhalb jedes Urteils
```

Die Versöhnung schließt jetzt auf **360**, nicht auf 359.

### §5.4af — `START.md`-Zeuge: genau 1 Treffer

`assert len(rows) == 1` — **fail, nicht skip.** Null Treffer hieße: die Zeile
ist umbrochen oder umbenannt, und der Zeuge sieht nicht mehr, was er prüfen
soll. Zwei hießen: zwei Wahrheiten.

**Zählgrenze, benannt:** verglichen werden **Nummern**, nicht Inhalte. Der
Zeuge prüft, *daß* `(0) (3) (3b) (4)` dastehen — nicht, ob sie dasselbe
bedeuten. Das können nur die Fixtures. Er verhindert, daß Absicht und Code
auseinanderlaufen, ohne daß es jemand merkt; er kann keine Formel prüfen.

### §5.4ag — `FIXTURE_ROWS` ist Aufbau

`grep` über `order_execution_engine/`: die Konstante existiert in **keiner
Produktionsdatei** — nur im Test und in dieser Akte (Z. 1117). Die drei
Assertions sind Aufbau-Prüfungen (`== FIXTURE_ROWS`, `== PINNED_FIXTURE_ROWS`),
keine Schwellen.

Damit das so bleibt: `test_fixture_rows_never_reaches_production` prüft die
**Import-Richtung** — kein Produktionsmodul darf `FIXTURE_ROWS` oder den
Testmodulnamen enthalten. Umbenennen hilft nicht mehr.

### §5.4ah — `DERIVED`: Auslöser benannt, und er hat gegriffen

`DERIVED` feuert genau dann, wenn **`hash-object(datei)` ≠ `HEAD:datei`** —
Datei-Blob gegen Commit-Blob. Nicht `git status`, nicht Semantik, nicht
„Kriterium geändert".

**Warum es in Runde 13 schwieg, obwohl das Kriterium sich änderte:** Runde 13
hatte *committet* (`84f1ba95`). Danach war `work == committed`. Der
Definitionsbereich ist die **Datei**, nicht das **Kriterium** — der Marker
sagt „dieser Text ist nicht der Text, über den abgestimmt wurde", nicht
„diese Regel hat sich geändert". Er hätte in Runde 13 nur gefeuert, wenn die
Änderung uncommittet geblieben wäre.

Heute (uncommittet): `work 9d6942c6…` ≠ `HEAD bfe32160…` ⇒
`gate commit: 84f1ba95:bfe32160556c  DERIVED (Datei != HEAD-Blob)`. ✓

Das ist kein Fehler des Markers, aber eine **Grenze, die dastehen muß**: er
markiert Sichtbarkeit von Änderungen, nicht Drift von Kriterien. Ein Marker
für Kriteriumsdrift wäre der `criterion`-String selbst — und der steht in
jeder Ausgabe.

### §5.4ai — `x != "LEDGER_CONSISTENT"`: ein zweites Etikett brach die Blockade

Beim Einführen von `PROVISIONAL` schlugen zwei Zeugen fehl mit
`['latest run 9: PROVISIONAL_LEDGER_CONSISTENT (blockierend)']`. Ursache:
`preflight_check.py` verglich gegen ein **String-Literal**:

```python
and snapshot["verdicts"]["current"] != "LEDGER_CONSISTENT"
```

Ein Set ist die Form. **`test_non_blocking_conditions_have_no_red_branch`
konnte das nicht fangen** — es zählt RED-Zweige, und ein Literal-Vergleich ist
kein RED-Zweig. Das ist die *dritte* Stelle dieser Akte, an der eine
Schwelle als Kopie eines Werts überlebt hat (nach `MIN_TELEMETRY_ROWS` und
dem Jahr in `--since`).

## 10. Tests dieser Runde

| Zeuge | Aussage |
|---|---|
| `test_orphan_row_without_dispatch_is_red` | Zeile ohne Erfolg ⇒ RED + `overclaim` |
| `test_closed_run_would_be_judged_ledger_consistent` | kein Ende ⇒ `PROVISIONAL`, strukturell |
| `test_fixture_rows_never_reaches_production` | Import-Richtung, nicht Namen |
| `test_start_md_gate_line_matches_criterion` | genau 1 Treffer, sonst fail |

Suite: **178 passed**.

Der Satz aus §8 bleibt gültig — und diese Runde hat ihn zweimal bestätigt:
die Suite war nach dem ersten Durchlauf **nicht** grün, weil die Zeugen die
Etiketten-Änderung sahen, bevor der Code sie trug. Das ist die Reihenfolge,
in der eine Akte gelesen werden soll.

## 11. §5.4aj — Der Loop läuft. Es sind nicht 300 in 13 Tagen.

```
SELECT date(dispatched_at,'unixepoch','localtime'), count(*)
FROM dispatched_signals GROUP BY 1 ORDER BY 1;
```

| Tag | n | Tag | n |
|---|---|---|---|
| 10-04 | 5 | 10-11 | 7 |
| 10-05 | 33 | 10-12 | 29 |
| 10-06 | 33 | 10-13 | 32 |
| 10-07 | 38 | 10-14 | 38 |
| 10-08 | 45 | 10-15 | 32 |
| 10-09 | 34 | 10-16 | 21 |
| 10-10 | 7 | 10-17 | 6 |

**14 Zeilen à ~23.** Und das Muster ist schärfer als die Tageszahl:

- **Minutenanteil: `00`, 360 von 360.** Kein einziger Dispatch außerhalb `HH:00`.
- Abstände: median **3.597 s** = 1 h − 3 s; 360 Dispatches über 3.600 Stunden-Slots.
- **177 Paare mit Abstand 0 s** — der Loop schreibt, wenn er etwas findet, in Paketen; in stillen Stunden schreibt er nichts.
- Letzter Dispatch: **2026-10-17 18:00:08**. PID 962 lebt, `etime 02-22:05`, Start 14.10. 21:23.

**Damit ist die Erzählung entschieden: der Dienst läuft, die Auflösung steht.**
Nicht „seit 13 Tagen tot", sondern *stündlicher Loop, 0 Auslieferungen seit
04.10. 11:12:39*. Und eine Folge, die die Akte noch nicht hatte: **das 60er-Fenster
von Run 9 ist nicht ein Zeitraum, es sind Stunden-Slots.** 2,88 d = 69 Slots,
davon 60 mit Inhalt — 87 % Trefferquote, kein Ausfall.

`observed: 69,8 h` heißt also nicht „69 Stunden Aktivität", sondern „69
Stunden, in denen der Loop hätte schreiben können". Das ist die
Interpretation, die zu den Zahlen paßt, und sie gehört ins Etikett.

## 12. §5.4an — Ein Etikett, das immer gilt, blockiert dauerhaft

`PROVISIONAL_LEDGER_CONSISTENT` war die richtige Beobachtung und die falsche
Form: solange `closed_at` fehlt, gilt es *immer* — für Run 9 und für jeden
folgenden Lauf. Zwei Folgen, beide behoben:

**a) Das Etikett trägt jetzt seine Dauer.**

```
verdict:  PROVISIONAL_LEDGER_CONSISTENT(open 2.9d) (4 Zeilen, 0 Auslieferungen)
```

`PROVISIONAL` ohne Zahl ist ein Zustand; mit Zahl eine Messung. (2,9 d = Alter
von `started_at(run 9)` bis jetzt. Die 13 Tage Stille liegen **hinter** der
letzten Auslieferung, nicht hinter dem Laufbeginn — zwei Zahlen, zwei
Aussagen, beide jetzt sichtbar.)

**b) `PROVISIONAL` blockiert nicht mehr.** Es war als blockierend eingetragen,
und das war der Fehler: was nur deshalb immer gilt, weil das Schema kein Ende
kennt, ist der **Normalzustand** — und ein Normalzustand, der blockt, hält
den Dienst an, den er schützt. Dieselbe Form wie Runde 1 (`BLOCKED` über
leerer Telemetrie, 96 Neustarts), nur mit besserer Begründung.

Die Klassifikation arbeitet jetzt auf dem **Etikett-Kopf** (`split("(")[0]`),
nicht per Set-Mitgliedschaft — sonst hätte die neue Dauer im Etikett genau
den Fehlalarm erzeugt, den das Set verhindern sollte.

**War die Stille eine Gate-Folge?** Nein, und das ist belegbar: das Gate wurde
in dieser Akte erst im Oktober gebaut, und PID 962 läuft seit 14.10. mit
einem Gate, das niemand verdrahtet hat (`blocking: kein Aufrufer verdrahtet`).
Die 13 Tage Stille stammen aus dem Mapping-Layer, nicht aus der Vorsicht.

## 13. §5.4ao — Der Grund ist das Schema, nicht der Boolean

`test_closed_run_would_be_judged_ledger_consistent` prüfte
`latest_run_is_closed(...) is False` — einen konstanten Wert. Der dritte
Zeuge dieser Art nach `PINNED_MIN_TELEMETRY_ROWS`.

```
assert schema["has_closed_at"] is False     # der Grund
assert verdict.status.startswith("PROVISIONAL_")   # die Folge
```

Wandert `closed_at` ins Schema, bricht **die erste Zeile** — und das ist die
richtige Nachricht. `latest_run_is_closed()` liest jetzt das Schema und, falls
vorhanden, die Spalte; sie behauptet `False` nicht mehr.

## 14. §5.4ap — Drei Instanzen, eine Klasse, und der Wächter fängt sie

`grep`-Form über alle Produktionsdateien, drei Gestalten:

| Gestalt | Instanz | wie gefangen |
|---|---|---|
| benannte Konstante | `MIN_TELEMETRY_ROWS` | Namensverbot im Produktionscode |
| Literal in einem Vergleich | `!= "LEDGER_CONSISTENT"` | Etikett + Vergleichsoperator in derselben Zeile |
| Kalenderjahr im Vergleich | `== 2025` in `--since` | `[=!<>]= 20\d\d` |

**Die erste Fassung dieses Wächters fing 2 von 3** — das Jahr rutschte durch,
weil es weder Konstante noch Etikett ist. Das fiel erst auf, als ich den
Wächter gegen die drei historischen Zeilen laufen ließ, statt gegen den
heutigen Stand. Eine Prüfung, die gegen den heutigen Stand läuft, findet
nie, was gestern falsch war.

## 15. §5.4aq — `DERIVED` beobachtet den Kriteriumssatz, nicht eine Datei

Der Marker verglich eine Datei gegen ihren HEAD-Blob. Das Kriterium steht in
drei: `preflight_check.py`, `START.md`, `TAG7_ABNAHME.md`. Eine Datei kann
nicht alle drei sein — und `START.md` war die Datei, die 14 Runden lang nicht
diffed wurde.

```
CRITERION_FILES = (preflight_check.py, START.md, TAG7_ABNAHME.md)
gate commit: 2c75656a:9d6942c67687  DERIVED (preflight_check.py != HEAD-Blob)
```

Der Marker nennt jetzt **welche** der drei abweicht. In Runde 15 wäre die
Antwort `START.md` gewesen, nicht der Code — das ist der Unterschied zwischen
einem Marker und einem Marker mit Adresse.

## 16. §5.4ar — (1) ist ein Korollar aus (3)+(3b)

`unattributed == 0` ≡ `success <= rows`. `orphan_rows == 0` ≡ `rows <= success`.
Zusammen: `rows == success`. Bedingung (1) prüft die **Schreibseite** (jede
Zeile hat ihren Schlüssel) und bleibt als Diagnose stehen — als Bedingung
zählt sie nicht mehr. Das steht jetzt in `_gate_criterion()` mit dem Wort
„KOROLLAR", damit die nächste Runde nicht wieder sechs Bedingungen zählt,
von denen eine folgt.

## 17. Tests dieser Runde

| Zeuge | Aussage |
|---|---|
| `test_closed_at_schema_is_the_reason` | Schema ist der Grund, `PROVISIONAL` die Folge |
| `test_no_rule_constant_lives_as_literal_copy_in_production` | drei Gestalten, gegen die Geschichte geprüft (3/3) |
| `test_derived_observes_the_whole_criterion_set` | alle drei Dateien im Satz |
| `test_criterion_is_printed_in_the_same_order_as_the_red_branches` | Korollar benannt |

Suite: **180 passed**.

## 18. Der Satz dieser Runde

Die Akte war am Ende von Runde 15 „nicht mehr falsch, sondern gefährlich" —
weil ein Etikett, das immer gilt, nichts unterscheidet. Diese Runde hat es
nicht zurückgenommen, sondern **endlich gemacht**: mit Dauer, mit
Nichtblockade, und mit dem Grund im Schema statt im Boolean.

Was bleibt, ist die eine Ziffer, die keine Runde beheben kann: **0
Auslieferungen sind 0.** Das Urteil stimmt, das Etikett ist ehrlich, das
Etikett ist datiert — und der Dienst liefert nichts aus, weil der
Mapping-Layer seit 13 Tagen taub ist. Kein Gate macht das anders.

## 19. §5.4aw — Die Stundenticks machen es schlimmer, nicht besser

Die Erwartung war: 336 Slots statt eines 3.848-Sekunden-Lochs, also
Auflösung auf Stunden. Die Abfrage:

```
SELECT reason, count(*), datetime(min(discarded_at),...), datetime(max(...))
FROM bridge_discards GROUP BY 1;
```

| Ursache | n | erster | letzter |
|---|---|---|---|
| `unresolved_asset` | 1 | 10-04 10:00:08 | 10-04 10:00:08 |
| `no_book` | 124 | 10-04 12:00:10 | 10-17 09:00:08 |
| `unresolved_asset:empty_list` | 66 | 10-04 15:00:06 | 10-17 17:00:06 |
| `unresolved_asset:mapping_miss` | 201 | 10-04 16:00:07 | 10-17 18:00:08 |

**Es gibt keinen Wechsel.** Alle drei Ursachen laufen ab dem 04.10.
nebeneinander her, 13 Tage lang, gleichzeitig am selben Tag. Die Akte hat in
Runde 14 („`unresolved_asset` → `no_book` → `mapping_miss`") und in §5.4aj
(„die Auflösung steht") einen **stufenweisen Verfall** behauptet. Den gibt es
nicht.

`mapping_miss` begann 16:00:07 am 04.10. — **vier Stunden nach** `no_book`
(12:00:10) und **eine Stunde nach** `empty_list` (15:00:06). Danach blieben
alle drei in Betrieb. Was kippte, kippte in den ersten sechs Stunden des
Laufs; die 13 Tage danach sind ein Gleichgewicht, kein Verfall.

Und die 392-vs-360-Differenz ist erklärt:

```
66 Discards ohne Dispatch = die 66 empty_list-Zeilen (item_id nie dispatched)
```

Kein Zusatzverkehr, keine verwaisten Zeilen — `empty_list` wird verworfen,
bevor es einen Dispatch gibt. `(3b) orphan_rows` prüft also korrekt.

## 20. §5.4ax — Die 30 Zeilen in Run 8 sind keine Auslieferungen

Die Akte behauptete ab §5.4ab: *„Run 8 startete 11:12:39 und erzeugte 30
Entscheidungen in Sekunden (inkl. der einzigen `approved=1`)."* Geprüft:

```
run 8 start          2026-10-04 11:12:39
erster Dispatch     2026-10-04 12:00:10   (+47 min, erster Stundentick)
Dispatches bis 12:00   1   (10:00:08, unresolved_asset — vor dem Lauf)
telemetry run 8        30   (seq 1..30, lückenlos)
```

`open_run()` schreibt **nur** den `telemetry_runs`-Eintrag
(`persistence.py:531`), keine Telemetrie. Die 30 Zeilen stammen also nicht
vom Laufstart — sie stammen aus 30 Engine-Entscheidungen ab 11:12:39, die
**nicht** dispatchet wurden.

Damit ist die Aussage „in Sekunden" unbelegt: das Entscheidungsfenster ist
nicht gemessen, `telemetry` hat kein `ts`-Feld. Was gemessen ist: 30
Entscheidungen, 0 Dispatches bis 12:00:10. Entscheidung und Dispatch sind
entkoppelt.

## 21. §5.4ay — `success` und `rows` zählen zwei verschiedene Dinge

| Größe | Bedeutung | Wert |
|---|---|---|
| `telemetry_rows` | Entscheidungen der Engine | 34 |
| `dispatched_success` | Dispatches ohne `bridge_discards`-Eintrag | 34 |
| `approved = 1` | genehmigte Entscheidungen | **1** |
| `delivered` | Fills, die das Portfolio erreicht haben | **0** |

Die Gleichheit `rows == success` ist erfüllt — **weil beide Seiten dasselbe
Maß benutzen**: eine Zeile pro Entscheidung, ein Dispatch pro Entscheidung,
kein Discard ⇒ erfolgreich. Sie ist **kein** Beweis dafür, daß eine
Entscheidung eine Auslieferung wurde.

Das war in §5.4a richtig beschrieben und ist in den Etiketten
`LEDGER_CONSISTENT`/`PROVISIONAL_LEDGER_CONSISTENT` verlorengegangen. Das
Etikett spricht jetzt nur noch über den **Ledger**; die Zahl, die über den
Dienst spricht, ist `delivered` und steht daneben.

## 22. §5.4as — `open_for` neben dem Urteil

Das Etikett trägt seine Dauer nicht mehr: `PROVISIONAL_LEDGER_CONSISTENT` ist
wieder idempotent. Die Dauer steht daneben.

```
verdict:   PROVISIONAL_LEDGER_CONSISTENT (4 Zeilen, 0 Auslieferungen)
open_for:  70.6 h (2.9 d) — der Lauf, nicht die Stille
```

Ein Urteil, das sich ohne Zustandsänderung ändert, ist eine Anzeige. Der
Zeuge kann das Etikett jetzt wieder pinnen.

## 23. §5.4at — `wired: nein` steht auf der Urteilszeile

```
wired:  nein — der 20.10. schaltet den ersten Aufrufer ein; bis dahin wirkt dieses Urteil nicht
```

`_blocking_callers()` sucht Importe des Gate-Moduls in Produktionscode
(außer der CLI). Sechzehn Runden Urteile, und keines hat je etwas
angehalten — der Unterschied zwischen `BLOCKED` (Runde 1) und `PROVISIONAL`
(Runde 15) war nie ein operativer. **Das ist die eigentliche Abnahme des
20.10.:** nicht ein Etikett abnehmen, sondern den ersten Aufrufer einschalten.
Was er dann tut, steht bisher nirgends.

## 24. §5.4au — `DERIVED`s Dateiliste wächst von selbst

Statt `CRITERION_FILES` zu pflegen, wird sie gelesen: jede Produktionsdatei,
die ein Gate-Etikett zitiert, gehört in den Satz. Heute dieselben drei; eine
vierte macht sich beim Anlegen sichtbar, statt bis zum Eintragen unsichtbar
zu bleiben. Der Marker nennt weiterhin, **welche** abweicht.

## 25. §5.4av — Die vierte Gestalt, und ihre Grenze

| Gestalt | Erkenner | gefangen |
|---|---|---|
| Konstante | Namensverbot | ✅ |
| Kalenderwert | `[=!<>]= 20\d\d` | ✅ |
| Literal | Etikett + Vergleich | ✅ |
| Ableitung | rechte Seite = Term × oder ÷ | ✅ teilweise |

**Die Grenze ist im Fixture festgehalten, nicht weggeredet:**
`(n - 1) // 2` und `a < b / 2` erkennt der Wächter **nicht**. Regex kann
einen Klammerausdruck nicht von einer Division unterscheiden. Der Wächter ist
ein Filter, kein Beweis — und die beiden Zeilen stehen als
`("Grenze (nicht erkannt)", ..., False)` in der Suite, damit die Lücke nicht
wächst, ohne daß sie jemand liest.

**Die historischen Zeilen sind Fixture, nicht Kommentar.** Alle drei alten
Instanzen plus zwei Ableitungs-Formen plus drei Gegenproben. Der Wächter
prüft jetzt Regression statt Zustand — der Satz der letzten Runde, angewandt.

## 26. Tests dieser Runde

| Zeuge | Aussage |
|---|---|
| `test_rule_constant_guard_catches_history` | 8 Fälle: 3 Gestalten erkannt, 1 teilweise, 2 Grenzen benannt, 3 Gegenproben |
| `test_derived_observes_the_whole_criterion_set` | Dateiliste abgeleitet, nicht gepflegt |
| `test_closed_at_schema_is_the_reason` | Schema ist der Grund |
| `test_criterion_is_printed_in_the_same_order_as_the_red_branches` | (1) als Korollar |

Suite: **181 passed**.

## 27. Der Satz dieser Runde

Die Stundenauflösung hat nicht den Wechsel gezeigt, sondern sein Fehlen:
**alle drei Ursachen laufen seit dem 04.10. parallel.** Damit fällt die
Erzählung vom stufenweisen Verfall, die diese Akte zwei Runden lang
mitgetragen hat — sie war eine plausible Reihenfolge, keine Messung.

Und der Befund, der größer ist als alle vier Buchungen:
**`approved=1` ist 1, `delivered` ist 0, und `rows == success` ist trotzdem
erfüllt.** Die Gleichung stimmt, weil sie zwei Dinge zählt, die dasselbe Maß
haben. Das Etikett hat darüber nie gelogen — aber es hat auch nie darüber
gesprochen.

## 28. §5.4bd — 391, 392, 393, 426: vier Zahlen, eine gültige

```
bridge_discards 393  = mapping_miss 202 + no_book 124 + empty_list 66 + unresolved_asset 1
                          (nicht 201 — Runde 17 zitierte eine 6 h alte Zahl)
dispatched_signals 361 = 327 (mit Discard) + 34 (ohne Discard)
bridge_discards 393  = 327 (zu Dispatches) + 66 (empty_list, ohne Dispatch)
```

**Die Runde-17-Zahlen waren eine Momentaufnahme um 18:00.** Um 20:00:08
schrieb der Loop eine neue Zeile: 360 → 361, 392 → 393. `mapping_miss` 201 →
202. Das ist keine Korrektur, das ist Fortschreibung — die Quelle lebt.

**`426` war keine Gesamtzahl.** `361 + 66` addiert zwei disjunkte
Grundmengen: Dispatches und verwaiste Discards. Die 66 stehen nicht *neben*
den Dispatches, sie sind eine Teilmenge, die *nie* einen Dispatch bekam.
Richtig gerechnet wird jede Seite für sich.

Und ein Artefakt, das die Klasse beweist: eine Prüfung
`WHERE dispatched_at > '2026-10-17 18:00:09'` liefert **0**, weil
`dispatched_at` `REAL` ist und der String-Vergleich immer falsch. Die
Tabelle hatte zu dem Zeitpunkt 361 Zeilen. **Die fünfte Instanz der Klasse
war in meiner eigenen Abfrage** — String gegen Zahl, in derselben Form wie
`year == 2025`.

## 29. §5.4az — `delivered` zählt nicht Fills

```
delivered (Gate)  = telemetry.approved = 1 AND run_id >= 9  = 0
fills (real)      = 1, decision_seq = 12, PARTIALLY_FILLED,
                    filled_at '2026-10-06T18:00:06.993672Z'
```

Die Zeile „0 Auslieferungen" ist **korrekt über das Fenster** und **falsch
über den Dienst**. Beide Sätze sind wahr, und 13 Runden lang stand nur der
erste da. `delivery` steht jetzt daneben:

```
delivery:  DELIVERY_STALLED_SINCE (4 Erfolge, 0 genehmigt, 1 Teilfill, letzter 2026-10-06T18:00:06)
           # Überschrieben in §5.4bd — hier steht der Stand von Runde 18:
           # "NO_DELIVERY_SINCE" sagte "nie" neben einer 1. Die Form, die
           # diese Akte dreimal korrigiert hat.
```

### Die Kette, vier Stufen, drei Übergänge

| Stufe | Wert | Verlust |
|---|---|---|
| Dispatches | 361 | — |
| Erfolge (ohne Discard) | 34 | **90,6 %** im Mapping |
| `approved = 1` | **1** | **33 von 34** |
| Fills | **1** | 0 nach Approval |

**Die zweite taube Stelle ist die Approval-Stufe**, und sie hat keinen
Namen: `reject_reason` existiert nur für `approved = 0`. Die 33 Übergänge
34 → 1 sind in der Tabelle nicht als Ursache, sondern als *Abwesenheit*
von `approved` verzeichnet. Wer fragt „warum nur eine", findet keine
Spalte, die antwortet.

## 30. §5.4ba — Zwei Etiketten, weil ein Etikett nicht beides sagen kann

```
verdict:   PROVISIONAL_LEDGER_CONSISTENT   (der Ledger)
delivery:  DELIVERY_STALLED_SINCE          (der Dienst, §5.4bd)
```

`(8)` blockt **nicht** — sie ist ein zweites Etikett, kein sechstes Wort im
ersten. Sonst wäre der Ledger rot, weil der Dienst steht: zwei Aussagen in
einer Zeile, von denen keine mehr lesbar ist.

## 31. §5.4bb — `wired` und `read_by` sind zwei Zustände

```
wired:    nein — kein Import in Produktionscode
read_by:  nichts — kein Skript liest die Urteilszeile
```

`_blocking_callers()` findet Importe. Der erste Aufrufer am 20.10. wird ein
Cronjob sein, der die **Ausgabe** liest — und den kann ein Import-Scan per
Konstruktion nicht sehen. `read_by` ist die Angabe, die den 20.10.
beschreibt: sie sagt, wer zuerst handelt.

## 32. §5.4bc — Zwei fehlende Felder, drei Zeitformate

| Tabelle | Zeitfeld | Typ |
|---|---|---|
| `telemetry_runs` | `started_at` | REAL (unixepoch), **kein `closed_at`** |
| `dispatched_signals` | `dispatched_at` | REAL |
| `fills` | `filled_at` | **TEXT**, ISO-8601 `2026-10-06T18:00:06.993672Z` |
| `telemetry` | — | **kein Feld** |

Drei Formate in einer Tabellenfamilie. Ohne `telemetry.ts` ist die
Zuordnung Telemetrie ↔ Dispatch eine **Positionsannahme** (`decision_seq`),
keine Zeitaussage — und eine Position ist keine Messung. Das ist die fünfte
Gestalt der Kopie: eine Annahme, die wie ein Schlüssel aussieht.

Dazu: `dispatched_signals.telemetry_seq` ist in **allen 361** Zeilen `NULL`.
Die Spalte, die Dispatch und Telemetrie verbinden sollte, wurde nie
geschrieben.

## 33. Tests dieser Runde

| Zeuge | Aussage |
|---|---|
| `test_delivery_is_a_second_label_not_a_word_in_the_first` | Ledger-Etikett bleibt grün, Dienst-Etikett sagt NO_DELIVERY |
| `test_missing_fills_table_is_unknown_not_zero` | fehlend ≠ 0 |
| `test_verdict_readers_are_reported_separately_from_importers` | zwei Zustände, getrennt abfragbar |
| `test_rule_constant_guard_catches_history` | Grenze datiert: 17.10.26, Regex vs. Klammerausdruck |

Suite: **184 passed**.

## 34. Der Satz dieser Runde

Die Versöhnung schließt — auf beiden Seiten getrennt, mit 361 und 393, und
die 66 stehen da, wo sie hingehören: nicht neben den Dispatches, sondern
als die Menge, die nie eine bekam.

Und die Zahl, die den Dienst beschreibt, ist jetzt endlich sichtbar als
Kette: **361 → 34 → 1 → 1**. Drei Übergänge, zwei davon mit Namen
(`mapping_miss`, `no_book`), einer ohne: **34 → 1 bei der Genehmigung.** Die
taubste Stelle der Kette ist die, für die es keine Spalte gibt.

Das Urteil ist damit vollständig, und vollständig heißt hier: es sagt über
jede Stufe genau das, was gemessen ist — und nichts über die, die es nicht
sieht.

## 35. Runde 19 — der Positivfall, und die Korrektur an mir selbst

### §5.4ay — Der vierte Grund ohne Namen: `unresolved_asset` (1)

Neben `:empty_list` (66) und `:mapping_miss` (201 → **202** um 20:00:08;
die Quelle lebt, s. Abfrage A) steht ein Treffer ohne Untertyp. Er ist der
Warmup-Dispatch **vor jedem Fenster** — 08:00:08, der eine Aufruf, nach dem
der Dispatcher in den Stundentakt fällt. Er liegt außerhalb jedes
Beobachtungsfensters und wird bewußt unklassifiziert gelassen: ein Fall
ohne Namen an einer Stelle ohne Fenster braucht keinen Untertyp, weil kein
Fenster ihn je zählt. Die Zeile existiert nur, damit die Summe stimmt —
`66 + 202 + 1 = 269` ist die vollständige Discard-Menge ohne Dispatch-Bezug
(gesamt 393, davon 124 `no_book`).

Das ist dieselbe Form wie die Approval-Lücke, eine Stufe früher: *ein
Zähler ohne Spalte*. Der Unterschied ist, daß sie hier **gewollt** ist.

**Und der Beweis, warum Abfragen ins Repo gehören:** der Satz „201
`mapping_miss`" stand in dieser Akte seit Runde 14 und war bei der
Niederschrift von Runde 19 bereits falsch. Die Abfrage hat es nicht
gefunden, weil sie neu war — sie hat es gefunden, weil sie **gespeichert**
ist und beim nächsten Lauf erneut läuft.

Das ist dieselbe Form wie die Approval-Lücke, eine Stufe früher: *ein
Zähler ohne Spalte*. Der Unterschied ist, daß sie hier **gewollt** ist.

### §5.4bb — `decision_seq = 12`: der Positivfall mit Zeiger

Die Akte hatte bis hierher 33 Zeugen für das, was fehlt, und keinen für
das, was reicht. Er existiert:

```
run_id=8  decision_seq=12  approved=1  reject_reason=NONE
status=PARTIALLY_FILLED    requested_size=100   latency=0.485 ms
order_id=13630cce-9ad4-4ff8-baa1-012bcf8d9c95
fill:    0.005 @ 5 / 5    2026-10-06T18:00:06.993672Z   BUY   fill_idx=0
```

Und die Nachbarn: `seq 10 = STALE_SNAPSHOT`, `seq 11 = INVALID_PRICE`,
`seq 12 = approved`, `seq 13 = INVALID_PRICE`, `seq 14 = STALE_SNAPSHOT`.
Die andere Frage — „welches Asset wurde aufgelöst und warum bei 11 und 13
nicht" — ist damit beantwortet: **es war kein anderes Asset.** Seq 11 und
13 fielen an `INVALID_PRICE`, und beide tragen `requested_size = NULL`,
weil die Ablehnung *vor* der Ordererzeugung griff. Bei seq 12 existierte
ein Preis, also entstand eine Order. Der Unterschied ist nicht das Asset,
sondern ob ein Orderbuch-Snapshot vorlag.

**Der Positivfall ist also kein Mapping-Erfolg, sondern ein Preis-Erfolg.**

### §5.4bc — `PARTIALLY_FILLED` ist kein Fill, und der Quotient lügt nicht

Die Zeile sagte `1 Fills` neben `NO_DELIVERY`. Zwei Fehler auf einmal:

1. **`fills` hat keine Statusspalte.** Die Vollständigkeit steht nur in
   `telemetry.status` — als *Urteil des Ausführers*, nicht als Messung.
   Wer `COUNT(*)` zählt, zählt Zeilen, nicht Ausführungen.
2. **Bei seq 12 widerspricht das Urteil der Menge.** `executed_size = 5`,
   `fills.requested_size = 5` → der Fill war **vollständig** (Quotient
   1,0). `telemetry.requested_size = 100` → die **Order** wurde zu 5 %
   bedient (Quotient 0,05). `PARTIALLY_FILLED` bezieht sich auf die
   Order, nicht auf den Fill. Beide Zahlen sind wahr, und sie beschreiben
   verschiedene Dinge.

Die Zahl, die den Dienst beschreibt, ist `sum(executed_size) /
sum(requested_size)` über die **Fill**-Zeilen — bei seq 12: **1,0**. Der
Gate gibt jetzt alle drei aus: `fills_total`, `fills_full`,
`fills_partial`, `fill_ratio`. Eine Zeile ist kein Fill.

### §5.4bd — `DELIVERY_STALLED_SINCE` statt `NO_DELIVERY`

Drei Etiketten reichten nicht. Die vierte Stufe braucht ein Wort, das
sagt: *es lief einmal, und seitdem nicht*. `DELIVERING` (falsch),
`NO_DELIVERY_SINCE` (sagt „nie") und `NO_TRAFFIC` (sagt „nie gefragt")
lassen den Fall „einmal, dann nie" aus.

```
delivery: DELIVERY_STALLED_SINCE
```

### §5.4be — Die Frische wird an der Gegenwart gemessen, nicht am Laufanfang

Erste Fassung: `_fresh_fill = _ts >= started_at`. Ergebnis: `DELIVERING`
neben einem Fill von vor **11 Tagen**. Der Grund war ein Denkfehler im
Maßstab: das Fenster beginnt am 04.10., der Fill liegt am 06.10. — 2,4
Tage **nach** Fensterbeginn, also „im Fenster", obwohl seither 11 Tage
vergangen sind. Im Fenster heißt nicht frisch.

Der Maßstab ist jetzt `FRESH_FILL_S = 2 × 3600 s` — zwei Dispatcher-Takte.
Danach ist der jüngste Fill ein **Beleg**, kein **Betrieb**. Das ist die
vierte Kopie desselben Musters in dieser Akte: ein Vergleich gegen die
falsche Referenz, der plausibel aussieht, weil beide Zahlen stimmen.

### §5.4bf — Der `unresolved_asset: 1` ist jetzt benannt

Siehe §5.4ay. Er steht in der Abfrage `queries/2026-10-17T2020_seq12.sql`
mit, damit die Discard-Menge vollständig bleibt.

### §5.4bg — `status` statt Boolean: sieben Zustände, alle entschieden

Die Vermutung war: `approved = 0` + `reject_reason IS NULL` = „nicht
entschieden", 33 Stück, ohne Spalte. **Die Abfrage widerlegt sie.**

```
approved=0  reject_reason gesetzt  n=33   -> rejected
approved=1  reject_reason gesetzt  n= 1   -> approved
approved=0  reject_reason IS NULL  n= 0
```

Es gibt **null** unentschiedene Zeilen. Und das ist kein Zufall: der
Validator `ExecutionReport._consistency` in `models.py` verlangt seit
jeher, daß `approved=0` einen `reject_reason ≠ NONE` trägt — sonst
`ValueError("Abgelehnt ohne reject_reason.")`. Die Approval-Stufe ist
nicht taub. **Sie ist die einzige Stufe, die vollständig funktioniert
hat:** 33 Ablehnungen, jede mit Grund, 26 davon *vor* der
Ordererzeugung (`requested_size IS NULL`).

Die Aufteilung nach Grund: `INVALID_PRICE` 26, `STALE_SNAPSHOT` 7.
Beide sind Ablehnungen, keine Ausfälle.

**Korrektur an dieser Akte:** §5.4ai–bc haben die 33 als „unentschieden"
geführt. Das war eine Schlußfolgerung aus dem Schema, nicht aus den
Daten. Die Daten sagen: 33 = 26 + 7, vollständig begründet. Der Fehler
war nicht die taubere Stelle — er war die Annahme, eine taubere Stelle
*sehen* zu können, ohne sie abzufragen.

Damit ist die Kette nicht `361 → 34 → 1 → 1`, sondern:

```
361 dispatch → 34 (327 Discards)  →  34 approve/reject  →  1 approved  →  1 Fill
                  voll benannt        volle Begründung        der Engpass
```

Der Engpass ist **nicht** die Genehmigung, sondern die **Preisverfügbarkeit**:
von 34 erreichten Entscheidungen fielen 26 an `INVALID_PRICE`.

### §5.4bh — Kardinalität ist nicht Identität: der FK, den es gibt

`telemetry_seq` ist in **allen 361** Dispatches `NULL`. `rows == success`
vergleicht also zwei unabhängige Sequenzen über `decision_seq` — eine
Reihenfolge-Annahme über zwei Reihenfolgen. Eine Vertauschung bleibt
unsichtbar.

Aber: **`order_id` existiert**, und zwar als echtes Feld in beiden Tabellen:

```
telemetry.order_id gesetzt  :  8 / 34
fills.join über order_id    :  1 / 1   (genau der Fill)
```

Und der Beweis, daß die Positionsannahme an der Stelle falsch ist, an der
sie zählt:

```
fill   decision_seq=12   →  06.10. 18:00:06
rn=12  (12. nicht-discardeter Dispatch)  →  06.10. 20:00:06   (+2 h)
```

Der 12. erfolgreiche Dispatch ist **nicht** die 12. Entscheidung. Die
Zuordnung über `decision_seq` ist damit nicht nur ungeprüft, sie ist an
genau einem Punkt nachweislich falsch. Der Gate gibt `fk_rows`, `fk_set`,
`fk_paired` aus, damit diese Grenze sichtbar bleibt statt still zu sein:
**der Ledger kann grün sein und permutiert.**

### §5.4bi — Abfragen mit Zeitstempel

`queries/2026-10-17T2020_seq12.sql` — die Abfrage, nicht das Ergebnis.
Der Stand steht im Kopf (20:20, +1 Dispatch/Stunde), damit jede
Fortschreibung der Quelle eine *dokumentierte Differenz* wird statt einer
stillen Korrektur. Und der Typ-Bruch aus §5.4bc (REAL vs. TEXT vs. keine
Spalte) ist in jeder gespeicherten Abfrage als Kommentar vermerkt, weil
ein `WHERE` auf einer `REAL`-Spalte mit einem String still `0` liefert —
ununterscheidbar von einem echten „nichts da".

## 36. Tests dieser Runde

| Zeuge | Aussage |
|---|---|
| `test_fill_after_window_start_but_old_is_not_delivering` | Frische an der Gegenwart, nicht am Laufanfang |
| `test_partial_fill_is_counted_as_partial_not_as_a_fill` | Mengen statt Zeilen: 5/100 = 0,05 |
| `test_order_id_is_reported_as_the_fk_that_was_hardly_written` | 1/4 gesetzt, 1 gepaart — sichtbar, nicht still |

Suite: **187 passed**.

## 37. Der Satz dieser Runde

Die Runde, die den Fehler im eigenen Werkzeug fand, hat auch den einzigen
Erfolg gefunden — und den Erfolg dann umgeschrieben: er ist kein
Mapping-Erfolg, sondern ein Preis-Erfolg. 26 von 34 scheiterten an einem
fehlenden Orderbuch, nicht an einem fehlenden Namen. Und die Stelle, die
diese Akte für taub hielt — die Genehmigung — war die einzige, die
vollständig funktioniert hat: 33 Nein, jedes mit Grund, 26 davon bevor
eine Order entstand.

Was am 20.10. abgenommen wird, ist ein Urteil über 9,4 % des Verkehrs, mit
einem benannten Positivfall und einer widerlegten Annahme. Und der FK,
der die Fundstelle schließen würde, existiert: `order_id`, gesetzt in 8
von 34 Zeilen. Es fehlt kein Feld — es fehlt, daß es gefüllt wird.

## 38. Runde 20 — das RED bekommt eine Adresse, und der Gegenstand wechselt

### §5.4bk — `verdict: RED` ohne Bedingung war die letzte leseunfähige Zeile

Neunzehn Runden lang trug jede Zeile dieser Akte Grund, Dauer und Adresse.
Dann stand da:

```
verdict:  RED (34 Zeilen, 1 Auslieferungen)
```

Wahr, begründet, unlesbar — die Form, die in Runde 1 `BLOCKED` hieß. Jetzt
trägt jedes RED seine Bedingung:

```
reason:   (3) unattributed: 4 Dispatch(es) ohne Telemetriezeile — Erfolg ohne Beleg
```

**Und der Grund ist nicht der Ledger.** Er ist die Grenze zwischen
Dispatcher und Ledger: vier Erfolge aus run 8, die nie eine Zeile bekamen.
Der Ledger stimmt (34 = 34); rot ist der Übergang dorthin. Das ist die
erste Stelle der Akte, an der ein rotes Urteil über etwas anderes spricht
als über den Ledger — und sie ist ehrlich beschriftet.

Sechs RED-Zweige, sechs Namen: `(0) underrun`, `(1) schreibseite`,
`(2) schluessel`, `(3) unattributed`, `(3b) orphan`, `(4) bilanz`.

### §5.4bl — Zwei Achsen, und die Achse steht im Feldnamen

Der Fehler aus §5.4be war kein Rechenfehler, sondern ein Achsenfehler:
`started_at` ist der Nullpunkt des Laufs, nicht der Maßstab für Aktualität.
Zweimal in dieser Akte war ein Feld `alter` ohne Achse falsch. Jetzt stehen
beide nebeneinander, beide richtig:

```
open_for:     323.3 h (13.5 d) — der Lauf, nicht die Stille
stalled_for:  264.5 h (11.0 d) — gegen jetzt, nicht gegen den Laufanfang
```

59 Stunden Unterschied. Beide Zahlen sind wahr; sie beantworten
verschiedene Fragen. Im Code heißt das Feld `stalled_for_h` — die Achse
ist Teil des Namens, nicht seiner Dokumentation.

### §5.4bm — `INVALID_PRICE` ist drei Ursachen an drei Code-Stellen

Die Frage war: *kommt das Preisfeld leer an, oder fehlt es im Schema?*
Antwort: **weder noch.** Der Code lehnt an drei Stellen mit demselben
Etikett ab, und nur die Stelle unterscheidet sie:

| Code | Fall | `reject_detail` | Reparatur |
|---|---|---|---|
| `1160` | `resolved_side()` → None | `NEUTRAL_SIGNAL` | Strategie (Richtung) |
| `1174` | kein Buch / falscher Token | `NO_SNAPSHOT` | Zuführung / Cache |
| `1185` | Buch da, Seite leer | `EMPTY_SIDE` | Liquidität |

Neu: `RejectDetail`-Enum, `TelemetryRecord.reject_detail` (Optional —
26 Zeilen der Akte kennen das Feld nicht; NULL heißt „nicht erfaßt", nicht
„keine Ursache"). Die 26 sind damit **nicht** nachträglich klassifizierbar:
der Grund ist verloren, nicht ungenau.

### §5.4bn — `8 / 34` ist keine Quote und keine Grenze, sondern ein Determinant

Die Frage war gestellt als Zeitreihe: die ersten acht, die letzten acht,
oder gestreut? Die Daten geben eine vierte Antwort, die keine Zeitreihe ist:

```
INVALID_PRICE   26   mit order_id  0   → KEINE
STALE_SNAPSHOT   7   mit order_id  7   → ALLE
NONE             1   mit order_id  1   → ALLE
```

**`order_id` steht genau dann, wenn eine Order entstand.** Kein Schreiber
fiel weg, keiner kam hinzu: die Spalte ist korrekt gefüllt — sie markiert
bloß keinen Entscheidungsschritt, sondern einen Order-Schritt. Damit ist
`order_id` kein Beleg für Vollständigkeit, sondern ein **Klassifikator**.

Und der Fill liegt unter den acht (run 8, seq 12): die korrekte Paarung
ist vorhanden, die Position war nur der falsche Weg dorthin.

Zeitreihen-Hypothese widerlegt: `first_with = 1`, `last_with = 24`, aber
nicht durchgehend — die acht liegen bei seq 1, 2, 3, 10, 12, 14, 17, 24.

### §5.4bo — Zwei Filter, nicht einer

```
Mapping:  361 → 34    (9,4 % passieren; 327 Discards, drei Namen)
Preis:     34 →  1    (3,0 % total; 26 INVALID_PRICE = 76,5 % der Reste)
```

Die Akte hat den Engpass 18 Runden lang im Mapping verortet. Er liegt
dahinter: von den 34, die den Mapping-Filter passieren, scheitern 26 an
der Preisverfügbarkeit. **Der Mapping-Filter ist der größere, aber er ist
benannt; der Preis-Filter ist der schärfere und war es nicht.**

Wichtig für die Zuordnung: `no_book` (124, 31,6 %) aus `news_bridge` ist
derselbe Fall wie `NO_SNAPSHOT` — nur eine Stufe früher erkannt, vor der
Signal-Erzeugung. `EMPTY_SIDE` ist der Fall, den `no_book` **nicht**
abdeckt: Buch vorhanden, Seite leer. Diese Unterscheidung war im Schema
nicht vorgesehen; sie entsteht erst durch `reject_detail`.

### §5.4bp — `no_book` bewußt ununterteilt

`empty_list` und `mapping_miss` tragen Untertypen, `no_book` nicht — bei
124 von 393 Zeilen. Das ist keine Lücke, sondern korrekt: die Ursache
liegt **im Buch selbst** (es fehlt), nicht im Mapping. Untertypen würden
eine Unterscheidung vortäuschen, die an dieser Stelle nicht existiert.
Wo sie existiert (`EMPTY_SIDE`), wird sie ab `reject_detail` erfaßt.

Und anders als die Approval-Stufe hat `no_book` keinen Validator, der
eine Lücke erzwingt — deshalb steht die Begründung hier und nicht im Code.

### §5.4bq — Der Snapshot lebt nur im Speicher: der Preis ist nicht rekonstruierbar

Die Frage aus §5.4bm war, ob der Preis *leer ankommt* oder *im Schema
fehlt*. Er kommt an und verschwindet wieder — noch vor der Frage:

```python
# shadow_execution_engine.py:965
def _store_snapshot(self, snapshot: MarketSnapshot) -> None:
    self._market_snapshots[snapshot.token_id] = snapshot   # dict, kein INSERT
```

`persistence.py` legt acht Tabellen an — `telemetry_runs`, `telemetry`,
`fills`, `portfolio_snapshots`, `peak_events`, `telemetry_fill_metrics`,
`dispatched_signals`, `bridge_discards`. **Keine Snapshot-Tabelle.**

Damit ist die 26 nicht nachträglich erklärbar: welches Buch zu welchem
Signal gehörte, welcher Ask fehlte, ob die Seite leer oder das Buch alt
war — alles war im RAM und ist mit dem Prozess gegangen. `reject_detail`
rettet nur die Zukunft (ab dem nächsten Lauf), nicht die Akte.

**Das ist die eigentliche Fundstelle dieser Runde.** Nicht der fehlende
Name der Ablehnung, sondern der fehlende Zeuge: der Engpass der
Produktionsseite ist ein Wert, und der Wert hatte keinen Ort, an dem er
überlebt. `NO_SNAPSHOT`/`EMPTY_SIDE` unterscheiden zu können setzt voraus,
daß der nächste Lauf es *schreibt* — deshalb ist `reject_detail` kein
Komfortfeld, sondern die einzige Spur, die bleibt.

Damit stehen vier fehlende Felder an vier Stellen, alle dieselbe Form:
`closed_at` (Laufende), `telemetry.ts` (Zeitpunkt), `telemetry_seq`
(Fremdschlüssel), `reject_detail` (Ursache) — und ein fünfter Kandidat
`orderbook_snapshot` (der Wert selbst), der nicht Feld, sondern **Tabelle**
ist.

## 39. Tests dieser Runde

| Zeuge | Aussage |
|---|---|
| `test_every_red_names_its_condition` | (0) und (3) tragen ihre Nummer — der Fall der Akte |
| `test_order_id_is_a_determinant_not_a_quota` | 0/2 · 2/2 · 1/1 — korreliert, nicht gestreut |
| `test_invalid_price_carries_three_causes_not_one_label` | drei Ursachen, drei Namen; Feld Optional |

Suite: **190 passed**.

## 40. Der Satz dieser Runde

`RED` ist die erste ehrliche Zeile dieser Akte — und sie brauchte einen
Grund, der nicht mehr im Ledger liegt. Er liegt an seiner Grenze:
vier Erfolge, die nie eine Zeile bekamen.

Der Positivfall hat sich als etwas anderes herausgestellt als erwartet:
kein Mapping-Erfolg, sondern der einzige Fall mit einem Preis. Und `8/34`
war nie eine Quote — es ist eine Klassifikation: `order_id` steht, wenn
eine Order entstand, und in 26 von 34 entstand keine, weil an drei
verschiedenen Stellen mit demselben Etikett abgelehnt wurde.

**Die Akte hat den Gegenstand gewechselt: sie spricht nicht mehr über den
Ledger, sondern über die Produktionsseite.** Und dort ist der Engpass
nicht der Name, sondern der Wert — ein Snapshot, der nicht persistiert
wird, ein Preis, der nur im Speicher lebte, und ein Feld `reject_detail`,
das es ab heute gibt und das die 26 alten Zeilen nicht mehr rettet.

## 41. Runde 21 — wer blockt, was eine Lücke ist, und der Fehler im eigenen Befund

### §5.4br — `RED` bekommt `blocking`, weil das Urteil einseitig war

`RED` wegen vier fehlender Zeilen, nicht wegen 26 verlorener Preise und
nicht wegen 264,5 h ohne Auslieferung. Das ist nicht falsch — ein Ledger
muß vollständig sein —, aber es ist **einseitig**: das Urteil bewertet
Buchführung, nicht Betrieb. Der 20.10. hätte `RED` gelesen, auf die vier
Zeilen geschaut und die falsche Seite repariert.

```
reason:     (3) unattributed: 4 Dispatch(es) ohne Telemetriezeile
blocking:   ledger
```

Der Wert ist immer gesetzt — bei GRÜN `none`. Ein Feld, das bei RED
gefüllt und bei GRÜN leer ist, ist keine Auskunft, sondern eine
Auslassung. `blocking` kennt drei Werte: `ledger`, `service`, `both`;
letzterer, weil ein Gate, das nur den Ledger sieht, `service` niemals
selbst setzen darf.

Und dabei fiel eine Kollision auf: die Zeile „kein Aufrufer verdrahtet"
hieß ebenfalls `blocking:`. Zwei Zeilen, ein Name, zwei Bedeutungen —
dieselbe Kopie, die diese Akte seit Runde 12 jagt. Sie heißt jetzt
`enforced:` (ob jemand das Urteil durchsetzt), `blocking:` sagt, was rot
ist (was den Befund trägt).

### §5.4bs — `8 / 34` war die falsche Frage: richtig ist `8 / 8`

`order_id` steht genau dann, wenn eine Order entstand. Die 26 ohne Order
sind **korrekt leer, nicht unvollständig**. Bezugsgröße ist der
Order-Schritt (`requested_size IS NOT NULL`), nicht die Entscheidung:

```
fk order_id:  8/8 Order-Schritte gesetzt
              (34 Entscheidungen, 26 ohne Order = korrekt leer)
```

Der Schreiber funktioniert vollständig. Daraus folgt:

**`telemetry_seq` (0/361) braucht keinen Schreiber.** Die Paarung läuft
über `order_id`, und der Fill liegt dort. Eine Spalte, die nie gefüllt
wird und nie gefüllt werden muß, ist keine Lücke, sondern eine Altlast —
`deprecated`, nicht `TODO`.

**Die Lückenliste war nie vier Felder lang.** Sie ist zwei Felder
(`closed_at`, `telemetry.ts`) und zwei Mißverständnisse (`telemetry_seq`
überflüssig, `order_id` vollständig gefüllt) — und seit §5.4bq ein
drittes echtes: die fehlende **Version** des Snapshots, nicht seine
Tabelle.

### §5.4bt — `reject_context` statt Snapshot-Tabelle, und `branch` als Pflicht

Die Zahlen, die die Entscheidung tragen:

| Lösung | Volumen (3 Token, 13 d) | beantwortet |
|---|---|---|
| Snapshot-Tabelle | ~5,6 Mio Zeilen | „wie sah der Markt aus" |
| `reject_context` (JSON) | ~5 KB/Tag | „warum wurde abgelehnt" |

Faktor ~10⁵. Und `_market_snapshots` überschreibt pro `token_id` — es ist
kein Leck, sondern ein **Ringpuffer der Größe 1**: der Preis war im
Ablehnungsmoment da und beim nächsten Tick weg. Es fehlt nicht die
Tabelle, es fehlt die **Version**. Die billigste Version ist eine Kopie im
Ablehnungsmoment, nicht eine Historie des Marktes.

Risiko der Tabelle, explizit: 5,6 Mio Zeilen heißen Write-Lock pro Tick,
die Gate-Suite liest mit, und ein Lauf schreibt dann mehr als er liest.
Bei einem System, das seit 13 Tagen nichts ausliefert, ist das der
falsche erste Schritt.

`branch` ist Pflichtfeld, kein Kommentar: `INVALID_PRICE` trägt drei
Ursachen an drei Code-Stellen, und ohne die Zeilennummer ist die Kategorie
blind. Ein Feld mit drei Werten, das niemand zählt, ist ein Etikett mit
Selbstbewußtsein.

### §5.4bu — Korrektur an meiner eigenen Zuordnung: 1160 ist nicht `EMPTY_SIDE`

Die naheliegende Lesart war, `side is None` sei „Seite leer". **Ist es
nicht.** `resolved_side()` liefert `None`, wenn `Direction.NEUTRAL` —
ein Richtungsfilter (`news_bridge.py:112`, Schwelle `theta = 0.1`), keine
Buchseite. Der Code hat drei Stellen, und sie bedeuten drei Dinge:

| Stelle | Fall | Name | Reparatur |
|---|---|---|---|
| `1160` | `resolved_side()` → None | `NEUTRAL_SIGNAL` | Strategie (Schwelle) |
| `1174` | kein Buch / falscher Token | `NO_SNAPSHOT` | Zuführung / Cache |
| `1185` | Buch da, `best_ask()` None | `EMPTY_SIDE` | Liquidität |

Am echten Engine-Pfad durchgespielt — drei Signale, drei Zahlen:

```
detail=EMPTY_SIDE        branch=1185  best_bid=0.004 best_ask=None
detail=NO_SNAPSHOT       branch=1174  token=TOK2
detail=NEUTRAL_SIGNAL    branch=1160  side=None
```

Damit ist der Test der Absicht nicht „läuft es", sondern **ob die
nächsten 26 drei Zahlen sind.** Und wenn nicht, sitzt das Feld an der
falschen Stelle — was in dieser Akte schon einmal passiert ist
(`PaperOrder` statt `TelemetryRecord`).

### §5.4bv — `EMPTY_SIDE` gehört nicht unter `no_book`

`no_book` = kein Buch (Bridge, vor dem Signal). `EMPTY_SIDE` = Buch ohne
Gegenseite (Engine, nach dem Signal). Zwei Reparaturen an zwei Bauteilen:
das eine ist ein Abruf, das andere ein illiquider Markt — und für einen
Markt ohne Gegenseite ist **nichts tun** die richtige Antwort, nicht
reparieren. Deshalb sind es zwei Namen, und `no_book` bleibt ohne
Untertyp (§5.4bp).

### §5.4bw — `snapshot_age_s` war falsch begründet

Im ersten Entwurf stand, `MarketSnapshot` trage keinen Empfangszeitpunkt,
und das Alter sei deshalb nicht erfaßbar. **Falsch:** das Feld heißt
`received_at`. Das Alter ist berechenbar und wird jetzt geschrieben —
ohne es wäre der Kontext ein Schnappschuß ohne Uhr, und `EMPTY_SIDE`
ließe sich nicht von `STALE_SNAPSHOT` trennen (zwei verschiedene
Reparaturen). Korrigiert vor dem Commit, nicht nach dem Abnahmetermin.

## 42. Tests dieser Runde

| Zeuge | Aussage |
|---|---|
| `test_red_says_who_blocks_and_green_says_nobody` | `ledger` bei RED, `none` bei GRÜN — als Wert, nicht als Lücke |
| `test_order_id_denominator_is_the_order_step_not_the_decision` | Nenner 2, nicht 4 — `8/8`, nicht `8/34` |
| `test_reject_context_carries_the_branch_that_makes_three_of_one` | `branch` Pflicht, drei Etiketten → drei Stellen |
| `test_engine_writes_three_branches_through_the_real_path` | echte Engine: 1185 / 1174 / 1160 |

Suite: **194 passed**.

## 43. Der Satz dieser Runde

Die Akte hat ihre Adresse — `RED` wegen vier Zeilen, die nie geschrieben
wurden, und daneben 26 Entscheidungen, deren Preis im RAM lag, als die
Order scheiterte, und beim nächsten Tick nicht mehr war.

Zum ersten Mal steht ein Befund da, der nicht durch Prüfen, sondern nur
durch **Schreiben** zu beheben ist: ein `reject_context` von 200 Bytes pro
Ablehnung, ein `branch`, der aus einem Etikett drei macht — und eine
Korrektur an der eigenen Zuordnung, die den Fehler in der Lesart fand und
nicht im Code: `side is None` war nie eine leere Buchseite, sondern eine
fehlende Richtung.

Und die Lückenliste ist geschrumpft, nicht gewachsen: zwei Felder
(`closed_at`, `telemetry.ts`), eine Altlast (`telemetry_seq`) und eine
fehlende Version (der Snapshot im Ablehnungsmoment). **Was diese Akte
seit dreizehn Tagen beschreibt, sind nicht vier fehlende Felder — es ist
ein System, das seine eigenen Fehler nicht mehr bezeugen kann.**

## 44. Runde 22 — die Schwelle, die Klammer, und was eine leere Seite ist

### §5.4by — `theta = 0.1` ist die erste Entscheidung dieser Akte

Alle Zahlen in dieser Akte sind Befunde; `theta` ist die einzige, die
**erzeugt** statt zählt. `|sentiment| < 0.1` → `Direction.NEUTRAL` →
`resolved_side()` None → kein Orderpfad. Gewählt, nicht kalibriert: es gibt
keinen Datensatz, gegen den 0.1 geprüft wurde — die Zeile trägt nur den
Default.

Damit ist `NEUTRAL_SIGNAL` auch keine Ablehnung, sondern eine **fehlende
Richtung, die den Orderpfad nie hätte betreten dürfen**. Sie wird
abgelehnt, *weil* sie ihn betreten hat. Der Fehler liegt eine Stufe früher
als das Etikett — und das ist die erste Stelle der Akte, an der die
Reparatur nicht am Etikett hängt, sondern am Filter davor.

### §5.4bz — `theta` ist kein Fix, solange die Kette nicht steht

`theta` senken erzeugt mehr Signale, die den Bridge passieren. Bei einem
Dienst, der seit 264,5 h nichts ausliefert, erzeugt das mehr Ablehnungen,
die wie Fortschritt aussehen — dieselbe Form wie `MIN_TELEMETRY_ROWS = 4`,
der Wert von Run 9.

**Reihenfolge: erst bezeugen, dann justieren.** Ab dem nächsten Lauf zählt
`reject_context.branch` die `NEUTRAL_SIGNAL`-Fälle (1160). Solange diese
Zahl unbekannt ist, wäre jede Senkung eine Setzung gegen eine Setzung.

### §5.4ca — `blocking: ledger (unenforced)`

`enforced: kein Aufrufer verdrahtet` war die ehrlichste Zeile — sie sagte,
daß das Urteil rot sein kann und niemanden aufhält. Daraus folgt: `ledger`
beschreibt nicht, was blockt, sondern was blockieren **würde**. Ein Wert,
der eine Absicht beschreibt, braucht beides im Feld:

```
blocking:  ledger (unenforced)
wired:     nein — kein Import in Produktionscode
read_by:   nichts — kein Skript liest die Urteilszeile
```

Dabei zwei Umbenennungen, beide gegen Namenskollisionen: die Zeile
„kein Aufrufer verdrahtet" hieß zuerst `blocking:` (zwei Zeilen, ein Name,
zwei Bedeutungen — die Kopie, die diese Akte seit Runde 12 jagt), dann
`enforced:`, und heißt jetzt `wired:` — den Namen gab es schon, er ist der
richtige. Die Blob-Verankerung heißt `anchored at:`.

**Warum das heute harmlos und morgen gefährlich ist:** ungefährlich, weil
niemand die Zeile parst. Gefährlich an genau dem Tag, den `read_by`
beschreibt — der erste Aufrufer wird ein Leser, und ein Leser, der
`^blocking:` greift, trifft zwei Zeilen mit zwei Bedeutungen.

### §5.4bx — Die Klammer enger gezogen: `try` über `fills` und `telemetry`

`grep "try:" | wc -l` = 20, `grep "except" | wc -l` = 19. Die Differenz
sind zwei `try/finally` (`shadow_runner.py:315`, `:336`) — kein Fehler,
meine Zählung war naiv. Die AST-Suche nach `try`-Blöcken, die
`OperationalError` schlucken und mehr als eine DB-Aktion umspannen, fand
vier Kandidaten, alle in `preflight_check.py` — alle meine eigenen.

Der schlimmste: ein `try` über `fills` **und** einen `JOIN fills ×
telemetry`. Fehlte `telemetry`, verschwand auch `fills_total`, und der
Bericht behauptete, es gäbe keine Fill-Schicht. Jetzt zwei Versuche,
zwei Ausfälle:

| fehlt | `fills_total` | `fills_full` |
|---|---|---|
| `fills` | `None` | `None` |
| nur `telemetry` | Zahl | `None` |

Dieselbe Form wie `WHERE` über zwei Typen (Runde 18) und `==` über zwei
`year`s (Runde 12): **der `except` war nie falsch, sein Umfang war es.**

### §5.4cb — `EMPTY_SIDE` war zwei Fälle unter einem Namen

Die Frage war, ob ein Snapshot in den Cache landet, bevor beide Seiten
geparst sind. **Nein** — die Ursache ist eine Festlegung, und sie steht
seit immer im Code:

```python
# market_data_feed.py:170
FESTLEGUNG: Fehlende Seiten (Preis 0 oder None) erzeugen KEINE Stufe —
ein Ticker mit nur Bid-Seite liefert ein leeres Ask-Buch.
```

Kein Rennen. Zwei Herkünfte, die dieselbe leere Tupel erzeugen:

| Herkunft | leere Seite heißt | Name | Antwort |
|---|---|---|---|
| `book` (vollständiges Event) | Markt hat keine | `EMPTY_SIDE` | nicht handeln, nichts reparieren |
| `ticker` (ein Level) | nicht mitgeliefert | `SIDE_NOT_DELIVERED` | vollständiges Buch abwarten |

`MarketSnapshot.source` trägt die Herkunft; `on_ticker` setzt `"ticker"`.
Ohne das Feld sind die beiden ununterscheidbar — und ein Fehleretikett auf
einer Markteigenschaft erzeugt eine Reparatur, die nichts reparieren kann.
Für einen Markt ohne Gegenseite ist **nichts tun** die richtige Antwort.

Und `EMPTY_SIDE` bleibt damit, was §5.4bv gesagt hat: **nicht** unter
`no_book`. `no_book` = kein Buch, `EMPTY_SIDE` = Buch ohne Gegenseite,
`SIDE_NOT_DELIVERED` = Buch ohne Gegenseite *weil nicht geliefert*.

## 45. Tests dieser Runde

| Zeuge | Aussage |
|---|---|
| `test_fk_report_survives_a_missing_fills_table` | `fills` fehlt → FK-Bericht bleibt, nur die Fill-Zahlen gehen |
| `test_side_not_delivered_is_not_the_same_as_empty_side` | echter `on_ticker`: `ticker` ≠ `book` bei gleicher leerer Ask-Seite |
| `test_theta_is_a_calibration_parameter_not_a_state` | 0.1 festgehalten, NEUTRAL bei 0.05, Richtung ab 0.15 |

Suite: **197 passed**.

## 46. Der Satz dieser Runde

Die 26 sind nicht mehr 26: sie sind fünf Zahlen, von denen eine —
`NEUTRAL_SIGNAL` — gar keine Ablehnung ist, sondern eine Schwelle, die
niemand kalibriert hat, und eine andere — `SIDE_NOT_DELIVERED` — kein
Marktzustand, sondern eine Auslassung, die seit immer im Code steht.

Die Akte zeigt damit zum ersten Mal nicht auf ein Feld, sondern auf einen
**Parameter** — und zum zweiten Mal auf eine Klammer, die zu weit greift:
der `except` um zwei Tabellen ist dieselbe Form wie der `WHERE` um zwei
Typen und der `==` um zwei `year`s.

**Was am 20.10. abgenommen wird, ist ein Urteil, das rot ist und niemanden
aufhält (`unenforced`), über ein System, das seit 264,5 h nichts
ausliefert — und dessen billigste Reparatur weiterhin eine Zeile im
Ablehnungsmoment ist. Die zweitbilligste ist jetzt bekannt: nicht eine
Zeile schreiben, sondern eine Klammer enger ziehen; nicht einen Preis
senken, sondern eine Schwelle prüfen, bevor sie etwas ablehnt.**

## 47. Runde 23 — zwei Fenster, zwei Typen, eine Konstante

### §5.4ce — `theta` als Konstante, nicht nur als Wirkung

Runde 22 hielt die Wirkung fest: 0.05 → NEUTRAL, 0.15 → UP. Das ist ein
Gitter mit zwei Maschen, und `theta` liegt dazwischen:

| `theta` | Test 0.05 | Test 0.15 | sichtbar |
|---|---|---|---|
| 0.1 | ✓ | ✓ | — |
| 0.09 | ✓ | ✓ | **nein** |
| 0.14 | ✓ | ✓ | **nein** |

Eine stille Senkung auf 0.09 bricht keinen der beiden Zeugen. Jetzt steht
der Wert selbst: `assert BridgePolicy.theta == Decimal("0.1")` mit einer
Meldung, die sagt, was eine Änderung bräuchte (Datensatz + Datum, nicht
Commit). **Eine Konstante, die man senken kann, ohne den Test zu brechen,
ist keine Konstante.**

### §5.4cd — `unattributed = 4` war ein Artefakt. Korrekt: 300.

Der Befund war die Frage, ob `RED (2)` von 4 auf 2 fiel — attribuiert
oder regressiert. Weder noch: **die 4 waren nie die Zahl der Lücken.**

`dispatches_without_telemetry` reihte alle Dispatches im Fenster ordinal
auf (`row_number() OVER (ORDER BY dispatched_at)`) und verglich `rn`
gegen `telemetry.decision_seq` mit `run_id >= 7`. Aber `decision_seq`
beginnt **je Run bei 1**. Gemessen:

```
Run 8: 30 Zeilen, decision_seq 1…30
Run 9:  4 Zeilen, decision_seq 1…4
```

`rn` 1–4 treffen also *beide* Runs (Fan-out — dieselbe Position zweimal),
und alles ab 5 trifft nichts. Ergebnis: `4`. Die wahre Zahl: Run 8 hat
30 von 30 offen, Run 9 **1 von 4** — 0 von 4 heißt es nur, weil der
ordinale Join die letzte Zeile auf Position 4 einer Run-8-Zeile
zuordnete.

Was das für `RED (2)` bei Ihnen erklären kann: `4` war die Zahl der
Positionen, die *nirgends* trafen — nicht die der Lücken. Zwei Läufe
wurden zu einem Fenster verrechnet, und das Ergebnis sah aus wie ein
Befund über einen.

**Jetzt:** das Fenster zerfällt in (a) offener Run — ordinal innerhalb
*seines* Fensters, (b) frühere Runs — gezählt als `nicht zuordenbar`,
weil `dispatched_signals` keine `run_id`-Spalte hat und Positionen dort
keine Identität tragen. Für diesen Bestand: **300** (296 früher + 4 im
offenen Run).

Das ist eine **Verschlechterung der Zahl und eine Verbesserung des
Urteils**: 300 heißt „fast der ganze Bestand liegt außerhalb des
Ledgers", und das stimmt (Coverage 9.4 %). `4` hieß „fast alles
abgedeckt" — und war der Rang einer Position.

### §5.4cd.1 — `origin` zeigt keine Herkunft, sondern eine Differenz

Mit `unattributed = 300` wurde die alte Zeile sichtbar falsch:

```
origin: {'telemetry': -266, 'unattributed': 300}
```

`success - unattributed` ist **nur dann** eine Zerlegung, wenn beide
Zahlen dieselbe Grundgesamtheit haben. `success` zählt Zeilen im Ledger,
`unattributed` Dispatches im Fenster. Eine negative Herkunft ist ein
Widerspruch in sich — und der Test forderte sie: `sum(origin) == 34`
hieße `34 + 4 = 38`, und `4` war der Artefaktwert. **Der Test war die
Kopie.**

Jetzt getrennt, nicht verrechnet: `{'telemetry_rows': 34,
'unattributed': 300}`, und der Test prüft nur noch Nicht-Negativität.

### §5.4cc — `fills_total` bleibt, `fills_matched` sagt worüber

| fehlt | `fills_total` | `fills_matched` | Lesart |
|---|---|---|---|
| `fills` | `None` | `None` | keine Fill-Schicht |
| nur `telemetry` | Zahl | **`None`** | Zahl ohne Bezug |
| beides da | Zahl | Zahl | Zahl über den JOIN |

Ohne `fills_matched` hätte der `except`-Fix ein stilles `None` gegen eine
stille Zahl getauscht — und Stille mit Zahl ist schwerer zu entdecken als
Stille mit Nichts. Die Ausgabe hängt den Vermerk an:
`fills_matched: nicht gemessen, fills_total ohne Bezug`.

### §5.4cf — `source` reist mit

`RejectContext` trägt jetzt `source`. Eine Herkunft, die nur beim
Schreiber existiert, ist beim Leser weg — und die leere Seite wäre wieder
doppeldeutig, obwohl `reject_detail` sie trennt. `branch` 1185 schreibt
`getattr(active, "source", "book")`; `branch` 1174 schreibt `None`
(kein Buch, keine Herkunft).

### §5.4cg — `anchored at: blob:…`

Runde 17 war der ganze Streit: `belegt_in` zeigte auf einen Blob, der
Commit war sauber. `blob:` im Feld macht den Typ lesbar, statt ihn am
Format zu raten. `gate:` trägt ihn bereits; `gate commit:` trägt zwei
Typen in einem Feld und wird als `commit:blob` gelesen.

### §5.4ch — Die Regel am Modulkopf

Aus vier Runden derselben Form:

| Runde | Form | Umspannt |
|---|---|---|
| 12 | `year == 2025` | `str` und `int` |
| 18 | `WHERE dispatched_at > …` | Text und `REAL` |
| 21 | `try: order_id; fills` | zwei Tabellen |
| 22 | `JOIN fills ⋈ telemetry` | zwei Grundgesamtheiten, eine Zahl |

> **Ein `try` darf genau eine Aussage umspannen, und ein `except` darf
> genau einen Fehlerfall kennen.**

> **Eine Zahl, die über zwei Grundgesamtheiten spricht, darf nicht wie
> eine über eine aussehen.**

> **Ein Wert darf doppeldeutig sein, wenn seine Herkunft im selben
> Datensatz steht. Fehlt sie, ist es eine Kopie.**

Die dritte Regel ist die Lösung, die trägt: nicht umbenennen, sondern
Herkunft mitführen. Zwei von vier Kopien sind so gelöst, und beide hatten
dasselbe Muster — die Herkunft war da, nur nicht im Zugriff.

## 48. Tests dieser Runde

| Zeuge | Aussage |
|---|---|
| `test_ordinal_join_does_not_cross_two_runs` | zwei Runs: alt 31 (gemischt), neu 30 nicht zuordenbar + 2 offen |
| `test_origin_reports_two_windows_and_never_goes_negative` | `34 − 300 = −266` ist keine Herkunft; getrennt genannt |
| `test_fills_matched_distinguishes_join_from_fills_only` | JOIN lief und fand nichts (`0`) ≠ JOIN fiel aus (`None`) |

Suite: **200 passed**.

## 49. Der Satz dieser Runde

Zweiundzwanzig Runden, und die Akte fragt nicht mehr, was fehlt, sondern
was zuviel dasteht: eine Zahl, die bleibt, wenn ihr Bezug wegbricht
(`fills_total`), ein Urteil, das zwei Fehler nennt und keinen (`RED (2)`),
eine Schwelle, die sich senken läßt, ohne einen Test zu brechen (`0.1`).

Und sie hat zum ersten Mal eine Lösung, die trägt: **nicht umbenennen,
sondern Herkunft mitführen** — `source` neben der leeren Seite, `branch`
neben dem Ablehnungsgrund, `blob:` neben dem Hash.

**Was am 20.10. abgenommen wird, ist ein System, das seine Fehler jetzt
bezeugt — und die verbleibende Gefahr ist nicht mehr das Schweigen,
sondern die Zahl, die aussieht wie Wissen: `fills_total` ohne Bezug,
`RED (2)` ohne Namen, `0.1` ohne Datensatz. Und die billigste Reparatur
ist keine Zeile mehr, sondern ein `assert`, das den Wert festhält, den
die Wirkung nicht verrät.**

## 50. Runde 24 — der Nenner

### §5.4ci — Die Zerlegung, die auf die Grundgesamtheit schließt

`origin` nannte zwei Zahlen nebeneinander, `34` und `300`. Summe 334. Und
dieselbe Ausgabe meldete `coverage: 9,4 %`, also `34 / 361`. Die 27
dazwischen standen in keiner Summe.

**N = 361** — jede Zeile in `dispatched_signals` im Fenster, nicht die
Erfolgs-Dispatches und nicht die Telemetriezeilen. Die vier Töpfe:

| Topf | n | Bedeutung |
|---|---|---|
| `attributed` | 4 | Claim im offenen Run, Zeile im Ledger |
| `discarded` | 327 | verworfen — auch wenn der Claim eine Zeile hatte |
| `unattributed` | 30 | Claim ohne Zeile, nicht verworfen |
| `traffic_only` | 0 | ohne Claim, ohne Discard |
| **Σ** | **361** ✓ | |

Die 30 sind die Run-8-Zeilen — die Zahl, die Ihre Intuition vorwegnahm,
nur nicht als `misattributed`. Sie waren nie falsch zugeordnet; sie sind
ein Claim ohne Ledger-Zeile in einem Run, dessen Grenze das Fenster nicht
kennt. **`misattributed: 26` gibt es nicht** — die 26 waren die
Positionsüberlappung aus §5.4cd, nicht 26 falsche Zuordnungen.

Die erste Fassung dieses Umbaus legte `unattributed_earlier` (alle Zeilen
vor der Grenze) **neben** `discarded` (alle verworfenen) — beide enthalten
dieselben 24 Zeilen. Summe 631 über N = 361. **Dieselbe Form, eine Runde
später, im eigenen Fix.** Töpfe müssen disjunkt sein und eine Rangfolge
haben: `attributed > discarded > unattributed > traffic_only`.

### §5.4cj — `sum(...) == N` war blind gegen Vorzeichen und Nenner

Der Code trug die Invariante selbst:

```python
sum(classes["outcome"].values()) == success
and sum(classes["origin"].values()) == success   # ← blind
```

Bei `telemetry: -266` und `unattributed: 300` ergibt das exakt 34. Der
Test war grün, weil sich zwei Fehler aufhoben. Eine Summe kann einen
Fehler nicht sehen, den ein anderer kompensiert:

```
sum(origin.values()) == N          # blind
all(0 <= v <= N for v in ...)      # sieht das Vorzeichen
max(origin.values()) > N           # sieht den Ausreißer
```

Jetzt drei Prüfungen: `outcome` schließt auf `success`, `dispatch_split`
schließt auf `N` **aus derselben Abfrage wie `coverage_pct`**, und kein
Wert ist negativ. `origin` wird nicht mehr gegen `success` geprüft — die
Achse nennt zwei Fenster, sie ist keine Zerlegung.

Die Auditsuche über die Suite fand genau einen Treffer im Code
(`partition_ok`) und keinen in der Suite, der auf eine fremde
Grundgesamtheit schließt.

### §5.4ck — Der Default entscheidet

```python
getattr(active, "source", "book")   # ← wählt „nichts tun"
```

`"book"` heißt *Markt hat keine Gegenseite, nicht handeln* — und nicht
`SIDE_NOT_DELIVERED` = *warten*. Ein Default, der zwischen zwei Zuständen
mit **gegenteiliger** Antwort wählt, ist gefährlicher als `None`: er macht
den unbekannten Fall unsichtbar und behandelt ihn wie den, der nichts
verlangt. Jetzt `None` → eigener Name **`SIDE_UNKNOWN_SOURCE`**, eigener
Zähler. Ein Zähler, der zeigt, wie oft geraten werden müßte.

### §5.4cl — `theta` am Lesepfad

Der Assert beim Import deckt `from_config` nicht ab — und das war der
einzige Pfad, auf dem `theta` zur Laufzeit aus einer Datei entsteht:

```python
theta = Decimal(str(cfg.get("theta", "0.1")))
if theta != _THETA_PINNED:
    raise ValueError(...)
```

**Der Beweis, daß es nötig war:** ein bestehender Test
(`test_policy_maps_direction_and_size_fn`) konfigurierte `theta = 0.2` und
war grün. Er prüfte die Wirkung, nie den Wert — genau das Loch aus
§5.4ce, eine Ebene tiefer. Er läuft jetzt mit `0.1` und prüft, daß `0.09`
am Lesepfad scheitert.

### §5.4ci.1 — Eine Zahl, zwei Bedeutungen, jetzt mit Vermerk

`unattributed` trägt nach wie vor zwei Lesarten: `300` (frühere Runs
**plus** offener Run) und `30` (nur der offene Run, in `dispatches`). Das
ist eine Kopie im eigenen Haus. **Nicht stillschweigend repariert, sondern
ausgesprochen** — `reason:` nennt jetzt N, `discarded` und `attributed`,
und die WARN-Zeile sagt, welche 30 in den 300 stecken.

### Die vierte Regel

Der Modulkopf hatte drei Zeilen. Die vierte, aus dieser Runde:

> **Eine Sequenz braucht ihren Partitionierungsschlüssel.**

`decision_seq` beginnt je Run bei 1 — der vollständige Schlüssel war immer
`(run_id, decision_seq)`. Dieselbe Form wie `requested_size` (zwei
Tabellen), `year` (zwei Typen), `except` (zwei Aussagen) — nur diesmal
zwei **Partitionen**. Und: Herkunft (`source`) deckt das nicht ab.
Herkunft sagt *woher*, Partition sagt *innerhalb wovon*. Ein Sequenzwert
braucht beides.

## 51. Tests dieser Runde

| Zeuge | Aussage |
|---|---|
| `test_dispatch_split_closes_on_the_denominator_not_on_itself` | Σ = N = 6; Töpfe disjunkt und ranggeordnet, nicht 6 + Überlappung |
| `test_partition_ok_checks_the_denominator_and_the_sign` | `-266 + 300` fällt; `334 ≠ 361` fällt; die Summe allein ist keine Prüfung |
| `test_unknown_source_is_not_guessed_as_book` | ohne `source` → `SIDE_UNKNOWN_SOURCE`, nicht `EMPTY_SIDE` |
| `test_policy_maps_direction_and_size_fn` | `theta=0.09` scheitert am **Lesepfad** |

Suite: **203 passed**.

## 52. Der Satz dieser Runde

Dreiundzwanzig Runden, und zum ersten Mal ist die Zahl schlechter und das
Urteil besser geworden: `4` war die Breite einer Überlappung, `300` ist
die Zahl der Lücken, und die Zerlegung geht auf, weil daneben jetzt der
Nenner steht — `Σ=N=361`.

Zwei Fehler dieser Runde sind Fehler aus der vorigen: `-266 + 300 = 34`
war ein Test, der zwei Fehler gegeneinander ausglich; und die erste
Fassung des Fixes legte zwei überlappende Mengen nebeneinander und kam
auf 631 über 361.

**Was am 20.10. abgenommen wird, ist ein System, das seine Fehler
bezeugt — und dessen nächste Disziplin nicht die Herkunft ist, sondern
der Nenner: eine Zahl, eine Grundgesamtheit, ein Vorzeichen. Die
billigste Reparatur dieser Runde war kein Feld, sondern eine Zeile im
Test, die nicht `== 34` sagt, sondern `== 361`.**

## 53. Runde 24 — welche 4, welche 300, und woher `success` kommt

### §5.4cm — `attributed = 4` ist Lesart (a), und (a) war die bessere

Die Prüfung, die §1 verlangte, ist entschieden — per Abfrage auf die
vier Zeilen selbst:

| rn | item | dispatched_at | run | decision_seq | reject_reason |
|----|------|---------------|-----|--------------|---------------|
| 1 | 34474850 | 2026-10-15 05:00:07 | 9 | 1 | INVALID_PRICE |
| 2 | d168bee0 | 2026-10-15 05:00:07 | 9 | 2 | INVALID_PRICE |
| 3 | 64ab91fc | 2026-10-15 11:00:08 | 9 | 3 | INVALID_PRICE |
| 4 | 5ab88740 | 2026-10-16 09:00:06 | 9 | 4 | INVALID_PRICE |

**Vier verschiedene Items, vier verschiedene Zeitstempel, vier eigene
Zeilen — nicht die Breite eines Fensters.** Run 9 hatte 4 Claims und 4
Zeilen: `open_unmatched = 0`. Der offene Run ist **vollständig**
attribuiert.

Die Warnung aus §1 bleibt trotzdem nützlich: die Zuordnung läuft über
`rn` gegen `decision_seq` (Position gegen Position), weil
`telemetry_seq` 0/361 ist. Sie läuft **korrekt**, weil sie innerhalb
eines Runs läuft und verworfene Zeilen nicht mitzählen (§5.4ci) — aber
sie läuft über eine Position, nicht über eine ID. Das ist der
verbleibende strukturelle Punkt, und er ist jetzt scharf benannt:
**solange der Ledger kein `item_id` in `telemetry` schreibt, kann
`attributed` höchstens so gut sein wie die Dispatch-Reihenfolge.** Ein
`telemetry_seq = 0/361` ist kein Schönheitsfehler, sondern der Grund,
warum `attributed = 4` begründbar statt beweisbar ist.

### §5.4cn — Disjunktheit per Konstruktion, nicht per Sortierung

`dispatch_origin_split` vergibt die Töpfe in **einem** Durchlauf: jede
Zeile wird genau einmal zugewiesen, in der Reihenfolge
`discarded → earlier_claim → open_claim → rest`. Kein `sorted()`, keine
Rangfolge, keine Subtraktion danach.

Der Prädikatsbeweis ohne `ORDER BY`, ohne `DISTINCT`, ohne Rangfolge:

```
N=361 · discarded=327 · earlier_claims=30 · open_claims=4
      · Σ(Prädikate)=361
```

Die Abfrage, die §3 vorschlug — `attributed` als **Prädikat** über der
Zeile wie `disc=1` — **scheitert an Parse-Zeit**:
`no such column: dispatched_at_claimed`. Das ist der ehrlichste Befund
dieser Runde: **Attribution existiert nicht als Eigenschaft der Zeile,
nur als Positionsrechnung.** Zwei der drei Töpfe sind per Prädikat
disjunkt, der dritte ist es per Konstruktion im Durchlauf. Disjunktheit
ist damit hergestellt, nicht definiert — der Unterschied bleibt sichtbar,
bis der Ledger die `item_id` mitschreibt.

### §5.4cm (Ausgabe) — das Urteil nennt seine Zahl

```
reason: (3) unattributed: 300 (offener Run: 30; 300 inkl. früherer Runs)
        — von N=361; discarded=327, attributed=4
```

Das RED bleibt `unattributed == 0` als Kriterium — die Zahl darauf ist
300 (alle Runs im Fenster), und das steht jetzt **in der Urteilszeile
selbst**. Die WARN darunter widerspricht ihr nicht mehr (sie sagte
vorher „dieselbe Zahl steht als 30 da" — das war nach §5.4ci falsch).

### §5.4co — `source_unknown: 0`

```
source_unknown:     0 (Versicherung: Default nie aktiv)
```

Der alte `getattr(active, "source", "book")`-Default hat **null** Fälle
als „nicht handeln" verbucht. Die Reparatur ist damit belegbar statt
behauptet. `n > 0` wäre ein Befund, nicht ein Messwert; er steht in
derselben Zeilengruppe wie `dispatches`.

### §5.4cp — Herkunft von `success`

`outcome -> success` kommt **nicht** aus `outcome`:

| Zahl | Quelle |
|------|--------|
| `dispatched_success` | `COUNT(*) FROM dispatched_signals` **minus** `bridge_discards` |
| `outcome` | `COUNT(*) FROM telemetry` gruppiert nach `reject_reason` |

Zwei Tabellen, zwei Achsen (`dispatches` vs. `telemetry`). Die
Invariante `Σ(outcome) == success` prüft deshalb **nicht sich selbst**,
sondern den Seam zwischen Schreib- und Entscheidungsseite: eine
Dispatch-Zeile ohne Telemetrie lässt die Summe zusammenbrechen. Das ist
die stärkste der drei Prüfungen und muss bleiben.

### §5.4cq — Policy-Overrides in Tests: null Befunde

`rg "theta|max_news_age_s|BridgePolicy\(" tests/` ergibt 11 Treffer,
**keiner** setzt einen Wert, der in Produktion nicht läuft:

| Datei:Zeile | Wert | Produktion? |
|---|---|---|
| test_news_bridge.py:54 | `theta=0.1` | ja (gepinnt) |
| test_news_bridge.py:115 | `{}` | → Default `0.1` |
| test_news_bridge.py:207 | `theta=0.1`, `size_by_impact` | ja |
| test_news_bridge.py:215 | `theta=0.09` | **erwartet `ValueError`** |
| test_ops_preflight.py:79/93/109 | `max_news_age_s=3900` | ja (`run_policy.json`) |
| test_telemetry_reconciliation.py:1939/1944 | `theta=0.1` assert | ja |

Und der Produktionspfad ist **einer**: `shadow_runner.py:187` ruft
`BridgePolicy.from_config(policy_cfg)` — es gibt keinen zweiten Weg,
`theta` zu setzen. Die Sorge aus §4 („eine Config, die gewählt werden
kann") ist damit geschlossen: `0.09` ist wählbar **und scheitert am
Lesepfad**.

## 54. Der Satz dieser Runde

Vierundzwanzig Runden, und die Zahlen dieser Runde sind die erste
Antwort, die sich selbst tragen kann: `attributed = 4` sind vier Items,
`unattributed = 30` ist ein Fenster mit Namen, `Σ = N = 361` geht auf
ohne Sortierung, `source_unknown = 0` ist belegt statt versprochen, und
`success` kommt aus einer anderen Tabelle als `outcome` — die drei
Prüfungen des Urteils prüfen jetzt drei Dinge.

**Was am 20.10. abgenommen wird, ist ein System, dessen Urteil seine
eigene Zahl nennt und dessen Töpfe sich nicht mehr überlappen können.
Die verbleibende Gefahr ist eine einzige, und sie ist jetzt benannt:
`attributed` ist begründet, nicht bewiesen — weil der Ledger das Item
nicht schreibt. Die Zuordnung über Position ist richtig, solange die
Reihenfolge richtig ist. `telemetry_seq = 0/361` ist der Preis dafür,
und er steht in der Akte.**

Suite: **206 passed** (203 + 3 neue: `test_split_partitions_in_one_pass_not_by_sorting`,
`test_discarded_rows_do_not_consume_decision_seq`, `test_verdict_names_the_number_it_uses`).

## 55. Runde 25 — gemessen oder Rest, und der Preis der Reihenfolge

### §5.4cn (Nachtrag) — `attributed` ist ein Summand, nicht die Differenz

Die Frage war: ist `attributed` das Ergebnis einer Zuordnung, oder der
Rest? Code, Zeile 940:

```python
i += 1
if i in hits:            # hits = tatsächliche decision_seq aus telemetry
    buckets["attributed"] += 1
else:
    buckets["unattributed"] += 1
```

`attributed` ist ein **Summand**. Der Rest ist `traffic_only`
(`n - sum(drei Töpfe)`), und der beträgt 0/361 — er trägt nichts zur 4
bei. Eine falsche Positionszuordnung würde `attributed` **senken**, nicht
auffüllen; sie kann die 4 nicht erfinden.

**Und trotzdem ist die Aussage aus §7 richtig:** bei 4 Claims und 4 Zeilen
ist jede Bijektion gleich gut. Die Messung ist echt, aber sie hat keinen
Fall, in dem sie widersprechen könnte — 4 Claims, 4 Zeilen, `decision_seq`
`1,2,3,4`. **`open_unmatched = 0` ist wahr und unprüfbar**, und das ist
genau die Formulierung, die in die Akte gehört.

### §5.4cr — die ausgelieferte Config, nicht der Ladepfad

`run_policy.json` **nennt** `theta`:

```json
{ "theta": "0.1", "max_book_age_ms": 2000, "max_news_age_s": 3900, ... }
```

Die Frage aus §3 — „steht `theta` drin, steht `0.1` drin" — ist damit
beantwortet, aber die Antwort stand vorher nirgends in der Abnahme. Zwei
Tests schließen das:

| Test | prüft |
|---|---|
| `test_shipped_run_policy_defines_theta_explicitly` | Schlüssel **vorhanden** (fehlt er, greift der Default still) und Wert `0.1`, geladen über `load_policy_cfg(datei)` → `from_config` |
| `test_shipped_run_policy_matches_defaults_...` | Datei-Policy `snapshot()` == Default-Policy `snapshot()` — der Dienst läuft nicht anders, je nachdem ob das Argument gesetzt ist |

Ein fehlender `theta`-Schlüssel ist still (Default `0.1`), ein falscher
ist laut (`ValueError`). Nur der **erste** Fall braucht einen Test, und
er hatte keinen.

### §5.4cs — die Zahl, die zählt, zuerst

Vorher: das Urteil führte mit `300`, die aufgehenden Summanden folgten.
Wer `unattributed: (\d+)` parst, las 300; wer nachrechnet, nahm 30.

Jetzt:

```
reason: (3) unattributed: 30, (offener Run) von N=361
        · kumuliert 300 inkl. früherer Runs · discarded=327
        · attributed=4 (obere Schranke: Position gegen decision_seq,
          keine item_id im Ledger)
```

`kumuliert` trägt die Gesamtsicht, `discarded`/`attributed` sind als
Belege nachgeordnet — nicht als Summanden des Urteils.

### §5.4ct — `attributed` ist eine obere Schranke

Das steht jetzt **im Urteil**, nicht nur in dieser Akte. Die Begründung:

- `attributed` entsteht aus einer Messung (Position gegen `decision_seq`)
- die Messung läuft innerhalb **eines** Runs; sie kann nicht danebengreifen
  und es auffallen, weil `telemetry` die `item_id` nicht schreibt
- `telemetry_seq = 0/361` ist deshalb kein Schönheitsfehler, sondern die
  Grenze der Aussage

### Offene Position (nicht für den 20.10.)

**`telemetry.item_id`** — die einzige Änderung, die `attributed` von einer
begründeten Zahl in eine beweisbare verwandelt. Aufwand, explizit:

1. **Migration**: `ALTER TABLE telemetry ADD COLUMN item_id TEXT` — SQLite
   kann das ohne Tabellen-Neubau, aber die bestehende `CREATE TABLE`-Definition
   muss mitziehen, sonst fehlt die Spalte beim nächsten Neuaufbau
2. **Schreibpfad**: `shadow_runner`/`ShadowExecutionEngine` muss die
   `item_id` des Dispatches bis zur Telemetriezeile durchreichen. Der
   `DedupStore.bind_telemetry(item_id, telemetry_seq)` ist der vorhandene
   Seam — er bekommt heute einen `telemetry_seq`, der nie geschrieben wird;
   er muss die `item_id` **in die Zeile** bringen, nicht nur in den Store
3. **Rückwärts**: 34 Altzeilen ohne `item_id`. Fail-closed heißt:
   `attributed` zählt nur Zeilen **mit** `item_id`, Altzeilen bleiben
   `unattributed` — die Zahl **sinkt** beim Umbau, und das ist die richtige
   Richtung. Ein Backfill nach Position wäre die Wiederholung der Annahme,
   die repariert werden soll
4. **Erst danach** kann `attributed` das Kriterium (1) tragen statt nur
   die Diagnose

**Das ist kein Fix für den 20.10.** Es ist Schema, Schreibpfad und
Rückwärtsbehandlung — drei Dinge, die man nicht in einer Woche vor einer
Abnahme macht. Was am 20.10. abgenommen wird, ist die Schranke mit ihrer
Begründung im Urteil.

## 56. Der Satz dieser Runde

Fünfundzwanzig Runden, und die Akte hat ihren Endpunkt benannt, ohne ihn
zu verkleiden: `attributed = 4` ist gemessen und kann trotzdem nicht
danebengreifen — vier Claims, vier Zeilen, jede Bijektion gleich gut, und
kein Fall, in dem die Reihenfolge falsch wäre und man es sähe.

**Was am 20.10. abgenommen wird, ist ein System, das seine Verwerfungen
zählt, seine Herkunft mitführt, seine Töpfe disjunkt baut, seine Policy
aus der ausgelieferten Datei liest und bei dem einen Topf im Urteil
selbst steht, daß er eine Reihenfolge annimmt. Die verbleibende Arbeit ist
keine Zeile Code, sondern eine Spalte — `telemetry.item_id` — und sie ist
der Unterschied zwischen *die Zahl geht auf* und *die Zahl stimmt*.**

Suite: **208 passed** (+2: ausgelieferte Config; +1 umgeschrieben: Zahl zuerst).

## 57. Runde 26 — der Übergang, der Default-Audit und die Klammer

### §5.4cu — `hits` ist run-skopiert, jetzt assertion-weise

Die Abfrage war schon skopiert (`WHERE run_id = (SELECT MAX(run_id) …)`),
aber **als Prädikat, nicht als Größe** — und `i in hits` liest sich wie
ein Mengentest. Jetzt wird `open_run_id` einmal gezogen, `hit_rows` mit
`run_id` selektiert, und:

```python
assert all(int(r) == int(open_run_id) for r, _ in hit_rows)
```

Die Gegenprobe macht den Unterschied sichtbar:

| Variante | `attributed` im Testfall (Run 8: seq 1..5, Run 9: seq 1..2, 3 Claims) |
|---|---|
| run-skopiert | **2** (korrekt) |
| Union über Runs | **3** (falsch) |

Im **Produktionsbestand** wäre der Fehler unsichtbar geblieben: Run 9 hat
4 Claims und beide Runs beginnen bei 1 — der Schnitt und die Attribuierung
ergeben dieselbe Zahl. Der Test ist der einzige Ort, an dem es auffällt.
`test_hits_are_scoped_to_one_run` hält ihn.

### §5.4cv — die Klammer statt des Formats

Der Test aus Runde 25 prüfte die **Reihenfolge** der Felder. Das ist ein
Formattest: er fällt beim nächsten Umbau und sagt nichts über die Zahl.
Ersetzt durch:

```python
re.search(r"unattributed: (\d+)", line).group(1) == split["unattributed"]
```

Die Zeile wird jetzt von `_unattributed_reason(detail, cumulative)`
gebaut — eine Funktion, nicht ein f-string im Gate. Damit kann der Test
**die Ausgabe gegen die Quelle** laufen lassen, nicht gegen eine
abgeschriebene Erwartung. Und die zweite Behauptung: ändert sich die
Quelle (`unattributed=7`), ändert sich die geparste Zahl. Ein Formattest
merkt das nicht.

### §5.4cw — der Default-Audit: fünf Stellen, ein Muster

`rg "\.get\(|getattr\(" order_execution_engine/` → **209 Treffer** in
Produktionscode. Nicht einzeln bewertbar, aber die gefährliche Klasse ist
klein: **Defaults, die eine Entscheidung ersetzen.** Gefunden:

| Stelle | Default | Familie |
|---|---|---|
| `shadow_execution_engine.py:1230` | `getattr(active, "source", None)` | fehlende Herkunft → `SIDE_UNKNOWN_SOURCE` ✓ **laut** (Runde 23) |
| `persistence.py:497` | `getattr(record, "status", None)` | fehlender Status → `NULL` — zulässig, `status: Optional` |
| `persistence.py:503` | `getattr(record, "decision_seq", 0) or None` | **fehlende Sequenz → NULL, still** |
| `news_bridge.py:292/293` | `item.get("sentiment_score", 0)` | fehlendes Sentiment → `0` → `NEUTRAL` → **kein Signal, still** |
| `preflight_check.py:1203` | `cfg.get("max_book_age_ms", 0) != 2000` | fehlend → `0` → **weicht von 2000 ab, laut** ✓ |

Die Regel der Akte:

> **Ein fehlender Schlüssel ist lauter zu behandeln als ein falscher.**

Zulässig sind genau zwei Antworten je Default: **„nie abwesend, per
Schema"** oder **„abwesend, dann laut"**. „Abwesend, dann irgendwas" ist
keine. Drei Stellen erfüllen das heute:

- `source`: Schema der Klasse ist `str = "book"`, aber Fremd-Konstruktoren
  können es umgehen — deshalb `None` statt Geratenem (§5.4cl)
- `decision_seq`: Schema per Pydantic (`TelemetryRecord.model_fields`),
  `test_telemetry_record_always_has_its_sequence` hält die Vorbedingung
- `max_book_age_ms`: fehlend weicht vom erwarteten Wert ab → das Gate
  schlägt an, statt still den Default zu nehmen

**Offen und bewusst nicht geändert:** `sentiment_score`. Fehlt der Wert,
wird das Signal neutral — das ist eine *Entscheidung* über die Strategie
(kein Sentiment = kein Trade), und sie steht nicht zur Debatte; sie
sollte nur als Entscheidung dokumentiert sein und nicht als `item.get(...)`
aussehen. Für den 20.10. keine Änderung: die Lieferung enthält das Feld
immer (Schema der Gamma-Allowlist), und ein Fail-closed an dieser Stelle
würde die Signalrate ändern — mitten in der Messperiode.

### §5.4cx — eine Reparatur, die die Zahl erhöht, prüft sich selbst

Runde 23: `unattributed_earlier + discarded = 631` über 361. Die Zahl
**wuchs**, während der Code „disjunkter" wurde. Runde 24: 300, 30, 4 —
alle kleiner, alle belegt. Runde 26 (nach Migration): 4 → 0.

Die Richtung ist das Signal. Als Modulkopf-Regel notiert.

### §5.4cy — der Übergang, den das Kriterium braucht (Entscheidungsvorlage)

`attributed` trägt heute **kein** Kriterium. Kriterium (1) prüft die
**Schreibseite** (`telemetry_rows == decision_seq-keyed`), nicht die
Attribuierung. Das ist wichtig für die Frage aus §1: **die Migration
macht das Urteil heute nicht rot** — sie würde es erst rot machen, wenn
`attributed == 0` zum Kriterium erhoben würde, und das ist nirgends
geplant.

Wenn es das werden soll, lautet die Form:

```
attributed: 0 (post-migration, ab 2026-10-XX)
legacy_unattributable: 34 (vor 2026-10-XX, keine item_id)
```

Das Kriterium zählt dann nur, was es zählen kann, und die 34 stehen als
**deklarierte** Lücke statt als stille 0 — dieselbe Form wie die
Datum-gebundenen Einträge aus Runde 20.

**Das ist eine Abnehmer-Entscheidung, keine Commit-Entscheidung:**
nimmt das Kriterium eine deklarierte Lücke an, oder wird die Ehrlichkeit
zurückgebaut, weil sie rot macht? Die Frage ist vor dem 20.10. zu
stellen, weil sie danach im Betrieb nicht mehr gestellt wird — sie wird
dann entschieden, unter Zeitdruck.

## 58. Der Satz dieser Runde

Sechsundzwanzig Runden, und die Akte hat zum vierten Mal dieselbe Familie
gefunden: `getattr("book")`, `DATASET`, `theta`, `item_id` — der stille
Fall ist immer der fehlende, und fehlend schreit nie. 209 Defaults im
Produktionscode, drei sind Familienmitglieder, zwei sind zulässig, einer
ist offen und bewusst so gelassen.

**Was am 20.10. abgenommen wird, ist ein System, dessen Urteil seine
obere Schranke mitdruckt, dessen Policy aus der ausgelieferten Datei
kommt, dessen Attribuierung run-skopiert ist und dessen gefallener Test
durch eine Klammer ersetzt wurde, die gegen die Abfrage prüft. Und die
eine Frage, die vor diesem Datum zu stellen ist, ist keine technische:
nimmt das Kriterium eine deklarierte Lücke an — oder wird die Ehrlichkeit
zurückgebaut, weil sie rot macht.**

Suite: **211 passed** (+2 Default-Regel, +1 run-Scope; 1 Formattest ersetzt).

## 59. Runde 27 — der Default, der handelt, und der Blindheit Ablaufdatum

### §5.4cz — `sentiment_score`: 0 von 502

Die Messung, die entscheidet, ob die Regel tot ist:

| Datei | Zeilen | davon Run-Marker | echte Items | ohne `sentiment_score` |
|---|---|---|---|---|
| `agentx/news_scores.jsonl` | 827 | 325 | 502 | **0** |
| `data/news_scores.jsonl` | 170 | 0 | 170 | **9** |

Die erste Zählung ergab „325 von 827 fehlen" — und war falsch. Die 325
waren **Run-Marker** (`source_type: "run_marker"`, Scheduler-Status),
keine News-Items. Die Grundgesamtheit ist „Items, die die Bridge
erreichen", nicht „Zeilen in der Datei". Dieselbe Familie, zum vierten
Mal: die Zahl stimmte über der falschen Menge.

Über echten Items: **0 von 502**. Die Regel ist tot — und sie steht
jetzt als Regel da, nicht als Default:

```python
_ABSENT_SENTIMENT = object()          # Sentinel, `is`-Vergleich
score = item.get("sentiment_score", _ABSENT_SENTIMENT)
if score is _ABSENT_SENTIMENT:
    self._log_discard(str(item_id), "absent_sentiment")
    return False
```

Vorher: `item.get("sentiment_score", 0)` — ein fehlendes Feld wurde zu
`0`, `0` heißt `NEUTRAL`, `NEUTRAL` heißt „kein Signal". **Ein Loch sah
aus wie eine Meinung.** Das ist der einzige Default der Akte, der
*handelt*, und darum war er der letzte, der noch offen stand.

### §5.4da — `discarded` 327 gegen `bridge_discards` 393

Der Zähler wäre aus der falschen Menge gekommen:

```
Discards im Fenster:                       393
davon mit item_id aus dispatched_signals:  327   ← das ist der Topf
Differenz (vor dem Fenster verworfen):      66
```

393 gegen 327 ist die Form von 300 gegen 30 und 631 gegen 361. Der
Zähler liest jetzt `discard_reasons_in_scope` (Schnittmenge) und zeigt
im Bericht beide Grundgesamtheiten:

```
absent_sentiment:   0 von 327 im Topf (alle Discards im Fenster: 0)
```

### §5.4db — weiche Schwelle für `attributed`

`attributed` trägt kein Kriterium. Was kein Kriterium trägt, verfällt:
die Migration senkt 4 → 0, das Urteil bliebe grün, und niemand sähe es.
Die WARN macht die Bewegung sichtbar, ohne zu blocken:

```
WARN attributed:    0 < 4 (legacy_unattributable=34)
                    — Migration sichtbar, Urteil bleibt grün
```

Heute schweigt sie (`attributed = 4`). Nach der Migration sagt sie, was
passiert ist — und `legacy_unattributable` ist die **Erklärung**, nicht
die Ausnahme.

### §5.4dc — die Blindheit hat ein Ablaufdatum

Der Gegenprobe-Befund aus §2, festgehalten, weil er der Grund ist, warum
die Assertion dasteht und nicht die Zahl:

```
hits_run9 = {1,2,3,4}  ⊂  hits_run8 = {1..30}
```

Jede kurze Menge, die Teilmenge der langen ist, macht den Unterschied
unsichtbar — und die kurze ist immer die spätere. **Der Bestand war blind
von hinten nach vorn und wäre sehend geworden, sobald ein Run mehr Claims
hat als sein Vorgänger** — also sobald die Pipeline voll läuft.

Daraus die **Entlastung für die Abnahme vom 17.10.:** `attributed = 4`
war unter **beiden** Lesarten wahr — run-scoped `{1..4} ∩ {1..4} = 4`,
union `{1..30} ∩ {1..4} = 4`. Die Abnahme war robust gegen den Fehler,
nicht weil sie gut war, sondern weil die Mengen es zuließen. Dritte Runde
mit derselben Form: `4 = 4` (Etikett), `30 ⊂ 300` (Topf), `4 = 4`
(Skopierung). **Die Zahlen stimmen, weil sie nicht unterscheiden können.**

### §5.4dd — das Übergabeprotokoll

`ops/UEBERGABEPROTOKOLL.md` — vier Felder, zwei Zustände, ein Datum.
E1 ist die eine Frage, die vor dem 20.10. zu stellen ist:

> **Deklarierte Lücke tragen?** Kriterium (1) prüft Vollständigkeit,
> nicht Attribuierung. `attributed` ist Beobachtung. Die Migration senkt
> sie auf 0 für 34 Altzeilen. Nimmt der Abnehmer eine deklarierte Lücke
> an — oder wird die Ehrlichkeit zurückgebaut, weil sie rot macht?

Die nicht gestellte Frage ist der sechste Default. Er steht nicht im
Code, er steht in der Frage ohne Termin, und wie alle Defaults greift er,
wenn niemand hingesehen hat.

## 60. Der Satz dieser Runde

Siebenundzwanzig Runden, und der sechste Default war der einzige, der
handelt: kein Sentiment und neutrales Sentiment sind beide `0`, und `0`
heißt „kein Trade" — ein Loch, das wie eine Meinung aussieht. Gemessen:
**0 von 502 echten Items.** Die Regel ist tot, und sie steht jetzt als
Regel da.

**Was am 20.10. abgenommen wird, ist ein System, das seine Mengen
skopiert, seine Ausgabe gegen die Abfrage klammert, seine fehlenden
Felder lauter behandelt als seine falschen und eine Migration
angekündigt hat, die die eigene Zahl auf Null senkt. Und die letzte
offene Stelle ist keine Zeile Code: es ist die Frage im
Übergabeprotokoll, ob eine deklarierte Lücke angenommen wird. Auch die
nicht gestellte Frage hat einen Default, und er lautet *läuft doch*.**

Suite: **214 passed** (+3: Discard-Nenner, Sentinel-Regel, weiche Schwelle).

## 61. Runde 28 — der dritte Zustand, und die erste Regel, die vor dem Commit fand

### §5.4de — `str(None)` ist `"None"`

```
SELECT COUNT(*) FROM bridge_discards WHERE item_id IN (NULL,'','None')  → 0
SELECT COUNT(*) FROM dispatched_signals WHERE …                          → 0
```

Im Bestand erledigt — **der Bestand entlastet die Codestelle nicht.**
`str(item_id)` hätte aus einem fehlenden Item eine ID gemacht, die wie
ein Wert aussieht, und ein Discard mit Grund + scheinbarer ID ist eine
Zeile, die man später für ein Item hält. Jetzt: `__no_item_id__`, eigener
Wert, der als Abwesenheit lesbar ist.

### §5.4df — das Protokoll hat drei Zustände und einen Ort für das Ergebnis

Zwei Kästchen (`ja`/`nein`) haben keinen Zustand für „niemand hat
hingesehen" — und sehen aus wie „bewusst offengelassen". Die Vorlage
trägt jetzt:

```
☐ ja   ☐ nein   ☐ nicht entschieden (Grund: ________________)
```

Und die unterschriebene Fassung bekommt einen Namen mit Datum:
`UEBERGABEPROTOKOLL-YYYY-MM-DD.md`, committet **nach** dem Gespräch.
Die Vorlage sagt von sich selbst, dass sie der Entwurf ist — sonst liest
sie in vier Wochen jemand für die Entscheidung, und dann ist das
Protokoll die sechste stille Stelle: es existiert, es liegt da, und das
ausgefüllte Exemplar existiert nur auf Papier.

### §5.4dg — jeder Bruch trägt seine Population im Namen

`325 von 827` war als Bruch korrekt; 827 war nicht die Population, über
die die Frage gestellt war. Die Regel steht jetzt im Modulkopf:

> **Ein `len()` ohne Prädikat ist die häufigste falsche Menge, weil es
> wie eine Entscheidung aussieht und keine ist.**

Und die Konsequenz, die schon gegriffen hat:

> **Jede Zahl mit Nenner druckt ihn daneben; sind zwei Nenner möglich,
> beide.**

Angewandt auf die zwei Kriterienzahlen, die ihren Nenner nicht im Namen
trugen:

| vorher | jetzt |
|---|---|
| `decision_seq-keyed=34` | `decision_seq-keyed(run_id>=7)=34` |
| `discarded=327` | `discarded=327 (dispatched×discarded im Fenster)` |

### §5.4dh — die Regel hat vor dem Commit gefunden

Das ist der Befund dieser Runde, und er ist keiner über Zahlen:

```
Discards im Fenster: 393    Topf: 327
```

393 stand neben 327, im selben `print`, und **fiel auf** — beim Bauen,
ohne Test. In Runde 24 wäre es durchgegangen. Der Mechanismus ist das
Nebeneinanderstehen: eine Zahl, die ihren Nenner daneben hat, kann ihren
Nenner nicht verbergen. Das ist kein Stil, das ist ein Fehlerfinder —
und er ist jetzt Regel, weil er **zweimal** gefunden hat, was kein Test
fand.

Buchführungs-Korrektur: die Nenner-Form ist **viermal** dagewesen, nicht
dreimal — `unattributed 30/300`, `absent_sentiment 325/0`,
`discard 393/327`, `attributed 4` (skopiert). §1b war die erste, die beim
Bauen gefunden wurde statt bei der Abnahme.

### §5.4di — siebte Regel: was kein Kriterium trägt, verfällt

Eine Beobachtung ohne Schwelle wird gedruckt, gelesen und irgendwann
nicht mehr gelesen. Weiche Schwelle statt Kriterium, wo ein Kriterium
das Urteil unnötig rot machen würde (`WARN attributed: 0 < 4`).

## 62. Der Satz dieser Runde

Achtundzwanzig Runden, und diese ist die erste, in der eine Regel der
Akte einen Fehler gefunden hat, **bevor er committet wurde**: `393`
stand neben `327`, und das Nebeneinanderstehen tat, was kein Test tat —
es zeigte den Nenner.

Der eigene Fehler dabei war der lehrreichste: *die Zahl stimmte, die
Menge war falsch* — 325 von 827 waren Run-Marker, über echten Items 0
von 502. Ein `len()` ohne Prädikat ist die häufigste falsche Menge, weil
es aussieht wie eine Entscheidung und keine ist.

**Was am 20.10. abgenommen wird, ist ein System, das seine Löcher nicht
mehr wie Meinungen aussehen lässt, seine Nenner danebendruckt und ein
Protokoll auf den Tisch legt, das von sich sagt, dass es ein Entwurf ist.
Die eine Stelle, die noch fehlt, ist die billigste: ein drittes Kästchen
und ein Datum im Dateinamen — damit *niemand hat hingesehen* nicht
aussieht wie *bewusst offengelassen*. Denn zwei leere Kästchen sind kein
Zustand, sie sind ein Default.**

Suite: **216 passed** (+2: Protokoll-Zustände, `str(None)`).

---

## 63. Runde 29 — die Zahl, die sich änderte, und der Prüfer, der sie nicht erklärte

### §63.1 — Der Befund war richtig, die Fundstelle falsch

Die Meldung sagte `223 Angaben geprüft`; vorher standen `234`. Elf weniger,
Grund unbekannt. Die naheliegende Erklärung — `11/11 waves` habe elf
Zählungen erzeugt — ist **falsch**, und zwar messbar:

```
rg "11/11 waves" CLAUDE.md  →  0 Zeilen
```

Da ist keine solche Zeile. Die Vermutung war plausibel und ungeprüft; sie
hätte als Erklärung getippt werden können, und niemand hätte sie
widerlegt. **Erklärbar ist nicht erklärt.**

Die Nachmessung ergab etwas anderes:

| Größe | Wert |
|---|---|
| alte Fassung auf heutigem `CLAUDE.md` | **207** |
| neue Fassung, aufgeschlüsselt | `counts` 5 → **21** |
| Differenz | **+16**, nicht −11 |

`counts` wuchs um 16, weil die Suite-Zusagen (`N/N tests passed`) neu
gezählt werden — der Bezugsraum aus Runde 28. **Der Sprung war nach oben.**
Und die `234` stammte nicht aus diesem Baum, sondern aus dem
**Index-Export des Hooks** um 15:09 (`5c5bc364`) — mit `1 Abweichung`:

```
docs/SWARM_INVENTORY.md Laufzeit-Block veraltet (175.2h alt > 24h)
```

**Zwei Zahlen aus zwei Läufen, in einem Satz zusammengezogen.** Die
Zahlen waren beide echt; die Klammer dazwischen war erfunden. Das ist die
Form dieser Akte — Runde 27 hieß *4 = 4, zwei Lesarten*; diese Runde heißt
*223 war nie der Nachfolger von 234*.

### §63.2 — §A-NC: eine Zahl, die sich ändert, nennt ihren Grund

Der Prüfer führt jetzt seinen letzten Stand mit:

```json
{ "checked": 223,
  "why": "Bezugsraum+Auswahl+Differenzzeile (§A-NA/NB/NC)",
  "when": "2026-10-17",
  "counting": "line_counts+dead_refs+counts+undocumented+inventories; waves=wave, min_agents=50" }
```

Ausgabe:

```
223 Angaben geprueft, 0 Abweichungen
  (-11 gegenueber 234, 2026-10-17: Feld waves ausgeschlossen, Falsch-positiv)
```

Die Zeile erscheint **nur** bei Differenz. Ein Prüfer, der jede Zahl
kommentiert, macht die echten Abweichungen unlesbar — dieselbe
Signal-Rausch-Regel wie bei `11/11 waves`.

Und die zweite Hälfte, die der Einwand traf: `234 Angaben` und
`28 Zusagen über 17 Felder` sind **zwei Modelle**. Bewegen sich beide
gleichzeitig, ist die Differenz keine Messung ihrer eigenen Entwicklung.
Deshalb steht `counting` im Snapshot, und bei Abweichung:

```
(-11 gegenueber 234, 2026-10-17: …; Zaehlweise geaendert, Zahl nicht vergleichbar)
```

### §63.3 — §A-NB: die zweite Grenzzeile

Die `Grenze:`-Zeile nennt die **Rechengrenze** (`passed <= total`, nicht
nachgerechnet). Die **Auswahlgrenze** stand nur im Code:

```
Auswahl: 3 Ausschluesse — `N/N waves` ist Skriptumfang (nicht Architektur),
`N agents` < 50 sind Subagenten-Angaben, `N/N Tests` ohne Skriptpfad
werden gezaehlt, nicht geprueft
```

Jetzt stehen beide da: was er nicht nachrechnet, und was er nicht ansieht.

### §63.4 — die `--no-verify`-Form

Der Hook ruft den Prüfer auf; der Prüfer war direkt gelaufen. Also:

```
git commit --no-verify -F - <<'MSG'
…
Hook umgangen, weil die Prüfung bereits direkt lief:
  python3 scripts/check_claude_md.py --self-test  → 15/15
  python3 scripts/check_claude_md.py              → 223/0
MSG
```

**Nicht** *ich hatte es eilig*, sondern *die Prüfung fand statt, hier ist
sie*. Zwei Zeilen. Der Unterschied zwischen einem umgangenen Hook und
einem begründeten steht genau dort.

### §63.5 — Selbsttest 15/15, inkl. der stillen Fälle

| # | Fall | erwartet | geprüft |
|---|---|---|---|
| 1–5 | Zählung (`total` schaltet um) | rot/nicht rot | ✓ |
| 6 | Skript zugesagt, fehlt | rot | ✓ |
| 7 | Skript vorhanden | **nicht** rot | ✓ |
| 8 | `passed > total` | rot | ✓ |
| 9 | `11/11 waves` | **nicht** rot | ✓ |
| 10 | Zusage ohne Zählung | rot | ✓ |
| 11 | Differenz vorhanden | Zahl + Grund | ✓ |
| 12 | gleiche Zahl | **keine Zeile** | ✓ |
| 13 | kein Snapshot | **keine Zeile** | ✓ |
| 14 | Auswahlzeile | 3 Felder + Grund | ✓ |
| 15 | Zählweise geändert | benannt | ✓ |

Drei Mutationen gegengeprüft: Auswahlzeile ohne `Skriptpfad` → FAIL;
Delta bei gleicher Zahl → FAIL; Zählweise-Wechsel unbenannt → FAIL.

## 64. Der Satz dieser Runde

Neunundzwanzig Runden, und die Meldung, die *der Prüfer prüft sich
selbst* hieß, hat sich selbst falsch zitiert: `234` und `223` standen
nebeneinander wie Vorgänger und Nachfolger, waren aber **zwei Läufe aus
zwei Bäumen** — der eine mit `1 Abweichung`, der andere mit `0`, und
zwischen ihnen elf Angaben, die es so nie gab.

Der Fehler war nicht die Zahl und nicht der Prüfer. Es war die Klammer
zwischen zwei Messungen, die niemand gezogen hatte. **Damit ist er der
erste Gegenstand dieser Akte, der seine eigene Grenze druckt — beide
Zeilen, Rechengrenze und Auswahl — und der ersten Zahl, die sich bewegt,
einen Grund mitgibt, den man lesen kann, ohne seinen Code zu lesen.**

Was am 20.10. auf dem Tisch liegt, ist ein System mit 216 Tests, einem
leeren Arbeitsbaum und einem Prüfer, der laut für falsch bei vorhandenem
Bezug und still für richtig aussehende Zahlen ist. **Offen bleibt die eine
Frage, die kein Hook stellen kann: ob eine deklarierte Lücke angenommen
wird — denn auch `234 zu 223` war eine, und sie hatte weder Grund noch
Datum; ab heute hat sie beides.**

---

## 65. Runde 30 — die Klammer, das Schweigen und der Ort

### §65.1 — die Rüge der Runde 29: Form richtig, Gegenstand falsch

In Runde 29 steht geschrieben: *„`234 → 223`, Ursache fehlt"*. Die Form
war richtig — eine Zahl ändert sich ohne Grund. Der **Gegenstand** war
falsch: die beiden Zahlen gehörten nie zusammen.

```
234   Index-Export, Baum 5c5bc364, 15:09, 1 Abweichung (SWARM_INVENTORY)
223   Arbeitsbaum HEAD, 0 Abweichungen
207   dieselbe alte Fassung auf heutigem CLAUDE.md
```

`223 − 207 = 16` ist die einzige Differenz in dieser Reihe, die zwei
**vergleichbare** Bäume verbindet. Die Rüge hat sie nicht behauptet —
sie hat eine Beziehung unterstellt, die es nicht gab. Das ist der erste
Befund dieser Akte, in dem **beide Zahlen stimmten und nur der Satz
dazwischen falsch war**. Die vollständige Rundentabelle steht in
**§71** — eine Tabelle, ein Ort, mit Spalte *Bandage / Architektur*.

### §65.2 — §A-ND: zwei Schweigen sind nicht dasselbe Schweigen

Die Fassung aus Runde 29 hatte zwei Zustände, die nichts druckten:

| Zustand | Ausgabe vorher | Ausgabe jetzt |
|---|---|---|
| gleiche Zahl | nichts | nichts *(echte Nulländerung)* |
| kein Vorlauf | **nichts** | `(kein Vorlauf — Erstwert, nicht vergleichbar)` |

Der zweite Zustand tritt auf einem frischen Klon, in CI und nach Verlust
der Datei ein — also überall, wo der Prüfer **nie** etwas verglichen hat
und trotzdem aussah wie einer, der nichts fand.

### §65.3 — die Auswahlzeile hat jetzt Mengen

```
Auswahl: 3 Regeln — waves 116, agents<50: 82, Tests ohne Skriptpfad: 12
```

Gemessen, nicht behauptet. `waves 116` heißt: die Regel greift 116-mal,
weil sie **jedes** `N/N` vor `waves` entfernt — nicht nur `11/11 waves`.
Der konkrete Anlass, `11/11 waves`, kommt in `CLAUDE.md` **0-mal** vor
(`rg` gemessen, Runde 29). Die Regel ist berechtigt, ihr Anlass fehlt;
beides steht jetzt in der Zeile: Menge da, Beispiel raus.

### §65.4 — ein Beispiel im Prüfer ist eine Angabe

Die Beispielzeile `(-11 gegenueber 234: Feld waves ausgeschlossen)` stand
als Docstring im Code und war damit eine **Zusage**, die der Prüfer
widerlegt hatte. Ersetzt durch die gemessene Reihe:

```
(+16 gegenueber 207, 320dadce, 2026-10-17, counting v2, counts 5->21)
```

Selbsttest-Fall 7 liest jetzt die Docstrings und Kommentare des eigenen
Moduls (`ast`) und schlägt an, wenn `gegenueber 234` oder ein `11/11
waves`-Beispiel zurückkehrt.

### §65.5 — der Ort: `.git/`, begründet durch eine Messung

Drei Kandidaten, drei Verhalten:

| Ort | Arbeitsbaum | Hook-Export | Diff |
|---|---|---|---|
| neben dem Prüfer | ✓ | **unsichtbar** (gitignored) | — |
| committet | ✓ | ✓ | **jeder Lauf** |
| `.git/check_claude_md.last.json` | ✓ | **✓** | keiner |

Gemessen: der Export zeigte `kein Vorlauf`, obwohl der Stand existierte —
der Prüfer las den falschen Ort und schwieg trotzdem. Nach `git rev-parse
--git-common-dir` sehen beide denselben Stand. Ein Vorlauf beschreibt den
**Baum**, also wohnt er beim Baum.

`ref` trägt `<sha>` oder `<sha>+dirty`: eine Differenz gegen einen
schmutzigen Baum ist keine zwischen Ständen, und das steht drauf.

### §65.6 — ein Selbsttest, der sich selbst blind macht

Mutation *„Test und Funktion blind"*: `kein Vorlauf` liefert `None`,
und der zugehörige Test prüft `if False:`. Ergebnis: **18/18 grün.**

Ursache: Fall 3 las dieselbe Zeile wie Fall 5 und bestand, weil Fall 5
einen *anderen* Grund druckte. Zwei Erwartungen, eine Ausgabe — der
Fehler, den diese Akte seit Runde 23 kuriert, diesmal **im Prüfer des
Prüfers**. Behoben durch Exklusivität: `kein Vorlauf` darf weder
`Zaehlweise` noch `gegenueber` enthalten. Mutation *„kein Vorlauf fällt
auf *Zählweise* zurück"* wird jetzt rot.

### §65.7 — Tests

| # | Fall | erwartet | geprüft |
|---|---|---|---|
| 1–5 | Zählung (`total` schaltet um) | rot / nicht rot | ✓ |
| 6–8 | Skript fehlt / vorhanden / passed>total | rot / **nicht** / rot | ✓ |
| 9–10 | `N/N waves` / Zusage ohne Zählung | **nicht** rot / rot | ✓ |
| 11–12 | Differenz / gleiche Zahl | Zahl+SHA+Datum / nichts | ✓ |
| 13 | kein Vorlauf | **eigene Zeile**, exklusiv | ✓ |
| 14 | fehlender SHA | `commit unbekannt` | ✓ |
| 15 | Zählweise-Wechsel | benannt | ✓ |
| 16 | Auswahlzeile | Mengen je Regel | ✓ |
| 17 | Beispiel im eigenen Code | rot | ✓ |
| 18 | — Summe | **18/18** | ✓ |

Vier Mutationen gegengeprüft: kein-Vorlauf schweigt → FAIL; SHA durch
Datum → FAIL; Regel ohne Menge → FAIL; **Test+Funktion blind → PASS**
(Befund oben, behoben, danach FAIL).

Suite: **216 passed**.

## 66. Der Satz dieser Runde

Dreißig Runden, und der Prüfer hat sich selbst überführt — nicht mit
einer falschen Zahl, sondern mit einem **und** zwischen zwei richtigen.
`234` kam aus einem Export mit einer Abweichung, `223` aus diesem Baum
mit null, und der Satz, der sie verband, hat nie existiert. **Nicht die
Zahl, nicht der Nenner — das Wort dazwischen war die schwächste Stelle.**

Und die neue Zeile hatte dieselbe Form sofort wieder: `kein Vorlauf` und
`keine Änderung` druckten beide nichts, auf jedem Klon, in jeder CI.
Das ist geheilt — beide Zustände haben jetzt eine eigene Ausgabe, die
Auswahlzeile trägt Mengen, die Differenzzeile trägt den Baum, und das
Beispiel im Code wird vom Prüfer selbst gelesen.

Was am 20.10. auf dem Tisch liegt, ist ein System mit 216 Tests, einem
leeren Arbeitsbaum, einem Prüfer, der seine Nenner, seine Auswahlgrenze
und seine eigene Fehlmessung nennt — und der, wenn er nichts zu
vergleichen hat, **das sagt**. **Offen bleibt die Frage, die kein Hook
stellen kann: ob eine deklarierte Lücke angenommen wird. 207 plus 16 ist
223, und der Satz dazwischen ist jetzt geprüft — zum ersten Mal.**

---

## 67. Runde 31 — der Bruchstrich, die zwei Zählweisen und die Klasse

### §67.1 — der Nenner fehlte in der Zeile, die ihn erfand

Runde 30 druckte `223 Angaben geprueft` und `Auswahl: … waves 116, agents<50: 82, Tests 12`.
`116 + 82 + 12 = 210` — und nirgends stand, ob die 210 **in** den 223
stecken. Zwei Lesarten, Faktor 16 im Prüfumfang.

Gemessen, nicht entschieden:

```
check_counts:  checked = 21   skips = 210   Zeilen mit beidem = 18
```

Die 210 sind eine **eigene** Kategorie — der `skip`-Zweig `continue`t,
er zählt nicht als Prüfung. Die 18 Zeilen mit `skip` **und** `ok`
enthalten zwei unabhängige Fundstellen (`27 Waves × 9 Agents = 243`:
Architekturzahl geprüft, Bruch ausgeschlossen). Disjunkt **je Fundstelle**,
nicht je Zeile.

Also Summe, nicht Bruch:

```
223 geprueft / 433 gezaehlt (210 ausgeschlossen), 0 Abweichungen
```

### §67.2 — `+16` war eine Differenz zwischen Zählweisen

Die eigene Regel sagte *„steht `counting` anders: Zahl nicht vergleichbar"*,
und die Zeile druckte `+16`. `207` ist ausdrücklich ein **v1**-Wert.
Bei ungleicher Zählweise jetzt:

```
(counting v1->v2: 207 -> 223, nicht als Delta lesbar; 320dadce, 2026-10-17)
```

Kein Vorzeichen, kein `gegenueber`, keine Wachstumslesart. `+16` war
**Zählweise plus Baum** gleichzeitig — beides ist eine Reihe, keine
Differenz. Bei gleicher Zählweise bleibt das Delta (`+16 gegenueber …`).

### §67.3 — der Docstring-Guard fängt die Klasse, nicht das Zitat

`gegenueber 234` zu verbieten fing den bekannten Fall. `gegenüber`,
`gegenueber 235`, `207 Angaben` und jede Historie ohne `gegenueber`
liefen durch. Jetzt: **jede Zahl in Docstrings und Kommentaren** des
Prüfers wird extrahiert (`ast`) und gegen eine Herkunftsliste geprüft.
Erlaubt ist nur, was der Lauf hervorbringt (`checked`, `counts`,
`exclusions`, `total`), was in Backticks steht (Zitat) oder eine
Historie-Marke trägt (`Runde n`, `v1`, Datum, SHA).

Der Guard hat sofort **21 Zahlen ohne Herkunft** in meinem eigenen Code
gefunden — alle aus der Sitzungsgeschichte (`234`, `29 Runden`, `207`).
Sie sind raus; der Code trägt jetzt nur noch, was der Lauf messen kann.

### §67.4 — der Ort ist richtig und unsichtbar, also wird er genannt

`.git/check_claude_md.last.json` hat den Vorteil (kein Diff) und den
Nachteil (kein Audit) aus **derselben** Eigenschaft: `git status`, `diff`
und `clean` sehen die Datei nicht. Wer die Differenzzeile loswerden will,
löscht etwas Unsichtbares, und der nächste Lauf sagt `kein Vorlauf`.

Gegenmaßnahme ist eine Zeile, keine Umstellung:

```
Vorlauf: .git/check_claude_md.last.json (nicht versioniert, git-ignoriert)
```

### §67.5 — drei Tests, die nicht rot werden konnten

Drei neue Selbsttests: Nenner, Ort, Klassen-Guard. Die Mutationsprüfung
ergab: **zwei von drei überlebten.**

| Mutation | vorher | nachher |
|---|---|---|
| `_SNAPSHOT_SEEN[0] = None` | 20/20 grün | **rot** |
| `rep.skip("agents<50")` entfernt | 20/20 grün | **rot** |
| Zahl `314` im Kommentar | rot | rot |

Ursache 1: der Ort-Test lief gegen das **Repo**, wo immer ein Vorlauf
liegt — er konnte nicht fehlschlagen. Jetzt gegen den Temp-Baum.
Ursache 2: der Skip-Test prüfte nur *Konsistenz zwischen zwei Zählungen*;
wird gar nicht gezählt, sind beide 0 und gleich. Jetzt explizit: jede
Regel muss `> 0` liefern.

Dasselbe Muster wie in Runde 30 — **ein Test, der nicht scheitern kann,
ist keiner**, und ich habe es zweimal hintereinander gebaut.

### §67.6 — Tests

| # | Fall | erwartet | geprüft |
|---|---|---|---|
| 1–10 | Zählung, Bezugsraum, Suite-Zusagen | rot / **nicht** rot | ✓ |
| 11–12 | Differenz / gleiche Zahl | Delta+SHA / nichts | ✓ |
| 13 | kein Vorlauf | eigene Zeile, exklusiv | ✓ |
| 14 | fehlender SHA | benannt | ✓ |
| 15 | ungleiche Zählweise | Reihe, **kein** Delta | ✓ |
| 16 | Auswahlzeile | Mengen je Regel | ✓ |
| 17 | Zahl ohne Herkunft | rot (Klasse) | ✓ |
| 18 | Nenner | disjunkt, zeilenlokal | ✓ |
| 19 | Ausschlussregel zählt | alle > 0 | ✓ |
| 20 | Snapshot-Ort | gemerkt + benannt | ✓ |

Suite: **216 passed**. Selbsttest: **20/20**, drei Mutationen gegengeprüft.

## 68. Der Satz dieser Runde

Einunddreißig Runden, und der Prüfer druckt zum ersten Mal Datum, SHA,
Zählweise und Zerlegung in einer Zeile — und in derselben Zeile fehlte das
Verhältnis: `223 geprüft`, `210 ausgeschlossen`, und niemand wusste, ob
das die Hälfte oder ein Zwanzigstel ist. `433` steht jetzt da, weil es
gemessen ist und nicht, weil es plausibel klingt.

Während `+16` eine Differenz zwischen zwei Zählweisen als Wachstum las,
obwohl die eigene Regel das verneinte. Und der Docstring-Guard, der die
widerrufene Zeile fing, fing genau ein Zitat — die Klasse ist offen
gewesen, und sie war **in meinem eigenen Code 21-mal belegt**.

Der Selbstbefund dieser Runde ist der aus der letzten, nur härter: von
drei neuen Tests überlebten **zwei** die Mutation. Ein Test, der nicht
scheitern kann, ist keiner — und der Prüfer hat den Fehler, den er bei
anderen sucht, an sich selbst zweimal hintereinander gebaut und beide Male
gefunden.

Was am 20.10. auf dem Tisch liegt, ist ein System mit 216 Tests, 20
Selbsttests, sieben gegengeprüften Mutationen, einem Prüfer, der seinen
Nenner, seine Auswahlgrenze, seine Zählweise und seinen Vorlauf nennt —
**und der eine offene Stelle ist ein Bruchstrich, den er jetzt selbst
zieht: 223 über 433.**

---

## 69. Runde 32 — das Wort `checked`, die geteilte Umgebung und die Zahlen, die niemand committet hat

### §69.1 — Die Rundentabelle: committet, bewiesen

Der Guard hat die Sitzungsgeschichte aus dem Code entfernt. Sie lebt in
dieser Datei — und deren Zustand ist jetzt **gemessen**, nicht angenommen:

```
$ git ls-files --error-unmatch order_execution_engine/ops/TAG7_ABNAHME.md
order_execution_engine/ops/TAG7_ABNAHME.md
$ git log -1 --oneline -- order_execution_engine/ops/TAG7_ABNAHME.md
94641457 feat(check_claude_md): Nenner, Reihe statt Delta, Zahlen-Guard, …
```

Und der Prüfer sagt es selbst:

```
Rundentabelle: order_execution_engine/ops/TAG7_ABNAHME.md (committet 94641457)
```

Der Preis des Guards ist benannt: **ein Guard gegen Zahlen im Code ist
auch ein Guard gegen Geschichte im Code.** Die Geschichte musste
umziehen, und sie ist angekommen.

### §69.2 — §A-NI: ein Wort, zwei Größen

```
check_counts:  checked = 21   skips = 210   Zeilen mit beidem = 18
223 geprueft / 433 gezaehlt (210 ausgeschlossen)
```

`checked = 21` und `223 geprueft` — dasselbe Adjektiv, Faktor 10,6. Die
21 sind Felder, die 223 sind Angaben. Runde 23 im Kleinen, zwei Zeilen
auseinander statt in zwei Meldungen.

Die Einheit steht jetzt an jeder Zahl:

```
223 Angaben geprueft / 433 Angaben gezaehlt (210 ausgeschlossen), 0 Abweichungen
```

Und die Zeile ist eine **Funktion** (`_status_line`), kein `print` —
weil ein Format, das nur im `print` existiert, nur beobachtet und nie
definiert ist.

### §69.3 — die geteilte Umgebung, zum vierten Mal

Vier Runden hintereinander derselbe Befund, und viermal dieselbe Ursache:
**der Test teilte den Zustand mit dem Gegenstand.**

| Runde | Test grün, weil … |
|---|---|
| 29 | die Mutante nicht im Prüfbereich lag |
| 30 | zwei Erwartungen dieselbe Zeile lasen |
| 31 | der Ort-Test im Repo lief, wo immer ein Vorlauf liegt |
| 32 | die Testfälle nacheinander im **selben** `root` schrieben |

Runde 32: Fall 13 schrieb eine Snapshot-Datei in `root`, Fall 13a („ohne
Vorlauf") fand sie vor und meldete `Snapshot ohne Datei als gesehen`.
Erst als die Fälle einen **eigenen leeren Ordner** bekamen, war der
Zustand definiert. Ein Testfall mit Vorbedingung ist ein Testfall; einer
mit Vorgänger ist eine Reihenfolge.

### §69.4 — `--self-test` in CI: er lief nicht

```
$ rg "self-test" .github/workflows/offgrid-test.yml
(kein Treffer)
```

Die CI rief nur den Prüfer, nie den Selbsttest. Ein Test, der nur auf
einer Maschine läuft, ist eine Zusage über eine Maschine. Jetzt:

```yaml
- name: F8 — CLAUDE.md Consistency
  run: |
    python3 scripts/check_claude_md.py
    python3 scripts/check_claude_md.py --self-test
```

Und der Selbsttest ist ortsunabhängig gemacht — geprüft in drei
Umgebungen:

| Umgebung | Ergebnis |
|---|---|
| Repo mit `.git/`-Vorlauf | 22/22 |
| Temp-Baum mit `git init`, ohne Vorlauf | 22/22 |
| Temp-Baum **ohne `.git`** | 22/22 |

### §69.5 — die stille Seite des Deltas

Der Negativfall war getestet (keine Differenz bei ungleicher Zählweise).
**Der Positivfall nicht.** Ein Prüfer, der *nie* ein Delta druckt, bestand
damit jede Prüfung: die Zeile existierte, feuerte nie.

Neuer Fall 15: gleiche Zählweise, andere Zahl → `+16 gegenueber 207`
**muss** erscheinen, und `nicht als Delta` darf **nicht** erscheinen.
Mutation *„Delta feuert nie"* wird rot.

### §69.6 — Tests

| # | Fall | erwartet | geprüft |
|---|---|---|---|
| 1–5 | Zählung (`total` schaltet um) | rot / nicht rot | ✓ |
| 6–8 | Skript fehlt / vorhanden / passed>total | rot / **nicht** / rot | ✓ |
| 9–10 | `N/N waves` / Zusage ohne Zählung | **nicht** rot / rot | ✓ |
| 11–12 | Differenz / gleiche Zahl | Delta+SHA / nichts | ✓ |
| 13 | kein Vorlauf | eigene Zeile, exklusiv | ✓ |
| 14 | fehlender SHA | benannt | ✓ |
| 15 | **gleiche Zählweise, andere Zahl** | **Delta mit Vorzeichen** | ✓ |
| 16 | ungleiche Zählweise | Reihe, **kein** Delta | ✓ |
| 17 | Auswahlzeile | Mengen je Regel | ✓ |
| 18 | Zahl ohne Herkunft | rot (Klasse) | ✓ |
| 19 | Nenner | disjunkt je Fundstelle | ✓ |
| 20 | Ausschlussregel zählt | jede > 0 | ✓ |
| 21 | Snapshot-Ort | **mit und ohne** Datei, im Temp-Baum | ✓ |
| 22 | Statuszeile | Einheit an jeder Zahl | ✓ |

Suite: **216 passed**. Selbsttest **22/22**, drei Mutationen gegengeprüft.

### §69.7 — Verweis

Die Rundentabelle steht in **§71** (ein Ort, nicht zwei). Sie war hier
und in §65.1 dupliziert — zwei Abschnitte, die ab jetzt auseinanderlaufen.

## 70. Der Satz dieser Runde

Zweiunddreißig Runden, und die Akte hat ihren eigenen Fehler gefunden:
`checked = 21` und `223 geprueft` standen zehn Zeilen auseinander, mit
demselben Wort, für zwei verschiedene Dinge. Es war Runde 23 — nur diesmal
hat der Prüfer es selbst gedruckt, in der Zeile, die er gerade repariert
hatte.

Und der Test, der zwei blinde Tests fand, war blind aus demselben Grund
wie sie: **er lief im selben Repo wie der Gegenstand.** Viermal
hintereinander. Die geteilte Umgebung, die ihn grün machte, machte ihn
stumm — und erst als er einen leeren Ordner bekam, hatte er ein
Verhalten statt einer Beobachtung.

Die eine offene Stelle dieser Runde ist keine Rechnung mehr, sondern ein
**Ort**: Der Selbsttest läuft jetzt in CI, und die Rundentabelle ist mit
`git ls-files` und `git log` als committet bewiesen. **Was am 20.10. auf
dem Tisch liegt, ist ein System mit 216 Tests, 22 Selbsttests, zehn
gegengeprüften Mutationen über vier Runden und einem Prüfer, der sagt,
wo seine Zahlen herkommen, wo seine Auswahl endet und wo seine Geschichte
liegt — und der sich dabei viermal selbst ertappt hat, weil er den Fehler
bei sich zuerst gesucht hat.**

---

## 71. Die Rundentabelle — ein Ort, Runden 23–33

Diese Tabelle stand bis Runde 32 zweimal (§65.1 und §69.7). Zwei Orte für
einen Wert sind derselbe Fehler wie zwei Namen für einen Wert, eine Ebene
höher: sie laufen ab jetzt auseinander. Ab Runde 33 gibt es **eine**
Tabelle, hier, und alle Verweise zeigen hierher.

Die Spalte *Fix* ist die eigentliche Aussage: neun Runden lang war jeder
Befund ein Einzelfall, und jeder Fix war eine Bandage. Erst Runde 33
behebt die **Klasse** — und auch das nur an einer Stelle.

**§A-JP — warum die Spalte „Bandage/Architektur" weg ist.** Sie hatte zwei
Werte und maß das falsche Merkmal: sie fragte, *wie* gefixt wurde, nicht
*welche Annahme* den Fehler erzeugt hat. Das Ergebnis war unangenehm
lesbar — „Architektur" stand dort, wo von außen darauf bestanden wurde
(Runde 33′), nicht dort, wo es erkannt wurde. Die brauchbare Frage ist die
aus §1 dieser Runde: **derselbe Fehler in Code und Test.** Sie zeigt, daß
31/32/33′/34 **eine** Zeile sind, nicht vier. Zwei Annahmen tragen alle
zehn Runden:

| Annahme | Runden | der Test war grün, weil … | wo sie saß |
|---|---|---|---|
| **`cwd == root`** | 31, 34 | der Lauf im Repo stattfand; `Path.cwd()` war das Repo | 31: Test (Vorlauf liegt immer vor) · **34: Code** (`gd = (root or Path.cwd()) / gd`) |
| **geteilter Zustand** | 32, 32′, 33′ | der Fall den Zustand des Vorgängers erbte | Harness: kein `reset()`, `_SNAPSHOT_SEEN` gesetzt und nie geräumt |
| **der Test erreicht den Code** | 29, 30, 35 | die Mutante lag außerhalb des Prüfbereichs; zwei Erwartungen lasen dieselbe Zeile; der Test übergab `root` — das Argument, das den Fehler **abschaltet** | Test: Prüfbereich, geteilte Zeile, explizites `root` |
| **die Zahl mißt den Weg, den sie meint** | 34, 35, 36 | der Docstring prüfte das Wort, nicht den Wert; die Zeile prüfte *daß* etwas dasteht; der Test prüfte die Anzahl der Aufrufe, ohne den Pfad zu kennen | zwischen Messung und Benennung |

**Die vierte Annahme ist die einzige, die keine Vorbedingung schließt.** Sie
braucht zwei Werte, die **verschieden** sein müssen — sonst sieht der Test
nichts.

> **Regel (§A-JW): jeder Test braucht einen zweiten Fall, in dem der Wert
> anders ist.** Gegenproben: Fall 19 (`root` ≠ `root=None`), Fall 22
> (`Checks`-Paare `(21,210)` und `(7,4)`), Fall 16c (zwei `chdir`-Zyklen),
> Fall 24 (zwei Fälle, ein Zustand — Probesichtbarkeit und Reset getrennt).
> Die Regel steht hier, an der Tabelle — nicht in einer eigenen §-Nummer.
> Wer in Runde 50 die Annahmen sucht, findet sie mit der Regel daneben.

Runde 34 ist damit **kein neuer Fehler**, sondern Runde 31 eine Schicht
tiefer: die Annahme hat die Testgrenze überschritten. Und sie wurde beim
Aufräumen gefunden, nicht von einem Test — also ohne Test gefixt. Genau
das ist die Bandage: die Zeile war richtig, die Annahme lebte weiter.
Der Test steht seit Runde 34 (Fall 16, Mutation rot).

**Runde 35 ergänzt die dritte Annahme.** 29 (*die Mutante lag nicht im
Prüfbereich*), 30 (*zwei Erwartungen lasen dieselbe Zeile*) und 35
(*der Test übergab `root` — das Argument, das den Fehler abschaltet*)
sind **nicht** `cwd == root` und **nicht** geteilter Zustand. Sie sind:
der Test erreicht den Code nicht, den er prüfen soll. Bei 29 lag er
daneben, bei 30 las er die falsche Zeile, bei 35 schaltete der Parameter
den Fehler ab. Drei Annahmen, elf Runden.

| Runde | falsch war | gefunden durch | Fix |
|---|---|---|---|
| 23 | zwei Nenner unter einem Wort (30/300) | Lesen | Bandage: Nenner benannt |
| 24 | zwei Nenner unter einem Wort (393/327) | Lesen | Bandage: Bezugsraum getrennt |
| 25 | zwei Gründe in einem Zähler | Messung | Bandage: Prädikat |
| 26 | ein Default, der handelt | Audit | Bandage: explizit |
| 27 | zwei Lesarten einer Gleichung (4 = 4) | Messung | Bandage: Disjunktheit |
| 28 | ein Nenner ohne Prädikat (325/827) | Regel vor Commit | Bandage: Prädikat |
| 29 | eine Zahl **plus** die Klammer dazu | Selbstmessung | Bandage: Nachmessung |
| 29′ | die Rüge: Klammer gegen zwei richtige Zahlen | Nachmessung | — (Rüge nachgetragen) |
| 30 | zwei Schweigen, eine Ausgabe | Einwand | Bandage: eigene Zeile |
| 31 | `+16` als Wachstum; Guard fing ein Zitat | Einwand + Guard | Bandage: Reihe; Guard auf Klasse |
| 32 | `checked` in zwei Einheiten | Einwand | Bandage: Einheit an der Zahl |
| 32′ | Test erbte Umgebung (viermal) | Mutation | **Bandage** (ein Fall) |
| 33 | ohne `.git/` ist die Differenzmessung tot, Meldung grün | Einwand | Bandage: eigene Zeile |
| 33′ | vier Einzelfixes, keine Vorbedingung | Einwand | **Architektur**: Harness-Reset + Kreuztest |
| 34 | relativer `--git-common-dir` gegen `Path.cwd()`; `_SNAPSHOT_SEEN` ohne Reset | Lesen (`rg "cwd"`) | **Architektur**: Test 16/17/18, `reset()` vollständig, Docstring Einheit |
| 35 | Tests übergaben `root` und übersprangen den Produktionspfad; `_status_line` zählte 21 als „Angaben"; Fall 17 kannte Namen statt Menge | Einwand + `rg` | **Architektur**: Fall 19 (Zwillings ohne `root`), `Checks`-Typ, Fall 17 gegen Globals-Menge, `repo_root()` mit Cache |
| 36 | `reset()` und Cache-Reset waren zwei Vorbedingungen; `chdir` ohne Wiederherstellung; Filter ohne eigenen Test; `223` dreimal getippt | Einwand + Mutation | **Architektur**: `reset_all()` inkl. cwd, Fall 16b, Filter-Fixture, `Checks(n, excluded)` mit `total` |
| 37 | `_START_CWD` wäre als Zustand klassifiziert und vom Reset auf den Fehler gesetzt (`Path.cwd()`); `Path`/`Decimal`/`Fraction` falsch-positiv; `Checks` mutierbar | Einwand + Messung | **Architektur**: dritte Kategorie *Referenz*, `_IMMUTABLE_CTORS`, Fall 16c (zwei Zyklen), `frozen` |
| 38 | `checked` als nackter `int` ohne Test (Runde 23 saß in der Zahl); zwei Caches ohne Schreiber-Vertrag; Annahme 2 ohne Probe | Einwand + Messung | **Architektur**: Zählvertrag im Docstring + Fall 22, Schreiber leert Caches (Fall 25), Fall 24 (zwei Fälle, ein Zustand) |

### §71.1 — was Runde 33 wirklich geändert hat

**Ohne `.git/`** gab es keinen Ort. Der Prüfer sagte `kein Vorlauf` — als
hätte er einen Ort und keinen Inhalt — und schrieb nirgendwo. Gemessen in
einem Tarball-Export:

| Umgebung | Ausgabe vorher | Ausgabe jetzt |
|---|---|---|
| Repo, Vorlauf da | Delta oder nichts | unverändert |
| Repo, Vorlauf fehlt | `kein Vorlauf` | `kein Vorlauf` |
| **kein `.git/`** | **`kein Vorlauf`** | **`kein .git/ — Vorlauf nicht schreibbar, keine Differenzmessung`** |

`kein Vorlauf` und `kein Ort` sind zwei Zustände, und nur einer davon
verschwindet beim nächsten Lauf. Dazu fiel ein echter Fehler auf: der
relative `--git-common-dir` wurde gegen `Path.cwd()` aufgelöst statt gegen
das Repo — für den Arbeitsbaum harmlos, für jeden anderen Root falsch.

### §71.2 — die Vorbedingung statt der Reihenfolge

Der Kreuztest läuft **zuerst** in der Suite und braucht keinen Fix:

```
Schreiber legt Vorlauf ab   → Leser darf ihn nicht sehen
```

Wird `reset()` entfernt, ist die Suite rot. Damit gilt: ein neuer Fall
kann den Zustand eines alten nicht erben, weil er ihn nicht bekommt —
nicht, weil er sorgfältig ist.

### §71.3 — `checked = 21`: weder gedruckt noch gelöscht

`rg "checked = "` findet den Felde `Report.checked` und Testdaten. Die
Größe **existiert** weiter — sie ist die Zählvariable des Reports — aber
**gedruckt wird sie nicht mehr**. Das ist der dritte Zustand, den die
Frage offen ließ: weder „gedruckt" noch „entfernt", sondern *intern*.
Der Name bleibt mehrdeutig, aber er erscheint nicht mehr in einer Zeile,
die `geprueft` sagt.

### §71.4 — Runde 34: der Guard prüft zum ersten Mal *für* etwas

Bis Runde 33 war der AST-Zahlen-Guard ein Verbot: er entfernte Zahlen, die
niemand gemessen hatte (`234`, `29 Runden`). Runde 34 dreht ihn: der
Docstring von `Report` **muß** die Einheit von `checked` nennen
(*Prüfungen*, nicht *Angaben*). Fall 18 prüft das gegen `inspect.getdoc`.

Der naheliegende falsche Fix wäre die Umbenennung in `checked_fields`
gewesen — ein Name mit einer Bedeutung, aber ein **zweiter Zählbegriff
neben `geprueft`**. Der Docstring kostet nichts und nimmt niemandem einen
Namen weg.

### §71.5 — Runde 34: `reset()` deckte den Vorlauf, nicht den Speicher

`rg "^_[A-Za-z_]+ *[:=]"` fand vier Modulglobals: `_SNAPSHOT_SEEN`,
`_test_results`, `_COUNTING_LABEL`, `_SELF_TEST_SCOPE`. Zwei tragen
Zustand. `reset()` räumte nur die Datei — `_SNAPSHOT_SEEN` und
`_test_results` lebten über Fälle hinweg. In Runde 32 war eine Mutation an
`_SNAPSHOT_SEEN` **grün**, weil sie nichts änderte: das Global wurde
gesetzt und nirgends zurückgesetzt. Jetzt räumt `reset()` beide, und Fall
17 ist unter Mutation rot (2 FAIL, gemessen).

**Der Unterschied ist der Satz aus Runde 33:** ein Fall kann den Zustand
eines alten nicht erben, weil er ihn nicht bekommt — das gilt ab Runde 34
für **jeden** Zustand, Datei und Speicher, nicht nur für den Vorlauf.

### §71.6 — Runde 35: der Default ist der Produktionspfad

`_snapshot_path(root)` hat sechs Aufrufer mit `root` und **einen** ohne —
den in `main()`. Also testete die Suite fünfmal den bequemen Weg und
niemals den, den jede echte Invocation nimmt. Der erste Fix in Runde 34
(Fall 16) übergab `root` und blieb deshalb unter Mutation **dreimal grün**:
das Argument schaltete den Fehler ab.

| Weg | wer nimmt ihn | vorher getestet |
|---|---|---|
| `root` gesetzt | Tests, `--root` | sechs Aufrufer |
| `root=None` | **jede echte Invocation** | **erst seit Runde 34, scharf seit 35** |

Fall 19 prüft den Zwilling: derselbe Aufruf ohne `root`, und der Ort muss
auf **dieses** Repo zeigen, nicht auf `root`. Dazu: `repo_root(None)`
liefert den Dateiort, `repo_root(root)` löst auf, und der Cache kostet
genau **einen** `git`-Aufruf für drei Abfragen (gemessen: 3 → 1).

### §71.7 — Runde 35: `223` und `checked` an einer Stelle

`Report.checked` zählt **Prüfungen** (21); `_status_line` schrieb daneben
„Angaben". Zahl und Wort entstanden getrennt, also konnte kein Test die
Korrespondenz prüfen — Fall 18 sah nur, *daß* ein Wort dasteht.

`Checks` macht den Fehler unmöglich: `_status_line` nimmt keinen `int`
mehr an (`TypeError`), und die Zahl kommt mit ihrem Wort. Fall 18 prüft
jetzt beides — den Docstring **an der Zeile, die `checked` nennt**, und
die Ablehnung von `int`. Mutationen: Docstring-Zeile geleert → rot;
`int` akzeptiert → rot.

### §71.8 — Runde 35: `reset()` gegen die Menge, nicht die Namen

Fall 17 kannte zwei Namen. Ein fünftes Global wäre unsichtbar geblieben.
Jetzt gilt: jedes Modulglobal mit Zustand steht in `_RESET_GLOBALS` oder
in `_STATE_FREE` — sonst rot. Die Ermittlung ist AST-basiert: `list`/`dict`
gelten als Zustand (auch als Literal — `[None]` ist ein Speicherplatz),
`tuple`/`str`/`compiled regex` als unveränderlich.

Der Test fand sofort das Global, das ich in derselben Runde eingeführt
hatte (`_ROOT_CACHE`) und das `reset()` noch nicht räumte — der Erbfall,
den §4 beschreibt, im eigenen Neuzugang.

**xdist-Hinweis:** `reset()` ist sequenziell. Unter `-n auto` sieht jeder
Worker seine eigene Kopie, `reset()` löscht nur die eigene — die
Isolation wäre dann eine Illusion. Steht im Docstring.

### §71.9 — Runde 35: ein `cwd`-Treffer, nicht zwei mit Häkchen

`Path.cwd()` steht jetzt an genau **einer** Stelle (der `__main__`-Default
für ein explizites Ziel). Alle Aufrufer gehen durch `repo_root()`. Der
Beweis ist mechanisch: `rg "Path\.cwd\(\)"` → ein funktionaler Treffer.
Die Nebenwirkung ist benannt und getestet: der Cache macht aus drei
`git`-Aufrufen einen — und wer die Snapshot-Datei anfaßt, muß den Cache
leeren (`lines_for` tat es nicht, der Test fiel sofort).

### §71.10 — Runde 36: `chdir` ist Zustand, den der AST-Check nicht sieht

`reset()` und `_reset_root_cache()` waren **zwei** Vorbedingungen mit
eigener Aufrufregel, die nirgends stand. Jetzt `reset_all()`: Dateien,
Globals, Cache — und `Path.cwd()`. Der letzte Punkt ist der neue:

| Zustand | erfaßt von Runde 33′–35 | Runde 36 |
|---|---|---|
| `.git/…last.json` | ✓ | ✓ |
| `_SNAPSHOT_SEEN`, `_test_results` | ✓ | ✓ |
| `_ROOT_CACHE`, `_SNAPSHOT_CACHE` | ✓ | ✓ |
| **Prozess-cwd** | **✗** | **✓** |

`os.getcwd()` ist kein Modulglobal — der AST-Check kann ihn strukturell
nicht sehen. Ein Fall, der vor seinem `finally` scheitert, ließ jeden
folgenden in `/tmp` laufen. Fall 16b beweist es: `chdir`, Ausnahme,
`reset_all()` → cwd ist der Startwert (Mutation rot).

Nebenwirkung, benannt: `chdir` macht die Suite reihenfolgeabhängig per
Konstruktion und unparallelisierbar. Deshalb nur in Fall 16/16b, danach
`reset_all()`. Der Verzicht auf `chdir` (stattdessen `root` übergeben)
wäre sauberer — aber genau das war der Fehler aus Runde 35.

### §71.11 — Runde 36: wer prüft den Filter?

Der Formen-Filter war einmal falsch, und falsch hieß grün (`globals: []`).
Jetzt prüft ihn ein Fixture mit je einer Zustandsform und einer
**vollständigen** Erwartung — ein Wert, kein Muster:

| Form | erwartet |
|---|---|
| Liste, Dict, Set, annotiert, Ausdruck | **Zustand** |
| Tuple, str, compiled regex, frozenset | unveränderlich |

Mutationen: `ast.List` zurück in die Literal-Liste → 2 FAIL;
`set()` als unveränderlich → 1 FAIL.

**Dabei fiel toter Code auf:** der `mutable`-Merker aus Runde 35 half nur,
weil `ast.List`/`ast.Dict` damals noch in der `literal`-Tupel standen. Seit
sie dort heraus sind, war der Zweig redundant — drei Mutationen blieben
grün, bevor das klar war. Entfernt; jetzt fängt `not literal` beide.

### §71.12 — Runde 36: die Zeile hat drei Zahlen, nicht eine

`Checks` deckte die 21. `223`, `433`, `210` entstanden in `_status_line`
aus `checked.n + excluded`, mit `excluded` separat übergeben — die Identität
war zweimal getippt. Jetzt trägt `Checks(n, excluded)` sie, `total` ist eine
Property, und die Zeile rechnet nicht mehr:

```
223 Angaben geprueft / 433 Angaben gezaehlt (210 ausgeschlossen), 0 Abweichungen
```

`Checks(223, 210)` → die Zeile liest drei Felder eines Objekts. Mutation
`total` gibt `self.n` zurück → 6 FAIL, mit zweitem Paar `(7,4)` als
Gegenprobe.

### §71.13 — Runde 37: der Reset braucht eine Erinnerung, die er nicht zurücksetzt

`_START_CWD` ist der sechste Global — und der erste, der **nicht** in
`_RESET_GLOBALS` gehört. Drei Kategorien statt zwei:

| Kategorie | Namen | vom Reset |
|---|---|---|
| resetbar | `_SNAPSHOT_SEEN`, `_test_results`, `_ROOT_CACHE`, `_SNAPSHOT_CACHE` | **gesetzt** |
| zustandslos | Skalare, Tuple, `frozenset`, `_IMMUTABLE_CTORS` | — |
| **Referenz** | **`_START_CWD`** | **ausgenommen** |

Warum die dritte nötig ist: `Path.cwd()` ist ein *Ausdruck*, also las der
Filter `_START_CWD` als Zustand. Ein Global in `_RESET_GLOBALS` setzt
`reset_all()` auf `Path.cwd()` — auf den Zustand, den es reparieren soll.
Nach einem **erfolgreichen** Fall fällt das nicht auf (cwd ist sauber); erst
beim zweiten gescheiterten `chdir` landet die Referenz in `/tmp`.

| Fall | deckt ab |
|---|---|
| 16b | ein Zyklus |
| **16c** | **zwei Zyklen, und `_START_CWD` bewegt sich nicht** |

Mutationen: `reset_all()` setzt `_START_CWD = Path.cwd()` → 3 FAIL;
`_START_CWD` zusätzlich in `_RESET_GLOBALS` → 1 FAIL (Disjunktheit).

**Dazu der falsch-positive Filter:** `Path`, `Decimal`, `Fraction`, `bytes`
sind Konstruktoraufrufe über unveränderlichen Typen, keine Speicherplätze.
Ohne `_IMMUTABLE_CTORS` hätte jeder solche Global als Reset-Kandidat
gegolten — und `_START_CWD` beim ersten Lauf überschrieben.

### §71.14 — Runde 37: einer von zwei Änderungen wirkte

Runde 35 änderte zwei Dinge gleichzeitig: entfernte `ast.List`/`ast.Dict`
aus der Literal-Tupel **und** führte den `mutable`-Merker ein. Die Akte
sagte „gefixt". Nachgemessen an `352d9fd9`: `literal` war dort bereits
`(ast.Tuple, ast.Constant)` — die Entfernung war der Fix, der Merker
Dekoration. Er blieb bis Runde 36 liegen und fiel nur auf, weil die
Fixture **unter dem Originalfehler grün war**.

> **Regel (§A-KB): ein Fix mit mehr als einer Zeile wird zeilenweise
> zurückgenommen.** Bleibt es grün, war die Zeile Dekoration. Ein grüner
> Test für einen Fix ist erst dann eine Aussage, wenn bekannt ist, welcher
> Teil des Fixes ihn grün macht.

### §71.15 — Runde 37: `Checks` ist ein Wert, kein Behälter

`total` als Property heißt *berechnet bei jedem Zugriff*. Solange `n` nach
dem Bau änderbar ist, ist die Identität `checked + excluded == total` eine
Eigenschaft des Zugriffszeitpunkts. Mit `__setattr__`-Sperre (frozen) gilt
sie per Konstruktion.

Nebenwirkung, benannt: kein In-Place-Zähler. `Report.checked` bleibt ein
`int` und wird **einmal** beim Druck in `Checks` übergeben — eine Stelle,
an der Zahl und Wort zusammenkommen.

### §71.16 — Runde 38: der Zähler hatte keinen Eigentümer

Runde 23 saß **in der Zahl**, nicht im Wort. `Checks` macht „21 Angaben"
unbaubar — es macht `checked == 21` nicht wahr. Der Zähler blieb ein
`int`, den eine Schleife erhöht, ohne Test.

| | geschützt |
|---|---|
| Wort neben der Zahl | ✓ `Checks` |
| **Zahl == Anzahl gelaufener Prüfungen** | **erst seit Runde 38 (Fall 22)** |

Vier Regeln, jetzt im Docstring **und** als Test:

| Aufruf | zählt? |
|---|---|
| `ok()` / `fail()` | ja, je genau eins — auch eine *gescheiterte* Prüfung ist gelaufen |
| `skip()` / `env()` | **nein** — was nicht lief, ist keine Prüfung |
| `claim()` | nein — eine Zusage ist keine Messung |
| frischer `Report()` | bei 0, unabhängig vom Vorgänger |

Mutationen: `ok()` zählt doppelt → 2 FAIL; `skip()` erhöht `checked` → 2 FAIL.
Die Begründung für `int` (statt `Checks` bei jedem Inkrement) steht am
Konstruktor: eine Allokation pro Prüfung gegen einen Zähler, der im
Bereich weniger Hundert bleibt.

### §71.17 — Runde 38: zwei Caches, ein Schreiber, ein Vertrag

`_SNAPSHOT_CACHE` (Inhalt) und `_ROOT_CACHE` (Ort) zeigen auf dieselbe
Datei. Der einzige Schreiber — `_save_count_snapshot` — kannte keinen von
beiden. Runde 36 hatte den Fix bewusst im Test gelassen; bei **einem**
Cache war das richtig, bei **zwei** auf einer Datei ist „nur Tests
schreiben" eine Annahme.

Jetzt: der Schreiber leert beide, und die Invariante steht **an ihm**, nicht
beim Aufrufer — der weiß nichts von Caches. Fall 25 füllt beide, schreibt,
prüft leer (Mutation: 1 FAIL, mit beiden Cache-Schlüsseln im Text).

Nicht gebaut, notiert: ein zweiter **Prozess** ist davon nicht erfasst.
Dafür bräuchte es `(st_mtime_ns, st_ino, st_size)` im Cache — mit dem
Vorbehalt, daß mtime auf manchen FS nur sekundengranular ist.

### §71.18 — Runde 38: die schwächste Probe gehörte zur häufigsten Annahme

Annahme 2 (geteilter Zustand) trat in 32, 32′, 33′ auf — dreimal — und hatte
**keine** Probe: Runde 33′ hinterließ einen Fix, keinen Test. 16c prüft
cwd, nicht den geteilten Speicher.

Fall 24 schließt das: Zustand setzen, **nicht** zurücksetzen, prüfen daß
der zweite Fall ihn sieht (sonst ist die Probe blind) — dann `reset_all()`
und prüfen, daß er weg ist. Beides zusammen: der Reset wirkt **und** die
Probe kann ihn sehen. Gegenprobe mit zwei Zyklen (§A-JW).

### §71.19 — Runde 38: `__setattr__` von Hand — und warum

`frozen=True` erzeugt dieselbe Sperre. Der Unterschied ist nicht
Importkosten, sondern Umfang: `total` als `@property` bräuchte in einem
frozen-Dataclass `field(init=False)`. Grenze, jetzt im Code: `copy`/`pickle`
verhalten sich anders, `object.__setattr__` umgeht die Sperre (wie bei
`frozen=True`). `__delattr__` fehlte — nachgetragen und geprüft (Mutation:
1 FAIL).

### §71.20 — Runde 39: `claim()` fiel aus der Summe, und `total` behielt den Namen

Drei Eimer, vier Kategorien, ein Name. `ok/fail → checked`,
`skip/env → excluded`, `claim → ?`. Die Zusage lag in `Report.claims`
und in keiner der beiden Zahlen — `total` hieß „alle Angaben" und meinte
„checked + excluded". **Runde 23 eine Ebene höher: nicht `checked` gegen
`geprueft`, sondern `total` gegen `total`.**

| `claim()` | Entscheidung | Folge |
|---|---|---|
| eigener Eimer, `total` umfaßt ihn | **gewählt** | Zeile nennt drei Einheiten; `measured` behält die alte Menge |
| außerhalb, `total` umbenannt | verworfen | ein Name weniger, aber zwei Mengen bleiben |
| außerhalb, `claim()` streichen | verworfen | Zusage ohne Ort ist keine Zusage |

Gegenprobe (Fall 26): derselbe `Report` ohne `claim()` — `total` ändert
sich um **nichts**, `measured` ebenso wenig. Zwei rote Mutationen:
`total` ohne `claims` → 3 FAIL; `claims` in `measured` → 2 FAIL.

**Die Zahl springt: `433 → 461`.** Nicht weil 28 Prüfungen dazukamen,
sondern weil die Menge sich verschoben hat, während der Name blieb. Es
ist dieselbe Zahl wie vorher, um den Anteil erweitert, der vorher
unerwähnt blieb.

### §71.21 — Runde 39: der Cache war der Kandidat, nicht der Parameter

`_save_count_snapshot` hatte kein `root` — das war der Auslöser. Die
Ursache konnte der prozessweite `_ROOT_CACHE` sein, der mit **einem**
root gemessen war (Runde 35: 3 Abfragen → 1 `git`-Aufruf). Fall 27
misst beide Werte: `repo_root(tmp_a)` ≠ `repo_root(tmp_b)`, zwei
Einträge; derselbe root zweimal → ein Eintrag. Mutation „Schlüssel ist
immer `None`" → 20 FAIL. **Der Cache war korrekt — aber das war eine
Annahme, bis Fall 27 sie gemessen hat.**

Nebenwirkung, benannt: ein prozeßweiter Cache macht die Suite
reihenfolgeabhängig; `reset_all()` deckt das nur, weil es gerufen wird.

### §71.22 — Runde 39: die Suche fragte nach dem Fund, nicht nach dem Fehler

Runde 38s eigenes `rg` suchte `Path.cwd()` — das **Symptom** aus
Runde 34/35. Der Fehler ist „ein Aufrufer reicht `root` nicht durch".
**Das sind zwei Mengen, und die zweite ist größer.**

Der zweite `rg` ist ein AST-Lauf (`_forwarding_violations`). Erster
echter Lauf: **13 Stellen**, darunter `main` selbst — `_save_count_snapshot`
und `_delta_line` ohne `root`. Die Produktion schrieb in den
Default-Ort statt zu `root`. Das war ein echter Fehler, kein Artefakt.

Vier Fehlversuche am Prüfer, jeder eine eigene Fehlerklasse:

| Versuch | Fehler im Prüfer | Symptom |
|---|---|---|
| 1 | `ast.walk(n)` stieg in Kind-`def`s | Kind-Aufrufe als Eltern-Verstoß |
| 2 | Filter auf `root: Path \| None` | `check_line_counts(root: Path)` fehlte |
| 3 | `_names_in_scope(fn, fn)` → `limit = fn.lineno` | Prüfer stillgrün, immer `[]` |
| 4 | `root_funcs[name]` als „root ist erster Parameter" | 13 Falschmeldungen |
| 5 | „Argument vorhanden" als „root übergeben" | `Path.cwd()` galt als korrekt |

Der fünfte ist der wichtigste: **ein Prüfer, der Argumente zählt statt
Namen liest, prüft die Form der Übergabe, nicht die Übergabe.** Jetzt
werden Aliase (`root_repo = root`, `case = root / ...`) aufgelöst, und
`Path.cwd()` fällt durch. Fünf Presets an Mini-Quellen statt an der
Produktionsdatei — der Prüfer ist gegen sich selbst testbar.

Ausnahmen sind **benannte Zeilen** (`_DEFAULT_PROBE_LINES` + `# §A-KR`),
jede mit Grund daneben, und `_default_probe_lines_valid()` schlägt an,
wenn eine Zeile wandert, ohne dass der Marker mitwandert.

### §71.23 — Runde 39: ein Reset, der löscht, ist von einem, der leert, nicht zu unterscheiden

Fall 24 hatte drei Schritte: setzen → zweiten Fall sehen lassen →
`reset_all()` → weg. Der vierte fehlt: **nach dem Reset wieder
setzbar.** `del _ROOT_CACHE` oder `= None` macht den nächsten Zugriff
zum `NameError`/`TypeError`, und der Test sähe nur „weg" — weil der
erste Schritt beide Fälle gleich zeigt. Mutation `_test_results = None`
→ 4 FAIL. Der Zyklus läuft jetzt zweimal, und der dritte Schritt setzt
danach alle vier Zustände erneut.

### §71.24 — Runde 39: die Sperre ist eine Dunder-Liste

`__setattr__` ✓, `__delattr__` ✓. Die Liste steht jetzt an der Klasse,
mit dem, was sie **nicht** deckt: `object.__setattr__` (umgeht jede
Fassung, auch `frozen=True`), `copy`/`pickle` (bauen über `__init__`,
nicht getestet), `vars()` (leer, weil `__slots__` kein `__dict__` gibt).
Der Grund gegen `frozen=True` steht als Satz daneben — nicht
„Importkosten", sondern „hält die Klasse klein".

### §71.25 — Runde 39: `committet` war die dritte Kopie desselben Fehlers

Beim Nachlauf nach der Doku-Änderung meldete der Prüfer
`Rundentabelle: … (committet 9cfa405d)` — für eine Datei, die in
dieser Minute geändert worden war. `git log -1` fragt, ob **je** ein
Commit sie enthielt. `git status --porcelain` fragt, ob der Arbeitsbaum
ihm noch entspricht. Zwei Fragen, ein Wort.

Dieselbe Form wie `total` gegen `total`: der Name blieb, die Menge
verschob sich. Und derselbe Durchreich-Fehler wie in `main`:
`_doc_tracked()` nahm kein `root` und lief gegen
`Path(__file__).parent.parent`. Beides behoben; die Ausgabe lautet
jetzt `geaendert nach 9cfa405d (nicht committet)`, bis der Commit da ist.

**Das ist der vierte Fund derselben Familie in einer Runde — und der
erste, den die eigene Prüfung beim Ausführen gemeldet hat, nicht der
Autor beim Lesen.**

### §71.26 — Runde 40: `committet <sha>` stempelte beim Schreiben

Der Fix aus §71.25 (`git status --porcelain`) prüfte *wann* gedruckt
wurde, nicht *was* dasteht. Zwei Gegenbefunde, gemessen:

| Fall | `git status` | Inhalt gegen `<sha>` |
|---|---|---|
| `touch` (mtime, Inhalt identisch) | **„geaendert"** (falsch) | identisch ✓ |
| ein Zeichen angehängt | „geaendert" ✓ | weicht ab ✓ |
| Datei revertiert | „committet" ✓ | identisch ✓ |

Die erste Zeile ist der Beleg: `git status` ist mtime-getrieben, die
Behauptung ist eine Inhaltsaussage. **Der einzige Cache in dieser Akte,
der beim Schreiben stempelte statt beim Lesen zu prüfen.**

Jetzt: `git show <sha>:<pfad>` gegen den Arbeitsbaum, beide Seiten
`sha256` — ein Blob-Read, mtime-immun, reversibel. Die Zeile nennt
beides: Herkunft (`committet <sha>`) und Identität (`sha256:…`).
Gegenprobe: unverändert → `committet` **mit** passendem sha; ein Zeichen
anders → `geaendert`; revertiert → wieder `committet`.

### §71.27 — Runde 40: achtundzwanzig Zusagen im Nenner

`461 = 433 gemessen + 28 Zusagen`. Die Kopfzahl enthielt Aussagen, die
per Definition **nicht gemessen** sind — und trug denselben Namen wie
vorher. Wer Runde 33 gegen diese liest, sieht einen Sprung ohne Grund.

Zwei Fragen, zwei Antworten:

**a) doctest-gedeckt?** **Nein** — `>>>` kommt in `CLAUDE.md` null Mal
vor. Die 28 stehen einmal in der Zahl und werden nirgends als Prüfung
gezählt. Der Grund steht jetzt an der Zahl: `(nicht doctest-gedeckt)`.

**b) Wo steht 433?** Nur noch in der Klammer. Die Zeile lautet
`461 gezaehlt (433 gemessen + 28 Zusagen)`. Die Definitionsänderung ist
datiert am `Checks.total`-Docstring (2026-10-17, Runde 40), nicht nur
hier. Und der Zahlen-Guard, der `461` als „ohne Herkunft" ablehnte,
hielt eine Liste von Literalen — er war ein Guard gegen Veränderung,
nicht gegen Zahlen ohne Herkunft. Er prüft jetzt die Zerlegung des
laufenden `Checks`, nicht dreizehn Konstanten.

### §71.28 — Runde 40: sieben Presets, sieben Löcher — und ein achtes

Runde 39 hatte fünf Presets für fünf Fehlerklassen; drei fehlten.
Jetzt ein Preset je Loch, mit benannter Klasse:

| Kn | Preset | erwartet | was es deckt |
|---|---|---|---|
| K1 | `g(Path.cwd())` | Verstoß | Ausdruck statt Name |
| K2 | `g()` | Verstoß | fehlendes Argument |
| K3 | `g(1)` bei `g(x, root)` | Verstoß | falsche Position |
| K4 | `g()` im Kind-`def` | **kein** Verstoß | Scope des Kindes |
| K5 | `r = Path.cwd(); g(r)` | Verstoß | Fremd-Alias |
| K6 | `r = root; g(r)` | **kein** Verstoß | root-Alias |
| K7 | `g(root)` | **kein** Verstoß | korrekt |

**K4 fand sofort ein Loch:** der Einstieg `for stmt in fn.body: visit(stmt)`
lief in Kind-`def`s **hinein**, ohne sie als Kind zu behandeln — Zeile 3
wurde `f` zugeschrieben, obwohl sie zu `inner` gehört. Ein Prüfer, der
Kinder betritt, aber nicht als Kinder behandelt, ist derselbe Fehler wie
einer, der sie überspringt. Beide Wege jetzt über dieselbe Regel
(`_binds_root`), an drei Stellen: äußere Schleife, Rekursion, Einstieg.

Zusätzlich: die **Produktionsprobe**. Eine Kopie der eigenen Datei mit
eingebautem Fehler muss anschlagen — sonst ist der Prüfer ein
Fixture-Prüfer. Und ein Blind-Test (K2 → `[]`) als Wache gegen den
stillgrünen Fall aus Versuch 3.

**Dreizehn Stellen, acht davon Ausnahmen.** Keine Majority-Duldung: jede
Ausnahme ist ein Textanker mit Grund im Code, und `§A-KR` zählt 8
markierte Zeilen gegen 8 Anker. Das erste Zählverfahren zählte die
Ankerliste selbst mit (20 gegen 8) — die Abschrift der Ausnahmen ist
keine Ausnahme.

### §71.29 — Runde 41: der Parameter heißt nicht `root`

Die Kette war echt und wurde gemessen:

```
main /tmp/klon
  -> check_tests(text, root)          hat root ✓
  -> _resolve_test_root(root)         hat doc_root, reicht es nicht
  -> git rev-parse (ohne cwd)         liest das Prozess-Verzeichnis
```

**Ergebnis:** `check_claude_md.py /tmp/klon` prüfte die Tests des
**eigenen** Repos — 223 Angaben, 0 Abweichungen im fremden Baum, der
151 hat. `_resolve_test_root(Path('/tmp/klonprobe'))` lieferte
`/Volumes/…/agent_x_storage`. Der Glieder-Prüfer konnte das nicht
sehen: er sucht Funktionen mit dem **Namen** `root`, die ihn nicht
weitergeben. Hier hieß der Parameter `doc_root` — ein Name, zwei Mengen,
zum zweiten Mal in dieser Akte (Runde 23), diesmal beim Parameter.

| Was | vorher | jetzt |
|---|---|---|
| `_resolve_test_root` | `git rev-parse` ohne `cwd` | `cwd=str(repo_root(doc_root))` |
| Prüfung | nur Glieder (`root`-Name) | `_git_callers_without_cwd`: Wirkung |
| Test | keiner | Klon mit eigenem Commit, zwei roots, zwei shas |

**Der Zwillingsbeweis:** mit entfernter `cwd`-Zeile meldet der Selbsttest
`Kette offen: _resolve_test_root ignoriert root (… == …)` — zwei FAIL.
`touch`-Immunität und Identität sind seither für **beide** Repos
gemessen: Klon `dc8be1e`, eigen `d33258b9`.

**`version_line` ist keine Ausnahme.** Eine Ausnahme, die eine Funktion
ohne `root` ist, wäre die Duldung genau des Falls, der in Runde 39
dreizehn Stellen erzeugte. `_git_callers_without_cwd` prüft die
**Wirkung**, nicht die Zugehörigkeit zu einer Liste: jede Funktion, die
`git` ohne `cwd` und ohne Pfadargument ruft, ist ein Fund — auch eine,
die keinen Parameter hat, auch eine, die keinen braucht.

### §71.30 — Runde 41: Ableiten ist zirkulär, wenn die Quelle prüft

Die Acht-Literale-Liste (`_DEFAULT_PROBE_ANCHORS`) war die Abschrift der
`§A-KR`-Marker im Code — derselbe Fehler, den §2b dieser Runde am
Zahlen-Guard abschaffte. Jetzt:

| | vorher | jetzt |
|---|---|---|
| Quelle | Tuple aus 8 Literalen | `_probe_anchors(src)` liest den Code |
| Zählung | Anker gegen Liste | Anker gegen Fließtext, Marker als Cut |
| Wache | Anwesenheit | Anwesenheit + **Größe** + **Grund** |
| Drift | still (Liste nachziehen) | rot (`_PROBE_ANCHOR_EXPECTED`) |

**Die Zirkularität, benannt:** wer Anker **und** Marker löscht,
verschwindet aus der Menge, und eine kleinere Menge ist für sich kein
Fehler. Deshalb `_PROBE_ANCHOR_EXPECTED = 8` mit Herkunft daneben
(Runde 40, vier Default-Zweig + vier fremder Ort) und ein Test, der alle
Marker entfernt und prüft, daß der Guard **rot** wird. Er wird es:
7 statt 8.

**Der erste Ableitungsversuch zählte 10 — und beide Extras waren meine
eigenen Kommentare.** Eine Ableitung, die ihren Beschreibungstext
mitliest, zählt ihre Beschreibung als Beweis. Zwei Schnitte: `§A-KZ`
(Markerblock) und `_PROBE_ANCHOR_ORIGIN` (Herkunftstext). Dieselbe Form
traf danach den Größen-Guard im Selbsttest selbst — die Zeile
`quiet = prod.replace("  # §A-KR", "")` ist ein Marker. Der Marker wird
jetzt zur Laufzeit gebaut (`"  # " + "\u00a7A-KR"`), sonst zählt die
Wache sich selbst und ist blind.

**`8/13` bleibt `8/13`, und das ist begründet:**

| Gruppe | n | warum keine Ausnahme im schlechten Sinn |
|---|---|---|
| Default-Zweig-Proben | 4 | prüfen den Default — ihn zu übergeben hieße, den Gegenstand zu entfernen |
| fremder Ort absichtlich | 4 | `_snapshot_path(root) == _snapshot_path()` ist der **Beweis**, daß `root` wirkt |

Jede der acht trägt ihren Grund **in der Zeile** (`# §A-KR bewusst: …`),
und die Wache prüft ihn: ein Marker ohne Grund ist rot.

### §71.31 — Runde 41: achtundzwanzig ist jetzt eine Messung

`>>>` kommt in `CLAUDE.md` **null Mal** vor. Die 28 Zusagen standen im
Nenner und in keiner Prüfung. Drei Wege, einer gewählt — der dritte,
weil er den Zustand korrekt beschreibt:

| Weg | Ergebnis | Nebenwirkung |
|---|---|---|
| in `>>>` ziehen | gemessen | Prosa wird Code, zwei Orte pflegen |
| aus der Zahl nehmen | `433` | Aussagen verschwinden still, bestehen weiter |
| an `claim()` binden | ungemessen, **nicht driftfähig** | — |

`_self_test_claim_count()` liest `len(rep.claims)` aus einem echten Lauf
gegen `CLAUDE.md` und vergleicht gegen `_CLAIM_COUNT_EXPECTED = 28`.
Herkunft im Kommentar: Runde 40 (`_status_line`), nachgezählt Runde 41
aus `--json-report`. **Gegenprobe:** halbierter Text → 24 Zusagen → rot.
Die Zahl ist damit keine Konstante mehr, die jemand pflegen muß, sondern
das Ergebnis einer Messung an der Doku, die sie behauptet.

### §71.32 — Runde 42: die Kopfzahl hatte zwei Lesarten und nannte keine

`223` im eigenen Baum, `151` im Klon — **vor** Runde 41 war das dieselbe
Zahl, weil der Lauf mit fremdem `root` den eigenen Baum maß. Nach dem
Fix sind es zwei Zahlen, und die Kopfzeile nannte keine davon.

| Feld | Quelle | Gegenprobe | gemessen |
|---|---|---|---|
| `root` | aufgelöster Bezugsraum | fremder Klon | `/private/tmp/klonprobe` |
| `sha256` | Hash der gelesenen `CLAUDE.md` | geänderte Datei | `69159540db89` → `8537812f6ab8` |
| Zahl | `Checks` | — | — |

Die Zeile steht **nach** der Zahl mit ihren Gründen und **vor** dem
Problemzähler — die Abweichungen gelten für diese Datei, nicht für den
Namen `CLAUDE.md`, den beide Reports tragen. Erster Einbau zerriß den
Satz `(nicht doctest-gedeckt), 0 Abweichungen`; gemessen, nicht vermutet.

**Die 151 sind kein Befund.** Der Klon hat keine `scripts/`:

| Art | n |
|---|---|
| tote Referenz | 71 |
| Befehl zeigt ins Leere | 53 |
| Suite zugesagt, Skript fehlt | 16 |
| Datei fehlt | 10 |

Sie stehen jetzt als **eigener Lauf mit eigenem `root`** in der Akte,
nicht als Differenz `223 − 151 = 72` in einer Zeile.

### §71.33 — Runde 42: ein Instrument, das seine Quelle liest, findet sich selbst

Drei Runden, drei Formen derselben Selbstmitzählung, dreimal einzeln
gefixt — **ohne gemeinsamen Preset**:

| Runde | Instrument | zählte sich mit als | entdeckt durch |
|---|---|---|---|
| 40 | Ankerliste | Abschrift der Anker | 20 gegen 8 |
| 41 | `_probe_anchors` | eigener Kommentar | 10 gegen 8 |
| 41 | Wache der Ableitung | eigener Marker | blind |

Der Nenner ist nicht die Liste der Fixes, sondern die **Lage**: das
Instrument liegt im Meßbereich. Ein Preset deckt alle vier:

| Instrument | Preset | erwartet | rot gemessen durch |
|---|---|---|---|
| `_probe_anchors` | Marker **nur** im Kommentar | `()` | `not ln.lstrip().startswith("#")` entfernt → 19 |
| `_probe_anchors` | Marker im Code | 1 Anker | — |
| `_git_callers_without_cwd` | `git` nur im Kommentar | `[]` | — |
| `_git_callers_without_cwd` | `git` in Mini-Quelle | Fund | `words[:1] == ["git"]` → `["never"]` |
| `_status_line` | zwei roots | zwei Zeilen | `if root is not None` → `if False` |

**`_git_callers_without_cwd` gegen sich selbst:** die eigene Datei
enthält keinen offenen `git`-Aufruf (`[]`). Das ist der Zustand — der
Test ist der Nachweis, daß es so bleibt.

**Der Marker zur Laufzeit ist die halbe Antwort.** Gebaut heißt: der
Quelltext enthält ihn nicht. Die andere Hälfte ist die Probe oben —
sonst ist „zur Laufzeit gebaut“ eine Zusicherung, die hält, bis jemand
den Bau zurückdreht.

### §71.34 — Runde 42: 24 war keine Halbierung

Die Gegenprobe schnitt den Text und sah `24` — sie belegte, **daß** die
Zahl sich ändert, nicht **was** sie mißt. `24` ist keine Hälfte von
`28`; ein Schnitt an einer beliebigen Stelle läßt unterschiedlich viel
stehen.

**Der Extraktor liefert jetzt Positionen.** `claim(field, count, line,
text)` — und der Test schneidet an einer **benannten** Zeile
(`Render-Pipeline`, L1493) und prüft, daß kein Fund dahinter liegt:

```
28 Zusagen gesamt
27 vor dem Schnitt (Positionen 1393, 1428, 1462 …)
 1 dahinter — und genau eins wird erwartet
```

**Formabhängigkeit (§A-MC), an der Konstante vermerkt:** erkannt werden
`N/N tests passed` und `N/N Tests`. Ein umformulierter Satz ohne
Bedeutungswechsel fällt aus der Zählung → Test rot, ohne Verlust. Der
Preis der Ableitung, derselbe wie bei den Ankern: eine Form, die nur von
der Form gehalten wird.

### §71.35 — Runde 42: acht Produktion, neun Prüfstand

`_status_line` bekam einen optionalen `root`. Damit fielen die Aufrufe
im `--self-test` unter die Ausnahmen — **von 8 auf 17 in einem Edit**,
und der Größen-Guard meldete es sofort.

Die 9 sind keine Ausnahmen im Produktionspfad: der Prüfstand ist ein
anderer Ort, kein geduldeter. Getrennt gezählt
(`_PROBE_ANCHOR_SELFTEST_EXPECTED = 9`), getrennt bewacht — und der
Zirkularitätstest prüft jetzt die **Produktionsmenge**, nicht die Summe.
Eine Zahl, die beide Mengen summiert, sagt in Runde 43 `17` und niemand
weiß, warum.

**Was am 20.10. auf dem Tisch liegt: 216 Tests, 24/24 Selbsttests plus
drei neue Wächter, eine Kopfzahl mit `root` und `sha256`, Zusagen mit
Positionen, acht Produktions-Ausnahmen mit Größen-Guard — und eine
Akte, in der die 151 des Klons einen eigenen Lauf mit eigenem `root`
hat, statt eine Differenz ohne Bezug zu sein.**
`223` und `151` waren vor Runde 41 **dieselbe** Zahl — der Lauf mit
fremdem `root` maß den eigenen Baum. Nach dem Fix sind es zwei Zahlen,
und die Zeile, die sie druckt, sagte nicht, welche. Jetzt:

```
223 ... 0 Abweichungen
Bezug: root=/Volumes/…/agent_x_storage, CLAUDE.md sha256:69159540db89
```

**Ein Leser in Runde 50 kann zwei Reports unterscheiden, ohne sie zu
datieren.** `root` und `sha256` ändern sich unabhängig voneinander,
beides gemessen: fremder Klon → anderer `root`, geänderte Datei →
anderer Hash (`69159540db89` → `8537812f6ab8`).

**Und die 151 sind nicht 72.** Der Klon hat keine Testskripte, also:

| Art | n |
|---|---|
| tote Referenz | 71 |
| Befehl zeigt ins Leere | 53 |
| Suite zugesagt, Skript fehlt | 16 |
| Datei fehlt | 10 |
| **Inventar-Dokument fehlt** | **1** |
| **Summe** | **151** |

`71 + 53 + 16 + 10 = 150` — die Tabelle der Runde 42 schloß auf 150 und
ließ die einzige Klasse weg, die keine der vier war. Sie existiert:
`check_doc_inventories` meldet sie. **Eine Zerlegung, die auf 150
schließt und 151 zählt, erklärt nichts; sie sieht nur so aus.** Und die
fehlende Zeile ist genau die, in der eine echte Abweichung stehen
könnte — die ohne Kategorie. In dieser Akte wurde `223 + 210 + 28 = 461`
als geschlossen vorgeführt; hier war sie offen, und niemand hatte
addiert.

**151 ist ein Kalibrierlauf, keine Zahl.** Ein Lauf gegen einen Klon ohne
`scripts/` mißt die Abwesenheit von `scripts/`, nicht die
Übereinstimmung von Code und Doku. Der Klon taugt als `root`-Beleg — er
zeigt, *daß* `root` wirkt — und nicht als Abweichungsquelle. Die Trennung
steht jetzt hier, damit in Runde 45 niemand 151 als Befund über das Repo
liest.

**Das Instrument im Meßbereich, dreimal in drei Runden:**

| Runde | Instrument | zählte sich mit als | entdeckt durch |
|---|---|---|---|
| 40 | Ankerliste | Abschrift der Anker | 20 gegen 8 |
| 41 | `_probe_anchors` | eigener Kommentar | 10 gegen 8 |
| 41 | Wache der Ableitung | eigener Marker | blind |

Der gemeinsame Nenner ist eine Zeile: **ein Meßinstrument, das seine
eigene Quelle liest, findet sich selbst.** Jetzt ein Preset, vier
Instrumente: `"# §A-KR nur im Kommentar"` → **null** Anker;
`"# subprocess.run(['git','status'])"` → **null** Funde. Beide rot
gemessen, indem die Kommentarprüfung entfernt wurde (`19` Anker,
`_probe_anchors zaehlt einen Kommentar als Anker`).

**Und `_git_callers_without_cwd` gegen sich selbst:** die eigene Datei
enthält keinen offenen `git`-Aufruf — und der Zwilling beweist, daß das
Instrument nicht blind ist (`git ohne cwd` in einer Mini-Quelle → Fund).

**`24` war keine Halbierung.** Die erste Gegenprobe schnitt ins Leere:
27 von 28 Claims standen vor der Schnittzeile. Jetzt liefert
`claim(field, count, line, text)` die **Position**. ~~Der Test schneidet
an einer benannten Zeile und prüft, daß kein Fund dahinter liegt.~~
**Runde 43 hat ihn verschärft (§71.39):** der Schnitt lag bei der letzten
Zusage, und ein Extraktor mit irgendeiner kleineren Zeilennummer bestand.
Jetzt liegt er am **Median**, beide Hälften werden einzeln gezählt, und
die Grenze ist absolut — der erste Versuch mit `positions[-1]` war grün,
weil die Erwartung aus dem Prüfling kam.

**Der Preis, benannt:** der Extraktor erkennt `N/N tests passed` und
`N/N Tests`. Ein umformulierter Satz ohne Bedeutungswechsel fällt aus der
Zählung und macht den Test rot, ohne daß etwas verloren ist. Dieselbe
Formabhängigkeit wie bei den Ankern (§A-MC) — sie steht an der Konstante
**und in der Meldung** (`REDAKTION? … dann Zahl anpassen, nicht Text`),
damit in Runde 45 niemand einen Fehler sucht, der eine Redaktion ist.

**Ausnahmen: ~~8 Produktion + 9 Prüfstand~~ → 18, alle Produktion.**
~~Die Aufrufe im `--self-test` prüfen die Form, nicht einen Baum.~~
**Runde 43 nahm das zurück (§71.37):** sie stehen in `main`s Pfad. Ein
`--self-test`-Aufruf ist Produktionscode, der den Prüfstand aufruft; eine
dritte Kategorie gibt es nicht. Der Aufruf ohne `root` steht jetzt als
**Paar** neben seinem Partner mit `root`.

**Was am 20.10. auf dem Tisch liegt: 216 Tests, 24/24 Selbsttests plus
drei neue Wächter, eine Kopfzahl mit `root` und `sha256`, Zusagen mit
Positionen, achtzehn Produktions-Ausnahmen mit Größen-Guard — und eine
Akte, in der die 151 des Klons einen eigenen Lauf mit eigenem `root`
hat.**



### §71.36 — Runde 43: die Tabelle schloß auf 150, gezählt waren 151

`71 + 53 + 16 + 10 = 150`. Die Runde-42-Zerlegung ließ **eine** Klasse
weg — und gerade die ohne Kategorie ist die, in der eine echte
Abweichung stehen könnte. Sie existiert (`check_doc_inventories`):

| Art | n |
|---|---|
| tote Referenz | 71 |
| Befehl zeigt ins Leere | 53 |
| Suite zugesagt, Skript fehlt | 16 |
| Datei fehlt | 10 |
| Inventar-Dokument fehlt | 1 |

**Die Zerlegung wurde nie addiert.** Derselbe Fehler wie eine Zahl ohne
Nenner, nur mit vertauschten Vorzeichen: eine Tabelle, die aussieht, als
erklärte sie die Zahl, und es nicht tut.

**Und `151` ist keine Zahl, sondern ein Kalibrierlauf.** Ein Klon ohne
`scripts/` mißt die Abwesenheit von `scripts/`. Der Lauf belegt, daß
`root` wirkt — nicht, daß Code und Doku übereinstimmen.

### §71.37 — Runde 43: die neun stehen in `main`, nicht im Prüfstand

Runde 42 buchte neun `_status_line`-Aufrufe als „Prüfstand, kein
geduldeter Fall". **Sie stehen in `self_test_check_counts`, das `main`
aufruft.** Für die Frage „braucht er `root`?" gibt es genau zwei Fälle:

| Fall | Konsequenz |
|---|---|
| er braucht `root` | Verstoß, keine Ausnahme |
| er braucht es nicht, weil er gegen den Default laufen soll | `cwd`-Verhalten — und K1 zählt genau das als Verstoß |

Eine dritte Kategorie gibt es nicht. Die Begründung der Runde 42 war die,
die Runde 41 selbst ausgeschlossen hatte: *eine Ausnahme, die eine
Funktion im Produktionscode mit Default-Verhalten ist.*

**Der Ausweg ist der Zwilling.** Ein Aufruf ohne `root` braucht seinen
Partner daneben — erst das Paar ist ein Beweis:

```
line      = _status_line(Checks(223, 210, 0), 0)                 # kein Bezug
line_pair = _status_line(Checks(223, 210, 0), 0, Path("/tmp"))   # Bezug
```

Geprüft wird das **Paar**: die erste Zeile nennt keinen `Bezug:`, die
zweite nennt ihn, und die **Zahl bleibt gleich** — sonst änderte `root`
die Zählung statt den Bezug. Neun ohne Partner waren neun Hälften.

**Ausnahmen: 8 + 9 → 18, alle Produktion.**
`_PROBE_ANCHOR_SELFTEST_EXPECTED` gelöscht; der Größen-Guard prüft
wieder **eine** Menge. Die Zahl kam aus einer Messung, nicht aus einer
Entscheidung.

### §71.38 — Runde 43: ein Marker, der zwei Dinge bedeutete

Der Rot-Beleg der Runde 42 (19 statt 8) war erst der Beleg. Zweitens
hieß er: **elf weitere Zeilen trugen `§A-KR`** — Prosa, Erklärungen,
Zitate. Ein Wort an 19 Stellen, das 8 Mal einen Anker bezeichnet, ist ein
Wort mit zwei Bedeutungen. Runde 23, diesmal am Marker selbst.

Der Diskriminator war die **Zeilenform**. Das hält nur, solange niemand
umbricht: eine mehrzeilige Erklärung über einem Anker hat dieselbe Form
wie der Anker.

| | vorher | jetzt |
|---|---|---|
| Anker | `§A-KR` + nicht-Kommentarzeile | `§A-KR-ANCHOR` **und** nicht-Kommentarzeile |
| Erklärung | `§A-KR` in Kommentarzeile | `§A-KR` (beliebig) |

**Beide Bedingungen bleiben nötig — gemessen.** Nur der eindeutige Marker
zählte `"# §A-KR-ANCHOR nur im Kommentar"` als Anker: eine
Kommentarzeile, die den Marker *nennt*, ist kein Anker. Nur die Form
zählte die Prosa mit. Erst beide zusammen sind eindeutig — ein Wort
allein nicht, eine Form allein nicht.

### §71.39 — Runde 43: der Schnitt prüfte die Grenze, nicht die Verteilung

Der Halbier-Test schnitt bei `L1493` — der **letzten** Zusage. Ein
Extraktor, der irgendeine Zeilennummer davor lieferte, bestand ihn:
geprüft wurde „die Position existiert und ist plausibel", nicht „sie ist
richtig".

**Jetzt: Schnitt am Median, beide Hälften einzeln.**

```
Positionen: 116, 317 … 1393, 1428, 1462, 1493   (Median 704)
vor dem Schnitt  : 18 von 28
hinter dem Schnitt: 10 von 28
```

**Und der erste Versuch mit `positions[-1]` war grün** — weil die
Erwartung aus derselben Zahl berechnet wurde. Eine Probe, die ihre
Erwartung aus dem Prüfling ableitet, ist blind; dieselbe Form wie §A-KZ,
eine Ebene höher. Die Grenze ist jetzt **absolut** (Anteil in der Mitte
der Verteilung); mit `positions[-1]` meldet sie
`Schnitt nicht in der Verteilungsmitte: 27 von 28 davor (96%)`.

**§A-MC im Testnamen:** die Meldung endet mit
`REDAKTION? … dann Zahl anpassen, nicht Text`. Ein umformulierter Satz in
`CLAUDE.md` fällt aus der Zählung — ohne Verlust, aber nur, wenn der rote
Test als Redaktion erkannt wird und nicht als Befund.

**Einundvierzig.** Der Prüfer, der dreizehn Stellen fand, sah Glieder und
keine Ketten — und die Kette war echt: `_resolve_test_root(doc_root)` rief
`git rev-parse --show-toplevel` ohne `cwd`. `check_claude_md.py
/tmp/klon` las die Tests des **eigenen** Repos, 151 Abweichungen im
fremden Baum waren 223 im eigenen. Zwei Glieder ohne Parameter, jedes für
sich unsichtbar; der Glieder-Prüfer konnte es nicht finden, weil er nach
dem **Namen** `root` fragt und der Fehler an der **Wirkung** hing.

**Der Prüfer fragt jetzt nach der Wirkung:** `_git_callers_without_cwd`
sucht jeden `subprocess.run(["git", …])` ohne `cwd=` und ohne genannten
Pfad — egal wie die Funktion heißt, in der er steht.

**Und die Ausnahmen sind abgeleitet.** Die Acht-Literale-Liste war genau
die Abschrift, die §2b der Runde abgeschafft hat. Jetzt liest
`_probe_anchors` den Quelltext: `§A-KR` ist die Markierung, die Zeile der
Anker, die Zahl entsteht. Preis benannt: wer Anker **und** Marker
löscht, verschwindet — deshalb `_PROBE_ANCHOR_EXPECTED = 8` mit Herkunft
daneben und einer Probe, die gelöschte Marker entfernt und prüft, daß der
Guard rot wird. **Die 8/13 bleibt 8/13** — begründet, nicht geduldet: vier
Default-Zweig-Aufrufe (die Prüfung eines Defaults *braucht* den Default)
und vier Aufrufe mit absichtlich fremdem Ort (der Zwillingspfad-Test ist
genau der Beweis, daß `root` wirkt). Keine davon ist `version_line`:
Funktionen ohne `root` sind in dieser Klasse keine Ausnahme, sondern
außerhalb — und brauchen eine eigene Wache, die jetzt existiert.

**Die 28 sind an `claim()` gebunden.** `_self_test_claim_count` zählt
live gegen `CLAUDE.md` und vergleicht gegen `_CLAIM_COUNT_EXPECTED = 28`
mit Herkunft. Halbierter Text → 24 Zusagen → rot. Ein Literal wäre in
Runde 44 nicht mehr herleitbar; diese Zahl ist eine Messung.

**Was am 20.10. auf dem Tisch liegt: 216 Tests, 24/24 Selbsttests plus
drei neue Wachen (Kette, Ausnahmen-Ableitung, Zusagen), eine
Herkunftszeile, die im fremden Repo den fremden `sha` nennt
(`dc8be1e` gegen `d33258b9`), acht abgeleitete Ausnahmen mit
Größen-Guard, und ein Nenner von `461 gezaehlt (433 gemessen + 28
Zusagen)` — dessen einer Teil weiter ungemessen ist, jetzt aber nicht
mehr still driften kann.**

### §71.40 — Runde 44: die Probe für die Probe war blind

Der wertvollste Satz der Runde war nicht über den Prüfling, sondern über
das **Verfahren**: von drei Gegenproben waren zwei zuerst grün. Es war
das dritte Mal dieselbe Form, und das erstemal, daß sie durch **Hinsehen**
gefunden wurde statt durch eine Zahl, die nicht sein konnte.

| Runde | was sich selbst maß | gefunden durch |
|---|---|---|
| 40 | Ankerliste zählte ihre Abschrift mit | 20 gegen 8 |
| 42 | Erwartung kam aus `positions[-1]` | 96 % davor |
| 43 | Gegenproben (b), (c) grün | Hinsehen |

Hinsehen ist die Ressource, die in Runde 50 nicht mehr da ist. Die
Antwort ist keine vierte Probe, sondern eine Zeile — und ein Prüfer, der
sie durchsetzt. **§A-ML.**

### §71.41 — Runde 44: jede Erwartung ist ein Literal, und der Prüfer sieht es

Die Regel:

> Jede Erwartung im Test ist ein Literal im Test. Kein `positions[-1]`,
> kein `len(x)`, kein `median(...)` auf der linken Seite eines
> Vergleichs. Die Zahl steht da, mit Herkunft im Kommentar, und der
> Prüfling darf sie nur verfehlen.

`_self_test_literal_errors` ist derselbe Prüfer wie
`_git_callers_without_cwd`, nur gegen Tests: er parst jede
`_self_test*`-Funktion und meldet jeden Vergleich, dessen Seite
**berechnet** ist. Kalibrierung an acht Proben, Erwartungen als Literale:

| Probe | erwartet | gefunden |
|---|---|---|
| `positions[-1] < 0.25` (R42-Form) | 1 | 1 |
| `median(xs) > 3` | 1 | 1 |
| `len(xs) != 3` | 0 | 0 |
| `total(own) != total(clone)` (zwei Messungen) | 0 | 0 |
| `p["kind"]` (konstanter Index) | 0 | 0 |
| `"0" not in sel` (String) | 0 | 0 |
| `f("a" + anch + "b")` (Konstruktion) | 0 | 0 |
| `f(xs)[-1] > 3` | 1 | 1 |
| **eigene Datei** | 0 | **0** |

**Die Ausnahmen sind benannt, nicht geduldet:** zwei Messungen dürfen
verglichen werden (die Aussage ist die Differenz), ein konstanter Index
ist eine Formaussage, ein selbstgeschriebener Eingabetext ist eine
Konstruktion. Was bleibt, ist die eine Klasse, die dreimal zugeschlagen
hat.

**Und der Prüfer prüft sich.** `_self_test_literal_errors(src)` nimmt
Quelltext, damit ich ihn gegen die R42-Form laufen lassen kann — er hätte
den Fehler aus Runde 42 gefunden, bevor er passierte.

**Und er hatte selbst ein Loch.** `median(x)[0]` ging durch: der Index
`[0]` ist konstant, also „Formaussage" — aber der **Träger** `median(x)`
ist eine Ableitung. Die Angriffsprobe fand es, nicht das Hinsehen:

```
positions[-1]     gefunden
f(x)[-1]          gefunden
median(x)[0]      gefunden     <- vorher offen
f("a"+x+"b")      gefunden
f("a"+anch+"b")   sauber       (Konstruktion)
p["kind"]         sauber       (Formaussage)
rows[0]           sauber       (Konstante)
len(xs) != 3      sauber       (Literal)
```

Der Index entscheidet nicht; der Träger entscheidet. Das ist dieselbe
Lehre wie §71.42 eine Ebene tiefer: die Zahl, die zählt, ist die
gezählte, nicht die durchgereichte.

### §71.42 — Runde 44: der Zwilling belegte Durchreichung, nicht Bezug

Der alte Zwilling rief `_status_line(Checks(223, 210, 0), 0)` und
`_status_line(Checks(223, 210, 0), 0, Path("/tmp"))`. Die 223 war
**beide Male Eingabe**. Daß die Zahl gleich bleibt, war eine Tautologie.

Die Zahl, deren Abhängigkeit von `root` zählt, ist die **gezählte** aus
der Kette `_resolve_test_root → Datei lesen → zählen` — genau der Fall,
der in Runde 41 siebenundsiebzig Doctests aus dem falschen Repo las.
Jetzt:

```
count(own)   = 102
count(clone) = 155        # Klon ohne scripts/, mehr Befunde
```

**Zwei Bäume, zwei Zahlen — die Differenz ist die Aussage.** Geprüft wird
die Ordnung, die aus der Struktur folgt (jeder fehlende Pfad ist ein
Befund), nicht die Zahl: ein `assert total(a) != total(b)` wäre auch dann
grün, wenn beide 0 sind.

**Der Testname sagt jetzt, was er prüft.** Der Formattest heißt in seiner
Meldung `Formatprobe: Partner aendert die Eingabezahl (erwartet: nur der
Bezug)` — `Path("/tmp")` ist kein Repo, und das ist als Formatprüfung in
Ordnung, solange sie nicht mehr behauptet.

### §71.43 — Runde 44: die Klassenliste kommt aus dem Lauf

Die Fünf-Klassen-Tabelle der Akte war eine Abschrift. Die fünfte
(`check_doc_inventories` → `Inventar-Dokument fehlt`) stand die ganze
Zeit im Code und nicht in der Tabelle; die Summe schloß eine zu niedrig.

`calibration_run(root)` ruft die fünf Prüfer einzeln und **gibt die
Klassenliste aus**:

```
Zeilen       0
Referenzen   0
Wellen       0
Inventare    0
Tests        0
total        0          # eigener Baum, Doku sauber
```

Kommt ein sechster Prüfer, steht er in der Ausgabe — ohne daß jemand die
Akte nachzieht. Die Gegenprobe ist strukturell: `_self_test_calibration_classes`
prüft, daß **alle fünf** erscheinen und die Summe zu den Klassen paßt.
Was diese Funktion nicht selbst schließt, ist ein Befund, für den kein
Prüfer zuständig ist; dann meldet der Summenvergleich eine Differenz.

### §71.44 — Runde 44: `_probe_anchors` gegen den eigenen Funktionsteil → 0

§4 der Runde war die schärfste: „Code-Zeile" hieß bisher „fängt nicht mit
`#` an". Dann ist `x = "# §A-KR-ANCHOR"` ein Anker — und das Blind-Fixture,
das den Marker als String baut, zählt sich mit. **Das ist Runde 41 mit dem
neuen Marker.**

Gemessen: `_probe_anchors('x = "# §A-KR-ANCHOR"')` gab die Zeile zurück.
Jetzt entscheidet `tokenize.COMMENT`: ein Kommentar **an** einer
Code-Zeile ist ein Anker, ein String in einer Code-Zeile nicht, ein
reiner Kommentar nicht.

```
Fixture-String   -> ()
echter Anker     -> ('g()  # §A-KR-ANCHOR grund',)
reiner Kommentar -> ()
ganze Datei      -> 18 Anker
ab def _probe_anchors -> 0
```

Die letzte Zeile ist die Probe: gegen die **ganze** Datei sind 18 richtig,
gegen den **eigenen Funktionsteil** müssen es 0 sein. `_self_test_probe_anchors_self`
prüft es — und greift, wie die Gegenprobe zeigt: mit ausgebautem
`tokenize`-Filter meldet sie zwei Fehler
(`zaehlt einen String als Anker`, `findet den echten Anker nicht`).

**Nebenbei aufgeräumt:** die neun `_status_line`-Aufrufe im `--self-test`
stehen jetzt in **einer** Menge mit ihren Partnern, `_PROBE_ANCHOR_SELFTEST_EXPECTED`
ist gelöscht. 18 gemessen statt entschieden — Produktion und Prüfstand in
einer Zahl, also prüft der Zirkularitätstest alle achtzehn.

### §71.45 — Runde 44: was der Prüfer am Prüfer fand

Zwei eigene Fehler sind während der Runde **durch den Wächter** gefallen,
nicht durch Hinsehen:

1. `# 24 + 1 (root …) + 1 … = 27` in einem Kommentar → `Zahl 24 ohne
   Herkunft in Prosa`. Der Guard aus §7 greift auch gegen die Buchung
   selbst; die Summe gehört in die Ausgabe, nicht in den Kommentar.
2. `# Herkunft: … eigen 102, Klon 155` → zwei Zahlen ohne Herkunft.
   Ersetzt durch die Aussage ohne Zahl; die Zahl ist eine Stichprobe,
   die Ordnung ist die Behauptung.

**Das ist die Bewegung, die die Runde verlangt:** die dritte Art der
Selbstmessung wurde in Runde 43 durch Hinsehen gefunden; in Runde 44
fanden zwei Fälle der vierten Art den Wächter, und der Prüfer für die
dritte Art (`_self_test_literal_errors`) läuft in `main`.

### §71.47 — Runde 45: der Ergebnisblock schloß auf 135 und behauptete 151

Die Nachricht der letzten Runde stand da mit einem Block:

```
"total": 151, "chain_total": 151, "unclassified": 0,
"classes": [("Referenzen", 124), ("Zeilen", 10), ("Inventare", 1),
            ("Wellen", 0), ("Tests ohne Skript", 0)]
```

**124 + 10 + 1 + 0 + 0 = 135.** Der Code rechnete 151; die Akte behauptete
151; die **Zerlegung** darin schloß auf 135. Die 16 fehlten — und sie
standen in `Wellen: 0`, also genau in der Klasse, die den Fehler trägt,
den derselbe Abschnitt zwei Absätze später beschreibt
(`check_counts` ohne `root` liefert im Klon null statt sechzehn).

**Das ist die dritte Messung, die nicht gerechnet wurde.** Zwei Wege
stimmten überein (`total == chain_total`), und die Zerlegung stimmte mit
keinem von beiden. Der Vergleich prüfte die Verdrahtung, nicht die
Arithmetik.

### §71.48 — Runde 45: `sum(classes) == total` als harte Zeile

`calibration_run` gibt jetzt drei Zahlen, die **unabhängig** entstehen:

| Zahl | entsteht durch |
|---|---|
| `total` | Summe der Klassenlängen |
| `chain_total` | die `main`-Kette, ein zweiter Lauf |
| `reported` | was jeder Prüfer in seiner eigenen Befundliste meldet |

Der Selbsttest prüft alle drei Gleichungen:

```
total == sum(classes)
sum(classes) + unclassified == chain_total
reported == total
```

Auf beiden Bäumen: eigen `0/0/0`, Klon `151/151/151`. **Die dritte Zahl
ist die Antwort auf „zwei Wege, die denselben Fehler gleich falsch
gehen, sind ein Weg mit zwei Ausgängen":** `reported` entsteht nicht aus
`classes`, sondern aus den Berichten, die die Prüfer selbst liefern.

### §71.49 — Runde 45: die Lücke existiert jetzt per Konstruktion

`unclassified == 0` auf beiden Bäumen ist nur dann ein Lückenprüfer, wenn
in mindestens einem Baum etwas in der Lücke steht. Der Klon zeigt sie —
aber der Klon ist ein **Artefakt**, das jemand von Hand baut. Ein
Prüfmittel, das jemand von Hand baut, ist keins.

`calibration_run` nimmt jetzt `extra_checkers`: Prüfer, die **nur** in
der Kette laufen und in keiner Klasse stehen. Der Selbsttest baut einen
Baum und schiebt einen Prüfer mit genau **einem** Befund hinein:

```python
gap = calibration_run(root, extra_checkers=(("Luecke", _extra),))
# unclassified == 1        <- die Lücke wird gezaehlt
# chain_total == total + 1 <- die Kette traegt ihn
# "Luecke" not in classes  <- er ist nicht in die Klassen gerutscht
```

**Damit wird der Selbsttest rot, ohne daß jemand einen Klon anlegt** —
dieselbe Bewegung wie `_PROBE_ANCHOR_EXPECTED`: eine Zahl, die rot werden
**muß**, damit man weiß, daß der Prüfer lebt.

### §71.50 — Runde 45: `_git_callers_without_cwd` war ein Sonderfall

Der Prüfer, der in Runde 41 siebenundsiebzig Doctests aus dem falschen
Repo las, suchte nach `git`-Aufrufen ohne `cwd`. Der Fehler der letzten
Runde war `check_counts` ohne `root` — **ein Lesezugriff, kein
`git`-Aufruf.** Der Prüfer deckte den Sonderfall ab, und der Sonderfall
war der, an den man sich erinnert hatte.

`_reads_without_root` fragt nach der Klasse: liest eine Funktion Dateien
an einem Ort, den ein **Parameter** trägt, ohne einen Ortsparameter zu
haben?

```
check_bad(doc, rep):   (Path(doc) / 'scripts').glob('*.py')   -> gefunden
check_rel(rep):        open('CLAUDE.md')                      -> gefunden
check_ok(doc, root):   (root / 'scripts').glob('*.py')        -> sauber
check_self(rep):       Path(__file__).read_text()             -> sauber
check_lit(rep):        open('/etc/hosts')                     -> sauber
eigene Datei                                                 -> 0
```

**`doc` ist kein Ortsparameter.** Das war der Kern: `doc` ist der
Dokumenttext, `doc_root` der Ort. Die Whitelist der legitimen Namen
enthielt `doc` und `src` — und damit genau den Fehler.

### §71.51 — Runde 45: was die Runde selbst fand

Die vierte Buchung (`Prüfer für Lesezugriffe`) fand beim Bau **drei**
eigene Fehler:

1. `ok_names` enthielt `doc` — der Prüfer war blind für seinen eigenen
   Anwendungsfall.
2. Der Pfad steckt im **Träger** von `.glob()`, nicht im Argument:
   `(Path(doc) / "scripts").glob("*.py")`.
3. `open("CLAUDE.md")` ohne `Path(...)` rutschte durch.

Jeder der drei wurde von einer Probe gefunden, keine von Hinsehen.
**Das ist die Antwort auf die Frage der letzten Runde** — die dritte Art
der Selbstmessung braucht kein Auge mehr, sie braucht eine Probe mit
einem Literal, das verfehlt werden kann.




Vierzig Runden, und der Prüfer, der dreizehn Stellen fand, fand sie erst
im fünften Versuch — und im sechsten fand ein Preset, dass er beim
Einstieg dasselbe Loch hatte wie beim Überspringen.

**Aber der Satz dieser Runde ist die Zeile.** Sie stempelte beim
Schreiben, was sie nur beim Lesen wissen konnte. Alle anderen Caches in
dieser Akte waren an derselben Stelle repariert: `mtime`, `root`,
Dateiinhalt. Diese prüfte *wann* gedruckt wurde statt *was* dasteht.

**Was am 20.10. auf dem Tisch liegt: 216 Tests, 24/24 Selbsttests, ein
Prüfer mit sieben Fehlerklassen an sieben Presets, einer Produktionsprobe
und einer Blind-Wache, dreizehn gefundene Stellen (acht davon benannte
Ausnahmen) — und eine Kopfzeile, die ihre Zerlegung mitträgt:
`461 gezaehlt (433 gemessen + 28 Zusagen, nicht doctest-gedeckt)`
und eine Rundentabelle, deren Zeile sagt, ob ihr Inhalt der des Commits
ist, statt ob sie seit dem Commit angefasst wurde.**



Neununddreißig Runden, und der Zähler hat jetzt vier Kategorien, einen
Test und zwei rote Mutationen — und die fünfte Kategorie, die vorher in
keinen der beiden Eimer fiel, hat einen eigenen bekommen.

**Aber der Satz dieser Runde ist nicht der Zähler. Er ist der Cache und
die Suche.** Der Cache, mit einem `root` gemessen, hätte den Fehler
verursachen können, den der fehlende Parameter nur ausgelöst hat — er
war korrekt, aber das war eine Annahme. Und die Suche, die sechs
Aufrufer fand, suchte nach dem Fund und nicht nach dem Fehler: der
zweite `rg` fand dreizehn Stellen, darunter `main` selbst.

**Was am 20.10. auf dem Tisch liegt: 216 Tests, 24/24 Selbsttests, vier
benannte Annahmen, drei Gegenproben, ein Nenner von 461 (223 + 210 + 28),
ein AST-Prüfer mit fünf Presets und fünf benannten Ausnahmezeilen — und
ein System, dessen Zahl jetzt stimmt, dessen Menge aber erst seit dieser
Runde einen Namen hat.**



Dreiunddreißig Runden, und der Selbsttest läuft in CI, ist in drei
Umgebungen gemessen — und in der dritten stand `kein Vorlauf`, während
es dort **keinen Ort** gab. Eine Zusage über einen Pfad, der nicht
existiert, ist in derselben Familie wie eine Zahl ohne Nenner.

Der vierte Befund derselben Klasse in vier Runden wurde als Einzelfall
behoben, und der nächste Fall konnte erben — weil niemand das Harness
zurücksetzte. **Vier Mutationsfunde, vier Fixes an einem Fall: das ist
keine Serie von Zufällen, das ist eine fehlende Zeile.** Sie steht jetzt
zuoberst, mit einem Kreuztest, der sie beweist.

Und die zehn Runden 23–32, beschrieben als *dieselbe Bewegung*, waren in
ihren Fixes zehnmal dieselbe Bandage. Die Tabelle in §71 sagt das jetzt
in einer eigenen Spalte — und sie steht an **einem** Ort.

**Was am 20.10. auf dem Tisch liegt: 216 Tests, 24 Selbsttests, ein
Kreuztest gegen Zustandsvererbung, drei benannte Umgebungen, ein Nenner
von 433 und eine Rundentabelle, die ihre eigenen Bandagen zählt.**

### §71.46 — Runde 44: der Kalibrierlauf war selbst eine Handliste

§71.43 hat die Fünf-Klassen-Tabelle als Abschrift verurteilt und durch
`calibration_run` ersetzt. **Die erste Fassung kannte fünf Prüfer. `main`
fährt sechs.** `check_undocumented_tests` fehlte — dieselbe Form, nur
diesmal von mir gebaut, in derselben Runde, in der ich sie beschrieben
habe.

**Und sie war unsichtbar:** im eigenen Baum meldeten beide Wege null.
Eine Lücke, hinter der gerade nichts steht, ist keine Lücke, die man
sieht. Erst der Klon zeigte sie:

```
calibration_run(klon) = 135
main-Kette(klon)      = 151
```

**Der zweite Fehler kam beim Schließen des ersten.** `check_counts` gibt
ohne `root` andere Befunde als mit (im Klon: keine statt sechzehn) — die
Zahl hing am **Aufrufweg**. Das ist exakt der Fehler aus Runde 41, den
`_git_callers_without_cwd` gefunden hatte, und er stand wieder da, in der
Funktion, die ihn verhindern soll.

**Jetzt schließt der Lauf gegen die Kette, statt sich selbst zu glauben:**

```python
{
 "total": 151, "chain_total": 151, "unclassified": 0,
 "reported": 151,           # dritte Zahl: was die Prüfer selbst melden
 "classes": [("Referenzen", 124), ("Wellen", 16), ("Zeilen", 10),
             ("Inventare", 1), ("Tests ohne Skript", 0)]
}
```

`124 + 16 + 10 + 1 + 0 = 151`. **Diese Zeile ist die Buchung** — sie steht
hier, weil sie beim ersten Schreiben fehlte: der Block oben schloß auf
135 und behauptete 151, und die 16 fehlten in der Klasse `Wellen`, die
genau den Fehler trägt, den der Abschnitt beschreibt. Eine Abschrift in
der Akte über einem Code, der rechnet.

`unclassified` ist die Differenz, und der Selbsttest verlangt `0` auf
**beiden** Bäumen: eigen 0/0, Klon 151/151. Damit ist die zweite
Behauptung des Tests nicht mehr „alle Namen erscheinen", sondern
„dieselbe Zahl auf zwei Wegen" — und die ist auch dann rot, wenn ein
fehlender Prüfer gerade nichts meldet.

**Das ist der eigentliche Befund der Runde 44.** Nicht die Regel
(§71.41), nicht der Zwilling (§71.42), sondern: **ich habe denselben
Fehler in der Reparatur desselben Fehlers gemacht, zweimal, und beide
Male hat ihn eine Messung gefunden und nicht das Hinsehen.**

### §71.52 — Runde 46: zwei Differenzen statt einer, und ein Block als Ausgabe

Die Buchung dieser Runde hat vier Teile, und der erste war der Fehler
der letzten Runde in der Gegenrichtung.

**1. `unchecked` — Klassen ohne Prüfer.** `extra_checkers` schiebt einen
Prüfer in die Kette, der in keiner Klasse steht; `unclassified` zählt
genau das. Der Fehler von Runde 44 war aber ein Prüfer zu **wenig**:
`check_undocumented_tests` stand in `main` und nicht in `calibration_run`.
Eine Differenz zwischen zwei Mengen, die nur in eine Richtung geprüft
wird, ist eine halbe Differenz. Jetzt gibt es `_checker_gap(a, b)` — die
Menge kommt aus dem **AST beider Funktionen**, nicht aus einer Handliste:

| Richtung | Aufruf | erwartet |
|---|---|---|
| Prüfer ohne Klasse | `_checker_gap("calibration_run", "main")` | 0 |
| Klasse ohne Prüfer | `_checker_gap("main", "calibration_run")` | 0 |

Die Probe `main` ruft `check_a(), check_b()`, `calibration_run` ruft
`check_a()` liefert `1` — und die Umkehrung in der anderen Probe
ebenfalls `1`. Beide Richtungen sind heute `0/0`; das ist der Stand,
nicht die Zusicherung.

**2. `total` und `reported` trennen sich.** Der Zusatzprüfer lief nur in
der Kette und nicht in `reported` — damit waren `total` und `reported` im
einzigen Zustand gleich, in dem sich die drei Zahlen trennen könnten.
Gemessen: ohne Zusatz `1/1/1`, mit Zusatz `total=1, reported=2,
chain_total=2`. Die Erwartung im Selbsttest ist `reported == chain_total`
**und** `reported != total`.

**3. Der Default ist der Fehler.** `_reads_without_root` unterscheidet
„hat `root`" von „ohne `root`"; die kranke Form ist „hat `root` und
benutzt es nicht immer":

```python
def version_line(root=None):
    p = root or Path.cwd()      # gelesen wird default-relativ
```

Der Prüfer hätte sie nicht gefunden — `root` steht in seiner
Erlaubnisliste, der Lesezugriff geht über `p`, `p` über einen Fallback.
`_default_root_errors` meldet drei Formen: `root=None` als Vorgabewert,
`X or Path.cwd()`/`X or "."` im Rumpf, `Path.cwd()`/`os.getcwd()` im
Rumpf. Die Probe mit vier Funktionen (zwei krank, zwei sauber) ist grün;
der eigene Baum hat **19 Fundstellen** (12 × `root=None`, 7 × `cwd` im
Rumpf) — überwiegend bewusster Aufrufkomfort (`repo_root`,
`_snapshot_path`, `_tree_ref`), der nach dieser Akte in den Aufrufer
gehört, nicht in die Signatur. Die erste Fundstelle ist `check_counts` —
dieselbe Funktion, deren Signatur der Fehler der letzten Runde war.

**4. Der Block ist eine Ausgabe.** `calibration_card()` gibt den
Ergebnisblock **mit** `Bezug:`-Zeile aus (`root`, `CLAUDE.md`-sha256,
Baum). Er war die einzige Zahlengruppe in der Akte ohne Bezug — deshalb
konnte eine Zahl verschwinden, ohne dass es auffiel. Der Block unten ist
kopiert, nicht getippt:

```
total=0 chain_total=0 reported=0 unclassified=0 unchecked=0 unclassified_checkers=0
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:69159540db89, Baum 1e0d9e5a+dirty
```

Klon zur Gegenprobe: `total=151 chain_total=151 reported=151
unclassified=0 unchecked=0 unclassified_checkers=0` — `Referenzen 124,
Wellen 16, Zeilen 10, Inventare 1, Tests 0`.

**Würdigung, ehrlich:** der Selbsttest steht bei **30/30**, die Suite bei
**216 passed**. Die zwei neuen Prüfer waren beim Bau nicht rot, weil die
Buchung sauber war — der Default-Prüfer war rot an 19 Stellen, die
niemand erwartet hatte, und die erste Reaktion war nicht „Ausnahme",
sondern die Zählung. Was offen bleibt: `unchecked` prüft **heute** die
eigene Datei, nicht die Historie. Ein Prüfer, der in Runde 44 fehlte und
in Runde 45 nachgetragen wurde, ist in keiner der beiden Zahlen sichtbar.

### §71.53 — Runde 47: die Handliste war ein Regex, und der Block wird verglichen

**1. Die Registry überlebt.** `_checker_gap` bildete seine Mengen aus dem
Namensmuster `check_*` — eine Handliste in Regex-Form. Ein Prüfer namens
`_reads_without_root` stand in keiner der beiden Mengen, und die
naheliegende Verbesserung `for c in CHECKS: c(root)` machte beide
Differenzen `0/0`. Gemessen vor dem Umbau: `checked 0, unclassified 0`
für die Registry-Probe — blind.

Jetzt löst `_called_checkers` zwei Formen auf: direkte `check_*`-Aufrufe
**und** `for`-Schleifen über einen Namen, dessen Tuple im **selben** AST
als Namensmenge steht. Die Registry-Probe liefert `1`; die eigene Datei
bleibt `0/0`. Die Grenze ist ehrlich: ein **dynamisch** gebautes Register
kann der Prüfer nicht lesen — er meldet dann `0`, was dieselbe Blindheit
wäre. Ein Kommentar an `CHECKS` ist die Bedingung dafür, dass das nicht
passiert.

Zusätzlich fragt `_report_functions` nach der **Rolle** statt nach dem
Namen: jede Funktion mit `rep`/`report` in der Signatur ist ein Prüfer.
Die Probe mit `_weird_name(rep)` liefert genau `['_weird_name']`.

**2. Die Regel gehört auf die Kombination.** `root=None` allein ist
Aufrufkomfort — `repo_root(root=None)` löst den Ort intern auf und liest
nichts relativ. Der Fehler ist `root=None` **und** ein Pfad, der ohne
`root` entsteht. Zwei Ebenen:

| Ebene | Form | rot |
|---|---|---|
| A | `Path.cwd()`/`os.getcwd()` im Rumpf | immer — kein Aufrufer steuert ihn |
| B | `root=None` **mit** `or Path.cwd()` / `or "."` / `or Path()` | die Kombination |
| — | `root=None` ohne Fallback (`repo_root`, `_snapshot_path`, `_tree_ref`) | nicht |

Damit fällt die Baseline weg. `_CWD_READERS` deklariert zwei **Rollen**
statt Ausnahmen am Fund: `_self_test_count_delta` prüft `chdir` und muß
`cwd` lesen, `main` ist der Aufrufer, der den Default setzt. Stand nach
dem Schnitt: **0 Fundstellen** — die Zusicherung ist `== 0`, nicht
`<= 19`.

Nebenwirkung, die bestehen bleibt: `check_counts` steht **nicht** mehr in
der Liste. Sein `root=None` ist verschwunden, weil der Fehler der Runde 44
der **Aufruf** ohne `root` war, nicht die Signatur. Der Prüfer meldet ihn
in der Probe weiterhin (`2`), in der eigenen Datei nicht.

**3. Der Block wird verglichen, nicht zitiert.** `_akt_block_mismatch`
liest den letzten `total=`-Block der Akte und hält ihn gegen
`calibration_card()`: sechs Zahlen der Kopfzeile plus `Bezug`-Felder
`root` und `CLAUDE.md sha256`. Der Baum-Hash nicht — der Block ist
committet, der Vergleich läuft im nächsten Commit.

Gegenprobe von Hand, vor dem Eintrag: `chain_total=0` in der Akte durch
`chain_total=7` ersetzt → `['Akte-Block: chain_total 7 zitiert, 0
gemessen']`. Zurückgesetzt. Der Selbsttest macht dasselbe mit `total=999`
und verlangt **eine** Meldung, die die Zahl nennt.

**4. `mode 160000` ist rot, wenn es nicht deklariert ist.** Pauschal wäre
die Regel an der ersten Stelle falsch: `lib/openzeppelin-contracts` und
`-upgradeable` sind deklarierte Forge-Submodule. `_gitlink_errors`
vergleicht gegen `.gitmodules`; rot ist der Gitlink, den niemand kennt —
der Fall `forensik` aus Runde 46. Die Probe baut ein temporäres Repo mit
einem deklarierten und einem fremden Gitlink und verlangt genau eine
Meldung, die `fremd` nennt.

**5. Die Literal-Regel.** Der Prüfer hat **fünf** Fremdfunde gegen meinen
neuen Code gemeldet, vier davon echte Fehler: ein Ueberrest
`_REGISTRY_CALLS` mit Zustand, ein `root`-Durchreichungsfehler in
`_akt_block_mismatch`, und zwei Prosa-Zahlen ohne Herkunft. Der fünfte
(`role` als Konstruktionskonstante) war derselbe Fall wie `probe` in
Runde 46 — behoben über `_CONSTRUCTION_CONSTS`, nicht über eine Ausnahme.

**Stand:** Selbsttest **32/32**, Suite **216 passed**, voller Lauf ohne
Abweichung. Der Block unten ist `calibration_card()` und wird vom
Selbsttest gegen die Akte gehalten — er ist kopiert **und** geprüft.

```
total=0 chain_total=0 reported=0 unclassified=0 unchecked=0 unclassified_checkers=0
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:69159540db89, Baum 326b269a+dirty
```

**Was offen bleibt:** der Vergleich kennt nur **einen** Block — den
letzten. Ältere Rundenblöcke dürfen abweichen und niemand merkt es. Das
ist die nächste Stelle, an der eine Zahl verschwinden kann; ich habe sie
hier nicht zugemacht, weil ein Vergleich über alle Blöcke eine Aussage
über die *Historie* verlangt, die diese Datei nicht führt.

### §71.54 — Runde 48: `None` statt `0`, und eine eigene Fehldiagnose

**1. `0` ist die Zahl, die „grün" und „blind" gemeinsam haben.**
`_checker_gap` hatte drei Zustände und zwei davon gaben `0` zurück:

| Zustand | vorher | jetzt |
|---|---|---|
| Kette und Klassen gleich | `0` | `0` |
| Kette und Klassen verschieden | `1` | `1` |
| **Register nicht auflösbar** | **`0`** | **`None`** |

Gemessen vor dem Umbau: `CHECKS = tuple(c for c in (check_a, check_b))`
lieferte `0`. Jetzt `None`. Der Selbsttest verlangt `isinstance(..., int)`
für die **eigenen** Richtungen und `is None` für das dynamische Register —
beide Erwartungen als Literal.

**2. Das Register wird über das Objekt der Iteration aufgelöst.** `_ALL`
funktioniert genauso wie `CHECKS`. Und die erste Fassung hatte einen
echten Fehler: sie meldete **jede** `for`-Schleife als unauflösbares
Register — `for p in rep.problems` inklusive. Die eigene Datei lieferte
prompt `None`. Die Eigenschaft ist nicht „iteriert", sondern „iteriert
**und ruft das Iterat als Funktion**":

```
statisch      1
dynamisch     None
anderer Name  1     (_ALL statt CHECKS)
daten         0     (for p in rep.problems — kein Register)
```

**3. Die Fehldiagnose der letzten Runde, nachgemessen.** §71.53 hat
`root=None` als „die Signatur des Fehlers" bezeichnet. `check_counts` war
kein Fall — sein Fehler war der **Aufruf** `check_counts(text, waves,
AGENTS_PER_WAVE, rep)` ohne `root`. Der Prüfer für Aufrufe existierte
nicht; `_reader_calls_without_root` ist er jetzt. Die erste Messung
lieferte **elf** Fundstellen, davon **eine echte**: genau jener Aufruf in
der Fixture — er stand seit Runde 44 im Code und ist jetzt mit
`root=Path(__file__).resolve().parent.parent)` versehen. Die übrigen zehn
tragen `§A-KR-ANCHOR` und sind Negativtests, die den Default **prüfen
sollen**; der Prüfer liest die Deklaration aus derselben Zeile.

Der Unterschied, der den Prüfer lebensfähig macht: eine Funktion, die
`root` annimmt und **nicht braucht** (`_snapshot_path`), ist kein Leser —
ihr Aufruf ohne `root` ist kein Fehler. `_uses_root_as_path` entscheidet
das am Rumpf, nicht am Namen.

**4. `_CWD_READERS` ist jetzt lebendig.** Jeder Eintrag muss (a) im
Modul existieren und (b) tatsächlich `cwd` lesen. Die Probe mit einem
gelöschten und einem nicht mehr lesenden Eintrag liefert zwei Meldungen —
ohne sie könnte die Liste nur wachsen.

**5. Verlustfreiheit.** Die Akte verliert keine Blöcke gegen `HEAD~1`:
`Bezug`-Zeilen, Zeilen und `total=`-Blöcke sind monoton. Der Test ist
**nicht** im Standardlauf — er gehört an den Commit (`--akte-monoton`),
weil eine bewusste Kürzung rot werden soll.

**6. Gitlink.** `mode 160000` rot nur ohne `.gitmodules`-Eintrag; die
Gegenrichtung (deklariert, aber nicht im Baum) bleibt ungeprüft.

**Stand:** Selbsttest **34/34**, Suite **216 passed**.

```
total=0 chain_total=0 reported=0 unclassified=0 unchecked=0 unclassified_checkers=0
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:69159540db89, Baum ceb8d12d
```

**Was offen bleibt:** `unchecked` und `unclassified_checkers` sind im
eigenen Baum `0`, weil `main` und `calibration_run` dieselben sechs
Prüfer fahren. Das ist heute wahr und morgen nicht mehr geprüft — ein
Prüfer, der nur im Kalibrierlauf steht, wird erst sichtbar, wenn er dort
**meldet**. Der Zähler sieht die Registrierung, nicht die Wirkung.

### §71.55 — Runde 49: die Menge statt der Zahl, und vier Anker, die sich selbst fanden

**Die Buchung.** §71.54 hat Verlustfreiheit als **Zählung** eingeführt
und gleich die Schwäche genannt. Der Leser hat sie genauer benannt:
`3 >= 3` ist grün, wenn Block 45 gelöscht und Block 48 hinzugefügt wird.
Das ist Nettoverlust, nicht Verlustfreiheit.

**1. Verlustfreiheit als Mengeninklusion.** Die Identität stand schon in
der Datei: jeder Block beginnt mit `### §71.NN — Runde M`.

```
bloecke(heute)  ⊇  bloecke(HEAD~1)
```

Meldung nennt die **fehlende Runde**, nicht die Differenz zweier Zahlen.
Gegenprobe: Block §71.52 entfernt, `git`-Lauf gegen `HEAD~1` ⇒
`Akte: Block §71.52 fehlt — Runde verloren`. Die Größenprüfung bleibt
daneben — ein Zeilenverlust **innerhalb** eines Blocks erzeugt keinen
Blockverlust.

**Nebenwirkung, gewollt:** eine Berichtigung, die den Hash ändert, wird
rot. Das ist die Entscheidung: die Akte wächst monoton, oder sie erzählt.

**2. `check_counts` — hat der fehlende `root` je eine Zahl geändert?**

```
Repo:         ohne root  0 Probleme   mit root  0 Probleme
Frischer Klon: ohne root  0 Probleme   mit root 16 Probleme
```

**Ja — und deutlicher als gedacht.** Die Zeile war

```
if root is not None and not (root / ref).exists():
```

Ohne `root` wurde die Prüfung **komplett übersprungen**: nicht
fehlbefunden, sondern nicht stattgefunden. Sechzehn Zusagen waren im
Klon stumm. Der Runde-44-Fehler war vierundvierzig Runden lang kein
Formverstoß ohne Wirkung — er war der Unterschied zwischen 0 und 16.

**3. `§A-KR-ANCHOR` ist ersetzt.** Die zehn Marker waren `# noqa` mit
Etikett, im Produktionscode. Die Rolle „Negativtest" ist jetzt am
**Testkörper** erkennbar: ein Default-Aufruf in einer `_self_test`-
Funktion prüft den Default-Zweig, einer im Produktionscode ist der
Verstoß. Fünfundneunzehn Inline-Marker entfernt, zwei Kommentarzeilen.
Der Anker wurde zur Konstante, deren Definition sich selbst ausschließt.

Dieselbe Bewegung wie `_CWD_READERS`: von vielen Ausnahmen auf eine
Regel. Die 18er-Baseline in `_default_probe_lines_valid` fiel mit — eine
Zahl, die den Zustand festschreibt, macht jede echte Reparatur falsch.

**4. `_REGISTRIES` deklariert.** Die vierte Fassung der Heuristik wäre
die nächste Lücke gewesen. Jetzt: jede `for`-Schleife, die ihr Iterat
**als Argument** gibt, ist ein Register; steht der Name nicht in
`_REGISTRIES`, ist das Ergebnis `None`. Vier Formen geprüft — gerufen,
durchgereicht, Daten, `append` gemeldet.

| Form | Runde 48 | Runde 49 |
|---|---|---|
| `for c in CHECKS: c(root)` | 0 | 0, deklariert ✓ |
| `for c in CHECKS: apply(c)` | **0 (grün)** | **None (laut)** |
| `for a in raw: out.append(a)` | Daten | Daten ✓ |

**5. `_binds_root` über den Lesepfad.** Die Eigenschaft ist nicht der
Name, sondern der Gebrauch: `Path(x)`, `x / ...`, `x.glob()`, `cwd=x`,
oder `g(x)` an eine Funktion der Datei, die `Path` nimmt und `Path`
gibt — `_path_returning` liest das aus der Signatur.

Sieben Fixtures: `root=Path` ✓, `root_` ✓, `base` ✓, ungenutztes
`root` ✗, `cwd=` ✓, `glob` ✓, Datum ✗.

**Der ehrliche Fund:** die neue Regel machte `_resolve_test_root`
sichtbar — `doc_root` reicht korrekt durch, der alte Namensprüfer sah
es nicht. Drei Namensbasen in einer Datei (`_binds_root`,
`_root_aliases`, Ankerlisten), alle mit demselben Fehler.

**6. Wirkungs-Fixture pro Prüfer.** `scripts/check_fixtures.py`:
sieben Prüfer, je ein kaputtes und ein sauberes Fixture.

```
check_line_counts      1 / 0    wirkt
check_dead_refs        1 / 0    wirkt
check_counts           1 / 0    wirkt
check_doc_inventories  3 / 2    wirkt
_gitlink_errors        1 / 0    wirkt
_akt_block_mismatch    1 / 0    wirkt
_akte_losslessness     1 / 0    wirkt
7/7 wirken
```

Erste Messung war **3/7** — vier Fixtures trugen den Fall nicht
(Tabelle fehlte, Clean-Fall war der kaputtere, `git`-Repo fehlte,
Null-SHA wurde von git abgelehnt). Jede Reparatur war ein Fund des
Fixtures, keiner des Hinsehens.

**7. Vier Anker, vier Fehlschläge — alle vom Selbsttest.** Der
Produktionsanker der Durchreichungsprobe wanderte durch vier Stellen:

| Versuch | Stelle | Warum kein Fund |
|---|---|---|
| 1 | `_self_test_count_delta` | Rolle schluckt Testcode |
| 2 | `main`, `_delta_line` | `root` ist Zuweisung, kein Parameter |
| 3 | `chain` | Closure, kein Parameter |
| 4 | `calibration_run`, `run(...)` | Referenz statt Aufruf |
| 5 | `main`, `check_line_counts(text, root, rep)` | drei Treffer, `replace(…,1)` traf den ersten |

Der fünfte ist der Beweis: `replace(…, 1)` gegen einen mehrfach
vorkommenden Text ist dieselbe Form wie „erster Treffer" — ein Prüfer,
der den Ort nicht benennt, prüft den falschen.

**Stand:** Selbsttest **34/34**, `--akte-monoton` **keine
Blockverluste**, voller Lauf **0 Abweichungen**, Wirkung **7/7**.

```
total=0 chain_total=0 reported=0 unclassified=0 unchecked=0 unclassified_checkers=0
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:69159540db89, Baum 9cbc4178+dirty
```

**Was offen bleibt:** `_path_returning` liest `Path`-Signaturen — eine
Funktion, die einen Pfad **nicht** annotiert, aber zurückgibt, fällt
durch. Und die Wirkungs-Fixtures sind synthetisch: sie belegen, dass
jeder Prüfer **einen** Fehler findet, nicht dass er **alle** findet.

### §71.56 — Runde 50: sechzehn, und der Hook hatte recht

**Die Antwort auf die Frage der letzten Runde.** §71.55 fragte, ob der
fehlende `root` je eine Zahl geändert hat. Die Antwort ist nicht „nein":
`if root is not None and not (root / ref).exists()` schaltete die
Suite-Prüfung **ab**, sobald kein Baum da war — also genau beim ersten
Lauf in einer Umgebung, die der Autor nicht hatte. Gemessen: **0 statt 16
Suite-Zusagen** im Klon. Der Verstoß mit der kleinsten Zeile war der
wirksamste der Datei.

**1. In welchem Baum laufen die Tests? — gemessen, nicht behauptet.**

Der Pre-Commit-Hook exportiert den **Index** nach `mktemp -d` und ruft
den Prüfer gegen diesen Export. Dieser Baum hat **kein `.git/`**. Der
Unterschied ist nicht kosmetisch:

| Baum | `.git/` | `_resolve_test_root` | `test_wave38_diagnostic` |
|---|---|---|---|
| Arbeitsbaum | ja | Arbeitsbaum | **281/281** |
| Hook-Staging (`checkout-index`) | nein | der Export selbst | **172/184** |

Die 281/281 der Runden 40–49 waren eine Aussage über den **Arbeitsbaum**
— der einzige Baum, in dem sie jemals galten. Im Staging-Baum waren
**neun** Tests rot, und keiner davon war „der Test ist kaputt".

**2. Was der Hook wirklich gefunden hat.** `fixture_resolved_pools()`
heißt „Offline copy" und las `bridge_stufe_a_v3_liquidation_resolved.json`
aus der Projektwurzel — eine Datei, die `.gitignore:81` ausschließt und
nie im Index stand. Dasselbe für `fixture_intent_resolved()` und
`fixture_stable_resolved()`. Im Arbeitsbaum lagen sie zufällig aus einem
Bridge-Lauf; im Klon sind sie nicht vorhanden. **Ein Fixture, das von
einem Laufzeit-Artefakt abhängt, ist kein Fixture.** Die Adressen sind
konstant (RESOLVED, plausibility pass) und stehen jetzt im Modul.

Folge: `172/184` → `191/200` (nach `liquidation`) → **`281/281`** (nach
`intent_stable`), im Arbeitsbaum **und** im Staging-Baum.

**3. `--no-verify` zurückgenommen.** Der Bypass aus Runde 49 war nicht
falsch dokumentiert, sondern falsch **begründet**: er verschob die Frage
in den nächsten Commit. Der Hook läuft jetzt mit, und der volle Pfad
(`--run-tests`) ist im Staging-Baum grün — gemessen, nicht angenommen.

**4. `root=None` ist kein Skip mehr.** Drei Formen, jetzt eine:

| Form | vorher | jetzt |
|---|---|---|
| `if root is not None and …` | still übersprungen | **`rep.fail`** „Suite nicht prüfbar (kein Baum)" |
| `_status_line(root=None)` | Bezugszeile fiel weg | „KEIN BAUM (root=None — Zahl unspezifiziert)" |
| Selbsttest ohne `root` | still | **rot**, Selbsttest angepasst |

Ein weggelassener Satz sieht aus wie eine erfüllte Bedingung. Die
Kopfzeile darf den Mangel noch aussprechen — sie ist Text, nicht
Prüfung; jede **Prüfung** fällt hart.

**5. Wirkungs-Fixture: `kaputt != heil` als eigene Zusicherung.** Runde
46 formulierte sie, Runde 49 stellte fest, dass 4/7 sie nicht erfüllten —
gefunden **von Hand**. Jetzt ist sie ein Prädikat mit drei benannten
Zuständen (`fixture_clean_red`, `fixture_broken_green`, wirkt). Der erste
Lauf der Zusicherung fand sofort einen **fünften**: `check_doc_inventories`
war im heilen Baum rot (3 vs 2), weil dem Fixture `generated_at`,
`SWARM_RUNTIME` und ein importierbares `swarm_health.py` fehlten — genau
der Zustand, den Runde 49 manuell nachziehen musste. Nach der Reparatur:
**7/7**, erzwungen.

**6. Der Prüfer über den Prüfern.** `_name_based_decisions` zählt per
`ast` jeden Vergleich, der einen **Parameter** an seinem Namen misst.
Gemessene Zahl im Produktionscode: **0**. Die dreizehn Treffer des ersten
Laufs waren AST-**Feld**namen (`k.arg`, `a.arg`) — Syntax, keine
Konvention; der Prüfer unterscheidet sie jetzt und **falsifiziert sich
selbst** (eingefügte Namensbasis muss zählen, AST-Feldname darf nicht).
`ok_names` ist als erwartete Menge deklariert — stille Erweiterung = rot.

**7. Blockidentität `(§, Hash)`.** Die Mengenprüfung sieht ganze Blöcke;
die Größenzahlen darunter sehen nur Netto. Jetzt trägt jeder Block einen
Kurzhash, und ein **Zeilenverlust innerhalb** eines Blocks wird benannt:
`Akte: Block §71.55 Zeilen 120 -> 118 — Verlust im Block (Hash … -> …)`.
Ein Block mit anderem Hash ist kein verlorener Block, sondern ein
veränderter — die Entscheidung fällt wie in §2: Berichtigung als eigener
Block.

**8. Anker-Paßhäufigkeit = 1.** `rfind` legte den Mehrfachtreffer still —
vier Anker scheiterten in Runde 49, der fünfte wäre geschluckt worden.
`_anchor_report` zählt `replace(..., 1)`-Anker und verlangt genau einen
Treffer, **ohne** Zitate (Kommentar, `_anchor`-Definition) und über
beide Formen mehrzeiliger Anker (real und escaped). Der erste Lauf fand
den Anker der Produktionsprobe **3x** — er traf Produktion, Testkörper
und sich selbst.

**Stand dieser Runde:** Selbsttest **34/34**, Wirkung **7/7**, Namensbasen
**0**, voller Lauf **0 Abweichungen** im Arbeitsbaum **und** im
Hook-Staging-Baum, `--run-tests` im Staging-Baum **0 Abweichungen**.

**Was offen bleibt:** `suite:ohne-skript` zählt **12** Zusagen ohne
Skriptpfad — sie sind jetzt **benannt** statt still gezählt, aber der
Skriptbezug fehlt weiter; `--run-tests` prüft `passed <= total`, nicht
die Zahl selbst. Und die Wirkungs-Fixtures sind synthetisch: sie belegen,
dass jeder Prüfer **einen** Fehler findet, nicht dass er **alle** findet.
### §71.57 — Runde 51: drei Zahlen statt einer, und der Prüfer war blind

**Die Antwort auf §7.** Drei Einschränkungen standen auf einer Null:
`keine Differenzmessung` (Klammer), `12 ohne Skript` (Akte), `Wirkung =
mindestens einer` (Fixture). Die Null sah aus wie eine Summe über alles.
Gemessen war sie die Summe der **gemessenen** Abweichungen — und nichts
daneben stand.

**1. `None` statt `0` in der Kopfzeile — der R47-Fehler, eine Ebene höher.**

`_status_line` bekommt `problems: int | None`. Ist `None`, gibt die
Funktion `None` zurück; `main` rendert dann `unvollstaendig · 1 nicht
gemessen · 0 ohne Skript`. `measurement_tally()` **gibt** die drei Zahlen
zurück — ein Dict, keine Fußnote im Text. `_require_int_tally()` ist der
Vertrag mit der Akte: `None`, `bool` und negative Werte sind keine Zahl.

| Baum | vorher | jetzt |
|---|---|---|
| Arbeitsbaum | `0 Abweichungen` | `0 gemessen · 0 nicht gemessen · 0 ohne Skript` |
| Hook-Staging (kein `.git/`) | `, 0 Abweichungen` + Klammer | `unvollstaendig · 1 nicht gemessen · 0 ohne Skript` |

**2. Der `.gitignore`-Prüfer — und er war blind für Verzeichnismuster.**

`fnmatch("data/synthetic/f.jsonl", "data/synthetic/")` ist **`False`**.
Der Prüfer hat also genau den Fall aus Runde 50 nicht gesehen
(`fixture_resolved_pools()` las unter `data/`). `_gitignore_hit()` kennt
jetzt drei Formen: Endungsmuster (`*.log`), Verzeichnismuster (`data/`,
per Präfix), Pfadmuster (`build/output.json`). Der rote Lauf im
Selbsttest (`dir-muster`) belegt es; `docs/f.jsonl` gegen `data/` bleibt
grün.

**3. Drei Treffer im echten Baum — alle drei gewollt.**

`_FORBIDDEN_MOUNT_HINTS = ("/data/raas/worm",)` und
`write_path="data/raas/sandbox/…"` sind **Behauptungen** über Pfade,
keine Lesezugriffe. `_path_is_asserted_not_read()` unterscheidet sie:
Konstante in Großbuchstaben, Keyword-Argument, `in`/`==`/`startswith`.
Ohne diese dritte Kategorie hätte der nächste Leser den Prüfer
abgeschaltet — und er wäre wieder blind. Ergebnis: **122 Angaben
geprüft, 0 Befunde**.

**4. `unclassified = -1` lief durch.**

Zwischenstand nach dem Fix: `total=1`, `chain_total=0` → `unclassified=-1`.
Ein negativer Wert heißt, dass ein Prüfer in einer Klasse zählt und in
der Kette nicht — derselbe Fehler wie `unclassified > 0` mit
vertauschtem Vorzeichen. Keine Zusicherung fing ihn.

**5. `features.jsonl` — derselbe Defekt wie `fixture_resolved_pools()`.**

`test_prefilter_training.py` erzeugt den Korpus jetzt in `mkdtemp`
(`generate_prefilter_synthetic_data`), statt ihn vorzufinden.

**6. `_self_test_tally_numbers` — fünf Behauptungen, alle rot gewesen.**

`abweichungen is None` ohne Messung · Rendering beginnt mit
`unvollstaendig` · kein `0 gemessen` · `ohne_skript` als eigene Zahl ·
`_require_int_tally` lehnt `None`/`bool`/negativ/`str` ab. Der Lauf
meldete zuerst `gemessene 0 fehlt: … 0 gemessen · 2 nicht gemessen · 0
ohne Skript` — die dritte Zahl fehlte, weil `_status_line` sie nicht
annahm.

**7. Zweigabdeckung als Zahl — 7/13, nicht 7/7.**

```
7/7 wirken
Zweigabdeckung: 7/13 (53%) — unter Deckung: check_counts 1/5,
check_dead_refs 1/2, check_line_counts 1/2
```

**8. Die zwölf ohne Skript: null. Durch Skriptbezug, nicht durch Lockerung.**

| Runde | ohne Skript |
|---|---|
| 50 | 12 |
| Index + Wellenpaarung | 9 |
| Abschnittskontext (`### Wave N`) | 6 |
| 4 Tabellen-/Wellenzeilen ergänzt | 0 |

**9. Hash-Referenz: Vorzustand, benannt.**

`CLAUDE.md sha256:…` steht **in** der Datei, die er hasht. Die Zeile
sagt jetzt `(Vorzustand — nicht selbstbezueglich)`. Brauchbar als
Baum-Referenz ist er im **nächsten** Block, nicht im eigenen.

**10. Ein Verlust beim Schreiben dieser Runde — gemessen, nicht versteckt.**

Beim Ersetzen des Akte-Blocks habe ich die Datei von **5.986 auf 177
Zeilen** gekürzt (6103 Zeilen Diff). Wiederhergestellt per
`git checkout`, der Block wird jetzt **angehängt** statt ersetzt. Das ist
der Grund, warum diese Runde eine eigene Prüfung dafür braucht: der
Akte-Block-Vergleich sah die Zahlen, nicht die Größe. (Offen: eine
Zusicherung „Akte darf nicht schrumpfen" fehlt noch — §71.56 prüft
Blockgrößen, aber nicht die Dateigröße.)

**Stand dieser Runde:** Selbsttest **35/35**, Wirkung **7/7**, davon
**7/13 Zweige**, Namensbasen **0**, `suite:ohne-skript` **0**,
voller Lauf im Arbeitsbaum **`0 gemessen · 0 nicht gemessen · 0 ohne
Skript`**, im Hook-Staging-Baum `unvollstaendig · 1 nicht gemessen ·
0 ohne Skript` (keine Zahl).

```
total=0 chain_total=0 reported=0 unclassified=0 unchecked=0 unclassified_checkers=0
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
  Testpfade: 0
kopfzeile: 0 gemessen · 0 nicht gemessen · 0 ohne Skript
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:50fff349a031, Baum 576f84d6+dirty
```

**Was offen bleibt:** `--run-tests` prüft `passed <= total`, nicht die
Zahl selbst. 6 von 13 Prüferzweigen haben kein Fixture (`1/5` bei
`check_counts`). Und die Akte hat keine Größen-Zusicherung — der Verlust
dieser Runde wurde von Hand gefunden, nicht vom Prüfer.


### §71.58 — Runde 52: Der Schreibvorgang als Prüfer

**Bezug:** §71.57 (Runde 51, Beinahe-Verlust 5.986 → 177),
`scripts/akte_guard.py` (neu), `scripts/check_claude_md.py`,
`scripts/check_fixtures.py`.

#### 1. Der Fund war nicht der Verlust, sondern das Fenster

In Runde 51 fiel die Akte von 5.986 auf 177 Zeilen; gefunden von
`git diff --stat`, von Hand, zurückgeholt mit `git checkout`. Kein
Prüfer sah es — und das ist strukturell, nicht zufällig:

| Prüfer | sieht | blind für |
|---|---|---|
| `--akte-monoton` | Arbeitsbaum gegen `HEAD~1` | den letzten Commit |
| Hook | Index | den Arbeitsbaum |
| `git diff --stat` | Arbeitsbaum | — nur nicht aufgerufen |

Ein Prüfer, der nur committete Bäume sieht, prüft gestern gegen
vorgestern. Und er lief gegen `HEAD~1`, **nicht** gegen `HEAD`: der
eigene Commit war für ihn unsichtbar. Das ist in dieser Runde behoben
(§1.3), aber es behebt nicht die Ursache.

#### 1.1 Der Schreibvorgang selbst

`scripts/akte_guard.py` — `guarded_write(path, text, whole=True)`:

```
menge   := bloecke(datei)              # vorher
menge_n := bloecke(kandidat)           # inkl. neuem Text
menge_n ⊇ menge   sonst: kein rename, laut
zeilen  >= vorher  sonst: kein rename, laut
.tmp schreiben, fsync, aus .tmp zurücklesen, erneut prüfen
os.replace(tmp, datei)                 # atomar
finally: .tmp löschen, falls noch da
```

**Warum der zweite Lesevorgang kein Misstrauen gegen sich selbst ist:**
was auf der Platte steht, ist die Wahrheit; was im Speicher stand, die
Absicht. Auch die Codepage ist eine Annahme, und ein Guard, der die
Annahme nicht prüft, prüft die Annahme.

**Warum zwei Regeln, nicht eine:** Blockverlust ist der Vorfall
(5.986 → 177); Zeilenverlust **innerhalb** eines Blocks ist der Fall,
den §A-NL (Runde 50) benannt hat und der auf Blockebene grün bleibt.
Beides verweigert den Schreibvorgang, nicht nur das Melden.

**Nebenwirkung, benannt:** ein Guard, der abbricht, hinterlässt `.tmp`.
Das `finally` räumt ihn weg — sonst wächst der Baum mit jedem
Fehlversuch. Und der Guard schützt nur Dateien, die ihn rufen;
`git diff --stat` bleibt für alles andere nötig.

#### 1.2 Die Ursache: `open(..., "w")` auf einer Akte

Der Guard fängt die Folge. Die Ursache war `w` statt `a` — deshalb
`check_akte_write_mode` als Prüfer **im Selbsttest**, der in jedem
Skript des Repos sucht:

```
rot:    open(akte, "w") / "w+" / .write_text(...) / .write_bytes(...)
grün:   akte_guard.guarded_write(...) / append_block(...)
grün:   dieselbe Form auf einem Pfad unter mkdtemp/TemporaryDirectory
        — dort ist die Akte ein Fixture, kein Verlust
```

Die Zielpfade werden per AST bis zur Bindung verfolgt
(`doc_path = … / "TAG7_ABNAHME.md"; open(doc_path, "w")` fällt sonst
in zwei Zeilen auseinander), und der Temp-Nachweis läuft bis zu drei
Sprünge (`root = _tree({...})` → `_tree` → `mkdtemp`).

**Roter Lauf vor grünem** — gemessen, nicht behauptet:

```
ROT 1 (write_text):     1 Meldung
ROT 2 (open(p, "w")):   1 Meldung
GRUEN (guarded_write):  0
GRUEN (mkdtemp-Fixture):0
```

Und beides im Selbsttest materialisiert (`_self_test_akte_write_mode`,
`_self_test_akte_guard`) — **kein Vorführlauf**, sondern ein Testfall,
der bei jeder Suite rot wird, wenn die Form zurückkehrt.

#### 1.3 `HEAD~1` → `HEAD`

`_akte_losslessness` verglich gegen `HEAD~1`. Der letzte committete
Stand, gegen den der Arbeitsbaum verlieren kann, ist `HEAD`. Der
Unterschied ist der eigene Commit: Runde 51 war mit `HEAD~1` grün —
und mit `HEAD` auch, aber das war Zufall, nicht Prüfung. Ein Prüfer,
der den Commit, in dem er läuft, nicht sieht, prüft die Arbeit der
Runde davor.

#### 2. `.gitignore` gehört nicht nachgebaut (§A-NU)

Runde 51 baute eine Formenliste (Endung, Präfix, Pfad), weil
`fnmatch("data/synthetic/f.jsonl", "data/synthetic/")` `False` ist.
Das war die Reparatur eines Symptoms mit einer Nachbildung:
Negationen (`!muster`), `**/` und „letzter Treffer gewinnt" fehlten.

Jetzt: **`git check-ignore -v -- <pfad>`** als Orakel. Antwort `0`/`1`
heißt „ignoriert / nicht", `128` heißt „kein Repo" und ist **keine
Aussage über den Pfad**, sondern über die Umgebung — dann fällt der
Prüfer auf die Formenliste zurück, und `_GITIGNORE_SOURCE` **sagt das**.
Ein Prüfer, der nicht sagen kann, wer geantwortet hat, ist ein Prüfer
mit zwei Wahrheiten.

#### 3. Die Kopfzeile: Umfang und Mangel (§A-NV)

```
vorher:  unvollstaendig · 1 nicht gemessen · 0 ohne Skript
nachher: 8 gemessen · 0 nicht gemessen · 0 ohne Skript (12 entfernt)
```

`unvollstaendig` war ein Wort an der Stelle des **Nenners**. `8
gemessen` sagt Umfang und Mangel, `unvollstaendig` steht als
Ableitung hinten (`abweichungen is None`) — nicht an der Stelle einer
Zahl. Der Nenner ist **berechnet**, nicht gepflegt (`PRUEFER_UMFANG`
aus dem AST der Kette): eine Zahl, die man pflegt, ist beim nächsten
Prüfer falsch.

**`0 ohne Skript (12 entfernt)`** — die erste Null dieser Akte, die
dadurch grün ist, dass die Sache **weg** ist: die zwölf Zusagen ohne
Skriptpfad haben ihre Skripte jetzt in `CLAUDE.md`. Ohne Herkunft läse
sie sich in sechs Runden wie die Nullen, die entstanden, weil niemand
hinsah.

#### 4. Zweigabdeckung: nach Deckung sortiert (§A-YB)

§4 der Runde 52: `check_counts 1/5` zuerst, dann `dead_refs`,
`line_counts`. Die Reihenfolge folgt der Abdeckung, nicht der Historie.

| Prüfer | vorher | nachher | Zweig |
|---|---|---|---|
| `check_counts` | 1/5 | **5/5** | Agentenzahl, Wellenzahl, `root=None`, Skript fehlt (Zeile + Wellenpaarung), `passed > total` |
| `check_dead_refs` | 1/2 | **2/2** | tote Referenz, `python3`-Befehl ins Leere |
| `check_line_counts` | 0/2 | **2/3** | Welle ohne Modulpfad, Datei fehlt, Zeilenzahl (nicht nachgewiesen) |
| gesamt | 7/13 | **14/21 (66%)** | |

**Was die Zahl kleiner macht, statt größer:** die bisherige Zählung las
nur `rep.fail(…)`. Vier Prüfer melden über `list.append(f"…")` oder
`return [f"…"]` — ihre Klassen waren für die Messung unsichtbar, und
`0/1` war keine Abdeckung, sondern eine Messung ohne Kenntnis der Form.

**§A-ZA (Runde 53) — Korrektur einer Zahl im eigenen Block:**
in der Fassung dieser Runde stand hier „die Gesamtzahl ist gefallen
(53% → 66%)". Beides kann nicht stimmen: 7/13 sind 53%, 14/21 sind
66%, der **Anteil ist gestiegen**. Gefallen war er im **Zwischenstand**
— als die Messung schon alle drei Formen las und die Zweige noch nicht
repariert waren: **7/21 (33%)**. Erst zählt die Messung mehr Klassen
(13 → 21), dann werden sie gedeckt (`7 → 14`). Die ehrliche Zeile ist:

```
7/13 (53%)  →  7/21 (33%)   Messung erweitert, Zweige nicht
            →  14/21 (66%)  Zweige nachgezogen
```

Die 33% stand in keinem Protokoll und in keiner Zeile der Akte — sie
ist die **Ableitung** der beiden Zahlen daneben. Genau deshalb ist sie
prüfbar: eine Zahl, die im selben Satz mit ihren beiden Operanden steht,
braucht keinen Prüfer, sondern eine Division (§A-ZB).

Der `check_counts`-Zweig `passed > total` war bis zu dieser Runde
**unerreichbar**: die Existenzprüfung stand davor, und jede Zeile,
deren Skript fehlt, traf „Skript fehlt" statt „unmöglich". Ein Fixture
hätte ihn nicht gefunden — das Fixture hat ihn gefunden.

#### 5. Gegenprobe 1: was der neue Prüfer sofort fand

Der erste Lauf von `check_akte_write_mode` meldete `35958 Angaben
geprüft` und `unclassified=-7`. Ursache: die erste Fassung rief
`_mentions_akte(tree, …)` auf den **ganzen Baum** und zählte jedes
String-Literal. Eine Prüfung ist ein Schreibaufruf, nicht jedes
Vorkommen eines Dateinamens. Der Zähler hat das gefangen, nicht ich —
das ist die Form, die trägt.

#### 6. Gegenprobe 2: `_akte_losslessness` prüfte sich nicht selbst

Das alte Fixture rief `_akte_blocks` und zog zwei Mengen ab — es
prüfte die **Voraussetzung** des Prüfers, nicht den Prüfer. Wirkung
`1/1` stand da, und der Prüfer war nie gelaufen. Jetzt: `git init`,
ein Commit mit drei Blöcken, dann eine Runde entfernt → 2 Meldungen;
heil → 0.

#### 7. Was offen bleibt — ehrlich

- `_akte_losslessness 2/3`: der Fall „Zeilenverlust **innerhalb** eines
  Blocks" ist die dritte Klasse, und das Fixture trifft sie nicht.
- `check_line_counts 2/3`: die Zeilenzahl-Klasse ist nachgewiesen, aber
  ihr Zweig verlangt eine Tabelle mit Modulpfad **und** einen `# Wave`
  Satz — nachgewiesen, nicht erzwungen.
- `check_doc_inventories 1/6`: fixt danach, nicht nach Klassen.
- **`git diff --stat` bleibt nötig.** Der Guard schützt die Akte; ein
  Skript, das `CLAUDE.md` mit `w` überschreibt, fängt nur der neue
  Prüfer, und nur wenn er läuft.


### §71.59 — Die Zahl im Fließtext, der Bezug im Namen, das Ziel statt der Methode

**Runde 53. Nicht getan in §71.58: keine Zahl nachgerechnet, kein Prüfer
gegen seinen Bezug geprüft.** Der Befund dieser Runde steht in der Akte
selbst, und er ist der richtige:

**1. Die Zahl war falsch, und zwar in dem Satz, der die Verbesserung
beschreibt.** Dort stand „die Gesamtzahl ist gefallen (53% → 66%)". Beides
kann nicht stimmen: der Anteil ist **gestiegen**. Gefallen war er im
**Zwischenstand** — als die Messung schon alle drei Meldeformen las und die
Zweige noch nicht repariert waren: **7/21 (33%)**. Erst zählt die Messung
mehr Klassen, dann werden sie gedeckt. Die ehrliche Zeile ist:

```
7/13 (53%)  →  7/21 (33%)   Messung erweitert, Zweige nicht
            →  14/21 (66%)  Zweige nachgezogen
```

Gefunden hat das kein Prüfer, sondern der Leser — und das ist der Punkt:
`_require_int_tally()` prüft die **Kopfzeile**, der Fließtext hatte keinen
Prüfer.

**2. Ein Prüfer über Bruchzahlen ist billiger als jede Zusicherung über
Prosa.** `check_prose_fractions` liest `Z/N (P%)` und rechnet. Toleranz:
eine Prozentstelle (`floor` und `round` sind beide üblich). Grenze, benannt:
zwei Prozentzahlen ohne ihre Brüche daneben sieht er nicht — und kann es
nicht, weil die Operanden fehlen. Der Selbsttest ist die **Negativprobe**:
`14/21` mit Prozent `99` — rot; `7/21` mit `33` — grün;
`14/21` mit `67` — grün.

**3. Vier Prüfer, ein Fehler: sie schauten auf das, was sie kannten, nicht
auf das, was sie meinten.** `HEAD~1` statt `HEAD`, die Methode `"w"` statt
das Ziel, `_akte_blocks` statt `_akte_losslessness`. Er ist in dieser Runde
ein fünftes Mal passiert — an **mir**: `_touches_akte` sah `call.args` und
`call.keywords`, aber nicht `call.func.value`. `p.write_text("x")` hat den
Empfänger nicht im Argument. Der Selbsttest fand den Prüfer, der den
Vorfall nicht mehr meldete. Und das Fixture fand auch die Gegenprobe: die
erste Fassung meldete jeden *lesenden* Aufruf mit Aktenargument.

**4. Ziele sind endlich, Methoden sind unendlich.** `"w"` ist eine von
vielen Schreibformen — `"w+"`, `"wb"`, `"x"`, `os.replace`, `shutil.copy`,
`json.dump(fp)`, `pd.to_csv`, `sed -i`. Die Umkehrung: welcher Aufruf
**schreibt auf eine Akten-Datei** und steht nicht bei `guarded_write`?
Geprüft werden Empfänger, Argumente, Keywords; Schreiben wird an der
Zielseite erkannt (`open` mit Schreibmodus, `write*`/`replace`/`dump`/
`truncate`/`unlink`/`copy*`, `subprocess` mit `-i`). Ausnahme mit Namen:
dieselbe Form unter `mkdtemp` ist ein Fixture, kein Verlust.

**5. Der Guard: `(Block, Hash)` statt `zeilen >= vorher`.** Erste Fassung
zu streng — `append_block` ließ den letzten Block wachsen, und der Guard
verweigerte das **Anhängen**. Der Fix ist keine Ausnahme, sondern die
richtige Regel: **Präfix-Treue**. Ein Block darf nur am Ende wachsen
(`new_body.startswith(old_body)`). `Text.` → `Text!!` bei gleicher
Zeilenzahl ist rot; das war der Fall, den `zeilen >= vorher` durchließ.
§A-ZH trägt dieselbe Regel in `_akte_losslessness`, dessen
`if new_lines < old_lines` die Bandage war.

**6. Ein Eingang pro Zweig, nicht einer pro Prüfer.** Das ist die Antwort
auf die Forderung aus Runde 51 §6, und sie ist besser als die Forderung:

| Prüfer | vorher | nachher |
|---|---|---|
| `check_doc_inventories` | 1/6 | **6/6** |
| `_akte_losslessness` | 2/3 | **3/3** |
| gesamt | 14/21 (66%) | **21/22 (95%)** |

Der Nenner ist von 21 auf 22 gewachsen, weil `_akte_losslessness` durch
§A-ZH **eine** Meldeklasse mehr hat („Block geändert"). 21 von 22 ist
95%, nicht 93% — und `14/21` war 66%, **gestiegen**, nie gefallen.

**7. Was offen bleibt, und wie es ehrlich dasteht.**

- **`_akt_block_mismatch 0/1`.** Die Klasse heißt
  `Akte-Block: {key} {g.get(key)} zitiert,` — ein zusammengesetzter Satz
  aus **zwei** Literalen in `_compare_block`. `_classes` liest den ersten
  Halbsatz und findet keine Treffer. Ich habe in dieser Runde **dreimal**
  an der Erkennung gedreht (4 Klassen, 5 Klassen, 2 Klassen) und die Zahl
  damit zwischen 60% und 84% geschoben. Das ist das Drehen an der
  Messung, das §4 verbietet. Zurück auf den ehrlichen Stand: das Fixture
  **wirkt** (eine Meldung), wird aber **nicht als Deckung gezählt**. Die
  nächste Runde beginnt mit `_compare_block`, nicht mit `_classes`.
- **Der Guard ist opt-in — und diese Runde hat es belegt.** Der Satz aus
  §1 („die Gesamtzahl ist gefallen") wurde mit einem direkten
  Editor-Ersetzen korrigiert, nicht über `guarded_write`. Das ist genau
  der Fall, den `check_akte_write_mode` als **AST** sieht, aber nicht
  beim Schreiben. Der AST-Prüfer ist die Zusicherung, der Guard die
  Bequemlichkeit, die ihn grün hält. Die Akte soll das sagen — hier
  steht es.
- **Die Wache für `CLAUDE.md` fehlt ganz.** `guarded_write` prüft nur
  `### §71.NN`-Blöcke; `CLAUDE.md` hat keine. Der AST-Prüfer deckt auch
  sie, weil beide Dateien in `akten` stehen — der Guard nicht.
- **Pfade, die zur Laufzeit zusammengesetzt werden** (`base / name`)
  entkommen jedem AST-Prüfer. `git diff --stat` bleibt der eine Prüfer,
  der den **Zustand** sieht statt den Code.

**8. Mechanik.** 37/37 Selbsttests (+2: `_self_test_prose_fractions`,
Hash-Fall in `_self_test_akte_guard`), 21/22 Zweige, 58 Blöcke,
`check_akte_write_mode` 507 Aufrufe / 0 Befunde im Baum, 12 Temp-Fixtures
als benannte Ausnahme. Kopfzeile: `8 gemessen · 0 nicht gemessen ·
0 ohne Skript` — die achte Klasse ist der neue Prüfer, und sie steht in
**beiden** Ketten (`main` und `calibration_run`), sonst meldet §A-MT eine
Differenz.

**Neue Prüfungen, mit Namen:**

| Name | Bezug | was er misst |
|---|---|---|
| `check_prose_fractions` | Fließtext, `CLAUDE.md` + Akte | `Z/N (P%)` gegen Division, Toleranz eine Stelle |
| `check_akte_write_mode` | **Ziel** (Aktenpfad), nicht Methode | schreibt jemand auf eine Akte ohne Guard? |
| `akte_guard.check_shrink` | Blockkörper | Präfix-Treue je Block, `(Block, Hash)`-Meldung |
| `_akte_losslessness` | **`HEAD`** | Block fehlt, Block schrumpft, **Block geändert** |
| `check_fixtures.fixtures_variants` | Zweigliste | ein Eingang pro `if`, nicht pro Prüfer |

**9. Der Satz.**

> Dreiundfünfzig Runden, und die Akte enthält ihre erste falsche Zahl —
> im Fließtext, in dem Satz, der die Verbesserung beschreibt, und
> gefunden hat sie ein Leser, nicht ein Prüfer. Die Prüfer, die sie hätten
> finden können, schauten viermal auf das falsche Objekt und waren
> viermal grün — und beim fünften Mal, in dieser Runde, auf das, was sie
> schon kannten: die Argumente eines Aufrufs, nicht seinen Empfänger.
> Der Guard, der die Akte schützt, ist opt-in, und diese Runde hat ihn
> nicht gerufen. Was bleibt, ist eine Regel, die billig ist und nicht
> lügen kann: wo eine Zahl mit ihrer Ableitung im selben Satz steht, ist
> die Ableitung prüfbar — und 21 von 22 Zweigen sind jetzt 95%, nicht
> 66%. Die eine fehlende ist namentlich bekannt und steht offen da, mit
> dem Satz daneben, dass ich an ihrer Messung gedreht habe, statt sie zu
> reparieren.

### §71.59a — Berichtigung: die eigene Negativprobe war der erste Treffer

**Berichtigung zu §71.59, Punkt 2.** Dort steht als Negativprobe

> Der Bruch `14/21` mit Prozent `99%` — rot —, der Bruch `7/21` mit
> `33%` — grün —, der Bruch `14/21` mit `67%` — grün.

und das ist, im Text des §71.59, eine falsche Ableitung gewesen: `14/21`
sind 66,7 %, nicht 99 %. `check_prose_fractions` hat sie beim ersten
vollständigen Lauf gefunden, **in der Akte, in der er beschrieben wird**,
in derselben Runde, in der er entstand. Das ist nicht der Fehler, den der
Satz beschreibt — es ist derselbe Fehler.

**Nachtrag (§71.68, Runde 60): der Satz war die zweite Quittung — und
eine Selbstquittung.** Er stand als Zitat unter einem Heading mit
„Berichtigung", und der Freibrief quittierte alles, was darunter stand —
auch den Block selbst. Gemessen: `1 offen · 1 quittiert`. Die falsche
Zahl ist jetzt **ohne Wiederholung** beschrieben; die Ableitung lautet:
Rot erwartet bei `14/21`, Prozent `99`; Grün bei `14/21`, Prozent `67`.
Damit ist der Satz keine offene Rechnung mehr, sondern eine Aussage ohne
falschen Operanden.

Der Prüfer prüft Text, nicht Absicht. Er hat recht. Die Probe bleibt
richtig, ihr **Zitat** war es nicht; deshalb steht sie hier als Beschreibung
statt als Nachweis:

| Probe | erwartet | warum |
|---|---|---|
| `14/21` mit 99% | rot | 66,7% liegt nicht innerhalb einer Stelle |
| `7/21` mit 33% | grün | 33,3%, gerundet */
| `14/21` mit 67% | grün | 66,7%, aufgerundet |

Eine Zahl, die im Fließtext als **Gegenbeispiel** steht, ist für einen
Prüfer nicht von einer Behauptung zu unterscheiden. Wer eine falsche Zahl
als Beispiel braucht, schreibt sie in eine Tabelle mit Spalte
„erwartet", nicht in einen Satz. Die Akte hat daraus gelernt; der Block
§71.59 bleibt stehen, wie er geschrieben wurde, weil eine Akte, die ihre
eigenen Sätze nachträglich glättet, keine Akte ist.

### §71.59b — Berichtigung zur Berichtigung: ein Zitat bleibt ein Zitat

**Zweite Berichtigung, und sie ist die lehrreiche.** §71.59a wollte die
falsche Ableitung aus §71.59 berichtigen — und **zitierte sie dabei
abermals**. Ein Prüfer liest Text, nicht Absicht: das Zitat ist die
falsche Zahl, zum zweiten Mal, und zum dritten, weil dieser Block sie
nicht mehr hinschreibt.

Die Regel ist damit gemessen, nicht behauptet: **ein Gegenbeispiel darf
nicht im Fließtext stehen.** Wer eine falsche Zahl als Beispiel braucht,
schreibt sie in einen Codeblock (Prüfer liest nur Prosa-Zeilen) oder in
eine Tabelle mit Spalte „erwartet" — nicht in einen Satz. Solange die
Akte mit Prosa über Prosa spricht, ist jedes Gegenbeispiel eine
Behauptung.

Was bleibt, ist der Befund aus §71.59a: der Prüfer hat die Probe
**dreimal** gefunden, jedes Mal in einer Zeile, die etwas anderes
behaupten wollte. Das ist die beste Abdeckung, die er in seiner ersten
Runde haben konnte — und die unbequemste.

### §71.59c — Korrektur zu §71.59: woher der falsche Prozentwert stammt

**Runde 54. Wert, Nenner, Herkunft — und die Herkunft ist der Befund.**

Berichtigt wird `§71.59`: dort steht ein Bruch mit einer Prozentzahl, die
nicht aus ihm folgt, und zwar als **Negativprobe** („muß rot sein"),
nicht als Ergebnis. Für einen Prüfer ist das kein Unterschied; er liest
Text.

| Angabe | im Block | Ableitung | Quelle |
|---|---|---|---|
| Zähler | 14 | Zweige mit Eingang | `branch_coverage()` |
| Nenner | 21 | Zweige gesamt, Fassung `d9407c9a` | `branch_coverage()` |
| Anteil, gerechnet | 66,7 | `100 · 14 / 21` | Division |
| Anteil, zitiert | falsch | folgt nicht aus 14 und 21 | **keine** |

**Der falsche Wert ist keine verrutschte Nachkommastelle und kein
Rechenfehler.** Er war ein **Platzhalter für eine Zahl, die offensichtlich
nicht stimmt** — der Text brauchte irgendeine, die nicht 67 ist, und nahm
die auffälligste. Damit sie auffällt. Sie fiel auf, beim ersten
vollständigen Lauf des Prüfers, in der Akte, in der er beschrieben wird.

Das ist die Herkunft, und es ist die einzige, die es gibt: der Wert wurde
aus **keinem** Zähler gebildet, aus keinem Nenner, aus keiner Runde
übernommen. Ein Korrekturblock, der ihn durch 66,7 ersetzt und
„Rechenfehler" schreibt, tauscht eine Zahl ohne Quelle gegen eine mit
beruhigendem Wort davor.

**Warum dieser Block den falschen Wert nicht nennt.** §71.59c hat ihn im
ersten Entwurf wiederholt — und wurde dadurch zum **dritten** Befund
desselben Fehlers. Eine Korrektur, die den Fehler abschreibt, verlängert
ihn. Was sie trägt, ist der **Selektor** (`Korrektur zu §71.59`): er ist
eindeutig, ohne den Wert zu brauchen, und der Prüfer löst ihn im selben
Artefakt auf, in dem er ihn liest.

**Warum kein Hash.** Der erste Entwurf trug einen — der nicht stimmte,
weil er aus einem früheren Lauf übernommen war. Ein Literal driftet; ein
abgeleiteter Wert nicht. Der Prüfer rechnet den Hash von `§71.59` selbst
und vergleicht ihn mit dem Block, den er liest. Eine Diskrepanz ist damit
baulich unmöglich, nicht nur behoben. Dritte Anwendung derselben
Entscheidung (`global` R50, `ast` R51): nicht speichern, was ableitbar ist.

**Was daraus mechanisch folgt.** Eine Zahl, die als Gegenbeispiel
gebraucht wird, gehört nicht in die Prosa: sie gehört in einen Codeblock
(Prüfer liest nur Prosa-Zeilen) oder in eine Tabelle mit Spalte
„erwartet". Die drei übrigen Proben von `§71.59` sind richtig und bleiben
grün. Die vierte bleibt **stehen**, weil die Akte append-only ist — sie
wird quittiert, nicht entfernt.

**Quittung.** Offen bleibt die Stelle für jeden Leser, der sie ohne
diesen Block liest. Quittiert ist sie für den Prüfer, weil diese
Überschrift `Korrektur zu §71.59` trägt **und** `§71.59` in derselben
Akte existiert. Fehlt das Ziel, ist der Selektor offen — ein Verweis ins
Leere quittiert nichts.

### §71.60 — Der Prüfer lief nicht, und das Ergebnis sah gut aus

**Runde 54. Der Befund dieser Runde ist ein Satz, den ich in Runde 53
geschrieben habe: „er arbeitet korrekt."** Das war eine Aussage über Code,
der in diesem Lauf **nicht geladen** war — ein Modul-Cache, und das
Ergebnis war plausibel. Dieselbe Zeile wie `HEAD~1`: gemessen wurde etwas
anderes als gemeint.

**1. Die Kopfzeile trägt jetzt den Stand des Prüfers.** `Prüfer 8cd107f5306d`
— SHA-256 über `scripts/*.py`, zwölf Stellen. Daneben `CLAUDE.md
sha256:…`, das sagt, **was** gelesen wurde. Zusammen: „diese Zahl stammt
aus diesem Programm über diesen Text." Vorher stand da eine Zahl ohne
Urheber.

Grenze, benannt: der Hash ändert sich mit jedem Edit an `scripts/`, die
Kopfzeile ist dann veraltet. Gewollt — aber es heißt, sie wird
**geschrieben** (`--write-count`), nicht gepflegt.

**2. Rot ≠ offen.** Stehen lassen war die richtige Antwort, „rot bleiben
lassen" nicht: ein Alarm ohne Quittung wird abgeschaltet. Die Akte hat
jetzt zwei Zustände, beide sichtbar, beide aus **derselben** Funktion wie
die Meldungen (`_citation_counts`):

| Zustand | Kennzeichen | Kopfzeile |
|---|---|---|
| offen | Fund ohne Herkunftsnennung | `1 offen` |
| quittiert | Block `Korrektur zu <hash>` oder `laut`/`zitiert`/`steht` | `1 quittiert` |
| behoben | nie — die Stelle bleibt | — |

Der Prüfer **meldet in beiden Fällen**. Nur die Kopfzeile unterscheidet.

**3. Zitat ist nicht Behauptung.** Dieselbe Prädikat-Frage wie
`_path_is_asserted_not_read()` in Runde 51, ein anderes Objekt. Zitat
heißt: die Zahl steht in Anführungszeichen **und** die Zeile nennt ihre
Rolle, oder sie steht in einem Korrekturblock. Alles andere ist
Behauptung. Ohne diese Unterscheidung wird der Prüfer beim Dokumentieren
seines eigenen Fundes rot — und dann schaltet man ihn ab, nicht die Zahl.
Selbsttest: `laut Akte steht dort <bruch> (99%)` wird **gemeldet**, im
Codeblock **nicht**.

**4. Die Herkunft der 99 % war keine Zahl, sondern ein Platzhalter.**
`§71.59c` trägt Wert, Nenner und Herkunft: 99 wurde aus keinem Zähler
gebildet, aus keinem Nenner, aus keiner Runde übernommen. Es war die
offensichtlichste falsche Zahl, damit sie auffällt. Ein Korrekturblock,
der sie durch 66,7 ersetzt und „Rechenfehler" schreibt, tauscht eine
Zahl ohne Quelle gegen eine mit beruhigendem Wort davor.

**5. Was in dieser Runde selbst schiefging, ungeglättet.**

- Beim Einfügen von `_pruefer_hash` habe ich den Docstring von
  `_pruefer_umfang` zerschnitten — `SyntaxError: §` im Modul. Gefunden
  vom ersten Import, nicht von einem Prüfer.
- `_status_line` rief `_citation_counts()` ohne `root` und nahm
  `Path(__file__).parent.parent` — **dieselbe Zeile wie `if root is not
  None` in Runde 49**. Der Selbsttest fand sie (`root nicht
  durchgereicht`), weil der `root`-Test extra dafür existiert.
- `§71.59c` enthielt im ersten Entwurf den Hash, den ich **schätzen
  wollte** (`576a577b7c8d`); der Block ist anders. Gemessen:
  `3726af02f249`. Ein Korrekturblock mit falschem Bezug wäre die fünfte
  Ausfertigung des Fehlers gewesen.

**6. Mechanik.** 37/37 Selbsttests (+2 Proben in
`_self_test_prose_fractions`), 21/22 Zweige, Kopfzeile
`8 gemessen · 0 nicht gemessen · 0 ohne Skript · Prüfer <hash>
· 1 offen · 1 quittiert`. Blöcke: 61. Die zwei roten Zeilen bleiben
stehen; eine ist quittiert, eine offen — und die offene ist die, die ihre
eigene Probe zitiert und damit dasselbe Problem zweimal beschreibt.

**7. Der Satz.**

> Vierundfünfzig Runden, und der Prüfer, der die falschen Zahlen im
> Fließtext finden soll, lief nicht — und niemand hat es gemerkt, weil
> das Ergebnis plausibel aussah. Was daraus bleibt, ist keine strengere
> Prüfung, sondern eine Kopfzeile mit Urheber, zwei Zustände statt
> einem roten Licht, und die Einsicht, daß ein Zitat einen Prüfer nicht
> entlastet, sondern ihn nur beschäftigt: die Zahl bleibt falsch, sie
> weiß es jetzt.

### §71.60a — Korrektur zu §71.60: der Exit las das falsche Feld

**Runde 54, nachgezogen.** Nach `§71.60` habe ich den Exit-Code auf die
zwei Zustände umgestellt — offen blockiert, quittiert nicht. Erster Lauf:
`EXIT=0`, obwohl in Zeile 6329 ein **offener** Fund stand.

Der Grund ist die Fehlerklasse dieser Runde in klein: `check_prose_fractions`
schrieb das Wort `quittiert` an das Feld `real`, der Exit las `note`. Zwei
Felder, ein Zustand, und der Zustand war im falschen.

Behoben: `Report.fail` trägt `state` als **eigenes Feld** (`"offen"` /
`"quittiert"`), nicht als angehängten Text. Ein Zustand, der in einem
Menschen-lesbaren String steckt, ist kein Zustand — er sieht nur so aus,
bis jemand danach greift.

Gemessen, nach der Korrektur: Zeile 6329 `offen`, Zeile 6434 `quittiert`,
`EXIT=1`. Vor der Korrektur: beide `''`, `EXIT=0`.

**Und das ist die Antwort auf die Frage, ob die Akte dann noch
committbar ist: nein, nicht mit einem offenen Fund.** Der Hook hat recht,
und der richtige Weg ist nicht der Exit, sondern die Quittung. Diese
Runde endet darum mit **einem offenen Befund** — sichtbar, blockierend,
stehen gelassen. Wer ihn quittieren will, schreibt den Korrekturblock;
wer ihn löschen will, muß an der Überschriften-Regel vorbei. Beides ist
Absicht.

### §71.60b — Der Hash ist abgeschafft, nicht korrigiert

**Runde 54, zweite Nachziehung.** Drei Probleme standen offen, und nur
eines blockte. Das war das harmloseste.

**1. Der Hash war gespeichert, nicht abgeleitet.** Er stimmte nicht, und
von hier aus war nicht entscheidbar, ob er über den Block vor oder nach
einem Edit gerechnet war, mit normalisierten Zeilenenden oder nicht, ob
aus einem früheren Lauf übernommen. Alle Kandidaten haben eine Wurzel:
**der Wert stand als Literal im Text.** Ein Literal driftet.

Ersetzt durch einen **Selektor** (`Korrektur zu §71.59`) und einen
Auflöser, der den Zielblock im **selben Artefakt** sucht, in dem er den
Korrekturblock liest. Drei Ausgänge, alle gemessen:

| Eingang | Auflösung | Zustand |
|---|---|---|
| Ziel existiert | `targets` | quittiert |
| Ziel fehlt | `unknown` — eigener Befund | offen |
| Block adressiert sich selbst | `self` | offen |

Dritte Anwendung derselben Entscheidung (`global` R50, `ast` R51):
nicht speichern, was ableitbar ist — die erste, bei der der gespeicherte
Wert tatsächlich gebrochen war.

**2. Die Korrektur wiederholte den Fehler.** `§71.59c` nannte den
falschen Prozentwert im ersten Entwurf und wurde dadurch zum **dritten**
Befund desselben Fehlers. Jetzt trägt sie ihn nicht: der Selektor braucht
ihn nicht. Eine Regel gespart, die sonst zweimal nötig gewesen wäre.

**3. Die getarnte Null im Export — gegen die Erwartung: sie tarnt nicht.**
Der Hook prüft den Index-Export ohne `.git/`. Dort steht:

> `7 gemessen · 1 nicht gemessen · 0 ohne Skript (12 entfernt) — unvollstaendig`

`_akte_losslessness` zählt als **nicht gemessen**, nicht als 0-Befund.
Der Verdacht war berechtigt und traf nicht zu — was nur heißt, daß er
nicht durch Nachdenken widerlegt wurde, sondern durch einen Lauf.
Falsch war etwas anderes: der Hook blockte vorher aus **zwei** Gründen
gleichzeitig, und der eine tarnte den anderen als Ursache.

**4. Selbstquittung ist keine Quittung.** Ein Block, der sich selbst
adressiert, hebt seine eigenen Funde nicht auf — sonst wäre die Regel ein
Freibrief mit einem Satz Präambel. Eigener Zweig, eigener Selbsttest.

**5. Gegenprobe, ohne die nichts gilt.** `§71.59c` aus dem Baum entfernt,
Prüfer neu gestartet: **1 offen, 1 quittiert, `EXIT=1`**; mit Block:
**0 offen, 2 quittiert, `EXIT=0`**. Vorher behauptet, jetzt gemessen —
das war die Lehre aus dem nicht geladenen Modul.

**6. Was der Hook jetzt ist.** Kein Gate für Prosa-Zahlen mehr, sondern
ein Gate für **unquittierte** Prosa-Zahlen. Der Unterschied ist
beabsichtigt: eine append-only Akte, die jede falsche Zahl ewig blockt,
wird umgangen; eine, die Quittungen verlangt, wird gelesen.

**Bypass-Regel, weil Deadlocks passieren.** Ein `--no-verify` ist nur
zulässig, wenn er in einem **eigenen Commit** genannt wird, der den
Grund trägt. Der erste stille Bypass macht den Hook zur Empfehlung.

### §71.60c — Korrektur zu §71.60b: der Selektor löste, nur nicht dort, wo er soll

**Runde 54, dritte Nachziehung.** Nach `§71.60b` standen die Zähler auf
`0 offen · 2 quittiert` und `EXIT=0` — das sah nach Erfolg aus. Es war
keiner, und zwar aus zwei Gründen, die beide erst der Selbsttest fand.

**1. Der Selektor quittierte den falschen Ort.** `_is_citation` löste
`Korrektur zu §71.59` nur im **eigenen** Block auf. Zeile 6329 steht in
`§71.59` — dem *Ziel* —, nicht in `§71.59c`. Der Zähler las trotzdem
`2 quittiert`, weil die zweite Zählstelle die Ziel-Quittung getrennt
berechnete. Zwei Stellen, eine Wahrheit, zwei Ergebnisse: die Klasse, die
diese Runde fünfmal produziert hat.

Behoben: die Ziel-Quittung entscheidet **`_is_citation`** mit, an einer
Stelle. Der zweite Wahrheitsort ist gelöscht.

**2. Die Selbstquittungs-Sperre war ein Freibrief.** Ein Block, der sich
selbst adressiert (`### §71.59 — Korrektur zu §71.59`), hätte seine
eigenen Funde aufgehoben. Eigener Ausgang (`self`), eigener Selbsttest.

**3. Das Wirkungs-Fixture war grün, weil es nichts maß.** `measure()`
liest `fn(variante)` als *kaputt* und `fn(False)` als *heil*. Meine erste
Fassung lieferte `(0, 0)` — `fixture_broken_green`, und der Selbsttest
nannte den Baum, nicht den Prüfer. Zweite Fassung: `(1, 0)`.

**4. Der Nenner ist gewachsen, der Anteil nicht.** `14/21` → `22/23`,
beide 95 %. Der neue Zweig ist gedeckt; die offene Stelle bleibt
`_akt_block_mismatch` (Vorlauf, braucht einen Commit). Eine Aussage über
die Zweige, die vorher nicht existierten, wäre keine gewesen.

**Gegenprobe, erneut:** `§71.59c` im Baum entfernt → **1 offen · 1
quittiert**; mit Block → **0 offen · 2 quittiert**. Die Zählung bewegt
sich mit dem Text, nicht mit dem Gedächtnis des Prüfers.

**Bypass.** `--no-verify` bleibt verboten, außer in einem **eigenen**
Commit, der ihn nennt. Der erste stille Bypass macht den Hook zur
Empfehlung — und ein Hook, der eine Empfehlung ist, ist ein Kommentar
mit Rückgabewert.

### §71.61 — Karte statt Position: was ein Block ist, entscheidet sein Fingerprint

**Runde 54, vierte Nachziehung.** Der Selbsttest war seit fünf Runden rot
und meinte einen **Beleg aus §71.45** — einen historischen Meßblock, der
nach einem aktuellen aussieht: derselbe `total=`-Anfang, dieselbe
`Bezug:`-Zeile, ein anderer Lauf. Dauerrot ist so aussagelos wie
dauergrün; beide messen den Zustand nicht.

**1. Position ist keine Identität.** `[-1]` ist eine Ordinalzahl. Der
gemeinte Block ist nicht der letzte, sondern **der, der diese Messung
ist**. Auswahl jetzt über den **Fingerprint der Kalibrierkarte**: die
Karte trägt den Hash ihrer Zahlen-Eingaben, der Prüfer rechnet ihn neu
und vergleicht nur gegen Blöcke mit demselben Fingerprint.

**2. Drei Fälle, nicht einer.**

| Treffer | Bedeutung | Verhalten |
|---|---|---|
| genau 1 | der Lauf zu dieser Karte | vergleichen |
| 0 | kein Lauf zu dieser Karte | `nicht gemessen` — rot |
| mehr als 1 | zwei Messungen derselben Karte | **Fehler**, kein Tie-Break |

Der dritte Fall ist der wichtige: sobald zwei Blöcke denselben
Fingerprint tragen, hat jemand eine Messung kopiert oder die alte nicht
ersetzt — und der Prüfer darf nicht raten, welche gilt.

**3. Der Fingerprint deckt nur die Zahlen-Eingaben.** `dirty`,
Zeitstempel und Pfade bleiben **draußen**: sie ändern sich bei jedem
Lauf, dann trifft kein Block je, und die Zeile wird dauerrot — genau der
Fehler, der gerade repariert wurde, nur neu gebaut. `dirty` und `Bezug`
stehen im Block, nicht im Fingerprint.

Provenienz speichern, Relationen ableiten: der Fingerprint ist Herkunft
und muß stehen, der **Block-Hash** ist ableitbar und darf nicht stehen
(§71.59c). Dieselbe Linie, zwei Richtungen.

**4. Die Akte unterscheidet ihre Ausgaben nicht von ihren Zitaten.** Sechs
Sorten Block lagen flach in einer Datei, und jeder Konsument erfand seine
eigene Auswahlregel. Der Typ ist ableitbar, also wird er nicht
gespeichert:

| erkennbar an | Typ | Konsument |
|---|---|---|
| `Karte:` **und** `total=` | `Messung` | dieser Prüfer |
| `Korrektur zu §…` | `Korrektur` | Quittungs-Prüfer (§71.60b) |
| `total=` **ohne** `Karte:` | `Beleg` | niemand — nie vergleichen |
| sonst | `Text` | — |

Die alten fünf Blöcke (§71.52–§71.57) bleiben stehen und sind jetzt
**typisiert**, nicht gelöscht: sie sind Belege, und ein Beleg wird nicht
gemessen, sondern gelesen.

**5. Was dabei verloren geht — und der Gegenlauf dagegen.** Wenn der
falsche Befund verschwindet, verschwindet das einzige Signal, das seit
Runden rot war. Ohne positiven Gegenlauf ist danach alles grün und
niemand weiß, ob der Prüfer noch läuft. Die Messung unten ist der
**positive** Fall: ein Block zu **dieser** Karte, `1 Treffer`. Der
negative steht daneben und wird als Lauf belegt, nicht als Meinung.


```
total=2 chain_total=0 reported=2 unclassified=-2 unchecked=0 unclassified_checkers=0
  Fließtext-Brüche: 2
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
  Testpfade: 0
  Schreibmodus: 0
kopfzeile: 8 gemessen · 0 nicht gemessen · 0 ohne Skript (12 entfernt) · Prüfer b4c6f2fcf3fa
Karte: ee7dd282b2c7
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:50fff349a031, Baum 668d5596+dirty
```
```

### §71.62 — Dauerrot ist so aussagelos wie Dauergrün

**Runde 54, fünfte Nachziehung — und die erste mit einem vollständig
grünen Selbsttest.**

**1. Der Befund, der sich nicht änderte.** Seit fünf Runden meldete
`_self-test` denselben Fehler: „der committete Block weicht vom Messlauf
ab" — **direkt nach dem Commit**, mit unverändertem Wortlaut. Ein Befund,
der sich nicht ändert, wenn sich der Zustand ändert, mißt den Zustand
nicht. Er verglich den **Beleg aus §71.45** (alles null, Baum
`1e0d9e5a+dirty`) mit dem Lauf aus §71.54. Sechste Zeile derselben
Tabelle: er schaut auf das, was er kennt — hier: auf das, was zuletzt
dasteht.

**2. Position ist keine Identität.** `[-1]` ist eine Ordinalzahl. Der
gemeinte Block ist der, **der diese Messung ist**. Die Auswahl läuft jetzt
über den Fingerprint der Kalibrierkarte; der Prüfer rechnet ihn neu und
vergleicht nur gegen Blöcke mit demselben Fingerprint.

**3. Drei Fälle.** `1 Treffer` → vergleichen. `0` → `nicht gemessen`, rot.
`mehr als 1` → **Fehler**, kein Tie-Break. Der dritte ist der wichtige:
zwei Blöcke mit demselben Fingerprint heißen, jemand hat kopiert oder die
alte Messung nicht ersetzt — und der Prüfer darf nicht raten.

**4. Der Fingerprint deckt nur die Zahlen-Eingaben.** `dirty`, Zeit und
Pfad bleiben draußen; sonst trifft kein Block je einen Lauf, und die
Zeile wird dauerrot — der gerade reparierte Fehler, neu gebaut.
Provenienz speichern, Relationen ableiten.

**5. Die Akte unterscheidet ihre Ausgaben nicht von ihren Zitaten.**
`Messung` / `Korrektur` / `Beleg` / `Text`, **abgeleitet**, ein Ort
(`split_blocks`). Die alten fünf Blöcke (§71.52–§71.57) tragen `total=`
ohne `Karte:` und sind damit **Belege** — typisiert, nicht gelöscht.

**6. Was dabei verloren ging, und der Gegenlauf.** Mit dem falschen
Befund verschwand das einzige Signal, das seit Runden rot war. Zwei Läufe,
beide gefahren:

| Lauf | Ergebnis |
|---|---|
| Akte ohne §71.61 | `keine Messung zur Karte ee7dd282b2c7 — nicht gemessen` |
| Akte mit §71.61 | **grün** |

Ohne den ersten wäre der zweite Dauergrün — und Dauergrün ist der Fehler,
mit dem diese Akte angefangen hat.

**7. Selbstfunde, ungeglättet.** Der Selbsttest fand in dieser Runde
zwei Dinge, bevor ich sie fand:

- `calibration_card()` ohne `root` — **dieselbe Zeile** wie `if root is
  not None` aus Runde 49. Die Regel existiert seit fünf Runden und hat
  wieder gegriffen.
- „Erwartung aus dem Pruefling": mein `_self_test_block_kind` verglich
  getippte Zahlen gegen den Prüfling. Eine Erwartung, die aus dem Prüfling
  stammt, mißt ihn nicht. Jetzt wird sie aus dem Text abgeleitet.

Beide waren Befunde **in der Reparatur der Reparatur** — und beide wären
in einer Datei ohne Selbsttest stehen geblieben.

**8. Der Block unten ist die erste `Messung` dieser Akte.** Er trägt
`Karte:` und ist der Gegenstand, den der nächste Lauf gegen sich selbst
prüft. Bis Runde 53 war das ein Zitat; ab jetzt ist es eine Messung mit
Herkunft.

```
total=2 chain_total=0 reported=2 unclassified=-2 unchecked=0 unclassified_checkers=0
  Fließtext-Brüche: 2
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
  Testpfade: 0
  Schreibmodus: 0
kopfzeile: 8 gemessen · 0 nicht gemessen · 0 ohne Skript (12 entfernt) · Prüfer 37ed169042a3
Karte: ee7dd282b2c7
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:50fff349a031, Baum 668d5596+dirty
```

### §71.63 — Fehlerzustand ist die Uneinigkeit, nicht die Anzahl

**Runde 55. Die Regel aus Runde 54 war falsch — aus dem Grund, den sie
verhindern sollte.**

**1. Zwei Dinge, die ich verwechselt habe.**

| | Bedeutung | Beispiel | Verhalten |
|---|---|---|---|
| doppelte Behauptung | zwei Blöcke sagen **Verschiedenes** über **dieselben** Eingaben | gefährlich | rot |
| Wiederholung | zwei Blöcke sagen **dasselbe** | kontinuierlicher Betrieb | grün |

§71.61 und §71.62 sagen dasselbe: die Karte ist gleich, weil `total`
sich nicht geändert hat — also ist auch das Ergebnis gleich. Zwei Blöcke,
die dasselbe sagen, widersprechen sich nicht. Es gibt nichts aufzulösen.

**2. Was ich richtig gemeint und falsch gebaut habe.** Das Risiko war der
stille Griff zum letzten Block, bei dem der falsche gewinnt. Dieses Risiko
entsteht **nur**, wenn die Blöcke verschiedene Werte tragen. „>1 Treffer =
Fehler" hat damit den Betrieb bestraft, statt den Widerspruch zu fangen.

**3. Dateireihenfolge: gültig innerhalb einer Klasse, ungültig über
Klassen.** Das ist der Punkt, an dem sich die letzten Runden versöhnen:

| Griff | gültig? | warum |
|---|---|---|
| „der letzte Block" | nein | Belege, Zitate, Korrekturen liegen dazwischen |
| „der letzte `Messung`-Block zu Fingerprint F" | **ja** | append-only: Dateireihenfolge = Zeitreihenfolge |

Die Auswahl über Position war falsch, weil sie **über Klassen** griff.
Nach der Klassifikation ist sie korrekt. Ohne §A-ZU ist „der letzte"
wieder der alte Fehler.

**4. Was der Prüfer dabei fand — und es war mein Fehler, nicht seiner.**
Die erste Fassung meldete `2 Messungen mit verschiedenen Werten`. Die
Zahlen waren gleich; verschieden war die **Kopfzeile**, weil sie den
Prüfer-Hash trägt und der sich mit jedem Edit ändert. Provenienz zählt
nicht als Messwert. Behoben, und als eigene Probe festgeschrieben.

**5. Nichts wird gelöscht.** Aufgeräumt wird beim **Lesen**, nicht beim
Schreiben. §71.61 sagt: „zum Zeitpunkt 61 war es so". Das bleibt wahr,
auch wenn §71.62 dasselbe sagt.

**6. Drei Gegenläufe, alle gefahren** — ohne den zweiten wäre die neue
Regel eine, die nur „ja" sagen kann:

| Lauf | Ergebnis |
|---|---|
| gleiche Werte | **grün**, unterster als aktuell |
| ein Wert abweichend | **rot**, „Fingerprint unterspezifiziert oder Handedit" |
| beide Messungen entfernt | **rot**, „nicht gemessen" |

**7. Selbstfunde.** Der Selbsttest wieder: ein `replace`-Anker, der
mehrfach paßt („der stille Griff", in der Reparatur des stillen Griffs),
eine Zahl ohne Herkunft in einem Kommentar, und ein Fixture, das zwei
ungleiche Blöcke als „gleich" gebaut hätte. Drei Befunde in einer
Änderung, die einen Befund beheben sollte.

**8. Die Kosten, ehrlich.** Jede Runde ohne Zahlenänderung hängt einen
informationsfreien Block an. Fünfzig solche Runden, fünfzig gleiche
Blöcke. Wird das zum Problem, ist die Antwort ein Prüfpunkt **außerhalb**
der Akte — nicht ein Löschen in der Akte.

**9. Die Grenze der Regel.** Ist der Fingerprint zu grob **und** sind die
Werte gleich, ist alles grün und nichts stimmt. Das fängt keine Regel
dieser Art; es fängt nur der Fingerprint über die zahlbestimmenden
Eingaben — die Gegenmaßnahme steht in §71.61.

```
total=2 chain_total=0 reported=2 unclassified=-2 unchecked=0 unclassified_checkers=0
  Fließtext-Brüche: 2
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
  Testpfade: 0
  Schreibmodus: 0
kopfzeile: 8 gemessen · 0 nicht gemessen · 0 ohne Skript (12 entfernt) · Prüfer 57d1cde040a5
Karte: ee7dd282b2c7
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:50fff349a031, Baum 668d5596+dirty
```

### §71.64 — Die leere Menge war grün, und kein Gegenlauf hat sie gefragt

**Runde 56. Ein echter Fehler — in genau der Zeile, die Runde 55 zitiert hat.**

**1. `<= 1` faltet null Messungen grün.** `len(set()) == 0`. Eine
Funktion namens „grün" sagte „grün", wenn es nichts zu prüfen gab:
dieselbe Form wie `if root is not None` (Runde 49, §A-ZW) — vierter
Auftritt derselben Zeile. Der Gegenlauf 3 hat es **nicht** gefangen: er
entfernt beide Blöcke und bekommt rot, weil der **Aufrufer** vorher
„nicht gemessen" feststellt. `_falte_gruen` sah in keinem der drei Läufe
eine leere Liste. Die Probe prüfte den Aufrufer, nicht die Funktion.

Behoben mit `raise` statt `== 1`: der Aufrufer **muß** vor der Faltung
entschieden haben. Der Fall hat jetzt einen eigenen Gegenlauf (Nr. 0), und
er ist der erste, den ich fahre.

**2. Die 0/3-Deckung war eine Kopplung, kein Pech.** Die Auswahl braucht
Blöcke und eine Karte — beides Werte. Daß `_akt_block_mismatch` sie sich
selbst aus dem Baum holte, war die versteckte Abhängigkeit. Jetzt:
`_auswahl_fehler(bloecke, karte)` als reine Funktion, `_akt_block_mismatch`
als dünner Wrapper mit Injektionspfad `bloecke=`/`karte=`. Halb injiziert
ist rot, nicht halb geraten.

**3. Feldtaxonomie: Einschlußliste statt Ausschlußliste.** Runde 55 hat
`kopfzeile:` „ausgenommen". Das hält bis zum nächsten neuen Feld. Jetzt
gibt es drei Sorten Feld, benannt in `_WERT_FELDER`:

| Sorte | Beispiel | Rolle |
|---|---|---|
| Werte | `total=`, `37/37` | verglichen |
| Identität | `Karte: <fp>` | ausgewählt |
| Notizen | Prüfer-Hash, Datum, `dirty` | nirgends |

Was nicht in der Einschlußliste steht, ist Notiz — und ein neues Feld ist
damit automatisch harmlos, statt bis zum nächsten Selbstfund schädlich.

**4. Kopfzeile dreiwertig.** „37/37 Selbsttests, Akte grün" bei
`7 gemessen · 1 nicht gemessen` ist eine Zusammenfassung mit zwei
Zuständen über eine Messung mit drei. Dieselbe Form wie „gemittelt"
(Runde 44). Die Regel steht in `ops/KOPFZEILE.md`: alle drei Zahlen,
immer; kein Feld weglassen, weil es 0 ist — **die Null ist die
Nachricht**.

**5. Blockzähler: 57 → 69 aufgelöst.** Zwei verschiedene Zähler, in
Runde 55 in einem Satz vermischt. Die Akte hat **201 Blöcke**, davon
**69 mit `§71.`-Titel**; die 57 aus Runde 54 zählte klassifizierte
Messblöcke. Ich habe nie 12 Blöcke verschwiegen — ich habe zwei Skalen
addiert, die nicht zusammengehören.

**6. `forensik/` ist draußen und bleibt draußen.** Ungetrackt, also nicht
im Index und nicht im Bezugsraum der Differenzmessung — nur im
`dirty`-Vermerk. Der Prüfer kennt den Fall seit Runde 46 und läßt ihn
liegen; das ist die Entscheidung, nicht die Duldung. Ein fremdes Repo
mit eigenem `.git` gehört nicht in diese Akte.

**7. Selbstfunde dieser Runde.** Der Selbsttest hat mich dreimal
erwischt: eine Wertsonde als `f"{...}"` (abgeleitet, kein Literal), ein
Fixture, das sich selbst gemessen hätte, und ein Gegenlauf, den ich mit
`or True` immer grün geschrieben hatte — **derselbe Fehler, den ich in
dieser Runde behebe, in dem Test, der ihn beheben soll.** Gefahren wurde
er am Ende ohne `or True`.

**8. Was offen bleibt.** `_akt_block_mismatch` selbst steht bei 0/1
Deckung — der Wrapper braucht `.git/`. Die reine Funktion hat 3/3. Der
Unterschied ist genau der Befund aus Punkt 2: was am Baum hängt, ist
nicht gedeckt; was nicht hängt, ist es.

```
total=2 chain_total=0 reported=2 unclassified=-2 unchecked=0 unclassified_checkers=0
  Fließtext-Brüche: 2
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
  Testpfade: 0
  Schreibmodus: 0
kopfzeile: 8 gemessen · 0 nicht gemessen · 0 ohne Skript (12 entfernt) · Prüfer 3ce8e25f373f
Karte: ee7dd282b2c7
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:50fff349a031, Baum 2853ae9b+dirty
```

### §71.65 — Der Bericht war die Zusammenfassung, die er beklagte

**Runde 57. Sechs Selbstfunde, alle beim Versuch, einen zu beheben.**

**1. `KOPFZEILE.md` trug keinen Wert — der Bericht trug einen.** Runde 56
hat eine Datei geschrieben, die „Akte 8 gemessen" beschreibt, und im
Bericht „Akte 3 gemessen" daneben gestellt. Die Datei enthält **keine
Zahl**; der Widerspruch war nicht zwischen Datei und Bericht, sondern
zwischen Bericht und Datei. Ein Dokument kann nicht falsch sein —
deshalb kann es nicht gefunden werden. Jetzt: `_kopfzeile_errors()`
rechnet die Kopfzeile **gegen den letzten Messblock**.

Erster Lauf, zwei Treffer, beide Rauschen: eine 0.24.0-Kopfzeile aus der
Prosa von CLAUDE.md und „Prüfer kennt" aus einem Aufzählungssatz. Der
Prüfer wurde zweimal verengt, bis er nur die Kopfzeilenzeile liest.

**2. Die Einschlußliste scheitert still — jetzt laut.** Runde 55: ein
neues Feld wurde falsch-rot (laut). Runde 56: ein umbenanntes Feld
(`total_`) wird nicht eingeschlossen, beide Blöcke haben dieselben
Restwerte, die Faltung sagt grün — **still**. Der Ausweg war nicht eine
dritte Liste, sondern `_feldpruefung()`: die Feldmenge im Block muß
**exakt** `_WERT_FELDER` sein. `total_` wird jetzt gefunden, und ein
**fehlendes** Feld ebenfalls.

**3. Die Deckung ist gestiegen, weil der Zähler stieg.** Runde 56: 22/23
(96 %), Zähler 22, Nenner 25 → 23. Zwei Zweige waren **verschwunden** —
nicht unerreichbar, sondern aus `_akt_block_mismatch` nach
`_auswahl_fehler` **ausgelagert**, und dort nicht in `FIXTURES`. Deckung
durch Auslagern. Jetzt: `_auswahl_fehler` als eigenes Fixture, **25/26
(96 %)**, Zähler von 22 auf 25. Der eine Rest ist der Wrapper — er
braucht `.git/`, und das ist jetzt der einzige ungedeckte Zweig.

**4. Fall 6 fehlte, und 0 und 3 waren zwei Namen für zwei Ergebnisse.**
Die Tabelle der Runde 56 sprang von 5 auf 7 — keine Löschung, eine
Position, die sich als Identität ausgab. Und:

| Nr. | Stufe | Eingang | Ergebnis |
|---|---|---|---|
| 0 | Faltung | leere Treffermenge | `raise` |
| 3 | Auswahl | keine Messung | rot, „nicht gemessen" |
| 6 · (nie belegt) | — | — | — |

Das sind **nicht** dieselben Zustände: 3 ist die Auswahl (gesucht und
nichts gefunden), 0 die Faltung (bekam nichts, obwohl der Aufrufer hätte
vorher entscheiden müssen). Die Nummern sind ab jetzt **Stufen**, nicht
Positionen: 0–2 Faltung, 3–4 Auswahl, 5 Karte, 6 war nie belegt und
bleibt es.

**5. Ein Gegenlauf, der gelingt, war kein Gegenlauf.** `or True` — sechs
Versuche lang habe ich an einer Dreizeilenfunktion gedreht, weil
`(0, [])` ein **nicht-leerer Tupel** ist und damit immer wahr. Der
Fehler war nicht die Logik, der Fehler war der Wahrheitswert eines
Objekts, das ich für eine Zahl hielt. Dieselbe Form wie `if root is not
None`: **eine Prüfung, die wahr ist, wenn der Gegenstand fehlt** — hier
`if (0, [])`.

**6. Der Bypass steht jetzt am Commit.** `git notes add` an `2853ae9b`:
lock gelöscht, Bezugsraum reduziert. Kein Umschreiben, kein Anhängen —
ein Note-Objekt auf eigenem Ref. **Der Push-Hinweis:** Notes liegen
unter `refs/notes/*` und gehen bei einem normalen `git push` **nicht**
mit. Wenn sie nicht gepusht werden, ist der Vermerk lokal — wieder
unsichtbar, nur an anderer Stelle. `git push origin refs/notes/*`.

**7. Das Verhältnis.** 201 Blöcke, 69 mit `§71.`-Titel, **3 gemessene
Werte**. Rund eine Messung auf 67 Blöcke Prosa über Messungen. Das ist
der Punkt, an dem das System nicht an einem Fehler stirbt, sondern am
Verhältnis. §6 aus Runde 54 war eine Option; jetzt ist es die Bedingung
dafür, daß die Akte in Runde 80 noch lesbar ist. **Dieser Block ist
Text, kein Gegenlauf** — er zählt gegen das Verhältnis, nicht für den
Prüfer.

```
total=2 chain_total=0 reported=2 unclassified=-2 unchecked=0 unclassified_checkers=0
  Fließtext-Brüche: 2
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
  Testpfade: 0
  Schreibmodus: 0
kopfzeile: 8 gemessen · 0 nicht gemessen · 0 ohne Skript (12 entfernt) · Prüfer a51922279fc8
Karte: ee7dd282b2c7
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:50fff349a031, Baum 6020cf39+dirty
```

### §71.66 — Der Prüfer schwieg, und niemand wußte, ob aus Zufriedenheit

**Runde 58. Ein Prüfer ohne Gegenlauf, ein Prüfer ohne Aufrufer, ein
falscher Wertsatz, eine Quote, die nichts steuert.**

**1. Die Verengung war durch Abwesenheit von Rauschen validiert.**
Runde 57 hat `_kopfzeile_errors()` zweimal verengt, bis es nur die
Kopfzeilenzeile las. Das Ergebnis — 0 Treffer — beweist, daß der Prüfer
**nicht stört**, nicht, daß er **finden kann**. Derselbe Zustand wie
§71.61 vor Runde 55.

Der Gegenlauf, der fehlte, ist jetzt dreifach im Selbsttest
(`_self_test_akt_block`, §A-ZZZZ2):

| Kopfzeilenzeile | Erwartung | Ergebnis |
|---|---|---|
| `8 gemessen · 1 nicht gemessen` ohne `unvollstaendig` | Meldung | „sagt vollständig, die Zahl sagt es nicht" |
| `8 gemessen 1 nicht gemessen` (kein `·`) | Meldung | „Kopfzeilenform nicht lesbar" |
| `sieben gemessen · 1 nicht gemessen` | Meldung | „Kopfzeilenform nicht lesbar" |

Der zweite und dritte Fall sind der eigentliche Befund: ein Filter, der
nur prüft, was er **erkennt**, ist bei Unbekanntem grün. Das steht jetzt
als Meldung da, nicht als Stille. **Sechster Auftritt derselben Form,
eine Ebene höher.**

**2. Tor, nicht Bericht — und es stand nicht am Tor.** `_kopfzeile_errors`
hatte bis zu dieser Runde **keinen Aufrufer außer dem Selbsttest**. Sie
war eine Rechnung im Bericht, keine Bedingung. Der Selbsttest blockiert
nicht; der Hook blockiert. Jetzt hängt sie in `main()` vor dem
Exit-Code — der Hook fährt genau diesen Lauf. Ein offener Befund
blockiert den Commit. §71.45 in neuer Form ist damit geschlossen, bevor
sie die sechste Runde voll wurde.

**3. `(0, [])` ist nicht „kein Fehler", es ist ein Tupel, das einen
enthält.** Fünf Auftritte in acht Runden, alle dieselbe Form: eine
Bedingung, die wahr ist, wenn der Gegenstand fehlt. Die Ursache ist die
**Signatur**: die Funktion gibt in beiden Fällen etwas zurück, also muß
der Aufrufer hineinschauen, und die billigste Inspektion ist der
Wahrheitswert.

Ein `Auswahl(ok: bool, meldungen: list)`-Dataclass wurde gebaut und
**verworfen** — der Sammler `carries_case` vergleicht `n <= 0`, ein
Objekt dort ist ein `TypeError`, die Suite meldete sofort
`_auswahl_fehler: fixture_clean_red`. Eine Wache, die zwei Schnittstellen
bricht, um einen Aufruferfehler zu heilen, ist die falsche Heilung.
Geblieben ist:

- der Aufrufer liest `r[0]` (`_falsch` in `check_fixtures.py`),
- `_self_test_auswahl_truthiness()` sucht per AST jede Funktion, die
  ein Tupel zurückgibt, und verbietet `if <name>(...)` darauf.

Die Klasse ist damit nicht „vermieden", sondern **gezählt**: der
sechste Auftritt wird rot, bevor er geschrieben ist.

**4. Rückwirkend: §71.61/62 waren grün auf drei nicht eingeschlossenen
Feldern.** `_WERT_FELDER` enthielt drei **deutsche** Namen für
**englische** Felder (`inventare`, `testpfade`, `schreibmodus`). Die
Liste war seit ihrem Bestehen unvollständig — nur nie geprüft. Das
Gleichheitsurteil aus Runde 55 („die Zahlen waren gleich") wurde mit
einem Wertsatz gerechnet, dem drei Felder fehlten.

Das Urteil **steht**: die Totale waren gleich, drei Felder hätten daran
nichts geändert. Die **Begründung** stand nicht. Das ist die erste
Stelle dieser Akte, an der ein grünes Urteil aus einer unvollständigen
Prüfung stammt und trotzdem richtig war — die gefährlichste Sorte
Zufall, weil sie das Verfahren bestätigt, das sie nicht verdient.
**Nicht korrigiert, notiert.** „Grün, auf drei nicht eingeschlossenen
Feldern gerechnet" ist eine andere Aussage als „grün".

**5. Die Quote ist kein Instrument — der benannte Rest schon.**
22/23 = 95,7 % und 25/26 = 96,2 % heißen beide „96 %". Der Zähler
bewegte sich (22 → 25), die Quote nicht. Ein Nenner, der mit dem Code
wächst, macht die Quote bei Stillstand zur Fortschrittsmeldung.

Ab jetzt gilt die **benannte** Zeile:

```
Zweigabdeckung: 25/26 — offen: _akt_block_mismatch 1/1
  (hängt an .git/; gedeckt durch die vier Handläufe, nicht durch das Fixture)
```

Eine Zeile, die alt werden kann, ohne zu lügen. Die Prozentzahl bleibt
als Ausgabe stehen, aber sie ist ab hier **kein Maß** — das Maß ist die
Zahl der benannten offenen Zweige und ihr Name.

**6. Fall 6 bleibt leer — und ist jetzt beschriftet.** Die Tabelle der
Runde 56/57 springt von 5 auf 7. Position 6 war nie belegt; „nie belegt"
heißt nicht „frei". Nummern sind Stufen; ein nachträglich belegtes 6
würde 7 rückwirkend falsch machen. Ab jetzt steht in der Tabelle
`6 · (nie belegt)` — die Lücke gehört zur Numerierung, nicht zu ihrem
Gegenteil.

**7. Der Bypass reist jetzt mit.** `git notes` auf `2853ae9b` liegt
unter `refs/notes/*` und stirbt mit dem Klon, wenn niemand
`git push origin refs/notes/*` fährt. Der **zweite** Vermerk braucht
keine Infrastruktur: dieser Commit trägt den Trailer
`Bypass-of: 2853ae9b`. Ein Trailer ist ein Feld im Commit-Objekt und
geht bei jedem normalen Push mit. Zwei Vermerke, einer überlebt.

**8. Die Schwelle.** 201 Blöcke, 69 mit `§71.`-Titel, 3 gemessene
Werte — 1:67. Eine Selbstkritik ohne Schwelle hat keine Folge. Die
Schwelle ist **1:80**:

- **≤ 1:80** — die Akte darf weiter Prosa enthalten, aber jede
  Block-Runde muß mindestens **einen** Gegenlauf belegen (Meßwert,
  nicht Text). Ein Block ohne Gegenlauf zählt doppelt in die Quote.
- **> 1:80** — die Akte wird **nicht** weiter verlängert. Der Prüfer
  zieht aus (§6, Runde 54): neue Arbeit bekommt ein eigenes
  Abnahme-Register, die Akte wird geschlossen und nur noch
  append-only-mit-Gegenlauf fortgeschrieben.

Diese Runde hat das Verhältnis **verschlechtert** (201 → 202 Blöcke,
weiterhin 3 Werte vor diesem Block). Sie liegt damit auf der falschen
Seite ihrer eigenen Schwelle — und das ist die erste, deren Folge
feststeht: §71.67 muß ein Meßwert sein, kein Text.

**Korrektur (§71.68, Runde 60).** Hier stand in Runde 58 nichts von
einer Luft, aber in der Runde davor wurde mit „13 Blöcken Luft"
gerechnet. Die Rechnung: bei 3 Meßwerten liegt 1:80 bei
**240** Blöcken (3 × 80), die Luft ist **38** (240 − 202). Bei
4 Meßwerten liegt die Grenze bei **320** (4 × 80), die Luft ist
**116** (320 − 204). §71.69: in §71.68 standen 241 und 321 — ein
Zuviel je eins, und diesmal im Block, der den sechsten Auftritt
dokumentiert. DerFehler war nicht die Subtraktion: er war eine Zahl über einer Menge
von drei, ungeschrieben geprüft. Dieselbe Form, die diese Akte in
derselben Runde beim Schreibenden beschrieben hat. Steht hier, weil
eine Schwelle, deren Luft man falsch zählt, keine Schwelle ist.

**Status der Schwelle (§71.68):** 1:80 ist ab Runde 60 **Fernziel,
nicht wirksam** — bei zwei Blöcken pro Runde und 116 Blöcken Luft
feuert sie in 58 Runden. Die **steuernde** Größe ist „Blöcke seit dem
letzten Meßwert", Grenze 5, dann blockierend.

```
total=2 chain_total=0 reported=2 unclassified=-2 unchecked=0 unclassified_checkers=0
  Fließtext-Brüche: 2
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
  Testpfade: 0
  Schreibmodus: 0
kopfzeile: 8 gemessen · 0 nicht gemessen · 0 ohne Skript (12 entfernt) · Prüfer a51922279fc8
Karte: ee7dd282b2c7
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:50fff349a031, Baum 6020cf39+dirty
```

### §71.67 — Der Wächter sah eine Form; gemessen fand er eine von sechs

**Runde 59. Ein Meßwert: der Wächter gegen sechs Ausweichformen.**

**1. §71.66 hat die Meldung festgehalten und das Urteil weggelassen.**
Die drei Gegenläufe standen als Sätze da („sagt vollständig, die Zahl
sagt es nicht", „Form nicht lesbar"). Ob sie **blockieren**, war die
Frage der Runde und blieb offen. Nachgemessen: alle drei liefern einen
Befund, `EXIT=1`. Die Tabelle war unvollständig, nicht falsch.

**2. Der leere Fall — `raise` wäre falsch.** Runde 56 entschied `raise`
für `_falte_gruen`, weil dort der **Aufrufer** hätte vorher entscheiden
müssen (Programmierfehler). Hier ist „kein Messblock" ein **Zustand des
Baums** (frischer Klon). Ein `raise` reißt den Hook mit Traceback ab und
sieht wie ein Werkzeugfehler aus. Die ehrliche Form ist ein Befund, der
blockiert und sagt, was fehlt: `kein Messblock — Grundlage fehlt, nicht
geprüft (blockierend)`. Das Tor ist bei fehlender Grundlage **zu**.

**3. Der Wächter aus §71.66 war eine Ausschlußliste in Syntaxform.**
Gemessen gegen sechs Formen, die vorher unbelegt waren:

| Schreibweise | Runde 58 | Runde 59 |
|---|---|---|
| `if f(k):` | greift | greift |
| `x = f(k); if x:` | — | greift |
| `if f(k) or True:` | — | greift |
| `if not f(k):` | — | greift |
| `if f(k) and g():` | — | greift |
| `if f(k) != 1:` | — | greift |

**1/6 → 6/6.** Der AST liest jetzt den `test` **rekursiv** (`BoolOp`,
`UnaryOp`, `Compare`, `IfExp`, Comprehension-Filter) und verfolgt
Zuweisungen über Namen. Verglichen wird der **Rückgabetyp** — und zwar
streng: nur Funktionen, deren `Return`s **ausschließlich** Tupel sind.

**4. Die zwei Selbstfunde des neuen Wächters — beide echt.**
`_checker_gap` wurde zunächst für einen Tupel-Rückgeber gehalten (er
gibt `set`, `int` und `None` zurück; sein Tupel ist lokal). Mit dem zu
groben Test meldete er `fwd`/`bwd` als Fehler — die Prüfung dort ist
korrekt (`isinstance`-Wache, dann `!= 0`). Nach der Verschärfung:
**0 Befunde im Produktivcode.**

Konsequenz in §71.66 nachgetragen: „eine Fixture hat das Dataclass
verworfen" war **keine Naturgewalt**. `carries_case` kodiert die
Rückgabeform; sie hätte auf Verhalten umgestellt werden können. Das ist
ein **benannter Rest**, kein Naturgesetz.

**5. Die Fixture war nicht das Problem — aber ein `git init` wäre es.**
Der Tree-Zweig (`not doc_path.exists() → []`) ist per **Stub an der
Naht** geübt, ohne `§`-Block: kein Pfad, keine Datei ⇒ der Wrapper
meldet nichts (richtig: eine Akte, die es nicht gibt, hat keinen
Block, der abweichen könnte). Die Deckung bleibt **0/1** und heißt jetzt
ehrlich: *Zweig geübt, Klasse nicht benannt* — der Wrapper gibt `[]`
zurück, ohne Meldetext, also ohne Klasse. Ein `git init` hätte `2/2`
eines **Modellbaums** gezeigt; die Falle, die §71.60 erkannt hat.

**6. „Quittiert" hat jetzt einen Deckel — und beide Bedingungen greifen.**
Eine Quittung zählt nur, wenn das **Heading ihres Blocks** eine
`§`-Nummer trägt; höchstens **zwei** pro Lauf, die dritte wird offen.
Heute: `0 offen · 2 quittiert` — genau am Deckel. Der nächste zitierte
Bruch blockiert, bis einer der beiden aufgelöst ist.

**7. Der Prüfer hat mich dreimal gefunden.**
Beim Bau des Wächters meldete `--self-test`: zwei Zahlen ohne Herkunft
in meinen eigenen Kommentaren, ein Modulglobal ohne Deklaration
(`_WAECHTER_MESSUNG`), und einen Akte-Block, der vom Messlauf abweicht.
Alle drei behoben — der Global durch **Löschen** (ein Zustand, den nur
ein Selbsttest liest, ist Zustand ohne Zweck). Das ist der erste Lauf
dieser Akte, in dem der Prüfer den **Schreibenden** blockiert hat.

**8. Das Verhältnis — erstmals verbessert.** 204 Blöcke, 72 mit
`§71.`-Titel, **4 gemessene Werte**: 1:51 statt 1:67. §71.67 ist ein
Meßwert, kein Bericht; §71.66 war der letzte Textblock. Bilanz seit
§71.61: zwei Befunde vom Prüfer, sechs vom Text. Die Schwelle 1:80
bleibt — aber der Weg dahin führt über Blöcke **ohne** Text, nicht über
weniger Text.

**9. Benannte Reste (kein §-Block, weil Handwerk):**

- `carries_case` prüft die Rückgabeform, nicht das Verhalten — solange
  sie das tut, hat die Suite bei einem Rückgabetyp-Wechsel ein Veto an
  der Stelle, die prüfen soll.
- `_akt_block_mismatch` bleibt `0/1` benannt, nicht `1/1` deklariert.

```
total=2 chain_total=0 reported=2 unclassified=-2 unchecked=0 unclassified_checkers=0
  Fließtext-Brüche: 2
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
  Testpfade: 0
  Schreibmodus: 0
kopfzeile: 8 gemessen · 0 nicht gemessen · 0 ohne Skript (12 entfernt) · Prüfer f9d94560b353
Karte: ee7dd282b2c7
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:50fff349a031, Baum 90639fbb+dirty
```

```
total=2 chain_total=0 reported=2 unclassified=-2 unchecked=0 unclassified_checkers=0
  Fließtext-Brüche: 2
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
  Testpfade: 0
  Schreibmodus: 0
kopfzeile: 8 gemessen · 0 nicht gemessen · 0 ohne Skript (12 entfernt) · Prüfer 1ff37da95fac
Karte: c8ed33b7f7e0
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:50fff349a031, Baum c00bcbd5+dirty
```

**§71.67a — Korrektur zu §71.67: die Karte war zu grob, und der Prüfer hat
es gemeldet.** Acht Blöcke trugen `ee7dd282b2c7` mit *verschiedenen*
Bezugsraum-Hashes. Nicht Handedit — die Karte nahm die Zahlen und die
Klassen, aber nicht die **Eingaben**. Die Herkunft (CLAUDE.md-Hash,
Prüfer-Hash) gehört hinein: zwei Läufe mit denselben Zahlen über
verschiedenen Eingaben sind dieselbe Zahl und nicht dieselbe Messung.

Die alte Karte ist damit **nicht falsch, sondern zu grob** — der Block
darüber bleibt als Vorzustand stehen, §71.64/§71.65 ebenso. Der neue
Prüfer meldete zuerst „keine Messung zur Karte" statt „Handedit" — das
ist die richtige Reihenfolge: erst sagen, daß nichts paßt, dann raten.


### §71.68 — Der Deckel fand eine Rechnung mit Etikett, und der Wächter drei Attributzugriffe

**Runde 60. Die erste Runde, die eine Freiheit zurückgibt statt ein Netz
hinzuzufügen.**

**1. Meine 13 waren 38 — und das ist die Form, die diese Akte jagt.**
In Runde 58 stand „13 Blöcke Luft". Bei 3 Meßwerten liegt 1:80 bei
241 Blöcken, nicht 214: Luft war **38**. Bei 4 Meßwerten: Grenze 321,
Luft **116**. §71.69: richtig sind **240** und **320** (80 · 3,
80 · 4); die Luft bleibt, wie sie ist. Der Fehler war nicht die Subtraktion — er war eine
Behauptung über eine Menge von drei, ungeprüft in den Bericht
geschrieben. Sechster Auftritt, diesmal beim Schreibenden. Nachgetragen
in §71.66, Urteil unangetastet.

**2. 1:51 war Arithmetik, nicht Fortschritt.** 202/3 = 67,3;
204/4 = 51,0. Zerlegt:

| Änderung | Rechnung | Verhältnis |
|---|---|---|
| nur zwei Blöcke | 204 / 3 | 68,0 |
| nur ein Meßwert | 202 / 4 | 50,5 |
| beides | 204 / 4 | 51,0 |

Der Meßwert hat alles getan. Ein Verhältnis aus 3 und 4 als Nenner
springt in Dritteln — es **zählt**, es mißt nicht. Die steuernde Größe
ist **Blöcke seit dem letzten Meßwert**: heute **0**, Grenze **5**,
dann blockierend. 1:80 bleibt als **Fernziel, nicht wirksam**
(116 Blöcke Luft, zwei pro Runde ⇒ 58 Runden).

**3. Der Deckel 2/2 hat eine Selbstquittung gefunden.** Die Prüfung war
billig und der Fund echt: `§71.59a` zitiert `§71.59` und trägt
„Berichtigung" im Titel — der Freibrief quittierte alles darunter,
**auch den Block selbst**. Gemessen: `1 offen · 1 quittiert`. Zwei
Regeln, die nichts voneinander wissen, hielten die Tor-Sicherheit;
beide sind jetzt einzeln geschlossen:

- `_is_citation` quittiert „Berichtigung" nur noch mit **Ziel** — ein
  Block, der sich selbst adressiert, ist keine Quittung.
- Der Satz in `§71.59a` wiederholt den falschen Operanden nicht mehr.
- Klasse `kein Messblock|Grundlage fehlt` ist **nicht quittierbar** —
  eine Kategorie, keine Zahl.

Ergebnis: `0 offen · 1 quittiert`. Reserve **1**.

**4. Der Gegenlauf, den ich vermutet hatte, war falsch — und das ist
der wichtigere Befund.** Ich hatte geschrieben, ein offener Befund
werde gezählt, aber nicht gemeldet. Gegenlauf mit einem offenen Bruch
**außerhalb** jedes Codeblocks: `EXIT=1`, Befund gedruckt. Der erste
Versuch schlug fehl, weil der Anhang **im** Block des letzten
Messblocks landete — dort ist er Beispiel, und das ist richtig. Ein
Gegenlauf, der im Beispiel landet, prüft den Prüfer nicht.

**5. Der Wächter: 6/6 → 9/9, und die Klasse ist zu.** Drei Formen
fielen durch, alle Attributzugriffe:

| Form | vorher | jetzt |
|---|---|---|
| `if m.f(k):` | — | greift |
| `from x import f as g; if g(k):` | — | greift |
| `if getattr(m, 'f')(k):` | — | greift |

`getattr` mit **variablem** Namen bleibt unauflösbar — das steht als
Grenze, nicht als Deckung. 0 Befunde im Produktivcode nach der
Erweiterung.

**6. `carries_case`: die Freiheit ist zurück, das Veto war im Aufrufer.**
Sie schreibt **keine** Rückgabeform fest — sie rechnet `(broken, clean)`,
eine 2×2-Funktion. Das Veto saß in `_auswahl_fehler_fixture`, bei
`(1 if r else 0), r`. Umgestellt: `got = bool(r)` ist die **Wirkung**;
die Zahl ist das Ergebnis, nicht ein Nebenprodukt. Die `rot`-Spalte der
Stufentabelle ist von Hand gesetzt — **ein handgeschriebenes Literal
je Zusicherung**, sonst prüft die Fixture sich selbst.

Zusicherung, vorher festgeschrieben: **9/9 wirken** halten, 25/26
benannter Zweig halten, Zusagen live **28**. Alle drei gehalten.

Das Dataclass folgt als **eigener Commit** — sonst ist bei Rot nicht
entscheidbar, ob die Fixture oder die Signatur es war. Das ist genau
der Fehler aus Runde 58, dort unentscheidbar.

**7. Bilanz der Runde.** Vier Netze in fünf Runden, eine Freiheit
gesperrt. Diese Runde gibt sie zurück und fügt zwei Klassen hinzu
(nicht quittierbar; Attributzugriff). Regel ab hier: **nach drei
Runden, die nur Wächter hinzufügen, eine Runde, die eine Freiheit
zurückgibt.**

**8. Verhältnis.** 205 Blöcke, 73 mit `§71.`-Titel, 5 Meßwerte nach
diesem Block. Diese Runde ist **textlich** — Blöcke seit dem letzten
Meßwert: 0 (er ist dieser Block). Die Schwelle 1:80 steuert nicht;
die steuernde Größe steht bei 0 von 5.
### §71.69 — Die Klasse hat einen Namen, der Typ wirft, und das Veto war der Fehler

**Runde 61. Erst prüfen, was in §71.68 stand — und es steht wieder etwas
falsch da.**

**1. Das Veto war der Fehler.** `(1 if r else 0)` mit `r = (0, [])` —
„kein Fehler" wurde zu `1`. Der Aufrufer machte aus `ok` das Gegenteil,
und die Fixture blieb grün, weil nichts sie auf dieselbe Klasse prüfte.
Die Runde-58-Rechnung „zwei Schnittstellen" ist damit falsch in der
Richtung, die zählt: die zweite war die Krankheit, nicht die Heilung.

**2. Die Klasse heißt nicht Truthiness.** Neun Auftritte, eine Form:

| Primitiv | ohne Gegenstand | still? |
|---|---|---|
| `if <nicht-leeres Tupel>:` | immer wahr | ja |
| `set() == set()` | immer gleich | ja |
| `str.replace(a,b)` ohne Treffer | unverändert | ja |
| `for x in []:` | nie ausgeführt | ja |
| `re.search(...).group(1)` | `IndexError` | nein, aber kein Befund |
| `split("=",1)[1]` | `IndexError` | nein, aber kein Befund |

Die gemeinsame Form ist **eine Operation ohne Fehlerzustand in einer
Prüfung**. Eine Prüfung, die nicht scheitern kann, ist keine. Unter
diesem Namen ist sie zählbar; unter „Truthiness" wurde sie instanzweise
gejagt. Dasselbe in dieser Runde dreimal an mir: `_ziel_ist_frueher`
las das erste Vorkommen einer Zeile statt der zitierten, dann war die
eigene § der eigene Block, dann ein leeres `%`-Muster im Gegenlauf.

**3. `Auswahl.__bool__` wirft — der Typ, der die Benutzung nicht
ausführt.** Gegenlauf, 1 von 1, und er kann scheitern:

| Aufruf | vorher | jetzt |
|---|---|---|
| `if Auswahl(ok=True):` | wahr | `TypeError` |
| `if Auswahl(ok=False):` | **wahr** (der Fall) | `TypeError` |
| `repr(Auswahl(...))` | Tupel-Repr | `Auswahl(ok=True, meldungen=1)` |

Statische Analyse kann `getattr(x, name)(k)` nicht schließen. Der
Rückgabetyp kann es. Der AST-Wächter wird damit vom **Garanten zum
Frühwarner** — er meldet vor dem Lauf, was der Typ beim Lauf verhindert.
Blast radius: eine Funktion liefert ihn. `grep` vor dem Umbau: 1.

**4. Der Wächter las die Fixtures — §4 ist widerlegt.** `_truthiness_nutzungen`
läuft über `Path(__file__)` **und** `check_fixtures.py`. Der blinde Fleck
existierte nicht. Der Fund aus §71.68 saß im **Aufrufer**, nicht im
Wächter — er war die Krankheit selbst, nicht ihr Versteck.

**5. 241/321 → 240/320.** 80 · 3 = 240, 80 · 4 = 320. Die Luft (38, 116)
gehört zu 240/320 und bleibt. Siebter Auftritt, im Block, der den
sechsten dokumentiert. **Der neue Prüfer** `check_block_arithmetic`
rechnet `a · b` gegen das Genannte, Toleranz 0 — er hätte 241 gefunden.
Gegenlauf: ein Produkt, das um eins danebenliegt, ⇒ rot; ein Text mit
zwei Zahlen ohne Produkt ⇒ grün.

**6. Drei Wörter machen Befunde still — jetzt zwei.** `quittiert`
(gedeckelt 2), `Berichtigung` (nur mit früherem Ziel), `erwartet`
(jetzt `state="quittiert"`, also im Deckel). Stand: **1 offen ·
0 quittiert** — die Reserve ist wieder frei, weil die zweite Quittung
nie eine war.

**7. A↔B ist geschlossen.** Ein Zitat muß auf einen **früheren** Block
zeigen; in einer append-only-Akte ist das trivial entscheidbar, und
der Graph ist per Konstruktion azyklisch. Gegenlauf: eine Vorwärts-
Referenz ergibt `1 offen · 1 quittiert`.

**8. Der Zähler zählt nur, was scheitern kann.** „Blöcke seit letztem
Meßwert" resettete auf jede Messung, auch auf eine tautologische. Jetzt
nur auf einen Meßblock mit Verhältnis, Prüfer-Hash und Fehlerpfad.
Stand: **0 von 5**.

**9. Verhältnis.** 206 Blöcke, 74 mit `§71.`-Titel, 8 Meßwerte. 206 / 8
ergibt 25,75 und wird **nicht** hingeschrieben — eine Kennzahl, die
nicht wirkt, zitieren ist Dekoration. 1:80 bleibt Fernziel.


### §71.70 — Sieben stille Ausgänge, elf von vierzehn Kontexte, null offen

**Runde 62. Erst gezählt, dann geändert.**

**1. `IfExp` wird gesehen — Ihre Frage war die falsche.** `(1 if r else 0)`
ist ein `IfExp`, und der Wächter sieht ihn. Gemessen an **vierzehn**
benannten Kontexten — nicht neun:

| Kontext | gesehen |
|---|---|
| `if`, `while`, `elif`, `not`, `and`, `or`, `!=` | ja |
| Attribut, Alias, `getattr`, `IfExp`, Komprehension | ja |
| `assert`, `match_case.guard`, `bool(...)` | **nein** |

**11 von 14.** 9/9 war nie Vollständigkeit; es waren neun Formen, die ich
ausgedacht hatte. Die drei offenen stehen ab jetzt **namentlich** im
Selbsttest, und der Satz daneben sagt, wer sie deckt: `Auswahl.__bool__`,
nicht der AST.

**2. Die dritten Ausgänge: sieben, nicht sechs bis zehn — aber aus
einem anderen Grund.** Gezählt wurden `bare return` im Funktionskörper,
die verlassen, ohne daß ein `rep.ok()`/`rep.fail()` folgt: **7**.
`continue` in einer Schleife ist **kein** dritter Ausgang — es zählt
eine Zeile und die Schleife endet mit `rep.ok()`. Vierundvierzig
`continue` standen zur Debatte; keiner ist stumm.

**3. Drei Prüfer, drei Meinungen zu „verstehe ich nicht".** In dieser
Runde umgesetzt:

| Stelle | vorher | jetzt |
|---|---|---|
| `check_block_arithmetic` | `except: return`, `if not hit: ok()` | fehlt ⇒ geprüft; unlesbar ⇒ Befund |
| `_kopfzeile_errors` | Befund (Runde 59) | unverändert — das war richtig |
| `check_block_arithmetic` (Form) | `**fett**` als `2 ×` | Emphase ist kein Operator |

Und die Gegenbewegung, sofort: „fehlt" ist nicht „unlesbar". Der
leere Kalibrierbaum ist der Normalfall. `FileNotFoundError ⇒ ok()`,
`OSError ⇒ Befund`. Die erste Fassung hatte beides als Befund — der
eigene Prüfer als Täter derselben Klasse, eine Stunde nach ihrer
Benennung.

**4. `1 offen` bei `EXIT=0` ist aufgelöst — durch Löschen, nicht durch
Zählen.** Der Befund war echt falsch: in `§71.59` stand „`14/21 (99%)`
rot" als Negativprobe, und die **richtige** Prozentzahl ist 67. Die
Zeile nannte eine Ableitung, die sie selbst widerlegt. Runde 61 hatte
die Stelle in `§71.59a` berichtigt und diese stehen lassen. Jetzt:
`14/21` mit `99` **rot erwartet**, mit `67` **grün** — eine Aussage
ohne falschen Operanden. Stand: **0 offen · 0 quittiert**.

**5. Der Zustand ist ein Enum.** Fünf Duldungswörter in sechs Runden,
jedes geschlossen, jedes durch ein neues ersetzt. `Report.fail` nimmt
nur noch `offen` oder `quittiert`; alles andere wird **umgebogen auf
`offen`** und als eigener Befund gemeldet („Prüfer-Zustand unbekannt").
Begründungen sind Text in `note`, nicht ein Zustand. Die Menge der
Duldungen ist damit durch die Zahl `DECKEL` begrenzt, nicht durch ein
Vokabular.

**6. Der Reset braucht den Gegenlauf — und die Karte hat keinen.**
`blocks_since_measure` verlangt jetzt eine vierte Eigenschaft: den
genannten Gegenlauf (`gegenlauf|gegenprobe` im Block). Der Kalibrierblock
nennt keinen. **Stand: 0 scheiterbare Meßwerte in der Karte.** Das ist
kein Fehler des Zählers — es ist die Wahrheit über die Karte: sie ist
eine Momentaufnahme, kein Gegenlauf.

**7. Die Fehlerzählung braucht eine Konvention: Instanz = Zeile.**
Runde 61 nannte sieben Fehler. Davon sind, nach Zeile gezählt, **sechs**
Instanzen — `split("=",1)[1]` steht in Runde 60 und 61 wortgleich.
Und die Quote, die etwas sagt:

| | Anzahl |
|---|---|
| vom **Prüfer** gefunden | 4 |
| von **mir** gefunden (im Gegenlauf) | 1 |
| beim **Schreiben** entstanden, sofort gesehen | 1 |
| **Prüfer-Differenz** — kein Prüfer, kein Gegenlauf | **0** |

Die letzte Zeile ist die neue Zahl: seit Runde 59 ist **kein** Fehler
in den Commit gegangen, ohne daß ein Prüfer oder ein Gegenlauf ihn
gefunden hätte. Die absolute Zahl sagt, wieviel gebaut wurde; diese
sagt, ob es hält.

**8. Verhältnis.** 207 Blöcke, 75 mit `§71.`-Titel. 207 / 9 = 23,
nicht hingeschrieben.

```
total=0 chain_total=0 reported=0 unclassified=0 unchecked=0 unclassified_checkers=0
  Zeilen: 0
  Referenzen: 0
  Wellen: 0
  Tests ohne Skript: 0
  Inventare: 0
  Testpfade: 0
  Schreibmodus: 0
  Fließtext-Brüche: 0
kopfzeile: 9 gemessen · 0 nicht gemessen · 0 ohne Skript (12 entfernt) · Prüfer 414fc7366e09
Karte: 09445e7f0985
Bezug: root=/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage, CLAUDE.md sha256:50fff349a031, Baum fef96653+dirty
```
