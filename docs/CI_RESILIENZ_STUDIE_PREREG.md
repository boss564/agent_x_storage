# CI-Resilienz-Studie — Vorab-registriertes Studien-Design

**Status:** Pre-Registration — Auswertungsregel festgelegt, bevor Code entsteht  
**Datum:** 2026-08-16  
**Charakter:** Vorab registriert. Keine Regel-Justage nach Daten-Sichtung.

---

## 1. Fragestellung & Hypothesen

Der CI-Schwarm (9 Agenten, Klassen A Sensorik / B Aktorik / C Koordination,
feste Takte 1/5/10 s) wird nicht nur im Normalbetrieb gemessen, sondern unter
Stress. Die Frage ist nicht „entsteht Koordination?" (das ist im Rescue-Track
beantwortet), sondern: **Ist R ein Resilienz-Indikator?**

Drei Hypothesen, in dieser Reihenfolge ausgewertet:

- **H0 (Voraussetzung):** Der CI-Schwarm ist im Normalbetrieb signifikant
  koordiniert (R_normal signifikant). *Ohne H0 ist H1/H2 nicht aussagekräftig.*
- **H1 (Degradation):** R degradiert unter einem Stress-Ereignis signifikant
  gegenüber dem Normalbetrieb.
- **H2 (Unterscheidbarkeit):** Die drei Stress-Typen erzeugen unterscheidbare
  Degradationsmuster.

## 2. Stress-Szenarien & Injektionen

Jedes Szenario injiziert bei `t_stress` einen klar definierten Störimpuls.
Die erwarteten Muster sind qualitativ verschieden — das ist der Kern von H2.

| Szenario | Injektion bei t_stress | Erwartetes Degradationsmuster |
|---|---|---|
| **Blackout** | Ein Klasse-B-Aktor (GridController) → `OUT_OF_SERVICE`, bleibt offline | **Plötzlicher** Abfall von R (abhängige Komponenten verlieren den Taktgeber) |
| **Cyber-Angriff** | Ein Klasse-A-Sensor (InfrastructureSensor) liefert manipulierte Messwerte (Offset + Rauschen); C2 entscheidet auf falscher Basis | **Schleichender** Abfall von R (Aktorik reagiert auf Fehl-Befehle, Synchronisation driftet) |
| **Naturkatastrophe** | Mehrere Agenten (1 Sensor + 1 Aktor) gleichzeitig degradiert (erhöhte Ausfallrate, reduzierte Effizienz), nicht alle | **Starker, breiter** Abfall von R (mehrere Komponenten betroffen, System arbeitet noch) |

**Abgrenzung:** Blackout = einzelne Komponente ganz aus. Cyber = Komponente
liefert falsch (nicht aus). Naturkatastrophe = mehrere Komponenten gleichzeitig
degradiert. Diese drei sind mechanisch verschieden und sollen unterscheidbar sein.

## 3. Metriken & Zeitphasen

- **Phase θ_j(t):** aus den zyklischen Mess-/Regelungsintervallen
  (Sensor 1 s, Aktor 5 s, C2 10 s), wie im CI-Design. θ_j = 2π·(t−t_cycle_start)/T_j.
- **Ordnungsparameter R(t):** |mean(exp(iθ_j))| über die operativen Einheiten.
- **Zeitphasen pro Lauf:**
  - `[0, t_warmup=60s]` — Warm-up, **nicht ausgewertet** (Einschwingen).
  - `[t_warmup, t_stress=300s]` — Normalbetrieb → **R_normal**.
  - `t_stress` — Stress-Injektion.
  - `[t_stress + burn_in=30s, t_end=600s]` — Stress-Phase → **R_stress**.
- **Degradations-Metriken:**
  - **ΔR = R_normal − R_stress** (primär, pro Lauf).
  - **Degradations-Kurve R(t)** in 30-s-Fenstern nach Stress-Beginn (deskriptiv, für H2-Muster).

## 4. Nullhypothese & Signifikanz

- **Nullhypothese für R-Signifikanz: Phasen-Offset-Shuffle** — Periode pro Einheit
  erhalten, relative Phase randomisieren. **NICHT IAAFT.** Das CI-System mit festen
  Takten (1/5/10 s) ist hochperiodisch; IAAFT wäre der dritte Artefakt-Fall
  (Lehren aus Wirtschafts- und Rescue-Dossier).
- **α = 0.01**, vorab registriert (konsistent über alle bisherigen Studien).
- **+1-Korrektur** p=(k+1)/(n+1), nie `p=0.0000`.
- **Für H1/H2 (Degradation):** gepaarter Vergleich über Seeds (Wilcoxon /
  Kruskal-Wallis), **kein** Surrogat-Test — die Frage ist R_stress < R_normal,
  nicht R > Zufall.

## 5. Design

- **10 Seeds × 3 Stress-Typen = 30 Läufe.** Jeder Lauf enthält Normalbetrieb
  (within-run baseline) + Stress-Phase. Der „nur Normalbetrieb"-Fall ist in jedem
  Lauf als `[t_warmup, t_stress]` enthalten.
- **RNG-Trennung:** Der Szenario-Stream (normale Last) ist identisch über alle
  drei Stress-Typen desselben Seeds und unabhängig vom Stress-Injektions-Stream.
  → Der between-Stress-Vergleich ist szenario-kontrolliert (Lehre aus der
  Rescue-Dichte-Studie: kein geteilter RNG zwischen Behandlung und Szenario).
- **Konstant:** Duration 600 s, dt=1 s, coupling=0.30, t_warmup=60, t_stress=300,
  burn_in=30, α=0.01.

## 6. Vorab-registrierte Auswertungsregel

**Schritt 0 — H0 prüfen (Voraussetzung):**

- R_normal via Phasen-Offset-Shuffle in ≥ 7/10 Läufen pro Stress-Typ signifikant
  (p < 0.01). → Normalbetrieb ist koordiniert.
- **Wenn H0 nicht erfüllt:** Studie ist nicht aussagekräftig. Die Takte/Kopplung
  müssen so angepasst werden, dass der Normalbetrieb koordiniert ist, bevor H1/H2
  ausgewertet werden. *Dies ist ein Design-Stopp, keine nachträgliche Regel-Justage.*

**Schritt 1 — H1 (Degradation), pro Stress-Typ:**

- ΔR = R_normal − R_stress über die 10 Seed-Paare.
- Einseitiger Wilcoxon-Vorzeichen-Rang-Test (H1: ΔR > 0), α=0.01.
- **Bestätigt** für einen Stress-Typ: ΔR > 0 und p < 0.01.
- **Falsifiziert** für einen Stress-Typ: ΔR ≤ 0 oder p ≥ 0.01.

**Schritt 2 — H2 (Unterscheidbarkeit), nur wenn H1 für ≥ 2 Typen bestätigt:**

- Kruskal-Wallis-Omnibus über die ΔR-Werte der drei Stress-Typen.
- Deskriptive Degradations-Kurven R(t) pro Stress-Typ (Muster-Vergleich).
- **Bestätigt:** Kruskal-Wallis p < 0.05 (omnibus).
- **Falsifiziert:** Kruskal-Wallis p ≥ 0.05.

**Keine nachträgliche Justage:** Die Schwellen (α=0.01, H0 ≥ 7/10, Kruskal-Wallis
p < 0.05) stehen, bevor Daten gesichtet werden. Ein „fast signifikant" wird nicht
umgedeutet.

## 7. Methodik-Lektionen (aus den früheren Dossiers)

| Lektion | Quelle | Anwendung hier |
|---|---|---|
| IAAFT artefaktisch auf periodischen Signalen | Wirtschafts- + Rescue-Dossier | **Phasen-Offset-Shuffle**, nicht IAAFT |
| RNG-Confound zwischen Behandlung und Szenario | Rescue-Koordination | RNG-Trennung, szenario-kontrollierter Vergleich |
| Zwei Datenpunkte sind keine Linie | Rescue-Dichte-Studie | 10 Seeds pro Bedingung |
| p-Hacking vermeiden | Rescue-Dichte-Studie | Vorab-registrierte Auswertungsregel, α=0.01 |
| +1-Korrektur, nie p=0.0000 | alle Dossiers | p=(k+1)/(n+1) |

## 8. Einschränkungen & offene Fragen

- **H0 ist nicht garantiert.** Der CI-Schwarm mit festen Takten 1/5/10 s könnte im
  Normalbetrieb *nicht* koordiniert sein (die Takte sind verschieden, nicht
  synchron). Dann ist die Degradations-Frage nicht sinnvoll, und das Design muss
  bei Schritt 0 stoppen. Das ist eine echte offene Frage, die die Studie beantwortet.
- **Degradationsmuster sind vorab nur qualitativ erwartet** (plötzlich/schleichend/breit).
  H2 testet quantitativ nur ΔR-Unterschiede; die Kurvenform wird deskriptiv bewertet.
- **Die Studie gilt für die gewählten Parameter** (coupling=0.30, Takte 1/5/10 s,
  t_stress=300). Andere Parameter können andere Ergebnisse liefern.
- **Keine „Rettung" eines nicht-signifikanten Ergebnisses.** Wenn H1 oder H2
  falsifiziert wird, ist das ein valider Befund und wird als solcher dokumentiert
  (Lehre aus der Dichte-Studie).

## 9. Bau-Reihenfolge (festgelegt)

1. **H0-Gate** zuerst: 10 Seeds, nur Normalbetrieb `[t_warmup, t_end]` bzw.
   `[t_warmup, t_stress]` ohne Injektion; R via Phasen-Offset-Shuffle; Gate ≥ 7/10.
2. Erst bei bestandenem H0: Fundament (9 Agenten, Ressourcen-Friction) +
   getrennte Stress-Injektoren (einzeln testbar) + 30 Stress-Läufe + H1/H2.
3. Ergebnis-Dossier nach dem Lauf — keine Regel-Justage.

**IAAFT ist für diese Studie ausgeschlossen.**
