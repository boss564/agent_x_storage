# E-1 Freigabe-Akte (Rohbelege)
**ts_utc:** `20261115T150525Z`  
**E-1 Freigabe:** `NICHT_ERTEILT`  
**Maschine-JSON:** `docs/architecture/E1_FREIGABE_AKTE.json`

## Verdict

| ID | Status |
|---|---|
| E1_freigabe | `NICHT_ERTEILT` |
| F0 | `PASS` |
| F1_plus | `PASS` |
| F2_plus | `DEFINIERT` |
| F4_plus | `PASS` |
| F5_plus | `DEFINIERT` |
| F6 | `PASS_DEFINITION` |
| F7_plus | `PASS` |
| F8 | `OUT_OF_SCOPE_DEKLARIERT` |

## F0 — gemessene Kommandos (Auszug)

```
git rev-parse HEAD
# 10a4ddf4394f7311fde9f793fdcf71a9134b5bc7
git rev-list --count origin/main..HEAD
# 333
git log --oneline --no-decorate 1e934cff..HEAD
# 10a4ddf4 feat(control-plane): Gate-6 shadow_runner lease enforcement & pin guard
# 70b17659 feat(gatectl): add --allow-manifest-mismatch for pre-migration snapshots
# bd511f0d feat(control-plane): Gate-4 hardening gaps (migrate, abort, post-run, mirror verify)
# 1aa998fc chore(ops): harden shadow-runner launchd plist (KeepAlive/RunAtLoad false)
# b0d700df feat(control-plane): Phase-2 H4 Drive preflight + pinned audit mirror folder
# 7e5bfb32 feat(control-plane): Phase-2 gatectl snapshot, audit chain, immutable mirror
# ca57b4e0 feat(control-plane): Phase-1 run_lease schema v12 (Scratch)
```

## F1+ / F7+ Kernzahlen

- journal_mode: `delete` · wal/shm: absent
- live_sha: `2a7915ef0eff5dea4b3e67332cbb117bf1b738190fbd9304c5dceaa3b54008ed`
- max_run_id preserved: `True`
- abort reopen pass: `True`
- f7 db: `{'max_run_id': 15, 'path': '/var/folders/pl/7s5198dd4917v2qgh1lv99qr0000gn/T/e1_f1plus_20261115T150525Z_eixb01c9/canary.db', 'user_version': 12}`
- f7 pass: `True`

## F4+ Klarstellung

0ee9a5da… was FILE sha256 of gatectl.py, NOT a git commit. Abnahme-Einheit = Quellstand HEAD; Datei-SHA = Fingerabdruck; kein separates Build-Binär (CPython import).

## F5+ / F8

- verify-mirror scope: gatectl verify-mirror prüft NUR Audit-Journal-Einträge (seq_hash.json per rclone cat) — NICHT byte-Identität der LIVE_DB.
- LaunchAgent: OUT OF SCOPE für E-1 Cutover-Kern — end_state=LaunchAgent nicht installiert / nicht geladen
