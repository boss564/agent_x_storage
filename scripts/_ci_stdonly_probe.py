"""§A-ZZZZ85 — der Prüfer importiert nichts Fremdes.

Warum diese Datei existiert
---------------------------
Runde 72 hat den Fund gemacht, den Runde 71 übersehen hat: ein Prüfer in
einem Job mit Fremdabhängigkeiten ist so grün wie einer ohne Auslöser.
`formal-invariants` stirbt an `openzeppelin-contracts-upgradeable`, bevor
F8 erreicht wird — `continue-on-error: false` schützt nur, was erreicht
wird.

Der eigene Job `pruefer` hat `needs: []` und **keine** Installation. Damit
das so bleibt, prüft dieses Skript die Bedingung, unter der der Verzicht
gilt: `scripts/check_claude_md.py` importiert ausschließlich Stdlib.

Wird dort ein Fremdimport eingefügt, bricht dieser Schritt ab — bevor der
nächste Job grün aussehen kann.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ZIEL = Path(__file__).resolve().parent / "check_claude_md.py"


def fremdimporte(pfad: Path) -> list[str]:
    """Top-Level-Module, die weder Stdlib noch `__future__` sind."""
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    module: list[str] = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            module += [a.name.split(".")[0] for a in knoten.names]
        elif (isinstance(knoten, ast.ImportFrom)
              and knoten.module and knoten.level == 0):
            module.append(knoten.module.split(".")[0])
    erlaubt = set(sys.stdlib_module_names) | {"__future__"}
    # §A-ZZZZ85b: Repo-Module neben dem Prüfer sind **keine**
    # Fremdabhängigkeit — sie liegen im Checkout, der Job klont das
    # Repository ohnehin. Eine Abhängigkeit ist, was **installiert**
    # werden müßte. `akte_guard` und `check_fixtures` sind Dateien, die
    # im selben Verzeichnis liegen; `requests` wäre eine Abhängigkeit.
    nachbar = {p.stem for p in pfad.parent.glob("*.py")}
    return sorted({m for m in module if m not in erlaubt and m not in nachbar})


def main() -> int:
    if not ZIEL.exists():
        print(f"FEHLER: {ZIEL.name} fehlt", file=sys.stderr)
        return 1
    echt = fremdimporte(ZIEL)
    # Und die Nachbarn müssen selbst stdlib-only sein — sonst importiert
    # der Prüfer über zwei Ecken ein Fremdpaket.
    for nachbar in sorted(ZIEL.parent.glob("*.py")):
        if nachbar.name == ZIEL.name or nachbar.name.startswith("test_"):
            continue
        if nachbar.name in ("akte_guard.py", "check_fixtures.py"):
            tief = fremdimporte(nachbar)
            if tief:
                print(f"FEHLER: {nachbar.name} (vom Prüfer importiert) "
                      f"braucht Fremdmodule: {tief}", file=sys.stderr)
                echt.extend(tief)
    if echt:
        print(f"FEHLER: {ZIEL.name} importiert Fremdmodule: {echt}",
              file=sys.stderr)
        print("Der Job `pruefer` installiert nichts. Entweder Import "
              "entfernen oder Installation ergänzen — nicht beides halb.",
              file=sys.stderr)
        return 1
    print(f"OK: {ZIEL.name} nutzt nur die Standardbibliothek")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
