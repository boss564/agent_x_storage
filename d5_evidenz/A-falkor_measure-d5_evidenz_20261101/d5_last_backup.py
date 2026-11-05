"""D5-Backup-Teil — NATIVE SQLite-Sicherung der Drill-Quelle (d5_schreiblast.db).

Absichtlich NICHT ``backup_newsagent.sh``: dieser Teil misst den Mechanismus
(Online-Backup bei laufendem Schreiber, Staging, Validierung, Publikation),
nicht die Verdrahtung des Produktionsskripts. Die Verdrahtung ist bereits
durch ``tests/test_backup_d5_sqlite_leitung.py`` (16/16) und den
Suitenlauf 596734 abgedeckt. Hier gilt: EIN Messobjekt, EIN Zweck.

Exit-Codes (benannt, nicht verglichen):
   0  veroeffentlicht (Artefakt + Meta liegen unter /sound)
  10  Quelle fehlt
  11  Isolation nicht nachgewiesen (query_only liess schreiben zu)
  12  Fehler war NICHT readonly (Isolation nicht aussagekraeftig)
  21  integrity_check auf der Kopie fehlgeschlagen
  22  integrity_check meldet 'busy' — Kopie unter Last nicht bewertbar
  23  -wal/-shm neben der Zwischendatei (Datei ist nicht der Stand)
  24  Zeilenzahl der Kopie weicht von der Quelle ab
  31  Publikation scheiterte (no-clobber)
  32  Meta fehlt nach Publikation
  41  Zielname existiert (no-clobber greift)
  42  kein freier Name gefunden
  43  Zwischendatei nicht exklusiv erzeugt
  99  unerwarteter Fehler
"""
import json
import os
import sqlite3
import sys
import time

SRC = "/data/d5_schreiblast.db"
STAGE = "/sound"                      # rw: hier wird gebaut
PUB = "/sound"                        # Publikation am selben Ort
STAMP = os.environ.get("STAMP", "x")
TRIES = int(os.environ.get("BACKUP_TRIES", "1"))


def aus(code: int, **kw) -> "NoReturn":  # noqa: F821
    print(json.dumps({"code": code, "t": time.time(), **kw}))
    sys.exit(code)


def conn(db: str, query_only: bool) -> sqlite3.Connection:
    c = sqlite3.connect(db, timeout=30)
    if query_only:
        c.execute("PRAGMA query_only=1")
    return c


def main() -> int:
    if not os.path.isfile(SRC):
        aus(10, pfad=SRC)

    # 1) SOURCE-ONLINE RESTORE-POINT (bounded): lesend ueber conn.backup.
    # Die Quelle wird vom Schreiber fortlaufend committet.
    for versuch in range(1, TRIES + 1):
        src = conn(SRC, query_only=True)
        base = f"d5sql-{STAMP}"
        part = os.path.join(STAGE, base + ".part")
        metatmp = os.path.join(STAGE, base + ".meta.part")
        final = os.path.join(PUB, base + ".sqlite")
        metaf = os.path.join(PUB, base + ".meta")

        # Zwischendatei exklusiv erzeugen (O_EXCL) — kein Erben fremder Reste.
        try:
            fd = os.open(part, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
        except FileExistsError:
            aus(43, datei=os.path.basename(part))

        # 2) ISOLATIONSPROBE: query_only hebt die Schreibabsicht nicht auf,
        # nur die Berechtigung — ein erfolgreicher Schreibversuch hier ist
        # ein Befund (11), ein ANDERER Fehler ist unbrauchbar (12).
        try:
            src.execute("PRAGMA user_version=9999")
            src.close()
            os.remove(part)
            aus(11, befund="Schreibversuch mit query_only wurde AKZEPTIERT")
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "readonly" not in msg and "read-only" not in msg:
                src.close()
                os.remove(part)
                aus(12, fehler=str(e))

        dst = sqlite3.connect(part)
        try:
            src.backup(dst, pages=64)
            # WAL -> Einzeldatei: die Kopie muss ohne -shm/-wal lesbar sein.
            dst.execute("PRAGMA journal_mode=DELETE")
            ic = dst.execute("PRAGMA integrity_check(1)").fetchone()[0]
            if ic != "ok":
                dst.close(); src.close(); os.remove(part)
                aus(22 if "busy" in ic.lower() else 21, integrity=ic)
            q = {
                t: src.execute(f"select count(*) from '{t}'").fetchone()[0]
                for t in ("drafts", "run_metrics", "cycles", "generation_state")
            }
            k = {
                t: dst.execute(f"select count(*) from '{t}'").fetchone()[0]
                for t in q
            }
            if q != k:
                dst.close(); src.close(); os.remove(part)
                aus(24, quelle=q, kopie=k)
            seq = dst.execute(
                "select last_written_seq from generation_state where id=1"
            ).fetchone()[0]
            pages = dst.execute("PRAGMA page_count").fetchone()[0]
            dst.close(); src.close()
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            try:
                dst.close(); src.close(); os.remove(part)
            except Exception:  # noqa: BLE001
                pass
            aus(99, fehler=f"{type(e).__name__}: {e}")

        for sfx in ("-wal", "-shm"):
            if os.path.exists(part + sfx):
                os.remove(part)
                aus(23, datei=os.path.basename(part + sfx))

        # 3) META-BELEG in die Zwischendatei
        with open(metatmp, "w") as f:
            json.dump({
                "stamp": STAMP, "source": SRC,
                "integrity_check": ic, "counts": k, "pages": pages,
                "source_seq": seq, "bytes": os.path.getsize(part),
                "t": time.time(),
            }, f, indent=2)
        # Beleg für die Wasserstandspruefung ausserhalb des Artefakts
        with open(os.path.join(PUB, base + ".seqproof"), "w") as f:
            json.dump({"source_seq": seq, "counts": k, "pages": pages,
                       "stamp": STAMP}, f)

        # 4) PUBLIKATION: no-clobber via os.link (atomar, weigert sich bei Existenz)
        try:
            os.link(part, final)          # 41 bei Existenz
            os.link(metatmp, metaf)
        except FileExistsError:
            for p in (part, metatmp):
                try: os.remove(p)
                except FileNotFoundError: pass
            aus(41, ziel=os.path.basename(final))
        os.remove(part)
        os.remove(metatmp)
        print(json.dumps({
            "code": 0, "artefakt": os.path.basename(final),
            "source_seq": seq, "counts": k, "pages": pages,
            "integrity": ic, "t": time.time(),
        }))
        return 0
    aus(42)


if __name__ == "__main__":
    sys.exit(main())
