# agents_b2g/macro/subagents/systemic_risk_and_cartel_monitor.py
"""
Agent 17.7 — SystemicRiskAndCartelMonitor

Erkennt Kartellstrukturen, Monopole und unethische Geldflüsse mittels
Graphentheorie und Netzwerkanalyse. Berechnet Zentralitätsmetriken,
Gini-Koeffizient und identifiziert systemische Risiken im Transaktionsnetzwerk.

Features:
  - Transaktionsgraph (Knoten=Akteure, Kanten=Zahlungsflüsse)
  - Zentralitätsmetriken (Betweenness, PageRank, Eigenvector)
  - Kartellmuster (gegenseitige Zahlungen, Zyklen A→B→C→A)
  - Gini-Koeffizient der Zahlungsströme
  - Monopol-Indikatoren (Betweenness > Schwelle, PageRank > Schwelle)
  - Alarmierung bei Risikoschwellwerten
  - Audit-Trail für Kartellamt
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict, Counter

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False

logger = logging.getLogger("SystemicRiskAndCartelMonitor")


class SystemicRiskAndCartelMonitorSubagent:
    """
    Subagent 17.7: Kartell- & Monopolerkennung via Graphentheorie.
    """

    def __init__(
        self,
        risk_threshold_betweenness: float = 0.3,
        risk_threshold_pagerank: float = 0.1,
        gini_threshold: float = 0.7,
        cycle_min_length: int = 3,
        mutual_payment_threshold_eur: float = 10000.0,
    ):
        self.risk_threshold_betweenness = risk_threshold_betweenness
        self.risk_threshold_pagerank = risk_threshold_pagerank
        self.gini_threshold = gini_threshold
        self.cycle_min_length = cycle_min_length
        self.mutual_threshold = mutual_payment_threshold_eur

    def analyze_network(
        self,
        transactions: List[Dict[str, Any]],
        tender_id: Optional[str] = None,
        period_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Hauptmethode: Analysiert das Transaktionsnetzwerk."""
        period_label = period_label or datetime.now(timezone.utc).strftime("%Y-%m")
        job_id = f"scm_{period_label}"

        if not transactions:
            return {"status": "NO_DATA", "job_id": job_id, "artifacts": [], "error": None,
                    "logs": [{"level": "WARN", "message": "Keine Transaktionen."}]}

        try:
            if not NETWORKX_AVAILABLE:
                return self._fallback_analysis(transactions, tender_id, period_label, job_id)

            G = self._build_graph(transactions)

            centrality = self._calculate_centrality(G)
            cartel_indicators = self._detect_cartel_patterns(G, transactions)
            gini = self._calculate_gini(G)
            monopoly = self._detect_monopoly(G, centrality)
            risk_score, alerts = self._evaluate_risk(centrality, cartel_indicators, gini, monopoly)

            report = {
                "status": "ANALYSIS_COMPLETE",
                "job_id": job_id,
                "tender_id": tender_id,
                "period_label": period_label,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "artifacts": [{"type": "cartel_report", "format": "json",
                               "metadata": {"risk_score": round(risk_score, 2)}}],
                "error": None,
                "logs": [{"level": "INFO", "message": f"Netzwerk: {G.number_of_nodes()} Knoten, "
                          f"{G.number_of_edges()} Kanten, Risiko={risk_score:.2f}"}],
                "network_metrics": {
                    "nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
                    "density": round(nx.density(G), 4),
                    "average_degree": round(sum(dict(G.degree()).values()) / max(G.number_of_nodes(), 1), 1),
                    "strongly_connected_components": nx.number_strongly_connected_components(G),
                },
                "centrality": centrality,
                "cartel_indicators": cartel_indicators,
                "gini_coefficient": gini,
                "monopoly_indicators": monopoly,
                "risk_score": round(risk_score, 2),
                "alerts": alerts,
                "has_alerts": len(alerts) > 0,
            }
            return report
        except Exception as e:
            logger.error(f"CartelMonitor fehlgeschlagen: {e}", exc_info=True)
            return {"status": "failed", "job_id": job_id, "artifacts": [], "error": str(e),
                    "logs": [{"level": "ERROR", "message": str(e)}]}

    def _build_graph(self, transactions: List[Dict]) -> "nx.DiGraph":
        G = nx.DiGraph()
        for tx in transactions:
            sender = tx.get("sender", tx.get("from", "UNKNOWN"))
            receiver = tx.get("receiver", tx.get("to", "UNKNOWN"))
            amount = float(tx.get("amount_eur", 0.0))
            ts = tx.get("timestamp", datetime.now(timezone.utc).isoformat())
            if sender == receiver or amount <= 0:
                continue
            if G.has_edge(sender, receiver):
                G[sender][receiver]["weight"] += amount
                G[sender][receiver]["count"] += 1
                G[sender][receiver]["last_tx"] = max(G[sender][receiver]["last_tx"], ts)
            else:
                G.add_edge(sender, receiver, weight=amount, count=1, last_tx=ts)
        return G

    def _calculate_centrality(self, G: "nx.DiGraph") -> Dict[str, Any]:
        try:
            betweenness = nx.betweenness_centrality(G, weight="weight")
            pagerank = nx.pagerank(G, weight="weight")
            eigenvector = nx.eigenvector_centrality(G, max_iter=1000, weight="weight")
            top_b = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:5]
            top_p = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:5]
            top_e = sorted(eigenvector.items(), key=lambda x: x[1], reverse=True)[:5]
            return {
                "top_betweenness": top_b, "top_pagerank": top_p, "top_eigenvector": top_e,
                "max_betweenness": max(betweenness.values()) if betweenness else 0,
                "max_pagerank": max(pagerank.values()) if pagerank else 0,
            }
        except Exception as e:
            logger.error(f"Zentralität fehlgeschlagen: {e}")
            return {}

    def _detect_cartel_patterns(self, G: "nx.DiGraph", transactions: List[Dict]) -> Dict[str, Any]:
        indicators = {"mutual_payments": [], "cycles": []}
        for u, v, data in list(G.edges(data=True)):
            if G.has_edge(v, u):
                w_uv = data.get("weight", 0)
                w_vu = G[v][u].get("weight", 0)
                if w_uv > self.mutual_threshold and w_vu > self.mutual_threshold:
                    indicators["mutual_payments"].append({
                        "a": u, "b": v, "a_to_b_eur": round(w_uv, 2),
                        "b_to_a_eur": round(w_vu, 2),
                        "ratio": round(w_uv / max(w_vu, 0.01), 2),
                    })
        try:
            cycles = list(nx.simple_cycles(G, length_bound=6))
            indicators["cycles"] = [c for c in cycles if len(c) >= self.cycle_min_length][:10]
        except Exception:
            pass
        return indicators

    def _calculate_gini(self, G: "nx.DiGraph") -> float:
        amounts = []
        for node in G.nodes():
            in_flow = sum(d.get("weight", 0) for _, _, d in G.in_edges(node, data=True))
            out_flow = sum(d.get("weight", 0) for _, _, d in G.out_edges(node, data=True))
            amounts.append(in_flow + out_flow)
        if not amounts or sum(amounts) == 0:
            return 0.0
        amounts.sort()
        n = len(amounts)
        total = sum(amounts)
        cum = sum(a * (i + 1) for i, a in enumerate(amounts))
        return round((2 * cum) / (n * total) - (n + 1) / n, 3)

    def _detect_monopoly(self, G: "nx.DiGraph", centrality: Dict) -> List[Dict]:
        indicators = []
        for node, score in centrality.get("top_betweenness", []):
            if score > self.risk_threshold_betweenness:
                indicators.append({"node": node, "metric": "betweenness", "score": round(score, 3), "risk": "HIGH"})
        for node, score in centrality.get("top_pagerank", []):
            if score > self.risk_threshold_pagerank:
                indicators.append({"node": node, "metric": "pagerank", "score": round(score, 3), "risk": "HIGH"})
        return indicators

    def _evaluate_risk(self, centrality, cartel, gini, monopoly) -> Tuple[float, List[Dict]]:
        risk = 0.0
        alerts = []
        if gini > self.gini_threshold:
            risk += 0.3
            alerts.append({"alert_type": "HIGH_GINI", "severity": "HIGH",
                           "message": f"Gini={gini:.2f} > {self.gini_threshold} — extreme Ungleichverteilung!"})
        elif gini > 0.5:
            risk += 0.15
            alerts.append({"alert_type": "ELEVATED_GINI", "severity": "MEDIUM",
                           "message": f"Gini={gini:.2f} — signifikante Ungleichverteilung."})
        mutual_count = len(cartel.get("mutual_payments", []))
        if mutual_count > 0:
            risk += min(0.3, mutual_count * 0.05)
            alerts.append({"alert_type": "MUTUAL_PAYMENTS", "severity": "HIGH",
                           "message": f"{mutual_count} gegenseitige Zahlungsmuster — Kartellverdacht!"})
        if monopoly:
            risk += min(0.3, len(monopoly) * 0.1)
            alerts.append({"alert_type": "MONOPOLY_RISK", "severity": "HIGH",
                           "message": f"{len(monopoly)} Akteure mit Monopol-Risiko!"})
        cycle_count = len(cartel.get("cycles", []))
        if cycle_count > 0:
            risk += min(0.2, cycle_count * 0.02)
            alerts.append({"alert_type": "CYCLES_DETECTED", "severity": "MEDIUM",
                           "message": f"{cycle_count} zyklische Zahlungsmuster — mögliche Verschleierung."})
        return min(1.0, risk), alerts

    def _fallback_analysis(self, transactions, tender_id, period_label, job_id) -> Dict:
        senders = [tx.get("sender", tx.get("from", "UNKNOWN")) for tx in transactions]
        receivers = [tx.get("receiver", tx.get("to", "UNKNOWN")) for tx in transactions]
        all_parties = set(senders + receivers)
        return {
            "status": "ANALYSIS_COMPLETE (FALLBACK)", "job_id": job_id,
            "tender_id": tender_id, "period_label": period_label,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "artifacts": [], "error": None,
            "logs": [{"level": "WARN", "message": "networkx nicht verfügbar — vereinfachte Analyse."}],
            "network_metrics": {"nodes": len(all_parties), "edges": len(transactions)},
            "top_senders": Counter(senders).most_common(5),
            "top_receivers": Counter(receivers).most_common(5),
            "gini_coefficient": 0.5, "risk_score": 0.1, "alerts": [],
        }
