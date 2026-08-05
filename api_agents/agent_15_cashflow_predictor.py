"""
Agent X — API Agent 15: CashflowPredictor (Zahlungsausfall-Prognose).

Kaplan-Meier-Survival-Analyse für Zahlungseingänge.
Gruppiert nach Kundentyp (Privat, Gewerbe, Öffentliche Hand).

Warum das der stille Killer ist:
  80% aller Handwerks-Insolvenzen entstehen durch schleppende Zahlungseingänge,
  nicht durch zu wenig Aufträge. Der Handwerker zahlt Material + Löhne SOFORT,
  aber der Bauherr zahlt nach 30-90 Tagen.

Sub-Agenten:
  15a: SurvivalAnalyzer — Kaplan-Meier-Schätzer
  15b: CashflowForecaster — Bedingte Wahrscheinlichkeit für offene Rechnung
  15c: ActionRecommender — Skonto/Mahnung/Liquiditätswarnung

Usage:
  predictor = CashflowPredictor()
  forecast = predictor.predict("sess_001")
  # → {"expected_payment_day": 68, "probability_next_30d": 0.78, ...}
"""

import json
import logging
import math
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CashflowPredictor")

DB_PATH = os.getenv("ERP_DB_PATH", "data/handover_proofs.db")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Kaplan-Meier Survival Analysis ──────────────────────────────────

class SurvivalAnalyzer:
    """Kaplan-Meier-Schätzer für Zahlungseingänge.

    Berechnet die Überlebensfunktion S(t) = P(Zahlung > t Tage).
    Daraus: bedingte Wahrscheinlichkeit, Median, Perzentile.

    Formel (Kaplan-Meier):
      S(t) = ∏_{i: t_i ≤ t} (1 − d_i / n_i)
      wobei d_i = Anzahl Zahlungen am Tag t_i
            n_i = Anzahl ausstehender Rechnungen vor Tag t_i
    """

    def __init__(self):
        self._survival_curves: dict[str, list[tuple[int, float]]] = {}
        self._median_times: dict[str, float] = {}
        self._samples: dict[str, int] = {}

    def fit(self, customer_type: str, payment_histories: list[int]):
        """Trainiert Kaplan-Meier für einen Kundentyp.

        Args:
            customer_type: "private", "commercial", "public"
            payment_histories: Liste von days_to_payment (Tage bis Zahlung)
        """
        if not payment_histories:
            self._survival_curves[customer_type] = [(0, 1.0)]
            self._median_times[customer_type] = 30.0
            self._samples[customer_type] = 0
            return

        # Sortiere nach Tagen
        sorted_days = sorted(payment_histories)
        n = len(sorted_days)
        self._samples[customer_type] = n

        # Kaplan-Meier: Ereigniszeitpunkte
        unique_times = sorted(set(sorted_days))
        curve = [(0, 1.0)]  # S(0) = 1.0
        at_risk = n

        for t in unique_times:
            events = sum(1 for d in sorted_days if d == t)  # d_i
            if at_risk > 0:
                survival = curve[-1][1] * (1 - events / at_risk)
                curve.append((t, round(survival, 6)))
            at_risk -= events

        self._survival_curves[customer_type] = curve
        # Median: erstes t wo S(t) ≤ 0.5
        median = next((t for t, s in curve if s <= 0.5), sorted_days[-1] if sorted_days else 30)
        self._median_times[customer_type] = float(median)

    def survival_probability(self, customer_type: str, days: int) -> float:
        """S(days) = Wahrscheinlichkeit dass Zahlung > days Tage dauert."""
        curve = self._survival_curves.get(customer_type, [(0, 1.0)])
        for t, s in reversed(curve):
            if days >= t:
                return s
        return 1.0

    def conditional_probability(self, customer_type: str, days_issued: int,
                                 within_days: int) -> float:
        """Bedingte Wahrscheinlichkeit: P(Zahlung ≤ days_issued+within_days | heute ist Tag days_issued).

        P = 1 − S(days_issued + within_days) / S(days_issued)
        """
        s_now = self.survival_probability(customer_type, days_issued)
        s_future = self.survival_probability(customer_type, days_issued + within_days)

        if s_now > 0:
            return round(1 - s_future / s_now, 4)
        return 0.0

    def median_time(self, customer_type: str) -> float:
        """Median der Zahlungsdauer."""
        return self._median_times.get(customer_type, 30.0)

    def percentile(self, customer_type: str, pct: float) -> int:
        """pct%-Perzentil der Zahlungsdauer."""
        curve = self._survival_curves.get(customer_type, [(0, 1.0)])
        target = 1 - pct / 100
        for t, s in curve:
            if s <= target:
                return t
        return 90

    @property
    def stats(self) -> dict:
        return {
            "curves": {k: len(v) for k, v in self._survival_curves.items()},
            "medians": self._median_times,
            "samples": self._samples,
        }


# ─── Sub-Agent 15b: CashflowForecaster ───────────────────────────────

class CashflowForecaster:
    """Berechnet Prognose für eine einzelne offene Rechnung."""

    def __init__(self, analyzer: SurvivalAnalyzer):
        self.analyzer = analyzer

    def predict(self, customer_type: str, days_since_issued: int,
                invoice_amount_eur: float) -> dict:
        """Prognostiziert Zahlungseingang für eine Rechnung.

        Args:
            customer_type: "private", "commercial", "public"
            days_since_issued: Tage seit Rechnungsstellung
            invoice_amount_eur: Rechnungsbetrag in EUR

        Returns:
            {"expected_payment_day": 68, "probability_next_30d": 0.78, ...}
        """
        # Bedingte Wahrscheinlichkeiten
        prob_7d = self.analyzer.conditional_probability(customer_type, days_since_issued, 7)
        prob_30d = self.analyzer.conditional_probability(customer_type, days_since_issued, 30)
        prob_60d = self.analyzer.conditional_probability(customer_type, days_since_issued, 60)

        # Erwarteter Zahlungstag (Median, adjustiert für bereits vergangene Tage)
        median = self.analyzer.median_time(customer_type)
        expected_day = max(days_since_issued, int(median))

        # P90 (90%-Perzentil — Worst Case)
        p90_day = self.analyzer.percentile(customer_type, 90)

        # Liquiditätsstress (Opportunitätskosten durch Dispozins)
        daily_rate = 0.0002  # ~7.3% p.a.
        remaining_days = max(0, expected_day - days_since_issued)
        opportunity_cost = invoice_amount_eur * (1 - math.exp(-daily_rate * remaining_days))

        # Ausfallrisiko (über 90 Tage)
        prob_default = 1 - self.analyzer.survival_probability(customer_type, 90)
        prob_default_conditional = (
            1 - self.analyzer.survival_probability(customer_type, 90) /
            max(0.001, self.analyzer.survival_probability(customer_type, days_since_issued))
        )

        return {
            "invoice_days_outstanding": days_since_issued,
            "customer_type": customer_type,
            "invoice_amount_eur": invoice_amount_eur,
            "expected_payment_day": expected_day,
            "days_until_expected_payment": max(0, expected_day - days_since_issued),
            "probability_payment_next_7d": round(prob_7d * 100, 1),
            "probability_payment_next_30d": round(prob_30d * 100, 1),
            "probability_payment_next_60d": round(prob_60d * 100, 1),
            "p90_payment_day": p90_day,
            "default_risk_90d_pct": round(prob_default_conditional * 100, 1),
            "opportunity_cost_eur": round(opportunity_cost, 2),
            "median_for_type": int(median),
            "samples_for_type": self.analyzer._samples.get(customer_type, 0),
        }


# ─── Sub-Agent 15c: ActionRecommender ────────────────────────────────

class ActionRecommender:
    """Generiert konkrete Handlungsempfehlungen aus der Prognose."""

    @staticmethod
    def recommend(forecast: dict) -> dict:
        prob_30d = forecast["probability_payment_next_30d"]
        days = forecast["invoice_days_outstanding"]
        amount = forecast["invoice_amount_eur"]
        expected = forecast["days_until_expected_payment"]

        if prob_30d < 30:
            action = "MAHNUNG_SENDEN"
            priority = "HIGH"
            message = (
                f"🚨 Zahlungsausfall-Risiko {forecast['default_risk_90d_pct']:.0f}%. "
                f"Rechnung über {amount:,.0f} EUR ist seit {days} Tagen offen. "
                f"Jetzt Mahnung mit Fristsetzung (7 Tage) senden."
            )
        elif prob_30d < 60:
            action = "SKONTO_ANBIETEN"
            priority = "MEDIUM"
            discount = round(amount * 0.02, 2)
            message = (
                f"⚠️ Verzugsrisiko erhöht ({prob_30d:.0f}% in 30 Tagen). "
                f"Skonto-Angebot: 2% ({discount:,.0f} EUR) bei Zahlung innerhalb 7 Tage. "
                f"Ersparnis gegenüber Dispo: {forecast['opportunity_cost_eur']:,.0f} EUR."
            )
        elif prob_30d < 80:
            action = "ERINNERUNG_SENDEN"
            priority = "LOW"
            message = (
                f"📋 Zahlung in {expected} Tagen erwartet. "
                f"Freundliche Zahlungserinnerung mit Verweis auf Blockchain-Beleg."
            )
        else:
            action = "MONITOR"
            priority = "INFO"
            message = (
                f"✅ Zahlungseingang wahrscheinlich ({prob_30d:.0f}% in 30 Tagen). "
                f"Keine Aktion erforderlich."
            )

        return {
            "action": action,
            "priority": priority,
            "message": message,
            "suggested_discount_eur": round(amount * 0.02, 2) if action == "SKONTO_ANBIETEN" else 0,
        }


# ─── Agent 15: CashflowPredictor ─────────────────────────────────────

class CashflowPredictor:
    """Haupt-Agent: Zahlungsausfall-Prognose + Handlungsempfehlung.

    Usage:
        predictor = CashflowPredictor()
        predictor.train_from_db()
        forecast = predictor.predict("sess_001")
        # → erwarteter Zahlungstag, Wahrscheinlichkeiten, Empfehlung
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.analyzer = SurvivalAnalyzer()
        self.forecaster = CashflowForecaster(self.analyzer)
        self.recommender = ActionRecommender()

    def train_from_db(self):
        """Trainiert das Modell mit historischen Zahlungsdaten aus der DB."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            # Hole alle abgeschlossenen Zahlungen mit days_to_payment
            rows = conn.execute(
                """SELECT customer_type, days_to_payment
                   FROM handover_proofs
                   WHERE payment_date IS NOT NULL AND days_to_payment IS NOT NULL
                   AND days_to_payment > 0 AND days_to_payment < 365"""
            ).fetchall()
            conn.close()

            if not rows:
                # Demo-Daten: typische Zahlungsdauern im Bauhandwerk
                logger.info("Keine DB-Daten — trainiere mit Demo-Daten")
                self._train_demo()
                return

            by_type: dict[str, list[int]] = defaultdict(list)
            for row in rows:
                ct = row["customer_type"] or "commercial"
                by_type[ct].append(row["days_to_payment"])

            for ct, histories in by_type.items():
                self.analyzer.fit(ct, histories)

            logger.info("Modell trainiert: %s", self.analyzer.stats)
        except Exception as e:
            logger.warning("DB-Training fehlgeschlagen: %s — Demo-Daten", e)
            self._train_demo()

    def _train_demo(self):
        """Trainiert mit realistischen Demo-Daten aus dem Bauhandwerk."""
        # Private Kunden (Einfamilienhaus): zahlen meist schnell
        self.analyzer.fit("private", [
            5, 7, 8, 10, 12, 14, 14, 15, 18, 20, 21, 22, 25, 28, 30,
            7, 9, 11, 13, 15, 16, 19, 21, 24, 26, 28, 30, 32, 35, 40,
        ])
        # Gewerbliche Kunden: zahlen langsamer, mehr Streuung
        self.analyzer.fit("commercial", [
            14, 21, 28, 30, 30, 35, 38, 40, 42, 45, 45, 48, 50,
            52, 55, 60, 60, 62, 65, 68, 70, 75, 78, 80, 85, 90,
            20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80,
        ])
        # Öffentliche Hand: zahlt am langsamsten (30-90 Tage)
        self.analyzer.fit("public", [
            30, 35, 40, 42, 45, 48, 50, 52, 55, 58, 60, 62, 65,
            68, 70, 72, 75, 78, 80, 82, 85, 88, 90, 95, 100,
        ])

    def predict(self, session_id: str) -> dict:
        """Prognostiziert Zahlung für eine bestimmte Rechnung (per session_id).

        Holt Rechnungsdaten aus DB, berechnet Prognose + Empfehlung.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM handover_proofs WHERE session_id = ?", (session_id,)
            ).fetchone()
            conn.close()

            if not row:
                raise ValueError(f"Session {session_id} nicht gefunden")
            doc = dict(row)
        except Exception as e:
            raise ValueError(f"DB-Fehler: {e}")

        # Tage seit Rechnungsstellung
        created = doc.get("created_at", _now_iso())
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - created_dt).days
        except Exception:
            days_since = 22  # Default

        customer_type = doc.get("customer_type", "commercial")
        amount = float(doc.get("amount_eur", 0))

        forecast = self.forecaster.predict(customer_type, days_since, amount)
        recommendation = self.recommender.recommend(forecast)

        return {
            "session_id": session_id,
            "forecast": forecast,
            "recommendation": recommendation,
            "model_stats": self.analyzer.stats,
            "generated_at": _now_iso(),
        }

    def predict_raw(self, customer_type: str, days_since_issued: int,
                    invoice_amount_eur: float) -> dict:
        """Direkte Prognose ohne DB-Lookup."""
        forecast = self.forecaster.predict(customer_type, days_since_issued, invoice_amount_eur)
        recommendation = self.recommender.recommend(forecast)
        return {"forecast": forecast, "recommendation": recommendation}

    def dashboard(self, open_invoices: list[dict]) -> dict:
        """Erstellt ein Liquiditäts-Dashboard für alle offenen Rechnungen."""
        results = []
        total_outstanding = 0.0
        high_risk = 0
        expected_30d = 0.0

        for inv in open_invoices:
            ct = inv.get("customer_type", "commercial")
            days = inv.get("days_since_issued", 0)
            amount = float(inv.get("amount_eur", 0))
            forecast = self.forecaster.predict(ct, days, amount)

            total_outstanding += amount
            if forecast["default_risk_90d_pct"] > 30:
                high_risk += 1
            if forecast["probability_payment_next_30d"] > 50:
                expected_30d += amount * (forecast["probability_payment_next_30d"] / 100)

            results.append({
                "session_id": inv.get("session_id", ""),
                "amount_eur": amount,
                "days_outstanding": days,
                "expected_in_days": forecast["days_until_expected_payment"],
                "risk_30d_pct": forecast["probability_payment_next_30d"],
                "action": self.recommender.recommend(forecast)["action"],
            })

        results.sort(key=lambda r: r["days_outstanding"], reverse=True)

        return {
            "total_outstanding_eur": round(total_outstanding, 2),
            "expected_30d_eur": round(expected_30d, 2),
            "high_risk_count": high_risk,
            "invoice_count": len(open_invoices),
            "invoices": results,
            "generated_at": _now_iso(),
        }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    predictor = CashflowPredictor()
    predictor.train_from_db()

    print("=== Cashflow Predictor Demo ===\n")

    # Test-Szenarien: Rechnung vor 22 Tagen gestellt
    for ct in ["private", "commercial", "public"]:
        result = predictor.predict_raw(ct, days_since_issued=22, invoice_amount_eur=18_400)
        f = result["forecast"]
        r = result["recommendation"]
        print(f"{ct:12s}: erwartet in {f['days_until_expected_payment']:3d}d, "
              f"P(30d)={f['probability_payment_next_30d']:5.1f}%, "
              f"Default-Risiko={f['default_risk_90d_pct']:5.1f}%, "
              f"Dispo-Kosten={f['opportunity_cost_eur']:6.1f} EUR")
        print(f"             → {r['action']}: {r['message'][:100]}...")
        print()

    # Dashboard
    dashboard = predictor.dashboard([
        {"session_id": "inv_001", "customer_type": "commercial",
         "days_since_issued": 45, "amount_eur": 28_500},
        {"session_id": "inv_002", "customer_type": "public",
         "days_since_issued": 72, "amount_eur": 52_000},
        {"session_id": "inv_003", "customer_type": "private",
         "days_since_issued": 8, "amount_eur": 3_200},
        {"session_id": "inv_004", "customer_type": "commercial",
         "days_since_issued": 85, "amount_eur": 18_400},
    ])
    print("=== Dashboard ===")
    print(f"Ausstehend: {dashboard['total_outstanding_eur']:,.0f} EUR "
          f"({dashboard['invoice_count']} Rechnungen)")
    print(f"Erwartet in 30d: {dashboard['expected_30d_eur']:,.0f} EUR")
    print(f"Hochrisiko (>30% Default): {dashboard['high_risk_count']}")
    for inv in dashboard["invoices"]:
        print(f"  {inv['session_id']}: {inv['amount_eur']:>8,.0f} EUR, "
              f"{inv['days_outstanding']:>3d}d offen, "
              f"Zahlung in {inv['expected_in_days']:>3d}d, "
              f"P(30d)={inv['risk_30d_pct']:.0f}%, "
              f"Aktion={inv['action']}")
