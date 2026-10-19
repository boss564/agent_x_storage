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


def summenzeile(stdout: str) -> tuple[int, int] | None:
    """Liest die LETZTE 'N/M'-Angabe, egal wo sie in der Zeile steht.

    R104-Selbstbefund: der Parser nahm das erste 'N/M' irgendeiner Zeile
    und las 1/1 statt 6/6. R105-Selbstbefund: er verlangte 'N/M' am
    ZEILENANFANG — aber die Ausgabe lautet "Assurance 43/43 | ...".
    Beide Lesarten waren falsch. Ein Eichnormal findet beides.
    """
    import re
    treffer = re.findall(r"(?<![\d/])(\d+)/(\d+)(?![\d/])", stdout)
    if not treffer:
        return None
    a, b = treffer[-1]
    return int(a), int(b)


# Eichnormal: bekannte Eingaben -> bekanntes Soll. Nachtragen statt raten.
FIXTURES: list[tuple[str, str, int, int]] = [
    ("einfach", "ok 1\nok 2\n\n2/2 Faelle gruen\n", 2, 2),
    ("zwischenzeile mit slash",
     "ok (1/2) Teil\nok (2/2) Teil\n\n6/6 Bewachungs-Befunde\n", 6, 6),
    ("mehrere Summenzeilen, letzte gewinnt",
     "1/1 alt\n5/5 neu\n", 5, 5),
    ("keine Summenzeile", "irgendwas ohne zahl\n", 0, 0),
    ("zeile mit 3 slash", "a/b/c\n\n3/4 done\n", 3, 4),
]


def zaehle() -> dict:
    out = {"assurance": [0, 0], "charakterisierung": [0, 0], "details": []}
    for name, (klasse, _) in SUITEN.items():
        p = REPO / "scripts" / name
        if not p.exists():
            continue
        r = subprocess.run([sys.executable, str(p)], cwd=REPO,
                           capture_output=True, text=True)
        s = summenzeile(r.stdout)
        a, b = s if s else ((0, 1) if r.returncode else (1, 1))
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
