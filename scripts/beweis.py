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
# Prosa-Referenzen (R105 erweitert — drei Luecken, alle real gefunden):
#   1 datei:zeile  mit beliebiger Endung (auch .git/hooks/pre-commit)
#   2 datei:von-bis
#   3 L<zahl> — Transcript-Zeilennummer ohne Artefakt. Genau der Defekt
#     aus P0b: "Zeile 8123" als Beweis ohne pruefbare Adresse.
PROSA = re.compile(
    r"(?P<pfad>[\w./-]*[\w-]):(?P<von>\d+)(?:-(?P<bis>\d+))?"
    r"|(?<![\w-])L(?P<lzeile>\d+)")


def _zeilen(pfad: Path) -> list[str]:
    return pfad.read_text(encoding="utf-8").splitlines()


def _bereich(pfad: Path, von: int, bis: int) -> str:
    zs = _zeilen(pfad)
    if von < 1 or bis > len(zs) or von > bis:
        raise ValueError(f"{pfad.name}: Bereich {von}-{bis} ungueltig "
                         f"(Datei hat {len(zs)} Zeilen)")
    # BEWEIS-SPEC v1 §2: LF only, kein CRLF, genau ein Trailing-LF.
    return "\n".join(z.rstrip("\r") for z in zs[von - 1:bis]) + "\n"


def kanonisch(text: str) -> bytes:
    """BEWEIS-SPEC v1 §2 — die EINZIGE Kanonisierung.

    LF only, kein CRLF, genau ein Trailing-LF, UTF-8 ohne BOM.
    Wer publiziert, MUSS diese Bytes schreiben. Wer prueft, MUSS sie
    hashen. Zwei Implementierungen waeren zwei Wahrheiten.
    """
    t = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    return (t.rstrip("\n") + "\n").encode("utf-8")


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def beleg(artefakt: str, von: int, bis: int, runde: str = "",
          warum: str = "") -> dict:
    pfad = REPO / artefakt
    inhalt = _bereich(pfad, von, bis)
    return {"artefakt": artefakt, "von": von, "bis": bis,
            "sha256": hashlib.sha256(kanonisch(inhalt)).hexdigest(),
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
    if hashlib.sha256(kanonisch(ist)).hexdigest() != sha:
        return f"{a}:{von}-{bis} Bereichs-SHA weicht ab"
    if ist.rstrip("\n") != text.rstrip("\n"):
        return f"{a}:{von}-{bis} Wortlaut weicht trotz SHA ab"
    return ""


def provenienz(a: str, dsha: str, zeilen: int) -> str:
    """BEWEIS-SPEC v1 §4: Datei-SHA ist Versionszeiger, keine Beweisbindung.

    Das Zitat bleibt wahr, wenn sich die Datei anderswo aendert. Deshalb
    meldet Provenienz-Drift sichtbar, blockiert aber nur mit --provenienz-streng.
    """
    pfad = REPO / a
    if not pfad.exists():
        return f"Artefakt fehlt: {a}"
    if _h(pfad.read_bytes().decode("utf-8")) != dsha:
        return f"{a}: Datei-SHA abweichend (Versionszeiger, Zitat unberuehrt)"
    if len(_zeilen(pfad)) != zeilen:
        return f"{a}: {len(_zeilen(pfad))} Zeilen statt belegt {zeilen}"
    return ""


def prosa_gate(text: str, belegte: set[tuple[str, int, int]]) -> list[str]:
    """Jede Datei:Zeile-Referenz muss ein Beleg sein. Rueckgabe: Luecken."""
    luecken = []
    # Exemption (R105): Zeilen, die als ZITAT einer Gate-Ausgabe markiert
    # sind, werden nicht geprueft — sonst ist jede Gate-Fehlermeldung
    # (die selbst file:zeile traegt) ein Gate-Verstoss.
    # Konvention: die Zeile beginnt mit "ZITAT>" oder folgt auf eine
    # Zeile, die genau "ZITAT-AUSGABE" lautet.
    zeilen = text.splitlines()
    ausgenommen = set()
    aktiv = False
    for i, z in enumerate(zeilen):
        if z.strip() == "ZITAT-AUSGABE":
            aktiv = True
            continue
        if aktiv:
            if not z.strip():
                aktiv = False
            else:
                ausgenommen.add(i)
    for m in PROSA.finditer(text):
        zi = text.count("\n", 0, m.start())
        if zi in ausgenommen:
            continue
        if m.group("lzeile"):
            luecken.append(f"L{m.group('lzeile')} (Transcript-Zeile ohne Artefakt)")
            continue
        a, v = m.group("pfad"), int(m.group("von"))
        b = int(m.group("bis") or v)
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
    streng_p = "--provenienz-streng" in sys.argv
    for e in belege:
        # Beweisbindung: Region. Blockiert immer.
        befund = pruefe_block(e["artefakt"], e["von"], e["bis"], e["sha256"],
                              e["sha256_datei"], e["zeilen"], e["text"])
        # Provenienz: Datei. Sichtbar; blockiert nur mit Flag (Spec §4).
        prov = provenienz(e["artefakt"], e["sha256_datei"], e["zeilen"])
        print(f"{'ok  ' if not befund else 'ROT '} {e['artefakt']}:{e['von']}-{e['bis']} "
              f"[{e.get('runde','?')}] {befund}")
        if prov:
            print(f"{'ROT ' if streng_p else 'PROV'} {prov}")
        defekte += bool(befund) + (bool(prov) and streng_p)
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
        out = REPO / "publiziert"
        out.mkdir(exist_ok=True)
        stem = f"{args[0].replace('/', '__')}_{von}-{bis}"
        (out / f"{stem}.payload.txt").write_bytes(kanonisch(e["text"]))
        (out / f"{stem}.beleg.json").write_text(
            json.dumps(e, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(e, ensure_ascii=False, indent=2))
    else:
        print(zitiere(e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
