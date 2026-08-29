# Paper Exit Implementation — Pre-Reg

**Status:** FREIGEGEBEN (2026-08-29) · Implementierung auf `feature/exit-implementation`  
**Parent (Theorie + Freeze):** [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md) — Option B, `PAPER_HOLD_SECONDS=4966` (§7 FROZEN · Amendment A1 / 1s-Bars)  
**Scope:** Live-Shadow Paper-Pfad · `live_execution=false` · `order_send=false` · `not_investment_advice=true`  
**Ziel:** Abgeschlossene Round-Trips für B2 (Kelly-Historie) ohne Charter-Bruch

**§7 Amendment A1 (2026-08-29):** Parent-Freeze korrigiert Preisbasis Trade-Tick → 1s last-price Bars. `k=433` ist **superseded** (Mikrostruktur); gültig ist `k=4966`. Das ist Messkorrektur, kein HARKing — siehe Parent §7.1.

Dieses Dokument ist die **technische Umsetzungsspezifikation**. Die wissenschaftliche Basis (Option B, k-Kalibrierung, Anti-HARKing) bleibt in der Parent-Spec unverändert.

---

## 0. Normative Verweise

| Quelle | Inhalt |
|--------|--------|
| Parent §4 / §7 | Option B, `k=4966` (1s-Bars), Freeze-Hash, Anti-HARKing |
| Parent Kostenschwelle | Round-Trip-Boden ≈ 20 bps; Gap-Default 30 s |
| [`POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) §4 | Keine Sizing-/Kelly-Felder in `paper_trades.worm.jsonl` |
| Charter | Paper-only; Single-Position; keine Advisories |

**Env (nach Implementierung):**

```yaml
PAPER_EXIT_MODE: "time_hold"
PAPER_HOLD_SECONDS: "4966"            # FROZEN — Parent §7 Amendment A1 (1s-Bars)
PAPER_MAX_OPEN_POSITIONS: "1"
PAPER_EXIT_GAP_DT_S: "30"             # kein Entry/Exit auf Gap
PAPER_EXIT_MAX_WAIT_S: "24830"        # 5 × 4966 — Max-Warte in EXIT_PENDING
PAPER_POSITION_STATE_PATH: "/data/state/paper_position.json"   # Cluster; lokal: {worm_dir}/state/…
PAPER_EDGES_PATH: "/data/audit/paper_edges.jsonl"             # Cluster; lokal: {worm_dir}/audit/…
# Force-Exit nur explizit:
# HUMAN_FORCE_EXIT=1  (oder API) — nie aus Regime/A7
```

---

## 1. Implementierungs-Invarianten (I1–I6)

### I1 — Single-Position-Gate

Zu keinem Zeitpunkt mehr als **eine** offene Paper-Position.

- `state ∈ {HOLDING, EXIT_PENDING}` → alle neuen Entry-Signale → **BLOCKED**
- Log: `SIGNAL_IGNORED_POSITION_OPEN` bzw. `SIGNAL_IGNORED_EXIT_PENDING`

### I2 — Hold-Timer-Absolutheit

- Timer startet bei **Entry-Tick** (`entry_tick_ts`, Wall-clock **UTC**).
- Läuft absolut **`PAPER_HOLD_SECONDS=4966`** Sekunden.
- **Kein** Reset bei neuem Signal, keine Verlängerung.
- `hold_seconds_actual = exit_tick_ts − entry_tick_ts` (Unix-Zeitdifferenz, **nicht** Tick-Zähler).

### I3 — Exit-Bedingung

Exit nur wenn **alle** gelten:

1. `hold_seconds_elapsed >= 4966`
2. Gültiger Exit-Tick: Δt zum vorherigen Tick **≤ `PAPER_EXIT_GAP_DT_S` (30 s)**
3. Sonst: in `EXIT_PENDING` warten

**Max-Warte (S1):** Wenn nach Hold-Ablauf länger als **`PAPER_EXIT_MAX_WAIT_S = 5 × 4966 = 24830 s`** kein gültiger Exit-Tick kommt → **Alarm** (`EXIT_WAIT_TIMEOUT`), Position bleibt offen, kein automatischer Force-Exit. Fortsetzung beim nächsten gültigen Tick oder `HUMAN_FORCE_EXIT`.

### I4 — WORM-Feld-Erweiterung

`paper_trades.worm.jsonl` — Exit als **`SIM_FILL` mit `side=SELL`** (kein drittes Parallel-Format). Zusätzliche Felder auf der SELL-Zeile:

| Feld | Typ | Bedeutung |
|------|-----|-----------|
| `entry_tick_ts` | ISO-8601 UTC / Unix | Entry-Zeitpunkt |
| `exit_tick_ts` | ISO-8601 UTC / Unix | Exit-Zeitpunkt |
| `hold_seconds_actual` | float | `exit_ts − entry_ts` |
| `hold_seconds_target` | int | `4966` (Freeze A1) |
| `exit_reason` | enum | **`hold_expired` \| `force_exit`** nur |

**Verboten auf Paper-WORM (B1):** `kelly_fraction_computed`, `advisory_position_size`, und alle Sizing-Export-Felder aus Parent-Sizing-Charter. Kelly nur in `/data/audit/position_sizing.jsonl` (Strang B / später).

BUY-`SIM_FILL` (Entry) trägt mindestens `entry_tick_ts` (gleich Tick-`ts`) für Restart-Rekonstruktion.

### I5 — Ledger-Wiring / Kanten-Ledger

Jeder erfolgreiche Exit schreibt:

1. `SIM_FILL` SELL in `paper_trades.worm.jsonl` (mit I4-Feldern + bestehendem `realized_pnl_eur`)
2. **einen** Kanten-Eintrag in **`/data/audit/paper_edges.jsonl`** (Hash-Kette, 1:1 zur SELL-Zeile)

Kanten-Felder (Minimum):

| Feld | Bedeutung |
|------|-----------|
| `edge_id` | fortlaufend / UUID |
| `entry_tick_id` / `exit_tick_id` | Signal-/Tick-IDs |
| `entry_price` / `exit_price` | Mark |
| `pnl_eur` | aus Paper-Ledger (`realized_pnl_eur`) |
| `hold_seconds_actual` | wie WORM |
| `hold_seconds_target` | Freeze-k (4966) |
| `hold_seconds_delta` | `actual − target` (Live-Lücken messbar; B2-Ausschluss wenn \|delta\| > gap) |
| `exit_reason` | `hold_expired` \| `force_exit` |
| `worm_sell_hash` | Hash der zugehörigen SELL-Zeile |
| Charter-Stempel | `live_execution=false`, `order_send=false`, `not_investment_advice=true`, `diagnostic_only=true` |

### I6 — Anti-HARKing

`k=4966` unveränderbar bis neuer WORM-Snapshot + neues Freeze in Parent §7. Keine Anpassung von k an f* / PnL / Edge-Statistik.

---

## 2. Zustandsautomat

### Zustände

| Zustand | Bedeutung |
|---------|-----------|
| `IDLE` | keine offene Position |
| `ENTRY_PENDING` | Entry-Intent, warte auf gültigen Entry-Tick |
| `HOLDING` | Position offen, Hold-Timer läuft (Wall-clock ab `entry_tick_ts`) |
| `EXIT_PENDING` | Hold abgelaufen, warte auf gültigen Exit-Tick (Gap-Schutz) |
| `EXITED` | transient nach Close → sofort `IDLE` |

Persistenz: **`/data/state/paper_position.json`** (B4) — speichert mindestens:

```json
{
  "state": "HOLDING",
  "entry_tick_ts": "2026-08-29T07:00:00.000000+00:00",
  "entry_price": "1850.42",
  "entry_signal_id": "sig-…",
  "hold_seconds_target": 4966,
  "symbol": "ETHUSDT",
  "updated_at": "…"
}
```

`EXITED` wird nicht persistiert (nur `IDLE` / `ENTRY_PENDING` / `HOLDING` / `EXIT_PENDING`).

### Entry-Trigger (B3) — **Tick-1-BUY / Idle-First-Tick**

Explizit und unverändert zur bisherigen Paper-Semantik:

- Aus **`IDLE`**: beim **ersten gültigen Tick** (kein Gap > 30 s zum Vorgänger, bzw. erster Tick nach Idle-Start) → `ENTRY_PENDING` → sofort Entry auf diesem Tick → `HOLDING`.
- Keine zusätzliche Shadow-Notional-Sonderlogik im Exit-Strang (Mengenregel bleibt bestehende Runner-`shadow_notional_eur`).
- Kein Entry aus A7/Regime-Signal.

### Übergänge

```text
IDLE + erster gültiger Tick     → ENTRY_PENDING → HOLDING  (entry_tick_ts gesetzt, BUY SIM_FILL)
HOLDING + elapsed ≥ 4966        → EXIT_PENDING
EXIT_PENDING + gültiger Tick    → EXITED → IDLE            (SELL SIM_FILL + Kante)
```

### Blockaden

| Situation | Verhalten |
|-----------|-----------|
| `HOLDING` + weiteres Signal/Tick-Entry | BLOCKED (I1), Log `SIGNAL_IGNORED_POSITION_OPEN` |
| `EXIT_PENDING` + Entry-Versuch | BLOCKED (I1), Log `SIGNAL_IGNORED_EXIT_PENDING` |
| `ENTRY_PENDING` / Entry und Gap > 30 s | kein Entry auf Gap-Tick; warten |
| `EXIT_PENDING` und Gap > 30 s | kein Exit auf Gap-Tick; warten (I3) |
| `EXIT_PENDING` und Wait > 24830 s | Alarm `EXIT_WAIT_TIMEOUT`; kein Auto-Force-Exit |

---

## 3. Edge-Cases

| ID | Fall | Verhalten |
|----|------|-----------|
| **E1** | Signal/Entry-Versuch während `HOLDING` | BLOCKED (I1); Log `SIGNAL_IGNORED_POSITION_OPEN` |
| **E2** | Entry-Versuch während `EXIT_PENDING` | BLOCKED (I1); Log `SIGNAL_IGNORED_EXIT_PENDING` |
| **E3** | Graceful Shutdown während `HOLDING` | **Kein** Close; Zustand + `entry_tick_ts` in `paper_position.json` persistieren; Timer läuft wall-clock weiter |
| **E4** | Graceful Shutdown während `EXIT_PENDING` | Wie E3; Exit beim nächsten Start fortsetzen |
| **E5** | Gap > 30 s bei Exit | Warten; kein Exit auf Gap-Tick (I3) |
| **E6** | Force-Exit | Nur `HUMAN_FORCE_EXIT` (Env/API); `exit_reason=force_exit`; **nie** aus Regime/A7/Daemon-Heuristik |
| **E7** | Pod-Restart während `HOLDING` | Rekonstruktion aus `/data/state/paper_position.json` (+ Konsistenzcheck mit letztem unpaired BUY in WORM); Hold **ohne Reset** (Wall-clock seit `entry_tick_ts`) |

**B2 — `exit_reason`:** Nur `hold_expired` | `force_exit`.  
`graceful_shutdown` ist **kein** Exit-Grund — Shutdown persistiert Zustand, schließt nicht.

---

## 4. WORM-Schema (SELL-Erweiterung)

Beispiel `SIM_FILL` SELL (Auszug):

```json
{
  "action": "SIM_FILL",
  "side": "SELL",
  "qty": "0.04",
  "price": "1852.17",
  "realized_pnl_eur": "1.75",
  "signal_id": "sig-…",
  "entry_tick_ts": "2026-08-29T07:00:00.000000+00:00",
  "exit_tick_ts": "2026-08-29T08:22:46.500000+00:00",
  "hold_seconds_actual": 4966.5,
  "hold_seconds_target": 4966,
  "exit_reason": "hold_expired",
  "live_execution": false,
  "order_send": false,
  "not_investment_advice": true,
  "scope": "DEFENSIVE_CAUSAL_GROUNDING"
}
```

**Nicht** enthalten: `kelly_fraction_computed` und andere Sizing-Felder.

---

## 5. Smoke-Kriterien (S1–S6)

| ID | Kriterium | Erwartung |
|----|-----------|-----------|
| **S1** | Single-Position-Gate | Zweiter Entry während Hold → BLOCKED; nur eine offene Position |
| **S2** | Hold-Timer-Absolutheit | Entry t=0, „Signal“ t=200 → kein Reset; Exit bei elapsed ≥ 4966 (kein Timer-Reset) |
| **S3** | Gap-Schutz | Exit-Tick mit Δt > 30 s → kein Exit; warten |
| **S4** | Restart-Rekonstruktion | State-Datei `HOLDING` + Restart → Timer fortgesetzt; kein doppelter BUY |
| **S5** | WORM-Vollständigkeit | Jeder SELL trägt I4-Felder; `exit_reason ∈ {hold_expired, force_exit}` |
| **S6** | Ledger-Wiring | Jeder SELL → genau eine Kante in `paper_edges.jsonl` mit `worm_sell_hash` |

Zusätzlich empfohlen: **S3b** Max-Warte → `EXIT_WAIT_TIMEOUT`-Alarm ohne Force-Close; **S6b** Force-Exit nur mit `HUMAN_FORCE_EXIT`.

---

## 6. Charter-Konformität

| Anforderung | Erfüllung |
|-------------|-----------|
| `not_investment_advice: true` | Mechanischer Hold-Timer; keine Advisories; Diagnose-Felder |
| Single-Position | I1 |
| Paper-only | `live_execution=false` / `order_send=false` unverändert |
| Kein Sizing im Paper-WORM | B1 — Kelly nur in Position-Sizing-Audit |
| Anti-HARKing | I6 / Parent §7 |

---

## 7. Implementierungs-Reihenfolge (nach Freigabe)

| Schritt | Inhalt |
|---------|--------|
| 1 | Branch `feature/exit-implementation` |
| 2 | Zustandsautomat + `paper_position.json` Persistenz |
| 3 | Hold-Timer + Gap-Regeln + Max-Warte-Alarm |
| 4 | SELL-WORM-Felder + `paper_edges.jsonl` |
| 5 | Smoke S1–S6 (+ S3b/S6b) |
| 6 | Live-Shadow: Env `PAPER_HOLD_SECONDS=4966`, Round-Trips sammeln bis N≥50 → Strang B (Sizing) |

**Kein Code vor Freigabe dieser Pre-Reg.**

---

## 8. Freigabe-Checkliste

- [x] B1 — kein Kelly im Paper-WORM  
- [x] B2 — `exit_reason ∈ {hold_expired, force_exit}`  
- [x] B3 — Entry = Idle-First-Tick / Tick-1-BUY-Semantik  
- [x] B4 — Persistenz `/data/state/paper_position.json`  
- [x] S1–S5 — Max-Warte, UTC, SIM_FILL SELL, Kanten-Pfad, Human Force-Exit  
- [x] Reviewer-Freigabe → Implementierung (`feature/exit-implementation`)  

---

## Siehe auch

- [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md) — Option B, §7 Freeze  
- [`POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) — B2 / Charter §4  
- [`REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) — Betrieb  
