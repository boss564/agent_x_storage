# Übergabeprotokoll Tag 7 — offene Entscheidungen

Die Fragen, die keinen Fehler machen und deshalb keinen Termin haben.
Jede Zeile: **ein Feld, zwei Zustände, ein Datum.** Ausgefüllt wird am
Tag der Übergabe, nicht vorher — aber die Zeile muss da sein, sonst wird
sie am 20.10. mit „läuft doch" beantwortet.

| # | Frage | Zustand (ja / nein) | entschieden von | Datum |
|---|-------|---------------------|-----------------|-------|
| E1 | **Deklarierte Lücke tragen?** Kriterium (1) prüft Vollständigkeit (`telemetry_rows == decision_seq-keyed`), **nicht** Attribuierung. `attributed` ist Beobachtung (heute 4/361). Die Migration `telemetry.item_id` senkt sie für 34 Altzeilen auf 0. Nimmt der Abnehmer eine deklarierte Lücke (`legacy_unattributable: 34`, datiert) an — oder wird die Ehrlichkeit zurückgebaut, weil sie rot macht? | ☐ ja ☐ nein | | |
| E2 | **Vollständig attribuierender Run als eigener Fall** — Run 9 · 4 Claims · 4 Zeilen · `decision_seq` 1–4, `open_unmatched = 0`. 34 Entscheidungen, 26 ohne Order, 8 mit Order, alle 8 gepaart. | ☐ ja ☐ nein | | |
| E3 | **`absent_sentiment` bleibt Regel, kein Kriterium** — Zähler `0 von 327 im Topf` (502 echte Items, kein fehlendes Feld). | ☐ ja ☐ nein | | |
| E4 | **WARN-Schwelle statt Kriterium für `attributed`** — Migration sichtbar, Urteil bleibt grün. | ☐ ja ☐ nein | | |

## Warum E1 vor dem 20.10. gehört

Nach dem 20.10. wird die Frage im Betrieb entschieden, unter Zeitdruck,
und der Nicht-Entscheid entscheidet: die Antwort „ja" ist dann der
Default, weil niemand widerspricht. Solange nichts rot ist, ist die
Frage billig; danach ist sie teuer.

## Stand am 17.10.2026

- `attributed = 4` — **obere Schranke**, nicht Zählung (keine `item_id`
  im Ledger). Steht im Urteil, nicht nur in der Akte.
- `unattributed = 30` (offener Run) / 300 (kumuliert) — das Urteil nennt
  beide, die Zahl zuerst, die das Kriterium prüft.
- `source_unknown = 0` — der alte `"book"`-Default hat nie gehandelt.
- `absent_sentiment = 0` — die Regel greift nie, weil das Feld immer kommt.
- Migration `telemetry.item_id`: angekündigt, **nicht** für den 20.10.
