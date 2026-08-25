"""Load occupancy from live capture dir or test mocks — never write reference artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from agents_b2g.diagnostic.config import CANDIDATE_IDS, DiagnosticConfig
from agents_b2g.diagnostic.cte_math import OccupancyBundle
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard, ReferenceWriteForbiddenError


def load_bundle_from_live_dir(
    live_dir: Path,
    *,
    candidate_ids: tuple[str, ...] = CANDIDATE_IDS,
    guard: ReferenceArtifactGuard | None = None,
) -> OccupancyBundle:
    """Load wave38/live JSON bundle written by capture agents (future)."""
    guard = guard or ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
    guard.assert_write_allowed(live_dir)

    manifest = live_dir / "occupancy_bundle.json"
    if not manifest.is_file():
        raise FileNotFoundError(f"Missing live occupancy bundle: {manifest}")

    guard.assert_write_allowed(manifest)
    body = json.loads(manifest.read_text(encoding="utf-8"))
    return OccupancyBundle(
        bridge_eth=list(body["bridge_eth"]),
        bridge_gnosis=list(body["bridge_gnosis"]),
        z_alt=[list(row) for row in body["z_alt"]],
        z_neu_occ={k: list(v) for k, v in body["z_neu_occ"].items()},
        z_neu_ter={k: list(v) for k, v in body["z_neu_ter"].items()},
        candidate_ids=tuple(body.get("candidate_ids", candidate_ids)),
        source=str(body.get("source", "live")),
    )


def save_mock_bundle(bundle: OccupancyBundle, live_dir: Path) -> Path:
    """Persist mock data only under wave38/live — never project root reference files."""
    guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
    guard.assert_write_allowed(live_dir)
    live_dir.mkdir(parents=True, exist_ok=True)
    out = live_dir / "occupancy_bundle.json"
    guard.assert_write_allowed(out)
    payload = {
        "bridge_eth": bundle.bridge_eth,
        "bridge_gnosis": bundle.bridge_gnosis,
        "z_alt": bundle.z_alt,
        "z_neu_occ": bundle.z_neu_occ,
        "z_neu_ter": bundle.z_neu_ter,
        "candidate_ids": list(bundle.candidate_ids),
        "source": bundle.source,
    }
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def assert_not_reference_path(path: Path) -> None:
    guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
    if guard.is_reference_path(path):
        raise ReferenceWriteForbiddenError(f"Path is sealed reference artifact: {path}")
