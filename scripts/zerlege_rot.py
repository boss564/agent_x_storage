#!/usr/bin/env python3
"""Zerlegt die roten Eintraege eines Laufs in mechanische Kategorien -- R96.

R95 ordnete jeden roten Eintrag MANUELL in "Umgebung/vorbestehend/veraltet/
Messfehler". Damit ist "keine neuen Systemfehler" unfalsifizierbar.

R96: Die Zuordnung folgt einer Regel aus dem Befundtext, nicht aus dem
Gedaechtnis des Erbauers. Erste zutreffende Regel gewinnt.

    ZEITLIMIT   Exit 124/143
    BEFUND      Exit 2 (unentscheidbar)
    DIENST      "no servers available", "Connection refused"
    IMPORT      "ModuleNotFoundError", "No module named"
    ASSERTION   FAIL-Marker mit n/n -- echte Regression
    UNKLAR      Exit != 0 ohne Verdict-/Assertion-Marker (wird gelistet)
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ERGEBNIS = SCRIPTS.parent / "data" / "lauf_letzter.json"

REGELN = [
    ("DIENST", re.compile(r"no servers available|Connection refused|"
                          r"ECONNREFUSED|name resolution")),
    ("IMPORT", re.compile(r"ModuleNotFoundError|ImportError|No module named")),
    ("DIENST", re.compile(r"UNREACHABLE|_SKIP_OR_FAIL|no servers|Startup:\s*False")),
    ("ASSERTION", re.compile(r"\b\d+/\d+\b|\bFAIL\b|passed")),
]


def zerlege(e):
    text = "\n".join(e.get("ende") or [e.get("letzte", "") or ""])
    if e["exit"] in (124, 143):
        return "ZEITLIMIT", f"exit={e['exit']}"
    if e["exit"] == 2:
        return "BEFUND", "Exit 2 = unentscheidbar"
    for name, rx in REGELN:
        m = rx.search(text)
        if m:
            return name, m.group(0)[:40]
    return "UNKLAR", "kein Verdict-/Assertion-Marker -- braucht menschliche Sicht"


def main() -> int:
    if not ERGEBNIS.exists():
        print("kein Lauf-Artefakt")
        return 1
    d = json.loads(ERGEBNIS.read_text(encoding="utf-8"))
    rot = [e for e in d["erg"] if e["klasse"] != "GRUEN"]
    zu = [(e,) + zerlege(e) for e in rot]
    c = Counter(z[1] for z in zu)
    print(f"Lauf: {len(d['erg'])} Dateien | rot gesamt: {len(rot)}")
    for k, n in c.most_common():
        print(f"  {k:10} {n}")
    print()
    for e, k, beleg in zu:
        print(f"  {k:10} {e['datei']:38} exit={e['exit']:<4} {beleg}")
    print(f"\nEchte Assertion-Faelle (Regression): {c.get('ASSERTION', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
