"""
Subagent: BidderComparisonEngine — Position-by-Position Comparison Matrix.

Creates a detailed per-GAEB-position comparison between claimant and winner
for the procurement tribunal's award justification (Vergabevermerk).

Features:
  1. OZ-matched comparison — every GAEB position compared
  2. Price deltas — absolute + percentage deviation per position
  3. Text similarity — identical / similar / different short texts
  4. Material group aggregation — which bidder cheaper per trade
  5. Overall assessment — cheaper by count vs. cheaper by value

Usage:
    engine = BidderComparisonEngine()
    matrix = engine.compare_bidders(tender_id, profiles, claimant_id)
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("BidderComparisonEngine")


class BidderComparisonEngine:
    """Position-by-position comparative matrix for Vergabekammer proceedings."""

    def compare_bidders(self, tender_id: str,
                        bidder_profiles: list[dict[str, Any]],
                        claimant_bidder_id: str | None = None) -> dict[str, Any]:
        """Generate position-level comparison matrix between claimant and winner."""

        logger.info(f"Bidder comparison for {tender_id}: {len(bidder_profiles)} bidders")

        if len(bidder_profiles) < 2:
            return self._error("Weniger als 2 Bieter — kein Vergleich möglich.")

        # Identify winner (lowest total price) and claimant
        sorted_bidders = sorted(
            bidder_profiles,
            key=lambda p: float(p.get("total_price_eur",
                               p.get("x84_data", {}).get("TotalAmount",
                               p.get("price_eur", float("inf")))))
        )
        winner = sorted_bidders[0]
        claimant = next((p for p in bidder_profiles
                        if p.get("bidder_id") == claimant_bidder_id), sorted_bidders[1]) \
                   if len(sorted_bidders) > 1 else None
        if not claimant:
            return self._error("Kein zweiter Bieter für Vergleich vorhanden.")

        # Extract positions keyed by OZ
        winner_positions = self._extract_positions(winner)
        claimant_positions = self._extract_positions(claimant)

        if not winner_positions and not claimant_positions:
            # Fallback: compare from flat price lists
            return self._compare_flat(tender_id, winner, claimant, sorted_bidders)

        # Position-by-position comparison
        matrix = self._compare_positions(winner, claimant, winner_positions, claimant_positions)
        summary = self._calculate_summary(matrix)

        print(f"  [BidderComp]    📊 {len(matrix)} Positionen verglichen: "
              f"Winner={winner.get('bidder_id')} ({summary['total_winner_price_eur']:,.2f} €) vs "
              f"Claimant={claimant.get('bidder_id')} ({summary['total_claimant_price_eur']:,.2f} €), "
              f"Δ={summary['total_price_delta_eur']:,.2f} €")

        return {
            "tender_id": tender_id,
            "winner": {"bidder_id": winner.get("bidder_id"),
                       "total_price_eur": summary["total_winner_price_eur"]},
            "claimant": {"bidder_id": claimant.get("bidder_id"),
                         "total_price_eur": summary["total_claimant_price_eur"]},
            "comparison_matrix": matrix,
            "summary": summary,
            "overall_cheaper": "claimant" if summary["winner_cheaper_total"] is False else "winner",
            "recommendation": self._get_recommendation(summary),
        }

    # ============================================================
    # Position extraction
    # ============================================================

    @staticmethod
    def _extract_positions(profile: dict) -> dict[str, dict]:
        """Extract all LV positions from X84 data, keyed by OZ."""
        positions = {}
        x84_data = profile.get("x84_data", {})
        for section in x84_data.get("sections", []):
            for pos in section.get("positions", []):
                oz = pos.get("oz") or pos.get("position_id") or pos.get("ItemID", "")
                if not oz:
                    continue
                positions[oz] = {
                    "oz": oz,
                    "short_text": pos.get("short_text", pos.get("description", "")),
                    "quantity": float(pos.get("quantity", pos.get("Qty", 0))),
                    "unit": pos.get("unit", pos.get("Unit", "Stk")),
                    "unit_price": float(pos.get("unit_price_net_eur",
                                         pos.get("unit_price_eur", pos.get("UP", 0)))),
                    "total_price": float(pos.get("total_price_net_eur",
                                          pos.get("total_eur", pos.get("TP", 0)))),
                    "material_group": pos.get("material_group", "Unbekannt"),
                }
        return positions

    # ============================================================
    # Position comparison
    # ============================================================

    def _compare_positions(self, winner: dict, claimant: dict,
                           w_pos: dict, c_pos: dict) -> list[dict]:
        """Compare every position between winner and claimant."""
        matrix = []
        all_keys = sorted(set(w_pos.keys()) | set(c_pos.keys()))

        for oz in all_keys:
            wp = w_pos.get(oz, {})
            cp = c_pos.get(oz, {})

            w_price = wp.get("unit_price", 0)
            c_price = cp.get("unit_price", 0)
            price_delta = c_price - w_price
            price_delta_pct = (price_delta / w_price * 100) if w_price > 0 else 0.0

            w_total = wp.get("total_price", 0)
            c_total = cp.get("total_price", 0)
            total_delta = c_total - w_total

            text_match = self._compare_texts(
                wp.get("short_text", ""), cp.get("short_text", ""))

            status = "BOTH"
            if not wp:
                status = "ONLY_IN_CLAIMANT"
            elif not cp:
                status = "ONLY_IN_WINNER"

            cheaper = "equal"
            if w_price > 0 and c_price > 0:
                cheaper = "winner" if w_price < c_price else (
                    "claimant" if c_price < w_price else "equal")

            matrix.append({
                "oz": oz,
                "material_group": wp.get("material_group") or cp.get("material_group", "?"),
                "short_text_winner": wp.get("short_text", "—"),
                "short_text_claimant": cp.get("short_text", "—"),
                "text_match": text_match,
                "quantity_winner": wp.get("quantity", 0),
                "quantity_claimant": cp.get("quantity", 0),
                "unit": wp.get("unit") or cp.get("unit", "Stk"),
                "unit_price_winner_eur": round(w_price, 2),
                "unit_price_claimant_eur": round(c_price, 2),
                "price_delta_eur": round(price_delta, 2),
                "price_delta_percent": round(price_delta_pct, 1),
                "total_price_winner_eur": round(w_total, 2),
                "total_price_claimant_eur": round(c_total, 2),
                "total_delta_eur": round(total_delta, 2),
                "cheaper_bidder": cheaper,
                "status": status,
            })

        return matrix

    @staticmethod
    def _compare_texts(t1: str, t2: str) -> str:
        if not t1 and not t2:
            return "identisch"
        if not t1 or not t2:
            return "unterschiedlich"
        if t1.lower().replace(" ", "") == t2.lower().replace(" ", ""):
            return "identisch"
        common = set(t1.lower().split()) & set(t2.lower().split())
        if len(common) >= 2:
            return "ähnlich"
        return "unterschiedlich"

    # ============================================================
    # Summary + recommendation
    # ============================================================

    @staticmethod
    def _calculate_summary(matrix: list[dict]) -> dict:
        winner_cheaper = sum(1 for e in matrix if e["cheaper_bidder"] == "winner")
        claimant_cheaper = sum(1 for e in matrix if e["cheaper_bidder"] == "claimant")
        equal_prices = sum(1 for e in matrix if e["cheaper_bidder"] == "equal")
        only_winner = sum(1 for e in matrix if e["status"] == "ONLY_IN_WINNER")
        only_claimant = sum(1 for e in matrix if e["status"] == "ONLY_IN_CLAIMANT")
        total_delta = sum(e["total_delta_eur"] for e in matrix)
        total_w = sum(e["total_price_winner_eur"] for e in matrix)
        total_c = sum(e["total_price_claimant_eur"] for e in matrix)

        # Material group aggregation
        groups: dict = defaultdict(lambda: {"positions": 0, "winner_cheaper": 0,
                                            "claimant_cheaper": 0, "total_delta_eur": 0.0})
        for e in matrix:
            g = e.get("material_group", "?")
            groups[g]["positions"] += 1
            if e["cheaper_bidder"] == "winner":
                groups[g]["winner_cheaper"] += 1
            elif e["cheaper_bidder"] == "claimant":
                groups[g]["claimant_cheaper"] += 1
            groups[g]["total_delta_eur"] += e["total_delta_eur"]

        return {
            "total_positions": len(matrix),
            "winner_cheaper_count": winner_cheaper,
            "claimant_cheaper_count": claimant_cheaper,
            "equal_prices": equal_prices,
            "only_in_winner": only_winner,
            "only_in_claimant": only_claimant,
            "total_price_delta_eur": round(total_delta, 2),
            "total_winner_price_eur": round(total_w, 2),
            "total_claimant_price_eur": round(total_c, 2),
            "winner_cheaper_total": total_delta > 0,
            "cheaper_by_count": "winner" if winner_cheaper > claimant_cheaper else "claimant",
            "cheaper_by_value": "winner" if total_delta > 0 else "claimant",
            "material_group_summary": {
                k: dict(v) for k, v in sorted(groups.items())},
        }

    @staticmethod
    def _get_recommendation(s: dict) -> str:
        if s["winner_cheaper_total"] and s["cheaper_by_count"] == "winner":
            return "Gewinner bei Preis und Anzahl günstiger — Zuschlag bestätigen."
        if s["winner_cheaper_total"]:
            return "Gewinner insgesamt günstiger — Zuschlag bestätigen."
        if s["claimant_cheaper_count"] > s["winner_cheaper_count"] * 1.5:
            return "Kläger signifikant öfter günstiger — Preisprüfung empfohlen."
        return "Gemischtes Bild — detaillierte Einzelfallprüfung erforderlich."

    # ============================================================
    # Fallback: flat comparison (no position data)
    # ============================================================

    def _compare_flat(self, tender_id: str, winner: dict, claimant: dict,
                      all_bidders: list) -> dict:
        """Simple price-ranking comparison when no OZ data available."""
        prices = [(p.get("bidder_id", "?"),
                   float(p.get("total_price_eur",
                        p.get("x84_data", {}).get("TotalAmount",
                        p.get("price_eur", 0)))))
                  for p in all_bidders]
        prices.sort(key=lambda x: x[1])

        winner_price = prices[0][1]
        claimant_price = next((pr for bid, pr in prices if bid == claimant.get("bidder_id")),
                              prices[1][1] if len(prices) > 1 else 0)
        gap = round(claimant_price - winner_price, 2)
        gap_pct = round(gap / max(1, winner_price) * 100, 2)

        claim_pos = next((i + 1 for i, (bid, _) in enumerate(prices)
                         if bid == claimant.get("bidder_id")), None)

        return {
            "tender_id": tender_id,
            "winner": {"bidder_id": prices[0][0], "total_price_eur": winner_price},
            "claimant": {"bidder_id": claimant.get("bidder_id"),
                         "total_price_eur": claimant_price},
            "comparison_matrix": [],
            "summary": {
                "total_positions": 0,
                "price_gap_eur": gap,
                "price_gap_pct": gap_pct,
                "claimant_rank": claim_pos,
                "total_bidders": len(prices),
            },
            "overall_cheaper": "winner" if gap > 0 else "claimant",
            "recommendation": (
                "Gewinner günstiger — Zuschlag bestätigen." if gap > 0
                else f"Kläger günstiger (Δ={gap:,.2f} €) — Preisprüfung empfohlen."),
        }

    @staticmethod
    def _error(msg: str) -> dict:
        return {"status": "ERROR", "message": msg,
                "timestamp": datetime.now(timezone.utc).isoformat()}
