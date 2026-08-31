# News-Agent — 24h Scheduler Gate (LaunchAgent)

**Status:** FROZEN (2026-08-31) — Bestehenskriterien **vor** Auswertung festgelegt  
**Amendment A1 (2026-08-31, vor Gate-Close):** G1 absolut `≥ 20` → **relativ** `n_markers ≥ floor(hours_awake × 0.85)` — Messkorrektur (Widerspruch zu §2 Sleep-Semantik), **kein** HARKing nach Datenblick.  
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
| **Start (Epoche)** | `NEWS_SCHEDULER_EPOCH_TS = 2026-08-31T09:00:00+00:00` |
| **Gate-Close (Auswertung)** | **2026-09-01T09:00:00+00:00** |
| **Dauer** | 24 h |

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

### G1 — Marker-Anzahl (**relativ zu wacher Laufzeit**, A1)

G4 (`total_sleep_h`) muss **vor** G1 bekannt sein (Sleep-Protokoll zuerst).

```text
hours_awake     = 24 − total_sleep_h          # Beobachtungsfenster §1
n_min           = max(1, floor(hours_awake × 0.85))
n_markers_post_epoch ≥ n_min
```

`n_markers_post_epoch` = Anzahl `run_marker` mit `ts ∈ [NEWS_SCHEDULER_EPOCH_TS, GATE_CLOSE]`.

**Anker (A1, keine Lockerung):** Bei `total_sleep_h = 0` gilt `n_min = floor(24 × 0,85) = 20` — **identisch** zur ursprünglichen absoluten Schwelle. A1 macht die 20 schlafabhängig statt fix; wer später „nach Datenblick weichgemacht?“ fragt, findet die Antwort in dieser Zeile.

**Beispiel (ein Nacht-Sleep-Block):** `sleep_h = 7.5` → `hours_awake = 16.5` → `n_min = 14`. Erwartung ~17 Marker (16× :00 + 1 Nachhol) — **PASS**, nicht FAIL.

**Begründung A1:** Absolut `≥ 20` widerspricht §2 (LaunchAgent holt beim Wake **einen** Lauf nach, nicht alle verschlafenen Slots). G2 misst Lücken bereits relativ zur wachen Zeit; G1 zählt jetzt konsistent **Dichte im Wachbetrieb**, nicht gegen ein fixes 24/24-Ziel.

**Verworfen (A1):** `n_markers_post_epoch ≥ 20` absolut — scheitert bei korrektem Scheduler + dokumentiertem Sleep (z. B. `n=17`, `sleep_h=7.5`).

### G2 — Maximale Lücke in **wacher** Laufzeit

```text
max_gap_awake_s ≤ 10_800   (= 3 h)
```

Zwischen zwei aufeinanderfolgenden post-Epochen-Markern, **nur** Intervalle, die **nicht vollständig** in einer dokumentierten Sleep-Phase liegen:

```text
gap_i = ts(marker_{i+1}) − ts(marker_i)
gap_awake_i = gap_i − overlap(gap_i, sleep_intervals)
max_gap_awake = max(gap_awake_i)
```

**Begründung:** Ein verpasstes :00 + ein Nachhol-Lauf ≈ bis 2 h; **3 h** Puffer für Netz/Scheduler-Jitter. Lücken **während** Sleep zählen nicht.

### G3 — Aktuelle Liveness am Gate-Close

```text
marker_liveness.status == ACTIVE
marker_liveness.age_s ≤ NEWS_MARKER_MAX_AGE_S   (Default 2 h)
```

Prüfung: `make news-agent-cron-status` unmittelbar vor/nach Gate-Close.

### G4 — Sleep-Protokoll (Pflicht-Anhang)

Auswertung **muss** eine Sleep-Notiz enthalten (eine Zeile reicht):

| Feld | Inhalt |
|------|--------|
| `sleep_intervals` | Liste `[{start_utc, end_utc}, …]` oder `none` |
| `sleep_source` | **`pmset`** (bevorzugt, maschinenlesbar) oder **`manual`** (nur Fallback) |
| `total_sleep_h` | Summe im Beobachtungsfenster — **gemessen**, nicht geschätzt |

**Herkunft `total_sleep_h`:** `pmset -g log` liefert Sleep-/Wake-Zeitstempel; Ableitung via [`scripts/news_24h_sleep_from_pmset.py`](../scripts/news_24h_sleep_from_pmset.py). **Manuell** nur wenn pmset im Fenster unvollständig ist — dann `sleep_source=manual` in der Ergebniszeile **Pflicht**. Überschätzung von `sleep_h` senkt `n_min` (weicher Nenner) — deshalb pmset vor Handeingabe.

Ohne G4: Auswertung **unvollständig** — kein PASS, auch wenn G1–G3 grün (Lücken nicht attributierbar).

---

## 4. Fail-Bedingungen (disjunktiv)

| ID | Bedingung | Verdict |
|----|-----------|---------|
| **F1** | `n_markers_post_epoch < n_min` (G1 A1, nach G4 `total_sleep_h`) | **FAIL** |
| **F2** | `max_gap_awake_s > 10_800` | **FAIL** |
| **F3** | Gate-Close: `marker_liveness` ∈ {`MISSING`, `STALE`, `UNPARSEABLE`} | **FAIL** |
| **F4** | Kein Sleep-Protokoll (G4) | **INCOMPLETE** (nicht PASS) |
| **F5** | Post-Epochen-Marker mit durchgehend `dead`/`DEGRADED` ohne Recovery | **FAIL** (Scheduler ok, Feed/Transport nicht — separates Ticket) |

**F5** ist **nicht** Teil von G1–G3, aber blockiert Freigabe „Scheduler + Feed gesund“. Mindestens ein Lauf mit allen Quellen `ok` oder `quiet` (nicht `dead`) nach Epoche.

---

## 5. Auswertung morgen (2026-09-01 ~09:00 UTC)

Read-only — kein Cluster, kein Cron-Patch.

```bash
# 1) Scheduler + aktuelle Liveness (G3)
make news-agent-cron-status

# 2) Sleep + G1 n_min (G4 zuerst — Nenner messen, nicht schätzen)
# Bevorzugt: pmset → sleep_h + n_min
PYTHONPATH=. python3 scripts/news_24h_sleep_from_pmset.py | tee /tmp/news_gate_sleep.txt
# Ausgabe z. B.: sleep_source=pmset sleep_h=7.52 n_min=14 intervals=1

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
n_min = max(1, math.floor(hours_awake * 0.85))

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
    for a, b in zip(markers, markers[1:]):
        ta = parse_marker_ts(str(a.get("ts")))
        tb = parse_marker_ts(str(b.get("ts")))
        if ta and tb:
            gaps.append((tb - ta).total_seconds())
    print("gaps_s", [round(g) for g in gaps])
    print("max_gap_s", round(max(gaps)) if gaps else None)
PY

# 3) Sleep-Rohlog (G4 Beleg, Archiv)
pmset -g log | tail -30
```

**Ergebnis** in einer Zeile festhalten, z. B.:

```text
NEWS_24H_GATE=PASS|FAIL|INCOMPLETE n=17 n_min=14 max_gap_awake_s=3600 liveness=ACTIVE sleep_h=7.52 sleep_source=pmset
```

---

## 6. Anti-HARKing

1. **G2** Schwellwert **3 h** (`max_gap_awake_s`) wird **nicht** nach dem ersten Blick angepasst.
2. **G1-A1** Faktor **0,85** und Formel werden **nicht** nach dem ersten Blick auf `n` angepasst.
3. **A1 (2026-08-31)** ist **Messkorrektur vor Gate-Close** (absolut `≥ 20` widersprach §2) — **kein** nachträgliches Senken auf „was wir gerade haben“.
4. Feed-Struktur (`structure_ok`) bleibt in [`NEWS_FEED_STRUCTURE_PREREG.md`](NEWS_FEED_STRUCTURE_PREREG.md) — dieses Gate prüft nur **Scheduler + Marker-Liveness**.

---

## 7. Nach PASS

- News-Agent bleibt Host-isoliert; Cluster unberührt bis separater Runbook-Schritt.
- PhaseSources (`:06`/`:07`) und `ASTROCORE_PHASE_SOURCES` — erst nach diesem Gate + Fenster W.
- Strang B (`PAPER_SIZING_PREREG.md`) — unabhängig; bereits FROZEN.

---

## Siehe auch

- [`docs/PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) — Strang B, Gate n≥50
- [`scripts/news_24h_sleep_from_pmset.py`](../scripts/news_24h_sleep_from_pmset.py) — G4 `total_sleep_h` aus `pmset -g log`
- [`scripts/news_agent_host_cron.py`](../scripts/news_agent_host_cron.py) — LaunchAgent-Plist
