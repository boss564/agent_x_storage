# Smart Grid — Vorab-registrierte Meta-Stabilitäts-Studie (Pre-Registration)

**Status:** Pre-Registration — Auswertungsregel festgelegt, bevor Code entsteht
**Datum:** 2026-08-17
**Charakter:** Vorab registriert. Keine Regel-Justage nach Daten-Sichtung.
**Methodik-Pate:** `CI_RESILIENZ_STUDIE_PREREG.md`, `HUMANITAERE_LOGISTIK_PREREG.md`
**Vorgänger-Dossiers:** Wirtschafts-Schwarm, Rescue-Koordination, Rescue-Dichte, CI-Resilienz, Humanitäre Logistik

---

## 0. Abgrenzung zu den Vorgänger-Studien

Diese Studie ist **strukturell anders** als die fünf bisherigen:

| Aspekt | Bisherige Studien | Smart-Grid-Studie |
|---|---|---|
| Ziel-Zustand | Koordination (R→1) | **Meta-Stabilität** (kontrollierte Phasen-Divergenz) |
| Hypothese | R degradiert unter Stress | **R_grid sinkt, W_dyn bleibt stabil** (invertiert) |
| Metriken | eine (R) | **zwei** (R_grid + W_dyn), getrennte Nullhypothesen |
| Kopplung | Heartbeat (periodisch) | **Schattenpreis-getriggert** (ereignisbasiert, aperiodisch) |
| Hypothesen-Form | enkelt | **Konjunktion** (R_grid↓ UND W_dyn≥0) |

Die Studie testet die Theorie der **Meta-Stabilität**: Ein plastisches Stromnetz opfert
bewusst physikalische Kohärenz (R_grid), um die ökonomische Versorgung (W_dyn) zu
sichern. Das ist das Gegenteil der starren 50-Hz-Synchronisation.

## 1. Fragestellung & Hypothesen

Vier Hypothesen, in dieser Reihenfolge ausgewertet:

- **H0 (Mess-Validität):** R_grid und W_dyn sind im Normalbetrieb messbar und
  last-sensitiv. *Dies ist KEIN „R→1"-Test.* Ohne H0 sind H1/H2 nicht aussagekräftig.
- **H1 (Plastizität / Meta-Stabilität):** Unter Störfall gilt die **Konjunktion**
  ΔR_grid < 0 UND ΔW_dyn ≥ 0 — das System opfert Kohärenz, hält aber die Wohlfahrt.
- **H2 (Unterscheidbarkeit):** Die drei Stress-Typen erzeugen unterscheidbare
  Degradationsmuster (über die Kombination von ΔR_grid und ΔW_dyn).
- **H3 (Hebel-Attribution):** Gemäß der vorab festgelegten Attributions-Strategie
  (Abschnitt 4).

## 2. Metriken & getrennte Nullhypothesen

**Kern-Entscheidung:** R_grid und W_dyn sind fundamental verschiedene Größen und
werden mit **verschiedenen Nullhypothesen** getestet. Sie dürfen nicht mit demselben
Surrogat gemessen werden.

### 2.1 R_grid — Phasenkohärenz der Erzeuger

**Definition:** R_grid(t) = |(1/N_gen) Σ_{j∈gen} e^{iθ_j(t)}|, wobei θ_j aus dem
Regelzyklus der Wechselrichter/Synchrongeneratoren (z.B. 5-s-Takt) abgeleitet wird.
R_grid ∈ [0,1]. Typ = **zirkuläre Statistik, oszillatorisch**.

**Nullhypothese: Phasen-Offset-Shuffle** — die Phasen-Trajektorie jedes Erzeugers
wird um einen zufälligen konstanten Offset verschoben (erhält Periode und interne
Dynamik, randomisiert die relative Ausrichtung). **NICHT IAAFT.**

**Begründung:** R_grid ist eine Phasen-Kohärenz-Metrik über periodische Regelzyklen.
Phasen-Offset-Shuffle ist die in allen fünf Vorgänger-Studien etablierte Nullhypothese
für solche Metriken. IAAFT erzeugt auf periodischen Signalen Artefakte (dokumentiert
im Wirtschafts-Dossier) und ist hier ausgeschlossen.

### 2.2 W_dyn — Ökonomische Wohlfahrt (Autarkie)

**Definition (festgenagelt für diese Pre-Reg):**

```
W_dyn = Σ_last P_gedeckt / Σ_last P_bedarf
```

mit W_dyn ∈ [0,1] (bei Bedarf 0: W_dyn := 0). Typ = **beschränkter Skalar,
NICHT oszillatorisch**.

**λ-Strafterm:** Für die Primärstudie ist **λ ≡ 0** (kein zusätzlicher Multiplikator).
Würde λ als „Anteil ungedeckter Last“ gesetzt, entstünde W_dyn = c · (1 − (1−c)) = c² —
eine Doppelzählung der Unterdeckung. Ein von der Coverage unabhängiger Strafterm
(z.B. Curtailment-Anteil) bleibt einer optionalen Folgestudie vorbehalten und ist
**nicht** Teil dieser Pre-Reg.

**Nullhypothese: Gepaarter Seed-Vergleich (Wilcoxon)** — W_dyn unter Stress wird
gepaart mit W_dyn im Normalbetrieb verglichen, über die 10 Seeds. **Kein
Phasen-Surrogat, kein IAAFT.**

**Begründung:** W_dyn ist eine Wohlfahrts-Kennzahl, keine Schwingung. Ein Phasen-Shuffle
ergibt dafür keinen Sinn. Der korrekte Test ist der gepaarte Vergleich über Seeds,
analog zum ΔR-Test in der CI-Studie.

## 3. Stress-Szenarien & Hebel-Zuordnung

Drei mechanisch verschiedene Störfälle, jeweils einem anderen Architektur-Hebel
zugeordnet. Dies ermöglicht **partielle Attribution** auch bei kombiniertem Effekt.

| Szenario | Injektion | Primär geforderter Hebel |
|---|---|---|
| **Bewölkung** | PV-Einspeisung bricht plötzlich ein | **Schattenpreise** + Speicher-Dispatch |
| **Spitzenlast** | EV-Flotte lädt gleichzeitig (Last-Spike) | **Flexibilität** + Lastverschiebung (Wärmepumpen, EV) |
| **Leitungsausfall** | Ein Netzsegment wird getrennt | **Hebb'sches Um-Routing** + Curtailment |

**Abgrenzung:** Bewölkung trifft die Erzeugung (Klasse A). Spitzenlast trifft die
Flexibilität (Klasse B). Leitungsausfall trifft die Netztopologie (Klasse C + Routing).
Diese drei sind mechanisch verschieden und fordern unterschiedliche Hebel.

## 4. Hebel-Attribution — vorab festgelegt

**Entscheidung: Kombinierter Effekt** für die Primärstudie. Alle vier Hebel
(Schattenpreise, Aktive Inferenz, Hebb'sche Plastizität, Kuramoto-Phase) sind
gleichzeitig aktiv. Die Studie misst das System als Ganzes.

**Partielle Attribution** erfolgt über die Stress-Typ-zu-Hebel-Zuordnung (Abschnitt 3):
Da jeder Störfall einen anderen Hebel primär fordert, lässt sich aus dem
Degradationsmuster pro Stress-Typ auf die Beteiligung des jeweiligen Hebels schließen.

**Abgestufte Aktivierung** (einzelne Hebel isoliert) ist als **optionale Folgestudie**
dokumentiert, falls die Primärstudie Attribution erfordert. Sie ist NICHT Teil dieser
Pre-Reg.

*Begründung der Wahl:* Die Primärstudie soll das Systemverhalten als Ganzes verstehen,
bevor einzelne Hebel isoliert werden. Die Stress-Typ-Zuordnung gibt genug Signal für
eine erste Attribution, ohne die Komplexität der abgestuften Aktivierung.

## 5. Zeitphasen & Design

Zeiteinheit = 1 Simulations-Minute. Analog zu CI und Humanitärer Logistik.

- `[0, t_warmup=60]` — Warm-up (1 h), **nicht ausgewertet** (Einschwingen).
- `[t_warmup, t_stress=1440]` — Normalbetrieb (Stunde 1–24) → **R_grid_normal, W_dyn_normal**.
- `t_stress=1440` — Stress-Injektion (Stunde 24).
- `[t_stress + burn_in=60, t_end=4320]` — Stress-Phase (Stunde 25–72)
  → **R_grid_stress, W_dyn_stress**. Der burn_in (1 h) schließt den unmittelbaren
  Übergang aus.

**Design:** 10 Seeds × 3 Stress-Typen = **30 Läufe**. Jeder Lauf enthält Normalbetrieb
(within-run baseline) + Stress-Phase. RNG-Trennung: Szenario-Stream ist unabhängig vom
Stress-Injektions-Stream; das Szenario ist identisch über alle drei Stress-Typen desselben
Seeds (szenario-kontrollierter between-Stress-Vergleich).

**Jitter:** Initial-Phase pro Erzeuger uniform(0, 2π); Regelzyklus-Jitter ±5% pro
Erzeuger (fix pro Erzeuger und Seed). Dies erzeugt echte Replikat-Varianz (Lehre aus
dem CI-Caveat-1).

## 6. Vorab-registrierte Auswertungsregel

**Schritt 0 — H0 prüfen (Mess-Validität, Voraussetzung):**
- **H0a:** R_grid_normal ist signifikant über der Phasen-Offset-Shuffle-Null
  (p < 0.01) in **≥ 7/10 Seeds**. *Dies bestätigt messbare Phasen-Kohärenz,
  erfordert aber NICHT R→1.*
- **H0b:** W_dyn_normal liegt im gültigen Bereich (0 < W_dyn ≤ 1) und variiert
  mit der Simulationsdynamik (nicht konstant).
- **H0 PASSES** wenn H0a UND H0b.
- **Wenn H0 nicht erfüllt:** Design-Stopp. Die Metriken oder die Simulation müssen
  kalibriert werden, bevor H1/H2 ausgewertet werden. *Keine nachträgliche Regel-Justage.*

**Schritt 1 — H1 (Plastizitäts-Konjunktion), pro Stress-Typ:**

Die Konjunktion wird als **Intersection-Union-Test** operationalisiert. Beide
Teilbedingungen müssen halten; nach dem IUT-Prinzip ist der Gesamt-Test auf Niveau α,
wenn jeder Teil-Test auf Niveau α ist (keine zusätzliche Bonferroni-Korrektur nötig).

- **H1a (R_grid sinkt):** ΔR_grid = R_grid_stress − R_grid_normal.
  Einseitiger Wilcoxon-Vorzeichen-Rang-Test (H1: median(ΔR_grid) < 0), α=0.01.
  **CONFIRMED** wenn p < 0.01.
- **H1b (W_dyn gehalten):** ΔW_dyn = W_dyn_stress − W_dyn_normal.
  **Operatives Kriterium:** median(ΔW_dyn) ≥ 0 UND **≥ 7/10 Seeds** haben ΔW_dyn ≥ 0.
  Der einseitige Wilcoxon-p-Wert (negative Richtung) wird als stützende Evidenz berichtet.
- **Konjunktion H1:** **CONFIRMED** für einen Stress-Typ wenn **H1a UND H1b** beide halten.
- **Falsifiziert** für einen Stress-Typ wenn H1a oder H1b (oder beide) nicht halten.

**Schritt 2 — H2 (Unterscheidbarkeit), nur wenn H1 für ≥ 2 Typen bestätigt:**
- Kruskal-Wallis-Omnibus über die ΔR_grid-Werte der drei Stress-Typen.
- **Bestätigt:** Kruskal-Wallis p < 0.05. **Falsifiziert:** p ≥ 0.05.

**Schritt 3 — H3 (Hebel-Attribution):**
- Deskriptive Zuordnung: Welcher Stress-Typ zeigt das stärkste ΔR_grid bzw. ΔW_dyn,
  und welcher Hebel ist diesem Stress-Typ zugeordnet (Abschnitt 3)?
- Dies ist eine **deskriptive** Attribution, kein inferentieller Test. Sie wird als
  Hypothese für die optionale Folgestudie (abgestufte Aktivierung) dokumentiert.

**Keine nachträgliche Justage:** Die Schwellen (α=0.01, H0 ≥ 7/10, H1b ≥ 7/10,
Kruskal-Wallis p < 0.05, Jitter ±5%) stehen, bevor Daten gesichtet werden. Ein
„fast signifikant" wird nicht umgedeutet. **+1-Korrektur** p=(k+1)/(n+1), nie p=0.0000.

## 7. Methodik-Lektionen (aus den früheren Dossiers)

| Lektion | Quelle | Anwendung hier |
|---|---|---|
| IAAFT artefaktisch auf periodischen Signalen | Wirtschafts- + Rescue-Dossier | **Phasen-Offset-Shuffle** für R_grid; **kein IAAFT** |
| Zwei Metriken brauchen zwei Nullhypothesen | Design-Review (diese Studie) | R_grid: Shuffle; W_dyn: Wilcoxon. Getrennt. |
| RNG-Confound zwischen Behandlung und Szenario | Rescue-Koordination | RNG-Trennung, szenario-kontrollierter Vergleich |
| Zwei Datenpunkte sind keine Linie | Rescue-Dichte-Studie | 10 Seeds × 3 Typen = 30 Läufe |
| p-Hacking vermeiden | Rescue-Dichte-Studie | Vorab-registrierte Auswertungsregel, α=0.01 |
| +1-Korrektur, nie p=0.0000 | alle Dossiers | p=(k+1)/(n+1) |
| H0 als Voraussetzung (messbarer Normalbetrieb) | CI-Resilienz-Prereg | Schritt 0, Design-Stopp bei Scheitern |
| Jitter für echte Replikat-Varianz | CI-Caveat-1, Humanitäre Logistik | Initial-Phase uniform, Zyklus-Jitter ±5% |
| Konjunktions-Hypothese als Intersection-Union-Test | Design-Review (diese Studie) | H1a UND H1b, jeder auf α=0.01 |

## 8. Einschränkungen & offene Fragen

- **Kombinierter Effekt, keine volle Attribution:** Die Primärstudie misst das System
  als Ganzes. Die Stress-Typ-Zuordnung gibt partielle Attribution, aber keine isolierte
  Hebel-Wirkung. Dafür wäre die optionale Folgestudie (abgestufte Aktivierung) nötig.
- **Schattenpreis-Kopplung ist aperiodisch:** Im Gegensatz zum Heartbeat der bisherigen
  Studien ist die Kopplung hier ereignisbasiert (Preis-Differenz triggert Nachricht).
  Die Phasen werden aus den periodischen Regelzyklen der Wechselrichter abgeleitet,
  nicht aus der Kommunikation. Dies ist ein anderer Kopplungsmechanismus als bisher.
- **W_dyn ohne λ in der Primärstudie:** Coverage-only (Abschnitt 2.2). Unabhängige
  Strafterme (Curtailment) bleiben Folgestudie.
- **H1b ist ein operatives Kriterium, kein formaler Test:** median ≥ 0 UND ≥ 7/10 Seeds
  ist eine vorab registrierte Regel, kein klassischer Hypothesentest. Das ist bewusst so,
  um die Non-Inferioritäts-Komplexität zu vermeiden.
- **Offene Frage:** Ist das System unter Normalbetrieb bereits meta-stabil (moderate
  R_grid, hohe W_dyn), oder muss Meta-Stabilität erst durch Stress „aktiviert" werden?
  Die Normalbetrieb-Messung (H0) gibt einen ersten Hinweis.
