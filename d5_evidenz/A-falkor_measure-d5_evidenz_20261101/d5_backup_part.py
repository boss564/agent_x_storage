"""D5-Drillteil: PUBLIKATION mit messbarem Haltepunkt.

Warum diese Fassung existiert (gemessen 2026-11-01, Host):
    Die erste Ablauf-Fassung publizierte `.part` -> `.sqlite` in einem Zug.
    Ein SIGKILL traf damit ENTWEDER vor dem Ende (dann blieb eine .part) ODER
    nach `os.link()` (dann war ein finales Artefakt da). Beide Male war das
    Messergebnis "1 publiziertes Artefakt" — und beide Male bedeutete es
    etwas anderes. Ein Abbruchtest, der den Zeitpunkt nicht trifft, misst
    nicht den Abbruch, sondern die Geschwindigkeit.

    Deshalb zerlegt diese Fassung die Publikation in zwei Schritte:
        1. `os.link(PART, FINAL)`      — das Artefakt erscheint unter seinem Namen
        2. `os.link(META_TMP, META)`   — die Quittung erscheint
    und der Ausfall wird im FENSTER zwischen ihnen gemessen.

    Der Befund, den das ergibt, ist benannt und nicht geschminkt:
    zwischen (1) und (2) liegt ein lesbares SQLite-Artefakt OHNE Meta.
    Genau das faengt der Drill mit `Luecke_ohne_meta` ab. Es ist KEIN
    Leser-Schaden (die Datei traegt integrity ok), aber eine Luecke in der
    Kette — und die gehoert benannt.

Ausgabe: ein JSON-Objekt je Zeile.
"""
import hashlib
import json
import os
import sqlite3
import sys
import time

SRC = "/data/drafts.db"
SND = "/sound"
STAMP = os.environ["STAMP"]
PART = f"{SND}/drafts-{STAMP}.sqlite.part"
FINAL = f"{SND}/drafts-{STAMP}.sqlite"
META = f"{SND}/drafts-{STAMP}.meta"
METATMP = f"{SND}/drafts-{STAMP}.meta.part"
EXPECT = ("drafts", "run_metrics", "cycles", "generation_state")

# Haltepunkt fuer den Abbruchtest: nur der Drill setzt beide Variablen.
HALT_MODE = os.environ.get("HALT_MODE", "")     # "" | "before_link" | "after_link"
HALT_SEK = float(os.environ.get("HALT_SEC", "0") or 0)


def out(**kw):
    print(json.dumps(kw))
    sys.exit(0)


def fail(code, **kw):
    print(json.dumps({"status": "FAIL", "code": code, **kw}))
    sys.exit(code)


def sha(p):
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
    except OSError:
        return None
    return h.hexdigest()[:16]


pre = {"src": sha(SRC)}
for sfx in ("-wal", "-shm"):
    pre[sfx] = sha(SRC + sfx)

# --- A) ISOLATIONSPROBE
c = sqlite3.connect(SRC)
c.execute("pragma query_only=1")
schreibfehler = None
try:
    c.execute("pragma user_version=9999")
except sqlite3.Error as e:
    schreibfehler = type(e).__name__ + ": " + str(e)
if not schreibfehler or "READONLY" not in schreibfehler.upper():
    c.close()
    fail(10, reason=f"Isolation nicht belegt — Schreibprobe: {schreibfehler!r}")

# --- B) ONLINE-BACKUP
try:
    os.close(os.open(PART, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640))
except FileExistsError:
    c.close()
    fail(11, reason="Stagingname belegt")
try:
    dst = sqlite3.connect(PART)
    c.backup(dst, pages=64)
    dst.execute("pragma journal_mode=delete")
    dst.commit()
    dst.close()
except sqlite3.Error as e:
    dst.close()
    c.close()
    fail(12, reason=f"conn.backup: {type(e).__name__}: {e}")
c.close()

# --- C) VALIDIERUNG
if open(PART, "rb").read(15) != b"SQLite format 3":
    fail(21, reason="Kopf ist kein SQLite")
v = sqlite3.connect("file:" + PART + "?mode=ro&immutable=1", uri=True)
ic = v.execute("pragma integrity_check").fetchone()[0]
if ic != "ok":
    v.close()
    fail(22, reason="integrity_check: " + str(ic))
tab = {r[0] for r in v.execute("select name from sqlite_master where type='table'")}
fehlt = sorted(set(EXPECT) - tab)
if fehlt:
    v.close()
    fail(23, reason="fehlende Tabellen: " + ",".join(fehlt))
counts = {t: v.execute(f"select count(*) from '{t}'").fetchone()[0] for t in EXPECT}
seq = v.execute("select last_written_seq from generation_state where id=1").fetchone()[0]
pages = v.execute("pragma page_count").fetchone()[0]
v.close()
if seq < 1:
    fail(24, reason=f"Wasserstand der Kopie {seq} < 1")
for sfx in ("-wal", "-shm"):
    if os.path.exists(PART + sfx):
        fail(31, reason="Seitendatei " + sfx + " neben dem Staging")

# --- D) PUBLIKATION, zweistufig: Artefakt zuerst, Quittung danach
if HALT_MODE == "before_link" and HALT_SEK > 0:
    time.sleep(HALT_SEK)
try:
    os.link(PART, FINAL)
except FileExistsError:
    fail(41, reason="Ziel existiert bereits — kein Ersetzen")
except OSError as e:
    fail(42, reason=f"link: {e.strerror}")
os.unlink(PART)

if HALT_MODE == "after_link" and HALT_SEK > 0:
    time.sleep(HALT_SEK)

with open(METATMP, "w") as f:
    json.dump({"stamp": STAMP, "sha": sha(FINAL), "bytes": os.path.getsize(FINAL),
               "seq": seq, "counts": counts, "pages": pages,
               "source_sha": pre["src"]}, f, indent=2)
try:
    os.link(METATMP, META)
except FileExistsError:
    fail(43, reason="Meta existiert bereits — kein Ersetzen")
os.unlink(METATMP)

post = {"src": sha(SRC)}
for sfx in ("-wal", "-shm"):
    post[sfx] = sha(SRC + sfx)

out(status="PUBLISHED", final=os.path.basename(FINAL),
    bytes=os.path.getsize(FINAL), seq=seq, counts=counts, pages=pages,
    integrity=ic, schreibprobe=schreibfehler, quelle_unveraendert=(pre == post),
    staging_reste=sorted(n for n in os.listdir(SND) if ".part" in n))
