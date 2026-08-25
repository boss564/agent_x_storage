# Emergenz — Kopplungs-Umbau: Pre-Registration

**Status:** **BINDEND** — Review-Freigabe erteilt 2026-08-24.  
**Studie:** **GESCHLOSSEN** 2026-08-25 — Full-Sweep final, **nicht nachjustiert**.  
**Ergebnis:** `KOPPLUNG_INVALID` · κ\* = `None` · §1.1 **widerlegt** · Gate B↔C nirgends ≥4/6.  
**Auswertung:** `agents_b2g/emergence/EMERGENZ_KOPPLUNG_ERGEBNIS.md` (FINAL) · Artefakte `agents_b2g/emergence/kopplung_full/`.  
Schwellen (§3) fest · Vorhersage (§1.1) eingefroren · Verdict-Mapping (§4) versiegelt.  
κ-Sweep freigegeben unter diesen Regeln; Ergebnis = was herauskommt. Kein weiterer Sweep auf derselben Fragestellung.
**Vorlauf:** `agents_b2g/emergence/README.md` (Baseline `NO_COUPLING`, versiegelt)
**Messkette:** `agents_b2g/emergence/measure.py` (Selbsttest 5/5), `adapter_agentx.py`
**Charakter:** Interventionsstudie am System, nicht an seiner Vermessung.
Erste Studie der Serie, die den Schwarm **verändert** statt ihn zu beschreiben.

---

## 0. Ausgangslage und Zweck

Baseline (27-Agenten-ABM, 128 Ticks): `D_dyn = 0,947`, Kuramoto `r = 0,671`,
`p = 0,582` → **`NO_COUPLING`**. Die Agenten divergieren und arbeiten, aber ihre
Taktraten sind voneinander unabhängig. Es existiert keine Rückkopplung: kein
Agent verändert sein Verhalten aufgrund dessen, was er bei anderen beobachtet.

Diese Studie führt genau eine solche Rückkopplung ein und prüft vorab
registriert, ob daraus kollektive Ordnung entsteht — oder ob nur die
eingespeiste Modulation durchschlägt.

### 0.1 Bekannte Lücke des Messwerkzeugs (bestimmt das Design)

`measure.assess()` erkennt `TRIVIAL_SYNC` ausschließlich über `D_dyn ≈ 0`.
Hängt die Taktmodulation an einer **globalen** Größe (Gesamt-Queue, globaler
Gaspreis), synchronisieren alle Agenten auf denselben äußeren Takt, während
`D_dyn > 0` bleibt — die Interpretationsmatrix meldet dann `COUPLED`, obwohl
eine gemeinsame Uhr vorliegt. Das Werkzeug kann diesen Fall nicht ausschließen.

**Konsequenz:** Die Modulation darf nur **lokal beobachtete** Partnerzustände
verwenden, und Arm C (§2.3) ist nicht optional, sondern der eigentliche Test.

---

## 1. Hypothesen

**H1:** Lokale Rückkopplung der Taktrate auf die Queue-Länge eines festen
Partners erzeugt kollektive Phasenkohärenz oberhalb einer kritischen
Kopplungsstärke κ_c.

**H0:** Es entsteht keine Kohärenz, die über die eingespeiste Modulation
hinausgeht — Arm B unterscheidet sich nicht von Arm C.

### 1.1 Registrierte riskante Vorhersage

**Arm C bleibt bei allen sechs κ-Stufen `NO_COUPLING`.**

Diese Vorhersage kann fehlschlagen und ist der Satz, an dem die Studie hängt.
Geht C ebenfalls `COUPLED` (Gate §3.1 nach Mehrheitsregel §3.3), misst die Studie
die Modulationsamplitude, nicht die Vernetzung — dann ist auch ein positives
Ergebnis in B wertlos.

---

## 2. Design

### 2.1 Intervention

```
interval_i = base_i × (1 + κ · inbox_len(partner_i) / capacity)
```

- `base_i` aus `gas/gas_profiles.py` (heterogen, unverändert)
- `partner_i` — genau **ein** Sticky-Partner je (Sender, Rolle), bestehende
  Signatur `coupling.update_sender_interval(agent, partner, kappa, …)`
- **Kein globales Aggregat.** Keine Gesamt-Queue, kein globaler Gaspreis,
  keine Zykluszahl als Eingang.

### 2.2 Topologie-Freeze (verbindlich)

Nach **32 Ticks Warm-up** wird die Sticky-Map (`StickySelector._last`)
eingefroren; die Least-Loaded-Umschaltung ist für den Rest des Laufs
deaktiviert. Ohne Freeze wandert die Nachbarschaft während des Sweeps, und κ
misst eine sich verändernde Topologie statt einer Kopplungsstärke.

*Implementiert:* `StickySelector.freeze()` / `unfreeze()` / `load_map()` —
siehe `partner_select.py`. Nach Freeze: keine Load-Umschaltung.

### 2.3 Drei Arme, identischer κ-Sweep

κ ∈ {0 · 0,2 · 0,4 · 0,6 · 0,8 · 1,2}, je Stufe 2 Läufe (Determinismus-Nachweis).

| Arm | Modulation | Registrierte Erwartung |
|-----|------------|------------------------|
| **A** Baseline | κ = 0 | `NO_COUPLING` (Replikation der Baseline) |
| **B** Intervention | echter Sticky-Partner | Übergang bei κ_c |
| **C** Shuffle | **degree-preserving** bijektive Permutation der eingefrorenen Sticky-Map | `NO_COUPLING` bei jedem κ |

Arm C hat identische Modulationsamplitude und identischen Grad
(`|partners_i|_C = |partners_i|_B` für jedes i), aber zerstörte Kanten-Identität.
Permutation innerhalb des Rollensegments, damit die Rollenstruktur erhalten bleibt.

---

## 3. Bindende Schwellen

| Konstante | Wert | Bedeutung |
|-----------|-----:|-----------|
| `N` | 27 | Agenten |
| `r_random` | 0,1925 | 1/√N — Zufallsgrundwert |
| `α` | 0,05 | Kuramoto-Surrogat, `measure.kuramoto` |
| `n_surrogates` | 200 | Phasenrandomisierung je Punkt |
| `Δr_min` | 0,10 | Mindestabstand Arm B zu Arm C bei gleichem κ |
| `r_floor` | 0,34 | `r_random + 0,15` — Effektstärke-Untergrenze |
| `warmup_ticks` | 32 | vor Topologie-Freeze |
| `cycles` | 512 | je Lauf, nach Warm-up |

### 3.1 Gate für `COUPLED` (alle vier, keine Ausnahme)

1. `p < α` gegen Phasen-Surrogate
2. `D_dyn > 0` — kein `TRIVIAL_SYNC`
3. `r_B − r_C ≥ Δr_min` bei identischem κ
4. `r_B ≥ r_floor`

Kriterium 4 folgt aus dem Korridor-Präzedenzfall: `r = 0,27` gegen einen
Zufallsgrundwert von 0,19 war signifikant und dennoch marginal. Eine vorab
gesetzte Untergrenze verhindert, dass ein p-Wert die Schwäche des Effekts verdeckt.

### 3.2 Form-Kriterium (primär, nicht Punkt-Signifikanz)

Kollektive Ordnung zeigt sich als **Übergang**, nicht als linearer Anstieg:

```
Δ_k        = r̄(κ_{k+1}) − r̄(κ_k)                 auf dem Seed-Mittel r̄
Bedingung  = max_k Δ_k ≥ 3 × mean_{j<k} Δ_j   UND   max_k Δ_k ≥ 2 × SD_pool
```

`SD_pool` = gepoolte Standardabweichung von `r` über die sechs Seeds (§5.1).
Ohne diese zweite Schranke könnte ein „Sprung" die Streuung zwischen den Seeds
sein statt ein Übergang — die Fehlerbalken, die Weg A nicht liefern konnte.

Ein linearer Verlauf `r(κ)` ist bloßes Durchschlagen der Erzwingung und zählt
nicht als Emergenz, auch wenn Gate §3.1 erfüllt ist.

### 3.3 Aggregation über Seeds (bindend)

Gate §3.1 wird **je Seed** ausgewertet, nicht auf dem Mittel. Ein κ gilt als
`COUPLED`, wenn **≥ 4 der 6 Seeds** alle vier Kriterien erfüllen — Mehrheitsregel
analog zur V2-`k*`-Zählung. Damit trägt die Seed-Variation die Aussage, statt in
einem Mittelwert zu verschwinden.

---

## 4. Verdict-Mapping

| Verdict | Bedingung (Priorität top-down) |
|---------|--------------------------------|
| `KOPPLUNG_INVALID` | Arm C bei irgendeinem κ `COUPLED` nach Gate §3.1 + Mehrheitsregel §3.3 → Vorhersage §1.1 widerlegt, Studie endet |
| `HOMOGENIZED` | `mean_seeds D_dyn(B, κ*) < mean_seeds D_dyn(A)`, wobei κ* die niedrigste κ-Stufe ist, die das Gate nach §3.3 erfüllt. Erfüllt kein κ das Gate, ist `HOMOGENIZED` nicht anwendbar (Ergebnis dann `NO_COUPLING`) |
| `COUPLED_EMERGENT` | Gate §3.1 nach Mehrheitsregel §3.3 **und** Form-Kriterium §3.2 |
| `COUPLED_FORCED` | Gate §3.1 nach Mehrheitsregel §3.3, aber Form-Kriterium §3.2 verfehlt — Effekt ist Erzwingung |
| `NO_COUPLING` | Gate §3.1 nach Mehrheitsregel §3.3 bei keinem κ erfüllt |

`KOPPLUNG_INVALID` und `HOMOGENIZED` sind vollwertige Ergebnisse, keine Fehlschläge.

---

## 5. Stochastik und Determinismus

### 5.1 `run_seed` als einzige Quelle der Lauf-Variation

```
run_seed ∈ {20260824, 20260825, 20260826, 20260827, 20260828, 20260829}
```

Der Seed speist **genau drei** Stellen:

| Ziel | Wirkung | Pfad |
|------|---------|------|
| `init_timing(…, run_seed=…)` | Anfangsphase: `(crc32(f"{agent_id}\|{run_seed}") % 1000)/1000 × base_interval` | **Intervall (§2.1)** |
| `oscillator_from_gas(…, run_seed=…)` | Anfangsladung des Relaxations-Oszillators | Relax / Korridor |
| `permute_sticky_map(frozen, seed=…)` | Arm-C-Permutation | beide |

**Diese Studie läuft im Intervall-Pfad.** Dort ist `use_osc = relax or use_corridor`
gleich `False` — es entstehen keine Oszillatoren, `oscillator_from_gas` wird nicht
aufgerufen. Ohne den `init_timing`-Hook würde `run_seed` deshalb ausschließlich
Arm C diversifizieren, während Arm B über alle sechs Seeds identisch bliebe.

Der Hook behebt zugleich eine degenerierte Anfangsbedingung: `init_timing` setzte
zuvor `phase = 0.0` für **jeden** Agenten. Für eine Synchronisationsstudie ist das
der ungünstigste Start — `r = 1,0` bei t = 0 per Konstruktion, und jede später
gemessene Kohärenz wäre nicht vom Rest dieses gemeinsamen Starts zu trennen.

Zwei Randbedingungen, die der Hook einhält und die so bleiben müssen:

- **Hash-Eingang ausschließlich `agent_id|run_seed`.** Keine Korrelation mit `fee`
  oder `base_rate`, sonst vermischen sich Seed-Variation und Heterogenität.
  `base_interval` wirkt nur als Multiplikator.
- **Wirkung vor dem Warm-up.** Die 32 Ticks bis zum Topologie-Freeze müssen bereits
  aus verschiedenen Anfangsbedingungen laufen. Sonst konvergieren alle Seeds auf
  dieselbe Sticky-Map und Arm C verliert seine Variation gleich mit.

Er speist **ausdrücklich nicht**: `base_rate` (bleibt aus `gas_profiles`),
Partnerwahl im Warm-up, Nachrichtenreihenfolge, Tick-Ordnung. Sonst
unterschieden sich Läufe in mehr als der Anfangsbedingung und κ_c wäre nicht
mehr zurechenbar.

Hintergrund: `TickController.__init__(seed=…)` nimmt einen Seed entgegen,
speichert ihn aber nicht — der Parameter ist wirkungslos. Ohne §5.1 wären sechs
Seeds sechs identische Läufe, berichtet als sechs Replikate. Das ist das
V2-Draw-Muster (21 Draws auf einer Stichprobe) eine Ebene höher.

### 5.2 Determinismus-Nachweis (Vorbedingung, zwei Teile)

Beide Teile müssen bei κ = 0 bestehen, bevor irgendein κ > 0 läuft:

| Teil | Bedingung | Was er ausschließt |
|------|-----------|--------------------|
| **D1** | gleicher `run_seed` → byte-identische Zustandsvektoren und Nachrichtenlogs | nicht reproduzierbare Läufe |
| **D2** | verschiedener `run_seed` → nachweislich **verschiedene** Zustandsvektoren | Duplikate, die als Replikate gezählt werden |

D2 ist der Teil, den Weg A nicht liefern konnte. Ohne ihn ist jede Mittelung
über Seeds eine Mittelung über Kopien.

### 5.3 Weitere Regeln

- `zlib.crc32` statt `hash()` für jede Arbeitsverteilung — `hash()` ist pro
  Prozess randomisiert (`PYTHONHASHSEED`).
- Arm A, B und C laufen je Seed und je κ mit identischem `run_seed`; die Arme
  unterscheiden sich ausschließlich in Modulation bzw. Sticky-Map.

---

## 6. Was diese Pre-Reg nicht tut

- Keine Änderung an der Graphdichte (TIER 1 abgeschlossen).
- Keine Intra-Rollen-Differenzierung — eigener Strang, eigene Pre-Reg.
- Keine Änderung der Messkette `measure.py` während des Sweeps.
- Keine Schwellen-Anpassung nach dem ersten Lauf.
- Keine Interpretation von `COUPLED_FORCED` als Emergenz.

---

## 7. Bindungs-Checkliste

- [x] `StickySelector.freeze()` implementiert und unit-getestet (ohne κ-Lauf)
      — `partner_select.py` + `scripts/test_emergence_kopplung_vorarbeit.py` V1 (7/7)
- [x] Shuffle degree-preserving, rollensegment-intern, verifiziert
      — `permute_sticky_map` / `assert_degree_preserving` + V2 (8/8)
- [x] `run_seed`-Hook in `oscillator_from_gas` **und** `init_timing` (§5.1, beide Pfade)
      — Intervall: Anfangsphase; Relax: Anfangsladung; Arm C: `permute_sticky_map`
- [x] Determinismus bei κ = 0: **D1 + D2** auf Intervall-Pfad (V3, 26/26;
      Phase vor Warm-up gestreut, in State-Matrix exponiert)
- [x] Schwellen als Zahlen fixiert (§3) — gebunden 2026-08-24
- [x] Registrierte Vorhersage vor Datenblick (§1.1) — eingefroren 2026-08-24
- [x] Explizite Bindungs-Freigabe — Review-Freigabe erteilt 2026-08-24

**Nach Bindung:** Schwellen und Vorhersage unveränderlich. κ > 0 freigegeben.
Bereichserweiterung des κ-Sweeps = neue Pre-Reg. Keine Schwellen-Anpassung nach Datenblick.

---

## 8. Abschluss (2026-08-25)

| Feld | Wert |
|------|------|
| Lauf | Full-Sweep · EXIT 0 · 78 Zellen · 493 s |
| Verdict | **`KOPPLUNG_INVALID`** |
| §1.1 | widerlegt (Arm C ab κ=0.2 mehrheitlich `COUPLED`) |
| Gate B↔C | 0/6 bei jedem κ |
| κ\* | `None` |
| Nachjustierung | **keine** |

Wissenschaftlich negatives Ergebnis / Falsifikation — final.
