# Kopplungs-Serie — Strang-Abschluss (final)

**Status:** STRANG GESCHLOSSEN · 2026-08-26 (Nachzug `EDGE_LOCAL_KOPPLUNG_v0`)  
**Charakter:** Keine neue Pre-Reg in diesem Strang. Die Serie hat ihre Frage beantwortet.  
**Letzte Studie:** `EDGE_LOCAL_KOPPLUNG_v0` · Artefakte `agents_b2g/emergence/edge_local_kopplung_v0/`  
**Vorgänger-Schluss:** 2026-08-25 nach `CLOSED_LOOP_KOPPLUNG_v0` — Edge-Local war der explizit freigehaltene Folgestrang und ist jetzt ebenfalls geschlossen.

---

## Frage der Serie

Erzeugt Taktraten-Kopplung unter Intervention κ eine **shuffle-sensitive** Kohärenz
(Arm B vs. Arm C / §1.1), wenn Eingang und/oder Reaktion partnerselektiv sind —
ggf. mit wechselseitiger Topologie und kanten-lokaler Symmetrie?

## Antwort

**Nein — in dieser Architekturfamilie nicht parametrisierbar.**

§1.1 ist kein Messfehler, keine falsche Größe, keine falsche Transformation,
keine fehlende Reaktions-Heterogenität, kein Reziprozitäts-Artefakt und kein
Mangel an Kanten-Lokalität der Honorarfunktion. Es ist ein struktureller Befund
über die **Kopplungsdynamik** selbst: Kohärenz entsteht netzwerk-weit, sobald
moduliert wird — unabhängig davon, ob die Partnerzuordnung echt oder permutiert ist.

---

## Sieben Studien

| Studie | Ebene | Vorbedingung | Sweep | Grund |
|--------|-------|--------------|-------|-------|
| `KOPPLUNG_QUEUE` | Eingangsgröße | partnerblind | `KOPPLUNG_INVALID` | Größe ungeeignet |
| `KOPPLUNG_REPUTATION_v1` | Eingangsgröße | `I1_FAILED` | gesperrt | Sättigung |
| `KOPPLUNG_EIJ_v1` | parametrisches E_ij | `I1_PASS` | `KOPPLUNG_INVALID` | Arm-C-Kohärenz |
| `PARTNERSELECT_SCREEN_v1` | Knoten-Screen | `NONE_CLOSE` | — | keine Größe |
| `KANTEN_LEDGER_v1` | Ledger-Bau | `LEDGER_SCREEN_PASS` | — | Abnahme |
| `KOPPLUNG_LEDGER_v1` | gebautes Ledger | PASS + Per-κ INTACT | `KOPPLUNG_INVALID` | Arm-C-Kohärenz |
| `CLOSED_LOOP_KOPPLUNG_v0` | φ_L + R_ij (Reaktion) | Batterie A∧B∧C · Per-κ INTACT | `KOPPLUNG_INVALID` | Arm-C-Kohärenz |
| **`EDGE_LOCAL_KOPPLUNG_v0`** | **κ_ij · h↔ · Wechselseitigkeit** | **Batterie ∧ via_led≥0.3 · trimmed_m7** | **`KOPPLUNG_INVALID`** | **Arm-C-Kohärenz ab κ=0.2** |

Eliminiert: Eingangs-Selektivität · Reaktions-Selektivität · Wechselseitigkeit ·
symmetrische Paar-Ehre \(h^{\leftrightarrow}=\tfrac12(h_{ij}+h_{ji})\).

---

## Was `CLOSED_LOOP_KOPPLUNG_v0` absichert

```text
Spot κ=0 Seed 20261601:  Batterie A∧B∧C PASS (kein SIGNAL_BLIND)
intact_kappas:  alle κ · 6/6 Seeds
PRECONDITION_LOST:  nirgends
§1.1:  widerlegt ab κ=0.2 (Arm C 6/6 COUPLED)
Gate B↔C ≥4/6:  nirgends
```

Ausrede „Antwort partnerblind“ und „Vorbedingung bricht unter κ“ ausgeschlossen.

## Was `EDGE_LOCAL_KOPPLUNG_v0` zusätzlich absichert

```text
Spot κ=0 Seed 20261801:  Batterie A∧B∧C PASS · via_led=1.0
F4 trimmed_m7 · F5 ACK/Receipt · h↔ Paar-Mittel
intact:  κ∈{0,0.2,0.4,0.6,1.2} → 6/6; κ=0.8 → 5/6
§1.1:  widerlegt ab κ=0.2 (Arm C 6/6 COUPLED)
Gate B↔C ≥4/6:  nirgends (max 1/6 bei κ=0.4)
κ=1.2: C-COUPLED 1/6 — kein §1.1-Gewinn (eher Überkopplung / anderer Zustand)
```

Ausrede „fehlende Rückkanten“ und „asymmetrische / globale `1+κ·h`-Formel“ ausgeschlossen.

## Formulierung (bindend für diesen Strang)

> Auch mit partnerselektivem Eingang, partnerselektiver Reaktion, wechselseitiger
> Sticky/Ledger-Topologie und kanten-lokaler symmetrischer Intervention
> (\(h^{\leftrightarrow}\)) erzeugt die permutierte Zuordnung dieselbe Kohärenz.
> Die Kohärenz hängt nicht daran, **mit wem** ein Agent gekoppelt ist, sondern
> nur daran, **dass** taktraten-moduliert wird.

Die Kopplung ist nicht zu schwach — sie ist **zu effektiv**: sie erzeugt Kohärenz
auch dort, wo keine echte Partnerschaft besteht.

## Der Ertrag des Kontrollarms

Ohne Arm C hätte jede Sweep-Studie leicht `COUPLED` gemeldet. Mehrfach ein
sauberes Positivergebnis — mehrfach falsch. **Arm C bleibt die Regel.**

---

## Was dieser Strang nicht öffnet

Keine neue Pre-Reg in **dieser** Serie. Keine Schwellen-Nachjustierung.
Keine Re-Analyse versiegelter Datensätze. Keine Nachinterpretation von κ=1.2
als „Edge-Local greift“.

Eine Fortsetzung wäre nur als **neuer Strang** mit **fundamental anderer
Dynamik** zulässig, z. B.:

> Ereignisbasierte statt iterative Modulation; differenzverstärkend statt
> kohärenzerzeugend — so dass Arm C keine netzwerk-weite Kohärenz mehr erzwingt.

Das ist eine bewusste Architekturentscheidung — nicht die Fortsetzung dieser Serie.

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
| `docs/EDGE_LOCAL_KOPPLUNG_v0_PREREG.md` | Edge-Local · BINDEND · INVALID |
| `agents_b2g/emergence/closed_loop_kopplung_v0/` | Studie 6 |
| `agents_b2g/emergence/edge_local_kopplung_v0/` | Studie 7 (letzte) |
