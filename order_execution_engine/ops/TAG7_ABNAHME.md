# Tag-7-Abnahme — Shadow Execution Engine

**Abnahme: Montag, 20.10.2025, 10:00** · Berichtstermin: Montag, 03.11.2025

Stand: 17.10.2026. Dieses Dokument ist **vorab** festgeschrieben. Wird später
etwas anders gelesen, gilt die hier stehende Nummer, nicht eine neue Lesart.

**Grundlage (Code, gegen den abgenommen wird):** `01fdbb1d`
(Reconciliation, Join-Schlüssel, zwei Achsen) · `bd241b1a` (dieses Dokument).
Das Kriterium beurteilt genau diesen Stand.

## 0. Termin

**Tag 7 = Montag, 20.10.2025, 10:00.** Auflösung per Befehl, **Ausgaben
eingefügt, nicht eingetippt** (`date -j -f "%Y-%m-%d" <datum> "+%A"`,
17.10.2026, 17:27):

| Datum | Ist-Ausgabe | Rolle |
|---|---|---|
| **2025-10-20** | `Monday` | **Tag 7 — Abnahme** (Code, entscheidbar) |
| 2025-11-03 | `Monday` | **Berichtstermin Marktbeobachtung** |
| 2025-11-01 | `Saturday` | **kein Termin** — Wochenende, niemand zuständig |
| 2026-10-20 | `Tuesday` | **nicht** der Abnahmetag (Jahreszahl-Falle) |

> Historische Notiz: Fassung `4fc93054` nannte „03.11." als Dienstag und
> `bd241b1a` nannte „01.11.2026" als Samstag. Beides waren Etiketten:
> 2025-11-03 ist ein **Montag**, 2026-11-01 ein **Sonntag**. Damit sind in
> dieser Akte **vier** Kalenderangaben nachträglich aufgelöst worden, keine
> davon beim ersten Schreiben. Die verbleibende Fehlerform: drei Zeilen waren
> abgeschrieben, die vierte gerechnet — ein aufgelöstes Etikett, das
> transkribiert statt eingefügt wird, ist wieder ein Etikett.

Das Datum ist **unbedingt**, nicht bedingt auf §5.1: Variante C ist
synthetisch und hängt weder an Run 8/9 noch am Markt noch an
`integrate_news_index`. §5.1 entscheidet eine Zeile im Bericht
(„Basis: Run 8 / Run 8+9"), nicht das Urteil.

**Basis-Zeile (Code je Run, nicht nur Run-Nummern):**

| Gegenstand | Commit / Hash | Rolle |
|---|---|---|
| Run 8 + 9 (Daten) | `5c5bc364` · Runner `92338139e8…` | **erzeugt** von diesem Stand |
| Gate (Urteil) | **`146b4be4`** · `preflight_check.py` `3dad796a…` | **neu**, beurteilt post hoc |
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

**Frist: Montag, 20.10.2025, 10:00 — unbedingt.** Die frühere Fassung trug
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

**Abnahmeprotokoll Montag, 20.10.2025, 10:00** — jede Zeile hat Befehl,
**erwartete Ausgabe** und **Verdikt bei Abweichung**.

**Regel für `NICHT ENTSCHEIDBAR`:** zulässig **nur** in Zeilen 5 und 6 —
dort hängt die Wahrheit an Daten, die noch nicht existieren (Markt,
Symbolindex). Bei allen deterministischen Zeilen (0–4) ist eine Abweichung
**NICHT BESTANDEN**. „Nicht entscheidbar" wäre dort kein Befund, sondern ein
Freifahrtschein für die einzige Zeile, die den Termin selbst trägt.

| # | Befehl | Erwartete Ausgabe | Verdikt bei Abweichung |
|---|---|---|---|
| 0 | `date -j -f "%Y-%m-%d" 2025-10-20 "+%A"` | `Monday` (**Ist, eingefügt**) | **NICHT BESTANDEN** |
| 1 | `pytest order_execution_engine/tests/` | `157 passed` | **NICHT BESTANDEN** |
| 2a | `pytest -k test_c1_positive` | `1 passed, 2 deselected`; Fill im Spread | **NICHT BESTANDEN** |
| 2b | `pytest -k test_c2_negative` | `1 passed, 2 deselected`; `INVALID_PRICE`, keine Metrik | **NICHT BESTANDEN** |
| 3 | `pytest -k test_c3_replay_does_not_touch` | `1 passed, 2 deselected`; Mess-DB 0 Diff | **NICHT BESTANDEN** |
| 4 | `gate_snapshot` | `join_is_one_to_one: True` über `(run_id, decision_seq)` | **NICHT BESTANDEN** |
| 5 | `gate_snapshot(min_run_id=8)` | `historical: RED (run 8, unattributed=4)`; Ausgangsachse **34**; `current: GREEN` | **NICHT ENTSCHEIDBAR** (Abweichung benennen, nicht glätten) |
| 6 | §5.1 + §5.4, dieses Dokument | Zeitstempel, Sweep- und Import-Graph-Ausgabe vorhanden | **NICHT ENTSCHEIDBAR** |

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
| 10:00 | Zeilen 0–6 | `Monday`, `157 passed`, `historical: RED`, Wurzel leer |
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
20.10. 157 Tests, leere Wurzel und unveränderten Prozess liest und sie für
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

**Der Prüfer datiert sich selbst.** Seit dieser Runde trägt jede Ausgabe den
Blob-Hash der urteilenden Fassung (`git hash-object`, 40 Hex SHA-1 — derselbe
Wert wie in `git rev-parse <commit>:<path>`). Ein Verdikt ohne Prüfer-Hash
nennt den Run, aber nicht den Richter: derselbe Befehl auf denselben Daten
könnte nach dem nächsten Werkzeug-Commit anders lauten, und das Protokoll
merkt es nicht. Ohne git fällt die Zeile auf SHA-256 zurück und **sagt das**
(`sha256 (git unavailable)`), statt eine falsche Form vorzutäuschen.

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

## 8. Tests dieser Runde

| Datei | Zeugen |
|---|---|
| `tests/test_fill_replay.py` | C-Positiv, C-Negativ, C-Isolation (3) |
| `tests/test_telemetry_reconciliation.py` | Vollständigkeit, `<`→Gleichheit, zwei Achsen, `decision_seq`-Kollision, Zeile ohne Key, Neustart je Run, `item_id` ≠ Join-Schlüssel, historical-rot-blockiert-nicht, current-rot-blockiert |

Suite: **157 passed** auf `01fdbb1d`-Stand. **Grün heißt „die Tests laufen",
nicht „die Tests prüfen das Richtige"** — die erste Fassung dieser Runde war
grün über einem falschen Join-Schlüssel. Deshalb sind die Negativkontrollen
(38 vs. 34, `decision_seq`-Kollision, current-RED) ausdrücklich Teil der Suite.
