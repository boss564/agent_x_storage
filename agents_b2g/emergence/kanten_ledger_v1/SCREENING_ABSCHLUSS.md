# KANTEN_LEDGER_v1 — Abschluss

**Status:** abgeschlossen · **Label:** `LEDGER_SCREEN_PASS`  
**DRAFT / Bindung:** `docs/KANTEN_LEDGER_v1_DRAFT.md` (ARCH_BINDEND)  
**Parameter:** seeds=[20261201, 20261202, 20261203] · warmup=32 · cycles=512 · κ=0 · γ=0.05  
**Laufzeit:** 16.23s  

**Kandidaten (≥2/3):** `avg_latency`, `interaction_count`  
**Near-Miss (≥2/3):** (keine)  

## Ergebnis (Seed 20261201 exemplarisch; Muster in 3/3 Seeds)

| Größe | MAE | \|ρ\|median | n_corr / n_sticky | S_S | S_G | Lesart |
|-------|----:|----------:|------------------:|:---:|:---:|--------|
| `interaction_count` | 1.405 | 0.156 | 64/64 | ✓ | ✓ | **PASS** |
| `avg_latency` | 0.248 | 0.348 | 64/64 | ✓ | ✓ | **PASS** |
| `trust_score` | 0.293 | 0.953 | 64/64 | ✓ | ✗ | getestet, S_G verfehlt (kein Near-Band: 0.953 > 0.95) |
| `bilateral_balance` | 89524 | — | **9/64** | ✓* | — | **nicht getestet** (untersampelt) |
| `edge_risk` | 0.004 | — | **7/64** | ✗ | — | **nicht getestet** (untersampelt) |

\*S_S bei `bilateral_balance` ist **skalenbedingt trivial** (Euro-Skala vs. Schwelle 0.05) — siehe unten.

### Untersampling ≠ Verworfen

`median_abs_rho: null` bei `bilateral_balance` (`n_corr=9`) und `edge_risk` (`n_corr=7`) bedeutet:
für die Mehrheit der Sticky-Kanten war keine Korrelation bildbar (konstante /
degenerierte Reihen). **S_G wurde nicht geprüft.** Das ist „kein Test“, nicht
„ausgeschlossen“. Eine spätere Runde darf diese Komponenten nicht als widerlegt
zitieren.

### MAE nicht skaleninvariant

Die Schwelle `MAE ≥ 0.05` ist absolut. Größen in Euro (`bilateral_balance`) bestehen
S_S trivial. Hier folgenlos (S_G ohnehin nicht prüfbar). Für Folgestudien / B-DRAFT:
MAE auf **normierte** Größe beziehen (z. B. relativ zur Streuung / Min-Max), sonst
ist das Kriterium wirkungslos.

### Kategorienwechsel vs. PARTNERSELECT

Knoten-Screen: `|ρ| ≈ 0.999` für praktisch jede Dimension.  
Ledger-Pass: `|ρ| ≈ 0.156` (`interaction_count`) und `0.348` (`avg_latency`).  
Das ist kein Schwellenkitzeln, sondern partnerlokaler Zustand statt Kollektiv-Kopie.

## HARKing-Sperre

- Kein κ-Sweep auf diesem Datensatz.
- Folgestudie = neue Pre-Reg + neue Seeds.
- `eij_*`, `partnerselect_screen_v1/` bleiben gesperrt.
- `bilateral_balance` / `edge_risk` nicht als negativ „geprüft“ führen.
