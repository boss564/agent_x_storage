# BVBS Test Suite — Official GAEB DA XML 3.3 Certification Files

Die folgenden Prüfdateien werden vom BVBS (Bundesverband Bausoftware e.V.)
für die Zertifizierung von Softwareprodukten nach GAEB DA XML 3.3 herausgegeben.
Sie enthalten maximale Stellenanzahlen, Sonderzeichen, Grafiken und alle Positionstypen.

## Download

**Quelle:** https://www.bvbs.de/en/zertifizierungen/

### Benötigte Dateien

| Datei | Phase | Zweck |
|-------|-------|-------|
| `BVBS_Pruefdatei GAEB DA XML 3.3 - Bauausfuehrung - V 04 04 2024.x83` | X83 | Referenz-Angebotsaufforderung mit allen Positionstypen |
| `BVBS_Pruefdatei GAEB DA XML 3.3 - Bauausfuehrung - V 11 06 2021.x84` | X84 | Referenz-Angebot mit Einheitspreisen (Soll-Werte) |

> **Hinweis:** Die BVBS-Webseite ist auf Englisch. Die Prüfdateien sind unter
> "Prüfdatei" im jeweiligen Zertifizierungsbereich (AVA, Bauausführung) verlinkt.

### Besonderheiten der Prüfdatei

- **Maximale Stellenanzahlen:** Summen bis 12.345.678,012 €
- **Grafiken im Langtext:** Base64-eingebettete Bilder
- **Alle Positionstypen:** Normal-, Bedarfs-, Index-, Alternativ-, Zulagepositionen
- **Hierarchie:** Mehrstufige OZ/Titel/Gruppen-Struktur
- **Nebenangebote:** Positionen mit `OZ-Art=4` (optional)
- **Mengenermittlung:** X31-Referenz für Aufmaß

## Ablage nach Download

```
archive_b2g/reference/bvbs_test_suite/
├── README.md
├── BVBS_Pruefdatei_BA_2024.x83    # ← hier ablegen
└── BVBS_Pruefdatei_BA_2021.x84    # ← hier ablegen
```

## Test ausführen

```bash
# Nach dem Download der BVBS-Dateien:
python3 scripts/test_gaeb_reference.py --mode all

# Nur XSD-Validierung der BVBS-Dateien:
python3 scripts/test_gaeb_reference.py --mode validate
```

## Vergleichskriterien (gegen Referenz-X84)

| Kriterium | Toleranz | Prüfmethode |
|-----------|----------|-------------|
| Projektsumme | ±0,01 € | `TotalAmount`-Vergleich |
| Anzahl Positionen | exakt | `Item`-Element-Zählung |
| Positionssummen | ±0,01 € | `TP`-Vergleich pro ItemID |
| Hierarchiestufen | exakt | OZ-Struktur-Tiefe |
| Währung | EUR | `Currency`-Attribut |
| DP-Phase | 84 | `DP`-Element |
| Version | 3.3 | `Version`-Element |
