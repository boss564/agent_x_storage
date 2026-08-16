# Hebel 3 — TIER-2a Re-Evaluation auf der Effizienzachse (Pre-Registration)

**Status:** Pre-Registration — Interpretationsschwelle festgelegt, **bevor**
Effizienzwerte der bestehenden TIER-2a-Läufe angesehen werden
**Datum:** 2026-08-16
**Charakter:** Andere Metrik auf denselben Daten. Kein HARKing.
**Nullmodell-Abgrenzung:** Baseline **ohne Rückstau** (κ=0).
Nicht „zufällige Zuweisung gleicher Last" (das gehört zu Hebel 2).

---

## Hypothese

TIER-2a (Rückstau) ist homöostatisch. Auf der Koordinationsachse war das ein
Negativbefund („nicht synchronisierend"); auf der Effizienzachse ist Homöostase
plausibel ein Positivbefund. TIER-2a verbessert Durchsatz/Quote/RT gegenüber
der Baseline ohne Rückstau.

## Metriken

- **Durchsatz** (events/s bzw. TX/Zyklus)
- **Quote** (Erfüllungsrate / checks_passed / checks_performed, soweit in Trace)
- **RT** (Reaktionszeit / Latenz-Proxy aus Trace, falls verfügbar)

## Nullmodell

Baseline ohne Rückstau (κ=0, ε=0) — das natürliche Nullmodell für Hebel 3.
**Nicht** zufällige Zuweisung (Hebel 2).

## Interpretationsschwelle (vorab, bevor Werte angesehen)

TIER-2a gilt als **Effizienz-Positivbefund**, wenn es

- den Durchsatz verbessert **ODER** die Quote hält/steigert,

**und** die jeweils andere Metrik **nicht signifikant verschlechtert**.

Reine RT-Verbesserung allein zählt als **schwacher Befund** (nicht als
Positivbefund für die Hypothese).

## Disziplin

Die TIER-2a-Läufe existieren bereits (wurden gegen Kuramoto-r ausgewertet).
Die Neuauswertung ist „andere Metrik auf denselben Daten", aber die
Interpretationsschwelle wird **jetzt** festgelegt, bevor die Effizienzwerte
angesehen werden.

## Nächster Schritt (nach dieser Pre-Reg)

Bestehende Baseline- und TIER-2a-Traces aggregieren; Schwelle oben anwenden;
Ergebnis in einem kurzen Befund-Dokument festhalten.
