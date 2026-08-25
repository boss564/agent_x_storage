# Stufe A v2 — Matched-N + Hawkes-Vorzeichen: Implementierungs-Spezifikation

**Status:** Spec fixiert nach Pre-Reg-Bestätigung (2026-08-18)
**Pre-Reg:** `docs/BRIDGE_STUFE_A_V2_PREREG.md` (bindend)
**Lock-in-Code:** `scripts/bridge_stufe_a_v2_config.py`, `scripts/bridge_stufe_a_v2_stats.py`,
`scripts/bridge_stufe_a_v2_pipeline.py`
**Tests:** `scripts/test_bridge_stufe_a_v2.py`
**Wiederverwendet (versiegelt, nicht editieren):** `scripts/bridge_stufe_a_config.py`,
`scripts/bridge_stufe_a_stats.py`, `scripts/bridge_stufe_a_pipeline.py` (Loader /
Hawkes-Jitter / CTE-Shuffle / BH)

Kein Recapture. Kein Peek der v2-Draw-Labels vor dem konfirmatorischen Lauf.
Stufe-A-`UNSPEZIFISCH` bleibt unangetastet.

---

## 0. Bestätigungen (eingeflossen)

| # | Entscheidung | Spec-Konsequenz |
|---|---|---|
| 1 | Vorzeichen nur Hawkes | Hit = `bh_reject ∧ γ̂ > 0`; CTE = reiner BH-Reject |
| 2 | 248er-Last pro Draw | eine BH über den ganzen Vektor; Konjunktion nur Zählregel danach |
| 3 | Exact-N-Subset ohne Zurücklegen | `ctrl_eth → N(treat_eth)`, `ctrl_arbitrum → N(treat_gnosis)`; Treatment nicht verdünnt |
| 4 | Getrennte RNGs | Treatment `SEED`; Thinning `SEED+1000+d`; Kontroll-Surrogate `SEED+10000+d` |
| 5 | D=21 + Borderline 10–12/21 | Majority ≥ 11 deskriptiv; `confirmatory_verdict` nur bei `k* ≥ 13` definitiv |
| 6 | Per-Draw-Kriterium | Effekt vorhanden ⇔ Draw-Label `V2_POSITIVBEFUND` (volle IUT inkl. CTE) |
| 7 | Majority über per-Draw-BH | kein gepoolter BH |
| 8 | Verdict-Prefix `V2_` | Stufe A nicht umdeuten |

---

## 1. Artefakte

| Schritt | Skript | Output |
|---|---|---|
| 1 Capture | — | dieselben gitignored JSONL wie Stufe A |
| 2 Auswertung | `scripts/bridge_stufe_a_v2_pipeline.py` | `bridge_stufe_a_v2_ergebnis.json` (gitignored) |
| 3 Dossier | manuell gegen Pre-Reg | `docs/BRIDGE_STUFE_A_V2_ERGEBNIS.md` |

Smoke-Manifeste werden ohne `--allow-smoke` abgelehnt (dieselbe Weigerung wie Stufe A).

---

## 2. Thinning

```text
exact_n_subset(times, N*, rng) -> sorted subset, |kept| = N*
idx = rng.sample(range(len(times)), N*)   # without replacement
```

Zwei unabhängige Subsets pro Draw (ctrl_eth, ctrl_arbitrum). Kein Uniform-im-Fenster,
kein IAAFT, kein Sampling mit Zurücklegen.

`N*` = Fenster-gefilterte Treatment-Längen aus denselben Capture-Loadern wie Stufe A.

Study-level Gates vor den Draws (Coverage < 80 %, Treatment-N < 100, Kontrolle
kürzer als N*): alle 21 Labels `V2_INCONCLUSIVE`, `skipped_compute=true`. Kein
Nachziehen der Surrogate. Im konfirmatorischen Capture (N ≫ 100) greift das
nicht.

---

## 3. 248-Vektor pro Draw

Reihenfolge analog Stufe A (Hawkes beider Paare, dann CTE beider Paare), aber:

1. Treatment-Hawkes und Treatment-CTE **einmal** mit `Random(SEED)`, p-Werte
   und beobachtete γ̂ / CTE fest.
2. Pro Draw d: Kontrolle thinnen, Occupancy neu, Hawkes+CTE mit
   `Random(SEED+10000+d)`, 1000 Surrogate.
3. 248-Vektor = feste Treatment-p + draw-spezifische Kontroll-p.
4. Eine `benjamini_hochberg(..., q=0.05)` über diese 248.
5. Zählregel: Hawkes-Hit nur bei `bh_reject ∧ observed > 0`; CTE-Hit bei `bh_reject`.

Treatment wird nicht pro Draw neu gesurrogated.

---

## 4. Per-Draw-Label und Aggregation

`v2_verdict(...)` spiegelt Stufe-A-`verdict()` mit Prefix `V2_` und mit den
sign-gefilterten Hawkes-Zählern.

`draw_effect_present(label)` ist wahr genau bei `V2_POSITIVBEFUND`.

`aggregate_draw_labels(labels)` mit D=21:

| Feld | Regel |
|---|---|
| `majority_label` | einziges Label mit Häufigkeit ≥ 11, sonst `V2_UNSPEZIFISCH` |
| `k_star` | max. Häufigkeit eines Labels |
| `borderline` | genau ein führendes Label und `k_star ∈ {10, 11, 12}` |
| `confirmatory_verdict` | `majority_label` nur wenn eindeutig und `k_star ≥ 13`, sonst `V2_UNSPEZIFISCH` |
| `definitive` | eindeutig und `k_star ≥ 13` (auch wenn das Label selbst `V2_UNSPEZIFISCH` ist) |

Ein Follow-up mit höherem D ist nicht Teil dieser Pipeline.

---

## 5. Tests (ohne Live-JSONL-Peek)

`scripts/test_bridge_stufe_a_v2.py`:

- Exact-N: Teilmenge, ohne Zurücklegen, Länge N*, sortiert
- `len(ctrl) < N*` → Draw `V2_INCONCLUSIVE`
- RNG-Trennung: Thinning-Stream ≠ Surrogat-Stream bei gleichem d
- Hawkes-Hit: `bh_reject ∧ γ̂ ≤ 0` zählt nicht; CTE ohne >0-Hürde
- 248-Last: Konjunktion ändert die Familiengröße nicht
- Per-Draw-Kriterium = `V2_POSITIVBEFUND`-IUT (Hawkes-pos + CTE + leere Kontrolle)
- Majority 13/21 eindeutig → confirmatory = dieses Label, nicht BORDERLINE
- Majority 11/21 oder 12/21 → `majority_label` gesetzt, `confirmatory_verdict = V2_UNSPEZIFISCH`, `borderline`
- k*=10 ohne Majority → beide UNSPEZIFISCH, `borderline`
- Split k*=7 → UNSPEZIFISCH, nicht BORDERLINE
- Pipeline-Smoke: synthetische JSONL, `--n-draws 3 --n-surrogates 2`, kein Live-Capture

---

## 6. Out of scope

- Stufe A nachziehen oder `UNSPEZIFISCH` überschreiben
- Stufe B / Ausfallfenster
- Gepoolter BH, Uniform-im-Fenster, IAAFT
- D nach erstem Draw ändern
- Recapture
