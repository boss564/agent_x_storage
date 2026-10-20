"""Hilfsfunktion fuer Tests: gueltiges Base64, falscher Inhalt (R113).

Der Kern der Beweiskette: Die Laengen-/Padding-Wache faengt einen
kaputten Block. Einen GUELTIG dekodierbaren Block mit veraendertem
Byte faengt nur sha256/hex_ende.
"""
import base64
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import beleg_export as E


def falscher_block() -> str:
    p = E.paket("Makefile", 56, 63)
    roh = bytearray(base64.b64decode(p["base64"]))
    roh[100] ^= 0x01                      # ein Bit kippen
    b64 = base64.b64encode(bytes(roh)).decode()
    kopf = (f"BELEG laenge={len(roh)} sha256={p['sha256']} "
            f"padding={p['padding']} hex_ende={p['hex_ende']}")
    return kopf + "\n" + b64 + "\n"
