# Stateful Graph Automata — Arbeitsprotokoll (**BINDEND**)

**Arbeitstitel:** `STATEFUL_GRAPH_v0`  
**Status:** **BINDEND** — 2026-08-26 · Sweep freigegeben  
**Kanonisches Pre-Reg:** `docs/STATEFUL_GRAPH_v0_PREREG.md`  
**Charakter:** Interventionsstudie (Dreiarm A/B/C) — **Serie 1 einer neuen Frage**  
**Nicht:** Studie 11 der φ/ρ-Kopplungsfamilie  
**Vorläufer-Familie:** `docs/KOPPLUNG_SERIE_ABSCHLUSS.md` — **FAMILIE GESCHLOSSEN** (10 Studien)  
**Proto:** `prototypes/v2_stateful_graph/` · Gate `PROTO_PASS` (3/3 · 0.01s / 16s)  
**Capture / Runner:** `prototypes/v2_stateful_graph/`  
**Artefakte:** `prototypes/v2_stateful_graph/runs/stateful_graph_v0/`

### Freigabe-Vermerk

```text
Status: PROTO_PASS → DRAFT → BINDEND
Strang: Stateful Graph (Serie 1) · nicht Kopplungsstudie 11
Mechanik: diskrete Repulsion · q ∈ Q
Metrik: ΔQ · H_Kante · Arm-C-Bruch
Sandbox: prototypes/v2_stateful_graph/
Transfer: verboten (keine Kopplungs-Runner / keine φ·ρ-Batterie)
Seeds: Sweep 20270201–06 · Spot 20270201 · Proto 20270101–03 gesperrt
Schwellen: ΔQ ≥ 0,5 · H_Kante ≥ 2,0 bit (Paare) · Margin ≥ 0,15
Dokument: docs/STATEFUL_GRAPH_v0_PREREG.md
```

### HARKing-Sperre (strikt)

Nicht für Hypothesentests / Gate-Auswertung dieser Studie verwenden:

- Gesamte φ/ρ-Kopplungsfamilie (Tick 1–7 · Event 8–9 · Reciprocity-Amp 10)  
- Alle Artefakte unter `agents_b2g/emergence/*kopplung*`  
- Proto-Seeds `20270101–03` und Gate-Zahlen des Screens  
- Alle Seeds ≤ `20270199` für Sweep-/Gate-Zellen  

Neue Seeds · neue Läufe · neue Artefakte unter `prototypes/v2_stateful_graph/runs/`.

### Abgrenzung

| Strang | Status | Was er misst |
|--------|--------|--------------|
| φ/ρ-Kopplung (10 Studien) | **versiegelt** | Kohärenz / Korrelation / κ |
| Dissensus (Option A) | nicht gestartet | kontinuierliches \|S_i−S_j\| |
| **dieser DRAFT** | offen | Zustandsübergänge · Kantenentropie · relationale Repulsion |

Kein Hybrid mit φ/ρ. Kein Import von Kopplungs-Capture/Runnern.
Delivery-Topologie bleibt Sticky-Ring M; nur der **Signal-Partner** unterscheidet Arme.

---

## 0. Zweck

### 0.1 Freeze-Fakten (Engineering → Architektur)

| Fakt | Wert / Quelle | Rolle |
|------|---------------|-------|
| Proto-Gate | `PROTO_PASS` 3/3 · ΔQ∈{1.23…1.30} · H∈{2.98…2.99} · anti B=1.0 / C≈0.5 | **F0** |
| Zustandsraum | \(Q=\{0,1,2,3\}\) · \(\lvert Q\rvert=4\) | **F1** |
| Repulsionsregel | \(q' = (\sigma + 1 + (q \bmod 2)) \bmod \lvert Q\rvert\) | **F2** |
| H_Kante | Shannon **über Paare** \((q_i,\,q_{j^*})\) auf true Sticky-Kante · Einheit **Bit** (\(\log_2\)) · \(H_{\max}=\log_2(\lvert Q\rvert^2)=4\) | **F3** |
| ε_H | **\(H_{\mathrm{Kante}} \ge 2{,}0\)** (50 % von \(H_{\max}\); Proto ≈2,98) | **F3b** |
| ΔQ-Floor | **\(\Delta Q \ge 0{,}5\)** (Proto 1,2–1,3; nicht `>0`) | **F3c** |
| Arm-C-Margin | **0.15** | **F4** |
| N · Warmup · Measure | N=9 · **Warmup=32** Events/Agent verwerfen · **Measure=80** Events/Agent | **F5** |
| Sticky M | Ring \(i \mapsto i{+}1 \bmod N\) | **F6** |
| π(M) | seed-abhängige Partnerpermutation (crc32) | **F7** |
| Anti-Alignment | \(q_i \in \{q_j{+}1,\,q_j{+}2\} \bmod \lvert Q\rvert\) vs. **true** Partner | **F8** |
| Sandbox-Disziplin | nur `prototypes/v2_stateful_graph/` · kein Kopplungs-Transfer | **F9** |
| Arm-A-σ | **eigene Zufallsziehung** je Event: \(\sigma \sim \mathrm{crc32}\) in \(Q\), **nicht** \(\sigma=q_i\) | **F10** |

**Verboten nach Freeze:** Änderung von F1–F5 / F8 / F10 / Schwellen F3b–F3c / F4 ohne neuen Proto-Screen.
Zahlen nicht nach Sweep-Datenblick senken.

**Begründung Schwellen (Muster `r_floor`):** Proto-Effekt ist die Referenz, nicht die Nullinie.
`ΔQ > 0` und `H > 0{,}15` wären dekorativ; Floor und ε_H liegen unter dem Proto-Band, aber über Totalsystemen.

### 0.2 Forschungsfrage

Erzeugt **diskrete Repulsion** auf Sticky-Kanten
(Signal = Partnerzustand → Automaten-Übergang in \(Q\))
eine **relationale Zustandsstruktur**
(\(\Delta Q \ge 0{,}5\) · \(H_{\mathrm{Kante}} \ge 2{,}0\,\mathrm{bit}\) · Arm-C-Bruch),
die unter Partnerpermutation π(M) bricht —
**ohne** φ/ρ-Kohärenz und ohne Kopplungs-κ?

### 0.3 Vorbedingung (bindend, per Seed) — Metrik-Triade auf Arm B

Messfenster: **nach Warmup** (F5) — nur Measure-Events zählen für ΔQ / H / anti.

| Schicht | Definition | Schwelle |
|---------|------------|----------|
| **ΔQ** | mittlere paarweise L1-Distanz der Zustandstrajektorien (Arm B, Measure) | \(\ge 0{,}5\) |
| **H_Kante** | Shannon-Entropie der Paare \((q_i,\,q_{j^*})\) auf **true** Sticky-Kante · **Bit** (Arm B, Measure) | \(\ge 2{,}0\) |
| **Arm-C-Bruch** | \(\mathrm{anti}_B - \mathrm{anti}_C \ge 0{,}15\) (Anti vs. true Partner, Measure) | Margin **F4** |

Sonst → `STRUCTURE_LOST` (Seed zählt nicht für Mehrheit / H1).

**Berichtspflicht (kein zusätzliches Gate-Label):** Rohwerte `anti_A`, `anti_B`, `anti_C`, `ΔQ`, `H_Kante` je Seed.

---

## 1. Hypothesen

**H1:** Auf ≥4/6 Sweep-Seeds gilt die Metrik-Triade (§0.3) —
relationale Repulsion auf echten Kanten, Bruch unter π(M).

**H0:** Mehrheit der Seeds verliert die Triade (`STRUCTURE_LOST` / kein Arm-C-Bruch).

### 1.1 Replikations-Vorhersage (§1.1) — Übertragbarkeit, nicht Proto-Risiko

Im Proto war der Arm-C-Bruch (anti_B = 1,0 vs. anti_C ≈ 0,5 bei Margin 0,15) bereits gemessen —
dort war die Vorhersage **riskant**. Hier sind Proto-Seeds gesperrt (`20270101–03`);
§1.1 prüft **Replikation auf frischen Seeds** (`20270201–06`):

**Arm-C-Bruch hält auf ≥4/6 Sweep-Seeds**
(\(\mathrm{anti}_B - \mathrm{anti}_C \ge 0{,}15\)).

Scheitert die Replikation (Bruch mehrheitlich weg), ist die relationale Struktur
**nicht übertragbar** → Verdict `RELATION_INVALID`.

### 1.2 Was diese Studie bewusst nicht fragt

- Keine Kuramoto-φ, kein ordinal-ρ, kein `r_floor`, kein κ-Raster  
- Keine Dissensus-Dynamik (\(\lvert S_i-S_j\rvert\)) — Option A bleibt separat  
- Kein Claim über Emergenz „im Sinne der Kopplungsserie“

---

## 2. Design

### 2.1 Dynamik — Freeze F0–F10

**Zustand:** jeder Agent \(i\) hält \(q_i \in Q\), \(|Q|=4\).

**Event-Uhr:** agent-privates Gap-Heap (crc32) — **kein** Tick-EWMA.

**Übergang (bei Event von Agent \(i\)):**

```text
# Arm A — Baseline: eigene Zufallsziehung (F10), kein Partner-Read
#   σ = floor(crc32(seed|aid|k|sigma) * |Q|) % |Q|
#   NICHT σ = q[i]  → das erzwänge 2-Zyklus 1↔3 und wäre keine Baseline
#
# Arm B/C — Signal vom signal_partner
sig = signal_partner[i]     # B: M · C: π(M)
σ   = q[sig]                # B/C only
q[i] ← (σ + 1 + (q[i] mod 2)) mod |Q|
# Metriken immer gegen TRUE sticky partner j* = M[i]
# Warmup: erste 32 Events/Agent verwerfen; Measure: folgende 80
```

| Freeze | Inhalt |
|--------|--------|
| **F0** | Proto `PROTO_PASS` |
| **F1** | \(\lvert Q\rvert = 4\) |
| **F2** | Repulsionsregel wie oben |
| **F3** | H = Shannon **Paare** · **Bit** · \(H_{\max}=4\) |
| **F3b** | \(H \ge 2{,}0\) |
| **F3c** | \(\Delta Q \ge 0{,}5\) |
| **F4** | Arm-C-Margin \(= 0{,}15\) |
| **F5** | N=9 · Warmup=**32** · Measure=**80** |
| **F6** | Sticky Ring M |
| **F7** | π(M) seed-abhängig |
| **F8** | Anti vs. **true** Partner |
| **F9** | Sandbox-only · kein Kopplungs-Transfer |
| **F10** | Arm A: σ = crc-Zufall in \(Q\), nicht \(q_i\) |

**Verboten:** φ/ρ-Batterie · κ-Inter-Arrival · Amplitude-Kopplung · Import aus `agents_b2g/emergence/` · Arm-A mit \(\sigma=q_i\).

### 2.2 Arme

| Arm | Signal-Partner | σ-Quelle | Rolle |
|-----|----------------|----------|-------|
| **A** | keiner | **F10:** crc-Zufallsziehung in \(Q\) je Event | Baseline — keine Kanten-Information |
| **B** | echte Sticky-Zuordnung M | \(q\) des true Partners | Intervention — echte Kante |
| **C** | π(M) | \(q\) des permutierten Partners | Kontrolle — Metrik vs. true M |

Delivery-Topologie M ist in allen Armen gleich (Ring); nur die **σ-Quelle** ändert sich.

### 2.3 Parameter und Seeds

| Parameter | Wert |
|-----------|------|
| Sweep-Seeds | `{20270201 … 20270206}` |
| Spot | `20270201` |
| Gesperrt | ≤ `20270199` (inkl. Proto `20270101–03`) |
| Warmup | **32** Events/Agent verwerfen |
| Measure | **80** Events/Agent |

### 2.4 Spot-Checks (nach BINDEND, vor Sweep)

| Check | Seed | Erwartung | Fail-Label |
|-------|------|-----------|------------|
| Triade Arm B | `20270201` | ΔQ≥0,5 ∧ H≥2,0 ∧ Arm-C-Bruch | `SIGNAL_BLIND` |
| Arm-A-Kontrast | `20270201` | `anti_A` berichtbar; kein 2-Zyklus-Artefakt (F10) | Dokumentation |
| Sandbox-Import | CI/lokal | kein Import aus Kopplungs-Runnern | `CONTAMINATION` |

---

## 3. Schwellen und Gate

**Zahlen nicht nach Daten senken:**

| Regel | Wert |
|-------|------|
| ΔQ | \(\ge 0{,}5\) |
| H_Kante | \(\ge 2{,}0\) bit (Paare, F3) |
| Arm-C-Bruch | \(\mathrm{anti}_B - \mathrm{anti}_C \ge 0{,}15\) |
| Mehrheit | ≥ **4/6** Seeds mit voller Triade |
| §1.1 | Arm-C-Bruch ≥4/6 (**Replikation** auf frischen Seeds) |

Primär-Gate einer Zelle = Metrik-Triade (§0.3).  
Studien-Verdict = Mehrheit über Sweep-Seeds (§4).

---

## 4. Verdict-Labels

| Label | Bedeutung |
|-------|-----------|
| `SIGNAL_BLIND` | Spot: Triade scheitert |
| `STRUCTURE_LOST` | Seed verliert ΔQ-Floor / H / Bruch |
| `RELATION_INVALID` | §1.1: Arm-C-Bruch mehrheitlich fehlend (Replikation scheitert) |
| `NO_STRUCTURE` | Triade auf keinem ≥4/6 Seed |
| `STRUCTURE_RELATIONAL` | Triade ≥4/6 · §1.1 gehalten |
| `CONTAMINATION` | Kopplungs-Import / Seed-Leck — sichtbares Verdict, kein stiller Confound |

---

## 5. Ablauf

1. ~~16s-Proto~~ **`PROTO_PASS`** (2026-08-26) · 3/3 · 0.01s  
2. **DRAFT** (dieses Dokument) — User → BINDEND  
3. Capture + Runner **in** `prototypes/v2_stateful_graph/` (F0–F10)  
4. Spot Seed `20270201`  
5. Sweep A/B/C × Seeds `20270201–06`  
6. Freeze Artefakte — keine Schwellen-Nachjustierung nach Datenblick  
7. Pre-Reg-Datei nur nach BINDEND spiegeln (`STATEFUL_GRAPH_v0_PREREG.md`)

## 6. Freigabe

| Stufe | Bedeutung |
|-------|-----------|
| **PROTO_PASS** | erreicht (2026-08-26) |
| **DRAFT** | erreicht |
| **BINDEND** | **erteilt 2026-08-26** |
| **Sweep** | freigegeben nach Spot PASS |


---

## 7. Checkliste vor BINDEND

| Anforderung | Status |
|-------------|--------|
| Frage: diskrete Repulsion → relationale Struktur + Arm-C-Bruch? | ✅ §0.2 |
| Neue Familie · φ/ρ versiegelt · kein Transfer | ✅ Kopf · F9 |
| H1 / H0 / §1.1 als Replikation | ✅ §1 |
| Triade: ΔQ≥0,5 ∧ H≥2,0 bit (Paare) ∧ Margin 0,15 | ✅ §0.3 · §3 |
| Freeze F0–F10 inkl. Arm-A-σ und Warmup=32 | ✅ §0.1 · §2.1 |
| Arme A/B/C · Signal M vs π(M) · Metrik vs true | ✅ §2.2 |
| Seeds `20270201–06` · Proto gesperrt | ✅ §2.3 |
| `CONTAMINATION` als Verdict | ✅ §4 |
| HARKing | ✅ Kopf |
| **BINDEND** | ✅ 2026-08-26 |

---

## 8. Änderungsprotokoll

| Datum | Änderung |
|-------|----------|
| 2026-08-26 | DRAFT v0-Skizze nach `PROTO_PASS` (Chat; Datei übersprungen) |
| 2026-08-26 | **DRAFT v0 Datei:** ΔQ≥0,5 · H≥2,0 bit Paare · Arm-A F10 crc-σ · Warmup=32 · §1.1 = Replikation |
| 2026-08-26 | **BINDEND** · Pre-Reg · Sweep Seeds `20270201–06` (nicht Proto `202701xx`) |
| 2026-08-26 | **BINDEND** · Pre-Reg · Sweep Seeds bleiben `20270201–06` (nicht Proto `202701xx`) |
