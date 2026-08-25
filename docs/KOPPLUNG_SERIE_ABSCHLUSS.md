# Kopplungs-Serie — Strang-Abschluss

**Status:** STRANG GESCHLOSSEN · 2026-08-25  
**Charakter:** Keine neue Pre-Reg. Die Serie hat ihre Frage beantwortet.  
**Letzte Studie:** `KOPPLUNG_LEDGER_v1` · Artefakte `agents_b2g/emergence/kopplung_ledger_v1/`

---

## Frage der Serie

Erzeugt Taktraten-Kopplung an eine **partnerselektive** Größe unter Intervention κ
eine shuffle-sensitive Kohärenz (Arm B vs. Arm C / §1.1)?

## Antwort

**Nein — in dieser Architektur nicht parametrisierbar.**

§1.1 ist hier kein Messfehler, keine falsche Größe und keine falsche Transformation.
Es ist ein struktureller Befund über die Kopplungsdynamik.

---

## Fünf Studien

| Studie | Größe | Vorbedingung | Sweep | Grund |
|--------|-------|--------------|-------|-------|
| `KOPPLUNG_QUEUE` | Queue-Länge | partnerblind | `KOPPLUNG_INVALID` | Größe ungeeignet |
| `KOPPLUNG_REPUTATION_v1` | Honor | `I1_FAILED` | gesperrt | Sättigung |
| `KOPPLUNG_EIJ_v1` | E_ij (parametrisch) | `I1_PASS` | `KOPPLUNG_INVALID` | Arm-C-Kohärenz |
| `PARTNERSELECT_SCREEN_v1` | Knoten-Screen | `NONE_CLOSE` | — | keine Größe |
| `KANTEN_LEDGER_v1` | Ledger-Bau | `LEDGER_SCREEN_PASS` | — | Abnahme, kein Sweep |
| **`KOPPLUNG_LEDGER_v1`** | **Kanten-Ledger (gebaut)** | **PASS + Per-κ INTACT** | **`KOPPLUNG_INVALID`** | **Arm-C-Kohärenz** |

Drei Größenklassen — Queue, Reputation/Edge, bewusst gebautes Kanten-Ledger — die
letzte vorab *und durchgehend* als partnerselektiv belegt. Dieselbe Antwort.

---

## Was `KOPPLUNG_LEDGER_v1` zusätzlich absichert

```text
intact_kappas:  alle κ · beide Größen · 6/6 Seeds
PRECONDITION_LOST:  nirgends
Spot κ=0:  PASS (kein SIGNAL_BLIND)
§1.1:  widerlegt bei κ=0.2 (C 4/6 L1 · C 6/6 L2)
Gate B↔C ≥4/6:  nirgends
```

Die Per-κ-Vorbedingung hat gehalten — und genau deshalb trägt der Befund.
Die Ausrede „endogene Dynamik frisst Selektivität“ ist ausgeschlossen.

## Formulierung (bindend für diesen Strang)

> Auch mit einer nachweislich und dauerhaft partnerselektiven Kopplungsgröße
> erzeugt die permutierte Zuordnung dieselbe Kohärenz. Die Kohärenz hängt nicht
> daran, **mit wem** ein Agent gekoppelt ist, sondern nur daran, **dass**
> moduliert wird.

Nicht die Kopplungsgröße war das Problem, sondern dass die **Antwort** der Agenten
sich nicht nach Partner unterscheidet. Neun rollengleiche Evaluatoren in einem
nahezu vollständigen Graphen reagieren auf jedes Signal derselben Verteilung
gleich — unabhängig davon, wer es liefert. Relationale Kohärenz setzt voraus,
dass nicht nur der Eingang, sondern auch die Reaktion beziehungsabhängig ist.

## Der Ertrag des Kontrollarms

Ohne Arm C hätte jede der drei Sweep-Studien leicht `COUPLED` gemeldet
(r≈0,24–0,30, p signifikant, Divergenz intakt, über Seeds stabil). Dreimal ein
sauberes Positivergebnis — dreimal falsch. **Arm C ist die Regel für alles, was
danach kommt.**

---

## Was dieser Strang nicht öffnet

Keine neue Pre-Reg. Keine Schwellen-Nachjustierung. Keine Re-Analyse versiegelter
Datensätze.

Wenn der Strang je wieder aufgenommen wird, muss die **Kopplungsdynamik** selbst
anders sein (Partner-abhängige Antwort), nicht nur die Größe. Das wäre ein neuer
Strang mit neuer Fragestellung — nicht die Fortsetzung dieser Serie.

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
| `agents_b2g/emergence/kopplung_ledger_v1/ABSCHLUSS.md` | letzte Studie |
