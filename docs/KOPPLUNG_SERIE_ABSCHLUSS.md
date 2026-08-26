# Kopplungs-Serie — Familien-Abschluss (final)

**Status:** **FAMILIE GESCHLOSSEN** · 2026-08-26 · 10 Studien  
**Commit-Siegel:** `bbb9ed29` · `P1_ONLY — κ relational, coherence not`  
**Charakter:** Keine neue Pre-Reg in **dieser** Architekturfamilie
(Tick-Modulation · ereignisgetriebene Kopplung · Reziprozitäts-Verstärkung).  
**Letzte Studie:** `RECIPROCITY_AMP_KOPPLUNG_v0` · Artefakte
`agents_b2g/emergence/reciprocity_amp_kopplung_v0/`

```text
Tick-Serie:       7× KOPPLUNG_INVALID  — Kohärenz ja, aber nicht relational
Event-Serie:      2× NO_COUPLING       — Kohärenz nein, auch nicht relational
Reziprozität-Amp: 1× P1_ONLY           — κ relational, Kohärenz nicht
```

Ein elfter Hebel in derselben Mechanik ist **unzulässig**. Dissensus oder Stateful
Graph wären die **erste Studie einer anderen Serie** — eigener Proto, eigene Frage.

---

## Frage der Familie

Erzeugt eine Intervention (κ / Amplifikation) **shuffle-sensitive Phasenkohärenz**
(Arm B vs. Kontrollarm bei matched Bedingungen / §1.1), wenn Eingang, Reaktion,
Topologie, Signalquelle oder Wechselseitigkeit partnerselektiv sind?

## Antwort

**Nein — in dieser Architekturfamilie nicht parametrisierbar.**

Geprüft und einzeln ausgeschlossen: Kopplungsgröße · Transformation ·
Reaktionsfunktion · Signalquelle · Wechselseitigkeit · kanten-lokale Symmetrie ·
Inter-Arrival · Receipt-Gate · reziprozitäts-gesteuerte Amplifikation (matched κ).

Das ist ein Negativergebnis **mit Ausdehnung**: es steckt einen Bereich ab, statt
einen Punkt zu markieren.

### Drei Architektur-Sätze (bindend)

| Architektur | Kohärenz | Relational | §1.1 |
|-------------|----------|------------|------|
| Tick-Basis | ja | nein | widerlegt |
| Event-Basis | nein | nein | gehalten |
| Reziprozität-Amp | nein (Phase) | nur κ (P1) | gehalten (§1.1d) |

```text
Tick-Basis:    erzeugt Kohärenz, aber nicht relational (Arm C koppelt auch)
Event-Basis:   erzeugt keine Kohärenz, auch nicht relational
Reziprozität:  verstärkt κ relational, erzeugt aber keine Phasenkohärenz
```

---

## Positivbefund, der den Abschluss überlebt: F8 / P1

In zehn Studien ist **eine** Stelle relational positiv — und sie gehört eigenständig
benannt, nicht als Nebenspalte eines Fehlschlags:

> **Reziprozitäts-gesteuertes κ-Wachstum (F8) wirkt relational auf die
> Kopplungsstärke:** κ̄ ≈ 1,5 auf echten Kanten gegen ≈ 0,2 auf permutierten
> (Faktor ~7,5; Sweep `RECIPROCITY_AMP`, P1 6/6 ab α=0.1).

Die Beziehung wirkt auf **κ**, nicht auf die **Phase**. Arm D (matched κ̄_B, π-Zuordnung)
zeigt: bei gleicher Stärke entsteht kein Gate B↔D (`P1_ONLY`). Das trennt
Stärke-Effekt von Ordnungs-Effekt — erstmals zurechenbar, ohne Konfund.

---

## Übertragbares Instrumentarium

Unabhängig von der Kohärenz-Frage bleibt das Messwerk für jeden neuen Strang:

| Instrument | Rolle |
|------------|-------|
| Kontrollarm (C / D matched) | verhindert plausibles Falsch-`COUPLED` |
| Batterie A∧B∧C | Fitness in Sekunden statt Minuten |
| Vorbedingung **pro Stufe** | kein einmaliges Vorab-OK |
| 16s-Proto-Gate | Fail → verwerfen, kein Pre-Reg-Overhead |
| `r_floor = 1/√N + 0.15` · N explizit | Effektstärke an Zufallsboden gebunden |
| HARKing-Sperren · versiegelte Artefakte | keine Nachjustierung nach Datenblick |

---

## Tick-Strang (Studien 1–7) — versiegelt

| Studie | Ebene | Sweep | Grund |
|--------|-------|-------|-------|
| `KOPPLUNG_QUEUE` | Eingangsgröße | `INVALID` | Größe ungeeignet |
| `KOPPLUNG_REPUTATION_v1` | Eingangsgröße | gesperrt | Sättigung |
| `KOPPLUNG_EIJ_v1` | E_ij | `INVALID` | Arm-C-Kohärenz |
| `PARTNERSELECT_SCREEN_v1` | Knoten-Screen | — | keine Größe |
| `KANTEN_LEDGER_v1` | Ledger-Bau | — | Abnahme |
| `KOPPLUNG_LEDGER_v1` | Ledger | `INVALID` | Arm-C-Kohärenz |
| `CLOSED_LOOP_KOPPLUNG_v0` | φ_L + R_ij | `INVALID` | Arm-C-Kohärenz |
| `EDGE_LOCAL_KOPPLUNG_v0` | κ_ij · h↔ | `INVALID` | Arm-C ab κ=0.2 |

**Tick-Formulierung:** Kohärenz hängt nicht daran, *mit wem* gekoppelt wird, sondern
daran, *dass* taktraten-moduliert wird. Zu effektiv für §1.1.

---

## Ereignis-Strang (Studien 8–10) — versiegelt

### 8 · `EVENT_DRIVEN_KOPPLUNG_v0` → `NO_COUPLING` · §1.1 gehalten

Erstes Halten von §1.1; Arm B und C brechen gemeinsam.

### 9 · `RECIPROCAL_EVENT_KOPPLUNG_v0` → `NO_COUPLING` · §1.1 gehalten

κ verdrahtet (T_mean −25 %), r flach. Echtes Negativ, kein Wiring-Fail.
Sockel = `1/√9`. Vorab-Korrektur: `r_floor = 1/√N + 0.15`.

### 10 · `RECIPROCITY_AMP_KOPPLUNG_v0` → `P1_ONLY` · §1.1d gehalten

Vierarm A/B/C/D · Gate B↔D (matched κ) · P1 YES 6/6 · P2 0/6.

---

## Was diese Familie nicht öffnet

- Keine Studie 11 in Tick / Event / Reziprozitäts-Amp  
- Kein Hybrid Tick/Event  
- Keine Schwellen-Nachjustierung an versiegelten Datensätzen  

**Neuer Strang** (Dissensus & Niche · Stateful Graph Automata): erlaubt nur mit
eigenem 16s-Proto, eigener Pre-Reg, eigenen Seeds — **Serie 1**, nicht Studie 11.

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
| `docs/CLOSED_LOOP_KOPPLUNG_v0_PREREG.md` | Closed-Loop · INVALID |
| `docs/EDGE_LOCAL_KOPPLUNG_v0_PREREG.md` | Edge-Local · INVALID · Tick letzte |
| `docs/EVENT_DRIVEN_KOPPLUNG_v0_PREREG.md` | Event · `NO_COUPLING` |
| `docs/RECIPROCAL_EVENT_KOPPLUNG_v0_PREREG.md` | Reciprocal-Event · `NO_COUPLING` |
| `docs/RECIPROCITY_AMP_KOPPLUNG_v0_PREREG.md` | Amp · Vierarm · `P1_ONLY` |
| `agents_b2g/emergence/reciprocity_amp_kopplung_v0/` | Studie 10 · Familien-Siegel |
