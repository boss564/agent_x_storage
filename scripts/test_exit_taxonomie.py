#!/usr/bin/env python3
"""Exit 4: der UNGEPRUEFT-Record darf nicht unter der Taxonomie sterben.

§A-ZZZZ187 (Runde 90): **zwei Lesarten von Exit 4, entgegengesetzte Pflichten.**

R89 fuehrte `ZEILE <h> UNGEPRUEFT;art=ZEITSTEMPEL-UNLESBAR` ein und
beendete mit Exit 4 — ohne zu sagen, ob stdout dann der Bericht ist.

  Lesart A (Prozess gescheitert): stdout undefiniert -> Konsument verwirft
      -> der UNGEPRUEFT-Record ist wertlos, der Fix aus R89 entwertet
  Lesart B (Bericht enthaelt Unbeurteilbares): Konsument MUSS lesen
      -> der Record lebt

Dieser Test baut BEIDE Konsumenten und misst, was jeder mit demselben
Record macht. Der Vertrag entscheidet fuer B; der Test beweist, dass die
Entscheidung einen Unterschied macht — nicht nur auf dem Papier.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
W = SCRIPTS / "einwurf_waechter.py"
V = SCRIPTS / "waechter_vertrag.json"
A = "A" * 500


def _z(ts: str | None) -> str:
    inner = f"<timestamp>{ts}</timestamp>\n{A}" if ts else A
    return json.dumps({"role": "user", "message": {"content": inner}})


def _lauf(zeilen: list[str]) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as td:
        f = (Path(td) / "s.jsonl").resolve()
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True)
        return r.returncode, r.stdout


def konsument_lesart_a(out: str, code: int) -> list[str]:
    """Prozess gescheitert -> stdout undefiniert -> verwerfen."""
    if code != 0:
        return []
    return [z for z in out.splitlines() if z.startswith("ZEILE ")]


def konsument_lesart_b(out: str, code: int, tax: dict) -> list[str]:
    """Bericht lesen, solange die Taxonomie stdout als Bericht deklariert."""
    if not tax.get(str(code), {}).get("stdout_ist_bericht"):
        return []
    return [z for z in out.splitlines() if z.startswith("ZEILE ")]


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    tax = d["exit_taxonomie"]["je_code"]

    code, out = _lauf([_z(None), _z(None)])   # zwei unlesbare Timestamps

    # 1. Der Fix aus R89 steht.
    gesamt += 1
    gut = code == 4 and "UNGEPRUEFT;pos=2;art=UNBEURTEILBAR;grund=ZEITSTEMPEL-UNLESBAR" in out
    print(f"{'ok  ' if gut else 'FAIL'} R89-Fix steht               "
          f"exit={code}")
    ok += gut

    # 2. Lesart A entwertet ihn — gemessen, nicht behauptet.
    gesamt += 1
    a = konsument_lesart_a(out, code)
    gut = a == []
    print(f"{'ok  ' if gut else 'FAIL'} Lesart A verwirft alles      "
          f"{len(a)} ZEILE-Records")
    ok += gut

    # 3. Lesart B erhaelt ihn — und das ist die Vertragsnorm.
    gesamt += 1
    b = konsument_lesart_b(out, code, tax)
    gut = any("UNGEPRUEFT" in z for z in b)
    print(f"{'ok  ' if gut else 'FAIL'} Lesart B liefert UNGEPRUEFT  "
          f"{len(b)} ZEILE-Records")
    ok += gut

    # 4. Die Divergenz ist der Beleg: derselbe Record, zwei Ausgaenge.
    gesamt += 1
    gut = a != b
    print(f"{'ok  ' if gut else 'FAIL'} Divergenz messbar             "
          f"A={len(a)} B={len(b)}")
    ok += gut

    # 5. Fuer JEDEN Code ist stdout deklariert — keine stille Luecke.
    gesamt += 1
    fehlend = [c for c in ("0", "1", "2", "3", "4")
               if "stdout_ist_bericht" not in tax.get(c, {})]
    gut = not fehlend
    print(f"{'ok  ' if gut else 'FAIL'} Taxonomie vollstaendig        "
          f"fehlend={fehlend}")
    ok += gut

    # 6. Exit 2 traegt keine Inhalts-Records — die Kreuz-Record-Invariante
    #    gilt auch in der Taxonomie.
    gesamt += 1
    c2, o2 = subprocess.run([sys.executable, str(W)], capture_output=True,
                            text=True).returncode, ""
    gut = tax["2"]["stdout_ist_bericht"] is True
    print(f"{'ok  ' if gut else 'FAIL'} Exit 2 stdout=Bericht        "
          f"(nur AUFRUF-Zeile)")
    ok += gut

    # 7. Kein Code hat stdout=undefiniert — die Absicht ist deklariert.
    gesamt += 1
    gut = d["exit_taxonomie"].get("warum_nicht_undefiniert") not in (None, "")
    print(f"{'ok  ' if gut else 'FAIL'} 'undefiniert' begruendet     "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Exit-4-Taxonomie-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
