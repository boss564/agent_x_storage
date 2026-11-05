"""D5-Last-Restore: prueft das UNTER LAST erzeugte Artefakt an fremdem Ort.

Drei Aussagen, unabhaengig voneinander:
  1. integrity_check == ok  (Struktur)
  2. Zeilenzaehler des Artefakts gegen die Selbstauskunft im Meta-Sidecar
  3. fachlicher Wasserstand (last_written_seq) gegen den Writer-Strom:
     liegt er STRIKT im Fenster (bereit, while), ist das Artefakt ein
     Schnitt MITTEN im Schreibstrom — nicht ein Zustand davor oder danach.

Die Pruefung liest NUR das restaurierte Artefakt (mode=ro&immutable=1) und
braucht kein -shm. Das ist die Bedingung dafuer, dass ein fremder Ort ohne
Schreibrecht ueberhaupt bewerten kann.

Aufruf: python d5_last_restore.py <artefakt> <writer_log.jsonl> [<meta.json>]
Ausgabe: ein JSON-Objekt. Exit 0 = alle Aussagen erfuellt, 1 = Befund,
2 = Beleg unbrauchbar (fehlt/leer) — Infrastruktur.
"""
import json
import os
import sqlite3
import sys


def lade_log(pfad: str) -> dict:
    phasen = {}
    if not os.path.isfile(pfad):
        return phasen
    with open(pfad) as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile:
                continue
            d = json.loads(zeile)
            phasen[d["phase"]] = d
    return phasen


def main() -> int:
    if len(sys.argv) < 3:
        print(json.dumps({"fehler": "Aufruf: artefakt writer_log [meta]"}))
        return 2
    art, logpfad = sys.argv[1], sys.argv[2]
    metapfad = sys.argv[3] if len(sys.argv) > 3 else None
    if not os.path.isfile(art):
        print(json.dumps({"fehler": "Artefakt fehlt", "pfad": art}))
        return 2

    phasen = lade_log(logpfad)
    b = phasen.get("bereit", {}).get("seq")
    w = phasen.get("while", {}).get("seq")
    d = phasen.get("done", {}).get("seq")
    reihenfolge = None not in (b, w, d) and b < w < d

    c = sqlite3.connect(f"file:{art}?mode=ro&immutable=1", uri=True)
    ic = c.execute("pragma integrity_check").fetchone()[0]
    counts = {
        t: c.execute(f"select count(*) from '{t}'").fetchone()[0]
        for t in ("drafts", "run_metrics", "cycles", "generation_state")
    }
    seq = c.execute("select last_written_seq from generation_state where id=1").fetchone()[0]
    pages = c.execute("pragma page_count").fetchone()[0]
    jm = c.execute("pragma journal_mode").fetchone()[0]
    c.close()

    meta = None
    if metapfad and os.path.isfile(metapfad):
        with open(metapfad) as f:
            meta = json.load(f)

    meta_pari = meta is not None and meta.get("counts") == counts and meta.get("source_seq") == seq
    im_fenster = reihenfolge and b < seq < w if reihenfolge else False

    print(json.dumps({
        "integrity": ic,
        "journal_mode_der_kopie": jm,
        "counts": counts,
        "last_written_seq": seq,
        "pages": pages,
        "writer_seq": {"bereit": b, "while": w, "done": d},
        "schreibstrom_reihenfolge_ok": reihenfolge,
        "meta_pari": meta_pari,
        "artefakt_liegt_strikt_im_fenster": im_fenster,
        "artefakt_veraltet_gegen_while": bool(w is not None and seq < w),
    }))
    ok = ic == "ok" and im_fenster and meta_pari
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
