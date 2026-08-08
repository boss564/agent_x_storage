"""
B2G Universal Orchestrator — 9 Agenten, 3 Cluster, 5 Sektor-Profile.

Cluster 1 (Identity): nPA/ZK/Role
Cluster 2 (Finance):  Banking/ERP/Tax
Cluster 3 (Web3):     Blockchain/Oracle/RegTech

Usage:
    from agents_b2g.orchestrator import B2GOrchestrator, CONTEXT_PROFILES
    orch = B2GOrchestrator(context="BAU")
    result = orch.process_full_workflow(nfc_1, nfc_2, contract_id, milestone_id)
"""
from agents_b2g.orchestrator.b2g_orchestrator import (
    OrchestratorConfig, JSONLogger, B2GOrchestrator,
    nPAReaderAgent, RegisterAgent, RoleResolverAgent,
    BankingAgent, ERPAgent, TaxAgent,
    BlockchainNodeAgent, OracleAgent, RegTechAgent,
)
from agents_b2g.orchestrator.context_profiles import CONTEXT_PROFILES

__all__ = [
    "OrchestratorConfig", "JSONLogger", "B2GOrchestrator", "CONTEXT_PROFILES",
    "nPAReaderAgent", "RegisterAgent", "RoleResolverAgent",
    "BankingAgent", "ERPAgent", "TaxAgent",
    "BlockchainNodeAgent", "OracleAgent", "RegTechAgent",
]
