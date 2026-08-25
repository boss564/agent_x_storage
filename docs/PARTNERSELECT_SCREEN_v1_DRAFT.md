# Partnerselektiver Zustandsraum — Screening-DRAFT

**Arbeitstitel:** `PARTNERSELECT_SCREEN_v1`  
**Status:** **ABGESCHLOSSEN** — 2026-08-25 · `SCREEN_BINDEND` → Lauf fertig · Label **`NONE_CLOSE`**  
**Charakter:** **Screening** (Zustandsraum-Charakterisierung), **keine** Hypothesentestung  
**Artefakte:** `agents_b2g/emergence/partnerselect_screen_v1/`  

### Bindungs-Vermerk

```text
Status: DRAFT → SCREEN_BINDEND → ABGESCHLOSSEN
Dokument: docs/PARTNERSELECT_SCREEN_v1_DRAFT.md
Datum: 2026-08-25
Outcome: NONE_CLOSE
Kandidaten (≥2/3): (keine)
Near-Miss (≥2/3): checks_failed, honor
Runner: scripts/run_partnerselect_screen_v1.py
Trennregel: bindend — Kandidat nicht im selben Datensatz testen
Abgrenzung: state_screen (NONE_CLOSE) und E_ij (I1_PASS) bleiben gesperrt
Eingefroren: Seeds {20261101,20261102,20261103} · warmup=32 · cycles=512 · κ=0
```

---

## 0. Kontext und Abgrenzung zu versiegelten Serien

### 0.1 Geschlossene Vorgänger (HARKing-Sperre aktiv)

| Artefakt | Status | Relevanz |
|----------|--------|----------|
| Queue-Kopplung | `KOPPLUNG_INVALID` | partnerblinde Größe |
| `KOPPLUNG_REPUTATION_v1` | `I1_FAILED` / `SIGNAL_BLIND` | Sättigung `s(H)`, MAE=0 |
| `state_screen/` (18 Knoten-Dims) | `NONE_CLOSE` · Ausgang 3 | **kein** partnerselektiver Knoten-Zustand im damaligen Lauf |
| `KOPPLUNG_EIJ_v1` | I1_PASS · Sweep `KOPPLUNG_INVALID` | Kante `e_ij` **ist** partnerselektiv; Intervention erfüllt §1.1 nicht |

**Verboten:** Neuanalyse oder Schwellen-Nachjustierung auf
`state_screen/`, `kopplung_full/`, `reputation_i1/`, `eij_i1/`, `eij_sweep/`.

### 0.2 Was dieser DRAFT **nicht** ist

- Keine Interventionsstudie (keine Arme A/B/C, kein κ-Grid, kein Gate B↔C).
- Keine Pre-Reg im vollen Sinn (kein H1/H0-Verdict, kein `KOPPLUNG_*`-Ausgang).
- Kein Retest von `E_ij` (I1-Edge bereits versiegelt).
- Kein Ersatz für den abgeschlossenen Knoten-Screen — aber dessen **Frage** wird
  formalisiert und auf einem **neuen** Lauf wiederholt/erweitert.

### 0.3 Forschungsfrage (eine Ebene tiefer)

> **Enthält der aktuelle Schwarm-Trace eine partnerselektive Zustandsgröße
> (Knoten-Dimension), gemessen mit denselben I1-Kriterien wie in den
> versiegelten Instrumentationschecks?**

Operationalisierung: I1-S (MAE unter Partnerpermutation) und I1-G (|ρ| zum
Schwarm-Mittel) — angewandt auf **alle** exportierten Knoten-Zustandsdimensionen,
nicht auf eine vorab ausgewählte Kopplungsgröße.

---

## 1. Screening-Protokoll

### 1.1 Design

| Parameter | Wert (eingefroren bei `SCREEN_BINDEND`) |
|-----------|----------------------------------------|
| Population | 27 Agenten (9 Provider / 9 Evaluator / 9 Economic) |
| κ | **0** (keine Taktraten-Kopplung) |
| warmup | 32 |
| cycles (Messfenster) | **512** (I1-Fenster der Reputation-/E_ij-Studien; länger als der historische Screen mit 64) |
| Seeds | `{20261101, 20261102, 20261103}` — **neu**, keine Überschneidung mit 20260901 / 20261001… |
| Partnerkarten | Sticky-Map B + degree-preserving Role-Segment-Shuffle C (wie I1) |
| Runner (geplant) | Erweiterung von `scripts/run_emergence_state_screen.py` / `state_space_screen.py` |
| Artefakt-Root | `agents_b2g/emergence/partnerselect_screen_v1/` (+ `/tmp/…` Roh) |

Pro Seed ein Trace; Screening-Aggregation: Dimension gilt als Kandidat nur wenn
**≥ 2 von 3 Seeds** die Kandidaten-Flags setzen (Mehrheit, vorab).

### 1.2 Abgrenzung zur Hypothesentestung

| Screening (dieser DRAFT) | Studie (spätere Pre-Reg) |
|--------------------------|---------------------------|
| Charakterisiert den Zustandsraum | Testet H1 unter Intervention |
| Labels: `SOME_CANDIDATES` / `NONE_CLOSE` / `NONE_CLEAR` | Verdicts: `KOPPLUNG_*` / `SIGNAL_BLIND` |
| Kein κ, keine Arme | κ-Sweep, Arme, Gate |
| Erzeugt **keine** Freigabe zum Sweep | Braucht eigene BINDEND-Pre-Reg |

---

## 2. Kriterien (Schwellen aus I1 — unverändert)

Identisch zu `KOPPLUNG_REPUTATION_v1` §4.2 / Knoten-I1 und zum bestehenden
`state_space_screen.py` (skalierte MAE für dimensionsübergreifenden Vergleich):

| ID | Kriterium | Schwelle | Anmerkung |
|----|-----------|----------|-----------|
| **S-V** | Stichproben-σ der Dimension über Agenten am Fensterende | `σ > 0` (Screening: strikte Positivität; Honor-I1 nutzte σ≥10 nur für H) | rein deskriptiv gegen totale Konstanz |
| **S-S** | Partnerselektivität: Mittel über Sticky-Kanten von `MAE_t` auf **Min-Max-skaliertem** Panel | `≥ 0.05` | wie I1-S |
| **S-G** | Nicht-Globalität: Median über i von `|corr_t(x_i(t), x̄(t))|` | `≤ 0.90` | wie I1-G; <14 corr-fähige Agenten → S-G Fail |
| **S-dyn** | Nicht-statisch im Fenster: `max_i (max_t x − min_t x) > 0` | Pflicht | Konfig-Konstanten sind keine Signale |

**Kandidat (pro Seed):** S-dyn ∧ S-V ∧ S-S ∧ S-G.  
**Kandidat (Studie):** Mehrheit der Seeds (≥2/3).

Keine Schwellen-Senkung nach Datenblick. Keine Transformation (`s(·)`, z-Score, Rang)
**innerhalb** dieses Screens — Transformationen erfordern einen **neuen** DRAFT
(wie Honor/`H_cap`-Lehre).

---

## 3. Dimensionsliste (Knoten — vollständig aus Trace)

Zu prüfen sind **alle** Keys in `SwarmTrace.state_keys` / Adapter-State-Matrix zum
Zeitpunkt von `SCREEN_BINDEND`. Inventarliste (Stand Adapter nach Emergence-Serie;
bei Abweichung: Trace-Export entscheidet, Liste hier nachziehen):

| # | Dimension | Klasse (erwartet) |
|---|-----------|-------------------|
| 1 | `inbox_len` | dynamisch (Queue) |
| 2 | `honor` | dynamisch (Reputation roh) |
| 3 | `s_honor` | abgeleitet / ggf. gesättigt |
| 4 | `phase` | oft konfig-/init-statisch im Fenster |
| 5 | `risk_factor` | konfig |
| 6 | `decision_bias` | konfig |
| 7 | `amount_multiplier` | konfig |
| 8 | `strictness` | konfig |
| 9 | `failure_count` | Zähler |
| 10 | `checks_performed` | Zähler |
| 11 | `checks_passed` | Zähler |
| 12 | `checks_failed` | Zähler |
| 13 | `settlements` | Zähler |
| 14 | `total_fee_burned` | kumuliert |
| 15 | `total_volume` | kumuliert |
| 16 | `total_reported` | kumuliert |
| 17 | `milestone_count` | Zähler |
| 18 | `tick_count` | Takt |

**Explizit außerhalb dieses Screens (bereits charakterisiert / andere Schicht):**

| Größe | Grund |
|-------|--------|
| `e_ij` / Edge-Tensor | I1-Edge in `KOPPLUNG_EIJ_v1` versiegelt (`I1_PASS`) — kein Retest |
| Queue als Interventionsgröße | Studie geschlossen |
| Honor als Interventionsgröße | I1_FAILED versiegelt |

Wenn der Trace **neue** Keys exportiert, die hier fehlen: append-only in §3
nachtragen **vor** `SCREEN_BINDEND`, nicht nach dem Lauf.

---

## 4. Trennregel (bindend)

1. Ein in diesem Screen gefundener Kandidat darf **nicht** auf demselben Trace /
   denselben Seeds als Interventions-Hypothese (κ-Sweep, Arme) getestet werden.
2. Folgetest = **neue** Pre-Reg (`DRAFT → BINDEND`) + **neue** Seeds + neue Läufe.
3. Schwellen, Dimensionsliste und Aggregation (≥2/3) werden bei `SCREEN_BINDEND`
   eingefroren; Nachjustierung nach Blick auf Artefakte = HARKing.
4. Versiegelte Alt-Artefakte (`state_screen/`, …) bleiben gesperrt — auch wenn
   Zahlen „ähnlich“ aussehen.

---

## 5. Ausgangs-Klassifikation

| Label | Definition | Konsequenz |
|-------|------------|------------|
| **`SOME_CANDIDATES`** | ≥1 Dimension ist Kandidat in ≥2/3 Seeds | Neue Pre-Reg erlaubt, mit dieser Dimension als **vorab** belegter I1-Vorbedingung; neuer Datensatz Pflicht |
| **`NONE_CLOSE`** | Kein Kandidat, aber ≥1 Dimension nahe an S-S oder S-G (MAE_scaled ∈ [0.03, 0.05) oder \|ρ\| ∈ (0.90, 0.95]) in ≥2/3 Seeds | Hinweis auf Transformations-/Skalenproblem — **nur** neuer DRAFT für Transformation, kein Nachziehen hier |
| **`NONE_CLEAR`** | Kein Kandidat und keine Near-Miss-Dimension nach obiger Bandbreite | Stärkster Architektur-Befund: im knotenbasierten Trace keine partnerselektive Größe unter I1-Kriterien → relationale Größe muss **gebaut** werden (Kanten-Ledger o.ä.), nicht „eingestellt“; begründet, nicht vermutet |

**Hinweis zur Serie:** `NONE_CLEAR` auf dem **neuen** längeren Fenster wäre eine
Bestätigung des historischen `NONE_CLOSE` (cycles=64) unter härteren Laufparametern.
Das widerspricht nicht `E_ij`-I1_PASS: Partnerselektivität kann auf der **Kante**
liegen, während der **Knoten**-Zustand leer bleibt — genau die architektonische
Trennung Execution / Routing(`E_ij`) / Verification.

---

## 6. Lieferobjekte

Nach Lauf (nur bei `SCREEN_BINDEND`):

- `PARTNERSELECT_SCREEN_v1.json` — je Seed × Dimension Flags + Kennzahlen  
- `PARTNERSELECT_SCREEN_v1.md` — Tabelle + Label  
- `SCREENING_ABSCHLUSS.md` — Label, HARKing-Vermerk, Verweis auf diesen DRAFT  
- SHA256SUMS der JSON/MD  

---

## 7. Freigabe

| Stufe | Bedeutung |
|-------|-----------|
| **DRAFT** | Protokoll formuliert; **kein** Lauf |
| **`SCREEN_BINDEND`** | Seeds/Fenster/Liste eingefroren; Lauf freigegeben — **erreicht 2026-08-25** |
| Abgeschlossen | Label gesetzt; Artefakte versiegelt; Folgestudie nur neue Pre-Reg |

**Nächster Schritt:** Runner `scripts/run_partnerselect_screen_v1.py` ausführen; Artefakte unter
`agents_b2g/emergence/partnerselect_screen_v1/`.

---

## 8. Checkliste DRAFT

| Anforderung | Status |
|-------------|--------|
| Screening vs. Hypothesentest abgegrenzt | ✅ §0.2, §1.2 |
| MAE + \|ρ\| mit I1-Schwellen | ✅ §2 |
| Alle Knoten-Dimensionen gelistet | ✅ §3 |
| Trennregel / kein Same-Dataset-Test | ✅ §4 |
| Drei Ausgänge + Konsequenzen | ✅ §5 |
| HARKing-Sperre Alt-Artefakte | ✅ §0.1 |
| Edge `e_ij` nicht retetet | ✅ §0.2, §3 |
