"""PM2 — AdversarialSignalQuarantiner.

Diagnostic quarantine of sandwich/frontrun footprints in capture.
Does not duplicate Wave-40 MEVShield / Confounder execution gates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from agents_b2g.diagnostic.post_mev.agents import make_response
from agents_b2g.diagnostic.post_mev.config import PostMEVConfig
from agents_b2g.diagnostic.post_mev.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.post_mev.types import sha256_hex, utc_now_iso


# ---------------------------------------------------------------------------
# Subagents (9)
# ---------------------------------------------------------------------------


class SandwichFootprintScanner:
    name = "SandwichFootprintScanner"

    def run(self, events: list[Mapping[str, Any]]) -> dict[str, Any]:
        hits: list[str] = []
        for ev in events:
            if bool(ev.get("sandwich")) or (
                ev.get("front_leg") and ev.get("back_leg") and ev.get("victim")
            ):
                hits.append(str(ev.get("signal_id", ev.get("id", ""))))
        return {"hit_ids": [h for h in hits if h], "count": len(hits)}


class FrontrunFootprintScanner:
    name = "FrontrunFootprintScanner"

    def run(self, events: list[Mapping[str, Any]]) -> dict[str, Any]:
        hits: list[str] = []
        for ev in events:
            if bool(ev.get("frontrun")) or (
                ev.get("competing_nonce") is not None and ev.get("same_target")
            ):
                hits.append(str(ev.get("signal_id", ev.get("id", ""))))
        return {"hit_ids": [h for h in hits if h], "count": len(hits)}


class BotDensityHeuristics:
    name = "BotDensityHeuristics"

    def run(self, events: list[Mapping[str, Any]], window: int = 50) -> dict[str, Any]:
        addrs = [str(ev.get("from_address", "")) for ev in events if ev.get("from_address")]
        if not addrs:
            return {"density": 0.0, "elevated": False}
        unique = len(set(addrs))
        density = 1.0 - (unique / max(len(addrs), 1))
        return {"density": round(density, 6), "elevated": density >= 0.5, "window": window}


class LeakageObservationLinker:
    name = "LeakageObservationLinker"

    def run(self, events: list[Mapping[str, Any]]) -> dict[str, Any]:
        leaks = [
            str(ev.get("signal_id", ev.get("id", "")))
            for ev in events
            if bool(ev.get("public_mempool_leak")) or bool(ev.get("leak_observed"))
        ]
        return {"leak_ids": [x for x in leaks if x], "count": len(leaks), "descriptive_only": True}


class QuarantineRegistryWriter:
    name = "QuarantineRegistryWriter"

    def run(self, path: Path, entries: list[dict[str, Any]]) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        appended = 0
        for entry in entries:
            line = json.dumps(entry, sort_keys=True, default=str)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            appended += 1
        return {"path": str(path), "appended": appended, "append_only": True}


class CooldownScheduler:
    name = "CooldownScheduler"

    def run(self, cooldown_h: float, now: str | None = None) -> dict[str, Any]:
        base = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        until = base + timedelta(hours=float(cooldown_h))
        return {
            "cooldown_h": float(cooldown_h),
            "until": until.isoformat(),
            "started_at": base.isoformat(),
        }


class SignalInvalidationMarker:
    name = "SignalInvalidationMarker"

    def run(self, signal_ids: list[str]) -> dict[str, Any]:
        # Marks only — never rewrites DiagnosticSignalEnvelope.
        return {
            "marked_ids": list(signal_ids),
            "envelope_rewritten": False,
            "marker": "POST_MEV_QUARANTINE",
        }


class FalsePositiveAuditor:
    name = "FalsePositiveAuditor"

    def run(self, hit_count: int, volume: int, prior_fp_rate: float = 0.05) -> dict[str, Any]:
        vol = max(int(volume), 1)
        rate = min(1.0, hit_count / vol)
        est_fp = round(rate * float(prior_fp_rate), 6)
        return {"hit_rate": round(rate, 6), "est_fp_rate": est_fp, "prior_fp_rate": prior_fp_rate}


class QuarantineVerdictComposer:
    name = "QuarantineVerdictComposer"

    def run(self, parts: Mapping[str, Any]) -> dict[str, Any]:
        ids = sorted(set(parts.get("candidate_ids", [])))
        return {
            "quarantined_ids": ids,
            "quarantined_count": len(ids),
            "cooldown_h": parts.get("cooldown_h", 24),
            "fp_estimate": parts.get("fp_estimate", 0.0),
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class PM2Result:
    quarantined_ids: list[str]
    cooldown_h: float
    registry_path: str
    subagent_results: dict[str, Any] = field(default_factory=dict)

    @property
    def quarantined_count(self) -> int:
        return len(self.quarantined_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "quarantined_ids": self.quarantined_ids,
            "quarantined_count": self.quarantined_count,
            "cooldown_h": self.cooldown_h,
            "registry_path": self.registry_path,
            "subagents": self.subagent_results,
        }


class AdversarialSignalQuarantiner:
    agent_name = "AdversarialSignalQuarantiner"

    def __init__(self, user_id: str = "post_mev", config: PostMEVConfig | None = None):
        self.user_id = user_id
        self.config = config or PostMEVConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)
        self.sandwich = SandwichFootprintScanner()
        self.frontrun = FrontrunFootprintScanner()
        self.density = BotDensityHeuristics()
        self.leakage = LeakageObservationLinker()
        self.registry = QuarantineRegistryWriter()
        self.cooldown = CooldownScheduler()
        self.marker = SignalInvalidationMarker()
        self.fp = FalsePositiveAuditor()
        self.composer = QuarantineVerdictComposer()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any], job_id: str = "pm2") -> PM2Result:
        return self._evaluate(payload, job_id)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._evaluate(payload, job_id)
        return make_response(
            "completed",
            job_id,
            artifacts=[
                {
                    "type": "pm2_result",
                    "path": result.registry_path,
                    "metadata": result.to_dict(),
                }
            ],
            logs=[f"quarantined={result.quarantined_count}"],
        )

    def _evaluate(self, payload: Mapping[str, Any], job_id: str) -> PM2Result:
        events = list(payload.get("capture_events", payload.get("events", [])))
        volume = int(payload.get("event_volume", len(events) or 1))

        sand_r = self.sandwich.run(events)
        fron_r = self.frontrun.run(events)
        dens_r = self.density.run(events)
        leak_r = self.leakage.run(events)

        candidates = sorted(
            set(sand_r["hit_ids"])
            | set(fron_r["hit_ids"])
            | set(leak_r["leak_ids"])
            | set(payload.get("force_quarantine_ids", []))
        )
        if dens_r["elevated"]:
            # Density alone does not quarantine; only annotates.
            pass

        cool_r = self.cooldown.run(self.config.cooldown_h)
        mark_r = self.marker.run(candidates)
        fp_r = self.fp.run(len(candidates), volume)
        verd_r = self.composer.run(
            {
                "candidate_ids": candidates,
                "cooldown_h": self.config.cooldown_h,
                "fp_estimate": fp_r["est_fp_rate"],
            }
        )

        registry_path = self._tenant / "quarantine_registry.jsonl"
        entries = [
            {
                "job_id": job_id,
                "signal_id": sid,
                "cooldown_until": cool_r["until"],
                "marker": mark_r["marker"],
                "content_hash": sha256_hex({"signal_id": sid, "job_id": job_id}),
                "created_at": utc_now_iso(),
            }
            for sid in verd_r["quarantined_ids"]
        ]
        reg_r = self.registry.run(registry_path, entries)

        return PM2Result(
            quarantined_ids=list(verd_r["quarantined_ids"]),
            cooldown_h=float(verd_r["cooldown_h"]),
            registry_path=str(registry_path),
            subagent_results={
                SandwichFootprintScanner.name: sand_r,
                FrontrunFootprintScanner.name: fron_r,
                BotDensityHeuristics.name: dens_r,
                LeakageObservationLinker.name: leak_r,
                QuarantineRegistryWriter.name: reg_r,
                CooldownScheduler.name: cool_r,
                SignalInvalidationMarker.name: mark_r,
                FalsePositiveAuditor.name: fp_r,
                QuarantineVerdictComposer.name: verd_r,
            },
        )
