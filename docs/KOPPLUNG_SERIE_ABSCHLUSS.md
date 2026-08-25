# Kopplungs-Serie — Strang-Abschluss (final)

**Status:** STRANG GESCHLOSSEN · 2026-08-25  
**Charakter:** Keine neue Pre-Reg in diesem Strang. Die Serie hat ihre Frage beantwortet.  
**Letzte Studie:** `CLOSED_LOOP_KOPPLUNG_v0` · Artefakte `agents_b2g/emergence/closed_loop_kopplung_v0/`

---

## Frage der Serie

Erzeugt Taktraten-Kopplung unter Intervention κ eine **shuffle-sensitive** Kohärenz
(Arm B vs. Arm C / §1.1), wenn Eingang und/oder Reaktion partnerselektiv sind?

## Antwort

**Nein — in dieser Architektur nicht parametrisierbar.**

§1.1 ist kein Messfehler, keine falsche Größe, keine falsche Transformation und
keine fehlende Reaktions-Heterogenität. Es ist ein struktureller Befund über die
**Kopplungsdynamik** selbst: Kohärenz entsteht netzwerk-weit, sobald moduliert wird —
unabhängig davon, ob die Partnerzuordnung echt oder permutiert ist.

---

## Sechs Studien

| Studie | Ebene | Vorbedingung | Sweep | Grund |
|--------|-------|--------------|-------|-------|
| `KOPPLUNG_QUEUE` | Eingangsgröße | partnerblind | `KOPPLUNG_INVALID` | Größe ungeeignet |
| `KOPPLUNG_REPUTATION_v1` | Eingangsgröße | `I1_FAILED` | gesperrt | Sättigung |
| `KOPPLUNG_EIJ_v1` | parametrisches E_ij | `I1_PASS` | `KOPPLUNG_INVALID` | Arm-C-Kohärenz |
| `PARTNERSELECT_SCREEN_v1` | Knoten-Screen | `NONE_CLOSE` | — | keine Größe |
| `KANTEN_LEDGER_v1` | Ledger-Bau | `LEDGER_SCREEN_PASS` | — | Abnahme |
| `KOPPLUNG_LEDGER_v1` | gebautes Ledger | PASS + Per-κ INTACT | `KOPPLUNG_INVALID` | Arm-C-Kohärenz |
| **`CLOSED_LOOP_KOPPLUNG_v0`** | **φ_L + R_ij (Reaktion)** | **Batterie A∧B∧C PASS · Per-κ INTACT** | **`KOPPLUNG_INVALID`** | **Arm-C-Kohärenz** |

Alle Ebenen durchgespielt: Eingangs-Selektivität reicht nicht · Reaktions-Selektivität
reicht nicht · beides zusammen reicht nicht.

---

## Was `CLOSED_LOOP_KOPPLUNG_v0` zusätzlich absichert

```text
Spot κ=0 Seed 20261601:  Batterie A∧B∧C PASS (kein SIGNAL_BLIND)
intact_kappas:  alle κ · 6/6 Seeds
PRECONDITION_LOST:  nirgends
§1.1:  widerlegt ab κ=0.2 (Arm C 6/6 COUPLED)
Gate B↔C ≥4/6:  nirgends (0/6 auf allen κ)
```

Die Ausrede „Antwort ist partnerblind“ ist ausgeschlossen. Die Ausrede
„Vorbedingung geht unter κ verloren“ ist ausgeschlossen.

## Formulierung (bindend für diesen Strang)

> Auch mit partnerselektivem Eingang (φ_L / Ledger) **und** partnerselektiver
> Reaktion (`R_ij`, Batterie A∧B∧C) erzeugt die permutierte Zuordnung dieselbe
> Kohärenz. Die Kohärenz hängt nicht daran, **mit wem** ein Agent gekoppelt ist,
> sondern nur daran, **dass** global moduliert wird.

Die Kopplung in dieser Architektur ist zu global: sie erzeugt Kohärenz über das
gesamte Netzwerk, nicht kanten-spezifisch über echte Partner.

## Der Ertrag des Kontrollarms

Ohne Arm C hätte jede Sweep-Studie leicht `COUPLED` gemeldet. Mehrfach ein
sauberes Positivergebnis — mehrfach falsch. **Arm C bleibt die Regel.**

---

## Was dieser Strang nicht öffnet

Keine neue Pre-Reg in **dieser** Serie. Keine Schwellen-Nachjustierung.
Keine Re-Analyse versiegelter Datensätze.

Eine Fortsetzung wäre nur als **neuer Strang** mit neuer Fragestellung zulässig:

> Welche Kopplungsdynamik erzeugt **kanten-spezifische** Kohärenz statt
> netzwerk-weiter Kohärenz?

Das wäre ein neuer DRAFT mit neuer Architektur — nicht die Fortsetzung dieser Serie.

---

## Verweise

| Dokument | Rolle |
|----------|-------|
| `docs/EMERGENZ_KOPPLUNG_PREREG.md` | Queue · geschlossen |
| `docs/KOPPLUNG_REPUTATION_v1_PREREG.md` | Reputation · I1_FAILED |
| `docs/KOPPLUNG_EIJ_v1_PREREG.md` | E_ij · INVALID |
| `docs/PARTNERSELECT_SCREEN_v1_PREREG.md` | Knoten · NONE_CLOSE |
| `docs/KANTEN_LEDGER_v1_DRAFT.md` | Ledger-Bau · PASS |
| `docs/KOPPLUNG_LEDGER_v1_PREREG.md` | Ledger-Sweep · INVALID |
| `docs/CLOSED_LOOP_RESPONSE_v0_DRAFT.md` | Schritt-2 Batterie · PASS |
| `docs/CLOSED_LOOP_KOPPLUNG_v0_PREREG.md` | Closed-Loop Sweep · INVALID |
| `agents_b2g/emergence/closed_loop_kopplung_v0/` | letzte Studie |
