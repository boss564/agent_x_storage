"""
Subagent: PricePlausibilityAnalyzer — Bid Price Forensics + VOB/A §16d.

Two-layer analysis:
  Layer 1 — Reference price comparison: unit prices vs. BKI GraphRAG market rates
  Layer 2 — Statistical forensics: Benford's Law, Z-Score, IQR, round numbers

Detects under-cost bids (§16d), suppressed unit prices, minimum wage violations,
and signals of bid-rigging through coordinated pricing patterns.

Usage:
    analyzer = PricePlausibilityAnalyzer(deviation_threshold_percent=20.0)
    result = analyzer.analyze_offer_prices(bidder_profile)
    # Statistical layer:
    result = analyzer.analyze(bidder_profiles)  # Benford + Z-Score + IQR
"""
from __future__ import annotations

import logging
import math
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any

getcontext().prec = 28
logger = logging.getLogger("PricePlausibilityAnalyzer")

# ============================================================
# Reference market prices (GraphRAG / BKI / DKG)
# ============================================================

REFERENCE_PRICES: dict[str, dict[str, float]] = {
    "Tiefbau": {
        "Baugrubenaushub": 42.50,
        "Bodenverdichtung": 8.20,
        "Kanalgraben": 65.00,
        "Verfüllung": 18.50,
        "Erdaushub": 35.00,
    },
    "Betonbau": {
        "Beton C30/37": 185.00,
        "Schalung": 32.50,
        "Bewehrung": 95.00,
        "Betonstahl": 850.00,
        "Ortbeton": 195.00,
        "Betonabbruch": 28.00,
    },
    "Rohrleitungsbau": {
        "Edelstahl DN300": 420.00,
        "Guss DN150": 180.00,
        "Armatur DN80": 450.00,
        "Schweißnaht": 85.00,
        "Edelstahlrohr": 380.00,
    },
    "Elektrotechnik": {
        "Kabel NYY 5x16": 28.50,
        "Verteiler 16A": 320.00,
        "Steuerung SPS": 1800.00,
        "Sensorik": 250.00,
        "Kabelschacht": 180.00,
    },
    "HLK": {
        "Pumpe 5kW": 2400.00,
        "Gebläse 10kW": 3800.00,
        "Ventil DN100": 420.00,
        "Luftkanal": 95.00,
        "Membranbelüfter": 380.00,
        "Dosierstation": 8500.00,
    },
    "Ausbau": {
        "Trockenbau": 85.00,
        "Fliesen": 120.00,
        "Malerarbeiten": 28.50,
        "Bodenbelag": 55.00,
        "Epoxidharz": 42.00,
    },
}

MIN_WAGE_PER_HOUR = 12.41        # Bauhauptgewerbe 2026
MIN_WAGE_PER_HOUR_SPECIAL = 14.50  # Facharbeiter

# Benford expected first-digit distribution
BENFORD_EXPECTED = {
    1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046,
}


class PricePlausibilityAnalyzer:
    """Two-layer bid price forensics: reference comparison + statistics."""

    def __init__(self, deviation_threshold_percent: float = 20.0,
                 z_score_threshold: float = 3.0,
                 iqr_multiplier: float = 1.5):
        self.deviation_threshold = deviation_threshold_percent
        self.z_score_threshold = z_score_threshold
        self.iqr_multiplier = iqr_multiplier

    # ============================================================
    # Layer 1: Reference price comparison (per-bidder)
    # ============================================================

    def analyze_offer_prices(self, bidder_profile: dict[str, Any]) -> dict[str, Any]:
        """Compare each unit price against GraphRAG reference prices per material group."""
        bidder_id = bidder_profile.get("bidder_id", "UNKNOWN")
        x84_data = bidder_profile.get("x84_data", {})
        sections = x84_data.get("sections", [])

        logger.info(f"Reference price check: bidder {bidder_id}")

        suspicious = []
        below_min_wage = []
        total_positions = 0
        total_variance = 0.0

        for section in sections:
            section_name = section.get("name", "Unbekannt")
            material_group = self._infer_material_group(section_name)

            for pos in section.get("positions", []):
                total_positions += 1
                oz = pos.get("oz", pos.get("position_id", "UNKNOWN"))
                short_text = pos.get("short_text", pos.get("description", ""))
                offered_price = float(pos.get("unit_price_net_eur",
                                      pos.get("unit_price_eur", 0.0)))

                # Find reference price
                ref_price = self._find_reference_price(short_text, material_group)
                if ref_price is None or ref_price <= 0:
                    continue

                deviation_pct = ((offered_price - ref_price) / ref_price) * 100

                # Under-cost detection (VOB/A §16d)
                if deviation_pct < -self.deviation_threshold:
                    suspicious.append({
                        "oz": oz,
                        "short_text": short_text,
                        "material_group": material_group,
                        "offered_price_eur": round(offered_price, 2),
                        "reference_price_eur": ref_price,
                        "deviation_percent": round(deviation_pct, 1),
                        "severity": "RED" if deviation_pct < -40 else "YELLOW",
                        "reason": "Unterkostenangebot (VOB/A §16d)",
                    })
                    total_variance += abs(deviation_pct)

                # Over-market detection
                elif deviation_pct > self.deviation_threshold * 2:
                    suspicious.append({
                        "oz": oz,
                        "short_text": short_text,
                        "material_group": material_group,
                        "offered_price_eur": round(offered_price, 2),
                        "reference_price_eur": ref_price,
                        "deviation_percent": round(deviation_pct, 1),
                        "severity": "YELLOW",
                        "reason": "Deutlich über Marktniveau",
                    })
                    total_variance += abs(deviation_pct)

                # Minimum wage check
                if any(w in short_text.lower() for w in ("lohn", "stunden", "std")):
                    if offered_price < MIN_WAGE_PER_HOUR:
                        below_min_wage.append({
                            "oz": oz,
                            "short_text": short_text,
                            "offered_price_eur": offered_price,
                            "min_wage_eur": MIN_WAGE_PER_HOUR,
                            "deviation": round(offered_price - MIN_WAGE_PER_HOUR, 2),
                        })

        risk_level = self._calculate_risk_level(total_positions, len(suspicious),
                                                len(below_min_wage))

        return {
            "bidder_id": bidder_id,
            "total_positions_checked": total_positions,
            "suspicious_positions": suspicious,
            "below_min_wage_positions": below_min_wage,
            "average_variance_pct": round(total_variance / max(1, total_positions), 1),
            "risk_level": risk_level,
            "verdict": self._get_verdict(risk_level),
        }

    # ============================================================
    # Layer 2: Statistical forensics (across all bidders)
    # ============================================================

    def analyze(self, bidder_profiles: list[dict[str, Any]]) -> dict[str, Any]:
        """Statistical price analysis: Benford + Z-Score + IQR + round numbers."""
        all_prices = self._extract_all_prices(bidder_profiles)
        logger.info(f"Statistical check: {len(all_prices)} prices from "
                     f"{len(bidder_profiles)} bidders")

        results: dict[str, Any] = {
            "total_prices": len(all_prices),
            "total_bidders": len(bidder_profiles),
            "risk_factors": [],
            "detailed_findings": {},
        }

        if len(all_prices) < 5:
            results["verdict"] = "GREEN — Zu wenige Preise für Statistik"
            return results

        benford = self._test_benford(all_prices)
        results["detailed_findings"]["benford"] = benford
        if not benford["conforms"]:
            results["risk_factors"].append("BENFORD_DEVIATION")

        zscore = self._test_zscore(all_prices)
        results["detailed_findings"]["z_score"] = zscore
        if zscore["outlier_count"] > 0:
            results["risk_factors"].append("ZSCORE_OUTLIERS")

        round_nums = self._test_round_numbers(all_prices)
        results["detailed_findings"]["round_numbers"] = round_nums
        if round_nums["suspicious_pct"] > 15.0:
            results["risk_factors"].append("ROUND_NUMBER_SUSPICIOUS")

        iqr = self._test_iqr(all_prices)
        results["detailed_findings"]["iqr"] = iqr
        if iqr["outlier_count"] > 0:
            results["risk_factors"].append("IQR_OUTLIERS")

        risk_count = len(results["risk_factors"])
        results["anomaly_score"] = min(risk_count * 20.0, 100.0)
        results["verdict"] = (
            "GREEN — Preise statistisch unauffällig" if risk_count == 0
            else "YELLOW — Leichte Anomalien" if risk_count <= 2
            else "RED — Erhebliche Preisanomalien"
        )
        return results

    # ============================================================
    # Full analysis (both layers)
    # ============================================================

    def full_analysis(self, bidder_profiles: list[dict[str, Any]]) -> dict:
        """Run both reference comparison (Layer 1) and statistics (Layer 2)."""
        per_bidder = {p.get("bidder_id", f"BID-{i}"):
                      self.analyze_offer_prices(p)
                      for i, p in enumerate(bidder_profiles)}
        stats = self.analyze(bidder_profiles)

        worst = max(
            (r for r in per_bidder.values() if isinstance(r, dict)),
            key=lambda r: {"GREEN": 0, "YELLOW": 1, "RED": 2, "CRITICAL": 3}
            .get(r.get("risk_level", "GREEN"), 0),
            default={"risk_level": "GREEN", "verdict": "Keine Daten"},
        )

        return {
            "per_bidder": per_bidder,
            "statistical_analysis": stats,
            "worst_risk_level": worst["risk_level"],
            "overall_verdict": worst["verdict"],
        }

    # ============================================================
    # Helpers — Reference prices
    # ============================================================

    def _find_reference_price(self, short_text: str, material_group: str) -> float | None:
        refs = REFERENCE_PRICES.get(material_group, {})
        for key, price in refs.items():
            if key.lower() in short_text.lower():
                return price
        if refs:
            return sum(refs.values()) / len(refs)
        return None

    @staticmethod
    def _infer_material_group(section_name: str) -> str:
        name = section_name.lower()
        if any(w in name for w in ("tiefbau", "erde", "aushub", "graben")):
            return "Tiefbau"
        if any(w in name for w in ("beton", "schalung", "bewehrung")):
            return "Betonbau"
        if any(w in name for w in ("rohr", "leitung", "armatur")):
            return "Rohrleitungsbau"
        if any(w in name for w in ("elektro", "kabel", "steuerung")):
            return "Elektrotechnik"
        if any(w in name for w in ("pumpe", "gebläse", "ventil", "HLK")):
            return "HLK"
        return "Ausbau"

    def _calculate_risk_level(self, total: int, suspicious: int,
                              below_min: int) -> str:
        if below_min > 0:
            return "CRITICAL"
        pct = suspicious / max(1, total)
        if pct > 0.20:
            return "RED"
        if pct > 0.10:
            return "YELLOW"
        return "GREEN"

    @staticmethod
    def _get_verdict(risk: str) -> str:
        return {
            "GREEN": "Preise plausibel — keine Beanstandungen.",
            "YELLOW": "Leichte Auffälligkeiten — plausibilisieren, ggf. Nachfrage beim Bieter.",
            "RED": "Erhebliche Abweichungen — Angebot auf Unterkosten und Nachunternehmer prüfen.",
            "CRITICAL": "MASSIVE VERSTÖSSE: Unterschreitung des Mindestlohns — Angebot ist zwingend auszuschließen!",
        }.get(risk, "Prüfung erforderlich.")

    # ============================================================
    # Statistical tests
    # ============================================================

    def _test_benford(self, prices: list[float]) -> dict:
        nonzero = [p for p in prices if p > 0.01]
        if len(nonzero) < 10:
            return {"conforms": True, "note": "Zu wenige Datenpunkte"}
        first_digits = [int(str(abs(p)).lstrip("0.")[0]) for p in nonzero
                       if str(abs(p)).lstrip("0.") and str(abs(p)).lstrip("0.")[0].isdigit()]
        observed = Counter(first_digits)
        n = len(first_digits)
        chi2 = sum((observed.get(d, 0) - BENFORD_EXPECTED[d] * n) ** 2
                   / (BENFORD_EXPECTED[d] * n) for d in range(1, 10))
        return {"conforms": chi2 < 15.507, "chi2": round(chi2, 2), "critical_005": 15.507}

    def _test_zscore(self, prices: list[float]) -> dict:
        if len(prices) < 3:
            return {"outlier_count": 0, "outliers": []}
        mean = sum(prices) / len(prices)
        std = math.sqrt(sum((p - mean) ** 2 for p in prices) / len(prices))
        if std < 0.01:
            return {"outlier_count": 0, "outliers": []}
        outliers = [{"price": round(p, 2), "z": round(abs(p - mean) / std, 2)}
                    for p in prices if abs(p - mean) / std > self.z_score_threshold]
        return {"outlier_count": len(outliers), "outlier_pct": round(len(outliers) / len(prices) * 100, 1),
                "mean": round(mean, 2), "std": round(std, 2), "outliers": outliers[:10]}

    def _test_round_numbers(self, prices: list[float]) -> dict:
        rnd = sum(1 for p in prices if p > 0 and p >= 100 and p % 100 == 0)
        pct = round(rnd / max(1, len(prices)) * 100, 1)
        return {"round_count": rnd, "suspicious_pct": pct, "suspicious": pct > 15.0}

    def _test_iqr(self, prices: list[float]) -> dict:
        s = sorted(prices)
        n = len(s)
        if n < 4:
            return {"outlier_count": 0, "outliers": []}
        q1, q3 = s[n // 4], s[(3 * n) // 4]
        iqr = q3 - q1
        if iqr < 0.01:
            return {"outlier_count": 0, "outliers": []}
        lo, hi = q1 - self.iqr_multiplier * iqr, q3 + self.iqr_multiplier * iqr
        outliers = [{"price": round(p, 2), "bound": "low" if p < lo else "high"}
                    for p in prices if p < lo or p > hi]
        return {"outlier_count": len(outliers), "q1": round(q1, 2), "q3": round(q3, 2),
                "iqr": round(iqr, 2), "outliers": outliers[:10]}

    @staticmethod
    def _extract_all_prices(profiles: list[dict]) -> list[float]:
        prices = []
        for p in profiles:
            for sec in p.get("x84_data", {}).get("sections", []):
                for pos in sec.get("positions", []):
                    for k in ("unit_price_net_eur", "unit_price_eur", "total_eur"):
                        if pos.get(k) and float(pos[k]) > 0:
                            prices.append(float(pos[k]))
                            break
        return prices
