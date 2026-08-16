# Hebel 2 — Last-/Capability-aware Zuweisung (Pre-Registration)

**Status:** Pre-Registration — Auswertungsregel festgelegt, bevor Code/Daten
**Datum:** 2026-08-16
**Charakter:** Vorab registriert. Keine Regel-Justage nach Daten-Sichtung.
**Vorgänger:** Hebel 1 (Redundanz) · Hebel 3 (TIER-2a Durchsatz INCONCLUSIVE)

---

## Hypothese

Eine Zuweisung, die den Agentenzustand berücksichtigt (Last, Gas, Inbox-Länge
und/oder Capability), verbessert den Durchsatz gegenüber der aktuellen
Zustellungs-/Shard-Logik (Sticky/Least-Loaded bzw. hash-basierte Rollenwahl —
konkret der Pfad, der heute Transaktionen an Evaluatoren/Economics verteilt).

## Nullmodell (fest)

**Zufällige Zuweisung gleicher Last** — uniform random über die Kandidaten der
Zielrolle (Seed-kontrolliert).

- **Nicht** „Baseline ohne Rückstau“ (das war Hebel 3).
- **Nicht** der aktuelle StickySelector als Nullmodell — Sticky ist die
  *Behandlungs*- oder *Status-quo*-Bedingung; das Nullmodell ist Würfeln bei
  gleicher Last.

## Bedingungen (vorab)

| Arm | Beschreibung |
|---|---|
| **Status quo** | Bestehender Routing-Pfad (StickySelector / Least-Loaded + crc32) |
| **Nullmodell** | Uniform random über dieselbe Kandidatenliste |
| **Behandlung** | Last-/Capability-aware Zuweisung (Spezifikation folgt vor Implementierung) |

## Metrik

Durchsatz := `len(messages) / ticks` (msg/tick), gleicher Code-Pfad wie Hebel 3
(`adapter_agentx` Capture, `cycles=128`).

Quote/RT: out-of-scope für die erste Runde, sofern nicht bereits im Trace
(sonst dokumentierte Limitation analog Hebel 3).

## Schwelle (vorab fixiert, ±5% analog Hebel 3)

- ΔDurchsatz := (Durchsatz_Behandlung − Durchsatz_Nullmodell) / Durchsatz_Nullmodell
- **VERBESSERT:** ΔDurchsatz ≥ +5%
- **VERSCHLECHTERT:** ΔDurchsatz ≤ −5%
- **KEINE_KLARE_WIRKUNG / INCONCLUSIVE:** −5% < ΔDurchsatz < +5%

Zusätzlich: Vergleich Status-quo vs. Nullmodell (deskriptiv), damit klar wird,
ob Sticky überhaupt besser ist als Würfeln.

## Entscheidungsregel

Strikt gegen die Schwelle. Kein Nachjustieren nach dem Datenblick.
INCONCLUSIVE bei dünner Datenbasis (&lt;3 Seeds pro Arm) oder Effekt im ±5%-Band.

## Design-Hinweise (noch keine Implementierung)

- Bei neun faktisch identischen Prüfern (Hebel 1: `strictness` tot) ist
  „nicht besser als Würfeln“ der **wahrscheinliche** Ausgang für
  Evaluator-Zuweisung — das Nullmodell ist deshalb nicht optional.
- Capability-Awareness setzt voraus, dass Verdikte/Regeln differenziert sind;
  sonst bleibt nur Last/Inbox als Signal (Homöostase, analog TIER-2a).

## Nächster Schritt

Detaillierte Spezifikation: Zuweisungs-Logik, Nullmodell-Implementierung,
Auswertungs-Skript — nach Freigabe dieser Pre-Reg.
