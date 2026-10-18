# Rundenbericht — feste Feldliste (§71.74, Leser in Runde 67)

**Commit:** ac83343e (Runde 66) → Commit dieser Runde folgt unten
**Zustand:** 4/8 Meßblöcke scheiterbar · 214 Blöcke · 7 Felder · 1/2 quittiert · R→F 1/letzte 1/Prüfer · 13 Regeln
**EXIT:** Selbsttest 0 · Hauptlauf 0
**offen:** 0 · **quittiert:** 1 · **frisch:** 1 (_self_test_prozent)
**Zahlen:** 214 Blöcke (213 + 1 Block Runde 68) · 4 scheiterbar / 8 Meßblöcke · 99 Prosazahlen aus 1872 Textzeilen (Quelle: `wc -l check_claude_md.py` = 8834) · 7 Felder (6 Trenner + 1) · 13 Regeln in `REGEL_PRUEFER`
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
