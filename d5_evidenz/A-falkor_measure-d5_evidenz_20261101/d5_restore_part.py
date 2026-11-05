"""D5-Restore-Probe: oeffnet die wiederhergestellte Kopie an fremdem Ort.

Rennt mit `mode=ro&immutable=1`: kein -shm wird angelegt, kein Schreibrecht
verlangt. Genau das verlangt ein Restore an einem Ort, der nicht die
Produktion ist.
"""
import json
import sqlite3

c = sqlite3.connect("file:/rest/restored.db?mode=ro&immutable=1", uri=True)
ic = c.execute("pragma integrity_check").fetchone()[0]
counts = {t: c.execute("select count(*) from '" + t + "'").fetchone()[0]
          for t in ("drafts", "run_metrics", "cycles")}
seq = c.execute("select last_written_seq from generation_state where id=1").fetchone()[0]
pages = c.execute("pragma page_count").fetchone()[0]
c.close()

print(json.dumps({"integrity": ic, "counts": counts,
                  "last_written_seq": seq, "pages": pages}))

# Vergleich gegen die Produktion (nur lesend, ohne Sperre).
p = sqlite3.connect("file:/data/drafts.db?mode=ro&immutable=1", uri=True)
pc = {t: p.execute("select count(*) from '" + t + "'").fetchone()[0]
      for t in ("drafts", "run_metrics", "cycles")}
pseq = p.execute("select last_written_seq from generation_state where id=1").fetchone()[0]
p.close()
print(json.dumps({"produktion": {"counts": pc, "last_written_seq": pseq},
                  "identisch": pc == counts and pseq == seq}))
