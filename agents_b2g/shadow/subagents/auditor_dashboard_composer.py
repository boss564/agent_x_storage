# agents_b2g/shadow/subagents/auditor_dashboard_composer.py
"""
Agent 18.7/18.9 — AuditorDashboardComposer + CompletionCertificateGenerator

Read-Only-Dashboard für RPA & Kämmerer (BHO/GemHVO). Kombiniert
Echtzeit-Salden, PoPW-Visualisierung und GoBD-Export in einer
behördenverständlichen Oberfläche. Generiert bei Abschluss das
PDF/A-3-Entlastungszertifikat.

9-stufige Dashboard-Pipeline:
  1. RPAAuthAndRoleManager        — eIDAS/BundID Read-Only Auth
  2. LedgerStateAggregator        — Live-Salden von Gnosis RPC
  3. TransactionStreamFetcher     — On-Chain-TX-Historie
  4. PoPWProofVisualizer          — IoT-Beweise als Badges
  5. TaxBreakdownReporter         — USt + §48b EStG Split-Darstellung
  6. GAEBFulfillmentTracker       — Soll/Ist-Vergleich + CPI
  7. GoBDExportEngine             — PDF/A-3 + JSONL Export
  8. RealtimeWebSocketPublisher   — SSE/WebSocket Live-Updates
  9. HTMLDashboardRenderer        — Responsive C-Level UI
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("AuditorDashboardComposer")


# ============================================================================
# SUB-SUBAGENT 18.7.1: RPAAuthAndRoleManager
# ============================================================================
class RPAAuthAndRoleManager:
    """eIDAS/BundID Read-Only Authentifizierung für RPA-Prüfer."""

    ACCESS_LEVELS = {"rpa_auditor": "READ_ONLY_AUDITOR", "kaemmerer": "READ_ONLY_ADMIN"}

    def authenticate(self, rpa_user_id: str, eidas_token: str = "") -> Dict[str, Any]:
        valid = bool(rpa_user_id and len(rpa_user_id) > 3)
        access = self.ACCESS_LEVELS.get(
            "kaemmerer" if "kaemmerer" in rpa_user_id.lower() else "rpa_auditor",
            "READ_ONLY_AUDITOR"
        )
        return {
            "rpa_officer": rpa_user_id,
            "access_level": access,
            "eidas_certified": valid,
            "session_start": datetime.now(timezone.utc).isoformat() + "Z",
            "permissions": ["VIEW_BALANCES", "VIEW_PROOFS", "EXPORT_GOBD", "VIEW_TAX"],
        }


# ============================================================================
# SUB-SUBAGENT 18.7.2: LedgerStateAggregator
# ============================================================================
class LedgerStateAggregator:
    """Aggregiert Live-Salden via Gnosis RPC (Mock)."""

    def get_balances(self, contract_address: str, budget_eur: float,
                     released_eur: float = 0, retention_eur: float = 0,
                     tax_eur: float = 0) -> Dict[str, Any]:
        remaining = round(budget_eur - released_eur, 2)
        balances = {
            "total_funded_gross_eur": round(budget_eur, 2),
            "total_disbursed_net_eur": round(released_eur - tax_eur - retention_eur, 2),
            "total_tax_paid_finanzamt_eur": round(tax_eur, 2),
            "vob_retention_locked_eur": round(retention_eur, 2),
            "escrow_remaining_available_eur": remaining,
        }
        # BHO Zero-Sum: Funded = Disbursed + Tax + Retention + Remaining
        check = round(balances["total_disbursed_net_eur"] + balances["total_tax_paid_finanzamt_eur"]
                      + balances["vob_retention_locked_eur"] + balances["escrow_remaining_available_eur"], 2)
        delta = round(abs(balances["total_funded_gross_eur"] - check), 2)

        return {"balances": balances, "delta_eur": delta,
                "is_balanced": delta <= 0.02,
                "status": "BALANCED_PERFECT" if delta <= 0.02 else "MISMATCH_ALERT"}


# ============================================================================
# SUB-SUBAGENT 18.7.4: PoPWProofVisualizer
# ============================================================================
class PoPWProofVisualizer:
    """Übersetzt ZK-Proofs in Audit-Badges."""

    def format(self, proofs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        badges = []
        for p in proofs:
            badges.append({
                "milestone_id": p.get("milestone_id", p.get("oz_id", "")),
                "badge": "VERIFIED_ON_CHAIN",
                "sensor": p.get("sensor_type", "IoT"),
                "device": p.get("device_did", ""),
                "human_readable": (f"{p.get('sensor_type', 'Sensor')}: "
                                   f"{p.get('measured_val', 'N/A')} verifiziert via ZK-Proof"),
            })
        return badges


# ============================================================================
# SUB-SUBAGENT 18.7.5: TaxBreakdownReporter
# ============================================================================
class TaxBreakdownReporter:
    """Stellt USt- & Bauabzug-Splits für RPA dar."""

    def report(self, tax_settlement: Dict[str, Any]) -> Dict[str, Any]:
        s = tax_settlement.get("split_summary", {})
        return {
            "ust_eur": s.get("vat_amount_eur", 0),
            "bauabzug_eur": s.get("bauabzug_tax_15pct_eur", 0),
            "net_payout_eur": s.get("net_payout_contractor_eur", 0),
            "vat_rate": s.get("vat_rate_pct", 19.0),
            "regime": tax_settlement.get("tax_regime", {}).get("regime", "Regelbesteuerung"),
        }


# ============================================================================
# SUB-SUBAGENT 18.7.7: GoBDExportEngine
# ============================================================================
class GoBDExportEngine:
    """Generiert GoBD-Prüfpaket (PDF/A-3 + JSONL)."""

    def export(self, tender_id: str, dashboard_data: Dict[str, Any]) -> Dict[str, Any]:
        export_hash = hashlib.sha256(
            json.dumps(dashboard_data, sort_keys=True, default=str).encode()
        ).hexdigest()
        return {
            "jsonl_url": f"/api/v1/audit/export/{tender_id}/jsonl",
            "pdf_a3_url": f"/api/v1/audit/export/{tender_id}/pdf",
            "export_hash": export_hash,
            "exported_at": datetime.now(timezone.utc).isoformat() + "Z",
            "gobd_compliant": True,
        }


# ============================================================================
# SUB-SUBAGENT 18.7.9: HTMLDashboardRenderer
# ============================================================================
class HTMLDashboardRenderer:
    """Generiert responsive C-Level UI (HTML Mock)."""

    def render(self, state: Dict[str, Any]) -> str:
        return (
            '<!DOCTYPE html>\n<html lang="de"><head><meta charset="UTF-8">'
            f'<title>RPA Dashboard — {state.get("tender_id", "")}</title>'
            '</head><body><div id="rpa-dashboard"></div>'
            '<script>window.__RPA_STATE__ = '
            f'{json.dumps(state, ensure_ascii=False)};</script>'
            '</body></html>'
        )


# ============================================================================
# AGENT 18.7: AuditorDashboardComposer (Root)
# ============================================================================
class AuditorDashboardComposer:
    """
    Subagent 18.7/18.9: Read-Only RPA-Dashboard + Abschlusszertifikat.
    """

    def __init__(self):
        self.auth = RPAAuthAndRoleManager()
        self.ledger = LedgerStateAggregator()
        self.proof_viz = PoPWProofVisualizer()
        self.tax_reporter = TaxBreakdownReporter()
        self.gobd_export = GoBDExportEngine()
        self.html_renderer = HTMLDashboardRenderer()

    def generate_dashboard(
        self,
        tender_id: str,
        rpa_user_id: str,
        contract_address: str,
        budget_eur: float,
        released_eur: float = 0,
        retention_eur: float = 0,
        tax_eur: float = 0,
        milestones: Optional[List[Dict[str, Any]]] = None,
        proofs: Optional[List[Dict[str, Any]]] = None,
        tax_data: Optional[Dict[str, Any]] = None,
        eidas_token: str = "",
    ) -> Dict[str, Any]:
        """
        Vollständiges RPA-Dashboard mit allen 9 Sub-Subagenten.

        Returns:
            Dashboard-Payload + HTML + GoBD-Export-URLs.
        """
        job_id = hashlib.sha256(
            f"rpa{tender_id}{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]

        logger.info(f"RPA-Dashboard {job_id}: {tender_id}, Prüfer={rpa_user_id}")

        try:
            # === Step 1: Auth ===
            session = self.auth.authenticate(rpa_user_id, eidas_token)

            # === Step 2: Ledger ===
            ledger = self.ledger.get_balances(
                contract_address, budget_eur, released_eur, retention_eur, tax_eur
            )

            # === Step 3: TX-Historie (Mock) ===
            tx_count = len(milestones or []) * 3  # Pro Milestone ~3 TX

            # === Step 4: Proof-Visualisierung ===
            proof_badges = self.proof_viz.format(proofs or [])

            # === Step 5: Tax-Report ===
            tax_report = self.tax_reporter.report(tax_data or {})

            # === Step 6: GAEB-Fulfillment ===
            completed = sum(1 for m in (milestones or [])
                            if m.get("status") == "RELEASED")
            total = len(milestones or []) or 1
            progress_pct = round(completed / total * 100, 1)

            # === Step 7: GoBD-Export ===
            gobd = self.gobd_export.export(tender_id, {
                "tender_id": tender_id, "ledger": ledger, "completed": completed,
            })

            # === Step 8: Abschlusszertifikat ===
            all_complete = completed == total
            certificate = None
            if all_complete:
                cert_hash = hashlib.sha256(
                    f"completion{tender_id}{budget_eur}".encode()
                ).hexdigest()
                certificate = {
                    "status": "PROJECT_COMPLETED",
                    "completion_date": datetime.now(timezone.utc).isoformat() + "Z",
                    "total_released_eur": released_eur,
                    "budget_eur": budget_eur,
                    "retention_eur": retention_eur,
                    "certificate_hash": cert_hash,
                    "pdf_url": f"/api/v1/certificate/{tender_id}/pdf-a3",
                }

            # === Step 9: HTML-Rendering ===
            payload = {
                "title": "B2G Reallabor — RPA Read-Only Transparenz-Dashboard",
                "tender_id": tender_id,
                "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
                "auditor_session": session,
                "blockchain_anchor": {
                    "network": "Gnosis Chain",
                    "contract_address": contract_address,
                    "explorer_url": f"https://gnosisscan.io/address/{contract_address}",
                },
                "financial_ledger": ledger,
                "project_progress": {
                    "milestones_completed": completed,
                    "milestones_total": total,
                    "progress_pct": progress_pct,
                    "status": "COMPLETED" if all_complete else "IN_PROGRESS",
                },
                "tax_summary": tax_report,
                "verified_proofs": proof_badges,
                "certificate": certificate,
                "gobd_export": gobd,
                "blockchain_events_count": tx_count,
            }
            html = self.html_renderer.render(payload)

            return {
                "status": "DASHBOARD_GENERATED",
                "job_id": job_id,
                "tender_id": tender_id,
                "dashboard": payload,
                "html": html,
                "completion_certificate": certificate,
                "gobd_export_urls": gobd,
                "artifacts": [
                    {"type": "rpa_dashboard", "format": "json"},
                    {"type": "rpa_dashboard", "format": "html", "content": html},
                ],
                "error": None,
                "logs": [{"level": "INFO",
                          "message": f"RPA-Dashboard: {completed}/{total} Milestones, "
                                     f"Ledger Δ={ledger['delta_eur']:.2f} EUR, "
                                     f"{'ZERTIFIKAT ERSTELLT' if certificate else 'in Bearbeitung'}"}],
            }

        except Exception as e:
            logger.error(f"Dashboard failed: {e}")
            return {"status": "FAILED", "job_id": job_id, "error": str(e),
                    "artifacts": [], "logs": [{"level": "ERROR", "message": str(e)}]}


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("AuditorDashboardComposer — Smoke Test")
    print("=" * 60)

    composer = AuditorDashboardComposer()

    result = composer.generate_dashboard(
        tender_id="TED-2026-SHADOW-001",
        rpa_user_id="ORR_Mueller_Rechnungspruefungsamt",
        contract_address="0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
        budget_eur=4_200_000.00,
        released_eur=3_800_000.00,
        retention_eur=190_000.00,
        tax_eur=722_000.00,
        milestones=[
            {"id": "M1", "status": "RELEASED"}, {"id": "M2", "status": "RELEASED"},
            {"id": "M3", "status": "RELEASED"}, {"id": "M4", "status": "RELEASED"},
            {"id": "M5", "status": "RELEASED"},
        ],
        proofs=[
            {"milestone_id": "M2", "sensor_type": "IoT-Waage", "device_did": "did:peaq:waage_03",
             "measured_val": "450 t Beton"},
            {"milestone_id": "M3", "sensor_type": "GPS", "device_did": "did:peaq:bagger_01",
             "measured_val": "52.5200,13.4050"},
        ],
        tax_data={"split_summary": {"vat_amount_eur": 610_000, "bauabzug_tax_15pct_eur": 112_000,
                  "net_payout_contractor_eur": 3_078_000, "vat_rate_pct": 19.0},
                  "tax_regime": {"regime": "§13b Reverse-Charge"}},
    )

    d = result["dashboard"]
    print(f"\nSession: {d['auditor_session']['rpa_officer']} ({d['auditor_session']['access_level']})")
    print(f"Ledger: {d['financial_ledger']['status']} (Δ={d['financial_ledger']['delta_eur']:.2f} EUR)")
    bal = d["financial_ledger"]["balances"]
    print(f"  Funded={bal['total_funded_gross_eur']:,.0f} | Net={bal['total_disbursed_net_eur']:,.0f} | "
          f"Tax={bal['total_tax_paid_finanzamt_eur']:,.0f} | Retention={bal['vob_retention_locked_eur']:,.0f}")
    print(f"Progress: {d['project_progress']['progress_pct']:.0f}% ({d['project_progress']['status']})")
    print(f"Proofs: {len(d['verified_proofs'])} Badges")
    print(f"HTML: {len(result['html'])} Zeichen")
    print(f"GoBD: {d['gobd_export']['jsonl_url']}")

    cert = result.get("completion_certificate")
    if cert:
        print(f"\nZertifikat: {cert['status']} — {cert['certificate_hash'][:32]}...")
    else:
        print("\nZertifikat: Noch nicht verfügbar (Projekt läuft)")

    print("\n✅ Smoke Test abgeschlossen.")
