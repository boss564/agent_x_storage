# L5 — Produktions-Startweg (Runbook)

**Status:** Spezifikation unter L5-a…h · **nicht ausführen vor E-1**  
**Freeze:** Runner-Pin `cfc79b2b…cf01` · Persistence-Pin `ce9cc2f8…c47f` · Prod-`RUN.lock` `58340c1e…` unangetastet  
**Verbote bis E-1:** kein `migrate`, kein Paket-`retire`, kein `launchctl`/`bootstrap`/`load`, kein Push `origin/main`

Dieses Dokument **kodifiziert** den Startweg. Es startet nichts. Beispiele nutzen nur Platzhalter (`<DATA_ROOT>`, `<DB>`, `<TOKEN_FILE>`, `<ALARM_LOG>`). Keine Klarname-Pfade, keine Credentials, keine Prod-Ordner-IDs (L5-f / F3).

---

## L5-a — Prod-Startweg

1. Deployter Runner-Datei-SHA256 **muss** `cfc79b2b46191ab54b7850f063242d2ad19f03424951ab182b93ecfd0f6dcf01` sein — sonst **Start verweigern**.
2. Nur `--lease-token-file <TOKEN_FILE>` (Mode `0600`, O_EXCL bei Issue).
3. `--lease-token` auf LIVE-markiertem Data-Root → Refuse Exit **76** (F7, frozen Runner).
4. `CONTROL_PLANE_CANARY` in Prod **unset**.
5. Paket-`RUN.lock` bleibt bis E-1-Retire `LOCKED=1` (dieser Runbook-Schritt startet **nicht** gegen Prod-Lock).

Platzhalter-Aufruf (Dokumentation only):

```text
python -m order_execution_engine.shadow_runner \
  --data-root <DATA_ROOT> \
  --user-id <USER> \
  --allowlist <ALLOWLIST_JSON> \
  --news-jsonl <NEWS_JSONL> \
  --lease-token-file <TOKEN_FILE> \
  --once --no-ws
```

## L5-b — Env-Mandat

| Variable | Wert |
|---|---|
| `CONTROL_PLANE_AUTHZ_ENFORCE` | unset oder `1` (Default = enforce; unset ≠ Allow-All) |
| `CONTROL_PLANE_ROLE` | **explizit** je Prozess: `runner` / `watchdog` / `auditor` / `operator` |
| `CONTROL_PLANE_CANARY` | unset in Prod |
| `CONTROL_PLANE_TEST_MODE` | unset in Prod |

Kein Default-Operator in Runtime-Code. Fehlende Rolle ⇒ Deny (L4-C1/C3).

## L5-c — Erststart vs. Restart

Klassifikation: `detect_restart_kind(<DB>)` — **WAL-/SHM-Größe**, nicht bloße Dateipräsenz (L3-N2).

| Zustand | Merkmal | Pfad |
|---|---|---|
| `clean_start` | kein `-wal` **oder** WAL-Größe == 0 (SHM ignorieren — bleibt nach clean Close oft groß) | Erststart-Sequenz |
| `crash_or_open_wal` | `-wal` **size > 0** | Crash-Recovery (Integrity → ggf. `abort-run` → neues Token) |

**Erststart-Sequenz (logisch, Scratch/Kopie vor E-1):**

1. Leere/frisch kopierte DB (Kopie ≠ LIVE).
2. Schema/Control-Plane nur nach E-1-Freigabe auf LIVE; auf Kopie: `gatectl migrate` unter Rolle `operator`.
3. `issue-token` → Token-Datei O_EXCL + `0600`.
4. Runner mit `--lease-token-file` (Rolle `runner` im Env des Startprozesses, sofern gatectl; Runner selbst pinned).

**Crash-Recovery:** nicht mit Erststart vermischen — erst Integrity/FK, dann explizites `abort-run` bei hängendem `RUNNING`, dann neues Token für **nächste** `run_id`.

## L5-d — kein launchctl vor E-1

- Plist bleibt `KeepAlive=false` / `RunAtLoad=false`.
- Dieses Runbook **dokumentiert** Vordergrund-Start; es führt **kein** `launchctl load|bootstrap` aus.
- Install/Load = Follow-up nach E-1 (E-1-LA), nicht Teil dieses Dokuments.

## L5-e — Watchdog

```text
python -m order_execution_engine.gatectl \
  --db <DB> --data-root <DATA_ROOT> \
  --role watchdog \
  watchdog-check --alarm-log <ALARM_LOG>
```

- Read-only DB-Öffnung.
- `T_max = 2 × TTL_MAX_S` (an `control_plane_lease.TTL_MAX_S` gebunden).
- Alarm: stderr und optional `--alarm-log` (JSONL).

## L5-f — Pfad-Governance

- Nur Platzhalter in Beispielen.
- Evidenz unter operator-lokalen Scratch-Roots / Evidence-Bäumen — keine Klarname-Prod-Pfade im Repo.
- Keine Secrets, keine Drive-Prod-IDs in Snippets.

## L5-g — Trockenprobe (vor E-1)

Gegen **Kopie** (C4-a-Muster): Pre-SHA LIVE (falls vorhanden) → Arbeit nur auf Kopie → Post-SHA LIVE gleich Pre. Suite: `test_control_plane_l5_runbook_dry.py`.

Schritte der Probe (automatisiert):

1. Runner-Pin prüfen (= `cfc79b2b…`).
2. Persistence-Pin prüfen (= `ce9cc2f8…`).
3. Scratch-DB migrieren; `detect_restart_kind` nach Checkpoint = `clean_start`; 0-Byte-WAL = `clean_start`.
4. Authz: unset ENFORCE ⇒ weiterhin Deny ohne Rolle; mit `--role operator` erlaubt Suite-Ops auf Scratch.
5. Token-Datei O_EXCL 0600; LIVE-Refuse `--lease-token` (F7) bleibt Exit 76.
6. LIVE-SHA Pre/Post gleich, wenn LIVE-Datei auf dem Host existiert (L3-N1).

## L5-h — F0 nach Runbook-Commit

Neuer Tip · pytest-Zahl (Docs/L5-Delta benennen) · Pins unverändert · RUN.lock unangetastet · kein launchd · **Mirror-FF sofort** auf `refs/heads/mirror/hardening-control-plane` (nicht `origin/main`).

---

## Operations-Matrix (Soll, L4-a)

Siehe Modul-Docstring `order_execution_engine/control_plane_authz.py` und `operations_matrix_markdown()`.
