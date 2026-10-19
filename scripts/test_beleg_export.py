"""Tests fuer beleg_export: Selbstkonsistenz + Grenze (R107).

Der Kern: Die Padding-Arithmetik aus R106 muss ein Werkzeug sein,
kein Handgriff. Und: die Selbstkontrolle darf NICHT behaupten,
Inhaltstreue zu prüfen.
"""
import base64, hashlib, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import beleg_export as E


def test_paket_ist_selbstkonsistent():
    p = E.paket("Makefile", 56, 63)
    assert E.pruefe_paket(p) == [], E.pruefe_paket(p)
    assert len(base64.b64decode(p["base64"])) == p["laenge"]


def test_padding_lehre_aus_r106():
    """R106: gertippte Base64 endete mit 'Cg==' (Rest 1), Datei hat 440 Byte (Rest 2)."""
    p = E.paket("Makefile", 56, 63)
    assert p["laenge"] == 440
    assert p["laenge"] % 3 == 2
    assert p["base64"].endswith("Ywo=")          # ein '=', nicht '=='
    assert not p["base64"].endswith("==")


def test_getipptes_r106_paket_wird_rot():
    """Das gelieferte R106-Paket verletzt drei Invarianten."""
    getippt = {
        "artefakt": "Makefile", "von": 56, "bis": 63,
        "laenge": 440, "mod3": 2, "padding": "=",
        "base64": ("CUBlY2hvICLwn5SBIExBVUYg4oCUIFZlZXRyYWdzc2NvcGUgKDM3IFN1aXRlbiksIGVpbmUg"
                   "WsOkaGxxdWVsbGU6IHRlc3RfemFlaGx3ZWlzZS56YWVobGUoKSIKCUBweXRob24zIHNjcmlwdHMv"
                   "bGF1Zi5weTsgcmM9JCQ/OyBcCgkgIGNhc2UgJCRyYyBpbiBcCgkgICAgMCkgZWNobyAi4pyFIEdS"
                   "VUVOIOKAlCBWZXRyYWdzc2NvcGUgZ3LDvG4iIDs7IFwKCSAgICAxKSBlY2hvICLimIwgRmVobGVy"
                   "IOKAlCBTdWl0ZSByb3QgKG1ha2UgbWVsZGV0IDIsIE5JQ0hUIDEpIiA7OyBcCgkgICAgMikgZWNoby"
                   "Ai4pqg77iPICBGZWhsZXIg4oCUIHVuZW50c2NoZWlkYmFyIG9kZXIgcm90IChtYWtlIG1lbGRldCAy"
                   "KSIgOzsgXAoJICAgICopIGVjaG8gIuKaoO+4jyAgRmVobGVyIChtYWtlIG1lbGRldCAyLCBsYXVm"
                   "LnB5IHNhZ3QgJCRyYykiIDs7IFwKCSAgZXNhYzsgZXhpdCAkJHJjCg=="),
        "sha256": "b24985950ab17b2c4092cf68138baccd433a726e2970aacd5ff2975ba99ba6e4",
    }
    fehler = E.pruefe_paket(getippt)
    assert any("Laenge" in f for f in fehler), fehler
    assert any("Padding" in f for f in fehler), fehler
    assert any("Sha256" in f for f in fehler), fehler


def test_konsistente_faelschung_bleibt_gruen_und_das_ist_dokumentiert():
    """Grenze: veraenderter Payload mit passendem eigenen SHA -> GRUEN.

    Das ist KEIN Bug, sondern die Grenze der Selbstkonsistenz.
    Inhaltstreue prüft beweis.py check (Region-SHA).
    """
    roh = b"x" * 10
    p = {"artefakt": "egal", "von": 1, "bis": 1,
         "laenge": 10, "mod3": 10 % 3, "padding": "==",
         "base64": base64.b64encode(roh).decode(),
         "sha256": hashlib.sha256(roh).hexdigest()}
    assert E.pruefe_paket(p) == []


def test_sha_bindet_bytes():
    p = E.paket("Makefile", 56, 63)
    assert hashlib.sha256(base64.b64decode(p["base64"])).hexdigest() == p["sha256"]
