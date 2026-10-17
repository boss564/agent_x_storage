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
| 9 | §5.4f–§5.4u | eine `pyc`, Schwelle beidseitig, `etime`, Blob↔Commit, `delivered` datiert, `DERIVED` definiert, `INVALID_PRICE` aufgelöst | **NICHT BESTANDEN** |

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
