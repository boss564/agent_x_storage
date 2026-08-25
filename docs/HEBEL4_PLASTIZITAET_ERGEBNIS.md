# Hebel 4 — Plastizität (Adaptiver Class-B-Dispatch): Ergebnis-Dossier

**Status:** Abgeschlossen — Verdict **NICHT_WIRKSAM** (Pre-Reg-konform, Schwellen nicht nachjustiert)
**Datum:** 2026-08-17
**Pre-Registration:** `docs/HEBEL4_PLASTIZITAET_PREREG.md`
**Spec:** `docs/HEBEL4_PLASTIZITAET_SPEC.md`
**Artefakt:** `hebel4_plastizitaet_ergebnis.json` (gitignored)
**Tests:** `scripts/test_hebel4_plastizitaet.py` — 11/11 (+ Smartgrid-Stress 6/6)
**Charakter:** Vorab registrierte Auswertungsregel (IUT-Konjunktion wie Smart Grid),
ergebnissoffen durchgeführt. Verdict nur Leitungsausfall-H1; Bewölkung/Spitzenlast
deskriptiv mit Generalisierungs-Vorbehalt.

---

## 1. Hypothese und IUT-Struktur

Aus `HEBEL4_PLASTIZITAET_PREREG.md`:

- **Hypothese:** Adaptiver Class-B-Dispatch (Wasserfall Batterie → EV → Wärmepumpe,
  begründet über Reaktionszeit × Degradationskosten) hält W_dyn stabil unter
  Leitungsausfall, während R_grid sinkt.
- **IUT-Konjunktion:** H1 = H1a **UND** H1b.
  - **H1a:** ΔR_grid < 0 (Wilcoxon α=0.01) — der Leitungsausfall senkt R_grid.
    Kommt vom Stressor; der Dispatch beeinflusst die Erzeuger-Phasen nicht.
  - **H1b:** ΔW_dyn ≥ 0 in ≥ 7/10 Seeds — der Dispatch hält die Wohlfahrt.
    Hier zielt der Dispatch hin.
- **Null:** nur passive `0.4 × Σ_B`-Flex (Stub, dokumentationspflichtig).
- **Treatment:** aktiver Wasserfall, **ersetzt** die 0.4 (kein `max`) — fairer Vergleich.
- **Dispatch:** Volldeckung pro Schritt, schritt-synchron (nicht OODA-getaktet).

## 2. Ergebnis

### Leitungsausfall — NULL (Replikation)

| | |
|---|---|
| H1a | mean ΔR = **−0.2884**, p = **0.0025** → **CONFIRMED** |
| H1b | median ΔW = **−0.1562**, **0/10** Seeds ≥ 0 → **NOT_CONFIRMED** |
| H1 | **NOT_CONFIRMED** |

### Leitungsausfall — TREATMENT (Verdict)

| | |
|---|---|
| H1a | mean ΔR = **−0.2884**, p = **0.0025** → **CONFIRMED** |
| H1b | median ΔW = **−0.2153**, **0/10** Seeds ≥ 0 → **NOT_CONFIRMED** |
| mean dispatch | **~30 kW** |
| H1 | **NOT_CONFIRMED → NICHT_WIRKSAM** |

H1a ist für Null und Treatment identisch (−0.2884), da der Dispatch die
Erzeuger-Phasen nicht beeinflusst — die R_grid-Senkung kommt allein vom
Leitungsausfall. Das ist konsistent mit der Spec-Trennung (Dispatch zielt auf
H1b, H1a kommt vom Stressor).

### Deskriptiv (Treatment, kein Verdict)

| Stress | mean ΔR | median ΔW | mean dispatch |
|---|---|---|---|
| Bewölkung | +0.0000 | −0.1123 | ~29 kW |
| Spitzenlast | +0.0000 | −0.2634 | ~30 kW |

## 3. Interpretation: Warum das Treatment schlechter ist als Null

Das zentrale, kontraintuitive Ergebnis: **Der aktive Dispatch macht H1b
schlechter als der passive Null-Stub** (median ΔW −0.2153 vs. −0.1562).

Die Ursache ist der **SoC-Drain**:

- Der passive Null-Stub stellt pauschal `0.4 × Σ_B ≈ 0.4 × 130 kW ≈ 52 kW`
  Flexibilität bereit, **ohne** dass sich ein Speicher leert.
- Der aktive Dispatch (Batterie → EV → Wärmepumpe) **ersetzt** diesen Stub,
  leert aber die SoC der Class-B-Ressourcen über die Simulationsdauer.
- Die mittlere Dispatch-Leistung sinkt dadurch auf **~30 kW**, was **unter**
  dem Stub-Niveau (52 kW) liegt.

Das bedeutet: Unter dem aktuellen Modell ist der aktive Dispatch **weniger
effektiv** als der passive Stub, weil die SoC begrenzt ist und sich leert,
während der Stub unerschöpflich ist. Die „Plastizität" (aktiver Dispatch) ist
hier schlechter als die „Starrheit" (passiver Stub).

**Der Vergleich ist fair**, weil der aktive Dispatch den Stub ersetzt (kein
`max(0.4 × Σ_B, aktiver_Dispatch)`). Das Treatment bekommt keinen unfairen
Vorteil; ein `max` hätte das Nullmodell künstlich auf Treatment-Niveau gezogen.
Das Ergebnis ist daher ein **ehrliches NICHT_WIRKSAM**, kein Artefakt einer
unfairen Baseline.

## 4. Deskriptive Ergebnisse (Bewölkung, Spitzenlast)

Beide werden deskriptiv berichtet, aber nicht für den Verdict verwendet (Pre-Reg).

Beide zeigen **ΔR = 0.0000**, weil sie Erzeugungs- bzw. Last-Szenarien sind und
die Erzeuger-Phasen nicht direkt beeinflussen (im Gegensatz zum Leitungsausfall,
der ein Netzsegment entfernt).

- **Bewölkung:** median ΔW = −0.1123 (moderater W_dyn-Rückgang durch Erzeugungseinbruch).
- **Spitzenlast:** median ΔW = −0.2634 (stärkerer W_dyn-Rückgang durch Lastanstieg).

Spitzenlast hat den größten W_dyn-Rückgang, was plausibel ist: Ein Lastanstieg
ist unter dem Dispatch-Modell eine größere Störung als ein Erzeugungseinbruch.

## 5. Methodische Caveats

1. **Der passive 0.4-Flex ist ein Stub**, kein realistisches Flexibilitätsmodell.
   Er ist eine pauschale, unerschöpfliche `0.4 × Capacity`. Ein reales System
   hätte eine Mischung aus aktiver und passiver Flexibilität mit endlicher SoC.
   Der Stub setzt damit eine hohe Messlatte, die der aktive Dispatch kaum
   erreichen kann.
2. **Keine SoC-Nachfüllung im Modell:** Der aktive Dispatch leert die SoC, füllt
   sie aber nicht nach (weder aus erneuerbarer Erzeugung noch aus dem Netz).
   Diese Modellvereinfachung benachteiligt den Dispatch. In einem realistischeren
   Modell mit SoC-Nachfüllung könnte der Dispatch effektiver sein.
3. **Dispatch schritt-synchron, nicht OODA-getaktet** (Spec-Caveat): Der Dispatch
   reagiert in diskreten Schritten auf das Defizit, nicht kontinuierlich getaktet
   durch die OODA-Zyklen. Das kann die Reaktionsfähigkeit leicht unterschätzen.
4. **Generalisierungs-Vorbehalt:** Der Verdict basiert nur auf Leitungsausfall-H1.
   Die Übertragbarkeit auf Bewölkung/Spitzenlast ist nicht getestet (beide sind
   deskriptiv und zeigen ΔR = 0, greifen also den Plastizitäts-Mechanismus anders).
5. **Schattenpreise / Hebb / Aktive Inferenz** sind bewusst ausgeklammert (Folgestudie).

## 6. Implikationen für Hebel 4 und die Hebel-Serie

Hebel 4 (Plastizität) ist **NICHT_WIRKSAM**. Der aktive Dispatch hält W_dyn nicht
stabil, weil die SoC begrenzt ist und sich leert, während der passive Stub
unerschöpflich ist.

Das setzt das **diagnostische Muster der Hebel-Serie** fort:

| Hebel | Ergebnis | Charakter |
|---|---|---|
| Hebel 1 (Redundanz) | NICHT_WIRKSAM auf realen Daten | strukturell gelöst, funktional datenabhängig |
| Hebel 2 (Zuweisung) | POSITIVBEFUND (Sim) | validierend, nicht therapeutisch (Prod nutzt Least-Loaded bereits) |
| Hebel 3 (TIER-2a) | INCONCLUSIVE | kein klarer Befund |
| Hebel 4 (Plastizität) | NICHT_WIRKSAM | aktiver Dispatch < passiver Stub (SoC-Drain) |

Die vier Hebel haben überwiegend **diagnostisch** gewirkt: Sie haben Probleme
aufgezeigt (Redundanz, mangelnde wirksame Plastizität) und Annahmen validiert
(Zuweisung), aber keine unmittelbaren therapeutischen Produktions-Verbesserungen
geliefert. Das ist eine ehrliche und wertvolle Erkenntnis — sie verhindert, dass
ineffektive Mechanismen als Verbesserungen verkauft werden.

## 7. Nächste Schritte (Optionen)

1. **Dispatch-Modell realistisch machen:** SoC-Nachfüllung modellieren — **neue Pre-Reg**.
2. **Passiven Stub hinterfragen:** realistischere Null-Baseline — **neue Pre-Reg**.
3. **Ergebnis akzeptieren:** kein unmittelbarer Handlungsbedarf.
4. **Hebel-Serie abschließen:** zusammenfassendes Abschluss-Dokument der vier Hebel.

## 8. Reproduktion

```bash
cd /Volumes/THX_OS_ULTRA\ -\ Data/Users/olivermueller/agent_x_storage

# Tests
python3 -m pytest scripts/test_hebel4_plastizitaet.py scripts/test_smartgrid_stress.py -v

# 10-Seed-Lauf (Null + Treatment + deskriptive Stressoren)
python3 scripts/run_hebel4_plastizitaet_study.py

# Artefakt: hebel4_plastizitaet_ergebnis.json
```
