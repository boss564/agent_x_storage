#!/usr/bin/env python3
"""Beleg-Export: Länge, Base64 UND Digest aus EINER Quelle (R107).

Befund R106: die Base64 im Bericht war getippt, nicht erzeugt. Zwei
Zeichen Unterschied am Ende (`Cg==` statt `Ywo=`), und im Payload
fehlte ein `r`: 'Vetragsscope'. Die Padding-Arithmetik hat es ohne
Shell verraten — `==` bedeutet Rest 1, die Datei hat 440 Bytes (Rest 2).

Die Lehre ist nicht "sorgfaeltiger tippen". Sie ist: drei Groessen,
die zusammengehoeren, duerfen nicht aus drei Quellen kommen.

Dieses Werkzeug erzeugt das Paket atomar:

    python3 scripts/beleg_export.py <artefakt> <von>:<bis>

und gibt aus:
    laenge:   <N>          (len der Bytes)
    mod3:     <N%3>        (muss zum Padding passen)
    base64:   <...>
    sha256:   <64 hex>
    padding:  <= / == / -> (vom Encoder, nicht gerechnet)

Ein Dritter prueft ohne Repo:
    echo '<base64>' | base64 -d | wc -c       -> laenge
    echo '<base64>' | base64 -d | sha256sum   -> sha256
"""
from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import beweis as B


def paket(artefakt: str, von: int, bis: int) -> dict:
    inhalt = B._bereich(REPO / artefakt, von, bis)
    roh = B.kanonisch(inhalt)
    b64 = base64.b64encode(roh).decode()
    pad = "" if len(roh) % 3 == 0 else ("=" if len(roh) % 3 == 2 else "==")
    return {"artefakt": artefakt, "von": von, "bis": bis,
            "laenge": len(roh), "mod3": len(roh) % 3,
            "padding": pad or "-",
            "base64": b64,
            "sha256": hashlib.sha256(roh).hexdigest()}


def pruefe_paket(p: dict) -> list[str]:
    """Invarianten, die ein Dritter OHNE Shell nachrechnen kann.

    GRENZE (R107): Diese Pruefung stellt nur SELBSTKONSISTENZ fest --
    Laenge, Padding und Digest passen zueinander. Sie kann eine
    konsistente Faelschung NICHT entdecken (Payload veraendert,
    439 statt 440 Bytes, '==' statt '=', eigener sha256 -> GRUEN).

    Inhaltstreue ist die Aufgabe von `beweis.py check` (Region-SHA
    gegen die Quelle). Zwei Fragen, zwei Werkzeuge:
      - "Sind die gelieferten Bytes das, was der Bericht behauptet?"  -> pruefe_paket
      - "Sind die gelieferten Bytes das, was in der Datei steht?"     -> beweise check
    Wer nur die erste stellt, kann an einer guten Base64 mit falschem
    Wort scheitern -- genau das war R106.
    """
    fehler = []
    roh = base64.b64decode(p["base64"])
    if len(roh) != p["laenge"]:
        fehler.append(f"Laenge: base64 dekodiert zu {len(roh)}, behauptet {p['laenge']}")
    erwartetes_pad = "" if p["laenge"] % 3 == 0 else ("=" if p["laenge"] % 3 == 2 else "==")
    if p["base64"].endswith("==") and p["laenge"] % 3 != 1:
        fehler.append(f"Padding: '==' verlangt Rest 1, Laenge {p['laenge']} hat Rest {p['laenge'] % 3}")
    if p["base64"].endswith("=") and not p["base64"].endswith("==") and p["laenge"] % 3 != 2:
        fehler.append(f"Padding: '=' verlangt Rest 2, Laenge {p['laenge']} hat Rest {p['laenge'] % 3}")
    if hashlib.sha256(roh).hexdigest() != p["sha256"]:
        fehler.append("Sha256 passt nicht zu den gelieferten Bytes")
    if p["padding"] != (erwartetes_pad or "-"):
        fehler.append(f"Padding-Feld {p['padding']} != {erwartetes_pad or '-'}")
    return fehler


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--self-check":
        e = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        fehler = pruefe_paket(e)
        print(f"{'ROT ' if fehler else 'ok  '}{e['artefakt']}:{e['von']}-{e['bis']}")
        for f in fehler:
            print(f"     {f}")
        return 1 if fehler else 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    von, bis = (int(x) for x in argv[1].split(":"))
    p = paket(argv[0], von, bis)
    print(f"artefakt: {p['artefakt']}:{p['von']}-{p['bis']}")
    print(f"laenge:   {p['laenge']}")
    print(f"mod3:     {p['mod3']}")
    print(f"padding:  {p['padding']}")
    print(f"sha256:   {p['sha256']}")
    print(f"base64:   {p['base64']}")
    return 0


if __name__ == "__main__":
    import json
    raise SystemExit(main(sys.argv[1:]))
