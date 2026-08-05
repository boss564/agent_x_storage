"""
Subagent: DelayAnalyzer — Critical Path Method (CPM) Delay Detection.

Computes forward/backward pass, total float, critical path, and delay prognosis
from the GAEB schedule plan vs. actual PoPW progress per activity.

Usage:
    analyzer = DelayAnalyzer()
    result = analyzer.analyze_delays("TED-2026-0815-KLAERANLAGE-NORD")
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("DelayAnalyzer")


class DelayAnalyzer:
    """CPM-based critical path analysis with progress-weighted delay detection."""

    _MOCK_SCHEDULE = {
        "start_date": "2026-06-01",
        "activities": {
            "AUSHUB":      {"name": "Baugrubenaushub",           "duration": 20,
                            "predecessors": [],          "oz": "LV-0501"},
            "SOHLPLATTE":  {"name": "Stahlbetonsohle gießen",    "duration": 30,
                            "predecessors": ["AUSHUB"],   "oz": "LV-0102", "milestone": True},
            "ROHRE":       {"name": "Edelstahl-Druckleitung",    "duration": 25,
                            "predecessors": ["SOHLPLATTE"],"oz": "LV-0201"},
            "TECHNIK":     {"name": "Maschinentechnik install.",  "duration": 35,
                            "predecessors": ["SOHLPLATTE"],"oz": "LV-0302", "milestone": True},
            "ELEKTRO":     {"name": "Elektroinstallation",       "duration": 20,
                            "predecessors": ["ROHRE", "TECHNIK"], "oz": "LV-0401"},
            "FERTIGSTELL": {"name": "Gesamtabnahme & Übergabe",  "duration": 10,
                            "predecessors": ["ELEKTRO"],  "oz": None, "milestone": True},
        },
    }

    # ============================================================
    # Main analysis
    # ============================================================

    def analyze_delays(self, tender_id: str,
                       comparison_matrix: list[dict] | None = None,
                       stichtag: str | None = None) -> dict[str, Any]:
        """CPM analysis with progress-weighted delay prognosis."""

        logger.info(f"Delay analysis for {tender_id}")

        schedule = self._MOCK_SCHEDULE
        start = datetime.fromisoformat(schedule["start_date"])
        activities = schedule["activities"]
        stichtag_dt = (datetime.fromisoformat(stichtag) if stichtag
                       else datetime.now(timezone.utc))

        # Map OZ → delta% from comparison matrix
        delta_by_oz = {}
        if comparison_matrix:
            delta_by_oz = {e["oz"]: e.get("delta_pct", 0) for e in comparison_matrix}

        # === Forward pass ===
        es, ef = {}, {}
        for act_id in activities:
            preds = activities[act_id]["predecessors"]
            es[act_id] = max((ef[p] for p in preds if p in ef), default=0)
            ef[act_id] = es[act_id] + activities[act_id]["duration"]

        project_end = max(ef.values())
        original_end = start + timedelta(days=project_end)

        # === Backward pass ===
        ls, lf = {}, {}
        for act_id in reversed(list(activities.keys())):
            succs = [k for k, v in activities.items()
                    if act_id in v["predecessors"]]
            lf[act_id] = min((ls[s] for s in succs if s in ls), default=project_end)
            ls[act_id] = lf[act_id] - activities[act_id]["duration"]

        # === Critical path ===
        critical = [a for a in activities if ls[a] - es[a] == 0]
        floats = {a: ls[a] - es[a] for a in activities}

        # === Delay per activity ===
        delays = {}
        for act_id, act in activities.items():
            oz = act.get("oz")
            delta = delta_by_oz.get(oz, 0)
            if delta < 0:
                # Negative delta = behind schedule
                delays[act_id] = int(abs(delta) / 100 * act["duration"])
            else:
                delays[act_id] = 0

        # Critical delays only
        critical_delays = {a: {"name": activities[a]["name"],
                               "delay_days": delays[a],
                               "oz": activities[a].get("oz")}
                          for a in critical if delays.get(a, 0) > 0}

        total_delay = max(delays.values()) if delays else 0
        expected_end = start + timedelta(days=project_end + total_delay)

        # === Prognosis ===
        prognosis = self._prognosis(total_delay, expected_end)

        print(f"  [DelayAnalyzer] ⏱️ CPM: {len(critical)}/{len(activities)} on critical path, "
              f"Total delay={total_delay}d, Expected end={expected_end.strftime('%Y-%m-%d')} "
              f"[{prognosis['status']}]")

        return {
            "status": "ANALYSIS_COMPLETE",
            "tender_id": tender_id,
            "stichtag": stichtag_dt.strftime("%Y-%m-%d"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "critical_path": {
                "activities": len(activities),
                "critical": critical,
                "total_float": floats,
                "delays": delays,
                "critical_delays": critical_delays,
                "original_end": original_end.strftime("%Y-%m-%d"),
                "expected_end": expected_end.strftime("%Y-%m-%d"),
                "total_delay_days": total_delay,
            },
            "prognosis": prognosis,
            "summary": {
                "total_activities": len(activities),
                "on_critical_path": len(critical),
                "delayed_critical": len(critical_delays),
                "total_delay_days": total_delay,
                "status": prognosis["status"],
                "expected_end": prognosis["expected_end_date"],
                "recommendation": self._recommend(total_delay),
            },
        }

    @staticmethod
    def _prognosis(delay_days: int, expected_end: datetime) -> dict:
        if delay_days == 0:
            return {"status": "ON_TRACK",
                    "message": "Endtermin wird voraussichtlich eingehalten.",
                    "expected_end_date": expected_end.strftime("%Y-%m-%d"),
                    "delay_days": 0}
        if delay_days <= 5:
            return {"status": "SLIGHT_DELAY",
                    "message": f"Leichter Verzug von {delay_days} Tagen.",
                    "expected_end_date": expected_end.strftime("%Y-%m-%d"),
                    "delay_days": delay_days}
        if delay_days <= 15:
            return {"status": "MODERATE_DELAY",
                    "message": f"Moderater Verzug von {delay_days} Tagen.",
                    "expected_end_date": expected_end.strftime("%Y-%m-%d"),
                    "delay_days": delay_days}
        return {"status": "SEVERE_DELAY",
                "message": f"Erheblicher Verzug von {delay_days} Tagen.",
                "expected_end_date": expected_end.strftime("%Y-%m-%d"),
                "delay_days": delay_days}

    @staticmethod
    def _recommend(delay_days: int) -> str:
        if delay_days == 0:
            return "Keine Maßnahmen erforderlich."
        if delay_days <= 5:
            return "Leichte Nachsteuerung — zusätzliche Schichten."
        if delay_days <= 15:
            return "Nachsteuerung erforderlich — Kapazitäten erhöhen."
        return "Umfassende Maßnahmen — Terminverlängerung prüfen."
