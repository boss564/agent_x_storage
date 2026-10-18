#!/usr/bin/env python3
"""Zwei unabhaengige Konsumenten — Divergenz als Messung, nicht als Meinung.

§A-ZZZZ173 (Runde 88): **eine Suite testet Implementation gegen
Implementation; nur ein Fremd-Konsument testet Spec gegen Implementation.**

Der Befund R88 sagt: solange die Konsumenten-Semantik nur in Testfaellen
existiert, kann jeder konforme Konsument anders handeln. Dieser Test
baut ZWEI Konsumenten, die den Vertrag lesen — nicht denselben Code
zweimal aufrufen:

  K1  liest `konsumenten_semantik.py` (die Norm als Code)
  K2  ist eine unabhaengige Nachimplementierung aus dem VERTRAGSTEXT
      allein: er bekommt ein Dict mit den Normfeldern und muss ohne
      Import von `konsumenten_semantik` zum selben Ergebnis kommen.

Divergieren sie, ist die Norm unterbestimmt — nicht der Test kaputt.
Genau das ist die Rolle, die ING spaeter spielt, nur im Kleinen.

Geprueft werden die fuenf offenen Fragen:
  1 Anker      drei Kopien, zwei Zeitstempel
  2 Drittfall  unlesbarer Zeitstempel
  3 Vorrang    ZEILE-Ereignis gegen DEDUP-Vorschrift
  4 Ordnung    gespiegelter Strom
  5 Default    regel-lose Wiederholung
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import konsumenten_semantik as K  # noqa: E402

W = SCRIPTS / "einwurf_waechter.py"
V = SCRIPTS / "waechter_vertrag.json"
A = "A" * 500


# ---------------------------------------------------------------- K2: fremd
def k2(regel: dict | None, ts: list[str | None]) -> list[str]:
    """Unabhaengige Nachimplementierung AUS DEM VERTRAGSTEXT.

    Bewusst anders geschrieben als K1: explizite if-Kette, kein
    NamedTuple, keine gemeinsamen Helfer. Wenn beide uebereinstimmen,
    stuetzt sich das Ergebnis nicht auf geteilten Code.
    """
    out = []
    for i in range(len(ts)):
        if i == 0:
            out.append("ZUSTELLEN")
            continue
        if regel is None:
            out.append("KEINE-REGEL")
            continue
        a, b = ts[i - 1], ts[i]
        if a is None or b is None:
            out.append(regel["bei_unlesbar"])   # Norm 2, dritter Zweig
        elif a == b:
            out.append(regel["bei_gleich"])      # Norm 1: i-1 ist der Anker
        else:
            out.append(regel["bei_ungleich"])
    return out


def _z(ts: str | None, txt: str = A) -> str:
    inner = f"<timestamp>{ts}</timestamp>\n{txt}" if ts is not None else txt
    return json.dumps({"role": "user", "message": {"content": inner}})


def _lauf(zeilen: list[str]) -> str:
    """§A-ZZZZ174: Exit 3 ist ein Befund, kein leerer stdout.

    Der erste Lauf gab einen RELATIVEN Pfad bei `cwd=td` — die Datei war
    nicht erreichbar, der Waechter meldete Exit 3, und dieser Helfer
    gab still "" zurueck. Ein Test, der nur stdout vergleicht, haette
    daraus "keine Ereignisse" statt "Strom unlesbar" gemacht.
    """
    with tempfile.TemporaryDirectory() as td:
        f = (Path(td) / "strom.jsonl").resolve()
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True)
        if r.returncode == 3:
            raise RuntimeError(f"Strom unlesbar (Exit 3): {r.stderr!r}")
        return r.stdout


def _felder(out: str) -> dict[str, str]:
    for z in out.splitlines():
        if z.startswith("DEDUP "):
            return dict(re.findall(r"([A-Za-z_][A-Za-z0-9_-]*)=([^;]*);", z))
    return {}


def main() -> int:
    ok = gesamt = 0
    out = _lauf([_z("T1"), _z("T1"), _z("T1")])
    regel = _felder(out)

    faelle = [
        ("1 Anker (T2 nach T1)", ["T1", "T2", "T2"],
         ["ZUSTELLEN", "WIEDERHOLT", "VERWERFEN"]),
        # §A-ZZZZ179 (R89): unlesbar ist UNGEPRUEFT, nicht WIEDERHOLT.
        # Das Soll wurde MIT der Norm geaendert — ein Test, dessen Soll
        # stehen bleibt, waehrend die Norm sich aendert, testet die alte.
        ("2 Drittfall unlesbar", ["T1", "T2", None],
         ["ZUSTELLEN", "WIEDERHOLT", "UNGEPRUEFT"]),
        ("2' alle unlesbar", [None, None],
         ["ZUSTELLEN", "UNGEPRUEFT"]),
        ("4 Ordnung gespiegelt", ["T2", "T1", "T1"],
         ["ZUSTELLEN", "WIEDERHOLT", "VERWERFEN"]),
        ("5 regel-los", ["T1", "T2"],
         ["ZUSTELLEN", "KEINE-REGEL"]),
    ]
    for name, ts, soll in faelle:
        r = regel if not name.startswith("5") else None
        k1 = [a.aktion for a in K.apply(r, ts)]
        k2r = k2(r, ts)
        gesamt += 1
        gut = k1 == k2r == soll
        print(f"{'ok  ' if gut else 'FAIL'} {name:24s} K1={k1} K2={k2r}")
        if not gut:
            print(f"       Soll={soll}")
        ok += gut

    # 3 Vorrang: ZEILE-Ereignis gewinnt gegen DEDUP-Vorschrift.
    gesamt += 1
    bericht = [_z("T1"), _z("T1")]
    _out = _lauf(bericht)
    ev = K.parse_zeilen(_out.splitlines())
    if not ev:
        print(f"FAIL 3 kein ZEILE-Record\n       Strom={bericht[0][:60]!r}\n"
              f"       Ausgabe={_out[:300]!r}")
        return 1
    h = next(iter(ev))
    gut = ev[h] == ["ZUSTELLEN", "VERWERFEN"] and len(ev) == 1
    print(f"{'ok  ' if gut else 'FAIL'} 3 Ereignisse aus ZEILE      {ev[h]}")
    ok += gut

    # 3' Der Vorrang ist im Vertrag benannt, nicht nur im Code.
    gesamt += 1
    d = json.loads(V.read_text(encoding="utf-8"))
    ks = d.get("konsumenten_semantik", {})
    gut = ks.get("vorrang") == K.VORRANG and ks.get("anker") == K.ANKER
    print(f"{'ok  ' if gut else 'FAIL'} 3' Norm im Vertrag          "
          f"vorrang={ks.get('vorrang')} anker={ks.get('anker')}")
    ok += gut

    # Der Anker steht auch im Record — der Konsument muss ihn nicht raten.
    gesamt += 1
    gut = regel.get("anker") == "vorgaenger"
    print(f"{'ok  ' if gut else 'FAIL'} Anker im Record            "
          f"anker={regel.get('anker')}")
    ok += gut

    print(f"\n{ok}/{gesamt} Konsumenten-Kongruenz-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
