#!/usr/bin/env python3
"""#14 (P0): Zweite Haelfte — der Auditor muss pruefen koennen.

R103 pruefte nur den Erbauer (Block, Drift, Ledger). R104 prueft die
Haelfte, die den Auditor ermaechtigt:

  1  VOLLER SHA: 64 Hex, kein 12-Zeichen-Index
  2  AUDITOR-RECHNUNG: sha256(text) == sha256, mit Kern-Utilities
     nachgerechnet — ohne Beweis-Werkzeug, ohne Repo
  3  DATEI-SHA: Aenderung AUSSERHALB des Bereichs wird erkannt
  4  KUERZUNG: gekuerztes Zitat besteht nicht
  5  PROSA-GATE: unverankerte Datei:Zeile wird rot
  6  PROSA-GATE: belegte Referenz bleibt gruen
  7  Ledger ist im Index (versioniert)

Ein Test, der gruen ist, weil das System kaputt ist, hat hier keinen
Platz — ausser er ist als Charakterisierung deklariert (separate Suite).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import beweis as B

ok = gesamt = 0


def pruefe(name: str, bedingung: bool, detail: str = "") -> None:
    global ok, gesamt
    gesamt += 1
    ok += bool(bedingung)
    print(f"{'ok  ' if bedingung else 'ROT '} {name}" + (f"  {detail}" if not bedingung else ""))


def main() -> int:
    e = B.beleg("Makefile", 56, 63)
    block = B.zitiere(e)

    pruefe("1a SHA ist voll (64 hex)", len(e["sha256"]) == 64 and all(c in "0123456789abcdef" for c in e["sha256"]))
    pruefe("1b Block traegt 64-stelligen SHA", e["sha256"] in block)
    pruefe("1c kein 12-Zeichen-Rest im Format", not B.MUSTER.search(block.replace(e["sha256"], "X" * 64)))

    # 2 Auditor rechnet selbst — sha256sum ueber den Text, wie ein Fremder
    r = subprocess.run(["shasum", "-a", "256"], input=e["text"].encode(),
                       capture_output=True)
    extern = r.stdout.decode().split()[0]
    pruefe("2a Auditor-Rechnung == Beleg (ohne Beweis-Werkzeug)", extern == e["sha256"], f"{extern} != {e['sha256']}")

    # 3 Datei-SHA faengt Aenderung ausserhalb des Bereichs
    kopie = Path("/tmp/mk_ausserhalb")
    zs = (REPO / "Makefile").read_text(encoding="utf-8").splitlines()
    zs[-1] = zs[-1] + "\n# mutiert ausserhalb 56-63"
    kopie.write_text("\n".join(zs) + "\n", encoding="utf-8")
    neue_datei_sha = hashlib.sha256(kopie.read_text(encoding="utf-8").encode()).hexdigest()
    pruefe("3a Datei-SHA aendert sich ausserhalb des Bereichs", neue_datei_sha != e["sha256_datei"])
    pruefe("3b Bereichs-SHA bleibt gleich (Bereich unberuehrt)",
           hashlib.sha256(B._bereich(kopie, 56, 63).encode()).hexdigest() == e["sha256"])

    # 4 Kuerzung
    kurz = "\n".join(e["text"].splitlines()[:3]) + "\n"
    pruefe("4a gekuerztes Zitat -> Defekt", bool(
        B.pruefe_block("Makefile", 56, 63, e["sha256"], e["sha256_datei"],
                       e["zeilen"], kurz)))
    pruefe("4b volles Zitat -> ok", B.pruefe_block(
        "Makefile", 56, 63, e["sha256"], e["sha256_datei"], e["zeilen"],
        e["text"]) == "")

    # 5/6 Prosa-Gate
    belegt = B.belegte_aus_ledger()
    luecken = B.prosa_gate("siehe Makefile:56-63 und foo.py:99", belegt)
    pruefe("5a unverankerte Referenz wird rot", "foo.py:99" in luecken, str(luecken))
    pruefe("5b belegte Referenz bleibt gruen", "Makefile:56-63" not in luecken, str(luecken))
    pruefe("5c Teilbereich eines Belegs ist gedeckt",
           B.prosa_gate("Makefile:60", belegt) == [])

    # 7 Ledger im Index
    r = subprocess.run(["git", "ls-files", "--error-unmatch",
                        "scripts/beweis_ledger.jsonl"], cwd=REPO, capture_output=True)
    pruefe("7 Ledger ist im Index", r.returncode == 0)

    print(f"\n{ok}/{gesamt} Beweiskanal-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
