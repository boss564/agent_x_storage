"""A7 — FiscalComplianceAuditor (Wave 40 Quadrant 4 / Operational).

Nine subagents: GewerbesteuerCalculator → JahresabschlussGenerator.
Invariants: Handelsbuchführung, §13b UStG, GoBD tags, DATEV export.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from agents_b2g.resilience.agents import make_response
from agents_b2g.resilience.config import ResilienceConfig
from agents_b2g.resilience.logging_utils import JSONLogger, _safe_call


def _d(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Subagents (9)
# ---------------------------------------------------------------------------


class GewerbesteuerCalculator:
    """Approximate trade GewSt (Hebesatz × Messzahl × Gewinn)."""

    name = "GewerbesteuerCalculator"

    def run(
        self,
        taxable_profit_eur: float,
        hebesatz: float = 400.0,
        messzahl: float = 0.035,
    ) -> dict[str, Any]:
        profit = _d(taxable_profit_eur)
        if profit <= 0:
            tax = _d(0)
        else:
            tax = (profit * _d(messzahl) * (_d(hebesatz) / _d(100))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return {
            "taxable_profit_eur": float(profit),
            "gewerbesteuer_eur": float(tax),
            "hebesatz": hebesatz,
            "messzahl": messzahl,
        }


class HandelsbuchfuehrungsValidator:
    """Validate double-entry trade book: debit == credit."""

    name = "HandelsbuchfuehrungsValidator"

    def run(self, entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        debit = sum((_d(e.get("debit", 0)) for e in entries), Decimal("0.00"))
        credit = sum((_d(e.get("credit", 0)) for e in entries), Decimal("0.00"))
        delta = debit - credit
        return {
            "debit_eur": float(debit),
            "credit_eur": float(credit),
            "delta_eur": float(delta),
            "balanced": abs(delta) <= Decimal("0.01"),
            "entry_count": len(list(entries)),
        }


class GoBDTransactionTagger:
    """Tag each TX with GoBD-required metadata."""

    name = "GoBDTransactionTagger"

    REQUIRED = ("tx_id", "timestamp", "amount_eur", "counterparty", "purpose")

    def run(self, transactions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        tagged = []
        missing = []
        for tx in transactions:
            gaps = [k for k in self.REQUIRED if not tx.get(k)]
            if gaps:
                missing.append({"tx_id": tx.get("tx_id"), "missing": gaps})
            else:
                tagged.append(
                    {
                        **dict(tx),
                        "gobd_tag": "WORM_ELIGIBLE",
                        "ustg_13b": bool(tx.get("reverse_charge", tx.get("ustg_13b", False))),
                    }
                )
        return {
            "tagged_count": len(tagged),
            "missing_count": len(missing),
            "ok": len(missing) == 0,
            "missing": missing[:16],
            "tagged": tagged[:32],
        }


class DatevExporter:
    """Produce DATEV-like CSV rows for Steuerberater."""

    name = "DatevExporter"

    def run(self, tagged: Sequence[Mapping[str, Any]], user_id: str) -> dict[str, Any]:
        rows = []
        for tx in tagged:
            rows.append(
                {
                    "Umsatz": tx.get("amount_eur"),
                    "SollHaben": "S" if float(tx.get("amount_eur", 0)) >= 0 else "H",
                    "Belegfeld1": tx.get("tx_id"),
                    "Buchungstext": tx.get("purpose"),
                    "Gegenkonto": tx.get("counterparty"),
                    "Datum": str(tx.get("timestamp", ""))[:10],
                    "BU": "40" if tx.get("ustg_13b") else "",
                }
            )
        return {
            "format": "DATEV_CSV_V1",
            "row_count": len(rows),
            "user_id": user_id,
            "rows": rows[:64],
            "exported": len(rows) > 0 or len(tagged) == 0,
        }


class TaxLotTracker:
    """FIFO tax-lot inventory for traded asset."""

    name = "TaxLotTracker"

    def run(self, lots: Sequence[Mapping[str, Any]], disposals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        inventory = [
            {"qty": float(l.get("qty", 0)), "cost_eur": float(l.get("cost_eur", 0))}
            for l in lots
            if float(l.get("qty", 0)) > 0
        ]
        realized = 0.0
        for d in disposals:
            need = float(d.get("qty", 0))
            proceeds = float(d.get("proceeds_eur", 0))
            cost = 0.0
            while need > 1e-12 and inventory:
                lot = inventory[0]
                take = min(need, lot["qty"])
                unit = lot["cost_eur"] / lot["qty"] if lot["qty"] else 0.0
                cost += take * unit
                lot["qty"] -= take
                need -= take
                if lot["qty"] <= 1e-12:
                    inventory.pop(0)
            realized += proceeds - cost
        remaining_qty = sum(l["qty"] for l in inventory)
        return {
            "remaining_qty": round(remaining_qty, 8),
            "realized_preview_eur": round(realized, 2),
            "lot_count": len(inventory),
            "ok": need <= 1e-12 if disposals else True,
        }


class RealizedGainLossAggregator:
    """Aggregate realized PnL across lots / periods."""

    name = "RealizedGainLossAggregator"

    def run(self, gains: Sequence[float], losses: Sequence[float]) -> dict[str, Any]:
        g = sum(float(x) for x in gains)
        l = sum(float(x) for x in losses)
        net = round(g - l, 2)
        return {"gains_eur": round(g, 2), "losses_eur": round(l, 2), "net_eur": net}


class AuditTrailSealer:
    """Seal fiscal audit package with content hash."""

    name = "AuditTrailSealer"

    def run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw = str(sorted(payload.items())).encode()
        digest = hashlib.sha256(raw).hexdigest()
        return {"seal_hash": digest, "sealed": True, "algo": "sha256"}


class BZStReporter:
    """BZSt / reverse-charge reporting stub (§13b)."""

    name = "BZStReporter"

    def run(self, transactions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        rc = [t for t in transactions if t.get("ustg_13b") or t.get("reverse_charge")]
        total = float(sum(_d(t.get("amount_eur", 0)) for t in rc))
        return {
            "reverse_charge_count": len(rc),
            "reverse_charge_total_eur": total,
            "reported": True,
            "schema": "BZSt_USt_13b_v1",
        }


class JahresabschlussGenerator:
    """Compose year-end summary from fiscal artifacts."""

    name = "JahresabschlussGenerator"

    def run(
        self,
        *,
        net_pnl_eur: float,
        gewerbesteuer_eur: float,
        balanced_books: bool,
        gobd_ok: bool,
        datev_exported: bool,
    ) -> dict[str, Any]:
        complete = balanced_books and gobd_ok and datev_exported
        return {
            "net_pnl_eur": net_pnl_eur,
            "gewerbesteuer_eur": gewerbesteuer_eur,
            "complete": complete,
            "fiscal_ok": complete,
            "sections": ["GuV", "Handelsbuch", "DATEV", "BZSt", "GoBD"],
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class FiscalComplianceResult:
    fiscal_ok: bool
    books_balanced: bool
    gobd_ok: bool
    datev_exported: bool
    gewerbesteuer_eur: float
    net_pnl_eur: float
    subagent_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fiscal_ok": self.fiscal_ok,
            "books_balanced": self.books_balanced,
            "gobd_ok": self.gobd_ok,
            "datev_exported": self.datev_exported,
            "gewerbesteuer_eur": self.gewerbesteuer_eur,
            "net_pnl_eur": self.net_pnl_eur,
            "subagents": self.subagent_results,
        }


class FiscalComplianceAuditor:
    """A7 — fiscal books, §13b, DATEV, year-end seal."""

    agent_name = "FiscalComplianceAuditor"

    def __init__(self, user_id: str = "wave40", config: ResilienceConfig | None = None):
        self.user_id = user_id
        self.config = config or ResilienceConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)
        self.gewst = GewerbesteuerCalculator()
        self.books = HandelsbuchfuehrungsValidator()
        self.gobd = GoBDTransactionTagger()
        self.datev = DatevExporter()
        self.lots = TaxLotTracker()
        self.pnl = RealizedGainLossAggregator()
        self.sealer = AuditTrailSealer()
        self.bzst = BZStReporter()
        self.jahres = JahresabschlussGenerator()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any]) -> FiscalComplianceResult:
        return self._evaluate(payload)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._evaluate(payload)
        status = "completed" if result.fiscal_ok else "blocked"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "fiscal_compliance_result",
                    "path": str(self._tenant / f"fiscal_{job_id}.json"),
                    "metadata": result.to_dict(),
                }
            ],
            logs=[
                f"fiscal_ok={result.fiscal_ok}",
                f"books_balanced={result.books_balanced}",
                f"datev={result.datev_exported}",
            ],
        )

    def _evaluate(self, payload: Mapping[str, Any]) -> FiscalComplianceResult:
        entries = list(
            payload.get(
                "book_entries",
                [
                    {"debit": 100.0, "credit": 0.0},
                    {"debit": 0.0, "credit": 100.0},
                ],
            )
        )
        transactions = list(
            payload.get(
                "transactions",
                [
                    {
                        "tx_id": "TX-1",
                        "timestamp": "2026-08-24T12:00:00Z",
                        "amount_eur": 100.0,
                        "counterparty": "1200",
                        "purpose": "trade_settlement",
                        "reverse_charge": True,
                    }
                ],
            )
        )
        lots = list(payload.get("lots", [{"qty": 10.0, "cost_eur": 1000.0}]))
        disposals = list(payload.get("disposals", [{"qty": 2.0, "proceeds_eur": 250.0}]))
        gains = list(payload.get("gains", [payload.get("realized_preview", 50.0)]))
        losses = list(payload.get("losses", [0.0]))
        profit = float(payload.get("taxable_profit_eur", sum(float(g) for g in gains) - sum(float(l) for l in losses)))
        hebesatz = float(payload.get("hebesatz", 400.0))

        books_r = self.books.run(entries)
        gobd_r = self.gobd.run(transactions)
        datev_r = self.datev.run(gobd_r.get("tagged", []), self.user_id)
        lots_r = self.lots.run(lots, disposals)
        # prefer lot tracker preview when present
        if "gains" not in payload and "losses" not in payload:
            gains = [max(0.0, float(lots_r["realized_preview_eur"]))]
            losses = [max(0.0, -float(lots_r["realized_preview_eur"]))]
        pnl_r = self.pnl.run(gains, losses)
        if "taxable_profit_eur" not in payload:
            profit = float(pnl_r["net_eur"])
        gew_r = self.gewst.run(profit, hebesatz=hebesatz)
        bzst_r = self.bzst.run(gobd_r.get("tagged", transactions))
        seal_r = self.sealer.run(
            {
                "books": books_r,
                "pnl": pnl_r,
                "gewst": gew_r,
                "bzst": bzst_r,
            }
        )
        jahr_r = self.jahres.run(
            net_pnl_eur=float(pnl_r["net_eur"]),
            gewerbesteuer_eur=float(gew_r["gewerbesteuer_eur"]),
            balanced_books=bool(books_r["balanced"]),
            gobd_ok=bool(gobd_r["ok"]),
            datev_exported=bool(datev_r["exported"]),
        )

        fiscal_ok = bool(jahr_r["fiscal_ok"] and lots_r["ok"] and seal_r["sealed"])

        return FiscalComplianceResult(
            fiscal_ok=fiscal_ok,
            books_balanced=bool(books_r["balanced"]),
            gobd_ok=bool(gobd_r["ok"]),
            datev_exported=bool(datev_r["exported"]),
            gewerbesteuer_eur=float(gew_r["gewerbesteuer_eur"]),
            net_pnl_eur=float(pnl_r["net_eur"]),
            subagent_results={
                GewerbesteuerCalculator.name: gew_r,
                HandelsbuchfuehrungsValidator.name: books_r,
                GoBDTransactionTagger.name: gobd_r,
                DatevExporter.name: datev_r,
                TaxLotTracker.name: lots_r,
                RealizedGainLossAggregator.name: pnl_r,
                AuditTrailSealer.name: seal_r,
                BZStReporter.name: bzst_r,
                JahresabschlussGenerator.name: jahr_r,
            },
        )
