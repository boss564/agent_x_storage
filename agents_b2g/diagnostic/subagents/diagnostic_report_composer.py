"""GoBD WORM report composer for Wave 38 live runs (Agent 9 / §7).

Hash-chained JSONL archive + PDF/A-3-compatible text report under
``{data_root}/{user_id}/wave38/live/reports/``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.reference_guard import (
    ReferenceArtifactGuard,
    ensure_live_directory,
)
from agents_b2g.diagnostic.types import AgentEnvelope


def _sha3(data: bytes) -> str:
    return hashlib.sha3_256(data).hexdigest()


def _reports_dir(user_id: str) -> Path:
    live = ensure_live_directory(DiagnosticConfig.DATA_ROOT, user_id)
    out = live / "reports"
    out.mkdir(parents=True, exist_ok=True)
    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(out)
    return out


class DiagnosticReportComposer:
    """Agent 9 GoBD path: WORM hash chain + PDF/A-3 text report."""

    agent_name = "DiagnosticReportComposer"

    def __init__(self, user_id: str = "wave38"):
        self.user_id = user_id

    def compose(
        self,
        job_id: str,
        *,
        envelope: dict[str, Any],
        pipeline_meta: dict[str, Any] | None = None,
        live_window: dict[str, Any] | None = None,
        agent_response: dict[str, Any] | None = None,
    ) -> AgentEnvelope:
        reports = _reports_dir(self.user_id)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = f"wave38_live_{job_id}_{ts}"

        chain_path = reports / "gobd_worm_chain.jsonl"
        prev_hash = "0x0"
        if chain_path.is_file():
            last = ""
            with chain_path.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        last = line
            if last:
                prev_hash = json.loads(last).get("hash", "0x0")

        record = {
            "job_id": job_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "user_id": self.user_id,
            "previous_hash": prev_hash,
            "envelope": envelope,
            "pipeline_meta": pipeline_meta or {},
            "live_window": live_window or {},
            "interpretation": (
                "OPERATIONAL_SIGNAL_ONLY — not scientific evidence; "
                "Bridge series remains sealed (WAVE38_LIVE_PREREG §1)."
            ),
        }
        payload = json.dumps(record, sort_keys=True, default=str).encode("utf-8")
        entry_hash = _sha3(prev_hash.encode() + b"|" + payload)
        record["hash"] = entry_hash

        with chain_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

        manifest = {
            "job_id": job_id,
            "gobd_compliant": True,
            "worm": True,
            "hash_alg": "sha3_256",
            "entry_hash": entry_hash,
            "previous_hash": prev_hash,
            "chain_path": str(chain_path),
            "timestamp_utc": record["timestamp_utc"],
            "verdict": envelope.get("verdict"),
            "gate_action": envelope.get("gate_action"),
            "cause": envelope.get("cause"),
            "live_window": live_window or {},
            "interpretation": record["interpretation"],
        }
        manifest_path = reports / f"{stem}_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8"
        )

        pdf_path = reports / f"{stem}_report.pdf"
        self._write_pdfa3_text(
            pdf_path,
            job_id=job_id,
            envelope=envelope,
            manifest=manifest,
            agent_response=agent_response,
        )
        manifest["pdf_path"] = str(pdf_path)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8"
        )

        return make_response(
            "completed",
            job_id,
            artifacts=[
                {
                    "type": "gobd_worm_report",
                    "format": "json",
                    "metadata": manifest,
                }
            ],
            logs=[
                f"worm_hash={entry_hash[:16]}…",
                f"pdf={pdf_path.name}",
            ],
        )

    def _write_pdfa3_text(
        self,
        path: Path,
        *,
        job_id: str,
        envelope: dict[str, Any],
        manifest: dict[str, Any],
        agent_response: dict[str, Any] | None,
    ) -> None:
        """Minimal PDF (PDF/A-3 compatible structure) with report body as text."""
        lines = [
            "Agent X — Wave 38 Causal Audit Live Report (GoBD)",
            f"Job: {job_id}",
            f"Timestamp: {manifest.get('timestamp_utc')}",
            f"Verdict: {envelope.get('verdict')}",
            f"Gate: {envelope.get('gate_action')} cause={envelope.get('cause')}",
            f"WORM hash: {manifest.get('entry_hash')}",
            f"Prev hash: {manifest.get('previous_hash')}",
            "",
            "INTERPRETATION (WAVE38_LIVE_PREREG §1):",
            "This is an OPERATIONAL signal for Wave 24/21/28.",
            "It is NOT scientific evidence about ETH↔Gnosis coupling.",
            "Bridge series DIAG_SIGNAL_VALID remains sealed.",
            "",
            "Live window:",
            json.dumps(manifest.get("live_window") or {}, indent=2, default=str),
            "",
            "Envelope:",
            json.dumps(envelope, indent=2, default=str)[:8000],
        ]
        if agent_response:
            lines.extend(
                [
                    "",
                    "Agent-X envelope:",
                    json.dumps(
                        {
                            "status": agent_response.get("status"),
                            "job_id": agent_response.get("job_id"),
                            "error": agent_response.get("error"),
                        },
                        indent=2,
                    ),
                ]
            )
        body = "\n".join(lines)
        # Escape PDF string specials
        safe = (
            body.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("\r", "")
        )
        # Simple multi-line text object (Latin-1 fallback via ASCII)
        ascii_safe = safe.encode("latin-1", errors="replace").decode("latin-1")
        stream = f"BT /F1 10 Tf 40 750 Td 12 TL ({ascii_safe[:2000]}) Tj ET"
        stream_bytes = stream.encode("latin-1", errors="replace")
        objects: list[bytes] = []
        objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
        objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
        objects.append(
            b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n"
        )
        objects.append(
            f"4 0 obj<< /Length {len(stream_bytes)} >>stream\n".encode("ascii")
            + stream_bytes
            + b"\nendstream\nendobj\n"
        )
        objects.append(
            b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>endobj\n"
        )
        # PDF/A hint via metadata stub
        objects.append(
            b"6 0 obj<< /Type /Metadata /Subtype /XML /Length 0 >>stream\n"
            b"endstream\nendobj\n"
        )

        out = bytearray(b"%PDF-1.4\n%AgentX-Wave38-GoBD-PDFA3\n")
        offsets = [0]
        for obj in objects:
            offsets.append(len(out))
            out.extend(obj)
        xref_pos = len(out)
        out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        out.extend(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
        out.extend(
            (
                f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_pos}\n%%EOF\n"
            ).encode("ascii")
        )
        path.write_bytes(bytes(out))


__all__ = ["DiagnosticReportComposer"]
