# SCHWARM_STATUS.md — Single Source of Truth (SSOT)

> Zentrales Ledger für das Agent-X-Ökosystem. Alle Statusangaben hier sind verbindlich.
> Änderungen nur nach verifizierter Messung + Git-Anker.
> **Pflege-Regel:** Kein Audit-Pfad-Abschluss ohne Messbeleg. Key-Rotation schließt nur mit Rotation + Beleg (Datum, Scope, Backup-Nachweis).

---

## 0. Dokument-Metadaten

| Feld | Wert |
|---|---|
| SSOT-Version | **0.3.14** |
| Messstand (Host) | **09.10.2026** Wächter SP16 (Journal-Paste) · `hub_rev=f7e0b294` · Offsite **242** (B-OFF-1 🟠) |
| Buchungsdatum | **09.10.2026** |
| Nächster geplanter Check | Wächter-Timer → **10.10.2026, 03:45 UTC** (Serienpunkt 17 → Schnitt 0.3.15; B-OFF-1 Review; Prüfauftrag Hub-FF) |
| Betriebsstatus | Betrieb läuft. **Serienpunkt 16** · **Exit-0-Serie 13** (SP4–SP16). B8 ✅. Laufzeit-Anker Hub **`f7e0b294`** (gemessen SP16). B-OFF-1 🟠 Offsite 242. Key-Rotation 🔴. Gate 🔴 (B6/B7). Sync 0.3.13 ✅ · 0.3.14 ⏳. |
| Sync-Status | **0.3.13 ✅** — Push + Hub-FF belegt durch SP16 `hub_rev=f7e0b294` (Exit 0). **0.3.14 ⏳** wartet auf Push/Hub-FF (Docs-Tip > `f7e0b294`), Beleg via SP17 `hub_rev=` |

---

## 1. Schwarm-Architektur (Zielbild v1.3)

```
┌─────────────────────────────────────────────┐
│  AGENT X  — Steuerungs-/Daten-Hub           │
│  Hetzner-Deploy · v1.3 Schema · Compose-DB  │
│  (FalkorDB ≠ Hub → newsagent / B4 ⚪)       │
│  SSOT 0.3.14                                │
└───────┬───────────────────┬─────────────────┘
        │                   │
  ┌─────▼─────┐       ┌─────▼──────────┐       ┌──────────────────┐
  │PolySentinel│      │ NewsAgent /    │       │ Weitere geplante │
  │ Polymarket │      │ Wächter        │       │ Satelliten:      │
  │ CLOB WS    │      │ Multi-Feed     │       │ · Trading Exec.  │
  │ Monitor    │      │ Ingestion      │       │ · Risiko-Mgmt    │
  │ Fail-Closed│      │ v1.3 Schema    │       │ · Sentiment      │
  │ 10/10 Pre- │      │ Exit-Kontrakt  │       │                  │
  │ flight     │      │ 0/1/2/3        │       │                  │
  └────────────┘      └────────────────┘       └──────────────────┘
```

> **Ist-Abweichung zum Zielbild:** PolySentinel läuft **ungated** — Fail-Closed-Gate defekt (§2, §3.3, §5.4, §6).

### 1.1 SSOT- und Scope-Regeln (verbindlich)

| Regel | Stand |
|---|---|
| **Maßgeblich-nur-Repo** | Einzige SSOT: `agent_x_storage/SCHWARM_STATUS.md`. Downloads / claude.ai / Chat = **Staging**, nie Ledger. |
| **FalkorDB ≠ Hub** | Graph-Layer → **newsagent** (B4 ⚪). Kein Hub-Schema. |
| **Fixtures repo-getrackt** | Anker **`b97bb551`** ✅ |
| **Daten-Weg (Wächter-Paste)** | **Option 2 = Standard.** |
| **Gemessener Checkout = Anker** | Mit live `hub_rev=`-Logging: **Journal-`hub_rev` am Lauf = Laufzeit-Anker Hub**, unabhängig vom Commit-Typ. Docs/Runtime-Trennung war Messlücke, kein Prinzip. Nachzug ohne Zwischenstopp auf überholten Ständen. |
| **Diff-Lärm-Regel** | Hook-Diff / „hash:FEHLT" = Rauschen; Summary maßgeblich. |
| **Offsite-Trend-Toleranz** | ≈ +4/Lauf; Abweichung **> ±4** = Befund (B-OFF-*). |
| **Zählweise (ab 0.3.10)** | **Serienpunkt (SPn)** = laufende Nummer des Wächter-Laufs seit SP1. **Exit-0-Serie** = Anzahl aufeinanderfolgender Exit-0-Läufe (seit SP4). Bis 0.3.9 vermischt („Serie = 11“ meinte SP11, nicht 11 Exit-0). |
| **Exit-0-Serie vs. Offsite-Befund** | Serie zählt `ExecMainStatus=0` + Hook/Zähler sauber + keine `[OPS]`. Offsite-Einbruch = Vollständigkeits-Befund, **kein** automatischer Serienbruch. |

---

## 2. Modul-Status

| Modul | Commit-Anker | Status | Bemerkung |
|---|---|---|---|
| **Agent X (Hub)** | **`f7e0b294`** (Laufzeit) | 🟢 aktiv | **Anker-Nachzug SP16:** `54db58c1` → `f7e0b294` per Journal-`hub_rev=`. Hist.: `54db58c1`, `98c3e5c8`, `25e82602`, `d2839763`, `16e48880`, `3c7ebc1b`, `2a19a1d8` 📁. |
| **PolySentinel** | `66be8def` | 🔴 ungated — Gate defekt | unverändert |
| **NewsAgent / Wächter** | **`677c49f`** (Referenz) | 🟢 aktiv | Kontext **`8afde1f`** (05.10.; Host-Checkout, bis SP16 unverändert) — kein Anker-Update. Mac-Checkout lokal auf `master` `319607d1` (09.10., kein Ledger-Bezug). |

### 2.1 Anker-Kette NewsAgent
- Referenz: **`677c49f`**. Kontext → … → `3250be4` (B8-Fix) → `2a18b92` (04.10.) → `0a88df0` → **`8afde1f`** (05.10., Backup-Defaults pipefail-fest).

### 2.2 Anker-Kette Hub
- **Laufzeit (aktuell):** **`f7e0b294`** — gemessen SP16 `hub_rev=f7e0b294` · Vollhash `f7e0b294` (0.3.13-Tip).
- **Historisch 📁:** `54db58c1` (Laufzeit SP15) · `98c3e5c8` (Laufzeit SP14) · `25e82602` (Laufzeit SP13) · `d2839763` (Laufzeit SP12) · `16e48880` (Laufzeit SP11) · `3c7ebc1b` (formal bis SP11) · `2a19a1d8` (abgeleitet/Smoke, überholt als Zwischenschritt).
- **Docs-Kette:** … → `2a19a1d8` (0.3.7) → `16e48880` (0.3.8) → `d2839763` (0.3.9) → `25e82602` (0.3.10) → Runtime/Inventar `f90bbb40` · `3b8de68d` · `58e689df` · `23b8ed16` → Inventar `2a62017a` → `98c3e5c8` (0.3.11) → Inventar `f7b25039` → `54db58c1` (0.3.12) → Inventar `eddb358c` → **`f7e0b294` (0.3.13 Docs-Tip / Laufzeit-Anker SP16)** → *(0.3.14-Tip = dieser Commit, Basis `01620033`)*.
- **Telemetrie-Commits (kein Ledger/Docs):** `f7e0b294` → `6da8a5c4` · `43fc5898` · `d317d446` · `0770ec45` · `397dd6cd` · `e67a1506` · `6bef64fd` · `01620033` (8 Commits, nur `dashboard/`). Beleg: `git diff --stat f7e0b294..01620033` → ausschließlich `dashboard/`; `git diff f7e0b294..01620033 -- SCHWARM_STATUS.md docs/` = **leer**; `git merge-base --is-ancestor f7e0b294 01620033` = **ANCESTOR** (kein Rewrite). **Der 0.3.14-Commit sitzt daher auf `01620033`, nicht direkt auf `f7e0b294`** — die Telemetrie-Commits gehören nicht in die Docs-Kette.
- **Hub-FF 0.3.13:** `54db58c1` → `f7e0b294` — zwischen SP15 und SP16 (inkl. Inventar `eddb358c`). Beleg = SP16-Journal `hub_rev=f7e0b294`, Exit 0.
- **Hub-FF 0.3.12:** `98c3e5c8` → `54db58c1` — zwischen SP14 und SP15; zieht Inventar `f7b25039` mit. Beleg = SP15-Journal `hub_rev=54db58c1`, Exit 0.
- **Hub-FF 0.3.11:** `25e82602` → `98c3e5c8` — zwischen SP13 und SP14; zieht Runtime `f90bbb40`/`3b8de68d` (preflight) + Inventar `2a62017a` mit. Beleg = SP14-Journal `hub_rev=98c3e5c8`, Exit 0 → Runtime-Änderung ohne Befund.
- **Hub-FF 0.3.10:** `d2839763` → `25e82602` — zwischen SP12 und SP13; Beleg = SP13-Journal `hub_rev=25e82602`. Hub-Checkout bei SP13 bewusst = Docs-Tip 0.3.10 (Mac HEAD war bereits `23b8ed16`).
- **Hub-FF 0.3.9:** `16e48880` → `d2839763` — zwischen SP11 und SP12; Beleg = SP12-Journal `hub_rev=d2839763` (Origin = lokal = `d2839763`, geprüft 05.10. 04:16 UTC).
- **Hub-FF 0.3.8 (nachgetragen):** `2a19a1d8` → `16e48880` @ **`2026-10-03T08:01:33Z`** · Vollhash `16e48880e771b2570c853fb5cebab57fd2c0ec39`.
- Origin nach 0.3.8: Tip-Kontext bis `9556b1d7` u. a. — **Hub-Checkout bei SP11 bewusst `16e48880`** (kein FF vor Messung).

---

## 3. Verifikationsprotokolle

### 3.4 Wächter-Serie — **Serienpunkt 16**

| # | Wann | Exit | Offsite | Bewertung |
|---|---|---|---|---|
| 5 | 28.09. | 0 | **230** | SP5 |
| 6 | 29.09. | 0 | **234** | +4 |
| 7 | 30.09. | 0 | **238** | +4 |
| 8 | 01.10. | 0 | **242** | +4 |
| 9 | 02.10. | 0 | **245** | +3 |
| 10 | 03.10. | 0 | **250** | +5 |
| 11 | 04.10. 03:45:04 UTC | 0 | **230** | `hub_rev=16e48880` ✅ · B-OFF-1 🟠 (−20 vs SP10) · Beleg 84303 s |
| 12 | 05.10. 03:45:01 UTC | 0 | **232** | `hub_rev=d2839763` ✅ · +2 vs SP11 · B-OFF-1 🟠 · Beleg 84297 s |
| 13 | 06.10. 03:45:03 UTC | 0 | **235** | `hub_rev=25e82602` ✅ · +3 vs SP12 · B-OFF-1 🟠 · Beleg 84302 s |
| 14 | 07.10. 03:45 UTC | 0 | **238** | `hub_rev=98c3e5c8` ✅ · +3 vs SP13 · B-OFF-1 🟠 · erster Lauf mit Runtime `f90bbb40`/`3b8de68d` |
| 15 | 08.10. 03:45:00 UTC | 0 | **240** | `hub_rev=54db58c1` ✅ · +2 vs SP14 · B-OFF-1 🟠 bleibt · Beleg 84300 s · Hook OK |
| **16** | **09.10. 03:45:02 UTC** | **0** | **242** | **`hub_rev=f7e0b294`** ✅ · +2 vs SP15 · B-OFF-1 🟠 bleibt · Beleg 84300 s · Hook OK |

> SP1–3 Exit 3; SP4–SP16 Exit 0 → **Serienpunkt 16 · Exit-0-Serie 13** (Zählweise §1.1).  
> Nächster Schnitt: **SP17** am **10.10.2026, 03:45 UTC** → **0.3.15** (B-OFF-1 Review; Eskalation 🔴 bei Offsite < 230; Erwartung ≈ 245 ±4).  
> **Prüfauftrag SP17 (prüfbare Bedingung):** `hub_rev=` muß dem **Tip von `origin/deploy-safe-snapshot` nach der 0.3.14-Buchung** entsprechen. Bleibt `hub_rev=f7e0b294`, wird der Befund **„Hub-FF hängt"** gebucht (kein Diff-Lärm). Der konkrete Hash wird erst in 0.3.15 aus dem SP17-Paste gebucht — kein Hash-Nachtrag per Folge-Commit.

**Timer:** LAST `2026-10-09 03:45:02 UTC` · NEXT `2026-10-10 03:45:00 UTC`.

### 3.14–3.15 Archiv
Tip `2a19a1d8` + Inventar · SP8–SP10 + §1.1-Entscheidung (0.3.8).

### 3.16 SP11 + B8-Schließung + Anker-Nachzug (Paste 04.10.)

| Feld | Wert |
|---|---|
| Exit | **0** (`ExecMainStatus=0`, Result=success) |
| Zähler | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` |
| Hook | `[OK] RC=0, kein Drift` |
| **`hub_rev=`** | **`16e48880`** — erste Journal-Zeile; Soll exakt |
| Offsite | **230** Dateien · Beleg 84303 s → **B-OFF-1 🟠** |
| B8 | ✅ geschlossen (Beleg = SP11-Journal, nicht Smoke) |
| Anker | `3c7ebc1b` → **`16e48880`** (direkt) |
| NA Kontext | `2a18b92` |

### 3.17 B-OFF-1 — Offsite-Einbruch SP11

| | |
|---|---|
| Ist / Soll | 230 / Band 250–258 (−20 vs. SP10=250) |
| Beleg-Alter | 84303 s — **kein Taktproblem** |
| Hinweis | 230 = SP5-Stand → eher Quellbestand/Sync-Scope als Zufall |
| Serie | **kein Bruch** — Exit-0-Kriterium erfüllt; Befund separat |
| Follow-up | Ursachenklärung P1; Review SP12; bei weiterem Rückgang → 🔴 |
| **Review SP12** | Ist **232** (+2 vs SP11) · Beleg 84297 s (stabil zu 84303 s → kein Taktproblem). Kein Rückgang < 230 → **kein 🔴**. Nicht ≥ 238 und nicht zurück im Band 250–258 → **🟠 bleibt**. Trend +2 liegt in Toleranz (±4 um +4) → kein neuer Befund; Niveau-Lücke (−18 zum Bandboden) unverändert offen. |
| **Review SP13** | Ist **235** (+3 vs SP12) · Beleg 84302 s → Erwartung ≈ 236 ±4 → **im Trend**, kein neuer Befund. Kein Wert < 230 → **kein 🔴**. Nicht ≥ 238, nicht Band 250–258 → **🟠 bleibt**. Niveau-Lücke −15 zum Bandboden; Trend läuft wieder ≈ +3/Lauf ab SP11-Basis 230 → Muster passt zu Reset auf SP5-Niveau (Quellbestand/Sync-Scope), Ursache weiter offen. |
| **Review SP14** | Ist **238** (+3 vs SP13) · Erwartung ≈ 239 ±4 → **im Trend**, kein neuer Befund. Kein Wert < 230 → **kein 🔴**. Schwelle ≥ 238 formal erreicht, aber Band 250–258 (Schließkriterium) nicht → **🟠 bleibt**. Niveau-Lücke −12 zum Bandboden; Serie 230→232→235→238 = SP5→SP7-Verlauf, um 7 Läufe versetzt → stützt Reset-Hypothese. Bei +3/Lauf Bandboden 250 ≈ SP18; Ursache weiter offen. |
| **Review SP15** | Ist **240** (+2 vs SP14) · Beleg 84300 s (stabil 84297–84303 s → kein Taktproblem) · Erwartung ≈ 241 ±4 → **im Trend**, kein neuer Befund. Kein Wert < 230 → **kein 🔴**. Band 250–258 nicht erreicht → **🟠 bleibt**. Niveau-Lücke −10 zum Bandboden. Zuwachs flacher als SP5-Verlauf (SP8: 242 bei +4) → Reset-Hypothese gilt, Tempo ≈ +2,5/Lauf → Bandboden ≈ SP18–19; Ursache weiter offen. |
| **Review SP16** | Ist **242** (+2 vs SP15) · Beleg 84300 s (stabil zu 84297–84303 s → kein Taktproblem) · Erwartung ≈ 243 ±4 → **im Trend**, kein neuer Befund. Kein Wert < 230 → **kein 🔴**. Band 250–258 nicht erreicht → **🟠 bleibt**. Niveau-Lücke −8 zum Bandboden. Tempo bestätigt ≈ +2/Lauf (flacher als SP5-Verlauf +4) → Bandboden ≈ SP18–19 bleibt Prognose; Ursache weiter offen. |

### 3.18 SP12 + Hub-FF-Beleg 0.3.9 + Anker-Nachzug (Paste 05.10.)

| Feld | Wert |
|---|---|
| Exit | **0** (`ExecMainStatus=0`, Result=success) |
| Zähler | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` |
| Hook | `[OK] RC=0, kein Drift` · keine `[OPS]` |
| **`hub_rev=`** | **`d2839763`** = Docs-Tip 0.3.9 = origin → Hub-FF belegt |
| Offsite | **232** Dateien · Beleg 84297 s → B-OFF-1 🟠 bleibt |
| Anker | `16e48880` → **`d2839763`** |
| NA Kontext | `8afde1f` |
| Timer | LAST 05.10. 03:45:01 · NEXT 06.10. 03:45:00 UTC |

### 3.19 SP13 + Hub-FF-Beleg 0.3.10 + Anker-Nachzug (Paste 06.10.)

| Feld | Wert |
|---|---|
| Exit | **0** (`ExecMainStatus=0`, Result=success) |
| Zähler | sauber (`befund 0 · blind 0 · alarm 0`) |
| Hook | `[OK] RC=0` · keine `[OPS]` |
| **`hub_rev=`** | **`25e82602`** = Docs-Tip 0.3.10 → Hub-FF belegt |
| Offsite | **235** Dateien · Beleg 84302 s → ≈ 236 ±4 · B-OFF-1 🟠 bleibt |
| Anker | `d2839763` → **`25e82602`** |
| NA Kontext | `8afde1f` (unverändert) |
| Timer | LAST 06.10. 03:45:03 · NEXT 07.10. 03:45:00 UTC |

### 3.20 SP14 + Hub-FF-Beleg 0.3.11 + Anker-Nachzug (Paste 07.10.)

| Feld | Wert |
|---|---|
| Exit | **0** |
| **`hub_rev=`** | **`98c3e5c8`** = Docs-Tip 0.3.11 → Hub-FF belegt (inkl. Runtime `f90bbb40`/`3b8de68d`) |
| Offsite | **238** Dateien → ≈ 239 ±4 · B-OFF-1 🟠 bleibt |
| Anker | `25e82602` → **`98c3e5c8`** |
| NA Kontext | `8afde1f` (unverändert) |
| Timer | LAST 07.10. 03:45 · NEXT 08.10. 03:45:00 UTC |
| Lücke | Sekundengenaue Laufzeit + Beleg-Alter nicht im Paste — bei SP15 mitliefern → **geschlossen SP15** (§3.21) |

### 3.21 SP15 + Hub-FF-Beleg 0.3.12 + Anker-Nachzug (Paste 08.10.)

| Feld | Wert |
|---|---|
| Exit | **0** |
| Zähler | sauber |
| Hook | `[OK] RC=0` |
| **`hub_rev=`** | **`54db58c1`** = Docs-Tip 0.3.12 → Hub-FF belegt (inkl. Inventar `f7b25039`) |
| Offsite | **240** Dateien · Beleg 84300 s → ≈ 241 ±4 · B-OFF-1 🟠 bleibt |
| Anker | `98c3e5c8` → **`54db58c1`** |
| NA Kontext | `8afde1f` (unverändert) |
| Timer | LAST 08.10. 03:45:00 · NEXT 09.10. 03:45:00 UTC |
| Repo bei Paste | lokal = origin = Hub `54db58c1`, Ledger-Datei 0.3.12 |

### 3.22 SP16 + Hub-FF-Beleg 0.3.13 + Anker-Nachzug (Paste 09.10.)

| Feld | Wert |
|---|---|
| Exit | **0** (`ExecMainStatus=0`, Result=success) |
| Zeit | Start/Ende **09.10.2026 03:45:02 UTC** (Sekundengenau) |
| Zähler | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` |
| Hook | `[OK] Hook-Drift: RC=0, kein Drift` · keine `[OPS]` |
| **`hub_rev=`** | **`f7e0b294`** = Docs-Tip 0.3.13 → Push + Hub-FF belegt (inkl. Inventar `eddb358c`) |
| Offsite | **242** Dateien · Beleg **84300 s** (Limit 93600 s) → ≈ 243 ±4 · B-OFF-1 🟠 bleibt |
| Anker | `54db58c1` → **`f7e0b294`** |
| NA Kontext | `8afde1f` (unverändert, Host-Checkout) |
| Timer | LAST 09.10. 03:45:02 · NEXT 10.10. 03:45:00 UTC |
| Repo bei Paste | lokal = origin = Hub `f7e0b294`; Ledger-Datei 0.3.13 |

### 3.23 Telemetrie-Befunde 09.10. (kein Wächter-Bezug, reine Beleg-Aufnahme)

| Punkt | Messung (09.10.2026) |
|---|---|
| **Rolle `/opt/polysentinel`** | ✅ **belegt:** `/etc/agent-x/telemetry-registry.json` (Hetzner) → `role: deploy`; mtime **2026-10-08 17:48:56.455322818 +0000**. Live-Snapshot `/var/lib/agent-x-telemetry/status.json`: `role=deploy · behind=0 · ahead=0 · state=ok · health=WARN`. Vorher-Zustand über zwei Backups belegt (`.bak-20261008-174856`, `.bak-20261008-164347` → jeweils `satellite`). |
| **Mac-Checkout `newsagent`** | Pfad aus Registry (`dashboard/telemetry-registry.mac.json` → `newsagent`): `/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage/newsagent`. Stand vor Korrektur: `f72279d9` auf Branch `tor-hook-eine-quelle`, ahead 1. Nach Korrektur + Push: `master` = `origin/master` = **`319607d1`**, ahead 0. |
| **Bridge-Gegenprobe `newsagent`** | **Belegter Funktionsnachweis `REPO_AHEAD` in beide Richtungen:** **06:10:48** → `ahead=1`, `behind=0`, Alert `REPO_AHEAD` (info) „1 lokale Commits nicht gepusht", Upstream `@{u}` = `origin/master`; **06:16:35** (nach Push) → `ahead=0`, `behind=0`, Alerts `[]`. Die Bridge folgt dem Push korrekt; kein Bridge-Befund. |
| **Korrigierter Befund-Doc** | `newsagent@319607d1:docs/kanonizitaet/BEFUND_TOR_HOOK_NICHT_DECKUNGSGLEICH_2026-10-08.md` — polysentinel-Abschnitt korrigiert (Behauptung „nie umgestellt" ersetzt, mtime-Beleg, „toter Code" berichtigt, Rollen-Matrix auf `deploy`). Push über Tor (allow, FF, keine Freigabe). |

---

## 4. Baustellen-Tracker (B-Tracks)

| ID | Thema | Status | Anker/Detail |
|---|---|---|---|
| B1 / B3 / B5 | — | ✅ | |
| **B4** | FalkorDB | ⚪ | Key-Rotationstermin |
| **B6** | venv/Deploy-Gate | 🔴 | |
| **B7** | `[OPS]`-Verdrahtung | 🔴 | |
| **B8** | Hub-`rev-parse` Journal | ✅ | SP11 `hub_rev=16e48880`; Fix `3250be4` / `waechter_lauf.sh` |
| **B-OFF-1** | Offsite-Einbruch | 🟠 | SP11: 230 · SP12: 232 · SP13: 235 · SP14: 238 · SP15: 240 · SP16: 242 (Band 250–258); Ursache offen; Review SP17 |
| Track 12 / m2 | — | 🔴/🟡 | |

### 3.24 Offene Punkte aus der Telemetrie-Sitzung 08.10. (Verweise, keine Buchungen)

> Nur Verweise auf Befund-Docs. Was nicht schriftlich belegt ist, ist als **nicht belegt** gekennzeichnet.

| Punkt | Quelle |
|---|---|
| Hook-Scope jenseits von `master` | `newsagent@44d5db2:docs/kanonizitaet/BEFUND_TOR_HOOK_NICHT_DECKUNGSGLEICH_2026-10-08.md` (auf `origin/master`; `git cat-file -e` OK) |
| `LEITPLANKEN.md` veraltet | derselbe Befund-Doc **+** `newsagent@44d5db2:docs/LEITPLANKEN.md` (Kopf: „Stand: 2026-09-12 … jede Aussage trägt eine Fundstelle") |
| `NOT FOUND`-Literal an der Quelle | `x-storage-control-center@d621eb3:SCHEMA.md:85ff` („`NOT FOUND` trägt ein Leerzeichen, keinen Unterstrich") **+** `agent_x_storage@01620033:dashboard/telemetry_bridge.py:425` |
| **Fetch-Timer für `/opt/polysentinel` fehlt** | `behind` ist nur so aktuell wie der letzte Fetch. Letzter `FETCH_HEAD`: **2026-10-08 17:39:09Z** (der Snapshot-`behind=0` gilt **nur bezogen auf diesen Zeitpunkt**); kein systemd-Timer, kein Cron-Eintrag. Ohne periodischen Fetch bleibt `REPO_BEHIND` trotz korrekt gesetztem `role: deploy` **blind** (`behind=0` = Blindheit, keine Aussage). |
| Rolle `/opt/polysentinel` | ✅ **erledigt** (Beleg §3.23). `role: deploy` gesetzt 08.10. 17:48:56Z. Der gestrige Widerspruch „`deploy` existiert nirgends" ist aufgelöst (Suche galt einer nicht existenten Repo-Datei). |
| Image-Herkunft `newsagent` | **nicht schriftlich belegt** — nur Sitzung 2026-10-08. Inhalt: Der Dienst läuft aus `localhost/newsagent:latest`, **nicht** aus dem Checkout; der Herkunfts-Commit des Images ist unbekannt. Vorschlag: `org.opencontainers.image.revision=<commit>` beim Build setzen, Telemetrie vergleicht das Label gegen `origin/master`. Randbeleg: `dashboard/CLAUDE_TELEMETRY.md` §Betrieb. |
| **§1.1 vs. B-OFF-1 (Regel-Abweichung)** | §1.1 nennt Offsite-Trend „≈ +4/Lauf"; die realen Läufe seit SP11 liegen bei **+2/+3** (230→232→235→238→240→242). Die Regel ist damit zu steil und widerspricht dem B-OFF-1-Review unkommentiert. Korrektur von §1.1 auf eine realistische Toleranz (≈ +2,5, Abweichung > ±4 = Befund) erfolgt in **0.3.15**. |

## 5. Schnittstellen-Verträge (v1.3)

### 5.3 Exit 0/1/2/3
- SP4–SP16: **dreizehn** Timer-Exit-0 in Folge (Exit-0-Serie 13). Serie läuft trotz B-OFF-1.

### 5.6 Wächter-Journal — Hub-Zeile
```
hub_rev=<short8>
```
**Ist:** live seit NA `3250be4`; Messungen SP11 (`16e48880`) ✅ · SP12 (`d2839763`) ✅ · SP13 (`25e82602`) ✅ · SP14 (`98c3e5c8`) ✅ · SP15 (`54db58c1`) ✅ · SP16 (`f7e0b294`) ✅.

---

## 6. Operational Safety — Wächter

| Komponente | Zustand | Detail |
|---|---|---|
| Timer | 🟢 | NEXT 10.10. 03:45 (SP17) |
| SP4–SP16 | 🟢 Exit 0 | Serienpunkt **16** · Exit-0-Serie **13** |
| B8 `hub_rev=` | ✅ | gemessen |
| **B-OFF-1** | 🟠 | Offsite 242 |
| PolySentinel-Gate | 🔴 | B6/B7 |

---

## 7. Audit-Pfade & Zero-Trust

| Prüfpfad | Stand |
|---|---|
| Hub Laufzeit-Anker | **`f7e0b294`** ✅ (SP16 `hub_rev=`) |
| Hub Docs-Tip (0.3.8) | **`16e48880`** · FF @ 08:01:33Z nachgetragen |
| Sync 0.3.9 | ✅ Hub-FF `d2839763` (SP12) |
| Sync 0.3.10 | ✅ Hub-FF `25e82602` (SP13) |
| Sync 0.3.11 | ✅ Hub-FF `98c3e5c8` (SP14) |
| Sync 0.3.12 | ✅ Hub-FF `54db58c1` (SP15) |
| Sync 0.3.13 | ✅ Hub-FF `f7e0b294` (SP16, inkl. Inventar `eddb358c`) |
| Sync 0.3.14 | ⏳ Docs-Tip nach diesem Commit; Beleg via SP17 `hub_rev=` |
| **Rolle `/opt/polysentinel`** | ✅ belegt — Registry (Hetzner) `role: deploy`, gesetzt **2026-10-08 17:48:56Z**; Live-Snapshot `role=deploy · behind=0 · ahead=0` (§3.23) |
| **Fetch-Timer `/opt/polysentinel`** | 🟠 offen — `FETCH_HEAD` 08.10. 17:39:09Z, kein Timer (§3 Offene Punkte) |
| NewsAgent Host-Checkout | **`8afde1f`** (Kontext) · Referenz `677c49f` |
| NewsAgent Mac-Checkout | **`319607d1`** (= `origin/master`, 09.10.) — kein Ledger-Bezug |
| PolySentinel | **`66be8def`** |
| B8 / Journal-Lücke | ✅ geschlossen |
| **Zero-Trust SSOT** | ✅ |
| **Key-Rotation** | 🔴 offen |
| **B-OFF-1** | 🟠 offen |

---

## 8. Änderungsprotokoll 0.3.13 → 0.3.14

| Thema | 0.3.13 | 0.3.14 |
|---|---|---|
| Charakter | SP15 + Hub-FF-Beleg 0.3.12 + Anker-Nachzug + B-OFF-1-Review | **SP16** + Hub-FF-Beleg 0.3.13 + Anker-Nachzug + B-OFF-1-Review + Telemetrie-Belege |
| Laufzeit-Anker | `54db58c1` | **`f7e0b294`** (gemessen SP16) |
| Sync | 0.3.12 ✅ · 0.3.13 ⏳ | 0.3.13 ✅ · 0.3.14 ⏳ |
| Zählung | Serienpunkt 15 · Exit-0-Serie 12 | **Serienpunkt 16 · Exit-0-Serie 13** |
| Offsite | 240 (SP15) | **242** (Beleg 84300 s) — im Trend, B-OFF-1 🟠 bleibt |
| Docs-Kette §2.2 | ohne `eddb358c` | Inventar **`eddb358c`** nachgezogen; Telemetrie-Commits (8) als Nicht-Docs-Kette dokumentiert |
| Neu §3 Offene Punkte | — | Verweis-Absatz (Hook-Scope, LEITPLANKEN, Fetch-Timer); Rolle polysentinel ✅ belegt |
| Neu §3.22/§3.23 | — | SP16-Paste + Telemetrie-Befunde 09.10. |
| Prüfauftrag SP17 | — | `hub_rev` = Tip von `origin/deploy-safe-snapshot` nach 0.3.14-Push, sonst Befund „Hub-FF hängt"; Hash-Buchung erst in 0.3.15 |
| Nächster Schnitt | SP16 → 0.3.14 | **SP17 → 0.3.15** |

---

## 9. Nächste Schritte (Priorität)

1. **B-OFF-1** 🟠 — Offsite 242: Quellbestand/Sync-Scope klären; Trend ≈ +2/Lauf → Bandboden 250 ≈ SP18–19; Review SP17; Eskalation 🔴 bei < 230.
2. **Sync 0.3.14** — Push + Hub-FF; **Prüfauftrag SP17:** `hub_rev` = Tip von `origin/deploy-safe-snapshot` nach der 0.3.14-Buchung, sonst Befund „Hub-FF hängt".
3. **Fetch-Timer `/opt/polysentinel`** 🟠 — ohne periodischen Fetch bleibt `REPO_BEHIND` blind (`FETCH_HEAD` 08.10. 17:39:09Z).
4. **Key-Rotation** 🔴 — B4.
5. **B6 / B7** — Gate + `[OPS]`.
6. **SP17** (10.10. 03:45 UTC) → **0.3.15**.

**Erledigt:** Rolle `/opt/polysentinel` ✅ (Registry + Snapshot, 09.10.) · Befund-Doc-Telemtrie korrigiert + Tor-Push `319607d1` ✅ · Sync 0.3.13 ✅ (SP16) · Anker-Nachzug `f7e0b294` · Docs-Kette `eddb358c` + Telemtrie-Abgrenzung · Sync 0.3.12 ✅ (SP15) · Anker-Nachzug `54db58c1` · Docs-Kette `f7b25039` · Paste-Lücke SP14 · Sync 0.3.11 ✅ (SP14, inkl. Runtime) · Anker-Nachzug `98c3e5c8` · Docs-Kette `2a62017a` · Sync 0.3.10 ✅ (SP13) · Anker-Nachzug `25e82602` · Sync 0.3.9 ✅ (SP12) · Anker-Nachzug `d2839763` · Zählweise vereinheitlicht · B8 ✅ · Anker-Nachzug `16e48880` · Journal-Lücke · SP11 Exit-0-Serie · Hub-FF-Beleg 0.3.8 nachgetragen · Frischstart-Staging verworfen.

---

*SSOT 0.3.14 · Laufzeit-Anker Hub `f7e0b294` · Serienpunkt 16 · Exit-0-Serie 13 · B8 ✅ · B-OFF-1 🟠 · Fetch-Timer 🟠 · Key-Rotation 🔴 · Sync 0.3.14 ⏳ · kein Abschluss ohne Beleg.*
