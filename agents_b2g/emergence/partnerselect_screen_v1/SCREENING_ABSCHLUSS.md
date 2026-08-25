# PARTNERSELECT_SCREEN_v1 — Abschluss

**Status:** abgeschlossen · **Label:** `NONE_CLOSE` · kein Studien-Verdict
**DRAFT / Bindung:** `docs/PARTNERSELECT_SCREEN_v1_DRAFT.md` (SCREEN_BINDEND)
**Parameter:** seeds=[20261101, 20261102, 20261103] · warmup=32 · cycles=512 · κ=0
**Laufzeit gesamt:** 16.75s

**Kandidaten (≥2/3):** (keine)
**Near-Miss (≥2/3):** `checks_failed` (3/3), `honor` (2/3)

### Near-Miss-Lesart (append-only)

Beide Near-Misses liegen im **MAE-Band** `[0.03, 0.05)`, nicht im ρ-Band:
`|ρ|≈0.999` (weit über 0.90) — global synchron, Partner-MAE nur knapp unter I1-S.
Das ist die Honor-Signatur (hohe Varianz, keine Partnerselektivität), bestätigt unter
härterem Fenster (512 vs. historisch 64). `inbox_len` bleibt partnerblind (MAE≪0.03)
bei niedriger Globalität.

## HARKing-Sperre

- Keine Hypothese auf **diesem** Datensatz testen.
- `state_screen/`, `reputation_i1/`, `eij_*`, `kopplung_full/` bleiben gesperrt.
- Folgestudie = neue Pre-Reg + neue Seeds.
