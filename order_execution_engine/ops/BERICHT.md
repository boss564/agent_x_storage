# BERICHT — Runde 71b

# BERICHT — Runde 74

**Commit:** Arbeitsstand Runde 74
**Zustand:** 4/8 Meßblöcke scheiterbar · seit 213 Protokoll (Einheitenwechsel) · Deckel 3000 ⇒ unter · 2525 Code-Blöcke · 234 Protokoll im Fenster · 4/13 Regeln mit Gegenlauf · 13 : 13 Regeln gedeckt · 1/2 quittiert · R→F 0/med 1/n 5/letzte 0/Prüfer · 10 Felder
**EXIT:** Selbsttest 0 · Hauptlauf 0
**offen:** 0 · **quittiert:** 1 · **frisch:** 1 (_self_test_prozent)
**Zahlen:** Nenner = 2525 `def`/`class` in `scripts/` **ohne** den Prüfer (233 Definitionen draußen) · 224 Protokollblöcke im Fenster, Rotation ab 240 · 282 ohne Bereich: **174 CODE_UNBEWERTET / 92 TEST_INSTRUMENT / 16 CONFIG** (VENDORED als vierte Klasse, greift heute nicht — `lib/` liegt außerhalb) · R→F min 0 / Median 1 / n 5
**Nicht getan:** die 12 offenen Kontexte · `FRISCH`-Versetzung · die CODE_UNBEWERTET einzeln zugewiesen
**Deckel-Entscheidung:** `_self_test_prozent` bleibt quittiert. `DECKEL_CODE` gilt `def`/`class` in `scripts/` **ohne** den Prüfer — die Waage ist nicht gedeckelt. `deploy-safe` = **`deploy-gate` grün** (`needs: [pruefer, contract-compile, unit-tests]`), nicht mehr ein Zweigname ohne Job; `make telemetry-deploy-hetzner` liest `offen` aus dieser Datei vor dem ersten `ssh` — kein Literal im Makefile.

## Runde 72 — Auslöser → Job

Der Beweis-Run 39142099847 bewies den **Start**, nicht den **Lauf**: F8 lag
in `formal-invariants`, das an `openzeppelin-contracts-upgradeable` starb.
Fünftes Glied: `needs: []`-Job `pruefer`, nur Stdlib, mit
Entkopplungs-Beweis. Der fand sofort die Repo-Importe `akte_guard` und
`check_fixtures` — beide stdlib, also keine Fremdabhängigkeit.

Die Waage stand im selben Raum: `_zaehle_codebloecke()` zählt jetzt
Code-Blöcke **ohne** den Prüfer. Sonst wüchse der Nenner mit jeder neuen
Regel, und jeder Gegenlauf sähe wie Stillstand aus.

`AUSGENOMMEN`-Einträge werden auf Existenz geprüft (zweite Richtung).
Die 283 sind in drei Klassen getrennt; `openzeppelin` und `Makefile`
stehen nicht mehr im selben Topf. **Der Prüfer fing sich selbst:** das
neue Probe-Skript erhöhte die Bilanz von 282 auf 283.

Protokoll: Rotation statt Löschung (`--rotate`), getestet im tmpdir ohne
Zeilenverlust. `DECKEL_CODE = 3000` gilt Code, nicht der Akte.

**Nächster Schritt:** Zähler 4 → 13 (je Regel ein erzwungener `fail`-Zweig).

**Commit:** `557fb2cd` (Runde 71b) · Arbeitsstand dieser Runde
**Zustand:** 4/8 Meßblöcke scheiterbar · seit 213 Protokoll (Einheitenwechsel) · Deckel 3000 ⇒ unter · 2525 Code-Blöcke · 234 Protokoll im Fenster · 4/13 Regeln mit Gegenlauf · 13 : 13 Regeln gedeckt · 1/2 quittiert · R→F 0/med 1/n 5/letzte 0/Prüfer · 10 Felder
**EXIT:** Selbsttest 0 · Hauptlauf 0
**offen:** 0 · **quittiert:** 1 · **frisch:** 1 (_self_test_prozent)
**Zahlen:** 216 Protokollblöcke (Name sagt jetzt, was gezählt wird) · 4 scheiterbar / 8 · 13 : 13 Regeln mit erzwungenem `fail`-Zweig · 282 Dateien unter `scripts/`/`.github/workflows/` **ohne Bereich, benannt** · R→F min 0 / Median 1 / n 5
**Nicht getan:** die 12 offenen Kontexte · Whitelist für Zeilennummern/Daten · `FRISCH`-Versetzung · 282 Dateien einzeln zugewiesen
**Deckel-Entscheidung:** `_self_test_prozent` bleibt quittiert und gedeckelt (unverändert). `deploy-safe` heißt: mit bekanntem, gezähltem Deckel — jetzt **auch im Deploy-Log gedruckt**.

## Runde 71b — der Auslöser als Prüfer

Die Wache war gebaut, verkabelt, `continue-on-error: false` — und kein Auslöser
nannte `scripts/check_claude_md.py`. `scripts/test_*.py` matcht den Namen nicht,
und `branches: [main]` schloß den Zweig aus. **Der Path-Filter war
branch-unabhängig:** auch auf `main` feuerte nichts, wenn nur der Prüfer sich
änderte. Gelegentliche grüne Läufe (wenn `tests/` im selben Commit lag) haben fünf
Wochen lang Deckung vorgetäuscht.

§A-ZZZZ82 schließt das vierte Glied: Name → `def` → Aufruf → **Lauf → Auslöser**.

**Der Beweis ist ein Lauf:** Push `557fb2cd` → Run 39142099847, Zweig
`deploy-safe-snapshot`, erstmals seit fünf Wochen. `failure` — aber nicht wegen des
Prüfers: fehlendes `openzeppelin-contracts-upgradeable` (Compilation),
`--timeout=60` ohne `pytest-timeout` (Unit). Wave 33 grün.

**§A-ZZZZ81b, ehrlich:** drei Versuche. 283 Einzelbefunde = Rauschen. Klasse `"/"`
als Abdeckung = **Gegenlauf blieb grün**, Prüfer tot. Jetzt: **282 Dateien benannt,
Zuwachs ⇒ rot** (`touch scripts/Zz_probe2.py` verifiziert).

**§A-ZZZZ81c:** `Blöcke` → `Protokollblöcke`. `4 : 216` heißt jetzt: vier
Gegenläufe auf 216 Absätze Bericht — nicht auf Deckung.

## Offen nach dieser Runde (CI)

1. `formal-invariants` → F8 startet nie, weil die Compilation an fehlenden
   Submodulen scheitert. **Die Wache feuert, ihr Job nicht.**
2. `pytest-timeout` fehlt in `requirements` des Unit-Jobs.
3. `openzeppelin-contracts-upgradeable` fehlt im Checkout.


# Rundenbericht — feste Feldliste (§71.74, Leser in Runde 67)

## Runde 65 war rot

`SELFTEST_EXIT=1` · `MAIN_EXIT=0`. Der einzige Befund: `Akte-Block weicht vom Messlauf ab`.
Wahr nach jedem Commit — der Block beschreibt die Akte nicht mehr, sobald sie wächst.
Das ist sein Zweck, aber es machte den Selbsttest konstant rot.

## Runde 66 verletzte §71.74

Fünf Felder fehlten: Zustand, Blockzahl, MAIN_EXIT, offen, „Nicht getan".
Der Bericht war vollständig lesbar und jede Aussage wahr — die zwei roten Felder fehlten.
§71.74 hatte keinen Leser.

## Runde 69 war rot, und zwar sechsmal

Sechs Felder wörtlich, und die Zeile sagte `7 Felder`. `git blame` sagte zu
den vier Globals `3ea986c1` — derselbe Commit wie die Regel. `R→F = 0`.
`.selftest-exit` fehlte ⇒ Crash statt FAIL. `REGEL_PRUEFER` löste gegen `def`
auf und fand einen Toten, den niemand gerufen hatte.

## Was Runde 69 gebaut hat

- **`7 Felder` wird gezählt.** `len(ZUSTAND_FELDER)` steht an der Stelle, an
  der die Zeile gerendert wird; `pruefe_zustandszeile` liest die Feldzahl
  gegen `len(teile)`. Handeintrag ⇒ rot (Gegenlauf im Selbsttest).
- **`4 : 213 Gegenläufe` ist zurück** — das Verhältnis war das aussagekräftigste
  Feld, und es fehlte.
- **`R→F` aus `git blame`.** `reparatur_zu_fund()` nennt den Commit der
  Globals und zählt den Abstand. Ergebnis: `0`, nachweisbar. Runde 68s `1`
  war geführt, nicht gemessen.
- **Der Gleichheitsleser liest jetzt die Berichts-Zeile.** Er war nie tot —
  er las die Kartenzeile. Die Berichtszeile wurde stehen gelassen, während
  der Bericht „0 Befunde" meldete.
- **`.selftest-exit` fehlt ⇒ rot, nicht `unbekannt`.** Gegenlauf ausgeführt:
  Datei weg ⇒ `MAIN_EXIT=1` mit `Bericht: kein Selbsttest-Stand (rot)`.
- **`REGEL_PRUEFER` prüft `Call`, nicht `def`.** Erster Fund: `_self_test_prozent`
  war definiert und nie gerufen, seit Runde 63. Jetzt in der Kette.
- **Scope benannt:** `wc -l scripts/check_claude_md.py` — eine Datei.

## Runde 70 — die Blockzahl berichtigt, und zwar laut

Runde 68 schrieb `214 Blöcke (213 + 1 Block Runde 68)`, Runde 69 maß `213`.
Beide Zeilen waren in sich stimmig — der neue Block war in den 213 schon
enthalten, die `+ 1` war eine **zweite Addition derselben Einheit**.
Runde 69 hätte das nennen müssen und sagte „alles grün". Das ist die
Buchung, die diese Runde einlöst: **213 ist richtig, 214 war doppelt
gezählt, und der Rechenweg ist ab jetzt gespeichert** (`.blockstand`).

**Was Runde 70 gebaut hat:**

- **13 Gegenläufe, einer je Regel** (`GEGENLAUF_JE_REGEL`), jeder erzwingt
  den `fail`-Zweig. Ergebnis: **13 : 13 Regeln gedeckt** — als eigenes
  Feld in der Zustandszeile, weil `4 : 213` die Frage nicht beantwortet.
- **Zwei Gegenläufe waren sofort rot** — §A-ZZZZ59 (ein fehlendes Feld
  ging durch, weil nur die Zahl geprüft wurde) und §A-ZZZZ63
  (`pruefe_deckung` existierte nicht). Beide behoben, jetzt grün.
- **`R→F 0/med 1/n 5/letzte 0/Prüfer`** — der Rekord mit Nenner. Median 1
  ist die ehrliche Zahl: zweimal `0`, dazwischen neun und vier Runden.
- **`3 Blöcke seit …`** kommt aus `.blockstand`, nicht aus einer Erinnerung.
- **Zwei Zustandszeilen werden gegeneinander geprüft** (Blockzahl), nicht
  nur je für sich.

## Was diese Datei ist

Der Bericht als **Datei mit festem Kopf**, geprüft von `scripts/check_claude_md.py`
(`pruefe_bericht`). Fehlt ein Feld ⇒ `EXIT ≠ 0`. Ein Feld, das man weglassen kann,
ist die Definition von „nicht gemessen".

## Runde 67 — der Bericht hat einen Leser

`§71.74` war ein Absatz; `pruefe_bericht` ist sein Leser. Das Feld `Nicht getan`
entfernt ⇒ `MAIN_EXIT=1` (gemessen, nicht behauptet). `FRISCH` bekam Deckel 2 und
einen Gegenlauf: es feuert nur, wenn die Akte existiert und nicht leer ist —
fehlt sie, ist der Block nicht „veraltet", sondern unprüfbar, und das ist rot.
`Prosa: nicht gemessen` ist aus der Hauptlauf-Ausgangszeile raus: eine Wache, die
in einem Container mit einer Quittung läuft, hat reduzierte Autorität.

## §71.77 — keine Regel ohne Leser im selben Commit

Von jetzt an: wer eine Regel bucht, bucht ihren Prüfer. `ZUSTAND_FELDER`
(Runde 64) ist der eine Fall, in dem beides gleichzeitig kam — der Leser fand
sofort seinen Autor. Ziel ist `R→F 0`, nicht `< 1`: `0` heißt „beim Schreiben
geprüft", nicht „schneller gefunden".

## Runde 68 — Übereinstimmung statt Anwesenheit, und §71.77 prüft sich selbst

**`EXIT` ist eingesetzt, nicht geschrieben.** Runde 67 prüfte, *ob* die Felder da
sind — ein Handeintrag `EXIT 0` in einer roten Runde ging durch. Jetzt schreibt
`ersetze_bericht` die Zeile aus `.selftest-exit`, und `pruefe_bericht(text, werte)`
vergleicht gegen dieselbe Quelle. Drei Gegenläufe, in-process ausgeführt:
eingesetzt ⇒ grün; Handeintrag `Selbsttest 1` gegen Bericht `0` ⇒ rot (beide
Felder); `offen: unbekannt` ⇒ rot.

**`§71.77` ist der erste Eintrag seiner eigenen Tabelle.** `REGEL_PRUEFER` bildet
13 Regeln auf Prüfernamen ab, und `pruefe_regeltabelle` löst jeden Namen gegen
den AST auf — ein Name, der auf kein `def` zeigt, ist Deckung ohne Gegenstand.
Gegenlauf: `pruefe_regeltabelle('def x(): pass')` meldet alle 13. Nur so ist
`R→F` zählbar: eine Regel mit aufgelöstem Leser zählt 0.

**`FRISCH` ist weiter gedeckelt, nicht versetzt.** Deckel 2 ist eine Bandage,
das steht hier und nicht in einem Kommentar. Die nachhaltige Lösung — Block beim
Commit erzeugen — ist **nicht** gemacht; sie braucht den ausgenommenen Meßbereich,
sonst entsteht der ±1-Fall ein zweites Mal.

**Die Metaklasse ist in `BERICHT.md` gewandert.** Kein Prüfer liest die Zahlen
*in* den Feldern. `Prosa` läuft im Selbsttest, `BERICHT.md` im Hauptlauf — beides
zusammen deckt die Datei nicht. Offen.

**Metazahl mit Werkzeug:** `1872 Textzeilen (Quelle: wc -l check_claude_md.py =
8834)` — die Kette endet in einem Befehl, nicht in einer Zahl.
