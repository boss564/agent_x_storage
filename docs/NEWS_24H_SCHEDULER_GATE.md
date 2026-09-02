# News-Agent — 24h Scheduler Gate (LaunchAgent)

**Status:** FROZEN (2026-08-31) — Bestehenskriterien **vor** Auswertung festgelegt  
**Amendment A1 (2026-08-31, vor Gate-Close):** G1 absolut `≥ 20` → **relativ** `n_markers ≥ floor(hours_awake × 0.85)` — Messkorrektur (Widerspruch zu §2 Sleep-Semantik), **kein** HARKing nach Datenblick.  
**Amendment A2 (2026-09-01, vor Hetzner-Epoche):** G4 auf Linux — `pmset` entfällt; **`downtime_h`** aus Neustart-Lücken (`uptime -s` führend, `journalctl` ergänzend) ersetzt **`total_sleep_h`**. A1-Anker bei `downtime_h=0` → `n_min=20` unverändert. **Kein** HARKing nach Datenblick.  
**Amendment A3 (2026-09-02, vor Polling-Epoche §8.6):** G1 **`n_min`** skaliert mit **`interval_min`** — `n_min = max(1, floor(hours_up × (60/interval_min) × 0.85))`. A1-Anker bei `interval_min=60`, `downtime_h=0` → **20**. Bei 5 min ohne Downtime → **244** (nicht 20). **Vor** erstem 5-min-Gate festlegen — kein Nachtrag nach 24 h Datenblick. Code: `services/news_agent/gate_g1.py`.  
**Amendment A3.1 (2026-09-02, nach Gate-Close, vor Polling-Epoche):** **`interval_min`** aus installierter Schedule (Crontab `# AGENTX_NEWS_AGENT` / macOS LaunchAgent-Plist) — **nicht** primär aus `NEWS_SCHEDULER_INTERVAL_MINUTES`. Env nur Fallback wenn Schedule nicht lesbar; `make news-agent-cron-status` **WARN** (non-blocking, exit 0) bei Env↔Schedule-Divergenz. **Methodik A3 unverändert** — Implementierungshärtung. Code: `services/news_agent/cron_schedule.py`.
**Erstellt:** 2026-08-31  
**Strang:** Host-Scheduler + `run_marker`-Liveness (Instanz 3) — **kein** Cluster, **kein** Code in diesem Gate  
**Parent:** [`NEWS_AGENT.md`](NEWS_AGENT.md) · [`NEWS_FEED_STRUCTURE_PREREG.md`](NEWS_FEED_STRUCTURE_PREREG.md) · [`AUDIT_WRITER_LIVENESS.md`](AUDIT_WRITER_LIVENESS.md)  
**Konstanten (Code):** `NEWS_SCHEDULER_EPOCH_TS`, `NEWS_MARKER_MAX_AGE_H` in `services/news_agent/liveness.py`

---

## 0. Zweck

Nach dem Wechsel auf **LaunchAgent** (`StartCalendarInterval`, Minute=0) wird **24 h** beobachtet, ob der Scheduler zuverlässig `run_marker` schreibt — **bevor** Feed-Qualität, PhaseSources oder Cluster-Registration bewertet werden.

Die **Pass/Fail-Regeln** sind hier eingefroren, damit morgen nicht ad-hoc entschieden wird, ob „21/24“ reicht.

---

## 1. Beobachtungsfenster

| Grenze | Wert |
|--------|------|
| **Start (Epoche)** | `NEWS_SCHEDULER_EPOCH_TS` — Timestamp des ersten **autonomen** Scheduler-Markers (`run_marker`, nicht Smoke/Manual). Kanonisch in `services/news_agent/liveness.py` + Gate-Protokoll. |
| **Gate-Close (Auswertung)** | **Epoche + 24 h** (UTC) |
| **Dauer** | 24 h |

**Archiv (Mac VOID, nicht für Hetzner):** Erster Lauf `2026-08-31T09:00:00+00:00` → Gate-Close `2026-09-01T09:00:00+00:00` — Fenster ohne post-Epochen-Marker (`launchd` `EX_CONFIG`). Epoche bleibt dokumentiert, zählt nicht für den aktuellen Strang (§8.5).

Zählen nur `run_marker` mit `ts ≥ NEWS_SCHEDULER_EPOCH_TS` (`measurement_run_markers` in `liveness.py`). Vor-Epochen-Marker = Vorlauf, ignorieren.

---

## 2. Scheduler-Semantik (kein Fehler bei Sleep)

**macOS LaunchAgent** mit `StartCalendarInterval` (stündlich :00):

- Während **Sleep** feuert der Job nicht.
- Nach **Wake** holt launchd **höchstens einen** versäumten Lauf nach — **nicht** alle verschlafenen :00-Slots.

| Situation | Erwartung |
|-----------|-----------|
| Rechner wacht 24/7 | bis zu **24** Marker im Fenster |
| Rechner schläft nachts (z. B. 7,5–8 h) | **~16–17** Marker — **korrekt** (stündlich im Wachbetrieb + **ein** Nachhol-Lauf) |
| Ein verpasstes :00 bei kurzem Sleep | ein Nachhol-Lauf; Lücke kann **> 1 h**, **≤ 3 h** in wacher Zeit sein |

**Anti-Pattern:** „24/24 oder FAIL“ — verworfen (ignoriert Sleep-Semantik).

---

## 3. Bestehenskriterien (konjunktiv)

Alle **vier** Bedingungen müssen zur Gate-Close-Zeit erfüllt sein.

### G1 — Marker-Anzahl (**relativ zu wacher Laufzeit × Abtasttakt**, A1+A3)

G4 (`total_sleep_h` **macOS** / `downtime_h` **Linux** — §8.5.2 A2) muss **vor** G1 bekannt sein (Betriebszeit-Protokoll zuerst).

```text
hours_awake     = 24 − total_sleep_h          # macOS (LaunchAgent + Sleep)
hours_up        = 24 − downtime_h             # Linux/Hetzner (Neustart-Lücken) — §8.5.2
interval_min    = crontab/launchd (# AGENTX_NEWS_AGENT) — env nur Fallback §8.6
n_min           = max(1, floor(hours_up × (60 / interval_min) × 0.85))
n_markers_post_epoch ≥ n_min
```

`n_markers_post_epoch` = Anzahl `run_marker` mit `ts ∈ [NEWS_SCHEDULER_EPOCH_TS, GATE_CLOSE]`.

**Anker (A1+A3, keine Lockerung):** Bei `downtime_h = 0` und **`interval_min = 60`** gilt `n_min = floor(24 × 1 × 0,85) = 20` — **identisch** zur ursprünglichen absoluten Schwelle und zum A1-only-Fall.

**Polling-Epoche (A3):** Bei `interval_min = 5`, `hours_up = 24` → `n_min = floor(288 × 0,85) = 244`. Ein Scheduler, der nur jeden 15. Lauf schafft (~19/h), würde mit **`n_min = 20`** trivial PASS — dieselbe Fehlanpassung wie `stale_s=300` am Watchdog, nur am **Nachweis**-Ende. A3 **vor** dem ersten 5-min-Gate schreiben, nicht nach einem scheinbaren PASS.

**Beispiel (ein Nacht-Sleep-Block, stündlich):** `sleep_h = 7.5` → `hours_awake = 16.5` → `n_min = 14`. Erwartung ~17 Marker (16× :00 + 1 Nachhol) — **PASS**, nicht FAIL.

**Watchdog (Transport):** `WATCHDOG_CRON_INTERVAL_MINUTES` muss zur Epoche passen (5 → 7/12 min WARN/CRIT). **G1** leitet `interval_min` aus der installierten Schedule-Zeile ab (`services/news_agent/cron_schedule.py`) — `make news-agent-cron-status` gibt bei Env↔Schedule-Divergenz **WARN** (non-blocking), G1 nutzt trotzdem Schedule.

**Begründung A1:** Absolut `≥ 20` widerspricht §2 (LaunchAgent holt beim Wake **einen** Lauf nach, nicht alle verschlafenen Slots). G2 misst Lücken bereits relativ zur wachen Zeit; G1 zählt jetzt konsistent **Dichte im Wachbetrieb**, nicht gegen ein fixes 24/24-Ziel.

**Verworfen (A1):** `n_markers_post_epoch ≥ 20` absolut — scheitert bei korrektem Scheduler + dokumentiertem Sleep (z. B. `n=17`, `sleep_h=7.5`).

### G2 — Maximale Lücke in **wacher** Laufzeit

```text
max_gap_awake_s ≤ 10_800   (= 3 h)
```

Zwischen zwei aufeinanderfolgenden post-Epochen-Markern, **nur** Intervalle, die **nicht vollständig** in einer dokumentierten Sleep-Phase liegen:

```text
gap_i = ts(marker_{i+1}) − ts(marker_i)
sleep_union = Vereinigung(sleep_intervals)    # disjunkte Blöcke — kein Doppel-Overlap
gap_awake_i = max(0, gap_i − overlap(gap_i, sleep_union))   # macOS
gap_awake_i = max(0, gap_i − overlap(gap_i, downtime_union)) # Linux — §8.5.2
max_gap_awake = max(gap_awake_i)
```

**Begründung:** Ein verpasstes :00 + ein Nachhol-Lauf ≈ bis 2 h; **3 h** Puffer für Netz/Scheduler-Jitter. Lücken **während** Sleep zählen nicht.

### G3 — Aktuelle Liveness am Gate-Close

```text
marker_liveness.status == ACTIVE
marker_liveness.age_s ≤ NEWS_MARKER_MAX_AGE_S   (Default 2 h)
```

Prüfung: `make news-agent-cron-status` unmittelbar vor/nach Gate-Close.

### G4 — Betriebszeit-Protokoll (Pflicht-Anhang)

**Plattform:**

| Plattform | Mechanik | `sleep_source` / `boot_source` |
|-----------|----------|--------------------------------|
| **macOS** (§2, Host) | `total_sleep_h` aus `pmset -g log` | `pmset` (bevorzugt) oder `manual` |
| **Linux** (§8.5 Hetzner, A2) | `downtime_h` aus Neustart-Lücken | `journalctl` (bevorzugt) oder `uptime` / `manual` |

Auswertung **muss** eine Betriebszeit-Notiz enthalten (eine Zeile reicht):

| Feld | macOS | Linux (A2) |
|------|-------|------------|
| Intervalle | `sleep_intervals` | `downtime_intervals` (Boot-Lücken) |
| Quelle | `sleep_source` | `boot_source` |
| Summe | `total_sleep_h` | `downtime_h` |

**Herkunft macOS:** [`scripts/news_24h_sleep_from_pmset.py`](../scripts/news_24h_sleep_from_pmset.py). **Linux:** `journalctl --list-boots`, `uptime -s` — siehe §8.5.2.

**pmset-Rotation (macOS, A1):** Reicht das Log **nicht** über das volle Gate-Fenster zurück → **`status=INCOMPLETE`**. **journalctl-Lücke (Linux, A2):** analog — keine still gekürzte `downtime_h`.

Ohne G4: Auswertung **unvollständig** — kein PASS, auch wenn G1–G3 grün (Lücken nicht attributierbar).

---

## 4. Fail-Bedingungen (disjunktiv)

| ID | Bedingung | Verdict |
|----|-----------|---------|
| **F1** | `n_markers_post_epoch < n_min` (G1 A1, nach G4 `total_sleep_h`) | **FAIL** |
| **F2** | `max_gap_awake_s > 10_800` | **FAIL** |
| **F3** | Gate-Close: `marker_liveness` ∈ {`MISSING`, `STALE`, `UNPARSEABLE`} | **FAIL** |
| **F4** | Kein Betriebszeit-Protokoll (G4): macOS `pmset_coverage=insufficient`; Linux `journal_coverage=insufficient` (A2) | **INCOMPLETE** (nicht PASS) |
| **F5** | Post-Epochen-Marker mit durchgehend `dead`/`DEGRADED` ohne Recovery | **FAIL** (Scheduler ok, Feed/Transport nicht — separates Ticket) |

**F5** ist **nicht** Teil von G1–G3, aber blockiert Freigabe „Scheduler + Feed gesund“. Mindestens ein Lauf mit allen Quellen `ok` oder `quiet` (nicht `dead`) nach Epoche.

---

## 5. Auswertung morgen (2026-09-01 **09:05–09:15 UTC**)

Read-only — kein Cluster, kein Cron-Patch. **Nicht** punktgenau 09:00 UTC: die 15-Minuten-Marge am Gate-Ende (`pmset_latest`) kompensiert fehlende letzte pmset-Minuten.

```bash
# 1) Scheduler + aktuelle Liveness (G3)
make news-agent-cron-status

# 2) Sleep + G1 n_min (G4 zuerst — Nenner messen, nicht schätzen)
# Bevorzugt: pmset → sleep_h + n_min
PYTHONPATH=. python3 scripts/news_24h_sleep_from_pmset.py | tee /tmp/news_gate_sleep.txt
# OK:     status=OK sleep_source=pmset sleep_h=7.52 n_min=14 …
# Lücke:  status=INCOMPLETE pmset_coverage=insufficient … (exit 3 — G1 nicht mit dieser sleep_h)

# Fallback nur wenn pmset unvollständig — sleep_source=manual in Ergebniszeile Pflicht:
# export SLEEP_H=7.5
# export SLEEP_SOURCE=manual

PYTHONPATH=. python3 <<'PY'
import math
import os
import re
from pathlib import Path
from services.news_agent.liveness import (
    load_run_markers,
    measurement_run_markers,
    parse_marker_ts,
)

GATE_CLOSE = "2026-09-01T09:00:00+00:00"
WINDOW_H = 24.0

sleep_h = float(os.environ.get("SLEEP_H", "0"))
sleep_source = os.environ.get("SLEEP_SOURCE", "")
if not sleep_source:
    try:
        line = open("/tmp/news_gate_sleep.txt").readline()
        if "status=INCOMPLETE" in line:
            print("gate_sleep INCOMPLETE — fix G4 before G1 (manual sleep_source or extend pmset log)")
            raise SystemExit(3)
        m = re.search(r"sleep_source=(\w+)", line)
        m2 = re.search(r"sleep_h=([\d.]+)", line)
        if m and m2:
            sleep_source = m.group(1)
            sleep_h = float(m2.group(1))
    except OSError:
        pass
if not sleep_source:
    sleep_source = "manual" if os.environ.get("SLEEP_H") else "pmset"

hours_awake = WINDOW_H - sleep_h
interval_min = int(os.environ.get("NEWS_SCHEDULER_INTERVAL_MINUTES", "60"))
n_min = max(1, math.floor(hours_awake * (60 / interval_min) * 0.85))

path = Path("data/news_scores.jsonl")
markers = measurement_run_markers(load_run_markers(path))
close = parse_marker_ts(GATE_CLOSE)
markers = [
    m for m in markers
    if (t := parse_marker_ts(str(m.get("ts") or ""))) and t <= close
]
n = len(markers)
print("sleep_source", sleep_source, "sleep_h", sleep_h, "hours_awake", hours_awake, "n_min", n_min)
print("n_markers_post_epoch", n, "g1_ok", n >= n_min)
if len(markers) >= 2:
    gaps = []
    for i, (a, b) in enumerate(zip(markers, markers[1:]), 1):
        ta = parse_marker_ts(str(a.get("ts")))
        tb = parse_marker_ts(str(b.get("ts")))
        if ta and tb:
            g = (tb - ta).total_seconds()
            gaps.append(g)
            print(f"pair {i} ts_i={a.get('ts')} ts_ip1={b.get('ts')} gap_s={round(g)}")
    print("gaps_s", [round(g) for g in gaps])
    print("max_gap_s", round(max(gaps)) if gaps else None)
    print("hint: fill G2 table §5.2 — max_gap_s is NOT max_gap_awake_s")
PY

# 3) Sleep-Rohlog (G4 Beleg, Archiv)
pmset -g log | tail -30
```

**Ergebnis** in einer Zeile festhalten, z. B.:

```text
NEWS_24H_GATE=PASS|FAIL|INCOMPLETE n=17 n_min=14 max_gap_awake_s=3600 liveness=ACTIVE sleep_h=7.52 sleep_source=pmset
```

### 5.1 Entscheidungsbaum (P0 — keine Nach-Tuning)

| Beobachtung | Verdict | Aktion |
|-------------|---------|--------|
| **pmset-Rotation** / Log deckt Fenster nicht ab | **F4 → INCOMPLETE** | `sleep_source=manual` + dokumentierte `sleep_intervals`. **Nicht** mit halber/truncated `sleep_h` trotzdem G1 rechnen. |
| **Marker-Liveness** `STALE` oder `MISSING` | **F3 → FAIL** | [`NEWS_AGENT.md`](NEWS_AGENT.md) (`make news-agent-cron-status`, `WRITER_STALE`) · [`AUDIT_WRITER_LIVENESS.md`](AUDIT_WRITER_LIVENESS.md). **Kein** Cluster-Patch — Host-isoliert. |
| `n_markers < n_min` (nach G4) | **F1 → G1 FAIL** | Urteilszeile dokumentieren. **Keine** Schwelle nachträglich anpassen (A1-Anker: `downtime_h=0`, `interval_min=60` → `n_min=20`). |
| `max_gap_awake_s > 10_800` (nach Sleep-Overlap-Abzug) | **F2 → G2 FAIL** | Einzeln dokumentieren: welches Marker-Paar, `gap_s`, Sleep-Overlap, `gap_awake_s`. **Nicht** `max_gap_s` (roh) für G2 verwenden. |

**G2-Rechnung (manuell):** pro Marker-Paar `gap_awake_i = gap_i − overlap(gap_i, sleep_intervals)`; Sleep-Intervalle aus pmset-Skript (`sleep_interval …`) oder manuellem G4-Protokoll. Vorlage: **§5.2**.

### 5.2 G2 — Awake-Gaps-Tabelle (morgen ausfüllen)

**Schritt A — Sleep-Intervalle** aus Schritt 2 (`news_24h_sleep_from_pmset.py`, Zeilen `sleep_interval …`). **Vor G2:** überlappende Blöcke zur **Vereinigung** zusammenführen (disjunkt machen). Das Skript liefert bereits gemergte Intervalle; bei `sleep_source=manual` selbst mergen.

```text
# Beispiel (Platzhalter — morgen aus pmset-Ausgabe übernehmen):
#   sleep_interval 2026-08-31T22:00:00+00:00 .. 2026-09-01T05:30:00+00:00
S1: [ ________________ , ________________ ]   # start_utc , end_utc (disjunkt)
S2: [ ________________ , ________________ ]   # oder „none“
```

**Schritt B — Overlap-Algorithmus** (disjunkte Sleep-Blöcke `S_k = [s_start, s_end)`):

```text
gap_i       = [ts_i , ts_{i+1})                    # aus §5-Snippet: pair … gap_s
overlap_k   = max(0, min(ts_{i+1}, s_end) − max(ts_i, s_start))   # Sekunden
overlap_i   = Σ_k overlap_k                         # nur gültig wenn S_k disjunkt (nach Vereinigung)
gap_awake_i = max(0, gap_i − overlap_i)           # negativ ⇒ Intervalle nicht disjunkt — neu mergen
```

**Warum Vereinigung + Klemmen:** `pmset` kann Sleep, DarkWake, Standby, PowerNap liefern — ohne Merge zählt `Σ overlap_k` doppelt, `overlap_i` kann `gap_i` übersteigen, `gap_awake_i` negativ. Fehlerrichtung: **zu viel Overlap → kleineres `gap_awake` → falsches G2-PASS** (nicht False-FAIL).

**Schritt C — Tabelle** (`gap_s` aus §5-Snippet `pair …`; `sleep_overlap_s` per Schritt B):

| i | ts_i (UTC) | ts_{i+1} (UTC) | gap_s | sleep_overlap_s | gap_awake_s |
|---|------------|----------------|------:|----------------:|------------:|
| 1 |            |                |       |                 |             |
| 2 |            |                |       |                 |             |
| 3 |            |                |       |                 |             |
| 4 |            |                |       |                 |             |
| 5 |            |                |       |                 |             |
| 6 |            |                |       |                 |             |
| 7 |            |                |       |                 |             |
| 8 |            |                |       |                 |             |
| 9 |            |                |       |                 |             |
|10 |            |                |       |                 |             |
|11 |            |                |       |                 |             |
|12 |            |                |       |                 |             |
|13 |            |                |       |                 |             |
|14 |            |                |       |                 |             |
|15 |            |                |       |                 |             |
|16 |            |                |       |                 |             |

*(Zeilen nach Bedarf ergänzen — typisch ~16–17 Marker-Paare bei Nacht-Sleep.)*

**Schritt D — G2-Urteil:**

```text
max_gap_awake_s = max(gap_awake_s) = ________
G2 ok:  max_gap_awake_s ≤ 10_800   →  ☐ PASS   ☐ FAIL (F2 — Zeile mit max notieren)
```

**Fehlrichtung Roh-Gap:** `max_gap_s` (roh) **≥** `max_gap_awake_s` — Roh-Gap für G2 → höchstens False-FAIL. **Fehlrichtung Doppel-Overlap:** nicht gemergte Sleep-Intervalle → False-**PASS** — deshalb Schritt A (Vereinigung) und `max(0, …)`.

---

## 6. Anti-HARKing

1. **G2** Schwellwert **3 h** (`max_gap_awake_s`) wird **nicht** nach dem ersten Blick angepasst.
2. **G1-A1** Faktor **0,85** und Formel werden **nicht** nach dem ersten Blick auf `n` angepasst.
3. **A1 (2026-08-31)** ist **Messkorrektur vor Gate-Close** (absolut `≥ 20` widersprach §2) — **kein** nachträgliches Senken auf „was wir gerade haben“.
4. **A3 (2026-09-02)** `interval_min` in G1 — **vor** erster Polling-Epoche (§8.6), nicht nach scheinbarem PASS mit `n_min=20`.
5. **A3.1 (2026-09-02)** Schedule als Source of Truth für `interval_min` — **nach** Gate-Close, **vor** Polling-Epoche; keine nachträgliche Umdeutung der A3-Formel.
6. Feed-Struktur (`structure_ok`) bleibt in [`NEWS_FEED_STRUCTURE_PREREG.md`](NEWS_FEED_STRUCTURE_PREREG.md) — dieses Gate prüft nur **Scheduler + Marker-Liveness**.

---

## 7. Nach PASS

- News-Agent bleibt Host-isoliert; Cluster unberührt bis separater Runbook-Schritt.
- PhaseSources (`:06`/`:07`) und `ASTROCORE_PHASE_SOURCES` — erst nach diesem Gate + Fenster W.
- Strang B (`PAPER_SIZING_PREREG.md`) — unabhängig; bereits FROZEN.

---

## 8. Nach FAIL — Neuauflage (nicht dasselbe Fenster retten)

**2026-09-01 (erster Lauf):** Installation kaputt (`launchd` `EX_CONFIG`, Plist-`WorkingDirectory` auf read-only-Pfad). Post-Epoche **0** Scheduler-Marker — das Fenster enthält **keine** Information über Scheduler-Zuverlässigkeit, nur über fehlgeschlagene Installation. Urteil: **FAIL dokumentieren**, nicht retunen.

```text
NEWS_24H_GATE=FAIL n=0 F3=STALE F1=n<n_min
root_cause=launchd_EX_CONFIG scheduler_never_fired_post_epoch
note=window_void_no_G1_information; archive_epoch_2026-08-31T09:00Z
```

**Verboten:** Fenster verlängern · `n_min` senken · manuelle `news-agent-once`-Marker als Scheduler zählen · Auswertung verschieben.

### 8.1 Reihenfolge Neuauflage (vor neuem 24h-Fenster)

Installation und Messung trennen — wie Alterprüfung vor Drift beim Inventar:

```text
1. enable (beschreibbarer Repo-Pfad) + Enable-Guards grün
      → Pfad existiert, beschreibbar, Plist-WD == repo_root()
      → sonst Abbruch (kein neues Fenster)
2. Eine Stunde warten — geplanter :00-Lauf
      → erster post-enable run_marker da?  ja → weiter
      → nein → Installationsproblem, Fenster gar nicht eröffnen
3. NEWS_SCHEDULER_EPOCH_TS = Zeitstempel des ersten bewiesenen Scheduler-Markers
      (nicht vor Schritt 2)
4. 24 h zählen ab Epoche — gleiche G1–G4-Kriterien (§3–§5)
```

**Enable-Guards** (`news_agent_host_cron.py`): Pflicht **vor** Schritt 3 — keine neue Funktion, Konsequenz aus `EX_CONFIG`-Befund. Verhindert, dass ein anderer Pfadfehler denselben Tag erneut verbrennt.

### 8.2 :00-Proof (Scheduler-Beweis, nicht Konfig-Check)

Nach Schritt 1 (`enable` + `status` grün: Plist auf beschreibbarem Pfad, `plist_working_directory == repo_root`, `last exit code ≠ 78`) **warten** — **kein** `kickstart`, **kein** `news-agent-once`, kein manueller Anstoß.

```bash
launchctl print gui/$(id -u)/com.agentx.news-agent | grep "last exit"
tail -1 data/news_scores.jsonl
make news-agent-cron-status
```

| Check | Erwartung | Bei Abweichung |
|-------|-----------|----------------|
| `last exit code` | **`0`** (Erfolg — nicht nur ≠ 78) | Non-Zero → neues Problem; Marker prüfen, **keine** Epoche |
| `news_scores.jsonl` | `source_type=run_marker`, `ts` ≈ volle `:00` | Kein Marker → Installationsproblem, Fenster nicht öffnen |
| `marker_liveness` | **ACTIVE** (`age_s < 2h`) — von STALE gekippt | End-to-End: Fix lebt, nicht nur konfiguriert |

**Epoche:** `NEWS_SCHEDULER_EPOCH_TS` = **exakter** Timestamp des ersten bewiesenen `:00`-Scheduler-Markers (nicht „jetzt", nicht willkürlich). Alte Epoche `2026-08-31T09:00Z` bleibt **VOID/archiviert**.

### 8.3 Plattform-Wechsel Cluster (nach Fenster W — kein Goalpost-Move)

**Befund:** Zwei Ausfallmodi sind Laptop-Eigenschaften (Sleep, APFS/Mount/GUI-Session), keine Bugs. Ein Host-Gate misst mit `sleep_h`/pmset primär **Wachzeit**, nicht Scheduler-Zuverlässigkeit. **Kriterien bleiben** (`run_marker`, Liveness, G1–G4-Intention); nur der **Zeitgeber** wechselt (LaunchAgent → **eigener** Cluster-CronJob, nicht in `regime-swarm-0` verflochten).

**Heute (Host):** §8.2 `:00`-Proof nur als **Pfad-Diagnose** — danach **kein** neues 24h-Fenster auf dem Host.

**Reihenfolge Cluster (Go/No-Go):**

| # | Schritt | Gate |
|---|---------|------|
| 1 | **Egress** — HTTP aus Pod zu CoinDesk + Cointelegraph RSS **mit Scraper-UA** `agent-x-news/0` (nicht nacktes `curl`; Pod hat oft kein `curl`) | Rot → Umzug trägt nicht |
| 2 | Scope: **eigene** CronJob-Ressource + **Datenfluss** (Shared PVC `news_scores.jsonl`; Shadow Evaluator **erst nach** Cluster-Gate PASS — kein Deployment in Phase A) | Architektur geklärt |
| 3 | §8.4 **Phase A** Plumbing, dann **Phase B** autonomes `:00` | siehe unten |
| 4 | **Neues Gate** auf Cluster — `hours_awake=24`, `n_min=20`, G2 ohne Sleep-Overlap, **kein** G4-pmset; Gap-Semantik an K8s anpassen (`startingDeadlineSeconds`, `concurrencyPolicy: Forbid`) | kein Erlass |
| 5 | PASS → Shadow Evaluator erster Live-Lauf (Host-Skript oder später K8s-Deployment — **nach** Gate) | unverändert |

**Nicht verwechseln:** Binance-**WS**-Ausfall (Lab-Listener) ≠ News-**HTTP/RSS**-Egress (grün mit UA).

### 8.4 Cluster — Phase A (Plumbing) vs. Phase B (Gate-Beweis)

**`kubectl create job --from=cronjob/…` ist der Mac-`kickstart` in K8s-Form** — beweist Verdrahtung, **nicht** Scheduler-Zuverlässigkeit. Marker eines manuellen Jobs **zählen nicht** für G1 und dürfen **nicht** `NEWS_SCHEDULER_EPOCH_TS` setzen.

```text
Phase A — Plumbing (jetzt, ohne 24h-Warten):
    CronJob-Manifest deployen (eigene Ressource, nicht regime-swarm-0)
      suspend: true              # Schedule feuert NICHT — nur manueller Job
      concurrencyPolicy: Forbid
      startingDeadlineSeconds: sinnvoll gesetzt (K8s-Skip ≠ launchd-Nachholen)
    kubectl create job …  (manueller Einmal-Job — funktioniert auch bei suspend: true)
    prüfen: Job exit 0, run_marker auf PVC (kubectl logs zeigt run_marker-JSON)
      oder Debug-Pod: PVC mount + tail news_scores.jsonl
    → startet NICHT das Gate, setzt NICHT die Epoche

Phase B — Gate (erfordert Warten):
    suspend: false — CronJob feuert AUTONOM um :00 (kein create job, kein kickstart)
    prüfen: Job-Name vom CronJob-Controller, run_marker ts ≈ :00
    ERST DANN NEWS_SCHEDULER_EPOCH_TS = dieser autonome Marker
    → frisches 24h-Fenster ab Epoche (gleiche G1–G3-Intention, kein sleep_h)
```

**Manifest:** `charts/regime-swarm/templates/news-agent-cronjob.yaml` · `values-news-agent.yaml` · `Dockerfile.news-agent`  
**Phase A Make:** `make news-agent-cluster-build` → `news-agent-cluster-apply` → `news-agent-cluster-plumbing`

| Trigger | Erlaubt für | Verboten für |
|---------|-------------|--------------|
| `kubectl create job` (manuell) | Phase A Plumbing | Epoche, G1-Zählung, Gate-Start |
| CronJob-Controller `:00` (autonom) | Phase B, Epoche, 24h-Gate | — |

**Shadow Evaluator:** erst Live-Lauf nach **sauberem** Cluster-Gate PASS (unverändert).

### 8.5 Hetzner-Host (Produzent-Umzug — Vor Epoche **BLOCKING**)

**Befund:** Sleep, versiegelte Volumes und GUI-Sessions entfallen — der Umzug beseitigt die Host-Ursache, nicht nur Symptome. **Gate-Intention unverändert** (`run_marker`, Liveness, G1–G3); **Zeitgeber** = Linux-Cron auf `65.108.246.89`, Daten: `/root/agent_x_storage/data/news_scores.jsonl`.

#### V1 — Verbraucher-Kopplung (**entschieden: Co-Location Hetzner**)

**Kanonisch (Option A):** Produzent und Gate-Konsument auf **demselben Host** (`65.108.246.89`, lokale NVMe).

```text
[ Hetzner ]
  Cron (:00) → news_agent → /root/agent_x_storage/data/news_scores.jsonl
  Cron/systemd → shadow_evaluator → liest dieselbe Datei (Direct Read)
[ Mac Studio TUI ] → passives Monitoring (SSH tail / rsync) — kein Gate-Konsument
```

| Rolle | Standort | Pfad / Zugriff |
|-------|----------|----------------|
| **News-Agent (Produzent)** | Hetzner | schreibt `data/news_scores.jsonl` |
| **Shadow Evaluator** | Hetzner (nach G1 PASS) | liest `/root/agent_x_storage/data/news_scores.jsonl` lokal |
| **TUI / Monitoring** | Mac | `ssh … tail` oder rsync — **nicht** für Gate-Bewertung |
| **Kind-Cluster CronJob** | Lab (Phase A/B) | separater Pfad; nicht mit Hetzner-Gate vermischen |

**Regel:** Hetzner-G1-PASS zählt nur mit Co-Location — kein Mac-/Cluster-Leser als Gate-Konsument.

#### V2 — Cron-Umgebung (Linux ≠ interaktive Shell)

Cron: minimales `PATH`, kein `PYTHONPATH`, CWD oft `$HOME`. Crontab **absolut** + explizit:

```cron
0 * * * * cd /root/agent_x_storage && PYTHONPATH=. /root/agent_x_storage/venv/bin/python -m services.news_agent.runner --once >> /root/agent_x_storage/logs/audit/news_cron.log 2>&1
```

| Pflicht | Warum |
|---------|--------|
| `cd /root/agent_x_storage` | relative Pfade (`data/`, `config/`) |
| `PYTHONPATH=.` | Modul-Import ohne System-Python-Falle |
| absoluter `venv/bin/python` | nicht `/usr/bin/python3` |
| `--once` | kein Loop im Cron-Kontext |

Smoke aus interaktiver SSH-Shell beweist **nicht** Cron — erst Marker **nach** erstem Cron-`:00` + Syslog (unten).

#### V3 — Git-Governance (Single Source of Truth)

```text
[ Mac Dev ] ──git commit & push──► [ origin/main ] ──git pull──► [ Hetzner Production ]
```

| Schicht | Kanonisch | Regel |
|---------|-----------|--------|
| **Code** | `origin/main` (Git) | Hetzner **PULL-ONLY** — nie editieren/mergen/pushen auf dem Server |
| **Laufzeit-Daten** | Hetzner `/root/agent_x_storage/data/` | Produzent; jeder Zustand = Commit-SHA nach `git pull` |
| **Hetzner** | Execution Target | Reproduzierbarkeit vor Epochenstart |

#### 8.5.1 :00-Proof Linux (Analog §8.2 — Daemon-Beweis)

**Kein** manueller `runner`-Aufruf für Epochen-Anker. Nach erstem vollem `:00`:

```bash
# 1) Cron-Daemon (nicht interaktive Shell)
journalctl -u cron --since "5 minutes ago" | grep -i news_agent
# Alternativ:
grep CRON /var/log/syslog | tail -10

# 2) WORM-Marker
tail -n 2 /root/agent_x_storage/data/news_scores.jsonl

# 3) Log exit 0 (optional)
tail -3 /root/agent_x_storage/logs/audit/news_cron.log
```

| Check | Erwartung |
|-------|-----------|
| `run_marker` `ts` | ≈ volle `:00` UTC |
| `feeds.*.health` | `ok`, `status` 200 |
| `syslog` CRON | Eintrag zum gleichen Zeitfenster |
| `marker_liveness` | ACTIVE (`age_s < 2h`) |

**Epoche:** `NEWS_SCHEDULER_EPOCH_TS` = Timestamp des ersten **Cron**-Markers (nicht Smoke aus SSH). Phase-A-/Cluster-Test-Marker davor = Vorlauf.

#### 8.5.2 G4-Linux (Amendment A2 — vor Epoche, **kein** pmset)

**Problem:** §5/`news_24h_sleep_from_pmset.py` sind macOS-only. Hetzner-Gate ohne A2 → G4 immer **INCOMPLETE** — Gate nie PASS, unabhängig von Markerzahl.

**Äquivalenz:** Auf einem Server gibt es kein Sleep — **Neustart** ist die einzige Größe, die Markerzahl legitim senkt (Cron läuft nicht während der Maschine down ist).

```text
downtime_h        = Σ Neustart-Lücken im Fenster [EPOCH, GATE_CLOSE]
hours_up          = 24 − downtime_h
interval_min      = crontab/launchd (# AGENTX_NEWS_AGENT) — §8.6; env nur Fallback
n_min             = max(1, floor(hours_up × (60 / interval_min) × 0.85))
boot_source       = journalctl | uptime
```

**Anker (A1+A2+A3):** `downtime_h = 0`, `interval_min = 60` → `hours_up = 24` → **`n_min = 20`** — identisch zum eingefrorenen A1-Anker.

**G2:** `downtime_union` ersetzt `sleep_union` bei `gap_awake`-Berechnung (Lücken während Reboot zählen nicht als Scheduler-Fehler).

**Vorab (einmal pro Host):** Journal-Persistenz klären — sonst droht falsches FAIL mit falscher Ursache:

```bash
ls -d /var/log/journal    # vorhanden → persistent; fehlt → nur RAM-Journal
grep ^Storage /etc/systemd/journald.conf
```

Ohne `/var/log/journal` (`Storage` nicht persistent) verliert `journalctl` Vorgänger-Boots nach Neustart → `--list-boots` zeigt nur den aktuellen Boot → `downtime_h = 0` obwohl Neustart im Fenster → fehlende Marker werden dem **Scheduler** zugeschrieben. **Gleiche Fehlerklasse** wie abgeschnittenes pmset — nur umgekehrt begründet.

**Mess-Hierarchie (A2.1):**

| Signal | Rolle | Belastbarkeit |
|--------|-------|----------------|
| **`uptime -s`** | **führend** — Boot-Zeitpunkt | Liegt Boot **in** `[EPOCH, GATE_CLOSE]` → Neustart **ja**, unabhängig vom Journal |
| `journalctl --list-boots` | Ergänzung — Lückenlänge / mehrere Boots | Nur belastbar bei persistentem Journal; sonst max. „Neustart ja/nein" via `uptime -s` |
| `boot_source=manual` | Fallback | Rohausgabe **Pflicht** (s. unten) |

```bash
uptime -s
journalctl --list-boots
# persistent: Boot-Grenzen → downtime_intervals → downtime_h
# volatile:   uptime -s in Fenster? → Neustart ja; Dauer nur wenn anderweitig belegt
```

| Feld | Inhalt |
|------|--------|
| `downtime_intervals` | `[{start_utc, end_utc}, …]` oder `none` |
| `boot_source` | `uptime`+`journalctl`, `uptime` allein, oder `manual` (Fallback) |
| `downtime_h` | Summe im Beobachtungsfenster — **gemessen**, nicht geschätzt |
| `journal_persistent` | `true` / `false` (aus `ls -d /var/log/journal`) |

**Ergebniszeile (Beispiel):** `NEWS_24H_GATE=… boot_source=uptime+journalctl journal_persistent=true downtime_h=0.00 hours_up=24.00 n_min=20 …`

**Manueller Weg (bis Skript existiert):** Ergebnisdokument enthält **nicht nur** `downtime_h=…`, sondern die **Rohausgabe** von `uptime -s` und `journalctl --list-boots` (copy-paste). `boot_source=manual` trägt den Nachweis bei sich — Ableitung ohne Werkzeug nachvollziehbar.

**Coverage:** Bei persistentem Journal muss `--list-boots` das Fenster ab Epoche abdecken; sonst `journal_coverage=insufficient` → **INCOMPLETE**. Bei volatilem Journal: `uptime -s` + dokumentierte Boot-Lücke (Rohausgabe); Dauer ohne Journal nur mit explizitem Beleg.

**Nicht:** `pmset` auf Linux erzwingen oder G4 weglassen — beides würde das Gate strukturell unmöglich machen.

#### 8.6 Polling-Epoche — G1 + Watchdog (Amendment A3, **vor** erstem 5-min-Gate)

**Kontext:** [`H1_M2_EVENT_DRIVEN_SPEC.md`](H1_M2_EVENT_DRIVEN_SPEC.md) §11 — Tag-7 NO-GO → 5-min-RSS **vor** 90-Tage-M2-Sammeln. Eigene **Scheduler-Epoche** (analog §8.5): neues `NEWS_SCHEDULER_EPOCH_TS`, neues 24h-Gate — **nicht** Ad-hoc-Cron ohne Präreg.

| Größe | Stündliche Epoche | 5-min Polling-Epoche |
|-------|-------------------|----------------------|
| Cron / LaunchAgent | `0 * * * *` (:00) | `*/5 * * * *` |
| `interval_min` (G1) | **60** (aus Schedule) | **5** (aus Schedule) |
| `NEWS_SCHEDULER_INTERVAL_MINUTES` | optional; muss Schedule matchen | optional; muss Schedule matchen |
| `WATCHDOG_CRON_INTERVAL_MINUTES` | **60** (WARN 90 / CRIT 150 min) | **5** (WARN 7,5 / CRIT 12,5 min) |
| G1 `n_min` bei `hours_up=24` | **20** | **244** |
| Erwartete Marker (Vollfenster) | ~24 | ~288 |

**G1-Formel (eingefroren A3):**

```text
n_min = max(1, floor(hours_up × (60 / interval_min) × 0.85))
```

**Implementierung:** `services/news_agent/cron_schedule.py` (Schedule → `interval_min`) · `services/news_agent/gate_g1.py` · `scripts/news_24h_sleep_from_pmset.py` (Ausgabe `interval_min=` + `source=`).

**`interval_min`-Quelle (A3.1):** Minute/Stunde der `# AGENTX_NEWS_AGENT`-Zeile (oder LaunchAgent-Plist auf macOS). `NEWS_SCHEDULER_INTERVAL_MINUTES` nur wenn Schedule nicht lesbar; bei Divergenz **WARN** (non-blocking) im Status-Check.

**Epochen-Checkliste (vor Gate-Start):**

1. Cron-Zeile / systemd-Timer auf Ziel-Takt (`0 * * * *` oder `*/5 * * * *`)
2. `WATCHDOG_CRON_INTERVAL_MINUTES` passend setzen (Transport-Schwellen)
3. `make news-agent-cron-status` — `scheduler_interval_min=` + `source=crontab`; Divergenz Env → **WARN** (exit 0)
4. Neues `NEWS_SCHEDULER_EPOCH_TS` setzen (erster **Cron**-Marker der Epoche)
5. 24 h warten — G1–G4 mit passendem **`n_min`** (20 bzw. 244)

**Verboten:** Erstes 5-min-Fenster mit `n_min=20` auswerten und A3 danach als „Korrektur“ einführen — das wäre HARKing am Nachweis-Ende.

##### 8.6.1 Amendment A3.1 — Schedule als Source of Truth (nach Gate-Close)

**Problem (A3 fragil):** Wenn Crontab `*/5` steht, `NEWS_SCHEDULER_INTERVAL_MINUTES=60` aber gesetzt ist, rechnete G1 mit `n_min=20` → PASS bei ~7 % Zuverlässigkeit — derselbe Fehlertyp wie falscher Watchdog-`stale_s`, nur am Nachweis-Ende.

**Lösung:** Crontab / LaunchAgent-Plist ist Source of Truth. Env nur wenn System-Abfrage fehlschlägt.

**Priorität (`get_scheduler_interval_from_system` / `measure_scheduler_interval_minutes`):**

1. Linux/Hetzner: `crontab -l`, Zeile mit `# AGENTX_NEWS_AGENT` — Minute-Feld (`*/5` → 5, `0` + `* *` → 60)
2. macOS: `~/Library/LaunchAgents/com.agentx.news-agent.plist` → `StartCalendarInterval` (stündlich → 60)
3. Fallback: `NEWS_SCHEDULER_INTERVAL_MINUTES`, dann `WATCHDOG_CRON_INTERVAL_MINUTES`
4. Default: **60** (A1-Anker)

**Validierung:** `make news-agent-cron-status` — bei lesbarer Schedule und gesetzter Env **WARN** (non-blocking, exit 0), wenn Werte divergieren. G1 und Cron-Lauf nutzen Schedule; Operator soll Env bereinigen.

**Deploy-Reihenfolge:**

```text
Gate-Close (2026-09-02T12:00:01Z)
  → v1.3 (rss_parser published_at)
  → A3.1 (cron_schedule.py)
  → Polling-Epoche (Tag 7+, neues NEWS_SCHEDULER_EPOCH_TS)
```

**Tests (Pflicht):** Crontab `*/5` → 5 · stündlich `0 * * * *` → 60 · Schedule nicht lesbar → Env · kein Env → 60 · Env≠Schedule → Mismatch-Text.

---

## Siehe auch

- [`docs/V13_DEPLOY_RUNBOOK.md`](V13_DEPLOY_RUNBOOK.md) — v1.3 Deploy **post Gate-Close only**
- [`docs/PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) — Strang B, Gate n≥50
- [`scripts/news_24h_sleep_from_pmset.py`](../scripts/news_24h_sleep_from_pmset.py) — G4 `total_sleep_h` (macOS)
- [`services/news_agent/gate_g1.py`](../services/news_agent/gate_g1.py) — G1 `n_min` (A1+A3)
- [`services/news_agent/cron_schedule.py`](../services/news_agent/cron_schedule.py) — `interval_min` aus Schedule (A3.1)
- §8.5.2 — G4 `downtime_h` (Linux/Hetzner, A2)
- §8.6 — Polling-Epoche `interval_min` + G1-Skalierung (A3)
- §8.6.1 — Schedule Source of Truth (A3.1)
- [`scripts/news_agent_host_cron.py`](../scripts/news_agent_host_cron.py) — LaunchAgent-Plist
