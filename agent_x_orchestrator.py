"""
Agent X — SymbolicsAgent / Zentraler Orchestrator (5-Klassen-Fusion).

Fusioniert Signale aller fünf Klassen:
  A — Konsensus & Determinismus (Sekunden)
  B — Druckventile (MEV, Gas) (Sekunden)
  C — Lending & Risiko (Sekunden–Minuten)
  D — DeFi-Events + Oracle (Sekunden–Minuten)
  E — DAO-Governance & Timelocks (Stunden–Monate)

Architektur (6-Schritt-Szenario mit Zeithorizonten):
  1. E1:   Langzeit-Scan — Timelocks, Unlocks, Proposals (Tage–Wochen)
  2. A3-1: Timing-Forecast (Slot, Validator)
  3. B1/B2: Druckventile — Gas-Pressure + MEV-Pressure prüfen
  4. D2:   Flash-Loan-Chance + Oracle-Update-Vorwarnung
  5. C2:   Health-Factor prüfen (mit B→C HF-Bump + E→C Pre-Unlock-Warnung)
  6. A3-3: Routing + E3-2 Hedge-Strategie

Neo4j-Audit optional.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("agent_x_orchestrator")

ORCHESTRATOR_POLL_INTERVAL = int(os.getenv("ORCHESTRATOR_POLL_INTERVAL", "12"))
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_ENABLED = os.getenv("NEO4J_ENABLED", "false").lower() == "true"

# ─── Schwellwerte (4-Klassen) ───────────────────────────────────────

MIN_CHI_FOR_DEFI_OPS = 60
MIN_CHI_FOR_HF_WARNING = 80
MIN_CHI_FOR_FLASH_LOAN = 60
MAX_MEV_BOTS_FOR_DIRECT_TX = 2
MAX_GAS_PRESSURE_FOR_ARBITRAGE = 85
MAX_MEV_PRESSURE_FOR_FLASH_LOAN = 70
HF_BUMP_GAS_STRESS_MODERATE = 0.05   # Gas > 80
HF_BUMP_GAS_STRESS_EXTREME = 0.10    # Gas > 90


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _neo4j_log(event_type: str, data: dict):
    if not NEO4J_ENABLED:
        return
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=("neo4j", "password"))
        with driver.session() as session:
            session.run(
                """CREATE (e:AgentXEvent {
                    type: $type, data: $data, timestamp: $ts
                })""",
                type=event_type, data=json.dumps(data), ts=_now_iso(),
            )
        driver.close()
    except Exception as e:
        logger.debug("Neo4j-Logging nicht verfügbar: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# SYMBOLICS AGENT (4-Klassen-Fusion)
# ═══════════════════════════════════════════════════════════════════════

class SymbolicsAgent:
    """Zentraler Orchestrator: Fusioniert A + B(Druck) + C(Lending) + D(DeFi)."""

    def __init__(self, capital: float = 100_000):
        self.capital = capital
        self.last_decision: dict = {}
        self.decision_log: list[dict] = []
        self._prev_global_score = 100.0  # Smooth-Transition-Gedächtnis

    # ─── Haupt-Evaluierung ───────────────────────────────────────────

    def evaluate(
        self,
        # Klasse A — Konsensus
        consensus_health_index: float = 100.0,
        exit_queue_length: int = 0,
        participation_rate: float = 0.97,
        finality_status: str = "on_time",
        reorg_depth: int = 0,
        eth_slots: list[dict] | None = None,
        sol_slots: list[dict] | None = None,
        trusted_validators: list[str] | None = None,
        # Klasse B — Druckventile (NEU)
        gas_pressure_index: float = 50.0,
        mev_pressure_index: float = 50.0,
        block_pressure_index: float = 50.0,
        basefee_current_gwei: float = 21.0,
        priority_fee_p95_gwei: float = 3.5,
        mev_spike_detected: bool = False,
        # Klasse C — Lending
        health_factors: list[dict] | None = None,
        # Klasse D — DeFi
        flash_loan_opportunities: list[dict] | None = None,
        mempool_bots_count: int = 0,
        cross_pool_opportunities: list[dict] | None = None,
        cross_chain_opportunities: list[dict] | None = None,
        # Klasse E — DAO/Timelocks
        pending_timelocks: list[dict] | None = None,
        upcoming_unlocks: list[dict] | None = None,
        active_proposals: list[dict] | None = None,
        # Klasse A/D Integration — Proaktives Timing
        leader_utilization_pct: float = 50.0,
        oracle_update_in_s: float = 999.0,
        expected_profit_usd: float = 500.0,
    ) -> dict:
        """Haupt-Evaluierung: 5-Klassen-Fusion mit A/D-Timing-Integration."""
        try:
            # Schritt 1: Alle 5 Klassen-Signale separat auswerten
            class_a = self._evaluate_class_a(
                consensus_health_index, exit_queue_length, participation_rate,
                finality_status, reorg_depth, eth_slots, sol_slots, trusted_validators,
            )
            # Klasse-A-Timing-Erweiterung
            class_a["leader_utilization_pct"] = leader_utilization_pct
            class_a["leader_discount_active"] = leader_utilization_pct < 30
            class_b = self._evaluate_class_b_pressure(
                gas_pressure_index, mev_pressure_index, block_pressure_index,
                basefee_current_gwei, priority_fee_p95_gwei, mev_spike_detected,
            )
            # CF-Drop-Projektion: extrahiere CF-Änderungen aus Timelock-Daten
            cf_changes = [
                t for t in (pending_timelocks or [])
                if "collateral" in str(t.get("action", "")).lower()
            ]
            class_c = self._evaluate_class_c_lending(health_factors, cf_changes)
            class_d = self._evaluate_class_d_defi(
                flash_loan_opportunities, mempool_bots_count,
                cross_pool_opportunities, cross_chain_opportunities,
            )
            # Klasse-D-Oracle-Erweiterung
            class_d["oracle_update_in_s"] = oracle_update_in_s
            class_d["oracle_update_imminent"] = oracle_update_in_s < 5
            class_e = self._evaluate_class_e_longterm(
                pending_timelocks or [], upcoming_unlocks or [], active_proposals or [],
            )

            # Schritt 2: Bridges berechnen
            hf_bump = self._compute_hf_bump_from_pressure(class_b)
            class_c["critical_hf_adjusted"] = round(1.05 + hf_bump, 3)
            class_c["hf_bump_applied"] = hf_bump > 0

            # Schritt 3: 5-Klassen Global-State-Fusion
            global_state = self._compute_global_state_5class(class_a, class_b, class_c, class_d, class_e)
            allowed_ops = self._determine_allowed_operations_4class(global_state, class_a, class_b, class_d)
            recommendations = self._generate_recommendations_5class(
                global_state, class_a, class_b, class_c, class_d, class_e,
            )

            # Schritt 4: 6-Schritt-Szenario (mit Langzeit-Horizont)
            scenario = self._run_6step_scenario(
                class_a, class_b, class_c, class_d, class_e,
                mempool_bots_count, trusted_validators, hf_bump,
            )

            # Schritt 5: Bundle-Execution-Integration (A/D-Signal-getrieben)
            bundle_advice = self._compute_bundle_advice(
                class_a, class_b, class_d,
                scenario.get("all_clear", False),
                expected_profit_usd,
            )

            decision = {
                "status": "completed",
                "agent": "SymbolicsAgent",
                "unified_decision": {
                    "global_state": global_state["state"],
                    "global_state_score": global_state["score"],
                    "time_horizon": global_state["time_horizon"],
                    "allowed_operations": allowed_ops,
                    "recommended_actions": recommendations,
                    "scenario": scenario,
                    "bundle_advice": bundle_advice,
                },
                "class_signals": {
                    "klasse_a_consensus": class_a,
                    "klasse_b_druckventile": class_b,
                    "klasse_c_lending": class_c,
                    "klasse_d_defi": class_d,
                    "klasse_e_longterm": class_e,
                },
                "capital": self.capital,
                "timestamp": _now_iso(),
            }

            self.last_decision = decision
            self.decision_log.append(decision)
            _neo4j_log("ORCHESTRATOR_DECISION_4CLASS", decision)
            return decision

        except Exception as e:
            logger.error("SymbolicsAgent.evaluate Fehler: %s", e)
            return {"status": "failed", "error": str(e)}

    # ─── Klasse A: Konsensus (unverändert) ───────────────────────────

    def _evaluate_class_a(self, chi, exit_q, part, fin, reorg, eth, sol, trusted):
        trusted_set = set(trusted or [])
        eth_timing = None
        if eth:
            eth_timing = {
                "next_slot": eth[0].get("slot") if eth else None,
                "next_slot_ms": eth[0].get("offset_ms") if eth else None,
                "slots_available": len(eth),
            }
        return {
            "health_detail": {
                "chi": chi,
                "network_status": ("healthy" if chi >= 80 else "caution" if chi >= 60
                                   else "stressed" if chi >= 40 else "degraded" if chi >= 20 else "critical"),
                "finality": fin, "reorg_depth": reorg, "participation": part,
                "exit_queue_stress": exit_q > 1000,
            },
            "timing": eth_timing,
            "routing_ready": chi >= MIN_CHI_FOR_DEFI_OPS and eth is not None and len(eth or []) > 0,
            "trusted_validators_available": len(trusted_set) > 0,
            "defi_operations_allowed": chi >= MIN_CHI_FOR_DEFI_OPS,
            "flash_loan_allowed": chi >= MIN_CHI_FOR_FLASH_LOAN and reorg == 0,
            "hf_warning_allowed": chi >= MIN_CHI_FOR_HF_WARNING,
        }

    # ─── Klasse B: Druckventile (NEU) ────────────────────────────────

    def _evaluate_class_b_pressure(
        self, gas_idx, mev_idx, block_idx, basefee, pf_p95, spike,
    ):
        combined = (gas_idx + mev_idx + block_idx) / 3

        if combined <= 30:
            level = "low"
        elif combined <= 50:
            level = "moderate"
        elif combined <= 70:
            level = "elevated"
        elif combined <= 85:
            level = "high"
        else:
            level = "extreme"

        return {
            "gas_pressure_index": gas_idx,
            "mev_pressure_index": mev_idx,
            "block_pressure_index": block_idx,
            "combined_pressure_index": round(combined, 1),
            "pressure_level": level,
            "basefee_current_gwei": basefee,
            "priority_fee_p95_gwei": pf_p95,
            "mev_spike_detected": spike,
            "arbitrage_safe": gas_idx < MAX_GAS_PRESSURE_FOR_ARBITRAGE and mev_idx < MAX_MEV_PRESSURE_FOR_FLASH_LOAN,
            "flash_loan_safe": mev_idx < MAX_MEV_PRESSURE_FOR_FLASH_LOAN and not spike,
            "requires_mev_protection": mev_idx > 50 or spike,
        }

    # ─── Klasse B: Lending (Snapshot-Builder + echte Modul-Aufrufe) ─

    @staticmethod
    def build_lending_snapshot(flat_users: list[dict]) -> list[dict]:
        """Konvertiert flache health_factor-Daten in das positions-Listen-Format.

        Das Lending-Modul erwartet pro User eine positions-Liste mit
        Einzelpositionen (symbol, amount, is_collateral, liquidation_threshold).
        Flache Snapshots (Backtest) enthalten nur health_factor + total_debt_usd.

        Diese Funktion leitet die fehlenden Felder ab und baut die
        korrekte Datenstruktur für den Produktionspfad des Moduls.
        """
        snapshots = []
        for i, user in enumerate(flat_users):
            debt_usd = float(user.get("total_debt_usd", 0))
            hf = float(user.get("health_factor", 1.5))
            threshold = float(user.get("liquidation_threshold", 0.80))

            # Collateral aus HF-Formel ableiten: HF = collat × thresh / debt
            # → collat = HF × debt / thresh
            if debt_usd > 0 and hf != float("inf"):
                collateral_usd = (debt_usd * hf) / threshold
            else:
                collateral_usd = float(user.get("total_collateral_usd", 0))

            # ETH-Preis-Annahme für amount-Berechnung
            eth_price = 3200.0

            positions = []
            if collateral_usd > 0:
                positions.append({
                    "symbol": "ETH",
                    "asset_address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                    "amount": collateral_usd / eth_price,  # ungerundet — vermeidet HF-Grenzartefakte
                    "price_usd": eth_price,
                    "is_collateral": True,
                    "liquidation_threshold": threshold,
                })
            if debt_usd > 0:
                positions.append({
                    "symbol": "USDC",
                    "asset_address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                    "amount": debt_usd,
                    "price_usd": 1.0,
                    "is_collateral": False,
                    "liquidation_threshold": 0.0,
                })

            snapshots.append({
                "user_address": user.get("user_address", f"0xSnapshot{i}"),
                "chain": user.get("chain", "ETHEREUM"),
                "positions": positions,
                "total_collateral_usd": round(collateral_usd, 2),
                "total_debt_usd": debt_usd,
                "liquidation_threshold": threshold,
                # Original health_factor als Referenz behalten
                "_ref_health_factor": hf,
            })
        return snapshots

    def _evaluate_class_c_lending(self, hfs, cf_changes=None):
        """Lending via echte B2/B3-Module mit CF-Drop-Projektion.

        Baut aus flachen health_factor-Daten vollständige positions-Listen,
        übergibt sie an das Lending-Modul und konsumiert dessen Output.
        Wenn CF-Änderungen via Timelock angekündigt sind, wird der
        projizierte HF NACH der Änderung berechnet (präventiv).
        """
        hfs = hfs or []

        # Inline-Klassifikation als Referenz
        inline_liquidatable = sum(1 for u in hfs if isinstance(u.get("health_factor"), (int, float)) and u["health_factor"] <= 1.0)
        inline_at_risk = sum(1 for u in hfs if isinstance(u.get("health_factor"), (int, float)) and 1.0 < u["health_factor"] <= 1.5)
        inline_worst = min((u["health_factor"] for u in hfs if isinstance(u.get("health_factor"), (int, float))), default=float("inf"))

        # Default: Inline-Werte (Fallback)
        at_risk, liquidatable, worst = inline_at_risk, inline_liquidatable, inline_worst
        source = "inline_fallback"
        module_summary = None

        # Echte Modul-Aufrufe — mit korrekter positions-Struktur
        try:
            from agent_x_lending_b2_risk import b2_2_health_factor_calculator, b2_3_risk_classifier
            from agent_x_lending_b3_liquidation import b3_1_liquidation_parser

            # Snapshot im Modul-Schema bauen (positions-Listen statt flacher Felder)
            enriched = self.build_lending_snapshot(hfs)

            # B2: Health-Factor via echtes Modul mit vollständigen Positionsdaten
            hf_result = b2_2_health_factor_calculator(user_states=enriched)
            b2_3_risk_classifier(hf_results=hf_result)
            b3_1_liquidation_parser(raw_liquidations=[])

            # Modul-Output KONSUMIEREN (nicht verwerfen!)
            module_summary = (
                hf_result.get("subagents", {})
                .get("b2_2b_hf_computation", {})
                .get("summary", {})
            )
            if module_summary:
                module_liquidatable = module_summary.get("liquidatable", 0)
                module_warning = module_summary.get("warning", 0)
                module_critical = module_summary.get("critical", 0)
                # at_risk = ALLE gefährdeten Zonen (liquidatable + critical + warning)
                module_at_risk = module_liquidatable + module_critical + module_warning

                # Inkonsistenz-Check: Weicht das Modul von der Inline-Logik ab?
                if (module_liquidatable != inline_liquidatable or
                        module_warning + module_critical != inline_at_risk):
                    logger.warning(
                        "LENDING INKONSISTENZ: Inline liq=%d risk=%d | "
                        "Modul liq=%d warn=%d crit=%d (total_risk=%d)",
                        inline_liquidatable, inline_at_risk,
                        module_liquidatable, module_warning, module_critical, module_at_risk,
                    )
                    # Modul-Werte verwenden (das Modul ist die autoritative Quelle)
                    at_risk = module_at_risk
                    liquidatable = module_liquidatable
                    source = "lending_modules_live_DIVERGED"
                else:
                    at_risk = inline_at_risk
                    liquidatable = inline_liquidatable
                    source = "lending_modules_live_CONSISTENT"

                # Worst HF aus dem Modul (falls vorhanden)
                module_users = (
                    hf_result.get("subagents", {})
                    .get("b2_2b_hf_computation", {})
                    .get("users", [])
                )
                module_worst = float("inf")
                for u in module_users:
                    hf = u.get("health_factor")
                    if isinstance(hf, (int, float)) and hf < module_worst:
                        module_worst = hf
                if module_worst != float("inf"):
                    worst = module_worst

        except Exception as e:
            logger.warning("Lending-Module nicht verfügbar: %s — Inline-Fallback", e)

        # Präventive CF-Drop-Projektion (von evaluate() aus Timelocks extrahiert)
        cf_projection = None
        if cf_changes and hfs:
            try:
                from agent_x_lending_b2_risk import calculate_cf_drop_impact
                cf_projection = calculate_cf_drop_impact(hfs, cf_changes)
                # CF-Drop-Projektion verschärft das Risiko
                projected_worst = cf_projection.get("worst_projected_hf", 999.0)
                if projected_worst < worst:
                    worst = projected_worst
                projected_liq = cf_projection.get("users_becoming_liquidatable", 0)
                if projected_liq > liquidatable:
                    liquidatable = projected_liq
            except ImportError:
                pass

        return {
            "users_tracked": len(hfs),
            "at_risk": at_risk,
            "liquidatable": liquidatable,
            "alerts_fired": at_risk > 0 or liquidatable > 0,
            "worst_hf": worst if worst != float("inf") else 999.0,
            "critical_hf_adjusted": 1.05,
            "hf_bump_applied": False,
            "_source": source,
            "_module_summary": module_summary,
            "_inline_ref": {"at_risk": inline_at_risk, "liquidatable": inline_liquidatable},
            "_cf_projection": cf_projection,
        }

    # ─── Klasse D: DeFi ──────────────────────────────────────────────

    def _evaluate_class_d_defi(self, fl, bots, cp, cc):
        fl, cp, cc = fl or [], cp or [], cc or []
        total_profit = sum(o.get("net_profit_usd", 0) for o in fl if o.get("profitable"))
        total_profit += sum(o.get("net_profit_usd", 0) for o in cp if o.get("executable"))
        total_profit += sum(o.get("net_profit_usd", 0) for o in cc if o.get("actionable"))

        mev_risk = ("extreme" if bots > 5 else "high" if bots > 2 else "medium" if bots > 0 else "low")

        return {
            "flash_loan_opportunities": len(fl), "flash_loan_profitable": sum(1 for o in fl if o.get("profitable")),
            "cross_pool_opportunities": len(cp), "cross_chain_opportunities": len(cc),
            "total_potential_profit_usd": round(total_profit, 2),
            "mempool_bots": bots, "mev_risk": mev_risk,
        }

    # ─── Klasse E: DAO/Timelocks (Langzeit-Heuristiken) ──────────────

    def _evaluate_class_e_longterm(self, timelocks, unlocks, proposals):
        hours_next = min((t.get("hours_until_executable", 9999) for t in timelocks), default=9999)
        days_next = min((u.get("days_until", 9999) for u in unlocks), default=9999)
        high_impact = sum(1 for t in timelocks if t.get("impact_score", 0) >= 7)
        max_impact = max((t.get("impact_score", 0) for t in timelocks), default=0)
        total_unlock_usd = sum(u.get("amount_usd", 0) for u in unlocks)

        # Impact-gewichtetes Stufenmodell:
        # Impact ≤ 6: T-24h → LIQUIDATE_WATCHLIST, T-12h → REDUCE
        # Impact ≥ 7: T-24h → REDUCE/HEDGE (sofortige Risikominimierung)
        has_high_impact = high_impact > 0

        longterm_risk = "low"
        action_escalation = "MONITOR"  # MONITOR | PREPARE | REDUCE | HEDGE

        if has_high_impact:
            # Kritische Parameteränderung — früher eskalieren
            if hours_next < 6:
                longterm_risk = "critical"
                action_escalation = "HEDGE"
            elif hours_next <= 24:
                longterm_risk = "high"
                action_escalation = "REDUCE"  # ← Impact≥7: REDUCE schon bei T≤24h
            elif hours_next < 72:
                longterm_risk = "elevated"
                action_escalation = "PREPARE"
            else:
                longterm_risk = "moderate"
                action_escalation = "MONITOR"
        else:
            # Standard-Governance — konservativ eskalieren
            if hours_next < 12:
                longterm_risk = "high"
                action_escalation = "REDUCE"
            elif hours_next < 24:
                longterm_risk = "elevated"
                action_escalation = "PREPARE"
            elif hours_next < 72 or days_next < 7:
                longterm_risk = "moderate"
                action_escalation = "MONITOR"
            else:
                longterm_risk = "low"
                action_escalation = "MONITOR"

        # Token-Unlock-Druckmodell: P_unlock = 24h-Volumen / Ø-Tagesvolumen
        # P_unlock > 5% → ELEVATED_RISK mit REDUCE, auch ohne Timelock
        total_24h_unlock_usd = sum(
            u.get("amount_usd", 0) for u in unlocks if u.get("days_until", 999) <= 1
        )
        # Geschätztes Ø-Tagesvolumen (von Klasse D/C — hier Default $50M)
        avg_daily_volume = 50_000_000
        p_unlock = total_24h_unlock_usd / avg_daily_volume if avg_daily_volume > 0 else 0

        if p_unlock > 0.05:  # >5% des Tagesvolumens = signifikanter Verkaufsdruck
            if action_escalation in ("MONITOR", "PREPARE"):
                action_escalation = "REDUCE"
            longterm_risk = "high" if longterm_risk in ("low", "moderate", "elevated") else longterm_risk
        elif total_unlock_usd > 10_000_000 and days_next < 7:
            # Legacy-Fallback: absoluter Schwellwert als Sanity-Check
            if longterm_risk == "moderate":
                longterm_risk = "elevated"
            elif longterm_risk == "low":
                longterm_risk = "moderate"

        return {
            "pending_timelocks": len(timelocks),
            "high_impact_timelocks": high_impact,
            "max_impact_score": max_impact,
            "hours_until_next_timelock": hours_next,
            "upcoming_unlocks": len(unlocks),
            "total_unlock_volume_usd": round(total_unlock_usd, 0),
            "days_until_next_unlock": days_next,
            "active_proposals": len(proposals),
            "longterm_risk_level": longterm_risk,
            "requires_preparation": hours_next < 72 or days_next < 30,
            "action_escalation": action_escalation,
            "p_unlock": round(p_unlock, 4),  # NEU: relativer Druck-Quotient
            "unlock_24h_usd": round(total_24h_unlock_usd, 0),
        }

    # ─── B → C Bridge: HF-Bump bei Gas-Stress ────────────────────────

    def _compute_hf_bump_from_pressure(self, class_b):
        gas = class_b["gas_pressure_index"]
        if gas > 90:
            return HF_BUMP_GAS_STRESS_EXTREME
        elif gas > 80:
            return HF_BUMP_GAS_STRESS_MODERATE
        return 0.0

    # ─── 4-Klassen Global State ──────────────────────────────────────

    def _compute_global_state_4class(self, a, b, c, d):
        return self._compute_global_state_5class(a, b, c, d, {"longterm_risk_level": "low"})

    def _compute_global_state_5class(self, a, b, c, d, e):
        """5-Klassen Global State mit Zeithorizont-Gewichtung."""
        # Basis — Rohwert vor Penalties
        chi_raw = a["health_detail"]["chi"]

        # Per-channel penalty computation (same values as before, just not subtracted yet)
        pressure_penalties = {"low": 0, "moderate": 2, "elevated": 6, "high": 14, "extreme": 22}
        mev_penalties = {"extreme": 18, "high": 12, "medium": 4, "low": 0}
        e_severity = {"critical": 8, "high": 5, "elevated": 2, "moderate": 0.5, "low": 0}
        hours = e.get("hours_until_next_timelock", 9999)
        days = e.get("days_until_next_unlock", 9999)
        nearest_h = min(hours, days * 24) if days < 999 else hours
        if nearest_h < 1:      e_scale = 1.0
        elif nearest_h < 6:    e_scale = 0.80
        elif nearest_h < 24:   e_scale = 0.50
        elif nearest_h < 72:   e_scale = 0.20
        else:                  e_scale = 0.05
        e_raw = e_severity.get(e.get("longterm_risk_level", "low"), 0)

        from agent_x_aggregation import aggregate, AggregationMethod

        # Per-channel penalties (computed same as before)
        mev = d.get("mev_risk", "low")
        p_b = pressure_penalties.get(b["pressure_level"], 0)
        liq_mult = float(os.getenv("LENDING_MULTIPLIER", "4"))
        liq_cap = float(os.getenv("LENDING_CAP", "26"))
        risk_mult = float(os.getenv("AT_RISK_MULTIPLIER", "1.2"))
        risk_cap = float(os.getenv("AT_RISK_CAP", "18"))
        p_c_risk = min(risk_cap, c.get("at_risk", 0) * risk_mult)
        p_c_liq = min(liq_cap, c.get("liquidatable", 0) * liq_mult)
        p_d = mev_penalties.get(mev, 0)
        p_e = round(e_raw * e_scale, 2)

        penalties = {
            "pressure": p_b, "c_at_risk": p_c_risk, "c_liquidatable": p_c_liq,
            "mev": p_d, "longterm": p_e,
        }

        # Aggregation: Modell B (Dominantes Maximum) by default.
        # Set env AGGREGATION_METHOD=sum for legacy additive behavior.
        method_str = os.getenv("AGGREGATION_METHOD", "sum")
        try:
            agg_method = AggregationMethod(method_str)
        except ValueError:
            agg_method = AggregationMethod.SUM

        p_exp = float(os.getenv("P_NORM_EXPONENT", "1.5"))
        penalty_total = aggregate(penalties, method=agg_method, p_exponent=p_exp)
        if agg_method == AggregationMethod.MULTIPLICATIVE:
            score = max(0.0, chi_raw * penalty_total)
        else:
            score = chi_raw - penalty_total

        # ─── Cross-Class Fast-Path: Oracle-Deviation + Gas-Spike ──────
        oracle_dev = getattr(self, "_last_oracle_deviation", 0.0)
        if oracle_dev > 0.015 and b.get("gas_pressure_index", 0) > 80:
            score = min(score, 40.0)

        # ─── Hysterese-Dämpfung: Fast-Drop, Slow-Recovery ─────────────
        prev_score = getattr(self, "_prev_global_score", score)
        is_extreme = b.get("pressure_level") == "extreme" or b.get("mev_spike_detected")
        has_critical_lending = c.get("liquidatable", 0) > 10 or c.get("worst_hf", 999) < 0.8

        if score < prev_score:
            max_drop = 25.0
            if score < prev_score - max_drop and not is_extreme and not has_critical_lending:
                score = prev_score - max_drop
        else:
            max_rise = 10.0
            if score > prev_score + max_rise:
                score = prev_score + max_rise

        self._prev_global_score = score

        score = max(0.0, min(100.0, round(score, 1)))
        state = ("healthy" if score >= 80 else "caution" if score >= 60
                 else "stressed" if score >= 40 else "critical")

        # Zeithorizont — priorisiert nach Dringlichkeit
        time_horizon = (
            "immediate" if state in ("critical",) or b.get("pressure_level") in ("extreme",)
            else "seconds" if state == "stressed"
            else "minutes" if state == "caution"
            else "hours_days" if e.get("longterm_risk_level") in ("critical", "high", "elevated")
            else "monitoring"
        )

        decomposed = {
            "consensus_base": a["health_detail"]["chi"],
            "pressure_penalty": p_b,
            "lending_penalty": p_c_risk + p_c_liq,
            "mev_penalty": p_d,
            "longterm_penalty": round(p_e, 2),
            "spike_bypass": is_extreme or has_critical_lending,
        }

        # CHI-ZERLEGUNG: trace every penalty's contribution
        chi_raw = a["health_detail"]["chi"]
        decomposed_sum = sum(
            v for k, v in decomposed.items()
            if k.endswith("_penalty") and isinstance(v, (int, float))
        )
        zone_raw = ("healthy" if chi_raw >= 80 else "caution" if chi_raw >= 60
                    else "stressed" if chi_raw >= 40 else "critical")
        zone_diverged = (zone_raw != state)
        detail_str = ", ".join(
            f"{k}={v}" for k, v in decomposed.items()
            if k.endswith("_penalty") and isinstance(v, (int, float)) and v > 0
        )
        method_label = os.getenv("AGGREGATION_METHOD", "sum")
        print(f"CHI-ZERLEGUNG chi_raw={chi_raw} gt_zone={zone_raw}  "
              f"penalties={{{detail_str}}}  additiv={decomposed_sum:.1f}  "
              f"aggregat({method_label})={penalty_total:.1f}  final={score}  state={state}"
              + ("  <-- WEICHT AB von Rohwert-Zone" if zone_diverged else ""))

        return {
            "score": score, "state": state, "time_horizon": time_horizon,
            "decomposed": decomposed,
        }

    # ─── Operations-Gating (4-Klassen) ───────────────────────────────

    # ─── Bundle-Execution-Advice (A/D-Integration) ──────────────────

    def _compute_bundle_advice(self, class_a, class_b, class_d, all_clear, profit_usd):
        """Berechnet Gas-Optimierung + Bundle-Submission-Empfehlung."""
        try:
            from agent_x_gas_optimizer import EVMDynamicOptimizer, SolanaPriorityOptimizer
            evm = EVMDynamicOptimizer()
            sol = SolanaPriorityOptimizer()

            oracle_imminent = class_d.get("oracle_update_imminent", False)
            leader_util = class_a.get("leader_utilization_pct", 50)
            mev_pressure = class_b.get("mev_pressure_index", 50)
            basefee = class_b.get("basefee_current_gwei", 22)

            evm_pf = evm.compute_optimal_priority_fee(
                current_basefee_gwei=basefee, mev_pressure_index=mev_pressure,
                oracle_update_expected=oracle_imminent,
            )
            profit_lamports = int(profit_usd / 180 * 1e9)
            sol_full = sol.full_optimization(
                expected_profit_lamports=profit_lamports,
                leader_utilization_pct=leader_util,
                oracle_update_expected=oracle_imminent,
            )
            should_submit = all_clear and profit_usd > 20

            return {
                "should_submit_bundle": should_submit,
                "ethereum": {
                    "optimal_priority_fee_gwei": evm_pf["optimal_priority_fee_gwei"],
                    "formula": evm_pf["formula"],
                    "oracle_boost_active": oracle_imminent,
                },
                "solana": {
                    "cu_price_microlamports": sol_full["cu_price_microlamports"],
                    "jito_tip_sol": sol_full["total_fee_sol"],
                    "leader_discount_active": leader_util < 30,
                    "profit_margin_pct": sol_full["profit_margin_pct"],
                },
                "cross_chain_recommendation": (
                    "SUBMIT_URGENT" if should_submit and oracle_imminent and leader_util < 30
                    else "SUBMIT_ETH_ORACLE_BOOST" if should_submit and oracle_imminent
                    else "SUBMIT_SOL_LEADER_DISCOUNT" if should_submit and leader_util < 30
                    else "SUBMIT_BOTH" if should_submit
                    else "HOLD"
                ),
            }
        except ImportError:
            return {"should_submit_bundle": False}

    def _determine_allowed_operations_4class(self, gs, a, b, d):
        ops = []
        ops.append({"operation": "read_positions", "allowed": True, "reason": "Basis"})
        ops.append({"operation": "monitor_health", "allowed": True, "reason": "Basis"})
        ops.append({"operation": "log_events", "allowed": True, "reason": "Basis"})

        score = gs["score"]

        ops.append({
            "operation": "execute_swaps",
            "allowed": score >= 40,
            "reason": "Swaps freigegeben" if score >= 40 else "Netzwerk zu instabil",
        })
        ops.append({
            "operation": "flash_loans",
            "allowed": (a["flash_loan_allowed"] and b["flash_loan_safe"]
                       and d["mev_risk"] != "extreme"),
            "reason": ("Flash-Loans freigegeben" if (a["flash_loan_allowed"] and b["flash_loan_safe"])
                       else "Gesperrt: Netzwerk/MEV-Druck zu hoch"),
        })
        ops.append({
            "operation": "arbitrage",
            "allowed": (score >= 60 and a["trusted_validators_available"]
                       and b["arbitrage_safe"]),
            "reason": ("Arbitrage freigegeben" if (score >= 60 and a["trusted_validators_available"])
                       else "Gesperrt: Score/Validator/Pressure"),
        })
        ops.append({
            "operation": "cross_chain_arbitrage",
            "allowed": score >= 70 and a["flash_loan_allowed"],
            "reason": "Cross-Chain freigegeben" if score >= 70 else "Gesperrt",
        })
        return ops

    # ─── Empfehlungen (4-Klassen) ────────────────────────────────────

    def _generate_recommendations_5class(self, gs, a, b, c, d, e):
        recs = self._generate_recommendations_4class(gs, a, b, c, d)

        # Klasse-E-Eskalation: Impact-gewichtete Langzeit-Empfehlungen
        escalation = e.get("action_escalation", "MONITOR")
        hours = e.get("hours_until_next_timelock", 9999)
        impact = e.get("max_impact_score", 0)

        if escalation == "HEDGE":
            recs.insert(0, {
                "priority": 2, "action": "HEDGE_TIMELOCK",
                "detail": f"Kritischer Timelock (impact={impact}) in {hours:.0f}h — sofort absichern!",
                "trigger": f"Impact≥7 + T-{hours:.0f}h",
            })
        elif escalation == "REDUCE":
            recs.insert(0, {
                "priority": 3, "action": "REDUCE_EXPOSURE",
                "detail": f"Timelock (impact={impact}) in {hours:.0f}h — Positionen reduzieren",
                "trigger": f"Impact-gewichtete Eskalation",
            })
        elif escalation == "PREPARE":
            recs.append({
                "priority": 5, "action": "PREPARE_TIMELOCK",
                "detail": f"Timelock in {hours:.0f}h — Watchlist prüfen, Liquidität vorbereiten",
                "trigger": f"T-{hours:.0f}h Vorbereitung",
            })

        # Unlock-Warnung
        unlock_usd = e.get("total_unlock_volume_usd", 0)
        days = e.get("days_until_next_unlock", 9999)
        if unlock_usd > 10_000_000 and days < 7:
            recs.append({
                "priority": 5, "action": "HEDGE_UNLOCK",
                "detail": f"${unlock_usd:,.0f} Token-Unlock in {days:.0f}d — Verkaufsdruck erwartet",
                "trigger": f">$10M Unlock in <7d",
            })

        return recs

    def _generate_recommendations_4class(self, gs, a, b, c, d):
        recs = []
        state = gs["state"]
        score = gs["score"]

        if state == "critical":
            recs.append({"priority": 1, "action": "EMERGENCY_SHUTDOWN",
                         "detail": "Alle DeFi-Positionen schließen, Kapital in Cold Storage",
                         "trigger": f"Global-State {score}/100"})
        elif state == "stressed":
            recs.append({"priority": 2, "action": "REDUCE_EXPOSURE",
                         "detail": "Nur Kapitalerhalt, keine neuen Positionen",
                         "trigger": f"Global-State {score}/100"})

        if b["pressure_level"] in ("extreme", "high"):
            recs.append({"priority": 5, "action": "MEV_PROTECTION_REQUIRED",
                         "detail": f"MEV-Druck {b['pressure_level']} — Flashbots/MEV-Boost zwingend ({b['priority_fee_p95_gwei']} gwei P95)",
                         "trigger": f"Pressure={b['combined_pressure_index']}"})

        if c.get("liquidatable", 0) > 0:
            recs.append({"priority": 3, "action": "LIQUIDATE_WATCHLIST",
                         "detail": f"{c['liquidatable']} Positionen liquidierbar, HF-Adjusted={c.get('critical_hf_adjusted',1.05)}",
                         "trigger": "HF <= 1.0"})

        if d.get("total_potential_profit_usd", 0) > 100 and a["defi_operations_allowed"] and b["arbitrage_safe"]:
            recs.append({"priority": 4, "action": "EXECUTE_ARBITRAGE",
                         "detail": f"${d['total_potential_profit_usd']:.0f} Profit — Arbitrage starten (Gas-P={b['gas_pressure_index']})",
                         "trigger": "Profit + Pressure-Safe"})

        if not recs:
            recs.append({"priority": 99, "action": "MONITOR", "detail": "Normalbetrieb", "trigger": "Standard"})

        return recs

    # ─── 5-Schritt-Szenario (erweitert) ──────────────────────────────

    def _run_6step_scenario(self, a, b, c, d, e, bots, trusted, hf_bump):
        return self._run_5step_scenario(a, b, c, d, bots, trusted, hf_bump)

    def _run_5step_scenario(self, a, b, c, d, bots, trusted, hf_bump):
        chi = a["health_detail"]["chi"]
        timing = a.get("timing", {}) or {}

        # Step 1: Timing (A3-1)
        ms = timing.get("next_slot_ms", 9999)
        step1 = {
            "source": "A3-1 (Timing)",
            "next_slot": timing.get("next_slot"),
            "ms_until_slot": ms,
            "actionable": ms is not None and ms < 30000,
            "message": f"Slot in {ms}ms" if ms and ms < 30000 else "Kein Timing",
        }

        # Step 2: Druckventile (B — NEU)
        step2 = {
            "source": "B (Druckventile)",
            "gas_pressure": b["gas_pressure_index"],
            "mev_pressure": b["mev_pressure_index"],
            "combined_pressure": b["combined_pressure_index"],
            "pressure_level": b["pressure_level"],
            "mev_spike": b["mev_spike_detected"],
            "flash_loan_safe": b["flash_loan_safe"],
            "arbitrage_safe": b["arbitrage_safe"],
            "message": (
                f"Druck {b['pressure_level']} (G={b['gas_pressure_index']} M={b['mev_pressure_index']}) — "
                f"Flash-Loan={'OK' if b['flash_loan_safe'] else 'RISKY'}, "
                f"Arbitrage={'OK' if b['arbitrage_safe'] else 'RISKY'}"
            ),
        }

        # Step 3: Flash-Loan (D2) — nur wenn Druck OK
        fl_ok = (a["flash_loan_allowed"] and b["flash_loan_safe"]
                and bots <= MAX_MEV_BOTS_FOR_DIRECT_TX
                and d.get("flash_loan_profitable", 0) > 0)
        step3 = {
            "source": "D2 (Flash-Loan)",
            "opportunities": d.get("flash_loan_opportunities", 0),
            "profitable": d.get("flash_loan_profitable", 0),
            "blocked_by_network": not a["flash_loan_allowed"],
            "blocked_by_pressure": not b["flash_loan_safe"],
            "blocked_by_mev": bots > MAX_MEV_BOTS_FOR_DIRECT_TX,
            "actionable": fl_ok,
            "message": "Flash-Loan-Chance erkannt" if fl_ok else "Flash-Loan blockiert",
        }

        # Step 4: Health-Factor (C2) — CONDITIONAL + B→C Bridge
        hf_suppressed = not a["hf_warning_allowed"] and c.get("alerts_fired", False)
        step4 = {
            "source": "C2 (Health-Factor)",
            "users_tracked": c.get("users_tracked", 0),
            "at_risk": c.get("at_risk", 0),
            "liquidatable": c.get("liquidatable", 0),
            "hf_warning_suppressed": hf_suppressed,
            "hf_warning_fired": a["hf_warning_allowed"] and c.get("alerts_fired", False),
            "critical_hf_original": 1.05,
            "critical_hf_adjusted": c.get("critical_hf_adjusted", 1.05),
            "hf_bump_from_pressure": hf_bump,
            "message": (
                f"HF-Adjusted={c.get('critical_hf_adjusted', 1.05)} "
                f"(Bump +{hf_bump} von Gas-Stress)" if hf_bump > 0
                else f"HF-Warnung UNTERDRÜCKT (CHI={chi}<{MIN_CHI_FOR_HF_WARNING})" if hf_suppressed
                else "Positionen sicher — Arbitrage freigegeben"
            ),
        }

        # Step 5: Routing (A3-3 + B3-1) — Priority-Fee aus Druckventilen
        pf = self._calculate_optimal_priority_fee(b, trusted)
        routing_ready = (
            step1["actionable"]
            and (step3["actionable"] or d.get("cross_pool_opportunities", 0) > 0)
            and not hf_suppressed
            and a["defi_operations_allowed"]
            and b["arbitrage_safe"]
        )

        step5 = {
            "source": "A3-3 + B3-1 (Routing + Priority-Fee)",
            "routing_ready": routing_ready,
            "optimal_priority_fee_gwei": pf,
            "trusted_validator": len(trusted or []) > 0,
            "message": (
                f"GO: Sende Tx mit {pf:.1f} gwei Priority — "
                f"{'vertrauenswürdiger' if trusted else 'unbekannter'} Validator"
                if routing_ready
                else "NO-GO: Bedingungen nicht optimal"
            ),
        }

        all_clear = routing_ready

        return {
            "step_1_timing": step1,
            "step_2_pressure": step2,
            "step_3_flash_loan": step3,
            "step_4_health_factor": step4,
            "step_5_routing": step5,
            "all_clear": all_clear,
            "summary": (
                "*** GO *** Alle 5 Steps grün — Arbitrage ausführen!"
                if all_clear
                else "NO-GO: " + ", ".join(
                    [f"Timing={'OK' if step1['actionable'] else 'WAIT'}",
                     f"Pressure={b['pressure_level']}",
                     f"FlashLoan={'OK' if step3['actionable'] else 'BLOCKED'}",
                     f"HF={'OK' if not hf_suppressed else 'SUPPRESSED'}",
                     f"Network={'OK' if a['defi_operations_allowed'] else 'DOWN'}"]
                )
            ),
        }

    def _calculate_optimal_priority_fee(self, b, trusted):
        """B3-1: Optimale Priority-Fee basierend auf Druckventil-Daten."""
        pf_p95 = b["priority_fee_p95_gwei"]
        pressure = b["pressure_level"]
        has_trusted = bool(trusted)

        if pressure in ("low", "moderate") and has_trusted:
            return 1.0
        elif pressure in ("low", "moderate"):
            return 2.0
        elif pressure == "elevated" and has_trusted:
            return pf_p95 * 0.7
        elif pressure == "elevated":
            return pf_p95 * 1.0
        elif pressure == "high":
            return pf_p95 * 1.2
        else:  # extreme
            return pf_p95 * 1.5

    # ─── Dashboard ──────────────────────────────────────────────────

    def dashboard(self) -> str:
        if not self.last_decision:
            return "Keine Entscheidung — rufe evaluate() zuerst auf."

        d = self.last_decision
        ud = d.get("unified_decision", {})
        sc = ud.get("scenario", {})
        sig = d.get("class_signals", {})

        lines = [
            "=" * 70,
            "  SYMBOLICS AGENT — 5-KLASSEN DASHBOARD",
            f"  {d.get('timestamp', '?')}",
            "=" * 70,
            "",
            f"  Global State: {ud.get('global_state', '?')} ({ud.get('global_state_score', '?')}/100)",
            f"  Zeithorizont: {ud.get('time_horizon', 'monitoring')}",
            f"  Kapital:      ${self.capital:,.0f}",
            "",
            "  KLASSEN-SIGNALE:",
        ]

        a = sig.get("klasse_a_consensus", {})
        b = sig.get("klasse_b_druckventile", {})
        c = sig.get("klasse_c_lending", {})
        d_sig = sig.get("klasse_d_defi", {})
        e_sig = sig.get("klasse_e_longterm", {})

        lines.append(f"    A (Konsensus): CHI={a.get('health_detail',{}).get('chi','?')}, Ops={'OK' if a.get('defi_operations_allowed') else 'BLOCKED'}")
        lines.append(f"    B (Druck):     G={b.get('gas_pressure_index','?')} M={b.get('mev_pressure_index','?')} → {b.get('pressure_level','?')}")
        lines.append(f"    C (Lending):   {c.get('at_risk',0)} at-risk, {c.get('liquidatable',0)} liq")
        lines.append(f"    D (DeFi):      {d_sig.get('flash_loan_profitable',0)} FL profit, {d_sig.get('mempool_bots',0)} MEV bots")
        lines.append(f"    E (Long-Term): {e_sig.get('pending_timelocks',0)} timelocks, {e_sig.get('upcoming_unlocks',0)} unlocks, {e_sig.get('longterm_risk_level','?')} risk")

        lines.append("")
        lines.append("  6-STEP-SZENARIO:")
        for step_name in ["step_1_longterm", "step_2_timing", "step_3_pressure", "step_4_flash_loan", "step_5_health_factor", "step_6_routing"]:
            s = sc.get(step_name, {})
            if s:
                lines.append(f"    {s.get('source', '?')}: {s.get('message', '?')}")

        lines.append("")
        lines.append(f"    GO/NO-GO: {'*** GO ***' if sc.get('all_clear') else 'NO-GO'}")
        lines.append(f"    {sc.get('summary', '')}")

        if ud.get("recommended_actions"):
            lines.append("")
            lines.append("  EMPFEHLUNGEN:")
            for rec in ud.get("recommended_actions", []):
                lines.append(f"    P{rec['priority']}: {rec['action']} — {rec['detail']}")

        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# INTEGRATIONSFUNKTION (4-Klassen)
# ═══════════════════════════════════════════════════════════════════════

def run_full_evaluation(
    capital: float = 100_000,
    # Klasse A
    consensus_health: float = 94.0,
    exit_queue: int = 42,
    reorg_depth: int = 0,
    # Klasse B — Druckventile
    gas_pressure: float = 50.0,
    mev_pressure: float = 50.0,
    block_pressure: float = 50.0,
    basefee_gwei: float = 21.0,
    pf_p95_gwei: float = 3.5,
    mev_spike: bool = False,
    # Andere
    mempool_bots: int = 1,
    trusted_validators: list[str] | None = None,
    user_positions: list[dict] | None = None,
    # Klasse E — Langzeit
    pending_timelocks: list[dict] | None = None,
    upcoming_unlocks: list[dict] | None = None,
    active_proposals: list[dict] | None = None,
    # Klasse A/D — Proaktives Timing
    leader_utilization_pct: float = 50.0,
    oracle_update_in_s: float = 999.0,
    expected_profit_usd: float = 500.0,
) -> dict:
    """Vollständige 5-Klassen-Evaluierung mit A/D-Timing.

    Dies ist DIE zentrale Funktion für externe Systeme (CLI, API, Cron).
    """
    agent = SymbolicsAgent(capital=capital)

    now_unix = time.time()
    eth_slots = [
        {"slot": 9_000_001 + i, "proposer_index": f"v_{100+i}",
         "unix_timestamp": now_unix + i * 12, "offset_ms": i * 12000}
        for i in range(10)
    ]

    flash_loans = [
        {"tx_hash": "0xfl", "protocol": "AaveV3", "loan_amount_usd": 2_000_000,
         "gross_profit_usd": 850.0, "flash_loan_fee_usd": 1800.0,
         "gas_cost_usd": 24.0, "net_profit_usd": 826.0, "profitable": True},
    ]
    cross_pool = [
        {"id": "cp1", "pair": "ETH-USDC", "gross_profit": 120.0,
         "gas_cost_usd": 24.0, "net_profit_usd": 96.0, "executable": True},
    ]
    positions = user_positions or [
        {"user_address": "0xAlice", "health_factor": 1.38, "total_debt_usd": 30000},
        {"user_address": "0xBob", "health_factor": 0.82, "total_debt_usd": 10000},
    ]

    # Class E demo data if none provided
    timelocks = pending_timelocks or [
        {"action": "setReserveBorrowRate", "timelock": "Aave_v3",
         "hours_until_executable": 23, "impact_score": 7,
         "params": {"new_rate": "5%", "old_rate": "3%"}},
    ]
    unlocks = upcoming_unlocks or [
        {"token": "ARB", "amount": 17_857_143, "amount_usd": 15_178_571,
         "days_until": 12, "unlock_type": "linear"},
    ]

    decision = agent.evaluate(
        consensus_health_index=consensus_health,
        exit_queue_length=exit_queue,
        reorg_depth=reorg_depth,
        eth_slots=eth_slots,
        trusted_validators=trusted_validators or ["validator_101"],
        gas_pressure_index=gas_pressure,
        mev_pressure_index=mev_pressure,
        block_pressure_index=block_pressure,
        basefee_current_gwei=basefee_gwei,
        priority_fee_p95_gwei=pf_p95_gwei,
        mev_spike_detected=mev_spike,
        health_factors=positions,
        flash_loan_opportunities=flash_loans,
        mempool_bots_count=mempool_bots,
        cross_pool_opportunities=cross_pool,
        pending_timelocks=timelocks,
        upcoming_unlocks=unlocks,
        active_proposals=active_proposals or [],
        leader_utilization_pct=leader_utilization_pct,
        oracle_update_in_s=oracle_update_in_s,
        expected_profit_usd=expected_profit_usd,
    )
    decision["dashboard"] = agent.dashboard()
    return decision


# ─── CLI ──────────────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════
# SymbolicsAgentOrchestrator — Echte Modul-Verdrahtung (v2.4.0)
# ═══════════════════════════════════════════════════════════════════════

class SymbolicsAgentOrchestrator:
    """Wrapper mit echten Modul-Importen aller 6 Klassen + Druckventile.

    Ersetzt die Inline-/Mock-Logik durch Aufrufe der tatsächlichen
    Fach-Engines und validiert den Laufzeit-Graphen via sys.modules.

    Usage:
        orch = SymbolicsAgentOrchestrator()
        orch.verify_wiring()  # Prüft ob alle Module geladen sind
        result = orch.evaluate_snapshot(data)
    """

    def __init__(self):
        self._engines = {}
        self._init_all_engines()

    def _init_all_engines(self):
        """Importiert alle Fach-Engines und speichert Referenzen."""
        imports = {
            # Klasse A — Konsensus
            "klasse_a1": ("agent_x_klasse_a_1_ingestion", "a1_1_beacon_listener"),
            "klasse_a2": ("agent_x_klasse_a_2_analytics", "a2_1_performance_analyst"),
            "klasse_a3": ("agent_x_klasse_a_3_strategie", "a3_2_health_classifier"),
            # Druckventile
            "pressure_b1": ("agent_x_klasse_b_pressure_b1_ingestion", "b1_1_evm_gas_listener"),
            "pressure_b2": ("agent_x_klasse_b_pressure_b2_analytics", "b2_1_gas_stress_index"),
            "pressure_b3": ("agent_x_klasse_b_pressure_b3_strategie", "b3_1_optimal_tx_timer"),
            # Gas-Optimizer + Bundle-Executor (Production Cores)
            "gas_optimizer": ("agent_x_gas_optimizer", "GasOptimizer"),
            "bundle_executor": ("agent_x_bundle_executor", "CrossChainBundleOrchestrator"),
            # Klasse B — Lending
            "lending_b1": ("agent_x_lending_b1_ingestion", "b1_1_evm_lending_subscriber"),
            "lending_b2": ("agent_x_lending_b2_risk", "b2_2_health_factor_calculator"),
            "lending_b3": ("agent_x_lending_b3_liquidation", "b3_1_liquidation_parser"),
            # Klasse C — DeFi-Events
            "defi_c1": ("agent_x_klasse_c_1_events", "c1_1_mempool_watcher"),
            "defi_c2": ("agent_x_klasse_c_2_flashloans", "c2_1_flash_loan_detector"),
            "defi_c3": ("agent_x_klasse_c_3_arbitrage", "c3_1_cross_pool_arbitrage"),
            # Klasse D — Oracle
            "oracle_d1": ("agent_x_klasse_d_1_ingestion", "d1_3_offchain_scout"),
            "oracle_d2": ("agent_x_klasse_d_2_analytics", "d2_1_heartbeat_timing"),
            "oracle_d3": ("agent_x_klasse_d_3_strategie", "d3_1_pre_update_alarm"),
            # Klasse E — DAO/Timelocks
            "gov_e1": ("agent_x_klasse_e_1_ingestion", "e1_1_timelock_listener"),
            "gov_e2": ("agent_x_klasse_e_2_3_strategie", "e2_1_parameter_simulator"),
            # Klasse F — Sentiment & Whales
            "sent_f1": ("agent_x_klasse_f_sentiment_whale", "f1_1_social_sentiment_tracker"),
            "sent_f2": ("agent_x_klasse_f_sentiment_whale", "f2_1_sentiment_aggregator"),
            # Monitoring + Backtest
            "metrics": ("agent_x_metrics", "AgentXMetrics"),
            "dashboard": ("agent_x_dashboard", "render_dashboard"),
            "backtest": ("agent_x_backtest", "BacktestRunner"),
        }

        loaded = 0
        for key, (mod_name, attr_name) in imports.items():
            try:
                mod = __import__(mod_name, fromlist=[attr_name])
                engine = getattr(mod, attr_name, None)
                if engine is not None:
                    self._engines[key] = engine
                    loaded += 1
                else:
                    logger.warning("Attribut %s nicht in %s gefunden", attr_name, mod_name)
            except Exception as e:
                logger.warning("Modul %s nicht geladen: %s", mod_name, e)

        logger.info("SymbolicsAgentOrchestrator: %d/%d Engines geladen", loaded, len(imports))

    def verify_wiring(self) -> dict:
        """Prüft ob alle erwarteten Module in sys.modules geladen sind."""
        expected = [
            "agent_x_lending_b1_ingestion", "agent_x_lending_b2_risk",
            "agent_x_lending_b3_liquidation", "agent_x_klasse_b_pressure_b1_ingestion",
            "agent_x_klasse_b_pressure_b2_analytics", "agent_x_klasse_b_pressure_b3_strategie",
            "agent_x_klasse_c_1_events", "agent_x_klasse_c_2_flashloans",
            "agent_x_klasse_c_3_arbitrage", "agent_x_klasse_d_1_ingestion",
            "agent_x_klasse_d_2_analytics", "agent_x_klasse_d_3_strategie",
            "agent_x_klasse_e_1_ingestion", "agent_x_klasse_e_2_3_strategie",
            "agent_x_klasse_f_sentiment_whale", "agent_x_gas_optimizer",
            "agent_x_bundle_executor", "agent_x_offchain_scout",
            "agent_x_aave_subscriber", "agent_x_beacon_client",
            "agent_x_solana_client", "agent_x_flashbots_client",
            "agent_x_jito_client", "agent_x_chainlink_client",
            "agent_x_pyth_client", "agent_x_governance_client",
            "agent_x_vesting_client", "agent_x_metrics",
            "agent_x_dashboard", "agent_x_backtest",
        ]

        import sys
        present = [m for m in expected if m in sys.modules]
        missing = [m for m in expected if m not in sys.modules]

        return {
            "total_expected": len(expected),
            "present_in_sys_modules": len(present),
            "missing": missing,
            "wiring_complete": len(missing) == 0,
            "engines_loaded": len(self._engines),
        }

    def evaluate_snapshot(self, snapshot_data: dict) -> dict:
        """Evaluiert einen Snapshot mit echten Modul-Aufrufen."""
        positions = snapshot_data.get("positions", [{
            "user_address": "0xAlice", "health_factor": 1.38, "total_debt_usd": 30000,
        }])

        # Lending HF via echtes Modul
        lending_b2 = self._engines.get("lending_b2")
        if lending_b2:
            try:
                hf_result = lending_b2(user_states=positions)
            except Exception:
                hf_result = {"status": "degraded"}
        else:
            hf_result = {"status": "not_loaded"}

        # Gas-Pressure via Druckventile
        pressure_b2 = self._engines.get("pressure_b2")
        if pressure_b2:
            try:
                gas_result = pressure_b2()
            except Exception:
                gas_result = {"gas_pressure_index": 50.0}
        else:
            gas_result = {"gas_pressure_index": 50.0}

        # Oracle via D2
        oracle_d2 = self._engines.get("oracle_d2")
        if oracle_d2:
            try:
                oracle_result = oracle_d2()
            except Exception:
                oracle_result = {"next_update_in_s": 999}
        else:
            oracle_result = {"next_update_in_s": 999}

        # Governance via E1
        gov_e1 = self._engines.get("gov_e1")
        if gov_e1:
            try:
                gov_result = gov_e1("scan")
            except Exception:
                gov_result = {"pending_actions": 0}
        else:
            gov_result = {"pending_actions": 0}

        # CHI-Berechnung aus echten Modul-Ergebnissen
        chi = 100.0
        if isinstance(hf_result, dict):
            users = hf_result.get("subagents", {}).get(
                "b2_2b_hf_computation", {}).get("users", [])
            min_hf = min(
                (u["health_factor"] for u in users
                 if isinstance(u.get("health_factor"), (int, float))),
                default=2.0,
            )
            if min_hf < 1.05:
                chi -= 35
            elif min_hf < 1.5:
                chi -= 15

        gas_idx = gas_result.get("gas_pressure_index", 50)
        if gas_idx > 80:
            chi -= 15
        elif gas_idx > 60:
            chi -= 8

        pending_actions = gov_result.get("pending_actions", 0)
        if pending_actions > 0:
            chi -= 5

        chi = max(0.0, round(chi, 1))

        return {
            "chi_score": chi,
            "risk_mode": "DEFENSIVE_LIMIT" if chi < 60 else "STANDARD",
            "modules_engaged": len(self._engines),
            "lending_hf_result": hf_result.get("status", "?"),
            "gas_pressure_result": gas_result.get("status", "?"),
            "oracle_result": oracle_result.get("status", "?"),
            "governance_result": gov_result.get("status", "?"),
        }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "evaluate"

    if cmd == "evaluate":
        r = run_full_evaluation(consensus_health=94.0, gas_pressure=45.0,
                                mev_pressure=30.0, mempool_bots=1,
                                trusted_validators=["validator_101"])
        print(r["dashboard"])

    elif cmd == "stress":
        r = run_full_evaluation(consensus_health=35.0, exit_queue=2500,
                                gas_pressure=92.0, mev_pressure=88.0,
                                block_pressure=90.0, mev_spike=True, mempool_bots=8)
        print(r["dashboard"])

    elif cmd == "hf_suppress":
        r = run_full_evaluation(consensus_health=65.0, gas_pressure=45.0,
                                mev_pressure=30.0, mempool_bots=1,
                                user_positions=[
                                    {"user_address": "0xBob", "health_factor": 0.82, "total_debt_usd": 10000},
                                ])
        print(r["dashboard"])

    elif cmd == "gas_stress":
        # Gas-Stress → HF-Bump
        r = run_full_evaluation(consensus_health=90.0, gas_pressure=88.0,
                                mev_pressure=60.0, block_pressure=82.0,
                                mempool_bots=3, mev_spike=True)
        print(r["dashboard"])

    elif cmd == "arbitrage_window":
        r = run_full_evaluation(consensus_health=94.0, gas_pressure=25.0,
                                mev_pressure=15.0, block_pressure=30.0,
                                mempool_bots=0, mev_spike=False,
                                trusted_validators=["validator_101"])
        print(r["dashboard"])

    elif cmd == "longterm":
        # Langzeit-Szenario: Timelock + Unlocks
        r = run_full_evaluation(
            consensus_health=88.0, gas_pressure=40.0, mev_pressure=30.0,
            pending_timelocks=[
                {"action": "setReserveBorrowRate", "timelock": "Aave_v3",
                 "hours_until_executable": 5, "impact_score": 7},
                {"action": "setCollateralFactor", "timelock": "Compound",
                 "hours_until_executable": 48, "impact_score": 8},
            ],
            upcoming_unlocks=[
                {"token": "ARB", "amount": 17_857_143, "amount_usd": 15_178_571, "days_until": 12},
                {"token": "OP", "amount": 15_625_000, "amount_usd": 22_656_250, "days_until": 18},
            ],
        )
        print(r["dashboard"])

    elif cmd == "full_scan":
        print("=== Agent X — 5-Klassen Full Scan ===")
        print()
        try:
            from agent_x_klasse_e_1_ingestion import e1_1_timelock_listener, e1_2_vesting_monitor, e1_3_proposal_scanner
            e11 = e1_1_timelock_listener("scan")
            e12 = e1_2_vesting_monitor("scan")
            e13 = e1_3_proposal_scanner("scan")
            tl = e11.get("subagents", {}).get("e1_1c_timeline", {}).get("pending", [])
            ul = e12.get("subagents", {}).get("e1_2c_unlock_countdown", {}).get("by_token", [])
            ap = e13.get("subagents", {}).get("e1_3c_impact_estimator", {}).get("proposals", [])
        except ImportError:
            tl, ul, ap = [], [], []
        r = run_full_evaluation(pending_timelocks=tl, upcoming_unlocks=ul, active_proposals=ap)
        print(r["dashboard"])

    elif cmd == "live_arbitrage":
        # Best-Case: Oracle-Update + Leader-Discount
        r = run_full_evaluation(
            consensus_health=94.0, gas_pressure=25.0, mev_pressure=20.0,
            mempool_bots=0, mev_spike=False,
            trusted_validators=["validator_101"],
            leader_utilization_pct=22.0,  # Klasse A: Leader läuft kühl
            oracle_update_in_s=3.0,        # Klasse D: Update in 3 Sekunden!
            expected_profit_usd=800.0,
        )
        print(r["dashboard"])
        # Bundle-Advice anzeigen
        ba = r.get("unified_decision", {}).get("bundle_advice", {})
        if ba:
            print(f"\n  BUNDLE ADVICE: {ba.get('cross_chain_recommendation', 'HOLD')}")
            eth = ba.get("ethereum", {})
            sol = ba.get("solana", {})
            print(f"    ETH: {eth.get('optimal_priority_fee_gwei',0):.1f} gwei (Oracle-Boost: {eth.get('oracle_boost_active')})")
            print(f"    SOL: CU={sol.get('cu_price_microlamports',0)} µLamports, Tip={sol.get('jito_tip_sol',0):.6f} SOL (Leader-Discount: {sol.get('leader_discount_active')})")

    elif cmd == "oracle_timing":
        # Oracle-Update-Timing-Simulation
        for secs in [60, 10, 3]:
            r = run_full_evaluation(oracle_update_in_s=secs, expected_profit_usd=500)
            ba = r.get("unified_decision", {}).get("bundle_advice", {})
            print(f"Oracle in {secs:3.0f}s: {ba.get('cross_chain_recommendation', 'HOLD'):30s} "
                  f"ETH-PF={ba.get('ethereum',{}).get('optimal_priority_fee_gwei',0):5.1f} gwei "
                  f"SOL-CU={ba.get('solana',{}).get('cu_price_microlamports',0):6d} µLamports")

    else:
        print(f"Verwendung: {sys.argv[0]} [evaluate|stress|hf_suppress|gas_stress|arbitrage_window|longterm|full_scan|live_arbitrage|oracle_timing]")
