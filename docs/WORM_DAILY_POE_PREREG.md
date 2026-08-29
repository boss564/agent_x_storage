# Daily WORM Proof of Existence (PoE) — Pre-Reg

**Status:** DRAFT (2026-08-29) · **kein Code vor FREIGABE**  
**Scope:** Ops / Compliance-Fernsicherung · ergänzt lokale GoBD-WORM-Hashketten, ersetzt sie nicht  
**Nicht Scope:** Cross-Venue · Paper-Exit / Edges / k · Signal-Gates · Z3-Hash-„Beweise“ · 9-Agenten-Schwarm · Live-Trading

**Parent / Bezug:** `prototypes/raas_paper_trading/worm_log.py` (`hash = SHA256(prev_hash ‖ json.dumps(row))`) · GoBD-WORM-Muster im B2G-Stack · getrennt von [`CROSS_VENUE_FEED_VALIDATION_PREREG.md`](CROSS_VENUE_FEED_VALIDATION_PREREG.md)

---

## 0. Verworfener Entwurf (explizit)

| Verworfen | Warum |
|-----------|--------|
| Z3 als Prüfer der SHA-256-Kettenfortsetzung / „Pre-Image-Resistance“ | Fake-Constraint (`curr != prev`); echte Prüfung ist `hashlib`, nicht SMT |
| 9 Agenten + Blackboard | Over-Engineering; Timer + Pipeline reicht |
| Claim „unfälschbar trotz totalem lokalen Root“ | Root kann bis zum nächsten erfolgreichen Remote-Anchor noch signieren; Claim = Zustand *zum Anchor-Zeitpunkt* |
| Signal-BLOCK / Fail-Closed gegen Paper-Ticks | PoE ist Diagnose/Ops; Exit-FSM unberührt |
| Feste Pfade `/var/log/worm`, `subprocess(..., shell=True)` | Env-Injektion + argv-Listen |

---

## 1. Claim (prüfbar)

> Täglich (Default **23:59 UTC**, konfigurierbar) wird der **Tip-Hash** der lokalen append-only WORM-Datei (SHA-256-Kette wie in `PaperWormLog`) zusammen mit dem **zuletzt erfolgreich remote verankerten Tip** und Metadaten als Payload gebildet, mit einem **HSM-/Token-gebundenen GPG-Schlüssel** detached signiert, als **signed Git-Tag** remote gepusht **und** als **S3-Objekt mit Object Lock COMPLIANCE** abgelegt. Unmittelbar danach: Read-Back beider Ziele, GPG-Verify, Hash-Match gegen lokal. Erfolg → Tip als „last good remote“ persistieren. Misserfolg → Retry mit Backoff, nach N Versuchen Alarm; **kein** neuer „last good“, alte Remote-Anker bleiben gültig.

**Kein Claim:** Gerichtsfeste Allaussage ohne Key-Ceremony/Runbook; Schutz vor Root vor dem ersten erfolgreichen Tag des Tages; Ersetzung der lokalen WORM-Zeilenprüfung.

---

## 2. Hash-Semantik (normativ)

Lokale Kette (bereits implementiert):

```text
row_n.hash = SHA256( row_{n-1}.hash  ‖  canonical_json(row_n without hash) )
tip        = hash der letzten Zeile der WORM-Datei
```

Täglicher PoE:

```text
H_tip          = tip der WORM zum Job-Start (read tip only; keine Preise nötig)
H_prev_remote  = last successfully verified remote tip (State-Datei / Env-Pfad)
```

**Konsistenz vor Push (Pflicht, Crypto-Code, kein Z3):**

1. `H_tip` ist der `hash` der letzten JSONL-Zeile.  
2. Optional stark (empfohlen für Audit-Fenster ≤ 24 h): Replay von `H_prev_remote` → `H_tip` über die Zwischenzeilen; bei Bruch → **ABORT + Alarm** (kein Push).  
3. **Nicht** erfinden: `SHA256(H_prev_remote ‖ H_tip)` als Kettenersatz — das ist keine Fortsetzung der bestehenden WORM-Semantik.

Payload (Minimum, sort_keys JSON):

```text
{ "date_utc", "worm_path_id", "tip_hash", "prev_remote_tip", "seq", "system_id" }
```

Keine Kursfelder; Charter-Stempel analog Paper (`live_execution=false` wo relevant).

---

## 3. Pipeline (5 Schritte, keine Agenten-Metapher)

| # | Schritt | Fail-Closed |
|---|---------|-------------|
| 1 | Tip lesen + optional Replay seit `prev_remote_tip` | ABORT |
| 2 | Payload bauen + GPG detached sign (HSM/Agent) | ABORT |
| 3 | Signed Git-Tag (`git tag -s` via argv-Liste) + atomic push | Retry |
| 4 | S3 put + Object Lock COMPLIANCE + Retention (Freeze: z. B. 10 y) | Retry |
| 5 | Read-Back Git + S3, GPG verify, `tip_hash` match | sonst kein `save_previous` |

Orchestrierung: `systemd`-Timer / Cron **oder** ein Prozess; Retry/Alarm = dieselbe Pipeline, kein separater „Resilience-Agent“.

---

## 4. Freeze vor Implementierung (nach FREIGABE)

| Parameter | Freeze |
|-----------|--------|
| Schedule | 23:59 UTC (Default) |
| WORM-Quelle | konfigurierbar (`WORM_POE_PATH` / Liste); Start: Paper-WORM Live-Shadow-Pfad |
| Git remote | privates Repo, signed tags only |
| GPG key | HSM/Token; Key-ID in Env; Ceremony im Ops-Runbook |
| S3 | Bucket mit Object Lock enabled; Mode COMPLIANCE; Retain-Until Freeze |
| Retries | N=3, exponential backoff; dann PagerDuty/Webhook |
| Z3 | **nicht** in dieser Pipeline (optional später nur JSON-Schema — eigenes Amendment) |

---

## 5. Hypothesen (schlank)

### H0 — Messbarkeit

In Fenster W_poe (≥ 7 Kalendertage): ≥ 6 erfolgreiche Dual-Verifies (Git∧S3) **oder** dokumentierter FAIL mit Alarm-Nachweis. Sonst unbrauchbar.

### H1 — Dual-Target-Konsistenz (deskriptiv + Gate)

Bei jedem Erfolg: `tip_hash` lokal = Payload in Git-Tag-Message/Objekt = S3-Body. Abweichung → FAIL (kein `last good` Update).

### H2 — Lock-Retention (Ops-Probe)

Einmalige Probe: Delete/Overwrite-Versuch am gelockten Objekt → erwartet AccessDenied / Retention enforced (dokumentiert, nicht täglich).

Kein Retuning der Retention nach H0-Blick ohne Amendment.

---

## 6. Abgrenzung

| | Lokale WORM | Daily PoE |
|--|-------------|-----------|
| Zweck | Zeilenintegrität / GoBD append-only | Tip zu T remote beweisen |
| Frequenz | jeder Append | täglich |
| Targets | Disk / PVC | Git + S3 Lock |
| Cross-Venue / Exit | unberührt | unberührt |

---

## 7. Implementierungs-Checkliste (nach FREIGABE)

| # | Inhalt |
|---|--------|
| 1 | Modul `scripts/worm_daily_poe.py` (oder `ops/worm_poe/`) — 5 Schritte |
| 2 | Env: Pfade, Key-ID, Bucket, Remote, N-Retries, Webhook |
| 3 | Smoke: Temp-WORM → sign (Test-Key) → mock Git/S3 oder Localstack → verify |
| 4 | Runbook: Key-Ceremony, Bucket-Policy, Tag-Policy, manuelles Recovery |
| 5 | Kein Eingriff in `CROSS_VENUE_*` / Paper-Exit |

**Branch (nach Freigabe):** `feature/worm-daily-poe`

---

## 8. Freigabe-Checkliste (Reviewer)

- [ ] Claim = Dual remote verify(tip) — kein Z3-Hash-Mythos  
- [ ] Hash-Semantik = bestehende `prev_hash ‖ payload` Kette  
- [ ] Keine Agenten-Metapher; keine Signal-Blocks  
- [ ] subprocess argv-Listen; Pfade via Env  
- [ ] Parallel zu Cross-Venue; eigener Deploy  
- [ ] Reviewer-Freigabe → dann Code  

---

## Siehe auch

- [`CROSS_VENUE_FEED_VALIDATION_PREREG.md`](CROSS_VENUE_FEED_VALIDATION_PREREG.md) — getrennter Strang (Konnektivität)  
- `prototypes/raas_paper_trading/worm_log.py` — lokale Kettenformel  
