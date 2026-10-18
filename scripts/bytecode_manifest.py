#!/usr/bin/env python3
"""Bytecode-Manifest: was der Baum heute baut — und ob es das Deployte ist.

§A-ZZZZ105 (Runde 75): **`deploy-gate` prüft Kompilierbarkeit, nicht
Deploybarkeit.** Der Name versprach mehr, als `needs` enthielt: kein
Schritt verglich Bytecode. Zwei Knöpfe in `foundry.toml` ändern Bytecode,
nicht nur Kompilierbarkeit — `via_ir` und `optimizer`. Ein Recompile nach
einer Konfigurationsänderung ist damit möglicherweise **ein anderes
Artefakt** bei gleichem Quelltext.

Dieses Skript macht die Drift **sichtbar**, bevor sie deployt wird. Es
blockiert nicht — es schreibt einen Hash je Contract und vergleicht ihn
mit dem committeten Manifest.

    python3 scripts/bytecode_manifest.py          # schreiben
    python3 scripts/bytecode_manifest.py --check  # vergleichen (Exit 1 bei Drift)

Warum `--check` nicht im Gate steht: der Snapshot-Zweig hat kein
deploytes Artefakt mit Hash (`deployments/` ist leer, `.deployed_contracts
.json` trägt Adresse und Gas, keinen Bytecode). Ein Vergleich gegen
`HEAD~1` wäre ein Vergleich gegen sich selbst. Der nächste ehrliche
Schritt ist ein Hash im Deploy-Artefakt — dann kann `--check` gegen das
**Deployte** laufen statt gegen den Vorstand.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
MANIFEST = ROOT / "order_execution_engine" / "ops" / "bytecode_manifest.json"

# Nur Contracts, nicht Libraries und Interfaces: die Länge trennt sie
# empirisch (Libraries unter 100 Bytes, Contracts darüber).
MIN_BYTES = 100


def _sammle() -> dict[str, dict[str, object]]:
    """deployedBytecode-Hash je Contract aus `out/`."""
    ergebnis: dict[str, dict[str, object]] = {}
    if not OUT.is_dir():
        return ergebnis
    for f in sorted(OUT.glob("*/*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        bc = (d.get("deployedBytecode") or {}).get("object", "")
        if not bc or bc == "0x":
            continue
        roh = bytes.fromhex(bc[2:])
        if len(roh) < MIN_BYTES:
            continue
        ergebnis[f.stem] = {
            "sha256": hashlib.sha256(roh).hexdigest(),
            "bytes": len(roh),
            "source": f.parent.name,
        }
    return ergebnis


def main(argv: list[str]) -> int:
    if not OUT.is_dir():
        print("out/ fehlt — zuerst `forge build`", file=sys.stderr)
        return 2
    jetzt = _sammle()
    if not jetzt:
        print("out/ enthält keine deploybaren Contracts — nichts zu messen",
              file=sys.stderr)
        return 2
    if "--check" in argv:
        if not MANIFEST.exists():
            print(f"kein Manifest ({MANIFEST.name}) — Drift nicht prüfbar",
                  file=sys.stderr)
            return 1
        alt = json.loads(MANIFEST.read_text(encoding="utf-8"))["contracts"]
        drift = []
        for name, wert in jetzt.items():
            if name not in alt:
                drift.append(f"+ {name} (neu, nicht im Manifest)")
            elif alt[name]["sha256"] != wert["sha256"]:
                drift.append(
                    f"~ {name}: {alt[name]['sha256'][:16]} → "
                    f"{wert['sha256'][:16]} ({alt[name]['bytes']} → "
                    f"{wert['bytes']} B)")
        for name in alt:
            if name not in jetzt:
                drift.append(f"- {name} (im Manifest, nicht gebaut)")
        if drift:
            print(f"Bytecode-Drift: {len(drift)} Contract(s)")
            for d in drift:
                print("  " + d)
            print("\nDas ist kein Fehler — es ist ein Befund. Ein neuer Hash "
                  "bei gleichem Quelltext heißt: andere Compiler-Konfiguration.")
            return 1
        print(f"Bytecode unverändert: {len(jetzt)} Contracts")
        return 0
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "hinweis": "Erzeugt von scripts/bytecode_manifest.py. Der Hash "
                   "bezieht sich auf deployedBytecode nach via_ir+optimizer "
                   "(foundry.toml). Vergleich mit dem Deployten ist offen, "
                   "solange kein Bytecode-Hash im Deploy-Artefakt liegt.",
        "solc": "0.8.35",
        "via_ir": True,
        "optimizer_runs": 200,
        "contracts": jetzt,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Manifest geschrieben: {len(jetzt)} Contracts → "
          f"{MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
