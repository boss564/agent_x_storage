#!/usr/bin/env python3
"""#12 — Die Wand testet den Turm. Wer testet die Wand? Diese Suite.

R100: Prueft die VERBRAUCHS-SEMANTIK von governance_gate._ausnahme()
regressiv, in einem isolierten Temp-Baum, ohne den echten Repo-Zustand
oder das echte ENTSCHEIDUNGEN-Register anzufassen.

Sieben Faelle: AKTIV, VOLLZOGEN, ANOMALIE (fremde Aenderung), ANOMALIE
ohne Ziel-Hash, Basis noch nicht im Baum, leere Dateiliste, fremde Datei.

Der Regressionstest zu #11/Befund B: eine FREMDE Aenderung darf die
Ausnahme NICHT verbrauchen. Vor R100 tat sie es.
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

ok = gesamt = 0


def pruefe(name: str, bedingung: bool, detail: str = "") -> None:
    global ok, gesamt
    gesamt += 1
    if bedingung:
        ok += 1
        print(f"ok   {name}")
    else:
        print(f"ROT  {name}  {detail}")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    import governance_gate as G

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "scripts").mkdir()
        f = root / "scripts" / "probe.py"
        datei = "scripts/probe.py"
        BASE, ZIEL = sha("baseline"), sha("ziel")

        # Der echte Baum hat die Datei bereits (ls-tree liefert sie)
        real_git = G._git
        G._git = lambda *a, **k: datei  # "Datei ist im Baum"
        G.SCRIPTS = root / "scripts"

        def entscheidung(**fix) -> dict:
            return {"id": "RX", "dateien_geschlossen": [datei], "fix": fix}

        try:
            # 1 AKTIV — Hash == Baseline
            f.write_text("baseline")
            ok_, grund = G._ausnahme(entscheidung(baseline_sha256=BASE,
                                                  ziel_sha256=ZIEL), [datei])
            pruefe("AKTIV: sha==baseline -> gestattet", ok_, grund)

            # 2 VOLLZOGEN — Hash == Ziel
            f.write_text("ziel")
            ok_, grund = G._ausnahme(entscheidung(baseline_sha256=BASE,
                                                  ziel_sha256=ZIEL), [datei])
            pruefe("VOLLZOGEN: sha==ziel -> verbraucht", not ok_ and "verbraucht" in grund,
                   grund)

            # 3 ANOMALIE — fremde Aenderung, nicht verbrauchen (#11/Befund B)
            f.write_text("fremd")
            ok_, grund = G._ausnahme(entscheidung(baseline_sha256=BASE,
                                                  ziel_sha256=ZIEL), [datei])
            pruefe("ANOMALIE: fremder Hash -> NICHT 'verbraucht'",
                   not ok_ and "ANOMALIE" in grund and "verbraucht" not in grund,
                   grund)

            # 4 ANOMALIE ohne Ziel-Hash — kein stilles 'verbraucht'
            ok_, grund = G._ausnahme(entscheidung(baseline_sha256=BASE), [datei])
            pruefe("ANOMALIE ohne Ziel-Hash -> Flagge, nicht 'verbraucht'",
                   not ok_ and "ANOMALIE" in grund and "Ziel-Hash fehlt" in grund,
                   grund)

            # 5 Basis noch nicht im Baum
            G._git = lambda *a, **k: ""
            f.write_text("egal")
            ok_, grund = G._ausnahme(entscheidung(baseline_sha256=BASE), [datei])
            pruefe("Basis nicht im Baum -> gestattet, deklariert",
                   ok_ and "noch nicht im Baum" in grund, grund)
            G._git = lambda *a, **k: datei

            # 6 leere Dateiliste
            ok_, grund = G._ausnahme({"id": "RX", "dateien_geschlossen": []}, [datei])
            pruefe("leere Dateiliste -> ungueltig", not ok_ and "ung" in grund, grund)

            # 7 fremde gestagte Datei
            f.write_text("baseline")
            ok_, grund = G._ausnahme(entscheidung(baseline_sha256=BASE,
                                                  ziel_sha256=ZIEL),
                                     [datei, "scripts/fremd.py"])
            pruefe("fremde Datei -> abgelehnt", not ok_ and "fremde" in grund, grund)
        finally:
            G._git = real_git

    # R102: Der Live-Befund. Ein Datensatz mit N Dateien braucht N Paare
    # (baseline, ziel). R101 lieferte EIN Paar fuer vier Dateien — drei
    # waren dadurch per Konstruktion ANOMALIE, und der Dreizustand hat
    # seinen ersten echten Einsatz nicht bestanden.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "scripts").mkdir()
        a, b = root / "scripts" / "a.py", root / "scripts" / "b.py"
        G.SCRIPTS = root / "scripts"
        G._git = lambda *x, **k: "scripts/a.py"
        a.write_text("ziel")     # == ziel_sha256
        b.write_text("anders")   # weder baseline noch ziel
        # EIN globales Paar, zwei Dateien -> b ist ANOMALIE
        d_ein_paar = {"id": "RX", "dateien_geschlossen": ["scripts/a.py", "scripts/b.py"],
                      "fix": {"baseline_sha256": sha("base"),
                              "ziel_sha256": sha("ziel")}}
        ok_, grund = G._ausnahme(d_ein_paar, ["scripts/a.py", "scripts/b.py"])
        pruefe("R102 ein globales Hash-Paar -> Datei ohne eigenes Paar ist ANOMALIE",
               not ok_ and "ANOMALIE" in grund, grund)

    print(f"\n{ok}/{gesamt} Verbrauchs-Semantik-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
