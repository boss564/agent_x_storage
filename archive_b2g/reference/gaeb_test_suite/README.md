# GAEB DA XML 3.3 Test Suite — Reference Files

Die Referenzdateien müssen von den offiziellen Quellen heruntergeladen werden.

## Download-Quellen

### 1. Schema-Dateien (.xsd) — Offizielle GAEB-Schemas

**Quelle:** https://www.gaeb.de/de/service/downloads/gaeb-datenaustausch/

Benötigte XSDs für die B2G-Pipeline:
- `GAEB_DA_XML_3.3_X83.xsd` — Angebotsaufforderung (Eingabe)
- `GAEB_DA_XML_3.3_X84.xsd` — Angebotsabgabe (Ausgabe)
- `GAEB_DA_XML_3.3_X86.xsd` — Auftragserteilung
- `GAEB_DA_XML_3.3_X89.xsd` — Rechnung

**Zielverzeichnis:** `archive_b2g/reference/gaeb_test_suite/schemas/`

### 2. BVBS-Prüfdateien — Offizielle Zertifizierungs-Testdateien

**Quelle:** https://www.bvbs.de/en/zertifizierungen/

| Datei | Phase | Zweck |
|-------|-------|-------|
| `BVBS_Pruefdatei GAEB DA XML 3.3 - Bauausfuehrung - V 04 04 2024.x83` | X83 | Referenz-Angebotsaufforderung |
| `BVBS_Pruefdatei GAEB DA XML 3.3 - Bauausfuehrung - V 11 06 2021.x84` | X84 | Referenz-Angebot (erwartetes Ergebnis) |

**Zielverzeichnis:**
- `.x83` → `archive_b2g/reference/gaeb_test_suite/x83_anfrage/`
- `.x84` → `archive_b2g/reference/gaeb_test_suite/x84_angebot/`

### 3. GAEB-Checker (Validierungstool)

**Quelle:** https://www.gaeb.de/de/service/downloads/gaeb-datenaustausch/

Der `GAEBXml-Checker 3.3` validiert XML-Dateien gegen das GAEB-Schema und prüft Pflichtfelder.

## Verzeichnisstruktur nach Download

```
archive_b2g/reference/gaeb_test_suite/
├── README.md                          # Diese Datei
├── schemas/
│   ├── GAEB_DA_XML_3.3_X83.xsd
│   ├── GAEB_DA_XML_3.3_X84.xsd
│   ├── GAEB_DA_XML_3.3_X86.xsd
│   └── GAEB_DA_XML_3.3_X89.xsd
├── x83_anfrage/
│   ├── BVBS_Pruefdatei_BA_2024.x83
│   └── *.x83                          # Weitere Test-X83
├── x84_angebot/
│   ├── BVBS_Pruefdatei_BA_2021.x84
│   └── *.x84                          # Weitere Test-X84
└── vhb_formblaetter/
    ├── VHB_221_EFB_Preis1.pdf         # VHB-221 Erfassungsformblatt
    └── VHB_222_EFB_Preis2.pdf         # VHB-222 Erfassungsformblatt
```

## Sofort-Test nach Download

```bash
# Nach dem Download der Dateien:
python3 scripts/test_gaeb_reference.py --mode all
```

Dieses Skript:
1. Lädt alle `.x83`-Dateien aus `x83_anfrage/`
2. Validiert sie gegen `schemas/GAEB_DA_XML_3.3_X83.xsd`
3. Parst jede Datei durch den `GAEBParserSubagent`
4. Generiert `.x84`-Angebote mit dem `GAEBX84PublisherSubagent`
5. Validiert die generierten X84 gegen `schemas/GAEB_DA_XML_3.3_X84.xsd`
6. Vergleicht generierte X84 mit Referenz-X84 (Preissummen, Struktur)
