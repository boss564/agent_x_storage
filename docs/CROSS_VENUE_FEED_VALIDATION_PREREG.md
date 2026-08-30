# Cross-Venue Feed Validation — Pre-Reg

**Status:** FREIGABE (2026-08-29) · Konnektivität only · **kein Code vor diesem Commit auf main**  
**Parent:** [`PAPER_FEED_GAP_DELTA_CONCORDANCE_PREREG.md`](PAPER_FEED_GAP_DELTA_CONCORDANCE_PREREG.md) · [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md)  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · `order_send=false` · `not_investment_advice=true`  
**Nicht Scope:** Arbitrage · Spread-/Preisvergleich · Signal-Gates auf Kursabweichung · Multi-Asset-Portfolio · Eingriff in Paper-Exit / Edges / k · Fenster W der Konkordanz-Studie · **Deviation-Strang** (`CROSS_VENUE_DEVIATION_PREREG.md` — erst nach Shadow-Validierung der 2×2)

**Branch (Implementierung nach diesem Commit):** `feature/cross-venue-connectivity` — Scope = Konnektivität only (kein Preis-Vergleich).

**Review-Amendments:**  
Runde 2 — H1/`p_NN` gestrichen · LL-Onset · Faktor ≤1.5 · H2-Prioritätskette.  
Runde 3 — **V2 = Coinbase eingefroren** · Denomination dokumentiert · Pyth nur §9.2-Fallback · Deviation-/15-bps-H1 bleibt verworfen (§0 / §9.1), eigener Follow-up-Strang.

---

## 0. Verworfener Alternativ-Claim (explizit)

Ein früherer Skizzen-Claim („Primärkurs weicht &gt; 0,15 % vom Sekundärkurs → Z3 blockiert Signal“) ist **nicht** Gegenstand dieser Pre-Reg:

| Problem | Warum verworfen |
|---------|-----------------|
| Nutzt **Preise** über Venues | Verletzt Charter-Zweckbindung (§5); Infrastruktur sähe aus wie Arbitrage-Rohstoff |
| Schwelle „kalibrieren“ nach historischen Deviation-Perzentilen | HARKing-Risiko; ε nach Datenblick |
| Koppelt an Exit-FSM / Signal-Freigabe | Stört laufendes Exit-Sample und Fenster W |
| Keine 2×2-Trennschärfe | Liefert keine Diagnose „wo hängt der Feed?“ |

Dieser Entwurf folgt dem **Unabhängigkeits-Einwand** aus der Feed-Gap-Korrektur: echte zweite Schicht = **zweiter Venue**, gemessen an **lokaler Empfangszeit**, Claim = **Konnektivitäts-2×2**, nicht Kurs-Diff.

---

## 1. Ziel und Claim

**Ziel:** Venue- vs. lokale Störungen unterscheidbar machen — die Trennschärfe, die `tick_spacing` gegen `hold_delta` nicht liefern konnte (beide aus derselben Reihe).

**Claim (prüfbar):** Über ein **eigenes** Beobachtungsfenster W_xv klassifizieren Empfangs-Lücken auf zwei unabhängigen Trade-Streams (gleiche Liquiditätsklasse) eine **2×2**; die tragende Hypothese ist **H2** (prioritätsgeordnete Verdicts inkl. Onset-Versatz auf LL). Instrumentierung allein („zwei Feeds laufen“) ist kein Claim.

**Kein Claim:**

- keine Arbitrage-Erkennung  
- keine Preisdifferenz, kein Spread, kein Mid, kein `deviation_pct`  
- keine Multi-Exchange-Orderausführung  
- keine Änderung an `PAPER_HOLD_SECONDS` / Edges-Eligibility / Strang B  
- **kein** konfirmatorisches Urteil über `p_NN` (zu träge / nicht falsifizierbar unter realistischen Ausfällen — siehe §4)

---

## 2. Die 2×2 (eigentlicher Gewinn)

Pro Auswertungs-Slot (feste Rasterlänge `slot_s`, Default **10 s**, lokal UTC):

| Binance (V1) | Venue 2 (V2) | Zelle | Schluss (Roh) |
|--------------|--------------|-------|----------------|
| Lücke | Lücke | **LL** | gemeinsame Ursache *oder* Koinzidenz (siehe §2.1) |
| Lücke | keine | **LN** | venue-/verbindungsseitig Binance |
| keine | Lücke | **NL** | Venue-2-seitig (Kontrollfall) |
| keine | keine | **NN** | Feed sauber |

„Lücke“ in einem Slot = mindestens ein Gap-Event dieses Venues **überlappt** den Slot (§3).

Auswertung zählt **Slot-Zellen**, nicht Roh-Ticks.

### 2.1 LL-Verzerrung und Onset-Versatz (Review-Punkt 2)

Ein Gap-Event ist per Definition breiter als `gap_dt_s` (Default 30 s); das Slot-Raster ist 10 s. Jedes Ereignis bemalt daher **≥ 3–4 Slots**. Zwei *unabhängige* Störungen, die zufällig nahe beieinander liegen, erzeugen LL-Slots, obwohl keine gemeinsame Ursache vorliegt. Die Verzerrung begünstigt **COLLAPSED** („Venue-Trennung liefert wenig“) — genau gegen die Trennschärfe.

Feineres Raster heilt das nicht (Breite kommt vom Event).

**Zusatzfeld (normativ, pro LL-Slot bzw. pro LL-Ereignispaar):**

```text
onset_skew_s = | gap_start_recv[V1] − gap_start_recv[V2] |
```

wobei Zuordnung bei mehreren Gaps im Slot: die beiden Events mit **minimalem** `onset_skew_s` unter allen V1×V2-Paaren, die den Slot überlappen (beste Koinzidenz-Kandidatur).

| Onset-Muster | Lesart |
|--------------|--------|
| `onset_skew_s` klein (Häufung nahe 0 relativ zur Eventbreite) | gemeinsame Ursache plausibel |
| `onset_skew_s` streut über Sekunden bis Eventbreite | eher Koinzidenz |

`onset_skew_s` und seine Verteilung über LL-Slots sind **deskriptiv auszuweisen** und gehen in die H2-Entscheidung ein (§4.2). Ohne Onset-Feld ist LL nicht prüfbar.

---

## 3. Definitionen (vorab)

### 3.1 Venues — Freeze vor Capture (Runde 3)

| ID | Venue | Stream | Liquiditätsklasse |
|----|-------|--------|-------------------|
| **V1** | Binance Spot | `ETHUSDT` Trade-WS (läuft, Live-Shadow) | high |
| **V2** | **Coinbase** (Entscheidung B) | Advanced Trade WS **`ETH-USD`** match/trades, read-only | high |

**Freeze-Satz (verbindlich bis Amendment):**

```text
V1:            Binance ETHUSDT (WS)
V2:            Coinbase ETH-USD (WS Advanced Trade)
Denomination:  USD (V2) vs USDT (V1) — Stream-Identität nur;
               in DIESER Pre-Reg kein Preis-/Basis-Normalband
               (Preise verboten, §5). FX-/Stablecoin-Basis ist
               Gegenstand einer allfälligen Deviation-Pre-Reg (§9.1), nicht hier.
gap_dt:        30 s / 30 s (Default) bzw. Regel 1 + Faktor ≤1.5 (§3.3)
Pyth:          nicht V2; nur Fallback-Kandidat (§9)
```

**Begründung V2 = Coinbase (Ausschluss Pyth als Primär-V2):**

1. **Unabhängigkeit:** eigener Orderbuch-/Matching-/Infrastrukturbetrieb. Pyth aggregiert Contributor-Quotes, die indirekt Binance spiegeln können → Self-Reference im Zielszenario (Binance-Störung): Validator partiell blind (still). Coinbase-Fehlalarm ist fail-closed und über Dual-Zähler (NL) sichtbar.  
2. **Kontinuierliche Trade-Ticks:** WS Last-Trades, gleiche Liquiditätsklasse → Gap-Schwellen vergleichbar; Reconnect/Gap-Muster aus `feed.py` wiederverwendbar.  
3. **Semantik:** echte Cross-Venue-Konnektivität (CEX↔CEX), nicht Venue-vs-Oracle.

Kein Trade-Endpoint, keine Order-Keys (`assert_no_order_urls`).

### 3.2 Lücken auf **lokaler Empfangszeit**

```text
t_recv = UTC wall clock when payload is accepted in-process
         (not exchange event time T / E / publish_time)
```

Gap-Event Venue X:

```text
gap  ⇔  t_recv_i − t_recv_{i−1}  >  gap_dt_s[X]
```

Börsenzeitstempel dürfen **nicht** auf Audit-Zeilen stehen (Preisverbot erweitert: keine fremden Uhren als Gap-Input). Optional nur in Ops-Logs außerhalb der JSONL-Auswertung.

### 3.3 Schwellen — Freeze-Regel inkl. Faktor-Gate (Review-Punkt 3)

Die 30-s-Schwelle stammt aus Binance-ETHUSDT / Exit-Gap-Filter. Ungleiche je-Venue-Schwellen verzerren genau H2: größeres `gap_dt[V2]` → NL untererfasst, LN übererfasst → „Binance ist die Störquelle“ als Artefakt.

**Vor Capture (Reihenfolge):**

1. **Bevorzugt:** Beide high-liquidity Trade-Streams →  
   `gap_dt_s[V1] = gap_dt_s[V2] = 30 s` (Default-Freeze, dokumentiert).

2. **Regel 1 (Kalibrier-Stichprobe, z. B. 1 h, nur Δt_recv, kein Blick auf Zellenraten):**  
   `gap_dt_s[X] = max(5 s, p99(Δt_recv[X]) × 3)` **nur zulässig, wenn**

   ```text
   max(gap_dt[V1], gap_dt[V2]) / min(gap_dt[V1], gap_dt[V2])  ≤  1.5
   ```

   Sonst: V2 gilt **nicht** als gleiche Liquiditätsklasse → V2 **austauschen**, nicht kompensieren. Kein Capture mit ungleichen Schwellen außerhalb Faktor 1.5.

3. Gewählte Werte + Kalibrier-Hash + Faktor-Check → Freeze-Tabelle im Ergebnisdok.  
   **Kein** Nachziehen nach Zellenraten in W_xv.

Default-Freeze:

| Venue | `gap_dt_s` |
|-------|------------|
| V1 Binance ETHUSDT | **30** |
| V2 Coinbase ETH-USD | **30** |

### 3.4 Persistenz

```text
/data/audit/cross_venue_gaps.jsonl     # Gap-Events pro Venue, nur t_recv
/data/audit/cross_venue_slots.jsonl    # Slot → Zelle {LL,LN,NL,NN}; bei LL: onset_skew_s
```

Gap-Zeile (Minimum): `source` (`recv_gap` \| `heartbeat` \| `restart_marker`), `venue`, `gap_start_recv_ts`, `gap_end_recv_ts`, `gap_duration_s`, `gap_dt_threshold_s`, `event_id`, Hash-Kette, Charter-Stempel.

**Heartbeat (pro Venue, vor W_xv Dual-Start):** stündlich `source=heartbeat` je `v1`/`v2` in `cross_venue_gaps.jsonl` — trennt „keine Lücke beobachtet" von „Beobachter tot". Auswertung: `writer_liveness_status(venue=…)`; H2-Priorität **OBSERVER_DOWN** vor INSUFFICIENT/V2_NOISE.

**Restart-Marker (pro Venue, bei `from_paths`):** `source=restart_marker` + Clock-Seeding analog Feed-Gap — verhindert **OBSERVER_DOWN** als False Positive unmittelbar nach Pod-Start, bevor der erste Heartbeat fällig ist.

**Observer-Gate (normativ, vor W_xv):** H2 ohne geladene `cross_venue_gaps.jsonl` → **`UNVERIFIED` / `NOT_GATED`** (kein sauberer PASS). Leere/stale Gaps → **`OBSERVER_DOWN`**. Meta-Zustand **U** (unbeobachtet): Venue-Seite nicht als „N" (ruhig) lesen, wenn der Beobachter tot ist.

\* Bei `heartbeat`/`restart_marker`: `gap_end_recv_ts`/`gap_duration_s` dürfen null sein (Lebendmarker, keine Lücke).

### 3.6 Deploy-Wiring (vor W_xv Dual-Start)

Cross-Venue-Heartbeats laufen **nur** über `LivePaperBridge.start_background` (gemeinsamer Thread `audit-writer-heartbeat` mit Feed-Gap):

```text
scripts/run_regime_swarm_daemon.py
  → _start_live_feed_thread (LIVE_FEED_ENABLED=true)
  → LivePaperBridge.from_env().start_background()
  → maybe_emit_all_heartbeats() für Feed-Gap + Cross-Venue
```

`PaperTradingRunner` allein startet **keinen** Heartbeat-Thread. Vor Dual-Start prüfen: `CROSS_VENUE_ENABLED=true` im Live-Shadow-Overlay **und** Daemon mit Live-Feed (nicht isolierter Runner).

Slot-Zeile (Minimum): `slot_start_ts`, `cell` ∈ {NN,LN,NL,LL}; wenn `cell=LL`: **`onset_skew_s`** (Pflicht).

**Verboten auf beiden Dateien:** `price`, `bid`, `ask`, `mid`, `deviation`, `spread`, Börsen-Eventzeit als Gap-Input.

Prometheus nur Ops — Auswertung = JSONL.

### 3.5 Eigenes Fenster W_xv

Konkordanz-Fenster W läuft seit **2026-08-29T13:17:46Z**. Cross-Venue startet **nicht** mittendrin in W.

```text
W_xv = 72–96 h ab eigenem Dual-Start
       (V1-Gap-Writer + V2-Empfang parallel; UTC + Image-Tag + Config-Commit)
```

---

## 4. Hypothesen

### H0 — Messbarkeit

In W_xv: beide Venues ≥ 1 h effektive Empfangs-Uptime **und** ≥ 500 ausgewertete Slots **und** jedes LL-Slot trägt `onset_skew_s`. Sonst unbrauchbar.

### Deskriptiv (kein konfirmatorisches H1)

```text
p_NN = Anteil Slots mit Zelle NN
```

**Begründung Streichung H1 (Review-Punkt 1):**  
Bei `slot_s=10 s` und W_xv=72 h ≈ 25 920 Slots erfordert `p_NN < 0.90` &gt; 2 592 gestörte Slots. Ein Gap &gt; 30 s bemalt ≥ 4 Slots → grob hunderte Lückenereignisse bzw. Stunden Gesamtausfall. Unter Normalbetrieb liegt `p_NN` bei 0.99+; ein Verdict CONFIRMED bei 0.90 wäre Leerformel und überlappt H0.  

`p_NN` (und Rohzählungen NN/LN/NL/LL) werden im Ergebnisdok **nur deskriptiv** ausgewiesen — **kein** CONFIRMED/NOT_CONFIRMED.

### H2 — Trennschärfe (tragende Behauptung)

Unter Slots mit **mindestens einer** Lücke (`disturbed = nicht NN`):

```text
p_LL = P(LL | disturbed)
p_LN = P(LN | disturbed)
p_NL = P(NL | disturbed)
# p_LL + p_LN + p_NL = 1
```

Zusätzlich über alle LL-Slots: Verteilung von `onset_skew_s` (Median, p90; Anteil mit `onset_skew_s ≤ 2 s` als `f_sync`).

#### 4.1 Prioritätsgeordnete, lückenlose Verdict-Zuordnung (Review-Punkt 4)

Hausregel analog Wave 38/39: **eine** Reihenfolge, **erschöpfend**, **überschneidungsfrei**. Erste zutreffende Regel gewinnt.

```text
Schritt −1 — Observer-Gate (zuerst):
  gaps JSONL nicht an Auswertung übergeben
  → UNVERIFIED (observer_check: NOT_GATED)
  # kein sauberer H2-PASS ohne Beobachter-Evidenz

Schritt 0 — OBSERVER_DOWN:
  writer_liveness(v1) oder writer_liveness(v2) ≠ ACTIVE
  → OBSERVER_DOWN
  # Meta-Zustand U: betroffene Venue nicht als „N" (ruhig) lesen

Schritt 1 — Voraussetzung:
  n_disturbed ≥ 20
  sonst → INSUFFICIENT_DISTURBED   (kein H2-Urteil)

Schritt 2 — V2_NOISE:
  wenn p_NL > 0.60
  → V2_NOISE
  # V2-Schwelle/Venue ungeeignet; Kontrollfall dominiert disturbed

Schritt 3 — COLLAPSED:
  wenn p_LL > 0.70
  → COLLAPSED
  # gemeinsame Ursache / Koinzidenz-Aufblähung dominiert;
  # Onset-Verteilung im Ergebnisdok: hoher f_sync stützt gemeinsame Ursache,
  # niedriger f_sync stützt Koinzidenz-Artefakt (deskriptiv, ändert Verdict nicht)

Schritt 4 — SEPARABLE:
  wenn p_LL ≤ 0.50
  → SEPARABLE
  # (p_LN+p_NL ≥ 0.50 folgt aus p_LL ≤ 0.50 — keine zweite Bedingung)

Schritt 5 — MIXED (Rest, lückenlos):
  sonst  (insb. 0.50 < p_LL ≤ 0.70 und p_NL ≤ 0.60)
  → MIXED
```

| Verdict | Bedeutung |
|---------|-----------|
| **UNVERIFIED** | gaps JSONL nicht geladen — kein H2-Urteil |
| **OBSERVER_DOWN** | Beobachter tot/stale — kein Zellen-Urteil |
| **INSUFFICIENT_DISTURBED** | zu wenig gestörte Slots |
| **V2_NOISE** | V2 zu störanfällig / falsch kalibriert |
| **COLLAPSED** | LL dominiert — Trennschärfe gering; Onset-Deskriptoren lesen |
| **SEPARABLE** | einseitige Zellen tragen; Venue-Trennung informativ |
| **MIXED** | Zwischenlage, weder klar separierbar noch kollabiert |

Kein Retuning von `gap_dt_s` nach Verdict — neues Amendment.  
Redundante Zweitbedingung `(p_LN+p_NL)≥0.40` entfällt (impliziert durch `p_LL≤0.50`).

---

## 5. Charter-Abgrenzung (normativ)

```text
VERWENDET WERDEN AUSSCHLIESSLICH ANKUNFTSZEITSTEMPEL (t_recv), KEINE PREISE.
```

| Erlaubt | Verboten |
|---------|----------|
| `t_recv`, Gap-Dauern, Slot-Zellen, `onset_skew_s` | `price`, Mid, Spread, `deviation_pct` |
| Diagnose-JSONL, Ops-Zähler | Signal-BLOCK wegen Kursabweichung |
| Fail-Closed nur für **dieses** Diagnose-Modul bei totalem Writer-Ausfall | Paper-Exit verzögern / Entry blockieren wegen Cross-Venue-Preis |

Zweckbindung = **Invariante**. Smoke muss eine Zeile mit Preis-Feld **ablehnen**.

---

## 6. Verhältnis zu Feed-Gap / Exit

| | Feed-Gap Konkordanz (W) | Cross-Venue (W_xv) |
|--|-------------------------|---------------------|
| Start | 13:17:46Z | eigener Dual-Start |
| Instrumente | socket ↔ tick_spacing (eine Venue) | V1 ↔ V2 Empfangslücken |
| Preise | irrelevant | **verboten** |
| Exit-FSM | unberührt | unberührt |

---

## 7. Implementierungs-Checkliste (nach Freigabe)

| # | Inhalt |
|---|--------|
| 1 | V2 Coinbase Advanced Trade `ETH-USD` WS read-only + URL-Guard |
| 2 | Gap-Detektor nur `t_recv`; Freeze inkl. Faktor-≤1.5-Gate |
| 3 | `cross_venue_gaps.jsonl` + `cross_venue_slots.jsonl` mit `onset_skew_s` bei LL |
| 4 | Report: deskriptives `p_NN` + H0 + H2 (Prioritätskette §4.1) |
| 5 | Smoke: einseitige Pause → LN/NL; synthetische Nah-Koinzidenz → LL + onset_skew; Preis-Feld → Reject |
| 6 | Dual-Start W_xv dokumentieren (nicht an W anhängen) |

**Ergebnisdok / LN-Dominanz (keine neue Verdict-Regel):** `p_LN` wird berechnet, fließt aber nicht in die H2-Kette ein (V1 = Untersuchungsgegenstand, V2 = Kontrolle; LN-Dominanz → typisch SEPARABLE). LN-Dominanz ist zweideutig (echte V1-Störung vs. zu enges `gap_dt[V1]`). Bei LN-Dominanz die **V1-Gap-Dauerverteilung** mitlesen: Häufung knapp über 30 s spricht für Schwellenartefakt, breitere Streuung für echte Störungen — beides bleibt SEPARABLE.

**Branch (nach Freigabe):** `feature/cross-venue-connectivity`

---

## 8. Freigabe-Checkliste (Reviewer)

- [x] Claim = H2 2×2 (+ Onset) — **kein** Kurs-Gate; **kein** `|div|`/15-bps-H1 in dieser Pre-Reg  
- [x] V2 = Coinbase ETH-USD eingefroren; Pyth nur §9.2-Fallback  
- [x] Nur `t_recv`; Preise verboten; `onset_skew_s` auf LL Pflicht  
- [x] Freeze: 30/30 oder Regel 1 **nur** bei Faktor ≤1.5, sonst V2 tauschen (§9)  
- [x] H2: V2_NOISE → COLLAPSED → SEPARABLE → MIXED (+ INSUFFICIENT), lückenlos  
- [x] Eigenes Fenster W_xv; W unberührt  
- [x] Exit-FSM / Edges / k unberührt  
- [x] Reviewer-Freigabe (2026-08-29) → Implementierung auf `feature/cross-venue-connectivity` nach Commit auf main  

---

## 9. Fallback und abgetrennte Claims

### 9.1 Deviation-/15-bps-H1 — **nicht** Bestandteil dieser Pre-Reg · Follow-up separat

Ein paralleler Wunsch (H1: `p50(|div|) ≤ 15 bps`, Tail p95/p99/max, erwartete Block-Rate, frozen 0,15 %-Gate) gehört zum **verworfenen** Preis-Claim (§0) und widerspricht §5 (Zweckbindung: nur `t_recv`).

**Reihenfolge (verbindlich):**

1. Konnektivität implementieren + Live-Shadow validieren (Dual-Feed präsent, 2×2 / Fail-closed hält).  
2. **Dann** Deviation-Pre-Reg öffnen: `docs/CROSS_VENUE_DEVIATION_PREREG.md` — H1 Normalband (p50/p95/p99/max + Block-Rate), 15 bps frozen, Tail-Befund → Amendment (kein stilles Retune).

| Wenn gewünscht | Dann |
|----------------|------|
| Konnektivität (diese Datei, FREIGABE) | 15-bps-/`|div|`-H1 **nicht** einmischen |
| Kurs-Normalband + Gate | erst nach Schritt 1; eigene Pre-Reg, eigenes Fenster, eigenes Freeze |

Stillschweigendes Zusammenlegen beider Claims = dieselbe Schwäche wie `not_investment_advice` nur als Literal.

### 9.2 Pyth als Fallback-Kandidat (nicht V2-Default)

Falls Coinbase-Kalibrierung scheitert (Faktor &gt; 1.5 nach Regel 1, dauerhaft V2_NOISE, Ops-Blockade):

1. Capture **abbrechen** bzw. nicht starten.  
2. Amendment: V2-Kandidat prüfen — Pyth nur wenn als **Trade-/Tick-Äquivalent** begründet und Faktor-Gate erfüllt; Aggregat-Self-Reference (§3.1) bleibt Risiko und muss im Amendment adressiert sein.  
3. Neue Freeze-Tabelle + neuer Dual-Start W_xv' — kein stiller Swap mittendrin.

---

## Siehe auch

- [`PAPER_FEED_GAP_DELTA_CONCORDANCE_PREREG.md`](PAPER_FEED_GAP_DELTA_CONCORDANCE_PREREG.md) — Unabhängigkeits-Korrektur  
- [`REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) — Live-Shadow; Fenster-W-Provenienz `59277d1a` / `feed-gap-v1`
