# Stufe A v2 — Matched-N + Hawkes-Vorzeichen: Ergebnis-Dossier

**Status:** Geschlossen — `confirmatory_verdict` **`V2_UNSPEZIFISCH`**
(definitiv unter D=21, `k* = 15 ≥ 13`, nicht BORDERLINE).
Power-Artefakt nicht bestätigt. Kontrolle keine saubere Negativkontrolle.
Stufe B praktisch blockiert und interpretatorisch geschwächt, nicht logisch tot.
Stufe A unangetastet. Vektor-Bergung (Datenrettung) läuft separat.
**Auswertung:** 2026-08-18 UTC (`bridge_stufe_a_v2_ergebnis.json`)
**Fenster:** 2026-05-20 00:00:00 UTC – 2026-08-17 23:59:59 UTC (unverändert)
**Pre-Registration:** `docs/BRIDGE_STUFE_A_V2_PREREG.md` (bindend, 2026-08-18)
**Spec:** `docs/BRIDGE_STUFE_A_V2_SPEC.md`
**Lock-in:** `scripts/bridge_stufe_a_v2_config.py`, `scripts/bridge_stufe_a_v2_stats.py`,
`scripts/bridge_stufe_a_v2_pipeline.py`
**Charakter:** Folgestudie. Stufe A bleibt versiegelt (`UNSPEZIFISCH`).
Dieses Dossier deutet Stufe A nicht um.

Die 248-Vektoren je Draw wurden nach Abschluss aller 21 Draws nicht persistiert
(`PermissionError` beim JSON-Schreiben). Labels und `n_sig` stammen aus dem
Pipeline-Stdout; `v2_verdict()` bestätigt jedes Draw-Label byte-gleich zur
registrierten IUT. Die Majority-Aggregation braucht die Vektoren nicht.
Deskriptive Median-γ̂ an τ=1,2,14 und α/UTE fehlen deshalb — sie sind nach
Pre-Reg §5.3 nicht konfirmatorisch und werden nicht nachträglich aus Stufe A
(volle Kontroll-N) substituiert.

---



## 1. Hypothese und Regel

**H1-v2:** Nach Exact-N-Thinning der Kontrolle und Hawkes-Hits nur bei
`bh_reject ∧ γ̂ > 0` gilt der Stufe-A-Kontrast zugunsten OmniBridge:
Treatment ≥ 1 positive Hawkes-BH **und** ≥ 1 CTE-BH; Matched-N-Kontrolle
0 positive Hawkes-BH **und** 0 CTE-BH.

**H0-v2:** Der Kontrast bleibt unspezifisch, oder das Treatment-Signal fällt
unter der v2-Zählregel.

Registrierte Last (unverändert gegenüber Stufe A, plus v2-Zählregel):


| Parameter    | Festlegung                                                        |
| ------------ | ----------------------------------------------------------------- |
| Tests        | 248 pro Draw, eine BH q=0.05 über den ganzen Vektor               |
| D            | 21, Seed `BRIDGE_STUFE_A_V2_SEED = 20260818`                      |
| Thinning     | Exact-N ohne Zurücklegen: ctrl_eth → 6 197, ctrl_arbitrum → 6 258 |
| Hawkes-Hit   | `bh_reject ∧ γ̂ > 0`                                              |
| CTE-Hit      | `bh_reject` allein                                                |
| Majority     | einziges Label ≥ 11/21                                            |
| Definitiv    | eindeutiges `k* ≥ 13`                                             |
| BORDERLINE   | eindeutiges `k* ∈ {10, 11, 12}` → nicht als V2-Befund lesen       |
| Gepoolter BH | verboten                                                          |


---



## 2. Datenbasis

Dieselben eingefrorenen Capture-Dateien wie Stufe A. Kein Recapture.


| Strom         | N voll          | N in v2                 |
| ------------- | --------------- | ----------------------- |
| treat_eth     | 6 197           | 6 197 (nicht verdünnt)  |
| treat_gnosis  | 6 258           | 6 258 (nicht verdünnt)  |
| ctrl_eth      | 1 637 253       | 6 197 je Draw (Exact-N) |
| ctrl_arbitrum | 419 106         | 6 258 je Draw (Exact-N) |
| Treiber       | Joint-AND 0,998 | unverändert             |


`INCONCLUSIVE`-Gates nicht erreicht (N≫100 nach Thinning, Coverage ≥ 80 %).

---



## 3. Verdict

```text
counts: V2_UNSPEZIFISCH=15  V2_POSITIVBEFUND=6  sonst=0
k* = 15 (eindeutig)
majority_label        = V2_UNSPEZIFISCH
confirmatory_verdict  = V2_UNSPEZIFISCH
borderline            = false
definitive            = true
n_effect_present      = 6/21
```

`k* = 15 ≥ 13` und eindeutig → das Majority-Label **ist** das bindende
Studien-Verdict. Der Borderline-Korridor {10, 11, 12} greift nicht.

Treatment-Konjunktion hielt in **allen** 21 Draws (`n_h_t = 3`, `n_c_t = 62`).
Kein Draw ist `V2_NEGATIVBEFUND` oder `V2_DISSOZIIERT`. Die Spread kommt
ausschließlich von der Matched-N-Kontrolle: 6 Draws mit leerer Kontrolle
(`V2_POSITIVBEFUND`), 15 Draws mit mindestens einem Kontroll-Hit
(`V2_UNSPEZIFISCH`).

Stufe-A-`UNSPEZIFISCH` wird nicht überschrieben.

---



## 4. Per-Draw-Tabelle (konfirmatorische Zähler)

Hits nach Draw-BH und Vorzeichen-Konjunktion (Hawkes nur γ̂ > 0).


| Draw | Label              | n_h_t | n_c_t | n_h_c | n_c_c | Effekt |
| ---- | ------------------ | ----- | ----- | ----- | ----- | ------ |
| 0    | `V2_UNSPEZIFISCH`  | 3     | 62    | 1     | 1     | nein   |
| 1    | `V2_UNSPEZIFISCH`  | 3     | 62    | 1     | 0     | nein   |
| 2    | `V2_POSITIVBEFUND` | 3     | 62    | 0     | 0     | ja     |
| 3    | `V2_POSITIVBEFUND` | 3     | 62    | 0     | 0     | ja     |
| 4    | `V2_UNSPEZIFISCH`  | 3     | 62    | 1     | 2     | nein   |
| 5    | `V2_POSITIVBEFUND` | 3     | 62    | 0     | 0     | ja     |
| 6    | `V2_UNSPEZIFISCH`  | 3     | 62    | 1     | 0     | nein   |
| 7    | `V2_UNSPEZIFISCH`  | 3     | 62    | 0     | 1     | nein   |
| 8    | `V2_UNSPEZIFISCH`  | 3     | 62    | 0     | 1     | nein   |
| 9    | `V2_UNSPEZIFISCH`  | 3     | 62    | 1     | 2     | nein   |
| 10   | `V2_UNSPEZIFISCH`  | 3     | 62    | 0     | 1     | nein   |
| 11   | `V2_POSITIVBEFUND` | 3     | 62    | 0     | 0     | ja     |
| 12   | `V2_POSITIVBEFUND` | 3     | 62    | 0     | 0     | ja     |
| 13   | `V2_UNSPEZIFISCH`  | 3     | 62    | 2     | 0     | nein   |
| 14   | `V2_UNSPEZIFISCH`  | 3     | 62    | 0     | 1     | nein   |
| 15   | `V2_UNSPEZIFISCH`  | 3     | 62    | 1     | 1     | nein   |
| 16   | `V2_UNSPEZIFISCH`  | 3     | 62    | 1     | 2     | nein   |
| 17   | `V2_POSITIVBEFUND` | 3     | 62    | 0     | 0     | ja     |
| 18   | `V2_UNSPEZIFISCH`  | 3     | 62    | 0     | 1     | nein   |
| 19   | `V2_UNSPEZIFISCH`  | 3     | 62    | 0     | 1     | nein   |
| 20   | `V2_UNSPEZIFISCH`  | 3     | 62    | 0     | 1     | nein   |


---



## 5. Deskriptiv (nicht konfirmatorisch)


| Größe                          | Wert              |
| ------------------------------ | ----------------- |
| Anteil Effekt vorhanden        | 6/21              |
| `n_h_c` Median (IQR)           | 0 (0–1)           |
| `n_c_c` Median (IQR)           | 1 (0–1)           |
| Draws mit n_h_c ≥ 1            | 8/21              |
| Draws mit n_c_c ≥ 1            | 12/21             |
| Kontroll-γ̂ Median an τ=1,2,14 | nicht persistiert |
| α, UTE                         | nicht persistiert |


Kein zweiter konfirmatorischer Pfad. Kein gepoolter BH. Kein Nachziehen von D.

---



## 6. Lesart (Pre-Reg §6)

`confirmatory_verdict = V2_UNSPEZIFISCH` ist unter D=21 **definitiv** (`k* = 15`).
Kein Nachziehen von D, kein gepoolter BH, keine Umdeutung von Stufe A.

Die Label-Definition (Pre-Reg §5) ist die Lesart, nicht eine Abschwächung:
`V2_UNSPEZIFISCH` genau dann, wenn das Treatment Hits hat **und die Kontrolle
`n_h_c ≥ 1` oder `n_c_c ≥ 1`**. Pre-Reg §0: Stufe A lieferte bindend
`UNSPEZIFISCH`, *weil die Kontrolle BH-Hits hatte*. v2 hat dasselbe Label
unter Matched-N und γ̂>0 gehalten.

**Die Kreuz-Anregung ist durch die Kontrolle nicht als bridge-spezifisch
isolierbar.** Das Kontrastpaar hat einen gemeinsamen Treiber sichtbar gemacht.
Das schließt eine **brückenspezifische Komponente des Treatments nicht aus**:
Stufe-A-Signaturen sind qualitativ verschieden, nicht dieselbe Struktur.

| | Treatment (Stufe A / v2) | Kontrolle (Stufe A, volle N) |
|---|---|---|
| CTE | 62 Rejects, bidirektional, alle 31 Lags | 3 Rejects, unidirektional (ba), spärlich |
| Hawkes-Vorzeichen | positiv (Anregung) | negativ |

v2: Treatment-Konjunktion in allen 21 Draws (`n_h_t = 3`, `n_c_t = 62`);
Kontrolle nach Exact-N nur 0–2 Hits je Draw. Das Kontroll-Restsignal ist
persistent genug für `UNSPEZIFISCH`, aber nicht so pervasiv wie das Treatment.

Das ist kein Nullergebnis. 21 Draws, 248 Tests, 1000 Surrogate, 1,64 Mio.
Kontroll-Events, Coverage 0,998, ~5,4 h. Die Aussage:

1. Kreuz-Anregung zwischen Chains existiert.
2. Die bedingte TE gegen Gas/BTC/CEX erklärt sie nicht weg (fehlendes Z).
3. Die Kontrolle ist keine saubere Negativkontrolle — Isolation der Bridge
   gelingt nicht; eine brückenspezifische Treatment-Komponente bleibt offen.

Der wissenschaftliche nächste Schritt ist die Frage nach Z: welcher Confounder
wirkt zeitgleich auf beide Chains ohne direkte Bridge-Transaktion und ist durch
Gas/BTC/CEX nicht abgedeckt? Das braucht **kein** Ausfallfenster. Konfirmatorisch
nur in einer **neuen** Pre-Reg.

**Power-Artefakt:** nicht bestätigt (15/21 Draws mit Kontroll-Hit nach Exact-N).
Das Restsignal ist intermittierend (6/21 Kontrolle leer). Unter der Pre-Reg
sind diese sechs **nicht handlungsleitend** (`k* = 15`, `borderline = false`);
sie sind auch kein Rauschen von null. So stehen lassen.

### 6.1 Stufe B — praktisch blockiert, nicht logisch tot

Die Prämisse „Kontrolle zeigt dieselbe Struktur wie Treatment“ ist nach Stufe A
**nicht** belegt (Tabelle oben). Damit ist eine brückenspezifische Komponente
nicht ausgeschlossen, nur nicht sauber isolierbar.

Stufe B jetzt **nicht** verfolgen, aus den präzisen Gründen:

- **(a) praktisch blockiert:** kein exogenes, datiertes OmniBridge-Halt-Fenster
- **(b) interpretatorisch geschwächt:** Kontrolle ist keine saubere
  Negativkontrolle (Restsignal auch bei matched N)

Nicht: die Frage der Brücken-Kausalität sei prinzipiell geschlossen.

### 6.2 Fehlendes Z — nächste Studie, nicht diese

Arbeitskatalog (nicht vorab registriert, nicht getestet):

| Kandidat | Event-Beispiel |
|---|---|
| Orakel | Chainlink `AnswerUpdated` |
| Intent-Solver | Across `FilledOrder` |
| Liquidationen | Aave `LiquidationCall` |
| Stablecoin-Brücke | CCTP `DepositForBurn` |
| Market-Maker | `tx.from`-Cluster |

Leitplanken gegen HARKing, für die **künftige** Pre-Reg:

1. Auswahl-Kriterium vorab registrieren, oder alle fünf testen
2. Mehrfachtest-Korrektur (BH-FDR) über die Kandidaten-Familie
3. Eigener Capture je Kandidat auf beiden Chains, vor der Analyse

Lag-Struktur aus der Vektor-Bergung ist **deskriptiv** und darf die
konfirmatorische Kandidaten-Prüfung nicht ersetzen. Mehrere Kandidaten liegen
auf ähnlichen Zeitskalen (Sekunden–Minuten). Auswahl via Lags → Prüfung nur
in neuer Pre-Reg.

### 6.3 Deskriptive Lag-Lesung (nach Vektor-Bergung)

Grundlage: gerettete 248er-Vektoren der sechs `V2_POSITIVBEFUND`-Draws
(0-based Draws: 2, 3, 5, 11, 12, 17). Nicht konfirmatorisch.
`V2_UNSPEZIFISCH` bleibt bindend.

1. **Lag-Signatur kommt aus γ̂(τ), nicht aus CTE.**
   CTE bleibt in allen sechs Draws breitbandig (0..30 in ab und ba, insgesamt
   62 Rejects) und liefert keinen engen Selektions-Peak.
2. **Hawkes-Peaks sind asymmetrisch; die Draw-Wiederholung ist hier nicht unabhängig.**
   In allen sechs `V2_POSITIVBEFUND`-Draws identisch:
   - `ab` (ETH→Gnosis): BH-Hit bei τ=6
   - `ba` (Gnosis→ETH): BH-Hits bei τ=15/16
   Damit ist die Kernaussage die **direktionale Asymmetrie**
   `τ_ab < τ_ba` (etwa 1 : 2,5), nicht der absolute Lag allein.
   **Wichtig:** Das ist keine „6-fache“ bzw. „21-fache“ Treatment-Bestätigung.
   Der Treatment-Strom wird in v2 einmal berechnet und über Draws wiederverwendet;
   die Draw-Variation testet nur das Kontroll-Thinning.
3. **Kontrollseite in den sechs Draws leer.**
   Per Definition von `V2_POSITIVBEFUND`: `n_h_c = 0`, `n_c_c = 0`.
   Die Kontroll-Peaks wandern zwar deskriptiv, haben aber keine BH-Rejects.
4. **Plus-one-Auflösung bleibt zu beachten.**
   p = `(1+hits)/1001`, Floor ≈ 0,000999. Das ist Auflösungsgrenze,
   keine Präzisionsangabe.

#### 6.3.1 Abgleich mit dokumentierter OmniBridge/AMB-Verarbeitung

Dokumentierte aktuelle Gnosis-Regeln nennen richtungsabhängige Verarbeitung:
Ethereum→Gnosis via FCR (~12 s), Gnosis→Ethereum via Block-Finality (~5 min),
mit Fallback auf strengere Finality bei Instabilität/Hardfork.
([FCR-Doku](https://docs.gnosischain.com/bridges/fast-confirmation-rule)).
Zusätzlich nennt die Bridge-FAQ für zk-light-client-Verifikation grob
„about 20 minutes“ als operative OmniBridge-Dauer
([FAQ](https://docs.gnosischain.com/faq/bridges)).

Der beobachtete asymmetrische Peak (`6` vs. `15/16` min) ist **konsistent mit
einer richtungsabhängigen Bridge-Komponente** (`τ_ab < τ_ba`), aber nicht
deckungsgleich mit einer einzigen statischen „Sollzeit“ aus der Dokumentation.
Das passt zu wechselnden Betriebsregeln über die 90 Tage (FCR/Fallback/zk-Pfad)
und ist daher als **deskriptives Indiz**, nicht als Beweis zu lesen.

#### 6.3.2 Abgleich mit Kandidaten-Zeitskalen (deskriptiv)

Sekunden-bis-wenige-Minuten-Klassen (Orakel, Intent-Solver, Liquidationen,
MM-Cluster) können kurze Lags erklären, liefern aber **a priori** weniger
natürlich die stabile Richtungsasymmetrie `ab` vs. `ba`.
Die Lag-Lesung grenzt damit Kandidaten ein, wählt aber keinen aus.
Auswahl und Test nur in neuer Pre-Reg mit vorab registriertem Kriterium + BH-FDR.

#### 6.3.3 Evidenzgewicht der Asymmetrie (methodischer Hinweis)

Die Asymmetrie `ab:6` vs. `ba:15/16` ist inhaltlich präzise und testbar,
aber ihr Robustheitsgewicht stammt in dieser Studie aus **einer**
Treatment-Stichprobe (plus Kontroll-Resampling), nicht aus unabhängigem
Treatment-Resampling.

Wenn die Asymmetrie als priorisierendes Kandidatensignal in die nächste
Pre-Reg eingehen soll, braucht ihre Stabilität eine eigene
treatment-seitige Resampling-Struktur (z. B. Zeitfenster-Splits oder
Block-Bootstrap über disjunkte Perioden). Erst dann misst Wiederholung die
Robustheit des Treatment-Signals statt primär die Robustheit des
Kontrollrauschens.

#### 6.3.4 Methodik-Rahmen für die nächste Kandidaten-Pre-Reg

Die folgende Methodik ist als **Vorab-Rahmen** zu verstehen (noch nicht
konfirmatorisch ausgeführt), um Selektions-Bias bei der Kandidatenwahl zu
vermeiden:

1. **Blocklänge ist Kernparameter und wird präregistriert.**
   MBB-Blocklänge darf nicht ex post getunt werden. Mindestbedingung
   `E[L] >= τ_max` (30 min) ist notwendig, aber nicht hinreichend, weil das
   Hawkes-Gedächtnis über `τ_max` hinausreichen kann (z. B. Tagesperiodik).
   Praktisch konservativ: 24 h als Baseline; 60 min nur als Sensitivität.
   Die finale Blocklänge wird mit vorab fixiertem Kriterium festgelegt
   (z. B. Politis-White / Hall-Horowitz-Variante), nicht nach Ergebnislage.

2. **Rollen von K-Fold und MBB werden getrennt.**
   Primärpfad: disjunkte Zeitblöcke (K-Fold) für Schätzung/Interpretation.
   Sensitivitätspfad: MBB zur Varianz-/Robustheitsprüfung.
   Keine unklare Doppel-Resampling-Kaskade als Hauptanalyse.

3. **Schwellen werden begründet und diskrete Auflösung dokumentiert.**
   `P_sign >= 0,95` und `ASR > 2,0` sind plausible 95%-nahe Schwellen, aber
   bei kleinem `K` grob quantisiert. Für `K <= 9` ist `P_sign >= 0,95`
   faktisch „volle Übereinstimmung“ (z. B. 9/9). Das wird explizit
   preregistriert, plus Sensitivität über Schwellenraster
   `{0,80; 0,90; 1,00}`.

4. **Winsorisierung und EB-Shrinkage mit fixen Tuning-Parametern.**
   Winsor-Anteil wird vorab fixiert (Baseline 1%) und über
   `{0,5%; 1%; 2%}` sensitiv geprüft.
   Für EB-Shrinkage wird die Schätzung der Varianzterme eindeutig festgelegt
   (empirische Varianz über die vordefinierten Blöcke), damit Implementierung
   und Interpretation reproduzierbar sind.

5. **Multiples Testen über 31 Lags wird korrigiert.**
   Stabilitäts-/Priorisierungssignale je Lag (inkl. ASR/P_sign-basierter
   Scores) erzeugen erneut ein Multiple-Testing-Problem.
   Daher BH-FDR über die 31 Lags, bevor ein Lag als priorisierbar gilt.

6. **Deskriptiv vs. konfirmatorisch bleibt strikt getrennt.**
   Die aktuelle Asymmetrie bleibt hypothesengenerierend. Auswahl/Ranking von
   Kandidaten erfolgt erst in der neuen Pre-Reg unter den obigen Regeln.

---

## 7. Was unverändert bleibt / was nicht folgt

- `docs/BRIDGE_STUFE_A_ERGEBNIS.md` — Verdict `UNSPEZIFISCH`, versiegelt
- 248 Tests, Fenster, Adressen, FDR, plus-one, kein IAAFT
- **Stufe B:** jetzt nicht verfolgen (praktisch blockiert + interpretatorisch
  geschwächt). Nicht logisch tot.
- **Smart-Grid-Plastizität:** eigener Strang, eigene Pre-Reg, nicht diese Studie
- **248-Vektoren:** Datenrettung (gleicher Seed, gleiche Pipeline). Bindendes
  `V2_UNSPEZIFISCH` unberührt. Lag-Kurven der 6 positiven Draws deskriptiv.

---



## 8. Reproduzierbarkeit

```text
python3 scripts/bridge_stufe_a_v2_pipeline.py \
  --bridge-eth bridge_eth.jsonl --bridge-gnosis bridge_gnosis.jsonl \
  --uniswap-eth uniswap_eth.jsonl --uniswap-arb uniswap_arb.jsonl \
  --drivers drivers_90d.jsonl --output bridge_stufe_a_v2_ergebnis.json
```

Seed 20260818, D=21, 1000 Surrogate, getrennte RNGs. Laufzeit dieses Laufs:
19 491 s (~5,4 h). Tests: `python3 scripts/test_bridge_stufe_a_v2.py` (20/20).