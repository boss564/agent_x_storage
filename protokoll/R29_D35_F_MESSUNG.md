# D35 — F-1a/b, F-3 Messung (HEAD+Neu8+Exit-2)

Stand: 2026-11-09 · HEAD: `7f675193` · Baum: R+C1+C2+D33+D37+D34-Spec

## Mapping (kanonisch aus `test_konstanten.py`)

Die offenen Labels **F-1a / F-1b / F-3** werden an die P7-`LESESTAT_ACHSE_PAARE`
gebunden (Gate-Doku L2: „LESESTAT_ACHSE_PAARE + F-* Konstanten“):

| Label | Fixture-Name | Soll |
|---|---|---|
| **F-1a** | `F-Summe-Paar` | json=1,kurz=2,envelope=3 → uebersprungen=6 · Klasse SUMME |
| **F-1b** | `F-Alias-unmoeglich-nach-Flip` | 1/1/1 → Summe=3 · Klasse SUMME (kein Alias nach Flip) |
| **F-3** | `F-Null-Paar` | 0/0/0 → uebersprungen=0 · Klasse SUMME |

Ergänzend (Dispatcher-F-*, nicht Labels F-1/F-3, aber mitgemessen):
`F-Alias`, `F-Summe`, `F-Null`, `F-meta`, `F-WertFehler`, V4 Fremd, D1 meta-6.

## Lauf

```
python3 scripts/test_konstanten.py   → 21/21 grün, EXIT=0
python3 scripts/test_konformitaet.py → 5/5 grün (+1 BOOK skip), EXIT=0
python3 scripts/mock_ingestion.py    → 7/7 grün, EXIT=0
```

### F-1a/b/F-3 Zeilen (Auszug)

```
ok   LESESTAT-Paar F-Summe-Paar                 {... uebersprungen: 6}
ok   LESESTAT-Paar F-Alias-unmoeglich-nach-Flip {... uebersprungen: 3}
ok   LESESTAT-Paar F-Null-Paar                  {... uebersprungen: 0}
ok   Pipeline F-Alias          → alias expand=True contract=False
ok   Pipeline F-Summe          → summe expand=True contract=True
ok   Pipeline F-Null           → summe expand=True contract=True
```

## Verdict D35

| Check | Status |
|---|---|
| F-1a | **PASS** |
| F-1b | **PASS** |
| F-3 | **PASS** |
| Suite-Kontext Konstanten/Konformität/Mock | **PASS** (21/21, 5/5, 7/7) |

Keine Vermischung mit D34-Messung (G1-content bleibt bis D38-Abnahme gesperrt).
