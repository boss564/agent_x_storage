# KOPPLUNG_LEDGER_v1 — Abschluss

**Status:** ABGESCHLOSSEN · 2026-08-25  
**Pre-Reg:** `docs/KOPPLUNG_LEDGER_v1_PREREG.md` (BINDEND → abgeschlossen)  
**Normierung:** σ · Spot-Check: ja · Runner: `scripts/run_kopplung_ledger_v1_sweep.py`  
**Lauf:** FULL · warmup=32 · cycles=512 · ~720 s · EXIT 0  
**Serien-Schluss:** `docs/KOPPLUNG_SERIE_ABSCHLUSS.md`

## Verdict (je Größe, bindend)

| Größe | Verdict | §1.1 | κ\* | Gate ≥4/6 |
|-------|---------|------|----|-----------|
| L1 `avg_latency` | **`KOPPLUNG_INVALID`** | widerlegt (κ=0.2: C 4/6) | None | nirgends |
| L2 `interaction_count` | **`KOPPLUNG_INVALID`** | widerlegt (κ=0.2: C 6/6) | None | nirgends |

```text
intact_kappas:  [0.0, 0.2, 0.4, 0.6, 0.8, 1.2]   — alle Stufen, beide Größen, 6/6 Seeds
Spot-Check κ=0: L1 |ρ| 0.348 · L2 |ρ| 0.156      — kein SIGNAL_BLIND
§1.1 widerlegt bei κ=0.2:  C 4/6 (L1) · C 6/6 (L2)
Gate B↔C ≥4/6:  nirgends
Peak r̄_B ≈ 0.30 (< R_FLOOR 0.34)
```

## Spot-Check κ=0 (Seed 20261301)

| Größe | Intact | mae_norm | median \|ρ\| |
|-------|:------:|---------:|-------------:|
| L1 | ✅ | 1.625 | 0.348 |
| L2 | ✅ | 1.337 | 0.156 |

→ kein `SIGNAL_BLIND`.

## Per-κ Vorbedingung — und warum der Befund trägt

**Alle κ-Stufen, beide Größen: 6/6 Seeds `INTACT`.**  
Kein Zellenlabel `PRECONDITION_LOST`.

Die naheliegende Ausrede wäre gewesen, dass die endogene Ledger-Dynamik unter κ>0
die Partnerselektivität auffrisst. Sie tut es nicht — an keiner Stufe, bei keinem
Seed. Die Per-κ-Kontrolle ist sauber zurückgekommen und **schließt** diese Erklärung
aus, statt sie zu bestätigen. Genau deshalb trägt der Befund: §1.1 fällt bei
erhaltener Vorbedingung.

## Kernbefund (Architektur, nicht Kandidat)

Nicht die Kopplungsgröße war das Problem, sondern dass die **Antwort** der Agenten
sich nicht nach Partner unterscheidet. Auch mit einer nachweislich und dauerhaft
partnerselektiven Größe erzeugt die permutierte Zuordnung (Arm C) dieselbe Kohärenz:
die Kohärenz hängt nicht daran, **mit wem** ein Agent gekoppelt ist, sondern nur
daran, **dass** moduliert wird.

Gate B↔C erreicht nirgends Mehrheit (max 1/6). Peak r̄_B ≈ 0.30 bei κ=0.2 liegt
unter `R_FLOOR=0.34`.

## Der Ertrag des Kontrollarms

Ohne Arm C hätte diese Studie — wie ihre Vorgänger — leicht `COUPLED` gemeldet
(r≈0,24–0,30, p signifikant, Divergenz intakt, über Seeds stabil). Mit Arm C ist
das Ergebnis `KOPPLUNG_INVALID`. Der Kontrollarm ist der eigentliche Ertrag der
Serie; siehe Serien-Schluss.

## Artefakte

- `SPOT_CHECK.json`
- `KOPPLUNG_LEDGER_L1_FULL.json` / `KOPPLUNG_LEDGER_L1_ERGEBNIS.md`
- `KOPPLUNG_LEDGER_L2_FULL.json` / `KOPPLUNG_LEDGER_L2_ERGEBNIS.md`
- `KOPPLUNG_LEDGER_SUMMARY.json`
- `SHA256SUMS.txt`

## Regel

Keine Schwellen-Nachjustierung. HARKing auf `kanten_ledger_v1/` bleibt gesperrt.
Keine neue Pre-Reg in diesem Strang.
