# Agent X — Klasse A: Konsensus & Epochen-Netzwerkdaten (Determinismus)

**Stand:** 01.08.2026 | **Typ:** Architektur-Spezifikation | **Status:** Entwurf

## Übersicht

Klasse A liefert **deterministische, protokollgetriebene Rahmenbedingungen** für die DeFi-Agenten (Klasse B & C). Während DeFi-Events stochastische, von Nutzerinteraktionen getriebene Signale sind, beantwortet Klasse A: *„Wie sicher, wie schnell und wie vorhersagbar ist das Netzwerk gerade, in dem meine DeFi-Transaktion stattfinden wird?“*

**9 Primäragenten, 27 Subagenten, 3 Cluster.**

---

## Bridge zu den DeFi-Agenten (Klasse B & C)

| Quelle | Ziel | Signal |
|--------|------|--------|
| A3-1 (Timing-Forecaster) | C2 (Arbitrage) | Exakte Slot-Zeiten für optimalen Tx-Broadcast |
| A2-3 (Churn-Predictor) | B2 (Lending-Risiko) | Warnung bei Validator-Exodus → Health-Factor-Impact |
| A3-2 (Health-Classifier) | C2 (Flash-Loan) | Deaktiviert Flash-Loan-Analyse bei Reorg/Finalitätsverzögerung |

---

## Cluster A1: Rohdaten-Beschaffung & Synchronisation (Ingestion)

### Agent A1-1: Beacon-Chain-Listener (Ethereum)
- Verbindung zum Beacon-Node (REST/SSE), Echtzeit-Events: `block`, `attestation`, `finalized_checkpoint`, `chain_reorg`
- **A1-1a** Block-Proposal-Sub: Filtert neue Blöcke, extrahiert `proposer_index` + Slot-Zeit
- **A1-1b** Attestation-Sub: Sammelt Attestationen → Partizipationsrate
- **A1-1c** Reorg-Detektor: Überwacht `chain_reorg`-Events, dokumentiert Reorg-Tiefe

### Agent A1-2: Solana-Leader-Schedule-Fetcher
- Lädt Leader-Schedule für 432.000 Slots (≈2–3 Tage), tracked aktuellen Slot-Index
- **A1-2a** Schedule-Parser: Pubkeys & Slot-Indizes → sortierte Zeitleiste
- **A1-2b** Slot-Progress-Tracker: Gleicht aktuellen Slot mit designiertem Leader ab
- **A1-2c** Skip-Rate-Monitor: Erkennt Skipped Slots, dokumentiert Ausfälle

### Agent A1-3: Validator-Exit- & Queue-Monitor
- Beobachtet Entry/Exit-Queues der Beacon-Chain
- **A1-3a** Exit-Queue-Rechner: `exit_queue_position` + `churn_limit` → Wartezeit in min/h
- **A1-3b** Activation-Queue-Rechner: Gleiches für neue Validatoren
- **A1-3c** Total-Active-Historian: Historischer Verlauf aktiver Validator-Anzahl

---

## Cluster A2: Zustandsanalyse & Deterministische Metriken (State & Analytics)

### Agent A2-1: Slot- & Epochen-Performance-Analyst
- Verdichtet Attestationen & Blöcke pro Epoche (384s) zu KPIs
- **A2-1a** Finality-Checker: Wurde Epoche innerhalb erwarteter Slots finalisiert?
- **A2-1b** Proposer-Effectiveness: Gefüllte vs. zugewiesene Slots pro Validator
- **A2-1c** Epoch-Aggregator: `EpochSummary`-Objekt (Partizipation, Missed Blocks, Reorgs)

### Agent A2-2: Sync-Committee- & Rotations-Tracker
- Sync-Committees wechseln alle 256 Epochen (≈27h), essenziell für Light Clients & Bridges
- **A2-2a** Committee-Rotation-Alarm: Countdown + Alert 1h vor Wechsel
- **A2-2b** Active-Member-Mapper: 512/1024 Validator-Pubkeys im Speicher
- **A2-2c** Light-Client-Simulator: Nächstes Light-Client-Update timen

### Agent A2-3: Staking-Flow- & Churn-Prädiktor
- Trägheitssensor des Netzwerks — Exit-Spike = Klasse-C-Punktprozess-Signal
- **A2-3a** Exit-Volumen-Spike-Detektor: 2-Sigma über 24h-Durchschnitt → Alarm
- **A2-3b** Entry-Time-Estimator: Vorhersage Aktivierungszeitpunkt neuer Validatoren
- **A2-3c** Netto-Staking-Delta: Entries − Exits pro Epoche

---

## Cluster A3: Strategische Timing- & Gesundheits-Signale (Output für SymbolicsAgent)

### Agent A3-1: Proposer- & Leader-Schedule-Forecaster
- *„Wer produziert in 30s den nächsten Block, und wer in 3min auf Solana?“*
- **A3-1a** ETH-Block-Timing-Predictor: UNIX-Timestamps der nächsten 64 Slots (≈12,8min)
- **A3-1b** Solana-Leader-Mapper: Aktuelle + nächste 100 Slots → Validator-Pubkeys
- **A3-1c** Cross-Chain-Overlap-Detector: Zeitfenster für atomare Cross-Chain-Arbitrage

### Agent A3-2: Netzwerk-Gesundheits- & Stress-Klassifizierer
- Fasst alle Metriken zum **Consensus Health Index (0–100)** zusammen
- **A3-2a** Validator-Churn-Stress: Exit-Queue > 1000 → hohe Punktzahl
- **A3-2b** Network-Participation-Grade: Normal > 95%; darunter = Warnsignal
- **A3-2c** Finality-Risk-Score: Wahrscheinlichkeit nicht-finalisierter Epoche

### Agent A3-3: Deterministic Order-Routing-Optimizer
- Nutzt Leader-Schedules zur Minimierung von Frontrunning/Sandwiching
- **A3-3a** Lowest-Latency-Slot-Finder: Nächster Slot mit vertrauenswürdigem/MEV-neutralem Validator
- **A3-3b** Builder-Connection-Broker: Verbindung zu MEV-Buildern nur zu optimalen Zeitpunkten
- **A3-3c** Tx-Dispatch-Optimizer: Konkrete Sendeempfehlung (Slot-Nummer + Zeit)

---

## Zusammenfassung aller 9 Agenten

| # | Agent | Cluster | Rolle | Subs |
|---|-------|---------|-------|------|
| A1-1 | Beacon-Chain-Listener | A1 Ingestion | ETH-Konsensus-Events | 3 |
| A1-2 | Solana-Schedule-Fetcher | A1 Ingestion | Leader-Schedule | 3 |
| A1-3 | Exit-Queue-Monitor | A1 Ingestion | Validator-Queues | 3 |
| A2-1 | Slot-Performance-Analyst | A2 Analytics | Epochen-KPIs | 3 |
| A2-2 | Sync-Committee-Tracker | A2 Analytics | Komitee-Rotationen | 3 |
| A2-3 | Staking-Flow-Prädiktor | A2 Analytics | Trägheitssignale | 3 |
| A3-1 | Proposer-Forecaster | A3 Strategie | Block-Timings | 3 |
| A3-2 | Health-Klassifizierer | A3 Strategie | Stress-Index | 3 |
| A3-3 | Order-Routing-Optimizer | A3 Strategie | Sendezeitpunkte | 3 |

---

## Integriertes Szenario (Klasse A + B + C)

1. **A3-1** meldet: *„In 4s beginnt Slot 200, Validator mit niedrigem MEV-Extraktionsverhalten.“*
2. **C2** entdeckt zinslosen Flash-Loan auf Aave mit Preisverzerrung auf Uniswap V3.
3. **B2** bestätigt: Kreditpositionen außerhalb kritischer Liquidationszone.
4. **A3-3** empfiehlt: *„Sende Arbitrage-Tx jetzt in diesen Slot — max. Gewinn, kein Sandwich-Risk.“*

**Gesamtsystem:** 18 Primäragenten (9 Klasse A + 9 Klasse B/C) + 27 Subagenten. SymbolicsAgent als zentraler Orchestrator.
