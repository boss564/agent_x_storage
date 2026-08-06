# ADR-008: Zustandsmaschine des VOB_Shadow_Escrow.sol

**Datum:** 2026-08-06
**Status:** Akzeptiert (Pilot) / Überarbeitung empfohlen (Produktion)
**Autor:** Oliver Mueller, Claude (Audit)

---

## Kontext

Der `VOB_Shadow_Escrow` Smart Contract (Wave 18, Shadow Contract Pilot) implementiert
eine VOB/B-konforme Bauabwicklung als parallele Schattenbuchhaltung. Die initiale
Zustandsmaschine hatte zwei Dead Ends, die im Pilotbetrieb tolerierbar sind,
im Echtbetrieb aber zu eingesperrten Geldern führen können.

### Dead End 1: `completeMilestone` nur durch Client

Das ursprüngliche `onlyOwner` auf `completeMilestone()` gab allein dem Bauherrn
die Kontrolle über die Leistungsbestätigung. Verweigert der Client die Bestätigung
— aus Trägheit, Boshaftigkeit oder technischem Defekt — kann der Contractor
erbrachte Leistung nicht abrechnen. `releaseMilestone()` benötigt `isCompleted = true`,
das Tor davor öffnet nur der Client.

### Dead End 2b: `releaseRetention` nur durch Client

`releaseRetention` war `onlyOwner` — nur der Bauherr konnte den Sicherheitseinbehalt
(5 % der Bausumme, §17 VOB/B) nach der Abnahme freigeben. Schweigt der Bauherr
nach Ablauf der Verjährungsfrist (§13 VOB/B: 4 Jahre für Bauwerke), ist das Geld
dauerhaft im Contract eingeschlossen. Kein Timeout, kein Auditor-Pfad.

Dies ist die heikelste Stelle des Contracts: §17 VOB/B gibt dem Auftragnehmer
nach Ablauf der Verjährungsfrist einen **gesetzlichen Anspruch** auf Rückgabe der
Sicherheit. Ein Contract, der diesen Anspruch technisch nicht abbildet, weicht
vom Vertragsrecht ab, das er nachbilden soll.

### Dead End 2 (alt): `closeProject()` ohne Rücksicht auf offene Posten

Das ursprüngliche `closeProject()` setzte `isActive = false` ohne Prüfung, ob
noch Meilensteine offen, nicht released oder VAT/Retention unverteilt sind.
Danach revertieren alle Mutationen (`completeMilestone`, `releaseMilestone`,
`releaseRetention`). Funds in VAT + Retention + ausstehenden Meilensteinen
wären **permanent eingesperrt** — ohne `reopenProject()`.

---

## Entscheidung

### Für den Piloten (aktueller Stand)

Keine Änderung. Die Risiken sind im **rechtlich risikofreien Parallelbetrieb**
tolerierbar, weil:

- Der echte Zahlungsweg über die traditionelle VOB/B-Abwicklung läuft
- Der Shadow Contract protokolliert nur und hält kein echtes Geld
- Ein Audit des realen Projekts würde Abweichungen sofort aufdecken

### Für den Echtbetrieb (implementiert, aktiv per `isActive = true`)

**Fix 1: `completeMilestone` — Drei-Parteien-Autorisierung**

```solidity
// Client: jederzeit
// Auditor (RPA/Wirtschaftsprüfer): jederzeit, als neutraler Dritter
// Contractor: nach 14-Tage-Timeout ohne Client-Bestätigung
bool isContractorWithTimeout = msg.sender == project.contractor
    && block.timestamp >= m.createdAt + 14 days;
```

Der 14-Tage-Timeout entspricht der Frist aus §13 VOB/B (Mängelrüge). Die Wahl
derselben Frist ist beabsichtigt: Wenn der Client 14 Tage nach Leistungserbringung
keine Mängel gerügt hat, darf der Contractor den Meilenstein selbst als erbracht
markieren.

**Fix 2: `closeProject()` mit Milestone-Vollständigkeitscheck + `reopenProject()`**

```solidity
function closeProject() external onlyOwner {
    // Alle Meilensteine müssen completed und released sein
    for (uint i = 0; i < milestoneIds.length; i++) {
        require(milestones[milestoneIds[i]].isCompleted);
        require(milestones[milestoneIds[i]].releaseableAmount == 0);
    }
    project.isActive = false;
}

function reopenProject() external {
    require(msg.sender == project.auditor);  // Nur neutraler Dritter
    project.isActive = true;
}
```

`reopenProject()` ist bewusst **nicht** `onlyOwner` — der Auditor als neutrale Partei
kann einen versehentlichen `closeProject()` korrigieren. Der Client allein hat diese
Macht nicht, um Missbrauch zu verhindern.

**Fix 3: `releaseRetention` — Drei-Parteien-Autorisierung mit Verjährungs-Timeout**

```solidity
uint256 constant WARRANTY_PERIOD = 4 * 365 days;  // VOB/B §13

function releaseRetention(uint256 _amount) external {
    // Client: jederzeit
    // Auditor: jederzeit, als neutraler Dritter
    // Contractor: nach Ablauf der Verjährungsfrist ab Abnahme
    bool isContractorAfterWarranty = msg.sender == project.contractor
        && project.acceptedAt > 0
        && block.timestamp >= project.acceptedAt + WARRANTY_PERIOD;
}
```

`project.acceptedAt` wird in `closeProject()` gesetzt — die Abnahme markiert den
Beginn der Verjährungsfrist. Nach 4 Jahren kann der Contractor seinen Einbehalt
auch ohne Client-Zustimmung abrufen. Dies bildet den gesetzlichen Anspruch aus
§17 VOB/B i.V.m. §13 VOB/B technisch ab.

---

## Konsequenzen

### Positiv

- **Kein eingesperrtes Geld mehr:** `closeProject()` ist nur bei vollständig
  abgewickelten Meilensteinen möglich; `reopenProject()` repariert Fehlschließungen
- **Contractor-Autonomie:** Nach 14 Tagen ohne Client-Reaktion kann der Contractor
  selbst bestätigen — kein Deadlock mehr. Nach 4 Jahren Verjährungsfrist ab Abnahme
  kann der Contractor auch den Sicherheitseinbehalt selbst abrufen (§17 VOB/B i.V.m.
  §13 VOB/B).
- **Auditor als neutrale Instanz:** Der Auditor (RPA/Wirtschaftsprüfer) kann
  Meilensteine bestätigen, Projekte wiedereröffnen und den Sicherheitseinbehalt
  freigeben — ohne selbst Gelder bewegen zu können

### Negativ

- Geringfügig erhöhte Gas-Kosten durch zusätzliche `require`-Checks in `closeProject()`
- Der Auditor muss im `constructor` gesetzt werden und eine vertrauenswürdige Adresse
  sein — im Piloten ist das die RPA-Prüfadresse, im Echtbetrieb eine MultiSig

### Neutral

- `onlyOwner` wurde auf zwei Funktionen reduziert, bei denen die exklusive
  Client-Kontrolle sachlich korrekt ist:
  - `fundProject` — nur der Bauherr finanziert
  - `addMilestone` — nur der Bauherr definiert Leistungen
  - `closeProject` — nur der Bauherr erklärt die Abnahme (aber nur bei vollständig
    abgewickelten Meilensteinen; Auditor kann mit `reopenProject` korrigieren)
- Drei Funktionen sind jetzt dreiparteienfähig (Client / Auditor / Contractor+Timeout):
  `completeMilestone`, `releaseRetention`
- `releaseMilestone` ist und bleibt permissionless (jeder kann einen fertigen
  Meilenstein zur Auszahlung bringen)

---

## Alternativen (verworfen)

| Alternative | Grund der Ablehnung |
|-------------|---------------------|
| 2-of-2 Multisig für `completeMilestone` | Deadlock-Risiko: Wenn eine Partei ausfällt, keine Freigabe |
| `closeProject` mit 30-Tage-Timelock | Komplexität; löst das Grundproblem (eingesperrte Funds) nicht |
| `completeMilestone` permissionless | Keine Qualitätskontrolle; PoPW-Proof allein reicht nicht als Leistungsnachweis |

---

## Verwandte Dokumente

- ADR-003: Non-custodial Escrow (kein emergency withdraw)
- ADR-004: BHO Zero-Sum (Δ ≤ 0,01 €)
- ADR-006: §13b UStG Reverse-Charge
- `shadow_contract_pilot/contract/VOB_Shadow_Escrow.sol`
- `agents_b2g/shadow/shadow_contract_orchestrator.py` (Wave 18)
