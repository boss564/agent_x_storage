#!/usr/bin/env python3
"""Prueft das Bridge-Siegel (Stufe A v3 + Filter-Diagnose).

Verifiziert Gate- und Ergebnis-JSONs sowie die vier grossen JSONL-Captures
gegen ``bridge_manifest.json``. Die JSONs gehoeren unter Versionskontrolle;
die JSONLs bleiben lokal und werden nur per SHA-256 fixiert.

    python3 scripts/check_bridge_seal.py              # verify (Exit 0/1)
    python3 scripts/check_bridge_seal.py --write      # Manifest neu schreiben
    python3 scripts/check_bridge_seal.py --json       # maschinenlesbar

Gedacht als Pre-Commit-Hook oder ``make verify``-Schritt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc

MANIFEST_NAME = "bridge_manifest.json"

COMMITTED_JSON = (
    "bridge_stufe_a_v3_coverage_gate.json",
    "bridge_stufe_a_v3_integrity_gate.json",
    "bridge_diagnostic_informativity_gate.json",
    "bridge_stufe_a_v3_ergebnis.json",
    "bridge_diagnostic_ablation.json",
    "bridge_diagnostic_permutation.json",
    "bridge_diagnostic_kfold.json",
    "bridge_diagnostic_ergebnis.json",
)

CAPTURE_JSONL = (
    "bridge_eth.jsonl",
    "bridge_gnosis.jsonl",
    "drivers_90d.jsonl",
    "bridge_stufe_a_v3_mev_cluster.jsonl",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_entry(path: Path) -> dict:
    st = path.stat()
    mtime = datetime.fromtimestamp(st.st_mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "sha256": _sha256(path),
        "bytes": st.st_size,
        "mtime_utc": mtime,
    }


def build_manifest(root: Path) -> dict:
    artifacts_json: dict[str, dict] = {}
    captures_jsonl: dict[str, dict] = {}
    missing: list[str] = []

    for name in COMMITTED_JSON:
        path = root / name
        if not path.is_file():
            missing.append(name)
            continue
        artifacts_json[name] = _file_entry(path)

    for name in CAPTURE_JSONL:
        path = root / name
        if not path.is_file():
            missing.append(name)
            continue
        captures_jsonl[name] = _file_entry(path)

    if missing:
        raise FileNotFoundError(f"fehlende Siegel-Dateien: {', '.join(missing)}")

    return {
        "schema": "bridge_seal_v1",
        "sealed_at": datetime.now(tz=UTC).isoformat(),
        "studies": ["bridge_stufe_a_v3", "bridge_diagnostic"],
        "dossiers": [
            "docs/BRIDGE_STUFE_A_V3_ERGEBNIS.md",
            "docs/BRIDGE_DIAGNOSTIC_ERGEBNIS.md",
        ],
        "artifacts_json": artifacts_json,
        "captures_jsonl": captures_jsonl,
    }


def verify_manifest(root: Path, manifest: dict) -> list[str]:
    errors: list[str] = []
    for section, names in (
        ("artifacts_json", COMMITTED_JSON),
        ("captures_jsonl", CAPTURE_JSONL),
    ):
        expected = manifest.get(section) or {}
        for name in names:
            path = root / name
            entry = expected.get(name)
            if entry is None:
                errors.append(f"{name}: fehlt im Manifest ({section})")
                continue
            if not path.is_file():
                errors.append(f"{name}: Datei fehlt")
                continue
            st = path.stat()
            if st.st_size != entry.get("bytes"):
                errors.append(
                    f"{name}: Groesse {st.st_size} != Manifest {entry.get('bytes')}"
                )
            digest = _sha256(path)
            if digest != entry.get("sha256"):
                errors.append(
                    f"{name}: SHA-256 abweichend "
                    f"(ist {digest[:16]}…, Manifest {str(entry.get('sha256', ''))[:16]}…)"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Projektroot (Default: cwd)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="bridge_manifest.json aus aktuellem Stand schreiben",
    )
    parser.add_argument("--json", action="store_true", help="JSON-Ausgabe")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest_path = root / MANIFEST_NAME

    if args.write:
        try:
            manifest = build_manifest(root)
        except FileNotFoundError as exc:
            print(f"FEHLER: {exc}", file=sys.stderr)
            return 1
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if args.json:
            print(json.dumps({"status": "written", "path": str(manifest_path)}, indent=2))
        else:
            n_json = len(manifest["artifacts_json"])
            n_jsonl = len(manifest["captures_jsonl"])
            print(f"geschrieben: {manifest_path} ({n_json} JSON, {n_jsonl} JSONL)")
        return 0

    if not manifest_path.is_file():
        print(
            f"FEHLER: {MANIFEST_NAME} fehlt — zuerst "
            f"'python3 scripts/check_bridge_seal.py --write' ausfuehren",
            file=sys.stderr,
        )
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = verify_manifest(root, manifest)

    if args.json:
        print(
            json.dumps(
                {
                    "status": "ok" if not errors else "mismatch",
                    "manifest": str(manifest_path),
                    "sealed_at": manifest.get("sealed_at"),
                    "errors": errors,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    elif errors:
        print(f"Bridge-Siegel: {len(errors)} Abweichung(en)")
        for err in errors:
            print(f"  - {err}")
    else:
        print(f"Bridge-Siegel: OK ({MANIFEST_NAME}, sealed {manifest.get('sealed_at', '?')})")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
