# Architektur-Härtung & Revidierter E-Plan (K1–K8)

**Status:** PLAN ABGENOMMEN — **Revision 12.7** (L6/R4 Eigentümer gebucht; Retention gemessen; Tip-Basis `ad4f3f60` vor L6-Commit)  
**Audit-Objekte:**  
- **Produktion (1c):** `1IBXL-lIrXTvnleZMvhv7Er1IJf5VAjla` (`audit_chain_objects_shadow_runner`) — Tests schreiben **nie** dorthin.  
- **Testziel:** `1knskUdopb-6E9eNhoXnuO5V6ULSzCwVe` (`control_plane_audit`) — Abnahme/Harness nur hier.  
Konfig: `AUDIT_OBJECTS_FOLDER_ID` / `--mirror-folder-id`.  
**Rev. B + N1/N2:** RO-Connect; Intent→Spiegel→Rename; Restore Marker-first; **kein** `GATECTL_PACKAGE_ROOT` (Paket = `Path(__file__)/ops`, wie Runner); L4 auf Live/Paket = **TTY + Zufallsnonce**, `--typed-confirm`/`--i-am-a-test` dort verweigert; Scratch behält Suite-Hooks.  
**Freeze-Produktion:** Prod-`RUN.lock` (`LOCKED=1`, SHA `58340c1e…`) + LIVE_DB unverändert.  
**Allowlist-Freeze `5adab542`:** Messlauf-Artefakt.  
**Ziel:** fail-closed Control-Plane vor `run_id=16`.  
**E-1 Live:** gesperrt. **Push `origin/main`:** gesperrt.  
**Retention:** gemessen 2026-11-16 — siehe Abschnitt *L6/R4 + Retention* unten.  
**Rohakte:** `E1_FREIGABE_AKTE.json` · …  
**Freeze-Pins (unverändert):** persistence `ce9cc2f8…c47f` · runner `cfc79b2b…cf01`.  
**Push-Basis:** nach L6-Commit neu messen.

### L6 / R4 — Operator-Freigabe 2026-11-16

**Geber:** Oliver Mueller (`operator_channel`) · **Basis-Tip:** `ad4f3f60` (118 passed / 4 skipped).  
**Buchung:** `scripts/waechter_vertrag.json` → `externes_buch.posten` EXT-1…4.

| ID | Eigentümer | Nachweis-/Review-Frist | Status |
|---|---|---|---|
| EXT-1 Fremd-Konsument Exit 4 / Schnittstelle | Oliver Mueller (`operator_channel`) | 2026-11-30 (post-E-1 / vor Push `origin/main`) | Besitz gebucht; Akzeptanz offen |
| EXT-2 Downstream Zeitstempel-Treue | Oliver Mueller (`operator_channel`) | 2026-11-30 (post-E-1 / vor Push `origin/main`) | Besitz gebucht; Akzeptanz offen |
| EXT-3 NRM-Strom n≥1418 | Oliver Mueller (`operator_channel`) | 2026-11-30 (post-E-1 / vor Push `origin/main`) | Besitz gebucht; Akzeptanz offen |
| EXT-4 Tafel zweite Hand | Oliver Mueller (`operator_channel`) | 2026-11-30 (post-E-1 / vor Push `origin/main`) | Besitz gebucht; Akzeptanz offen |

**Gate:** `python3 scripts/governance_gate.py` → `0/4 EXT offen` (vorher `4/4`).  
**Grenze:** Besitz ≠ Schließung — Fremdnachweis bis Frist; E-1 und Push `origin/main` bleiben gesperrt. RUN.lock / LIVE_DB / `shadow_runner.py` / `persistence.py` / `~/.config/rclone/` unberührt.

### Retention — Messung 2026-11-16 (Operator-Gate)

**Quelle (RO):** `gdrive:newsagent-backup/retention.log` (248 Zeilen, Stand Tail `2026-11-15T03:36:00Z`).  
**Befund:** Keine Treffer für geschützte Härtungs-Artefakte (`p0_p1_preflight*`, `git_bundle_*`, `hardening_incr_*`, `audit_chain*`, `control_plane_audit`, `SHA256SUMS`, `CHAIN_RESTORE`). Log enthält nur Routine-Alterslöschungen (`graph-*`, `drafts-*`, `budget-*`, `config-*`, `pre-receive-*`).

**Noch vorhanden (dirs-only, RO):**  
`p0_p1_preflight_sp1933_offhost_20261115T0954Z/` · `git_bundle_20261115T094918Z/` · `hardening_incr_20261115T{133457,164147,172330}Z/` · `audit_chain_objects_shadow_runner/` · `control_plane_audit/`.

**Operator-Regel (bindend bis E-1+):** Alters-Retention **darf** Anker-, Bundle-, Hardening-Inkrement- und Audit-Ordner **nicht** löschen. Jede künftige Retention-Job-Änderung braucht explizite Denylist dieser Präfixe + Nachmessung gegen `retention.log`.

### Off-Host-Inkrement nach jedem Härtungs-Commit (bindend)

Nach **jedem** Commit auf `hardening/control-plane` (und Nachfolge-Härtungs-Branches):

1. `git bundle create <datei> <letzter_offhost_anker>..<branch>` — nur die neuen Commits.
2. Eigenes Verzeichnis neben dem verankerten Ordner (Anker **nicht** anfassen), mit eigener `SHA256SUMS.txt`.
3. Spiegel per `rclone copy`/`copyto` (kein Config-Dump); Anker-Ordner bleibt unverändert.

**Beweis-Anker (kein Git-Bundle):** `p0_p1_preflight_sp1933_offhost_20261115T0954Z` — ID `1D6QE987XWN_R0U2MMK8OUwCXUYbIKxqI` (Gate-Akten, Guard, `RUN.lock`, Plan). Unberührt lassen.

**Git-Wiederherstellungskette im Drive (4 Glieder; Host: rclone-Lesung + einmalige Schreibprobe 1b):**

| # | Drive-Ordner | ID | Deckt | Bundle-SHA256 (Drive-Redownload) |
|---|---|---|---|---|
| 1 | `git_bundle_20261115T094918Z` | `1w3wvOt9FTCVsovMw97zF58yBZz8OW4Rn` | Voll-Bundle bis `1e934cff` | `25ced3f8…d5b940` |
| 2 | `hardening_incr_20261115T133457Z` | `1VxqOIvk1a2qTBuQlpJ4PE3Z3p6Co7Tzz` | `1e934cff..7e5bfb32` | `b2156dfc…087598` |
| 3 | `hardening_incr_20261115T164147Z` | `1_kKwsiO3S1mgth4yWKFurIUDqw3F3seu` | `7e5bfb32..2d9df0cf` | `89ed461f…072186` |
| 4 | `hardening_incr_20261115T172330Z` | `1PqLcdBUHDIbd20CtMasPgv0zflQRsIQ0` | `2d9df0cf..c0996759` | `6da48ede…59d796` (8447 B) |

Lokal: `reports/P0_P1_PREFLIGHT_SP1933/git_bundle_incr_20261115T172330Z/` + Vorgänger. **Punkt 8 erledigt.** **4-Glieder-Gegentest 2026-11-15T172736Z:** rclone `copyto --drive-root-folder-id` → SHA MATCH ×4 → `git bundle verify` ok ×4 → clone #1 → fetch #2→#3→#4 → Tip `c0996759`; fünf Kerndatei-SHA256 Restored==Host-WT; `/tmp` bereinigt. Beweis `CHAIN_RESTORE_PROOF.json` (jetzt 4 Glieder, `drive_redownload_rehash=true`).

### Reihenfolge vor Phase 2a

| # | Punkt | Status |
|---|---|---|
| 1 | OAuth-Token / eigene rclone-Client-ID + eigener Audit-Ordner (Spiegel = Freigabe-Pfad) | **offen (Prüfer)** — 1a/1c/1d erneut; Ziel-Audit-ID `1IBXL-lIrXTvnleZMvhv7Er1IJf5VAjla` |
| 2 | Systemplatte unter 85 % nach bestätigtem Off-Host-Backup | **PASS** — Data **65 %** / **~652 GiB** frei (Nachmessung 2026-11-15T17:28Z; unter 85 %-Schwelle) |
| 3 | Repo-Plist `KeepAlive=false`, `RunAtLoad=false` | **PASS** — Repo `false`/`false`; kein `WatchPaths`; Install fehlt; Service nicht geladen; plistlib-Regression |
| 4 | Lücken-Schnitt (`retire-run-lock`, `migrate`, `abort-run`, `post-run-check --run-id`, `news_scores.jsonl`-Präfix, `verify-mirror`, Digest streamen, `--skip-disk-check` × Live-Freigabe) | **PASS** — 8 Bausteine + Scratch-Suite `test_control_plane_gate4.py` (44 Control-Plane-Tests gesamt) |
| 5 | Canary-Kopie LIVE_DB (explizite Freigabe nötig): Migration, Soll-Manifest, Digest-Laufzeit/RAM | **Schema/Migrate belegt** (v9→v13 / `8f756655…` auf LIVE-Kopie) — **nicht** E-Canary (kein Live-Markierungspfad; siehe Blocker) |
| 6 | Runner-Anbindung: Claim/`open_run`, Exit bei fehlendem Token, Guard-Pin-Test | **PASS** — Preflight v12+Manifest; Claim via Lease; Exit 75/76; Pin `93ed1267…7116cc` |

**Vor-2a #1 — Abnahmekriterien (Prüfer-Register 2026-11-15, nachgezogen):**

| # | Kriterium | Stand |
|---|---|---|
| 1a | Klartext-OAuth-Token im Google-Konto widerrufen | **offen** — nur Operator |
| 1b | rclone mit eigener Client-ID schreibt wieder | **belegt** (Schreib/Lösch + Bundle-Lesen); Client-ID-Herkunft ohne Config-Dump |
| 1c | Eigener Drive-Ordner für Audit-Objekte; ID im Plan | **offen** — Soll-ID `1IBXL-lIrXTvnleZMvhv7Er1IJf5VAjla` in Plan/Env; frühere Probe `1knskUdopb…` zählt nicht als Abschluss |
| 1d | Überschreib-Test im Zielordner | **offen** — gegen `1IBXL…` mit rclone wiederholen |
| L4 | Live/Paket = TTY + Zufallsnonce; kein `--typed-confirm`-Bypass (N2) | **im Code (12.6)** — Operator-Ratifikation der Hürde steht; Agent mit User-Rechten bleibt technisch nicht ganz aussperrbar |
| Systemplatte | 97 % → 65 % Herkunft | **ungeklärt** (aktuell 65 % gemessen) |

**Canary `/tmp` @ `c0996759` (18:38Z + S1–S4):** belegt **Schema-Migrate v9→v13** und Recovery-Logik auf echten Daten-Bytes — **zählt nicht** als E-Canary-Abnahme (Pfad ohne Live-Markierung; `--run-lock`/`--lease-token`/Paket-Retire unbewiesen). LIVE-Kopie 18:38Z: Operator-Freigabe in AUFGABE „Canary-Abnahme … Freigabe“; SHA `2a7915ef…` unverändert.

**Verifiziert (RO, Host):**
- **Gate #6 Pin** `shadow_runner.py` SHA256 = `93ed12674cefa183aea8d21e751edc5bf7c4cd297429639e333db1f6b27116cc` (Preflight + Claim; Exit 75 lock / 76 control-plane)
- Historisch Pre-Gate-6 Guard: `2157113ad64c88c0e5c2ab346e2c6b3530b869440981aa5a708a3f73c6faefb3` (mtime 2026-11-14T19:49:01Z)
- `RUN.lock` unverändert `LOCKED=1` / `forbid_run_id_gt=14` (SHA `58340c1e…a69845b`); untracked am Paketpfad bis E-1

**Nicht übernommen:** `control.db` (R1). Digest ohne `run_lease` bzw. E-0 vor `issue-token`.

---

## Review-Register

| ID | Status |
|---|---|
| B1–B5, D1–D3 | geschlossen |
| **Guard-WT** | kritisch — Off-Host-SHA jetzt; Dirty-WT nicht „klären“, sondern **sichern + committen/branch** vor jedem Reset |
| **L1** | `revoked_at` + Index; `issue-token` widerruft Abgelaufene |
| **L2–L5** | geschlossen (Stand Tip `ad4f3f60` vor L6-Commit) |
| **L6 / R4** | Eigentümer EXT-1…4 gebucht 2026-11-16; Frist 2026-11-30; Gate `0/4 EXT offen` |
| **Retention** | gemessen 2026-11-16 — geschützte Ordner nicht in `retention.log`; Denylist-Regel dokumentiert |
| R1 / R2 / KeepAlive-Ausnahme | wie Rev. 2 |
| **E-1 / Push `origin/main`** | gesperrt |

---

## Übersicht K1–K8

| ID | Phase |
|---|---|
| K1 Forensik + Guard-WT-Nachtrag | 0 |
| K2 Token + Launchd | 0, 1 |
| K3 Trigger Monotonie / No-Delete | 1 |
| K4 Snapshot + Digest | 2 |
| K5 Falkor | 3′ out-of-scope |
| K6 Recovery / Daemon | 1, 4 |
| K7 Hygiene / Audit | 0, 2 |
| K8 `gatectl` | 2 |

---

## Phase 0 — Forensik, Launchd, Hygiene

### K1 + Guard-WT

- [x] Zeitvergleich run15 ≺ Lock (Akte `K1_RUN15_VS_FORBID14.txt`)
- [x] Guard nur im WT (gemessen); Akte um 19:49Z-Nachtrag ergänzt
- [x] **Off-Host Beweis-Anker (GDrive) 2026-11-15T09:54Z** — Host nur gelesen; **kein Git-Bundle**
  - Ordner: `gdrive:newsagent-backup/p0_p1_preflight_sp1933_offhost_20261115T0954Z`
  - Drive-ID: `1D6QE987XWN_R0U2MMK8OUwCXUYbIKxqI` (Gate-Akten, Guard, `RUN.lock`, Plan — getrennt von der Bundle-Kette)
  - `SHA256SUMS.txt` (58 Einträge) SHA256 = `76523c5611f1f531e17d91425f51dbc982eb6967e31b70c6769b07764283aa08` ← **Anker** (kein WORM; Anker = dieser Hash)
  - Archiv `…tar.gz` 64912 B / `573892aac6a73d677a0f60d19347eb973f1f1b056834c10e8c42f32f32964882`
  - Einzelkopien: Guard `2157113a…efaefb3`, Lock `58340c1e…a69845b`, Plan `61275a46…87c3b4` (7831 B) — Host-Nachmessung MATCH
- [x] **Git-Voll-Bundle** `git_bundle_20261115T094918Z` — Drive-ID `1w3wvOt9FTCVsovMw97zF58yBZz8OW4Rn` (bis `1e934cff`; Start der Wiederherstellungskette)
- [ ] Dirty WT: Guard weiterhin **nicht** per `checkout` verlieren; zusätzlich auf Härtungs-Branch committen (Off-Host ersetzt Commit nicht)
- [ ] Grabstein-Event später in `audit_chain.jsonl`; `forbid_*` ablösen

### Launchd

- [x] `KeepAlive=false`, `RunAtLoad=false`, kein `WatchPaths`; Diff installiert vs. Repo
- [x] Ausnahme zu `Restart=on-failure`: Messlücke bis neuer Freigabe bewusst

**Gate #3 PASS (2026-11-15T15:32Z):**
- Repo-Plist `order_execution_engine/ops/com.agentx.shadow-runner.plist`: **`KeepAlive=false`**, **`RunAtLoad=false`**, **kein** `WatchPaths`; Kommentar `<!-- daemon off until E-1 / explicit load -->`
- Diff Repo ↔ Install: `~/Library/LaunchAgents/com.agentx.shadow-runner.plist` **fehlt** → **installiert ≠ Repo, nicht geladen** (kein Auto-Start möglich ohne `bootstrap`/`load`)
- `launchctl print gui/$(id -u)/com.agentx.shadow-runner` → Service nicht gefunden (RO; kein load/bootstrap)
- Regression: `test_shadow_runner_plist_daemon_off_until_e1` (plistlib only)
- **Ausnahme `Restart=on-failure` (bewusst):** launchd-Plist hat kein systemd-`Restart=`; die frühere KeepAlive-Semantik (= Auto-Restart bei Exit) ist mit `KeepAlive=false` abgeschaltet. Ob ein künftiger expliziter Load + Exit-Verhalten den Guard/`RUN.lock`-Pfad messbar trifft, bleibt **Messlücke bis Freigabe** (kein Runner-Start in diesem Gate)

### Hygiene

- [ ] Gezielte Ignores; `RUN.lock` bleibt am Paketpfad bis `retire-run-lock`
- [ ] Signierschlüssel für Tag dokumentieren

> Phase 1 = nur Scratch. Live-Migration = Phase 2a.

---

## Phase 1 — Control-Plane (Scratch)

### Connect-Factory

- [ ] Pragmas WAL/FULL/FK/busy_timeout; WAL-Umschaltung erst in 2a deklariert
- [ ] RO-Connect **ohne** `ShadowStore.__init__`

### `run_lease` (L1)

```sql
CREATE TABLE IF NOT EXISTS run_lease (
    token        TEXT PRIMARY KEY,
    run_id       INTEGER NOT NULL,
    issued_at    INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL,
    consumed_at  INTEGER,
    revoked_at   INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_run_lease_open_run
  ON run_lease(run_id)
  WHERE consumed_at IS NULL AND revoked_at IS NULL;
```

- [ ] `issue-token`: in einer TX abgelaufene offene Tokens (`expires_at <= now`, noch unkonsumiert) → `revoked_at=now` (auditiert), dann neues Token
- [ ] Gültigkeit: `consumed_at IS NULL AND revoked_at IS NULL AND expires_at > CAST(strftime('%s','now') AS INTEGER)`
- [ ] **kein** `consumed_pid` (Trigger kennt keine PID)

### Trigger auf `telemetry_runs`

- [ ] **BEFORE INSERT:** `NEW.run_id` gesetzt und `== MAX+1`; Lease offen+gültig für diese `run_id`; sonst `RAISE(ABORT)` — kein Consume
- [ ] **AFTER INSERT:** `consumed_at` am passenden Token setzen
- [ ] **BEFORE DELETE** / **BEFORE UPDATE OF run_id:** jedes → `RAISE(ABORT)`

### `open_run` / Claim

- [ ] Explizites `INSERT … (run_id, …) VALUES (MAX+1, …)` in `BEGIN IMMEDIATE`
- [ ] Start genau dann: **kein** `LOCKED=1`-Lock **und** erfolgreicher Claim (Übergang: Lock blockiert bis E-1 weiter)

### Schema Control-Plane (D3 → v12)

- [ ] Nicht in `__init__`; Refuse `<10`; nur `gatectl migrate` / `migrate_control_plane`
- [ ] Spalten: `closed_at`, `status`
- [ ] **`RUN_ID_FLOOR = 15`:** nächste Claim-ID = `MAX(15, COALESCE(MAX(run_id),0))+1` — gilt **auch auf Scratch** (kein „Scratch ab 1“); Grabstein bleibt nach Restore auf älteren Dump
- [ ] **Altzeilen 1–15:** nach Migration nicht `status=NULL` lassen — Terminalstatus setzen; **run15 = `ABORTED`** (Grabstein); 1–14 terminal (`ABORTED`/`COMMITTED` nach Aktenlage), damit E-0 „kein RUNNING“ und E-4 eindeutig
- [ ] **Lease BI (G1):** `issued_at <= now+5`; TTL-Differenz allein reicht nicht (Zukunfts-`issued_at` wäre sonst Bypass)
- [ ] **Preflight:** `preflight_check.py` Verzweigung `has_closed_at` (≈757–781) in v10-Umfang anpassen; bestehenden Zeugen-Test mitziehen (kein erfundener „Negativtest“-Name)

### Manifest-Integrität Trigger (fälschbar sonst)

- [ ] `gatectl status` / `trigger_manifest_sha256`: CREATE TABLE (`run_lease`+`telemetry_runs`) + Index `ux_run_lease_open_run` + **alle** Trigger beider Tabellen hashen (G2 — nicht nur `tbl_name='run_lease'`)

### Tests

- [ ] Lease/Run-Fixture; Concurrency; expired; wrong id; reused; no-lease ABORT; revoke+reissue (L1)
- [ ] Preflight/`closed_at`-Pfad nach v10 grün

### Daemon

- TTL = Claim-Fenster; Crash → neues Token → nächste `run_id`
- E-4 an `closed_at` / Terminal-`status`

### L2 — hängendes `RUNNING`

- [ ] `issue-token` **verweigert**, solange `EXISTS (SELECT 1 FROM telemetry_runs WHERE status='RUNNING')`
- [ ] Zuvor: `gatectl abort-run --run-id N` setzt auditiert `status=ABORTED`, `closed_at=now` (kein stilles Überschreiben)

---

## Phase 2 — `gatectl`, Snapshot, Audit

- [x] Snapshot Artefakt-SHA + logischer Digest (`run_lease` ausklammern / vor Token)
- [x] Kommandos: `status`, `issue-token`, `verify-snapshot`, `post-run-check --run-id`, `migrate`, `retire-run-lock`, `abort-run`, `verify-mirror`
- [x] Audit-Kette; GDrive-Spiegel fail-closed **nur freigebend** (H4 Preflight + verify-mirror)
- [x] Auflage 3 Carry-over / Gate #4 Lücken-Schnitt (2026-11-15)
- [x] `news_scores.jsonl`: Offset + Größe + SHA256(Präfix) via `compute_jsonl_prefix_sha256`

**Gate #4 PASS (2026-11-15):** Streaming-Digest (`sha256_file_streaming`); `--skip-disk-check` refuse auf LIVE ohne `--allow-live-skip-disk-check`; JSONL-Präfix-SHA; `verify-mirror`; `migrate` mit Pre-Snapshot+Audit+Post-Manifest; `retire-run-lock` TABU für `ops/` + Audit; `abort-run` atomar (Audit-Fail → ROLLBACK); `post-run-check --run-id` mit Runner-SHA + optional JSONL.

---

## Phase 2a — Live-Migration

- [x] Scratch grün + Gate #5 Canary (logische Kopie via `Connection.backup`)
- [x] **F1** byte-identische LIVE-Kopie (`shutil.copy2`) + Restore-Probe + Abort-Rollback — `docs/architecture/E1_F1_MIGRATION_PROBE.json`
- [ ] LIVE `gatectl migrate` — **nur nach E-1-Freigabe**

**Gate #5 Canary PASS (2026-11-15T144406Z)** — Artefakt `docs/architecture/GATE5_CANARY_MEASUREMENT.json` (untracked):

| Feld | Wert |
|---|---|
| LIVE_DB | `…/agentx/shadow_live/shadow/shadow/shadow.db` |
| Größe | 364 544 B |
| SHA-256 vorher/nachher/final | `2a7915ef0eff5dea…b54008ed` (identisch; RO-URI + `Connection.backup`) |
| Canary Pre | integrity=`ok`, schema=**9**, max_run_id=**15** |
| Canary Post-migrate | integrity=`ok`, schema=**12**, max_run_id=**15**, null-status=0 |
| Trigger-Manifest Ist | `3e685b7d98349aeefae3ab591908dd672b731f89f06a7d71fedbd0e49574c9d9` |
| Trigger-Manifest Soll | `3e685b7d98349aeefae3ab591908dd672b731f89f06a7d71fedbd0e49574c9d9` (**MATCH**) |
| Streaming-Digest | wall **0,186 ms**; tracemalloc peak **1 570 060 B**; ru_maxrss **50 511 872 B** |
| Trockentest | issue-token→claim→abort→post-run **run_id=16 nur auf /tmp-Canary**; LIVE max bleibt 15 |
| Cleanup | `/tmp/gate5_canary_20261115T144406Z` entfernt |
| Hinweis | Pre-`verify-snapshot` braucht `--allow-manifest-mismatch` (v9 ≠ Soll-DDL); Post-`migrate` erzwingt Soll-Match |

**Gate #6 Runner-Anbindung PASS (2026-11-15):**
- `main`: LOCKED=1 → Exit **75**; `forbid_run_id_gt` vs next run_id → Exit **75**
- `ensure_control_plane_ready`: schema≠12 oder Manifest≠Soll → Exit **76**
- kein gültiges `run_lease` → `LeaseError` / Exit **76**, kein `telemetry_runs`-Insert
- Claim via `open_run`→`claim_run` (Lease BI); `close_run(COMMITTED|ABORTED)` im `finally`
- Scratch-Suite `test_control_plane_gate6.py` (Negativ: no-token / lock / DROP TRIGGER; Positiv: issue→once→COMMITTED)
- Pin: `93ed12674cefa183aea8d21e751edc5bf7c4cd297429639e333db1f6b27116cc`

---

## E-1 Cutover — Freigabe gesperrt (Review 2026-11-15 → Rev. 6)

**Satz:** E-1 wird nicht freigegeben, solange der RUN.lock vor dem vollständigen Zyklus
(issue → Einzellauf → post-run-check GRÜN) gelöst würde. Lock-Ablösung = **letzter** Akt.
Rohbelege in `E1_FREIGABE_AKTE.json` — Zusammenfassung allein ist kein Beleg.

### F0 — Tip neu gemessen (2026-11-15T150525Z)

| Messung | Ergebnis |
|---|---|
| `git rev-parse HEAD` | `10a4ddf4394f7311fde9f793fdcf71a9134b5bc7` (= erwartet) |
| `git rev-list --count origin/main..HEAD` | **333** (alte **326 ungültig**) |
| `git log --oneline 1e934cff..HEAD` | **7** Commits: `ca57b4e0`…`10a4ddf4` (Phase-1 → Gate-6) |
| R3 (kein Amend/Rebase/Force am Tip) | Reflog: `commit:` (kein amend/rebase/reset --hard) · Parent `70b17659` |
| R4 Governance | `scripts/governance_gate.py` rc=0 · Warnung **4/4 ohne Eigentümer** (Lücke DEKLARIERT) |
| Guard-SHA | Datei = Pin `93ed1267…7116cc` · WT blob = HEAD blob `33e0d327…` |
| RUN.lock | SHA `58340c1e…a69845b` · `LOCKED=1` · untracked |
| LIVE | SHA `2a7915ef…` · `journal_mode=delete` · **kein** `-wal`/`-shm` · uv=9 · max=15 · kein `shadow_runner`-PID · LaunchAgent nicht installiert |

### Code-Stand-Zeile (F4+) — Abnahme-Einheit = Quellstand HEAD

**Korrektur:** `0ee9a5da…` war **Datei-SHA256** von `gatectl.py`, **kein** Git-Commit.
Kein separates Build-Binär — F1-Probe und E-1 importieren dieselbe Worktree-Quelle.

| Artefakt | Datei-SHA-256 | Git-Blob @ HEAD | Provenienz |
|---|---|---|---|
| HEAD | — | `10a4ddf4…` | Tip |
| `gatectl.py` | `0ee9a5da…180c78b7` | `e01a7af2…` | Ancestor-Kette enthält `7e5bfb32`/`bd511f0d`/`70b17659` |
| `shadow_runner.py` | `93ed1267…7116cc` | `33e0d327…` | Gate #6 Pin; WT=HEAD |
| `control_plane_lease.py` | `5af2bb8f…d499dff6` | `13c2934a…` | `migrate_control_plane` seit `ca57b4e0` (Ancestor von HEAD) |
| Manifest Soll | `3e685b7d…574c9d9` | aus HEAD-DDL via `expected_control_plane_manifest_sha256()` | F1+ MATCH |

`git show HEAD:…/control_plane_lease.py` enthält `SCHEMA_V12=12`, `migrate_control_plane`, `BEGIN IMMEDIATE`.

### Korrigierte E-1-Schrittfolge (Soll)

| # | Schritt | Lock-Status | Nachweis |
|---|---|---|---|
| 1 | Pre-Migration-Snapshot LIVE + `integrity_check` + **expliziter** Off-Host-DB-Artefakt-Upload | `LOCKED=1` | Snapshot-SHA |
| 2 | `gatectl migrate` LIVE 9→12; Post-`integrity_check`; Manifest = Soll | `LOCKED=1` | sonst **Restore** (F6) |
| 3 | Post-Migration-DB-Artefakt off-host + `verify-mirror` auf **Audit-Kette** GRÜN | `LOCKED=1` | F5+ (siehe unten) |
| 4a | `issue-token --run-id 16` | `LOCKED=1` | F7+ |
| 4b | **Primär:** `shadow_runner` + `--run-lock <scratch UNLOCKED>` | Paket-Lock physisch `LOCKED=1` | Lease-Pfad (F2+) |
| 4c | **Sekundär:** Plist-Test — **kein „oder“** | Paket-Lock `LOCKED=1` | launchd-Env |
| 4d | `post-run-check --run-id 16` PASS | `LOCKED=1` | Zyklus getragen |
| 5 | **`retire-run-lock`** + Audit + `verify-mirror` | Lock jetzt abgelöst | letzter Akt |
| — | LaunchAgent | **OUT OF SCOPE (F8)** | Endzustand = nicht geladen; Load = Follow-up E-1-LA |

### F0 / F1+…F8 Register

| # | Status | Beleg |
|---|---|---|
| **F0** | **PASS (gemessen)** | `E1_FREIGABE_AKTE.json` → `F0` inkl. Kommandos; count=**333** |
| **F1+** | **PASS (gemessen)** | `journal_mode=delete`; kein wal/shm; Quieszenz deklariert; copy2 SHA=LIVE; max_run_id=15 erhalten; Abort nach `trg_lease_bu` → **Reopen** uv=9 / kein `run_lease`; Restore SHA=LIVE |
| **F2+** | **DEFINIERT** (nicht ausgeführt) | Scratch-Lock **unlocked**; kein Acquire — Override prüft nur diesen Pfad; Schutz = **Lease** (derselbe Pfad wie nach retire); Paket-Lock bleibt für Default-Starts |
| **F3** | **DOKUMENTIERT** | primär **und** sekundär — Ausführung = Freigabe |
| **F4+** | **PASS (gemessen)** | Quellstand HEAD; Datei-SHA=Fingerabdruck; Probe-Import = Live-Import; `ca57b4e0` Ancestor; migrate 9→12 in HEAD-Tree |
| **F5+** | **DEFINIERT** | `verify-mirror` = **Audit-Journal**-SHA off-host, **nicht** LIVE_DB-Bytes; DB-Artefakt-Upload = eigener ausgewiesener Schritt; GRÜN vor Lock-Ablösung |
| **F6** | **PASS (Definition)** | Restore-Kriterien unverändert |
| **F7+** | **PASS (gemessen)** | refuse auf **post-Migration-Kopie** uv=12 / max=15 |
| **F8** | **OUT OF SCOPE** | LaunchAgent nicht Teil E-1-Kern; Follow-up E-1-LA |

**Gesamt:** Vorarbeit messbar · Restrisiken A/B/C auf Scratch geschlossen · **E-1 Live-Cutover gesperrt**.

### Restrisiken A/B/C (Rev. 7 — Scratch belegt)

| ID | Status | Beleg |
|---|---|---|
| **A1** Fail-Closed-Lease | **PASS Scratch** | schema/manifest/no-token → Exit **76**; `DatabaseError` in ensure → raise; Suite `test_control_plane_e1_residuals.py` |
| **A2** Lease-Stuck | **PASS Scratch** | TTL-Expiry → re-issue widerruft; `RUNNING` → `abort_run` → nächste `run_id` issuebar |
| **A3** Scratch = Post-Retire | **PASS Scratch** | Retire = **rename-archive** (nie delete); Aktivpfad **absent**; parse `locked=False`/`forbid=None`; Generalprobe absent oder `LOCKED=0\n`; **Bugfix:** `forbid_run_id_gt` gilt nur noch bei `LOCKED=1` |
| **A4** Override explizit | **PASS Scratch** | Default = `ops/RUN.lock`; Plist **ohne** `--run-lock` |
| **B** DB-Artefakt-Upload | **DEFINIERT** | In E-1-Scope; **vor** Retire; Ziel = H4-Folder + `db_snapshots/`; Hash = Artefakt-SHA256; Retention ≥ E-1+7d; Transport `rclone copyto`; `verify-mirror` = Audit-Journal Vollständigkeit/Integrität |
| **C** Probe↔HEAD Code | **PASS C2** | Committed Pin `e9efe320…` @ `6d7fd729`; D6a `6d7fd729..af0ac607` runner/gatectl **leer**; D-WT erneut dirty |
| **D1** Lease-Fencing | **PASS Scratch** | `claim_run(token=)` atomar; stale nach Re-Issue refuse; kein RUNNING-TTL-Abort |
| **D2** Abort konsumiert | **PASS Scratch** | Abort → MAX=rid, next=rid+1; 2. abort refuse; Audit-Fail → ROLLBACK |
| **D3** absent-Phase | **PASS Scratch** | Package absent ohne `RUN.RETIRED` → refuse; Marker → proceed |
| **D4** Upload-Gate | **PASS Scratch** | `--enforce-e1-upload-gate` ohne Upload → Retire refuse, Lock bleibt |
| **D5** F0 am Tip | **PASS gemessen** | Tip `af0ac607`; ahead=338; R3 commit; R4 rc=0; Guard-Pin WT stale bis D-Commit |
| **D6** Deklarationen | **PASS Scratch** | D6a leer @ Tip; D6b Exit-76 no-retry; D6c Mapping in `E1_INTEGRATION_SEMANTICS.md` |

**Retire (Scratch):** `before_sha256` im Audit **vor** Rename; Archiv `RUN.lock.retired.<sha12>.<utc>`; `RUN.RETIRED` Marker; Paket-`ops/` weiter **TABU** bis eigener Freigabeakt.

### F2+ Scratch-Lock-Semantik (verbindlich)

| Punkt | Festlegung |
|---|---|
| Initialzustand Scratch | **absent** (bevorzugt, = Post-Retire) oder `LOCKED=0\n` ohne forbid |
| Wirkung | `parse_run_lock` → `locked=False`, `forbid=None`; Paket-Lock wird bei Override **nicht** gelesen |
| Getesteter Mechanismus | Token/Lease = Post-retire-Sicherheitsmodell (gleiche Verzweigung) |
| A4 | `--run-lock` nur explizit; Plist ohne Override; Default = Paketpfad |

### F5+ Mirror-Zielzustand (verbindlich)

| Objekt | Bedeutung |
|---|---|
| `verify-mirror` | Jeder lokale Audit-Eintrag existiert off-host mit **identischem Payload-SHA** |
| LIVE_DB | Wird von `verify-mirror` **nicht** byteverglichen |
| DB-Nachweis | Separater Snapshot-Upload pre/post migrate (Schritt 1+3); SHA in Audit/Akte |
| Schreibakt | `verify-mirror` schreibt keine DB; nur ggf. Audit-Eintrag `verify_mirror` |

### F6 Rollback-Kriterium (bindend)

**Restore** (Snapshot zurück, keine In-Place-Reparatur), wenn nach LIVE-`migrate` eines gilt:

1. `PRAGMA integrity_check` ≠ `ok`
2. `user_version` ≠ 12
3. Trigger-Manifest Ist ≠ Soll `3e685b7d…574c9d9`
4. `MAX(run_id)` ≠ 15
5. `status IS NULL`-Zeilen verbleiben
6. Non-Zero Exit / Exception aus `gatectl migrate`
7. Mid-Step-Abbruch → Reopen zeigt uv≠9 oder Partial-DDL (auf Kopie: Abort `trg_lease_bu` → uv=9, kein `run_lease`)

### F1+ Messwerte (Akte `20261115T150525Z`)

| Feld | Wert |
|---|---|
| LIVE SHA | `2a7915ef0eff5dea4b3e67332cbb117bf1b738190fbd9304c5dceaa3b54008ed` |
| journal_mode | `delete` · wal/shm absent · kein runner-PID |
| Kopie | `shutil.copy2` byte-identisch |
| Post-migrate | UV=12, **max_run_id=15**, integrity=ok, Manifest MATCH |
| Abort | Reopen-Kontrolle (nicht nur Datei-SHA) |
| F7+ DB | uv=12 / max=15 auf Canary-Kopie |

---

## Phase 3′ — Falkor out-of-scope (shadow run16)

---

## Phase 4 — Recovery S1–S4 & E

### Recovery-Szenarien (definiert)

| ID | Abbruch | Erwartung |
|---|---|---|
| **S1** | vor `issue-token` | kein Lease; kein neuer Run; fail-closed |
| **S2** | nach Token, vor Claim; TTL abgelaufen | `issue-token` erneut: altes Token `revoked_at`; neues Token ok (L1) |
| **S3** | nach Claim, `status=RUNNING`, Prozess tot (SIGKILL) | `issue-token` refuse; `abort-run` → `ABORTED`; danach neues Token für **nächste** `run_id` |
| **S4** | Reboot mit aktivem Lock (vor Lock-Ablösung) | rc=75; nach `retire-run-lock` nur Token-Pfad |

- [x] S1–S4 **Wiederanlauf-Logik** auf Scratch + (opt-in) LIVE-Byte-Kopie belegt — **nicht** E-Abnahme
- [ ] E-Canary auf **live-markiertem** Temp-Pfad + Paket-Lock-Semantik (nach Code-Schnitt Paket-Retire / Plan-E-Reihenfolge)

**Messwerte S1–S4 (2026-11-15, Tip `c0996759`) — was belegt / was nicht:**

| ID | Scratch | `/tmp`-Kopie (ohne Live-Markierung) | Nicht belegt |
|---|---|---|---|
| **S1** | Exit **76**; kein Lease; keine neuen Runs | gleich; max=15 | LIVE-Flags |
| **S2** | TTL-Expiry → Re-Issue + `revoked_at` | run_id=16 | — |
| **S3** | `abort-run` → ABORTED; nächste `run_id` | 16→17 | — |
| **S4** | Scratch-Lock Exit **75**; `retire` + `--skip-e1-upload-gate`; Token-Pfad | gleich | **Paket-Lock-Retire**; Runner-Start unter Paket-Lock; `--run-lock`/`--lease-token`-Refuse auf LIVE |

Suite: `test_control_plane_recovery_s1_s4.py` — Default = Scratch only; Canary nur mit `CONTROL_PLANE_CANARY=1` (+ optional `CANARY_LIVE_SHA`, `CANARY_S14_ROOT`). LIVE SHA Pin default `2a7915ef…` (nach run16: `CANARY_LIVE_SHA` setzen).

### E-0 … E-5 (Rev. B — Runbook, Paket-Kopie / live-markierter Temp-Root)

**Kein Lauf vor Lock-Ablösung.** Prod-`ops/RUN.lock` und Prod-LIVE bleiben TABU.

| Schritt | Name | Lock | Hinweis |
|---|---|---|---|
| **E-0** | Vorprüfung | `LOCKED=1` | nur RO-`status`/Checks; **kein** SHA-Drift der LIVE_DB-Kopie; `schema=not_migrated` auf v9 |
| **E-1** | migrate | `LOCKED=1` | einzige WAL-Umschaltung; Off-Host-Artefakt + `db_artefact_upload`; bei Fail → `restore-db-artefact` |
| **E-2** | Paket-Retire | → Marker | `--allow-package-retire` + `--allow-live-db` + L4 `RETIRE_PACKAGE_LOCK`; Intent-Spiegel **vor** Rename; Confirm danach; `GATECTL_PACKAGE_ROOT` = Temp-Paket |
| **E-3** | Token | Marker | `issue-token` → `--lease-token-file` (kein raw argv auf LIVE) |
| **E-4** | Lauf | Marker | **Vordergrund von Hand**, kein launchd; **innerhalb Token-TTL** |
| **E-5** | Nachprüfung | Marker | RO `post-run-check` + `verify-mirror` |

**Notbremse:** manuelles `ops/RUN.lock` mit `LOCKED=1` (ohne Retire-Undo) → Runner Exit **75** (gewollt).  
**Rollback nach E-2:** `restore-run-lock` (Marker zuerst; Lock+Marker → `--clear-stale-marker`; offene Tokens widerrufen).  
**Abnahme-Ort:** `/tmp/abnahme_revb_<ts>/` — danach vollständig löschen; Probe-Audit-Ordner `1knsk…` von Testobjekten leeren.

---

## Explizit nicht

- Guard per `checkout`/`stash` verlieren ohne Off-Host-Kopie  
- Auto-Migration in Store-`__init__`  
- Consume-vor-Insert · `consumed_pid` · `control.db`  
- Lock verschieben / lösen **vor** post-run-check GRÜN  
- Netzabhängige Refuse  
- Claim-Test auf Prod-LIVE ohne E-1-Freigabe  
- Falkor als run16-Blocker  
- E-1 ohne F1–F7  
- Push trotz fehlendem Remote-Ref (separater Blocker)  
