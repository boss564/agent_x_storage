# Operative Härtung — Strang-Abschluss (final)

**Status:** **STRANG GESCHLOSSEN** · 2026-08-26  
**Charakter:** Engineering / Compliance aus `docs/THREAT_MODEL_POST_QUANTUM_v0.md`  
**Nicht:** Emergenz-Pre-Reg · nicht Stateful-Graph-Fortsetzung  

```text
Strang:     Operative Härtung (M7, M8, M9)
Status:     ABGESCHLOSSEN
M7:         829e6b00 — PRODUCTION (trimmed_m7 · MAD-Reject · Poison-Log)
M9:         e730f14e — PRODUCTION (Trust ∝ BHO Δ≠0)
M8:         24681bb3 — AUDIT · NICHT RELEVANT (keine SNARK-Circuits; BHO = Z3 SMT)
Threat:     docs/THREAT_MODEL_POST_QUANTUM_v0.md (ehrlich aktualisiert)
```

---

## Frage des Strangs

Welche Threat-Model-Maßnahmen (M7 Latenz-Poisoning, M9 Sybil, M8 SNARK-Soundness)
sind in der **aktuellen** Architektur umsetzbar bzw. überhaupt relevant?

## Antwort

| ID | Ergebnis |
|----|----------|
| **M7** | Produktiv integriert — Spike vor Fenster verworfen, Default `trimmed_m7` |
| **M9** | Produktiv integriert — Trust nur bei Settlement; Spam ohne Δ wirkungslos auf α/β |
| **M8** | Circuit-Migration **nicht relevant** — keine Circom/R1CS; Groth16 = Label/Mock (+ S6 Pairing-Logik ohne VK); BHO = Z3 SMT |

Drei Sätze:

1. Timing- und Sybil-Flächen am Ledger sind **geschlossen** (M7∪M9).  
2. M8 als SNARK→STARK-Migration wäre Arbeit am **falschen** Format — Audit verhindert das.  
3. Threat Model unterscheidet jetzt **relevante** (M7/M9) und **nicht-relevante** (M8-Migration) Maßnahmen.

---

## Was dieser Strang nicht öffnet

- Keine neue Emergenz-Studie unter dem Härtungs-Siegel  
- Keine STARK-Implementierung „trotzdem“  
- Keine Nachjustierung versiegelter Kopplungs-/Stateful-Graph-Artefakte  

**Stateful Graph** (`docs/STATEFUL_GRAPH_SERIE_v0.md`) bleibt eigener Strang —
`|Q|`-Variation / Topologie sind **Fortsetzungen dort**, nicht Teil dieser Härtung.

---

## Verweise

| Dokument / Commit | Rolle |
|-------------------|-------|
| `docs/THREAT_MODEL_POST_QUANTUM_v0.md` | Threat-Landkarte · M7/M8/M9-Status |
| `docs/M8_ZK_AUDIT_v0.md` | M8 Inventur · S6≠S7 · Z1≠ZK |
| `agents_b2g/emergence/kanten_ledger.py` | M7 + M9 Produktionspfad |
| `scripts/test_m7_latency_poison.py` | M7 Smoke |
| `scripts/test_m9_sybil_trust.py` | M9 Smoke |
| `829e6b00` · `e730f14e` · `24681bb3` | Maßnahme-Commits |

---

## Siegel

```text
STRANG GESCHLOSSEN — Operative Härtung
Pause. Nächste Frage nur außerhalb dieses Siegels.
```
