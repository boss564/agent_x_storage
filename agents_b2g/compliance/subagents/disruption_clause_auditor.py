"""
Subagent: DisruptionClauseAuditor — VOB/B §6 Disruption + Weather + Liability.

Audits construction disruption notifications against weather data,
delay analysis, and assigns liability (Owner vs. GC) with penalty risk.

Usage:
    auditor = DisruptionClauseAuditor()
    result = auditor.audit_disruptions("TED-2026-0815", delay_analysis=...)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("DisruptionClauseAuditor")


class DisruptionClauseAuditor:
    """VOB/B §6 disruption audit: weather, liability, penalty risk."""

    _MOCK_DISRUPTIONS = [
        {"id": "DIS-001", "date": "2026-07-15T10:00:00Z",
         "data": {"position": "LV-0301", "description": "Starkregen — Betonierarbeiten gestoppt",
                  "duration_days": 3, "cause": "weather", "reported_by": "GU"}},
        {"id": "DIS-002", "date": "2026-08-01T14:00:00Z",
         "data": {"position": "LV-0201", "description": "Material-Lieferverzug durch Änderungswunsch Bauherr",
                  "duration_days": 5, "cause": "owner", "reported_by": "GU"}},
    ]

    _MOCK_WEATHER = {
        "rain_events": [
            {"date": "2026-07-15", "amount_mm": 35.2},
            {"date": "2026-07-16", "amount_mm": 28.7},
            {"date": "2026-08-03", "amount_mm": 18.1},
        ],
    }

    def __init__(self, archive_dir: str = "archive_b2g",
                 audit_log: str = "logs/b2g_event_bus.jsonl"):
        self.archive_dir = Path(archive_dir)
        self.audit_log = Path(audit_log)

    # ============================================================
    # Main audit
    # ============================================================

    def audit_disruptions(self, tender_id: str,
                          delay_analysis: dict | None = None,
                          stichtag: str | None = None) -> dict[str, Any]:
        """Audit all disruption notifications for liability + penalty risk."""

        logger.info(f"Disruption audit for {tender_id}")

        notifications = self._load_notifications(tender_id)
        weather = self._MOCK_WEATHER

        results = []
        for n in notifications:
            results.append(self._audit_one(n, weather, delay_analysis))

        owner_liab = sum(1 for r in results if r["liability"] == "Bauherr")
        gu_liab = sum(1 for r in results if r["liability"] == "GU")
        high_risk = sum(1 for r in results if r["penalty_risk"] == "HOCH")
        total_penalty = sum(r["potential_penalty_eur"] for r in results)

        verdict = ("GREEN" if gu_liab == 0 and high_risk == 0
                   else "YELLOW" if gu_liab <= 2 and high_risk <= 1
                   else "RED")

        print(f"  [Disruption]    ⚖️ {len(results)} disruptions: "
              f"Owner={owner_liab}, GU={gu_liab}, HighRisk={high_risk}, "
              f"Penalty={total_penalty:,.0f} € — {verdict}")

        return {
            "status": "AUDIT_COMPLETE",
            "tender_id": tender_id,
            "stichtag": stichtag or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notifications": results,
            "summary": {
                "total": len(results),
                "owner_liability": owner_liab,
                "gu_liability": gu_liab,
                "high_risk": high_risk,
                "total_potential_penalty_eur": round(total_penalty, 2),
                "verdict": verdict,
            },
            "recommendation": self._recommend(verdict, gu_liab),
        }

    # ============================================================
    # Per-notification audit
    # ============================================================

    def _audit_one(self, n: dict, weather: dict,
                   delay_analysis: dict | None) -> dict:
        data = n.get("data", {})
        cause = data.get("cause", "unknown")
        duration = data.get("duration_days", 0)
        position = data.get("position", "")

        # Weather match
        weather_match = self._check_weather(n, weather)

        # Delay match
        delay_match = False
        delay_days = 0
        if delay_analysis:
            cds = delay_analysis.get("critical_path", {}).get("critical_delays", {})
            for act, info in cds.items():
                if info.get("oz") == position:
                    delay_match = True
                    delay_days = info.get("delay_days", 0)
                    break

        # Liability
        if cause == "weather" and weather_match:
            liability = "Bauherr"
            reason = "Unvermeidbare Witterung (VOB/B §6 Abs. 2)"
        elif cause == "owner":
            liability = "Bauherr"
            reason = "Änderungswunsch / Verzögerung durch Bauherrn"
        else:
            liability = "GU"
            reason = "Organisatorische/technische Probleme des GU"

        # Penalty risk
        if liability == "GU" and duration > 0:
            penalty_risk = "HOCH" if duration > 3 else "MITTEL"
            potential = duration * 0.01 * 1_274_896.80  # 1% of contract per day
        else:
            penalty_risk = "GERING"
            potential = 0.0

        return {
            "notification_id": n.get("id", "?"),
            "date": n.get("date", ""),
            "position": position,
            "description": data.get("description", ""),
            "duration_days": duration,
            "cause": cause,
            "weather_match": weather_match,
            "delay_match": delay_match,
            "delay_days_matched": delay_days,
            "liability": liability,
            "liability_reason": reason,
            "penalty_risk": penalty_risk,
            "potential_penalty_eur": round(potential, 2),
            "action": self._action(liability, penalty_risk),
        }

    @staticmethod
    def _check_weather(n: dict, weather: dict) -> bool:
        date_str = (n.get("date", ""))[:10]
        for event in weather.get("rain_events", []):
            if event.get("date") == date_str and event.get("amount_mm", 0) > 10:
                return True
        return False

    @staticmethod
    def _action(liability: str, risk: str) -> str:
        if liability == "Bauherr":
            return "Terminverlängerung prüfen — keine Vertragsstrafe."
        if risk == "HOCH":
            return "GU in Verzug setzen — Vertragsstrafe droht!"
        return "Nachsteuerung einfordern."

    @staticmethod
    def _recommend(verdict: str, gu_count: int) -> str:
        if verdict == "GREEN":
            return "Alle Behinderungen im Risikobereich Bauherr. Keine Vertragsstrafen."
        if verdict == "YELLOW":
            return f"{gu_count} GU-seitige Verzögerungen. Nachsteuerung empfohlen."
        return "Hohes Vertragsstrafen-Risiko. GU in Verzug setzen."

    # ============================================================
    # Data loading
    # ============================================================

    def _load_notifications(self, tender_id: str) -> list[dict]:
        if self.audit_log.exists():
            notifications = []
            for line in self.audit_log.read_text().splitlines():
                if tender_id not in line:
                    continue
                try:
                    rec = json.loads(line.strip())
                    if "disruption" in rec.get("subject", "").lower():
                        notifications.append(rec)
                except json.JSONDecodeError:
                    continue
            if notifications:
                return notifications
        return self._MOCK_DISRUPTIONS
