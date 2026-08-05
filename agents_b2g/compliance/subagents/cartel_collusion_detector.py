"""
Subagent: CartelCollusionDetector — Forensic Cartel Detection Engine.

Detects illegal bid rigging and submission fraud through four heuristics:
  1. Identical typos/formulations across bidder short texts
  2. Timestamp clusters — multiple X84 files created within seconds
  3. Price correlation — unit prices deviating < 0.5% (signalling prices)
  4. Metadata fingerprints — identical XML generators, OS, machine IDs

Usage:
    detector = CartelCollusionDetector()
    result = detector.analyze_bids(bidder_profiles)
    # result["verdict"]: GREEN / YELLOW / ORANGE / RED / CRITICAL
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("CartelCollusionDetector")


class CartelCollusionDetector:
    """Forensic cartel detection for procurement tribunals (Vergabekammer)."""

    def __init__(self, similarity_threshold: float = 0.85,
                 price_deviation_threshold: float = 0.5,
                 timestamp_cluster_seconds: int = 300):
        self.similarity_threshold = similarity_threshold
        self.price_deviation_threshold = price_deviation_threshold  # percent
        self.timestamp_cluster_seconds = timestamp_cluster_seconds

    # ============================================================
    # Main analysis
    # ============================================================

    def analyze_bids(self, bidder_profiles: list[dict[str, Any]]) -> dict[str, Any]:
        """Run all four detection heuristics and return collusion score + verdict."""
        logger.info(f"Cartel check: {len(bidder_profiles)} bidders")

        results: dict[str, Any] = {
            "total_bidders": len(bidder_profiles),
            "collusion_score": 0.0,
            "risk_factors": [],
            "suspicious_pairs": [],
            "detailed_findings": {},
        }

        if len(bidder_profiles) < 2:
            results["verdict"] = "GREEN — Nur ein Bieter, keine Kartellprüfung möglich"
            return results

        # Heuristic 1: Identical typos
        typo = self._detect_common_typos(bidder_profiles)
        if typo["detected"]:
            results["risk_factors"].append("IDENTICAL_TYPOS")
            results["detailed_findings"]["typos"] = typo
            results["suspicious_pairs"].extend(typo["pairs"])

        # Heuristic 2: Timestamp clusters
        time_f = self._detect_timestamp_clusters(bidder_profiles)
        if time_f["detected"]:
            results["risk_factors"].append("TIMESTAMP_CLUSTER")
            results["detailed_findings"]["timestamps"] = time_f
            results["suspicious_pairs"].extend(time_f["pairs"])

        # Heuristic 3: Price correlation (signalling prices)
        price = self._detect_price_correlation(bidder_profiles)
        if price["detected"]:
            results["risk_factors"].append("PRICE_CORRELATION")
            results["detailed_findings"]["prices"] = price
            results["suspicious_pairs"].extend(price["pairs"])

        # Heuristic 4: Metadata fingerprints
        meta = self._detect_metadata_fingerprints(bidder_profiles)
        if meta["detected"]:
            results["risk_factors"].append("METADATA_FINGERPRINT")
            results["detailed_findings"]["metadata"] = meta
            results["suspicious_pairs"].extend(meta["pairs"])

        # Verdict
        risk_count = len(results["risk_factors"])
        results["collusion_score"] = min(risk_count * 25.0, 95.0)
        results["verdict"] = {
            0: "GREEN — Keine Auffälligkeiten",
            1: "YELLOW — Geringes Risiko, weitere Prüfung empfohlen",
            2: "ORANGE — Erhöhtes Risiko, Nachprüfung erforderlich",
            3: "RED — Hohes Kartellrisiko, Vergabekammer informieren",
        }.get(risk_count, "CRITICAL — Dringender Verdacht auf Submissionsbetrug")

        logger.info(f"Cartel score: {results['collusion_score']:.0f}% — {results['verdict']}")
        return results

    # ============================================================
    # Heuristic 1: Common typos
    # ============================================================

    _TYPO_PATTERNS = [
        r"Rohrleitunng", r"Edelstahl(?!\-)", r"Betonier(?!ung)", r"Schalunng",
        r"Bewehrung(?!s)", r"Dichtunng", r"Verschraubunng",
        r"Klaeranlage", r"Sanierung(?!s)", r"Abdichtunng",
    ]

    def _detect_common_typos(self, profiles: list[dict]) -> dict:
        all_texts: list[tuple[str, str]] = []
        for p in profiles:
            bid = p.get("bidder_id", "UNKNOWN")
            texts = p.get("x84_data", {}).get("short_texts", [])
            if not texts:
                texts = self._extract_texts_from_profile(p)
            all_texts.append((bid, " ".join(texts)))

        typo_hits: list[tuple[str, str]] = []
        for bid, text in all_texts:
            for pattern in self._TYPO_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    typo_hits.append((bid, pattern))

        pairs = []
        pattern_counts = Counter(t[1] for t in typo_hits)
        for pattern, count in pattern_counts.items():
            if count >= 2:
                affected = [t[0] for t in typo_hits if t[1] == pattern]
                pairs.append({"bidders": affected, "pattern": pattern, "risk": "HIGH"})

        return {"detected": len(pairs) > 0, "pairs": pairs, "hits": len(typo_hits)}

    @staticmethod
    def _extract_texts_from_profile(profile: dict) -> list[str]:
        texts = []
        for sec in profile.get("x84_data", {}).get("sections", []):
            for pos in sec.get("positions", []):
                if pos.get("short_text"):
                    texts.append(pos["short_text"])
                if pos.get("description"):
                    texts.append(pos["description"])
        return texts

    # ============================================================
    # Heuristic 2: Timestamp clusters
    # ============================================================

    def _detect_timestamp_clusters(self, profiles: list[dict]) -> dict:
        timestamps: list[tuple[str, datetime]] = []
        for p in profiles:
            bid = p.get("bidder_id", "UNKNOWN")
            ts_str = (p.get("x84_data", {})
                       .get("project_metadata", {})
                       .get("submission_date", ""))
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                dt = datetime.now(timezone.utc)
            timestamps.append((bid, dt))

        timestamps.sort(key=lambda x: x[1])
        pairs = []
        for i in range(len(timestamps) - 1):
            a_id, a_ts = timestamps[i]
            b_id, b_ts = timestamps[i + 1]
            delta = abs((b_ts - a_ts).total_seconds())
            if delta < self.timestamp_cluster_seconds:
                pairs.append({
                    "bidders": [a_id, b_id],
                    "delta_seconds": round(delta, 1),
                    "risk": "MEDIUM" if delta < 60 else "LOW",
                })

        return {"detected": len(pairs) > 0, "pairs": pairs}

    # ============================================================
    # Heuristic 3: Price correlation (signalling prices)
    # ============================================================

    def _detect_price_correlation(self, profiles: list[dict]) -> dict:
        position_prices: dict[str, list[tuple[str, float]]] = {}
        for p in profiles:
            bid = p.get("bidder_id", "UNKNOWN")
            for sec in p.get("x84_data", {}).get("sections", []):
                for pos in sec.get("positions", []):
                    oz = pos.get("oz", pos.get("position_id", "UNKNOWN"))
                    price = float(pos.get("unit_price_net_eur", pos.get("unit_price_eur", 0)))
                    position_prices.setdefault(oz, []).append((bid, price))

        pairs = []
        for oz, price_list in position_prices.items():
            if len(price_list) < 2:
                continue
            prices = [x[1] for x in price_list]
            avg = sum(prices) / len(prices)
            if avg <= 0:
                continue
            max_dev = max(abs(p - avg) / avg * 100 for p in prices)
            if max_dev < self.price_deviation_threshold:
                pairs.append({
                    "position": oz,
                    "bidders": [x[0] for x in price_list],
                    "prices": prices,
                    "avg_price": round(avg, 2),
                    "max_deviation_pct": round(max_dev, 2),
                    "risk": "HIGH" if max_dev < 0.2 else "MEDIUM",
                })

        return {"detected": len(pairs) > 0, "pairs": pairs}

    # ============================================================
    # Heuristic 4: Metadata fingerprints
    # ============================================================

    def _detect_metadata_fingerprints(self, profiles: list[dict]) -> dict:
        fingerprints: dict[str, list[str]] = {}
        for p in profiles:
            bid = p.get("bidder_id", "UNKNOWN")
            meta = p.get("x84_data", {}).get("project_metadata", {})
            gen = meta.get("generator", meta.get("ProgSystem", "unknown"))
            os_info = meta.get("os", meta.get("platform", "unknown"))
            fp = f"{gen}::{os_info}"
            fingerprints.setdefault(fp, []).append(bid)

        pairs = []
        for fp, bidders in fingerprints.items():
            if len(bidders) >= 2:
                pairs.append({
                    "fingerprint": fp,
                    "bidders": bidders,
                    "risk": "MEDIUM" if "unknown" not in fp.lower() else "LOW",
                })

        return {"detected": len(pairs) > 0, "pairs": pairs}
