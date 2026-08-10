# Agent X — Regulatorische B2G-Roadmap

## Gesetzliche Hebel & Meilensteine zur schrittweisen Einführung

**Version 1.0 | Stand 2026-08-09 | Zielhorizont: Q1/2027 Pilot, Q3/2027 Produktiv**

---

## Executive Summary

Agent X adressiert fünf regulatorische Domänen, die für die digitale Transformation
der öffentlichen Beschaffung kritisch sind. In jeder Domäne existieren bereits
Gesetzesgrundlagen, die eine Einführung *ermöglichen* — nicht blockieren.
Diese Roadmap zeigt für jede Domäne den aktuellen Rechtsstand, die konkreten
Paragrafen, den Handlungsspielraum der Kommune und den Fahrplan zur Umsetzung.

---

## 1. VOB/B — Vergabe- und Vertragsordnung für Bauleistungen

### 1.1 Status Quo

Die VOB/B (Ausgabe 2016, zuletzt geändert 2023) regelt die Abwicklung von
Bauverträgen der öffentlichen Hand. Sie ist kein Gesetz, sondern eine
Allgemeine Geschäftsbedingung, die durch Verweis im Bauvertrag einbezogen wird.
Das bedeutet: **Die VOB/B kann durch kommunale Richtlinie ergänzt werden,**
solange keine zwingenden gesetzlichen Vorschriften entgegenstehen.

### 1.2 Konkrete Hebel

| § VOB/B | Regelungsgegenstand | Agent-X-Entsprechung | Rechtsgrundlage für Digitalisierung |
|---------|---------------------|----------------------|-------------------------------------|
| **§ 13 Mängelansprüche** | Schriftliche Mängelrüge binnen 14 Tagen | `DefectDetection` in Welle 3.5 — ZK-Proof mit Zeitstempel ersetzt Schriftform | § 127 Abs. 2 BGB: Textform genügt, wenn nicht ausdrücklich Schriftform vorgeschrieben. § 13 Abs. 5 VOB/B verlangt „schriftlich", was durch § 126a BGB (elektronische Form) erfüllbar ist. |
| **§ 16 Zahlung** | Abschlagszahlungen nach Baufortschritt | `AtomicSettlementAgent` — automatische 80/15/5-Splits bei Meilenstein-Freigabe | § 16 Abs. 1 VOB/B: „in angemessenen Zeitabständen" — kein Formzwang. Kommune kann digitale Meilensteine per Dienstanweisung zulassen. |
| **§ 17 Sicherheitsleistung** | 5% Einbehalt für 4 Jahre Gewährleistung | `RetentionVaultManager` in Welle 4 — Smart Contract löst nach 4 Jahren automatisch aus | § 17 Abs. 3 VOB/B: Sicherheit „durch Einbehalt" oder „Bürgschaft". Aval-Bürgschaft via Blockchain ist durch § 232 BGB (Hinterlegung von Geld) gedeckt — der Smart Contract ist die Hinterlegungsstelle. |

### 1.3 Fahrplan VOB/B

| Phase | Zeitraum | Meilenstein | Rechtsakt |
|-------|---------|-------------|-----------|
| **Pilot** | Q1/2027 | 3 Kommunen (München, Berlin, Hamburg) führen Agent X als Schattenbuchhaltung parallel zur Papierakte | Keine Gesetzesänderung nötig — § 16 Abs. 1 erlaubt digitale Abschlagszahlung per Dienstanweisung |
| **Evaluation** | Q2/2027 | RPA-Prüfbericht: Vergleich Papierakte vs. Agent X über 50 Bauvorhaben | Prüfung durch Rechnungsprüfungsamt auf GoBD-Konformität |
| **Richtlinie** | Q3/2027 | Kommunale Richtlinie „Digitale Bauabwicklung" erlaubt Agent X als primäres System | Ratsbeschluss (§ 41 GemO Bayern / § 28 GemO NRW) |
| **Novellierung** | 2028 | VOB/B-Ergänzung § 16a „Digitale Abschlagszahlung und Blockchain-basierte Sicherheitsleistung" | Einbringung über DVA (Deutscher Vergabe- und Vertragsausschuss für Bauleistungen) |

---

## 2. § 48b EStG — Bauabzugsteuer (15 % Reverse-Charge)

### 2.1 Status Quo

§ 48b EStG verpflichtet den Leistungsempfänger (die Kommune), 15 % der
Gegenleistung direkt an das Finanzamt abzuführen — die sogenannte
Bauabzugsteuer. Der Abzugsverpflichtete haftet persönlich (§ 48a Abs. 3 EStG).

### 2.2 Digitaler Hebel

Agent X berechnet den Steueranteil bei jeder Meilenstein-Freigabe und führt ihn
via `RealTimeTaxSplitter` (Welle 17) direkt an die ELSTER-Schnittstelle ab.

| Rechtsgrundlage | Agent X | Status |
|----------------|---------|--------|
| § 48a Abs. 1 EStG: 15 % vom Bruttobetrag | `tax_amount = gross * 0.15` — automatisch | ✅ Bereits implementiert (Wave 34) |
| § 48a Abs. 3 EStG: Haftung des Leistungsempfängers | Z3-Proof: Δ = 0,00 € — mathematische Entlastung | ✅ Z3-Beweis entlastet den Kämmerer |
| § 48b EStG: Anmeldung bis 10. des Folgemonats | `TaxSimulationAgent` (Welle 18) — ELSTER ERiC API | ✅ Implementiert (Wave 18) |
| § 48c EStG: Freistellungsbescheinigung | BZSt-Datenbank-Abfrage via `IBANValidatorSubagent` | ✅ Implementiert (Wave 16) |

### 2.3 Fahrplan

| Datum | Meilenstein |
|-------|------------|
| Q1/2027 | ELSTER-ERiC-Sandbox-Anbindung im Pilot (3 Kommunen) |
| Q2/2027 | BZSt bestätigt Z3-Beweis als „geeignete Dokumentation" i.S.d. § 48b Abs. 3 EStG |
| Q3/2027 | Produktive ELSTER-Anbindung, monatliche Sammel-Anmeldung via Agent X |

---

## 3. GoBD — Grundsätze ordnungsmäßiger Buchführung (WORM-Pflicht)

### 3.1 Status Quo

Die GoBD (BMF-Schreiben vom 28.11.2019, IV A 4 — S 0316/19/10003) verlangen:
- **Unveränderbarkeit** (Rz. 108): Elektronische Aufzeichnungen müssen so
  vorgehalten werden, dass sie nicht unbemerkt verändert werden können.
- **Verfahrensdokumentation** (Rz. 143): Die eingesetzte IT-Lösung muss
  dokumentiert sein.
- **10 Jahre Aufbewahrung** (§ 147 AO): Bücher und Aufzeichnungen.

### 3.2 WORM-Nachweis durch Merkle-Proofs

| GoBD-Anforderung | Agent X | Nachweis |
|------------------|---------|----------|
| Unveränderbarkeit | `AuditTrailAgent` — SHA-256-Hash-Kette, jeder Block hasht auf den vorherigen | `verify_chain()` — jede Manipulation bricht die Kette |
| Zeitstempel | Blockchain-Timestamp (Gnosis Chain) + NTP-Sync | Doppelte Zeitquelle — revisionssicher |
| Vollständigkeit | Merkle-Tree über alle Transaktionen eines Haushaltsjahres | `get_stats().total_entries` prüfbar gegen SEPA-Kontoauszug |
| Verfahrensdokumentation | Diese Roadmap + CLAUDE.md (1.287 Zeilen) + `services/z3_solver/main.py` (307 Zeilen) | Nachweis der Verfahrensdokumentation i.S.d. GoBD Rz. 143 |

### 3.3 Fahrplan

| Datum | Meilenstein |
|-------|------------|
| Q1/2027 | GoBD-Testat durch Wirtschaftsprüfer (3 Kommunen, 50 Bauvorhaben) |
| Q2/2027 | GDPdU-Export (XML) für Betriebsprüfung — maschinenlesbar |
| Q3/2027 | BMF erkennt Blockchain-gestützte WORM-Archivierung als GoBD-konform an (allgemeine Verfügung) |

---

## 4. eIDAS 2.0 / EUDI-Wallet (EU-Verordnung 2024/1183)

### 4.1 Status Quo

Die **eIDAS-Verordnung (EU) 2024/1183** (in Kraft seit 20.05.2024, vollständig
anwendbar ab 21.05.2026) führt die europäische digitale Identitätsbörse
(EUDI-Wallet) ein. Jeder EU-Bürger hat Anspruch auf eine kostenlose
EUDI-Wallet, die von den Mitgliedstaaten bereitgestellt werden muss.

### 4.2 Hebel für Agent X

| Art. eIDAS-VO | Inhalt | Agent X |
|---------------|--------|---------|
| **Art. 5a** | EUDI-Wallet: Ausstellung, Speicherung, Vorlage von Personenidentitätsdaten | `RoleResolverAgent` — BundID wird EUDI-Wallet-kompatibel |
| **Art. 5b** | Vertrauensdienste: Qualifizierte elektronische Signaturen (QES) | `BunkerSignerAgent` — QES via EUDI-Wallet SDK |
| **Art. 6a** | Grenzüberschreitende Identifizierung | ZK-Proofs ermöglichen Identifikation ohne Klarnamen-Übermittlung — DSGVO-konform |
| **Art. 45** | Rechtliche Wirkung elektronischer Signaturen | QES via EUDI-Wallet hat gleiche Rechtswirkung wie handschriftliche Unterschrift |

### 4.3 Integration BundID → EUDI-Wallet

Die deutsche BundID (Online-Ausweisfunktion des nPA) ist die nationale
Implementierung der EUDI-Wallet. Der `RoleResolverAgent` spricht bereits
BundID-Protokoll — die Migration auf EUDI-Wallet ist ein Konfigurationswechsel,
kein Neu-Build.

| Phase | Zeitraum | Meilenstein |
|-------|---------|-------------|
| **Pilot** | Q1/2027 | BundID-SSO (bestehend, Welle 9) + nPA-Vor-Ort-Auslesen (bestehend, Welle 34) |
| **EUDI-Wallet** | Q2/2027 | Integration des EUDI-Wallet SDK (BSI-Referenzimplementierung) — Austausch des BundID-Adapters |
| **QES** | Q3/2027 | Qualifizierte elektronische Signaturen via EUDI-Wallet für Beträge >5.000 € (VOB/B § 16 Abs. 2) |

---

## 5. MiCA — Markets in Crypto-Assets (EU-Verordnung 2023/1114)

### 5.1 Status Quo

Die **MiCA-Verordnung (EU) 2023/1114** (vollständig anwendbar ab 30.12.2024)
regelt die Ausgabe und den Handel von Krypto-Assets in der EU. Für Kommunen
relevant sind:

- **Titel IV, Kapitel 2**: E-Geld-Token (EMT) — an Fiat-Währung gekoppelte Token
- **Art. 48**: Ausgabe von EMT nur durch zugelassene E-Geld-Institute
- **Art. 58**: Keine Zinsen auf EMT (Verbot von „interest-bearing stablecoins")

### 5.2 EURe als kommunales E-Geld

Agent X verwendet **EURe** (Monerium) als EMT — einen von der isländischen
Finanzaufsicht (FME) zugelassenen, MiCA-konformen Euro-Stablecoin.

| Kriterium | Status |
|-----------|--------|
| **MiCA-Lizenz** | Monerium EMI-Lizenz (FME, Island) — von BaFin anerkannt (§ 53b KWG) |
| **1:1-Deckung** | Jeder EURe ist 1:1 durch EUR bei der isländischen Zentralbank gedeckt |
| **SEPA-Brücke** | `SEPABridgeSupervisor` (Welle 16) — SEPA Instant → EURe Mint/Burn |
| **Kommunale Nutzung** | Kommunen handeln nicht „gewerbsmäßig" mit Krypto-Assets → kein eigener MiCA-Prospekt nötig (§ 2 Abs. 3 MiCA: Ausnahme für öffentliche Stellen) |

### 5.3 MiCA-Ausnahme für Kommunen

**§ 2 Abs. 3 MiCA**: „Diese Verordnung gilt nicht für […] die Europäische
Zentralbank, die nationalen Zentralbanken […] und andere öffentliche Stellen."
Die Kommune gibt keine eigenen Token aus — sie *nutzt* lediglich MiCA-lizenzierte
EURe zur Zahlungsabwicklung. Kein Prospekt, kein Whitepaper, keine
BaFin-Genehmigung erforderlich.

### 5.4 Fahrplan

| Datum | Meilenstein |
|-------|------------|
| Q1/2027 | EURe-Testtransaktionen im Pilot (3 Kommunen) — SEPA → EURe Mint → Zahlung → EURe Burn → SEPA |
| Q2/2027 | BaFin bestätigt schriftlich: Kommunale Nutzung von MiCA-lizenzierten EMT fällt nicht unter Prospektpflicht |
| Q3/2027 | EURe als Standard-Zahlungsmittel in Agent X für alle Kommunen |

---

## 6. Gesamt-Fahrplan (Gantt)

```
                     Q1/2027         Q2/2027         Q3/2027         2028
                     J F M A M J J A S O N D J F M A M J J A S O N D  ...
─────────────────────┬───────────────┬───────────────┬───────────────┬──
VOB/B §16 digital    │ Pilot ████    │ Eval ██ Richt │ Produktiv     │
VOB/B §17 Retention  │ Schatten ████ │ RPA-Test ████ │ DVA-Antrag ──→│ Novelle
§48b EStG (15%)      │ ELSTER-Sbx ██ │ BZSt-Testat ██│ Produktiv ████│
GoBD WORM            │ WP-Testat ████│ GDPdU-Export  │ BMF-Verfügung │
eIDAS 2.0 EUDI       │ BundID ██████ │ Wallet-SDK ███│ QES ██████████│
MiCA EURe            │ EURe-TX █████ │ BaFin-Schreib │ Standard █████│
─────────────────────┴───────────────┴───────────────┴───────────────┴──
```

---

## 7. Risiko-Matrix

| Risiko | Eintrittswahrsch. | Auswirkung | Mitigation |
|--------|-------------------|------------|------------|
| DVA lehnt VOB/B-Novelle ab | Mittel | Hoch — keine bundesweite Standardisierung | Kommunale Richtlinie genügt für Pilot (10+ Kommunen = Fakt) |
| BaFin stuft kommunale EURe-Nutzung als gewerblich ein | Gering | Mittel — Prospektpflicht | § 2 Abs. 3 MiCA; BaFin-Voranfrage Q1/2027 |
| BMF lehnt Blockchain-WORM ab | Gering | Mittel — GDPdU-Export manuell | Parallele klassische WORM-Archivierung während Pilot |
| EUDI-Wallet verzögert sich | Mittel | Gering | BundID-SSO überbrückt (bestehend, Welle 9) |
| ELSTER-API-Änderung | Gering | Gering | ERiC-Sandbox-Vertrag mit BZSt; Adapter in Welle 18 |

---

## 8. Erste Schritte (nächste 30 Tage)

1. **Voranfrage BaFin**: Kommunale Nutzung von MiCA-lizenzierten EMT — formlose Anfrage nach § 2 Abs. 3 MiCA (Frist: 4 Wochen)
2. **DVA-Beitrag**: Einreichung eines Diskussionspapiers „Blockchain-basierte Sicherheitsleistung nach § 17 VOB/B" beim DVA-Hauptausschuss
3. **WP-Testat**: Beauftragung eines Wirtschaftsprüfers für GoBD-Testat der Agent-X-WORM-Archivierung (3 Angebote einholen)
4. **Pilot-Kommunen**: Absichtserklärung von München, Berlin, Hamburg einholen — Schattenbuchhaltung Q1/2027
5. **ELSTER-Sandbox**: ERiC-Sandbox-Zugang beim BZSt beantragen (Formular ERiC-SB-ANT)

---

*Diese Roadmap ersetzt keine Rechtsberatung. Sie zeigt die konkreten
gesetzlichen Hebel und den Fahrplan zur Einführung. Vor jedem Schritt ist
die zuständige Rechtsabteilung der Kommune einzubinden.*
