# Shadow Hub Wiring — Review-Protokoll (2026-09-26)

**Modul:** `order_execution_engine/`  
**Charter:** `diagnostic_only=true` · `live_execution=false` · `order_send=false`  
**Suite bei Freigabe:** 88/88

---

## Freigegebene Commit-Kette (Boss-Übergabe)

| # | Commit | Kurz | Delta-Zip (Beispielname) |
|---|--------|------|--------------------------|
| 1 | `5cc86419` | Hub: Feed, Reaper-Tick, Journal-Audit | `hub_wiring_commit_*.zip` |
| 2 | `54d18754` | Reaper nur `register_order`; Journal immer | `hub_reaper_journal_fix_*.zip` |
| 3 | `21d39e8e` | `signal_id`-Fallback im Matcher-Reaper; Journal-Test straffer | `hub_signal_id_fix_*.zip` |
| 4 | `51b14e69` | Unabhängiger Fold + inkrementelles Audit | `hub_incremental_audit_*.zip` |
| 5 | `5654634c` | Peak-Invarianten + cursor-sicherer Fold | `hub_peak_cursor_fix_*.zip` |
| 6 | `4a8883db` | Typing/Docstring Findings-Logging + dieses Protokoll | `hub_micro_docs_*.zip` |

Zips sind **Delta-Pakete** (Pfade erhalten) — Auspacken im Repo-Root; Suite braucht den restlichen Kanon (`market_data_feed`, `persistence`, …).

---

## Befunde und Fixes (Kurz)

| Schwere | Befund | Fix-Commit |
|---------|--------|------------|
| 🔴 | Orderbuch-Reaper setzte terminale FAK-Orders auf EXPIRED | `54d18754` (`_registered_only`) |
| 🟡 | Journal-Lücke bei `matcher.signal_id=None` | `54d18754` + `21d39e8e` |
| 🟡 | Audit war nicht unabhängig (`JournalReplay` → `apply_fill`) | `51b14e69` (eigener Fold; Monkeypatch-Zeuge) |
| 🟡 | Jeder Tick spielte das volle Journal neu ab (O(n)/s) | `51b14e69` (Cursor `_audited_upto` + optional Vollaudit) |
| 🔴 | `peak_equity`-Gleichheit: False Positive nach Kurs-Spike | `5654634c` (Floor + Monotonie) |
| 🟡 | Fold-`ValueError` mitten im Batch korrumpierte Cursor | `5654634c` (consume + Finding; SELL-Check vor Cash) |

Mutationstests: neue Tests gegen Vorgänger-Stand rot; Spike-Fall nach `5654634c` grün.

**Fuzz (Nachweis):** 200 Seeds × 60 Schritte = 12.000 Audits; 2 Tokens; Spreads/Tiefen zufällig; UP/DOWN; jedes 7. Audit voll; 0 Fehlalarme.

---

## Offenes Ticket: PeakEvent (Obergrenze)

**Status:** offen (Stufe 2)  
**Warum:** Stufe 1 prüft nur Untergrenze + Monotonie. Ob der Live-Peak *zu hoch* ist (Drawdown-Lockout zu früh), braucht journalisierte Peak-Anhebungen.

**Skizze:** `PeakEvent(marks, journal_pos)` bei jeder Peak-Anhebung; Replay rechnet Equity am Fold-Stand nach; vergleicht Obergrenze.

Relevant sobald Drawdown-Lockout scharf ausgewertet wird. Siehe auch `docs/SHADOW_ENGINE_FOLLOWUPS.md` (PeakEvent-Eintrag).

**Nicht tun:** Peak-Gleichheit Live↔Replay wieder einführen (Spike/Revert = False Positive).

---

## Betriebshinweise

- `ShadowHub.raise_on_divergence=True` (Default): Fail-fast — Feed läuft entkoppelt weiter.
- `False`: Findings (`peak_equity.monotonic`, `journal`) oft nur einmal — **`report.findings` loggen**, nicht nur `ok`.
- `full_audit_every_n_ticks=300` (~5 Min bei 1 s): Kontrolle gegen inkrementellen Drift.
