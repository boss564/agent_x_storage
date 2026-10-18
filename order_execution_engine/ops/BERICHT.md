# Rundenbericht — feste Feldliste (§71.74, Leser in Runde 67)

**Commit:** ac83343e (Runde 66) → Commit dieser Runde folgt unten
**Zustand:** 4/8 Meßblöcke scheiterbar · 212 Blöcke · 7 Felder · 1/2 quittiert · R→F 1/letzte 1/Prüfer
**EXIT:** Selbsttest 0 · Hauptlauf 0
**offen:** 0 · **quittiert:** 1 (`_self_test_prozent`) · **frisch:** 1 (`Akte-Block`)
**Zahlen:** 213 Blöcke (212 + 1 Block Runde 67) · 4 scheiterbar / 8 Meßblöcke · 99 Prosazahlen aus 1848 Textzeilen · 7 Felder (6 Trenner + 1) · FRISCH 1/Deckel 2
**Nicht getan:** die 12 offenen Kontexte · Whitelist für Zeilennummern/Daten · `_self_test_prozent` behoben

## Runde 65 war rot

`SELFTEST_EXIT=1` · `MAIN_EXIT=0`. Der einzige Befund: `Akte-Block weicht vom Messlauf ab`.
Wahr nach jedem Commit — der Block beschreibt die Akte nicht mehr, sobald sie wächst.
Das ist sein Zweck, aber es machte den Selbsttest konstant rot.

## Runde 66 verletzte §71.74

Fünf Felder fehlten: Zustand, Blockzahl, MAIN_EXIT, offen, „Nicht getan".
Der Bericht war vollständig lesbar und jede Aussage wahr — die zwei roten Felder fehlten.
§71.74 hatte keinen Leser.

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
