"""
B2G Lifecycle Orchestrator — 9 Agenten, 6 Phasen, 3 Cluster.

Cluster 1 (Acquisition): TenderScraper, Bidding, Contract
Cluster 2 (Identity):    nPA-Reader, Register, Role-Resolver
Cluster 3 (Settlement):  Atomic-Splitter, Tax, GoBD-Archiver

Usage:
    from agents_b2g.lifecycle import LifecycleOrchestrator
    orch = LifecycleOrchestrator()
    result = orch.execute_full_lifecycle(sector="BAU")
"""
from agents_b2g.lifecycle.lifecycle_orchestrator import (
    LifecycleConfig, JSONLogger, LifecycleOrchestrator, LifecycleContext,
    TenderScraperAgent, BiddingAgent, ContractAgent,
    nPAReaderAgent, RegisterAgent, RoleResolverAgent,
    AtomicSplitterAgent, TaxAgent, GoBDArchiverAgent,
)
__all__ = [
    "LifecycleConfig", "JSONLogger", "LifecycleOrchestrator", "LifecycleContext",
    "TenderScraperAgent", "BiddingAgent", "ContractAgent",
    "nPAReaderAgent", "RegisterAgent", "RoleResolverAgent",
    "AtomicSplitterAgent", "TaxAgent", "GoBDArchiverAgent",
]
