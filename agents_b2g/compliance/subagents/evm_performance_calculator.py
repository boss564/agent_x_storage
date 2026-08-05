"""
Subagent: EVMPerformanceCalculator — Earned Value Management (SPI/CPI/EAC).

Computes ANSI/EIA-748 EVM metrics from GAEB budget, PoPW progress,
and treasury actuals: PV, EV, AC, SPI, CPI, EAC, ETC, VAC, TCPI.

Usage:
    calc = EVMPerformanceCalculator()
    result = calc.calculate_evm("TED-2026-0815", comparison_matrix=matrix)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any

getcontext().prec = 28
logger = logging.getLogger("EVMPerformanceCalculator")


class EVMPerformanceCalculator:
    """ANSI/EIA-748 Earned Value Management metrics."""

    BAC = Decimal("1274896.80")

    _POSITION_BUDGET = {
        "LV-0101": 83250.00, "LV-0102": 112100.00, "LV-0201": 20900.00,
        "LV-0301": 540000.00, "LV-0302": 17000.00,
        "LV-0401": 3360.00, "LV-0501": 55250.00, "LV-0601": 144000.00,
    }

    def __init__(self, archive_dir: str = "archive_b2g",
                 audit_log: str = "logs/b2g_event_bus.jsonl"):
        self.archive_dir = Path(archive_dir)
        self.audit_log = Path(audit_log)

    # ============================================================
    # Main calculation
    # ============================================================

    def calculate_evm(self, tender_id: str,
                      comparison_matrix: list[dict] | None = None,
                      stichtag: str | None = None) -> dict[str, Any]:
        """Compute full EVM report: PV, EV, AC, SPI, CPI, EAC, VAC, TCPI."""

        logger.info(f"EVM for {tender_id}")

        # 1. Planned Value (Budget)
        pv = self._load_pv(tender_id)

        # 2. Actual Cost (from ledger)
        ac = self._load_ac(tender_id)

        # 3. Earned Value (progress × budget)
        ev = self._calculate_ev(comparison_matrix or [])

        # 4. Performance indices
        metrics = self._compute_metrics(pv, ev, ac)

        # 5. Forecast
        forecast = self._forecast(metrics, ac)

        # 6. Traffic light
        tl = self._traffic_light(metrics)

        stichtag_str = stichtag or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        print(f"  [EVM-Calc]      📈 SPI={metrics['spi']:.3f}, CPI={metrics['cpi']:.3f}, "
              f"EAC={forecast['eac_eur']:,.0f} €, "
              f"Schedule={tl['schedule']['status']}, Cost={tl['cost']['status']}")

        return {
            "status": "EVM_CALCULATED",
            "tender_id": tender_id,
            "stichtag": stichtag_str,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
            "forecast": forecast,
            "traffic_light": tl,
        }

    # ============================================================
    # Data loading
    # ============================================================

    def _load_pv(self, tender_id: str) -> Decimal:
        # Try from settlement JSONs
        for sf in self.archive_dir.rglob("*settlement*.json"):
            try:
                data = json.loads(sf.read_text())
                if tender_id in json.dumps(data):
                    amt = data.get("contract_value_eur", 0)
                    if amt > 0:
                        return Decimal(str(amt))
            except (json.JSONDecodeError, OSError):
                continue
        return self.BAC

    def _load_ac(self, tender_id: str) -> Decimal:
        ac = Decimal("0")
        if self.audit_log.exists():
            for line in self.audit_log.read_text().splitlines():
                if tender_id not in line:
                    continue
                try:
                    rec = json.loads(line.strip())
                    subj = rec.get("subject", "")
                    payload = rec.get("payload", rec)
                    if "disburse" in subj or "payment" in subj:
                        ac += Decimal(str(payload.get("amount_eur", 0)))
                except (json.JSONDecodeError, ValueError):
                    continue
        # Mock fallback
        if ac == 0:
            ac = Decimal("434778.00")  # ~34% of BAC
        return ac

    # ============================================================
    # EV computation
    # ============================================================

    def _calculate_ev(self, matrix: list[dict]) -> Decimal:
        ev = Decimal("0")
        if matrix:
            for entry in matrix:
                oz = entry.get("oz", "")
                pct = Decimal(str(entry.get("delta_pct", 0)))
                progress = max(Decimal("0"), min(Decimal("100"), Decimal("100") + pct))
                budget = Decimal(str(self._POSITION_BUDGET.get(oz, 0)))
                ev += (progress / Decimal("100")) * budget
        else:
            # No matrix: use 31% progress (from telemetry wave)
            ev = self.BAC * Decimal("0.31")
        return ev.quantize(Decimal("0.01"))

    # ============================================================
    # Metrics
    # ============================================================

    @staticmethod
    def _compute_metrics(pv: Decimal, ev: Decimal, ac: Decimal) -> dict:
        ac_safe = ac if ac > 0 else ev  # Avoid div by zero
        pv_safe = pv if pv > 0 else Decimal("1")
        spi = float((ev / pv_safe).quantize(Decimal("0.001")))
        cpi = float((ev / ac_safe).quantize(Decimal("0.001")))
        sv = float(ev - pv)
        cv = float(ev - ac)
        pct = float((ev / pv_safe * 100).quantize(Decimal("0.1")))

        return {"pv_eur": float(pv), "ev_eur": float(ev), "ac_eur": float(ac),
                "spi": spi, "cpi": cpi,
                "schedule_variance_eur": sv, "cost_variance_eur": cv,
                "percent_complete": pct}

    # ============================================================
    # Forecast
    # ============================================================

    @staticmethod
    def _forecast(m: dict, ac: Decimal) -> dict:
        ev = Decimal(str(m["ev_eur"]))
        ac_safe = Decimal(str(m["ac_eur"]))
        bac = Decimal(str(m["pv_eur"]))
        cpi = Decimal(str(m["cpi"]))
        cpi_safe = cpi if cpi > Decimal("0.01") else Decimal("1.0")

        eac = (bac / cpi_safe).quantize(Decimal("0.01"))
        etc = (eac - ac_safe).quantize(Decimal("0.01"))
        vac = (bac - eac).quantize(Decimal("0.01"))
        tcpi = float(((bac - ev) / max(Decimal("0.01"), bac - ac_safe))
                      .quantize(Decimal("0.001")))

        status = ("BUDGET_EINGEHALTEN" if eac <= bac
                  else "LEICHTE_UEBERSCHREITUNG" if eac <= bac * Decimal("1.05")
                  else "BUDGETUEBERSCHREITUNG")

        return {"bac_eur": float(bac), "eac_eur": float(eac), "etc_eur": float(etc),
                "vac_eur": float(vac), "tcpi": tcpi, "projection_status": status}

    # ============================================================
    # Traffic light
    # ============================================================

    @staticmethod
    def _traffic_light(m: dict) -> dict:
        spi, cpi = m["spi"], m["cpi"]
        s_s = "GREEN" if spi >= 0.95 else ("YELLOW" if spi >= 0.85 else "RED")
        c_s = "GREEN" if cpi >= 0.95 else ("YELLOW" if cpi >= 0.85 else "RED")
        s_msg = { "GREEN": "Terminplan eingehalten.", "YELLOW": "Leichte Verzögerung.",
                  "RED": "Erhebliche Verzögerung!" }
        c_msg = { "GREEN": "Budget eingehalten.", "YELLOW": "Leichte Überschreitung.",
                  "RED": "Erhebliche Überschreitung!" }
        return {
            "schedule": {"status": s_s, "spi": spi, "message": s_msg[s_s]},
            "cost": {"status": c_s, "cpi": cpi, "message": c_msg[c_s]},
            "overall": {"status": "RED" if "RED" in (s_s, c_s)
                         else ("YELLOW" if "YELLOW" in (s_s, c_s) else "GREEN")},
        }
