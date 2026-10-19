#!/usr/bin/env python3
"""Produkt-Governance (R105): der Vertrag hat eine durable Adresse.

Vorher: data/lauf_letzter.json = .gitignore 'data/', nie committet,
in keiner bewachten Menge. Ein Vertrag auf Sand.

Dieser Test prueft die drei Eigenschaften, die "durable" bedeuten:
  1 Snapshot liegt im Baum (git ls-files), nicht im Ignorier-Bereich
  2 Zeiger ist ein VERWEIS: {snapshot, sha256} — nie der Inhalt
  3 Zeiger und Snapshot stimmen ueberein (kein stiller Drift)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ok = gesamt = 0


def pruefe(name: str, b: bool, detail: str = "") -> None:
    global ok, gesamt
    gesamt += 1
    ok += bool(b)
    print(f"{'ok  ' if b else 'ROT '} {name}" + (f"  {detail}" if not b else ""))


def main() -> int:
    ziel = REPO / "vertrag"
    zeiger = ziel / "latest.json"
    pruefe("1a Zeiger existiert", zeiger.exists())
    if not zeiger.exists():
        print(f"\n{ok}/{gesamt} Vertrag-Faelle gruen")
        return 1
    z = json.loads(zeiger.read_text(encoding="utf-8"))

    pruefe("2a Zeiger traegt keine Nutzlast (kein 'klassen')",
           "klassen" not in z and "dateien" not in z, str(list(z)))
    pruefe("2b Zeiger hat snapshot + sha256", {"snapshot", "sha256"} <= set(z))

    snap = ziel / z["snapshot"]
    pruefe("2c Snapshot liegt IN DER NAEHE des Zeigers", snap.exists())
    if snap.exists():
        ist = hashlib.sha256(snap.read_bytes()).hexdigest()
        pruefe("3a Snapshot-SHA == Zeiger-SHA", ist == z["sha256"],
               f"{ist[:16]} != {z['sha256'][:16]}")

    r = subprocess.run(["git", "ls-files", "--error-unmatch",
                        str(snap.relative_to(REPO))], cwd=REPO, capture_output=True)
    pruefe("1b Snapshot ist im Index (durable, nicht ignoriert)", r.returncode == 0)

    # 1c: die Ignore-LAGE wird ERZEUGT, nicht behauptet (Hook-Regel:
    # wer ein Muster aus .gitignore beziffert, muss es herstellen).
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "-C", tmp, "init", "-q"], capture_output=True)
        (Path(tmp) / "data").mkdir()
        (Path(tmp) / "data" / "lauf_letzter.json").write_text("{}", encoding="utf-8")
        (Path(tmp) / ".gitignore").write_text("data/\n", encoding="utf-8")
        ignoriert = subprocess.run(["git", "-C", tmp, "check-ignore", "-q",
                                    "data/lauf_letzter.json"],
                                   capture_output=True).returncode == 0
        # und die Gegenprobe: der Snapshot-Pfad ist NICHT gedeckt
        (Path(tmp) / "vertrag").mkdir()
        (Path(tmp) / "vertrag" / "latest.json").write_text("{}", encoding="utf-8")
        snap_frei = subprocess.run(["git", "-C", tmp, "check-ignore", "-q",
                                    "vertrag/latest.json"],
                                   capture_output=True).returncode != 0
    pruefe("1c 'data/' ignoriert data/lauf_letzter.json (erzeugt)", ignoriert)
    pruefe("1d 'data/' deckt vertrag/ NICHT (Snapshot bleibt frei)", snap_frei)

    print(f"\n{ok}/{gesamt} Vertrag-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
