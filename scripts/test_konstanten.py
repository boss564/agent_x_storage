#!/usr/bin/env python3
"""Konstanten-Test: fängt richtig *geratene* Zahlen, nicht nur falsche.

§A-ZZZZ130 (Runde 83): **ein Fixture-Wert fängt nur falsche Konstanten.**

Der Mutant `KANAL-DUPLIKAT=37` bestand den Vertrag der Runde 82, weil
das einzige Fixture 37 erwartete. 37 == 37. Ein Detektor, der die Zahl
hartkodiert statt zu zaehlen, waere damit zertifiziert worden.

Dieser Test faehrt **drei synthetische Stroeme mit abweichenden
Soll-Werten** gegen den echten Waechter. Erst abweichende Erwartungen
binden die Rechnung an die Eingabe:

    Fixture A: 1 Meldung, 0 Duplikate        -> Paare=0
    Fixture B: 2 identisch + 1 verschieden   -> Paare=1, KANAL-DUPLIKAT=1
    Fixture C: 3 identisch, ts verschieden   -> Paare=2, WIEDERHOLUNG=2

Kein fester Wert kann alle drei bestehen. Die Soll-Werte stammen aus der
Fixture-Konstruktion (ich zaehle, was ich hineinlege), nicht aus der
Ausgabe des Prueflings — sonst ratifizierte der Vertrag einen
systematischen Zaehlfehler.

Der Live-Strom-Snapshot (38/37/1) ist bewusst **nicht** hier: er wandert
mit jeder neuen Meldung und wuerde CI rot faerben, ohne dass ein Defekt
vorliegt.

D4 Drift 11→12→…: zusaetzliche Expand-Fixtures (Dispatcher/L4/P7) —
keine Producer-Regression. Aktuelle Zaehlung steht im Footer.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from achsen_invariante import (
    ACHSEN_META_6,
    ACHSEN_STROM_8,
    AchsenKlasse,
    ERLAUBT_META_KEYS,
    ERLAUBT_STROM_KEYS,
    SCHEMA_KERN_ALT5,
    VERDICT_TAIL_KEYS,
    akzeptiert_contract,
    akzeptiert_expand,
    achsenzeile_fremdkeys,
    bewerte_achsenzeile,
    erste_achsenzeile,
    parse_messachse,
)

W = Path(__file__).resolve().parent / "einwurf_waechter.py"
_REPO = Path(__file__).resolve().parent.parent
A = "A" * 500
B = "B" * 500


def _head_alt5_from_vertrag() -> frozenset[str]:
    """C4/D12: Alt5-Orakel aus Freeze-Datei, nicht aus SCHEMA_KERN_ALT5.

    Quelle: scripts/orakel_head_messachse_alt5.json (Freeze von
    HEAD:waechter_vertrag.json zum Commit-R-Baseline-SHA — siehe Datei).
    Kein `git show` zur Laufzeit: Hook-TMP hat kein .git.
    Dual-Alt5 = Grammatik-Intersektion. Formale Rekonziliation = Commit 1.
    """
    doc = json.loads(
        (Path(__file__).resolve().parent / "orakel_head_messachse_alt5.json")
        .read_text(encoding="utf-8")
    )
    return frozenset(doc["messachse"])

# P7: LESESTAT-Zustand → erwarteter achse()-Return (nach Flip).
# Spec: achse() liest LESESTAT["kurz"]/["envelope"]; uebersprungen = Summe;
# json = LESESTAT["json"] (nach E4 ohne ueber-Ternary).
# Status: Code-Lesung/Spec fuer Commit R; Messung = G3 in Commit 1.
LESESTAT_ACHSE_PAARE = (
    ("F-Summe-Paar",
     {"json": 1, "kurz": 2, "envelope": 3},
     {"json": 1, "kurz": 2, "envelope": 3, "uebersprungen": 6}),
    ("F-Alias-unmoeglich-nach-Flip",
     {"json": 1, "kurz": 1, "envelope": 1},
     {"json": 1, "kurz": 1, "envelope": 1, "uebersprungen": 3}),
    ("F-Null-Paar",
     {"json": 0, "kurz": 0, "envelope": 0},
     {"json": 0, "kurz": 0, "envelope": 0, "uebersprungen": 0}),
)

# V4 Negativfixture: Alias und Summe wahr, trotzdem Fremd-Key → rot.
F_FREMD_SUMME_ZEILE = (
    "Meldungen=1;Paare=0;KANAL-DUPLIKAT=0;WIEDERHOLUNG=0;"
    "ZEITSTEMPEL-UNLESBAR=0;uebersprungen=1;json=1;kurz=0;envelope=0;Fremd=1"
)

# D1 Positiv: meta-6 passiert L4 und erreicht META.
F_META6_ZEILE = (
    "Paare=0;KANAL-DUPLIKAT=0;WIEDERHOLUNG=0;"
    "ZEITSTEMPEL-UNLESBAR=0;uebersprungen=0;json=0;"
)

# Dispatcher-Fixtures als volle Achsenzeilen (D3: nur bewerte_achsenzeile).
# (name, zeile, soll_klasse, expand_ok, contract_ok)
DISPATCHER_ZEILEN = (
    ("F-Alias",
     "Paare=0;KANAL-DUPLIKAT=0;WIEDERHOLUNG=0;ZEITSTEMPEL-UNLESBAR=0;"
     "uebersprungen=1;json=1;kurz=1;envelope=1;",
     AchsenKlasse.ALIAS, True, False),
    ("F-Summe",
     "Paare=0;KANAL-DUPLIKAT=0;WIEDERHOLUNG=0;ZEITSTEMPEL-UNLESBAR=0;"
     "uebersprungen=6;json=1;kurz=2;envelope=3;",
     AchsenKlasse.SUMME, True, True),
    ("F-Null",
     "Paare=0;KANAL-DUPLIKAT=0;WIEDERHOLUNG=0;ZEITSTEMPEL-UNLESBAR=0;"
     "uebersprungen=0;json=0;kurz=0;envelope=0;",
     AchsenKlasse.SUMME, True, True),
    ("F-meta",
     F_META6_ZEILE,
     AchsenKlasse.META, True, True),
    ("F-WertFehler",
     "Paare=0;KANAL-DUPLIKAT=0;WIEDERHOLUNG=0;ZEITSTEMPEL-UNLESBAR=0;"
     "uebersprungen=9;json=1;kurz=1;envelope=1;",
     AchsenKlasse.WERT_RELATION_FEHLER, False, False),
)


def _z(ts: str, txt: str) -> str:
    return json.dumps({"role": "user", "message": {
        "content": f"<timestamp>{ts}</timestamp>\n{txt}"}},
        ensure_ascii=False)


def _achse(stdout: str) -> dict[str, int]:
    # Kanonisch: achsen_invariante.parse_messachse (SP-1682 / V2).
    return parse_messachse(stdout)


def _erwarte_return_aus_lesestat(lesestat: dict[str, int]) -> dict[str, int]:
    """P7: Soll-Return aus LESESTAT-Dict (Summe-Formel).

    Kein Patch von einwurf_waechter.LESESTAT — reine Dict-Rechnung,
    testreihenfolge-unabhaengig (V7). Messung gegen echten Producer = G3.
    """
    j, k, e = lesestat["json"], lesestat["kurz"], lesestat["envelope"]
    return {"json": j, "kurz": k, "envelope": e, "uebersprungen": j + k + e}


def main() -> int:
    ok = 0
    gesamt = 0
    faelle = [
        ("A: 1 Meldung, 0 Duplikate",
         [_z("T1", A)],
         {"Paare": 0, "KANAL-DUPLIKAT": 0, "WIEDERHOLUNG": 0}),
        ("B: 2 identisch + 1 verschieden",
         [_z("T1", A), _z("T1", A), _z("T2", B)],
         {"Paare": 1, "KANAL-DUPLIKAT": 1, "WIEDERHOLUNG": 0}),
        ("C: 3 identisch, ts verschieden",
         [_z("T1", A), _z("T2", A), _z("T3", A)],
         {"Paare": 2, "KANAL-DUPLIKAT": 0, "WIEDERHOLUNG": 2}),
    ]
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for name, zeilen, soll in faelle:
            f = d / "strom.jsonl"
            f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
            r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                               capture_output=True, text=True, cwd=d)
            ist = _achse(r.stdout)
            gut = all(ist.get(k) == v for k, v in soll.items())
            diff = {k: (v, ist.get(k)) for k, v in soll.items()
                    if ist.get(k) != v}
            print(f"{'ok  ' if gut else 'FAIL'} {name:32s} "
                  f"{' '.join(f'{k}={v}' for k, v in soll.items())}"
                  + (f"  ABWEICHUNG soll/ist {diff}" if diff else ""))
            ok += gut
            gesamt += 1

    # Expand-Fixtures nur ueber bewerte_achsenzeile (D3: kein Direkt-_klassifiziere).
    for name, zeile, soll_klasse, expand_ok, contract_ok in DISPATCHER_ZEILEN:
        gesamt += 1
        bok, bgrund, klasse = bewerte_achsenzeile(zeile, modus="expand")
        # Contract-Sicht separat (Alias muss dort rot sein).
        cok, _, cklasse = bewerte_achsenzeile(zeile, modus="contract")
        gut = (
            klasse is soll_klasse
            and akzeptiert_expand(klasse) is expand_ok
            and akzeptiert_contract(cklasse) is contract_ok
            and bok is expand_ok
            and cok is contract_ok
        )
        print(f"{'ok  ' if gut else 'FAIL'} Pipeline {name:16s} "
              f"→ {klasse.value} expand={expand_ok} contract={contract_ok}"
              f" ({bgrund})")
        ok += gut

    # P7: LESESTAT→Return-Paare (Spec-Orakel; Messung folgt in G3/Commit 1).
    for name, lesestat, erwartet in LESESTAT_ACHSE_PAARE:
        gesamt += 1
        berechnet = _erwarte_return_aus_lesestat(lesestat)
        gut = berechnet == erwartet
        if gut:
            # Summe-Zeile durch volle Pipeline (nicht Direkt-Dispatcher).
            z = (f"Paare=0;KANAL-DUPLIKAT=0;WIEDERHOLUNG=0;"
                 f"ZEITSTEMPEL-UNLESBAR=0;uebersprungen={berechnet['uebersprungen']};"
                 f"json={berechnet['json']};kurz={berechnet['kurz']};"
                 f"envelope={berechnet['envelope']};")
            _, _, kl = bewerte_achsenzeile(z)
            gut = kl is AchsenKlasse.SUMME
        print(f"{'ok  ' if gut else 'FAIL'} LESESTAT-Paar {name:28s} "
              f"{berechnet}")
        ok += gut

    # V4: Fremd+Summe — L4 vor Dispatcher.
    gesamt += 1
    fok, fgrund, fklasse = bewerte_achsenzeile(F_FREMD_SUMME_ZEILE)
    gut = (not fok) and fklasse is AchsenKlasse.FREMD_KEYS and "Fremd" in fgrund
    print(f"{'ok  ' if gut else 'FAIL'} V4 Fremd+Summe Negativ   "
          f"ok={fok} klasse={fklasse.value} {fgrund}")
    ok += gut

    # D1: meta-6-Positiv — L4 durchlassen, META erreichen.
    gesamt += 1
    mok, mgrund, mklasse = bewerte_achsenzeile(F_META6_ZEILE)
    gut = mok and mklasse is AchsenKlasse.META and mgrund == "meta"
    print(f"{'ok  ' if gut else 'FAIL'} D1 meta-6 Positiv        "
          f"ok={mok} klasse={mklasse.value} {mgrund}")
    ok += gut

    # D4: Nicht-Messachsen-Zeile am Zeilenanfang — L4-Scope = Paare=-Zeile.
    gesamt += 1
    gemischt = "Fehler=2\n" + F_META6_ZEILE
    voll = parse_messachse(gemischt)  # darf Fehler mitziehen (Telemetrie)
    az = erste_achsenzeile(gemischt)
    dok, _, dklasse = bewerte_achsenzeile(az or "")
    gut = (
        "Fehler" in voll
        and az is not None
        and "Fehler" not in (az or "")
        and dok
        and dklasse is AchsenKlasse.META
    )
    print(f"{'ok  ' if gut else 'FAIL'} D4 Scope Paare-Zeile     "
          f"messung_hat_Fehler={'Fehler' in voll} "
          f"achsenzeile_ohne={az is not None and 'Fehler' not in (az or '')}")
    ok += gut

    # D6a/D9 Spot-Check (keine formale Rekonziliation — die = Commit 1/P8):
    # Neu: live ∈ {HEAD_ALT_5, STROM_8}; Alt: HEAD_ALT_5 aus git-HEAD-Vertrag.
    gesamt += 1
    gram = json.loads(
        (Path(__file__).resolve().parent / "waechter_vertrag.json")
        .read_text(encoding="utf-8")
    )["ausgabe_grammatik"]["messachse"]
    live = set(gram)
    HEAD_ALT_5 = _head_alt5_from_vertrag()  # C4: echte Quelle, nicht Spiegel
    gut = (
        ACHSEN_META_6 == ACHSEN_STROM_8 - {"kurz", "envelope"}
        and ERLAUBT_META_KEYS == ACHSEN_META_6
        and ERLAUBT_STROM_KEYS == ACHSEN_STROM_8 | {"Meldungen"}
        and VERDICT_TAIL_KEYS == frozenset({"treffer", "sha", "aktion", "grund"})
        and not ({"kurz", "envelope"} & VERDICT_TAIL_KEYS)
        and live in (HEAD_ALT_5, ACHSEN_STROM_8)
        and HEAD_ALT_5 <= ACHSEN_META_6
        and HEAD_ALT_5 == SCHEMA_KERN_ALT5  # Dual-Kern ≡ HEAD-Gramm
    )
    print(f"{'ok  ' if gut else 'FAIL'} D6a/D9 Spot Vokabel↔gram "
          f"HEAD_ALT_5={sorted(HEAD_ALT_5)} live={sorted(live)} "
          f"∈Alt5={live == HEAD_ALT_5} ∈STROM8={live == ACHSEN_STROM_8}")
    ok += gut

    # D6b: fehlender Kernkey → SCHEMA_LUECKE (nicht FREMD).
    gesamt += 1
    z_miss = (
        "Paare=0;KANAL-DUPLIKAT=0;ZEITSTEMPEL-UNLESBAR=0;"
        "uebersprungen=0;json=0;kurz=0;envelope=0;"
    )  # WIEDERHOLUNG fehlt
    bok, bgrund, bklasse = bewerte_achsenzeile(z_miss)
    gut = (not bok) and bklasse is AchsenKlasse.SCHEMA_LUECKE and "WIEDERHOLUNG" in bgrund
    print(f"{'ok  ' if gut else 'FAIL'} D6b SCHEMA fehlender Pflichtkey "
          f"ok={bok} klasse={bklasse.value} {bgrund}")
    ok += gut

    # D6c: kurz ohne envelope → SCHEMA_LUECKE (nicht META, nicht FREMD).
    gesamt += 1
    z_partial = (
        "Paare=0;KANAL-DUPLIKAT=0;WIEDERHOLUNG=0;ZEITSTEMPEL-UNLESBAR=0;"
        "uebersprungen=0;json=0;kurz=1;"
    )
    cok, cgrund, cklasse = bewerte_achsenzeile(z_partial)
    gut = (
        (not cok)
        and cklasse is AchsenKlasse.SCHEMA_LUECKE
        and "envelope" in cgrund
    )
    print(f"{'ok  ' if gut else 'FAIL'} D6c kurz-ohne-envelope   "
          f"ok={cok} klasse={cklasse.value} {cgrund}")
    ok += gut

    # D6d: Meldungen auf meta → FREMD (strom-only).
    gesamt += 1
    z_mm = (
        "Meldungen=1;Paare=0;KANAL-DUPLIKAT=0;WIEDERHOLUNG=0;"
        "ZEITSTEMPEL-UNLESBAR=0;uebersprungen=0;json=0;"
    )
    mok, mgrund, mklasse = bewerte_achsenzeile(z_mm)
    gut = (not mok) and mklasse is AchsenKlasse.FREMD_KEYS and "Meldungen" in mgrund
    print(f"{'ok  ' if gut else 'FAIL'} D6d meta+Meldungen Fremd "
          f"ok={mok} klasse={mklasse.value} {mgrund}")
    ok += gut

    # D7a: fremdkeys meta-Zweig OHNE Meldungen-Grant — direkte Membership-Messung.
    gesamt += 1
    meta_keys_mm = {
        "Paare", "KANAL-DUPLIKAT", "WIEDERHOLUNG", "ZEITSTEMPEL-UNLESBAR",
        "uebersprungen", "json", "Meldungen",
    }
    fk = achsenzeile_fremdkeys(meta_keys_mm, hat_meldungen=True)
    gut = fk == {"Meldungen"}
    print(f"{'ok  ' if gut else 'FAIL'} D7a fremdkeys meta∋Meldungen "
          f"fremd={sorted(fk)}")
    ok += gut

    # D7b/C5: Alt5-Fixture aus HEAD-Vertrag-Keys (+ Alias-Relation), nicht aus
    # SCHEMA_KERN_ALT5 gespiegelt. ZEITSTEMPEL fehlt, weil HEAD-Gramm ihn nicht hat.
    gesamt += 1
    HEAD_ALT_5 = _head_alt5_from_vertrag()
    gut_kern = (
        SCHEMA_KERN_ALT5 == HEAD_ALT_5
        and SCHEMA_KERN_ALT5 == ACHSEN_META_6 - {"ZEITSTEMPEL-UNLESBAR"}
    )
    kern_parts = [
        f"{k}=0" for k in sorted(HEAD_ALT_5 - {"uebersprungen", "json"})
    ]
    z_alt5 = (
        ";".join(kern_parts)
        + ";uebersprungen=1;json=1;kurz=1;envelope=1;"
    )
    aok, agrund, aklasse = bewerte_achsenzeile(z_alt5)
    gut = gut_kern and aok and aklasse is AchsenKlasse.ALIAS
    print(f"{'ok  ' if gut else 'FAIL'} D7b Alt5 HEAD-Alias L4   "
          f"src=orakel-freeze keys={sorted(HEAD_ALT_5)} "
          f"ok={aok} klasse={aklasse.value}")
    ok += gut

    # D7c: Praezedenz Shape→Kern→Fremd — fehlender Kern + Fremd → SCHEMA_LUECKE.
    gesamt += 1
    z_asym = (
        "Paare=0;KANAL-DUPLIKAT=0;ZEITSTEMPEL-UNLESBAR=0;"
        "uebersprungen=0;json=0;Fremd=1;"
    )  # WIEDERHOLUNG fehlt + Fremd
    sok, sgrund, sklasse = bewerte_achsenzeile(z_asym)
    gut = (
        (not sok)
        and sklasse is AchsenKlasse.SCHEMA_LUECKE
        and "WIEDERHOLUNG" in sgrund
    )
    print(f"{'ok  ' if gut else 'FAIL'} D7c Praezedenz Pflicht>Fremd "
          f"ok={sok} klasse={sklasse.value} {sgrund}")
    ok += gut

    print(f"\n{ok}/{gesamt} Konstanten-Proben gruen")
    print("Kein fester Wert besteht alle drei — die Zahl folgt der Eingabe.")
    print("P7-Paare: Spec/Code-Lesung; Producer-Messung = G3 (Commit 1).")
    print(
        "D10 Drift 14→18→21: +Abgleich(D6a) +Schema-Luecke(D6b) "
        "+Grenzfall(D6c) +meta+Meldungen(D6d) "
        "+fremdkeys-Messung(D7a) +Alt5-Alias(D7b) +Praezedenz(D7c)."
    )
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
