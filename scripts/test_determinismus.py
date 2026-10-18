#!/usr/bin/env python3
"""Baseline-Determinismus: N=4 Seeds ist eine Stichprobe, kein Beweis.

§A-ZZZZ199 (Runde 90 Befund 8): "6/6 unter 4 Seeds" ist eine Messung auf
vier ZIEZOGENEN Umgebungen. Ein Mutant, der unter Seed #5 entkommt,
bleibt unsichtbar. Die Seed-Varianz ist die richtige Achse — aber sie
beweist keine Determinismus-Eigenschaft.

Dieser Test trennt die zwei Aussagen, die R89 vermischt hat:

  1. BASELINE-DETERMINISMUS: zweimal, gleicher Seed, gleicher Strom
     -> byte-gleiche Ausgabe. Das ist beweisbar und wird hier bewiesen.
  2. SEED-UNABHAENGIGKEIT: verschiedene Seeds -> gleiche URTEILE.
     Das bleibt eine Stichprobe (N=4); bewiesen wird nur, dass
     PYTHONHASHSEED den Vertrag nicht beruehrt (crc32 statt hash()).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
W = SCRIPTS / "einwurf_waechter.py"
V = SCRIPTS / "waechter_vertrag.json"
A, B = "A" * 500, "B" * 500


def strom(pfad: Path) -> None:
    z = [
        {"role": "user", "message": {"content": f"<timestamp>T1</timestamp>\n{A}"}},
        {"role": "user", "message": {"content": f"<timestamp>T1</timestamp>\n{A}"}},
        {"role": "user", "message": {"content": f"<timestamp>T2</timestamp>\n{A}"}},
        {"role": "user", "message": {"content": f"<timestamp>T2</timestamp>\n{B}"}},
        {"role": "user", "message": {"content": A}},
    ]
    pfad.write_text("\n".join(json.dumps(x) for x in z) + "\n", encoding="utf-8")


def lauf(pfad: Path, seed: str) -> tuple[int, str]:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    r = subprocess.run([sys.executable, str(W), "--strom", str(pfad)],
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as td:
        p = (Path(td) / "s.jsonl").resolve()
        strom(p)

        # 1. Byte-Gleichheit bei identischem Seed — zweimal.
        gesamt += 1
        c1, o1 = lauf(p, "0")
        c2, o2 = lauf(p, "0")
        gut = (c1, o1) == (c2, o2)
        print(f"{'ok  ' if gut else 'FAIL'} Zweimal Seed 0 byte-gleich  "
              f"exit {c1}=={c2}, out {'==' if gut else '!='}")
        ok += gut

        # 2. Seed-Unabhaengigkeit der URTEILE (Stichprobe, ehrlich benannt).
        gesamt += 1
        base = lauf(p, "0")[1]
        abw = []
        for s in ("1", "7", "12345"):
            c, o = lauf(p, s)
            if o != base:
                abw.append(s)
        gut = not abw
        print(f"{'ok  ' if gut else 'FAIL'} Urteile seed-unabhaengig    "
              f"abweichend={abw}")
        ok += gut

        # 3. Die ZEILEN sind in allen Seeds identisch (nicht nur der Exit).
        #    5 ZEILE-Records: ZUSTELLEN(A), VERWERFEN(A), WIEDERHOLT(A),
        #    ZUSTELLEN(B), UNGEPRUEFT(unlesbare Kopie). Die `  # `-Kommentare
        #    zaehlen nicht (Praefix ist zwei Leerzeichen, nicht "ZEILE ").
        gesamt += 1
        z0 = [z for z in base.splitlines() if z.startswith("ZEILE ")]
        gut = len(z0) == 5
        print(f"{'ok  ' if gut else 'FAIL'} Urteils-Zeilen stabil       "
              f"{len(z0)} ZEILE-Records (erwartet 5)")
        ok += gut

        # 3b. §A-ZZZZ200: die Ontologie-Trennung ist im echten Record sichtbar.
        gesamt += 1
        u = [z for z in z0 if "UNGEPRUEFT" in z]
        gut = bool(u) and "art=UNBEURTEILBAR" in u[0] and \
            "grund=ZEITSTEMPEL-UNLESBAR" in u[0] and \
            "art=ZEITSTEMPEL" not in u[0]
        print(f"{'ok  ' if gut else 'FAIL'} art=Ontologie, grund=Ursache "
              f"{'korrekt' if gut else 'vermischt'}")
        ok += gut

    # 4. Die Begruendung steht im Vertrag — N=4 als Stichprobe benannt.
    gesamt += 1
    b = d["mutation_protokoll"].get("seed_begruendung", "")
    gut = "Stichprobe" in b and "kein Beweis" in b
    print(f"{'ok  ' if gut else 'FAIL'} N=4 als Stichprobe benannt  "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 5. Der vollstaendige Hash steht im Record, nicht die Kurzform.
    gesamt += 1
    z0 = [z for z in base.splitlines() if z.startswith("ZEILE ")][0]
    import re
    m = re.match(r"ZEILE ([0-9a-f]+) ", z0)
    gut = bool(m) and len(m.group(1)) == 64
    print(f"{'ok  ' if gut else 'FAIL'} Hash-Laenge im Record       "
          f"{len(m.group(1)) if m else 0} hex")
    ok += gut

    # 6. Paar-Zaehlung n>2 ist normiert (n-1, nicht C(n,2)).
    gesamt += 1
    pz = d["aggregation"].get("paar_zaehlung", {})
    gut = "n - 1" in pz.get("definition", "") and "C(n,2)" in pz.get("nicht", "")
    print(f"{'ok  ' if gut else 'FAIL'} Paar-Zaehlung n>2          "
          f"{'n-1 normiert' if gut else 'ungenannt'}")
    ok += gut

    # 7. Vier-Eimer-Invariante ist ein Normsatz.
    gesamt += 1
    ve = d["aggregation"].get("vier_eimer_invariante", "")
    gut = "Paare = KANAL-DUPLIKAT + WIEDERHOLUNG + ZEITSTEMPEL-UNLESBAR" in ve
    print(f"{'ok  ' if gut else 'FAIL'} Vier-Eimer-Invariante       "
          f"{'deklariert' if gut else 'fehlt'}")
    ok += gut

    # 8. Vokabular-Abbildung deckt alle sieben Ebenen.
    gesamt += 1
    va = d.get("vokabular_abbildung", {})
    gut = len([k for k in va if k not in ("norm", "zustand")]) >= 6
    print(f"{'ok  ' if gut else 'FAIL'} Vokabular-Abbildung        "
          f"{len(va)} Eintraege")
    ok += gut

    print(f"\n{ok}/{gesamt} Determinismus-und-Zahlen-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
