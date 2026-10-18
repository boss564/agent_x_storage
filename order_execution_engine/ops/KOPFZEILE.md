# §A-ZZZ — Kopfzeilen-Regel (Runde 56)

**Ein Befund aus Runde 55, der nicht im Code saß, sondern in meinem Bericht.**

## Der Fall

Die Kopfzeile lautete:

> `37/37 Selbsttests, Akte grün, Commit 2853ae9b`

Der Hook-Lauf derselben Runde sagte:

> `7 gemessen · 1 nicht gemessen — unvollstaendig (kein .git/)`

Zwei Artefakte, ein Urteil. Das Urteil hat zwei Zustände, die Messung hat
drei. Dieselbe Form wie „gemittelt" in Runde 44: eine Zusammenfassung, die
den einzigen nicht-grünen Feldeintrag nicht abbilden kann, sagt immer grün.

**Der nächste Leser liest die Kopfzeile zuerst.** Darum ist die Kopfzeile
kein Stil, sondern der Ort, an dem die Dreiwerigkeit verloren geht.

## Die Regel

Die Kopfzeile trägt **alle drei** Zahlen, immer, in der Reihenfolge:

```
Selbsttest <a>/<b> · Akte <N> gemessen · <U> unvollständig · <K> keine · Commit <sha>
```

| Feld | Herkunft |
|---|---|
| `Selbsttest a/b` | `--self-test` |
| `Akte N gemessen` | `tally_line` des letzten Laufs |
| `U unvollständig` | `abweichungen is None` → 1, sonst 0 |
| `K keine` | `_falte_gruen` hat `ValueError` geworfen |
| `Commit sha` | `git rev-parse --short HEAD` |

**Verboten** in der Kopfzeile:

- „Akte grün" ohne die drei Zahlen (mehrdeutig, nicht falsifizierbar)
- Weglassen eines Feldes, weil es `0` ist (die Null ist die Nachricht)
- Summieren von Selbsttest und Hook-Lauf zu einem Wort („grün")

## Warum das keine Berichts-Kosmetik ist

Das Urteil „grün" ruft dieselbe Klasse Fehler hervor wie `_falte_gruen([])`
und `if root is not None`:

- `_falte_gruen([])` → `True`: die leere Menge gilt als geprüft
- `if root is not None` → der fehlende Baum gilt als anwesend
- „Akte grün" bei `1 nicht gemessen` → der reduzierte Bezugsraum gilt als vollständig

Drei Fassungen derselben Zeile: **eine Bedingung, die wahr ist, wenn der
Gegenstand fehlt.** Runde 56 hat die erste mit `raise` geschlossen, die
zweite in Runde 54 mit `calibration_card(root)`. Die dritte ist diese
Regel.

## Die Gegenprobe

Die Regel wird erst gültig, wenn **ein** Lauf mit `N>0, U>0` im Bericht
steht und die Kopfzeile das zeigt. Der Lauf vom 18.10. (Commit `2853ae9b`)
war genau dieser Fall — nur steht es im Nachhinein in diesem Block, nicht
in seiner Kopfzeile.

## Bücher

- `_falte_gruen([])` → `raise`: **erledigt** (Runde 56)
- `_akt_block_mismatch(bloecke, karte)` injizierbar: **erledigt** (Runde 56)
- Kopfzeile dreiwertig: **diese Regel**
- Bypass am Commit vermerken: `2853ae9b` bleibt ohne Vermerk — ein
  Commit, der einen reduzierten Bezugsraum hatte, nachträglich zu
  interpretieren wäre eine Geschichte, kein Protokoll. Der Vermerk steht
  hier und im Folgeblock.
