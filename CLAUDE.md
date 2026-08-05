# Agent X — Risk Management & B2G Procurement Platform

6-Klassen-Risikomanagement + 90-Agent B2G Public-Sector Procurement Engine.

## Overview

Two integrated systems sharing core infrastructure (SymbolicsAgent, Consensus Engine, Backtesting):

1. **Agent X Core** — DeFi risk management: 6 classes (A–F), 60+ agents, consensus-driven state evaluation with CHI (Composite Health Index), backtesting against 8 historical crisis scenarios.

2. **Agent X B2G** — Public-sector procurement: 117 agents in 13 waves covering the complete lifecycle from GAEB tender receipt through VOB/B multi-installment payment, defect/dispute arbitration, BHO-compliant treasury reconciliation, GoBD archiving, multi-chain notarization, operations, user/project management with BundID SSO, a complete query & reporting layer, and a **real-time macroeconomic engine** (Wave 17) with velocity tracking, inflation measurement, programmable fiscal stimulus, tax splitting, capital efficiency, cartel detection, and central bank ledger twin.

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
├── agents_b2g/                   # 117 B2G-Agenten in 13 Wellen (s.u.)
├── scripts/                      # Runner & Tests
│   ├── calibrate_agent_x.py      # Compound-Risk-Kalibrierung
│   ├── paper_trading_agent_x.py  # Paper-Trading mit Deep-Logging
│   ├── bootstrap_b2g.py          # B2G-Bootstrap
│   ├── end_to_end_90_agents.py   # 90-Agenten-10-Wellen-E2E-Test (11/11 passed)
│   ├── end_to_end_b2g_test.py    # 25-Schritte-E2E-Test
│   ├── test_gaeb_reference.py    # GAEB DA XML 3.3 Test Suite
│   ├── test_wave17_macro.py      # Wave 17 E2E: 8-Stufen-Makro-Pipeline (8/8 passed)
│   ├── fetch_xrechnung_schematron.py # XRechnung 3.0 Schematron Fetcher
│   └── export_backtest_signals.py # Backtest-Daten-Exporter
├── config/
│   └── calibration_config.yaml   # Kalibrierungs-Konfiguration
├── archive_b2g/                  # GAEB-XML + GoBD-JSON-Archiv
├── orchestrator_b2g_full.py      # 90-Agenten-10-Wellen-Pipeline, 342 lines
├── orchestrator_b2g.py           # B2G-Tendering-Bootstrap
├── cli_b2g_query.py              # CLI für alle Wave-10-Query-Agenten
├── docker-compose.yml            # 90 Container + Infrastruktur, 654 lines
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

### Architecture: 13 Waves × 9 Agents = 117 Agents

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
Wave 17 (MacroEconomy):     VelocityOfMoneyTracker → RealTimeInflationOracle →
                            SupplyChainMultiplierCalc → ProgrammableStimulusEngine →
                            RealTimeTaxSplitter → CapitalEfficiencyAnalyzer →
                            SystemicRiskAndCartelMonitor → CentralBankLedgerTwin
```

### Wellen-Übersicht

Welle 3.5 (VOB/B Disput) ist eine Unterwelle von Welle 3 (Execution) und wird nicht als eigenständige Hauptwelle gezählt. Die Gesamtzahl der Hauptwellen beträgt 13 (Wellen 1–10, 15, 16, 17). Die Wellen-Nummern 11–14 existieren nicht — die Nummerierung springt von 10 direkt auf 15 (Public Portal), 16 (SEPA Bridge) und 17 (MacroEconomy).

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

### B2G Module Structure

```
agents_b2g/
├── tendering/
│   └── agents.py                 # Wave 1: 9 agents, 741 lines
├── composing/
│   └── agents.py                 # Wave 2: 9 agents, 634 lines
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
│   └── pilot_agents.py           # Wave 8: 9 agents + PilotSupervisor + ALL_AGENTS, 760 lines
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
├── event_bus.py                  # Pub/Sub + JSONL Audit-Log
├── gov_procurement_agent.py      # Root Orchestrator, BHO thresholds
└── tender_reader_agent.py        # GAEB-XML Reader
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

- **E2E 90-Agent Test:** 11/11 waves passed (`scripts/end_to_end_90_agents.py`), 0.8s duration
- **E2E Integration Test:** 20/25 passed (`scripts/end_to_end_b2g_test.py`)
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

### Smart Contracts (Schwesterprojekt)

Die Smart Contracts befinden sich im Schwesterprojekt [`craft-procurement-engine`](https://github.com/craft-engine/craft-procurement-engine). Agent X interagiert mit ihnen über den `EscrowCoordinatorAgent` (Wave 3) und den `MultiChainAnchorAgent` (Wave 5).

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

# B2G — Full Pipeline (117 agents, 13 waves)
python3 orchestrator_b2g_full.py

# B2G — E2E Test (117 agents, 13 waves)
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

# Docker — Full Stack (117 agents + Redis/Neo4j/NATS/Prometheus/Grafana)
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
| nats | nats:2.10-alpine | JetStream message broker (replaces in-process EventBus) |
| prometheus | prom/prometheus:v2.55.0 | Metrics collection from all 117 agents |
| grafana | grafana/grafana:11.3.0 | Dashboards for ops and project management |

### Wave 10 Detail: Query & Reports (9 Agents)

| Agent | Subagenten | Funktion |
|-------|-----------|----------|
| VergabekammerQueryAgent | TenderHistoryFetcher, BidderComparison, VOBARuleChecker | Kartell-/Verstoßprüfung, Bietervergleich |
| RPAQueryAgent | PDFAuditComposer, LedgerExporter, HashVerifier | Rechnungsprüfungsbericht (PDF/A) mit BHO-Ledger + Chain-Anchors |
| ConstructionProgressQueryAgent | SollIstVergleich, GanttChartGenerator, DelayAnalyzer | GAEB-Plan vs. PoPW-Telemetrie, Baufortschritt |
| TreasuryQueryAgent | BalanceSheetCalculator, RetentionTracker, SEPATransactionExporter | Escrow-Saldo, 5%-Einbehalt, SEPA-Tracking |
| ComplianceQueryAgent | PIIAnonymizer, AuditTrailValidator, RetentionPolicyChecker | DSGVO/GoBD-Prüfung, JSONL-Vollständigkeit |
| ControllingQueryAgent | CostTrendAnalyzer, AgentUtilizationStat, OnTimeDashboard | Kosten, Auslastung (117 Agenten), Termintreue |
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

## Language

German for communication and documentation. Code comments in English.

## Version

Agent X Core: 0.4.0 (stable, 90/100 backtest). Agent X B2G: 0.8.0 (117 agents, 13 waves + Wave 3.5 VOB/B + 25 compliance agents, E2E: Waves 1-17, RPA + VK PDFs, GAEB DA XML 3.3, XRechnung 3.0, VHB-221/222, BVBS Sync, Public Portal Wave 15: 68/68 tests, SEPA Bridge Wave 16: 43/43 tests, MacroEconomy Wave 17: 8/8 E2E passed, MEHI 0.74 Grade B).
