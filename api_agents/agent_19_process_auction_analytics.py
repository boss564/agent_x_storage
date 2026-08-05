"""
Agent X — API Agent 19: ProcessMining + AuctionBehavior Analytics.

Zwei Agenten in einem Modul:
  19a: ProcessMiningAgent — Pool-Lebenszyklus-Analyse, Engpass-Erkennung
  19b: AuctionBehaviorAgent — Großhändler-Profiling, Rabattkurven, Sweet-Spot

Macht aus rohen Pool-Events handlungsorientierte Erkenntnisse:
  - ∅ Pool-Füllzeit, ∅ Auktionsdauer, ∅ Lieferzeit
  - Welcher Großhändler gibt bei welcher Menge den besten Rabatt?
  - Ab welcher Pool-Größe lohnt sich der Aufwand (Sweet-Spot)?

Integration: Liest aus demand_pools + pool_bids (Agent 18).
             Schreibt in process_metrics + wholesaler_profiles.
"""

import json
import logging
import math
import os
import random
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ProcessAuctionAnalytics")

DB_PATH = os.getenv("DEMAND_DB", "data/pooled_demand.db")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── DB-Initialisierung ──────────────────────────────────────────────

def _init_analytics_db(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pool_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_timestamp TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS process_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                product_group TEXT,
                calculated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wholesaler_profiles (
                wholesaler_id TEXT NOT NULL,
                product_group TEXT NOT NULL,
                sweet_spot_quantity REAL,
                avg_discount_pct REAL,
                elasticity REAL,
                sample_count INTEGER DEFAULT 0,
                last_updated TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (wholesaler_id, product_group)
            )
        """)
        conn.commit()


# ─── Sub-Agent 19a: ProcessMiningAgent ───────────────────────────────

class ProcessMiningAgent:
    """Rekonstruiert den Lebenszyklus jedes Pools aus Events.

    Berechnet:
      - ∅ Pool-Füllzeit (Created → ThresholdReached)
      - ∅ Auktionsdauer (AuctionStarted → AuctionSettled)
      - ∅ Lieferzeit (AuctionSettled → DeliveryConfirmed)
      - Engpass-Erkennung (Phase mit höchster Varianz)
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        _init_analytics_db(db_path)

    def analyze(self, timeframe_days: int = 90) -> dict:
        """Analysiert alle abgeschlossenen Pools der letzten N Tage."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=timeframe_days)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            pools = conn.execute(
                """SELECT * FROM demand_pools
                   WHERE auction_status = 'awarded'
                   AND awarded_at > ?""",
                (cutoff,),
            ).fetchall()

        if not pools:
            return {"status": "no_data",
                    "message": f"Keine abgeschlossenen Pools in den letzten {timeframe_days} Tagen.",
                    "timeframe_days": timeframe_days}

        metrics = self._compute_metrics(pools)
        bottlenecks = self._detect_bottlenecks(pools)
        trends = self._trend_analysis(pools)

        # Persistieren
        with sqlite3.connect(self.db_path) as conn:
            for name, value in metrics.items():
                if isinstance(value, (int, float)):
                    conn.execute(
                        """INSERT INTO process_metrics (metric_name, value, product_group)
                           VALUES (?, ?, ?)""",
                        (name, value, "ALL"),
                    )
            conn.commit()

        return {
            "status": "completed",
            "pools_analyzed": len(pools),
            "timeframe_days": timeframe_days,
            "metrics": metrics,
            "bottlenecks": bottlenecks,
            "trends": trends,
            "analyzed_at": _now_iso(),
        }

    def _compute_metrics(self, pools: list[sqlite3.Row]) -> dict:
        """Berechnet ∅ Zeiten über alle Pools."""
        fill_times = []
        auction_times = []
        settlement_times = []
        by_product: dict[str, dict[str, list]] = defaultdict(
            lambda: defaultdict(list))

        for pool in pools:
            timeline = self._get_timeline(pool["pool_id"])
            if not timeline:
                continue

            pg = pool["product_group"]
            if timeline["fill_hours"] is not None:
                fill_times.append(timeline["fill_hours"])
                by_product[pg]["fill"].append(timeline["fill_hours"])
            if timeline["auction_hours"] is not None:
                auction_times.append(timeline["auction_hours"])
                by_product[pg]["auction"].append(timeline["auction_hours"])
            if timeline["settlement_hours"] is not None:
                settlement_times.append(timeline["settlement_hours"])

        def avg(lst): return round(sum(lst) / len(lst), 1) if lst else 0
        def p90(lst): return round(sorted(lst)[int(len(lst) * 0.9)], 1) if lst else 0

        per_product = {}
        for pg, phases in by_product.items():
            per_product[pg] = {
                "avg_fill_h": avg(phases.get("fill", [])),
                "avg_auction_h": avg(phases.get("auction", [])),
                "pool_count": len(phases.get("fill", [])),
            }

        return {
            "avg_pool_fill_time_hours": avg(fill_times),
            "p90_pool_fill_time_hours": p90(fill_times),
            "avg_auction_duration_hours": avg(auction_times),
            "p90_auction_duration_hours": p90(auction_times),
            "avg_settlement_time_hours": avg(settlement_times),
            "total_pools_analyzed": len(pools),
            "per_product": per_product,
        }

    def _get_timeline(self, pool_id: str) -> Optional[dict]:
        """Extrahiert die Timeline eines Pools aus Events."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            events = conn.execute(
                """SELECT * FROM pool_events
                   WHERE pool_id = ? ORDER BY event_timestamp ASC""",
                (pool_id,),
            ).fetchall()

        if not events:
            return None

        created = None
        threshold = None
        auction_start = None
        auction_end = None
        delivered = None

        for ev in events:
            ts = datetime.fromisoformat(ev["event_timestamp"])
            if ev["event_type"] == "PoolCreated":
                created = ts
            elif ev["event_type"] == "PoolThresholdReached":
                threshold = ts
            elif ev["event_type"] == "AuctionStarted":
                auction_start = ts
            elif ev["event_type"] == "AuctionSettled":
                auction_end = ts
            elif ev["event_type"] == "DeliveryConfirmed":
                delivered = ts

        def diff_h(a, b):
            return (b - a).total_seconds() / 3600 if a and b else None

        return {
            "fill_hours": diff_h(created, threshold),
            "auction_hours": diff_h(auction_start, auction_end),
            "settlement_hours": diff_h(auction_end, delivered),
        }

    def _detect_bottlenecks(self, pools: list[sqlite3.Row]) -> list[dict]:
        """Findet die Phase mit der höchsten Varianz (Engpass-Indikator)."""
        phase_variances = {"fill": [], "auction": [], "settlement": []}

        for pool in pools:
            tl = self._get_timeline(pool["pool_id"])
            if not tl:
                continue
            if tl["fill_hours"]:
                phase_variances["fill"].append(tl["fill_hours"])
            if tl["auction_hours"]:
                phase_variances["auction"].append(tl["auction_hours"])
            if tl["settlement_hours"]:
                phase_variances["settlement"].append(tl["settlement_hours"])

        results = []
        for phase, values in phase_variances.items():
            if len(values) < 2:
                continue
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            cv = math.sqrt(variance) / mean if mean > 0 else 0  # Variationskoeffizient
            results.append({
                "phase": phase,
                "mean_hours": round(mean, 1),
                "std_hours": round(math.sqrt(variance), 1),
                "cv": round(cv, 3),
                "is_bottleneck": cv > 0.5,  # CV > 0.5 = hohe Variabilität
            })

        results.sort(key=lambda r: r["cv"], reverse=True)
        return results

    def _trend_analysis(self, pools: list[sqlite3.Row]) -> dict:
        """Analysiert Trends über die Zeit (werden Pools schneller/langsamer?)."""
        monthly: dict[str, list] = defaultdict(list)

        for pool in pools:
            tl = self._get_timeline(pool["pool_id"])
            if not tl or not tl["fill_hours"]:
                continue
            month = pool["created_at"][:7] if pool["created_at"] else "unknown"
            monthly[month].append(tl["fill_hours"])

        trend_data = {}
        for month, times in sorted(monthly.items()):
            trend_data[month] = {
                "avg_fill_h": round(sum(times) / len(times), 1),
                "pool_count": len(times),
            }

        # Trend-Richtung (letzte 3 Monate vs. vorherige)
        months_sorted = sorted(trend_data.keys())
        if len(months_sorted) >= 4:
            recent = [trend_data[m]["avg_fill_h"] for m in months_sorted[-3:]]
            older = [trend_data[m]["avg_fill_h"] for m in months_sorted[-6:-3]]
            recent_avg = sum(recent) / len(recent) if recent else 0
            older_avg = sum(older) / len(older) if older else 0
            direction = "improving" if recent_avg < older_avg else "worsening"
            change_pct = round((recent_avg - older_avg) / older_avg * 100, 1) if older_avg else 0
        else:
            direction = "insufficient_data"
            change_pct = 0

        return {
            "monthly": trend_data,
            "direction": direction,
            "change_pct": change_pct,
        }


# ─── Sub-Agent 19b: AuctionBehaviorAgent ─────────────────────────────

class AuctionBehaviorAgent:
    """Analysiert Bieterverhalten, Rabattkurven und Sweet-Spots.

    Für jede Produktgruppe + Großhändler-Kombination:
      - Rabatt in Abhängigkeit von der Pool-Größe
      - Lineare Regression: discount = a × quantity + b
      - Sweet-Spot: Menge ab der marginale Rabatt < 0.1 % pro Einheit
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        _init_analytics_db(db_path)

    def analyze(self, wholesaler_id: str | None = None,
                product_group: str | None = None) -> dict:
        """Analysiert Bieterverhalten und berechnet Sweet-Spots."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            query = """
                SELECT b.*, p.product_group, p.total_quantity
                FROM pool_bids b
                JOIN demand_pools p ON b.pool_id = p.pool_id
                WHERE p.auction_status = 'awarded' AND b.status IN ('won', 'revealed')
            """
            params = []
            if wholesaler_id:
                query += " AND b.bidder = ?"
                params.append(wholesaler_id)
            if product_group:
                query += " AND p.product_group = ?"
                params.append(product_group)
            query += " ORDER BY b.bid_price_eur ASC"

            bids = conn.execute(query, params).fetchall()

        if len(bids) < 5:
            return {"status": "insufficient_data",
                    "message": f"Nur {len(bids)} Gebote — mindestens 5 benötigt.",
                    "bid_count": len(bids)}

        # Gruppiere nach Großhändler × Produktgruppe
        profiles = {}
        for bid in bids:
            key = (bid["bidder"], bid["product_group"])
            if key not in profiles:
                profiles[key] = []
            profiles[key].append({
                "quantity": bid["total_quantity"],
                "bid_price": bid["bid_price_eur"],
            })

        results = {}
        for (wholesaler, pg), bid_list in profiles.items():
            profile = self._compute_profile(wholesaler, pg, bid_list)
            results[f"{wholesaler}/{pg}"] = profile

            # Persistieren
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO wholesaler_profiles
                       (wholesaler_id, product_group, sweet_spot_quantity,
                        avg_discount_pct, elasticity, sample_count, last_updated)
                       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (wholesaler, pg, profile["sweet_spot_quantity"],
                     profile["avg_discount_pct"], profile["elasticity"],
                     len(bid_list)),
                )
                conn.commit()

        return {
            "status": "completed",
            "profiles_analyzed": len(results),
            "total_bids_analyzed": len(bids),
            "profiles": results,
            "generated_at": _now_iso(),
        }

    def _compute_profile(self, wholesaler: str, product_group: str,
                         bids: list[dict]) -> dict:
        """Berechnet Rabattkurve und Sweet-Spot für eine Kombination."""
        # Basis-Listenpreis
        base_price = bids[0]["bid_price"] * 1.15 if bids else 5.0

        # Rabatt pro Gebot
        discounts = []
        for b in bids:
            discount = (base_price - b["bid_price"]) / base_price
            discounts.append({
                "quantity": b["quantity"],
                "discount_pct": round(discount * 100, 2),
            })

        avg_discount = sum(d["discount_pct"] for d in discounts) / len(discounts)
        avg_quantity = sum(d["quantity"] for d in discounts) / len(discounts)

        # Lineare Regression: discount = slope × quantity + intercept
        n = len(discounts)
        sum_x = sum(d["quantity"] for d in discounts)
        sum_y = sum(d["discount_pct"] for d in discounts)
        sum_xy = sum(d["quantity"] * d["discount_pct"] for d in discounts)
        sum_x2 = sum(d["quantity"] ** 2 for d in discounts)

        if n * sum_x2 - sum_x * sum_x != 0:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
            intercept = (sum_y - slope * sum_x) / n
        else:
            slope, intercept = 0, avg_discount

        # Sweet-Spot: Wo flacht die Kurve ab?
        # Vereinfacht: Erster Punkt wo marginaler Rabatt < 0.1% pro 100 Einheiten
        sorted_by_qty = sorted(discounts, key=lambda d: d["quantity"])
        sweet_spot = avg_quantity
        for i in range(1, len(sorted_by_qty)):
            delta_q = sorted_by_qty[i]["quantity"] - sorted_by_qty[i-1]["quantity"]
            delta_d = sorted_by_qty[i]["discount_pct"] - sorted_by_qty[i-1]["discount_pct"]
            if delta_q > 0 and abs(delta_d / delta_q * 100) < 0.1:
                sweet_spot = sorted_by_qty[i]["quantity"]
                break

        # Elastizität: %ΔDiscount / %ΔQuantity
        elasticity = round(slope * (avg_quantity / max(0.1, avg_discount)), 2)

        return {
            "wholesaler": wholesaler,
            "product_group": product_group,
            "sample_count": len(bids),
            "avg_discount_pct": round(avg_discount, 1),
            "max_discount_pct": round(max(d["discount_pct"] for d in discounts), 1),
            "sweet_spot_quantity": round(sweet_spot, 0),
            "elasticity": elasticity,
            "regression": {
                "slope_per_1000_units": round(slope * 1000, 4),
                "intercept_pct": round(intercept, 2),
                "r_squared": round(self._r_squared(discounts, slope, intercept), 3),
            },
            "discount_curve": discounts[:10],
            "recommendation": (
                f"Für {wholesaler}/{product_group}: Optimaler Pool bei "
                f"{sweet_spot:.0f} Einheiten (∅ {avg_discount:.1f}% Rabatt). "
                f"Elastizität: {elasticity:.2f} — "
                f"{'stark preissensitiv' if abs(elasticity) > 1 else 'moderat preissensitiv'}."
            ),
        }

    @staticmethod
    def _r_squared(data: list[dict], slope: float, intercept: float) -> float:
        if len(data) < 2:
            return 0
        mean_y = sum(d["discount_pct"] for d in data) / len(data)
        ss_res = sum(
            (d["discount_pct"] - (slope * d["quantity"] + intercept)) ** 2
            for d in data
        )
        ss_tot = sum((d["discount_pct"] - mean_y) ** 2 for d in data)
        return round(1 - ss_res / ss_tot, 3) if ss_tot > 0 else 0


# ─── Synthetic Data Generator ─────────────────────────────────────────

class SyntheticDataGenerator:
    """Erzeugt realistische Testdaten für ProcessMining + AuctionBehavior.

    Generiert 50 Pools × 6 Monate × 3 Großhändler.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        _init_analytics_db(db_path)

    def generate(self, num_pools: int = 50):
        """Erzeugt synthetische Pool-Events und Gebote."""
        products = ["Kupferrohr_15x1", "Kupferrohr_22x1", "Pressfitting_T_15mm"]
        wholesalers = ["GC-Gruppe", "Hagebau", "Bender-Gruppe"]
        base_prices = {"Kupferrohr_15x1": 6.80, "Kupferrohr_22x1": 10.50,
                       "Pressfitting_T_15mm": 4.20}

        now = datetime.now(timezone.utc)

        with sqlite3.connect(self.db_path) as conn:
            # Pool-Daten löschen und neu aufbauen
            conn.execute("DELETE FROM pool_events")
            conn.execute("DELETE FROM pool_bids")
            conn.execute("DELETE FROM demand_pools")
            conn.execute("DELETE FROM demand_entries")
            conn.execute("DELETE FROM process_metrics")
            conn.execute("DELETE FROM wholesaler_profiles")

            for i in range(num_pools):
                pg = random.choice(products)
                qty = random.choice([800, 1500, 2500, 3500, 5000, 7500])
                base = base_prices[pg]
                participants = random.randint(3, 15)
                pool_id = f"pool_{pg}_{i:04d}"

                # Zeitstempel über 6 Monate verteilt
                days_ago = random.randint(0, 180)
                created = now - timedelta(days=days_ago)
                threshold_reached = created + timedelta(
                    hours=random.randint(4, 72))
                auction_start = threshold_reached + timedelta(
                    hours=random.randint(1, 12))
                auction_end = auction_start + timedelta(
                    hours=random.randint(6, 48))
                delivered = auction_end + timedelta(
                    days=random.randint(3, 21))

                # Pool anlegen
                conn.execute(
                    """INSERT INTO demand_pools
                       (pool_id, product_group, total_quantity, participant_count,
                        pool_price_eur, auction_status, pool_hash,
                        winning_bidder, winning_price_eur, awarded_at)
                       VALUES (?, ?, ?, ?, ?, 'awarded', ?, ?, ?, ?)""",
                    (pool_id, pg, qty, participants,
                     base * 0.75, "0xhash",
                     random.choice(wholesalers),
                     round(base * random.uniform(0.65, 0.85), 2),
                     auction_end.isoformat()),
                )

                # Events generieren
                events = [
                    ("PoolCreated", created),
                    ("PoolThresholdReached", threshold_reached),
                    ("AuctionStarted", auction_start),
                    ("AuctionSettled", auction_end),
                    ("DeliveryConfirmed", delivered),
                ]
                for ev_type, ev_time in events:
                    conn.execute(
                        """INSERT INTO pool_events (pool_id, event_type, event_timestamp)
                           VALUES (?, ?, ?)""",
                        (pool_id, ev_type, ev_time.isoformat()),
                    )

                # Gebote von 3 Großhändlern
                for w in wholesalers:
                    conn.execute(
                        """INSERT INTO pool_bids (pool_id, bidder, bid_price_eur,
                           bid_hash, status, revealed_at)
                           VALUES (?, ?, ?, ?, 'revealed', ?)""",
                        (pool_id, w,
                         round(base * random.uniform(0.65, 0.92), 2),
                         "0xbidhash", auction_end.isoformat()),
                    )

            conn.commit()

        logger.info("Synthetische Daten generiert: %d Pools", num_pools)
        return {"pools_generated": num_pools, "products": products,
                "wholesalers": wholesalers, "date_range": "6 Monate"}


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 1. Synthetische Daten generieren
    gen = SyntheticDataGenerator()
    gen.generate(50)

    # 2. Process Mining
    pma = ProcessMiningAgent()
    result = pma.analyze(timeframe_days=180)

    print("=== Process Mining Agent ===\n")
    m = result.get("metrics", {})
    print(f"Pools analysiert: {result['pools_analyzed']}")
    print(f"∅ Pool-Füllzeit:  {m.get('avg_pool_fill_time_hours', 0):.1f}h "
          f"(P90: {m.get('p90_pool_fill_time_hours', 0):.1f}h)")
    print(f"∅ Auktionsdauer:  {m.get('avg_auction_duration_hours', 0):.1f}h "
          f"(P90: {m.get('p90_auction_duration_hours', 0):.1f}h)")
    print(f"∅ Lieferzeit:     {m.get('avg_settlement_time_hours', 0):.1f}h")

    bottlenecks = result.get("bottlenecks", [])
    if bottlenecks:
        print(f"\nEngpass-Analyse:")
        for b in bottlenecks:
            flag = " ⚠️ ENGPASS" if b["is_bottleneck"] else ""
            print(f"  {b['phase']}: ∅={b['mean_hours']:.1f}h, "
                  f"σ={b['std_hours']:.1f}h, CV={b['cv']:.3f}{flag}")

    trends = result.get("trends", {})
    print(f"\nTrend: {trends.get('direction', '?')} "
          f"({trends.get('change_pct', 0):+.1f}%)")

    # Per-Produkt
    for pg, pm in m.get("per_product", {}).items():
        print(f"  {pg}: ∅ Fill={pm['avg_fill_h']:.1f}h, "
              f"Auction={pm['avg_auction_h']:.1f}h ({pm['pool_count']} Pools)")

    # 3. Auction Behavior
    print(f"\n=== Auction Behavior Agent ===\n")
    aba = AuctionBehaviorAgent()
    result2 = aba.analyze()

    for key, profile in result2.get("profiles", {}).items():
        print(f"{key}:")
        print(f"  Samples: {profile['sample_count']}")
        print(f"  ∅ Rabatt: {profile['avg_discount_pct']:.1f}% "
              f"(max {profile['max_discount_pct']:.1f}%)")
        print(f"  Sweet-Spot: {profile['sweet_spot_quantity']:.0f} Einheiten")
        print(f"  Elastizität: {profile['elasticity']:.2f}")
        print(f"  R²: {profile['regression']['r_squared']:.3f}")
        print(f"  {profile['recommendation'][:120]}")
        print()
