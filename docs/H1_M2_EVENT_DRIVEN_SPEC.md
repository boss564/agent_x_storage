# H₁ M2 — Event-Driven Exogenous Engine (Spezifikation)

**Status:** PREREG / REIẞBRETT — **kein Live-Run** vor Gate-Close + Daten-Schwelle  
**Datum:** 2026-09-01  
**Parent:** [`H1_NEWS_METHODOLOGY_PREREG.md`](H1_NEWS_METHODOLOGY_PREREG.md) · [`STRATEGY_THESIS.md`](STRATEGY_THESIS.md) · [`NEWS_AGENT.md`](NEWS_AGENT.md)  
**Gate:** [`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md) — Code-Freeze bis `2026-09-02T12:00:01Z`

---

## 0. Zweck

M2 übersetzt die Paradigmenkorrektur in eine **testbare Spezifikation**:

```text
[Exogenes Ereignis E_t] → [Entity & Sentiment] → [Execution Window W_t] → [Order / Sim]
         News JSONL              Filter θ              15m OHLCV              19 bps
```

**M2 beantwortet:** Liefert **echtes** News-Sentiment **saubere** Precision auf eine profitable Tail — nicht nur hohen Recall?

**M1-Maßstab (Ceiling, Cheating):** Oracle auf Dip-Pool: n=341 (18,7%), E[net]=**+27 bps**.  
M2 muss zeigen, dass Live-News diese Decke **annähert**, ohne Look-Ahead und mit akzeptabler Precision.

---

## 1. Architektur (frozen für v1)

```text
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│ news_scores.jsonl   │     │ Event Gate + Asset   │     │ OHLCV 15m (ccxt)    │
│ (diagnostic_only)   │────►│ Map + Sentiment θ    │────►│ Entry/TP/SL/Time    │
└─────────────────────┘     └──────────────────────┘     └─────────────────────┘
         t₀ ingest                  W_t = [t₀, t₀+T_max]        pessimistic
```

| Schicht | Rolle |
|---------|--------|
| **Ingestion** | Ein JSONL-Record ≠ automatisch Trade — Event-Gate zuerst |
| **Signal** | `sentiment_score` + Asset-Match + Impact-Schwelle |
| **Execution** | Preis nur Ausführungsmedium — gleiche Invarianten wie A/B2/H2 |
| **Evaluation** | Precision-Recall **vor** E[PnL] als Primärmetrik |

---

## 2. Vier Kernfragen (vor Code beantwortet)

### 2.1 Was ist ein „News-Event“?

**Definition v1 (eingefroren):** Ein **einzelner** JSONL-Record aus `data/news_scores.jsonl`, der **alle** Bedingungen erfüllt:

| Kriterium | Regel |
|-----------|--------|
| Record-Typ | `source_type != "run_marker"` |
| **Schema** | **`schema == "news_agent_multi/v1.3"`** (hart — siehe §2.1.3) |
| Asset | `target_assets` enthält `BTC` oder `ETH` (Ticker, nicht `GENERAL` allein) |
| Sentiment-Stärke | `\|sentiment_score\| ≥ θ_abs` (Default **0.30**, aus Shadow Evaluator D1) |
| Impact (optional v1.1) | `impact_level ∈ {HIGH, CRITICAL}` oder `impact_score ≥ 0.70` |
| Dedup | Pro `item_id` max. **ein** Event; Burst-Dedup siehe §2.1.1 |

**Nicht** ein Event (v1):

- `run_marker`, leere `target_assets`, nur `GENERAL`/`MACRO` ohne BTC/ETH
- **`schema != "news_agent_multi/v1.3"`** — keine Ausnahme, kein Fallback (§2.1.3)
- `sentiment_score` im Neutralband `(-θ_abs, +θ_abs)`
- Duplikat-URL/`item_id` innerhalb Dedup-Fenster

#### 2.1.3 Schema-Gate v1.3 (Pflicht — nicht im Code „erraten")

M2 wertet **ausschließlich** Zeilen mit `schema == "news_agent_multi/v1.3"` aus.

| Schema | `timestamp` | `published_at` | M2-tauglich |
|--------|-------------|----------------|-------------|
| **v1.3** | immer `t_ingest` | Feed-`published_at` wenn vorhanden | ✅ |
| v1.2 RSS | `t_ingest` | fehlt | ❌ |
| v1.2 Announcement | **`releaseDate` (falsch als timestamp)** | fehlt | ❌ **vermischte Semantik** |

**Warum hart:** In v1.2 bedeutete `timestamp` bei Announcements das **Release-Datum**, bei RSS die **Ingest-Zeit** — dieselbe Spalte, zwei `t₀`-Bedeutungen. Ein Backtest ohne Schema-Filter hätte zwei Semantiken unsichtbar gemischt.

**Regel:** Keine Rekonstruktion aus Feldnamen, kein „wenn `published_at` fehlt, nimm `timestamp`“. v1.2-Zeilen sind für M2 **WORM-historisch**, aber **analyse-exkludiert**.

Deploy von v1.3 auf Hetzner markiert die **Epoche** ab der M2-Daten gültig sind (nach Gate-Close).

#### 2.1.1 Burst-Dedup (Aggregation — explizit abgelehnt in v1)

**v1:** Keine Aggregation („3 News in 15 min“). Jede Zeile = ein Event.  
**Begründung:** Aggregation verschleiert Latenz und Look-Ahead; erst in v2 nach ≥6 Monaten Daten.

**Burst-Schutz:** Wenn zwei Events gleiches `item_id` oder gleiche `url` → zweites ignorieren.  
Wenn ≥3 Events gleicher `source_name` + gleiches Asset innerhalb **5 min** → nur das mit höchstem `|sentiment_score|` behalten (Rest suppress).

#### 2.1.2 Quellen (v1)

| `source_type` | v1 |
|---------------|-----|
| `rss` | ✅ |
| `announcement` | ✅ |
| `regulatory` | ✅ |
| `social` | ❌ (v1.1 — Noise-Risiko) |

---

### 2.2 Was ist das Entry-Fenster?

#### 2.2.1 Zwei Zeitachsen (strukturell — vor Live-Replay klären)

| Anker | Feld | Bedeutung |
|-------|------|-----------|
| **`t_ingest`** | JSONL `timestamp` | Server-Ingest / Scrape-Zeit (RSS: aktuell `now` beim stündlichen `:00`-Cron) |
| **`t_published`** | `published_at` (schema v1.3) | Feed-Veröffentlichungszeit (RSS `pubDate`, Binance `releaseDate`) |

```text
detection_lag = t_ingest − t_published   (wenn published_at vorhanden)
```

**Stündlicher Cron:** Meldung um 10:03 → erst um 11:00 gescraped → `detection_lag ≈ 57 min`.  
Das Fenster `[t_ingest+1min, t_ingest+15min]` misst dann **58–72 min nach Veröffentlichung** — nicht die unmittelbare News-Reaktion.

| Risiko | Konsequenz |
|--------|------------|
| **Falsches Negativ** | „Kein Effekt" obwohl die richtige Aussage lautet: **„mit dieser Latenz nicht messbar"** |
| **Ehrliche Vorhersage** | Bei stündlichem Polling ist sub-15-min-Reaktions-Edge **wahrscheinlich nicht erreichbar** |

**M2 berichtet zwei Arme (beide Pflicht sobald `published_at` existiert):**

| Arm | Entry-Anker | Frage |
|-----|-------------|--------|
| **A — Operational** | `t_ingest` | Was können wir **mit heutiger Infrastruktur** handeln? |
| **B — Sensitivity** | `t_published` | Gibt es **theoretisch** eine Reaktion nahe Veröffentlichung? (Upper bound, nicht deploybar) |

**Stratifizierung (Pflicht):** Alle Events mit `published_at` → `detection_lag` loggen; Auswertung nach Lag-Buckets:

```text
lag < 15 min  |  15–60 min  |  > 60 min
```

Wenn Arm B nur bei `lag < 15 min` Signal zeigt und Arm A nicht → **Infrastruktur-Limit**, keine Hypothesen-Falsifikation.

#### 2.2.2 Fenster-Parameter (eingefroren v1)

**Operational (Arm A):** `t₀ = t_ingest`. Kein Trade vor `t₀`. Kein Trade nach `t₀ + T_max`.

| Parameter | Default v1 | Grid (nur Dev-Set) |
|-----------|----------|-------------------|
| `T_max` | **15 min** | {5, 15, 30} min |
| `Δ_processing` | **+1 min** | {0, 1, 2} min |
| Entry-Preis | Open der ersten 15m-Kerze mit `candle_open ≥ t₀ + Δ` | — |

**Sensitivity (Arm B):** `t₀ = t_published`; gleiche `T_max`/`Δ` — nur wenn `published_at` im JSONL.

**Regeln:**

1. Entry frühestens bei Kerze mit `open ≥ t₀ + Δ_processing`.
2. Bis `t₀ + T_max` kein Fill → Event **expired**.
3. **Non-overlap** wie A/B2/H2.
4. Kein dynamisches Fenster in v1.

```text
t₀ ──Δ──► earliest_entry ───────────────► t₀ + T_max
          [══════ Execution Window W_t ══════]
```

**Infrastruktur-Voraussetzung vor Live-Replay:** RSS-Parser muss `published_at` persistieren (`NewsItem` + JSONL-Feld). Bis dahin: nur Arm A — mit explizitem **Messbarkeits-Vorbehalt** (§2.2.1).

---

### 2.3 Wie definieren wir „Sentiment“?

| Feld | Verwendung v1 |
|------|----------------|
| **Primär** | `sentiment_score` ∈ [−1, +1] (keyword_v1 × confidence) |
| **Richtung** | Long wenn `sentiment_score ≥ +θ_abs`; Short wenn `≤ −θ_abs` |
| **Nicht verwendet v1** | Diskretes `sentiment` ±1 ohne Score; LLM-Scores |
| **Aggregation** | **Keine** Rolling-Mean über mehrere News (v1) — ein Event, ein Score |

**Schwellen (eingefroren für erste M2-Runs — Vorfestlegung):**

```text
θ_abs = 0.30     # |score| ≥ 0.30 → directional
θ_strong = 0.70  # optional Subgruppe (HIGH impact alignment)
```

**Herkunft `θ_abs = 0.30` (nicht aus M2-Daten gefittet):**

| Quelle | Verwendung |
|--------|------------|
| Shadow Evaluator D1 (`SHADOW_EVALUATOR_PREREG.md`) | `sentiment < −0.30` für defensives Z3-Gate (asymmetrisch, negativ) |
| M2-Adaptation | **Bidirektional:** `\|sentiment_score\| ≥ 0.30` — gleiche Größenordnung, **keine** Optimierung auf Live-JSONL |

**Regel bei zu wenig Events (jetzt festgeschrieben):**

```text
Nach 90 Tagen JSONL: gated Events < 200  →  Antwort = „länger warten"
NICHT: θ_abs senken, Grid erweitern, oder Schwellen nachträglich anpassen.
```

Erst nach **180 Tagen** und dokumentierter Begründung darf θ in v2 diskutiert werden — nicht vor erstem OOS-Lauf.

**Richtungs-Invariante:** Short nur wenn explizit in Präreg erlaubt; v1 testet **Long und Short separat** (orthogonal wie B2).

---

### 2.4 Look-Ahead-Bias — harte Regeln

| Gefahr | Gegenmaßnahme |
|--------|----------------|
| News nach Entry sichtbar | Entry nur mit `candle_open ≥ t₀ + Δ` |
| σ aus Zukunft | `sigma_15m = std(returns, 15).shift(1)` |
| `t_published` nach `t_ingest` | `published_at` nur für Arm B / Lag-Stratifizierung; Arm A nutzt `t_ingest` |
| Run_marker / Zukunft | Strikt filtern; chronologisches Replay |
| OOS-Leak | Zeit-Split 60/40, kein Shuffle (§5) |
| Oracle-Labels | Verboten in M2 (nur M1) |
| Uniformes Nullmodell | Strukturierte Injektion §6.2.2 (IAAFT-Prinzip) |

**Bias-Audit (Pflicht vor erstem M2-Lauf):**

1. **Uniform-Null** (§6.2.1): zufällige `t₀` gleichverteilt → E[net] ≈ −19 bps (Pipeline-Integrität).
2. **Strukturierte Null** (§6.2.2): `t₀` aus **empirischer** News-Zeitverteilung (Stunde, Wochentag) → Kostenboden unter Nachrichten-Regime.
3. Jeder Trade: `assert entry_candle_open >= t₀ + Δ`.
4. `detection_lag` pro Event loggen sobald `published_at` verfügbar.

---

## 3. Entry-, Exit- & Risk-Logik (aligned mit A/B2/H2)

| Parameter | Wert v1 |
|-----------|---------|
| Entry | Close der Entry-Kerze (konservativ: **nächste** Kerze Open nach `t₀+Δ`) |
| TP | `P_entry × (1 + k_tp × σ₁₅ₘ)` Long; invertiert Short |
| SL | `P_entry × (1 − k_sl × σ₁₅ₘ)` Long; invertiert Short |
| `k_tp` / `k_sl` | **1.5 / 1.0** (kanonisch, wie M0-Pool) |
| Time Exit | **60 min** (4 × 15m Kerzen) |
| Friction | **19 bps** round-trip |
| Intrabar | Pessimistic — TP+SL gleiche Kerze → SL |

---

## 4. Metriken — Precision-Recall **vor** E[PnL]

M2 darf **nicht** nur E[PnL] optimieren. Primärmetriken:

### 4.1 Ground Truth für „profitable Tail“ (M1-kompatibel)

Ein Event-Trade ist **positiv** (Label=1), wenn:

```text
gross_pnl ≥ +30 bps   (0.003)   innerhalb Time-Exit-Fenster
```

Das ist dieselbe Schwelle wie M1-Oracle — verbindet Ceiling mit Live-Test.

### 4.2 Klassifikationsmetriken

Event löst Trade aus (Prediction=1) wenn Gate + Sentiment passiert.

| Metrik | Formel | Ziel v1 |
|--------|--------|---------|
| **Precision** | TP / (TP + FP) | **≥ 0.25** (jeder 4. Trade trifft Tail) |
| **Recall** | TP / (TP + FN) | Sekundär — hoher Recall ohne Precision ist wertlos |
| **F1** | harmonisches Mittel | Berichtspflicht |
| **Lift vs. Base** | Precision / P(tail) | **≥ 2×** gegenüber unkonditionierter 15m-Baseline |

**FN** = profitable 30m-Bewegungen ohne News-Event (nicht messbar ohne volles Scan — FN nur innerhalb Event-aktiviertem Subset).

### 4.3 PnL-Metriken (sekundär)

| Metrik | Szenario 1 | Szenario 2 | Szenario 3 |
|--------|------------|------------|------------|
| E[PnL_net] | ≥ +10 bps | −5 bis +10 bps | < −5 bps |
| n_trades | ≥ **50** OOS | — | — |
| Sharpe | ≥ 1.0 | — | — |
| vs. M1 Ceiling | ≥ **50%** von +27 bps net | — | — |

**Entscheidungsregel:** Precision-Ziel verfehlt → **Falsifikation**, auch wenn E[PnL] zufällig positiv (Overfitting).

---

## 5. Out-of-Sample-Split

| Set | Zeitraum | Verwendung |
|-----|----------|------------|
| **Train / Dev** | Erste 60% der Events (chronologisch) | Schwellen `{θ_abs, T_max, Δ}` nur hier |
| **OOS Test** | Letzte 40% | **Einmalige** finale Bewertung — nicht nachoptimieren |

**Mindest-Daten vor erstem OOS-Lauf:**

| Schwelle | Wert |
|----------|------|
| Kalendertage JSONL | ≥ **90** |
| Scored Events (nach Gate) | ≥ **200** |
| Events mit Asset BTC/ETH | ≥ **80** |
| OOS Events | ≥ **50** |

Bis dahin: nur **Shadow-Mode** + Synthetic-Injection (§6.2).

### 5.1 Messbarkeits-Vorprüfung — Tag 7 (kein Backtest)

**Zweck:** Entscheiden, ob 90 Tage Sammeln die Frage **überhaupt** beantworten können — **bevor** drei Monate in ein garantiertes Infrastruktur-Null investiert werden.

| Was | Wann | Daten | Output |
|-----|------|-------|--------|
| **Lag-Verteilung** | **~7 Tage** nach v1.3-Deploy | nur `schema==v1.3`, nur `detection_lag` | Median, p90, **Verdict GO/NO-GO** |
| M2 Live-Replay | ≥90 Tage | ≥200 gated Events | Precision-Recall + PnL |

**Warum 7 Tage reichen für Lag:** Die Verteilung wird vom **Polling-Takt** bestimmt, nicht von der Sammeldauer. ~168 Cron-Läufe/Woche → >100 `detection_lag`-Beobachtungen genügen für eine stabile Verteilung.

#### 5.1.1 Schwelle (eingefroren — aus `T_max`, nicht nachträglich bewertet)

Das Einstiegsfenster Arm A kodiert `t₀+1min … t₀+15min` (`T_max = 15 min`, §2.2.2): Die Reaktion soll **innerhalb von ~15 Minuten nach `t₀`** messbar sein. Damit `t₀ = t_ingest` diese Rolle spielen kann, muss Ingest nahe genug an der Veröffentlichung liegen.

**Abgeleitete Go/No-Go-Regel (Tag 7, nur `detection_lag`, kein Preis):**

```text
Median(detection_lag) ≤ 15 min   →  GO   — 90-Tage-Pfad kann die kausale Frage prüfen
Median(detection_lag) >  15 min   →  NO-GO — Polling-Epoche zuerst (§11), kein 90-Tage-Backtest
```

| Konstante | Wert | Herkunft |
|-----------|------|----------|
| `LAG_GO_THRESHOLD_MIN` | **15** | identisch mit `T_max` (§2.2.2) — keine separate Kalibrierung |
| `LAG_MIN_OBSERVATIONS` | **100** | Mindest-n für Verdict (sonst `INSUFFICIENT_DATA`) |

**Vorhersage (stündliches Polling, uniforme Veröffentlichungen):** Erwarteter Median ≈ **30 min** → **NO-GO**. Der Report **bestätigt oder widerlegt** diese Vorhersage — er ist eine Prüfung mit Ausgang, keine Ablesung mit anschließender Bewertung.

**Begründungskette bei NO-GO (nicht neu interpretieren am Tag 7):**

```text
Median(detection_lag) > 15 min  UND  Effekthorizont ≈ T_max
  → 90 Tage Sammeln erzeugen ein garantiertes Infrastruktur-Null
  → Aussage: „mit diesem Polling nicht messbar" — nicht „News tot", nicht widerlegt
  → Nächster Schritt: Polling-Epoche (§11), nicht θ/T_max anfassen
```

**§11-Entscheidung ohne 90-Tage-Warte:** Der Tag-7-Lag-Report genügt allein — Median vs. `LAG_GO_THRESHOLD_MIN` (15 min, aus `T_max`). Die 90-Tage-Schwelle (§4.2) gilt für **M2-OOS-Replay**, nicht für die Polling-Epoche. Bei erwartetem Median ≈ 30 min (stündlich) ist die Lage **vorregistriert NO-GO**; der Report bestätigt oder widerlegt die Vorhersage, er erzeugt sie nicht erst.

**Kein Input aus M2-Shadow-Diagnostik:** `alpha_decay_diagnostic.decay_curve_bps` (λ-Fit auf OHLCV) ist **kein** Beleg für §11 — insbesondere keine Hochrechnung „bei 0s wären es X bps" für schnelleres Polling (`curve_disclaimer` im Shadow-Report). Die Taktänderung braucht keine Rechtfertigung aus M2-Daten; sie ist die **Voraussetzung** dafür, dass überhaupt Events im interessanten Lag-Bereich liegen.

**Reihenfolge bei NO-GO (nicht umkehren):**

```text
Tag-7 NO-GO  →  Polling-Epoche (§11, z. B. 5 min)  →  neue Epoche  →  dann 90-Tage-M2-Sammeln
NICHT: 90 Tage in [600s, 2400s]-Lag-Träger sammeln und danach Polling ändern
```

Nach 5-Min-Polling verschiebt sich der beobachtete `detection_lag`-Träger typischerweise von ~`[600s, 2400s]` auf ~`[0s, 300s]`; was unter stündlichem Takt `extrapolated: true` trägt, wird dort gemessen.

#### 5.1.2 p90 (Pflicht-Metrik, kein zweites Gate)

**p90(`detection_lag`)** wird mitgeführt und persistiert — **ohne** eigenes Go/No-Go-Kriterium.

| Situation | Lesart |
|-----------|--------|
| Median ≈ 30 min, p90 ≈ 55 min | Typisch stündlich — enge Basis, moderate Ausreißer |
| Median ≈ 30 min, p90 ≫ 3 h | Gleicher Median, aber **breite Streuung** — Lag-Stratifizierung (§2.2.1) später wichtiger |

p90 dient der Streuungsdiagnose und der späteren Schichtung nach Lag-Buckets; der **Verdict** folgt allein dem Median gegen `LAG_GO_THRESHOLD_MIN`.

#### 5.1.3 `published_at`-Abdeckung (Pflicht — Nenner sichtbar)

Nicht jede v1.3-Zeile trägt ein brauchbares `published_at` (fehlendes `pubDate`, unparsbares Format, Feed ohne Feld). Diese Zeilen haben `detection_lag = null` und **fallen aus der Median-Berechnung** — still, wenn der Nenner fehlt.

**WORM-Regel:** Der Nenner gehört neben das Ergebnis. Der Tag-7-Report **muss** vor Median/p90 folgende Felder enthalten:

```json
{
  "n_items_total": 412,
  "n_with_published_at": 247,
  "n_with_lag": 247,
  "lag_coverage": 0.60,
  "coverage_by_source": {
    "CoinDesk": 0.98,
    "Cointelegraph": 0.95,
    "Binance": 0.02
  },
  "median_lag_by_source": {
    "CoinDesk": 28.5,
    "Cointelegraph": 31.2,
    "Binance": null
  }
}
```

| Feld | Definition |
|------|------------|
| `n_items_total` | Alle v1.3-Zeilen (ohne `run_marker`) |
| `n_with_published_at` | Zeilen mit nicht-leerem `published_at` |
| `n_with_lag` | Zeilen mit nicht-null `detection_lag` (Median-Nenner) |
| `lag_coverage` | `n_with_published_at / n_items_total` |
| `coverage_by_source` | pro `source_name`: Anteil mit `published_at` |
| `median_lag_by_source` | pro `source_name`: Median `detection_lag` in Minuten (`null` wenn keine Beobachtungen); gleiche Schlüssel wie `coverage_by_source` |

**Lesart:** Median über 60 % der Daten ist nicht derselbe Median wie über 100 %; niedrige `coverage_by_source` bei einer Quelle → quellenverzerrter gepoolter Median. Gepoolter Median verdeckt zudem unterschiedliche effektive Latenzen (RSS vs. Announcements, anderer Abfragepfad). `median_lag_by_source` ist die Aufteilung für spätere Lag-Stratifizierung (§2.2.1) — **Verdict** bleibt am gepoolten Median (§5.1.1).

**Kein zusätzliches Go/No-Go-Gate in v1** (optional in v1.1): Abdeckung ist **sichtbar**, bevor jemand den Median liest. `LAG_MIN_OBSERVATIONS` gilt weiter nur für `n_with_lag`.

**Keine Gate-Änderung:** Lesender Report auf WORM-JSONL, kein manueller `runner --once`, kein Trading.  
Artefakt: `results/h1_m2_detection_lag_report.json` (Skeleton: `--lag-report`).

---

## 6. Implementierungs-Stufen (nach Gate-Close)

### 6.1 Skeleton (jetzt erlaubt)

- [`scripts/backtest_h1_news_m2_skeleton.py`](../scripts/backtest_h1_news_m2_skeleton.py)
- Typed Data-Loader + Alignment-Engine + Bias-Assertions
- **Kein** Performance-Report, **kein** Hetzner-Deploy

### 6.2 Synthetic-Injection Dry Run (vor Live-Daten)

#### 6.2.1 Uniform-Null (Pipeline-Integrität)

- Zufällige `t₀` gleichverteilt über OHLCV-Indizes (≥1000 Events)
- Erwartung: E[gross] ≈ 0, E[net] ≈ −19 bps
- **Beweist:** Kein Schein-Alpha aus der Pipeline

#### 6.2.2 Strukturierte Null (IAAFT-Prinzip)

**Problem:** Echte News ballen sich um Handelszeiten / Ankündigungstermine (hohe Vol, breite Spreads).  
Uniform-Null **unterschätzt** Kosten zum Zeitpunkt echter Events.

**Lösung:** Injektions-`t₀` aus der **empirischen Verteilung** der News-Events ziehen:

```text
(t_hour, t_weekday) ~ Empirie(news_scores.jsonl.t_ingest)
→ zufälliger Kalendertag im OHLCV mit gleicher Stunde/Wochentag
```

Fallback wenn `< 30` Events: **Cron-Proxy** — nur `:00`-Minuten (stündliches Polling).

| Metrik | Uniform-Null | Strukturierte Null |
|--------|--------------|-------------------|
| Erwartung E[net] | ≈ −19 bps | ≤ Uniform (Kosten ≥ uniform) |
| PASS | \|E[gross]\| < 5 bps | E[net] ≤ Uniform + 5 bps |

Strukturierte Null ist die **ehrliche Negativkontrolle** für M2-Live-Replay — nicht der Uniform-Lauf allein.

#### 6.2.3 Live-Replay blockiert bis

- [x] `published_at` im JSONL (lokal v1.3; Deploy nach Gate-Close)
- [ ] v1.3 auf Hetzner deployed → Schema-Gate aktiv
- [ ] Tag-7-Lag-Report (§5.1) — Messbarkeits-Entscheid
- [ ] Strukturierte Null PASS auf beiden Assets
- [ ] ≥90d v1.3-JSONL, ≥200 gated Events

### 6.3 M2 Live-Evaluator (nach Daten-Schwelle)

- Replay `news_scores.jsonl` chronologisch
- Shadow-Mode: `diagnostic_only=true`, `order_send=false` (bestehende Invariante)
- Output: `results/h1_m2_live_replay_summary.csv` + Precision-Recall-Report

---

## 7. Gate-Disziplin

```text
BIS Gate-Close (2026-09-02T12:00:01Z):
  ✅ Spezifikation (dieses Dokument)
  ✅ Skeleton + Synthetic-Injection lokal
  ❌ Kein manueller runner --once auf Hetzner (Gate TABU)
  ❌ Kein Live-M2-Replay auf Produktions-JSONL als „Ergebnis“

NACH Gate-Close + G1-PASS + ≥90d JSONL:
  ✅ M2 Live-Replay Shadow
  ✅ OOS einmalig
```

---

## 8. Artefakte

| Artefakt | Pfad |
|----------|------|
| M2 Spezifikation | `docs/H1_M2_EVENT_DRIVEN_SPEC.md` (dieses Dokument) |
| Skeleton | `scripts/backtest_h1_news_m2_skeleton.py` |
| Synthetic-Injection Report | `results/h1_m2_synthetic_injection.csv` (nach Dry Run) |
| Live Replay Summary | `results/h1_m2_live_replay_summary.csv` (später) |

---

## 9. Infrastruktur-Voraussetzungen (vor Live-Replay — blockierend)

| # | Item | Status | Blocker für |
|---|------|--------|-------------|
| 1 | `published_at` + einheitliches `timestamp=t_ingest` | ✅ lokal v1.3, **Deploy nach Gate-Close** | Arm B, `detection_lag` |
| 2 | **Schema-Gate** `news_agent_multi/v1.3` only | ✅ Spec §2.1.3 | Vermischte v1.2-Semantik |
| 3 | Tag-7 **Lag-Report** (§5.1) | ⏳ nach Deploy + 7d | §11 Polling-Epoche **oder** GO für 90-Tage-Pfad |
| 4 | Strukturierte Null PASS | ⏳ | Ehrliche Kostenbasis |
| 5 | ≥90d v1.3-JSONL, ≥200 gated Events | ⏳ **nach** GO oder **nach** Polling-Epoche bei NO-GO | OOS M2-Lauf |

## 11. Abtasttakt — eigentlicher Hebel (post-Gate, eigene Epoche)

**These:** Der Engpass ist **Latenz**, nicht Backtest-Design. Die §11-Entscheidung folgt aus dem **Tag-7-Lag-Report** (§5.1.1) — nicht aus 90-Tage-M2-Daten und nicht aus `alpha_decay_diagnostic`.

| Polling | Erwarteter Median `detection_lag` (uniform pub) | vs. `T_max=15 min` |
|---------|--------------------------------------------------|---------------------|
| Stündlich (`:00`) | **~30 min** | Arm A misst 45–75 min nach Veröffentlichung |
| Alle 5 min | **~2,5 min** | Arm A kann Reaktionsfenster treffen |

RSS-Feeds vertragen 5-Min-Polling ohne neue Abhängigkeit. **Keine** Hypothesen- oder Auswertungsänderung — nur Infrastruktur. **G1** skaliert mit (`NEWS_24H_SCHEDULER_GATE` §8.6, Amendment A3): `n_min=244` bei 5 min — nicht `n_min=20` der stündlichen Epoche.

**Watchdog (Transport):** `scripts/watchdog_news_ingestion.py` leitet WARN/CRITICAL aus `WATCHDOG_CRON_INTERVAL_MINUTES` ab (1,5× / 2,5×). Bei Epochenwechsel auf 5 min → `WATCHDOG_CRON_INTERVAL_MINUTES=5` (7 / 12 min) — keine separaten Schwellen-Tuning-Schritte.

**Warum nicht jetzt:**

- Berührt **24h-Scheduler-Gate** der **stündlichen** Epoche (`n_min=20` bei `interval_min=60`, Epoche `c8755c2e`)
- Erfordert **neue Epoche** + Präreg **A3** ([`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md) §8.6), nicht Ad-hoc-Cron-Änderung

**Reihenfolge nach Gate-Close + G1-PASS:**

1. v1.3 deployen → Tag-7-Lag-Report (§5.1.1) — **§11-Entscheidung hier, nicht nach 90 Tagen**
2. Verdict **NO-GO** (`Median > 15 min`): **Polling-Epoche** (5 min) **vor** 90-Tage-M2-Sammeln — sonst drei Monate im falschen Lag-Träger
3. Verdict **GO** (`Median ≤ 15 min`): 90-Tage-Fenster für M2-OOS öffnen

## 12. Offene Punkte (v1.1 — nicht blockierend für Spec)

1. Neo4j Entity-Graph als zusätzlicher Asset-Resolver
2. On-Chain-Events (x402/Nansen) als zweite Exogen-Quelle
3. Burst-Aggregation „N News in T“ als separater Testarm
4. Sub-stündliches Polling — siehe §11 (eigene Epoche)

---

## 13. Changelog

| Datum | Eintrag |
|-------|---------|
| 2026-09-01 | M2-Reißbrett v1 — vier Kernfragen, Precision-Recall, OOS, Gate-Disziplin |
| 2026-09-01 | Synthetic-Injection Uniform-Null PASS (BTC/ETH, n=1000, E[net]≈−19 bps) |
| 2026-09-01 | `published_at` + `detection_lag` in JSONL (schema v1.3) — lokal, Deploy nach Gate |
| 2026-09-01 | §2.1.3 Schema-Gate v1.3; §5.1 Tag-7-Lag-Report; §11 Abtasttakt post-Gate |
| 2026-09-01 | §5.1.1 Median ≤15 min → GO (aus `T_max`); p90 diagnostisch; Vorhersage NO-GO bei Stunden-Cron |
| 2026-09-01 | §5.1.3 `published_at`-Abdeckung + `coverage_by_source` im Lag-Report (Nenner sichtbar) |
| 2026-09-01 | §5.1.3 `median_lag_by_source` neben Coverage (gleiche Schlüssel, Verdict gepoolt) |
| 2026-09-02 | §5.1: Tag-7 genügt für §11; NO-GO = nicht messbar (nicht widerlegt); Polling vor 90-Tage-Sammeln; kein α-decay-Input |
