# News-Agent — 24h Scheduler Gate (LaunchAgent)

**Status:** FROZEN (2026-08-31) — Bestehenskriterien **vor** Auswertung festgelegt  
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
| Rechner schläft nachts (z. B. 8 h) | **deutlich weniger** als 24 Marker — **korrekt**, kein Scheduler-Defekt |
| Ein verpasstes :00 bei kurzem Sleep | ein Nachhol-Lauf; Lücke kann **> 1 h**, **≤ 3 h** in wacher Zeit sein |

**Anti-Pattern:** „24/24 oder FAIL“ — verworfen (ignoriert Sleep-Semantik).

---

## 3. Bestehenskriterien (konjunktiv)

Alle **vier** Bedingungen müssen zur Gate-Close-Zeit erfüllt sein.

### G1 — Marker-Anzahl (Schwellwert, nicht Vollzähligkeit)

```text
n_markers_post_epoch ≥ 20
```

`n_markers_post_epoch` = Anzahl `run_marker` mit `ts ∈ [NEWS_SCHEDULER_EPOCH_TS, GATE_CLOSE]`.

**Begründung:** Bei typischem Nacht-Sleep sind 20–22 Marker normal; 24 ist Ideal, kein Pflichtziel.

**Sleep-Korrektur (informativ, kein Nach-Tuning):** Wenn dokumentierte Sleep-Zeit **> 4 h** im Fenster liegt, wird `n_markers` in der Auswertungsnotiz neben `hours_awake ≈ 24 − sleep_h` protokolliert. **G1 bleibt ≥ 20** — keine nachträgliche Senkung auf „was wir gerade haben“.

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
| `source` | `pmset -g log`, `log show`, oder manuell (`Rechner zu`, `Dock`) |
| `total_sleep_h` | Summe im Beobachtungsfenster |

Ohne G4: Auswertung **unvollständig** — kein PASS, auch wenn G1–G3 grün (Lücken nicht attributierbar).

---

## 4. Fail-Bedingungen (disjunktiv)

| ID | Bedingung | Verdict |
|----|-----------|---------|
| **F1** | `n_markers_post_epoch < 20` | **FAIL** |
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

# 2) Marker zählen + Lücken (G1, G2) — aus Repo-Root
PYTHONPATH=. python3 <<'PY'
from pathlib import Path
from datetime import datetime, timezone
from services.news_agent.liveness import (
    load_run_markers,
    measurement_run_markers,
    parse_marker_ts,
    NEWS_SCHEDULER_EPOCH_TS,
)

GATE_CLOSE = "2026-09-01T09:00:00+00:00"
path = Path("data/news_scores.jsonl")
markers = measurement_run_markers(load_run_markers(path))
close = parse_marker_ts(GATE_CLOSE)
markers = [
    m for m in markers
    if (t := parse_marker_ts(str(m.get("ts") or ""))) and t <= close
]
print("n_markers_post_epoch", len(markers))
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

# 3) Sleep-Protokoll (G4) — macOS, manuell anpassen
pmset -g log | tail -30
```

**Ergebnis** in einer Zeile festhalten, z. B.:

```text
NEWS_24H_GATE=PASS|FAIL|INCOMPLETE n=22 max_gap_awake_s=5400 liveness=ACTIVE sleep_h=7.5
```

---

## 6. Anti-HARKing

1. Schwellen **20** und **3 h** werden **nicht** nach dem ersten Blick auf `n` angepasst.
2. Sleep erklärt niedrige Zählung — rechtfertigt **kein** Senken von G1 unter 20.
3. Feed-Struktur (`structure_ok`) bleibt in [`NEWS_FEED_STRUCTURE_PREREG.md`](NEWS_FEED_STRUCTURE_PREREG.md) — dieses Gate prüft nur **Scheduler + Marker-Liveness**.

---

## 7. Nach PASS

- News-Agent bleibt Host-isoliert; Cluster unberührt bis separater Runbook-Schritt.
- PhaseSources (`:06`/`:07`) und `ASTROCORE_PHASE_SOURCES` — erst nach diesem Gate + Fenster W.
- Strang B (`PAPER_SIZING_PREREG.md`) — unabhängig; bereits FROZEN.

---

## Siehe auch

- [`docs/PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) — Strang B, Gate n≥50
- [`scripts/news_agent_host_cron.py`](../scripts/news_agent_host_cron.py) — LaunchAgent-Plist
