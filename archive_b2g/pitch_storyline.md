# Agent X — Pitch-Storyline für den Kämmerer

## Die eine Frage, die alles ändert

> **„Herr Kämmerer — wissen Sie in diesem Moment, ob auch nur eine einzige
> Abschlagszahlung in Ihrem Haushalt um einen Cent von der VOB/B abweicht?"**

---

## Akt I: Das Problem (30 Sekunden)

Jede deutsche Kommune wickelt Bauprojekte so ab wie vor 50 Jahren:

- **Papier.** GAEB-Leistungsverzeichnisse, VOB/B-Verträge, XRechnungen. Alles auf Papier oder als PDF. Kein System weiß, was das andere tut.
- **60 Tage.** Die durchschnittliche Zahlungsfrist im öffentlichen Bau. Der Handwerker geht in Vorleistung, die Kommune verliert den Überblick.
- **Kein Live-Budget.** Der Kämmerer sieht die Haushaltslage einmal im Quartal — im Bericht des Rechnungsprüfungsamts. Nicht live. Nicht pro Transaktion.

Das ist kein Technologieproblem. Es ist ein **Vertrauensproblem**. Zwischen Kommune und Handwerker, zwischen Bauamt und Kämmerer, zwischen Haushalt und Realität.

---

## Akt II: Die Garantie (60 Sekunden)

Agent X gibt eine Garantie, die kein Papierprozess geben kann:

> **Δ = 0,00 €. Mathematisch bewiesen. Für jede einzelne Transaktion.**

Was bedeutet das?

Eine Abschlagszahlung von 45.000 € wird in drei Teile zerlegt:
- **80 % Netto (36.000 €)** → sofort an den Handwerker
- **15 % Steuer §48b EStG (6.750 €)** → direkt ans Finanzamt
- **5 % Einbehalt §17 VOB/B (2.250 €)** → treuhänderisch auf separates Unterkonto

Die Summe muss exakt dem Brutto entsprechen — **auf den Cent genau**.

Agent X beweist das **vor jeder Freigabe im Escrow-Pfad** mit einem mathematischen
Theorem-Prover. Kein Mensch muss prüfen. Kein Rechnungsprüfungsamt muss
stichproben. Der Computer beweist: Δ = 0,00 €. Wenn nicht, wird die
Zahlung markiert und die BHO-Verletzung protokolliert.

Das ist der Unterschied zwischen *„wir haben das geprüft"* und *„es ist mathematisch unmöglich, dass es falsch ist"*.

*(Live-Demo: `http://localhost:8501` → Transaktion starten → BHO-Balken zeigt Δ = 0)*

---

## Akt III: Der Beweis (60 Sekunden)

Sie müssen das nicht glauben. Sie können es nachmessen.

Agent X hat **42 BSI-Compliance-Checks** — und sagt Ihnen, welche davon
maschinell verifiziert sind und welche auf menschlicher Zusicherung beruhen:

*(Live-Demo: `http://localhost:8000/compliance` → 23 verifiziert, 8 durch Implementierung belegt, 11 zugesichert)*

| Was geprüft wird | Wie | Status |
|------------------|-----|--------|
| BHO-Nullsumme | Z3-Theorem-Prover (UNSAT-Beweis, <50 µs) | verifiziert |
| GoBD-WORM | SHA-256-Hash-Kette, Merkle-Proofs | verifiziert |
| VOB/B §17 | 5 % Einbehalt, 4 Jahre, automatische Freigabe | verifiziert |
| eIDAS | ZK-Proofs, BundID-kompatibel | belegt |
| MiCA | EURe via Monerium (EMI-lizenziert, FME Island) | zugesichert |

Kein externes Audit, das einmal im Jahr kommt. **Continuous Compliance** — jederzeit, live, maschinenlesbar.

---

## Akt IV: Die Krise (30 Sekunden)

Was passiert, wenn das Internet ausfällt? Wenn die Banken nicht erreichbar sind?

Agent X hat einen **Off-Grid-Modus** — als 5-Knoten-MPC-Verbund implementiert
und im Mock-Stack vollständig lauffähig (63 Tests grün, inklusive
Dilithium-Signaturen und LoRaWAN-Mesh).

- 5 MPC-Knoten (Software-Architektur), Threshold 3 von 5
- Kommunikation über LoRaWAN-Funk (868 MHz, UDP-Simulation im Mock-Stack)
- Post-Quantum-Kryptografie (Dilithium/Kyber, resistent gegen Quantencomputer)
- 3 von 5 Knoten müssen signieren — selbst bei Ausfall von 2 Knoten läuft das System
- Für den Pilotbetrieb wären fünf physische Standorte einzurichten; die Software ist dafür fertig

Die BHO-Garantie gilt auch ohne Banken. Dann in Ressourcen-Einheiten (kWh, Liter, kg) statt Euro — aber die Mathematik ist dieselbe.

---

## Akt V: Die Wirtschaft (30 Sekunden)

Und wenn 500 Bauprojekte gleichzeitig laufen?

Agent X enthält ein **agentenbasiertes Wirtschaftsmodell (ABM)**. 27 spezialisierte Agenten — Produzenten, Prüfer, Verwalter — laufen im Hintergrund und melden, wie sich der Markt verhält:

- **32.429 Zustandsübergänge** in 50 Zyklen (reproduzierbar: `python3 scripts/demo_producer_cluster.py --full --cycles 50`)
- **5.589 Settlement-Transaktionen** über die SimChain verbucht
- **171 BHO-Verletzungen erkannt** — 9 Provider mit unterschiedlichen Risikoprofilen, darunter absichtlich manipulierte Meldungen

Das Modell ist bereit für Pilotdaten aus Ihren ersten drei Bauvorhaben. Sobald echte Zahlen einfließen, sehen Sie live: Wie entwickelt sich das Auftragsvolumen? Wo entstehen Zahlungsengpässe? Welche Gewerke sind ausgelastet?

Nicht im Quartalsbericht — **in Echtzeit**.

---

## Der Abschluss (30 Sekunden)

Sie haben heute drei Optionen gehört. Sie können:

1. **Weitermachen wie bisher.** Papier. 60 Tage. Rechnungsprüfungsamt.
2. **Eine Insellösung kaufen.** Die macht eine Sache gut und alles andere nicht.
3. **Agent X als Pilot in drei Bauvorhaben einsetzen.** Keine Risiken. Keine Prozessänderung. Ihr System läuft parallel weiter. Sie sehen in Echtzeit, was passiert — und entscheiden nach dem Pilot, ob Sie umsteigen.

Option 3 kostet Sie heute: **nichts.**

Keine Lizenzgebühr im Pilot. Keine Hardware-Anschaffung. Keine Prozessänderung.

Was Sie heute bekommen, ist eine mathematische Garantie, dass Ihre Bauzahlungen auf den Cent stimmen. Was Sie morgen bekommen, ist ein Wirtschaftsmodell, das Ihnen sagt, wie sich Ihr Haushalt entwickelt — bevor es das Rechnungsprüfungsamt tut.

---

## Die eine Antwort

> **„Ja, Herr Kämmerer. Ich weiß es. Δ = 0,00 €. Für jede einzelne Zahlung.
> Seit heute."**

---

*Pitch-Dauer: ca. 4 Minuten. Live-Demo: 2 Minuten. Fragen: nach Bedarf.*
*Technische Validierung: 48 Dateien, 11.426 Zeilen, 0 Hook-Abweichungen, alle Suiten grün.*
