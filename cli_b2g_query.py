#!/usr/bin/env python3
"""
Agent X B2G — CLI Query Tool (Wave 10).

Usage:
    python cli_b2g_query.py --agent RPA --tender TED-2026-0815-KLAERANLAGE-NORD
    python cli_b2g_query.py --agent Vergabekammer --tender TED-2026-0815
    python cli_b2g_query.py --agent Controlling --project PROJ-...
    python cli_b2g_query.py --agent Ops --health
    python cli_b2g_query.py --agent PublicData --format csv
    python cli_b2g_query.py --agent LocalEconomy --region Niedersachsen
    python cli_b2g_query.py --agent Treasury --tender TED-... --project PROJ-...
    python cli_b2g_query.py --agent Compliance --audit
    python cli_b2g_query.py --agent Construction --project PROJ-...
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents_b2g.query import QuerySupervisor


async def main():
    parser = argparse.ArgumentParser(description="Agent X B2G Query CLI (Wave 10)")
    parser.add_argument("--agent", type=str, required=True,
                        choices=["Vergabekammer", "RPA", "Construction", "Treasury",
                                 "Compliance", "Controlling", "Ops", "PublicData",
                                 "LocalEconomy"],
                        help="Query agent to invoke")
    parser.add_argument("--tender", type=str, help="Tender ID filter")
    parser.add_argument("--project", type=str, help="Project ID filter")
    parser.add_argument("--region", type=str, default="Niedersachsen",
                        help="Region filter (LocalEconomy)")
    parser.add_argument("--format", type=str, default="json",
                        choices=["json", "csv"], help="Output format")
    parser.add_argument("--health", action="store_true", help="Ops health briefing")
    parser.add_argument("--audit", action="store_true", help="Audit trail validation")
    parser.add_argument("--full-package", action="store_true",
                        help="Full audit package (RPA + Compliance + Treasury)")
    parser.add_argument("--forensic", action="store_true",
                        help="Run forensic cartel + price plausibility analysis")
    parser.add_argument("--amount", type=float, default=0,
                        help="Contract amount for RPA report")
    args = parser.parse_args()

    supervisor = QuerySupervisor()
    result = {}

    print(f"\n  Agent X B2G — Query CLI (Wave 10)")
    print(f"  Agent: {args.agent}")
    print(f"  Time:  {datetime.now(timezone.utc).isoformat()}")
    print(f"  {'─' * 40}")

    if args.agent == "Vergabekammer":
        if args.tender:
            if args.forensic:
                result = await supervisor.vergabekammer.forensic_audit(args.tender)
            else:
                history = await supervisor.vergabekammer.get_tender_history(args.tender)
                compliance = await supervisor.vergabekammer.check_vob_compliance(args.tender)
                result = {"history": history, "vob_compliance": compliance}
        else:
            result = {"error": "--tender required for Vergabekammer queries"}

    elif args.agent == "RPA":
        if args.full_package and args.tender:
            result = await supervisor.full_audit_package(args.tender, args.amount)
        elif args.tender:
            result = await supervisor.rpa.generate_rpa_report(args.tender, args.amount)
        else:
            result = {"error": "--tender required for RPA queries"}

    elif args.agent == "Construction":
        pid = args.project or args.tender or "unknown"
        result = await supervisor.construction.compare_plan_vs_actual(pid)

    elif args.agent == "Treasury":
        tid = args.tender or args.project or ""
        if tid:
            balance = await supervisor.treasury.get_balance_sheet(tender_id=tid)
            retention = await supervisor.treasury.get_retention_status(tid)
            result = {"balance_sheet": balance, "retention": retention}
        else:
            result = {"error": "--tender or --project required"}

    elif args.agent == "Compliance":
        if args.audit:
            result = await supervisor.compliance.validate_audit_trail()
        else:
            result = await supervisor.compliance.check_retention_policy()

    elif args.agent == "Controlling":
        pid = args.project or ""
        cost = await supervisor.controlling.analyze_cost_trend(pid, args.amount)
        utilization = await supervisor.controlling.get_agent_utilization()
        ontime = await supervisor.controlling.get_ontime_stats()
        result = {"cost_trend": cost, "utilization": utilization, "on_time": ontime}

    elif args.agent == "Ops":
        if args.health:
            result = await supervisor.ops_briefing()
        else:
            result = await supervisor.ops.health_snapshot()

    elif args.agent == "PublicData":
        if args.format == "csv":
            result = await supervisor.public_data.export_open_data("csv")
            print(result)
            return
        result = await supervisor.public_data.get_anonymized_stats()

    elif args.agent == "LocalEconomy":
        regional = await supervisor.local_economy.calculate_regional_share(args.region)
        subsidy = await supervisor.local_economy.generate_subsidy_report(args.region)
        result = {"regional_share": regional, "subsidy_impact": subsidy}

    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, indent=2, default=str, ensure_ascii=False))

    print(f"\n  Query completed.")


if __name__ == "__main__":
    asyncio.run(main())
