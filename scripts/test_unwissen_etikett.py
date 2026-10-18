#!/usr/bin/env python3
"""Unwissen ist kein Etikett — weder im Vergleich noch im Verdict.

§A-ZZZZ180 (Runde 89): **`"?"` und `WIEDERHOLT` sind dieselbe Krankheit.**

R88 beseitigte das erste Exemplar (`"?" == "?"` -> VERWERFEN) und baute
das zweite ein: `bei_unlesbar=WIEDERHOLT`. Ein Token, der seit R85
"bewusste Neusendung, belegt durch anderen Zeitstempel" heisst, behauptete
jetzt auch "wir wissen es nicht". Ein Downstream, der `WIEDERHOLT` als
Wiederholung behandelt, behandelt Unbekanntes als Bekanntes.

Zwei Defekte, gekoppelt:
  A  `_Unlesbar() != _Unlesbar()` ist True — ein boolesch vergleichender
     Konsument klassifiziert zwei Unlesbare als UNGLEICH.
  B  Bei `bei_unlesbar == bei_ungleich == WIEDERHOLT` ist der Fehler
     folgenlos — Kollaps als Deckel. R89 loest den Kollaps
     (bei_unlesbar=UNGEPRUEFT) und muss A im SELBEN Zug schliessen.
     Sonst detoniert A genau jetzt.

Dieser Test prueft beide zusammen. Er ist der Grund, warum A nicht
verschoben werden darf.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import konsumenten_semantik as K  # noqa: E402
from einwurf_waechter import UNLESBAR_TS, _Unlesbar, ts_vergleich  # noqa: E402

V = SCRIPTS / "waechter_vertrag.json"
W = SCRIPTS / "einwurf_waechter.py"
A = "A" * 500


def _strom(zeilen: list[str]) -> str:
    with tempfile.TemporaryDirectory() as td:
        f = (Path(td) / "s.jsonl").resolve()
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True)
        return r.stdout


def _z(ts: str | None) -> str:
    inner = f"<timestamp>{ts}</timestamp>\n{A}" if ts else A
    return json.dumps({"role": "user", "message": {"content": inner}})


def main() -> int:
    ok = gesamt = 0

    # A1: der totale Vergleich gewinnt gegen den booleschen.
    gesamt += 1
    gut = (ts_vergleich(UNLESBAR_TS, UNLESBAR_TS) == "unlesbar"
           and (UNLESBAR_TS == UNLESBAR_TS) is False)
    print(f"{'ok  ' if gut else 'FAIL'} A1 ts_vergleich vs ==       "
          f"total={ts_vergleich(UNLESBAR_TS, UNLESBAR_TS)!r} "
          f"bool={UNLESBAR_TS == UNLESBAR_TS}")
    ok += gut

    # A2: die Falle ist BENANNT — `==` ist im Vertrag verboten.
    gesamt += 1
    d = json.loads(V.read_text(encoding="utf-8"))
    ks = d["konsumenten_semantik"]
    gut = "ts_vergleich" in ks.get("vergleich_pflicht", "")
    print(f"{'ok  ' if gut else 'FAIL'} A2 vergleich_pflicht         "
          f"{ks.get('vergleich_pflicht', 'FEHLT')!r}")
    ok += gut

    # B1: kein Verdict behauptet eine Klassifikation, die nicht stattfand.
    gesamt += 1
    out = _strom([_z(None), _z(None)])
    # Nur ZEILE-Records zaehlen: `bei_ungleich=WIEDERHOLT` im DEDUP-Record
    # ist die Vorschrift fuer den BELEGTEN Fall und bleibt richtig.
    zeile = [z for z in out.splitlines() if z.startswith("ZEILE ")]
    gut = (any("UNGEPRUEFT;pos=2;art=ZEITSTEMPEL-UNLESBAR" in z
               for z in zeile)
           and not any("WIEDERHOLT" in z for z in zeile))
    print(f"{'ok  ' if gut else 'FAIL'} B1 unlesbar -> UNGEPRUEFT      "
          f"WIEDERHOLT={'WIEDERHOLT' in out}")
    ok += gut

    # B2: die Messachse zaehlt Unwissen in keinen bekannten Eimer.
    gesamt += 1
    achse = out.splitlines()[0]
    felder = dict(p.split("=", 1) for p in achse.split(";") if "=" in p)
    gut = (felder.get("WIEDERHOLUNG") == "0"
           and felder.get("KANAL-DUPLIKAT") == "0"
           and felder.get("ZEITSTEMPEL-UNLESBAR") == "1")
    print(f"{'ok  ' if gut else 'FAIL'} B2 Achse drei disjunkte Eimer "
          f"{felder.get('KANAL-DUPLIKAT')}/"
          f"{felder.get('WIEDERHOLUNG')}/"
          f"{felder.get('ZEITSTEMPEL-UNLESBAR')}")
    ok += gut

    # B3: der Regel-Token trennt Verdict und Aktion.
    gesamt += 1
    regeln = K.regel_aus_bericht(out.splitlines())
    r = next(iter(regeln.values()))
    gut = r.get("bei_unlesbar") == "UNGEPRUEFT"
    print(f"{'ok  ' if gut else 'FAIL'} B3 bei_unlesbar              "
          f"{r.get('bei_unlesbar')!r}")
    ok += gut

    # B4: UNGEPRUEFT vs. WIEDERHOLT sind disjunkt — kein gemeinsamer Token.
    gesamt += 1
    gut = (r.get("bei_ungleich") != r.get("bei_unlesbar")
           and r.get("bei_gleich") != r.get("bei_unlesbar"))
    print(f"{'ok  ' if gut else 'FAIL'} B4 drei Verdicts verschieden  "
          f"{r.get('bei_gleich')}/{r.get('bei_ungleich')}/"
          f"{r.get('bei_unlesbar')}")
    ok += gut

    # C: die Kopplung. Ein boolescher Konsument gegen den echten Strom.
    gesamt += 1
    strom_ts = [None, None]

    def bool_konsument() -> list[str]:
        out2 = []
        for i in range(len(strom_ts)):
            if i == 0:
                out2.append("ZUSTELLEN")
                continue
            a, b = strom_ts[i - 1], strom_ts[i]
            # Der naheliegende, FALSCHE Weg: boolesch.
            if a == b:
                out2.append(r["bei_gleich"])
            else:
                out2.append(r["bei_ungleich"])   # <- unlesbar landet hier
        return out2

    falsch = bool_konsument()
    richtig = [x.aktion for x in K.apply(r, strom_ts)]
    gut = falsch != richtig and richtig[1] == "UNGEPRUEFT"
    print(f"{'ok  ' if gut else 'FAIL'} C  bool-Konsument divergiert   "
          f"bool={falsch[1]} total={richtig[1]}")
    ok += gut

    # C2: K2 (Nachbau aus dem Vertrag) macht den Fehler NICHT.
    gesamt += 1
    k2 = []
    for i in range(len(strom_ts)):
        if i == 0:
            k2.append("ZUSTELLEN")
            continue
        a, b = strom_ts[i - 1], strom_ts[i]
        if a is None or b is None:
            k2.append(r["bei_unlesbar"])
        elif a == b:
            k2.append(r["bei_gleich"])
        else:
            k2.append(r["bei_ungleich"])
    gut = k2 == richtig
    print(f"{'ok  ' if gut else 'FAIL'} C2 Vertragstext-Konsument     "
          f"{k2[1]} == {richtig[1]}")
    ok += gut

    print(f"\n{ok}/{gesamt} Unwissen-ist-kein-Etikett-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
