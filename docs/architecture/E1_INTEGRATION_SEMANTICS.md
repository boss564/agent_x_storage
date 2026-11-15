# E-1 Integrationssemantik (§4) — bindend vor Live

**Status:** dokumentiert + Scratch-belegt · **E-1 Freigabe ≠ erteilt**  
**Bezug:** Review „vier offene Semantik-Details“ + Restrisiken D1–D6; Suite `test_control_plane_e1_residuals.py`

---

## A1 — Exit 76 / ensure-raise / keine halboffene Lease

| Frage | Antwort |
|---|---|
| Ist **76** erstklassig? | Ja: `EXIT_CONTROL_PLANE = 76` in `shadow_runner` — Startverweigerung **vor** Run-Insert. Stderr + Log; **kein** `telemetry_runs`-Eintrag. |
| Rolle in `post-run-check`? | **Nicht anwendbar.** `post-run-check --run-id N` setzt einen existierenden Terminal-Run voraus. Exit 76 ⇒ kein Run ⇒ post-run-check wird nicht aufgerufen. Ops-Semantik: 76 = Control-Plane-Refuse, 75 = Lock-Refuse, 0 = Lauf beendet → dann post-run-check. |
| ensure-raise → halboffene Lease? | **Nein.** `ensure_control_plane_ready` läuft **vor** Claim. Bei Schema/Manifest-Fehler: Exit 76, Store close, **kein** `issue_token`/`claim_run`. Bei uv&lt;12 existiert `run_lease` ggf. gar nicht. Belegt: `test_a1_ensure_fail_leaves_no_half_open_lease`. |

### D6b — Aufrufer-Semantik Exit 76

| | |
|---|---|
| Retry | **Kein Retry** als transienter Fault |
| Audit | Als **Refusal** buchen (nicht als Infrastructure-Fault) |
| Follow-up | E-1-LA darf Aufrufer verdrahten; bis dahin: Startskripte/Plist dürfen 76 nicht als Restart-Trigger lesen (`KeepAlive=false`) |
| Beleg | `shadow_runner.main` Log-Text `D6b no-retry`; Suite Exit-76-Pfade |

---

## A2 — Zwei Recovery-Pfade (strikt getrennt)

### (a) Lease offen, nie gestartet (TTL abgelaufen) — nur unter Fencing (D1)

| | |
|---|---|
| Zustand | `run_lease` open+expired; **keine** `telemetry_runs`-Zeile |
| Recovery | `issue-token` erneut für **dieselbe** `run_id` (MAX+1 unverändert) — altes Token `revoked_at` |
| `run_id=16` | **wiederverwendet**, verfällt **nicht** |
| Fencing (D1) | `claim_run(token=…)` in `BEGIN IMMEDIATE`: Token muss exakt matchen, nicht expired, nicht closed; nach INSERT muss **dieses** Token `consumed_at` tragen. Stale P1 nach Re-Issue → Refuse. |
| RUNNING-Liveness | **Kein** TTL-Auto-Abort von `RUNNING`. TTL gilt nur für unclaimed Leases. `RUNNING` blockiert `issue-token` (L2); Advance nur über explizites `abort_run`. |
| Beleg | `test_a2a_open_never_started_expiry_reuses_same_run_id` · `test_d1_stale_token_after_reissue_cannot_claim` · `test_d1_running_blocks_reissue_no_auto_abort` |

### (b) Lease RUNNING, Prozess tot — Abort konsumiert (D2)

| | |
|---|---|
| Zustand | `telemetry_runs.status='RUNNING'`; Token konsumiert |
| Recovery | `gatectl abort-run` → `abort_run()` setzt `ABORTED`+`closed_at`, widerruft Rest-Leases; **Audit** in `gatectl` (`abort_run` Journal-Eintrag) |
| Advance / Konsum | Abort **konsumiert** `run_id` (z. B. 16): `MAX(run_id)=16`, nächste = **17**, Lücke dokumentiert; **16 wird nie erneut gelaufen** |
| Rollback | Audit-Fail → `ROLLBACK` der Abort-TX (`test_abort_run_atomic_and_audit_rollback`) — DB bleibt `RUNNING` |
| Zweites Abort | `LeaseError` (nicht RUNNING) — **kein Doppel-Advance** |
| Beleg | `test_a2b_running_stuck_abort_audit_idempotent_advance` · `test_d2_abort_consumes_run_id_gap_documented` |

---

## A3 / D3 — Phasen-Diskriminierung absent

| Phase | Lock-Datei | Verhalten |
|---|---|---|
| **Pre-retire (Freeze)** | `LOCKED=1` am Paketpfad | Datei **weg ohne** `RUN.RETIRED` → **Refuse** (Exit 75) — fail-closed |
| **Post-retire** | absent + `RUN.RETIRED` Marker | absent → proceed (nur noch Lease schützt) |
| Scratch / `--run-lock` Override | absent oder `LOCKED=0` | proceed (expliziter Override) |

| | |
|---|---|
| Retire-Methode | **rename-archive** (nie delete); schreibt `RUN.RETIRED` |
| Rekreation | Runner **schreibt kein** `RUN.lock` |
| Bugfix | `forbid_run_id_gt` gilt **nur** bei `LOCKED=1` |
| Beleg | `test_d3_package_absent_without_marker_refuses` · `test_d3_retire_writes_marker_and_archive` · `test_a3_scratch_parse_matches_post_retire` |

---

## B / D4 — DB-Artefakt-Upload (Fehlpfad blockiert Retire)

| Feld | Festlegung |
|---|---|
| Scope | **In E-1** — eigener Schritt |
| Sequenz | (1) pre-migrate Snapshot off-host → (2) migrate → (3) post-migrate Snapshot off-host → (4) … issue/run/post-run-check **GRÜN** → (5) **DB-Upload** (`db_artefact_upload` ok=true+sha256) → (6) `verify-mirror` Audit GRÜN → (7) Retire |
| Gate | `retire-run-lock --enforce-e1-upload-gate` — ohne prior `db_artefact_upload` ok → **Refuse**, Lock bleibt `LOCKED=1` |
| Partial / Hash-Mismatch | als Fehler werten (kein best-effort) |
| Upload OK, Retire fail | post-Migration + gelockt = zulässiger degradierter Zustand |
| Beleg | `test_d3_retire_writes_marker_and_archive` (Gate-Refuse-Zweig) |

---

## C-Tor (Provenienz)

Abnahme-Einheit = **Commit**. Dirty Worktree-Läufe sind Experimente. Nach Residual-Commit: C1–C6 (Pin-Bindung, F0 neu, F1+ vollständig, pytest am Tip, Bundle = DR ≠ Remote-Ref).

### D6a — Code-Identität (D-Commit)

Relevant ist der Diff des **Code-Commits** gegen seinen Parent, nicht eine ältere leere Range.  
`git diff af0ac607..98a6f307 -- shadow_runner.py gatectl.py` = **nicht leer** (trägt D1–D4).  
Nach Docs-Commit: Code-Dateien unverändert → Pin bleibt an `98a6f307`.

### D5 — Pin-Rebind (committed)

| Pin | Alt (ungültig) | Neu @ `98a6f307` |
|---|---|---|
| Runner `shadow_runner.py` | `e9efe320…` | `1c65b0be2925da85fee6ce090a1fe817f93b61ed6be4a2a0a2cfc0d80e2b8d77` |
| Guard/`gatectl.py` | `93ed1267…` / `f5a3bb76…` | `5068d869b3f03e97cdcc77ed8e683b89b73736b6521dfa89cedb1db70d19d567` |

F0 vollständig wird am Tip **nach** dem Docs-Commit gemessen (Chat-Akte).

---

## D6c — Test ↔ §4-Mapping (Traceability)

| Semantik | Test-ID |
|---|---|
| Exit 76 erstklassig / no-retry (D6b) | `test_runner_refuses_without_token` · `test_a1_ensure_fail_leaves_no_half_open_lease` |
| Expiry → gleiche `run_id` | `test_a2a_open_never_started_expiry_reuses_same_run_id` |
| Stale-Token nach Re-Issue refuse (D1) | `test_d1_stale_token_after_reissue_cannot_claim` |
| RUNNING blockiert Re-Issue; kein Auto-Abort (D1) | `test_d1_running_blocks_reissue_no_auto_abort` |
| Abort konsumiert `run_id` / 2.-abort-refuse (D2) | `test_d2_abort_consumes_run_id_gap_documented` · `test_a2b_…` |
| Abort Audit-Rollback clean | `test_abort_run_atomic_and_audit_rollback` |
| Package absent pre-retire refuse (D3) | `test_d3_package_absent_without_marker_refuses` |
| Post-retire absent proceed / marker | `test_d3_retire_writes_marker_and_archive` · `test_a3_…` |
| Upload-Gate blockiert Retire (D4) | `test_d3_retire_writes_marker_and_archive` |
| Mapping selbst | `test_d6c_section4_mapping_declared` |


---

## D1-a / D2-a / D2-b / D3-a / D4-a — Kanten geschlossen (Scratch)

| ID | Festlegung | Beleg |
|---|---|---|
| **D1-a** | Kein Auto-Abort; `gatectl status` meldet `running[].age_s` für Operator-Watchdog (E-1-LA Alert-Pfad) | `cmd_status` |
| **D2-a** | Write-ahead Audit: `journal.append` **vor** `COMMIT`; Fail → `ROLLBACK` | `cmd_abort_run` · `test_abort_run_atomic_and_audit_rollback` |
| **D2-b** | `--confirm-abort` muss `== --run-id` (operator intentionality) | `test_d2b_abort_requires_confirm` |
| **D3-a** | Marker nur **nach** rename, `O_EXCL`; pre-existing marker → refuse | `test_d3a_preexisting_marker_refuses_retire` |
| **D4-a** | Upload-Gate **default-on**; Opt-out nur `--skip-e1-upload-gate` | `test_d3_retire_writes_marker_and_archive` |
