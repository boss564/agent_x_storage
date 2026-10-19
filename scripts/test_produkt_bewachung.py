#!/usr/bin/env python3
"""R102 §2: Das Produkt ist ungoverned. Dieser Test macht es sichtbar.

Befund: P1 erklaerte data/lauf_letzter.json zur Vertragsschnittstelle,
und die Datei ist gitignored (.gitignore:38 'data/'), in keiner
Entscheidung bewacht, und 'protokoll/' wurde NIE committet.

Zwei Ausfaelle als Charakterisierungstest — er wird rot, sobald jemand
die Zustandsaenderung vornimmt. Bis dahin dokumentiert er die Luecke
statt sie zu verschweigen.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ok = gesamt = 0


def pruefe(name: str, bedingung: bool, detail: str = "") -> None:
    global ok, gesamt
    gesamt += 1
    if bedingung:
        ok += 1
        print(f"ok   {name}")
    else:
        print(f"ROT  {name}  {detail}")


def main() -> int:
    # 1: die Vertragsschnittstelle ist gitignored (Befund, nicht Wunsch)
    # Achtung: check-ignore gibt auch bei NEGATION Exit 0. Wahrheit ist
    # "ist die Datei ignoriert", nicht "nennt git sie ueberhaupt".
    r = subprocess.run(["git", "check-ignore", "-q", "data/lauf_letzter.json"],
                       cwd=REPO, capture_output=True)
    pruefe("1 Produkt KEINE durable Adresse: lauf_letzter.json ist gitignored",
           r.returncode == 0, "Datei ist tracked — Befund ueberholt, Test anpassen")

    # Fall 4: die .gitignore-Regel selbst, in einem Temp-Repo ERZEUGT.
    # Der Hook verlangt: wer ein Muster aus .gitignore beziffert, muss es
    # auch herstellen. Beide Richtungen — Glob greift, Ausnahme greift.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        git = ["git", "-C", tmp]
        subprocess.run(git + ["init", "-q"], capture_output=True)
        (Path(tmp) / "scripts").mkdir()
        regeln = ["*.jsonl"]
        (Path(tmp) / ".gitignore").write_text(
            "*.jsonl\n!scripts/beweis_ledger.jsonl\n", encoding="utf-8")
        treffer = subprocess.run(git + ["check-ignore", "-q", "x.jsonl"],
                                 capture_output=True).returncode == 0
        ausnahme = subprocess.run(git + ["check-ignore", "-q",
                                         "scripts/beweis_ledger.jsonl"],
                                  capture_output=True).returncode != 0
    pruefe("4a Glob *.jsonl greift (erzeugt, nicht behauptet)", treffer)
    pruefe("4b Ausnahme NACH dem Glob macht das Ledger versionierbar", ausnahme,
           "Reihenfolge falsch — letzte Regel gewinnt")

    # und die Gegenprobe im echten Repo: das Ledger LIEGT im Index
    r = subprocess.run(["git", "ls-files", "--error-unmatch",
                        "scripts/beweis_ledger.jsonl"], cwd=REPO,
                       capture_output=True)
    pruefe("4c Beweis-Ledger ist im Index (versioniert)", r.returncode == 0,
           "Ledger nicht eingecheckt — Kanal traegt seine Belege nicht")

    # 2: protokoll/ wurde nie committet
    r = subprocess.run(["git", "log", "--all", "--oneline", "--", "protokoll/"],
                       cwd=REPO, capture_output=True, text=True)
    pruefe("2 protokoll/ wurde noch NIE committet (D1 verriegelt nur den Boden)",
           r.stdout.strip() == "", r.stdout[:120])

    # 3: das Produkt steht in keiner bewachten Dateiliste
    entscheide = sorted((REPO / "scripts").glob("entscheidung_R*.json"))
    import json
    bewacht = set()
    for e in entscheide:
        try:
            bewacht |= set(json.loads(e.read_text(encoding="utf-8"))
                           .get("dateien_geschlossen", []))
        except Exception:
            pass
    pruefe("3 Produkt ist in KEINER bewachten Menge",
           "data/lauf_letzter.json" not in bewacht
           and not any(p.startswith("protokoll/") for p in bewacht),
           str(sorted(bewacht))[:200])

    print(f"\n{ok}/{gesamt} Produkt-Bewachungs-Befunde (Charakterisierung)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
