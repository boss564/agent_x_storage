"""Agent X RaaS B2B Exporter — P9 output only (JSON / Markdown / PDF + Merkle).

Does not touch gate, runner, prefilter, or orchestration. Reads an existing
tenant run via raas_portal store/certificate builders and writes a commercial
gutachten package under {run_dir}/exports/b2b/.

Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false · submitter-only
Baseline tag: v1.0-raas-baseline
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from services.exporter import merkle as merkle_mod
from services.raas_portal import exporter as portal_exporter
from services.raas_portal import store

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
BASELINE_TAG = "v1.0-raas-baseline"
PACKAGE_SCHEMA = "raas_b2b_gutachten_v0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _worm_lines(tenant_id: str, run_id: str) -> List[str]:
    worm = store.run_dir(tenant_id, run_id) / "audit.worm.jsonl"
    if not worm.is_file():
        return []
    return [ln for ln in worm.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _minimal_pdf(title: str, lines: Sequence[str]) -> bytes:
    """Tiny single-page PDF (no third-party deps). GoBD-friendly plain text."""
    # Escape PDF string specials
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content_lines = [f"BT /F1 12 Tf 50 780 Td ({esc(title)}) Tj"]
    y_cmd = "0 -16 Td"
    for i, line in enumerate(lines[:40]):
        chunk = esc(line[:110])
        if i == 0:
            content_lines.append(f"T* /F1 9 Tf ({chunk}) Tj")
        else:
            content_lines.append(f"{y_cmd} ({chunk}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objs: List[bytes] = []
    objs.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objs.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objs.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objs.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\n"
    )
    objs.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)


def build_b2b_package(
    *,
    tenant_id: str,
    run_id: str,
    caller_tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build gutachten JSON + Merkle proofs from an existing completed run."""
    caller = caller_tenant_id if caller_tenant_id is not None else tenant_id
    cert = portal_exporter.build_certificate(
        tenant_id=tenant_id,
        run_id=run_id,
        caller_tenant_id=caller,
    )
    rd = store.run_dir(tenant_id, run_id)
    worm_raw = _worm_lines(tenant_id, run_id)
    stress_path = rd / "stress_summary.json"
    stress_hash = _sha256_file(stress_path) if stress_path.is_file() else None

    # Ordered leaves for Merkle (stable labels)
    leaf_specs: List[Dict[str, str]] = [
        {
            "id": "certificate",
            "hash": merkle_mod.leaf_hash(
                json.dumps(cert, sort_keys=True, default=str)
            ),
        },
        {
            "id": "worm_tail",
            "hash": merkle_mod.leaf_hash(worm_raw[-1] if worm_raw else "EMPTY_WORM"),
        },
    ]
    if stress_hash:
        leaf_specs.append({"id": "stress_summary", "hash": stress_hash})
    for i, line in enumerate(worm_raw):
        leaf_specs.append({"id": f"worm_line_{i}", "hash": merkle_mod.leaf_hash(line)})

    leaf_hashes = [s["hash"] for s in leaf_specs]
    root, _ = merkle_mod.build_tree(leaf_hashes)
    proofs = {
        s["id"]: merkle_mod.inclusion_proof(leaf_hashes, i)
        for i, s in enumerate(leaf_specs)
    }
    # Verify locally (fail-closed)
    for s in leaf_specs:
        ok = merkle_mod.verify_inclusion(s["hash"], proofs[s["id"]], root)
        if not ok:
            raise RuntimeError(f"merkle self-check failed for {s['id']}")

    package = {
        "schema": PACKAGE_SCHEMA,
        "baseline_tag": BASELINE_TAG,
        "scope": SCOPE,
        "live_execution": False,
        "not_investment_advice": True,
        "envelope_policy": "submitter_only_v3_4_3",
        "issued_at": _now(),
        "tenant_id": tenant_id,
        "run_id": run_id,
        "subjects": cert.get("subjects"),
        "counterparties_mentioned": [],
        "certificate": cert,
        "merkle": {
            "algorithm": "sha256",
            "root": root,
            "leaf_count": len(leaf_hashes),
            "leaves": leaf_specs,
            "inclusion_proofs": proofs,
        },
        "worm": {
            "line_count": len(worm_raw),
            "tail_hash": cert.get("worm_tail_hash"),
        },
        "note": (
            "B2B output package only. Core/gate/prefilter untouched. "
            "Simulation gutachten — no order execution."
        ),
    }
    package["package_id"] = hashlib.sha256(
        json.dumps(
            {"root": root, "tenant_id": tenant_id, "run_id": run_id, "issued_at": package["issued_at"]},
            sort_keys=True,
        ).encode()
    ).hexdigest()[:32]
    return package


def package_to_markdown(package: Dict[str, Any]) -> str:
    cert = package.get("certificate") or {}
    m = cert.get("metrics") or {}
    merkle = package.get("merkle") or {}
    lines = [
        "# Agent X RaaS — B2B Risikogutachten",
        "",
        f"**Package ID:** `{package.get('package_id')}`",
        f"**Baseline:** `{package.get('baseline_tag')}`",
        f"**Merkle root:** `{merkle.get('root')}`",
        f"**Verdict:** {cert.get('verdict')} · Gate: {cert.get('gate_verdict')}",
        f"**Scope:** {package.get('scope')} · live_execution={package.get('live_execution')}",
        "",
        "## Mandant / Run",
        f"- Tenant: {package.get('tenant_id')}",
        f"- Run: {package.get('run_id')}",
        f"- Subjects: {package.get('subjects')}",
        f"- Counterparties: {package.get('counterparties_mentioned')}",
        "",
        "## Kennzahlen",
        f"- Szenarien: {m.get('n_scenarios')}",
        f"- Risk block rate: {m.get('risk_block_rate')}",
        f"- WORM lines: {(package.get('worm') or {}).get('line_count')}",
        f"- Merkle leaves: {merkle.get('leaf_count')}",
        "",
        "## Hinweis",
        package.get("note", ""),
        "",
        "not_investment_advice=true",
    ]
    return "\n".join(lines)


def export_b2b_gutachten(
    *,
    tenant_id: str,
    run_id: str,
    caller_tenant_id: Optional[str] = None,
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Write JSON + Markdown + PDF + merkle sidecar under exports/b2b/."""
    package = build_b2b_package(
        tenant_id=tenant_id,
        run_id=run_id,
        caller_tenant_id=caller_tenant_id,
    )
    rd = store.run_dir(tenant_id, run_id)
    dest = Path(out_dir) if out_dir else (rd / "exports" / "b2b")
    dest.mkdir(parents=True, exist_ok=True)

    json_path = dest / "gutachten.json"
    md_path = dest / "gutachten.md"
    pdf_path = dest / "gutachten.pdf"
    merkle_path = dest / "merkle_proofs.json"

    md = package_to_markdown(package)
    json_path.write_text(json.dumps(package, indent=2, default=str) + "\n", encoding="utf-8")
    md_path.write_text(md + "\n", encoding="utf-8")
    merkle_path.write_text(
        json.dumps(package["merkle"], indent=2) + "\n", encoding="utf-8"
    )
    pdf_path.write_bytes(
        _minimal_pdf(
            "Agent X RaaS B2B Gutachten",
            [
                f"Package: {package.get('package_id')}",
                f"Baseline: {BASELINE_TAG}",
                f"Tenant: {tenant_id}  Run: {run_id}",
                f"Merkle: {package['merkle']['root']}",
                f"Verdict: {package['certificate'].get('verdict')}",
                "not_investment_advice=true  live_execution=false",
                package.get("note", ""),
            ],
        )
    )

    store.append_worm_line(
        tenant_id,
        run_id,
        {
            "phase": "b2b_gutachten_export",
            "package_id": package["package_id"],
            "merkle_root": package["merkle"]["root"],
            "baseline_tag": BASELINE_TAG,
        },
    )

    return {
        "status": "completed",
        "package_id": package["package_id"],
        "merkle_root": package["merkle"]["root"],
        "paths": {
            "json": str(json_path),
            "markdown": str(md_path),
            "pdf": str(pdf_path),
            "merkle": str(merkle_path),
        },
        "package": package,
        "scope": SCOPE,
        "live_execution": False,
        "baseline_tag": BASELINE_TAG,
    }


__all__ = [
    "BASELINE_TAG",
    "build_b2b_package",
    "export_b2b_gutachten",
    "package_to_markdown",
]
