# D5-Evidenz — Zuordnung der Baumstufen

Dieses Verzeichnis liegt **außerhalb jedes Git-Checkouts** und ist die
dauerhafte Ablage für Messbelege. Es ersetzt `/tmp` als Evidenzort.

## A — gemessener Stand (2026-11-01 17:37Z)

Entspricht **byte-genau** dem Bündel Gruppe A + kuratierter Drill, das als
Implementierungs-/Testcommit vorgesehen ist.

| Datei | Zustand |
|---|---|
| `d5_drill_v2.sh` | aus dem Agent-Store, SHA `f3b5e8e8…`; identisch mit der Host-Fassung, aus der gemessen wurde |
| `lib`-Inhalt (`d5_*.py`) | aus dem Repo (`deploy/falkor_measure/d5_drill/lib/`) |
| `d5_last/` | Writer- und Live-Protokolle aller Lastläufe (`.jsonl`) |
| `d5_sound/` | Artefakte, Meta-Dateien und Seqproofs der Lastläufe |

**Vorbehalt:** `d5_drill_v2.sh` in A ist die **ungekürzte** Vorfassung mit
`DATA=/var/lib/newsagent`, `/tmp`-Arbeitsverzeichnissen und `"$DIR"`-Pfaden.
Die versionierte Fassung ist `d5_drill.sh` mit Umgebungsvariablen und
`lib/`. Damit gilt: **die Messung lief auf der ungekürzten Fassung**, der
Commit enthält die parametrisierte. Die Neumessung aus dem Commit ersetzt
diesen Stand (Auftrag vom 2026-11-01, Punkt „finaler Commit frisch gemessen").

## B — nicht maßgeblich

Der Host-Baum `/tmp/d5_drill` und der Agent-Store enthielten zwei
verschiedene Fassungen von `d5_drill_v2.sh`:

| Quelle | SHA-256 `d5_drill_v2.sh` |
|---|---|
| `/tmp/d5_drill` (Host) | `f3b5e8e8…` |
| Agent-Store | `f3b5e8e8…` (identisch) |
| Arbeitskopie `/tmp/d5_drill_v2/` lokal | nicht maßgeblich |

Die lokale Arbeitskopie in `/tmp/d5_drill_v2/` diente nur der
`py_compile`-Vorprüfung und enthält zusätzlich Sonden (`d5_fdscan.py`,
`d5_open.py`, `d5_probe.py`, `d5_why_ro.py`), die **nicht** Teil des Drills
sind. Sie sind hier bewusst nicht abgelegt.

## Was in einen Messbericht gehört

Commit-Hash · Zeitpunkt · Host · `podman --version` · `sqlite3 --version` ·
Python-Version · `sha256` von `d5_drill.sh` und `lib/*.py`.

Ohne diese sieben Angaben ist ein Drill-Ergebnis eine Anekdote.

## Regel

Belege werden **nicht** gelöscht, bevor ihr Befund versioniert ist
(Projektregel nach dem 2026-09-11-Verlust). Ein `.part`-Rest aus einem
Abbruchtest ist Beweismaterial, kein Müll.
