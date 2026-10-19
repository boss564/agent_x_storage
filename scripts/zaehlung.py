#!/usr/bin/env python3
"""Assurance und Charakterisierung sind verschiedene Wahrheiten.

Ein gruener Assurance-Test sagt: das System tut, was es soll.
Ein gruener Charakterisierungstest sagt: der Defekt ist noch da.

Beide in einer Summe zu zaehlen laesst die Zahl das Gegenteil
bedeuten. Diese Datei ist die EINZIGE Quelle der Klassifikation —
der Bericht zitiert sie, er erfindet sie nicht.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# suite -> (klasse, befehl, erwartete faelle)
SUITEN: dict[str, tuple[str, str]] = {
    "test_governance_gate.py": ("assurance", ""),
    "test_governance_semantik.py": ("assurance", ""),
    "test_aufrufbaum.py": ("assurance", ""),
    "test_lauf_aufrufer.py": ("assurance", ""),
    "test_lauf_artefakt.py": ("assurance", ""),
    "test_beweiskanal.py": ("assurance", ""),
    # GRUEN, WEIL DAS PRODUKT UNGESCHUETZT IST. Wird rot, wenn jemand
    # es behebt — dann ist der Test umzuschreiben, nicht zu loeschen.
    "test_produkt_bewachung.py": ("charakterisierung", ""),
}


def zaehle() -> dict:
    out = {"assurance": [0, 0], "charakterisierung": [0, 0], "details": []}
    for name, (klasse, _) in SUITEN.items():
        p = REPO / "scripts" / name
        if not p.exists():
            continue
        r = subprocess.run([sys.executable, str(p)], cwd=REPO,
                           capture_output=True, text=True)
        # Die Summenzeile ist die, die MIT "N/M" BEGINNT. Sonst frisst der
        # Parser das erste "N/M" irgendeiner Zwischenzeile (Selbstbefund R104).
        letzte = [z for z in r.stdout.strip().splitlines()
                  if z.strip() and z.split()[0].count("/") == 1
                  and z.split()[0].split("/")[0].isdigit()]
        if letzte:
            teil, ganz = letzte[-1].split()[0].split("/")
            a, b = int(teil), int(ganz)
        else:
            a, b = (0, 1) if r.returncode else (1, 1)
        out[klasse][0] += a
        out[klasse][1] += b
        out["details"].append({"suite": name, "klasse": klasse,
                               "ok": a, "gesamt": b, "rc": r.returncode})
    return out


def main() -> int:
    z = zaehle()
    a, c = z["assurance"], z["charakterisierung"]
    print(f"Assurance {a[0]}/{a[1]} | "
          f"Charakterisierung (dokumentierte Defekte) {c[0]}/{c[1]}")
    if "--json" in sys.argv:
        print(json.dumps(z, indent=2))
    rot = [d for d in z["details"] if d["rc"] != 0]
    return 0 if not rot else 1


if __name__ == "__main__":
    raise SystemExit(main())
