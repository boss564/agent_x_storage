# agents_b2g/onboarding/subagents/ecosystem_health_monitor.py
"""Agent 19.8 — EcosystemHealthMonitor: Health Dashboard, Metriken, Rollenverteilung."""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
logger = logging.getLogger(__name__)

class EcosystemHealthMonitor:
    def __init__(self):
        self._onboardings: List[Dict[str, Any]] = []
        self._transactions: List[Dict[str, Any]] = []
        self._errors: List[Dict[str, Any]] = []

    def record_onboarding(self, data: Dict[str, Any]) -> None:
        self._onboardings.append({"company": data.get("company_name", data.get("company", "")),
                                   "role": data.get("assigned_role", data.get("role", "")),
                                   "timestamp": data.get("onboarding_timestamp", ""),
                                   "success": data.get("status", "") == "ONBOARDING_SUCCESSFUL"})
        logger.info(f"Health: +1 onboarding ({len(self._onboardings)} total)")

    def get_health_report(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        last_24h = []
        for o in self._onboardings:
            try:
                ts = datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00"))
                if ts >= now - timedelta(hours=24):
                    last_24h.append(o)
            except (ValueError, KeyError):
                pass
        success = [o for o in last_24h if o["success"]]
        rate = len(success) / max(len(last_24h), 1) * 100
        dist = defaultdict(int)
        for o in self._onboardings:
            dist[o["role"]] += 1
        return {"status": "HEALTHY" if rate > 80 else "DEGRADED",
                "total_onboarded": len(self._onboardings),
                "onboardings_24h": len(last_24h),
                "success_rate_24h_pct": round(rate, 1),
                "role_distribution": dict(dist),
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"}
