#!/usr/bin/env python3
"""DashboardRendererAgent — Streamlit + Plotly Kämmerer-Dashboard (D1).

Rendert das Kämmerer-Dashboard mit BHO-Nullsummen-Balkendiagramm,
Z3-Proof-Status-Anzeige und Live-Ticker.

Author: Agent X — Final Veredelung (Wave 34)
"""

import logging
import json
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List

logger = logging.getLogger("DashboardRendererAgent")

try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logger.warning("plotly not installed — charts will be ASCII fallback")


class DashboardRendererAgent:
    """Renders the Kämmerer live dashboard with BHO bar chart and Z3-proof badge."""

    def __init__(self, user_id: str = "kaemmerer"):
        self.user_id = user_id
        self.render_count = 0
        logger.info(f"DashboardRendererAgent initialized for user={user_id}")

    # ── Public API ────────────────────────────────────────────────

    def render(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Render complete dashboard view for a single transaction.

        Returns JSON-serializable dict with ticker, bar_data, proof_status,
        and optional HTML fragment for Streamlit embedding.
        """
        self.render_count += 1
        logger.info(f"Rendering dashboard #{self.render_count} "
                     f"for contract {transaction.get('contract_id', '?')}")

        gross = float(transaction.get("gross_amount", 0))
        ticker = self._build_ticker(transaction)
        bar_data = self._compute_bho_split(transaction)
        proof = self._extract_proof_status(transaction)
        violation = self._detect_violation(bar_data, gross)
        chart = self._build_chart(bar_data, proof)

        result = {
            "status": "started",
            "job_id": f"dashboard-{self.render_count}",
            "artifacts": [{
                "type": "dashboard_view",
                "ticker": ticker,
                "bar_data": bar_data,
                "proof": proof,
                "bho_delta": violation["delta_eur"],
                "bho_violation": violation["violation"],
                "split_source": bar_data.get("split_source", "DERIVED"),
                "timestamp": datetime.now().isoformat(),
                "chart_json": chart,
                "render_count": self.render_count,
                "user_id": self.user_id,
            }],
            "error": None,
            "logs": [],
        }

        if violation["violation"]:
            result["artifacts"][0]["alert"] = {
                "severity": "CRITICAL",
                "message": f"BHO-Verletzung! Δ = {violation['delta_eur']:.2f} €",
            }

        return result

    def render_streamlit(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Render Streamlit-specific components.

        Returns a dict with keys that Streamlit calls understand:
          - 'st_metrics': list of (label, value, delta) tuples for st.metric
          - 'st_chart': plotly figure or None
          - 'st_dataframe': dict for st.dataframe
        """
        data = self.render(transaction)
        a = data["artifacts"][0]

        metrics = [
            ("Vertrag", a["ticker"]["contract_id"][:24], None),
            ("Brutto", f"{a['bar_data']['brutto_eur']:,.2f} €", None),
            ("BHO Δ", f"{a['bho_delta']:.2f} €",
             "off" if a['bho_delta'] == 0 else "on"),
            ("Z3-Proof", a["proof"]["label"], None),
        ]

        fig = None
        if PLOTLY_AVAILABLE and a.get("chart_json"):
            fig = go.Figure(data=[
                go.Bar(
                    x=list(a["bar_data"]["split"].keys()),
                    y=list(a["bar_data"]["split"].values()),
                    marker_color=["#28a745", "#17a2b8", "#ffc107"],
                    text=[f"{v:,.0f} €" for v in a["bar_data"]["split"].values()],
                    textposition="auto",
                )
            ])
            fig.update_layout(
                title=f"BHO-Nullsummen-Aufteilung — {a['ticker']['contract_id']}",
                yaxis_title="Euro (€)",
                height=400,
                margin=dict(l=20, r=20, t=40, b=20),
            )

        return {
            "st_metrics": metrics,
            "st_chart": fig,
            "alerts": a.get("alert"),
            "timestamp": a["timestamp"],
        }

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _build_ticker(transaction: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "contract_id": transaction.get("contract_id", "N/A"),
            "contractor": transaction.get("contractor", "N/A"),
            "milestone": transaction.get("milestone", "N/A"),
            "sector": transaction.get("sector", "N/A"),
            "gross_amount": transaction.get("gross_amount", 0),
            "time": transaction.get("timestamp", datetime.now().isoformat()),
        }

    @staticmethod
    def _compute_bho_split(transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Compute BHO split from real transaction amounts when available.

        If the transaction carries net/tax/retention amounts, those are used
        verbatim so that the BHO delta reflects actual bookkeeping, not just
        an algebraic identity derived from percentage rules.

        When amounts are absent, the statutory split (80/15/5) is used as a
        fallback, but the source is marked DERIVED to make the distinction
        visible — a derived split is structurally zero and proves nothing.
        """
        gross = float(transaction.get("gross_amount", 0))
        keys = ("net_amount", "tax_amount", "retention_amount")

        if all(k in transaction for k in keys):
            net       = float(transaction["net_amount"])
            tax       = float(transaction["tax_amount"])
            retention = float(transaction["retention_amount"])
            source    = "TRANSACTION"
        else:
            net       = round(gross * 0.80, 2)
            tax       = round(gross * 0.15, 2)
            retention = round(gross * 0.05, 2)
            source    = "DERIVED"

        actual_sum = round(net + tax + retention, 2)
        delta      = round(gross - actual_sum, 2)

        return {
            "brutto_eur": gross,
            "split": {
                "Netto (Handwerker)": net,
                "Steuer (§48b EStG)": tax,
                "Einbehalt (VOB/B §17)": retention,
            },
            "sum_eur": actual_sum,
            "delta_eur": delta,
            "split_source": source,
        }

    @staticmethod
    def _extract_proof_status(transaction: Dict[str, Any]) -> Dict[str, Any]:
        proof = transaction.get("z3_proof", {})
        status = proof.get("status", "PENDING")
        status_map = {
            "MATHEMATICALLY_PROVED": ("✅ Bewiesen", "#28a745"),
            "VERIFIED": ("✅ Verifiziert", "#28a745"),
            "PENDING": ("⏳ Ausstehend", "#ffc107"),
            "UNVERIFIED": ("⚠️ Ungeprüft", "#6c757d"),
            "FAILED": ("❌ Fehlgeschlagen", "#dc3545"),
            "VIOLATION": ("🚨 Verletzung", "#dc3545"),
        }
        label, color = status_map.get(status, ("❓ Unbekannt", "#6c757d"))
        return {
            "status": status,
            "label": label,
            "color": color,
            "proof_hash": proof.get("proof_hash", "0x0"),
        }

    @staticmethod
    def _detect_violation(bar_data: Dict[str, Any],
                          gross: float) -> Dict[str, Any]:
        delta = bar_data["delta_eur"]
        violated = abs(delta) > 0.01
        return {
            "delta_eur": delta,
            "violation": violated,
            "threshold_eur": 0.01,
        }

    @staticmethod
    def _build_chart(bar_data: Dict[str, Any],
                     proof: Dict[str, Any]) -> Optional[Dict]:
        """Build Plotly chart JSON (offline-safe)."""
        if not PLOTLY_AVAILABLE:
            return None
        fig = go.Figure(data=[
            go.Bar(
                x=list(bar_data["split"].keys()),
                y=list(bar_data["split"].values()),
                marker_color=["#28a745", "#17a2b8", "#ffc107"],
                text=[f"{v:,.0f} €" for v in bar_data["split"].values()],
                textposition="auto",
            )
        ])
        fig.update_layout(
            title=(
                f"BHO-Nullsumme "
                f"(Δ = {bar_data['delta_eur']:.2f} € — "
                f"{'✅' if abs(bar_data['delta_eur']) <= 0.01 else '🚨'})"
            ),
            yaxis_title="Euro (€)",
            height=400,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        # Annotation for proof status
        fig.add_annotation(
            x=1.5, y=max(bar_data["split"].values()) * 1.05,
            text=f"Z3-Proof: {proof['label']}",
            showarrow=False,
            font=dict(size=14, color=proof["color"]),
        )
        return json.loads(fig.to_json())


# ── Standalone smoke test ──────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    agent = DashboardRendererAgent(user_id="kaemmerer_mueller")
    tx = {
        "contract_id": "VOB-2026-MUC-8812",
        "sector": "BAU",
        "gross_amount": 45000.0,
        "contractor": "meier-bau.firma.b2g",
        "inspector": "bauamt.muenchen.b2g",
        "milestone": "MILESTONE_05",
        "timestamp": datetime.now().isoformat(),
        "z3_proof": {
            "status": "MATHEMATICALLY_PROVED",
            "proof_hash": "0x" + "a1b2c3" * 8,
        },
    }

    result = agent.render(tx)
    a = result["artifacts"][0]
    print(f"Dashboard #{a['render_count']} — {a['ticker']['contract_id']}")
    print(f"  Brutto: {a['bar_data']['brutto_eur']:,.2f} €")
    print(f"  BHO Δ:  {a['bho_delta']:.2f} €")
    print(f"  Proof:  {a['proof']['label']}")
    print(f"  Status: {'✅ SAUBER' if not a['bho_violation'] else '🚨 VERLETZUNG'}")
    sys.exit(0)
