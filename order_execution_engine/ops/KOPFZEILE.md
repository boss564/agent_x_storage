# §A-ZZZZ — Kopfzeilen-Regel (Runde 56, korrigiert Runde 57)

**Ein Dokument kann nicht falsch sein. Deshalb kann es nicht gefunden
werden — und deshalb steht hier kein Wert.**

## Der Fall (Runde 56)

Die Kopfzeile lautete `37/37 Selbsttests, Akte grün` — bei
`7 gemessen · 1 nicht gemessen`. Zwei Artefakte, ein Urteil. Das Urteil
hat zwei Zustände, die Messung hat drei. Dieselbe Form wie „gemittelt"
in Runde 44: eine Zusammenfassung, die den einzigen nicht-grünen
Feldeintrag nicht abbilden kann, sagt immer grün.

## Was Runde 56 falsch machte

Runde 56 hat darauf mit einer **Datei** geantwortet. Diese Datei trug
einen Wert („8 gemessen"), der Bericht daraus einen anderen („3
gemessen") — **unter demselben Feldnamen.** Die Meldung, die
Zusammenfassungen ohne Prüfung beklagte, war selbst eine
Zusammenfassung ohne Prüfung.

Behoben nicht durch einen dritten Text, sondern durch
`_kopfzeile_errors()`: die Kopfzeile wird **gegen den letzten
Messblock gerechnet**, nicht gegen die Hand geschrieben.

## Das Format (prüfbar, wertfrei)

```
Selbsttest <a>/<b> · Akte <N> gemessen · <U> unvollständig · <K> keine · Commit <sha>
```

| Feld | Herkunft |
|---|---|
| `Selbsttest a/b` | `--self-test` |
| `Akte N gemessen` | Felder 1–2 der `kopfzeile:`-Zeile des letzten Messblocks |
| `U unvollständig` | Feld 2 derselben Zeile; `>0` **erzwingt** das Wort in der Zeile |
| `K keine` | `_falte_gruen` hat `raise` geworfen — **nicht** aus dem Block ablesbar |
| `Commit sha` | `git rev-parse --short HEAD` |

## Was `_kopfzeile_errors()` prüft — und was nicht

Geprüft:

- Das Format nennt alle drei Felder namentlich.
- Der letzte Messblock trägt eine lesbare `kopfzeile:`-Zeile.
- `U > 0` ⇒ die Zeile nennt `unvollstaendig`. **Das ist der Fehler,
  den Runde 56 begangen hat**, und er wird jetzt gefunden.
- Die Prüfer-Fassung im Block wird gegen `_pruefer_hash()` gehalten und
  der Abstand benannt, wenn sie abweicht.

**Nicht geprüft:** `N von M`. Der Block trägt die Zahl `N` und die Zahl
`U`, nicht den Umfang `M` in derselben Zeile. Solange er das nicht tut,
ist `8 gemessen` mit `8 von 8` und `8 von 9` verträglich — eine Zahl,
die zwei Zustände deckt. Das ist die nächste Lücke, und sie steht hier
statt in einem Folgeblock.

## Warum das keine Berichts-Kosmetik ist

Dieselbe Zeile in drei Fassungen:

- `_falte_gruen([])` → `True`: die leere Menge gilt als geprüft
  (**Runde 56, `raise`**)
- `if root is not None`: der fehlende Baum gilt als anwesend
  (**Runde 54, `calibration_card(root)`**)
- „Akte grün" bei `1 nicht gemessen`: der reduzierte Bezugsraum gilt
  als vollständig (**diese Regel, jetzt gerechnet**)

Eine Bedingung, die wahr ist, wenn der Gegenstand fehlt. Drei Fassungen,
drei `raise`-Äquivalente — bei der dritten ist es ein Prüfer statt einer
Vorschrift.

## Bücher

- `_falte_gruen([])` → `raise`: **erledigt** (Runde 56)
- `_akt_block_mismatch(bloecke, karte)` injizierbar: **erledigt**
- `_auswahl_fehler` als eigenes Fixture: **erledigt** (Runde 57, 24/26)
- Kopfzeile gegen den Block gerechnet: **erledigt** (Runde 57)
- `N von M` in der Blockzeile: **offen**
- Bypass `2853ae9b`: `git notes`, nicht Commit-Umschreibung
