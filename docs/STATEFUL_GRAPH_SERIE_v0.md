# Stateful Graph — Serie v0 (Konsolidierung)

**Status:** Studie 1 abgeschlossen · **PAUSE vor Folgestudie** · 2026-08-26  
**Commit:** `91265e8e` · `STRUCTURE_RELATIONAL`  
**Charakter:** Neue Architekturfamilie — **nicht** Studie 11 der φ/ρ-Kopplung  
**Sandbox:** `prototypes/v2_stateful_graph/` · Transfer der Kopplungs-Runner **verboten**

```text
Kopplungsfamilie:     FAMILIE GESCHLOSSEN (10 Studien) — Kohärenz nicht relational
Stateful Graph v0:    STRUCTURE_RELATIONAL (1 Studie)  — Zustandsstruktur relational
```

---

## Frage der Serie

Erzeugt **diskrete Repulsion** auf Sticky-Kanten
(\(q \in Q\), Signal = Partnerzustand → Automaten-Übergang)
eine **relationale Zustandsstruktur**
(\(\Delta Q\), \(H_{\mathrm{Kante}}\), Arm-C-Bruch),
die unter Partnerpermutation bricht — ohne φ/ρ und ohne κ?

## Antwort (Studie 1)

**Ja — in dieser Sandbox-Architektur, auf frischen Seeds, repliziert.**

| Metrik | Schwelle | Sweep `20270201–06` |
|--------|----------|---------------------|
| ΔQ | ≥ 0,5 | 1,23 – 1,28 · 6/6 |
| H_Kante (Paare, Bit) | ≥ 2,0 · \(H_{\max}=4\) | 2,97 – 3,00 · 6/6 |
| anti-B (echt) | — | 1,00 |
| anti-A / anti-C | — | ≈ 0,45 – 0,54 (Zufallsniveau) |
| Margin B↔C | ≥ 0,15 | 0,46 – 0,57 · 6/6 |
| §1.1 Replikation | ≥4/6 | **6/6** |
| Verdict | — | **`STRUCTURE_RELATIONAL`** |

```text
Arm B (echte Kante):     anti = 1.00  → vollständige Repulsion
Arm A (crc-Baseline):    anti ≈ 0.5   → kein Kanten-Signal
Arm C (π(M)):            anti ≈ 0.5   → permutiert bricht Relationalität
```

---

## Abgrenzung zur Kopplungsfamilie

| Serie | Was gemessen wird | Verdict-Familie |
|-------|-------------------|-----------------|
| φ/ρ-Kopplung (10) | Kohärenz / Korrelation / κ | INVALID · NO_COUPLING · P1_ONLY |
| Stateful Graph (1) | Zustandsübergänge · Kantenentropie | `STRUCTURE_RELATIONAL` |

Drei Sätze:

1. Die Kopplungsfamilie hat gezeigt: **Kohärenz ist hier nicht relational.**  
2. Stateful Graph zeigt: **relationale Struktur existiert** — als diskrete Zustandsdynamik.  
3. Das ist **kein** Widerspruch zur Versiegelung: andere Frage, andere Metrik, andere Sandbox.

Überlebender Positivbefund der Kopplung (F8/P1: κ relational) bleibt unberührt —
er betrifft Stärke, nicht Phase und nicht \(\Delta Q\)/\(H\).

---

## Studie 1 — Freeze (kurz)

| ID | Inhalt |
|----|--------|
| F1–F2 | \|Q\|=4 · \(q'=(\sigma+1+(q\bmod2))\bmod\|Q\|\) |
| F3 | H = Shannon **Paare** · Bit · \(H_{\max}=4\) |
| F3b/c | H ≥ 2,0 · ΔQ ≥ 0,5 |
| F4 | Arm-C-Margin ≥ 0,15 |
| F5 | Warmup=32 · Measure=80 |
| F10 | Arm A: σ = crc-Zufall · **nicht** \(\sigma=q_i\) |
| Seeds | Spot/Sweep `20270201–06` · Proto `20270101–03` gesperrt |

Dokumente: `docs/STATEFUL_GRAPH_v0_DRAFT.md` · `docs/STATEFUL_GRAPH_v0_PREREG.md`  
Artefakte: `prototypes/v2_stateful_graph/runs/stateful_graph_v0/`

---

## Methodische Lehren (Serie)

| Lehre | Herkunft |
|-------|----------|
| 16s-Proto vor Pre-Reg | Gate `PROTO_PASS` 3/3 |
| Schwellen am Effekt, nicht an Null | ΔQ≥0,5 · H≥2,0 (nicht `>0` / `>0,15`) |
| Arm-A-σ explizit (F10) | verhindert 2-Zyklus-Confound |
| Warmup vor Measure | F5 · 32/80 |
| §1.1 = Replikation auf frischen Seeds | Übertragbarkeit, nicht Proto-Risiko |
| `CONTAMINATION` als Verdict | Kopplungs-Import sichtbar |

---

## Status & offene Türen

**Jetzt:** Pause — Befund konsolidiert, bevor Folgestudie.

**Natürliche Folgestudie (nicht dringend):** Dissens-Gegenprobe  
— gilt `STRUCTURE_RELATIONAL` auch bei kontinuierlichem \(\lvert S_i-S_j\rvert\)?  
Eigene Sandbox · eigener Proto · eigene Seeds · **kein** Transfer dieses Runners.

**Weitere Optionen (später):** \|Q\|-Variation · Topologie-Variation.

**Nicht erlaubt:** Studie 11 in der φ/ρ-Familie · Hybrid Tick/Event · Schwellen-Nachjustierung an versiegelten Sweep-Artefakten.

---

## Verweise

| Dokument | Rolle |
|----------|-------|
| `docs/KOPPLUNG_SERIE_ABSCHLUSS.md` | φ/ρ-Familie versiegelt |
| `docs/STATEFUL_GRAPH_v0_DRAFT.md` | Studie 1 · BINDEND |
| `docs/STATEFUL_GRAPH_v0_PREREG.md` | Studie 1 · Pre-Reg |
| `prototypes/v2_stateful_graph/` | Sandbox + Sweep |
