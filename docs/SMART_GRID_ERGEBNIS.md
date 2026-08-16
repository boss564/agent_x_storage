# Smart Grid — Meta-Stabilitäts-Studie: Ergebnis-Dossier

**Status:** Abgeschlossen — H1 (Meta-Stabilität) **falsifiziert**, H2 (Unterscheidbarkeit) bestätigt, H3 deskriptiv
**Datum:** 2026-08-17
**Commits:** Pre-Reg `3d55ebb8` · H0-Gate `81c22766` · Stress-Injektoren `5c5fc39b` · Studie (30 Läufe)
**Pre-Registration:** `docs/SMART_GRID_PREREG.md`
**Charakter:** Vorab registrierte Auswertungsregel, ergebnissoffen durchgeführt. Die Meta-Stabilitäts-Hypothese wurde nicht bestätigt — ein valider wissenschaftlicher Ausgang, kein Fehlschlag.

---

## 1. Hypothesen & vorab registrierte Auswertungsregel

Aus `SMART_GRID_PREREG.md`:

- **H1 (Plastizität / Meta-Stabilität):** Intersection-Union-Test.
  - H1a: ΔR_grid < 0 (Koordination sinkt unter Stress), einseitiger Wilcoxon, α=0.01.
  - H1b: median(ΔW_dyn) ≥ 0 UND ≥ 7/10 Seeds mit ΔW_dyn ≥ 0 (Wohlfahrt bleibt stabil).
  - H1 CONFIRMED wenn H1a UND H1b.
- **H2 (Unterscheidbarkeit):** Kruskal-Wallis über die Stress-Typen, p < 0.05.
- **H3 (Hebel-Attribution):** deskriptive Stress-Typ-zu-Hebel-Zuordnung.

## 2. Ergebnis

### H1 — Meta-Stabilität: NICHT bestätigt (alle drei Stress-Typen)

| Stress-Typ | ΔR_grid | H1a (p) | H1a | median ΔW_dyn | Seeds ΔW≥0 | H1b | **H1 Konjunktion** |
|---|---|---|---|---|---|---|---|
| Bewölkung | +0.0000 | p=1.0000 | NOT_CONFIRMED | −0.0742 | 0/10 | NOT_CONFIRMED | **NOT_CONFIRMED** |
| Spitzenlast | +0.0000 | p=1.0000 | NOT_CONFIRMED | −0.2391 | 0/10 | NOT_CONFIRMED | **NOT_CONFIRMED** |
| Leitungsausfall | **−0.2884** | p=0.0025 | **CONFIRMED** | −0.1561 | 0/10 | NOT_CONFIRMED | **NOT_CONFIRMED** |

### H2 — Unterscheidbarkeit: bestätigt

**Kruskal-Wallis p = 0.0001 → CONFIRMED.** Mindestens ein Stress-Typ erzeugt ein signifikant anderes ΔR_grid-Muster.

### H3 — Hebel-Attribution: deskriptiv

| Stress-Typ | Primär geforderter Hebel | Beobachtetes Muster |
|---|---|---|
| Bewölkung | Schattenpreise + Speicher-Dispatch | ΔR=0, ΔW=−0.07 |
| Spitzenlast | Flexibilität + Lastverschiebung | ΔR=0, ΔW=−0.24 |
| Leitungsausfall | Hebb'sches Um-Routing + Curtailment | ΔR=−0.29, ΔW=−0.16 |

## 3. Mechanische Interpretation der drei Stress-Typen

| Stress-Typ | Injektion | Wirkung auf Phasen | Wirkung auf Leistung |
|---|---|---|---|
| **Bewölkung** | PV-Capacity-Factor → 0.1 | **Keine** — Inverter-Phasen bleiben an den Grid-Bus gekoppelt, unabhängig vom Capacity-Factor. ΔR_grid = 0. | PV-Erzeugung bricht ein → weniger gedeckte Last → W_dyn fällt. |
| **Spitzenlast** | Last +50% | **Keine** — die Laständerung beeinflusst die Leistungsbilanz, nicht die Inverter-Phasen. ΔR_grid = 0. | Last übersteigt Erzeugung+Flexibilität → W_dyn fällt am stärksten (−0.24). |
| **Leitungsausfall** | Wind-Inverter: Capacity-Factor → 0, Periode → 100 min | **Ja** — die Wind-Inverter verlieren den Anschluss an den Grid-Bus (Periode 100 min vs. Grid-Bus 4 min), ihre Phasen driften → R_grid sinkt (−0.29). | Wind-Erzeugung fällt weg → W_dyn fällt. |

**Kern:** Die drei Injektionen sind mechanisch verschieden und wirken auf unterschiedliche Größen. Bewölkung und Spitzenlast treffen nur die Leistungsbilanz (W_dyn), nicht die Phasen (R_grid). Leitungsausfall trifft beides.

## 4. Der zentrale Befund: H1 falsifiziert — die Plastizitäts-Hebel sind Stubs

Das wichtigste Ergebnis ist die **Konjunktions-Lücke**: In keinem der drei Fälle bleibt W_dyn stabil, während R_grid sinkt. Konkret:

- **Bewölkung/Spitzenlast:** R_grid ändert sich nicht (ΔR=0), W_dyn fällt. Das System „opfert" keine Kohärenz — es verliert schlicht Leistung, ohne dass die Phasen-Koordination reagiert.
- **Leitungsausfall:** R_grid sinkt (ΔR=−0.29), aber W_dyn sinkt ebenfalls (ΔW=−0.16). Das System verliert also **sowohl** Kohärenz **als auch** Wohlfahrt — es opfert R_grid *nicht*, um W_dyn zu halten, sondern verliert beides.

**Ursache:** Die vier Architektur-Hebel der Meta-Stabilität — Schattenpreise, Aktive Inferenz, Hebb'sche Plastizität, Flexibilität-Dispatch — sind in der Simulation noch **Stubs** (die `_unit_act`-Methode ist ein `pass`). Die Flexibilität-Agenten (Batterie, EV, Wärmepumpe) kompensieren die ausgefallene Erzeugung oder die gestiegene Last nicht; sie entladen keine Speicher, verschieben keine Ladevorgänge, drosseln keine Wärmepumpen. Deshalb kann W_dyn unter Stress nur fallen, nie stabil bleiben.

**Das ist die ehrliche Bedeutung des Ergebnisses:** Die Meta-Stabilitäts-Hypothese ist für das *aktuelle* Design falsifiziert, weil die Plastizitäts-Mechanismen noch nicht implementiert sind. Das ist kein Widerspruch zur Theorie, sondern eine **notwendige Vorbedingung**, die noch fehlt.

## 5. Design-Limitation: Bewölkung/Spitzenlast können die Meta-Stabilität nicht testen

Ein methodischer Befund, der für die Neuauflage wichtig ist: **Bewölkung und Spitzenlast können die Meta-Stabilitäts-Hypothese strukturell nicht testen**, weil sie R_grid nicht beeinflussen (ΔR=0). Die Hypothese H1 verlangt aber ΔR_grid < 0 als eine der beiden Konjunktions-Bedingungen. Solange ein Stress-Typ R_grid nicht senkt, kann H1a für ihn nicht bestätigt werden — unabhängig davon, was die Flexibilität-Agenten tun.

**Nur der Leitungsausfall** senkt R_grid und kann damit prinzipiell die Meta-Stabilität zeigen. Für eine vollständige Test-Abdeckung müssten Bewölkung und Spitzenlast so erweitert werden, dass sie auch die Phasen beeinflussen (z.B. über eine Frequenz-/Leistungs-Rückkopplung auf die Inverter-Phasen, wie sie in echten Netzen besteht).

## 6. Methodische Caveats (ehrlich offengelegt)

### Caveat 1 — H2 wurde auf ΔR_grid allein getestet
Die Pre-Reg spezifiziert H2 „über die Kombination von ΔR_grid und ΔW_dyn". Die Implementierung testet den Kruskal-Wallis auf ΔR_grid allein. Auf ΔR allein sind **Bewölkung und Spitzenlast nicht unterscheidbar** (beide ΔR=0); sie unterscheiden sich nur auf ΔW. H2 CONFIRMED bedeutet daher: „mindestens ein Stress-Typ (Leitungsausfall) unterscheidet sich signifikant von den anderen" — nicht, dass alle drei paarweise unterscheidbar sind. Für die volle paarweise Unterscheidbarkeit wäre ein Zwei-Metriken-Test nötig.

### Caveat 2 — W_dyn-Formel vereinfacht
W_dyn = P_gedeckt / P_bedarf (λ ≡ 0) ist eine Autarkie-Quote, kein vollständiges Wohlfahrtsmaß. Ein reales Wohlfahrtsmaß würde Degradationskosten, Komfortverlust und Degradation der Flexibilitätseinheiten einpreisen. Für den relativen Vergleich (Normalbetrieb vs. Stress) ist die Autarkie-Quote ausreichend.

### Caveat 3 — Stress-Injektoren sind vereinfacht
Bewölkung ist ein instantaner PV-Einbruch, kein allmählicher Wolkenzug. Spitzenlast ist eine pauschale +50%-Last, kein realistisches EV-Ladeprofil. Leitungsausfall trennt ein ganzes Wind-Segment, nicht eine einzelne Leitung. Für die erste Studie ausreichend, für eine realistische Neuauflage zu verfeinern.

## 7. Bezug zu den früheren Dossiers

| Dossier | Lehre | Anwendung hier |
|---|---|---|
| `WIRTSCHAFTS_SCHWARM_DOSSIER.md` | IAAFT artefaktisch auf periodischen Signalen | **Phasen-Offset-Shuffle**, kein IAAFT |
| `RESCUE_KOORDINATION_DOSSIER.md` | Zwei Metriken brauchen zwei Nullhypothesen | R_grid: Shuffle; W_dyn: gepaarter Seed-Vergleich |
| `CI_RESILIENZ_STUDIE_PREREG.md` | H0 als Voraussetzung; Inverter-Flotten für N_gen | H0-Gate (10/10), N_gen = 9 Inverter |
| `HUMANITAERE_LOGISTIK_ERGEBNIS.md` | Koordination ≠ Effizienz | Hier: Plastizität (Koordination opfern für Wohlfahrt) wurde getestet und nicht bestätigt |

Diese Studie ist die **sechste** Emergence-Studie der Reihe und die erste mit einer **invertierten Hypothese** (R darf sinken, solange W stabil bleibt). Die Methodik (Phasen-Offset-Shuffle, Pre-Reg, H0-Gate) ist konsistent mit den fünf Vorgängern.

## 8. Gesamteinordnung & Ausblick

**Vier belastbare Befunde:**

1. **H0 messbar** (10/10): R_grid und W_dyn sind im Normalbetrieb messbar und last-sensitiv. Das System ist ein valides Testbed.
2. **H1 falsifiziert:** Die Meta-Stabilitäts-Hypothese ist für das aktuelle Design nicht bestätigt. Das System verliert unter Stress Leistung (W_dyn), ohne Kohärenz zu opfern oder Wohlfahrt zu halten.
3. **H2 bestätigt:** Die drei Stress-Typen sind unterscheidbar (Kruskal-Wallis p=0.0001), zumindest auf ΔR_grid (Leitungsausfall vs. die anderen beiden).
4. **Zentrale Erkenntnis:** Die **Plastizitäts-Hebel sind die fehlende Vorbedingung**. Solange Schattenpreise, Aktive Inferenz, Hebb'sche Plastizität und Flexibilität-Dispatch Stubs sind, kann das System keine Meta-Stabilität zeigen.

**Ausblick — was eine Neuauflage braucht:**

- **Plastizitäts-Hebel implementieren** (notwendige Vorbedingung): Flexibilität-Dispatch (Batterie entladen, EV verschieben, Wärmepumpe drosseln), Schattenpreis-getriggerte Kommunikation, ggf. Aktive Inferenz für vorausschauende Reserveplanung. Erst dann kann W_dyn unter Stress stabil bleiben.
- **Stress-Injektoren phasenwirksam machen:** Bewölkung und Spitzenlast sollten auch die Inverter-Phasen beeinflussen (Frequenz-/Leistungs-Rückkopplung), damit sie H1a testen können. Sonst bleibt nur der Leitungsausfall als meta-stabiler Testfall.
- **H2 auf beide Metriken erweitern:** Kruskal-Wallis über die Kombination von ΔR_grid und ΔW_dyn, wie in der Pre-Reg spezifiziert, für volle paarweise Unterscheidbarkeit.

## 9. Reproduktion

```bash
cd /Volumes/THX_OS_ULTRA\ -\ Data/Users/olivermueller/agent_x_storage

# Unit-Tests (Stress-Injektoren)
python3 -m pytest scripts/test_smartgrid_stress.py -v

# H0-Gate (Normalbetrieb, 10 Seeds)
python3 scripts/run_smartgrid_h0.py

# Stress-Studie (30 Läufe)
python3 scripts/run_smartgrid_stress_study.py

# Ergebnis extrahieren
python3 -c "
import json
d = json.load(open('smartgrid_stress_study_results.json'))
print('H1 META-STABILITY:')
for stype, h1 in d['h1_meta_stability'].items():
    print(f'  {stype:20s}: ΔR={h1[\"mean_delta_r_grid\"]:+.4f} (p={h1[\"wilcoxon_r_p\"]:.4f}) H1a={h1[\"h1a_status\"]}')
    print(f'    median ΔW={h1[\"median_delta_w_dyn\"]:+.4f}  {h1[\"n_seeds_w_dyn_geq_0\"]}/10 H1b={h1[\"h1b_status\"]} -> H1={h1[\"h1_status\"]}')
print()
print('H2 DISTINGUISHABILITY:')
h2 = d['h2_distinguishability']
print(f'  Kruskal-Wallis p={h2[\"kruskal_wallis_p\"]:.4f}  -> {h2[\"h2_status\"]}')
"
```
