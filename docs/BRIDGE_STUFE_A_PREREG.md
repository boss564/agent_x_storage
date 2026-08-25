# Stufe A — Bridge-vermittelte Kreuz-Anregung ETH ↔ Gnosis (Pre-Registration)

**Status:** Pre-Registration — **bindend** (Parameter bestätigt 2026-08-17).
**Datum:** 2026-08-17
**Spec:** `docs/BRIDGE_STUFE_A_SPEC.md`
**Mechanismus:** OmniBridge-Flüsse (ETH ↔ Gnosis)
**Kontrolle:** Kontrastpaar (OmniBridge-Korridor vs. Uniswap-Marktaktivität ETH ↔ Arbitrum)
**Charakter:** Vorab registrierte Auswertungsregel, ergebnisoffen.
Schwellen und Adressen sind fixiert. Nach Datenblick **keine** Nachjustage.

Stufe B (interventionell, Ausfallfenster) bleibt optional und braucht eine
**eigene** Pre-Reg. Diese Datei deckt nur Stufe A (Beobachtung).

---

## Bestätigungen (2026-08-17) — die fünf offenen Parameter

| # | Parameter | Festlegung |
|---|---|---|
| 1 | Ungebrückte Kontroll-Chain | **Arbitrum One** (chainId 42161) |
| 2 | OmniBridge-Adressen | Multi-Token-Mediator, siehe §4 (nicht AMB, nicht xDAI-Bridge) |
| 3 | Value-Schwelle | **keine** — alle Mediator-Events, unabhängig vom Token-Wert |
| 4 | Beobachtungsperiode | **90 Kalendertage**, kalendarisch eingefroren: **2026-05-20 00:00:00 UTC bis 2026-08-17 23:59:59 UTC** (inklusive) |
| 5 | Lag-Bereich | **0–30 Minuten in 1-Minuten-Schritten** (31 Lags) |

Zusätzlich festgehalten, weil der Entwurf sonst unterbestimmt blieb:

- **Kontroll-Paar ist nicht ETH↔Arbitrum-Bridge.** Arbitrum hat eine kanonische
  ETH-Bridge. Ein Paar „ETH Inbox ↔ Arbitrum Gateway“ wäre ein *zweiter*
  Bridge-Korridor, keine Negativkontrolle. Eingefroren: Kontroll-Events =
  Uniswap Universal Router auf ETH und auf Arbitrum (Marktaktivität, kein
  OmniBridge, kein Arbitrum-Inbox).
- **Event-Quelle Treatment:** Logs der Mediator-Contracts
  (`TokensBridgingInitiated`, `TokensBridged`), nicht `tx.to == Mediator`.
  Auf Gnosis→ETH ruft der Nutzer typischerweise `transferAndCall` am ERC-677-
  Token auf; `tx.to` wäre der Token, nicht der Mediator.
- **xDAI-Native-Bridge ausgeschlossen** (`0x4aa4…` / `0x7301…`). Anderer
  Mechanismus; Mischung wäre HARKing.
- **Kein IAAFT.** Jitter (Hawkes) / Shuffle (TE). Begründung: metronomische
  Blockzeiten, Spektrum-erhaltende Nullartefakte (AstroCore-Nachtrag,
  Wirtschafts-Schwarm).

---

## 1. Hypothese

**H1 (gerichtet, mit Lag):** Zwischen Ethereum und Gnosis existiert eine
gerichtete Kreuz-Anregung in den OmniBridge-Flow-Ereignissen. Sie ist stärker
als im Kontroll-Paar ETH↔Arbitrum (Uniswap) und übersteht die Konditionierung
auf Gas, BTC-Preis und CEX-Volumen.

**Richtung:** bidirektional (ETH → Gnosis und Gnosis → ETH).

**Lag:** geprüft auf τ ∈ {0, 1, …, 30} Minuten. Mechanistische Erwartung
(deskriptiv, nicht filternd): ETH→Gnosis um die Foreign-Finalität
(~15 ETH-Confirmations ≈ 3 min, mit Slack in den ersten 10 min);
Gnosis→ETH um Home-Finalität + ETH-Confirmation (Größenordnung 15–25 min).
**Alle 31 Lags bleiben konfirmatorisch** — die mechanistische Erwartung
wird nicht nachträglich zur Subset-Filterung missbraucht.

**H0:** Keine Kreuz-Anregung über die gemeinsamen Markttreiber hinaus.
Jede beobachtete Assoziation ist durch Gas, BTC und CEX-Volumen erklärbar
und/oder erscheint gleichermaßen im Kontroll-Paar.

---

## 2. Messachsen

**Primär — Hawkes-Anregungskern γ(τ)** (nicht-parametrisch, 1-min-Bins):

- `γ_ETH→Gnosis(τ)`, `γ_Gnosis→ETH(τ)`
- Analog für das Kontroll-Paar: `γ_ETH→Arbitrum(τ)`, `γ_Arbitrum→ETH(τ)`
- Skalares Branching `α = Σ_τ γ(τ)·Δτ` mit Δτ = 1 min ist **deskriptiv**,
  kein 249. konfirmatorischer Test.

**Ko-primär — bedingte Transferentropie (CTE):**

- `CTE_ETH→Gnosis | Gas, BTC, CEX` bei Lag τ (binäre 1-min-Belegung)
- analog die drei anderen Richtungen

**Deskriptiv — unbedingte Transferentropie (UTE):** gleicher Schätzer ohne
Treiber. Differenz UTE−CTE beschreibt, wie viel der Assoziation die Treiber
erklären. Kein zusätzlicher BH-Test.

---

## 3. Nullmodelle (kein IAAFT)

| Metrik | Null | Surrogate | Entscheidung |
|---|---|---|---|
| Hawkes γ(τ) | Jitter: jedes Event uniform ±5 min, Rejection-Sampling bis der Zeitstempel im Beobachtungsfenster bleibt (Event-Zahl konstant) | 1000 | beobachteter Wert > 95%-Quantil der Null |
| CTE / UTE | Shuffle: Zeitstempel des *Quell*-Prozesses permutieren; Ziel und Treiber unverändert | 1000 | analog |

p-Wert: `p = (1 + #{surr ≥ obs}) / 1001` (plus-one, konservativ).

---

## 4. Event-Definitionen (eingefroren)

### 4.1 Treatment — OmniBridge Multi-Token Mediator

Quelle: [Gnosis Omnibridge docs](https://docs.gnosischain.com/bridges/About%20Token%20Bridges/omnibridge)
und [Useful Contracts](https://docs.gnosischain.com/developers/Usefulcontracts).

| Seite | Rolle | Adresse |
|---|---|---|
| Ethereum | Foreign Multi-Token Mediator Proxy | `0x88ad09518695c6c3712AC10a214bE5109a655671` |
| Gnosis | Home Multi-Token Mediator Proxy | `0xf6A78083ca3e2a662D6dd1703c939c8aCE2e268d` |

**Events (beide Mediatoren):**

```text
TokensBridgingInitiated(address indexed token, address indexed sender, uint256 value, bytes32 indexed messageId)
TokensBridged(address indexed token, address indexed recipient, uint256 value, bytes32 indexed messageId)
```

**topic0 (keccak256 der Signatur, eingefroren):**

| Event | topic0 |
|---|---|
| TokensBridgingInitiated | `0x59a9a8027b9c87b961e254899821c9a276b5efc35d1f7409ea4f291470f1629a` |
| TokensBridged | `0x9afd47907e25028cdaca89d193518c302bbb128617d5a992c5abd45815526593` |

Ein Punktprozess-Event = ein Log mit einem dieser topic0, emittiert vom
jeweiligen Mediator, Zeitstempel = Blockzeit. Keine Value-Schwelle.
Duplikate (gleiche txHash+logIndex) werden einmal gezählt.

**Nicht enthalten:** AMB-Proxy, Validator-Management, wETH-Router-Helper,
xDAI-Native-Bridge.

### 4.2 Kontrolle — Uniswap Universal Router (ETH ↔ Arbitrum One)

Quelle: Uniswap `universal-router-sdk` `CHAIN_CONFIGS` (Stand Abruf 2026-08-17).
Union aller gelisteten Router-Versionen, damit eine Migration in den 90 Tagen
kein HARKing-Fenster öffnet.

**Ethereum (chainId 1) — tx.to ∈**

| Version | Adresse |
|---|---|
| V1.2 | `0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD` |
| V2.0 | `0x66a9893cc07d91d95644aedd05d03f95e1dba8af` |
| V2.1.1 | `0x4C82D1fBFe28C977cBB58D8C7FF8FCF9F70a2cCA` |
| V2.2.0 | `0x0542093271A31f6FC1DADB232bd59eeb27de780F` |

**Arbitrum One (chainId 42161) — tx.to ∈**

| Version | Adresse |
|---|---|
| V1.2 | `0x5E325eDA8064b456f4781070C0738d849c824258` |
| V2.0 | `0xa51afafe0263b40edaef0df8781ea9aa03e381a3` |
| V2.1.1 | `0x8B844f885672f333Bc0042cB669255f93a4C1E6b` |

Ein Kontroll-Event = eine Transaktion mit `tx.to` in der jeweiligen Menge,
Zeitstempel = Blockzeit, keine Value-Schwelle.

**Bewusst ausgeschlossen:** ältere Interface-Router, die nicht in dieser
SDK-Liste stehen (u. a. `0x3fC91A3afd70395Cc084A9dCb6CDe3bD4B8904E8`).
Kein Nachziehen nach Volumenblick.

### 4.3 Gemeinsame Treiber (1-min-Aggregation)

| Treiber | Definition | Quelle (Reihenfolge) |
|---|---|---|
| Gas | Median `baseFeePerGas` der ETH-Blöcke in der Minute, Fallback `gasPrice` | ETH-RPC `eth_feeHistory` / Block-Header |
| BTC | BTC/USD Schluss der Minute | CoinGecko `bitcoin` market_chart, Fallback Binance `BTCUSDT` kline |
| CEX-Volumen | Summe Spot-Volumen USD der Minute, Top-5 CEX laut CoinGecko-Ticker (BTC+ETH Paare aggregiert wie in der Spec) | CoinGecko / CEX-REST |

Fehlende Minuten: linear interpolieren über Lücken ≤ 5 min; Lücken > 5 min
bleiben NaN und die CTE-Bins mit NaN-Treibern werden **drop** (kein Fill-0).

---

## 5. Kontrastpaar-Design

| Paar | Ketten | Event-Klasse | Rolle |
|---|---|---|---|
| Behandlung | Ethereum ↔ Gnosis | OmniBridge-Mediator-Logs | erwartete Kreuz-Anregung |
| Kontrolle | Ethereum ↔ Arbitrum One | Uniswap Universal Router `tx.to` | Negativkontrolle (kein OmniBridge-Korridor) |

Beide Paare sehen Gas/BTC/CEX. Nur das Behandlungs-Paar hat den OmniBridge-
Korridor zwischen den gemessenen Punktprozessen.

**Caveat (vorab):** Event-Klassen sind nicht identisch (Bridge-Logs vs. DEX-
`tx.to`). Das ist Absicht: eine kanonische Arbitrum-Bridge als Kontrolle
würde H1 nicht falsifizieren können. Die Asymmetrie steht im Ergebnis-Dossier.

---

## 6. Tests, FDR, Verdict

**α = 0.05** vor Korrektur. **Benjamini-Hochberg FDR q = 0.05.**

**248 Tests:** 2 Richtungen × 31 Lags × 2 Metriken (Hawkes γ, CTE) × 2 Paare.

UTE, skalares α, Treiber-Korrelationen = deskriptiv, nicht in den 248.

**Mindeststichprobe:** Jeder der vier Punktprozesse braucht **N ≥ 100** Events
im Fenster. Sonst Verdict `INCONCLUSIVE` (nicht „n.s.“).

**Verdict (IUT-artig, eingefroren):**

| Label | Regel |
|---|---|
| `POSITIVBEFUND` | Nach BH-FDR: ≥1 signifikantes **Treatment**-Lag in CTE **und** ≥1 in Hawkes γ, in mindestens einer Richtung; **und** das Kontroll-Paar hat **0** BH-signifikante CTE-Tests **und** 0 BH-signifikante Hawkes-Tests |
| `NEGATIVBEFUND` | Treatment: 0 BH-signifikante Tests in CTE **und** 0 in Hawkes γ |
| `DISSOZIIERT` | Hawkes und CTE widersprechen sich auf der Treatment-Seite (eines sig, das andere nicht), Kontrolle 0 sig |
| `UNSPEZIFISCH` | Treatment signifikant **und** Kontrolle ebenfalls ≥1 sig Test (gemeinsamer Treiber / Kontrast versagt) |
| `INCONCLUSIVE` | N < 100 in mindestens einem der vier Ströme, oder Treiber-Coverage < 80 % der Minuten |

Kein Nachschärfen der Labels nach Zahlenblick.

---

## 7. Zeitfenster und Auflösung

- **Fenster:** 2026-05-20 00:00:00 UTC – 2026-08-17 23:59:59 UTC
- **Hawkes:** exakte Block-Zeitstempel (Sekunden)
- **CTE / Treiber:** 1-Minuten-Bins; Event-Bin = floor(ts / 60)
- **Binärisierung CTE:** 1 wenn ≥1 Event in der Minute, sonst 0

---

## 8. Caveats (Pflicht im Ergebnis-Dossier)

1. Metronomische Blockzeiten sind kein Hawkes-Prozess — nur Transfer-/Bridge-
   Zeitstempel.
2. Stufe A ist beobachtend. POSITIVBEFUND = Assoziation, nicht Kausalität.
3. Kontrastpaar ist schwächer als eine Intervention (Stufe B).
4. Kontroll-Event-Klasse ≠ Treatment-Event-Klasse.
5. CEX-Volumen ist ein Proxy.
6. Öffentliche RPCs können `eth_getLogs` über 90 Tage ablehnen; Capture braucht
   archive-fähige Endpoints. Fehlende Logs = `INCONCLUSIVE`, nicht Imputation.
7. OmniBridge-Validator-Pause in diesem Fenster wäre ein natürliches
   Ausfallfenster — **nicht** in Stufe A auswerten (Stufe B, neue Pre-Reg).

---

## 9. Was nach Datenblick verboten ist

- Adressen, Router-Versionen, Value-Schwellen, Fenster, Lag-Raster ändern
- IAAFT nachreichen, weil Jitter „zu konservativ“ wirkt
- 248 Tests auf „interessante“ Lags reduzieren
- xDAI-Bridge oder AMB-only-Logs nachträglich einmischen
- Kontroll-Paar auf Arbitrum-Inbox umstellen, weil Uniswap „zu laut“ ist
