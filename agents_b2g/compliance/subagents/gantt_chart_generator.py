"""
Subagent: GanttChartGenerator — Mermaid Gantt + Milestone Trend Analysis.

Generates Mermaid.js Gantt charts (Soll/Ist comparison) and MTA
(Milestone Trend Analysis) from the construction schedule and
Soll/Ist comparison matrix.

Usage:
    gen = GanttChartGenerator()
    result = gen.generate_gantt("TED-2026-0815", comparison_matrix=m)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("GanttChartGenerator")


class GanttChartGenerator:
    """Mermaid Gantt + milestone trend analysis for construction progress."""

    _MOCK_SCHEDULE = {
        "start_date": "2026-06-01",
        "activities": {
            "AUSHUB":      {"name": "Baugrubenaushub",           "duration": 20,
                            "predecessors": [],          "start": "2026-06-01", "end": "2026-06-20",
                            "oz": "LV-0501"},
            "SOHLPLATTE":  {"name": "Stahlbetonsohle gießen",    "duration": 30,
                            "predecessors": ["AUSHUB"],   "start": "2026-06-21", "end": "2026-07-20",
                            "oz": "LV-0102", "milestone": True},
            "ROHRE":       {"name": "Edelstahl-Druckleitung",    "duration": 25,
                            "predecessors": ["SOHLPLATTE"],"start": "2026-07-21", "end": "2026-08-14",
                            "oz": "LV-0201"},
            "TECHNIK":     {"name": "Maschinentechnik install.",  "duration": 35,
                            "predecessors": ["SOHLPLATTE"],"start": "2026-07-21", "end": "2026-08-24",
                            "oz": "LV-0302", "milestone": True},
            "ELEKTRO":     {"name": "Elektroinstallation",       "duration": 20,
                            "predecessors": ["ROHRE", "TECHNIK"], "start": "2026-08-25", "end": "2026-09-13",
                            "oz": "LV-0401"},
            "FERTIGSTELL": {"name": "Gesamtabnahme & Übergabe",  "duration": 10,
                            "predecessors": ["ELEKTRO"],  "start": "2026-09-14", "end": "2026-09-23",
                            "oz": None, "milestone": True},
        },
    }

    # ============================================================
    # Main generator
    # ============================================================

    def generate_gantt(self, tender_id: str,
                       comparison_matrix: list[dict] | None = None,
                       stichtag: str | None = None) -> dict[str, Any]:
        """Generate Mermaid Gantt + MTA."""

        logger.info(f"Gantt generation for {tender_id}")

        schedule = self._MOCK_SCHEDULE
        stichtag_str = stichtag or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        delta_by_oz = {}
        if comparison_matrix:
            delta_by_oz = {e["oz"]: e.get("delta_pct", 0) for e in comparison_matrix}

        soll = self._build_soll(schedule)
        ist = self._build_ist(schedule, delta_by_oz)
        mermaid = self._mermaid(soll, ist, stichtag_str)
        mta = self._mta(schedule, delta_by_oz)

        print(f"  [GanttGen]      📊 Mermaid={len(mermaid)} chars, "
              f"MTA={mta['total_milestones']} milestones, "
              f"Trend={mta['overall_trend']}")

        return {
            "status": "GANTT_GENERATED",
            "tender_id": tender_id,
            "stichtag": stichtag_str,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mermaid_code": mermaid,
            "mta": mta,
        }

    # ============================================================
    # Soll/Ist builders
    # ============================================================

    @staticmethod
    def _build_soll(schedule: dict) -> list[dict]:
        return [{
            "id": aid, "name": a["name"],
            "start": a["start"], "end": a["end"],
            "duration": a["duration"], "milestone": a.get("milestone", False),
        } for aid, a in schedule["activities"].items()]

    @staticmethod
    def _build_ist(schedule: dict, delta_by_oz: dict) -> list[dict]:
        ist = []
        for aid, a in schedule["activities"].items():
            oz = a.get("oz")
            delta = delta_by_oz.get(oz, 0) if oz else 0
            progress = max(0, min(100, 100 + delta))
            remaining = 100 - progress
            delay_days = int((remaining / 100) * a["duration"])
            try:
                end_dt = datetime.fromisoformat(a["end"]) + timedelta(days=delay_days)
                ist_end = end_dt.strftime("%Y-%m-%d")
            except (ValueError, KeyError):
                ist_end = a["end"]

            ist.append({
                "id": aid, "name": a["name"],
                "start": a["start"] if progress > 0 else "UNBEGONNEN",
                "end": ist_end, "progress_pct": round(progress, 1),
                "milestone": a.get("milestone", False),
            })
        return ist

    # ============================================================
    # Mermaid code generation
    # ============================================================

    @staticmethod
    def _mermaid(soll: list[dict], ist: list[dict], stichtag: str) -> str:
        lines = ["gantt",
                 f"    title Baufortschritt — Soll/Ist (Stichtag: {stichtag})",
                 "    dateFormat YYYY-MM-DD", "    todayMarker off",
                 "", "    section Soll (Plan)"]
        for a in soll:
            marker = "milestone, " if a["milestone"] else ""
            lines.append(f"    {a['name']} :{marker}{a['id']}_soll, {a['start']}, {a['end']}")

        lines.append("    section Ist (Tatsächlich)")
        for a in ist:
            if a["start"] == "UNBEGONNEN":
                lines.append(f"    {a['name']} :crit, {a['id']}_ist, after {a['id']}_soll, {a['duration']}d")
            else:
                crit = "crit, " if a.get("progress_pct", 0) < 80 else ""
                lines.append(f"    {a['name']} :{crit}{a['id']}_ist, {a['start']}, {a['end']}")

        lines.append(f"\n    section Status")
        lines.append(f"    Stichtag :done, today, {stichtag}, 1d")
        return "\n".join(lines)

    # ============================================================
    # MTA
    # ============================================================

    def _mta(self, schedule: dict, delta_by_oz: dict) -> dict:
        milestones = []
        for aid, a in schedule["activities"].items():
            if not a.get("milestone"):
                continue
            oz = a.get("oz")
            delta = delta_by_oz.get(oz, 0) if oz else 0
            progress = max(0, min(100, 100 + delta))
            remaining = 100 - progress
            delay = int((remaining / 100) * a["duration"])

            try:
                planned = datetime.fromisoformat(a["end"])
                actual = planned + timedelta(days=delay)
            except (ValueError, KeyError):
                planned = datetime.now(timezone.utc)
                actual = planned

            deviation = (actual - planned).days
            status = ("ON_TRACK" if deviation <= 0
                      else "SLIGHT_DELAY" if deviation <= 3
                      else "SIGNIFICANT_DELAY")

            milestones.append({
                "id": aid, "name": a["name"],
                "planned": planned.strftime("%Y-%m-%d"),
                "actual": actual.strftime("%Y-%m-%d"),
                "deviation_days": deviation, "status": status,
            })

        total = len(milestones)
        on_track = sum(1 for m in milestones if m["status"] == "ON_TRACK")
        significant = sum(1 for m in milestones if m["status"] == "SIGNIFICANT_DELAY")

        return {
            "milestones": milestones, "total_milestones": total,
            "on_track": on_track, "significant_delay": significant,
            "overall_trend": ("ON_TRACK" if on_track >= total * 0.8
                              else "MODERATE_DELAY" if significant <= 2
                              else "SIGNIFICANT_DELAY"),
        }
