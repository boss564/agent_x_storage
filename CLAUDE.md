# Agent X — Risk Management & B2G Procurement Platform

6-Klassen-Risikomanagement + 277-Agent B2G Public-Sector Procurement Engine (27 Hauptwellen × 9 + Wave 3.5 + 25 Compliance = 277).

## Overview

Two integrated systems sharing core infrastructure (SymbolicsAgent, Consensus Engine, Backtesting):

1. **Agent X Core** — DeFi risk management: 6 classes (A–F), 60+ agents, consensus-driven state evaluation with CHI (Composite Health Index), backtesting against 8 historical crisis scenarios.

2. **Agent X B2G** — Public-sector procurement: 243 agents (27 main waves × 9 + Wave 3.5 VOB/B + 25 compliance agents = 277 total) covering the complete lifecycle from GAEB tender receipt through VOB/B multi-installment payment, defect/dispute arbitration, BHO-compliant treasury reconciliation, GoBD archiving, multi-chain notarization, operations, user/project management with BundID SSO, a complete query & reporting layer, a **real-time macroeconomic engine** (Wave 17) with velocity tracking and programmable fiscal stimulus, a **VOB Shadow Contract & Pilot** (Wave 18) for risk-free blockchain adoption, a **Multi-Stakeholder Onboarding Ecosystem** (Wave 19) for craftsmen, builders, developers, IoT and banking partners, a **CertiK Security Audit & Formal Verification Engine** (Wave 20) with 81 subagents for mathematical proof, BSI C5/ISO 27001/SOC2 compliance, and real-time threat monitoring, through **Clearing & Settlement** (Wave 27) with multilateral netting and BHO zero-sum proofs, **External Threat Defense** (Wave 28) with swarm immunity and active countermeasures, **Omnichannel UX & Verwaltungs-Dashboard** (Wave 31) — the human interface for Kämmerer, Bauleiter, and citizens, and **Survival & Off-Grid Mode** (Wave 33) — sovereign post-quantum enclave with mesh networking, resource-backed economy, and air-gapped MPC bunkers.

## Agent X Core — Projektstruktur

```
agent_x_storage/
├── agent_x_orchestrator.py       # SymbolicsAgent: CHI, 5-Klassen-Fusion, Zeithorizont
├── agent_x_backtest.py           # 8 Szenarien, BlockSnapshot, Grade A-F
├── agent_x_aggregation.py        # Penalty-Aggregation (sum, max_damp, p_norm)
├── agent_x_metrics.py            # Prometheus Exporter (36+ Gauges)
├── agent_x_dashboard.py          # Live-Terminal-Dashboard
├── agent_x/                      # Analyse-Module
│   └── metrics/
│       └── compound_analyzer.py  # EWMA-Kalibrierungs-Analyzer
├── agents/                       # Core runtime (Surface/Subsurface/Security/Air)
│   └── air/                      # Air Interceptor Layer A01–A09: Soft-Finality, Transient-CAS, Poison-Neutralisierung, AWACS
├── agents_b2g/                   # B2G-Agenten (s.u. Wellen-Tabelle)
│   ├── protocol.py                # ABM-Kommunikationsprotokoll: BaseAgent, TickController, 18 Payload-Typen (485 L)
│   ├── bunker/                    # Bunker HSM Adapter — Dual-Mode (SoftHSM + NitroKey)
│   │   ├── __init__.py
│   │   └── hsm_adapter.py        # UnifiedPKCS11HSM: ECDSA-Signing, 76 L
│   ├── clearing/                 # Wave 27: Clearing & Settlement
│   │   ├── __init__.py
│   │   └── clearing_settlement_orchestrator.py  # 9+81 Subagenten
├── scripts/                      # Runner & Tests
│   ├── calibrate_agent_x.py      # Compound-Risk-Kalibrierung
│   ├── paper_trading_agent_x.py  # Paper-Trading mit Deep-Logging
│   ├── bootstrap_b2g.py          # B2G-Bootstrap
│   ├── end_to_end_90_agents.py   # 90-Agenten-11-Wellen-E2E-Test (11/11 passed, inkl. Wave 3.5)
│   ├── end_to_end_b2g_test.py    # 25-Schritte-E2E-Test
│   ├── test_gaeb_reference.py    # GAEB DA XML 3.3 Test Suite
│   ├── test_wave17_macro.py      # Wave 17 E2E: 8-Stufen-Makro-Pipeline (8/8 passed)
│   ├── fetch_xrechnung_schematron.py # XRechnung 3.0 Schematron Fetcher
│   ├── demo_finale.py             # Durchsatz-Benchmark mit BHO-Verletzungserkennung (179 L)
│   ├── demo_producer_cluster.py   # 27-Agenten-ABM: Provider/Evaluator/Economic (514 L)
│   ├── pitch_test.sh              # Pre-Pitch-Gate: BHO + Compliance Zero-Sum (failed_count==0), 7/7 quick
│   ├── test_air_layer.py          # Air Layer E2E A01–A09 + Chaos F07–F09 (18/18)
│   ├── test_esp32_firmware.py      # ESP32 Firmware Test Suite (15/15 passed)
│   ├── test_e2e_pipeline.py        # 6-Schichten-E2E (C01→P09→D05→Anvil)
│   └── verify_1m_tsunami.py        # 1M-Tsunami-Verifier (Zero-Loss + P99 + RSS + L1-Anker)
├── mock_d01_responder.py       # D01 Mock ZK Proof Responder (NATS + Anvil L1 anchor)
├── simchain_ingest.py          # Producer: 96k–115k events/s NATS load generator
│   └── export_backtest_signals.py # Backtest-Daten-Exporter
├── config/
│   ├── calibration_config.yaml   # Kalibrierungs-Konfiguration
│   ├── prometheus.yml            # Overwatch-Scrape (surface/d01/infantry, 1s)
│   └── grafana/                  # Overwatch-Dashboard-Provisioning
│       ├── datasources/prometheus.yml
│       └── dashboards/           # overwatch.json + provider.yml
├── archive_b2g/                  # GAEB-XML + GoBD-JSON + Pitch-Dokumente
│   ├── pitch_storyline.md         # Kämmerer-Pitch 0.24.0: „Das System, das sich selbst prüft", 5 Akte, ~4 Min (107 L)
│   ├── regulatory_roadmap.md      # B2G-Regulierungs-Roadmap (VOB/B, GoBD, eIDAS, MiCA), 224 L
│   └── tokenomics_model.md        # Drei-Token-Modell ($AGX/veAGX/EURe), Burn-Tabelle, 364 L
├── orchestrator_b2g_full.py      # 286-Agenten-Pipeline (alle Waves inkl. 3.5), 378 lines
├── orchestrator_b2g.py           # B2G-Tendering-Bootstrap
├── cli_b2g_query.py              # CLI für alle Wave-10-Query-Agenten
├── docker-compose.yml            # 90 Container + Infrastruktur, 654 lines
├── docker-compose.mock.yml         # 5-Bunker + Handwerker Mock-Stack, 161 L
├── Dockerfile.bunker               # MPC-Bunker Container (Python 3.11 + SoftHSM), 43 L
├── Dockerfile.dashboard            # Streamlit Dashboard Container, 39 L
├── Dockerfile.d01                  # D01 Mock ZK Responder Container (nats-py + web3), 8 L
├── Makefile                        # make pitch / make full-pitch / make test-all / make demo-* (15+ targets, 180 L)
├── tests/                          # MPC-Bunker Mock-Stack & Integrationstests
│   ├── mock_hsm.py                 # Mock NitroKey HSM 2: PKCS#11, MPC-Threshold (t=3,n=5), 357 L
│   ├── mock_lorawan.py             # Mock LoRa-Transceiver: UDP SX1262-Simulation, 204 L
│   ├── mock_handyman.py            # Mock Handwerker: CBOR-Pakete, Meilensteine, 276 L
│   ├── test_bunker_integration.py  # 18 Tests: HSM, LoRa, Handyman, E2E, 594 L
│   ├── test_bunker_e2e.py          # 27 PyTest E2E: 7 Test-Klassen, Docker-Fixture, 526 L
│   ├── test_hsm_adapter.py         # 6/6 Tests: HSM-Dual-Mode (SoftHSM + Hardware), 46 L
│   └── test_z3_integration.py      # 13 Tests: Z3-Kernel, HTTP, Orchestrator, IEEE-754, 268 L
├── services/                       # Microservices (FastAPI + Docker)
│   ├── __init__.py
│   ├── z3_solver/                  # Z3 Theorem Prover + BSI-Compliance Gate
│   │   ├── main.py                 # /prove_bho_invariant, /health, /compliance (681 L; gate/passed/failed_count, RPA-Triade, probe-promotion)
│   │   ├── Dockerfile.z3           # Python 3.11-slim + Z3-Binaries; Quellbaum :ro unter / gemountet (_ROOT=/)
│   │   └── requirements.txt        # fastapi, uvicorn, z3-solver, pydantic, 4 L
│   ├── multichain_api.py           # MultiChain REST API (10 endpoints), 374 L
│   ├── telemetry_ingest/           # MQTT/HTTP Bridge for ESP32 IoT sensors
│   │   ├── main.py                 # /telemetry/ingest, /flood, HW signature verification, 290 L
│   │   └── requirements.txt
│   └── chaos_matrix.py             # 10 Attack Scenarios × Z3 Intercept, 290 L
├── .github/                        # GitHub Actions CI/CD
│   └── workflows/
│       └── offgrid-test.yml        # 5 Jobs: Unit/Docker/Wave33/Contracts/Formal-Invariants, 310 L
├── firmware/                       # ESP32 Embedded Firmware
│   └── esp32_lorawan/               # LoRaWAN IoT Resource Oracle
│       ├── esp32_lorawan.ino         # Main: Boot, ADC-Read, CBOR, ECDSA, LoRa-TX (408 L)
│       ├── cbor_payload.h            # CBOR Encoder <150 Bytes (283 L)
│       ├── sig_engine.h              # ECDSA Engine ATECC608A + Soft-Fallback (378 L)
│       ├── sx1262_interface.h        # SX1262 LoRa Driver SPI (400 L)
│       ├── sensor_reader.h           # ADC/CT-Clamp Sensor Interface (182 L)
│       └── README.md                 # Build/Flash/Pin-Belegung
├── chaos/                          # Chaos Fleet (F07–F09): killer, throttler, poison injector
│   ├── docker-compose.chaos.yml    # 3 chaos services, docker.sock mounted
│   ├── Dockerfile.killer           # alpine + docker CLI, SIGKILL random worker
│   ├── Dockerfile.throttler        # ubuntu + stress-ng, CPU load 90%
│   ├── Dockerfile.poison           # golang multi-stage, constraint-bloat injector
│   ├── poison.go                   # 4.19M constraint bloat + 64KB junk payloads
│   └── scripts/                    # killer.sh, throttler.sh
├── shadow_contract_pilot/          # Smart Contracts & Pilot (Wave 18 + IoT Oracle)
│   ├── contract/                   # 8 Contracts: IoTVerifier, CommodityToken, ResourceTrader,
│   │                               # CommodityLedger, VOB_Shadow_Escrow, ComplianceVerifier,
│   │                               # ValhallaVerifier, ProtoGalaxyVerifier
│   ├── backend/pilot_backend.py    # 7 REST-Routen, Mock + Live-Modus
│   ├── dashboard/index.html        # Echtzeit-Dashboard (5s Polling)
│   └── test_lifecycle.py           # 25/25 Tests (Fund→Release→Retention)
├── foundry.toml                   # Foundry/Anvil Config (OpenZeppelin v5)
├── lib/openzeppelin-contracts/    # OpenZeppelin v5.0.0 (via Forge)
├── charts/agent-x/               # Helm-Chart: KEDA Autoscaling + SGX Limits (9 Dateien)
├── docs/                         # COMPLIANCE_PLAYBOOK.md (K1–K6) + asyncapi.yaml
├── event_bus.py                  # Pub/Sub + JSONL Audit-Log
├── gov_procurement_agent.py      # Root Orchestrator, BHO thresholds
├── tender_reader_agent.py        # GAEB-XML Reader
└── LOG.md                        # Entwicklungs-Log
```

### Agent X Core: Consensus Engine (4 Validators, 3/4 Threshold)

| Validator | Checks | Techniques |
|-----------|--------|------------|
| GoBD | 7 | XRechnung fields, DE tax ID, ISO 8601, ECDSA |
| Fraud Detection | 5 | Benford's Law (chi², p=0.05), Z-score (>3σ), round numbers, IQR |
| Plausibility | 5 | Price bounds, quantity ranges, unit consistency, net+vat=gross |
| Geofence + IoT | 4 | H3 cell matching, Haversine, time-window, peaq-DID |

**Zone boundaries:** 80/60/40 (healthy/caution/stressed/critical)
**Aggregation:** Additive sum (FN=0). Channel weights: c_liquidatable ×4/Cap 26, c_at_risk ×1.2/Cap 18.
**Configurable via env:** `LENDING_MULTIPLIER`, `LENDING_CAP`, `AT_RISK_MULTIPLIER`, `AT_RISK_CAP`, `AGGREGATION_METHOD`

### Backtesting

8 historical crisis scenarios (Terra, FTX, SVB, Bull Run, Flash Crash, Aave Rate Hike, ARB Unlock, Compound CF Change). 36 labeled blocks with `expected_global_state` ground truth.

**Result:** Score 90/100 (A), FN=0, FP=2, $2.325M profit saved.

## Agent X B2G — Public Sector Procurement

### Architecture: 27 Waves × 9 Agents = 243 Agents (+ Wave 3.5 VOB/B + 25 Compliance = 277 total)

```
Wave 1 (Tendering):        Monitor → Parser → Eligibility → CHI-Risk → PoPW-Index →
                            OfferCalculator → Composer → Deadline → BidSubmittal
Wave 2 (Composing):        Aggregator → PriceInjector → GapFiller → AnnexComposer →
                            X84Serializer → X84Validator → QESSigner → PlatformSubmitter →
                            SubmissionFinalizer
Wave 3 (Execution):        ContractActivation → PoPWCollector → ProgressVerification →
                            DeliveryOracle → QualityAssurance → InvoiceAggregator →
                            XRechnungGenerator → PaymentExecutor → SettlementFinalizer
Wave 3.5 (VOB/B):          InstallmentPlanner → ProgressSnapshot → PartialInvoice →
                            RetentionManager → DefectDetection → DisputeArbiter →
                            RemediationTracker → FinalSettlement → EscrowReconciliation
Wave 4 (Treasury):         SEPAGateway → EMIMinter → RetentionVault → InstallmentLedger →
                            BHOReconciler → PaymentRelease → SEPABurnDisburser →
                            TaxCompliance → FinalAuditCloser
Wave 5 (Telemetry):        GPSCollector → IoTScaleReader → PhotoEvidence → GeoFenceValidator →
                            ZKMerkleProver → TelemetryAggregator → PoPWProofGenerator →
                            SensorHealthCheck → TelemetryArchiver
Wave 6 (Invoicing/Audit):  XRechnung3Serializer → ZUGFeRDFormatter → InvoiceValidator →
                            GoBDArchiver → AuditTrailIndexer → TaxXMLExporter →
                            InvoiceDispatcher → PaymentMatcher → ArchiveFinalizer
Wave 7 (Operations):       OrchestratorAgent → HealthCheckAgent → LogAggregatorAgent →
                            MetricsCollectorAgent → AlertingAgent → DeadLetterHandlerAgent →
                            ConfigManagerAgent → BackupAgent → SelfHealingAgent
Wave 8 (Pilot/Production): OpsHealthAgent → DeadLetterRecoveryAgent → AuditExporterAgent →
                            TenderAPIGatewayAgent → UserNotificationAgent →
                            ComplianceReportAgent → MultiTenantIsolatorAgent →
                            SimulationTestAgent → PilotDashboardAgent
Wave 9 (User & Project):   UserAuthenticatorAgent → ProjectManagerAgent → TaskDispatcherAgent →
                            DocumentManagerAgent → NotificationCenterAgent →
                            ReportGeneratorAgent → ComplianceCheckerAgent →
                            DataPrivacyAgent → FeedbackCollectorAgent
Wave 10 (Query & Reports): VergabekammerQueryAgent → RPAQueryAgent →
                            ConstructionProgressQueryAgent → TreasuryQueryAgent →
                            ComplianceQueryAgent → ControllingQueryAgent →
                            OpsQueryAgent → PublicDataQueryAgent → LocalEconomyQueryAgent
Wave 15 (Public Portal):    PublicPortalOrchestrator → ProjectSummaryAggregator →
                            BlockchainVerificationWidget → QRCodeGenerator →
                            InteractiveMapComposer → ZKPrivacyShield →
                            TrustButtonService → CitizenNotificationService →
                            AuditTrailPublicExporter
Wave 16 (SEPA Bridge):      SEPABridgeOrchestrator → EUReMinterSubagent →
                            EUReBurnerSubagent → IBANValidatorSubagent →
                            SEPAAuditTrailSubagent → MoneriumAPIClientSubagent →
                            GasPaymasterSubagent → BridgeBalanceMonitorSubagent →
                            SEPAConfirmationSubagent
Wave 17 (MacroEconomy):     MacroEconomyOrchestrator → VelocityOfMoneyTracker →
                            RealTimeInflationOracle → SupplyChainMultiplierCalc →
                            ProgrammableStimulusEngine → RealTimeTaxSplitter →
                            CapitalEfficiencyAnalyzer → SystemicRiskAndCartelMonitor →
                            CentralBankLedgerTwin
Wave 18 (Shadow Contract):  ShadowContractOrchestrator → LifecycleStateEngine →
                            ShadowContractDeployer → PrivateClientBridge →
                            MilestoneConditionChecker → TaxSimulationAgent →
                            RetentionVaultManager → AuditorDashboardComposer →
                            PilotMetricsCollector → GovernmentOnboardingKit
Wave 19 (Ecosystem):        EcosystemOnboardingOrchestrator → CraftsmanOnboarding →
                            DeveloperOnboarding → BuilderOnboarding →
                            IoTPartnerOnboarding → BankingPartnerOnboarding →
                            ComplianceEnrollment → EcosystemHealthMonitor →
                            PartnerSuccessManager
Wave 20 (CertiK Security):  SmartContractStaticAnalyzer → AccessControlAndGovAuditor →
                            OracleAndDeFiDynamicsTester → L1L2InfrastructureAuditor →
                            FormalVerificationEngine → PenetrationAndFuzzingAgent →
                            C5AndBSIGovernmentCertifier → RealTimeThreatMonitor →
                            CertiKAuditReportComposer
Wave 21 (Skynet Monitor):   SkynetOrchestrator → CodeSecurityRatingAgent →
                            FundamentalHealthAgent → OperationalSecurityAgent →
                            MarketStabilityAgent → CommunityTrustAgent →
                            GovernanceStrengthAgent → SkynetRiskAlertEngine →
                            SkynetDashboardComposer
Wave 22 (Ops Security):     KeyVaultManager → GasOptimizer → NonceManager →
                            MetaTxEngine → AutotaskScheduler → WebhookIntegrator →
                            ConditionExecutor → DeployVerifier →
                            SecureDeployOrchestrator
Wave 23 (Token Launch):     TokenomicsArchitect → TokenContractDeployer →
                            VestingAndVaultManager → LiquidityPoolInitializer →
                            TokenGovernanceEngine → RegulatoryComplianceGuard →
                            AirdropAndClaimDistributor → TokenMetadataAndBranding →
                            TokenLaunchOrchestrator
Wave 24 (Trading):          DEXLiquidityRouter → AutomatedMarketMakerAgent →
                            LimitOrderBookEngine → MarketMakingStrategyAgent →
                            CrossChainSwapRelayer → MEVAndSlippageProtectionAgent →
                            GasOptimalTradeExecutor → FeeAndDividendDistributor →
                            TradingAnalyticsAndRiskMonitor
Wave 25 (Smart Wallet):     AccountAbstractionEngine → MultiSigAndSessionManager →
                            BHOZeroSumValidator → eIDASIdentityAndCompliance →
                            ZKPrivacyShield → CrossChainUnifiedTreasury →
                            IntentBasedTxSigner → SuccessionAndRecoveryManager →
                            GoBDSnapshotArchiver
Wave 27 (Clearing):         TransactionAccumulator → BilateralNettingEngine →
                            MultilateralNettingAggregator → SettlementPriorityQueue →
                            FinalSettlementDispatcher → SettlementVerificationOracle →
                            FiatGatewaySynchronizer → NettingEfficiencyTracker →
                            SettlementAuditArchiver
Wave 28 (Defense):          PerimeterGatewayDefender → SwarmDetectionRadar →
                            ThreatClassifierEngine → ActiveResponseCoordinator →
                            DeceptionAndHoneypotFactory → SwarmLearningAdapter →
                            ExternalIntelAggregator → DefenseMetricsDashboard →
                            DefenseOrchestrator
Wave 29 (Token Runtime):    ComputeFuelAuctioneer → SlashingAndPenaltyExecutor →
                            PriorityQueueAccessManager → DisputeBondEscrowAgent →
                            BuybackAndBurnRelayer → LiveYieldAndStakingOperator →
                            OracleDataFeeDispatcher → ERPQuotaAccessManager →
                            TokenRuntimeOrchestrator
Wave 31 (UX & Dashboard):   RoleBasedDashboardComposer → ResponsiveWebPortal →
                            NaturalLanguageAssistant → ProcessWorkflowVisualizer →
                            RealTimeAnalyticsHub → SandboxSimulationPlayer →
                            SmartAlertAndNotification → GoBDReportGenerator →
                            UXOrchestrator
Wave 32 (Philately):        StampMintAndIssuanceEngine → MessagePostageValidator →
                            CancellationAndPostmarkEngine → RarityAndEditionClassifier →
                            PhilatelicAlbumManager → SecondaryMarketTrader →
                            MuseumExhibitionCurator → StampStakingVault →
                            PhilatelyOrchestrator
Wave 33 (Survival):         PQC-DilithiumSigner → MPC-BunkerNodes → ZK-STARKCompressor →
                            LoRaWAN-MeshAgent → Peer-DiscoveryDHT → StateSyncRollup →
                            Resource-OracleIoT → ZK-eIDRationing → MultilateralClearing →
                            SurvivalOrchestrator
```

### Wellen-Übersicht

Welle 3.5 (VOB/B Disput) ist eine Unterwelle von Welle 3 (Execution) und wird nicht als eigenständige Hauptwelle gezählt. Die Gesamtzahl der Hauptwellen beträgt 27 (Wellen 1–10, 15–33). Die Wellen-Nummern 11–14, 26 und 30 existieren nicht.

| Welle | Name | Agenten | Modul | Fokus |
|-------|------|---------|-------|-------|
| 1 | Tendering-Engine | 9 | `tendering/agents.py` | GAEB-Parsing, CHI-Risk, PoPW-Bonus, Angebotskalkulation |
| 2 | Composing & QES | 9 | `composing/agents.py` | GAEB-X84, eIDAS-QES, Plattform-Upload |
| 3 | Execution & PoPW | 9 | `execution/agents.py` | Bauausführung, PoPW-Collector, XRechnung |
| 3.5 | VOB/B Disput | 9 | `execution/vob_extension.py` | Abschläge, 5% Einbehalt, Mängelrüge (14d), Minderung |
| 4 | Treasury & BHO | 9 | `treasury/agents.py` | SEPA, EURe, RetentionVault, BHO Zero-Sum (Δ=0,00€) |
| 5 | Telemetry & Verification | 9 | `telemetry/agents.py` | GPS, IoT-Waagen, Foto-Evidenz, ZK-Merkle-Proofs |
| 6 | Invoicing & Audit | 9 | (placeholder) | XRechnung 3.0, ZUGFeRD, GoBD-Archiv |
| 7 | Operations & Maintenance | 9 | `ops/agents.py` | Orchestrator, HealthCheck, Metrics, Alerting, SelfHealing |
| 8 | Pilot & Production | 9 | `ops/pilot_agents.py` | OpsHealth+CircuitBreaker, API-Gateway, Dashboard, GoBD-Export |
| 9 | User & Project Management | 9 | `user/agents.py` | BundID-SSO, Projekt-Lifecycle, DSGVO, Compliance (13 Regeln), NPS |
| 10 | Query & Reports | 9 | `query/agents.py` | RPA-Prüfberichte, Vergabekammer, Baufortschritt, Treasury, Ops, OpenData |
| 15 | Public Portal & Transparency | 9 | `public_portal/agents.py` | QR-Codes, Blockchain-Verifikation, Kommunalkarte, DSGVO-Shield, Open Data |
| 16 | Monerium SEPA-Bridge | 9 | `bridge/agents.py` | EURe Mint/Burn, IBAN/BZSt-Validierung, ERC-4337 Paymaster, Δ=0,00€ Bridge-Reconciliation |
| 17 | MacroEconomy Engine | 9 | `macro/macro_economy_orchestrator.py` | Velocity, Inflation, Multiplikator, Stimulus, Steuer, Kapitaleffizienz, Kartell, Zentralbank |
| 18 | Shadow Contract & Pilot | 9 | `shadow/shadow_contract_orchestrator.py` | VOB Shadow Escrow, IoT/ZK-Milestones, ELSTER-Steuer, Retention, RPA-Dashboard |
| 19 | Ecosystem Onboarding | 9 | `onboarding/ecosystem_onboarding_orchestrator.py` | Handwerker, Bauherren, Developer, IoT, Banken — 5 Rollen |
| 20 | CertiK Security Audit | 9 | `security/certik_audit_orchestrator.py` | Statische Analyse, Access Control, Oracle/DeFi, L1/L2, Formale Verifikation, Fuzzing, BSI C5/ISO 27001/SOC2/GDPR, Real-Time Threat, CertiK Zertifizierung (81 Subagenten) |
| 21 | Skynet Dynamic Monitor | 9 | `security/skynet_orchestrator.py` | 6-Säulen-Echtzeit-Score: Code, Fundamentales, Betrieb, Markt, Community, Governance — 54 Subagenten |
| 22 | Ops Security & Deploy | 9 | `ops/relay_orchestrator.py` | Key-Vault, Gas-Opt, Nonce, Meta-TX, Autotasks, Webhooks, Deploy-Verify, Multi-Sig-Deploy — 36 Subagenten |
| 23 | Token Creation & Launch | 9 | `tokenomics/token_launch_orchestrator.py` | Tokenomics, ERC-20-Deploy, Vesting, DEX-Liquidity, DAO-Governance, MiCAR/SEC-Compliance, Airdrop-Merkle-Claims, IPFS-Metadaten — 81 Subagenten |
| 24 | Trading Infrastructure | 9 | `trading/token_trading_orchestrator.py` | DEX-Routing, AMM-Tick-Management, Limit-Orders, Market-Making, Cross-Chain-Swaps, MEV-Schutz, Gas-Optimierung, Fee-Distribution, Circuit-Breaker |
| 25 | Smart Wallet & Identity | 9 | `wallet/smart_wallet_orchestrator.py` | ERC-4337, Multi-Sig, BHO-Kasse, eIDAS/BundID, ZK-Privacy, Cross-Chain-Treasury, Intent-Signer, Amtsübergabe, GoBD-Archiv — 81 Subagenten |
| 27 | Clearing & Settlement | 9 | `clearing/clearing_settlement_orchestrator.py` | Multilaterales Netting (100 TXs → 1 Netto-Zahlung), BHO-Zero-Sum, Z3-Proof, GoBD-WORM, Fiat-Gateway — 81 Subagenten |
| 28 | External Threat Defense | 9 | `defense/swarm_defense_orchestrator.py` | Perimeter-Schutz, Schwarm-Erkennung, Bedrohungsklassifizierung, Honeypot-Fallen, selbstlernende Abwehr, Threat-Intelligence — 81 Subagenten |
| 29 | Token Runtime Operations | 9 | `tokenomics/token_runtime_orchestrator.py` | Compute-Abrechnung, Slashing, Priority-Queue, Dispute-Bonds, Buyback/Burn, Live-Staking-Yields, Oracle-Entlohnung, ERP-Quota — 81 Subagenten |
| 31 | UX & Verwaltungs-Dashboard | 9 | `ux/ux_orchestrator.py` | 6 Rollen, Responsive (Mobile/Tablet/Desktop), Sprach-Assistent, Workflow-Visualisierung, Analytics, Sandbox-Simulationen, Smart Alerts, GoBD-Berichte — 81 Subagenten |
| 32 | Crypto-Philately & Digital Stamp | 9 | `philately/philately_orchestrator.py` | Briefmarken (ERC-1155), Poststempel, Seltenheitsbewertung, Sammelalben, Sekundärmarkt, Staking — 81 Subagenten |
| 33 | Survival & Off-Grid Post-Quantum | 9 | `survival/survival_orchestrator.py` | PQC (Dilithium-5/Kyber-1024/SPHINCS+), MPC-Bunker (t=3,n=5), ZK-STARKs, LoRaWAN/HAM/Sat-Mesh, Ressourcen-Clearing, ZK-eID-Rationierung, 180d Autarkie — 9 Subagenten |

Welle 34 (Finale Veredelung) ist ein Pitch-Orchestrator mit 3 Agenten + Streamlit-Dashboard und wird — analog zum Compliance-Modul — außerhalb der ×9-Formel dokumentiert.

| Welle | Name | Agenten | Modul | Fokus |
|-------|------|---------|-------|-------|
| 34 | Finale Veredelung (Pitch & Go-Live) | 1+3 | `finale/finale_orchestrator.py` | Dashboard (Streamlit+Plotly), GoBD-Audit-Trail, Realtime-Monitor, Z3-Live-Integration, Pitch-Summary — 1.876 lines, 21/21 Tests |
| 35 | SimChain Multi-Chain Economy | 9+27 | `simchain/economic_orchestrator_multi.py` | 3 Chains × 3 Agents, DePIN (1000 TPS), VOB/B Settlement (Z3-Proof), Liquidity (Token/Staking/Burn), Cross-Chain-Bridge, Friktion 5.6% (Burns+Fees), Staking separat, value_conserved verifiziert, drei getrennte Chain-Bücher, BHO Δ=0, 199/199 Tests — 2.200+ lines |
| 36 | MultiChain Sovereign Appchains | 9+27 | `multichain/chain_orchestrator.py` | 4 Chain Layers × 9 Sovereign Appchains, Merkle-Proof-Bridge, Identity Chain (SSI/ZK), Cross-Chain-Latenz, 113/113 Tests — 1.800+ lines |
| 37 | Demo Pipeline (Pitch & Investoren) | 9+27 | `demo/demo_orchestrator.py` | 3 Akte × 9 Agenten, Differenzierte Transformationsprofile, 8 einzigartige Friktions-Raten, Live-Proof-Mode, BHO Δ=0 — Pitch-fertig |

### B2G Module Structure

```
agents_b2g/
├── bunker/                        # Bunker HSM Adapter (Dual-Mode: SoftHSM + NitroKey)
│   ├── __init__.py
│   └── hsm_adapter.py            # UnifiedPKCS11HSM: ECDSA-Signing, 76 L
├── tendering/
│   └── agents.py                 # Wave 1: 9 agents, 741 lines
├── composing/
│   └── agents.py                 # Wave 2: 9 agents, 645 lines
├── execution/
│   ├── agents.py                 # Wave 3: 9 agents, 523 lines
│   ├── vob_extension.py          # Wave 3.5: 9 agents, 515 lines
│   ├── escrow_coordinator_agent.py
│   └── subagents/emi_bridge.py
├── treasury/
│   └── agents.py                 # Wave 4: 9 agents, 369 lines
├── telemetry/
│   └── agents.py                 # Wave 5: 9 agents, 472 lines
├── ops/
│   ├── agents.py                 # Wave 7: 9 agents + OpsSupervisor, 474 lines
│   ├── pilot_agents.py           # Wave 8: 9 agents + PilotSupervisor + ALL_AGENTS, 760 lines
│   └── relay_orchestrator.py     # Wave 22: 9 agents + 36 Subagenten, Key-Vault/Relay/Deploy
├── user/
│   ├── __init__.py               # Wave 9 exports
│   └── agents.py                 # Wave 9: 9 agents + UserSupervisor, 1.259 lines
├── query/
│   ├── __init__.py               # Wave 10 exports
│   ├── agents.py                 # Wave 10: 9 agents + QuerySupervisor, 844 lines
│   └── subagents/
│       ├── archive_query_subagent.py  # GoBD-JSONL archive search, 180 lines
│       └── pdf_composer.py           # PDF/A audit report generator, 150 lines
├── compliance/                   # Forensic + RPA Subagents (23 Subagents + 2 Orchestratoren)
│   ├── rpa_main_orchestrator.py      # RPA 8-Schritt-Prüfpipeline → Entlastungsbericht
│   ├── vergabekammer_orchestrator.py # VK 9-Agenten-Forensik → PDF
│   └── subagents/
│       ├── gobd_integrity_checker.py       # WORM-Archiv Hash-Ketten
│       ├── ledger_exporter_subagent.py     # Decimal-BHO-Kassenbuch
│       ├── hash_verifier_subagent.py       # On-Chain Merkle-Abgleich (Gnosis/peaq)
│       ├── xrechnung_audit_checker.py      # EN 16931 / Schematron / Leitweg-ID
│       ├── popw_evidence_auditor.py        # PoPW-Telemetrie-Deckung (GPS/IoT/Fotos)
│       ├── vobb_payment_compliance_checker.py # §16 Fristen, §17 Einbehalt, §13 Mängel
│       ├── tax_compliance_auditor.py       # §13b UStG + BZSt + Freistellungsattest
│       ├── pdf_audit_composer.py           # RPA-Entlastungsbericht PDF/A-3
│       ├── tender_history_fetcher.py       # Zeitstrahl-Rekonstruktion
│       ├── voba_rule_checker.py            # 5 formale Ausschluss-Checks
│       ├── price_plausibility_analyzer.py  # 2-Layer (Ref + Statistik)
│       ├── cartel_collusion_detector.py    # 4 Kartell-Heuristiken
│       ├── popw_bonus_auditor.py           # 6 PoPW-Checks (DKG/DID/ZK)
│       ├── qes_crypto_verifier.py          # 5 QES-Prüfungen + Audit-Seal
│       ├── bidder_comparison_engine.py     # Position-by-position Matrix
│       ├── audit_report_generator.py       # Vergabekammer-PDF
│       ├── soll_ist_vergleichs_engine.py   # GAEB/PoPW Soll/Ist-Matrix
│       ├── delay_analyzer.py               # CPM Critical Path + Verzugsprognose
│       ├── evm_performance_calculator.py   # SPI/CPI/EAC Earned Value
│       ├── disruption_clause_auditor.py    # VOB/B §6 + Wetter + Haftung
│       ├── gantt_chart_generator.py        # Mermaid Gantt + MTA
│       ├── progress_dashboard_composer.py   # HTML Dashboard + Traffic Lights
│       └── sepa_transaction_exporter.py    # CAMT.053 + MT940 + CSV
├── public_portal/                # Wave 15: Public Portal & Transparency
│   ├── __init__.py               # Wave 15 exports
│   └── agents.py                 # Wave 15: 9 agents + PublicPortalSupervisor
├── bridge/                       # Wave 16: Monerium SEPA-Bridge
│   ├── __init__.py               # Wave 16 exports
│   └── agents.py                 # Wave 16: 9 agents + SEPABridgeSupervisor
├── macro/                        # Wave 17: MacroEconomy Engine
│   ├── __init__.py               # Wave 17 exports
│   ├── macro_economy_orchestrator.py  # Root: 8-Stufen-Pipeline, MEHI
│   └── subagents/
│       ├── velocity_of_money_tracker.py        # Agent 2: Umlaufgeschwindigkeit (768 L)
│       ├── programmable_stimulus_engine.py     # Agent 3: Taylor-Regel + EURe Mint/Burn (872 L)
│       ├── real_time_tax_splitter.py           # Agent 4: §13b UStG + Bauabzug + BZSt (558 L)
│       ├── capital_efficiency_analyzer.py      # Agent 5: ROIC, CCC, WCR, PROIC (540 L)
│       ├── supply_chain_multiplier_calc.py     # Agent 6: Keynes + Leontief + Tiers (640 L)
│       ├── systemic_risk_and_cartel_monitor.py # Agent 7: Betweenness, PageRank, Gini (200 L)
│       ├── real_time_inflation_oracle.py       # Agent 8: Laspeyres/Paasche/Fisher (858 L)
│       └── central_bank_ledger_twin.py         # Agent 9: Bilanz + Taylor-Zins (260 L)
├── shadow/                       # Wave 18: VOB Shadow Contract & Pilot
│   ├── __init__.py
│   ├── shadow_contract_orchestrator.py  # 14-Phase-Lifecycle, 10 Subagenten
│   └── subagents/ (10 files)
├── onboarding/                   # Wave 19: Ecosystem Onboarding
│   ├── __init__.py
│   ├── ecosystem_onboarding_orchestrator.py  # 5-Rollen-Root
│   └── subagents/ (8 files)
├── security/                      # Wave 20+21: CertiK + Skynet Security
│   ├── __init__.py               # Wave 20+21 exports
│   ├── certik_audit_orchestrator.py  # Wave 20: 9+81 Subagenten
│   └── skynet_orchestrator.py    # Wave 21: 9+54 Subagenten
├── tokenomics/                    # Waves 23+29: Token Creation & Runtime
│   ├── __init__.py
│   ├── token_launch_orchestrator.py  # Wave 23: 9+81 Subagenten (Launch)
│   └── token_runtime_orchestrator.py # Wave 29: 9+81 Subagenten (Runtime)
├── trading/                       # Wave 24: Trading Infrastructure
│   ├── __init__.py
│   └── token_trading_orchestrator.py  # 9 Agenten: DEX, AMM, MEV, Market Making
├── wallet/                        # Wave 25: Institutional Smart Wallet & Identity
│   ├── __init__.py
│   └── smart_wallet_orchestrator.py  # 9+81 Subagenten
├── clearing/                      # Wave 27: Binnenmarkt-Clearing & Settlement
│   ├── __init__.py
│   └── clearing_settlement_orchestrator.py  # 9+81 Subagenten, 2.125 lines
├── defense/                       # Wave 28: External Threat Defense & Swarm Immunity
│   ├── __init__.py
│   └── swarm_defense_orchestrator.py  # 9+81 Subagenten, 1.459 lines
├── philately/                     # Wave 32: Crypto-Philately & Digital Stamp
│   ├── __init__.py
│   └── philately_orchestrator.py  # 9+81 Subagenten
├── survival/                      # Wave 33: Survival & Off-Grid Post-Quantum
│   ├── __init__.py
│   ├── survival_orchestrator.py   # 9 Agenten: PQC, MPC, Mesh, Resources, Clearing
│   └── subagents/
│       ├── pqc_signer.py          # Dilithium-5, Kyber-1024, SPHINCS+ (608 lines)
│       ├── mpc_bunker.py          # Air-Gapped MPC (t=3, n=5)
│       ├── zk_compression.py      # STARK Proofs (FRI, SHA3)
│       ├── lorawan_mesh.py        # LoRaWAN + HAM + Satellite
│       ├── peer_discovery.py      # DHT + Gossip Topology
│       ├── state_sync.py          # Hash-Ketten State Sync
│       ├── resource_oracle.py     # IoT Resource Sensing
│       ├── rationing.py           # ZK-eID Ration Distribution
│       └── clearing.py            # Multilateral Resource Netting

├── ux/                            # Wave 31: Omnichannel UX & Verwaltungs-Dashboard
│   ├── __init__.py
│   └── ux_orchestrator.py         # 9+81 Subagenten, 1.628 lines
├── finale/                        # Wave 34: Finale Veredelung — Pitch & Go-Live
│   ├── __init__.py
│   ├── finale_orchestrator.py     # Master-Agent: Audit-Zertifikat, Z3-Live, 317 L
│   ├── streamlit_app.py            # Streamlit-Dashboard (4 Modi), 303 L
│   └── subagents/
│       ├── __init__.py
│       ├── dashboard_renderer.py   # D1: BHO-Balken + Plotly/ASCII, 249 L
│       ├── audit_trail.py          # D2: GoBD-WORM Hash-Kette, 183 L
│       └── realtime_monitor.py     # D3: 5-Stufen-Eskalation, Health, 248 L
├── simchain/                      # Wave 35: Multi-Chain Economic Simulation
│   ├── __init__.py                # Exports EconomicOrchestratorMulti
│   ├── economic_orchestrator_multi.py  # 9 Agents × 3 Chains, Cross-Chain-Bridge
│   ├── streamlit_app.py            # Dashboard: 5 Tabs, Plotly Charts, Live Mode
│   └── subagents/
│       ├── __init__.py            # All 9 subagent exports
│       ├── sensor_aggregator.py   # S1: DePIN Sensor Batch Aggregation (1000 TPS)
│       ├── bridge_agent.py        # S2: Cross-Chain Merkle Bridge + Latency
│       ├── depin_wallet.py        # S3: Micro-Payout Wallet Management
│       ├── vob_settlement.py      # L1: VOB/B Milestone Settlement + Z3 Proofs
│       ├── legal_compliance.py    # L2: GoBD Archiving + Tax (§13b UStG)
│       ├── settlement_executor.py # L3: Multi-Split + Escrow Retention
│       ├── token_minter.py        # T1: Token Minting + Burn Mechanics
│       ├── staking_pool.py        # T2: Lockup Management + APY Distribution
│       └── burn_fee_agent.py      # T3: Fee Collection + Token Burns (Friction)
├── multichain/                    # Wave 36: Sovereign Appchain Ecosystem
│   ├── __init__.py                # Exports ChainOrchestrator, BridgeProtocol
│   ├── chain_orchestrator.py      # 4 Layers, 9 Sovereign Appchains + Demo
│   ├── bridge_protocol.py         # Merkle Tree Proof-of-Inclusion Protocol
│   └── subchains/
│       ├── __init__.py            # All 9 subchain exports
│       ├── sensor_aggregator.py   # A1: DEPIN Appchain, 1000 TPS, Merkle Root
│       ├── bridge_relayer.py      # A2: Cross-Chain Relay + Merkle Proofs
│       ├── depin_wallet.py        # A3: Micro-Payout Wallet Chain
│       ├── vob_settlement.py      # A4: VOB/B Settlement Chain + Z3
│       ├── legal_compliance.py    # A5: GoBD Archiving + Tax Chain
│       ├── settlement_executor.py # A6: Multi-Split + Escrow Chain
│       ├── token_minter.py        # A7: Token Mint + Burn Chain
│       ├── staking_pool.py        # A8: Staking + APY Chain
│       └── identity_compliance.py # A9: Identity Chain (SSI/DIDs/ZK)
├── settlement/                    # D01–D04: ZK Settlement & Compliance Pipeline
│   ├── __init__.py                # D01 ZK-Settlement, D02 Forensic, D03 Emergency, D04 Chaos, C09 Ingest, DAG, ComplianceExporter (~1.500 lines)
│   └── chaos_harness.py          # D04 Storm Diver: 4 fault-injection experiments
├── crew/                          # 5-Member Internal Crew + DID Registry
│   ├── __init__.py                # AgentCrew, DIDRegistry, ForensicStamp
│   ├── crew.py                    # 5-role pipeline: Comms→Navigator→Tactical→Gas→Decision
│   ├── agents.py                  # 9 specialized agents (C01–C09) with fee collection
│   ├── did_registry.py            # Dynamic DID registry, demo/production modes, injectable verifier
│   └── did_tracker.py             # Forensic stamp generator, attack type detection
├── gas/                           # Autonomous Gas/Fuel Management
│   ├── __init__.py                # GasProfile, GasOrchestrator
│   ├── gas_profiles.py            # 9 agent fuel profiles (tank, consumption, reserve)
│   └── gas_orchestrator.py        # OUT_OF_GAS protocol, emergency refuel, treasury
├── valhalla/                      # ZK Honor Protocol — anonymous reputation
│   ├── __init__.py                # ValhallaOrchestrator, HonorCalculator, ValhallaLedger
│   └── valhalla.py                # H = α·SAT + β·TPS − γ·UNSAT + δ·perfect
├── demo/                          # Wave 37: Pitch Pipeline with differentiated profiles
│   ├── __init__.py                # DemoOrchestrator, TransformProfiles
│   ├── demo_orchestrator.py       # 9-agent pipeline, 8 unique friction rates
│   └── transform_profiles.py      # Per-agent fee/retention/burn rates
├── wirtschaft/                    # 9 Wirtschaftsagenten (Klassen A/B/C): Gewaltenteilung, Bausteine 1–5; NO_COUPLING (IFI-robust) — docs/WIRTSCHAFTS_SCHWARM_DOSSIER.md
├── rescue/                        # Katastrophenschutz: 9 Einheiten A/B/C, OODA, Phase-Pull/RoE/RNG; Dichte-Hypothese falsifiziert — docs/RESCUE_KOORDINATION_DOSSIER.md · docs/RESCUE_DICHTE_STUDIE.md
├── ci/                            # Kritische Infrastruktur: 9 Agenten A/B/C, H0 PASSES (3/5/5/10s); Stress H1+H2 CONFIRMED (Natur>Blackout>Cyber) — docs/CI_RESILIENZ_STUDIE_PREREG.md · docs/CI_RESILIENZ_STUDIE_ERGEBNIS.md
├── surface/                       # C01–C09 Surface Agents: NATS Queue-Group Workers
│   ├── __init__.py
│   ├── handler.py                 # SurfaceHandler: NATS, TPS, adaptive batching, constraint metering
│   ├── predictive_router.py       # PredictiveHealthRouter: score-based traffic shunting
│   ├── run_agent.py               # AGENT_ID resolver, 9-chain config, /metrics endpoint
│   └── Dockerfile                 # Python 3.12-slim, nats-py + aiohttp
├── mechanized/                    # P01–P09 Panzergrenadier: Edge-Clearance (Infantry)
│   ├── __init__.py                # PanzergrenadierCoordinator, P01–P09 Exports
│   ├── base.py                    # Coordinator + DeploymentState + ClearanceResult
│   ├── handler.py                 # NATS-Consumer (infantry.edge) + /metrics (8082)
│   ├── metrics.py                 # MetricsRegistry (clearance_p99_ms, deep_state_p99_ms)
│   ├── deep_state.py              # 2ms-Hard-SLA Deep-State-Query
│   ├── p01_cross_shard.py … p09_reconnaissance.py  # 9 Agenten
│   └── Dockerfile                 # Python 3.12-slim, nats-py
├── subsurface/                    # D00–D01 Prover Factory & Failover Orchestration
│   ├── __init__.py
│   └── prover_factory.py          # ZKProverBackend: SGX-TDX/SEV-SNP/CUDA/CPU, curve unification
├── ephemeral/                     # F01–F03 Paratrooper WASM Subagents
│   ├── __init__.py
│   ├── payload/
│   │   └── types.py               # ParatrooperDropPayload, SubAgentID enum, 9 WASM modules
│   ├── runtime/
│   │   └── wasm_runner.py          # WasmSandbox with 500ms TTL
│   ├── src/                        # Go source: f01_hash_breaker, f02_liquidity_freeze, f03_gps_spoof_detector
│   └── wasm/                       # Compiled .wasm modules (3× 1.1MB)
```

### Wave 7 Detail: Operations & Maintenance (9 Agents)

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| OrchestratorAgent | EventRouter, DependencyResolver | Master-Scheduler, Circuit Breaker, Retry-Logik |
| HealthCheckAgent | HTTPPinger, ProcessWatcher, RestartTrigger | Vitality-Checks, Auto-Restart |
| LogAggregatorAgent | LogForwarder, AlertPatternMatcher | Strukturierte JSONL-Logs, Pattern-Matching |
| MetricsCollectorAgent | LatencyTracker, ErrorCounter, ThroughputMeter | Prometheus-Metriken (Latenz, Fehlerrate, Durchsatz) |
| AlertingAgent | ThresholdChecker, EscalationManager, NotificationSender | Schwellwert-basierte Alerts (E-Mail, PagerDuty) |
| DeadLetterHandlerAgent | ErrorClassifier, RetryScheduler | DLQ mit exponentiellem Backoff (10s–1h) |
| ConfigManagerAgent | ConfigFetcher, VersionTracker, RollbackSubagent | Live-Konfiguration, versioniert, Rollback |
| BackupAgent | SnapshotCreator, Encryptor, Uploader | State-Store Snapshots, AES-256, S3/Blob |
| SelfHealingAgent | DefectPatternLibrary, ActionExecutor, HealingValidator | Automatische Reparatur bekannter Fehlermuster |

### Wave 8 Detail: Pilot & Production Readiness (9 Agents)

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| OpsHealthAgent | HeartbeatCollector, MetricAggregator, AutoRestarter | 81-Agent-Health-Monitoring, Circuit Breaker (CLOSED→OPEN→HALF_OPEN) |
| DeadLetterRecoveryAgent | RetryScheduler, ErrorClassifier, AdminAlertSubagent | DLQ-Analyse, transiente vs. permanente Fehler, Eskalation |
| AuditExporterAgent | GoBDXMLSerializer, ZIPCompressor, AuditIndexer | JSONL→GDPdU-XML, PGP-verschlüsseltes ZIP |
| TenderAPIGatewayAgent | BundIDAuthenticator, GAEBUploadHandler, StatusQueryResolver | REST/GraphQL-API, BundID-Auth, GAEB-Upload |
| UserNotificationAgent | EmailTemplateEngine, SMSSender, BundIDPostfachConnector | 4 Templates, 3 Kanäle |
| ComplianceReportAgent | PDFComposer, BundesrechnungshofFormatter, DigitalSealSubagent | Rechnungsprüfungs-Bericht (PDF/A) mit QES |
| MultiTenantIsolatorAgent | TenantKeyManager, DBRouter, DataLeakDetector | AES-256 pro Tenant, Redis-DB-Routing, Cross-Tenant-Leak-Detection |
| SimulationTestAgent | MockDataGenerator, ResultComparator, RegressionAlert | Synthetische GAEB-Daten, Regressionstests |
| PilotDashboardAgent | WebSocketServer, ChartGenerator, BlockchainExplorerLinker | Live-Dashboard, Gnosis/peaq-Explorer-Links |

### Wave 9 Detail: User & Project Management (9 Agents)

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| UserAuthenticatorAgent | BundIDProxy, RoleMapper, SessionManager | BundID/eIDAS SSO, 5 Rollen (ADMIN/PROJECT_LEAD/INSPECTOR/CONTRACTOR/VIEWER), JWT-Sessions |
| ProjectManagerAgent | ProjectCreator, BudgetAllocator, DeadlineSetter | Projekt-Lifecycle (8 Statuses), VOB/A-Budgetverteilung |
| TaskDispatcherAgent | MilestoneToTaskMapper, AgentTrigger, TaskMonitor | Meilensteine→Agent-Tasks, Wellen-Trigger, Fortschritt |
| DocumentManagerAgent | DMSConnector, VersionTracker, AccessControl | 8 Dokumenttypen, rollenbasierte ACLs, Versionierung |
| NotificationCenterAgent | ChannelRouter, TemplateEngine, DeliveryTracker | 5 Kanäle (E-Mail/SMS/BundID/Teams/Slack), 8 Templates, Prioritäts-Routing |
| ReportGeneratorAgent | ReportAggregator, PDFReportBuilder, Scheduler | 6 Report-Typen, PDF/A-Export, zeitgesteuert |
| ComplianceCheckerAgent | RuleEngine, AuditTrailReviewer, AlertSubagent | **13 Regeln**: VOB/A(2), VOB/B(3), BHO(2), GoBD(2), DSGVO(3), eIDAS(1) |
| DataPrivacyAgent | AnonymizationEngine, ConsentManager, DeletionSubagent | DSGVO: Pseudonymisierung, Einwilligungen, Löschanträge (<30d) |
| FeedbackCollectorAgent | FeedbackFormEngine, SatisfactionMeter, ImprovementTracker | NPS-Berechnung, 5-Sterne-Rating, Improvement→Ops-Pipeline |

### Compliance Module Detail (23 Subagents + 2 Orchestrators)

**VergabekammerOrchestrator** (9-agent forensic pipeline):
History → VOB → Price → Cartel → PoPW-Bonus → QES → BidderCompare → AuditPDF → Evidence-Seal

**RPAMainOrchestrator** (8-step audit pipeline → discharge report):
GoBD → Ledger (BHO Δ=0,00€) → Chain-Hash → XRechnung → PoPW-Coverage → VOB/B → Tax (§13b) → PDF/A-3

| Subagent | Prüfungen | Methoden |
|----------|-----------|----------|
| GoBDIntegrityChecker | 3 | Hash-Ketten, WORM-Eigenschaft, Vollständigkeit + Zertifikat |
| LedgerExporterSubagent | 3 | Decimal-Buchführung, BHO Zero-Sum, Soll-Ist-Abgleich |
| HashVerifierSubagent | 2 | On-Chain Merkle-Root-Abgleich (Gnosis + peaq) |
| XRechnungAuditChecker | 4 | Schematron, Steuer (§13b), Leitweg-ID, UBL-Struktur |
| PoPWEvidenceAuditor | 3 | GPS-Geofence, IoT-Waagen, EXIF-Fotos, 90% Coverage-Schwelle |
| VOBBPaymentComplianceChecker | 3 | §16 Zahlungsfristen (30d), §17 5%-Einbehalt, §13 Mängelrügen |
| TaxComplianceAuditor | 3 | §13b UStG Reverse-Charge, BZSt-IBAN-Abgleich, Freistellungsattest |
| PDFAuditComposer | 1 | PDF/A-3 Entlastungsbericht mit allen Prüfschritten |
| CartelCollusionDetector | 4 | Tippfehler, Zeitstempel-Cluster, Preiskorrelation, Metadaten |
| PricePlausibilityAnalyzer | 4 | Benford's Law, Z-Score, IQR, Round-Number + Referenzpreise (42 BKI) |
| PoPWBonusAuditor | 6 | DKG-Existenz, DID-Matching, Zeit, ZK-Proof, Metriken, Duplikate |
| QESCryptoVerifier | 5 | X.509-Zertifikat, OCSP, RSA/ECDSA-Signatur, Chain-Integrität, Audit-Seal |
| BidderComparisonEngine | 3 | OZ-Positionsvergleich, Textähnlichkeit, Materialgruppen-Aggregation |
| VOBARuleChecker | 5 | Fristen, EFB-Formblätter, Änderungen, Eignungsnachweise, GAEB-Struktur |
| TenderHistoryFetcher | 3 | WORM-Archiv, Chain-Events, chronologischer Zeitstrahl + State-Aggregation |
| AuditReportGenerator | 1 | Gerichtsfester Vergabekammer-Prüfbericht (PDF/A) |

### Reference Data & Standards

| Resource | Location | Contents |
|----------|----------|----------|
| GAEB DA XML 3.3 XSDs | `archive_b2g/reference/gaeb_test_suite/schemas/` | 5 XSDs (X83, X84, X86, X89, Lib) |
| GAEB Sample X83 | `archive_b2g/reference/gaeb_test_suite/x83_anfrage/` | Kläranlage Nord, 8 Positionen, 4.2M € |
| BVBS Test Suite | `archive_b2g/reference/bvbs_test_suite/` | BVBS certification files target |
| XRechnung 3.0 Schematron | `archive_b2g/schemas/xrechnung_30/schematron/` | KoSIT/itplr-kosit, UBL + CII |
| VHB-221/222 PDFs | `archive_b2g/offers/` | VOB/A-konforme Angebots-PDFs |
| RPA Reports | `archive_b2g/rpa_reports/` | RPA-Entlastungsberichte (PDF/A-3) |
| Vergabekammer Reports | `archive_b2g/reports/` | VK-Prüfberichte (PDF) |

### Key B2G Decisions (ADR)

1. **Non-custodial Escrow:** EscrowVault.sol has no emergency withdraw. Platform = software provider, never custodian. (ADR in Schwesterprojekt `craft-procurement-engine`)

2. **BHO Zero-Sum:** Every payment: Deposits = Paid + Retained + Vault_Balance. |Δ|>0.01€ halts all payments. Decimal arithmetic.

3. **VOB/B §17 Retention:** 5% per installment, held in separate sub-account, released 95% at acceptance.

4. **VOB/B §13 Defects:** State machine: IDLE→DEFECT→DEADLINE(14d)→RESOLVED/REDUCTION.

5. **§13b UStG:** Reverse-charge for construction services.

6. **BundID/eIDAS Auth:** SSO via BundID-Proxy, JWT-Validierung, 5 Rollen mit granularer Permission-Matrix.

7. **DSGVO Compliance:** Pseudonymisierung (SHA-256), Consent-Management, Löschanträge <30 Tage, AVV.

8. **Multi-Chain Notarization:** Gnosis Chain (EVM) + peaq (Substrate). EscrowVault.sol on Gnosis, DID-based PoPW proofs on peaq.

9. **GAEB DA XML 3.3:** Bidirectional X83↔X84 with official XSD validation. BVBS certification files for regression testing. VHB-221/222 PDF for authority acceptance.

10. **XRechnung 3.0 EN 16931:** KoSIT Schematron validation (graceful degradation). ZUGFeRD PDF embedding. §13b UStG Reverse-Charge compliance.

11. **RPA Discharge Pipeline:** 8-step audit (GoBD→Ledger→Chain→XRechnung→PoPW→VOB/B→Tax→PDF/A-3) with ENTLASTET/VORBEHALT/ENTLASTUNG_VERWEIGERT verdict.

### B2G Test Results

- **BSI Compliance Gate:** `verified=30/42` · `claimed=1` (nur 1.1 NFC AusweisApp2 — dokumentierte Hardware-Ceiling) · `attested=11` · `failed=0` · `gate=PASS` · `KONFORM_MIT_VORBEHALT` (`services/z3_solver/main.py`)
- **Probe-Promotion 2026-08-16:** 2.1 WORM · 3.4 GAEB (SON) · 3.6 VOB/B Mängel+4y Warranty (Option A) · 4.5 HSM_PIN · 5.4 Proof-Hash · 5.6 Dashboard · 7.5 CI/CD (5 Jobs)
- **3.6 Integrität:** GuaranteeTracker an VOB/B §13 Abs. 4 angeglichen (`warranty_years: 4`); Probe assertiert 4 Jahre (BGB-5y-Abweichung behoben)
- **E2E 90-Agent Test:** 11/11 waves passed (`scripts/end_to_end_90_agents.py`), 0.8s duration
- **E2E Integration Test:** 25/25 passed (`scripts/end_to_end_b2g_test.py`)
- **Air Layer E2E:** 18/18 passed (`scripts/test_air_layer.py`) — Soft-Finality P99 13.8µs (<200µs), Transient CAS, Poison-Neutralisierung, Chaos-Resilienz (F07–F09), Conservation + BHO Δ=0,00€
- **GAEB DA XML 3.3:** 2/2 tests passed (`scripts/test_gaeb_reference.py`) — X83/X84 XSD validation ALLE VALIDE; X84 generation DP/VersDate/UP/TotalAmount compliant (`X84SerializerAgent`)
- **Treasury Pipeline:** 4/4 installments, all BHO Δ=0.00€
- **CHI Decomposition:** Functional, per-block penalty trace
- **Wave 7+8 Integration:** 18 agents, Circuit Breaker, DLQ recovery, GoBD export, API gateway
- **Wave 9 Integration:** BundID SSO, 13/13 compliance rules, NPS tracking, GDPR deletion workflow
- **Wave 10 Integration:** RPA=ENTLASTET_MIT_HINWEIS, Forensic=RED, 9 query agents functional
- **Compliance Module:** 23 subagents + 2 orchestrators, Vergabekammer PDF + RPA PDF
- **GAEB DA XML 3.3:** X83 parsing (8 positions, 4.2M €), X84 generation validated
- **GoBD Integrity:** PASSED (hash chains verified), BHO Zero-Sum Δ=0.00€
- **Wave 15 Public Portal:** 68/68 tests passed (QR generation SVG/PNG, batch, municipality, tenant isolation, fast-track, DSGVO shield, blockchain verification, open data export)
- **Wave 16 SEPA Bridge:** 43/43 tests passed (Mint/Burn, IBAN/BZSt/MOD97/Blacklist, GoBD audit, OAuth2/CircuitBreaker/HALF_OPEN, ERC-4337 Paymaster + sponsor_tx, Δ=0.00€ reconciliation, SEPA polling/timeout, MiCAR compliance)
- **Wave 17 MacroEconomy:** 8/8 E2E passed (`scripts/test_wave17_macro.py`), MEHI 0.74 Grade B, all 8 pipeline stages green, cartel patterns detected, balance sheet Δ=0.00€
- **Wave 18 Shadow Contract:** 14/14 phases passed, Ledger Δ=0.00€, 21.600× speedup, 99.85% reliability, Atomic Settlement Δ=0.00€, Shadow Contract Lifecycle 25/25 passed (`shadow_contract_pilot/test_lifecycle.py`), VOB_Shadow_Escrow.sol compiled (OZ v5, Foundry), deployed on Anvil local node
- **Wave 19 Ecosystem:** 5/5 stakeholder roles onboarded, 100% conversion rate, ecosystem health dashboard active
- **Wave 20 CertiK Security:** 164/164 tests passed (`scripts/test_wave20_security.py`), 15 test groups covering all 9 agent groups + E2E + config + logging + failsafe, CertiK Score A+ (secure contracts), Score C/D (vulnerable contracts detected)
- **Wave 21 Skynet Monitor:** 80/80 tests passed (`scripts/test_wave21_skynet.py`), 12 test groups covering 6 pillars + score aggregator + alert engine + dashboard + E2E + config, Skynet Score 100.0 (clean mock data)
- **Wave 22 Ops Security:** 48/48 tests passed (`scripts/test_wave22_ops.py`), 10 test groups covering all 9 agents + config, Relay/Gas/Nonce/MetaTX/Autotasks/Webhooks/DeployVerify/SecureDeploy (benötigt >256 MB RAM, daher nicht im Hook)
- **Wave 23 Token Launch:** TokenCreation Pipeline funktional — MiCAR/SEC-Howey BLOCKING-Gate, ERC-20-Deployment, Vesting, DEX-Liquidity, DAO-Governance, Merkle-Airdrop, IPFS-Metadaten
- **Wave 24 Trading Infrastructure:** Combined Risk+Trading pipeline E2E: 36 events, 21 trading signals, FN=0, FP=0. Compliance Gate (sanctions/MiCAR/circuit breaker) as Phase 0. DEX routing over 5 DEXes, MEV protection, ERC-4337 gasless trading, SAR+Archive post-trade. VOB_Shadow_Escrow.sol compiled (Foundry/OZ v5), deployed on Anvil local node.
- **Wave 25 Smart Wallet:** ERC-4337, eIDAS/BundID, ZK-Privacy, BHO-Kasse, Amtsübergabe — Integration mit W1-W24 im demo_kammerer.sh
- **Wave 27 Clearing & Settlement:** 122/122 tests passed (`scripts/test_wave27_clearing.py`), 14 test groups covering all 9 agents + E2E + BHO Zero-Sum + empty list + cycle detection + config, 100 TXs → 1–3 Netto-Zahlungen, ≥95% Reduction
- **Wave 28 External Threat Defense:** 105/105 tests passed (`scripts/test_wave28_defense.py`), 14 test groups covering all 9 agents + E2E legitimate/cartel/rate-limit/geo-block/sybil + config, 81 Subagenten
- **Wave 29 Token Runtime Operations:** 101/101 tests passed (`scripts/test_wave29_tokenomics.py`), 12 test groups covering all 9 agents + E2E full cycle + empty inputs + token state + config, 81 Subagenten, 9-stage pipeline all green
- **Wave 31 UX & Dashboard:** 92/92 tests passed (`scripts/test_wave31_ux.py`), 14 test groups covering all 9 agents + E2E login/commands/simulation/reports/multi-role + config, 81 Subagenten, 6 Rollen (Kämmerer, Bauleiter, Prüfer, Bürger, Entwickler, Bank)
- **Wave 32 Crypto-Philately:** 51/51 tests passed (`scripts/test_wave32_philately.py`), 12 test groups covering all 9 agents + E2E lifecycle/multi-edition/collection + config, 81 Subagenten
- **Wave 33 Survival & Off-Grid:** 63/63 tests passed (`scripts/test_wave33_survival.py`), 11 test groups covering all 9 agents + PQC (Dilithium/Kyber/SPHINCS+) + MPC-Bunker + ZK-STARKs + Mesh-Networking + Resource-Clearing + E2E Survival Demo, PQC-Backend: SHA3/SHAKE-Simulation (liboqs-ready)
- **Wave 34 Finale Veredelung:** 21/21 tests passed (`scripts/test_finale.py`, benötigt `plotly` für Charts — ASCII-Fallback ohne), 5 test groups: Dashboard (4), Audit-Trail (4), Realtime-Monitor (5), Orchestrator (6), E2E (2) — Streamlit+Plotly+GoBD-WORM+Z3-Live-Integration, 1.876 lines
- **Wave 35 SimChain Multi-Chain Economy:** 199/199 tests passed (`scripts/test_simchain.py`), 15 test groups covering all 9 agents + 3 chains + E2E multi-chain + falsifiable friction + BHO zero-sum + value conservation + config + error handling + dashboard (8 tests) — 3 Chains (DEPIN/Settlement/Liquidity), Cross-Chain-Bridge, Friktion 5.6% (Burns+Fees), value_conserved verifiziert, drei getrennte Chain-Bücher, Streamlit Dashboard mit Live-TPS/Volumen/Latenz
- **Wave 36 MultiChain Sovereign Appchains:** 113/113 tests passed (`scripts/test_multichain.py`), 11 test groups covering all 9 sovereign appchains + bridge protocol + Merkle proofs + orchestrator + identity chain — 4 Chain Layers, 9 Appchains mit eigenem State/Block-Height/Mempool, 167k events/s Durchsatz
- **Bunker Integration:** 18/18 tests passed (`tests/test_bunker_integration.py`), 6 test groups: HSM Signing, LoRa Transmission, Handyman CBOR, BHO Zero-Sum, Merkle Chain, E2E
- **HSM Adapter:** 6/6 tests passed (`tests/test_hsm_adapter.py`), Dual-Mode HSM (SoftHSM + Hardware), ECDSA-Signing

### Smart Contracts

#### On-Chain Contracts (shadow_contract_pilot/contract/)

4 neue Smart Contracts für das IoT Resource Oracle — ERC-1155 Commodity-Token, Hardware-Signatur-Verifikation, P2P-Tausch und BHO-Ledger.

| Contract | Lines | Typ | Funktion |
|----------|-------|-----|----------|
| `shadow_contract_pilot/contract/IoTVerifier.sol` | 199 | Zero-Trust Gateway | ECDSA-Signaturprüfung von ESP32-Messungen, Device-Registry, Replay-Schutz |
| `shadow_contract_pilot/contract/CommodityToken.sol` | 299 | ERC-1155 Multi-Token | 6 Ressourcen-Typen (ENERGY/WATER/WHEAT/DIESEL/MEDICAL/H2), Minting nur nach IoT-Verifikation |
| `shadow_contract_pilot/contract/ResourceTrader.sol` | 268 | P2P Exchange | Atomarer Swap (kWh↔Liter↔kg), Trade-Proposals, öffentliche Order-Books |
| `shadow_contract_pilot/contract/CommodityLedger.sol` | 231 | BHO Ledger | Hash-Ketten-Buchführung, BHO-Invarianz (Δ≤0), WORM-Audit, Supply-Tracking |
| `shadow_contract_pilot/contract/VOB_Shadow_Escrow.sol` | 441 | Escrow (exist.) | VOB/B-Meilensteine, 5% Retention, §13b UStG |
| `shadow_contract_pilot/contract/ComplianceVerifier.sol` | 120 | Compliance (exist.) | BSI C5/ISO27001-Audit-Log |

**Prüfsummen:** Alle Contracts mit Foundry/Solc 0.8.35 kompiliert (OZ v5.0.0). 4 neue Contracts = 997 lines Solidity.

#### Externe Contracts (Schwesterprojekt)

Die externen Contracts befinden sich im Schwesterprojekt [`craft-procurement-engine`](https://github.com/craft-engine/craft-procurement-engine).

| Contract | Lines | Functions | Events | Bytecode | EIP-170 |
|----------|-------|-----------|--------|----------|---------|
| DemandPoolFactory.sol | 345 | 17 | 6 | 6.020 B | 24,5% |
| EscrowVault.sol | 441 | 25 | 9 | 9.187 B | 37,4% |

### Test Suites

End-to-End-Validierung erfolgt über `scripts/end_to_end_90_agents.py` (11/11 waves). Detaillierte Test-Suiten (test_agent_x.py, test_b2g_e2e.py, test_smoke.py, tests/) befinden sich im Schwesterprojekt `craft-procurement-engine`, nicht in `agent_x_storage`.

### Deployment

```bash
# Agent X Core — Backtest
python3 agent_x_backtest.py

# Agent X — Calibration
python3 scripts/calibrate_agent_x.py
python3 scripts/calibrate_agent_x.py --generate-samples

# Agent X — Paper Trading
python3 scripts/paper_trading_agent_x.py

# B2G — Bootstrap (3-agent demo)
python3 scripts/bootstrap_b2g.py

# B2G — Full Pipeline
python3 orchestrator_b2g_full.py

# B2G — E2E Test
python3 scripts/end_to_end_90_agents.py

# B2G — GAEB Reference Test
python3 scripts/test_gaeb_reference.py --mode all

# B2G — XRechnung Schematron Fetcher
python3 scripts/fetch_xrechnung_schematron.py
python3 scripts/fetch_xrechnung_schematron.py --status

# B2G — Query CLI (Wave 10)
python3 cli_b2g_query.py --agent RPA --tender TED-... --full-package
python3 cli_b2g_query.py --agent Vergabekammer --tender TED-... --forensic
python3 cli_b2g_query.py --agent Ops --health
python3 cli_b2g_query.py --agent LocalEconomy --region Niedersachsen

# B2G — Public Portal (Wave 15)
python3 scripts/test_public_portal.py              # Run all 68 tests
python3 -c "
from agents_b2g.public_portal.agents import PublicPortalSupervisor
sup = PublicPortalSupervisor()
# Generate QR codes for all projects in Niedersachsen
print(sup.generate_qr_for_municipality('Niedersachsen'))
# Citizen query with DSGVO shield
print(sup.citizen_query('TED-2026-0815'))
"

# B2G — MacroEconomy Engine (Wave 17)
python3 scripts/test_wave17_macro.py               # Run 8-stage E2E pipeline
python3 -c "
from agents_b2g.macro import MacroEconomyOrchestrator
orch = MacroEconomyOrchestrator(user_id='test')
report = orch.analyze_economy()
print(f'MEHI: {report[\"macro_economy_health_index\"][\"score\"]:.2f} ({report[\"macro_economy_health_index\"][\"grade\"]})')
print(f'Steps: {report[\"steps_completed\"]}')
"
# Individual agent smoke tests
python3 agents_b2g/macro/subagents/velocity_of_money_tracker.py
python3 agents_b2g/macro/subagents/real_time_inflation_oracle.py
python3 agents_b2g/macro/subagents/supply_chain_multiplier_calc.py
python3 agents_b2g/macro/subagents/programmable_stimulus_engine.py
python3 agents_b2g/macro/subagents/real_time_tax_splitter.py
python3 agents_b2g/macro/subagents/capital_efficiency_analyzer.py

# B2G — Shadow Contract & Pilot (Wave 18)
python3 agents_b2g/shadow/shadow_contract_orchestrator.py
# B2G — Ecosystem Onboarding (Wave 19)
python3 agents_b2g/onboarding/ecosystem_onboarding_orchestrator.py

# B2G — CertiK Security Audit (Wave 20)
python3 scripts/test_wave20_security.py             # Run all 164 tests (15 groups)
python3 agents_b2g/security/certik_audit_orchestrator.py  # Full audit demo
python3 -c "
from agents_b2g.security import CertiKAuditOrchestrator
orch = CertiKAuditOrchestrator(user_id='test')
report = orch.run_full_audit(
    contract_name='EscrowVault.sol',
    contract_code=open('contracts/EscrowVault.sol').read(),
    chain='gnosis',
)
print(f'CertiK Score: {report[\"score_percent\"]} ({report[\"rating\"]})')
print(f'Verdict: {report[\"audit_verdict\"]}')
print(f'Vulnerabilities: {report[\"vulnerability_summary\"]}')
"

# B2G — Ops Security & Secure Deploy (Wave 22)
python3 scripts/test_wave22_ops.py              # Run all 48 tests
python3 agents_b2g/ops/relay_orchestrator.py    # Full relay/deploy demo

# B2G — Token Creation & Launch (Wave 23)
python3 agents_b2g/tokenomics/token_launch_orchestrator.py  # Full launch demo

# B2G — Trading Infrastructure (Wave 24)
python3 agents_b2g/trading/token_trading_orchestrator.py    # Full trading demo

# B2G — Clearing & Settlement (Wave 27)
python3 agents_b2g/clearing/clearing_settlement_orchestrator.py  # Full netting demo
python3 scripts/test_wave27_clearing.py                    # Run all 122 tests

# B2G — External Threat Defense (Wave 28)
python3 agents_b2g/defense/swarm_defense_orchestrator.py   # Full defense demo
python3 scripts/test_wave28_defense.py                     # Run all 105 tests

# B2G — Token Runtime Operations (Wave 29)
python3 agents_b2g/tokenomics/token_runtime_orchestrator.py # Full runtime cycle demo
python3 scripts/test_wave29_tokenomics.py                  # Run all 101 tests

# B2G — UX & Verwaltungs-Dashboard (Wave 31)

# B2G — Crypto-Philately (Wave 32)
python3 agents_b2g/philately/philately_orchestrator.py  # Full philately demo
python3 scripts/test_wave32_philately.py                # Run all 51 tests

# B2G — Survival & Off-Grid Post-Quantum (Wave 33)
python3 agents_b2g/survival/survival_orchestrator.py    # Full survival demo
python3 scripts/test_wave33_survival.py                 # Run all 63 tests
python3 scripts/test_wave33_survival.py --demo           # Demo only
python3 -c "
from agents_b2g.survival import SurvivalOrchestrator
orch = SurvivalOrchestrator(user_id='kaemmerer_mueller')

# Off-Grid-Modus aktivieren (Banken & Internet ausgefallen)
result = orch.activate_off_grid_mode()
print(f'Mesh-Peers: {result[\"mesh_peers\"]} | Überleben: {result[\"survival_estimate_days\"]} Tage ({result[\"survival_grade\"]})')

# Ressourcen-Transfer ohne Banken (Diesel für Krankenhaus)
tx = orch.execute_resource_transaction(
    sender='Rathaus', recipient='Krankenhaus',
    resource_type='diesel_liters', amount=500
)
print(f'Transfer: {tx[\"status\"]} — {tx[\"amount\"]} {tx[\"resource\"]}')

# PQC-Benchmark (ECDSA vs Dilithium-5 vs SPHINCS+)
bench = orch.run_pqc_benchmark(iterations=50)
print(f'PQC Mode: {bench[\"backend\"]}')
for algo, comp in bench['comparison']['quantum_resistant'].items():
    print(f'  {algo}: {comp}')

# Clearing-Cycle (Schulden-Kreise auflösen)
orch.clearing_agent.register_transaction('A', 'B', 'electricity_kwh', 100)
orch.clearing_agent.register_transaction('B', 'C', 'electricity_kwh', 100)
orch.clearing_agent.register_transaction('C', 'A', 'electricity_kwh', 100)
clearing = orch.clearing_agent.execute_clearing()
print(f'Clearing: {clearing[\"message\"]}')

# Rückkehr zum Normalbetrieb
orch.return_to_normal()
print(f'Modus: {orch.context.mode.value} — Souveränität: {\"✅\" if orch.context.sovereignty_preserved else \"❌\"}')
"
python3 scripts/test_wave31_ux.py                          # Run all 92 tests
python3 -c "
from agents_b2g.ux import UXOrchestrator
ux = UXOrchestrator(user_id='kaemmerer_mueller')
ux.login(user_id='kaemmerer', role='KAEMMERER', device='desktop', language='de')
# Dashboard
dash = ux.render_dashboard()
print(f'BHO Δ={dash[\"artifacts\"][0][\"analytics\"][\"bho\"][\"delta_eur\"]}€ | Compliance={dash[\"artifacts\"][0][\"analytics\"][\"compliance\"][\"score\"]}/100')
# Sprach-Assistent
cmd = ux.process_command('Budget Haushalt anzeigen')
print(f'Intent: {cmd[\"artifacts\"][0][\"intent\"]} → {cmd[\"artifacts\"][0][\"message\"][:60]}')
# Sandbox-Simulation
sim = ux.run_simulation({'name': 'Budget -10%', 'budget_eur': 5000000, 'budget_change_pct': -10, 'token_price': 0.10, 'supply_change_pct': 0, 'demand_change_pct': 5, 'tps': 100, 'duration_s': 60})
print(f'Budget: {sim[\"artifacts\"][0][\"budget\"][\"current_budget\"]:,.0f} € → {sim[\"artifacts\"][0][\"budget\"][\"new_budget\"]:,.0f} € ({sim[\"artifacts\"][0][\"budget\"][\"impact\"][\"risk_level\"]} Risk)')
# VOB/B-Workflow
viz = ux.visualize_project('TED-2026-001')
print(f'Milestones: {viz[\"artifacts\"][0][\"progress\"][\"progress_pct\"]}% done')
# Alert
alert = ux.trigger_alert('CRITICAL', 'Budget-Alarm', 'Schulzentrum: +12.345 € über Plan!')
print(f'Alert: {alert[\"artifacts\"][0][\"severity\"]} — DND: {alert[\"artifacts\"][0][\"dnd_deferred\"]}')
# Status
status = ux.get_system_status()
print(f'Sessions: {status[\"artifacts\"][0][\"active_sessions\"]} | Alerts: {status[\"artifacts\"][0][\"active_alerts\"]} | Health: {status[\"artifacts\"][0][\"system_health\"]}')
"
python3 -c "
from agents_b2g.clearing import SettlementOrchestrator
import random
parties = ['Treasury', 'GeneralContractor', 'Subcontractor', 'TaxAuthority', 'ESCO']
txs = [{'invoice_id': f'INV-{i:04d}', 'payer_wallet': random.choice(parties),
        'payee_wallet': random.choice([p for p in parties if p != random.choice(parties)]),
        'amount_eur': round(random.uniform(100, 50000), 2), 'currency': 'EURe',
        'invoice_date': '2026-08-01'} for i in range(100)]
orch = SettlementOrchestrator(user_id='demo')
result = orch.process_monthly_settlement(txs, year=2026, month=8)
a = result['artifacts'][0]
print(f'{a[\"original_transactions\"]} TXs → {a[\"net_payments\"]} Zahlung(en) ({a[\"reduction_percentage\"]}% Reduktion)')
print(f'BHO Δ=0: {a[\"bho_zero_sum\"]} | Settlement: {a[\"settlement_approved\"]}')
print(f'Pipeline: {a[\"pipeline_steps\"]}')
"
python3 -c "
from agents_b2g.trading import TokenTradingOrchestrator
orch = TokenTradingOrchestrator(user_id='test')
result = orch.run_full_cycle(token='AGX', pair='EURe', amount=10000, current_price=1.0)
print(f'DEX: {result[\"artifacts\"][0][\"dex_route\"][\"best_route\"][\"dex\"]}')
print(f'Trading: {result[\"artifacts\"][0][\"trading_allowed\"]}')
"

# B2G — SimChain Multi-Chain Economy (Wave 35)
python3 scripts/demo_simchain.py                      # 100-cycle multi-chain demo
python3 scripts/demo_simchain.py 1000                 # 1000-cycle full simulation
python3 scripts/test_simchain.py                      # Run all 175 tests
python3 -c "
from agents_b2g.simchain import EconomicOrchestratorMulti
import asyncio
async def demo():
    orch = EconomicOrchestratorMulti(user_id='test', cycles=50)
    result = await orch.run_simulation(cycles=50)
    report = result['artifacts'][0]
    fa = report['friction_analysis']
    print(f'Value In (minted): €{fa[\"value_in_eur\"]:,.2f}')
    print(f'Net Payout (C09): €{fa[\"net_payout_eur\"]:,.2f}')
    print(f'Friction (Burns+Fees): €{fa[\"friction_eur\"]:,.2f}')
    print(f'Friction Verified: {fa[\"friction_verified\"]}')
    print(f'Value Conserved: {fa[\"value_conserved\"]}')
    print(f'BHO Δ=0: {report[\"compliance\"][\"bho_zero_sum_verified\"]}')
asyncio.run(demo())
"

# B2G — Settlement Pipeline (D01–D04, C09, Compliance Export)
python3 -c "from agents_b2g.settlement import demo_zk_settlement; demo_zk_settlement()"         # D01 ZK Settlement
python3 -c "from agents_b2g.settlement import demo_forensic_repair; demo_forensic_repair()"     # D02 Forensic
python3 -c "from agents_b2g.settlement import demo_forensic_api; demo_forensic_api()"           # D02 API
python3 -c "from agents_b2g.settlement import demo_emergency_rescue; demo_emergency_rescue()"   # D03 Emergency
python3 -c "from agents_b2g.settlement import demo_state_transition; demo_state_transition()"   # DAG Transition
python3 -c "from agents_b2g.settlement import demo_c09_ingest_handler; demo_c09_ingest_handler()"  # C09 Ingest
python3 -c "from agents_b2g.settlement import demo_compliance_export; demo_compliance_export()"  # Compliance Export
python3 -m agents_b2g.settlement.chaos_harness         # D04 Chaos (4 experiments)

# B2G — Crew & DID Registry
python3 -c "import asyncio; from agents_b2g.crew import demo_crew_pipeline; asyncio.run(demo_crew_pipeline())"  # Default-deny pipeline
python3 -m agents_b2g.crew.agents                      # 9-agent fleet smoke test

# B2G — Valhalla ZK Honor Protocol
python3 -c "from agents_b2g.valhalla import demo_valhalla; demo_valhalla()"

# B2G — Protocol (Surface-Subsurface NATS routing)
python3 -c "from agents_b2g.protocol import demo_surface_protocol; demo_surface_protocol()"

# B2G — Pitch Demos
python3 scripts/demo_abfang.py                         # Z3 Intercept (5 scenarios)
python3 scripts/demo_chaos.py                          # Chaos Matrix (10 attacks)
python3 scripts/demo_coastal.py                        # Coastal Defense (5 phases)

# B2G — One-Command Full Pitch
make full-pitch                                        # 4-Akt-Pitch in ~15 Sekunden

# B2G — Kämmerer-Demo (E2E Showcase)
bash scripts/demo_kammerer.sh                         # 4-Schritte-Demo für Behörden

# B2G — Testnet Deployment (Anvil/Chiado)
python3 scripts/testnet_dry_run.py                    # Dry-Run: RPC + Wallet-Check
python3 scripts/deploy_testnet.py                     # Live-Deployment (benötigt PRIVATE_KEY)
python3 -c "
from agents_b2g.tokenomics import TokenLaunchOrchestrator
orch = TokenLaunchOrchestrator(user_id='test')
result = orch.run_launch_pipeline('Agent X Token', 'AGX', 100_000_000, is_utility=True)
print(f'Contract: {result[\"artifacts\"][0][\"contract_address\"]}')
print(f'Phase: {result[\"artifacts\"][0][\"phase\"]}')
"

# B2G — Skynet Dynamic Security Score (Wave 21)
python3 scripts/test_wave21_skynet.py               # Run all 80 tests
python3 agents_b2g/security/skynet_orchestrator.py   # Full Skynet audit demo
python3 -c "
from agents_b2g.security import SkynetOrchestrator
orch = SkynetOrchestrator(user_id='test')
result = orch.run_full_audit(
    contract_name='EscrowVault.sol',
    contract_data={'audit_findings': [{'fixed': True}], 'multisig': {'required': 3, 'total': 5}},
    market_data={'pool': {'liquidity_usd': 5_000_000}},
    community_data={'tweets': [{'sentiment': 'positive'}]},
    governance_data={'voting_power': [1, 2, 3, 4, 5]},
)
print(f'Skynet Score: {result[\"artifacts\"][0][\"score\"][\"skynet_score\"]:.1f}')
print(f'Rating: {result[\"artifacts\"][0][\"score\"][\"rating\"]}')
"

# B2G — SEPA Bridge (Wave 16)
python3 scripts/test_wave16_bridge.py              # Run all 43 tests
python3 -c "
from decimal import Decimal
from agents_b2g.bridge.agents import SEPABridgeSupervisor
sup = SEPABridgeSupervisor()
# Full flow: deposit → payout → reconcile → confirm
sup.deposit(Decimal('500000.00'), 'DE89370400440532013000', 'TED-2026-0815')
sup.payout(Decimal('70300.00'), 'DE89370400440532013000', 'GENODEF1XXX', 'TED-2026-0815', 1)
print(sup.reconcile())
"

# Contracts — Compile + Deploy (Schwesterprojekt craft-procurement-engine)
# python3 scripts/deploy.py --dry-run
# python3 scripts/deploy.py  # requires PRIVATE_KEY

# Docker — Full Stack (alle Agenten + Redis/Neo4j/NATS/Prometheus/Grafana)
docker-compose up -d
docker-compose logs -f pilot_dashboard
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGGREGATION_METHOD` | `sum` | Penalty aggregation (sum, max_damp, p_norm) |
| `LENDING_MULTIPLIER` | `4` | c_liquidatable weight |
| `LENDING_CAP` | `26` | c_liquidatable cap |
| `AT_RISK_MULTIPLIER` | `1.2` | c_at_risk weight |
| `AT_RISK_CAP` | `18` | c_at_risk cap |
| `AGENT_X_ENV` | `pilot` | Deployment environment (dev/pilot/prod) |
| `NEO4J_USER` | `neo4j` | Neo4j database user |
| `NEO4J_PASSWORD` | — | Neo4j database password |
| `GNOSIS_RPC` | `https://rpc.gnosischain.com` | Gnosis Chain RPC endpoint |
| `PEAQ_RPC` | `wss://wsspc.peaq.network` | peaq WebSocket RPC endpoint |
| `BUNDID_JWKS_URL` | — | BundID JWKS endpoint for JWT validation |
| `SMTP_HOST` | — | SMTP server for email notifications |
| `TWILIO_ACCOUNT_SID` | — | Twilio account for SMS |
| `TWILIO_AUTH_TOKEN` | — | Twilio auth token |
| `TENANT_ENCRYPTION_MASTER_KEY` | — | Master key for tenant AES-256 encryption |

### Infrastructure (docker-compose.yml)

| Service | Image | Purpose |
|---------|-------|---------|
| redis | redis:7.4-alpine | State store, session cache, pub/sub |
| neo4j | neo4j:5.26-community | Graph database for audit trails, agent relationships |
| nats | nats:2.10-alpine | Core NATS + JetStream, ports 4222/8222, queue-group load balancing |
| prometheus | prom/prometheus:v2.55.0 | Metrics collection from all agents |
| grafana | grafana/grafana:11.3.0 | Dashboards for ops and project management |
| anvil | ghcr.io/foundry-rs/foundry:latest | L1 Settlement Chain (Foundry local EVM, port 8545) |

### Wave 10 Detail: Query & Reports (9 Agents)

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| VergabekammerQueryAgent | TenderHistoryFetcher, BidderComparison, VOBARuleChecker | Kartell-/Verstoßprüfung, Bietervergleich |
| RPAQueryAgent | PDFAuditComposer, LedgerExporter, HashVerifier | Rechnungsprüfungsbericht (PDF/A) mit BHO-Ledger + Chain-Anchors |
| ConstructionProgressQueryAgent | SollIstVergleich, GanttChartGenerator, DelayAnalyzer | GAEB-Plan vs. PoPW-Telemetrie, Baufortschritt |
| TreasuryQueryAgent | BalanceSheetCalculator, RetentionTracker, SEPATransactionExporter | Escrow-Saldo, 5%-Einbehalt, SEPA-Tracking |
| ComplianceQueryAgent | PIIAnonymizer, AuditTrailValidator, RetentionPolicyChecker | DSGVO/GoBD-Prüfung, JSONL-Vollständigkeit |
| ControllingQueryAgent | CostTrendAnalyzer, AgentUtilizationStat, OnTimeDashboard | Kosten, Auslastung (alle Agenten), Termintreue |
| OpsQueryAgent | CircuitBreakerStatus, ErrorLogAggregator, PerformanceHeatmap | Systemgesundheit, Fehlerraten, Latenzen |
| PublicDataQueryAgent | AnonymizationEngine, StatisticalCalculator, OpenDataExport | Vergabestatistik für Transparenzportale |
| LocalEconomyQueryAgent | GeoIPResolver, RegionalShareCalculator, SubsidyImpactReport | Regionaler Unternehmensanteil, Fördermittel-Impact |

### Wave 15 Detail: Public Portal & Open Government Explorer (9 Agents)

Citizen-facing transparency layer. Translates blockchain-anchored procurement data into human-readable formats with DSGVO privacy enforcement.

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| PublicPortalOrchestrator | — | Root agent: citizen queries (QR scan, project ID, invoice number), orchestrates sub-agents |
| ProjectSummaryAggregator | — | Public KPIs: budget, disbursed, progress %, milestones, next steps |
| BlockchainVerificationWidget | — | Live Gnosis/peaq hash verification, returns VERIFIED/UNVERIFIED seal |
| QRCodeGenerator | QRCodeRenderer, BatchScanner, QRFileWriter | SVG/PNG QR codes for construction signs, batch + municipality generation, tenant isolation |
| InteractiveMapComposer | — | Leaflet/OSM GeoJSON overlays, color-coded markers (green/yellow/red) |
| ZKPrivacyShield | — | DSGVO anonymization: strips names, emails, phones, IBANs, addresses, tax IDs |
| TrustButtonService | — | Verification widget for journalists: invoice number → GREEN seal + timestamp |
| CitizenNotificationService | — | Opt-in email/push on milestone reached, budget change, completion |
| AuditTrailPublicExporter | — | Open Data export (JSON/CSV) for researchers, all PII stripped |

**Key characteristics:**
- All 9 agents return standardized JSON: `{"status": "started|completed|failed", "job_id": "uuid", "artifacts": [...], "error": null, "logs": []}`
- Multi-tenancy: QR codes written to `/data/{user_id}/qrcodes/`
- Fast-track: existing QR codes detected and skipped
- JSONLogger replaces all print() calls
- try/except wrapping on every agent method
- EventBus integration for pub/sub audit trail

### Wave 16 Detail: Monerium SEPA-Bridge & Euro-Stablecoin-Orchestrierung (9 Agents)

MiCAR-compliant fiat-to-crypto bridge. Handwerker and Behorden never touch native gas tokens — all blockchain interaction is abstracted behind SEPA IBANs and ERC-4337 Paymasters.

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| SEPABridgeOrchestrator | — | Root: receives payment orders, routes mint/burn, enforces MiCAR, circuit breaker |
| EUReMinterSubagent | — | Fiat → On-Chain: SEPA receipt → 1:1 EURe mint via Monerium API |
| EUReBurnerSubagent | — | On-Chain → Fiat: PoPW release → burn EURe + SEPA Instant payout |
| IBANValidatorSubagent | — | IBAN/BIC/Steuer-ID validation, MOD 97 checksum, SEPA zone, BZSt database |
| SEPAAuditTrailSubagent | — | GoBD JSONL audit for every bridge transaction (MINT/BURN/RECONCILE) |
| MoneriumAPIClientSubagent | — | REST API wrapper (auth, issue, redeem, balance) with retry + circuit breaker |
| GasPaymasterSubagent | — | ERC-4337 gasless UX: sponsors xDAI/PEAQ fees via pre-funded Paymaster contract |
| BridgeBalanceMonitorSubagent | — | Vault vs. bank Δ=0.00 € reconciliation every 10 s, trips circuit on mismatch |
| SEPAConfirmationSubagent | — | Polls SEPA Instant status, confirms final credit on recipient IBAN |

**Key characteristics:**
- All 9 agents return standardized JSON: `{"status": "started|completed|failed", "job_id": "uuid", "artifacts": [...], "error": null, "logs": []}`
- MiCAR compliance: SEPA-zone only, ≤ 5M EUR per transaction
- BHO Zero-Sum: Bank balance = Vault balance (Δ ≤ 0.01 €)
- API resilience: all Monerium calls fall back to mock on network failure
- ERC-4337: Users never touch xDAI/PEAQ — Paymaster sponsors all gas
- JSONLogger replaces all print() calls
- try/except wrapping on every agent method

### Wave 17 Detail: MacroEconomy Engine — Real-Time Economic Digital Twin (9 Agents)

Closed-loop macroeconomic control system. Measures velocity of money, inflation from GAEB unit prices, Keynesian multiplier, tax decomposition, capital efficiency, cartel risk, and mirrors the central bank balance sheet. Programmable fiscal stimulus via Taylor Rule with EURe Mint/Burn integration.

**8-Stufen-Pipeline (E2E: 8/8 passed):**
```
Transactions → Velocity → Inflation → SupplyChain → Stimulus → TaxSplitter → CapitalEff → CartelMon → CBLedger
    500 TX       V=2.12      0.33%        k=1.86       +250K€       4.76M€       ROIC 39%     Risk 0.50    Δ=0.00€
```

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| MacroEconomyOrchestrator | — | Root: 8-Stufen-Pipeline, MEHI (MacroEconomyHealthIndex), GoBD-Export |
| VelocityOfMoneyTracker | — | Umlaufgeschwindigkeit V=PT/M, Sektor-Velocity, Trend, Prognose, 7 Alert-Typen |
| RealTimeInflationOracle | — | Laspeyres/Paasche/Fisher-Preisindex, BKI-Benchmark (14 Gewerke), Fisher-Gleichung P=M×V/Y |
| SupplyChainMultiplierCalc | — | Keynesianischer Multiplikator k=1/(1−MPC(1−t)+m), 5 Lieferketten-Tiers, Beschäftigungs-Multiplikator, ifo/DIW/IWF-Benchmarks |
| ProgrammableStimulusEngine | — | Taylor-Regel ΔG=α(V*−V)+β(π*−π)+γ(k*−k), 6 Stimulus-Typen, EURe Mint/Burn-Integration, Sektor-Allokation |
| RealTimeTaxSplitter | — | §13b UStG Reverse-Charge, §48 EStG Bauabzug, GewSt-Zerlegung, BZSt-Steuer-ID-Validierung, Steuerverteilung nach GG Art. 106 |
| CapitalEfficiencyAnalyzer | — | ROIC, Cash Conversion Cycle, Working Capital Ratio, Public ROIC, Kapitalbindungsdauer |
| SystemicRiskAndCartelMonitor | — | Betweenness/PageRank/Eigenvector-Zentralität, Gini-Koeffizient, Zykluserkennung, Kartellmuster (gegenseitige Zahlungen) |
| CentralBankLedgerTwin | — | ISO 20022 CAMT.053, Zentralbank-Bilanz (Δ=0.00€), Taylor-Zinsempfehlung, Seigniorage-Tracking, Dashboard |

**MEHI (MacroEconomyHealthIndex) Components:**
| Component | Weight | Source |
|-----------|--------|--------|
| Velocity | 20% | VelocityOfMoneyTracker |
| Price Stability | 15% | RealTimeInflationOracle |
| Supply Chain | 15% | SupplyChainMultiplierCalc |
| Fiscal Policy | 15% | ProgrammableStimulusEngine |
| Systemic Risk | 15% | SystemicRiskAndCartelMonitor |
| Tax Compliance | 10% | RealTimeTaxSplitter (default) |
| Capital Efficiency | 10% | CapitalEfficiencyAnalyzer (default) |

**Key characteristics:**
- All 9 agents return standardized JSON: `{"status": "started|completed|failed", "job_id": "uuid", "artifacts": [...], "error": null, "logs": []}`
- Closed-loop: Sensors (Velocity, Inflation, Multiplier) → Decision (StimulusEngine) → Actors (EURe Mint/Burn, TaxSplitter)
- Taylor Rule: ΔG = 0.5(V*−V) + 0.8(π*−π) + 0.3(k*−k)
- Fisher Equation: P = M × V / Y
- BHO Zero-Sum: Central bank assets = liabilities (Δ ≤ 0.01 €)
- Multi-tenancy: All reports under `{data_root}/{user_id}/macro/reports/`
- JSONLogger replaces all print() calls
- try/except wrapping on every agent method
- E2E Test: `python3 scripts/test_wave17_macro.py` — 8/8 passed

### Wave 18 Detail: VOB Shadow Contract & Real-World Pilot (9 Agents)

Rechtssicherer Parallelbetrieb: Smart-Contract-basierte Bauabwicklung als Schattenbuchhaltung zur traditionellen VOB/B-Abwicklung. Ermöglicht Behörden die Beobachtung und Validierung ohne Prozessänderung.

**14-Phasen-Lifecycle (E2E: 14/14 passed):**
```
Init → Deploy → Fund → 5×Milestones → Tax → Retention → Complete → Auditor → Metrics → Onboarding
```

| Agent | Funktion |
|-------|----------|
| ShadowContractOrchestrator | Root: 14-Phasen-Lifecycle, alle Subagenten integriert |
| LifecycleStateEngine | CREATED→FUNDED→ACTIVE→DISPUTED→SETTLED→COMPLETED |
| ShadowContractDeployer | 9-stufig: Compile→Deploy→Gnosisscan→GoBD |
| PrivateClientBridge | 6-stufig: SEPA→vIBAN→Reconcile→Monerium→Verify |
| MilestoneConditionChecker | 9-stufig: IoT→ZK→Quantity→Quality→Schedule→Release |
| TaxSimulationAgent | 9-stufig: §13b→BZSt→Split→ELSTER→PDF/A-3 |
| RetentionVaultManager | VOB/B §17: 5% Einbehalt, 4-Jahres-Frist, Aval-Bürgschaft |
| AuditorDashboardComposer | Read-Only RPA-Dashboard + Completion Certificate |
| PilotMetricsCollector | 21.600× Speedup, 99.85% Reliability, 88.4 SUS |
| GovernmentOnboardingKit | EVB-IT-Vertrag, DSGVO-DSFA, Sandbox-Demo-Zugang |

### Wave 19 Detail: Multi-Stakeholder Onboarding & Ecosystem (9 Agents)

5 Zielgruppen — Handwerker, Bauherren, Software-Partner, IoT-Hersteller, Banken. Flywheel: Jeder integrierte Partner zieht weitere an.

| Agent | Funktion |
|-------|----------|
| EcosystemOnboardingOrchestrator | Root: 5-Rollen-Routing, Batch-Onboarding, Ecosystem Health |
| CraftsmanOnboardingAgent | BundID→IBAN→BZSt→ERC-4337→Freemium, Sofort-Auszahlung in <60s |
| DeveloperOnboardingAgent | API-Keys, SDK (Python/TS/.NET), Sandbox, Rate Limits |
| BuilderOnboardingAgent | GAEB-Upload, Escrow, Shadow-Contract-Init |
| IoTPartnerOnboardingAgent | peaq-DID-Registrierung, Telemetrie-Oracle |
| BankingPartnerOnboardingAgent | ISO-20022-Endpoint, Settlement-Node |
| ComplianceEnrollmentAgent | KYB, AML, BZSt-Steuer-ID-Validierung |
| EcosystemHealthMonitor | Real-Time Health Dashboard, 24h-Metriken, Rollenverteilung |
| PartnerSuccessManager | Rollenbasierte Empfehlungen, Upsell-Erkennung |

### Wave 20 Detail: CertiK Security Audit & Formal Verification Engine (9 Agents + 81 Subagents)

Mathematisch verifizierte Sicherheitsprüfung für Smart Contracts, L1/L2-Infrastruktur und das gesamte Agent X B2G Ökosystem. Integriert mit BSI C5, ISO 27001, SOC2 Type2, GoBD, eIDAS und DSGVO Compliance.

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| SmartContractStaticAnalyzer | ReentrancyDetector, IntegerOverflowChecker, GasOptimizationFinder, ShadowVariableScanner, UncheckedCallAuditor, MathInvarianceVerifier, CallStackDepthChecker, SolcBytecodeDiff, CodeComplexityScorer | Statische Code-Analyse: Reentrancy, Integer Overflow, Gas, Shadow Variables, Unchecked Calls, Math, Call Stack, Bytecode Diff, Complexity |
| AccessControlAndGovAuditor | MultiSigConfigVerifier, TimelockDelayValidator, PrivilegeEscalationScanner, AdminKeyCentralizationScorer, EmergencyPauseVerifier, ProxyUpgradeGuard, RoleBasedAccessChecker, OwnershipTransferAuditor, GovernanceQuorumAnalyzer | Access Control & Governance: MultiSig, Timelock, Privilege Escalation, Zentralisierung, Emergency Pause, Proxy, RBAC, Ownership, Quorum |
| OracleAndDeFiDynamicsTester | FlashLoanAttackSimulator, OracleManipulationChecker, TWAPWindowValidator, MEVSandwichGuard, SlippageToleranceAuditor, CollateralFactorStressTester, LiquidationThresholdAuditor, ArbitrageLoopDetector, TokenomicsBurnValidator | Oracle & DeFi: Flash Loan, Oracle Manipulation, TWAP, MEV, Slippage, Collateral, Liquidation, Arbitrage, Tokenomics |
| L1L2InfrastructureAuditor | ConsensusMechanismValidator, CryptographicPrimitiveChecker, SybilAttackResilienceScorer, 51PercentAttackCostCalc, RPCNodeSecAuditor, PeerDiscoverySanitizer, CrossChainBridgeGuard, ValidatorSlashingAuditor, HardforkStateVerifier | L1/L2 Infrastructure: Consensus, Cryptography, Sybil, 51%-Attack, RPC, Peers, Bridge, Slashing, Hardfork |
| FormalVerificationEngine | Z3TheoremProver, SMTLibSpecGenerator, InvariantDefinitionChecker, SymbolicExecutionRunner, StateMachineExhaustivityTester, BoundaryValueProver, EquivalenceChecker, FormalPropertyEncoder, CertificateProofGenerator | Mathematische Beweisführung: Z3, SMT-LIB2, Invarianten, Symbolic Execution, State Machine, Boundary, Equivalence, VOB-Properties, Zertifikate |
| PenetrationAndFuzzingAgent | EchidnaFuzzingRunner, FoundryInvariantTester, MutationTestingEngine, ExploitationPayloadGenerator, ReplayAttackSimulator, BoundaryConditionFuzzer, TransactionOrderingFuzzer, AnomalyInjectionEngine, HeapStackOverflowScorer | Dynamisches Testen: Echidna, Foundry, Mutation, Exploits, Replay, Boundary, TX-Ordering, Anomaly-Injection, Heap/Stack |
| C5AndBSIGovernmentCertifier | BSIC5CriteriaMatcher, ISO27001ControlChecker, SOC2Type2Auditor, GoBDInvarianceVerifier, eIDASValidationAuditor, GDPRPrivacyAuditScanner, EVBITContractGuard, PenetrationTestReportFormatter, BSIExecutiveSummaryGenerator | Behörden-Compliance: BSI C5, ISO 27001, SOC2, GoBD, eIDAS, GDPR, EVB-IT, Pentest-Report, BSI-Summary |
| RealTimeThreatMonitor | OnChainMempoolWatcher, FrontrunningDetector, AnomalyStateObserver, CircuitBreakerAutoTrigger, MaliciousBytecodeDetector, SuspiciousWithdrawalGuard, AntiSybilMempoolFilter, ThreatLevelEscalator, AutomatedFreezeRelayer | Echtzeit-Überwachung: Mempool, Frontrunning, Anomalien, Circuit Breaker, Malicious Bytecode, Withdrawal Guard, Sybil Filter, Eskalation, Freeze Relay |
| CertiKAuditReportComposer | CertiKScoreCalculator, VulnerabilityCategorizer, RemediationPlanGenerator, ExecutiveSummaryDrafter, TechnicalDeepDivePackager, PublicBadgeCertifier, CodeFixValidator, AuditTrailWORMArchiver, CertiKCertificationPublisher | Zertifizierung: Score, Kategorisierung, Remediation, Summary, Deep Dive, Badge, Fix-Validation, WORM-Archiv, Publishing |

**Key characteristics:**
- 81 Subagenten in 9 Gruppen — vollständige Security-Audit-Abdeckung
- Formal Verification: Z3-Theorem-Prover, SMT-LIB2, Conservation-of-Funds-Invariante
- BSI C5, ISO 27001, SOC2 Type2, GoBD, eIDAS, GDPR, EVB-IT, MiCAR Compliance
- Real-Time Threat Monitoring: Mempool-Watching, Frontrunning-Detection, Circuit-Breaker
- CertiK Security Score (A+ bis F) mit Remediation-Plänen und Web3-Badge
- Multi-Tenancy: Alle Reports unter `{data_root}/{user_id}/audits/`
- JSONLogger für alle 81 Subagenten
- try/except + Retry mit exponentiellem Backoff auf jeder Node
- E2E Test: `python3 scripts/test_wave20_security.py` — 15 Test-Gruppen, 164/164 passed

### Wave 21 Detail: Skynet Dynamic Security Score & Real-Time Monitoring (9 Agents + 54 Subagents)

Kontinuierliches Echtzeit-Sicherheitsmonitoring mit 6 gewichteten Säulen. Überführt das einmalige CertiK-Audit (Wave 20) in einen dynamischen Live-Score.

**6-Pillar-Weighting (env-konfigurierbar):**

| Pillar | Weight | Quelle |
|--------|--------|--------|
| Code Security (P1) | 30% | Static + Dynamic Scan, Bug Bounty, Formal Proofs, Zero-Day DB |
| Operational Security (P3) | 25% | MultiSig, Timelock, HSM, RPC Uptime, SOC2/ISO27001, Key Rotation |
| Governance Strength (P6) | 15% | Gini, Voter Distribution, Insider Holdings, Quorum, Flash-Loan Guard |
| Market Stability (P4) | 15% | Liquidity Depth, Whale Concentration, Volatility, Slippage, Wash Trading |
| Fundamental Health (P2) | 10% | Commit Velocity, Developer Count, Spec Coverage, Docs, Dependencies |
| Community Trust (P5) | 5% | Sentiment NLP, Bot Density, Discord/Telegram, Phishing Detection |

**Agent Structure:**

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| SkynetOrchestrator | — | Root: 6-Pillar Pipeline, weighted score, alert engine, dashboard |
| CodeSecurityRatingAgent | 9 | Remediation, Patch, VulnWeight, BugBounty, Compiler, Static, Proof, ZeroDay, Aggregator |
| FundamentalHealthAgent | 9 | Commits, Devs, Spec, Docs, Branch, Deps, Reputation, Reviews, TestCoverage |
| OperationalSecurityAgent | 9 | MultiSig, Timelock, HSM-Key, RPC, Cloud, Pause, Rotation, HSM, AuditLog |
| MarketStabilityAgent | 9 | Liquidity, Whale, Volatility, Slippage, Volume, Wash, Vesting, IL, OrderBookDepth |
| CommunityTrustAgent | 9 | Sentiment, Bots, Mentions, Discord, Telegram, Phishing, GovSentiment, Influencer, DeveloperActivity |
| GovernanceStrengthAgent | 9 | Gini, Voters, Insider, Delegation, Quorum, ExecTimelock, FlashLoan, Veto, ProposalSuccess |
| SkynetRiskAlertEngine | — | Score-Drop-Detektor, Critical-Threshold-Warnung, Freeze-Signal |
| SkynetDashboardComposer | — | Radarchart, Badge, Leaderboard, PDF-Export, Checksum |

**Key characteristics:**
- 6 Pillars mit konfigurierbaren Gewichten (env `SKYNET_W_*`)
- Skynet Score = Σ(pillar_raw × weight), 0–100
- Rating: SECURE_EXCELLENT (≥85) / ACCEPTABLE_MODERATE (≥70) / CRITICAL_WARNING (<70)
- Alert bei Score-Drop >5 Punkte oder Score <60
- Multi-Tenancy: Alle Reports unter `{data_root}/{user_id}/skynet/`
- JSONLogger + _safe_call auf allen 54 Subagenten
- E2E Test: `python3 scripts/test_wave21_skynet.py` — 80/80 passed

### Wave 22 Detail: Ops Security — Secure Relay & Automated Deployment (9 Agents + 36 Subagents)

Schließt die drei verbleibenden Lücken zu OpenZeppelin Defender: Relay-Infrastruktur, serverlose Autotasks und Deployment-Verifikation.

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| KeyVaultManager | HSMConnector, KeyRotationScheduler, SigningProxy, AuditLogWriter | Verwaltet private Schlüssel in eingebetteten, sicheren Tresoren |
| GasOptimizer | FeeEstimator, ResubmissionEngine, ChainProfiler, MEVProtectionAdvisor | Multi-Chain Gas-Preis-Optimierung und automatische Resubmission |
| NonceManager | NonceTracker, GapDetector, ConflictResolver, ChainStateReconciler | Zuverlässiges Nonce-Tracking und Konfliktlösung |
| MetaTxEngine | UserOpBuilder, PaymasterIntegrator, BundlerClient, EntryPointValidator | ERC-4337 Meta-Transaktions-Infrastruktur für gaslose UX |
| AutotaskScheduler | CronScheduler, WebhookListener, SandboxExecutor, ConditionEvaluator | Serverlose Automatisierung mit Cron + Webhooks + IFTTT |
| WebhookIntegrator | WebhookReceiver, SignatureVerifier, RateLimiter, PayloadValidator | Externe Event-Ingestion mit HMAC/ECDSA-Sicherheitsprüfung |
| ConditionExecutor | ThresholdTrigger, TimeBasedTrigger, EventBasedTrigger, ActionDispatcher | Führt Aktionen nur bei erfüllten Bedingungen aus (IFTTT) |
| DeployVerifier | BytecodeComparator, SourceVerifier, StorageLayoutChecker, CompilerFlagValidator | Post-Deployment-Bytecode-Verifikation und Source-Matching |
| SecureDeployOrchestrator | MultiSigApprover, StagedRolloutManager, RollbackGuard, DeploymentAuditor | Multi-Sig-gesteuerte, gestaffelte Deployments mit Rollback |

**Key characteristics:**
- 36 Subagenten in 9 Gruppen — Relay, Autotasks, Deploy-Verification
- Multi-Sig via Safe/Fireblocks: mindestens 2 von N Signaturen für Deployments
- ERC-4337 EntryPoint-Integration für gaslose Transaktionen
- Serverlose Autotasks: Cron + Webhooks + IFTTT-Conditions
- Post-Deploy: Bytecode-Diff, Source-Verification, Storage-Layout-Check
- 10 Chains supported: Ethereum, Polygon, Arbitrum, Optimism, Base, Gnosis, peaq, zkSync, Linea, Scroll
- Multi-Tenancy: Keys + Deployments unter `{data_root}/{user_id}/`
- JSONLogger + _safe_call auf allen 36 Subagenten
- E2E Test: `python3 scripts/test_wave22_ops.py` — 48/48 passed

### Wave 23 Detail: Token Creation, Governance & Launch Engine (9 Agents + 81 Subagents)

Vollständiger Lebenszyklus: Tokenomics → ERC-20-Deploy → Vesting → DEX → DAO → Compliance → Airdrop → Metadata.

| Agent | Sub | Funktion |
|-------|-----|----------|
| TokenomicsArchitect | 9 | Supply-Cap, Inflationsmodell, Allocation-Split, Staking-Yield, Burn-Mechanismus, Makro-Stabilitätstest |
| TokenContractDeployer | 9 | ERC-20-Standard-Selektor, OpenZeppelin-Compiler, Fee-Modul, CREATE2-Predictor, Explorer-Verifier |
| VestingAndVaultManager | 9 | Cliff-Enforcer, Lineare-Freigabe, Merkle-Vesting, Team-Lockup, Treasury-Vault |
| LiquidityPoolInitializer | 9 | Preis-Kalkulator, DEX-Router, LP-Token-Lock, Slippage-Guard, MEV-Protection |
| TokenGovernanceEngine | 9 | ERC20Votes, Governor-Deploy, TimelockController, Quorum-Calc, Snapshot-Integration |
| RegulatoryComplianceGuard | 9 | MiCAR-Klassifikation, Howey-Test, OFAC/EU/UN-Sanktionen, KYB/KYC, Steuer-Export |
| AirdropAndClaimDistributor | 9 | Merkle-Tree, Sybil-Filter, Claim-Deployer, ERC-4337-Gasless, Unclaimed-Recycler |
| TokenMetadataAndBranding | 9 | IPFS-Upload, Token-List-Builder, CoinGecko/CMC-Submission, ENS-Writer |
| TokenLaunchOrchestrator | 9 | Lifecycle-Engine (DESIGN→LIVE), Pipeline-Guard, Gas-Estimator, MultiSig-Coordinator, Launch-Monitor |

**Key characteristics:**
- 9 × 9 = 81 Subagenten
- 6-Phasen-Lifecycle: DESIGN → COMPILED → VERIFIED → DEPLOYED → PAIRED → LIVE
- MiCAR/SEC-Howey BLOCKING-Gate vor Deployment
- ERC-20Permit + Gasless-Claims via ERC-4337
- Multi-Tenancy: Tokens unter `{data_root}/{user_id}/tokens/`
- JSONLogger + _safe_call auf allen 81 Subagenten

### Wave 24 Detail: Trading Infrastructure (9 Agents)

DEX-Routing, AMM-Tick-Management, MEV-Schutz und Market Making.

| Agent | Funktion |
|-------|----------|
| DEXLiquidityRouter | Best-Price Routing & Multi-Hop Swaps über Uniswap v3, Curve, Balancer |
| AutomatedMarketMakerAgent | Uniswap v3 Concentrated Liquidity Tick Management |
| LimitOrderBookEngine | On-Chain Limit Orders & Trigger Executions |
| MarketMakingStrategyAgent | Spread-Management & Bestandskontrolle |
| CrossChainSwapRelayer | LayerZero/CCIP Cross-Chain Swaps |
| MEVAndSlippageProtectionAgent | Anti-Sandwich, Private RPCs & Max Slippage |
| GasOptimalTradeExecutor | ERC-4337 Meta-Transactions & Paymaster Sponsoring |
| FeeAndDividendDistributor | Buyback-and-Burn & Staking Dividends |
| TradingAnalyticsAndRiskMonitor | Real-Time VWAP, Volatility & Circuit Breaker |

**Key characteristics:**
- 9 Agenten für vollständige Handelsinfrastruktur
- Multi-DEX-Routing über 5 DEXes (Uniswap v3, Curve, Balancer, PancakeSwap, SushiSwap)
- MEV-Schutz: Flashbots, Private RPC, Slippage-Guard
- ERC-4337 Gasless Trading via Paymaster
- Cross-Chain: LayerZero + CCIP Bridge-Integration
- Circuit Breaker bei >5% Verlust oder extremer Volatilität
- JSONLogger + _safe_call auf allen Agenten

### Wave 25 Detail: Institutional Smart Wallet & Identity Engine (9 Agents + 81 Subagents)

ERC-4337 Smart Wallet für Behörden mit Multi-Sig, BHO-Kassenführung und eIDAS-Identität.

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| AccountAbstractionEngine | UserOpBuilder, PaymasterSponsor, EntryPointValidator, FiatBridgeOnRamp (9) | ERC-4337 Smart Wallet mit SEPA-Instant-FiatBridge |
| MultiSigAndSessionManager | SignerRegistry, BiometricVerifier, SessionTimeoutGuard (9) | 2/3-Multi-Sig mit biometrischen Sessions |
| BHOZeroSumValidator | DepositTracker, DisbursementLedger, BalanceReconciler (9) | §71-BHO-Kassenidentität Δ≤0,01€ in Echtzeit |
| eIDASIdentityAndCompliance | BundIDConnector, QESVerifier, GeofenceChecker, RoleMapper (9) | eIDAS-Identität mit BundID + QES |
| ZKPrivacyShield | Groth16Prover, BalanceShielder, PublicAuditView (9) | Zero-Knowledge-Privacy für Salden |
| CrossChainUnifiedTreasury | UnifiedLedger, YieldEngine, BudgetPeriodManager (9) | Chain-übergreifende Treasury + Haushaltsperiode |
| IntentBasedTxSigner | IntentParser, ParamValidator, MultiSigCollector (9) | Intent-basierte Signierung (statt raw TX) |
| SuccessionAndRecoveryManager | GuardianRegistry, TimelockEnforcer, CouncilApprovalGate (9) | Amtsübergabe + Social Recovery |
| GoBDSnapshotArchiver | WORMWriter, TaxCategorizer, AuditTrailVisualizer (9) | GoBD-WORM-Archiv mit Timeline-Visualisierung |

**Key characteristics:**
- 9 Agenten × 9 Subagenten = 81 Prüfungen
- ERC-4337 Account Abstraction mit B2G-Paymaster
- BHO-Zero-Sum als BLOCKING-Gate vor jeder Zahlung
- eIDAS/BundID-Identity mit QES für Beträge >5.000€
- ZK-Privacy (Groth16) für Salden und Transaktionen
- BudgetPeriodManager verhindert Haushaltsüberziehung
- Amtsübergabe mit 30-Tage-Timelock + Ratsbeschluss
- Multi-Tenancy: Wallets unter `{data_root}/{user_id}/wallet/`
- JSONLogger + _safe_call auf allen 81 Subagenten

### Wave 27 Detail: Binnenmarkt-Clearing & Settlement Engine (9 Agents + 81 Subagents)

Multilaterales Netting: 100 Binnenmarkt-Transaktionen pro Monat schmelzen auf eine einzige Netto-Überweisung zusammen — mit mathematischem BHO-Zero-Sum-Beweis.

**9-Stufen-Pipeline (E2E: 122/122 tests passed):**
```
Accumulator → Bilateral → Multilateral → Priority → Dispatch → Verify → Gateway → Track → Archive
  100 TXs       Matrix       Cycles       Sorted       1 Payment     Δ=0 Proof    Bank sync    99% Reduction   WORM
```

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| TransactionAccumulator | InvoiceNormalizer, DateRangeFilter, CurrencyHarmonizer, DuplicateDeductor, CounterpartyResolver, ValueDateNormalizer, TransactionHasher, RawDataValidator (9) | Sammelt & normalisiert alle Binnenmarkt-TXs eines Monats |
| BilateralNettingEngine | OwedAmountCalc, DebtAmountCalc, NetPositionCalc, MutualSettlementEligibility, CreditLimitEnforcer, OverduePenaltyAccumulator, EscrowReleaseCoordinator, DisputeResolutionMarker (9) | Saldiert gegenseitige Forderungen A↔B |
| MultilateralNettingAggregator | DirectedGraphBuilder, CycleDetector, NettingOptimizer, CentralCounterparty, DebtCompressionEngine, LiquiditySavingCalculator, CollateralManager, DefaultHandlingEngine (9) | Löst Dreiecks-Schulden auf (A→B→C→A) via Topological Sorting + CCP |
| SettlementPriorityQueue | MaturityDateSorter, LiquidityCriticalityScorer, RegulatoryDeadlineChecker, PoliticalPriorityEnforcer, MinimumAmountThresholdFilter, EarliestPaymentDateScheduler, InterestAccrualBypasser, SlashAndBurnExecutive (9) | Sortiert Zahlungen nach Dringlichkeit & Fälligkeit |
| FinalSettlementDispatcher | SinglePaymentPreparer, BatchPaymentSplitter, AtomicSettlementExecutor, GaslessPaymasterTrigger, MultiSigApprovalCollector, ReceiptGenerator, FallbackBankTransferPreparer, DisbursementConfirmer (9) | Führt die eine Netto-Überweisung atomar aus |
| SettlementVerificationOracle | BHOZeroSumChecker, HaushaltsdeckungsPrüfer, CounterpartySolvencyChecker, SettlementComplianceGate, Z3ProofGenerator, AuditTrailComparator, DoubleSpendPreventer, VerificationSigner (9) | Mathematische BHO-Δ=0-Prüfung vor Ausführung |
| FiatGatewaySynchronizer | BankStatementImporter, BalanceReconciliationEngine, PendingTransactionMatcher, FXRateConverter, BankFeeDeductor, SEPAPaymentTrigger, AccountingEntryGenerator, FiatWithdrawalExecutioner (9) | Gleicht On-Chain-Saldo mit Hausbank ab |
| NettingEfficiencyTracker | TxReductionRatioCalc, LiquiditySavingIndex, TimeToSettlementComparator, GasCostAvoidanceCalc, OperationalCostSavings, RiskReductionScorer, DashboardVisualizer, BenchmarkingEngine (9) | Misst Reduktion (Ziel: >95%) & Einsparungen |
| SettlementAuditArchiver | NettingDecisionLogger, TransactionHistoryFreezer, BHOProofArchiver, SignerKeyRecorder, GoBDCompliantFormatter, WORMStorageWriter, RetentionPolicyEnforcer, AuditorAccessManager (9) | GoBD-WORM-Archivierung (10 Jahre) |

**Key characteristics:**
- 9 Agenten × 9 Subagenten = 81 Prüfungen
- Multilaterales Netting mit Cycle Detection & CCP-Fallback
- 100 Transaktionen → 1 Netto-Zahlung (≥95% Reduktion)
- BHO-Zero-Sum (Δ≤0,01€) als BLOCKING-Gate
- Z3-Proof-Generator für mathematische Korrektheit
- Liquidity Savings: Gas + Buchhaltungskosten eingespart
- SEPA-Instant-Fallback bei On-Chain-Fehlern
- ERC-4337 Gasless Settlement via Paymaster
- Multi-Tenancy: Reports unter `{data_root}/{user_id}/clearing/`
- JSONLogger + _safe_call auf allen 81 Subagenten
- E2E Test: `python3 scripts/test_wave27_clearing.py` — 122/122 passed

### Wave 28 Detail: External Threat Defense & Swarm Immunity (9 Agents + 81 Subagents)

Aktive, lernende Abwehr gegen externe Bedrohungen. Schwarm-Erkennung, Perimeter-Schutz, Honeypot-Fallen und selbstlernende KI-Abwehr.

**8-Stufen-Defense-Pipeline (E2E: 105/105 tests passed):**
```
Perimeter → Radar → Classifier → Response → Honeypot → Learning → Intel → Dashboard
  Gateway    Swarm    Threat     Counter    Deception    Model    External   KPI
```

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| PerimeterGatewayDefender | RateLimiter, CredentialValidator, ReputationScoreLookup, GeoFencingEnforcer, SybilDetector, AnomalyHeaderInspector, TLSFingerprinter, ChallengeResponseRequester (9) | Authentifiziert & filtert eingehende Anfragen |
| SwarmDetectionRadar | TemporalCorrelationAnalyzer, SpatialCorrelationAnalyzer, BehavioralPatternMatcher, GraphClusteringEngine, EntropyScoreCalculator, VolumeSpikeDetector, HoneypotTriggerAnalyzer, SwarmSignatureDatabase (9) | Erkennt koordinierte Bot-Schwärme |
| ThreatClassifierEngine | MEVArbitrageClassifier, BidCartelClassifier, YieldVacuumClassifier, SurveillanceSwarmClassifier, SybilSwarmClassifier, DDoSPreClassifier, ReconnaissanceClassifier, ConfidenceScorer (9) | Identifiziert Angriffstyp (MEV, Kartell, Sybil, DDoS) |
| ActiveResponseCoordinator | ThrottlingEnforcer, LatencyInjectionEngine, HoneypotRouter, RateLimitEnforcer, IPBanEnforcer, LegalEvidenceCollector, CounterSwarmDeployer, EscalationTrigger (9) | Abgestufte Gegenmaßnahmen |
| DeceptionAndHoneypotFactory | FakeTenderGenerator, DecoyLiquidityPool, FakeKYCIdentityProvider, SimulatedVulnerability, HoneypotContractDeployer, AttackerBehaviorLogger, DeceptionNetworkManager, IntelligenceGatherer (9) | Baut Köder-Umgebungen zur Angreifer-Analyse |
| SwarmLearningAdapter | AttackVectorDatabase, ReinforcementLearner, PatternEvolutionTracker, FalsePositiveAnalyzer, AdversarialTrainingEngine, FeatureExtractor, ModelVersionManager, HumanFeedbackIntegrator (9) | Trainiert Abwehr an vergangenen Angriffen |
| ExternalIntelAggregator | ChainalysisAPIAdapter, FortaNetworkListener, CVEExploitDatabaseCrawler, DarkWebMonitor, SocialMediaSentimentAnalyzer, GovernmentThreatFeed, OpenSourceIntelParser, CrossChainThreatCorrelator (9) | Externe Threat-Intelligence |
| DefenseMetricsDashboard | AttackVolumeGauge, ThreatTypeDistribution, ResponseSuccessRate, SwarmHeatmap, HoneypotActivityLog, LearningProgressTracker, ActiveDefensesList, IncidentTimelineView (9) | Echtzeit-Bedrohungslage für Kämmerer |

**Key characteristics:**
- 9 Agenten × 9 Subagenten = 81 Prüfungen + DefenseOrchestrator
- Perimeter: Rate Limiting, Geo-Fencing, TLS-Fingerprinting, Proof-of-Work
- Schwarm-Erkennung: 5 Signal-Typen (Temporal, Spatial, Behavioral, Graph, Entropy)
- Klassifizierung: 7 Angriffstypen (MEV, Cartel, YieldVacuum, Surveillance, Sybil, DDoS, Recon)
- Response: 8-stufige Eskalation (Throttle → Latency → Honeypot → RateLimit → IPBan → Evidence → CounterSwarm → Human)
- Honeypots: Fake Tenders, Decoy Pools, Fake KYC, Simulated Vulnerabilities
- Learning: Reinforcement Learning + Adversarial Training + Human Feedback
- External Intel: Chainalysis, Forta, CVE/NVD, DarkWeb, BSI/BaFin
- Multi-Tenancy: Reports unter `{data_root}/{user_id}/defense/`
- JSONLogger + _safe_call auf allen 81 Subagenten
- E2E Test: `python3 scripts/test_wave28_defense.py` — 105/105 passed

### Wave 29 Detail: Token Runtime Operations — $AGX Live Mechanics (9 Agents + 81 Subagents)

Laufender $AGX-Token-Betrieb: Compute-Abrechnung auf L1, Slashing für IoT-Manipulation, Priority-Queue für VOB/B-Zahlungen, Dispute-Bonds, Buyback-and-Burn, Live-Staking-Yields, Oracle-Entlohnung, ERP-Quota.

**9-Stufen-Runtime-Cycle (E2E: 101/101 tests passed):**
```
ComputeFuel → Slashing → PriorityQueue → DisputeBond → BuybackBurn → LiveYield → OraclePay → ERPQuota
```

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| ComputeFuelAuctioneer | ProofCostEstimator, ZKCircuitPricer, SkynetScanFeeCalc, MempoolAuctionEngine, UtilizationTracker, SurgePricingEngine, PrepaidBalanceManager, SolverCompetitionRanker (9) | Z3/ZK/Skynet-Rechenleistung in $AGX abrechnen |
| SlashingAndPenaltyExecutor | ViolationDetector, SlashingCalculator, LiquidationEngine, BurnDistributor, AppealProcessor, ReputationDeductor, EventBroadcaster, OffenseTracker (9) | $AGX-Stake bei IoT-Fälschung verbrennen |
| PriorityQueueAccessManager | PriorityScoreCalc, SlotAllocator, FeeCalculator, QueuePositionTracker, BumpEngine, FairnessAuditor, LatencyGuarantor, AccessAuditLogger (9) | VOB/B-Zahlungen von High-Stakern priorisieren |
| DisputeBondEscrowAgent | BondDepositHandler, EscrowStateMachine, ArbitrationInitiator, ExpertFeeAllocator, ForfeitureProcessor, SettlementFinalizer, TimerManager, AppealCoordinator (9) | Kautions-Gelder bei VOB/B-Streitigkeiten verwalten |
| BuybackAndBurnRelayer | FeeAggregator, BuybackScheduler, DEXSelector, SlippageGuard, BurnExecutor, SupplyTracker, DeflationDashboard, BurnAuditLogger (9) | Protokollgebühren → $AGX-Rückkauf + Verbrennung |
| LiveYieldAndStakingOperator | PoolManager, RewardCalculator, CompoundingEngine, CooldownEnforcer, YieldAdjuster, MigrationCoordinator, PerformanceScorer, WithdrawalManager (9) | Sekündliche Staking-Renditen ausschütten |
| OracleDataFeeDispatcher | OracleRegistry, DataFreshnessChecker, ChainlinkPayer, WeatherOraclePayer, DINNormPayer, PerformanceTracker, DisputeResolver (9) | Chainlink/Wetter/DIN-Orakel in $AGX entlohnen |
| ERPQuotaAccessManager | ERPRegistry, TierAssigner, RateLimitEnforcer, SAPConnector, DATEVExporter, ThroughputMonitor, OverageFeeCalculator, UpgradePathAdvisor (9) | SAP/DATEV-API-Durchsatz gegen $AGX-Holding |

**Key characteristics:**
- 9 Agenten × 9 Subagenten = 81 Prüfungen + TokenRuntimeOrchestrator
- $AGX-Flywheel: Compute → Slashing → Priority → Burn → Yield → Oracle → ERP
- Buyback-and-Burn: 20% der Protokollgebühren → DEX-Kauf → Verbrennung
- Slashing: 10% des Stakes bei IoT-Manipulation, 50% an Whistleblower
- Staking: 5% Basis-APY, 7-Tage-Cooldown, Compound-Option
- ERP-Tiers: FREE / STANDARD / PREMIUM / PLATINUM nach $AGX-Holding
- Multi-Tenancy: Reports unter `{data_root}/{user_id}/token_runtime/`
- JSONLogger + _safe_call auf allen 81 Subagenten
- E2E Test: `python3 scripts/test_wave29_tokenomics.py` — 101/101 passed

### Wave 31 Detail: Omnichannel UX & Verwaltungs-Dashboard (9 Agents + 81 Subagents)

Menschliche Schnittstelle zum gesamten Agent-X-Stack. Rollenbasierte Dashboards, Responsive Web (Mobile/Tablet/Desktop), Sprach-Assistent mit Intent-Erkennung, Workflow-Visualisierung, Real-Time-Analytics, Sandbox-Simulationen, Smart Alerts und GoBD-Berichte.

**4-Stufen-Render-Pipeline (E2E: 92/92 tests passed):**
```
RoleDashboard → Analytics → Alerts → Portal
    6 Rollen     5 KPIs     Push+SMS   Mobile/Desktop
```

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| RoleBasedDashboardComposer | UserRoleResolver, PermissionMatrixLoader, DashboardLayoutBuilder, KpiSelectorForRole, ActionButtonVisibility, WidgetOrchestrator, DataPreaggregator, ThemeAndAccessibilityController (9) | Personalisierte Dashboards für 6 Rollen (Kämmerer, Bauleiter, Prüfer, Bürger, Entwickler, Bank) |
| ResponsiveWebPortal | MobileFirstDesignEngine, TabletOptimizedRenderer, DesktopPowerUserMode, OfflineDataSynchronizer, ProgressiveWebAppInstaller, AccessibilityChecker, LocalizationAndCurrency, SessionTimeoutManager (9) | WCAG 2.1 AA, PWA, Offline-Support, Multi-Locale |
| NaturalLanguageAssistant | IntentRecognizer, EntityExtractor, CommandExecutor, ContextMemoryManager, VoiceToTextHandler, TextToVoiceResponder, ConfidenceScoreFilter, MultiLanguageSupport (9) | Sprach- & Chat-Steuerung (de/en/fr), 9 Intents |
| ProcessWorkflowVisualizer | MilestoneTimelineBuilder, ProgressIndicatorEngine, DependencyGraphRenderer, StatusColorCoder, FinancialBurnRateDisplay, DelayRiskHeatmap, GanttChartGenerator, CollaborationAnnotationEngine (9) | VOB/B-Meilensteine, Gantt-Charts, Risiko-Heatmaps |
| RealTimeAnalyticsHub | BHOZeroSumMonitor, NettingEfficiencyTracker, TokenFlywheelVisualizer, DefenseActivityHeatmap, LiquidityPoolPerformance, GasCostSaverCounter, ComplianceScoreDash, CustomizableReportBuilder (9) | BHO-Status, Netting-Effizienz, Token-Flywheel, Defense-Lage |
| SandboxSimulationPlayer | ScenarioParameterInput, BudgetImpactSimulator, MilestoneShiftSimulator, TokenPriceSimulator, NetworkLoadTester, RiskScenarioPlanner, ResultComparisonEngine, ScenarioAuditLogger (9) | "Was-wäre-wenn"-Szenarien für Haushaltsplanung |
| SmartAlertAndNotification | ThresholdBreachDetector, CriticalEventDistributor, PushNotificationSender, EmailReportGenerator, SMSGuardianSender, InAppMessageCenter, EscalationPolicyEngine, DoNotDisturbScheduler (9) | Push, E-Mail, SMS, 5-Stufen-Eskalation, DND-Modus |
| GoBDReportGenerator | GoBDCompliantFormatter, PDFExportEngine, DATEVExporter, XMLReportBuilder, QuarterlySummaryGenerator, YearlyAuditPackager, ArchiveSignatureAttacher, AccessControlReport (9) | PDF/A-3, DATEV-Export, XBRL (BaFin), WORM-Signaturen |

**Key characteristics:**
- 9 Agenten × 9 Subagenten = 81 Prüfungen + UXOrchestrator
- 6 Rollen: KAEMMERER, BAULEITER, PRUEFER, BUERGER, ENTWICKLER, BANKING_PARTNER
- Responsive: Mobile (1-col), Tablet (2-col), Desktop (3-col)
- NL-Assistant: 9 Intents (SHOW_BUDGET, SHOW_INVOICES, SHOW_PROJECT, SHOW_COMPLIANCE, RUN_SIMULATION, EXPORT_REPORT, SHOW_ALERTS, CONFIGURE, HELP)
- Assistenz-Sprachen: Deutsch, English, Français
- Sandbox: Budget-Simulationen, Token-Preis-Szenarien, Netzlast-Tests
- Alerts: Push, E-Mail, SMS mit 5-Stufen-Eskalation + DND (22–7 Uhr)
- GoBD: PDF/A-3, DATEV-CSV, XBRL (BaFin), WORM-Archiv, QES-Signaturen
- WCAG 2.1 AA, PWA-Installation, Offline-Synchronisation
- Multi-Tenancy: Reports unter `{data_root}/{user_id}/ux/`
- JSONLogger + _safe_call auf allen 81 Subagenten
- E2E Test: `python3 scripts/test_wave31_ux.py` — 92/92 passed

## Language

German for communication and documentation. Code comments in English.

## Version

Agent X Core: 0.4.0 (stable, 90/100 backtest). Agent X B2G: 0.24.7 (243 agents in 27 main waves plus Wave 3.5 and 25 compliance agents — 277 total, plus Wave 34 Finale Veredelung, Wave 35 SimChain (9 Agents × 3 Chains, 2.200+ lines, 199/199 tests), Wave 36 MultiChain Sovereign Appchains (9 Appchains × 4 Layers, 1.800+ lines, 113/113 tests), Wave 37 Demo Pipeline (9 Agents, 8 unique friction rates), plus Settlement (D01–D04 divers, C09 ingest, ComplianceExporter, ~1.500 lines), Crew (5-role pipeline + DID registry + 9 specialized agents), Gas (autonomous fuel management), Valhalla (ZK honor protocol), Surface Agents (C01–C09: NATS queue-group workers, adaptive batching, constraint metering, predictive health routing, 223k events/s burst), Subsurface Prover Factory (SGX-TDX/SEV-SNP/CUDA/CPU with curve unification), D01 Mock Responder (8 replicas, batch ZK, binary bisect quarantine), Ephemeral Paratroopers (F01–F03, 3 WASM modules compiled, 500ms TTL), Air Layer E2E: 18/18, Chaos Resilience: F07–F09 abgefangen (Chaos Fleet: killer, throttler, poison injector), Telemetry Ingest (MQTT/HTTP bridge, 7 endpoints), Chaos Matrix (10 attack scenarios), 8 Solidity contracts (inkl. ValhallaVerifier.sol, ProtoGalaxyVerifier.sol, Foundry/Solc 0.8.35) + ESP32 LoRaWAN Firmware (1.651 lines C++/Arduino), E2E: Waves 1–33 all green, Wave 34: 21/21, Wave 35: 199/199, Wave 36: 113/113, Wave 37: Pitch-fertig, Chaos Resilience: 4/4 experiments, Docker: 109+ containers, NATS: Core+JetStream (4222/8222), Anvil: Block 0→1 confirmed, CertiK Security Wave 20: 164/164, Skynet Monitor Wave 21: 80/80, Ops Security Wave 22: 48/48, Token Launch Wave 23: funktional, Trading Wave 24: FN=0/FP=0, Smart Wallet Wave 25: integriert, Clearing & Settlement Wave 27: 122/122, External Threat Defense Wave 28: 105/105, Token Runtime Operations Wave 29: 101/101, UX & Dashboard Wave 31: 92/92, Survival & Off-Grid Wave 33: 63/63, BSI C5/ISO 27001/SOC2/GoBD/eIDAS/GDPR/EVB-IT compliant, GAEB DA XML 3.3, XRechnung 3.0, VHB-221/222, GoBD/BHO-ready, 68.000+ lines, plus 5-Pillar Scale-Up — 1M-Tsunami (0 Loss, 54µs P99, 9.554 echte L1-Anker), Testnet-Bridge (EIP-1559), Overwatch-Dashboard (Prometheus/Grafana), Compliance-Playbook (K1–K7), K8s/Helm-Chart (KEDA+SGX), plus Wirtschafts-Schwarm + Rescue + CI-Resilienz + Humanitäre Logistik + Smart-Grid Meta-Stabilität (H1 falsifiziert, Plastizitäts-Hebel Stubs) — docs/SMART_GRID_ERGEBNIS.md).

```
0.24.7 (2026-08-17) — Smart Grid Meta-Stabilitäts-Studie (Dezentrale Energienetze):
- 9 Agenten A Erzeugung / B Flexibilität / C Netz-Guardians, Inverter-Flotten N_gen=9,
  Grid-Bus-Kopplung 0.60, Jitter ±5%
- H0 PASSES (R_grid ≈ 0.97, p=0.002, 10/10; W_dyn valid); Stress 10×3=30 Läufe
- H1 falsifiziert: Meta-Stabilität nicht bestätigt; W_dyn fällt in allen drei Fällen
  (Plastizitäts-Hebel sind Stubs). Bewölkung/Spitzenlast ΔR=0; Leitungsausfall
  ΔR=−0.29 (H1a CONFIRMED); H1b überall 0/10
- H2 CONFIRMED (Kruskal-Wallis p=0.0001); H3 deskriptiv
- Zentrale Erkenntnis: Plastizitäts-Hebel = fehlende Vorbedingung für Meta-Stabilität
  Details: docs/SMART_GRID_ERGEBNIS.md · Pre-Reg docs/SMART_GRID_PREREG.md
- Tests: scripts/test_smartgrid_*.py + run_smartgrid_h0 / run_smartgrid_stress_study

0.24.6 (2026-08-16) — Humanitäre Logistik Resilienz-Studie:
- 9 Agenten A Sensorik & Bedarf / B Transport & Logistik / C Governance & Priorisierung,
  Takt-Spreizung 3:1, Jitter ±10%, Heartbeat (2-min-Pull von OCHA)
- H0 PASSES (R≈0.95, 10/10); Stress 10 Seeds × 3 Szenarien = 30 Läufe
- H2+H3 CONFIRMED; H1 nur Hub-Verlust (ΔR=+0.11); Nachbeben/Komm-Kollaps
  degradieren Koordination nicht messbar (Heartbeat kompensiert), Effizienz trotzdem
  (ΔQuote +2–4%)
- Zentraler Zusatzbefund: Koordination ≠ Effizienz — synchronisiert ≠ effizient
  Details: docs/HUMANITAERE_LOGISTIK_ERGEBNIS.md · Pre-Reg docs/HUMANITAERE_LOGISTIK_PREREG.md
- Tests: scripts/test_hum_stress.py (6/6), run_hum_h0.py (10/10), run_hum_stress_study.py (30/30)

0.24.5 (2026-08-16) — CI-Resilienz-Studie (Kritische Infrastrukturen):
- 9 Agenten A Sensorik / B Aktorik / C Koordination, Takt 3/5/5/10 s (Option A)
- H0 PASSES (R=0.516, p=0.008, 10/10); Stress 10×3=30 Läufe
- H1+H2 CONFIRMED: Natur ΔR=0.16 > Blackout 0.13 > Cyber 0.02
- Caveats: Seeds byte-gleich; Cyber nur Payload (Fenster-Effekt)
  Details: docs/CI_RESILIENZ_STUDIE_ERGEBNIS.md · Pre-Reg docs/CI_RESILIENZ_STUDIE_PREREG.md
- Tests: scripts/test_ci_*.py + run_ci_h0 / run_ci_stress_study

0.24.4 (2026-08-16) — Rescue-Dichte-Studie (Option B): Dichte-Hypothese falsifiziert
- 10 Seeds × 4 Intervalle {15,25,40,70}s × 2 (baseline/Clearance) = 80 Läufe
- Vorab: Spearman R~log(1/interval) einseitig α=0.01 + Kruskal-Wallis
- Verdict NOT_CONFIRMED beiderseits (ρ=−0.34/−0.44, p(ρ>0)≈0.99)
- Befund 1 im Koordinations-Dossier verlinkt (Mechanismus offen)
  Details: docs/RESCUE_DICHTE_STUDIE.md · Commit Studie 17b0bc54

0.24.3 (2026-08-16) — Rescue-Koordination Emergence-Messung (Dossier):
- 9 Einheiten A/B/C, Nachrichten-Phase-Pull, exponentielle Szenario-Injektion,
  RoE-Clearance (Gewaltenteilung: nur C gibt frei), RNG-Trennung Szenario/Assessment
- Befund 1: Phasen-Pull-Koordination real, szenarioabhängig (dicht COORDINATED
  R=0.7582 p=0.002; dünner UNCOORDINATED) — Dichte-Hypothese später falsifiziert (0.24.4)
- Befund 2: RoE ≠ zweite-Ordnung-Kopplung (ΔR≈−0.0037, Falsifikation); Access-Control
- Befund 3: geteilter RNG war Confound; Fix ccf63be5. α=0.01 vorab.
  Details: docs/RESCUE_KOORDINATION_DOSSIER.md
- Tests: scripts/test_rescue*.py (22)

0.24.2 (2026-08-16) — Wirtschafts-Schwarm (Gewaltenteilung) Emergence-Messung:
- 9 Agenten, 3 Klassen (A Kapital / B Ausführung / C Governance), Bausteine 1–5:
  Fundament, Funktionsschranken (default-deny), Freigabe-Kreislauf, Routing
  (crc32-KlassenResolver), Kuramoto-Evaluator (AstroCore)
- Befund (IFI-Shuffle-robust): NO_COUPLING — Gewaltenteilung ist organisatorische,
  keine Kuramoto-Phasenkopplung; das IAAFT-COUPLED (r≈0.535, p<0.002) ist ein
  Periodizitäts-Artefakt der Sim-Frequenzen 2/3/4. Fire-Corridor bleibt die belegte
  Timing-Emergenz. Details: docs/WIRTSCHAFTS_SCHWARM_DOSSIER.md
- Tests: scripts/test_wirtschaft_*.py (6 Suiten) + scripts/cross_check_wirtschaft_ifi.py
- Monte-Carlo +1-Korrektur in AstroCore (p-Floor ≈ 0.002 bei 500 Surrogaten)

0.24.1 (2026-08-16) — Emergenz TIER 0 (Mess-Validität):
- Reproduzierbarkeit: zlib.crc32 statt hash() für Economic-Sharding
  (adapter_agentx.py + demo_producer_cluster.py); PYTHONHASHSEED-unabhängig
- TickController.run(): Docstring-Warnung Routing-No-op (Rollen-Adressierung)
  + Determinismus-Hinweis (kein builtins.hash für Arbeitsverteilung)
- Gate unverändert NO_COUPLING — Messung jetzt gültig

0.24.0 (2026-08-16) — Compliance-Härtung & Air-Layer:
- Air Interceptor Layer (A01–A09): Soft-Finality-Fastpath, Transient-CAS,
  Poison-Neutralisierung, AWACS-Datalink; test_air_layer.py 18/18
- Compliance-Gate: verified=30/42, claimed=1 (HW-Ceiling 1.1), attested=11,
  failed=0, gate=PASS, KONFORM_MIT_VORBEHALT (Probe-Promotion)
- E2E Integration: 25/25 (X84 GAEB-Pflichtfelder + BHO-Assertion)
- 6 echte Fixes: HSM-Default-PIN→Env, X84 DP/VersDate/UP/TotalAmount,
  CI-YAML-Reparatur (5 Jobs), Gewährleistung 5y→4y (VOB/B §13 Abs. 4),
  BHO-Assertion-Inversion, Fehler-Trunkierung [:3] aufgehoben
- Betrieb: SON-Nacht-Cron + Backup-Automatisierung, Probe-Regeln R1/R2
```

## 5-Pillar Scale-Up (2026-08-14)

Überführung von docker-compose (109+ Container) auf ein produktionsreifes Fundament. Kompletter L1-Kreislauf: `Producer → NATS → Surface → D01 → Epochen-Akkumulator → Anvil (echte Ethereum-TXs)`.

| Säule | Deliverable | Status |
|-------|-------------|--------|
| 4 · 1M-Tsunami | `scripts/verify_1m_tsunami.py` — 0 Loss, 54µs Surface-P99, 9.554 echte L1-Anker | ✅ |
| c · Testnet-Bridge | `SepoliaSettlementBridge` (EIP-1559 + Fee-Escalation, `L1_NETWORK`-Routing) | ✅ |
| d · Overwatch-Dashboard | Prometheus (1s Scrape) + Grafana (Port 3002), Dual-Format `/metrics` | ✅ |
| e · Compliance-Playbook | `docs/COMPLIANCE_PLAYBOOK.md` (K1–K7 Matrix + Auditor-Runbook + Probe-Promotion) | ✅ |
| a · K8s/Helm | `charts/agent-x/` (KEDA Event-Driven Autoscaling + SGX Resource Limits) | ✅ |

**Konservierungs-Invariante:** `Ingested = Cleared + Quarantined = L1 Settled` — 1.000.000 = 949.734 + 50.266 = 1.000.000.

**Test-Suites:** 1M-Tsunami 13/13, Smoke 13/13; `test_e2e_pipeline.py` im CLAUDE.md-Checker registriert.
