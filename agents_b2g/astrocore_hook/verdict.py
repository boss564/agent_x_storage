"""Verdict caps — synthetic provenance cannot yield scientific positives (D1)."""
from __future__ import annotations

# Positive / confirmatory verdicts blocked when data_provenance == "synthetic"
_POSITIVE_VERDICTS = frozenset({
    "CLUSTER_DETECTED",
    "COUPLED",
    "CONFIRMED",
    "SIGNIFIKANT",
    "EMERGENCE_PASSED",
})


_NON_LIVE_PROVENANCE = frozenset({"synthetic", "worm", "gap_synthetic"})


def cap_verdict_for_provenance(verdict: str, data_provenance: str) -> str:
    """Cap verdict when inputs are not live Neo4j (D1/D1b).

    Non-live provenance may report ``SYNTHETIC_ONLY`` at most; confirmatory
    labels require ``data_provenance=neo4j``.
    """
    if data_provenance not in _NON_LIVE_PROVENANCE:
        return verdict
    if verdict in _POSITIVE_VERDICTS:
        return "SYNTHETIC_ONLY"
    return verdict
