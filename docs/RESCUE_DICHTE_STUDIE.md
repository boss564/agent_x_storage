# Rescue-Dichte-Studie — Multi-Seed × Dichte: Falsifikation der Dichte-Hypothese

**Status:** Abgeschlossen — Dichte-Hypothese **falsifiziert** (vorab registrierte Regel)  
**Datum:** 2026-08-16  
**Commit:** `17b0bc54` · Rohdaten `rescue_density_study.json` (gitignored)  
**Charakter:** Vorab registrierte Auswertungsregel, ergebnissoffen durchgeführt. Kein p-Hacking, keine nachträgliche Regel-Justage.

---

## 1. Fragestellung & Hypothese

Aus `RESCUE_KOORDINATION_DOSSIER.md` (Befund 1) stammt die Arbeitshypothese:

> **Dichte-Hypothese:** Der Kuramoto-Ordnungsparameter R steigt monoton mit der
> Interaktionsdichte (Anzahl Schadensmeldungen pro Zeiteinheit). Koordination ist
> ein Effekt der Nachrichtenrate.

Diese Hypothese war durch **zwei Datenpunkte** motiviert (detected=90 → COORDINATED,
detected=68 → UNCOORDINATED), aber nie systematisch getestet. Die vorliegende Studie
testet sie mit einem Multi-Seed × Dichte-Raster.

## 2. Vorab registrierte Auswertungsregel (vor dem Lauf festgelegt)

- **Primäranalyse:** Spearman-Korrelation von R über log(1/mean_interval),
  einseitig (H1: ρ>0), α=0.01.
- **Sekundäranalyse:** Kruskal-Wallis-Omnibus über die 4 Dichte-Stufen.
- **Bestätigt** genau dann, wenn (a) Spearman ρ>0 und p<0.01 **UND**
  (b) Kruskal-Wallis p<0.05.
- **Falsifiziert**, wenn (a) nicht erfüllt ist.

## 3. Design

- **10 Seeds × 4 Dichte-Stufen** (mean_interval_s ∈ {15, 25, 40, 70}) = 40 Läufe pro Bedingung.
- **Zwei Bedingungen:** baseline (ohne Clearance) und with_clearance (RoE aktiv).
- **Gesamt:** 80 Simulationsläufe (Tests 5/5, Studie 80/80).
- Konstant: Duration 600 s, dt=1 s, coupling=0.30, α=0.01.
- RNG-Trennung aktiv (Szenario-Stream unabhängig vom Assessment-Stream).

## 4. Ergebnis

| | baseline | with_clearance |
|--|--|--|
| Spearman ρ | **−0.3409** | **−0.4397** |
| p (einseitig, ρ>0) | **0.9893** | **0.9980** |
| Kruskal-Wallis p | 0.141 | 0.0414 |
| **Verdict** | **NOT_CONFIRMED** | **NOT_CONFIRMED** |

**→ Ausgang 3 der vorab registrierten Regel: Dichte-Hypothese falsifiziert.**

Die Primärbedingung (ρ>0, p<0.01) ist in beiden Bedingungen klar verfehlt — ρ ist
negativ, der einseitige p-Wert für einen Anstieg liegt bei ~0.99.

## 5. Manipulations-Check (Dichte wurde tatsächlich manipuliert)

| interval | mean_detected | mean_R (base) | COORD base | mean_R (clr) | COORD clr |
|--|--|--|--|--|--|
| 15 s | 139.3 | 0.599 | 3/10 | 0.647 | 4/10 |
| 25 s | 87.1 | 0.696 | 4/10 | 0.707 | 7/10 |
| 40 s | 57.1 | 0.677 | 5/10 | 0.744 | 6/10 |
| 70 s | 33.2 | 0.747 | 5/10 | 0.763 | 9/10 |

Die Manipulation hat gegriffen (detected 139 → 33). Der beobachtete Trend ist
**umgekehrt** zur Hypothese: niedrigere Dichte geht mit höherem mittleren R einher.

## 6. Interpretation — Falsifikation, keine Bestätigung

1. **Die Anstiegs-Hypothese ist klar falsifiziert.** ρ ist negativ, nicht positiv;
   der einseitige p-Wert für ρ>0 beträgt ~0.99. Koordination entsteht **nicht**
   einfach durch mehr Nachrichten.

2. **Der umgekehrte Trend ist explorativ, nicht gesichert.** Der negative ρ
   (−0.34 / −0.44) und die Abnahme von R mit steigender Dichte deuten auf einen
   möglichen Überlast-/Fragmentierungseffekt hin. Aber: baseline Kruskal-Wallis
   p=0.141 ist nicht signifikant — dort ist der Abwärtstrend nur eine Tendenz.
   Nur under Clearance ist er grenzwertig signifikant (p=0.0414, auf 0.05, nicht
   auf 0.01). **Wir melden das als explorative Beobachtung, nicht als Befund
   „Koordination sinkt mit Dichte".**

3. **Die beiden Dossier-Datenpunkte waren kein Mechanismus.** detected=90 COORDINATED
   und detected=68 UNCOORDINATED waren eine punktuell plausible, aber unter
   Multi-Seed-Kontrolle nicht replizierbare Konstellation. Das ist genau der Grund,
   warum Multi-Seed-Studien nötig sind: zwei Punkte legen eine Linie, zehn Seeds
   pro Stufe zeigen, ob sie trägt. Sie trägt nicht.

## 7. Bezug zum Koordinations-Dossier (Befund 1)

Dieses Ergebnis **löst die offene Hypothese aus Befund 1** von
`RESCUE_KOORDINATION_DOSSIER.md` auf, ohne den Befund selbst zu widerrufen:

- Koordination aus Nachrichten-Phase-Pull ist **real** (in bestimmten Szenarien
  beobachtet) — das bleibt gültig.
- Die **Dichte-Skalierung als Erklärung ist falsifiziert** — das ist das neue Ergebnis.
- Die **Szenarioabhängigkeit bleibt bestehen**, aber der vorgeschlagene Mechanismus
  (Dichte) ist falsch. **Wann und warum Koordination auftritt, ist wieder eine
  offene Frage.**

→ `RESCUE_KOORDINATION_DOSSIER.md` Befund 1 sollte um einen Verweis auf diese
Studie ergänzt werden (Hypothese falsifiziert, Mechanismus offen).

## 8. Einschränkungen & offene Fragen

- Der negative ρ ist nicht robust signifikant (baseline KW p=0.141). Eine Aussage
  „R sinkt mit Dichte" ist durch diese Daten **nicht** gedeckt.
- Die Studie gilt für coupling=0.30, Duration 600 s, diesen Szenario-Generator.
  Andere Parameter können andere Ergebnisse liefern.
- **Offene Frage:** Wenn nicht Dichte — was bestimmt, ob ein Szenario KOORDINIERT
  oder nicht? Kandidaten: Verhältnis von OODA-Perioden zur Nachrichtenrate,
  Topologie des Abhängigkeitsgraphen, Resupply-Kadenz. Das wäre eine eigene Studie.

## 9. Reproduktion

```bash
cd /Volumes/THX_OS_ULTRA\ -\ Data/Users/olivermueller/agent_x_storage

# Statistik-Helfer (keine Simulation)
python3 -m pytest scripts/test_study_rescue_density.py -v

# Studie (80 Simulationen)
python3 scripts/study_rescue_density.py | tee rescue_density_study.json

# Urteil extrahieren
python3 -c "
import json
d = json.load(open('rescue_density_study.json'))
for cond in ('baseline', 'with_clearance'):
    a = d[cond]
    print(f'{cond:16s} rho={a[\"spearman_rho\"]:+.4f} '
          f'p(rho>0)={a[\"spearman_p_one_sided\"]:.4f} '
          f'KW={a[\"kruskal_p\"]:.4f} -> {a[\"verdict\"]}')
"
```
