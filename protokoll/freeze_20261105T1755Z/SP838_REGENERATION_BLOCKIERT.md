# SP-838 — Regeneration des Messblocks: Warum sie nicht mechanisch ist

**Stand:** 2026-11-05T18:40Z · **HEAD:** `ff050c2f`
**Status:** **BLOCKIERT — nicht regenerierbar ohne Entscheidung.** Kein Bypass, keine Änderung.

## Die drei Messungen

### M1 — Die Karte ist deterministisch

Zwei Läufe `calibration_card()` bytegleich. Die Regeneration ist damit **prinzipiell**
routinierbar — nicht mehr ein Einmal-Stempel. Das ist die gute Nachricht und der
Grund, warum B77 (nachhaltig) erreichbar ist.

### M2 — Der falsche Block ist nicht der letzte

`TAG7_ABNAHME.md` enthält **14** Kalibrierungsblöcke. Der letzte (`@355622`, Z. 7828,
`af77393000f8`) ist der, den der Prüfer liest. **Er ist ein historischer Block** —
`total=0 chain_total=0` und eine `Zustand:`-Zeile mit `Deckel 5`/`210 Blöcke`, die zu
einer früheren Runde gehört.

Sein Inhalt gegen den heutigen Baum:

| Feld | Block (zitiert) | Heute gemessen | Befund |
|---|---|---|---|
| `total` | 0 | 2 | Zitat veraltet |
| `chain_total` | 0 | 2 | Zitat veraltet |
| `reported` | 0 | 2 | Zitat veraltet |
| `Tests ohne Skript` | 0 | 1 | Zitat veraltet |
| `Inventare` | 0 | 1 | Zitat veraltet |
| `Prüfer` | `af77393000f8` | `3b7240aaeaba` | Zitat veraltet |
| `Karte` | `745fc89a2fc9` | `894f987f3c63` | Zitat veraltet |
| `Zustand` | `4/8 · Deckel 5 · 210 Blöcke` | `4/8 · Deckel 3000 · 2789 Code-Blöcke` | **andere Größe** |

### M3 — Kein anderer Block passt entweder (Karten-Test)

Der naheliegende Kandidat war Block 10 (`@335756`, `1ff37da95fac`) — vollständig,
mit `kopfzeile`, `Karte` und `Bezug`. Der Karten-Test `_auswahl_fehler` gegen die
**heutige** Karte liefert:

```
Akte-Block: chain_total 0 zitiert, 2 gemessen
Akte-Block: unclassified -2 zitiert, 0 gemessen
```

`unclassified = -2` ist eine **negative Zahl von Unklassifizierten** — in Block 10
selbst. Also nicht nur „veraltet", sondern strukturell unmöglich.

## Der Widerspruch, der die Entscheidung erzwingt

`_akt_block_mismatch` vergleicht **nicht** die `Zustand:`-Zeile — nur Zahlen und die
`Bezug`-Felder `root` und `CLAUDE.md sha256` (Baum-Hash ausdrücklich nicht).

Das heißt:

- **Eine echte** `calibration_card()` **würde** den Prüfer grün machen — der Zähler
  steht heute bei **0 Befunden** (vorher 2: `Harness-Zaun` und `Kopfzeile`).
- Aber sie würde eine `Zustand:`-Zeile (`Deckel 3000`, `2789 Code-Blöcke`,
  `seit 213 Protokoll`) in die Akte schreiben, die **keinem historischen Block
  entspricht** und `Deckel 5 ⇒ unter` durch `Deckel 3000 ⇒ unter` ersetzt.

**Zwei Ziele kollidieren:**

| Ziel | Verlangt |
|---|---|
| Gate grün (§1, SP-838) | Block = heutige `calibration_card()` |
| Akte unverfälscht (§6, „erst messen, dann buchen") | Kein Block, der Zahlen behauptet, die kein Lauf erzeugte |

Eine `Zustand:`-Zeile ist **keine Messung**, sondern ein Aggregat mit Deckeln und
Rundenzählern, die in einer historischen Runde gesetzt wurden. Sie nachträglich auf
heutige Werte zu stempeln ist **Berichts-Kosmetik** — genau das, was `KOPFZEILE.md`
in §„Warum das keine Berichts-Kosmetik ist" für erledigt erklärt.

## Optionen (nicht ausgeführt)

| # | Option | Folge | Risiko |
|---|---|---|---|
| A | Block durch `calibration_card()` ersetzen, anhängen | Gate grün, Verified-Commit möglich | `Zustand:`-Zeile behauptet Deckel/Rundenzustand, der nicht gemessen ist |
| B | `Zustand:`-Zeile als „offen" prüfen: `_kopfzeile_errors` erweitern, sodass der Drift **kein** Befund ist, sondern eine benannte Ausnahme | Gate grün ohne Akte-Eingriff | Erweiterung von Prüfer-Logik = selbst ein Eingriff am Gate |
| C | Akte an der Stelle auf **heutigen** Stand mit **neuem** Block fortschreiben (append, alter Block bleibt) + Regression | Gate grün, Historie erhalten | Braucht eine Runde und Buchführung, nicht 5 Minuten |
| D | Gate bleibt rot, SP-838 offen, kein dritter Bypass | Ehrlich, aber blockiert alles | Kein Verified-Commit, kein Push |

**C ist die einzige Variante, die beide Ziele hält** — aber sie ist eine
**Rundenarbeit am Dokument**, nicht ein Regenerationsskript. Das gehört gesagt,
bevor jemand „Regeneration" als Einzeiler verbucht.

## Was ich nicht getan habe

- Keinen Block geschrieben, keinen Commit, keinen Bypass.
- Die Zähl-Korrektur (`protokoll/bypass_zaehlung.txt`) liegt **uncommitted** im
  Arbeitsbaum — wie in SP-839 verlangt (Commit erst nach grünem Gate).
- Der Arbeitsbaum ist damit wieder **nicht leer**: das ist beabsichtigt und
  dokumentiert, kein Unfall.
