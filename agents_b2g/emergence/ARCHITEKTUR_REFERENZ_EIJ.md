# Architektur-Referenz — 4 Schichten + E_ij-Schutzmechanismen

**Status:** Referenz · **keine Pre-Reg** · generiert keine Hypothese · wertet keine Daten aus  
**Kohärenz:** Screening `NONE_CLOSE` / Ausgang 3 · Queue versiegelt · Reputation `I1_FAILED`  
**HARKing:** Daten unter `state_screen/` bleiben für Hypothesentests gesperrt.

Dieses Dokument beschreibt eine **Zielarchitektur**. Es ist kein Studienprotokoll und
kein Freigabe-DRAFT. Ein messbarer Test von `E_ij` erfordert eine **explizite neue Pre-Reg**.

---

## 4-Schichten-Modell

| Schicht | Funktion | Beziehung zum Screening-Befund |
|---------|----------|--------------------------------|
| **Teil 1 – Ausführung** | Operative Verarbeitung, Worker-Spawning, BHO Δ=0 | Ephemere Sub-Agenten → kein persistenter Knotenzustand; verschmutzen `S_i` nicht weiter |
| **Teil 2 – Routing** | `E_ij`-Kanten-Matrix, Partnerwahl | Antwort auf Ausgang 3: Partnerselektivität konstruktional in der Kante, nicht aus `S_i` |
| **Teil 3 – Verifikation** | Z3, MPC-Konsens, HSM-Signatur | Prüft Kanten-Ergebnisse, nicht globalen Schwarmzustand → keine Re-Synchronisation als Emergenz-Surrogat |
| **Teil 4 – Verwaltung** | GoBD-WORM, ERP-Sync, SEPA-Finalität | Konsumiert zertifizierte Ergebnisse; kein Routing aus `S_i` |

Trennung: Durchsatz (1) · Beziehung (2) · Wahrheit (3) · Jurisdiktion (4).

---

## Operative Schutz- und Steuerungsmechanismen (E_ij-Layer)

Erweiterung für Teil 2 (Kanten-Speicher) und Teil 3 (Verifikation) — strukturelle Antworten
auf Sättigung (`S_i` / `H_cap`) und fehlende Partnerselektivität:

| # | Mechanismus | Funktion | Adressiertes Problem |
|---|-------------|----------|----------------------|
| 1 | **Kaltstart-Exploration** | Thompson-Sampling für `E_ij = ∅` | Starre bei neuen/unbekannten Paaren; datengestützte Initialisierung |
| 2 | **Exponentieller Decay** | `E_ij(t) = E_ij(t−1)·e^(−γ Δt) + S_neu` | Sättigung wie bei `H_cap`; Historie verblasst, aktuelle Performance dominiert |
| 3 | **ZK-Privatsphäre** | ZK-Proofs für Kantenschwellen (`κ_ij ≥ θ`) | Beziehungsgeflechte/Volumina vor globaler Einsicht (DSGVO/Betriebsgeheimnis) |
| 4 | **Z3-Kanten-Integration** | `UNSAT ⇔ (Δ=0,00 €) ∧ (E_ij.risk ≤ limit)` | Mathematische Korrektheit reicht nicht bei verletztem Kanten-Sicherheitslimit |

**Einordnung:** reine Architektur-Spezifikation — keine Hypothese, keine Auswertung,
kein Umgehen der HARKing-Sperre.

---

## Tracking

```text
Status: BINDEND → KOPPLUNG_INVALID
I1-Edge: I1_PASS · κ-Sweep: final
Artefakte: agents_b2g/emergence/eij_i1/ · eij_sweep/
HARKing-Sperre: strikt aktiv auf state_screen / kopplung_full / reputation_i1
```

Pre-Reg: `docs/KOPPLUNG_EIJ_v1_PREREG.md`