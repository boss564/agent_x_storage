# D40 — G1-content Messung (nach D38-Abnahme)

Stand: 2026-11-09 · HEAD-Basis: `f954060b` · Spec: `7f675193` (D34/D38)

## Gate-Formel (D34)

Pro Schicht ≥1 Positiv + ≥1 Negativ; Live-Producer Neu8 deckungsgleich.
Pipeline: `bewerte_achsenzeile` (Shape→Kern→Fremd→Dispatcher).

## Ergebnis

| Schicht | Fall | Verdict | Klasse / Grund |
|---|---|---|---|
| 1 Shape | POS Neu8 kurz∧envelope | **PASS** | ok → summe |
| 1 Shape | NEG kurz-ohne-envelope | **PASS** | SCHEMA_LUECKE (fehlt envelope) |
| 2 Kern | POS Kernkeys | **PASS** | SCHEMA_KERN_ALT5 ⊆ keys |
| 2 Kern | NEG fehlt WIEDERHOLUNG | **PASS** | SCHEMA_LUECKE |
| 3 Fremd | POS kein Fremdkey | **PASS** | ok |
| 3 Fremd | NEG Fremd-Key | **PASS** | FREMD_KEYS |
| 4 Disp | POS Summe | **PASS** | SUMME expand+contract |
| 4 Disp | POS Alias expand-only | **PASS** | ALIAS expand=True contract=False |
| 4 Disp | POS META meta-6 | **PASS** | META |
| 4 Disp | NEG WertRelation | **PASS** | WERT_RELATION_FEHLER |
| Live | Producer `achse()` Neu8 8 Keys | **PASS** | summe |

**D40: 10/10 Schichtfälle + Live PASS.** Keine xfail.

Hinweis: Neu8-Nullzeile (`uebersprungen=0=json+kurz+envelope`) klassifiziert als
**SUMME**, nicht META — Shape/Fremd-POS prüfen `ok` und Keys, nicht die META-Klasse.
