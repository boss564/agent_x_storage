#!/usr/bin/env python3
"""Exit-Code vor Stdout — ein leerer Strom ist nicht „keine Ereignisse".

§A-ZZZZ182 (Runde 89): **die eigene Falle als Normsatz.**

R88 baute in `test_konsument_kongruenz._lauf` eine Falle und fixte sie auf
Harness-Ebene (absoluter Pfad, `raise` bei Exit 3). Die Vertragsebene
fehlte. Der Anlass ist praezise: ein relativer Pfad bei `cwd=td` machte
Exit 3, stdout war leer, und der Test las **„keine Ereignisse"** statt
**„Strom unlesbar"**.

Ein leerer stdout ist ambig zwischen zwei Zustaenden:
    (a) der Lauf war erfolgreich, es gab nichts zu berichten
    (b) der Lauf ist gescheitert, es gibt keinen Bericht

Nur der Exit-Code loest die Ambiguitaet. Ein Konsument, der stdout zuerst
liest, interpretiert (b) als (a) — und das ist die Ur-Maske in
Konsumentenform: die Meldung ist verschwunden, der Lauf sieht sauber aus.

Die Ueberschrift "K1/K2 haben den Fehler beide nicht gemacht" gilt: sie
sind Test-Doubles, keine Konsumenten. DIESER Test baut den falschen
Konsumenten ABSICHTLICH und zeigt, dass er divergiert.
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


def konsument_falsch(stdout: str, exit_code: int) -> list[str]:
    """Der naheliegende Fehler: stdout zuerst, Exit nur zur Info."""
    return [z for z in stdout.splitlines() if z.startswith("ZEILE ")]


def konsument_richtig(stdout: str, exit_code: int) -> list[str] | str:
    """Norm: Exit zuerst. Bei Exit != 0 ist stdout undefiniert."""
    if exit_code == 3:
        return "STROM-UNLESBAR"
    if exit_code == 2:
        return "AUFRUF-VERWORFEN"
    return [z for z in stdout.splitlines() if z.startswith("ZEILE ")]


def _lauf(strom: Path | None) -> tuple[int, str]:
    if strom is None:
        r = subprocess.run([sys.executable, str(W)], capture_output=True,
                           text=True)
    else:
        r = subprocess.run([sys.executable, str(W), "--strom", str(strom)],
                           capture_output=True, text=True)
    return r.returncode, r.stdout


def main() -> int:
    ok = gesamt = 0

    # Der unlesbare Pfad: Exit 3, KEINE ZEILE-Records.
    # §A-ZZZZ183: die Achse steht auch hier (R82: ein Feld darf nicht
    # existieren, weil der Exit zufaellig 0 ist). Der stdout ist also NICHT
    # leer — aber er traegt keine Ereignisse. Genau deshalb ist "stdout ist
    # undefiniert" die richtige Norm: er sieht gefuellt aus und ist es nicht.
    code, out = _lauf(Path("/tmp/gibt-es-nicht-r89.jsonl"))
    gesamt += 1
    hat_ereignis = any(z.startswith("ZEILE ") for z in out.splitlines())
    gut = code == 3 and not hat_ereignis and out.strip() != ""
    print(f"{'ok  ' if gut else 'FAIL'} Exit 3, Achse ja / Ereignis nein "
          f"exit={code} ereignis={hat_ereignis}")
    ok += gut

    # Der falsche Konsument liest daraus "keine Ereignisse".
    falsch = konsument_falsch(out, code)
    richtig = konsument_richtig(out, code)
    gesamt += 1
    gut = falsch == [] and richtig == "STROM-UNLESBAR"
    print(f"{'ok  ' if gut else 'FAIL'} Divergenz gemessen            "
          f"falsch={falsch} richtig={richtig!r}")
    ok += gut

    # Und bei einem gesunden Lauf sind beide einig — der Normsatz kostet
    # nichts, wo er nicht greift.
    gesamt += 1
    with tempfile.TemporaryDirectory() as td:
        f = (Path(td) / "s.jsonl").resolve()
        f.write_text(json.dumps({"role": "user", "message": {
            "content": "<timestamp>T1</timestamp>\n" + "A" * 500}}) + "\n")
        code2, out2 = _lauf(f)
    gut = konsument_falsch(out2, code2) == konsument_richtig(out2, code2) != []
    print(f"{'ok  ' if gut else 'FAIL'} gesunder Lauf, beide einig    "
          f"exit={code2}")
    ok += gut

    # Die Norm steht im Vertrag, nicht nur im Test.
    gesamt += 1
    d = json.loads(V.read_text(encoding="utf-8"))
    norm = d["konsumenten_semantik"].get("exit_vor_stdout", "")
    gut = "Exit" in norm and "undefiniert" in norm
    print(f"{'ok  ' if gut else 'FAIL'} Norm im Vertrag              "
          f"{norm[:40]!r}")
    ok += gut

    print(f"\n{ok}/{gesamt} Exit-vor-Stdout-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
