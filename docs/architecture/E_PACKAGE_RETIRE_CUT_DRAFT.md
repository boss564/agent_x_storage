# Entwurf: Paket-Retire-Schnitt (Rev. B — Prüferpunkte 1–5 eingearbeitet)

**Status:** Rev. B + **N1/N2-Fixes** im WT (2026-11-15); **nicht committen** bis Prüfer-Nachmessung; Prod unberührt  
**N1:** `GATECTL_PACKAGE_ROOT` entfernt — Paket = `Path(__file__)/ops` (wie Runner).  
**N2:** Live/Paket: kein `--typed-confirm`/`--i-am-a-test`; TTY + `stem:nonce` Pflicht.  
**Änderung gegenüber Rev. A:** RO-Connect ohne WAL (§A); Intent→Spiegel→Commit→Confirm (§4); Restore-Reihenfolge + Heilung Lock+Marker (§5); **L4 bindend** (§6); kleinere Klarstellungen (§1/§8/§9)  
**Ziel:** auditierter Weg, Paket-`ops/RUN.lock` abzulösen und Runner danach nur über Marker + Token zu starten  
**Betroffene Dateien:** `gatectl.py`; `control_plane_lease.py` (RO-Connect); `control_plane_audit.py` (post-retire lock-absent); Runner/`persistence` unverändert (§7)  
**Folge:** neue Pins; live-markierte Temp-Paket-Abnahme; Plan E-0…E-5

---

## 0. Ist-Zustand (gelesen + Prüfer-Messung)

| Mechanismus | Verhalten |
|---|---|
| `cmd_retire_run_lock` | Soft-TABU: `lock == _REAL_LOCK` **oder** unter `ops/` → Refuse (829–847) |
| `_open_sqlite` | setzt immer `PRAGMA journal_mode=WAL` — **auch bei `status --allow-live-db`** |
| Prüfer-Messung | v9 unter live-markiertem Temp: vor `status` `journal_mode=delete`, danach `wal`; Datei-SHA geändert; `-wal` entstanden; `status` bricht mit `no such table: run_lease` ab |
| Plan | WAL-Umschaltung gehört zur **Migration**, nicht zur Vorprüfung |
| Runner post-retire | absent + `RUN.RETIRED` → proceed to lease; M2 unverändert |

---

## A. Lesende Verbindungen — kein Schreib-Nebenkanal (Prüferpunkt 1)

### A.1 Connect-API (Soll)

| Funktion | Nutzung | Öffnung |
|---|---|---|
| `connect_control_plane_ro(path, *, allow_live=False)` | **neu** | `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`; **keine** `journal_mode`/`synchronous`-Pragmas; nur `query_only=ON` optional; FK/busy ok falls RO-sicher |
| `connect_control_plane` / `_open_sqlite` | **nur Schreibpfade** | WAL+FULL wie heute — ausschließlich `migrate` (und ggf. issue/abort/claim die ohnehin schreiben) |

### A.2 Welche Kommandos RO nutzen

| Kommando / Teil | Connect |
|---|---|
| `status` | **RO** |
| Vorbedingungen in `retire-run-lock` / `restore-run-lock` (V2/V5/V6, Digest) | **RO** |
| `post-run-check` (Lese-Invarianten) | **RO** (Artefakt-Persistenz ggf. separat auf Snapshot-Dateien, nicht via WAL-Umschaltung der LIVE-DB) |
| `verify-snapshot` Pre-Migrate | **RO** |
| `migrate` | RW (`_open_sqlite`) — **einziger** Ort der WAL-Umschaltung auf LIVE |

### A.3 `status` auf v9

- Kein Absturz bei fehlendem `run_lease`.
- Ausgabe z. B. `"schema": "not_migrated"`, `user_version=9`, `control_plane=false`, `ok=true` (Beschreibung), nicht `ok=false` wegen fehlender Tabelle.
- **Negativprobe:** Datei-SHA und `journal_mode` vor/nach `status` identisch; keine `-wal`/`-shm`.

### A.4 Lesen der LIVE-DB in Retire-Vorbedingungen (Prüfer §5 klein)

V2/V5/V6 und Digest brauchen DB-Lesen. **Festlegung:**

- Retire-Vorbedingungen öffnen LIVE **RO** und verlangen dafür **`--allow-live-db`** (explizite Lesefreigabe derselben Klasse wie andere LIVE-Touches), **zusätzlich** zu `--allow-package-retire`.
- Begründung: RO ohne Schalter wäre ein stiller LIVE-Zugriffskanal; mit Schalter + getippter Bestätigung (§6) bleibt der Kanal auditierbar.
- Scratch-Retire: unverändert ohne `--allow-live-db`.

---

## 1. Schalter (Anforderung 1)

```
--allow-package-retire
```

| Aufruf | Ergebnis |
|---|---|
| Paket-Lock ohne Schalter | TABU / Refuse |
| Paket-Lock + `--allow-package-retire` (+ `--allow-live-db` für DB-RO/V*) | nur wenn V1–V8 halten |
| Scratch-Lock + `--allow-package-retire` | Refuse (Schalter nur für `_REAL_LOCK`) |
| Scratch-Retire ohne Schalter | wie heute |

`--allow-live-db` öffnet Retire **nicht** allein.

---

## 2. Vorbedingungen Paket-Retire (Anforderung 2)

Alle **vor** Intent-Spiegel und vor Rename. Verletzung → Lock unberührt.

| # | Prüfung | Connect |
|---|---|---|
| V1 | Audit-Kette intakt | — |
| V2 | Schema = v13 | RO + `--allow-live-db` |
| V3 | Trigger-Manifest = Soll-Pin | RO |
| V4 | Keine `shadow_runner`-PIDs | — |
| V5 | Kein `RUNNING` | RO |
| V6 | Kein offenes Token | RO |
| V7 | Spiegel erreichbar (`rclone` Fail-Closed) | — |
| V8 | `db_artefact_upload` ok + Digest-Match | RO für Digest |

Plus: `LOCKED=1`, kein vorab-`RUN.RETIRED`, Archiv-Name frei.  
`require_manifest_match=True` für Paket-Retire.

---

## 3. `--skip-e1-upload-gate` (Anforderung 3)

| Kontext | Verhalten |
|---|---|
| Scratch | erlaubt (Test) |
| Paket / `--allow-package-retire` | **immer Refuse** |

---

## 4. Retire-Reihenfolge — Intent/Confirm wie `issue-token` (Prüferpunkt 2)

Freigebende Transition; Spiegel **vor** Mutation:

1. Vorbedingungen V1–V8 (+ L4-Tipp §6)  
2. `before_sha = sha256(lock)`; Archiv-Pfad festlegen  
3. **Intent:** Audit-Append `retire_run_lock_intent` → **sofort spiegeln**  
   - Spiegel scheitert → **Stop**; Lock unberührt  
4. `lock.rename(archive)`  
5. `RUN.RETIRED` mit `O_EXCL` schreiben  
6. **Confirm:** Audit-Append `retire_run_lock_confirm` → spiegeln  
   - Spiegel/Confirm scheitert → Fehler melden; Lock already absent+Marker; `status` zeigt offene Intent-ohne-Confirm (wie abort-Paare); Undo via `restore-run-lock`

Crash zwischen 4 und 5: absent ohne Marker → Runner 75. Restore heilt (§5).

---

## 5. `restore-run-lock` (Prüferpunkt 3)

### Zustandsmatrix

| Zustand | Heilung |
|---|---|
| Lock absent, Marker da, Archiv da | **Normal-Restore:** erst Marker weg, dann Archiv→`RUN.lock` |
| Lock absent, Marker fehlt, Archiv da | Halbzustand: volles Restore (Archiv→Lock); kein Marker nötig bzw. nachziehen vermieden |
| **Lock da und Marker da** | `retire` refuse (Marker); normales Restore refuse (R1). **Eigener Heilpfad:** auditiertes Entfernen nur des Markers (`restore_run_lock_clear_marker` oder `restore-run-lock --clear-stale-marker`), Lock bleibt `LOCKED=1` |
| Mehrere Archive, kein Marker | Refuse; `--archive <path>` Pflicht |

### R3

Soll-SHA primär aus dem letzten erfolgreichen `retire_run_lock_confirm` (oder Intent+Confirm-Paar) im Audit; Marker nur Hilfszeiger. Archiv-Bytes müssen `before_sha256` matchen.

### Ablauf Normal-Restore (Reihenfolge umgedreht)

1. L4-Tipp; V/R Quiet; offene Tokens → **widerrufen** (auditiert)  
2. Intent `restore_run_lock_intent` → spiegeln (Fail → Stop)  
3. **Marker unlink zuerst**  
4. `archive.rename(RUN.lock)`  
5. Confirm → spiegeln  

Absturz zwischen 3 und 4 → „Lock fehlt, Marker fehlt, Archiv da“ → von Halbzustands-Regel geheilt (voller Restore ohne Marker).

### Offene Tokens

Vor Rename zurück: alle `consumed_at IS NULL AND revoked_at IS NULL` → `revoked_at=now`, auditiert (`restore_run_lock_revoke_open`).

---

## 6. L4 — **Entscheidung im Entwurf: ja, Standard** (Prüferpunkt 4)

**Bindend für diesen Schnitt** (kein Env-Opt-in, kein „später“):

Getippte Bestätigung ist **Standard** vor:

| Aktion | Exakte Eingabe (Soll) |
|---|---|
| `retire-run-lock --allow-package-retire` | `RETIRE_PACKAGE_LOCK` |
| `restore-run-lock` (Paket / clear-stale-marker) | `RESTORE_PACKAGE_LOCK` |
| jedes Kommando mit `--allow-live-db` | `ALLOW_LIVE_DB` |
| `abort-run` | `ABORT_RUN_<run_id>` |

- Nicht-TTY → Refuse (außer Suite).  
- Test-Hook `--i-am-a-test` (falls eingeführt): **verweigert** auf live-markierten Pfaden **und** am Paket-Lock; nur Scratch-Temp ohne Live-Marker.  
- Kein `CONTROL_PLANE_TYPED_CONFIRM=1` als Schutz — Umgehen durch Nicht-Setzen ist damit ausgeschlossen.

Operator-Ratifikation dieser L4-Festlegung = Teil der Freigabe „Freeze aufheben / Patch anwenden“.

---

## 7. Runner unverändert (Anforderung 7)

Nach Retire: Default-Pfad, kein `--run-lock`, Marker → Lease; `--lease-token-file` auf LIVE. M2 bleibt. `shadow_runner.py` unverändert.

**Notbremse (Runbook):** Ein von Hand angelegtes `ops/RUN.lock` mit `LOCKED=1` (ohne Retire-Undo) sperrt den Runner erneut — gewollt, dokumentieren.

**E-4:** Start **von Hand im Vordergrund**, nicht launchd; innerhalb der Token-TTL.

---

## 8. E-Reihenfolge (Plan = Code)

| Schritt | Name | Lock | Hinweis |
|---|---|---|---|
| **E-0** | Vorprüfung | `LOCKED=1` | nur RO-`status`/Checks; **kein** SHA-Drift der LIVE_DB |
| **E-1** | LIVE migrate | `LOCKED=1` | einzig WAL-Umschaltung; Off-Host-Artefakt + `db_artefact_upload` |
| **E-2** | Paket-Retire | → Marker | Intent-Spiegel vor Rename; Confirm danach |
| **E-3** | Token | Marker | `--lease-token-file` |
| **E-4** | Lauf | Marker | Vordergrund, kein launchd, TTL beachten |
| **E-5** | Nachprüfung | Marker | RO `post-run-check` + `verify-mirror` |

### Rückweg nach gescheiterter Migration (E-1)

Schreibzugriff auf LIVE → **eigenes auditiertes Kommando** (Soll-Name: `gatectl restore-db-artefact`) oder Runbook-Schritt mit:

1. Snapshot-SHA vorher/artefakt vergleichen  
2. Datei ersetzen nur nach getippter Bestätigung + `--allow-live-db`  
3. Post: `journal_mode`/integrity/uv wie Pre-Migrate; Audit-Eintrag  

Nicht stilles `cp` ohne Gate. Details im Patch-PR; Schnitt muss den Hook mindestens stubben oder Runbook+Test für SHA-Vergleich liefern.

Abbruch nach E-2 → `restore-run-lock`.  

---

## 9. Abnahme-Harness + Negativproben

Aufbau wie Rev. A (Temp-Paketkopie + live-markierter Data-Root). Prod unberührt.

### Zusätzliche Negativproben (Prüferpunkt 5)

| Probe | Erwartung |
|---|---|
| `status` auf v9 (live-markiert, `--allow-live-db`) | meldet `not_migrated`; **Datei-SHA unverändert**; kein `-wal` |
| Retire bei nicht erreichbarem Spiegel (V7 / Intent-Spiegel) | Lock unberührt `LOCKED=1` |
| Retire ohne `--allow-live-db` (LIVE-DB-Pfad) | Refuse (RO-Vorbedingungen) |
| `--i-am-a-test` auf Paket-Lock oder LIVE-Pfad | Refuse |
| Restore bei Lock+Marker | nur clear-stale-marker-Pfad; nicht blindes Rename |
| Mehrere Archive ohne `--archive` | Refuse |

Weitere Proben aus Rev. A bleiben.

---

## 10. Testplan (nach Freigabe)

- RO-`status` v9: SHA stabil, kein WAL, kein Crash  
- Paket-Retire Intent-Spiegel-Fail → Lock bleibt  
- Paket-Retire Positiv: Intent+Confirm gespiegelt  
- Restore: Marker-first; Lock+Marker-Heilung; Token-Revoke  
- L4: ohne Tipp → Refuse; mit Tipp → ok (pty/fixture)  
- `--i-am-a-test` auf LIVE/Paket refuse  
- Gated E-0…E-5 Harness (`CONTROL_PLANE_CANARY=1`)

---

## 11. Explizit nicht

- Prod-LIVE / Prod-`ops/RUN.lock` in Abnahme mutieren  
- Lauf vor Retire  
- Env-opt-in als einziger L4-Schutz  
- WAL bei lesenden Kommandos  
- Patch anwenden ohne Operator-Freigabe Freeze-Lift  

---

## 12. Freigabe-Checkliste

- [x] Prüferpunkte 1–5 in Entwurf Rev. B  
- [x] L4 im Entwurf: **ja, getippte Bestätigung = Standard**  
- [x] Operator: Entwurf Rev. B + L4 ratifiziert (AUFGABE Apply)  
- [x] Patch angewendet (WT); Prod-LIVE/Lock unberührt  
- [x] Suite 72 passed / 4 skipped + `/tmp/abnahme_revb_*` ALL_PASS  
- [x] Plan E-0…E-5 Runbook (Rev. 12.5)  

**Ende Rev. B — angewendet; E-1 Live-Cutover weiter Operator-Freigabe.**
