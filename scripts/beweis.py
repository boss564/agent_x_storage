#!/usr/bin/env python3
"""#14: Der Beweiskanal. Zitate werden adressierbar und pruefbar.

Drei Runden, dreimal unpruefbares Zitat. Der Auditor hat keinen
Dateizugriff; er sieht nur Prosa mit Zeilennummern.

R103 baute die Haelfte, die den ERBAUER diszipliniert. R104 baut die
Haelfte, die den AUDITOR ermaechtigt:

  1. VOLLER SHA-256 — nicht 12 Hex. Ein gekuerzter Digest ist eine
     Hausnummer; wer ihn nicht nachrechnen kann, glaubt ihn.

  2. BYTE-EXAKTE PUBLIKATION — `cite --publish` schreibt den Beleg in
     scriptbares JSON. Wer das Artefakt hat, rechnet:
         sha256(json["text"]) == json["sha256"]
     und hat es ohne Werkzeug geprueft. Kein Repo, kein Vertrauen.

  3. PROSA-GATE — `cite --stdin` nimmt Fliesstext und meldet jede
     Zeilennummer-Referenz, die kein Beleg ist. Der Original-Defekt
     war nie das Ledger, sondern der Bericht.

Format im Text (kopierbar, nicht kuerzbar):

    <<<BEWEIS artefakt=Makefile zeile=56-63
    sha256=<64 hex, vollstaendig>
    datei=<64 hex ueber die GANZE Datei> zeilen=972
    ...wörtlicher Inhalt, zeilengleich...
    BEWEIS>>>

check verifiziert: Datei existiert, Zeilen im Bereich, Bereichs-SHA
und GANZ-DATEI-SHA. Ein Beweis, dessen Datei-SHA nicht mehr passt,
ist ROT — das Artefakt hat sich geaendert, irgendwo.
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
    r"<<<BEWEIS artefakt=(?P<a>\S+) zeile=(?P<v>\d+)-(?P<b>\d+)\n"
    r"sha256=(?P<h>[0-9a-f]{64}) datei=(?P<d>[0-9a-f]{64}) "
    r"zeilen=(?P<z>\d+)\n(?P<t>.*?)\nBEWEIS>>>", re.S)
# Prosa-Referenzen: Makefile:63, scripts/lauf.py:112, artefakt:12-14
PROSA = re.compile(r"\b([\w./-]+\.(?:py|json|jsonl|md|sh|yml|yaml|sol|ino))"
                   r":(\d+)(?:-(\d+))?")


def _zeilen(pfad: Path) -> list[str]:
    return pfad.read_text(encoding="utf-8").splitlines()


def _bereich(pfad: Path, von: int, bis: int) -> str:
    zs = _zeilen(pfad)
    if von < 1 or bis > len(zs) or von > bis:
        raise ValueError(f"{pfad.name}: Bereich {von}-{bis} ungueltig "
                         f"(Datei hat {len(zs)} Zeilen)")
    return "\n".join(zs[von - 1:bis]) + "\n"


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def beleg(artefakt: str, von: int, bis: int, runde: str = "",
          warum: str = "") -> dict:
    pfad = REPO / artefakt
    inhalt = _bereich(pfad, von, bis)
    return {"artefakt": artefakt, "von": von, "bis": bis,
            "sha256": _h(inhalt),
            "sha256_datei": _h(pfad.read_bytes().decode("utf-8")),
            "zeilen": len(_zeilen(pfad)),
            "text": inhalt, "runde": runde, "warum": warum}


def zitiere(e: dict) -> str:
    return (f"<<<BEWEIS artefakt={e['artefakt']} zeile={e['von']}-{e['bis']}\n"
            f"sha256={e['sha256']} datei={e['sha256_datei']} "
            f"zeilen={e['zeilen']}\n{e['text'].rstrip(chr(10))}\nBEWEIS>>>")


def pruefe_block(a: str, von: int, bis: int, sha: str, dsha: str,
                 zeilen: int, text: str) -> str:
    """Gibt '' bei OK, sonst den Defekt."""
    pfad = REPO / a
    if not pfad.exists():
        return f"Artefakt fehlt: {a}"
    ist = _bereich(pfad, von, bis)
    if _h(ist) != sha:
        return f"{a}:{von}-{bis} Bereichs-SHA weicht ab"
    if ist.rstrip("\n") != text.rstrip("\n"):
        return f"{a}:{von}-{bis} Wortlaut weicht trotz SHA ab"
    if _h(pfad.read_bytes().decode("utf-8")) != dsha:
        return f"{a} Datei-SHA weicht ab — Artefakt AUSSERHALB des Bereichs geaendert"
    if len(_zeilen(pfad)) != zeilen:
        return f"{a} Zeilenzahl {len(_zeilen(pfad))} != belegt {zeilen}"
    return ""


def prosa_gate(text: str, belegte: set[tuple[str, int, int]]) -> list[str]:
    """Jede Datei:Zeile-Referenz muss ein Beleg sein. Rueckgabe: Luecken."""
    luecken = []
    for m in PROSA.finditer(text):
        a, v = m.group(1), int(m.group(2))
        b = int(m.group(3) or v)
        # akzeptiere, wenn irgendein Beleg der Datei den Bereich deckt
        if not any(x == a and v >= lo and b <= hi for x, lo, hi in belegte):
            luecken.append(f"{a}:{v}" + (f"-{b}" if b != v else ""))
    return luecken


def belegte_aus_ledger() -> set[tuple[str, int, int]]:
    if not LEDGER.exists():
        return set()
    out = set()
    for z in LEDGER.read_text(encoding="utf-8").splitlines():
        if z.strip():
            e = json.loads(z)
            out.add((e["artefakt"], e["von"], e["bis"]))
    return out


def check(strict: bool = False, prosa_pfad: str | None = None) -> int:
    belege = [json.loads(z) for z in
              LEDGER.read_text(encoding="utf-8").splitlines() if z.strip()] \
        if LEDGER.exists() else []
    defekte = 0
    for e in belege:
        befund = pruefe_block(e["artefakt"], e["von"], e["bis"], e["sha256"],
                              e["sha256_datei"], e["zeilen"], e["text"])
        print(f"{'ok  ' if not befund else 'ROT '} {e['artefakt']}:{e['von']}-{e['bis']} "
              f"[{e.get('runde','?')}] {befund}")
        defekte += bool(befund)
    if prosa_pfad:
        luecken = prosa_gate(Path(prosa_pfad).read_text(encoding="utf-8"),
                             belegte_aus_ledger())
        for l in luecken:
            print(f"ROT  Prosa-Referenz ohne Beleg: {l}")
        defekte += len(luecken)
    print(f"\n{defekte} Defekt(e) in {len(belege)} Beleg(en)")
    return 1 if (strict and defekte) else 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("cite", "check"):
        print(__doc__)
        return 2
    if argv[0] == "check":
        pp = argv[argv.index("--prosa") + 1] if "--prosa" in argv else None
        return check("--strict" in argv, pp)
    args = [a for a in argv[1:] if not a.startswith("--")]
    if "--stdin" in argv:
        luecken = prosa_gate(sys.stdin.read(), belegte_aus_ledger())
        for l in luecken:
            print(f"ROT  {l}")
        print(f"{len(luecken)} unbelegte Prosa-Referenz(en)")
        return 1 if luecken else 0
    if len(args) != 2:
        print("cite <datei> <von>:<bis> [--publish]")
        return 2
    von, bis = (int(x) for x in args[1].split(":"))
    e = beleg(args[0], von, bis)
    if "--publish" in argv:
        print(json.dumps(e, ensure_ascii=False, indent=2))
    else:
        print(zitiere(e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
