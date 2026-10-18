# Rundenbericht — feste Feldliste (§71.74, Leser in Runde 67)

**Commit:** `8b3a902b` (Runde 69) → Commit dieser Runde unten
**Zustand:** 4/8 Meßblöcke scheiterbar · 0 Blöcke seit 213 · Deckel 5 ⇒ unter · 213 Blöcke · 4 : 213 Gegenläufe · 13 : 13 Regeln gedeckt · 1/2 quittiert · R→F 0/med 1/n 5/letzte 0/Prüfer · 9 Felder
**EXIT:** Selbsttest 0 · Hauptlauf 0
**offen:** 0 · **quittiert:** 1 · **frisch:** 1 (_self_test_prozent)
**Zahlen:** 214 ist **verzogen** — 213 war richtig, Runde 68 addierte den Block ein zweites Mal · 4 scheiterbar / 8 Meßblöcke · 13 : 13 Regeln mit erzwungenem `fail`-Zweig · 104 Prosazahlen aus 1979 Textzeilen (Quelle: `wc -l scripts/check_claude_md.py` = 9214, **eine Datei**) · R→F min 0 / Median 1 / n 5
**Nicht getan:** die 12 offenen Kontexte · Whitelist für Zeilennummern/Daten · `FRISCH`-Versetzung
**Deckel-Entscheidung (Runde 71):** `_self_test_prozent` bleibt **quittiert und gedeckelt**, bewusst. Grund: der Prüfer über den Prüfern liest jeden Vergleich eines berechneten Werts gegen ein Literal als Selbstbezug — fünfzehn Umbauten haben daran nichts geändert. Der Deckel ist 2, der Test läuft (§A-ZZZZ73), und der nächste echte Fehler erscheint als `FAIL`, weil ein `FAIL` nur noch heißt: hier ist etwas offen. **Deploy-Zweig `deploy-safe-snapshot` trägt diesen Deckel bewusst** — „deploy-safe" heißt hier „mit bekanntem, gezähltem Deckel", nicht „ohne offene Position".

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
