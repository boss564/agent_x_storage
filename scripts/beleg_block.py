#!/usr/bin/env python3
"""Erzeugt einen Belegblock, der nicht getippt werden kann (R112).

Anlass: In R111 §2 wurde die R106-Kette von Hand in den Bericht
eingefuegt -- und ab Zeichen 539 verstuemmelt ('IHNagtICQkcmMp'
statt 'IHNhZ3QgJCRyYyki'). 586 statt 588 Zeichen, 438 statt 439 Bytes.
Die Selbstpruefung daneben behauptete weiterhin 439 -- sie war die
Ausgabe des Extrakors, nicht des gedruckten Blocks.

Wurzel: Der Bericht wird als Prosa geschrieben, die Bytes als Zitat
eingefuegt. Zwischen Werkzeug und Leser liegt eine Handschrift.

Loesung: Der Block wird als Datei erzeugt. Er traegt seine Pruefsumme
in der ersten Zeile. Wer ihn in einen Bericht uebernimmt, kopiert die
Datei -- und ein Leser kann den Block gegen seine eigene Kopfzeile
pruefen, ohne dem Autor zu glauben.

Format (Zeile 1 = Maschinen-Kopf, danach genau eine Base64-Zeile):
    BELEG laenge=439 sha256=3025... padding=g== hex_ende=20 24 24 72 63 0a
    CUBlY2hv...
"""
from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import beleg_export as E


def erzeuge(artefakt: str, von: int, bis: int) -> str:
    p = E.paket(artefakt, von, bis)
    kopf = (f"BELEG laenge={p['laenge']} sha256={p['sha256']} "
            f"padding={p['padding']} hex_ende={p['hex_ende']}")
    return f"{kopf}\n{p['base64']}\n"


def pruefe(block: str) -> list[str]:
    """Prueft einen kopierten Block gegen seine eigene Kopfzeile.

    Ein Leser braucht dafuer kein Repo -- nur den Block.
    """
    zeilen = block.strip("\n").split("\n")
    if len(zeilen) != 2:
        return [f"Block muss 2 Zeilen haben, hat {len(zeilen)}"]
    kopf, b64 = zeilen
    if not kopf.startswith("BELEG "):
        return ["Kopfzeile fehlt"]
    # hex_ende enthaelt Leerzeichen; deshalb regex statt split.
    import re as _re
    felder = {}
    for key in ("laenge", "sha256", "padding", "hex_ende"):
        m = _re.search(rf"{key}=(.*?)(?=\s+(?:laenge|sha256|padding|hex_ende)=|$)",
                       kopf[len("BELEG "):])
        if m:
            felder[key] = m.group(1).strip()
    fehler = []
    if "..." in b64 or "\u2026" in b64:
        fehler.append("Base64 gekuerzt")
    try:
        roh = base64.b64decode(b64)
    except Exception as e:
        return [f"Base64 unlesbar: {e}"]
    if str(len(roh)) != felder.get("laenge"):
        fehler.append(f"laenge: {len(roh)} != {felder.get('laenge')}")
    if hashlib.sha256(roh).hexdigest() != felder.get("sha256"):
        fehler.append("sha256 passt nicht zu den Bytes")
    if roh[-6:].hex(" ") != felder.get("hex_ende"):
        fehler.append(f"hex_ende {roh[-6:].hex(' ')!r} != {felder.get('hex_ende')!r}")
    erwartetes = "" if len(roh) % 3 == 0 else ("=" if len(roh) % 3 == 2 else "==")
    if (erwartetes or "-") != felder.get("padding"):
        fehler.append(f"padding {erwartetes or '-'} != {felder.get('padding')}")
    return fehler


def main(argv: list[str]) -> int:
    if argv[:1] == ["--pruefe"]:
        fehler = pruefe(Path(argv[1]).read_text(encoding="utf-8"))
        for f in fehler:
            print("ROT", f)
        return 1 if fehler else 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    von, bis = (int(x) for x in argv[1].split(":"))
    sys.stdout.write(erzeuge(argv[0], von, bis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
