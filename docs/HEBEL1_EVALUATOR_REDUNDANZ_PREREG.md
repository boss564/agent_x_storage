# Hebel 1 — Evaluator-Redundanz (Pre-Registration)

**Status:** Pre-Registration — Auswertungsregel festgelegt, bevor Follow-up-Fixes
**Datum:** 2026-08-16
**Charakter:** Struktureller Beweis + Runtime-Assertion. Kein HARKing.

---

## Hypothese (strukturell)

Alle neun Evaluatoren wenden dieselbe deterministische Regel
`abs(delta) <= 0.01` an. `strictness` wird gesetzt, aber nie gelesen
(tote Konfiguration, Kommentar-Code-Divergenz:
`a.strictness = bias  # Höher = strengere Prüfung`).
Daher ist die paarweise Uneinigkeit ≡ 0 by construction — neun Prüfer sind
**Replikation, nicht Verifikation**.

## Befund-Typ

Struktureller Beweis, abgestützt durch Runtime-Assertion.
Kein empirischer Fan-out nötig für die Kernaussage.

## Zusatzbefund (Routing)

Routing ist **1-von-9** (`StickySelector`), kein Fan-out.
Die Neun-Redundanz wird aktuell nicht ausgeübt.

## Entscheidungsschwelle (vorab)

Bestätigt sich, dass `strictness` das Verdikt nicht beeinflusst →
die Neun-Evaluator-Redundanz kauft nichts an Verifikation → Follow-up ist
**Differenzierung** (verschiedene Regeln/Datenquellen) **ODER Reduktion**,
nicht Toleranz-Multiplikator allein
(`abs(delta) <= 0.01 * strictness` erzeugt nur Uneinigkeit im schmalen Band
um 0.01 und keine meaningful Unabhängigkeit).

## Tests

`scripts/test_evaluator_redundancy.py`
