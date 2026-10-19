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


# --- R108: der Diff muss gegen die GELIEFERTEN Bytes laufen --------------

R106_B64 = (
    "CUBlY2hvICLwn5SBIExBVUYg4oCUIFZlZXRyYWdzc2NvcGUgKDM3IFN1aXRlbiksIGVpbmUg"
    "WsOkaGxxdWVsbGU6IHRlc3RfemFlaGx3ZWlzZS56YWVobGUoKSIKCUBweXRob24zIHNjcmlwdHMv"
    "bGF1Zi5weTsgcmM9JCQ/OyBcCgkgIGNhc2UgJCRyYyBpbiBcCgkgICAgMCkgZWNobyAi4pyFIEdS"
    "VUVOIOKAlCBWZXRyYWdzc2NvcGUgZ3LDvG4iIDs7IFwKCSAgICAxKSBlY2hvICLimIwgRmVobGVy"
    "IOKAlCBTdWl0ZSByb3QgKG1ha2UgbWVsZGV0IDIsIE5JQ0hUIDEpIiA7OyBcCgkgICAgMikgZWNoby"
    "Ai4pqg77iPICBGZWhsZXIg4oCUIHVuZW50c2NoZWlkYmFyIG9kZXIgcm90IChtYWtlIG1lbGRldCAy"
    "KSIgOzsgXAoJICAgICopIGVjaG8gIuKaoO+4jyAgRmVobGVyIChtYWtlIG1lbGRldCAyLCBsYXVm"
    "LnB5IHNhZ3QgJCRyYykiIDs7IFwKCSAgZXNhYzsgZXhpdCAkJHJjCg==")


def test_r106_shift_ist_ein_byte_ab_position_24():
    """R108: Die R107-Diagnose ('Byte 178, r fehlt') war falsch.

    Tatsaechlich: Praefix ab Byte 24 != Quelle, Suffix 222 identisch,
    shift +1. Geliefert Byte 24 = 'e', Quelle = 'r'. Und das Ende
    '\\n' fehlt in der gelieferten Fassung.
    """
    q = E.REPO / "publiziert/Makefile_56-63.payload.txt"
    if not q.exists():
        return  # Quelle nicht im Baum (frischer Clone) -- Test ist dann stumm
    d = E.diff_gegen_quelle(R106_B64, q.read_bytes())
    assert d["laenge_geliefert"] == 439
    assert d["laenge_quelle"] == 440
    assert d["praefix_identisch"] == 24
    assert d["shift"] == 1
    assert d["geliefert_mitte"].startswith(b"etragsscope")
    assert d["quelle_mitte"].startswith(b"rtragsscope")


def test_r106_sha_der_gelieferten_bytes():
    """Die SHA der gelieferten 439 Bytes -- R107 behauptete hier faelschlich 3025..."""
    import base64
    assert (hashlib.sha256(base64.b64decode(R106_B64)).hexdigest()
            == "2205f240ea394941e92d19ba4493282e724d4c9d18238c4be7c646620e672168")


def test_einfuegung_ist_shift_nicht_n_einzelbytes():
    """Eine Einfuegung macht alle Folgebytes zu 'Abweichungen'. Der Diff
    muss das als shift melden, nicht als 243 Einzelbefunde."""
    q = b"abcdefghij"
    g_b64 = base64.b64encode(b"abXcdefghij").decode()
    d = E.diff_gegen_quelle(g_b64, q)
    assert d["shift"] == -1          # Quelle hat 1 Byte weniger
    assert d["praefix_identisch"] == 2
    assert d["suffix_identisch"] == 8


def test_reine_ersetzung_shift_null():
    q = b"abcdefghij"
    g_b64 = base64.b64encode(b"abcXefghij").decode()
    d = E.diff_gegen_quelle(g_b64, q)
    assert d["shift"] == 0
    assert d["geliefert_mitte"] == b"X"
    assert d["quelle_mitte"] == b"d"
