"""D5-Schreiber — persistente, separat gepruefte Testdatei (NICHT Inline-Python).

Aufgabe: belegen, dass waehrend der Sicherung tatsaechlich committet wird.

Geschrieben wird gegen das ECHTE Produktionsverzeichnis (in diesem Container
``/data``), aber NUR in eine eigens angelegte Drill-Datenbank
``d5_schreiblast.db``. Das ist der Grund, warum diese Last zulaessig ist:
- ``drafts.db`` selbst bleibt unberuehrt (keine Persistenzaenderung am
  Backup-Objekt, kein Eingriff in den Bestand);
- die Last entsteht im selben Verzeichnis, auf demselben Dateisystem, unter
  denselben WAL-Regeln und demselben Rechte-/Mount-Kontext wie die echte
  Quelle — der Rechte-/Layout-Kontext (UID 10001, 0750) ist genau die
  Bedingung, an der der erste Versuch gescheitert ist;
- der Schreiber-Prozess laeuft dauerhaft und waehrend der Sicherung.

Protokoll: /data/d5_schreiblast.log.jsonl, eine Zeile je Phase.
    {"phase": "bereit"|"while"|"done", "commits": n, "seq": s, "rows": r, "t": ts}

Beendigung: nach WRITER_DAUER Sekunden, Exit 0. Jede unbehandelte Ausnahme
verlaesst das Skript mit Exit 1 — der Driller wertet das als Infrastruktur-
fehler (Kernbedingung nicht hergestellt), nicht als "Schreiblast belegt".
"""
import json
import os
import sqlite3
import sys
import time

DIR = os.environ.get("DRILL_DIR", "/data")
P = os.path.join(DIR, "d5_schreiblast.db")
LOG = os.path.join(DIR, "d5_schreiblast.log.jsonl")
LIVE = os.path.join(DIR, "d5_schreiblast.live.jsonl")
DAUER_S = int(os.environ.get("WRITER_DAUER", "25"))


def lege_db_an() -> None:
    for sfx in ("", "-wal", "-shm"):
        try:
            os.remove(P + sfx)
        except FileNotFoundError:
            pass
    c = sqlite3.connect(P)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA wal_autocheckpoint=0")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("CREATE TABLE drafts (id INTEGER PRIMARY KEY, url TEXT, body TEXT)")
    c.execute("CREATE TABLE cycles (id INTEGER PRIMARY KEY, note TEXT)")
    c.execute("CREATE TABLE run_metrics (id INTEGER PRIMARY KEY, ms INTEGER)")
    c.execute(
        "CREATE TABLE generation_state (id INTEGER PRIMARY KEY, "
        "last_written_seq INTEGER, next_seq INTEGER)"
    )
    c.execute("INSERT INTO generation_state VALUES (1, 0, 1)")
    c.executemany(
        "INSERT INTO drafts (url, body) VALUES (?, ?)",
        [(f"https://example.org/{i}", "x" * 300) for i in range(300)],
    )
    c.commit()
    c.close()


def oeffne() -> sqlite3.Connection:
    c = sqlite3.connect(P, isolation_level=None, timeout=20)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA wal_autocheckpoint=0")
    return c


def messung(c: sqlite3.Connection) -> dict:
    seq = c.execute("select last_written_seq from generation_state where id=1").fetchone()[0]
    rows = c.execute("select count(*) from drafts").fetchone()[0]
    return {"seq": int(seq), "rows": int(rows)}


def hoch(c: sqlite3.Connection) -> None:
    """Ein Commit, der den fachlichen Wasserstand FORTSCHREIBT."""
    seq = c.execute("select last_written_seq from generation_state where id=1").fetchone()[0]
    c.execute("BEGIN IMMEDIATE")
    c.execute(
        "update generation_state set last_written_seq=?, next_seq=? where id=1",
        (seq + 1, seq + 2),
    )
    c.execute("insert into drafts(url, body) values (?, ?)", (f"live/{seq + 1}", "b" * 400))
    c.execute("insert into run_metrics(ms) values (?)", (int(time.time() * 1000) % 100000,))
    c.commit()


def log(phase: str, **kw) -> None:
    with open(LOG, "a") as f:
        f.write(json.dumps({"phase": phase, "t": time.time(), **kw}) + "\n")


def main() -> int:
    try:
        lege_db_an()
        c = oeffne()
        commits = 0
        for _ in range(5):                      # 5 Pflicht-Commits VOR der Sicherung
            hoch(c)
            commits += 1
        log("bereit", commits=commits, **messung(c))

        ende = time.time() + DAUER_S
        zyklus = 0
        while time.time() < ende:               # Schreiblast WAEHREND der Sicherung
            for _ in range(5):
                hoch(c)
                commits += 1
            zyklus += 1
            with open(LIVE, "a") as f:
                f.write(json.dumps({"commits": commits, "t": time.time(), **messung(c)}) + "\n")
            time.sleep(0.2)
        log("while", commits=commits, **messung(c))

        for _ in range(5):                      # Nachlauf NACH der Sicherung
            hoch(c)
            commits += 1
        log("done", commits=commits, **messung(c))
        c.close()
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"WRITER-FEHLER: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
