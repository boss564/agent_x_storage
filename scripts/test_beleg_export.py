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

try:
    import hole_r106_aus_transkript as _H
    R106_B64 = _H.hole()
except (SystemExit, FileNotFoundError):
    R106_B64 = None  # Transkript nicht am Ort -> Tests ueberspringen


def test_r106_hat_zwei_defekte_header_ist_korrekt():
    if R106_B64 is None:
        return  # Transkript nicht verfuegbar

    """R110: Die GELIEFERTE R106-Kette (Transkript Zeile 8306) hat ZWEI Ops.

      insert  178  '' -> 'r'         (Vetragsscope, GRUEN-Zeile)
      replace 216  U+260C -> U+274C  (\u260c statt \u274c)
    Header bei 22 ist KORREKT ('Vertragsscop').
    Ende ist in BEIDEN identisch '$$rc\\n'.

    Falsch waren: R107 (Byte 178 'r' -- Substanz richtig, aber sha falsch),
    R108 (shift +1, 243 Abweichungen), R109 (ERFUNDENER replace@24 gegen
    eine selbst geschriebene Fixture), R109-Review-Tail (fehlendes c).

    Die Fixture ist jetzt byte-exakt aus dem Transkript uebernommen.
    """
    import difflib
    q = (E.REPO / "publiziert/Makefile_56-63.payload.txt")
    if not q.exists():
        return
    q = q.read_bytes()
    g = base64.b64decode(R106_B64)
    assert len(g) == 439 and len(q) == 440
    assert g.endswith(b"$$rc\n") and q.endswith(b"$$rc\n")
    ops = [(t, i1, i2, j1, j2) for t, i1, i2, j1, j2
           in difflib.SequenceMatcher(a=g, b=q, autojunk=False).get_opcodes()
           if t != "equal"]
    assert [o[0] for o in ops] == ["insert", "replace"], ops
    assert ops[0][1] == 178 and q[178:179] == b"r"     # Vetragsscope fehlt r
    assert ops[1][1] == 216 and g[216:217] == b"\x98"  # ☌ U+260C
    assert q[217:218] == b"\x9d"                      # ❌ U+274C
    # Header ist KORREKT: kein replace@24 in der gelieferten Kette
    assert g[22:34] == b"Vertragsscop"


def test_r106_sha_der_gelieferten_bytes():
    if R106_B64 is None:
        return  # Transkript nicht verfuegbar

    """SHA der TATSAECHLICH gelieferten 439 Bytes (Transkript Zeile 8306).

    R108 verwarf 3025... als 'falsch' und setzte 2205... -- letzteres war
    der SHA einer selbstgeschriebenen Fixture ('Veetragsscope').
    3025... ist der SHA dessen, was der Auditor bekam.
    """
    import base64
    assert (hashlib.sha256(base64.b64decode(R106_B64)).hexdigest()
            == "30257636d107f7019074d85de4742e119f0faa24ddcf6340e0741d4ce7b00b52")


def test_einfuegung_wird_als_insert_gemeldet():
    """Eine Einfuegung ist EIN insert-Op, nicht N Abweichungen."""
    q = b"abcdefghij"
    g_b64 = base64.b64encode(b"abXcdefghij").decode()
    d = E.diff_gegen_quelle(g_b64, q)
    assert d["n_ops"] == 1
    assert d["ops"][0]["op"] == "delete"
    assert d["ops"][0]["a_bytes"] == b"X"
    assert d["ops"][0]["a_pos"] == 2


def test_reine_ersetzung_ist_ein_replace():
    q = b"abcdefghij"
    g_b64 = base64.b64encode(b"abcXefghij").decode()
    d = E.diff_gegen_quelle(g_b64, q)
    assert d["n_ops"] == 1
    assert d["ops"][0]["op"] == "replace"
    assert d["ops"][0]["a_bytes"] == b"X"
    assert d["ops"][0]["b_bytes"] == b"d"


# --- R111: Kuerzung und getippte Hex-Werte ------------------------------

def test_gekuerzte_base64_wird_rot():
    """R107 §3 lieferte 'CUBlY2hv...bz4=' -- Mitte abgeschnitten.
    Ein gekuerzter Beleg ist kein Beleg."""
    p = E.paket("Makefile", 56, 63)
    p_kuerz = dict(p, base64=p["base64"][:40] + "..." + p["base64"][-4:])
    fehler = E.pruefe_paket(p_kuerz)
    assert any("gekuerzt" in f for f in fehler), fehler


def test_getippter_hex_wert_wird_rot():
    """R109 §4 behauptete '24 47 24 63 0a' fuer '$rc\\n'.
    Echt (beide Ketten): '20 24 24 72 63 0a' = ' $$rc\\n'."""
    p = E.paket("Makefile", 56, 63)
    assert p["hex_ende"] == "20 24 24 72 63 0a"
    p_falsch = dict(p, hex_ende="24 47 24 63 0a")
    fehler = E.pruefe_paket(p_falsch)
    assert any("hex_ende" in f for f in fehler), fehler


# --- R112: der Block muss sich selbst pruefen ----------------------------

def test_beleg_block_gruen():
    import beleg_block as BB
    block = BB.erzeuge("Makefile", 56, 63)
    assert BB.pruefe(block) == [], BB.pruefe(block)
    assert block.splitlines()[0].startswith("BELEG laenge=440 ")
    assert "hex_ende=20 24 24 72 63 0a" in block.splitlines()[0]


def test_r111_verstuemmelter_block_wird_rot():
    """R111 §2 druckte 586 statt 588 Zeichen; ab Pos. 539 verstuemmelt.
    Der Block traegt den korrekten Kopf, aber falsche Bytes -> ROT."""
    import beleg_block as BB, hole_r106_aus_transkript as H
    if R106_B64 is None:
        return
    import base64 as _b64
    g = _b64.b64decode(H.hole())
    kopf = (f"BELEG laenge={len(g)} sha256={hashlib.sha256(g).hexdigest()} "
            f"padding=g== hex_ende={g[-6:].hex(' ')}")
    verstuemmelt = H.hole()[:539] + "agtICQkcmMpIiA7OyBcCgkgIGV4aXQgJCRyYw=="
    fehler = BB.pruefe(kopf + "\n" + verstuemmelt + "\n")
    assert any("sha256" in f for f in fehler), fehler
    assert any("laenge" in f for f in fehler), fehler


def test_gekuerzter_block_wird_rot():
    import beleg_block as BB
    block = BB.erzeuge("Makefile", 56, 63)
    kopf, b64 = block.strip().split("\n")
    rot = kopf + "\n" + b64[:200] + "..." + b64[-8:] + "\n"
    assert any("gekuerzt" in f for f in BB.pruefe(rot))
