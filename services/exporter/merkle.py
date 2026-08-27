"""Minimal Merkle tree with inclusion proofs (SHA-256 hex leaves).

Standalone — does not import B2G agents. Used by B2B RaaS exporter only.
"""
from __future__ import annotations

import hashlib
from typing import Dict, List, Sequence, Tuple


def _h(left: str, right: str) -> str:
    return hashlib.sha256((left + right).encode("utf-8")).hexdigest()


def leaf_hash(payload: bytes | str) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_tree(leaves: Sequence[str]) -> Tuple[str, List[List[str]]]:
    """Return (root, levels) where levels[0] is the leaf layer."""
    if not leaves:
        empty = "0" * 64
        return empty, [[empty]]
    level = list(leaves)
    levels: List[List[str]] = [level]
    while len(level) > 1:
        nxt: List[str] = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            nxt.append(_h(left, right))
        level = nxt
        levels.append(level)
    return level[0], levels


def inclusion_proof(leaves: Sequence[str], index: int) -> Dict[str, object]:
    """Sibling path for leaf at index (0-based)."""
    if index < 0 or index >= len(leaves):
        raise IndexError("leaf index out of range")
    root, levels = build_tree(leaves)
    proof: List[Dict[str, str]] = []
    idx = index
    for level in levels[:-1]:
        sibling_idx = idx ^ 1
        if sibling_idx >= len(level):
            sibling_idx = idx  # odd last node duplicated
        side = "left" if sibling_idx < idx else "right"
        proof.append({"side": side, "hash": level[sibling_idx]})
        idx //= 2
    return {
        "leaf_index": index,
        "leaf_hash": leaves[index],
        "siblings": proof,
        "root": root,
    }


def verify_inclusion(leaf: str, proof: Dict[str, object], expected_root: str) -> bool:
    cur = leaf
    for step in proof.get("siblings") or []:
        sib = str(step["hash"])
        if step.get("side") == "left":
            cur = _h(sib, cur)
        else:
            cur = _h(cur, sib)
    return cur == expected_root and expected_root == proof.get("root")
