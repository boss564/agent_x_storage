# Hebel 3 — TIER-2a Effizienz-Ergebnis (Durchsatz)

**Status:** Abgeschlossen — **INCONCLUSIVE**
**Datum:** 2026-08-16
**Pre-Reg:** `docs/HEBEL3_TIER2A_EFFIZIENZ_PREREG.md` (`00ee07a3`)
**Artefakte:** `tier2a_runs.json`, `tier2a_durchsatz_sweep.json` (gitignored)
**Runner:** `scripts/run_tier2a_effizienz_sweep.py` · Eval: `scripts/eval_tier2a_effizienz.py`

---

## Ergebnis (strikt gegen Pre-Reg ±5%)

| κ | Durchsatz (msg/tick) | Δ vs. Baseline | Klassifikation |
|---|---|---|---|
| 0.0 (Baseline) | 5.0312 | — | BASELINE |
| 0.25 | 4.9922 | −0.78% | KEINE_KLARE_WIRKUNG |
| 0.5 | 4.9375 | −1.86% | KEINE_KLARE_WIRKUNG |
| 1.0 | 4.9453 | −1.71% | KEINE_KLARE_WIRKUNG |
| 2.0 | 4.8984 | −2.64% | KEINE_KLARE_WIRKUNG |

**Vorzeichen-Konsistenz:** 0/4 verbessert (benötigt ≥3) → nicht erfüllt.
**VERDICT:** **INCONCLUSIVE**

## Interpretation

TIER-2a hat auf der Durchsatzachse **keine klare Wirkung** jenseits der ±5%-Schwelle.
Richtung konsistent leicht negativ (−0.8% … −2.6%), aber unter der Schwelle und
ohne echte Seed-Varianz (Determinismus: `TickController.seed` ungenutzt).

**Antwort auf die Frage „Verbessert TIER-2a den Durchsatz?“:** Nicht messbar
(INCONCLUSIVE), kein POSITIV-/NEGATIVBEFUND.

## Limitationen (dokumentiert)

- Quote und RT out-of-scope (Pre-Reg-Amendment).
- Byte-identische Seeds — RNG-Fix optional als Follow-up, nicht nötig für diesen
  Abschluss.

## Sequenz

Hebel 3 abgeschlossen → weiter zu **Hebel 2** (Last-/Capability-aware Zuweisung).
