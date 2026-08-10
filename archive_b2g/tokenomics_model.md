# Agent X — Ökonomisches Tokenomics-Modell

## Der wirtschaftliche Schwungrad-Mechanismus für B2G/DePIN

**Version 1.0 | 2026-08-09**

---

## 1. Das Drei-Token-Modell

Agent X verwendet drei Token-Typen mit klar getrennten Funktionen:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     AGENT X TOKEN-ARCHITEKTUR                        │
│                                                                      │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐          │
│   │    EURe     │     │   $AGX      │     │   veAGX     │          │
│   │  (EMT)      │     │  (Utility)  │     │  (Gov)      │          │
│   │             │     │             │     │             │          │
│   │ • Zahlungs- │     │ • Staking   │     │ • Voting    │          │
│   │   mittel    │     │ • Fee-Pool  │     │ • Proposals │          │
│   │ • 1:1 EUR   │     │ • Slashing  │     │ • Veto      │          │
│   │ • MiCA      │     │ • Burn      │     │ • Timelock  │          │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘          │
│          │                   │                   │                  │
│   ┌──────┴───────────────────┴───────────────────┴──────┐          │
│   │                   TEILNEHMER                          │         │
│   │  Kommune  │  Bauuntern.  │  Subunter.  │  Auditor     │         │
│   │  (Zahler) │  (Staker)   │  (Holder)   │  (Verifier)  │         │
│   └──────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
```

| Token | Typ | Funktion | Emission | Zielgruppe |
|-------|-----|----------|----------|------------|
| **EURe** | EMT (MiCA-lizenziert) | Zahlungsmittel für Bauleistungen | 1:1 Mint/Burn via SEPA | Alle — kein Spekulationsobjekt |
| **$AGX** | ERC-20 Utility Token | Staking, Fee-Pool, Slashing, Burn | Max. 100 Mio., 20 % Community | Bauunternehmen, Subunternehmer |
| **veAGX** | ERC-20Votes (Vote-Escrowed) | Governance, Proposal-Voting, Veto | 1 $AGX locked 1y → 1 veAGX | Subunternehmer, Auditor |

---

## 2. Der Schwungrad-Mechanismus (Flywheel)

```
                     ┌──────────────────────────────────────┐
                     │                                      │
                     ▼                                      │
   ┌──────────────────────────────────────┐                 │
   │  1. KOMMUNE SCHREIBT AUS             │                 │
   │     → EURe wird per SEPA geminted    │                 │
   │     → Ausschreibung auf Agent X      │                 │
   └──────────────┬───────────────────────┘                 │
                  │                                          │
                  ▼                                          │
   ┌──────────────────────────────────────┐                 │
   │  2. BAUUNTERNEHMEN BIETET            │                 │
   │     → Muss $AGX staken (Sicherheit)  │                 │
   │     → Höherer Stake = bessere        │                 │
   │       Position im Bieter-Ranking     │                 │
   └──────────────┬───────────────────────┘                 │
                  │                                          │
                  ▼                                          │
   ┌──────────────────────────────────────┐                 │
   │  3. MEILENSTEIN WIRD FREIGEGEBEN     │                 │
   │     → 80 % EURe an Bauunternehmen    │                 │
   │     → 15 % §48b EStG an Finanzamt    │                 │
   │     →  5 % Retention in Vault        │                 │
   └──────────────┬───────────────────────┘                 │
                  │                                          │
                  ▼                                          │
   ┌──────────────────────────────────────┐                 │
   │  4. TRANSAKTIONS-GEBÜHR (0.1 %)      │                 │
   │     → 50 % an $AGX-Staker (Reward)   │                 │
   │     → 30 % Burn ($AGX deflationär)   │                 │
   │     → 20 % Vault-Liquidität          │                 │
   └──────────────┬───────────────────────┘                 │
                  │                                          │
                  ▼                                          │
   ┌──────────────────────────────────────┐                 │
   │  5. $AGX WIRD WERTVOLLER             │                 │
   │     → Mehr Bauunternehmen staken ────┼─────────────────┘
   │     → Mehr B2G-Volumen               │
   │     → Mehr Fee-Burn                  │
   └──────────────────────────────────────┘
```

**Der Flywheel-Effekt in Zahlen:**
- 1 Mrd. € B2G-Volumen × 0.1 % Fee = 1 Mio. € Gebühren
- 300.000 € Burn → $AGX Supply sinkt → Preis steigt
- 500.000 € Staking-Rewards → mehr Bauunternehmen staken → höhere Sicherheit → mehr Aufträge

---

## 3. Staking-Modell für Bauunternehmen

### 3.1 Warum Staking?

Bauunternehmen hinterlegen $AGX als **Sicherheitsleistung** — als Alternative
zur klassischen Aval-Bürgschaft der Bank (Kosten: 0.5–1.5 % p.a. der
Bürgschaftssumme). Der Stake bietet eine kryptografische Alternative
mit **anderem Sicherheitsprofil** als eine Bankbürgschaft:

**Wichtig:** $AGX ist kein Aval-Ersatz im rechtlichen Sinne. Eine
Bankbürgschaft haftet mit dem Rating der Bank, der Nominalwert ist
stabil, und die Bonität ist extern geprüft. $AGX-Staking ist Sicherheit
im Token der Plattform selbst — der Wert kann schwanken. Die Ersparnis
ist real, die Gleichwertigkeit zur Bankbürgschaft nicht.

1. Keine laufenden Kosten verursacht (die Bankbürgschaft kostet jährlich)
2. Automatisch nach 4 Jahren Gewährleistung freigegeben wird
3. Verzinst wird (Staking-Rewards aus Transaktionsgebühren)

### 3.2 Stake-Anforderungen

| Auftragsvolumen | Mindest-Stake ($AGX) | Stake in € (bei 1 $AGX = 0.10 €) | Klassische Aval-Kosten (1 % p.a.) | Ersparnis (4 Jahre) |
|-----------------|---------------------|-----------------------------------|-----------------------------------|---------------------|
| 50.000 € | 50.000 $AGX | 5.000 € | 2.000 € | −3.000 € (erst ab 500k sinnvoll) |
| 500.000 € | 100.000 $AGX | 10.000 € | 20.000 € | +10.000 € |
| 5 Mio. € | 250.000 $AGX | 25.000 € | 200.000 € | +175.000 € |
| 50 Mio. € | 500.000 $AGX | 50.000 € | 2.000.000 € | +1.950.000 € |

**Break-Even:** Ab 500.000 € Auftragsvolumen ist Staking günstiger als Aval.
Die Ersparnis steigt linear mit dem Volumen.

### 3.3 Staking-Pool-Mechanik

```python
# Vereinfachtes Staking-Modell

class StakingPool:
    def __init__(self):
        self.total_staked = 0          # Summe aller Stakes
        self.annual_reward_rate = 0.05  # 5 % APY aus Fee-Pool
        self.slashing_penalty = 0.10    # 10 % bei IoT-Manipulation

    def stake(self, builder: str, amount: float) -> dict:
        """Bauunternehmen staked $AGX."""
        self.total_staked += amount
        return {
            "builder": builder,
            "staked": amount,
            "min_lock_days": 365,            # 1 Jahr Minimum
            "expected_apy": self.annual_reward_rate,
            "unlock_date": "2027-08-09",
            "bid_boost": amount / self.total_staked  # Ranking-Bonus
        }

    def slash(self, builder: str, reason: str) -> dict:
        """Slashing bei IoT-Manipulation oder Mangel nicht behoben."""
        stake = self.get_stake(builder)
        penalty = stake * self.slashing_penalty
        return {
            "builder": builder,
            "slashed": penalty,
            "reason": reason,
            "whistleblower_reward": penalty * 0.50,  # 50 % an Melder
            "burn": penalty * 0.50                    # 50 % verbrannt
        }
```

### 3.4 Staking-Tiers und Bietervorteil

| Tier | Stake ($AGX) | Ranking-Boost | APY | Voraussetzung |
|------|-------------|---------------|-----|---------------|
| **BRONZE** | 10.000 | +2 % | 3 % | Mindest-Stake für Teilnahme |
| **SILBER** | 50.000 | +5 % | 5 % | 3 erfolgreiche Projekte |
| **GOLD** | 250.000 | +10 % | 7 % | 10 Projekte, kein Slashing |
| **PLATIN** | 1.000.000 | +15 % | 10 % | 50 Projekte, Governance |

Der Ranking-Boost fließt in den PoPW-Index ein (Preis-Leistungs-Verhältnis mit
regionalem Bonus). Ein Gold-Staker mit gleichem Angebotspreis wie ein
Nicht-Staker gewinnt die Ausschreibung.

---

## 4. Vault-Liquidität für kommunale Kassen

### 4.1 Der Retention-Vault

Jede Bauzahlung behält 5 % für 4 Jahre ein (§ 17 VOB/B). Diese Mittel liegen
nicht brach — sie werden im **Retention-Vault** verwaltet und generieren
Liquidität für die Kommune.

```
┌──────────────────────────────────────────────────────────────┐
│                    RETENTION-VAULT                            │
│                                                               │
│  Eingang: 5 % jeder Bauzahlung                                │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ 95 % → Kommunales Liquiditätspolster                 │     │
│  │        • Verwendbar für kurzfristige Kassenkredite   │     │
│  │        • Spart 3-5 % Kreditzinsen pro Jahr           │     │
│  │        • Automatische Rückführung bei Freigabe       │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ 5 % → Staking-Pool                                    │     │
│  │        • EURe → $AGX via DEX                          │     │
│  │        • Erwirtschaftet ~5 % APY                      │     │
│  │        • Erträge: 70 % Vault, 30 % Fee-Pool           │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Vault-Größenordnung (Beispiel München)

| Bauvolumen (jährlich) | 5 % Retention | Vault-Größe (4 Jahre kumuliert) | Zinsersparnis (5 % p.a.) |
|----------------------|---------------|--------------------------------|-------------------------|
| 100 Mio. € | 5 Mio. € | 20 Mio. € | 1.0 Mio. € |
| 500 Mio. € | 25 Mio. € | 100 Mio. € | 5.0 Mio. € |
| 2 Mrd. € | 100 Mio. € | 400 Mio. € | 20.0 Mio. € |

---

## 5. Burn-Mechanismus (Deflation)

### 5.1 Transaktions-Burn

Jede B2G-Transaktion verbrennt einen Teil der $AGX-Gebühren:

| Komponente | Anteil | Verwendung |
|-----------|--------|------------|
| **Staking-Reward** | 50 % | Ausgeschüttet an $AGX-Staker (pro rata) |
| **Burn** | 30 % | Unwiderruflich verbrannt (Supply ↓) |
| **Vault-Reserve** | 20 % | Kommunales Liquiditätspolster |

### 5.2 Burn-Simulation (10 Jahre)

```
Annahmen:
  - Start-Supply: 100.000.000 $AGX
  - Jährliches B2G-Volumen: steigend 100 Mio. → 5 Mrd. €
  - Fee: 0.1 % des Transaktionsvolumens
  - Burn-Rate: 30 % der Fee
  - Burn in $AGX = Burn (EUR) / $AGX-Preis (EUR)
  - $AGX-Preis: exogen gesetzt (illustrativ, nicht aus Burn abgeleitet)
  - Jahre 7–9: Volumen linear interpoliert zwischen Jahr 6 und Jahr 10;
    Preis exogen gesetzt, keine Interpolation

Jahr  Vol.(Mio.€) Fee(€)    Burn(€)   Preis(€)  Burn($AGX)  Supply(Mio.)  Burn kum.(Mio.)
────  ────────── ────────   ────────   ────────  ──────────  ────────────  ───────────────
  1         100    100.000    30.000     0.10      300.000        99.70          0.30
  2         250    250.000    75.000     0.12      625.000        99.08          0.93
  3         500    500.000   150.000     0.15    1.000.000        98.08          1.93
  4       1.000  1.000.000   300.000     0.19    1.578.947        96.50          3.50
  5       1.500  1.500.000   450.000     0.24    1.875.000        94.63          5.38
  6       2.000  2.000.000   600.000     0.30    2.000.000        92.62          7.38
  7       2.750  2.750.000   825.000     0.38    2.171.053        90.45          9.55
  8       3.500  3.500.000 1.050.000     0.45    2.333.333        88.12         11.88
  9       4.250  4.250.000 1.275.000     0.49    2.602.041        85.51         14.49
 10       5.000  5.000.000 1.500.000     0.52    2.884.615        82.63         17.37
```

**Kumulierter Burn über 10 Jahre: 17,37 Mio. $AGX (17,4 % des Initial-Supply)**
— nachvollziehbar aus den 10 gezeigten Zeilen. Der deflationäre Druck ist
signifikant — kombiniert mit Staking-Lockups (bis zu 40 % des Supply
dauerhaft gestaked, bezogen auf Initial-Supply = 40 Mio. $AGX) verknappt
sich das frei handelbare Angebot auf ~42,6 Mio. $AGX nach 10 Jahren
(82,63 Mio. Supply − 40 Mio. gestaked).

---

## 6. Governance-Rechte für Subunternehmer

### 6.1 veAGX — Vote-Escrowed $AGX

Subunternehmer erhalten Governance-Rechte via **veAGX**, ein
Vote-Escrow-Token nach dem Vorbild von Curve (veCRV):

- **Lock-Periode**: 1 $AGX locked × 1 Jahr → 1 veAGX
- **Voting-Power**: proportional zu Lock-Dauer (max. 4 Jahre = 4× Power)
- **Veto-Recht**: 33 % der veAGX-Inhaber können einen Vorschlag blockieren
- **Quorum**: 20 % der veAGX für gültige Abstimmung

### 6.2 Governance-Bereiche

| Bereich | Quorum | Mehrheit | Beispiel |
|---------|--------|----------|---------|
| **Fee-Anpassung** (0.05 %–0.50 %) | 30 % | 60 % | Erhöhung auf 0.15 % bei steigendem Volumen |
| **Slashing-Strafen** (5 %–25 %) | 25 % | 55 % | Anpassung der IoT-Manipulationsstrafe |
| **Staking-Parameter** (APY, Lock-Dauer) | 25 % | 55 % | APY von 5 % auf 7 % erhöhen |
| **Protokoll-Upgrade** | 20 % | 66 % | Smart-Contract-Migration |
| **Notfall-Pause** | 15 % | 75 % | Einfrieren aller Transaktionen |

### 6.3 Warum Governance für Subunternehmer?

Subunternehmer sind die größte Teilnehmergruppe (80 % der Bieter) und tragen
das höchste Risiko (Zahlungsverzug, Mangelhaftung). Governance-Rechte via
veAGX geben ihnen eine Stimme im System — ohne dass sie Kapital in großem
Umfang binden müssen.

| Teilnehmer | Anteil am Volumen | $AGX-Holding | veAGX-Voting-Power |
|-----------|-------------------|-------------|-------------------|
| Großunternehmen (5 %) | 60 % | 200.000 | 200.000 |
| Mittelstand (15 %) | 25 % | 50.000 | 50.000 |
| Subunternehmer (80 %) | 15 % | 10.000 | 40.000 (4y lock) |

Durch längere Lock-Dauer können Subunternehmer ihre Voting-Power vervielfachen
und so ein Gegengewicht zu den Großunternehmen bilden.

---

## 7. Modell-Annahmen (illustrativ, nicht prognostisch)

Die folgenden Zahlen sind **deterministische Szenario-Rechnungen auf Basis
der in Abschnitt 5.2 dokumentierten Parameter.** Sie sind keine Preisprognose
und keine Monte-Carlo-Simulation. Eine stochastische Simulation mit
10.000 Läufen ist für Q1/2027 vorgesehen, sobald Pilotdaten aus den ersten
drei Kommunen vorliegen.

Für ein B2G-Volumen von 500 Mio. € jährlich (Größenordnung Großstadt)
ergeben sich aus den Formeln in Abschnitt 2-6:

| Metrik | Wert | Herleitung |
|--------|------|------------|
| **$AGX-Preis (Jahr 1)** | Annahme: 0.15 € | Startpreis aus Token-Sale-Äquivalent (15 Mio. € FDV bei 100 Mio. Supply) |
| **Staking-APY** | 3.3 % (Basis) / 5.0 % (Sensitivität) | Basis: (0.1 % Fee × 50 % Staker-Anteil × 500 Mio. €) / (50 Mio. $AGX × 0.15 €) = 250.000 € / 7.5 Mio. € ≈ 3.3 %. Sensitivität: bei 1 Mrd. € Volumen oder 33 Mio. $AGX gestaked steigt APY auf 5.0 %. |
| **Burn (jährlich)** | 1.000.000 $AGX | 30 % × Fee / Preis (aus Tabelle 5.2, Jahr 3) |
| **Vault-Liquidität** | 25 Mio. € | 5 % × 500 Mio. € × 1 Jahr (Rotationsbasis) |
| **Kommunale Zinsersparnis** | 1.25 Mio. € | 5 % × 25 Mio. € (Differenz Kassenkredit vs. Vault-Rendite) |

**Keine Monte-Carlo-Simulation.** Die Werte sind Einpunkt-Schätzungen auf
Basis der deterministischen Burn-Tabelle in Abschnitt 5.2. Preis-Prognosen
für $AGX in späteren Jahren sind spekulativ und daher nicht angegeben.
Sobald Pilotdaten aus Q1/2027 vorliegen, wird eine stochastische Simulation
mit belegten Eingangsparametern nachgeliefert.

---

## 8. Token-Allokation

| Allokation | Anteil | Menge ($AGX) | Vesting |
|-----------|--------|-------------|---------|
| **Community / Staking-Rewards** | 40 % | 40.000.000 | 10 Jahre linear |
| **Entwicklungsteam** | 20 % | 20.000.000 | 4 Jahre, 1 Jahr Cliff |
| **Öffentliche Hand (Reserve)** | 15 % | 15.000.000 | Kein Vesting, nur mit Ratsbeschluss |
| **Ecosystem-Fund** | 15 % | 15.000.000 | 5 Jahre linear |
| **Liquidität (DEX)** | 10 % | 10.000.000 | Sofort, via Uniswap v3 |

**Kein Pre-Mine-Verkauf. Kein VC-Rabatt.** Die 15 % für die öffentliche Hand
stellen sicher, dass Kommunen selbst $AGX halten und an der Plattform-Governance
teilnehmen können — ein eingebauter Interessenausgleich. $AGX ist ein
Utility-Token für Staking und Governance, kein Investment-Vehikel. Die
Allokation begründet keine Erwartung einer Wertsteigerung.

---

## 9. Risiken & Mitigation

| Risiko | Mitigation |
|--------|------------|
| **$AGX-Preis-Volatilität** | EURe als Zahlungsmittel (stabil); $AGX nur für Staking/Gov — kein Zahlungsmittel |
| **Staking-Konzentration** | Max. 5 % des Supply pro Adresse; Governance votet über Anpassung |
| **Burn zu aggressiv** | Fee-Rate via Governance anpassbar (0.05 %–0.50 %) |
| **Slashing-Missbrauch** | Whistleblower-Reward gedeckelt auf 50 %; Rest verbrannt |
| **Regulatorische Unsicherheit** | EURe ist MiCA-lizenziert; $AGX fällt unter Utility-Token-Ausnahme (Art. 2 Abs. 4 MiCA) |

---

*Dieses Modell ist eine Simulation. Staking-Renditen sind variabel und
abhängig vom tatsächlichen B2G-Transaktionsvolumen. Keine Anlageberatung —
$AGX ist ein Utility-Token, kein Investment-Vehikel.*
