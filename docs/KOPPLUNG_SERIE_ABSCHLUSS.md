# Kopplungs-Serie — Strang-Abschluss (final)

**Status:** TICK-STRANG GESCHLOSSEN · 2026-08-26 (`EDGE_LOCAL_KOPPLUNG_v0`)  
**Charakter:** Keine neue Pre-Reg in **diesem** (Tick-)Strang. Die iterative Frage ist beantwortet.  
**Letzte Tick-Studie:** `EDGE_LOCAL_KOPPLUNG_v0` · Artefakte `agents_b2g/emergence/edge_local_kopplung_v0/`  
**Neuer Strang (offen):** `EVENT_DRIVEN_KOPPLUNG_v0` — siehe unten § Ereignis-Strang.  
**Vorgänger-Schluss:** 2026-08-25 nach `CLOSED_LOOP_KOPPLUNG_v0` — Edge-Local war der explizit freigehaltene Folgestrang der Tick-Serie und ist jetzt ebenfalls geschlossen.

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

Keine neue Pre-Reg in **dieser Tick-Serie**. Keine Schwellen-Nachjustierung.
Keine Re-Analyse versiegelter Datensätze. Keine Nachinterpretation von κ=1.2
als „Edge-Local greift“.

Eine Fortsetzung der **Tick-Architektur** ist unzulässig. Der Ereignis-Strang
ist ein **anderer Strang** (siehe unten) — nicht Studie 8 der Tick-Serie.

---

## Ereignis-Strang (offen, 2026-08-26)

**Studie:** `EVENT_DRIVEN_KOPPLUNG_v0`  
**Pre-Reg:** `docs/EVENT_DRIVEN_KOPPLUNG_v0_PREREG.md` (BINDEND)  
**Artefakte:** `agents_b2g/emergence/event_driven_kopplung_v0/`  
**Verdict:** `NO_COUPLING` · Spot `20262001` Batterie PASS · §1.1 **gehalten**

```text
Spot κ=0 Seed 20262001:  A∧B∧C PASS (kein SIGNAL_BLIND)
intact_kappas:           alle κ · 6/6
§1.1:                    gehalten (Arm C 0–1/6 COUPLED; Mehrheit nie)
Gate B↔C ≥4/6:           nirgends (0/6 auf allen κ)
Arm B:                   ebenfalls NO_COUPLING (fast überall)
```

**Meilenstein:** Erstes Mal in der Kopplungs-Forschung, dass Arm C den Konsens-Attraktor
**nicht** mehrheitlich erzwingt. Die Nullhypothese bleibt über **fehlendes Gate**,
nicht über §1.1-Fail.

### Folgestudie: `RECIPROCAL_EVENT_KOPPLUNG_v0`

**Pre-Reg:** `docs/RECIPROCAL_EVENT_KOPPLUNG_v0_PREREG.md` (BINDEND)  
**Artefakte:** `agents_b2g/emergence/reciprocal_event_kopplung_v0/`  
**Verdict:** `NO_COUPLING` · Spot `20262201` Batterie PASS · §1.1 **gehalten**

```text
Spot κ=0 Seed 20262201:  A∧B∧C PASS
intact_kappas:           alle κ · 6/6
§1.1:                    gehalten (Arm C 0/6 COUPLED)
Gate B↔C ≥4/6:           nirgends
r_B:                     flach (≈0.28–0.31; Span≈0.028 < sd_pool≈0.045)
Verdrahtung:             κ ANGESCHLOSSEN (T_mean Δ≈−0.33; States/Messages ≠)
```

**Befund:** Design funktioniert (Kontrollarm unten → interpretierbar). Modulation
ändert Timing/Zustand, erzeugt aber keine Phasenkohärenz — **echtes Negativ**,
kein Wiring-Fail. Offene Frage des Ereignis-Strangs bleibt:

> Wie erzeugt man Gate-fähige Kohärenz auf Arm B, ohne §1.1 zu verlieren?

Hybrid Tick-für-B / Event-für-C ist ein Rückfall in die versiegelte Tick-Serie
und **nicht** zulässig.

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
| `docs/EDGE_LOCAL_KOPPLUNG_v0_PREREG.md` | Edge-Local · BINDEND · INVALID · Tick-Serie letzte |
| `docs/EVENT_DRIVEN_KOPPLUNG_v0_PREREG.md` | Ereignis-Strang · BINDEND · `NO_COUPLING` |
| `docs/RECIPROCAL_EVENT_KOPPLUNG_v0_PREREG.md` | Reziprozitäts-Event · BINDEND · `NO_COUPLING` · §1.1 JA |
| `agents_b2g/emergence/closed_loop_kopplung_v0/` | Studie 6 |
| `agents_b2g/emergence/edge_local_kopplung_v0/` | Studie 7 (letzte Tick-Studie) |
| `agents_b2g/emergence/event_driven_kopplung_v0/` | Ereignis-Strang Studie 1 |
| `agents_b2g/emergence/reciprocal_event_kopplung_v0/` | Ereignis-Strang Studie 2 |
