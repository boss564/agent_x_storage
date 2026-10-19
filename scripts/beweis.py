#!/usr/bin/env python3
"""#14: Der Beweiskanal. Zitate werden adressierbar und pruefbar.

Drei Runden, dreimal unpruefbare Zitate: Makefile-Rezept gekuerzt,
Transcript-Zeile ohne Fundstelle, Hash-Paar ohne Form. Der Auditor
hat keinen Dateizugriff; er sieht nur Prosa mit Zeilennummern.

Dieses Werkzeug macht aus einem Zitat eine PRUEFBARE Adresse:

    python3 scripts/beweis.py cite <datei> <von>:<bis>

gibt einen Block aus, der Artefakt-SHA, Zeilennummern und den
VOLLEN Wortlaut traegt. Ein gekuerztes Zitat entsteht hier nicht —
wer kuerzt, muss das Blockformat von Hand brechen und das ist sichtbar.

    python3 scripts/beweis.py check            alle Belege im Ledger
    python3 scripts/beweis.py check --strict   Exit 1 bei jedem Defekt

Das Zitatformat (maschinell lesbar, im Bericht kopierbar):

    <<<BEWEIS artefakt=Makefile zeile=56-63 sha=<12hex>
    ...wörtlicher Inhalt...
    BEWEIS>>>

check verifiziert: Datei existiert, Zeilen im Bereich, SHA des
Bereichs stimmt mit dem im Block ueberein. Ein Beweis, dessen SHA
nicht mehr passt, ist ROT — das Artefakt hat sich geaendert.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "scripts" / "beweis_ledger.jsonl"
MUSTER = re.compile(
    r"<<<BEWEIS artefakt=(?P<a>\S+) zeile=(?P<v>\d+)-(?P<b>\d+) "
    r"sha=(?P<h>[0-9a-f]{12})\n(?P<t>.*?)\nBEWEIS>>>", re.S)


def _bereich(pfad: Path, von: int, bis: int) -> str:
    zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
    if von < 1 or bis > len(zeilen) or von > bis:
        raise ValueError(f"{pfad.name}: Bereich {von}-{bis} ungueltig "
                         f"(Datei hat {len(zeilen)} Zeilen)")
    return "".join(zeilen[von - 1:bis])


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def zitiere(artefakt: str, von: int, bis: int) -> str:
    pfad = REPO / artefakt
    inhalt = _bereich(pfad, von, bis)
    return (f"<<<BEWEIS artefakt={artefakt} zeile={von}-{bis} "
            f"sha={_sha(inhalt)}\n{inhalt.rstrip(chr(10))}\nBEWEIS>>>")


def pruefe_block(a: str, von: int, bis: int, sha: str, text: str) -> str:
    """Gibt '' bei OK, sonst den Defekt."""
    pfad = REPO / a
    if not pfad.exists():
        return f"Artefakt fehlt: {a}"
    try:
        ist = _bereich(pfad, von, bis)
    except ValueError as e:
        return str(e)
    if _sha(ist) != sha:
        return (f"{a}:{von}-{bis} SHA-Drift — Block sagt {sha}, "
                f"Datei ist {_sha(ist)}")
    if ist.rstrip("\n") != text.rstrip("\n"):
        return f"{a}:{von}-{bis} Wortlaut weicht trotz SHA ab"
    return ""


def check(strict: bool = False) -> int:
    if not LEDGER.exists():
        print(f"kein Ledger: {LEDGER}")
        return 0
    defekte = 0
    for nr, zeile in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        if not zeile.strip():
            continue
        e = json.loads(zeile)
        befund = pruefe_block(e["artefakt"], e["von"], e["bis"], e["sha"], e["text"])
        marke = "ok  " if not befund else "ROT "
        print(f"{marke} {e['artefakt']}:{e['von']}-{e['bis']} "
              f"[{e.get('runde','?')}] {befund}")
        defekte += bool(befund)
    print(f"\n{defekte} Defekt(e) in {sum(1 for z in LEDGER.read_text(encoding='utf-8').splitlines() if z.strip())} Beleg(en)")
    return 1 if (strict and defekte) else 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("cite", "check"):
        print(__doc__)
        return 2
    if argv[0] == "check":
        return check("--strict" in argv)
    if len(argv) != 3:
        print("cite <datei> <von>:<bis>")
        return 2
    von, bis = (int(x) for x in argv[2].split(":"))
    print(zitiere(argv[1], von, bis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
