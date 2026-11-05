# SP-844 — Befund: Konsument 6/7 vorbestehend, Ursache Schema-Lücke auf `exit=3`

**Stand:** 2026-11-05T18:42Z · **HEAD:** `ff050c2f` · **Art:** Befund, **nicht durch diese Runde verursacht**

## 1. Ist-Zustand

Der Pre-Commit-Check meldet im Bericht `Konsument 6/7`. Reproduzierbar isoliert:

```
$ python3 scripts/mock_ingestion.py
FAIL  fehlt -> ungeprueft  exit=3 aktion=zustellen  marke=UNGEPRUEFT  alarm=True
6/7 Konsumenten-Faelle gruen
```

## 2. Vorbestehendheit (Beleg)

- `git status --porcelain scripts/mock_ingestion.py scripts/einwurf_waechter.py` → **leer**.
  Keine der beiden Dateien ist in dieser Runde angefasst.
- Der Zähler ist eine **gemessene Zahl** (`(\d+)/(\d+) Konsumenten-Faelle gruen`
  aus dem Ausgang von `mock_ingestion.py`), keine getippte.

## 3. Ursache (Paste)

| Seite | Zeile | Aussage |
|---|---|---|
| Mock (Erwartung) | `mock_ingestion.py:119` | `fehlend = [k for k in ("Paare", …)]` — verlangt `Paare` im Schema |
| Mock (Prüfung) | `mock_ingestion.py:130` | `gut = k["messung"].get("Paare") == "1"` |
| Wächter (Exit 3) | `einwurf_waechter.py:517` + `558` | `STROM UNLESBAR;grund=…` + `achse(0,0,0[,0])` + `return 3` |
| Wächter (Aktion) | — | Bei Exit 3 fällt der Wächter **vor** der regulären Aktionszeile (Z. 547) heraus — es gibt keine `aktion=`-Ausgabe für diesen Pfad |

Die Meldung ist exakt: `Schema-Luecke auf exit=3: ['Paare']`.
Der Mock verlangt ein Feld, das der Exit-3-Pfad nicht liefert.

## 4. Einordnung

- **Nicht** durch O3 verursacht, nicht durch SP-841, nicht durch den Inventory-Sync.
- **Blockiert das Gate nicht** — der Bericht weist `1 Befund(e)` aus (nur Form),
  nicht `6/7` als Fehler. `6/7` steht im Bericht als **Zahl mit Nenner**, nicht als
  Grün-Behauptung.
- **Offen als eigener Befund.** Eine Schema-Änderung am Wächter (Exit-3-Pfad liefert
  `Paare=0` + `aktion=zustellen` + `marke=UNGEPRUEFT`) ist eine **Kanal-Vertragsänderung**
  und gehört nicht in den O3-Commit.

## 5. Folge

SP-844 bleibt offen. Die Zahl `6/7` darf **nicht** als „alles grün bis auf einen
Formfehler" gelesen werden — sie ist ein **offener Konsumenten-Fall**, der einen
Schema-Defekt im Exit-3-Pfad belegt.
