# Stufe A — Bridge-vermittelte Kreuz-Anregung ETH ↔ Gnosis: Ergebnis-Dossier

**Status:** Abgeschlossen — Verdict **`UNSPEZIFISCH`** (Pre-Reg-konform, Schwellen nicht nachjustiert)
**Auswertung:** 2026-08-18 UTC (`bridge_stufe_a_ergebnis.json`)
**Fenster:** 2026-05-20 00:00:00 UTC – 2026-08-17 23:59:59 UTC
**Pre-Registration:** `docs/BRIDGE_STUFE_A_PREREG.md` (bindend, 2026-08-17)
**Spec:** `docs/BRIDGE_STUFE_A_SPEC.md`
**Lock-in:** `scripts/bridge_stufe_a_config.py`, `scripts/bridge_stufe_a_stats.py`, `scripts/bridge_stufe_a_pipeline.py`
**Charakter:** Vorab registrierte Auswertungsregel, ergebnisoffen. 248 Tests, eine BH-FDR q=0.05 über den 248-Vektor, Verdict ausschließlich aus `verdict()`.

Dieses Dossier berichtet die registrierte Last. Qualitative Beobachtungen stehen
getrennt und ändern das Label nicht.

---

## 1. Hypothese und Regel

**H1 (Pre-Reg §1):** Gerichtete Kreuz-Anregung in OmniBridge-Flow-Events ETH ↔ Gnosis,
stärker als im Kontroll-Paar Uniswap ETH ↔ Arbitrum, übersteht Konditionierung auf
Gas, BTC und CEX-Volumen. Bidirektional; alle 31 Lags konfirmatorisch.

**H0:** Keine Kreuz-Anregung über die gemeinsamen Markttreiber hinaus.

**Registrierte Last (Pre-Reg §3, §6):**

| Parameter | Festlegung |
|---|---|
| Tests | 248 = 2 Richtungen × 31 Lags × 2 Metriken (Hawkes γ, CTE) × 2 Paare |
| FDR | eine Benjamini-Hochberg-Prozedur, q=0.05, über den ganzen 248-Vektor |
| Hawkes-Null | Jitter ±5 min, nur Quelle, Ziel fest, Rejection im Fenster, 1000 Surrogate |
| CTE-Null | Shuffle der Quell-Belegung, Ziel und Treiber fest, 1000 Surrogate |
| p | plus-one: `(1 + #{surr ≥ obs}) / 1001` |
| Hawkes-Entscheidung | beobachteter Wert **größer** als die Null (einseitige obere Seite) |
| Seed | `BRIDGE_STUFE_A_SEED = 20260817` |
| IAAFT | verboten |
| α = Σγ(τ), UTE | deskriptiv, nicht in den 248 |

**Verdict-Regel (unverändert):**

| Label | Regel |
|---|---|
| `POSITIVBEFUND` | Treatment: ≥1 BH-sig Hawkes **und** ≥1 BH-sig CTE; Kontrolle: 0 Hawkes **und** 0 CTE |
| `NEGATIVBEFUND` | Treatment: 0 Hawkes und 0 CTE |
| `DISSOZIIERT` | Treatment Hawkes XOR CTE; Kontrolle 0 |
| `UNSPEZIFISCH` | Treatment signifikant **und** Kontrolle ≥1 BH-sig Test |
| `INCONCLUSIVE` | N<100 in einem der vier Ströme, oder Treiber-Coverage < 80 % |

Kein Nachschärfen nach Zahlenblick. Keine Reduktion auf „8 Hypothesen“ oder
„interessante Lags“ (Pre-Reg §9).

---

## 2. Datenbasis

Capture-Gate (`scripts/check_bridge_stufe_a_capture.py`): **CONSISTENCY PASS.**

| Strom | N | Timestamp-Span | Rolle |
|---|---|---|---|
| treat_eth | 6 197 | 89,69 d | OmniBridge Foreign-Mediator, beide topic0 |
| treat_gnosis | 6 258 | 89,77 d | OmniBridge Home-Mediator, beide topic0 |
| ctrl_eth | 1 637 253 | 89,79 d | Uniswap Universal Router `tx.to` (ETH) |
| ctrl_arbitrum | 419 106 | 89,83 d | Uniswap Universal Router `tx.to` (Arbitrum) |
| Treiber | 129 600 min | Joint-AND **0.998** | Gas / BTC / CEX je 0.998 |

**INCONCLUSIVE-Gates:** nicht erreicht. N≫100; Treiber-Coverage ≥80 % auf allen
drei Achsen und im Joint-AND.

**Typ-Kreuzung (deskriptiv, kein Gate):** ETH Initiated 3167 = Gnosis Bridged 3167
(Δ=0); Gnosis Initiated 3091 ≈ ETH Bridged 3030 (Δ=61, 2 %). Die Gesamtdifferenz
N=61 ist derselbe Rest.

**Gemeinsame Timestamp-Überlappung:** 2026-05-20 01:09:59 UTC → 2026-08-17 17:49:47 UTC
(**89,69 d**), begrenzt durch das letzte ETH-Brücken-Event. Pre-Reg-Fenster 90 Kalendertage;
die Kante ist dokumentiert, das Fenster nicht nachjustiert.

**N-Asymmetrie (Pre-Reg §5, vorab):** Kontroll-Events sind DEX-`tx.to`, Treatment
sind Mediator-Logs. Nach Recapture: Kontrolle ~265× (ETH) bzw. ~67× (Arbitrum)
größer als Treatment. Das ist Event-Klasse, nicht Capture-Fehler.

Erste Uniswap-Counts (2850 / 2830) stammten aus einem abgebrochenen `txlist`-Walker
(1,38 d / 20 d) und sind **ungültig**. Die Tabelle oben ist der volle 90-Tage-Recapture.

---

## 3. Verdict

```text
n_sig hawkes_treat=3  cte_treat=62  hawkes_ctrl=3  cte_ctrl=3
Verdict: UNSPEZIFISCH
```

Treatment hat BH-signifikante Hawkes- **und** CTE-Tests. Kontrolle hat ebenfalls
BH-signifikante Tests (Hawkes 3, CTE 3). Die eingefrorene Regel für
`POSITIVBEFUND` verlangt eine Kontrolle mit **0** BH-Hits in beiden Metriken.
Diese Bedingung ist nicht erfüllt → **`UNSPEZIFISCH`**.

`INCONCLUSIVE` greift nicht (N, Coverage). `NEGATIVBEFUND` und `DISSOZIIERT`
greifen nicht (Treatment hat beide Metriken sig).

BH-Rejects gesamt: **71 / 248**.

---

## 4. Hawkes-Kern γ(τ) — konfirmatorisch

Monte-Carlo plus-one, BH über den 248-Vektor. Die Null ist einseitig **oben**
(`surr ≥ obs`). Ein BH-Reject heißt: γ̂ liegt im oberen Schwanz der Jitter-Null,
nicht „γ̂ < 0 ist getestet“.

### 4.1 BH-signifikante Lags

| Paar | Richtung | τ (min) | γ̂ | p |
|---|---|---|---|---|
| treatment | ab (ETH→Gnosis) | 6 | +0.001333 | 0.00999 |
| treatment | ba (Gnosis→ETH) | 15 | +0.001672 | 0.01199 |
| treatment | ba | 16 | +0.001691 | 0.002997 |
| control | ab | 14 | −0.000302 | 0.005994 |
| control | ba | 1 | −0.001075 | 0.005994 |
| control | ba | 2 | −0.001121 | 0.008991 |

Treatment: 3 BH-Hits, alle mit **positivem** Punktwert. Control: 3 BH-Hits, alle
mit **negativem** Punktwert — aber auf der **oberen** Seite der Jitter-Verteilung
(weniger negativ als die Null). Die Pre-Reg zählt nur Reject/Nicht-Reject, nicht
das Vorzeichen von γ̂.

Mechanistische Lag-Erwartung (Pre-Reg §1, deskriptiv, nicht filternd):
ETH→Gnosis in den ersten ~10 min (getroffen: τ=6); Gnosis→ETH um 15–25 min
(getroffen: τ=15, 16). Keine nachträgliche Subset-Filterung.

### 4.2 Punktwerte (alle 31 Lags)

Treatment ab (BH nur τ=6):

`0.001371, 0.001312, 0.001177, 0.001193, 0.001056, 0.001220, 0.001333*, 0.001193, 0.001185, 0.000994, 0.001011, 0.000938, 0.000860, 0.000865, 0.000860, 0.000736, 0.000726, 0.000723, 0.000642, 0.000728, 0.000704, 0.000838, 0.000720, 0.000548, 0.000782, 0.000682, 0.000685, 0.000553, 0.000626, 0.000699, 0.000728`

Treatment ba (BH τ=15, 16):

`0.001384, 0.001533, 0.001701, 0.001720, 0.001637, 0.001608, 0.001792, 0.001744, 0.001699, 0.001643, 0.001464, 0.001523, 0.001422, 0.001432, 0.001605, 0.001672*, 0.001691*, 0.001400, 0.001392, 0.001248, 0.001254, 0.001083, 0.001121, 0.001121, 0.001030, 0.000998, 0.000902, 0.001009, 0.001091, 0.001083, 0.001102`

Control-Kerne sind durchgängig negativ (volle Vektoren in der JSON). Die drei
BH-Hits sind die oberen Ausreißer relativ zum Jitter, nicht ein Test gegen Null.

---

## 5. Deskriptives Branching α = Σ_τ γ(τ)·Δτ (nicht in den 248)

| Paar | Richtung | α |
|---|---|---|
| treatment | ab | +0.02769 |
| treatment | ba | +0.04310 |
| control | ab | −0.01115 |
| control | ba | −0.03882 |

α spiegelt das Vorzeichen der Punktkerne. Es ist kein 249. Test und geht nicht
in `verdict()` ein.

---

## 6. CTE | Gas, BTC, CEX — konfirmatorisch

| Paar | Richtung | BH-Rejects | min p | CTÊ-Spanne |
|---|---|---|---|---|
| treatment | ab | **31 / 31** | 0.000999 (τ=24: 0.002997) | 0.000505 … 0.001360 |
| treatment | ba | **31 / 31** | 0.000999 | 0.000655 … 0.002024 (Peak τ=7) |
| control | ab | **0 / 31** | 1.0 | ~10⁻⁵ … 10⁻⁴ |
| control | ba | **3 / 31** | 0.001998 | BH: τ=13, 25, 30; CTÊ ≈ 1.1×10⁻⁴ |

Treatment-CTE: 62/62 Tests BH-signifikant nach Konditionierung. Control-CTE:
3/62, Größenordnung ~10× kleiner als Treatment.

Die drei Control-ba-Hits (τ=13, 25, 30) genügen der Pre-Reg, die Kontrolle als
„≥1 sig“ zu zählen. Deshalb kann `POSITIVBEFUND` nicht eintreten, unabhängig
davon, dass Control-ab nach Konditionierung **keine** BH-Hits hat.

---

## 7. UTE — deskriptiv (nicht in den 248)

Differenz UTE−CTE beschreibt, wie viel der Assoziation die Treiber erklären
(Pre-Reg §2). Kein BH-Test.

| Paar | Richtung | UTE (Lage) |
|---|---|---|
| treatment | ab | ~2.4×10⁻⁴ … 8.7×10⁻⁴ |
| treatment | ba | ~4.0×10⁻⁴ … 1.6×10⁻³ |
| control | ab | **~0.0032–0.0033** über alle 31 Lags |
| control | ba | ~10⁻⁴ |

Control-ab: unbedingte TE ist groß und flach; nach Konditionierung auf
Gas/BTC/CEX sind alle 31 p=1. Die Treiber nehmen diese gemeinsame Komponente
weitgehend heraus — genau die Konfundierung, gegen die das Kontrastpaar schützen
soll. Treatment-CTE bleibt danach BH-signifikant. Das ändert `verdict()` nicht,
weil die Kontrolle an anderer Stelle (Hawkes; CTE ba) weiterhin BH-Hits hat.

---

## 8. Pflicht-Caveats (Pre-Reg §8)

1. **Metronomische Blockzeiten** sind kein Hawkes-Prozess. Analyse nutzt
   Bridge-/Transfer-Zeitstempel, nicht den Slot-Takt.
2. **Stufe A ist beobachtend.** Selbst `POSITIVBEFUND` wäre Assoziation, nicht
   Kausalität.
3. **Kontrastpaar < Intervention.** Stufe B (Ausfallfenster) braucht eine
   eigene Pre-Reg; ein OmniBridge-Validator-Pause-Fenster in diesen 90 Tagen
   wird hier nicht ausgewertet (§8.7).
4. **Event-Klassen ungleich:** Mediator-Logs vs. Uniswap `tx.to`. Absicht
   (Pre-Reg §5): eine kanonische Arbitrum-Bridge wäre ein zweiter Korridor.
5. **CEX-Volumen ist ein Proxy.** Coinbase-API 400 im Capture; Binance + Kraken
   + OKX + Bybit tragen die Serie (Coverage 0.998).
6. **RPC-Lücken:** Gnosis-Logs über öffentlichen RPC (`rpc.gnosischain.com`),
   nicht Alchemy (HTTP 400 über ~10 Blöcke). ETH-Gas über `eth.drpc.org` nach
   Alchemy-403. Capture vollständig; kein `INCONCLUSIVE` wegen fehlender Logs.
7. **Ausfallfenster** nicht in Stufe A.

**Zusätzlich, aus der Durchführung (kein Regelwechsel):**

- Uniswap-N ist ~265× / ~67× Treatment. Die Kontrolle hat dadurch höhere Power
  für schwache Effekte (CTÊ ~10⁻⁴). `UNSPEZIFISCH` ist damit auch eine
  Konsequenz der vorab gewählten Event-Klasse, nicht nur eines „gemeinsamen
  Treibers“ im mechanischen Sinn.
- Hawkes testet nicht das Vorzeichen. Eine Regel „BH-sig **und** γ̂>0“ wäre
  eine **neue** Pre-Reg, keine Nachjustierung dieser.
- Subsampling der Kontrolle auf Treatment-N wäre ebenfalls eine neue Pre-Reg
  (Pre-Reg §9: Kontroll-Paar nicht umstellen, weil Uniswap „zu laut“ ist).

---

## 9. Was diese Studie nicht tut

- Adressen, Fenster, Lag-Raster, FDR, Surrogate-Zahl nach Datenblick ändern
- 248 Tests auf 8 Familien oder auf τ=6/15/16 reduzieren
- IAAFT nachreichen
- xDAI-Bridge / AMB einmischen
- Kontrolle auf Arbitrum-Inbox umstellen
- `UNSPEZIFISCH` in `POSITIVBEFUND` umlabeln, weil Treatment-CTE 62/62 ist

---

## 10. Einordnung (an die Regel gebunden)

Der **bindende** Ausgang ist `UNSPEZIFISCH`. Treatment-Hawkes und Treatment-CTE
sind BH-signifikant; die Kontrolle ist es auch. Die IUT-artige Konjunktion für
`POSITIVBEFUND` verlangt eine leere Kontrolle und bekommt sie nicht.

Getrennt davon, und **nicht** verdict-fähig:

- Treatment-γ̂ an den BH-Lags positiv; Control-γ̂ an den BH-Lags negativ
  (Punktwerte). Die einseitige Null prüft nur „größer als Jitter“.
- Treatment-CTE überlebt Gas/BTC/CEX flächendeckend; Control-ab-CTE kollabiert
  nach derselben Konditionierung (UTE ~0.0033 → alle p=1).
- Deskriptives α: Treatment positiv, Control negativ.

Das ist die konservative Lesart der registrierten Last: die qualitative
Trennung der Paare ist sichtbar und im Dossier festgehalten; das Label bleibt
`UNSPEZIFISCH`.

Stufe B (Intervention / Ausfallfenster) und eine vorzeichenbewusste oder
N-gematchte Hawkes/CTE-Regel bleiben optionale **neue** Pre-Regs.

---

## 11. Reproduktion

```bash
# Capture-Gate (bereits PASS)
python3 scripts/check_bridge_stufe_a_capture.py \
  --bridge-eth bridge_eth.jsonl --bridge-gnosis bridge_gnosis.jsonl \
  --uniswap-eth uniswap_eth.jsonl --uniswap-arb uniswap_arb.jsonl \
  --drivers drivers_90d.jsonl

# Konfirmatorische Last (248 Tests, 1000 Surrogate, Seed 20260817)
python3 scripts/bridge_stufe_a_pipeline.py \
  --bridge-eth bridge_eth.jsonl --bridge-gnosis bridge_gnosis.jsonl \
  --uniswap-eth uniswap_eth.jsonl --uniswap-arb uniswap_arb.jsonl \
  --drivers drivers_90d.jsonl \
  --output bridge_stufe_a_ergebnis.json

python3 scripts/test_bridge_stufe_a.py   # 29/29; N_TESTS == 248
```

JSON-Felder: `verdict`, `n_sig`, `n_events`, `driver_coverage`, `tests[]`
(`pair`, `metric`, `direction`, `lag_min`, `observed`, `p`, `bh_reject`),
`alpha_descriptive`, `ute_descriptive`.
