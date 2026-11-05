"""D5-Restaufraeumer — benannter Aufraeumgrund, kein stilles Loeschen.

Zweck: Reste aus Drill-Abbruechen (`.part`, `.meta.part`) wieder entfernen,
ohne die Messung zu faelschen. Ein Kill im Publikationsfenster hinterlaesst
diese Dateien absichtlich — der Befund ist "Fenster mit Artefakt ohne
Quittung", nicht "Staging-Verzeichnis ist dreckig".

Regeln:
  - es werden NUR `*.part` entfernt,
  - jede Datei wird vorher geSHA't und ins Protokoll geschrieben,
  - Endungen `.sqlite` / `.meta` / `.seqproof` werden NIE angefasst.

Exit-Codes (benannt):
  0  aufgeraeumt
  1  Verzeichnis nicht lesbar
  3  Rest nach dem Aufraeumen noch vorhanden
"""
import hashlib
import json
import os
import sys

SND = os.environ.get("SND", "/tmp/d5_sound")


def sha(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def main() -> int:
    try:
        namen = sorted(os.listdir(SND))
    except OSError as e:  # noqa: BLE001
        print(json.dumps({"fehler": f"{type(e).__name__}: {e}"}))
        return 1

    reste = [n for n in namen if n.endswith(".part")]
    protokoll = []
    for n in reste:
        p = os.path.join(SND, n)
        try:
            rec = {"datei": n, "bytes": os.path.getsize(p), "sha16": sha(p)}
            os.remove(p)
            rec["entfernt"] = True
        except OSError as e:  # noqa: BLE001
            rec = {"datei": n, "entfernt": False, "fehler": str(e)}
        protokoll.append(rec)

    rest_nachher = sorted(n for n in os.listdir(SND) if n.endswith(".part"))
    print(json.dumps({
        "verzeichnis": SND,
        "reste_vorher": len(reste),
        "reste_nachher": len(rest_nachher),
        "protokoll": protokoll,
        "unberuehrt": sorted(n for n in os.listdir(SND) if not n.endswith(".part")),
    }))
    return 0 if not rest_nachher else 3


if __name__ == "__main__":
    sys.exit(main())
