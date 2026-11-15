# E-1 Integrationssemantik (§4) — bindend vor Live

**Status:** dokumentiert + Scratch-belegt · **E-1 Freigabe ≠ erteilt**  
**Bezug:** Review „vier offene Semantik-Details“; Suite `test_control_plane_e1_residuals.py`

---

## A1 — Exit 76 / ensure-raise / keine halboffene Lease

| Frage | Antwort |
|---|---|
| Ist **76** erstklassig? | Ja: `EXIT_CONTROL_PLANE = 76` in `shadow_runner` — Startverweigerung **vor** Run-Insert. Stderr + Log; **kein** `telemetry_runs`-Eintrag. |
| Rolle in `post-run-check`? | **Nicht anwendbar.** `post-run-check --run-id N` setzt einen existierenden Terminal-Run voraus. Exit 76 ⇒ kein Run ⇒ post-run-check wird nicht aufgerufen. Ops-Semantik: 76 = Control-Plane-Refuse, 75 = Lock-Refuse, 0 = Lauf beendet → dann post-run-check. |
| ensure-raise → halboffene Lease? | **Nein.** `ensure_control_plane_ready` läuft **vor** Claim. Bei Schema/Manifest-Fehler: Exit 76, Store close, **kein** `issue_token`/`claim_run`. Bei uv&lt;12 existiert `run_lease` ggf. gar nicht. Belegt: `test_a1_ensure_fail_leaves_no_half_open_lease`. |

---

## A2 — Zwei Recovery-Pfade (strikt getrennt)

### (a) Lease offen, nie gestartet (TTL abgelaufen)

| | |
|---|---|
| Zustand | `run_lease` open+expired; **keine** `telemetry_runs`-Zeile |
| Recovery | `issue-token` erneut für **dieselbe** `run_id` (MAX+1 unverändert) — altes Token `revoked_at` |
| `run_id=16` | **wiederverwendet**, verfällt **nicht** |
| Beleg | `test_a2a_open_never_started_expiry_reuses_same_run_id` |

### (b) Lease RUNNING, Prozess tot

| | |
|---|---|
| Zustand | `telemetry_runs.status='RUNNING'`; Token konsumiert |
| Recovery | `gatectl abort-run` → `abort_run()` setzt `ABORTED`+`closed_at`, widerruft Rest-Leases; **Audit** in `gatectl` (`abort_run` Journal-Eintrag) |
| Advance | `next_run_id` wird **einmal** MAX+1; zweites `abort_run` → `LeaseError` (nicht RUNNING) — **kein Doppel-Advance** |
| Beleg | `test_a2b_running_stuck_abort_audit_idempotent_advance` |

---

## A3 — absent = proceed, keine Lock-Rekreation

| | |
|---|---|
| Post-Retire | Aktivpfad **absent** (Rename-Archiv); `parse_run_lock` → `locked=False`, `forbid=None` |
| proceed | `main` prüft nur `locked`; absent ⇒ kein Exit 75 |
| Rekreation | Runner **schreibt kein** `RUN.lock`. Einziger Schreiber im Freeze: Operator/Abort-Pfade außerhalb Gate-6-Start. Plist ohne `--run-lock` ⇒ Default-Paketpfad; nach Paket-Retire (TABU bis Freigabe) absent ⇒ proceed nur über Lease. |
| Bugfix | `forbid_run_id_gt` gilt **nur** bei `LOCKED=1` (sonst Post-Retire-Stillstand) |

---

## B — DB-Artefakt-Upload (Beleg, nicht nur Verweis)

| Feld | Festlegung |
|---|---|
| Scope | **In E-1** — eigener Schritt |
| Sequenz | (1) pre-migrate Snapshot off-host → (2) migrate → (3) post-migrate Snapshot off-host → (4) … issue/run/post-run-check **GRÜN** → (5) **DB-Upload-Verify** der post-run Artefakte → (6) `verify-mirror` Audit GRÜN → (7) Retire |
| Gate | Upload der **post-run** DB **nach** `post-run-check --run-id 16` PASS und **vor** `retire-run-lock` |
| Ziel | rclone Remote unter `DEFAULT_AUDIT_MIRROR_FOLDER_ID` / Präfix `db_snapshots/` (Operator bestätigt Ordner) |
| Hash | SHA-256 der Snapshot-Datei; in Audit-Payload |
| Retention | ≥ E-1 + 7 Tage; kein Auto-Delete |
| Transport | `rclone copyto` (kein Config-Dump) |
| `verify-mirror` | Audit-Journal: Sequenz lückenlos, Payload-SHA match, Objekte erreichbar — **nicht** DB-Bytes |

---

## C-Tor (Provenienz)

Abnahme-Einheit = **Commit**. Dirty Worktree-Läufe sind Experimente. Nach Residual-Commit: C1–C6 (Pin-Bindung, F0 neu, F1+ vollständig, pytest am Tip, Bundle = DR ≠ Remote-Ref).
