# Emergenz — Kopplungs-Umbau: Ergebnis (FINAL)

**Status:** FINAL · Studie geschlossen · keine Nachjustierung  
**Pre-Reg:** `docs/EMERGENZ_KOPPLUNG_PREREG.md` (BINDEND 2026-08-24 · geschlossen 2026-08-25)  
**Lauf:** FULL · warmup=32 · cycles=512 · 493 s · 78 Zellen · EXIT 0  
**Artefakte:** `agents_b2g/emergence/kopplung_full/` (Dauerhaft) · Quelle `/tmp/emergence_kopplung/`  
**SHA-256:** `f4c9c583b67e36a4af4552b8f063f73e7ad83a2ffd8db11d28accd242b2d22d3` (md) · `7ee406a107dc4fd350350b97940cc796f700b718f91a355411d6ed77adae06f2` (json, 27856 B)

## Verdict (bindend)

**`KOPPLUNG_INVALID`** — Arm C bei mehreren κ `COUPLED` (Mehrheit ≥4/6) → registrierte Vorhersage §1.1 **widerlegt**. Studie endet hier (§4).

| Kennzahl | Wert |
|----------|------|
| Gate §3.3 (B vs C) | nirgends ≥4/6 |
| κ\* | `None` |
| Form §3.2 | False |
| §1.1 gehalten | **NEIN** |

## Arm C (§1.1)

| κ | COUPLED Seeds | ≥4/6 |
|--:|-------------:|:----:|
| 0.0 | 0/6 | no |
| 0.2 | 6/6 | YES |
| 0.4 | 3/6 | no |
| 0.6 | 6/6 | YES |
| 0.8 | 6/6 | YES |
| 1.2 | 6/6 | YES |

## Kennzahlen

r̄_B(κ) = [0.0933, 0.2907, 0.2234, 0.2344, 0.2427, 0.2405] · SD_pool = 0.0710  
D_dyn(A) mean = 1.0079

## Regel

Keine Schwellen-Nachjustierung. Kein weiterer Sweep auf derselben Fragestellung.  
Weiterarbeit nur mit neuer Pre-Reg (append-only) und neuer Hypothese/Daten.

---

## Diagnose-Korrektur (2026-08-25, append-only)

**Zurückgezogen:** „Kopplung zu stark / zu starr / Konsens verfehlt.“

**Gültig:** Die gekoppelte Größe (Queue-Länge) trägt **keine partnerspezifische Information**.

Stützende Zahlen aus dem versiegelten Sweep (keine neue Hypothese, nur Mechanismus des Negativbefunds):

| Beobachtung | Wert |
|-------------|------|
| r̄_B | 0,093 → ≈0,24 (schwache Kohärenz; r_random ≈ 0,19) |
| Kriterium 3 | verlangt `r_B − r_C ≥ 0,10` |
| Gemessen | `Δr ≈ 0,001 … 0,013` (bei κ=0,2: r_C sogar leicht > r_B) |

Arm B und Arm C sind ununterscheidbar, weil Queue-Längen unter Partnerpermutation praktisch invariant sind — nicht weil die Kopplung „zu stark“ wäre.

**Nomenklatur:** Arm A/B/C = Studienarme. Vermessene Population = 27 Agenten (9 Provider / 9 Evaluator / 9 Economic). Keine Gleichsetzung mit Security/Finance/Cluster-W oder `BlockchainNodeAgent`/`OracleAgent`.

**HARKing-Sperre:** Dieser Datensatz wird nicht für eine neue Hypothese umgedeutet. Nächster Strang = neue Pre-Reg + neue Läufe (`KOPPLUNG_REPUTATION_v1`, DRAFT).
