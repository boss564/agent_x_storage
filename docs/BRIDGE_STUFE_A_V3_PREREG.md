# Stufe A v3 — Z-Erweiterung der CTE (Pre-Registration)

**Status:** **bindend** (gesetzt am 2026-08-19)  
**Ziel:** Kandidatenbasierte Erweiterung des Konditionierungssatzes, ohne Umdeutung von Stufe A / v2  
**Bindender Vorlauf:** `docs/BRIDGE_STUFE_A_ERGEBNIS.md` (`UNSPEZIFISCH`), `docs/BRIDGE_STUFE_A_V2_ERGEBNIS.md` (`V2_UNSPEZIFISCH`)

---

## 0. Vorbedingungen und Scope

1. Stufe A und v2 bleiben versiegelt; diese Studie ändert keine Verdicts rückwirkend.
2. Zweck: testen, ob ein erweiterter Treibersatz `Z_neu` den residualen Cross-Chain-Informationsfluss erklärt.
3. Keine Kandidatenauswahl nach Datenblick: Auswahlregel und Testfamilie sind vorab fix.

---

## 1. Blocking-Entscheidungen (vor Capture)

### 1.1 Finalitäts-Abgleich: Labeling-Regel

Der Abgleich `τ_ab=6`, `τ_ba=15/16` wird bis zur Vertrags-/Doku-Verifikation als
**konsistent mit Komponenten-Konstruktion** geführt, nicht als „entspricht dokumentierter Finalität“.

- Zulässige Primärquelle für „dokumentierte Finalität“:
  - OmniBridge/AMB-Dokumentation mit richtungsspezifischen Regeln, und/oder
  - On-chain-Parameter aus relevanten AMB/Mediator-Verträgen.
- Bis diese Quelle vollständig gezogen ist, ist das Finalitätsargument deskriptiv/hypothesengenerierend.

### 1.2 Kandidatenliste vollständig (kein stiller Drop)

Die Kandidatenfamilie umfasst **fünf** Klassen (fix):

1. Orakel: `AnswerUpdated` (Chainlink)
2. Intent-Relayer: z. B. Across `FilledOrder`, CoW-/ähnliche Settlement-Signale
3. Liquidationen: z. B. Aave `LiquidationCall` (ggf. Spark/Compound bei vordefinierter Erweiterung)
4. Stablecoin Mint/Burn & Peg-Arb: z. B. CCTP `DepositForBurn`/`MintAndWithdraw`, Maker PSM `BuyGEM`/`SellGEM`
5. MEV/Searcher-Cluster: vordefinierte `tx.from`-Heuristik

Kandidat #4 ist **verpflichtend enthalten**, außer es existiert ein **vorab dokumentiertes**
technisches Ausschlusskriterium (z. B. im Fenster keine verwertbaren Events auf beiden Chains).

### 1.3 FDR-Familie über Kandidaten × Richtungen × Lags

Within-Kandidat-FDR reicht nicht. Konfirmatorische Testfamilie ist global und
umfasst die **volle Matrix**, nicht nur eine nachträglich gefilterte Teilmenge:

| Dimension | Werte | Anzahl |
|---|---|---:|
| Kandidaten | 5 | 5 |
| Richtungen | `ab`, `ba` | 2 |
| Lags | `τ = 0..30` | 31 |
| **Gesamt** |  | **310 Tests** |

BH-FDR q=0.05 läuft über **alle 310 Tests**. Eine eventuelle Filterung
`S(τ) > 0` bestimmt nur, welche Lags **interpretiert** werden, nicht welche
Lags in die FDR-Familie eingehen.

### 1.4 Falsifikationskriterien vollständig

Die Pre-Reg fixiert drei Ausgänge (nicht nur „Kollaps“):

1. **Persistenz:** CTE bleibt nach Konditionierung auf alle Kandidaten signifikant  
   → `V3_PERSISTENZ`; kein Treiber identifiziert; Studie endet bindend mit
   „nicht erklärt durch `Z_neu`“. Eine Erweiterung des Kandidatensets wäre
   eine **neue** Pre-Reg, keine Fortsetzung dieser Studie.
2. **Einzel-Kollaps:** genau ein Kandidat erfüllt vorab definierte Kollaps-Regel  
   → kandidatenspezifische Erklärung bevorzugt.
3. **Mehrfach-Kollaps:** mehrere Kandidaten erfüllen Kollaps-Regel  
   → vordefinierter Tie-Break:
   1. größte mittlere `ΔCTE = CTE_vorher - CTE_nachher` über **alle 31 Lags**
   2. bei Gleichstand: höhere Robustheit über K-Folds (`n_folds_mit_kollaps`)
   3. bei weiterem Gleichstand: früherer Peak-Lag des Kandidaten-Events relativ
      zum Treatment-Event

---

## 2. Resampling-Architektur (konfirmatorischer Vorbau)

### 2.1 Primär vs. Sensitivität

- **Primär:** disjunkte Zeitblöcke (K-Fold, abhängigkeitsbewusst), `K = 9`
- **Sensitivität:** Moving Block Bootstrap (MBB), nicht als zweiter Primärpfad

### 2.2 Blocklänge (präregistriert)

Blocklänge ist kritischer Tuning-Parameter und wird vorab fixiert:

- Baseline: 24h
- Sensitivität: 60min
- Optionales datengetriebenes Auswahlkriterium nur, wenn die Regel *vorab* fixiert ist
  (z. B. Politis-White-ähnlich); keine Ex-post-Wahl.

### 2.3 Schwellen und Diskretisierung

- `P_sign >= 0.95`, `ASR > 2.0` als Baseline
- Bei kleinem `K` wird die Diskretisierung explizit dokumentiert
  (`P_sign>=0.95` kann auf Vollkonsens hinauslaufen)
- Sensitivitätsraster: `P_sign ∈ {0.80, 0.90, 1.00}`

### 2.4 Robustifizierung

- Winsorisierung vorab fixiert (Baseline 1%, Sensitivität 0.5%/2%)
- EB-Shrinkage mit eindeutig definierter Varianzschätzung über vordefinierte Blöcke

### 2.5 Determinismus

- Fester Seed für alle stochastischen Komponenten: `BRIDGE_STUFE_A_V3_SEED = 20260819`
- Version-Pinning aller Libraries im Spec/Lockfile
- Gleiche Inputs + gleicher Seed müssen byte-identische Outputs liefern
- Seed-Verwendung (fix):
  - Fold-Split/Block-Reihenfolge: `SEED`
  - MBB-Ziehungen: `SEED + 1000 + b`
  - eventuelle Surrogat-/Permutationsteile: `SEED + 10000 + r`

---

## 3. Capture-Spezifikation (bindend vor Implementierung)

Für jeden der 5 Kandidaten:

- Event-Signaturen / Contract-Adressen pro Chain
- Zeitfenster identisch zu Stufe A/v2 (sofern nicht anders präregistriert)
- Normalisierung auf 1-min Raster und Join-Regeln
- Qualitätsschwellen (Coverage, Missingness, Fallback-Regeln)

### 3.0 Chainlink-Adressauflösung (harte Vorstufe)

`AnswerUpdated(int256,uint256,uint256)` wird bei Chainlink vom
**Aggregator-Implementierungsvertrag** emittiert, nicht vom Proxy.
Ein `eth_getLogs` nur auf Proxy-Adressen kann daher null Events liefern.

Bindende Regel für Chainlink-Capture:

1. pro Feed/Chain zunächst Proxy-Adresse erfassen (autoritative Feed-Liste),
2. on-chain Auflösung aktueller und historischer Aggregatoren via
   `aggregator()` plus `phaseAggregators(phaseId)` über alle im 90-Tage-Fenster
   relevanten Phasen,
3. Capture läuft auf der Vereinigung aller im Fenster aktiven Aggregator-Adressen.

Ohne abgeschlossene Proxy→Aggregator-Auflösung startet kein Chainlink-Capture.

### 3.0.1 Feed-Zustands-Taxonomie (Gate)

| Zustand | Bedeutung | Gate-Wirkung |
|---|---|---|
| `verified` | Proxy verifiziert (`docs_verified=true`, `docs_source`, Datum) | testbar, kein Blocker |
| `missing_candidate` | Adresse noch nicht beschafft | **Blocker** |
| `excluded` | dokumentierter Verzicht (`adaptation_reason` + Pre-Reg-Verweis) | `V3_UNTESTBAR`, kein Blocker, sichtbar im Report |
| `substituted` | ersetzt durch anderen Feed (z. B. WBTC→BTC) | Substitut muss `verified` sein |

**Dokumentierte Exclusions (Chainlink-Feedliste):**

- **GNO/USD auf Ethereum Mainnet:** kein öffentlicher Standard-Chainlink-Aggregator;
  Feed bleibt in der Liste mit `status=excluded`, Capture nur auf Gnosis Chain.
- **USDT/USD auf Gnosis Chain:** kein öffentlicher Standard-Chainlink-Feed;
  Feed bleibt in der Liste mit `status=excluded`.
- **GNO/USD auf Gnosis Chain:** öffentlicher Feed vorhanden (`verified`).

**Exclusion: USDT/USD Ethereum (Feed-strikt, nach Capture):**

- **Feed:** USDT/USD
- **Chain:** ethereum
- **Status:** `excluded` (`V3_UNTESTBAR` für diesen Feed)
- **adaptation_reason:** N=90 Events im 90-Tage-Fenster, unter der präregistrierten
  N≥100-Schwelle **pro Feed**. Tages-Coverage ist 1.0 (90/90 Tage); das harte
  N-Gate ist nicht erfüllt. Entscheidung: Feed-strikt-Exclusion, **kein**
  Ausschluss der Kandidatenklasse Chainlink.
- **docs_source:** `docs/BRIDGE_STUFE_A_V3_PREREG.md` §3.0.1;
  Coverage-Deskriptiva in `bridge_stufe_a_v3_chainlink.jsonl.manifest.json`
- **blocks_release:** false
- **Entscheidungsdatum:** 2026-08-20

Chainlink als Kandidatenklasse bleibt `TESTBAR` (N=12 199, Coverage=1.0).
In den Konditionierungssatz gehen die verbleibenden **8 Feeds** (ETH/BTC/WBTC/USDC
auf Ethereum; ETH/WBTC/USDC/GNO auf Gnosis). USDT/USD Ethereum bleibt in der
Capture-Datei sichtbar, wird aber nicht als `Z_neu`-Occupancy verwendet.

**Wichtige Ergänzung (Verifikationsschichten):**

1. **Schicht A (Quelle):** Proxy-Adressen müssen aus autoritativer Feed-Quelle
   verifiziert sein (Chainlink Feed-Adressverzeichnis je Chain).
2. **Schicht B (On-chain):** Resolver prüft Proxy→Aggregator-Auflösung
   (`aggregator()`, `phaseAggregators`).
3. **Schicht C (Plausibilität):** pro aufgelöstem Aggregator wird
   `latestRoundData()` auf semantische Feed-Passung geprüft
   (Preisgröße zur Feed-Bezeichnung konsistent).

Die Resolver-Prüfung allein reicht nicht gegen den Fall
„korrekter Chainlink-Proxy, aber falscher Feed“. Bei Scheitern von A oder C:
Abbruch und `V3_UNTESTBAR` für den betroffenen Feed/Kandidaten.

**Bindende Plausibilitätsbänder** (`latestRoundData`, USD-Skala):

| Feed | Plausibilitätsband |
|---|---|
| ETH/USD | `10^2 .. 10^4` USD |
| WBTC/USD | `10^3 .. 10^6` USD |
| BTC/USD | `10^3 .. 10^6` USD |
| USDC/USD | `0.9 .. 1.1` USD |
| USDT/USD | `0.9 .. 1.1` USD |
| GNO/USD | `10^0 .. 10^3` USD |

Die Bänder sind absichtlich grob und dienen nur zum Fangen von
„richtiger Proxy-Typ, falscher Feed“, nicht zur Marktvalidierung.

### 3.0.2 Liquidationen-Adressverifikation (Aave v3 / Spark)

Analog zu §3.0, mit angepasster Schicht B: `LiquidationCall` wird vom
**Pool-Proxy** emittiert (Delegatecall im Proxy-Kontext). Keine Aggregator-
oder Phasen-Auflösung.

Event-Signatur (Topic0 im Skript per keccak, nicht hardcodiert):

`LiquidationCall(address,address,address,uint256,uint256,address,bool)`

| Schicht | Chainlink (§3.0) | Liquidationen |
|---|---|---|
| A — Quelle | docs.chain.link | Aave Address Book / Spark Address Registry |
| B — On-chain | Proxy → Aggregator + Phasen | `getReservesList()` am Pool (nicht leer) |
| C — Plausibilität | `latestRoundData()` im Band | Smoke: Pool emittiert `LiquidationCall` (kein hartes N vor Capture) |

Ohne abgeschlossene Schicht A+B startet kein Liquidationen-Capture.
Fehlende oder unreproduzierbare Pools: `missing_candidate` (Blocker) oder
dokumentiertes `excluded`. Capture-Adressen sind die Pool-Proxies.

**Verifizierte Pool-Proxies (Schicht A, 2026-08-20):**

| Protokoll | Chain | Pool-Proxy | Quelle |
|---|---|---|---|
| Aave v3 | ethereum | `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2` | Aave Address Book `AaveV3Ethereum.POOL` |
| Aave v3 | gnosis | `0xb50201558B00496A145fE76f7424749556E326D8` | Aave Address Book `AaveV3Gnosis.POOL` |
| Spark | ethereum | `0xC13e21B648A5Ee794902342038FF3aDAB66BE987` | Spark Address Registry `SparkLend.POOL` |
| Spark | gnosis | `0x2Dae5307c5E3FD1CF5A72Cb6F698f915860607e0` | Spark Address Registry `Gnosis.POOL` |

Coverage nach Capture: ≥40 % der Tage mit ≥1 Event; N≥100 auf **Kandidaten-Ebene**
(alle Pools zusammen). Unter Schwelle: `V3_UNTESTBAR` für den Kandidaten Liquidationen.

### 3.0.3 Intent-Relayers (Across + CoW)

**Primärprotokolle:** Across V3 SpokePool-Fills und CoW `Trade`.  
**Chains:** nur Treatment ETH + Gnosis. Arbitrum wird nicht erfasst
(Kontrolle, nicht Teil von `Z_neu`).

**Join:** eine Occupancy-Serie, OR in der Minute über alle erfassten
Fill-/Trade-Events (Across ETH ∪ CoW ETH ∪ CoW Gnosis).

**Coverage (unverändert §3.1):** ≥60 % der Tage; N≥100 auf Kandidaten-Ebene.

| Schicht | Methode |
|---|---|
| A — Quelle | Across `deployed-addresses.json` / CoW CREATE2-Docs |
| B — On-chain | Across: `numberOfDeposits()`; CoW: `vaultRelayer()` ≠ 0 |
| C — Smoke | Events im Fenster (kein hartes N vor Capture) |

**Across Fill-Events** (V3SpokePoolInterface, 2026-08-20):

Aktuelles Fill-Event:

`FilledRelay(bytes32,bytes32,uint256,uint256,uint256,uint256,uint256,uint32,uint32,bytes32,bytes32,bytes32,bytes32,bytes32,(bytes32,bytes32,uint256,uint8))`

Legacy (ABI noch enthalten, für Fenster-Vollständigkeit mit erfasst):

`FilledV3Relay(address,address,uint256,uint256,uint256,uint256,uint32,uint32,uint32,address,address,address,address,bytes,(address,bytes,uint256,uint8))`

Topic0 im Skript per keccak, nicht hardcodiert. Occupancy: OR beider Events.

**CoW Trade** (GPv2Settlement.sol; IERC20 = address):

`Trade(address,address,address,uint256,uint256,uint256,bytes)`

Nur `owner` ist indexed. Die vorläufige Signatur mit extra `uint256` und
`bytes32` ist **falsch** und wird nicht verwendet.

**Verifizierte Adressen (Schicht A, 2026-08-20):**

| Protokoll | Chain | Adresse | Quelle |
|---|---|---|---|
| Across SpokePool | ethereum | `0x5c7BCd6E7De5423a257D81B442095A1a6ced35C5` | Across `broadcast/deployed-addresses.json` chain 1 |
| Across SpokePool | gnosis | — | **excluded** |
| CoW GPv2Settlement | ethereum | `0x9008D19f58AAbD9eD0D60971565AA8510560ab41` | docs.cow.fi CREATE2, identisch auf Gnosis |
| CoW GPv2Settlement | gnosis | `0x9008D19f58AAbD9eD0D60971565AA8510560ab41` | docs.cow.fi / gnosisscan |

**Exclusion: Across auf Gnosis.** Offizielle Across-Deployment-JSON
(`legacy-addresses.json` und `deployed-addresses.json`) enthält keine
SpokePool für Chain-ID 100. Kein stilles Weglassen.

**Dokumentierte Einschränkung (Interpretation, nicht Capture-Blocker):**
Across verbindet Ethereum nicht mit Gnosis. Als Cross-Chain-Intent-Protokoll
kann Across daher **kein direkter gemeinsamer Treiber** der ETH↔Gnosis-Beziehung
sein. Die Cross-Chain-Komponente des Kandidaten trägt **CoW** (Settlement auf
beiden Treatment-Chains). Die kombinierte Occupancy (Across-Fills auf ETH ∪
CoW-Trades auf ETH und Gnosis) bleibt ein valider Test der Hypothese
„Intent-Relayers als gemeinsamer Treiber“. Falls der Kandidat die Kopplung
nicht auflöst, liegt das **nicht** an der fehlenden Across-SpokePool auf
Gnosis, sondern daran, dass Intent-Aktivität insgesamt kein ausreichender
Treiber ist.

**Exclusion: LayerZero.** Generisches Messaging ohne Intent-Fill-Event.
`PayloadDelivered` ist kein Across/CoW-Fill. Intent-Logik läge in
Anwendungen (z. B. Stargate), die separat zu spezifizieren wären.
`blocks_release: false`.

### 3.0.4 Stablecoin Mint/Burn & Peg-Arb (PSM + CCTP)

**Primärprotokolle:** Maker/Sky LitePSM (+ Classic PSM OR), Circle CCTP V1+V2.  
**FiatToken** (USDC/USDT Emittenten-Mint/Burn): **EXCLUDED** — institutionell,
selten, nicht Pre-Reg-Primärprotokoll.  
**Chains:** nur Ethereum. Gnosis: keine PSM-/CCTP-Deployments (s. u.).

**Join:** eine Occupancy-Serie, OR in der Minute über alle erfassten Events
(LitePSM ∪ Classic PSM ∪ CCTP V1 ∪ CCTP V2 auf ETH).

**Coverage (unverändert §3.1):** ≥60 % der Tage; N≥100 auf Kandidaten-Ebene.

| Schicht | Methode |
|---|---|
| A — Quelle | MakerDAO/Spark Docs, Circle CCTP Contract Addresses / Domains |
| B — On-chain | LitePSM/`gem()`; Classic/`gemJoin()`; CCTP/`localMessageTransmitter()` |
| C — Smoke | Events im Fenster (kein hartes N vor Capture) |

**PSM-Events** (dss-psm / DssLitePsm ABI, 2026-08-20):

`BuyGem(address,uint256,uint256)`  
`SellGem(address,uint256,uint256)`

Nur `owner` indexed. Die vorläufige Signatur mit extra `uint256` und
`BuyGEM`-Schreibweise ist **falsch** und wird nicht verwendet.

**CCTP V1** (TokenMessenger):

`DepositForBurn(uint64,address,uint256,address,bytes32,uint32,bytes32,bytes32)`  
`MintAndWithdraw(address,uint256,address)`

**CCTP V2** (TokenMessengerV2 / BaseTokenMessenger):

`DepositForBurn(address,uint256,address,bytes32,uint32,bytes32,bytes32,uint256,uint32,bytes)`  
`MintAndWithdraw(address,uint256,address,uint256)`

Topic0 im Skript per keccak. Capture auf **TokenMessenger**, nicht
MessageTransmitter. Occupancy: OR aller PSM- und CCTP-Events.

**Verifizierte Adressen (Schicht A, 2026-08-20):**

| Protokoll | Chain | Adresse | Quelle |
|---|---|---|---|
| LitePSM USDC | ethereum | `0xf6e72Db5454dd049d0788e411b06CfAF16853042` | Spark/Sky LitePSM Docs |
| Classic MCD PSM USDC-A | ethereum | `0x89B78CfA322F6C5dE0aBcEecab66Aee45393cC5A` | MakerDAO dss-psm README |
| CCTP V1 TokenMessenger | ethereum | `0xBd3fa81B58Ba92a82136038B25aDec7066af3155` | developers.circle.com CCTP V1 |
| CCTP V2 TokenMessengerV2 | ethereum | `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d` | developers.circle.com CCTP addresses |
| PSM / CCTP | gnosis | — | **excluded** |

**Exclusion: Gnosis (PSM + CCTP).** Weder Maker/Spark PSM noch Circle CCTP
haben eine Gnosis-Deployment (PSM: keine Docs-Adresse; CCTP: Gnosis fehlt in
Supported Domains). Kein stilles Weglassen.

**Dokumentierte Einschränkung (Interpretation, nicht Capture-Blocker):**
Der Kandidat ist **ETH-only**. Er testet eine abgeschwächte Form der
Gemeinsamer-Treiber-Hypothese: Stablecoin-Aktivität auf Ethereum als Korrelat
der Marktbedingungen, nicht als direkter Gnosis-Treiber. Falls der Kandidat
die Kopplung nicht auflöst, liegt das **nicht** an einem Capture-Fehler,
sondern an dieser methodischen Einschränkung.

**Exclusion: FiatToken.** Emittenten-Mint/Burn (Circle/Tether) ist primär
institutionell und nicht Teil der Pre-Reg-Primärprotokolle.
`blocks_release: false`.

### 3.0.5 MEV-Cluster (Cross-Chain-EOA, gleiche UTC-Minute)

**Kein Protokoll-Capture.** Adress-basiert: `tx.from` erfolgreicher Top-Level-TXs
auf ETH und Gnosis. Arbitrum: **excluded** (Kontrolle).

**Operationalisierung „aktiv“:** nur `status=1`; alle TX-Typen; nur `tx.from`;
keine internen Traces. Adressen lowercase.

**Δt:** gleiche UTC-Minute (`t // 60`), konsistent mit Occupancy der anderen
Kandidaten. Approximation von |Δt|≤60 s — Minuten-Grenzartefakt ist bekannt und
deterministisch.

**Occupancy:** Minute M occupied, wenn ≥1 Adresse A existiert mit Aktivität auf
ETH und Gnosis in M, A ist EOA (`eth_getCode == 0x`), A nicht in der
präregistrierten Ausschlussliste.

**N-Gate:** ≥100 **occupied Minutes** (JSONL: eine Zeile pro occupied Minute).
Coverage (≥70 % der Tage) unverändert §3.1.

| Schicht | Methode |
|---|---|
| A — Quelle | RPC `eth_getBlockByNumber` / Receipts; Ausschlussliste Docs |
| B — RPC/Smoke | Batch-Probe, Receipt-Methode, Stichprobe tx.from/status/timestamp |
| C — Plausibilität | TX-Volumen in Größenordnung der Chain-Aktivität |

**Capture:** `eth_getBlockByNumber(full)` + Erfolgsfilter via Block-Receipts
(`eth_getBlockReceipts` bevorzugt). JSON-RPC-Batch, Chunking, Checkpoint/Resume.
Streaming (SQLite-Aktivitätstabelle), kein Vollspeicher aller TXs.

**Ausschlussliste (präregistriert):** OmniBridge/AMB/xDAI-Bridge, Across, CoW,
CCTP, PSM, Aave/Spark-Pools, Chainlink Proxies/Aggregatoren (aus Resolved),
Zero-Address — `config/bridge_stufe_a_v3_mev_cluster_exclusion_list.json`.

**EOA-Filter:** zweistufig — erst Cross-Chain-Kandidaten, dann `eth_getCode`.

### 3.1 Coverage-Gates (vor erstem CTE-Blick)

Coverage wird **vor** jeder CTE-/Kollaps-Auswertung geprüft. Kandidaten unter
Schwelle werden als `V3_UNTESTBAR` markiert und **vorab** aus der 310er-Matrix
entfernt. Die FDR-Familie läuft dann über die verbleibende, vor CTE-Blick
feststehende Matrix.

| Kandidat | Mindest-Coverage | Operationalisierung |
|---|---|---|
| Chainlink | ≥ 80 % der Tage | pro Feed und Chain: ≥ 1 `AnswerUpdated` |
| Intent-Relayers | ≥ 60 % der Tage | ≥ 1 Event/Tag |
| Liquidationen | ≥ 40 % der Tage | ≥ 1 Event/Tag |
| Stablecoin Mint/Burn | ≥ 60 % der Tage | ≥ 1 Event/Tag |
| MEV-Cluster | ≥ 70 % der Tage | ≥ 1 Cross-Chain-EOA/Tag |

Zusätzlich (hartes N-Gate): testbar nur bei `N_events >= 100` je Kandidat und
Richtungspfad im 90-Tage-Fenster. Kandidaten mit 1–99 Events sind `V3_UNTESTBAR`.

**Chainlink, Feed-strikt (zusätzlich zur Klassen-Schwelle):** ein einzelner Feed
mit N<100 bei sonst erfüllter Tages-Coverage wird `excluded` / `V3_UNTESTBAR`
für diesen Feed (siehe USDT/USD Ethereum in §3.0.1). Die Klasse bleibt testbar,
wenn die verbleibenden Feeds die Klassen-Schwellen erfüllen.

### 3.2 Zero-Event-Regel

Hat ein Kandidat im gesamten 90-Tage-Fenster **0 Events**, wird er automatisch
als `V3_UNTESTBAR` markiert. Keine Sonderbehandlung, kein Imputing.

### 3.3 Exakte technische Spezifikation

Vor Status „bindend“ müssen im Spec ergänzt sein:

- exakte Event-Signaturen je Kandidat
- exakte Vertragsadressen je Chain
- CTE-Schätzung: Binning-Methode, Anzahl Bins, Diskretisierung aller `Z`-Variablen
- Join-Regeln für mehrere Feeds / mehrere Contracts je Kandidatenklasse
- Interaktionsregel der Kandidaten (`einzeln` vs `gemeinsam`) als Primär-/Sensitivitätspfad

**Startreihenfolge (operativ):**

1. Chainlink-Capture (risikoärmster Einstieg)
2. Restliche Kandidaten-Captures gemäß finaler Kandidatenliste

Kein produktives Capture-Skript vor Bindung dieser Pre-Reg.

---

## 4. Entscheidungsregel (bindend)

Ein Kandidat gilt als „erklärend“ nur, wenn alle vorab festgelegten Bedingungen erfüllt sind:

1. global FDR-korrigierte Lag-Signale bestehen den Schwellenpfad,
2. **Kollaps** ist eindeutig definiert als:
   - nach Konditionierung auf den Kandidaten gilt bei globaler BH-FDR mit
     `q = 0.05` über die 310er-Familie: **kein** Lag des Treatment-Signals
     bleibt signifikant
   - Richtungsanforderung ist strikt bidirektional: **ab UND ba** ohne
     signifikanten Treatment-Lag
   - `S(τ)` ist **kein Filter** für den Kollaps-Test; `S(τ)` dient nur der
     Interpretation/Priorisierung nach der globalen Entscheidung
   - `ΔCTE` wird zusätzlich deskriptiv berichtet, ist aber nicht Teil der
     Kollaps-Entscheidung
3. Ergebnis ist im Primärpfad und Sensitivitätspfad konsistent.

Fehlt eine Bedingung, wird kein Treiber behauptet.

### 4.1 Across-Kandidaten-Interpretation

- **`V3_UNTESTBAR`**: Kandidat scheitert am Coverage-/Zero-Event-Gate
- **`V3_PERSISTENZ`**: keiner der testbaren Kandidaten verursacht Kollaps
- **Einzel-Kollaps**: genau ein testbarer Kandidat verursacht Kollaps
- **Mehrfach-Kollaps**: mehrere testbare Kandidaten verursachen Kollaps → Tie-Break §1.4

### 4.2 Kandidaten-Interaktion (verbindlich)

- **Primärverfahren:** jeder Kandidat wird **separat** getestet  
  `CTE(X→Y | Z_alt ∪ Z_kandidat_i)`, `i = 1..5`
- **Sensitivitäts-Check:** gemeinsamer Konditionierungstest aller testbaren Kandidaten  
  `CTE(X→Y | Z_alt ∪ Z_kandidat_1..n)`
- Der Sensitivitäts-Check überschreibt das Primärverdict nicht; er wird
  separat berichtet.

### 4.3 CTE-Estimator und Alignment (verbindlich)

- CTE-Estimator (explizit): frequenzbasierte/plugin-CTE über bedingte
  Shannon-Entropien der diskretisierten Zeitreihen, analog Stufe A
  (`transfer_entropy_binary`)
- Zeitraster: 1 Minute
- Diskretisierung:
  - `Y_t`, `Y_{t-1}`, `X_{t-τ}` als binäre Occupancy (0/1)
  - `Z_alt` und `Z_neu` quantilbasiert in 3 Tertile-Bins je Variable
- Join/Alignment:
  - Mehrere Kandidaten-Events in einer Minute → Occupancy=1 (keine Mehrfachzählung)
  - Kein Kandidaten-Event in einer Minute → Occupancy=0
  - Fehlende Treiberwerte werden per Stufe-A-Regel behandelt (kurze Lückeninterpolation,
    sonst Missing-Gate), vor CTE-Lauf geprüft.

---

## 5. Was diese Pre-Reg explizit nicht tut

- Keine rückwirkende Änderung von Stufe A / v2
- Keine Kandidatenauswahl anhand bereits gesehener Lag-Kurven
- Keine Ex-post-Anpassung von Blocklängen, Schwellen oder FDR-Familie
- Kein Hinzufügen weiterer Kandidaten im Persistenz-Fall

---

## 6. Bindungs-Checkliste

Alle Punkte müssen erfüllt sein vor Statuswechsel auf **bindend**:

- [ ] 1. Event-Signaturen und Vertragsadressen für alle 5 Kandidaten exakt spezifiziert
- [ ] 2. CTE-Schätzer explizit benannt (Diskretisierung + Entropie-Methode)
- [ ] 3. Join-Regeln für Mehrfach-Events und Null-Events pro Minuten-Raster dokumentiert
- [ ] 4. Coverage-Gates und `N_events`-Schwellen (`>=100` / `1..99` / `0`) fixiert; Prüfung vor erstem CTE-Blick
- [ ] 5. Kollaps-Definition final: `ab` **UND** `ba`, globale BH-FDR `q=0.05` über 310 Tests, `ΔCTE` nur deskriptiv
- [ ] 6. Tie-Break-Reihenfolge fixiert: `ΔCTE` (alle 31 Lags) → Fold-Robustheit → frühester Peak-Lag
- [ ] 7. Determinismus vollständig: Seed-Verwendung + Library-Version-Pinning dokumentiert
- [ ] 8. Kein Capture gestartet vor Statuswechsel auf **bindend**

