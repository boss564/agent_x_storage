# SCHWARM_STATUS.md — Single Source of Truth (SSOT)

> **Dokument:** Agent X Schwarm-Ledger  
> **Version:** 0.2.9  
> **Stand:** 2026-09-26 (Messung Host)  
> **Verantwortlich:** Project Lead (System-Architekt)  
> **Charter (bindend):** `diagnostic_only=true` · `live_execution=false` · `order_send=false` · `not_investment_advice=true` · `DEFENSIVE_CAUSAL_GROUNDING`  
> **Status-Legende:** 🟢 produktiv (belegt) · 🟡 im Aufbau / teilweise belegt · 🔴 blockiert · ⚪ geplant · ⬛ nicht im Baum / unverifizierbar  
> **SSOT-Verankerung:** wird mit diesem Commit getrackt; Hash → Buchung in **0.3.0**.  
> **Checker:** kern-fertig belegt (`--self-test` → 5/5) — **Fußnote: Evidenz Mac-Arbeitsstand / Hub uncommitted**; Host-Snapshot `5a5985c5` kennt `--self-test` nicht. **Nicht** host-verifiziert (§7).  
> **Maßgeblich:** nur `agent_x_storage/SCHWARM_STATUS.md`. **Keine** Spiegel-Kopien.  
> **Zero-Trust (SSOT):** Jede Änderung braucht Messbeleg (Fixture/Protokoll/`rev-parse`) **und** wird erst nach Commit-Anker verbindlich — untracked SSOT ist Entwurf.  
> **Nächster Prüfpunkt:** Wächter-Lauf **2026-09-27 03:45 UTC** → Ziel **0.3.0** (nach SSOT-Commit).

---

## 1. System-Übersicht

Drei getrennte Codebasen — nicht vermischen:

```
┌──────────────────────────────────────────────────────────────┐
│  AGENT X (Hub) — Repo agent_x_storage                        │
│  Git-Anker: 81502319 (Host 26.09.) · 5a5985c5 historisch     │
│  DB: Redis/Neo4j/NATS/Anvil (Compose) — FalkorDB ≠ Hub       │
│  News-Ingest: services/news_agent/  schema news_agent_multi/v1.3 │
└──────────────┬───────────────────────────────┬───────────────┘
               │                               │
    ┌──────────▼──────────┐         ┌──────────▼──────────────────┐
    │  PolySentinel       │         │  newsagent (Host+Bare)      │
    │  ⬛ nicht im Baum   │         │  Ist-Anker: eec4c50         │
    │  Anker d567966      │         │  Kette: d2990d3→3b8ada8→…  │
    │  unbelegbar hier    │         │  SCHEMA 1.1.0 · Wächter 🟢  │
    └─────────────────────┘         │  Falkor: B4 offen           │
                                    └─────────────────────────────┘
```

**Regel:** Schema `news_agent_multi/v1.3` = Hub (`services/news_agent/`). Host-Ist-Anker `3b8ada8` + Exit **0/1/2/3** = newsagent. `d2990d3` = historischer Ticket-/Freigabe-Referenz-Anker (Ancestor), **nicht** Verifikations-Ist.

### 1.1 Claims-vs-Beleg (Abgrenzung)

Ein Claim ist erst **belegt**, wenn ein reproduzierbarer Nachweis existiert (Testprotokoll, Live-Lauf, Commit-Verifikation). Alles ohne Nachweis wird hier nicht als Fakt geführt.

| Claim | Status | Begründung |
|---|---|---|
| PolySentinel Preflight 10/10 / [OPS] verifiziert | ❌ **abgelehnt** | Modul fehlt im Baum; kein Protokoll. W2 höchstens *definiert*, nicht *erfüllt*. |
| NewsAgent Exit-Kontrakt nur 0/1/2 (Retry auf 1) | ❌ **abgelehnt** | Code: **0/1/2/3**; `1` = BEFUND (kein stiller Retry). Host-Exit-Nachweis ausstehend (§7 B2). |
| Agent X Ingest v1.3 **aktiv** | ❌ **abgelehnt** als Laufzeit-Fakt | Schema/Code + Anker `5a5985c5` ✓; „aktiv“ braucht Host-Live-Protokoll (B1–B2). |
| Checker `check_claude_md.py` kern-fertig | ✅ **belegt** | `--self-test` 5/5 (2 Gegenproben + 3 Positivfälle), ohne `CLAUDE.md`. |
| Checker / Stack host-verifiziert | ❌ **abgelehnt** | B1–B3 Host-Messungen ✅; `--self-test` auf Host fehlt (Track 12); B4 offen. |

---

## 2. Modul-Status

### 2.1 Agent X — Orchestrator / Daten-Hub

| Feld | Wert |
|---|---|
| Repo | `agent_x_storage` (dieses Arbeitsverzeichnis) |
| Git-Anker (Host-Ist) | `81502319` — gemessen 2026-09-26 ✓ |
| Git-Anker (historisch) | `5a5985c5` — Safe-Snapshot 2026-09-10 |
| Deployment | Hetzner `/root/agent_x_storage` (Safe-Snapshot-Pfad); Hub ≠ FalkorDB |
| Datenbank (Hub) | Compose-Stack (Redis, Neo4j, NATS, Anvil, …). **FalkorDB gehört zu `newsagent/`**, nicht zum Hub — kein Hub-Schema (Scope v0.2.2) |
| News-Ingest (Hub) | `services/news_agent/` → flache JSONL-Rows `schema: news_agent_multi/v1.3` |
| Status | 🟡 Snapshot + Schema belegt; Laufzeit „Ingest aktiv“ erst nach Host-Live-Protokoll (§7) |
| Offene Punkte | FalkorDB nur unter NewsAgent-Scope (`newsagent/` → B4); Hub-Ingest-Aktivität → §7 B1–B2 |

### 2.2 PolySentinel — Polymarket-Monitor

| Feld | Wert |
|---|---|
| Funktion (Anspruch) | CLOB WebSocket, Vol-Spikes, Telegram-Alerts |
| Code im verbundenen Ordner | **fehlt** — kein Repo, kein Modul, kein Pfad |
| Git-Anker `d567966` | ⬛ **nicht verifizierbar** in diesem Baum |
| Fail-Closed / Preflight 10/10 / Reconnect-Grenze / [OPS] | ⬛ **unbelegt** (kein Code) |
| Status | ⬛ nicht im Baum — Claims (10/10, OPS, 🟢 produktiv) **unbelegt → §1.1** |

### 2.3a Hub-News — `services/news_agent/` (Agent X)

| Feld | Wert |
|---|---|
| Funktion | Multi-Feed RSS/Announcement/Social/Regulatory → JSONL |
| Schema | `news_agent_multi/v1.3` (`services/news_agent/models.py`, `SCHEMA`) |
| Pflicht | `REQUIRED_SCHEMA = "news_agent_multi/v1.3"` in M2-Skripten — **kein v1.2-Fallback** |
| Lag-Felder | `detection_lag` **und** `detection_lag_sec` (gleicher Wert) |
| Charter-Felder je Row | `diagnostic_only=true`, `live_execution=false`, `order_send=false`, `not_investment_advice=true` |
| Envelope `schema_version` / `agent_id` / `trace_id` / `payload` | **nicht implementiert** — Entwurf verworfen (§3) |
| Git | Teil von Hub-Anker `5a5985c5` (kein eigener Nested-Commit) |
| Status | 🟡 Code + Schema belegt; Host-Aktivität → §7 |

### 2.3b newsagent / Wächter — nested Repo `newsagent/`

| Feld | Wert |
|---|---|
| Pfad | `newsagent/` (eigenes Git) |
| Remote | `root@65.108.246.89:/root/newsagent-bare.git` |
| Git-Anker (Ticket-Ref) | `d2990d3` — Freigabe-Mindestziel / Ancestor (historisch) |
| Git-Anker (Host-Ist) | `eec4c50` — **verbindlicher Verifikations-Anker** (2026-09-26) ✅ |
| Anker-Kette | `d2990d3` → `3b8ada8` → `eec4c50` (Ancestor-Logik analog B3) |
| Format-Vertrag | `SCHEMA_VERSION = "1.1.0"` — **≠** Hub v1.3 |
| Aktive DB (Code-Annahme) | **Neo4j** + SQLite `drafts.db` |
| FalkorDB | unter `newsagent/` gebaut/getestet; **Deploy-Entscheidung offen** (§7 B4) |
| Preflight | **3** Checks (Telegram, Neo4j, LLM) — nicht 10/10 |
| Exit-Kontrakt | **0 / 1 / 2 / 3** (`waechter_lauf.sh`) |
| Laufzeit-Status | 🟡 Timer aktiv; 03:45-Läufe Exit **3** (skip); Grün nur 26.09. 11:11 Exit **0** |

### 2.4 Geplante Satelliten

| Modul | Zweck | Status | Priorität | Charter |
|---|---|---|---|---|
| Trading Execution | Order-Routing | ⚪ geplant | hoch | **gesperrt** (`order_send=false`) |
| Risiko-Management | Limits, Drawdown-Brakes | ⚪ geplant | hoch | nur Shadow bis Charter-Änderung |
| Sentiment-Agent | Sozial-/Markt-Aggregation | ⚪ geplant | mittel | diagnostic_only |

---

## 3. Schnittstellen — was der Code wirklich schreibt

### 3.1 Hub-News Row (IST — `news_agent_multi/v1.3`)

Flache Row, kein Envelope. Pflicht/Charter aus `NewsItem.to_dict()`:

```json
{
  "schema": "news_agent_multi/v1.3",
  "timestamp": "ISO-8601",
  "published_at": "ISO-8601|null",
  "source_type": "rss|announcement|social|regulatory",
  "source_name": "...",
  "title": "...",
  "url": "...",
  "target_assets": [],
  "entities": {},
  "cross_chain_impact": {},
  "sentiment_score": 0.0,
  "impact_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "summary": "",
  "item_id": "",
  "feed_error": "",
  "detection_lag": 0,
  "detection_lag_sec": 0,
  "diagnostic_only": true,
  "live_execution": false,
  "order_send": false,
  "not_investment_advice": true
}
```

**Verworfen (0.1.0-Entwurf):** Envelope mit `schema_version` / `agent_id` / `trace_id` / `payload`.

### 3.2 newsagent Wächter — Exit-Kontrakt (`waechter_lauf.sh`)

| Code | Bedeutung | Ops-Folge |
|---|---|---|
| `0` | alles geprüft, kein Befund | OK |
| `1` | mindestens ein **BEFUND** | Alert — **kein stiller Retry** |
| `2` | **BLIND** oder **ALARM** | ungemessen; stärker als Befund |
| `3` | alle Wächter übersprungen / Teil-Skip (`skip`≥1 und nichts Voll-Grün) | **kontrakt-konform** (bereits 0/1/2/3); Ops: `[OPS]`-WARN, **kein** CRIT — B5 |

**B5-Entscheidung (0.2.9):** Exit `3` liegt **nicht** außerhalb des Kontrakts. Die Formulierung „außerhalb 0/1/2“ ist abgelehnt (§1.1 / False Claim). Semantik bleibt: Skip/Teilprüfung → WARN. Optional später Offsite-Mount fixen, damit 03:45 eher Exit `0` liefert — das ist Betrieb, keine Kontrakt-Lücke.

### 3.3 newsagent Format-Vertrag

`schema_version: "1.1.0"` — getrennt von Hub `schema: news_agent_multi/v1.3`.

### 3.4 Alert-Kanal

- `[OPS]` = prioritärer Ops-Kanal. PolySentinel-[OPS]-Pfad: ⬛ unbelegt.
- **CRIT-Regel:** nur Exits **außerhalb 0/1/2/3** (oder unkontrollierter Abbruch). Exit `3` = WARN, nicht CRIT.

---

## 4. Operational Safety — Wächter-Regeln

| # | Regel | Verantwortlich | Status |
|---|---|---|---|
| W1 | Reconnect / Fail-Closed | PolySentinel | ⬛ |
| W2 | Preflight | newsagent: 3 Checks | 🟡 Code; Host offen |
| W3 | Exit 0/1/2/3 | `waechter_lauf.sh` | 🟢 Code |
| W4 | Systemd-Units | newsagent Repo + Host | 🟢 Wächter-timer enabled+active (0.2.8) |
| W5 | Credentials / Rotation | alle | 🟡 |
| W6 | Charter no order-send | News-Rows + Inventar | 🟢 |

### W4 — Units im Repo (nicht Host-Beweis)

| Unit | Pfad |
|---|---|
| `newsagent-waechter.service` / `.timer` | `deploy/systemd/` |
| `newsagent-takt.service` / `.timer` | `deploy/` |
| `newsagent-backup.service` / `.timer` (+ `-failure`) | `deploy/systemd/` |
| `newsagent-digest.timer` | `deploy/systemd/` |
| `newsagent-restore-drill.service` / `.timer` (+ `-failure`) | `deploy/systemd/` |
| `newsagent-security.timer` | `deploy/systemd/` |
| `newsagent-dev.timer` | `deploy/systemd/` |
| `rclone-mount-gdrive.service` | `deploy/systemd/` |

Host-Fixtures: `deploy/hetzner/fixtures/` (B1/B2b/Drift). Wächter-Unit auf Host: enabled+active (B3).

---

## 5. Audit-Pfad & Git-Anker

| Anker | Modul | Zweck | Stand |
|---|---|---|---|
| `81502319` | Agent X Hub (Host) | **Ist** 2026-09-26 | ✓ gemessen |
| `5a5985c5` | Agent X Hub | historisch Safe-Snapshot | abgelöst als Ist |
| `eec4c50` | newsagent Host+Bare | **Ist-Deploy** 2026-09-26 | ✓ sync origin |
| `3b8ada8` | newsagent | Zwischen-Ist (B3) | historisch in Kette |
| `d2990d3` | newsagent | Ticket-/Freigabe-Ref (Ancestor) | ✓ in Kette |
| `d567966` | PolySentinel | Monitor | ⬛ fehlt |

**Checker-Kern (Zero-Trust, unabhängig vom Repo-State der Doku):**

```bash
python3 scripts/check_claude_md.py --self-test
# Gegenproben: 277 ohne Mark → 243; 243 agents total → 277; Positivfälle; 5/5
```

Gegenproben sind der stärkere Teil (zeigt: nicht alles wird durchgewinkt). Das erfüllt den Zero-Trust-Anspruch **für die Zähllogik**. Der Checker gilt im Ledger **nicht** als host-verifiziert, solange §7-Blocker offen.

```bash
git -C …/agent_x_storage log -1 --oneline 5a5985c5
git -C …/agent_x_storage/newsagent log -1 --oneline d2990d3
```

---

## 6. Änderungslog (Ledger)

| Datum | Version | Änderung | Autor |
|---|---|---|---|
| 2026-09-20 | 0.1.0 | Initiales Ledger-Draft | Kimi |
| 2026-09-20 | 0.1.1 | Checker-Mutationsnachweis (`--self-test` 5/5) | Team |
| 2026-09-20 | 0.2.0 | Trennung Module; IST-Row; Exit 0/1/2/3; Charter; PolySentinel ⬛ | Auto / Prüfer |
| 2026-09-20 | 0.2.1 | Claims-vs-Beleg; Host-Blocker B1→B4; B4 = Entscheidung | Auto / Prüfer |
| 2026-09-20 | 0.2.2 | FalkorDB-Scope explizit `newsagent/` (kein Hub-Schema); Stale-0.1.x-Körper (Envelope/Exit-0/1/2/§7-alt) verworfen | Team / Auto |
| 2026-09-20 | 0.2.3 | **Repo-only SSOT** — Downloads-/Arbeitskopie-Spiegel eingestellt; eine Datei, eine Wahrheit (§1.1 gegen False-Claims auf Stale-Körper) | Team / Auto |
| 2026-09-20 | 0.2.4 | **B1 Host-Fixtures** geliefert (`host_units_2026-09-20T1036Z.json`); Wächter not-found; backup+m2 failed; newsagent Host `f0b1b41` ≠ `d2990d3` | Auto |
| 2026-09-20 | 0.2.5 | Drift aufgelöst als Befund: `d2990d3` lokal-only (unpushed); Host `f0b1b41` / Bare `c2ff340`; B3 gesperrt; B2b+Drift-Protokolle; B2a Host-Checker exit=1; backup OnFailure=[ERWARTET] | Auto |
| 2026-09-20 | 0.2.6 | Regel (a)/(b): `d2990d3` = Wächter-Safety → **(a)**; (b) verworfen; Anker bleibt Soll-Deploy; Host-Ist `f0b1b41`; Bare `c2ff340`; Hub `--self-test` separat (uncommitted) | Auto |
| 2026-09-20 | 0.2.7 | Kalender: Deploy≠Anker bis 21.09. Freigabe-(a); B1 not-found = undeployter Safety; Hub `--self-test` Mac-Fußnote + eigener Commit-Track; B3→B4 Reihenfolge fix | Auto / Team |
| 2026-09-23 | 0.2.8 | **B3 ✅**: Host/Bare `3b8ada8`; `d2990d3` Ancestor; Wächter-timer enabled+active; Host-Ist-Anker fortgeschrieben; B1 not-found behoben; nächster: B4 | Auto |
| 2026-09-23 | 0.2.8b | Baseline-Konsolidierung: Ist-Anker `3b8ada8` vs Ticket-Ref `d2990d3`; B1 geschlossen; Baustellen B4/Track12/m2; Verträge = Code-IST (Exit 0/1/2/3, kein PolySentinel-10/10); Zero-Trust-SSOT-Regel; Prüfpunkt 24.09. 03:45 → 0.2.9 | Auto / Team |
| 2026-09-23 | 0.2.8c | Downloads-Rewrite (PolySentinel 🟢/10/10, Exit 0/1/2, Envelope, Falkor-am-Hub) **abgelehnt** — §1.1; Repo bleibt einzige SSOT; Spiegel gelöscht | Auto |
| 2026-09-26 | 0.2.9 | Host-Messung: Hub `81502319`, newsagent `eec4c50`; 03:45 Exit 3 = WARN (kein Grün); Grün 11:11 Exit 0; m2 🟡; PolySentinel ⬛; **B5 geschlossen** (Exit 3 kontrakt-konform; False Claim „außerhalb 0/1/2“ korrigiert); CRIT nur außerhalb 0/1/2/3; Offsite→Exit0 optional Betrieb; SSOT-Commit-Go → Hash in 0.3.0; Check 27.09. 03:45 | Auto |

---

## 7. Baustellen-Tracker & Verifikation (0.2.9)

### Zero-Trust für dieses Dokument
Jede SSOT-Änderung: (1) Messbeleg, (2) Ledger-Zeile, (3) **Commit-Anker** — ohne (3) bleibt die Datei Entwurf. Track-12/SSOT-Commit → Ziel **0.3.0**.

### Geschlossen / gemessen

| ID | Ergebnis | Beleg |
|---|---|---|
| **B1** | geschlossen (not-found = undeployter Safety) | `fixtures/host_units_*` |
| **B2b** | backup OnFailure; m2 damals EXEC | `fixtures/b2b_*` |
| **B3** | Ist damals `3b8ada8` | 2026-09-23 |
| **B5** | ✅ geschlossen: Exit `3` kontrakt-konform (0/1/2/3); WARN/OnFailure ok, kein CRIT; False Claim „außerhalb 0/1/2“ korrigiert | Code `waechter_lauf.sh` + §3.2; Messung 24–26.09. 03:45 |
| Wächter 03:45 | Exit **3**, `skip 1` (Offsite) — **kein Grün** | Journal 24/25/26 03:45 UTC |
| Wächter Grün | Exit **0**, `geprüft 2 · skip 0` | Journal **2026-09-26 11:11 UTC** |
| Host-Anker | Hub `81502319` · newsagent `eec4c50` | `rev-parse` 2026-09-26T16:39Z |

### 🔴 / 🟡 Offen (Priorität)

| Prio | Track | Status | Nächster Schritt |
|---|---|---|---|
| 1 | **B4** Falkor | 🔴 | Ledger-Entscheidung (a) Deploy oder (b) zurückstellen |
| 2 | **SSOT committen** | 🟡 Go erteilt 26.09. — Hash → **0.3.0** | `.gitignore`-Ausnahme aufheben; Track 12 (`--self-test`) weiter parallel |
| 3 | **m2-live-monitor** | 🟡 wirkt behoben | Beleg 26.09. 16:00 success / Median-Lag ~36 min; beobachten bis 27.09. |
| 4 | Offsite-Skip bei 03:45 | 🟡 Betrieb | optional Mount/Pfad, damit Timer Exit 0 statt 3 — kein Kontrakt-Change |
| 5 | Wächter-Check | gebucht | **2026-09-27 03:45 UTC** → 0.3.0 |
| — | PolySentinel | ⬛ | keine frische Messung — nicht als aktiv führen |


### Verbindliche Schnittstellen (Code-IST — nicht Briefing)

| Vertrag | Quelle | Nicht |
|---|---|---|
| Hub-News Row `news_agent_multi/v1.3` + `detection_lag`/`_sec` + Charter-Flags | `services/news_agent/models.py` | Envelope `schema_version`/`trace_id`/`payload` |
| Exit **0/1/2/3** (1=BEFUND, kein Retry; 2=BLIND/ALARM; 3=Skip) | `newsagent/deploy/waechter_lauf.sh` | „0/1/2 + Retry auf 1“ |
| newsagent Preflight | 3 Checks (Telegram/Neo4j/LLM) | PolySentinel „10/10“ |
| `[OPS]` | Ops-Präfix; backup OnFailure-Pfad belegt | PolySentinel-[OPS] (⬛ Modul fehlt) |
| PolySentinel Fail-Closed / 10/10 | — | **kein** verbindlicher Vertrag (§1.1 abgelehnt) |

### Parallel (nicht blockierend)

- ⬛ PolySentinel-Code oder Anker `d567966` streichen  
- ⬜ Hub-Anker: Ist `81502319` vs. lokale Branches abgleichen  
- ⬜ `schemas/*.json` nur für IST-Row (§3.1)  
- ⬜ Trading/Risiko Charter-gesperrt  

### Archiv (historische Zwischenstände 0.2.4–0.2.7)

Kalender „Deploy≠Anker“, Freigabe-Kette 21.09. und Drift-Tabellen sind **erledigt/abgelöst** durch B3 @ `3b8ada8`. Details bleiben in §6 Changelog und unter `deploy/hetzner/fixtures/`.
