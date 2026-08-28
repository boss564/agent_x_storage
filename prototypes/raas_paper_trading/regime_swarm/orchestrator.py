"""A1 Orchestrator — 9-agent regime drift swarm (monitoring only)."""
from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from prototypes.raas_paper_trading.regime_drift import definition_hash
from prototypes.raas_paper_trading.regime_swarm.adaptive import (
    AdaptiveCoolingOffManager,
    StuckUnreliableTracker,
)
from prototypes.raas_paper_trading.regime_swarm.agents import (
    AuditAlertAgent,
    DataIngestorAgent,
    DriftClassifierAgent,
    FeatureEngineerAgent,
    KSTestAgent,
    StrategyAdapterAgent,
    WassersteinAgent,
    WindowManagerAgent,
)
from prototypes.raas_paper_trading.regime_swarm.gates.config import InfraGatesConfig
from prototypes.raas_paper_trading.regime_swarm.types import (
    REAL_DRIFT_COOLING_THRESHOLD,
    SWARM_SCHEMA,
    UNRELIABLE_COOLING_THRESHOLD,
    SwarmCycleResult,
)


@dataclass
class RegimeSwarmOrchestrator:
    """A1 — coordinates A2→A9 pipeline per symbol / WORM."""

    audit_path: Path = Path("logs/worm/regime_drift_audit.jsonl")
    cooling_path: Path = Path("logs/worm/regime_swarm_cooling.jsonl")
    seed: int = 42
    a2: DataIngestorAgent = field(default_factory=DataIngestorAgent)
    a3: FeatureEngineerAgent = field(default_factory=FeatureEngineerAgent)
    a4: WindowManagerAgent = field(default_factory=WindowManagerAgent)
    a5: KSTestAgent = field(default_factory=KSTestAgent)
    a6: WassersteinAgent = field(default_factory=WassersteinAgent)
    a7: DriftClassifierAgent = field(default_factory=DriftClassifierAgent)
    a8: StrategyAdapterAgent = field(default_factory=StrategyAdapterAgent)
    a9: AuditAlertAgent = field(default_factory=AuditAlertAgent)
    infra_gates: InfraGatesConfig = field(default_factory=InfraGatesConfig.from_env)
    _cooling: Optional[AdaptiveCoolingOffManager] = field(default=None, repr=False)
    _stuck: StuckUnreliableTracker = field(default_factory=StuckUnreliableTracker)
    infrastructure_healthy: bool = True
    _a0: Any = field(default=None, repr=False)
    _a25: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.a5.seed = self.seed
        self.a9.audit_path = self.audit_path
        self._cooling = AdaptiveCoolingOffManager(path=self.cooling_path)
        if self.infra_gates.enabled:
            from prototypes.raas_paper_trading.regime_swarm.gates.core_sanity_adapter import (
                CoreSanityAdapter,
            )
            from prototypes.raas_paper_trading.regime_swarm.gates.transport_boundary import (
                TransportBoundaryGate,
            )

            self._a0 = CoreSanityAdapter(
                max_price_change_pct=self.infra_gates.g0_max_price_change_pct,
                max_spread_pct=self.infra_gates.g0_max_spread_pct,
            )
            self._a25 = TransportBoundaryGate(
                max_latency_ms=self.infra_gates.g25_max_latency_ms,
            )

    def _infra_audit_block(
        self,
        *,
        cid: str,
        symbol: str,
        worm_path: Path,
        agent_log: Dict[str, Any],
        infrastructure: Dict[str, Any],
        write_audit: bool,
    ) -> Dict[str, Any]:
        self.infrastructure_healthy = False
        infrastructure["infrastructure_healthy"] = False
        audit_entry: Dict[str, Any] = {
            "schema": SWARM_SCHEMA,
            "cycle_id": cid,
            "symbol": symbol,
            "status": "INFRASTRUCTURE_BLOCKED",
            "infrastructure": infrastructure,
            "drift_summary": "NOT_COMPUTED",
            "definition_hash": definition_hash(),
            "worm_path": str(worm_path),
            "agents": agent_log,
        }
        if write_audit:
            agent_log["A9"] = self.a9.run(audit_entry)
        else:
            agent_log["A9"] = {"agent": "A9_AuditAlert", "status": "INFRASTRUCTURE_FAILED"}
        audit_entry["agents"] = agent_log
        return audit_entry

    def _run_infrastructure_gates(
        self,
        *,
        prices: List[float],
        ingest: Dict[str, Any],
        agent_log: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.infra_gates.enabled or self._a0 is None:
            return None

        infrastructure: Dict[str, Any] = {
            "g0_core_sanity": "SKIPPED",
            "g25_transport_boundary": "SKIPPED",
            "infrastructure_healthy": True,
        }

        if not prices:
            infrastructure["g0_core_sanity"] = "SKIPPED (no prices)"
            infrastructure["g25_transport_boundary"] = "SKIPPED (no data)"
            agent_log["A0"] = infrastructure["g0_core_sanity"]
            agent_log["A2.5"] = infrastructure["g25_transport_boundary"]
            return infrastructure

        ref_price = prices[-2] if len(prices) >= 2 else None
        tick = {"price": prices[-1]}
        a0_ok, a0_result = self._a0.validate_tick(tick, reference_price=ref_price)
        agent_log["A0"] = a0_result.to_audit_dict()
        infrastructure["g0_core_sanity"] = a0_result.message
        if not a0_ok:
            infrastructure["infrastructure_healthy"] = False
            return infrastructure

        transport_meta = ingest.get("transport_meta") or {}
        if transport_meta and self._a25 is not None:
            a25_ok, a25_result = self._a25.validate_frame(transport_meta)
            agent_log["A2.5"] = a25_result.to_audit_dict()
            infrastructure["g25_transport_boundary"] = a25_result.message
            if not a25_ok:
                infrastructure["infrastructure_healthy"] = False
                return infrastructure
        else:
            agent_log["A2.5"] = "SKIPPED (no transport metadata in WORM)"
            infrastructure["g25_transport_boundary"] = agent_log["A2.5"]

        self.infrastructure_healthy = True
        return infrastructure

    def run_cycle(
        self,
        *,
        worm_path: Path,
        symbol: str,
        cycle_id: Optional[str] = None,
        write_audit: bool = True,
    ) -> Dict[str, Any]:
        """Single swarm cycle for one WORM file."""
        cid = cycle_id or f"SWARM-{uuid.uuid4().hex[:8].upper()}"
        agent_log: Dict[str, Any] = {}

        ingest = self.a2.run(worm_path)
        agent_log["A2"] = ingest
        prices = self.a2.load_prices(worm_path)

        infrastructure = self._run_infrastructure_gates(
            prices=prices,
            ingest=ingest,
            agent_log=agent_log,
        )
        if infrastructure is not None and not infrastructure.get("infrastructure_healthy", True):
            return self._infra_audit_block(
                cid=cid,
                symbol=symbol,
                worm_path=worm_path,
                agent_log=agent_log,
                infrastructure=infrastructure,
                write_audit=write_audit,
            )

        if len(prices) < 2 * 30:
            out: Dict[str, Any] = {
                "schema": SWARM_SCHEMA,
                "cycle_id": cid,
                "symbol": symbol,
                "status": "INSUFFICIENT_DATA",
                "n_prices": len(prices),
                "definition_hash": definition_hash(),
                "agents": agent_log,
            }
            if infrastructure is not None:
                out["infrastructure"] = infrastructure
            return out

        agent_log["A3"] = self.a3.run(prices)
        matrix = self.a3.build_matrix(prices)
        if matrix is None:
            out = {
                "schema": SWARM_SCHEMA,
                "cycle_id": cid,
                "symbol": symbol,
                "status": "INSUFFICIENT_WINDOWS",
                "n_prices": len(prices),
                "definition_hash": definition_hash(),
                "agents": agent_log,
            }
            if infrastructure is not None:
                out["infrastructure"] = {
                    **infrastructure,
                    "infrastructure_healthy": True,
                }
            return out

        agent_log["A4"], iid_status = self.a4.run(matrix, symbol=symbol)
        ks_results, ks_meta = self.a5.run(matrix)
        agent_log["A5"] = ks_meta

        w_result, w_meta = self.a6.run(matrix)
        agent_log["A6"] = w_meta

        classification, classification_meta, pre_reg = self.a7.run(
            ks_results, w_result, matrix, iid_status=iid_status
        )
        agent_log["A7"] = classification_meta

        cooling_decision = self._cooling.update(
            symbol,
            regime_flag=classification.regime_flag,
            classified_regime=classification.classified_regime,
        )
        agent_log["A1"] = {"orchestrator_decision": cooling_decision}

        advisory, a8_meta = self.a8.run(
            classification,
            symbol=symbol,
            cooling_decision=cooling_decision,
        )
        agent_log["A8"] = a8_meta

        confirmed = bool(cooling_decision.get("confirmed"))
        streak = int(
            cooling_decision.get("real_drift_counter", 0)
            or cooling_decision.get("unreliable_counter", 0)
        )

        affected = [r.feature for r in ks_results if r.drift_detected]
        alert_level = "OK"
        if classification.regime_flag == 1:
            alert_level = "WARNING"
        elif classification.regime_flag >= 2:
            alert_level = "CRITICAL" if confirmed else "WARNING_PENDING_COOLDOWN"

        sig = (
            f"α < {0.01:.2f} (kritisch)"
            if classification.ks_p_value_min < 0.01
            else f"α ≥ {0.01:.2f} (nicht kritisch)"
        )
        if classification.iid_unreliable:
            deviation = (
                f"Drift signalisiert (flag={classification.regime_flag}), aber Raten-Vergleich "
                f"gegen i.i.d.-Tabelle unzuverlässig (ρ={iid_status.rho:.2f}, "
                f"n_eff={iid_status.n_eff:.1f}, W₁_std={classification.standardized_drift:.2f})."
            )
        elif classification.regime_flag > 0:
            deviation = (
                f"Verteilung weicht ab (KS p_min={classification.ks_p_value_min:.4f}, "
                f"W₁ mean={w_result.mean_w1:.4f}, RSI={classification.regime_shift_index:.1f})."
            )
        else:
            deviation = "Keine signifikante Abweichung zur Referenz-Baseline."

        ref_ret = matrix.baseline.get("log_return_pct", [])
        baseline_std = statistics.pstdev(ref_ret) if len(ref_ret) > 1 else 1e-12
        if baseline_std < 1e-12:
            baseline_std = 1e-12

        window_meta = (agent_log.get("A4") or {}).get("window_metadata", {})

        drift_summary = {
            "ks_p_value_min": classification.ks_p_value_min,
            "wasserstein_distance": w_result.mean_w1,
            "baseline_std": round(baseline_std, 8),
            "standardized_drift": round(classification.standardized_drift, 4),
            "regime_shift_index": classification.regime_shift_index,
            "classified_regime": classification.classified_regime,
            "drift_type": classification.drift_type,
            "affected_features": affected,
            "regime_flag": classification.regime_flag,
            "allow_amendment": classification.allow_amendment,
            "iid_unreliable": classification.iid_unreliable,
            "bonferroni_hit": classification.bonferroni_hit,
            "bonferroni_alpha_used": round(classification.effective_alpha_used, 6),
            "pre_reg_caveat_active": classification.pre_reg_caveat_active,
        }

        pre_reg_dict = pre_reg.to_dict() if pre_reg else {"triggered": False}
        final_action = a8_meta.get("final_action", "PARAMETER_UNCHANGED")
        compliance = self._stuck.evaluate(symbol, classification.classified_regime)

        swarm_message = {
            "cycle_id": cid,
            "classification": {
                "regime_flag": classification.regime_flag,
                "classified_regime": classification.classified_regime,
                "allow_amendment": classification.allow_amendment,
                "bonferroni_alpha_used": round(classification.effective_alpha_used, 6),
                "pre_reg_caveat_active": classification.pre_reg_caveat_active,
            },
            "window_metadata": window_meta,
            "orchestrator_decision": cooling_decision,
            "strategy_state": a8_meta.get("strategy_state", {}),
            "compliance": compliance,
        }

        result = SwarmCycleResult(
            cycle_id=cid,
            symbol=symbol,
            agent_trigger="A7_Classifier",
            drift_summary=drift_summary,
            statistical_significance=sig,
            deviation_from_backtest=deviation,
            adaptive_action=advisory.to_dict(),
            alert_level=alert_level,
            cooling_off_cycles_required=REAL_DRIFT_COOLING_THRESHOLD,
            cooling_off_cycles_seen=streak,
            regime_flag_confirmed=confirmed,
            hash_checksum="",
            pre_reg_intervention=pre_reg_dict,
            final_action=final_action,
            agents=agent_log,
        )
        audit_entry = result.to_audit_dict()
        audit_entry["definition_hash"] = definition_hash()
        audit_entry["worm_path"] = str(worm_path)
        audit_entry["status"] = "COMPLETE"
        audit_entry["swarm_message"] = swarm_message
        if infrastructure is not None:
            audit_entry["infrastructure"] = {
                **infrastructure,
                "infrastructure_healthy": True,
            }
        audit_entry = self.a9.enrich_compliance(audit_entry, compliance=compliance)

        write_audit_now = write_audit and (
            alert_level != "OK"
            or pre_reg_dict.get("triggered")
            or compliance.get("compliance_alert") == "REVIEW_REQUIRED"
        )
        if write_audit_now:
            a9_out = self.a9.run(audit_entry)
            agent_log["A9"] = a9_out
            result.hash_checksum = a9_out["hash_checksum"]
        else:
            result.hash_checksum = AuditAlertAgent()._checksum(audit_entry)
            agent_log["A9"] = {"agent": "A9_AuditAlert", "skipped": alert_level == "OK"}

        out = result.to_audit_dict()
        out["timestamp"] = audit_entry.get("timestamp")
        out["hash_checksum"] = result.hash_checksum
        out["agents"] = agent_log
        out["status"] = "COMPLETE"
        out["definition_hash"] = definition_hash()
        out["worm_path"] = str(worm_path)
        out["final_action"] = final_action
        out["pre_reg_intervention"] = pre_reg_dict
        out["swarm_message"] = swarm_message
        out["cooling_off"]["unreliable_threshold"] = UNRELIABLE_COOLING_THRESHOLD
        if infrastructure is not None:
            out["infrastructure"] = {
                **infrastructure,
                "infrastructure_healthy": True,
            }
        return out

    def run_worm_dir(
        self,
        root: Path,
        *,
        write_audit: bool = True,
    ) -> List[Dict[str, Any]]:
        from prototypes.raas_paper_trading.regime_drift import discover_worm_files

        reports: List[Dict[str, Any]] = []
        for path in discover_worm_files(root):
            sym = "UNKNOWN"
            for suffix in ("btcusdc", "ethusdc", "solusdc"):
                if suffix in path.as_posix().lower():
                    sym = suffix.upper()
                    break
            reports.append(
                self.run_cycle(worm_path=path, symbol=sym, write_audit=write_audit)
            )
        return reports
