"""Wave 38 first --live cycle: freeze → capture → 6→9 → GoBD → EventBus.

Operative only (WAVE38_LIVE_PREREG §1). Never mutates sealed Bridge artifacts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bridge_stufe_a_v3_pipeline import encode_z_neu_tertile  # noqa: E402

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import CANDIDATE_IDS, DiagnosticConfig
from agents_b2g.diagnostic.cte_math import OccupancyBundle
from agents_b2g.diagnostic.gatekeeper_dispatcher_agent import GatekeeperDispatcherAgent
from agents_b2g.diagnostic.ingestion_rpc import LiveRpcTransport
from agents_b2g.diagnostic.intent_and_stablecoin_agent import IntentAndStablecoinAgent
from agents_b2g.diagnostic.liquidation_cascade_agent import LiquidationCascadeAgent
from agents_b2g.diagnostic.live_ingestion import (
    prepare_live_address_books,
    rebuild_ingest_from_sqlite,
    run_live_ingestion,
)
from agents_b2g.diagnostic.live_prereg import load_wave38_thresholds
from agents_b2g.diagnostic.live_window import (
    FrozenLiveWindow,
    freeze_live_window,
    load_frozen_window,
)
from agents_b2g.diagnostic.mev_capture_agent import MEVCaptureAgent
from agents_b2g.diagnostic.oracle_signal_agent import OracleSignalAgent
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard
from agents_b2g.diagnostic.subagents.diagnostic_report_composer import (
    DiagnosticReportComposer,
)
from agents_b2g.diagnostic.subagents.intent_stable_capture import IntentStableConfig
from agents_b2g.diagnostic.subagents.liquidation_capture import LiquidationConfig
from agents_b2g.diagnostic.subagents.mev_capture import MEVConfig
from agents_b2g.diagnostic.subagents.oracle_capture import OracleConfig
from agents_b2g.diagnostic.types import AgentEnvelope, DiagnosticRunInput
from agents_b2g.diagnostic.wave38_analysis_pipeline import Wave38AnalysisPipeline
from agents_b2g.diagnostic.wave38_capture_pipeline import (
    CaptureStageResult,
    load_occupancy_archive,
    occupancy_from_events_by_family,
)
from agents_b2g.diagnostic.wave38_full_pipeline import ENVELOPE_REQUIRED_KEYS
from agents_b2g.event_bus import EventBus


EVENT_SUBJECT = "wave38.diagnostic.signal"


def _publish_eventbus(
    *,
    user_id: str,
    envelope: dict[str, Any],
    agent_response: dict[str, Any],
) -> dict[str, Any]:
    live = DiagnosticConfig.wave38_live_root(user_id)
    audit = live / "eventbus_audit.jsonl"
    bus = EventBus(audit_log=audit)
    payload = {
        "wave": 38,
        "consumer_hints": {
            "wave24_trading": {
                "released_signals": envelope.get("released_signals"),
                "s_tau": envelope.get("s_tau"),
            },
            "wave21_skynet": {
                "causal_score": envelope.get("collapse_info"),
                "cleansing_workers": (envelope.get("collapse_info") or {}).get(
                    "cleansing_workers"
                )
                if isinstance(envelope.get("collapse_info"), dict)
                else None,
            },
            "wave28_defense": {
                "blocked_signals": envelope.get("blocked_signals"),
                "cause": envelope.get("cause"),
            },
        },
        "signal_envelope": envelope,
        "agent_x_response": {
            "status": agent_response.get("status"),
            "job_id": agent_response.get("job_id"),
            "error": agent_response.get("error"),
            "artifacts": agent_response.get("artifacts"),
            "logs": agent_response.get("logs"),
        },
        "interpretation": "OPERATIONAL_SIGNAL_ONLY",
    }
    bus.publish(EVENT_SUBJECT, payload)
    return {
        "subject": EVENT_SUBJECT,
        "msg_id": bus.message_count,
        "audit_log": str(audit),
    }


def assemble_live_bundle(
    captures: dict[str, CaptureStageResult],
    *,
    bridge_eth: list[int],
    bridge_gnosis: list[int],
    z_alt_raw: list[list[int]],
    n_bins: int,
    window_start_ts: int,
    source: str,
) -> OccupancyBundle:
    z_neu_occ: dict[str, list[int]] = {}
    for cid, stage_key in (
        ("chainlink", "chainlink"),
        ("mev_cluster", "mev_cluster"),
        ("liquidations", "liquidations"),
    ):
        path = captures[stage_key].occupancy_path
        if not path:
            raise ValueError(f"{cid}: occupancy_path missing")
        body = load_occupancy_archive(path)
        occ = [int(x) for x in body["occupancy"]]
        if len(occ) < n_bins:
            occ = occ + [0] * (n_bins - len(occ))
        else:
            occ = occ[:n_bins]
        z_neu_occ[cid] = occ

    is_meta = captures["intent_stablecoin"].metadata
    events_path = is_meta.get("events_path")
    if not events_path or not Path(events_path).is_file():
        raise ValueError("intent_stablecoin events_path missing")
    events: list[dict[str, Any]] = []
    with Path(events_path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    z_neu_occ["intent_relayers"] = occupancy_from_events_by_family(
        events, "intent_relayers", n_bins=n_bins, window_start_ts=window_start_ts
    )
    z_neu_occ["stablecoin_mint_burn"] = occupancy_from_events_by_family(
        events, "stablecoin_mint_burn", n_bins=n_bins, window_start_ts=window_start_ts
    )

    for cid in CANDIDATE_IDS:
        if cid not in z_neu_occ:
            raise ValueError(f"missing {cid}")

    # Align bridge / Z_alt lengths
    eth = list(bridge_eth[:n_bins]) + [0] * max(0, n_bins - len(bridge_eth))
    gno = list(bridge_gnosis[:n_bins]) + [0] * max(0, n_bins - len(bridge_gnosis))
    z_alt = []
    for series in z_alt_raw:
        s = list(series[:n_bins]) + [0] * max(0, n_bins - len(series))
        z_alt.append(encode_z_neu_tertile(s))

    while len(z_alt) < 3:
        z_alt.append([0] * n_bins)
    z_alt = z_alt[:3]

    z_neu_ter = {cid: encode_z_neu_tertile(z_neu_occ[cid]) for cid in CANDIDATE_IDS}
    if source.startswith("reference"):
        raise ValueError("live bundle source must not be reference-*")
    return OccupancyBundle(
        bridge_eth=eth,
        bridge_gnosis=gno,
        z_alt=z_alt,
        z_neu_occ=z_neu_occ,
        z_neu_ter=z_neu_ter,
        candidate_ids=CANDIDATE_IDS,
        source=source,
    )


class Wave38LivePipeline:
    """First --live operational cycle (3d-ix)."""

    def __init__(
        self,
        user_id: str = "wave38",
        *,
        ethical_orchestrator: Any | None = None,
    ):
        from agents_b2g.ethical_boundary import EthicalBoundaryOrchestrator

        self.user_id = user_id
        self.oracle = OracleSignalAgent(user_id)
        self.mev = MEVCaptureAgent(user_id)
        self.liq = LiquidationCascadeAgent(user_id)
        self.intent_stable = IntentAndStablecoinAgent(user_id)
        orch = ethical_orchestrator or EthicalBoundaryOrchestrator(user_id)
        self.ethical_orchestrator = orch
        self.analysis = Wave38AnalysisPipeline(
            user_id,
            ethical_orchestrator=orch,
        )
        self.gatekeeper = GatekeeperDispatcherAgent(
            user_id,
            ethical_orchestrator=orch,
        )
        self.report = DiagnosticReportComposer(user_id)
        self.reference_guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)

    def freeze_window(self, *, job_id: str = "live-first", force: bool = False) -> FrozenLiveWindow:
        return freeze_live_window(user_id=self.user_id, job_id=job_id, force=force)

    def run_live(
        self,
        *,
        job_id: str = "live-first",
        mev_stride: int = 120,
        mev_max_blocks: int | None = 8_000,
        capture_tail_days: int | None = 10,
        capture_resume: bool = False,
        capture_resume_from_target: int | None = None,
        require_etherscan: bool = False,
        skip_capture: bool = False,
        ingest_result: Any | None = None,
    ) -> AgentEnvelope:
        thresholds = load_wave38_thresholds()
        window = load_frozen_window(user_id=self.user_id)
        self.reference_guard.verify_unchanged()
        ref_before = self.reference_guard.compute_hashes()

        prepare_live_address_books(user_id=self.user_id)

        if ingest_result is None and not skip_capture:
            ingest_result = run_live_ingestion(
                window,
                user_id=self.user_id,
                job_id=job_id,
                mev_stride=mev_stride,
                mev_max_blocks=mev_max_blocks,
                capture_tail_days=capture_tail_days,
                capture_resume=capture_resume,
                capture_resume_from_target=capture_resume_from_target,
                require_etherscan=require_etherscan,
            )
        if ingest_result is None:
            return make_response(
                "failed",
                job_id,
                error="live capture missing (pass ingest_result or skip_capture=False)",
            )

        self.reference_guard.verify_unchanged()
        if self.reference_guard.compute_hashes() != ref_before:
            return make_response(
                "failed",
                job_id,
                error="reference_guard: sealed hashes changed during live capture",
            )

        run_input: DiagnosticRunInput = {
            "run_id": job_id,
            "user_id": self.user_id,
            "options": {
                "live": True,
                "fixture": False,
                "seed": window.seed,
                "prereg_version": "WAVE38_LIVE_PREREG.md",
            },
        }

        live_root = DiagnosticConfig.wave38_live_root(self.user_id)
        n_bins = ingest_result.n_bins or window.n_bins
        w_start = ingest_result.capture_start_ts or window.window_start_ts
        raw_db = ingest_result.raw_db_path

        captures: dict[str, CaptureStageResult] = {}

        def _cap(key: str, stage: str, result: AgentEnvelope) -> None:
            if result["status"] != "completed":
                raise RuntimeError(f"{stage} failed: {result.get('error')}")
            meta = result["artifacts"][0]["metadata"]
            captures[key] = CaptureStageResult(
                stage=stage,
                status="completed",
                metadata=meta,
                occupancy_path=meta.get("occupancy_path"),
            )

        try:
            _cap(
                "chainlink",
                "oracle",
                self.oracle.run(
                    run_input,
                    f"{job_id}-oracle",
                    raw_db_path=raw_db,
                    fixture_mode=False,
                    cfg=OracleConfig(
                        fixture_mode=False,
                        n_bins=n_bins,
                        window_start_ts=w_start,
                        min_events=50,
                        soft_plausibility=True,
                    ),
                ),
            )
            _cap(
                "mev_cluster",
                "mev",
                self.mev.run(
                    run_input,
                    f"{job_id}-mev",
                    raw_db_path=raw_db,
                    fixture_mode=False,
                    cfg=MEVConfig(
                        fixture_mode=False,
                        n_bins=n_bins,
                        window_start_ts=w_start,
                        window_end_ts=ingest_result.capture_end_ts
                        or window.window_end_ts,
                        min_occupied_minutes=1,
                        rpc_transport=LiveRpcTransport(),
                    ),
                ),
            )
            _cap(
                "liquidations",
                "liquidations",
                self.liq.run(
                    run_input,
                    f"{job_id}-liq",
                    raw_db_path=raw_db,
                    fixture_mode=False,
                    cfg=LiquidationConfig(
                        fixture_mode=False,
                        n_bins=n_bins,
                        window_start_ts=w_start,
                        min_events=20,
                        resolved_path=live_root
                        / "liquidations"
                        / "liquidation_resolved.json",
                    ),
                ),
            )
            _cap(
                "intent_stablecoin",
                "intent_stable",
                self.intent_stable.run(
                    run_input,
                    f"{job_id}-is",
                    raw_db_path=raw_db,
                    fixture_mode=False,
                    cfg=IntentStableConfig(
                        fixture_mode=False,
                        n_bins=n_bins,
                        window_start_ts=w_start,
                        min_events=50,
                        intent_resolved_path=live_root
                        / "intent_stablecoin"
                        / "intent_relayer_resolved.json",
                        stable_resolved_path=live_root
                        / "intent_stablecoin"
                        / "stablecoin_mint_burn_resolved.json",
                    ),
                ),
            )
        except RuntimeError as exc:
            return make_response("failed", job_id, error=str(exc))

        bundle = assemble_live_bundle(
            captures,
            bridge_eth=ingest_result.bridge_eth_occ,
            bridge_gnosis=ingest_result.bridge_gnosis_occ,
            z_alt_raw=ingest_result.z_alt,
            n_bins=n_bins,
            window_start_ts=w_start,
            source=f"live:{live_root}",
        )

        gate = self.analysis.run_stages_6_7_8_9(
            bundle,
            job_id=job_id,
            thresholds=thresholds,
            run_input=run_input,
            seed=window.seed,
        )
        if gate["status"] != "completed":
            return make_response(
                "failed",
                job_id,
                error=f"Analysis 6→9 failed: {gate.get('error')}",
                artifacts=gate.get("artifacts") or [],
            )

        env = gate["artifacts"][0]["metadata"]
        missing = ENVELOPE_REQUIRED_KEYS - set(env.keys())
        if missing:
            return make_response(
                "failed",
                job_id,
                error=f"Envelope contract missing keys: {sorted(missing)}",
            )

        # Standard Agent-X response wrapping DiagnosticSignalEnvelope
        agent_response = make_response(
            "completed",
            job_id,
            artifacts=[
                {
                    "type": "diagnostic_signal_envelope",
                    "format": "json",
                    "metadata": env,
                }
            ],
            logs=[
                f"verdict={env.get('verdict')}",
                f"gate_action={env.get('gate_action')}",
                "interpretation=OPERATIONAL_SIGNAL_ONLY",
            ],
        )

        gobd = self.report.compose(
            job_id,
            envelope=env,
            pipeline_meta=env.get("pipeline") or {},
            live_window=window.to_dict(),
            agent_response=agent_response,
        )
        if gobd["status"] != "completed":
            return make_response(
                "failed",
                job_id,
                error=f"GoBD report failed: {gobd.get('error')}",
            )

        bus_meta = _publish_eventbus(
            user_id=self.user_id,
            envelope=env,
            agent_response=agent_response,
        )

        sealed = next(
            (p for p in self.reference_guard.registered_paths if p.is_file()),
            None,
        )
        write_blocked = False
        if sealed is not None:
            try:
                self.reference_guard.assert_write_allowed(sealed)
            except Exception:  # noqa: BLE001
                write_blocked = True

        meta = {
            "pipeline": "live_1→9",
            "live": True,
            "fixture_mode": False,
            "interpretation": "OPERATIONAL_SIGNAL_ONLY",
            "live_window": window.to_dict(),
            "ingestion": {
                "raw_db_path": raw_db,
                "n_events": ingest_result.n_events,
                "n_transactions": ingest_result.n_transactions,
                "mev_blocks_scanned": ingest_result.mev_blocks_scanned,
                "block_ranges": ingest_result.block_ranges,
                "rpc_urls": ingest_result.rpc_urls,
                "capture_tail_days": ingest_result.capture_tail_days,
                "capture_start_ts": ingest_result.capture_start_ts,
                "n_bins_analysis": n_bins,
            },
            "envelope": env,
            "verdict": env.get("verdict"),
            "gate_action": env.get("gate_action"),
            "cause": env.get("cause"),
            "gobd_report": gobd["artifacts"][0]["metadata"],
            "eventbus": bus_meta,
            "reference_guard_unchanged": True,
            "reference_write_blocked": write_blocked,
            "agent_x_response": {
                "status": agent_response["status"],
                "job_id": agent_response["job_id"],
                "artifacts": agent_response["artifacts"],
                "error": agent_response.get("error"),
                "logs": agent_response.get("logs"),
            },
        }
        # Surface Wave 39 markers at live-result root (CERTIFIED or BLOCKED).
        ax_meta = ((agent_response.get("artifacts") or [{}])[0] or {}).get("metadata") or {}
        if isinstance(ax_meta, dict) and ax_meta.get("ethical_boundary"):
            meta["ethical_boundary"] = ax_meta["ethical_boundary"]
        out_path = live_root / f"live_result_{job_id}.json"
        out_path.write_text(json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
        meta["result_path"] = str(out_path)

        return make_response(
            "completed",
            job_id,
            artifacts=[{"type": "wave38_live_cycle", "format": "json", "metadata": meta}],
            logs=[
                f"verdict={env.get('verdict')}",
                f"gate={env.get('gate_action')}",
                f"gobd={gobd['artifacts'][0]['metadata'].get('entry_hash', '')[:16]}…",
                f"eventbus={bus_meta.get('subject')}",
            ],
        )


__all__ = [
    "EVENT_SUBJECT",
    "Wave38LivePipeline",
    "assemble_live_bundle",
]
