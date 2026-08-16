# Hebel 3 — TIER-2a Re-Evaluation auf der Effizienzachse (Pre-Registration)

**Status:** Pre-Registration — Interpretationsschwelle + operationale Definition
fixiert, **bevor** Effizienzwerte angesehen / ausgewertet werden
**Datum:** 2026-08-16
**Charakter:** Andere Metrik auf denselben Code-Pfad. Kein HARKing.
**Nullmodell-Abgrenzung:** Baseline **ohne Rückstau** (κ=0, ε=0).
Nicht „zufällige Zuweisung gleicher Last" (das gehört zu Hebel 2).

---

## Hypothese

TIER-2a (Rückstau) ist homöostatisch. Auf der Koordinationsachse war das ein
Negativbefund („nicht synchronisierend"); auf der Effizienzachse ist Homöostase
plausibel ein Positivbefund. TIER-2a verbessert den Durchsatz gegenüber der
Baseline ohne Rückstau.

## Amendment — Operationale Definition (vor Datenblick fixiert)

### Scope dieser Runde

- Gemessen wird **NUR der Durchsatz**.
- **Quote und RT sind OUT OF SCOPE** für diese Runde (nicht in den Traces
  vorhanden; Instrumentierung wäre ein eigener Neulauf-Aufwand).
- **EHRLICHE LIMITATION:** Da die Quote nicht gemessen wird, kann eine
  Quote-VERSCHLECHTERUNG durch den Rückstau nicht ausgeschlossen werden.
  Der Durchsatz-Befund steht unter dem Vorbehalt, dass die Quote nicht
  geprüft wurde. Dies wird im Ergebnis explizit dokumentiert, nicht
  stillschweigend übergangen.

### Durchsatz-Definition

```
Durchsatz := len(SwarmTrace.messages) / ticks   # msg/tick
```

Abgeleitet aus demselben Code-Pfad wie die ursprüngliche TIER-2a-Messung
(`adapter_agentx.py` TX-Rate), aber **PERSISTIERT** pro Lauf.
Kein neues Design, keine neue Metrik-Erfindung — nur Persistenz der
bestehenden Messung.

### Neulauf-Spezifikation

- κ=0, ε=0 als Baseline (Nullmodell, entsprechend Pre-Reg).
- κ-Sweep mit den ursprünglich verwendeten κ-Werten:
  **κ ∈ {0, 0.25, 0.5, 1.0, 2.0}** (LOG TIER 2a; ≥3 Werte mit κ>0 →
  Vorzeichen-Konsistenz-Zusatzkriterium greift).
- Gleicher Code-Pfad (`agents_b2g/emergence/adapter_agentx.py`), ε=0,
  kein relax/corridor.
- Seed-Satz: neu fixiert und dokumentiert, falls der historische Seed nicht
  rekonstruierbar ist (Adapter-Default `assess(..., seed=7)`; Capture-Seed
  gesondert dokumentieren).
- Pro Lauf persistieren: κ, ε, ticks, len(messages), Durchsatz, Seed.

### „Signifikant" — operative Schwellen (jetzt fixiert)

- ΔDurchsatz := (Durchsatz_κ>0 − Durchsatz_κ=0) / Durchsatz_κ=0
- **VERBESSERT:** ΔDurchsatz ≥ +5%
- **VERSCHLECHTERT:** ΔDurchsatz ≤ −5%
- **KEINE KLARE WIRKUNG:** −5% < ΔDurchsatz < +5%

Die ±5%-Schwelle ist eine vorab festgelegte Konvention, keine physikalische
Größe. Sie wird nach dem Datenblick **NICHT** angepasst, auch wenn das
Ergebnis knapp an der Schwelle liegt.

### Vorzeichen-Konsistenz (κ-Sweep mit ≥3 κ>0-Werten)

Zusatzkriterium: In **≥ 2/3** der κ>0-Werte liegt der Durchsatz ≥ +5% über
der κ=0-Baseline. Dies stützt einen POSITIVBEFUND, ersetzt aber nicht die
primäre ΔDurchsatz-Schwelle.

### Entscheidungsregel (strikt, ohne Nachjustieren)

- **POSITIVBEFUND:** Mindestens ein repräsentativer κ>0-Punkt (oder der
  Sweep-Aggregat) mit ΔDurchsatz ≥ +5%, **und** Vorzeichen-Konsistenz
  erfüllt (≥ 2/3 der κ>0-Werte ≥ +5%). Unter der dokumentierten Limitation,
  dass die Quote nicht gemessen wurde.
- **NEGATIVBEFUND:** ΔDurchsatz ≤ −5% am repräsentativen Vergleich
  (bzw. Mehrheit der κ>0-Werte ≤ −5%).
- **INCONCLUSIVE:** −5% < ΔDurchsatz < +5%, **ODER** die Datenbasis ist zu
  dünn (<3 reproduzierbare Läufe pro κ-Einstellung), **ODER**
  Vorzeichen-Konsistenz und Einzelpunkt widersprechen sich.
  INCONCLUSIVE wegen dünner Daten ist ein ehrliches Ergebnis, kein
  NEGATIVBEFUND.

## Disziplin

Keine Effizienz-Zahlen wurden für die Festlegung dieser Schwellen
herangezogen. Kein Nachjustieren nach dem ersten Neulauf.

## Nächster Schritt

1. Neulauf-Skript: κ-Sweep persistiert TX-Rate.
2. Auswertung strikt gegen diese Schwelle → POSITIV / NEGATIV / INCONCLUSIVE.
