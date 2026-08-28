"""A1 Orchestrator — 9-agent regime drift swarm (monitoring only)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from prototypes.raas_paper_trading.regime_drift import definition_hash
from prototypes.raas_paper_trading.regime_swarm.agents import (
    AuditAlertAgent,
    CoolingOffTracker,
    DataIngestorAgent,
    DriftClassifierAgent,
    FeatureEngineerAgent,
    KSTestAgent,
    StrategyAdapterAgent,
    WassersteinAgent,
    WindowManagerAgent,
)
from prototypes.raas_paper_trading.regime_swarm.types import (
    COOLING_OFF_CYCLES,
    SWARM_SCHEMA,
    DriftClassification,
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
    _cooling: Optional[CoolingOffTracker] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.a5.seed = self.seed
        self.a9.audit_path = self.audit_path
        self._cooling = CoolingOffTracker(self.cooling_path)

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
        if len(prices) < 2 * 30:
            return {
                "schema": SWARM_SCHEMA,
                "cycle_id": cid,
                "symbol": symbol,
                "status": "INSUFFICIENT_DATA",
                "n_prices": len(prices),
                "definition_hash": definition_hash(),
                "agents": agent_log,
            }

        agent_log["A3"] = self.a3.run(prices)
        matrix = self.a3.build_matrix(prices)
        if matrix is None:
            return {
                "schema": SWARM_SCHEMA,
                "cycle_id": cid,
                "symbol": symbol,
                "status": "INSUFFICIENT_WINDOWS",
                "n_prices": len(prices),
                "definition_hash": definition_hash(),
                "agents": agent_log,
            }

        agent_log["A4"] = self.a4.run(matrix)
        ks_results, ks_meta = self.a5.run(matrix)
        agent_log["A5"] = ks_meta

        p_min = ks_meta["ks_p_value_min"]
        w_result, w_meta = self.a6.run(matrix)
        agent_log["A6"] = w_meta

        # Resource gate: skip deep classify only if clearly stable
        if p_min > 0.05 and w_result.mean_w1 < 1e-8:
            classification_meta = {
                "agent": "A7_DriftClassifier",
                "regime_shift_index": 10.0,
                "regime_flag": 0,
                "classified_regime": "STABLE_SIDEWAYS",
                "skipped_deep_path": True,
            }
            classification = DriftClassification(
                regime_shift_index=10.0,
                regime_flag=0,
                classified_regime="STABLE_SIDEWAYS",
                drift_type="none",
                ks_p_value_min=p_min,
                anomaly_count=0,
                mean_shift_sigma=0.0,
            )
        else:
            classification, classification_meta = self.a7.run(ks_results, w_result, matrix)
        agent_log["A7"] = classification_meta

        advisory, a8_meta = self.a8.run(classification)
        agent_log["A8"] = a8_meta

        streak, confirmed = self._cooling.update(symbol, classification.regime_flag)

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
        deviation = (
            f"Verteilung weicht ab (KS p_min={classification.ks_p_value_min:.4f}, "
            f"W₁ mean={w_result.mean_w1:.4f}, RSI={classification.regime_shift_index:.1f})."
            if classification.regime_flag > 0
            else "Keine signifikante Abweichung zur Referenz-Baseline."
        )

        drift_summary = {
            "ks_p_value_min": classification.ks_p_value_min,
            "wasserstein_distance": w_result.mean_w1,
            "regime_shift_index": classification.regime_shift_index,
            "classified_regime": classification.classified_regime,
            "drift_type": classification.drift_type,
            "affected_features": affected,
            "regime_flag": classification.regime_flag,
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
            cooling_off_cycles_required=COOLING_OFF_CYCLES,
            cooling_off_cycles_seen=streak,
            regime_flag_confirmed=confirmed,
            hash_checksum="",
            agents=agent_log,
        )
        audit_entry = result.to_audit_dict()
        audit_entry["definition_hash"] = definition_hash()
        audit_entry["worm_path"] = str(worm_path)
        audit_entry["status"] = "COMPLETE"

        if write_audit and alert_level != "OK":
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
            symbol = "UNKNOWN"
            for suffix in ("btcusdc", "ethusdc", "solusdc"):
                if suffix in path.as_posix().lower():
                    symbol = suffix.upper()
                    break
            reports.append(
                self.run_cycle(worm_path=path, symbol=symbol, write_audit=write_audit)
            )
        return reports
