# Rescue-Koordination — Emergence-Messung: Phasen-Pull, RoE und RNG-Trennung

**Status:** Abgeschlossen — Befund fixiert, bevor weiter experimentiert wird  
**Datum:** 2026-08-16  
**Commits:** Fundament `a90c1617` · Simulation `52828df1` · Clearance/RoE `4f80da57` · RNG-Trennung `ccf63be5`  
**Charakter:** Ergebnissoffene Messung, α=0.01 vorab registriert. Keine der drei Aussagen war vor der Messung gesetzt.

---

## 1. Fragestellung

Drei Fragen an den zivilen Rettungsschwarm (9 Agenten, 3 Klassen, Gewaltenteilung):

1. **Emergiert Koordination aus der Interaktion** — oder muss sie durch einen geteilten Takt gesetzt werden?
2. **Sind Einsatzregeln/Freigaben (RoE) eine Kopplung zweiter Ordnung** — synchronisiert der Clearance-Prozess die OODA-Zyklen zusätzlich?
3. **Sind die Vergleiche methodisch sauber** — oder erzeugen Artefakte Schein-Befunde?

## 2. Das System

9 Rettungsagenten in drei Klassen (Gewaltenteilung; Code in `agents_b2g/rescue/`):

| Klasse | Agenten | Rolle |
|---|---|---|
| **A — Lageerkundung** | DamageAssessment, SurvivorDetection, AerialMapping | erkennen, keine Wirkmittel |
| **B — Rettung & Versorgung** | SearchRescue, MedicalResponse, Infrastructure | retten, keine Befehlsgewalt |
| **C — Führung & Unterstützung** | IncidentCommand, Logistics, Coordination | freigeben/versorgen, keine Feldaktion |

Kopplungsmechanismus ist der **Nachrichten-Phase-Pull**: sendet Einheit X eine handlungsrelevante Nachricht an Y, wird Y's OODA-Phase in Richtung X's Sende-Phase gezogen (Puls-Kopplung). **Kein globales Taktsignal, kein geteiltes Feld.** Szenario-Injektion (Schadensmeldungen) ist exponentiell, nicht-periodisch.

Der **RoE-Baustein** (Clearance) ergänzt: Ein strukturell unsicheres Gebiet darf von Klasse B nicht betreten werden, bevor Klasse C eine Infrastruktur-Freigabe erteilt — informiert durch eine unabhängige Struktur-Einschätzung (Klasse B Infrastructure). Der Responder kann sich nicht selbst freigeben.

## 3. Methodik

- **Phasen:** OODA-Zyklus pro Einheit, θ_j(t) = 2π·(t − t_cycle_start)/T_ooda_j. Individuelle Zykluszeiten 8–40 s.
- **Metrik:** Kuramoto-Ordnungsparameter R = |mean(exp(iθ_j))| über die operativen Einheiten.
- **Nullhypothese:** **Phasen-Offset-Shuffle** (erhält die Zyklusperiode jeder Einheit, randomisiert die relative Phase). **Nicht IAAFT** — die Lektion aus dem Wirtschafts-Dossier (`WIRTSCHAFTS_SCHWARM_DOSSIER.md`): IAAFT kann auf periodischen Signalen artefaktische Signifikanz erzeugen.
- **Signifikanz:** α = **0.01 vorab registriert** (konsistent über alle Messungen, kein p-Hacking). Monte-Carlo mit **+1-Korrektur** p=(k+1)/(n+1), n=500 Surrogate → p-Minimum 1/501 ≈ 0.002, nie `p=0.0000`.
- **Szenario-Vergleichbarkeit:** A/B-Vergleiche nur bei **identischem Szenario-Stream** (RNG-Trennung, s. Befund 3).

## 4. Befund 1 — Phasen-Pull-Koordination ist real, aber szenarioabhängig

| Szenario | detected | R | p | Status |
|---|---|---|---|---|
| dicht (seed 42, 600 s, vor RNG-Trennung) | 90 | **0.7582** | **0.002** | **COORDINATED** |
| dünner (seed 42, 600 s, nach RNG-Trennung) | 68 | 0.6206 | 0.0259 | UNCOORDINATED |

Im dichten Szenario emergiert signifikante Phasen-Kohärenz **ausschließlich aus dem Nachrichten-Phase-Pull** — ohne geteilten Takt. Das ist der Nachweis, dass Koordination aus Interaktion entstehen kann, nicht gesetzt werden muss.

**Aber:** Die beiden Zeilen sind **verschiedene Szenarien** (die RNG-Trennung änderte den Szenario-Stream, daher detected 90 vs. 68) und nicht direkt vergleichbar. Die Koordination ist **szenarioabhängig**.

**Arbeitshypothese (systematisch getestet, falsifiziert):** Koordination skaliert mit der **Interaktionsdichte** — mehr Opfer/Gebiete → mehr Nachrichten → mehr Phase-Pull → mehr Kohärenz. → **Falsifiziert** in der vorab registrierten Multi-Seed × Dichte-Studie (`docs/RESCUE_DICHTE_STUDIE.md`, Commit `17b0bc54`): Spearman ρ negativ (−0.34 / −0.44), Verdict **NOT_CONFIRMED** in baseline und Clearance. Die beiden Datenpunkte oben waren kein genereller Mechanismus. **Szenarioabhängigkeit bleibt; der Dichte-Mechanismus ist falsch; was Koordination bestimmt, ist offen.**

## 5. Befund 2 — RoE ist Access-Control, kein Timing-Koppler (Falsifikation)

Sauberes A/B nach RNG-Trennung, **identisches Szenario** (detected=68 beiderseits), seed 42, 600 s, α=0.01:

| | Clearance aus | Clearance an | Δ |
|---|---|---|---|
| R | 0.6206 | 0.6169 | **−0.0037** |
| p | 0.0259 | 0.0259 | 0 |
| Status | UNCOORDINATED | UNCOORDINATED | — |
| served | 33 | 32 | −1 (Delay-Kosten) |
| msgs | 46 | 54 | +8 (Assessment/Clearance) |
| assigned | 61 | 66 | +5 |
| clearances | — | 6 / 19 areas | — |

**ΔR ≈ 0**: Die Freigaben ändern den OODA-Ordnungsparameter **nicht messbar**. Die Hypothese *„Freigaben sind eine Kopplung zweiter Ordnung"* ist damit auf OODA-Ebene **falsifiziert**.

Was die RoE stattdessen tut: Sie steuert den **Zugang** (wer ein unsicheres Gebiet betreten darf), nicht das **Timing** (wann die OODA-Zyklen alignen). Mehr Nachrichten (+8), mehr zugewiesene Gebiete (+5, weil die Clearance unsichere Gebiete freigibt statt dauerhaft zu blockieren), eine Rettung weniger im Zeitfenster (−1, der Sicherheits-Delay).

Das ist eine **korrekte Gewaltenteilung**: Sicherheitsfreigaben sind ein Access-Control-Mechanismus, kein Synchronisationsmechanismus. Wäre die RoE ein starker Koppler, würde sie Einsatzzeiten diktieren — starr und unrealistisch. (Der frühere scheinbare COORDINATED→UNCOORDINATED-Flip war der RNG-Confound, s. Befund 3.)

## 6. Befund 3 — RNG-Confound als Methodik-Lektion

Der vor der RNG-Trennung beobachtete Flip *„ohne Gate COORDINATED, mit Gate UNCOORDINATED"* war **vollständig ein Artefakt**: `ScenarioGenerator` und das Clearance-Assessment teilten sich einen RNG-Stream. Das Assessment verbrauchte RNG-Werte und verschob damit die Szenario-Generierung — mit/ohne Clearance entstanden verschiedene Schadenslagen (detected 90 vs. 122 im damaligen Lauf). Der Koordinations-Unterschied war dem Gate **nicht** zuschreibbar.

**Fix (`ccf63be5`):** eigener Szenario-Stream (`ScenarioGenerator(random.Random(seed + 1000003))`), Assessment auf separatem Stream. Danach ist die Schadenslage mit/ohne Clearance identisch, und das A/B in Befund 2 ist gültig.

**Lehre (verallgemeinerbar):** Jeder A/B-Vergleich verlangt **szenario-identische Streams**. Ein geteilter RNG zwischen Szenario-Generierung und experimenteller Behandlung ist ein Confound. Analog zur IAAFT-Lektion aus dem Wirtschafts-Dossier: Erst die passende Methodik macht den Befund belastbar.

## 7. Einschränkungen & Ausblick

- **Befund 1** beruht auf zwei Szenarien (ein COORDINATED, ein UNCOORDINATED). Die Dichte-Hypothese als Erklärung ist **falsifiziert** (`docs/RESCUE_DICHTE_STUDIE.md`); Szenarioabhängigkeit und der offene Mechanismus bleiben.
- **Befund 2** ist sauber (szenario-identisches A/B) und abgeschlossen.
- **Befund 3** ist eine dauerhafte Methodik-Regel.
- **α=0.01-Grenzfälle:** Die dünnen Läufe liegen bei p≈0.026 (zwischen 0.01 und 0.05) — schwaches Koordinationssignal, korrekt als UNCOORDINATED berichtet. Kein p-Hacking.

## 8. Reproduktion

```bash
cd /Volumes/THX_OS_ULTRA\ -\ Data/Users/olivermueller/agent_x_storage

# Test-Suiten (Fundament + Simulation + Clearance)
python3 -m pytest scripts/test_rescue.py scripts/test_rescue_simulation.py \
                  scripts/test_rescue_clearance.py -v

# Befund 1: Koordination (dichtes Szenario = frühe RNG-Belegung)
python3 -c "
from agents_b2g.rescue.simulation import RescueSimulation
print(RescueSimulation(seed=42, duration_s=600.0).run()['summary'])
"

# Befund 2: RoE-A/B (szenario-identisch nach RNG-Trennung)
python3 -c "
from agents_b2g.rescue.simulation import RescueSimulation
for gate in (False, True):
    r = RescueSimulation(seed=42, duration_s=600.0, enable_clearance=gate).run()
    print(('Clearance AN ' if gate else 'Clearance AUS'), r['summary'])
"
```
