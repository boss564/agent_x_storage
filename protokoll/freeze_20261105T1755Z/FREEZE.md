# Freeze-Anker — Review-Artefakte (SP-825)

**Erstellt:** 2026-11-05T17:55Z (UTC+1)
**Zweck:** Blocker 0 (unsauberer Working Tree) einfrieren **ohne Löschen**. Der Baum
war zum Zeitpunkt der Wiedereröffnung nicht sauber (1 modified, 7 untracked, 1 Stash).
Diese Datei dokumentiert den Zustand vor dem Freeze-Commit.

**Vorgänger-Anker (vor Freeze):** `913af0dc` (R113, 2026-10-20)
**Branch:** `deploy-safe-snapshot`

## Was eingefroren wird

| Eintrag | Typ | Größe | Umgang |
|---|---|---|---|
| `order_execution_engine/ops/BERICHT.md` | modified | Diff 2.441 B | Diff gesichert (`BERICHT.diff`), dann committet |
| `archive_b2g/audit/` | untracked | 3,0 MB | eingefroren (755 P1-Payloads) |
| `d5_evidenz/` | untracked | 6,8 MB | eingefroren (134 Dateien) |
| `global_market_data/` | untracked | 619 MB | **nur getrackte Quellen** eingefroren (~1 Datei); `.venv/`/`.mypy_cache/` per .gitignore ausgeschlossen |
| `protokoll/` | untracked | 36 KB | eingefroren (inkl. dieses Verzeichnis) |
| `publiziert/r106.md` | untracked | 8 KB | eingefroren |
| `publiziert/scripts__entscheidung_R101.json_6-16.payload.txt` | untracked | 4 KB | eingefroren |
| `scripts/fixtures/` | untracked | 4 KB | eingefroren |
| Stash `stash@{0}` | Stash | 7.137 B Patch | **gelesen, gesichert** (`stash_full.patch`, `stash_stat.txt`), **nicht gedroppt** |

## Was NICHT passiert ist

- Kein `rm`, kein `git clean`, kein `git stash drop`
- Kein `clear`
- Kein `git push` (gemäß Guardrail §2: nur Vorschlag)

## Stash-Inhalt (gelesen, relevant)

`stash@{0}` = „On feature/position-sizing-subswarm: local runbook ticks WIP"
SHA: `27a3bf7bb8d5c6a5846c662007823d0bc1bf9e73`

- `docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md` (+12/−3): Deployment-Drift Chart-vs-Pod
  (Image `agentx-regime-swarm:live-shadow` imperativ gesetzt, PVC 10Gi vs. 5Gi im Overlay,
  Rebuild-Vermerk), neues Metric `swarm_ticks_last_cycle`, `cycle_complete`-Event.
- `scripts/test_live_feed_prometheus.py` (+59): Test für `ticks_per_cycle`-Metrik.

**Bewertung:** Relevante Arbeit, kein Rauschen. Verbleibt als Stash (nicht auf Branch
gezogen) bis zur separaten Entscheidung — der Patch ist hier vollständig gesichert.

## Ablage

| Datei | Inhalt |
|---|---|
| `status_porcelain.txt` | `git status --porcelain=v1` vor Freeze (8 Zeilen) |
| `BERICHT.diff` | `git diff` des modifizierten Berichts (22 Zeilen) |
| `stash_stat.txt` | `git stash show --stat` |
| `stash_full.patch` | `git stash show -p` vollständig (7.137 B) |

## Anker

Der Anker ist der **Commit-Hash des Freeze-Commits** (unten eingetragen) plus
die Prüfung `git status --porcelain` = leer danach.

**Freeze-Commit:** (wird nach dem Commit eingetragen)
