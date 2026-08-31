# Paper Position Sizing (Strang B) — Pre-Reg

**Status:** ENTWURF (2026-08-31)  
**Erstellt:** 2026-08-31  
**Strang:** Kelly-Boundary-Diagnostik (B0–B8) · **kein** Order-Send · **kein** Signal  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · `order_send=false` · `not_investment_advice=true`  
**Parent:** [`POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) · [`POSITION_SIZING_REGIME_MAPPING.md`](POSITION_SIZING_REGIME_MAPPING.md) · [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md) · [`PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md)  
**Außerhalb:** Kein Code in **diesem** Dokument — aber **Messkorrekturen** (§2.1, §3.7, §4.2) sind vor dem ersten B2-Lauf zu implementieren; danach wären sie Tuning.

---

## 0. Zweck (eine Zeile)

Die **Messmethode** für Kelly-Boundary-Diagnostik (p, b, f*, Schranke) wird **vor dem ersten Auswertungslauf** eingefroren — analog `PAPER_HOLD_SECONDS=4966` vor Deploy. Ergebnisse (f* ≤ 0, LIMIT_EXCEEDED, …) sind **Daten**, keine Tuning-Hebel.

---

## 1. Abgrenzung — was dies NICHT ist

| Nicht | Warum |
|-------|--------|
| Implementierung / PR | Code existiert als Entwurf; Freigabe folgt dieser Pre-Reg |
| Trading-Signal / Allokation | Ausgabe = Belastungsgrenze (`max_notional_before_limit_breach_eur`), keine Empfehlung |
| Paper-WORM-Erweiterung | [`POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) §4.1 — Kelly-Felder **verboten** in `paper_trades.worm.jsonl` |
| Liveness-`run_marker` | Inline-Gate; Lebendigkeit = Aufrufer (Regime-Zyklus), siehe [`AUDIT_WRITER_LIVENESS.md`](AUDIT_WRITER_LIVENESS.md) |
| Nachjustierung nach f* | HARKing — siehe §5 |

---

## 2. Estimand (was p, b und f* bedeuten)

p und b beschreiben **nicht** das Entry-Signal. Sie beschreiben die Verteilung der **k-Schritt-Renditen**, die die **Exit-Regel Option B** erzeugt.

| Größe | Definition (eingefroren) |
|-------|---------------------------|
| **Round-Trip** | BUY → Hold k → SELL mit netto `realized_pnl_eur` (§2.1) |
| **k** | `PAPER_HOLD_SECONDS` (Freeze §3) |
| **Rendite pro Trip** | `profit_fraction = realized_pnl_eur / entry_notional_eur` (Notional **ohne** Gebühr — Nenner unverändert; Zähler netto) |
| **p** | Anteil Trips mit `profit_fraction > 0` im Fenster |
| **b** | `mean(profit_fraction \| win) / abs(mean(profit_fraction \| loss))` — nur wenn §3.7 Mindestbesatz erfüllt |
| **f\*** | Fraktionaler Kelly-Anteil (§4) — **Punktschätzung + Bootstrap-Intervall**, nicht eine Zahl allein |

Exit-Regel ist **Stichprobendesign**. Änderung von k, Gap-Toleranz oder Eligibility **vor** N≥50 ändert den Estimand — verboten ohne neue Spec-Version.

### 2.1 Amendment A1 — netto Trip-PnL (Messkorrektur, kein HARKing)

**Befund (Ist `ledger.py`):** Cash ist korrekt (`sim_buy` belastet `cost = notional + fee`), aber `avg_entry` wird aus **notional** gebildet, `sim_sell` zieht nur die **Exit-Gebühr** ab. Die Einstiegsgebühr (~7,5 bps taker) fehlt in der Trip-PnL.

```text
sim_buy:  cost = notional + fee_eur
          avg_entry ← (… + notional) / new_qty     # fee fehlt im Einstand
sim_sell: pnl = (p − avg_entry) × q − fee_exit   # nur Exit-Gebühr
```

Bei σ_k ≈ 75 bps liegen grob **~4 %** der Trips im Band (−7,5 bps, 0] — zählen als Gewinn, obwohl netto Verlust. **p ist systematisch nach oben verzerrt**; `kelly_raw` reagiert auf p am empfindlichsten. Mehr Round-Trips heilen das nicht (systematische Verzerrung, keine Streuung).

| Option | Fix | Bewertung |
|--------|-----|-----------|
| **A (festgelegt)** | `avg_entry` aus **`cost`** (notional + entry_fee) pro BUY-Zeile | Einstand = volle Anschaffungskosten; `realized_pnl_eur` netto ohne B2-Sonderformel |
| B | B2: `profit_fraction = (realized_pnl_eur − entry_fee_eur) / entry_notional_eur` | Ledger unverändert; zwei PnL-Definitionen (Cash vs. Kelly) |

**Freeze:** Option **A** vor erstem eligible Trip / erstem B2-Lauf. Klassifikation: **Messkorrektur** (wie Trade-Tick → 1s-Bar), nicht Performance-Tuning.

**Nach A1 (Live-Ledger):** `profit_fraction = realized_pnl_eur / entry_notional_eur` mit netto-Zähler.

#### Epochengrenze — ein Estimand im 50er-Fenster

A1 erzeugt eine **PnL-Basis-Grenze**. Bereits vorhandene eligible Trips (~12 Stand ENTWURF) tragen `realized_pnl_eur` nach der **alten** Rechnung (Einstiegsgebühr fehlt); alles nach A1-Deploy rechnet netto. Beide im selben Fenster = zwei Estimands — analog k=433 vs k=4966.

| Weg | Folge |
|-----|--------|
| Neu zählen | ~12 Trips verwerfen, ~10 h Sammelzeit verloren |
| **Rückrechnen (festgelegt)** | Trips behalten; Gate rückt nicht |

**Festgelegt vor erstem B2-Auswertungslauf:** Trips **vor** A1-Deploy werden aus dem WORM **netto nachgerechnet** — `pnl_netto = realized_pnl_eur − entry_fee_eur` (BUY-Fill `"fee_eur"`, Paarung über `signal_id` zum SELL). Trips **danach** entstehen bereits netto (Option A im Ledger). **Beide sind derselbe Estimand.** Die Korrektur ist **exakt** (Subtraktion vorhandener Werte), keine Schätzung — anders als verworfener Positions-Exit, wo ein Preis hätte erfunden werden müssen.

Wer erst beide Varianten rechnet und die bessere f* wählt, verletzt H9–H11. Keine nachträgliche Wahl.

`PAPER_SIZING_A1_EPOCH_TS` = Zeitstempel des A1-Deploys (ISO 8601 UTC, bei Rollout setzen — analog `NEWS_SCHEDULER_EPOCH_TS`). B2 wendet Rückrechnung nur auf SELL-Zeilen mit `ts < PAPER_SIZING_A1_EPOCH_TS`.

---

## 3. Freeze-Tabelle (Parameter)

Alle Werte **vor** erstem Strang-B-Auswertungslauf gültig. Änderung nur via neue Pre-Reg-Version + dokumentierter Messkorrektur (kein Performance-Tuning).

### 3.1 Exit & Stichprobe (Parent-Freeze, hier referenziert)

| Parameter | Wert | Quelle / Hash |
|-----------|------|----------------|
| `PAPER_EXIT_MODE` | `time_hold` (Option B) | [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md) §4 |
| `PAPER_HOLD_SECONDS` (k) | **`4966`** | Parent §7 Freeze 2026-08-29 (1s-Bar Amendment) |
| `price_basis` | `last_price_bar` (bar=1s) | Parent §7 — Messkorrektur, kein HARKing |
| `PAPER_EXIT_GAP_DT_S` | **30** | [`PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md) |
| `PAPER_MAX_OPEN_POSITIONS` | **1** | Parent §4.4 — unabhängige Round-Trips |

**Superseded:** k=433 (Trade-Tick-Basis) — **nicht** für B2-Eligibility.

### 3.2 B2-Fenster & Gate N

| Parameter | Wert | Verhalten |
|-----------|------|-----------|
| `window_size` N | **50** | Rollierendes Fenster der letzten N eligible Renditen |
| `min_trades` N_min | **50** (= N) | `< 50` → `INSUFFICIENT_HISTORY`, **kein** Kelly, **kein** Fallback-p |
| `min_wins` | **5** | `< 5` Gewinne im Fenster → `INSUFFICIENT_HISTORY` (§3.7) |
| `min_losses` | **5** | `< 5` Verluste im Fenster → `INSUFFICIENT_HISTORY` (§3.7) |
| **Gate Strang B** | **n_eligible ≥ 50** | Erst dann Freigabe `POSITION_SIZING_ENABLED=true` (Runbook) |

**Zähler:** `n_eligible_at_freeze_k` — nicht `grep SELL`, nicht WORM-Zeilen, nicht SIGNAL-Events.

### 3.3 B2-Eligibility (drei Bedingungen, konjunktiv)

Ein abgeschlossener Trip zählt **nur**, wenn:

1. `hold_seconds_target == PAPER_HOLD_SECONDS` (**4966**)
2. `exit_reason == hold_expired` (kein `force_exit`, kein Break-Exit)
3. `|hold_seconds_actual − hold_seconds_target| ≤ PAPER_EXIT_GAP_DT_S` (**30** s)

Gemischte k oder gap-gestreckte Holds = **anderer Estimand** → ausgeschlossen.

### 3.7 Mindestbesatz Gewinne **und** Verluste (b-Wächter)

`b ≤ 0` fängt fehlende Gewinne. **Fehlende Verluste** nicht:

- leere Verlustmenge → `mean(loss)` undefiniert;
- **ein** kleiner Verlust → `b` explodiert → `kelly_raw → 1`, `f* → γ` (25 % Kapital) aus **einer** Beobachtung.

**Freeze (konjunktiv zu §3.2):**

```text
n_wins  = |{ profit_fraction > 0 }|  ≥  min_wins  (= 5)
n_loss  = |{ profit_fraction < 0 }|  ≥  min_losses (= 5)
```

Sonst `INSUFFICIENT_HISTORY` — auch wenn `stats_count = 50` und `b > 0`.

### 3.4 Kelly & Schranke

| Parameter | Wert | Rolle |
|-----------|------|-------|
| `risk_limit_fraction` | **0.02** (2 %) | `max_notional_before_limit_breach_eur = capital_eur × 0.02` |
| `gamma_default` | **0.25** | Fallback wenn Regime unbekannt |
| Kapitalquelle | `PaperLedger` mark-to-market | Kein fixes Startkapital |

### 3.5 γ-Regime-Map (eingefroren v0)

| `classified_regime` | `regime_flag` | γ |
|---------------------|---------------|---|
| `STABLE` | 0 | 0.25 |
| `STABLE_SIDEWAYS` | 0 | 0.10 |
| `LOW_LEVEL_DRIFT` | 1 | 0.20 |
| `DRIFT_IID_UNRELIABLE` | 1 | **0.00** (Safe Mode) |
| `HIGH_VOL_TREND` | 2 | 0.40 |
| `HIGH_VOL_TREND_BEARISH` | 2 | 0.35 |
| *unbekannt / fehlend* | — | 0.25 (`gamma_source: default`) |

γ skaliert nur `computed_hypothetical_notional_eur` (Diagnose). Export bleibt **Schranke**, nie Empfehlung.

### 3.6 A7-Trigger (wann B0 rechnen darf)

| # | Bedingung |
|---|-----------|
| T0 | `POSITION_SIZING_ENABLED=true` (nach Gate N) |
| T1 | Regime-Zyklus abgeschlossen (`classified_regime` vorhanden) |
| T2 | **`regime_flag >= 1`** (kein Sizing in STABLE-only-Phasen) |
| T3 | B2 `stats_count >= 50` (sonst hard block) |

---

## 4. Kelly-Formel (eingefroren)

Klassischer Kelly auf Einheits-Rendite b (Gewinn/Verlust-Verhältnis):

```text
kelly_raw = (p · b − (1 − p)) / b
f*        = max(0, γ · kelly_raw)
```

### 4.1 Unsicherheit bei N=50 (Pflicht — vor Daten einfrieren)

Bei n=50 ist f* eine **Punktschätzung** ohne Fehlerbalken:

```text
SE(p) ≈ √(p(1−p)/50) ≈ 0.071   bei p ≈ 0.5
Vorzeichenwechsel kelly_raw bei p = 1/(1+b)  →  p = 0.5 für b = 1
```

p̂ = 0.55 ist von p = 0.48 bei diesem n nicht trennbar. **b** ist wackliger (Quotient zweier Mittel aus je ~25 Beobachtungen, rechtsschief, ein großer Gewinn reicht).

**Freeze — Bootstrap (analog Prefilter-σ-Robustheit):**

| Parameter | Wert |
|-----------|------|
| `bootstrap_B` | **1000** |
| Resampling | Mit Replacement über die **50** eligible `profit_fraction`-Werte |
| Pro Draw | p, b, `kelly_raw`, f* neu rechnen (gleiche Formeln §4) |
| Ausgabe | `f*_point` (Punktschätzung) **+** `f*_p05`, `f*_p50`, `f*_p95` |

Audit-Pflichtfelder (zusätzlich zu Parent §4.2): `kelly_fraction_computed` (= `f*_point`), `kelly_fraction_p05`, `kelly_fraction_p95`, `bootstrap_B`.

### 4.2 Sizing-Gate (B6) — mit Intervall

| Schritt | Formel |
|---------|--------|
| B4 (Diagnose) | `computed_hypothetical_notional_eur = f*_point × capital_eur` |
| Schranke | `max_notional_before_limit_breach_eur = capital_eur × 0.02` |
| Einheiten | `max_units_before_limit_breach = max_notional / price_eur` |

**Sizing-Gate (B6):**

| Entscheidung | Bedingung |
|--------------|-----------|
| `INSUFFICIENT_HISTORY` | `stats_count < 50` · `n_wins < 5` · `n_losses < 5` · `b ≤ 0` · `b` undefiniert |
| `LIMIT_OK` | **`f*_p05 > 0`** **und** `f*_point × capital_eur ≤ max_notional_before_limit_breach_eur` |
| `LIMIT_EXCEEDED` | `f*_p05 > 0` **und** hypothetische Notional (Punktschätzung) **>** Schranke |
| *(sonst)* | `f*_p05 ≤ 0` → kein `LIMIT_OK`/`LIMIT_EXCEEDED` — Kelly-Vorzeichen unsicher; Status bleibt diagnostisch (`kelly_sign_uncertain: true`) |

`LIMIT_OK` nur, wenn die **untere Bootstrap-Grenze** über null liegt — sonst beruht die Schranke auf Rauschen.

Kein Exchange-Send in allen Fällen (`order_send=false`).

---

## 5. Anti-HARKing / Freeze-Gates

| ID | Gate | Regel |
|----|------|-------|
| H1 | **k-Freeze** | `PAPER_HOLD_SECONDS=4966` unveränderbar bis neuer WORM-Snapshot + neues Parent-Freeze — **nicht** an f* / PnL anpassen |
| H2 | **N-Freeze** | `min_trades = window_size = 50` — kein N=30 mit `confidence: LOW` während Gate-Phase |
| H3 | **Kein Fallback-p** | Bei `< 50` eligible: **kein** p=0.5, b=1.0, kein Kelly |
| H4 | **Eligibility-Freeze** | Zähler nur B2-eligible (§3.3) — nicht SELL-Gesamtzahl |
| H5 | **γ-Freeze** | Map §3.5 — nicht nach erstem positivem f* drehen |
| H6 | **Schwellen-Freeze** | `risk_limit_fraction=0.02` — nicht an LIMIT_EXCEEDED-Rate anpassen |
| H7 | **Ergebnis ist Ergebnis** | f* ≤ 0 nach 50 Trips = Befund („Signal ohne Kante nach Kosten"), kein k-Tuning |
| H8 | **Charter** | Keine `advisory_position_size` / Empfehlungsfelder im Audit |
| H9 | **Netto-PnL (A1)** | Ledger: `avg_entry` aus `cost`; WORM-Vorläufe: Rückrechnung §2.1 — **vor** erstem B2-Lauf; nicht nach p̂ tunen |
| H10 | **Bootstrap-Freeze** | B=1000, Perzentile p05/p50/p95 — nicht nach erstem `LIMIT_OK` drehen |
| H11 | **b-Mindestbesatz** | min_wins=min_losses=5 — nicht nachträglich auf 3 senken |

**Erlaubte Messkorrekturen (kein HARKing):** Preisbasis Trade-Tick → 1s-Bar (Parent §7) · **A1 netto Trip-PnL** (§2.1) — beides **vor** erstem B2-Lauf.

---

## 6. Gate n ≥ 50 (Freigabe Strang B)

### 6.1 Primär-Gate

```text
n_eligible_at_freeze_k ≥ 50
```

wobei jeder Zählerstand die drei Eligibility-Bedingungen (§3.3) erfüllt.

### 6.2 Was das Gate **nicht** ist

| Ungültig | Gültig |
|----------|--------|
| ≥ 50 WORM-Zeilen | ≥ 50 **eligible** Round-Trips |
| ≥ 50 BUY-Ticks | ≥ 50 SELL mit `hold_expired` @ k=4966 |
| ≥ 50 SIGNAL-Events | ≥ 50 unabhängige k-Schritt-Renditen |

### 6.3 Zeitliche Erwartung (Planung, kein Erfolgskriterium)

Bei k=4966 s (~82,8 min), max. 1 offene Position: **≈ 50 × 4966 s ≈ 69 h** bis Gate — zzgl. Entry-Lücken. Das ist **Vorlauf**, kein Pass/Fail der Methodik.

### 6.4 Nach Gate-Pass

Erst dann:

- `POSITION_SIZING_ENABLED=true` (Runbook / Helm — **nicht** allein per Env ohne Gate-Nachweis)
- B0–B8-Läufe schreiben **`/data/audit/position_sizing_audit.jsonl`** (Schema Parent §4.2)
- Auswertung f*, LIMIT_OK/LIMIT_EXCEEDED unter **dieser** Pre-Reg — keine Parameteränderung ohne Amendment

---

## 7. Claims (falsifizierbar, nach Daten)

Erst nach Gate-Pass und unter eingefrorener Methodik prüfbar:

| ID | Claim |
|----|--------|
| C1 | Bei n≥50 eligible + §3.7 rendert B2 `p`, `b` ohne Fallback |
| C2 | f*_p05 ≤ 0 → kein `LIMIT_OK` (Vorzeichen unsicher) |
| C3 | `LIMIT_EXCEEDED` nur wenn f*_p05 > 0 **und** f*_point × capital > 2 % |
| C4 | Kein Kelly-Feld in `paper_trades.worm.jsonl` |
| C5 | Nach A1: Trip mit Brutto-Verlust (−7,5 bps netto) zählt nicht als Gewinn |

---

## 8. Freigabe-Checkliste (vor VALIDIERT)

- [ ] **A1** netto Trip-PnL: Ledger-Deploy + `PAPER_SIZING_A1_EPOCH_TS`; WORM-Rückrechnung §2.1 für Trips davor
- [ ] **§3.7** min_wins=min_losses=5 in B2
- [ ] **§4.1** Bootstrap B=1000 + f*_p05/p95 im Audit-Schema
- [ ] Parent-Freeze k=4966 + 1s-Bar unverändert
- [ ] Gate-Zähler `n_eligible_at_freeze_k` definiert (nicht SELL-grep)
- [ ] γ-Map §3.5 eingefroren
- [ ] H1–H11 im Runbook zitiert
- [ ] News-24h-Gate + Paper-Exit-Gate abgeschlossen (Vorbedingung Beobachtung)
- [ ] **Kein** Strang-B-Enable vor n≥50

**Nach VALIDIERT:** Ergebnisse dokumentieren; Parameteränderung nur via **PAPER_SIZING_PREREG v2** + neues Freeze.

---

## Siehe auch

- [`docs/AUDIT_WRITER_LIVENESS.md`](AUDIT_WRITER_LIVENESS.md) — Inline-Gate vs. zeitgesteuert
- [`docs/PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md) — I6 Anti-HARKing k
- [`docs/NEWS_FEED_STRUCTURE_PREREG.md`](NEWS_FEED_STRUCTURE_PREREG.md) — Muster: Methodik vor Messung
