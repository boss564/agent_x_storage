# S_i-Commonality Probe (FULL)

**Kein Pre-Reg.** `|ρ|` von `S_i` *vor* jeder R-Transformation.  
**Majority:** `S_COMMON` · ~16s

| Seed | S vs S̄ | pairwise | sticky-S | sticky-ℓ | Label |
|-----:|--------:|---------:|---------:|---------:|:------|
| 20261401 | 0.164 | 0.050 | **0.964** | 0.348 | `S_COMMON` |
| 20261402 | 0.164 | 0.050 | **0.964** | 0.348 | `S_COMMON` |
| 20261403 | 0.164 | 0.050 | **0.964** | 0.348 | `S_COMMON` |

## Lesart

- sticky-ℓ |ρ|=0.35 ⇒ Kante selektiv (Ledger-Befund).
- S pairwise |ρ|=0.05 ⇒ Sender-Mittel sind **nicht** global synchron.
- sticky-S |ρ|=0.96 ⇒ dieselbe `S_i`-Serie liegt auf **vielen** Sticky-Keys
  (Key-Multiplizität / Panel-Konstruktion). `ρ(a·x, x)=1` erklärt Schicht-A-Fail
  bei v0.2 ohne Schwellen-Nachjustierung.

**Engpass:** Topologie / Sticky-Fächerung — nicht die Reaktion `f_i`.  
Nächster Strang wäre Topologie; kein weiterer R-Screen, keine Pre-Reg hier.
