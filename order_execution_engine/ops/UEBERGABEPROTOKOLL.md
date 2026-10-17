# Übergabeprotokoll — Entwurf (nicht unterschrieben)

> **Dies ist der Entwurf.** Die unterschriebene Fassung wird als
> `UEBERGABEPROTOKOLL-YYYY-MM-DD.md` **nach** dem Abnahmegespräch
> committet. Wer in vier Wochen wissen will, was entschieden wurde, darf
> nicht auf eine leere Vorlage stoßen — dann existiert das Protokoll nur
> auf Papier, und das ist die sechste stille Stelle.
>
> Drei Zustände, nicht zwei: `☐ ja` / `☐ nein` / `☐ nicht entschieden`.
> Zwei leere Kästchen sind kein Zustand, sie sind *nicht gelesen* — und
> sehen aus wie *bewusst offengelassen*.

Die Fragen, die keinen Fehler machen und deshalb keinen Termin haben.

| # | Frage | Zustand | entschieden von | Datum |
|---|-------|---------|-----------------|-------|
| E1 | **Deklarierte Lücke tragen?** Kriterium (1) prüft Vollständigkeit (`telemetry_rows == decision_seq-keyed(run_id>=7)`), **nicht** Attribuierung. `attributed` ist Beobachtung (heute 4/361, obere Schranke). Die Migration `telemetry.item_id` senkt sie für 34 Altzeilen auf 0. Nimmt der Abnehmer eine deklarierte Lücke (`legacy_unattributable: 34`, datiert) an — oder wird die Ehrlichkeit zurückgebaut, weil sie rot macht?<br>☐ ja &nbsp; ☐ nein &nbsp; ☐ nicht entschieden (Grund: ________________) | | | |
| E2 | **Vollständig attribuierender Run als eigener Fall** — Run 9 · 4 Claims · 4 Zeilen · `decision_seq` 1–4, `open_unmatched = 0`. 34 Entscheidungen, 26 ohne Order, 8 mit Order, alle 8 gepaart.<br>☐ ja &nbsp; ☐ nein &nbsp; ☐ nicht entschieden (Grund: ________________) | | | |
| E3 | **`absent_sentiment` bleibt Regel, kein Kriterium** — Zähler `0 von 327 im Topf` (502 echte Items, kein fehlendes Feld).<br>☐ ja &nbsp; ☐ nein &nbsp; ☐ nicht entschieden (Grund: ________________) | | | |
| E4 | **WARN-Schwelle statt Kriterium für `attributed`** — Migration sichtbar, Urteil bleibt grün.<br>☐ ja &nbsp; ☐ nein &nbsp; ☐ nicht entschieden (Grund: ________________) | | | |

## Warum E1 vor dem 20.10. gehört

Nach dem 20.10. wird die Frage im Betrieb entschieden, unter Zeitdruck,
und der Nicht-Entscheid entscheidet: die Antwort „ja" ist dann der
Default, weil niemand widerspricht. Solange nichts rot ist, ist die
Frage billig; danach ist sie teuer.

## Stand am 17.10.2026 (gemessen, nicht behauptet)

| Größe | Wert | Population |
|---|---|---|
| `attributed` | 4 | Run 9, obere Schranke (keine `item_id` im Ledger) |
| `unattributed` | 30 offen / 300 kumuliert | `dispatched_signals` im Fenster, N=361 |
| `discarded` | 327 | dispatched × discarded im Fenster (Discard-Tabelle: 393) |
| `traffic_only` | 0 | Rest ohne Claim und ohne Discard |
| `Σ` | 361 ✓ | |
| `source_unknown` | 0 von 361 | der alte `"book"`-Default hat nie gehandelt |
| `absent_sentiment` | 0 von 502 echten Items | Run-Marker ausgeschlossen; 827 Zeilen waren die falsche Menge |

## Laufende Beobachtung, nicht Entscheidung

- **Run-Längen:** Der Bestand ist blind von hinten nach vorn — `{1..4} ⊂
  {1..30}`. Das endet, sobald ein Run mehr Claims hat als sein Vorgänger.
  Dann ist `attributed` erstmals gegen den Skopierungsfehler prüfbar.
