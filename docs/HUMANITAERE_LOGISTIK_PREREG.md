# Humanitäre Logistik — Vorab-registrierte Resilienz-Studie (Pre-Registration)

**Status:** Pre-Registration — Auswertungsregel festgelegt, bevor Code entsteht  
**Datum:** 2026-08-16  
**Charakter:** Vorab registriert. Keine Regel-Justage nach Daten-Sichtung.  
**Methodik-Pate:** `docs/CI_RESILIENZ_STUDIE_PREREG.md`  
**Vorgänger-Dossiers:** Wirtschafts-Schwarm, Rescue-Koordination, Rescue-Dichte, CI-Resilienz

---

## 1. Fragestellung & Hypothesen

Der humanitäre Logistik-Schwarm (9 Agenten, Klassen A Sensorik & Bedarf /
B Transport & Logistik / C Governance & Priorisierung) wird im Normalbetrieb
und unter Stress gemessen. Die Frage ist nicht „entsteht Koordination?" als
Selbstzweck, sondern: **Ist der Schwarm ein resilientes Versorgungssystem,
und lässt sich Resilienz messen?**

**Kontext-Szenario:** Erdbeben in einer Megacity — Mobilfunk-Ausfall,
Straßen unpassierbar, ~10.000 Verletzte über 4 Notaufnahmepunkte.
Gemessen werden die ersten 72 Stunden der Nothilfe.

Vier Hypothesen, in dieser Reihenfolge ausgewertet:

- **H0 (Voraussetzung):** Der Schwarm ist im Normalbetrieb (funktionierende
  Infrastruktur, kein Stress) signifikant koordiniert (R signifikant).
  *Ohne H0 sind H1/H2 nicht aussagekräftig.*
- **H1 (Koordinations-Degradation):** R degradiert unter einem Stress-Ereignis
  signifikant gegenüber dem Normalbetrieb.
- **H2 (Unterscheidbarkeit):** Die drei Stress-Typen erzeugen unterscheidbare
  Degradationsmuster.
- **H3 (Effizienz-Degradation):** Unter Stress sinkt die Erfüllungsquote
  (Request-Fulfillment) signifikant und die Reaktionszeit steigt signifikant.

## 2. Das System — 9 Agenten, OODA-Zyklen, Takt-Kalibrierung

### 2.1 Klassen und Agenten

| Klasse | Agent | Rolle |
|---|---|---|
| A — Sensorik & Bedarf | NGOResponseAgent | Lageberichte, Bedarfserfassung |
| A | SARAgent | Ortung & Rettung (Golden Hour) |
| A | UAVAgent | Luftaufklärung, Relay |
| B — Transport & Logistik | THWAgent | Landtransport Hub→Verteilpunkt |
| B | UNHASAgent | Lufttransport (schwer erreichbar) |
| B | ForwardHubAgent | Lokales Verteilzentrum |
| C — Governance & Priorisierung | OCHAAgent | Dringlichkeits-Priorisierung |
| C | B2GAgent | Zoll, humanitäre Korridore |
| C | MedCoordinationAgent | Medizinische Triage & Zuweisung |

### 2.2 Takt-Kalibrierung (CI-Lehre)

**Natürliche Takte** (realistische humanitäre Zeitskalen) haben eine Spreizung
von ca. 12:1 (SAR ~5 min schnell, Zoll ~60 min langsam). Die **CI-Studie hat
gezeigt, dass eine 10:1-Spreizung H0 zum Scheitern bringt** (R=0.471, p=0.012);
die Reduktion auf 3.3:1 rettete H0 (R=0.516, p=0.008).

Daher werden für diese Studie **kalibrierte Takte mit ~3:1-Spreizung** verwendet.
Die natürliche 12:1-Spreizung wird als Limitation dokumentiert, nicht als
Studiendesign — die Studie misst Koordination unter erreichbarer Takt-Nähe,
nicht unter realistischer Maximal-Spreizung.

**Kalibrierte Takte** (Zeiteinheit = 1 Simulations-Minute):

| Agent | Takt (min) | Begründung |
|---|---|---|
| SARAgent | 10 | Golden Hour, zeitkritisch |
| NGOResponseAgent | 12 | Lagebericht-Zyklus |
| UAVAgent | 12 | Überflug-Zyklus |
| ForwardHubAgent | 15 | Lokale Verteilung |
| THWAgent | 18 | Fahrzyklus |
| MedCoordinationAgent | 18 | Triage-Zyklus |
| OCHAAgent | 20 | Priorisierungsliste |
| UNHASAgent | 25 | Flugzyklus |
| B2GAgent | 30 | Zoll-Freigabe |

Spreizung: 10 → 30 min = **3:1** (analog zu CI Option A).

**Hinweis:** Wenn H0 mit diesen Takten scheitert, ist das ein Design-Stopp;
die Takte sind dann weiter zu kalibrieren, bevor die Stress-Studie läuft.

## 3. Metriken — Koordination UND Effizienz (zwei getrennte Messgrößen)

**Entsprechend Option A (bestätigt):** Request-Fulfillment ist eine
**Effizienz-Metrik**, keine Kuramoto-Phase. Kuramoto misst die
Zyklus-Synchronisation der Agenten; Request-Fulfillment misst die
Lieferketten-Effizienz. Beide werden gemessen, aber nicht vermischt.

### 3.1 Koordinations-Metrik (Kuramoto)

- **Phase θ_j(t):** aus dem OODA-Zyklus jedes Agenten (Periode = Takt aus 2.2).
  θ_j = 2π·(t − t_cycle_start)/Takt_j. Wiederkehrende Zyklen, keine
  Request-Fulfillment-Fortschrittsvariable.
- **Ordnungsparameter R(t):** |mean(exp(iθ_j))| über die operativen Agenten.
- **R_normal:** Mittelwert über das Normalbetrieb-Fenster.
- **R_stress:** Mittelwert über das Stress-Fenster.

### 3.2 Effizienz-Metrik (Request-Fulfillment)

- **Erfüllungsquote:** Anteil der Versorgungsanfragen, die innerhalb von
  24 Sim-Stunden erfüllt werden (0–1).
- **Reaktionszeit:** mittlere Zeit von Anfrage bis Erfüllung (Sim-Minuten).
- **ΔQuote = Quote_normal − Quote_stress** (positiv = Effizienzverlust).
- **ΔReaktionszeit = Reaktionszeit_stress − Reaktionszeit_normal** (positiv = Verlangsamung).

## 4. Stress-Szenarien & Injektionen

Drei mechanisch verschiedene Injektionen (CI-Lehre: keine drei Varianten
desselben Störimpulses). Alle injizieren bei `t_stress`.

| Szenario | CI-Analog | Injektion bei t_stress | Erwartetes Muster |
|---|---|---|---|
| **Hub-Verlust** | Blackout | ForwardHubAgent → OUT_OF_SERVICE, bleibt offline | **Plötzlicher** Abfall von R + Quote; Verteilzentrum fehlt |
| **Nachbeben** | Naturkatastrophe | THWAgent + UAVAgent gleichzeitig degradiert (Takt ×1.5) | **Starker, breiter** Abfall; Transport & Aufklärung verlangsamt |
| **Komm-Kollaps** | Cyber (angepasst) | Klasse-A-Bandbreite reduziert, Mesh-Fallback (Nachrichten-Zustellrate ↓) | **Schleichender** Abfall; Lageberichte kommen verzögert an |

**Abgrenzung:** Hub-Verlust = eine Komponente ganz aus. Nachbeben = zwei
Komponenten verlangsamt (nicht aus). Komm-Kollaps = keine Komponente aus,
aber die Nachrichten-Zustellung ist gestört. Diese drei sind mechanisch
verschieden und sollen unterscheidbar sein.

## 5. Zeitphasen (72-Sim-Stunden)

Zeiteinheit = 1 Simulations-Minute. Gesamt = 4320 Einheiten (72 h).

- `[0, t_warmup=60]` — Warm-up (1 h), **nicht ausgewertet** (Einschwingen).
- `[t_warmup, t_stress=1440]` — Normalbetrieb (Stunde 1–24) → **R_normal, Quote_normal**.
- `t_stress=1440` — Stress-Injektion (Stunde 24).
- `[t_stress + burn_in=60, t_end=4320]` — Stress-Phase (Stunde 25–72)
  → **R_stress, Quote_stress**. Der burn_in (1 h) schließt den unmittelbaren
  Übergang aus.

## 6. Nullhypothese & Signifikanz

- **Nullhypothese für R-Signifikanz: Phasen-Offset-Shuffle** — die Phasen-
  trajektorie jedes Agenten wird um einen zufälligen konstanten Offset
  verschoben (erhält Periode und interne Dynamik, randomisiert die relative
  Ausrichtung). **NICHT IAAFT.** Bestätigt für Vergleichbarkeit mit
  Wirtschafts-/Rescue-/CI-Dossiers.
- **α = 0.01**, vorab registriert (konsistent über alle bisherigen Studien).
- **+1-Korrektur** p=(k+1)/(n+1), nie p=0.0000.
- **Für H1/H3 (Degradation):** gepaarter Vergleich über Seeds (Wilcoxon),
  kein Surrogat-Test — die Frage ist R_stress < R_normal bzw.
  Quote_stress < Quote_normal, nicht R > Zufall.

## 7. Design (Multi-Seed, RNG-Trennung, Jitter)

- **10 Seeds × 3 Stress-Typen = 30 Läufe.** Jeder Lauf enthält Normalbetrieb
  (within-run baseline) + Stress-Phase.
- **RNG-Trennung:** Der Szenario-Stream (Anfragen-Last) ist identisch über alle
  drei Stress-Typen desselben Seeds und unabhängig vom Stress-Injektions-Stream.
  → Der between-Stress-Vergleich ist szenario-kontrolliert.
- **Jitter für echte Replikat-Varianz (methodische Verbesserung gegenüber CI):**
  Die CI-Studie hatte byte-gleiche Seeds (keine Streuung), wodurch der
  Wilcoxon-Test keine Replikat-Varianz maß. Für diese Studie werden zwei
  Jitter-Quellen vorab registriert:
  - **Initial-Phase:** pro Agent und Seed zufällig (uniform 0..2π).
  - **Takt-Jitter:** ±10% pro Agent (fix pro Agent und Seed).
  Dadurch streuen die 10 Seeds tatsächlich, und der Wilcoxon-Test misst echte
  Varianz. **Trade-off (dokumentiert):** Die Zahlen sind dadurch nicht 1:1 mit
  den deterministischen CI-Zahlen vergleichbar; die Methodik ist bewusst
  verbessert, nicht kopiert.
- **Konstant:** Duration 4320, dt=1, coupling=0.30, t_warmup=60,
  t_stress=1440, burn_in=60, α=0.01.

## 8. Vorab-registrierte Auswertungsregel

**Schritt 0 — H0 prüfen (Voraussetzung):**

- R_normal via Phasen-Offset-Shuffle in ≥ 7/10 Läufen pro Stress-Typ signifikant
  (p < 0.01). → Normalbetrieb ist koordiniert.
- **Wenn H0 nicht erfüllt:** Design-Stopp. Die Takte (2.2) oder die Kopplung
  müssen kalibriert werden, bevor H1/H2/H3 ausgewertet werden. *Dies ist ein
  Design-Stopp, keine nachträgliche Regel-Justage.*

**Schritt 1 — H1 (Koordinations-Degradation), pro Stress-Typ:**

- ΔR = R_normal − R_stress über die 10 Seed-Paare.
- Einseitiger Wilcoxon-Vorzeichen-Rang-Test (H1: ΔR > 0), α=0.01.
- **Bestätigt** pro Stress-Typ: ΔR > 0 und p < 0.01.
- **Falsifiziert** pro Stress-Typ: ΔR ≤ 0 oder p ≥ 0.01.

**Schritt 2 — H2 (Unterscheidbarkeit), nur wenn H1 für ≥ 2 Typen bestätigt:**

- Kruskal-Wallis-Omnibus über die ΔR-Werte der drei Stress-Typen.
- **Bestätigt:** Kruskal-Wallis p < 0.05.
- **Falsifiziert:** Kruskal-Wallis p ≥ 0.05.

**Schritt 3 — H3 (Effizienz-Degradation), pro Stress-Typ:**

- ΔQuote = Quote_normal − Quote_stress; ΔReaktionszeit = RT_stress − RT_normal.
- Einseitiger Wilcoxon (H1: ΔQuote > 0 bzw. ΔReaktionszeit > 0), α=0.01.
- **Bestätigt** pro Stress-Typ: ΔQuote > 0 und p < 0.01.
- H3 ist eine eigenständige Hypothese und wird auch ausgewertet, wenn H1
  für einen Stress-Typ nicht bestätigt ist (Effizienz kann degradieren,
  auch wenn die Zyklus-Koordination hält).

**Keine nachträgliche Justage:** Die Schwellen (α=0.01, H0 ≥ 7/10,
Kruskal-Wallis p < 0.05, Jitter ±10%) stehen, bevor Daten gesichtet werden.
Ein „fast signifikant" wird nicht umgedeutet.

## 9. Methodik-Lektionen (aus den früheren Dossiers)

| Lektion | Quelle | Anwendung hier |
|---|---|---|
| IAAFT artefaktisch auf periodischen Signalen | Wirtschafts- + Rescue-Dossier | **Phasen-Offset-Shuffle**, nicht IAAFT |
| RNG-Confound zwischen Behandlung und Szenario | Rescue-Koordination | RNG-Trennung, szenario-kontrollierter Vergleich |
| Zwei Datenpunkte sind keine Linie | Rescue-Dichte-Studie | 10 Seeds pro Bedingung |
| p-Hacking vermeiden | Rescue-Dichte-Studie | Vorab-registrierte Auswertungsregel, α=0.01 |
| +1-Korrektur, nie p=0.0000 | alle Dossiers | p=(k+1)/(n+1) |
| H0 als Voraussetzung (koordinierter Normalbetrieb) | CI-Resilienz-Prereg | Schritt 0, Design-Stopp bei Scheitern |
| **Zu große Takt-Spreizung lässt H0 scheitern** | **CI-Resilienz-Studie** | **Kalibrierte Takte 3:1 statt natürlicher 12:1** |
| **Byte-gleiche Seeds messen keine Varianz** | **CI-Resilienz-Ergebnis (Caveat 1)** | **Jitter (Initial-Phase + Takt ±10%) vorab registriert** |
| Request-Fulfillment ist keine Oszillator-Phase | Design-Review (Option A) | Effizienz-Metrik getrennt von Kuramoto-Phase |

## 10. Einschränkungen & offene Fragen

- **Kalibrierte statt natürliche Takte:** Die Studie misst Koordination unter
  3:1-Takt-Spreizung, nicht unter der realistischen 12:1-Spreizung. Ob der
  Schwarm auch unter 12:1 koordiniert wäre, ist eine offene Frage und würde
  eine eigene Studie erfordern.
- **Jitter-Trade-off:** Durch den Jitter sind die Zahlen nicht 1:1 mit den
  deterministischen CI-Zahlen vergleichbar. Die Methodik ist bewusst verbessert.
- **Die Studie gilt für die gewählten Parameter** (coupling=0.30, Takte 2.2,
  t_stress=1440). Andere Parameter können andere Ergebnisse liefern.
- **Keine „Rettung" eines nicht-signifikanten Ergebnisses.** Wenn H1/H2/H3
  falsifiziert werden, ist das ein valider Befund und wird als solcher
  dokumentiert (Lehre aus der Dichte-Studie).
- **Offene Frage:** Ob die Effizienz-Metrik (H3) empfindlicher auf Stress
  reagiert als die Koordinations-Metrik (H1) — z.B. ob die Lieferkette
  einbricht, bevor die Zyklus-Koordination messbar degradiert. Das wäre ein
  eigener Befund.

## 11. Bau-Reihenfolge (festgelegt)

1. **H0-Gate** zuerst: 10 Seeds, Normalbetrieb, Jitter aktiv, R via
   Phasen-Offset-Shuffle; Gate ≥ 7/10.
2. Erst bei bestandenem H0: Stress-Injektoren (Hub-Verlust / Nachbeben /
   Komm-Kollaps) + Effizienz-Metrik + 30 Stress-Läufe + H1/H2/H3.
3. Ergebnis-Dossier nach dem Lauf — keine Regel-Justage.

**IAAFT ist für diese Studie ausgeschlossen. Jitter ist Teil des Designs.**
