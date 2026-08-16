"""WirtschaftsSchwarm: orchestrates the 9 agents + the distributed
Freigabe (approval) and Delegation flows (Baustein 3).

Gewaltenteilung across classes:
  freigabe_required -> approver's ComplianceEngine -> GRANT -> re-execute
  delegated         -> an agent of the responsible class executes
"""
from typing import Any, Dict, Optional

from agents_b2g.wirtschaft.base import KompetenzKlasse
from agents_b2g.wirtschaft.profiles import Aktion
from agents_b2g.wirtschaft.agents import AGENT_CLASSES, create_agent


class WirtschaftsSchwarm:
    def __init__(self):
        self.agents: Dict[str, Any] = {}
        self.class_members = {k: [] for k in KompetenzKlasse}
        self.approvers: Dict[KompetenzKlasse, str] = {}

    def add(self, agent):
        self.agents[agent.id] = agent
        k = agent.competence.klasse if agent.competence else None
        if k is not None:
            self.class_members[k].append(agent.id)
        return agent

    def set_approver(self, klasse, agent_id):
        self.approvers[klasse] = agent_id

    def approver(self, klasse):
        return self.agents.get(self.approvers.get(klasse))

    def execute(self, agent_id, aktion, payload=None):
        agent = self.agents.get(agent_id)
        if agent is None:
            return {"status": "unknown_agent", "agent": agent_id}
        result = agent.execute(aktion, payload)
        status = result.get("status")
        if status == "freigabe_required":
            return self._handle_freigabe(agent, aktion, payload, result)
        if status == "delegated":
            return self._handle_delegation(agent, aktion, payload, result)
        return result

    # --- internals ---

    def _klasse_from_target(self, target):
        if isinstance(target, str) and "." in target:
            try:
                return KompetenzKlasse(target.split(".")[-1])
            except ValueError:
                return None
        return None

    def _handle_freigabe(self, requester, aktion, payload, result):
        fr = result.get("freigabe_request") or {}
        klasse = self._klasse_from_target(fr.get("target"))
        approver = self.approver(klasse) if klasse is not None else None
        if approver is None:
            result["status"] = "freigabe_no_approver"
            return result
        verdict = self._approve(approver, requester, aktion, payload)
        result["verdict"] = verdict
        if verdict.get("decision") == "GRANT":
            requester.grant_freigabe(aktion)
            return requester.execute(aktion, payload)
        result["status"] = "freigabe_denied"
        return result

    def _handle_delegation(self, requester, aktion, payload, result):
        fr = result.get("freigabe_request") or {}
        klasse = self._klasse_from_target(fr.get("target"))
        executor = self._find_executor(klasse, aktion) if klasse is not None else None
        if executor is None:
            result["status"] = "delegation_no_executor"
            return result
        result["delegated_to"] = executor.id
        result["delegated_result"] = executor.execute(aktion, payload)
        return result

    def _approve(self, approver, requester, aktion, payload):
        engine = getattr(approver, "compliance_engine", None)
        if engine is not None:
            return engine.check({"aktion": aktion, "requester": requester.id,
                                 "details": payload or {}})
        if approver.may(Aktion.TX_APPROVE):
            return {"decision": "GRANT", "grund": "approver_competent"}
        return {"decision": "DENY", "grund": "approver_not_competent"}

    def _find_executor(self, klasse, aktion):
        for aid in self.class_members.get(klasse, []):
            agent = self.agents[aid]
            if agent.may(aktion):
                return agent
        return None


def build_schwarm():
    """Build the full 9-agent swarm with approvers wired. Returns (schwarm, agents)."""
    schwarm = WirtschaftsSchwarm()
    agents = {name: create_agent(name) for name in AGENT_CLASSES}
    for agent in agents.values():
        schwarm.add(agent)
    schwarm.set_approver(KompetenzKlasse.GOVERNANCE, agents["retention"].id)
    schwarm.set_approver(KompetenzKlasse.AUSFUEHRUNG, agents["settlement"].id)
    schwarm.set_approver(KompetenzKlasse.KAPITAL, agents["treasury"].id)
    return schwarm, agents
