#!/usr/bin/env python3
"""Projektion: der Strom-Exit muss aus den Zeilen-Urteilen folgen.

Der Vertrag ist das ORAKEL. Der Produktionscode liest ihn NICHT.
Damit koennen Code und Vertrag widersprechen — und der Drift-Test
findet es.

  Schicht 1 (main return)      <-> Schicht 3 (Vertrag) : _wahl_grund
  Schicht 2 (exit_aus_zeilen)  <-> Schicht 3 (Vertrag) : _drift_check
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

V = Path(__file__).resolve().parent / "waechter_vertrag.json"
W = Path(__file__).resolve().parent / "einwurf_waechter.py"
A = "A" * 500
B = "B" * 500


def _z(ts: str, txt: str) -> str:
    return json.dumps({"role": "user", "message": {
        "content": f"<timestamp>{ts}</timestamp>\n{txt}"}},
        ensure_ascii=False)


def _lauf(zeilen):
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "strom.jsonl"
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True, cwd=td)
        return r.returncode, r.stdout


def _mapping() -> dict:
    v = json.loads(V.read_text(encoding="utf-8"))
    return v["ausgabe_grammatik"]["exit_semantik"]["projection_mapping"]


def _erwartet_exit(out: str) -> int:
    m = _mapping()
    urteile = set(re.findall(r"ZEILE \S+ ([A-Z]+);", out))
    for urteil in m["praezedenz"]:
        if urteil in urteile:
            return int(m["urlteil_zu_exit"][urteil])
    return 0


def _ist_556b(out: str) -> bool:
    return bool(re.search(r"^STROM UNLESBAR;grund=Stream nicht lesbar:", out, re.M))


def _lade_waechter():
    spec = importlib.util.spec_from_file_location("einwurf_waechter", str(W))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wahl_grund() -> int:
    ok = gesamt = 0
    faelle = [
        ("nur neu (rc0)", [_z("T1", A), _z("T2", B)], 0),
        # rc=1: gleicher Text, ANDERER Zeitstempel -> WIEDERHOLUNG -> rc 1
        ("wiederholung (rc1)", [_z("T1", A), _z("T2", A)], 1),
        # rc=2: gleicher Text, GLEICHER Zeitstempel -> VERWERFEN -> rc 2
        ("kanal-duplikat (rc2)", [_z("T1", A), _z("T1", A)], 2),
        ("nur muell (rc4)", ["KEIN JSON"], 4),
        ("verw+muell (rc2)", [_z("T1", A), _z("T1", A), "KEIN JSON"], 2),
        ("wied+muell (rc4)", [_z("T1", A), _z("T2", A), "KEIN JSON"], 4),
    ]
    print("\n== Projektionsfaelle (Schicht 1 <-> 3) ==")
    for name, zeilen, soll in faelle:
        gesamt += 1
        code, out = _lauf(zeilen)
        abg = _erwartet_exit(out)
        gut = code == abg == soll
        print(f"{'ok  ' if gut else 'FAIL'} {name:22s} exit={code} "
              f"aus_vertrag={abg} soll={soll}")
        ok += gut

    gesamt += 1
    r = subprocess.run([sys.executable, str(W)], capture_output=True, text=True)
    abg = _erwartet_exit(r.stdout)
    gut = r.returncode == abg == 2
    print(f"{'ok  ' if gut else 'FAIL'} {'kein modus (rc2)':22s} "
          f"exit={r.returncode} aus_vertrag={abg} soll=2")
    ok += gut

    gesamt += 1
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "x.jsonl"
        f.write_text(_z("T1", A) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--einwurf", str(f),
                            "--strom", "/tmp/gibt-es-nicht-r23.jsonl"],
                           capture_output=True, text=True, cwd=td)
    hat_zeile = bool(re.search(r"^ZEILE ", r.stdout, re.M))
    gut = r.returncode == 3 and _ist_556b(r.stdout) and not hat_zeile
    print(f"{'ok  ' if gut else 'FAIL'} {'556 stream (rc3)':22s} "
          f"exit={r.returncode} strom={_ist_556b(r.stdout)} zeile={hat_zeile}")
    ok += gut

    # rc=2-Kollisionspfade: --strom ohne Wert darf NICHT mehr crashen
    for name, args, soll_grund in [
        ("strom ohne wert (V2)", ["--einwurf", "/tmp/ein23.jsonl", "--strom"],
         "strom_ohne_wert"),
        ("strom ohne wert (V3)", ["--strom"], "strom_ohne_wert"),
        ("einwurf ohne wert (V4)", ["--strom", "/tmp/ein23.jsonl", "--einwurf"],
         "einwurf_ohne_wert"),
        ("einwurf ohne strom (V5)", ["--einwurf"], "einwurf_ohne_strom"),
        # asymmetrischer Fall: Modus --strom gesetzt, --einwurf ohne Wert
        ("einwurf ohne wert (V6)", ["--strom", "/tmp/y24.jsonl", "--einwurf"],
         "einwurf_ohne_wert"),
    ]:
        gesamt += 1
        r = subprocess.run([sys.executable, str(W)] + args,
                           capture_output=True, text=True)
        token = ("ZEILE AUFRUF VERWERFEN;grund=" in r.stdout
                 and "grund=kein_modus" not in r.stdout)
        grund = next((t.split("grund=")[1].split(";")[0]
                      for t in r.stdout.split(";") if "grund=" in t), None)
        token = token and grund == soll_grund
        no_tb = "Traceback" not in r.stderr
        gut = r.returncode == 2 and token and no_tb
        print(f"{'ok  ' if gut else 'FAIL'} {name:22s} exit={r.returncode} "
              f"token={token} kein_tb={no_tb}")
        ok += gut

    print(f"\n{ok}/{gesamt} Projektions-Faelle gruen")
    return 0 if ok == gesamt else 1


def _drift_check() -> int:
    """Schicht 2 (exit_aus_zeilen) <-> Schicht 3 (Vertrag)."""
    print("\n== Drift-Check exit_aus_zeilen <-> projection_mapping ==")
    w = _lade_waechter()
    m = _mapping()
    mapping = {k: int(v) for k, v in m["urlteil_zu_exit"].items()}
    schwere = {int(k): int(v) for k, v in m["schwere"].items()}
    terminator = {int(t) for t in m["terminator"]}
    ok = gesamt = 0
    for urteil, erwartet in mapping.items():
        gesamt += 1
        got = w.exit_aus_zeilen([f"ZEILE deadbeef {urteil};x=1;"])
        gut = got == erwartet
        print(f"{'ok  ' if gut else 'FAIL'} urteil={urteil:12s} code={got} vertrag={erwartet}")
        ok += gut
    kombis = [
        ({"VERWERFEN","UNGEPRUEFT"}, "VERWERFEN"),
        ({"UNGEPRUEFT","WIEDERHOLT"}, "UNGEPRUEFT"),
        ({"WIEDERHOLT","ZUSTELLEN"}, "WIEDERHOLT"),
        ({"VERWERFEN","ZUSTELLEN"}, "VERWERFEN"),
    ]
    for urteile, sieger in kombis:
        gesamt += 1
        bericht = [f"ZEILE deadbeef {u};x=1;" for u in urteile]
        erwartet = mapping[sieger]
        got = w.exit_aus_zeilen(bericht)
        gut = got == erwartet
        print(f"{'ok  ' if gut else 'FAIL'} kombi={','.join(sorted(urteile)):30s} code={got} vertrag={erwartet}")
        ok += gut
    # Terminator gewinnt gegen JEDE Schwere, nicht nur eine
    for term in terminator:
        for other in schwere:
            if other == term:
                continue
            gesamt += 1
            got = w.aggregiere(other, term)
            gut = got == term
            print(f"{'ok  ' if gut else 'FAIL'} aggregiere({other},{term}) = {got} soll={term}")
            ok += gut
    # Cross-Check: praezedenz-Liste und schwere-Zahlen muessen dieselbe
    # Ordnung kodieren. Sonst kann eine Vertragseditur beide widerspruechlich
    # machen, und kein Test faengt es.
    prae = m["praezedenz"]
    for hi, lo in zip(prae, prae[1:]):
        gesamt += 1
        ch, cl = mapping[hi], mapping[lo]
        if ch in terminator or cl in terminator:
            soll_ok = ch in terminator or ch == cl
        else:
            soll_ok = schwere[ch] > schwere[cl]
        print(f"{'ok  ' if soll_ok else 'FAIL'} praezedenz: {hi} vor {lo} "
              f"(schwere {schwere[ch]} vs {schwere[cl]})")
        ok += soll_ok
    inhaltlich = [c for c in schwere if c not in terminator]
    for a in inhaltlich:
        for b in inhaltlich:
            if a == b: continue
            gesamt += 1
            got = w.aggregiere(a, b)
            erwartet = a if schwere[a] > schwere[b] else b
            gut = got == erwartet
            print(f"{'ok  ' if gut else 'FAIL'} aggregiere({a},{b}) = {got} soll={erwartet}")
            ok += gut

    print(f"\n{ok}/{gesamt} Drift-Faelle gruen")
    return 0 if ok == gesamt else 1


def main() -> int:
    rc1 = _wahl_grund()
    rc2 = _drift_check()
    return 0 if rc1 == 0 and rc2 == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
