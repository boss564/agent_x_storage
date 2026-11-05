"""D5-Vorlauf: liest nur die Datenbank-Metadaten der Produktion.

Ausgabe: ein JSON-Objekt. Kein Schreibzugriff:
  * journal_mode wird mit PRAGMA gelesen, mit query_only=1 abgesichert;
  * Schema und Wasserstand ueber mode=ro&immutable=1.
"""
import json
import sqlite3

P = "/data/drafts.db"

c = sqlite3.connect(P)
c.execute("pragma query_only=1")
jm = c.execute("pragma journal_mode").fetchone()[0]
c.close()

v = sqlite3.connect("file:" + P + "?mode=ro&immutable=1", uri=True)
tables = sorted(r[0] for r in v.execute("select name from sqlite_master where type='table'"))
r = v.execute("select last_written_seq, next_seq from generation_state where id=1").fetchone()
v.close()

print(json.dumps({
    "journal_mode": jm,
    "tables": tables,
    "last_written_seq": r[0] if r else None,
    "next_seq": r[1] if r else None,
}))
