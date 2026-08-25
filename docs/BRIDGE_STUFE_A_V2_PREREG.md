# Stufe A v2 — Matched-N + Hawkes-Vorzeichen (Pre-Registration)

**Status:** Pre-Registration — **bindend** (bestätigt 2026-08-18). Studie **geschlossen** (`docs/BRIDGE_STUFE_A_V2_ERGEBNIS.md`: `V2_UNSPEZIFISCH`, definitiv).
**Datum:** 2026-08-18
**Spec:** `docs/BRIDGE_STUFE_A_V2_SPEC.md`
**Folgestudie von:** `docs/BRIDGE_STUFE_A_PREREG.md` / `docs/BRIDGE_STUFE_A_ERGEBNIS.md`
**Charakter:** Neue, eigenständige Auswertungsregel. Stufe A bleibt versiegelt
(`UNSPEZIFISCH`). Diese Datei deutet Stufe A nicht um.

Stufe B (Ausfallfenster) und Smart-Grid-Plastizität stehen hier nicht zur
Debatte. Nach dem geschlossenen `V2_UNSPEZIFISCH` ist Stufe B **jetzt nicht
zu verfolgen**: praktisch blockiert (kein datiertes Halt-Fenster) und
interpretatorisch geschwächt (Kontrolle keine saubere Negativkontrolle).
Das schließt Brücken-Kausalität nicht prinzipiell; siehe
`docs/BRIDGE_STUFE_A_V2_ERGEBNIS.md` §6.1.

---

## 0. Warum v2, und was sie nicht ist

Stufe A hat bindend `UNSPEZIFISCH` geliefert, weil die Kontrolle BH-Hits hatte.
Zwei *Hypothesen über dieses Label* sind ungetestet:

1. Die Kontroll-Hits sind ein **Power-Artefakt** der N-Asymmetrie
   (~265× / ~67× Events).
2. Die Kontroll-Hawkes-Hits sind **keine Anregung**: γ̂ < 0, der Test war
   einseitig oben gegen Jitter (`surr ≥ obs`), nicht ein Test auf γ̂ > 0.

v2 testet beide Hypothesen **gemeinsam**, auf denselben eingefrorenen 90 Tagen,
ohne neue Events und ohne Ausfallfenster.

v2 ist **nicht:** Nachjustierung von Stufe A, Reduktion der 248 Tests,
Zweiseitigkeit (würde Anregung schwächen), Stufe B.

---

## 1. Hypothese

**H1-v2:** Nach (i) Angleich der Kontroll-Eventzahl an das Treatment per
Exact-N-Thinning und (ii) Zählen von Hawkes-Hits nur bei BH-Reject **und**
γ̂ > 0 gilt die Stufe-A-Kontrastlogik zugunsten des OmniBridge-Paars:

Treatment zeigt mindestens eine BH-signifikante **positive** Hawkes-Anregung
**und** mindestens einen BH-signifikanten CTE-Lag; die Matched-N-Kontrolle
zeigt **keine** positive Hawkes-BH-Hits und **keine** CTE-BH-Hits.

**H0-v2:** Nach Matched-N und Vorzeichen-Konjunktion bleibt der Kontrast
unspezifisch oder das Treatment-Signal verschwindet unter der v2-Zählregel.

---

## 2. Was von Stufe A unverändert bleibt

| Parameter | Wert |
|---|---|
| Fenster | 2026-05-20 00:00:00 UTC – 2026-08-17 23:59:59 UTC |
| Capture-Dateien | dieselben JSONL wie Stufe A (kein Recapture) |
| Adressen / topic0 / UR-Menge | `bridge_stufe_a_config.py` (byte-gleich) |
| Lags | 0…30 min, 1 min → **248 Tests** pro Draw |
| Metriken | Hawkes γ(τ), CTE \| Gas, BTC, CEX |
| FDR | **eine** BH-Prozedur, q=0.05, über den **ganzen 248-Vektor** |
| Hawkes-Null | Jitter ±5 min, nur Quelle, Ziel fest, 1000 Surrogate |
| CTE-Null | Shuffle der Quell-Belegung, 1000 Surrogate |
| p | plus-one `(1 + #{surr ≥ obs}) / 1001` |
| IAAFT | verboten |
| Treiber | `drivers_90d.jsonl`, Coverage-Gate ≥ 80 % (Joint-AND) |
| N_min | 100 Events je Strom **nach** Thinning |

α = Σγ(τ) und UTE bleiben deskriptiv, nicht in den 248.

---

## 3. Was v2 gegenüber Stufe A ändert

Nur zwei Dinge, beide vorab:

### 3.1 Vorzeichen-Konjunktion — nur Hawkes

Ein Hawkes-Lag zählt als Hit genau dann, wenn

```text
bh_reject AND (γ̂ > 0)
```

Begründung: γ̂ kann positiv oder negativ sein. Der Stufe-A-Test prüft nur
obere Abweichung vom Jitter. Die Konjunktion verlangt zusätzlich **Anregung**
(positiver Punktwert). Sie ändert die Nulldichte nicht, nur die Zählregel.

**CTE bleibt reiner BH-Reject.** Plugin-CTE ist definitionsgemäß ≥ 0.
Eine zusätzliche Hürde „CTÊ > 0“ ist identisch mit „CTÊ nicht 0“ und wäre
eine Scheinhürde. CTE-Hits = `bh_reject` allein.

Zweiseitige Hawkes-Tests gegen Jitter sind **verboten** (würden Anregung
abschwächen).

### 3.2 Matched-N der Kontrolle (ändert die Null)

Nur die **Kontroll-Punktprozesse** werden verdünnt. Treatment bleibt bei vollem N
(6 197 / 6 258). Treiber und das 1-min-Raster bleiben unangetastet.

---

## 4. Exact-N-Thinning (vollständig)

### 4.1 Zielkardinalität

Paar-Positionen: Treatment (ETH, Gnosis) ↔ Kontrolle (ETH, Arbitrum).

| Kontroll-Strom | Ziel-N nach Thinning |
|---|---|
| ctrl_eth | N\* = N(treat_eth) im Fensterfilter der Pipeline |
| ctrl_arbitrum | N\* = N(treat_gnosis) im Fensterfilter der Pipeline |

N\* ist durch die versiegelten Capture-Dateien bestimmt, nicht durch v2-Peek.

Falls `len(ctrl) < N\*`: Draw `V2_INCONCLUSIVE` (erwartet: tritt nicht ein).

### 4.2 Verfahren — Uniformes Event-Subset (bedingtes Independent Thinning)

**Zugelassen:** Ziehung **ohne Zurücklegen** von genau N\* Indizes aus der
sortierten Eventliste des Kontroll-Stroms. Die behaltenen Zeitstempel sind
eine echte Teilmenge der beobachteten Events.

```text
idx = rng.sample(range(N_ctrl), N_star)   # ohne Zurücklegen, uniform
thinned = sorted(times[i] for i in idx)
```

Das ist Independent Thinning **bedingt auf** #{kept} = N\*. Intensität wird
skaliert; relative Cluster unter den behaltenen Punkten bleiben reale
Teil-Cluster. Hawkes und CTE arbeiten weiter auf Zeitstruktur, nicht auf
einer neu gewürfelten Lage im Fenster.

**Verboten (zerstört die Punktprozess-Struktur):**

- Events auf `Uniform(window_start, window_end)` neu setzen
- Minuten-Bins unabhängig von den Eventzeiten subsamplen
- Block-Bootstrap / IAAFT
- Mit Zurücklegen (würde Duplikat-Zeitstempel erzeugen)
- Dieselbe Indexmenge auf beide Kontroll-Ströme zwingen (unterschiedliche N)

Zwei unabhängige Subsets pro Draw: eines für ctrl_eth, eines für ctrl_arbitrum.

### 4.3 Occupancy

Pro Draw: 1-min-Belegung neu aus den verdünnten Zeitstempeln. Treatment-
Occupancy wird einmal berechnet und für alle Draws wiederverwendet.

### 4.4 Anzahl Draws

**D = 21** (ungerade, Majority ohne 50/50-Patt).

D=21 bleibt. Ein Majority-Ergebnis im Korridor 10–12/21 ist **kein**
definitives V2-Label — siehe §5.2.

### 4.5 Seed und RNG-Trennung

```text
BRIDGE_STUFE_A_V2_SEED = 20260818
```

| Strom | Generator |
|---|---|
| Treatment, einmalig (Hawkes-Jitter + CTE-Shuffle) | `Random(SEED)` |
| Draw d ∈ {0,…,20}: Thinning beider Kontroll-Ströme | `Random(SEED + 1_000 + d)` |
| Draw d: Kontroll-Surrogate (Jitter/Shuffle) | `Random(SEED + 10_000 + d)` |

Thinning-RNG und Surrogat-RNG sind getrennt. Treatment wird **nicht** pro Draw
neu gesurrogated (sonst mischte man Monte-Carlo-Rauschen des Treatments in die
Draw-Streuung).

### 4.6 Surrogate pro Draw

Pro Draw dieselben **1000** Jitter- bzw. Shuffle-Surrogate wie Stufe A, auf den
**verdünnten** Kontroll-Serien (und dem festen Treatment). Plus-one-p analog.
Kein Teilen von Surrogaten über Draws.

### 4.7 BH pro Draw

Pro Draw ein 248-Vektor: Treatment-p (fest) + Kontroll-p (draw-spezifisch).
**Eine** BH-Prozedur q=0.05 über diese 248 p-Werte. Danach Hawkes-Zählung mit
Vorzeichen-Konjunktion. Die BH-Schwelle darf über Draws variieren (Ranking
ändert sich) — das ist FDR-Kontrolle je Draw, kein Nachziehen.

**Kein gepoolter BH über Draws.** Ein gepoolter BH würde die Draws vermischen
und könnte von einzelnen starken Draws dominiert werden; er beantwortet eine
andere Frage („gibt es einen Effekt in den gepoolten Daten?“) und ist für die
Robustheitsfrage die schwächere Wahl.

---

## 5. Verdict-Logik (nur v2, Prefix `V2_`)

Hits, nach BH des jeweiligen Draws:

| Zähler | Definition |
|---|---|
| `n_h_t` | #{Treatment-Hawkes-Lags: bh_reject ∧ γ̂ > 0} |
| `n_c_t` | #{Treatment-CTE-Lags: bh_reject} |
| `n_h_c` | #{Kontroll-Hawkes-Lags: bh_reject ∧ γ̂ > 0} |
| `n_c_c` | #{Kontroll-CTE-Lags: bh_reject} |

| Label | Regel |
|---|---|
| `V2_POSITIVBEFUND` | n_h_t ≥ 1 **und** n_c_t ≥ 1 **und** n_h_c = 0 **und** n_c_c = 0 |
| `V2_NEGATIVBEFUND` | n_h_t = 0 **und** n_c_t = 0 |
| `V2_DISSOZIIERT` | Treatment Hawkes-pos XOR CTE (eines 0, das andere ≥ 1); Kontrolle n_h_c = n_c_c = 0 |
| `V2_UNSPEZIFISCH` | Treatment hat (n_h_t ≥ 1 und n_c_t ≥ 1) **oder** ein DISSOZIIERT-Muster, **und** Kontrolle hat n_h_c ≥ 1 **oder** n_c_c ≥ 1 |
| `V2_INCONCLUSIVE` | N < 100 in einem Strom nach Thinning, oder Treiber-Coverage < 80 % |

Wie Stufe A: POSITIVBEFUND verlangt Treatment-Konjunktion Hawkes **und** CTE
sowie leere Kontrolle. Der einzige Unterschied zur Stufe-A-Zählung ist, dass
Hawkes-Hits γ̂ > 0 verlangen.

### 5.0 Per-Draw-Kriterium (Majority ist sonst nicht wohldefiniert)

Die Majority zählt **Labels**, nicht p-Werte. Dafür muss vorab festliegen, wann
ein Draw „den Effekt“ trägt.

**Effekt in Draw d vorhanden** genau dann, wenn das Draw-Label
`V2_POSITIVBEFUND` ist, also nach der **Draw-BH** über den ganzen 248-Vektor:

1. Treatment: ≥ 1 Hawkes-Lag mit `bh_reject ∧ γ̂ > 0`
2. Treatment: ≥ 1 CTE-Lag mit `bh_reject` (kein Vorzeichen-Zusatz)
3. Matched-N-Kontrolle: **0** Hawkes-Lags mit `bh_reject ∧ γ̂ > 0`
4. Matched-N-Kontrolle: **0** CTE-Lags mit `bh_reject`

Ohne (1)–(4) ist die Majority-Zählung von `V2_POSITIVBEFUND` nicht definiert.
Die übrigen vier Labels folgen der Tabelle oben; jedes Draw bekommt genau
eines der fünf `V2_*`-Labels. Majority ist die 5-Wege-Zählung dieser Labels,
nicht ein Binär-Votum und nicht ein gepoolter BH.

### 5.1 Aggregation über 21 Draws

**majority_label** = einziges Label mit Häufigkeit ≥ 11; sonst (Split / kein
Label ≥ 11) `V2_UNSPEZIFISCH`.

- Ein Draw `V2_INCONCLUSIVE` zählt als Stimme für `V2_INCONCLUSIVE`.
  ≥ 11 solche Stimmen → `majority_label = V2_INCONCLUSIVE`.

Stufe-A-`UNSPEZIFISCH` wird nicht überschrieben, nicht in die Majority gemischt,
nicht als Fallback verwendet.

### 5.2 Borderline-Korridor (D=21)

D=21 ist ungerade und für ein klares bimodales Muster (die meisten Draws
leer vs. die meisten Draws mit Restsignal) ausreichend. Instabil ist nur ein
Ergebnis nahe der Majority-Schwelle.

Sei `k*` die Häufigkeit des **häufigsten** Labels. **BORDERLINE** genau dann,
wenn genau ein Label diese Häufigkeit erreicht **und** `k* ∈ {10, 11, 12}`.
Gleichstand an der Spitze ist ein Split (`majority_label = V2_UNSPEZIFISCH`),
kein Borderline-Fall.

| `k*` | majority_label | confirmatory_verdict | Lesart |
|---|---|---|---|
| ≥ 13, eindeutig | dieses Label | dasselbe Label | definitiv unter D=21 |
| 11 oder 12, eindeutig | dieses Label (≥ 11) | `V2_UNSPEZIFISCH` | **nicht** definitiv; Follow-up mit höherem D empfohlen |
| 10 (führend) | `V2_UNSPEZIFISCH` (keine Majority) | `V2_UNSPEZIFISCH` | **nicht** definitiv; Follow-up mit höherem D empfohlen |
| ≤ 9 oder Gleichstand an der Spitze | `V2_UNSPEZIFISCH` | `V2_UNSPEZIFISCH` | Split / keine Majority; kein Borderline-Zwang |

`confirmatory_verdict` ist das bindende Studien-Verdict. Ein 11/21 oder 12/21
darf **nicht** als belastbares `V2_POSITIVBEFUND` / `V2_NEGATIVBEFUND` /
`V2_DISSOZIIERT` gelesen werden — `majority_label` bleibt deskriptiv im JSON.

Ein Follow-up mit höherem D ist eine **neue** Pre-Reg (D vor dem Lauf
festgelegt). In dieser Studie wird D nicht nachgezogen.

### 5.3 Deskriptiv (nicht konfirmatorisch)

- Anteil Draws mit Effekt vorhanden = #{`V2_POSITIVBEFUND`} / 21
- Median und IQR von `n_h_c`, `n_c_c` über Draws
- Median der Kontroll-γ̂ an τ=1,2,14 (Stufe-A-Kontroll-Hits) — **nur** Dossier,
  nicht als Extra-BH
- α und UTE wie Stufe A
- `borderline`, `k*`, `majority_label` neben `confirmatory_verdict`

Kein zweiter konfirmatorischer Pfad (kein Median-p-dann-ein-BH zusätzlich,
kein gepoolter BH).

---

## 6. Lesart der möglichen Ausgänge

Die Lesart gilt nur, wenn `confirmatory_verdict` definitiv ist (`k* ≥ 13`,
nicht BORDERLINE). Bei BORDERLINE: Stufe-A-`UNSPEZIFISCH` bleibt ungedeutet;
v2 dokumentiert Instabilität unter D=21.

| confirmatory_verdict | Was es über Stufe-A-`UNSPEZIFISCH` sagt |
|---|---|
| `V2_POSITIVBEFUND` | Kontroll-Hits der Stufe A sind unter Matched-N + Vorzeichen nicht reproduzierbar; der Kontrast trägt unter der strikteren Regel |
| `V2_UNSPEZIFISCH` | Auch bei gleichem N und γ̂>0-Filter bleibt die Kontrolle BH-auffällig; Power/Vorzeichen erklären das Label nicht vollständig — **oder** BORDERLINE / Split |
| `V2_NEGATIVBEFUND` | Treatment-Konjunktion fällt unter der Vorzeichen-Regel (Hawkes-Hits waren nicht positiv, oder CTE fällt — letzteres unerwartet) |
| `V2_DISSOZIIERT` | Nur eine der beiden Treatment-Metriken trägt unter v2; Kontrolle leer |
| `V2_INCONCLUSIVE` | Thinning/Coverage-Gate |

Keine dieser Lesarten ändert `docs/BRIDGE_STUFE_A_ERGEBNIS.md`.

---

## 7. Was nach Bestätigung verboten ist

- 248 Tests auf Familien oder „interessante“ Lags reduzieren
- CTE mit einer Vorzeichen-Hürde nachrüsten
- Hawkes zweiseitig gegen Jitter
- Thinning durch Uniform-im-Fenster oder IAAFT ersetzen, weil Cluster „zu stark“ bleiben
- D, Seed, N\*-Regel, Majority-Schwelle, Borderline-Korridor oder per-Draw-Kriterium nach dem ersten Draw ändern
- Einen 11/21- oder 12/21-Majority-Label als definitives V2-Label berichten
- Gepoolter BH über Draws statt Majority über per-Draw-BH
- Kontrolle auf Arbitrum-Inbox umstellen
- Stufe-A-JSON-p-Werte der Kontrolle wiederverwenden (volle N); v2 muss Kontrolle neu rechnen
- Treatment pro Draw neu thinnen (H1-v2 betrifft die Kontrolle)
- Studien-Verdict aus deskriptiven Median-Kurven ableiten
- D in dieser Studie erhöhen, weil das Ergebnis im Borderline-Korridor lag
  (das wäre optionales Stoppen; Follow-up = neue Pre-Reg)

---

## 8. Reihenfolge / Gates

1. Diese Pre-Reg **bestätigen** — erledigt 2026-08-18 (Status bindend).
2. Spec + Tests ohne Live-JSONL-Peek der v2-Ausgänge (Synthetic Thinning,
   Sign-Zählung, Majority, Borderline).
3. Pipeline gegen die **eingefrorenen** Capture-Dateien.
4. Dossier `docs/BRIDGE_STUFE_A_V2_ERGEBNIS.md` strikt gegen diese Datei.

Kein Schritt 3 vor Schritt 1.
