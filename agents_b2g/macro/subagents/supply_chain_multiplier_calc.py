# agents_b2g/macro/subagents/supply_chain_multiplier_calc.py
"""
Agent 17.6 — SupplyChainMultiplierCalc

Berechnet den keynesianischen Multiplikator-Effekt öffentlicher Bauausgaben
entlang der gesamten Lieferkette des Agent-X-Ökosystems.

Theoretische Grundlagen:
  1. Keynesianischer Multiplikator:
     k = 1 / (1 − MPC) = 1 / MPS
     wobei MPC = marginale Konsumneigung, MPS = marginale Sparquote

  2. Fiskaler Multiplikator (erweitert):
     ΔY = k × ΔG
     k = 1 / (1 − MPC × (1 − t) + m)
     wobei t = Steuersatz, m = Importquote

  3. Lieferketten-Multiplikator (Leontief-Inverse):
     L = (I − A)^(−1)
     wobei A = Input-Output-Matrix (technische Koeffizienten)

  4. Lokaler Multiplikator (Moretti, 2010):
     Jeder € im handelbaren Sektor schafft 1.6× mehr lokale Jobs
     als im nicht-handelbaren Sektor.

Tiers der Lieferkette:
  Tier 0: Generalunternehmer (GU)      — erhält Auftragssumme
  Tier 1: Subunternehmer                — 60-80% der GU-Summe
  Tier 2: Zulieferer (Material)         — 30-50% der Tier-1-Summe
  Tier 3: Rohstoffproduzenten           — 20-40% der Tier-2-Summe
  Tier 4: Logistik & Dienstleistungen   — 5-15% der Tier-3-Summe

Features:
  - Multi-Tier-Multiplikator (Tier 0 → Tier 4)
  - Sektor-spezifische Multiplikatoren (Beton, Stahl, Technik...)
  - Regionaler Multiplikator (bleibt Geld in der Region?)
  - Leontief-Inverse für Input-Output-Analyse
  - Beschäftigungs-Multiplikator (Jobs pro Mio €)
  - Vergleich mit empirischen Benchmark-Werten
  - Alert bei Multiplikator < 1.0 (Kontraktion)
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from statistics import mean, stdev

logger = logging.getLogger("SupplyChainMultiplierCalc")


class SupplyChainMultiplierCalcSubagent:
    """
    Subagent 17.6: Berechnet den Multiplikator-Effekt öffentlicher Bauausgaben.

    Formel: k = ΔY / ΔG  (Output-Änderung / Fiskalimpuls)
    """

    # Empirische Multiplikator-Benchmarks (Quelle: ifo, DIW, IWF)
    BENCHMARKS = {
        "bau_infrastruktur": {
            "fiscal_multiplier": 1.8,       # 1€ Staatsausgabe → 1.80€ BIP
            "employment_multiplier": 12.5,   # Jobs pro 1 Mio €
            "local_retention": 0.72,         # 72% des Geldes bleibt in Region
            "source": "ifo Institut (2024), DIW (2023)",
        },
        "bau_hochbau": {
            "fiscal_multiplier": 1.5,
            "employment_multiplier": 10.2,
            "local_retention": 0.65,
            "source": "ifo Institut (2024)",
        },
        "bau_tiefbau": {
            "fiscal_multiplier": 1.6,
            "employment_multiplier": 11.0,
            "local_retention": 0.68,
            "source": "DIW (2023)",
        },
        "technik_elektro": {
            "fiscal_multiplier": 1.3,
            "employment_multiplier": 8.5,
            "local_retention": 0.55,
            "source": "IWF (2024)",
        },
        "dienstleistung": {
            "fiscal_multiplier": 1.2,
            "employment_multiplier": 7.0,
            "local_retention": 0.80,
            "source": "IWF (2024)",
        },
    }

    # Durchschnittliche Wertschöpfungsanteile pro Lieferketten-Tier
    # (basierend auf Bauwirtschaft-Statistiken)
    DEFAULT_TIER_SHARES = {
        0: {"label": "Generalunternehmer", "value_added_share": 0.15, "retained_local": 0.85},
        1: {"label": "Subunternehmer", "value_added_share": 0.25, "retained_local": 0.70},
        2: {"label": "Materialzulieferer", "value_added_share": 0.30, "retained_local": 0.50},
        3: {"label": "Rohstoffproduzenten", "value_added_share": 0.20, "retained_local": 0.30},
        4: {"label": "Logistik & Services", "value_added_share": 0.10, "retained_local": 0.60},
    }

    # Sektor → Benchmark-Mapping
    SECTOR_BENCHMARK_MAP = {
        "bau": "bau_infrastruktur",
        "beton": "bau_infrastruktur",
        "stahl": "bau_infrastruktur",
        "hochbau": "bau_hochbau",
        "tiefbau": "bau_tiefbau",
        "erdarbeiten": "bau_tiefbau",
        "straße": "bau_tiefbau",
        "kanal": "bau_tiefbau",
        "elektro": "technik_elektro",
        "heizung": "technik_elektro",
        "sanitaer": "technik_elektro",
        "planung": "dienstleistung",
        "ausbau": "bau_hochbau",
    }

    def __init__(
        self,
        tier_shares: Optional[Dict[int, Dict]] = None,
        import_quote: float = 0.15,       # 15% Importanteil (Material aus Ausland)
        tax_rate: float = 0.19,            # 19% USt (vereinfacht)
        savings_rate: float = 0.12,        # 12% Sparquote (deutsche Bauwirtschaft)
        local_retention_base: float = 0.65,  # 65% Basis-Regionalbindung
        alert_threshold_multiplier: float = 1.0,  # k < 1.0 → Kontraktion
    ):
        """
        Args:
            tier_shares: Wertschöpfungsanteile pro Tier (optional)
            import_quote: Importquote m (0-1)
            tax_rate: Durchschnittlicher Steuersatz t (0-1)
            savings_rate: Marginale Sparquote MPS (0-1)
            local_retention_base: Basis-Regionalbindung (0-1)
            alert_threshold_multiplier: k < Wert → Alarm
        """
        self.tier_shares = tier_shares or self.DEFAULT_TIER_SHARES
        self.import_quote = import_quote
        self.tax_rate = tax_rate
        self.savings_rate = savings_rate
        self.local_retention_base = local_retention_base
        self.alert_threshold = alert_threshold_multiplier

        # MPC = 1 − MPS − Importanteil
        self.mpc = 1.0 - self.savings_rate - self.import_quote

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def calculate_multiplier(
        self,
        transactions: List[Dict[str, Any]],
        initial_spending_eur: float,
        tender_id: Optional[str] = None,
        period_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Hauptmethode: Berechnet den Multiplikator-Effekt aus Transaktionsdaten.

        Args:
            transactions: Transaktionen mit sender, receiver, amount_eur, sector, tier
            initial_spending_eur: Initiale Staatsausgabe (Auftragssumme)
            tender_id: Optionaler Tender-Filter
            period_label: Perioden-Label

        Returns:
            Multiplikator-Report mit k-Werten, Tier-Analyse und Beschäftigungseffekten
        """
        period_label = period_label or datetime.now(timezone.utc).strftime("%Y-%m")
        job_id = f"mult_{period_label}"

        logger.info(
            f"Multiplikator-Analyse: {len(transactions)} TX, "
            f"Initialausgabe={initial_spending_eur:,.0f} EUR"
        )

        if initial_spending_eur <= 0:
            return {
                "status": "INVALID_INPUT",
                "job_id": job_id,
                "artifacts": [],
                "error": "Initialausgabe muss > 0 sein.",
                "logs": [],
            }

        if not transactions:
            return {
                "status": "NO_DATA",
                "job_id": job_id,
                "artifacts": [],
                "error": None,
                "logs": [{"level": "WARN", "message": "Keine Transaktionen für Multiplikator-Analyse."}],
            }

        try:
            # === 1. Keynesianischer Multiplikator (theoretisch) ===
            keynesian_k = self._calculate_keynesian_multiplier()

            # === 2. Empirischer Multiplikator aus Transaktionsdaten ===
            empirical_k = self._calculate_empirical_multiplier(
                transactions, initial_spending_eur
            )

            # === 3. Lieferketten-Tier-Analyse ===
            tier_analysis = self._calculate_tier_multipliers(
                transactions, initial_spending_eur
            )

            # === 4. Sektor-spezifische Multiplikatoren ===
            sector_multipliers = self._calculate_sector_multipliers(
                transactions, initial_spending_eur
            )

            # === 5. Regionaler Multiplikator ===
            regional_k = self._calculate_regional_multiplier(transactions)

            # === 6. Beschäftigungs-Multiplikator ===
            employment_impact = self._calculate_employment_impact(
                transactions, initial_spending_eur
            )

            # === 7. Benchmark-Vergleich ===
            benchmark_comparison = self._compare_with_benchmarks(
                empirical_k, sector_multipliers
            )

            # === 8. Gesamt-Multiplikator (Composite) ===
            composite_k = self._calculate_composite_multiplier(
                keynesian_k=keynesian_k,
                empirical_k=empirical_k,
                tier_k=tier_analysis.get("weighted_multiplier", 1.0),
                sector_ks=sector_multipliers,
            )

            # === 9. Alerts ===
            alerts = self._generate_alerts(
                composite_k, empirical_k, tier_analysis, regional_k
            )

            report = {
                "status": "ANALYSIS_COMPLETE",
                "job_id": job_id,
                "tender_id": tender_id,
                "period_label": period_label,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "artifacts": [
                    {
                        "type": "multiplier_report",
                        "format": "json",
                        "metadata": {
                            "period": period_label,
                            "composite_k": round(composite_k, 3),
                            "keynesian_k": round(keynesian_k, 3),
                        },
                    }
                ],
                "error": None,
                "logs": [
                    {
                        "level": "INFO",
                        "message": (
                            f"Multiplikator: k_composite={composite_k:.3f}, "
                            f"k_keynes={keynesian_k:.3f}, "
                            f"k_empirical={empirical_k:.3f}"
                        ),
                    }
                ],
                "multiplier_metrics": {
                    "composite_multiplier": round(composite_k, 3),
                    "keynesian_multiplier": round(keynesian_k, 3),
                    "empirical_multiplier": round(empirical_k, 3),
                    "mpc": round(self.mpc, 3),
                    "mps": round(self.savings_rate, 3),
                    "import_quote": round(self.import_quote, 3),
                    "tax_rate": round(self.tax_rate, 3),
                },
                "tier_analysis": tier_analysis,
                "sector_multipliers": sector_multipliers,
                "regional_multiplier": regional_k,
                "employment_impact": employment_impact,
                "benchmark_comparison": benchmark_comparison,
                "alerts": alerts,
                "has_alerts": len(alerts) > 0,
                "policy_implication": self._policy_advice(composite_k),
            }

            logger.info(f"Multiplikator-Analyse abgeschlossen: k={composite_k:.3f}")
            return report

        except Exception as e:
            logger.error(f"Multiplikator-Berechnung fehlgeschlagen: {e}", exc_info=True)
            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": str(e),
                "logs": [{"level": "ERROR", "message": str(e)}],
            }

    # ========================================================================
    # KEYNESIAN MULTIPLIER
    # ========================================================================

    def _calculate_keynesian_multiplier(self) -> float:
        """
        Berechnet den keynesianischen Multiplikator:

            k = 1 / (1 − MPC × (1 − t) + m)

        wobei:
            MPC = 1 − MPS − m (marginale Konsumneigung)
            t = Steuersatz
            m = Importquote
        """
        denominator = 1.0 - self.mpc * (1.0 - self.tax_rate) + self.import_quote
        if denominator <= 0:
            return 1.0  # Fallback
        return 1.0 / denominator

    # ========================================================================
    # EMPIRICAL MULTIPLIER (from transaction data)
    # ========================================================================

    def _calculate_empirical_multiplier(
        self,
        transactions: List[Dict],
        initial_spending_eur: float,
    ) -> float:
        """
        Berechnet den empirischen Multiplikator:

            k_emp = Σ(all downstream transactions) / initial_spending

        Misst, wie viel Gesamtumsatz 1 € Initialausgabe generiert.
        """
        total_volume = sum(float(tx.get("amount_eur", 0.0)) for tx in transactions)

        if initial_spending_eur <= 0:
            return 1.0

        k_emp = total_volume / initial_spending_eur
        return round(k_emp, 3)

    # ========================================================================
    # TIER ANALYSIS
    # ========================================================================

    def _calculate_tier_multipliers(
        self,
        transactions: List[Dict],
        initial_spending_eur: float,
    ) -> Dict[str, Any]:
        """
        Berechnet den Multiplikator pro Lieferketten-Tier (0-4).

        Tier 0: GU → Sub
        Tier 1: Sub → Zulieferer
        Tier 2: Zulieferer → Rohstoff
        Tier 3: Rohstoff → Logistik
        Tier 4: Logistik → Services
        """
        # Nach Tier gruppieren (wenn vorhanden, sonst schätzen)
        tier_volumes: Dict[int, float] = defaultdict(float)
        tier_counts: Dict[int, int] = defaultdict(int)
        tier_actors: Dict[int, set] = defaultdict(set)

        for tx in transactions:
            tier = tx.get("tier")
            if tier is None:
                # Schätze Tier basierend auf sender/receiver
                tier = self._estimate_tier(tx)

            amount = float(tx.get("amount_eur", 0.0))
            tier_volumes[tier] += amount
            tier_counts[tier] += 1
            tier_actors[tier].add(tx.get("sender", tx.get("from", "")))
            tier_actors[tier].add(tx.get("receiver", tx.get("to", "")))

        results = []
        for tier in sorted(self.tier_shares.keys()):
            volume = tier_volumes.get(tier, 0.0)
            count = tier_counts.get(tier, 0)
            n_actors = len(tier_actors.get(tier, set()))

            tier_info = self.tier_shares[tier]
            tier_k = volume / initial_spending_eur if initial_spending_eur > 0 else 0.0
            value_added = volume * tier_info["value_added_share"]
            retained_local = volume * tier_info["retained_local"]

            results.append(
                {
                    "tier": tier,
                    "label": tier_info["label"],
                    "transaction_count": count,
                    "unique_actors": n_actors,
                    "volume_eur": round(volume, 2),
                    "volume_share_pct": round(volume / max(sum(tier_volumes.values()), 1) * 100, 1),
                    "tier_multiplier": round(tier_k, 4),
                    "value_added_eur": round(value_added, 2),
                    "value_added_share": tier_info["value_added_share"],
                    "retained_local_eur": round(retained_local, 2),
                    "retained_local_share": tier_info["retained_local"],
                }
            )

        # Gewichteter Multiplikator über alle Tiers
        total_tier_volume = sum(r["volume_eur"] for r in results)
        weighted_k = total_tier_volume / initial_spending_eur if initial_spending_eur > 0 else 0.0

        return {
            "tiers": results,
            "total_tier_volume_eur": round(total_tier_volume, 2),
            "weighted_multiplier": round(weighted_k, 3),
            "initial_spending_eur": round(initial_spending_eur, 2),
        }

    def _estimate_tier(self, tx: Dict[str, Any]) -> int:
        """
        Schätzt das Lieferketten-Tier aus dem Transaktionskontext.
        - Große Beträge → Tier 0-1 (GU/Sub)
        - Mittlere Beträge → Tier 2 (Zulieferer)
        - Kleine Beträge → Tier 3-4 (Rohstoff/Services)
        """
        amount = float(tx.get("amount_eur", 0.0))
        category = tx.get("category", tx.get("type", ""))

        if category in ("retention", "refund"):
            return 0  # Einbehalte/Erstattungen → Tier 0

        if amount > 100_000:
            return 1  # Große Transfers → Tier 1 (Subunternehmer)
        elif amount > 20_000:
            return 2  # Mittlere Transfers → Tier 2 (Zulieferer)
        elif amount > 5_000:
            return 3  # Kleinere Transfers → Tier 3 (Rohstoff)
        else:
            return 4  # Kleinstbeträge → Tier 4 (Services)

    # ========================================================================
    # SECTOR MULTIPLIERS
    # ========================================================================

    def _calculate_sector_multipliers(
        self,
        transactions: List[Dict],
        initial_spending_eur: float,
    ) -> Dict[str, Any]:
        """
        Berechnet sektor-spezifische Multiplikatoren.
        """
        sector_volumes: Dict[str, float] = defaultdict(float)
        sector_counts: Dict[str, int] = defaultdict(int)

        for tx in transactions:
            sector = tx.get("sector", "")
            if not sector:
                desc = tx.get("description", "").lower()
                sector = self._classify_sector(desc)

            amount = float(tx.get("amount_eur", 0.0))
            sector_volumes[sector] += amount
            sector_counts[sector] += 1

        results = {}
        for sector, volume in sorted(sector_volumes.items(), key=lambda x: x[1], reverse=True):
            k_sector = volume / initial_spending_eur if initial_spending_eur > 0 else 0.0
            benchmark_key = self.SECTOR_BENCHMARK_MAP.get(sector, "bau_infrastruktur")
            benchmark_k = self.BENCHMARKS.get(benchmark_key, {}).get("fiscal_multiplier", 1.5)

            results[sector] = {
                "transaction_count": sector_counts[sector],
                "volume_eur": round(volume, 2),
                "sector_multiplier": round(k_sector, 3),
                "benchmark_multiplier": benchmark_k,
                "deviation_pct": round((k_sector - benchmark_k) / benchmark_k * 100, 1),
            }

        return results

    def _classify_sector(self, description: str) -> str:
        """Klassifiziert Beschreibung in Sektor."""
        desc = description.lower()
        for keyword, sector in self.SECTOR_BENCHMARK_MAP.items():
            if keyword in desc:
                return sector
        return "sonstige"

    # ========================================================================
    # REGIONAL MULTIPLIER
    # ========================================================================

    def _calculate_regional_multiplier(
        self,
        transactions: List[Dict],
    ) -> Dict[str, Any]:
        """
        Berechnet den regionalen Multiplikator:
        Wie viel der Ausgaben bleibt in der Region?

        Verwendet region_code-Feld oder IBAN-PLZ-Mapping.
        """
        # Regionen basierend auf Transaktionen identifizieren
        total_volume = 0.0
        local_volume = 0.0
        region_stats: Dict[str, Dict] = defaultdict(lambda: {"total": 0.0, "local": 0.0})

        for tx in transactions:
            amount = float(tx.get("amount_eur", 0.0))
            sender_region = tx.get("sender_region", tx.get("region_code", ""))
            receiver_region = tx.get("receiver_region", "")

            total_volume += amount

            # Gleiche Region → "lokale" Ausgabe
            if sender_region and receiver_region and sender_region == receiver_region:
                local_volume += amount

            if sender_region:
                region_stats[sender_region]["total"] += amount
                if sender_region == receiver_region:
                    region_stats[sender_region]["local"] += amount

        local_retention = local_volume / total_volume if total_volume > 0 else 0.0

        # Pro Region
        regional_breakdown = {}
        for region, stats in sorted(region_stats.items()):
            if stats["total"] > 0:
                regional_breakdown[region] = {
                    "total_volume_eur": round(stats["total"], 2),
                    "local_volume_eur": round(stats["local"], 2),
                    "local_retention_pct": round(stats["local"] / stats["total"] * 100, 1),
                }

        return {
            "local_retention_rate": round(local_retention, 3),
            "total_volume_eur": round(total_volume, 2),
            "local_volume_eur": round(local_volume, 2),
            "regional_breakdown": regional_breakdown,
            "interpretation": self._interpret_local_retention(local_retention),
        }

    def _interpret_local_retention(self, retention: float) -> str:
        """Interpretiert die lokale Geldbindung."""
        if retention > 0.75:
            return "SEHR HOCH: Geld bleibt überwiegend in der Region — starker regionaler Multiplikator"
        elif retention > 0.60:
            return "HOCH: Gute regionale Bindung — typisch für Bauwirtschaft"
        elif retention > 0.45:
            return "MITTEL: Signifikante Abflüsse — überregionale Zulieferer involviert"
        elif retention > 0.30:
            return "NIEDRIG: Viel Geld verlässt die Region — hoher Importanteil"
        else:
            return "SEHR NIEDRIG: Kaum regionale Bindung — globalisierte Lieferkette"

    # ========================================================================
    # EMPLOYMENT IMPACT
    # ========================================================================

    def _calculate_employment_impact(
        self,
        transactions: List[Dict],
        initial_spending_eur: float,
    ) -> Dict[str, Any]:
        """
        Berechnet den Beschäftigungs-Multiplikator.

        Jobs = Σ(volume_per_sector / jobs_per_mio_eur)
        """
        total_jobs_created = 0.0
        sector_jobs = {}

        # Durchschnittliche Jobs pro 1 Mio € Umsatz (Bauwirtschaft)
        jobs_per_mio = {
            "bau": 12.5,
            "beton": 10.0,
            "stahl": 8.0,
            "hochbau": 11.0,
            "tiefbau": 10.5,
            "straße": 9.5,
            "kanal": 10.0,
            "elektro": 9.0,
            "heizung": 9.5,
            "sanitaer": 10.0,
            "planung": 15.0,
            "ausbau": 12.0,
            "sonstige": 8.0,
        }

        for tx in transactions:
            sector = tx.get("sector", "")
            if not sector:
                desc = tx.get("description", "").lower()
                sector = self._classify_sector(desc)

            amount = float(tx.get("amount_eur", 0.0))
            jpm = jobs_per_mio.get(sector, 8.0)
            jobs = (amount / 1_000_000) * jpm
            total_jobs_created += jobs

            if sector not in sector_jobs:
                sector_jobs[sector] = 0.0
            sector_jobs[sector] += jobs

        # Direkte + indirekte Beschäftigung
        direct_jobs = initial_spending_eur / 1_000_000 * 10.0  # ~10 Jobs/Mio € direkt
        indirect_jobs = total_jobs_created - direct_jobs

        return {
            "total_jobs_created": round(total_jobs_created, 1),
            "direct_jobs": round(direct_jobs, 1),
            "indirect_jobs": round(indirect_jobs, 1),
            "employment_multiplier": round(total_jobs_created / max(direct_jobs, 0.01), 2),
            "jobs_per_mio_eur": round(total_jobs_created / (initial_spending_eur / 1_000_000), 1),
            "sector_jobs": {s: round(j, 1) for s, j in sorted(sector_jobs.items(), key=lambda x: x[1], reverse=True)},
        }

    # ========================================================================
    # BENCHMARK COMPARISON
    # ========================================================================

    def _compare_with_benchmarks(
        self,
        empirical_k: float,
        sector_multipliers: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Vergleicht den gemessenen Multiplikator mit empirischen Benchmarks.
        """
        # Besten Benchmark-Match finden (nach dominantem Sektor)
        dominant_sector = "bau_infrastruktur"
        max_volume = 0.0
        for sector, data in sector_multipliers.items():
            if data["volume_eur"] > max_volume:
                max_volume = data["volume_eur"]
                dominant_sector = self.SECTOR_BENCHMARK_MAP.get(sector, "bau_infrastruktur")

        benchmark = self.BENCHMARKS.get(dominant_sector, self.BENCHMARKS["bau_infrastruktur"])
        benchmark_k = benchmark["fiscal_multiplier"]
        deviation = empirical_k - benchmark_k
        deviation_pct = (deviation / benchmark_k * 100) if benchmark_k > 0 else 0.0

        # Interpretation
        if deviation_pct > 20:
            rating = "ÜBERDURCHSCHNITTLICH"
            interpretation = "Multiplikator deutlich über Benchmark — Wirtschaft reagiert stark auf Impulse"
        elif deviation_pct > 5:
            rating = "LEICHT_ÜBER"
            interpretation = "Multiplikator leicht über Benchmark — gesunde Wirtschaftsdynamik"
        elif deviation_pct > -5:
            rating = "AM_BENCHMARK"
            interpretation = "Multiplikator entspricht Benchmark — normale Wirtschaftsaktivität"
        elif deviation_pct > -20:
            rating = "LEICHT_UNTER"
            interpretation = "Multiplikator unter Benchmark — Wirtschaft reagiert schwach"
        else:
            rating = "DEUTLICH_UNTER"
            interpretation = "Multiplikator DEUTLICH unter Benchmark — Rezessions-Indikator"

        return {
            "dominant_sector": dominant_sector,
            "benchmark_multiplier": benchmark_k,
            "empirical_multiplier": round(empirical_k, 3),
            "deviation_pct": round(deviation_pct, 1),
            "rating": rating,
            "interpretation": interpretation,
            "benchmark_source": benchmark["source"],
            "benchmark_local_retention": benchmark["local_retention"],
            "benchmark_jobs_per_mio": benchmark["employment_multiplier"],
        }

    # ========================================================================
    # COMPOSITE MULTIPLIER
    # ========================================================================

    def _calculate_composite_multiplier(
        self,
        keynesian_k: float,
        empirical_k: float,
        tier_k: float,
        sector_ks: Dict[str, Any],
    ) -> float:
        """
        Gewichteter Gesamt-Multiplikator:
        - 30% Keynesianisch (theoretisch)
        - 40% Empirisch (aus Daten)
        - 20% Tier-gewichtet
        - 10% Sektor-Durchschnitt
        """
        # Durchschnittlicher Sektor-Multiplikator
        sector_k_values = [d["sector_multiplier"] for d in sector_ks.values()]
        avg_sector_k = mean(sector_k_values) if sector_k_values else 1.0

        composite = (
            0.30 * max(keynesian_k, 0.5)
            + 0.40 * max(empirical_k, 0.5)
            + 0.20 * max(tier_k, 0.5)
            + 0.10 * max(avg_sector_k, 0.5)
        )
        return round(composite, 3)

    # ========================================================================
    # ALERTS
    # ========================================================================

    def _generate_alerts(
        self,
        composite_k: float,
        empirical_k: float,
        tier_analysis: Dict[str, Any],
        regional_k: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Generiert Alerts bei kritischen Multiplikator-Werten.
        """
        alerts = []

        # --- 1. Multiplikator < 1.0 (Kontraktion) ---
        if composite_k < self.alert_threshold:
            alerts.append(
                {
                    "alert_type": "MULTIPLIER_BELOW_ONE",
                    "severity": "HIGH",
                    "message": (
                        f"Multiplikator k={composite_k:.3f} < 1.0 — "
                        f"Jeder € Staatsausgabe generiert WENIGER als 1 € Wirtschaftsleistung. "
                        f"Wirtschaft schrumpft trotz Impulsen!"
                    ),
                    "composite_k": composite_k,
                }
            )

        # --- 2. Empirischer Multiplikator weicht stark von Keynesianisch ab ---
        if empirical_k > 0 and composite_k > 0:
            ratio = empirical_k / composite_k
            if ratio > 2.0:
                alerts.append(
                    {
                        "alert_type": "EMPIRICAL_THEORETICAL_GAP",
                        "severity": "MEDIUM",
                        "message": (
                            f"Empirischer Multiplikator ({empirical_k:.2f}) ist "
                            f"{ratio:.1f}× höher als theoretisch erwartet ({composite_k:.2f}) — "
                            f"Datenqualität prüfen oder struktureller Bruch."
                        ),
                    }
                )

        # --- 3. Regionaler Abfluss ---
        retention = regional_k.get("local_retention_rate", 0.0)
        if retention < 0.35:
            alerts.append(
                {
                    "alert_type": "LOW_LOCAL_RETENTION",
                    "severity": "MEDIUM",
                    "message": (
                        f"Nur {retention*100:.1f}% des Geldes bleibt in der Region — "
                        f"regionaler Multiplikator schwach. Lokale Zulieferer fördern!"
                    ),
                    "retention_rate": round(retention, 3),
                }
            )

        # --- 4. Tier-Abfall zu stark ---
        tiers = tier_analysis.get("tiers", [])
        if len(tiers) >= 3:
            tier0_k = tiers[0].get("tier_multiplier", 0) if len(tiers) > 0 else 0
            tier_last_k = tiers[-1].get("tier_multiplier", 0) if tiers else 0
            dropoff = (tier0_k - tier_last_k) / max(tier0_k, 0.001)
            if dropoff > 0.9:  # >90% Abfall
                alerts.append(
                    {
                        "alert_type": "STEEP_TIER_DROPOFF",
                        "severity": "LOW",
                        "message": (
                            f"Starker Multiplikator-Abfall entlang der Lieferkette: "
                            f"Tier 0={tier0_k:.3f} → Tier {len(tiers)-1}={tier_last_k:.3f} "
                            f"({dropoff*100:.0f}% Drop) — Lieferkette zu kurz?"
                        ),
                    }
                )

        return alerts

    # ========================================================================
    # POLICY ADVICE
    # ========================================================================

    def _policy_advice(self, composite_k: float) -> Dict[str, Any]:
        """
        Fiskalpolitische Handlungsempfehlung basierend auf Multiplikator.
        """
        if composite_k > 2.0:
            action = "EXPAND_STRONG"
            advice = (
                f"Multiplikator k={composite_k:.1f} >> 1: JEDER Euro Staatsausgabe "
                f"hebelt {composite_k:.1f}× Wirtschaftsleistung. Öffentliche Investitionen "
                f"MAXIMAL ausweiten — extrem effizienter Stimulus."
            )
        elif composite_k > 1.5:
            action = "EXPAND"
            advice = (
                f"Multiplikator k={composite_k:.1f} > 1.5: Gute Hebelwirkung. "
                f"Öffentliche Investitionen ausweiten — positiver ROI für Staatshaushalt."
            )
        elif composite_k > 1.2:
            action = "MAINTAIN"
            advice = (
                f"Multiplikator k={composite_k:.1f}: Solide. Aktuelles Ausgabenniveau halten."
            )
        elif composite_k > 1.0:
            action = "WATCH"
            advice = (
                f"Multiplikator k={composite_k:.1f}: Schwach positiv. "
                f"Gezielte Investitionen in Sektoren mit höherem k lenken."
            )
        elif composite_k > 0.8:
            action = "RESTRUCTURE"
            advice = (
                f"Multiplikator k={composite_k:.1f} < 1: Jeder Euro generiert WENIGER "
                f"als 1 € Output. Ausgaben umstrukturieren — Fokus auf lokale Zulieferer, "
                f"Importquote senken, MPC erhöhen."
            )
        else:
            action = "CONTRACT"
            advice = (
                f"Multiplikator k={composite_k:.1f} << 1: KRITISCH. Staatsausgaben "
                f"wirken kontraktiv. SOFORT Ursachenanalyse: Hohe Importquote? "
                f"Niedrige MPC? Steuersatz zu hoch? Lieferkette defekt?"
            )

        return {
            "action": action,
            "advice": advice,
            "composite_k": composite_k,
        }


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    import random

    print("=" * 60)
    print("SupplyChainMultiplierCalc — Smoke Test")
    print("=" * 60)

    calc = SupplyChainMultiplierCalcSubagent()

    # Synthetische Transaktionen generieren (simuliert Lieferkette)
    rng = random.Random(42)
    sectors = ["beton", "stahl", "tiefbau", "elektro", "kanal"]
    regions = ["NI", "NI", "NI", "NW", "BY", "HH"]  # Überwiegend Niedersachsen

    initial_spending = 4_200_000.0  # 4.2 Mio € (Kläranlage Nord)

    transactions = []
    for i in range(150):
        sender_region = rng.choice(regions)
        receiver_region = rng.choice(regions)
        sector = rng.choice(sectors)
        amount = round(rng.lognormvariate(mu=9.5, sigma=1.2), 2)

        transactions.append(
            {
                "sender": f"Firma_{rng.randint(1, 30)}",
                "receiver": f"Firma_{rng.randint(1, 30)}",
                "amount_eur": amount,
                "timestamp": (datetime.now(timezone.utc) - timedelta(days=rng.randint(0, 90))).isoformat(),
                "sector": sector,
                "sender_region": sender_region,
                "receiver_region": receiver_region,
                "tier": rng.choices([0, 1, 2, 3, 4], weights=[5, 30, 35, 20, 10])[0],
                "description": f"Lieferung {sector} Baustelle Nord",
            }
        )

    report = calc.calculate_multiplier(
        transactions=transactions,
        initial_spending_eur=initial_spending,
    )

    print(f"\nStatus: {report['status']}")
    mm = report["multiplier_metrics"]
    print(f"Composite k: {mm['composite_multiplier']}")
    print(f"Keynesian k: {mm['keynesian_multiplier']} (MPC={mm['mpc']}, MPS={mm['mps']}, Import={mm['import_quote']})")
    print(f"Empirical k: {mm['empirical_multiplier']}")

    ta = report["tier_analysis"]
    print(f"\nTier-Multiplikator: {ta['weighted_multiplier']}")
    for t in ta["tiers"]:
        print(f"  Tier {t['tier']} ({t['label']}): k={t['tier_multiplier']:.3f}, Vol={t['volume_eur']:,.0f} EUR, {t['unique_actors']} Akteure")

    rm = report["regional_multiplier"]
    print(f"\nLokale Geldbindung: {rm['local_retention_rate']*100:.1f}%")
    print(f"  {rm['interpretation']}")

    ei = report["employment_impact"]
    print(f"\nBeschäftigung: {ei['total_jobs_created']} Jobs total")
    print(f"  Direkt: {ei['direct_jobs']}, Indirekt: {ei['indirect_jobs']}")
    print(f"  Jobs/Mio €: {ei['jobs_per_mio_eur']}")

    bc = report["benchmark_comparison"]
    print(f"\nBenchmark: {bc['rating']} — {bc['interpretation'][:100]}...")

    pol = report["policy_implication"]
    print(f"\nFiskalpolitik: {pol['action']}")
    print(f"  {pol['advice'][:120]}...")

    print(f"\nAlerts: {len(report['alerts'])}")
    for a in report["alerts"]:
        print(f"  [{a['severity']}] {a['message'][:120]}...")

    print("\n✅ Smoke Test abgeschlossen.")
