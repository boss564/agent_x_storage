# Stateful Graph — Serie v0 (Konsolidierung)

**Status:** Studie 1 BINDEND · Gegenprobe Screen `PROTO_PASS` · \|Q\|-Varianz Screen 24/24 · 2026-08-26  
**Charakter:** Neue Architekturfamilie — **nicht** Studie 11 der φ/ρ-Kopplung  
**Sandbox diskret:** `prototypes/v2_stateful_graph/`  
**Sandbox Dissensus:** `prototypes/v3_continuous_dissensus/` · **kein** Runner-Transfer

```text
Kopplungsfamilie:     FAMILIE GESCHLOSSEN (10 Studien) — Kohärenz nicht relational
Stateful Graph v0:    STRUCTURE_RELATIONAL (diskret, |Q|=4) — Sweep 6/6
Dissens-Gegenprobe:   PROTO_PASS (kontinuierlich, matched gate) — kein Pre-Reg
|Q|-Varianz-Screen:   STRUCTURE_RELATIONAL für alle |Q| ∈ {4, 8, 16, 32} — 24/24
```

---

## Frage der Serie

Erzeugt **diskrete Repulsion** auf Sticky-Kanten
(\(q \in Q\), Signal = Partnerzustand → Automaten-Übergang)
eine **relationale Zustandsstruktur**
(\(\Delta Q\), \(H_{\mathrm{Kante}}\), Arm-C-Bruch),
die unter Partnerpermutation bricht — ohne φ/ρ und ohne κ?

**Erweiterung (Gegenprobe):** Gilt dieselbe relationale Trennung
(Anti vs. **true** Partner) auch unter kontinuierlicher Repulsion
\(S_i \mathrel{+}= \alpha(S_i-S_j)\) (tanh-begrenzt)?

## Antwort (Studie 1 — diskret)

**Ja — Sweep `20270201–06`, Verdict `STRUCTURE_RELATIONAL`.**

| Metrik | Schwelle | Sweep |
|--------|----------|-------|
| ΔQ | ≥ 0,5 | 1,23 – 1,28 · 6/6 |
| H_Kante (Paare, Bit) | ≥ 2,0 · \(H_{\max}=4\) | 2,97 – 3,00 · 6/6 |
| Margin B↔C (anti true) | ≥ 0,15 | 0,46 – 0,57 · 6/6 |
| Verdict | — | **`STRUCTURE_RELATIONAL`** |

## Antwort (Gegenprobe — kontinuierlich, Screen only)

**Proto-PASS unter matched Gate** (Anti vs. true Partner · 3/3 Seeds `20270301–03`).

| Ebene | Befund |
|-------|--------|
| Primary (relational) | Margin true 0,20–0,39 · **PASS** |
| Secondary (global) | anti≈0,53–0,56 · B≈C — **kein** Gate |

Früherer `PROTO_FAIL`-Bericht war Metrikfehler (global statt relational).
Korrigiert: Dual-Metrik in `prototypes/v3_continuous_dissensus/ANALYSIS.md`.

**Kein Pre-Reg / kein Sweep** für Dissensus in diesem Stand — nur Screen.

---

## Antwort (|Q|-Varianz — Screen only)

**Frage:** Bleibt die relationale Trennung (Arm B vs. π) stabil, wenn \|Q\| wächst?

**Mechanik:** BINDEND-Runner (`stateful_graph_study.py`), nur `N_STATES` ∈ {4, 8, 16, 32}.  
**Seeds:** `20270401–06` (frisch; Studie-1-Seeds gesperrt).  
**Screen-Gate:** ΔQ ≥ 0,5 ∧ H ≥ 2,0 ∧ Margin > 0,1 (BINDEND-Margin 0,15 separat berichtbar).

| \|Q\| | Passes | Avg Margin | Avg H_B | H_max | Verdict |
|------|--------|------------|---------|-------|---------|
| 4 | 6/6 | 0,51 | 2,99 | 4 | `STRUCTURE_RELATIONAL` |
| 8 | 6/6 | 0,78 | 3,98 | 6 | `STRUCTURE_RELATIONAL` |
| 16 | 6/6 | 0,89 | 4,96 | 8 | `STRUCTURE_RELATIONAL` |
| 32 | 6/6 | 0,93 | 5,92 | 10 | `STRUCTURE_RELATIONAL` |

**Befund:** Trennung bricht **nicht** — Margin steigt mit \|Q\| (mehr Differenzierung).  
Artefakte: `prototypes/v2_stateful_graph/q_variance_screen.py` · `q_variance_results.json`.  
**Kein Pre-Reg** — Screen-Erweiterung der Serie.

---

## Abgrenzung zur Kopplungsfamilie

| Serie | Was gemessen wird | Status |
|-------|-------------------|--------|
| φ/ρ-Kopplung (10) | Kohärenz / κ | versiegelt |
| Stateful Graph diskret (1) | Zustandsübergänge · H_Kante · \|Q\|=4 | `STRUCTURE_RELATIONAL` |
| Dissensus-Gegenprobe | kontinuierliche Repulsion · anti true | `PROTO_PASS` Screen |
| \|Q\|-Varianz | dieselbe Mechanik · \|Q\| ∈ {4…32} | `STRUCTURE_RELATIONAL` 24/24 Screen |

---

## Studie 1 — Freeze (kurz)

| ID | Inhalt |
|----|--------|
| F1–F2 | \|Q\|=4 · Repulsionsregel mod \|Q\| |
| F3b/c | H ≥ 2,0 bit · ΔQ ≥ 0,5 |
| F4 | Arm-C-Margin ≥ 0,15 |
| F5 | Warmup=32 · Measure=80 |
| F10 | Arm A: σ = crc-Zufall |
| Seeds | Sweep `20270201–06` |

## Gegenprobe — Screen-Freeze

| Fakt | Wert |
|------|------|
| Update | \(S \leftarrow b\tanh((S+\alpha(S-S_{\mathrm{sig}}))/b)\) · sync |
| v1 | unbounded → DIVERGENCE |
| Gate | ΔS ≥ 0,5 ∧ anti_true Margin ≥ 0,15 |
| Seeds | `20270301–03` |
| Pre-Reg | **gesperrt** bis User-Freigabe |

---

## Methodische Lehre (Dual-Metrik)

Globale Paarstatistik kann B und C „identisch“ erscheinen lassen und ein
falsches Negativ erzeugen. Die relationale Frage ist Anti vs. **true** Partner —
dieselbe Definition wie in Studie 1. **Wahrheit vor Optik.**

---

## Status & offene Türen

**Jetzt:** Studie 1 · Dissensus-Screen · \|Q\|-Varianz-Screen (24/24) — **kein** Dissensus-Pre-Reg.

**Optional später:** Dissensus DRAFT/Pre-Reg/Sweep · **Topologie** (vollständig / spärlich / skalenfrei).

**Nicht erlaubt:** Studie 11 φ/ρ · Hybrid · Schwellen-Nachjustierung an versiegelten Artefakten · Strang-Negativ aus globaler Metrik.

---

## Verweise

| Dokument | Rolle |
|----------|-------|
| `docs/KOPPLUNG_SERIE_ABSCHLUSS.md` | φ/ρ versiegelt |
| `docs/STATEFUL_GRAPH_v0_DRAFT.md` / `_PREREG.md` | Studie 1 |
| `prototypes/v2_stateful_graph/` | diskret Sweep + \|Q\|-Varianz-Screen |
| `prototypes/v3_continuous_dissensus/` | Dissensus Screen + Dual-Metrik |
