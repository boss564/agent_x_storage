"""
Subagent: ProgressDashboardComposer — Final Construction Progress Dashboard.

Aggregates Soll/Ist, CPM, EVM, Disruption, and Gantt results into a
structured dashboard with traffic lights, heatmap, critical positions,
and HTML preview for Bauleitung, Investor, and Behörde.

Usage:
    composer = ProgressDashboardComposer()
    dashboard = composer.compose_dashboard(tender_id, comparison, delay, evm, disruption, gantt)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("ProgressDashboardComposer")

STATUS_COLOR = {"GREEN": "#28a745", "YELLOW": "#ffc107",
                "ORANGE": "#fd7e14", "RED": "#dc3545"}


class ProgressDashboardComposer:
    """Aggregates all controlling results into a structured dashboard."""

    # ============================================================
    # Main compose
    # ============================================================

    def compose_dashboard(self, tender_id: str,
                          comparison_result: dict,
                          delay_result: dict,
                          evm_result: dict,
                          disruption_result: dict,
                          gantt_result: dict,
                          stichtag: str | None = None) -> dict[str, Any]:
        """Aggregate all 5 subagent results into final dashboard."""

        logger.info(f"Dashboard composition for {tender_id}")

        stichtag_str = stichtag or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        overview = self._build_overview(comparison_result, delay_result,
                                        evm_result, disruption_result)
        traffic = self._build_traffic(comparison_result, delay_result,
                                      evm_result, disruption_result)
        heatmap = self._build_heatmap(comparison_result)
        evm = self._build_evm_card(evm_result)
        critical = self._build_critical(comparison_result, delay_result,
                                        disruption_result)
        recommendations = self._build_recommendations(traffic, critical, evm)

        dashboard = {
            "tender_id": tender_id, "stichtag": stichtag_str,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overview": overview, "traffic_light": traffic,
            "heatmap": heatmap, "evm_summary": evm,
            "critical_positions": critical,
            "gantt_code": gantt_result.get("mermaid_code", ""),
            "mta": gantt_result.get("mta", {}),
            "recommendations": recommendations,
            "export_formats": {"json": True, "html": True},
        }
        dashboard["html_preview"] = self._html(dashboard)

        print(f"  [Dashboard]     📊 Status={overview['overall_status']}, "
              f"Progress={overview['progress_pct']:.1f}%, "
              f"Critical={len(critical)}")

        return dashboard

    # ============================================================
    # Overview
    # ============================================================

    @staticmethod
    def _build_overview(comp: dict, delay: dict, evm: dict, disr: dict) -> dict:
        progress = evm.get("metrics", {}).get("percent_complete", 0)
        delay_days = delay.get("summary", {}).get("total_delay_days", 0)
        budget = evm.get("forecast", {}).get("projection_status", "?")
        dr_verdict = disr.get("summary", {}).get("verdict", "GREEN")

        if delay_days > 5 or dr_verdict == "RED":
            overall = "RED"
        elif delay_days > 0 or dr_verdict == "YELLOW":
            overall = "YELLOW"
        else:
            overall = "GREEN"

        return {"overall_status": overall, "progress_pct": round(progress, 1),
                "total_delay_days": delay_days, "budget_status": budget,
                "disruption_verdict": dr_verdict}

    # ============================================================
    # Traffic lights
    # ============================================================

    @staticmethod
    def _build_traffic(comp: dict, delay: dict, evm: dict, disr: dict) -> dict:
        delay_days = delay.get("summary", {}).get("total_delay_days", 0)
        s = "GREEN" if delay_days == 0 else ("YELLOW" if delay_days <= 3 else "RED")
        schedule = {"status": s,
                    "message": { "GREEN": "Terminplan eingehalten.",
                                 "YELLOW": "Leichte Verzögerung.",
                                 "RED": "Erhebliche Verzögerung!" }[s]}

        cpi = evm.get("metrics", {}).get("cpi", 1.0)
        c = "GREEN" if cpi >= 0.95 else ("YELLOW" if cpi >= 0.85 else "RED")
        cost = {"status": c,
                "message": { "GREEN": "Budget eingehalten.",
                             "YELLOW": "Leichte Überschreitung.",
                             "RED": "Erhebliche Überschreitung!" }[c]}

        matrix = comp.get("matrix", [])
        crit = sum(1 for m in matrix if m.get("status") == "CRITICAL")
        q = "GREEN" if crit == 0 else ("YELLOW" if crit <= 2 else "RED")
        quality = {"status": q,
                   "message": { "GREEN": "Alle Positionen im Rahmen.",
                                "YELLOW": f"{crit} kritische Abweichungen.",
                                "RED": f"{crit} kritische Abweichungen!" }[q]}

        return {"schedule": schedule, "cost": cost, "quality": quality}

    # ============================================================
    # Heatmap
    # ============================================================

    @staticmethod
    def _build_heatmap(comp: dict) -> dict:
        positions = {}
        for item in comp.get("matrix", []):
            oz = item.get("oz", "?")
            dp = abs(item.get("delta_pct", 0))
            color = ("#008000" if dp < 5 else "#FFD700" if dp < 10
                     else "#FF8C00" if dp < 20 else "#FF0000")
            positions[oz] = {"delta_pct": round(item.get("delta_pct", 0), 1),
                             "color": color, "status": item.get("status", "OK"),
                             "soll": item.get("soll_qty", 0), "ist": item.get("ist_qty", 0)}
        return {"positions": positions,
                "legend": {"<5%": "#008000", "5-10%": "#FFD700",
                           "10-20%": "#FF8C00", ">20%": "#FF0000"}}

    # ============================================================
    # EVM card
    # ============================================================

    @staticmethod
    def _build_evm_card(evm: dict) -> dict:
        m = evm.get("metrics", {})
        f = evm.get("forecast", {})
        t = evm.get("traffic_light", {})
        return {"spi": m.get("spi", 1.0), "cpi": m.get("cpi", 1.0),
                "percent_complete": m.get("percent_complete", 0),
                "eac_eur": f.get("eac_eur", 0), "vac_eur": f.get("vac_eur", 0),
                "schedule_status": t.get("schedule", {}).get("status", "?"),
                "cost_status": t.get("cost", {}).get("status", "?")}

    # ============================================================
    # Critical positions
    # ============================================================

    @staticmethod
    def _build_critical(comp: dict, delay: dict, disr: dict) -> list[dict]:
        crit = []
        for item in comp.get("matrix", []):
            if item.get("status") in ("CRITICAL", "WARNING"):
                crit.append({"oz": item["oz"], "type": "DEVIATION",
                             "severity": item["status"],
                             "msg": f"Δ={item.get('delta_pct', 0):.1f}%"})

        for act_id, info in (delay.get("critical_path", {})
                              .get("critical_delays", {}).items()):
            crit.append({"oz": info.get("oz", "?"), "type": "DELAY",
                         "severity": "CRITICAL",
                         "msg": f"{info.get('delay_days', 0)}d: {info.get('name', '')}"})

        for n in disr.get("notifications", []):
            if n.get("penalty_risk") == "HOCH":
                crit.append({"oz": n.get("position", "?"), "type": "DISRUPTION",
                             "severity": "CRITICAL",
                             "msg": n.get("description", "")[:60]})
        return crit

    # ============================================================
    # Recommendations
    # ============================================================

    @staticmethod
    def _build_recommendations(traffic: dict, critical: list, evm: dict) -> list[str]:
        recs = []
        if traffic["schedule"]["status"] == "RED":
            recs.append("Terminverzug — Nachsteuerung + Kapazitäten erhöhen.")
        elif traffic["schedule"]["status"] == "YELLOW":
            recs.append("Leichter Terminverzug — Nachsteuerung empfohlen.")
        if traffic["cost"]["status"] == "RED":
            recs.append("Budgetüberschreitung — Kostenkontrolle intensivieren.")
        crit_count = sum(1 for c in critical if c["severity"] == "CRITICAL")
        if crit_count > 3:
            recs.append(f"{crit_count} kritische Positionen — Einzelfallprüfung.")
        if not recs:
            recs.append("Baufortschritt im Plan — alle Kennzahlen grün.")
        return recs

    # ============================================================
    # HTML preview
    # ============================================================

    def _html(self, d: dict) -> str:
        o = d["overview"]; t = d["traffic_light"]; e = d["evm_summary"]
        sc = STATUS_COLOR.get(o["overall_status"], "#28a745")

        def badge(s): return STATUS_COLOR.get(s, "#999")

        rows = "".join(
            f'<li><span style="background:{badge(c.get("severity","GREEN"))};'
            f'color:white;padding:2px 8px;border-radius:12px;font-size:12px">'
            f'{c["type"]}</span> {c["oz"]} — {c["msg"]}</li>'
            for c in d["critical_positions"][:10])

        recs = "".join(f"<li>{r}</li>" for r in d["recommendations"])

        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Baufortschritt — {d['tender_id']}</title>
<style>body{{font-family:Arial;margin:20px;background:#f8f9fa}}
.card{{background:white;border-radius:8px;padding:20px;margin:0 0 20px;box-shadow:0 2px 4px rgba(0,0,0,.1)}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}}
.metric{{text-align:center;padding:15px;background:#f8f9fa;border-radius:8px}}
.val{{font-size:24px;font-weight:bold}}
.tl{{display:flex;justify-content:space-around}}
.light{{text-align:center;padding:10px 20px;border-radius:8px;color:white;min-width:120px}}
</style></head><body><div style="max-width:1200px;margin:0 auto">
<div class="card"><h1>Baufortschritts-Dashboard</h1>
<h2>{d['tender_id']}</h2><p>Stichtag: {d['stichtag']} |
Status: <span style="background:{sc};color:white;padding:8px 16px;border-radius:20px">
{o['overall_status']}</span></p></div>
<div class="card"><h3>Kennzahlen</h3><div class="grid">
<div class="metric"><div>Fortschritt</div><div class="val">{e['percent_complete']:.1f}%</div></div>
<div class="metric"><div>SPI</div><div class="val">{e['spi']:.3f}</div></div>
<div class="metric"><div>CPI</div><div class="val">{e['cpi']:.3f}</div></div>
<div class="metric"><div>Verzug</div><div class="val">{o['total_delay_days']}d</div></div>
</div></div>
<div class="card"><h3>Ampelstatus</h3><div class="tl">
<div class="light" style="background:{badge(t['schedule']['status'])}">
<b>Termin</b><br>{t['schedule']['message']}</div>
<div class="light" style="background:{badge(t['cost']['status'])}">
<b>Kosten</b><br>{t['cost']['message']}</div>
<div class="light" style="background:{badge(t['quality']['status'])}">
<b>Qualität</b><br>{t['quality']['message']}</div>
</div></div>
<div class="card"><h3>Kritische Positionen</h3><ul>{rows if rows else '<li>Keine.</li>'}</ul></div>
<div class="card"><h3>Empfehlungen</h3><ul>{recs}</ul></div>
<div class="card"><pre><code>{d['gantt_code'][:2000]}</code></pre></div>
<p style="text-align:center;color:#999;font-size:12px">
Agent X B2G — {d['timestamp'][:19]}</p></div></body></html>"""
