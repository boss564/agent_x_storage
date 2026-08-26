# Stateful Graph — Serie v0 (Konsolidierung)

**Status:** Studie 1 · Gegenprobe · \|Q\|-Varianz · \|Q\|=2-Grenze · completion_proof · wall_clock_verify · 2026-08-26  
**Charakter:** Neue Architekturfamilie — **nicht** Studie 11 der φ/ρ-Kopplung  
**Sandbox diskret:** `prototypes/v2_stateful_graph/`  
**Sandbox Dissensus:** `prototypes/v3_continuous_dissensus/` · **kein** Runner-Transfer

```text
Kopplungsfamilie:     FAMILIE GESCHLOSSEN (10 Studien) — Kohärenz nicht relational
Stateful Graph v0:    STRUCTURE_RELATIONAL (diskret, |Q|=4) — Sweep 6/6
Dissens-Gegenprobe:   PROTO_PASS (kontinuierlich, matched gate) — kein Pre-Reg
|Q|-Varianz-Screen:   STRUCTURE_RELATIONAL für |Q| ∈ {4, 8, 16, 32} — 24/24
|Q|=2 Grenzfall:      STRUCTURE_BREAKS — 0/6 · untere Leistungsgrenze |Q|=4
completion_proof:     STRUCTURE_RELATIONAL unter Receipt-Gate — 18/18 (baseline/always/lossy)
wall_clock_verify:    HYPOTHESIS_CONFIRMED — Struktur stabil · ms↑ mit |Q| · tps↓
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

**Befund:** Trennung bricht **nicht** für \|Q\|≥4 — Margin steigt mit \|Q\|.  
Artefakte: `prototypes/v2_stateful_graph/q_variance_screen.py` · `q_variance_results.json`.  
**Kein Pre-Reg** — Screen-Erweiterung der Serie.

---

## Antwort (|Q|=2 Grenzfall — Screen only)

**Frage:** Bricht die relationale Trennung am minimalen Zustandsraum?

**Mechanik:** dieselbe BINDEND-Pipeline · nur `N_STATES=2`.  
**Seeds:** `20270501–06` · Gate wie Varianz-Screen (Margin > 0,1).  
**H_max:** \(\log_2(2^2)=2{,}0\) bit — Gate H≥2 verlangt Sättigung.

| Metrik | Sweep | Lesart |
|--------|-------|--------|
| ΔQ | ≈ 0,49–0,53 | Bewegung ja, nicht relational |
| H_Kante | ≈ 1,98–2,00 | an der Decke |
| anti_B / anti_C | 1,0 / 1,0 | identisch |
| Margin | **0,000** | keine B↔C-Diskrimination |
| Passes | **0/6** | — |
| Verdict | **`STRUCTURE_BREAKS`** | Hypothese bestätigt |

**Vollbild:**

| \|Q\| | Avg Margin | Verdict |
|------|------------|---------|
| **2** | **0,00** | **`STRUCTURE_BREAKS`** ← Grenze |
| 4 | 0,51 | `STRUCTURE_RELATIONAL` |
| 8 | 0,78 | `STRUCTURE_RELATIONAL` |
| 16 | 0,89 | `STRUCTURE_RELATIONAL` |
| 32 | 0,93 | `STRUCTURE_RELATIONAL` |

**Untere Leistungsgrenze: \|Q\|=4.** Darunter (hier \|Q\|=2) ist Partnerpermutation
nicht mehr diskriminierbar (`anti_B=anti_C`).  
Artefakte: `q2_boundary_screen.py` · `q2_boundary_results.json`.

---

## Abgrenzung zur Kopplungsfamilie

| Serie | Was gemessen wird | Status |
|-------|-------------------|--------|
| φ/ρ-Kopplung (10) | Kohärenz / κ | versiegelt |
| Stateful Graph diskret (1) | Zustandsübergänge · H_Kante · \|Q\|=4 | `STRUCTURE_RELATIONAL` |
| Dissensus-Gegenprobe | kontinuierliche Repulsion · anti true | `PROTO_PASS` Screen |
| \|Q\|-Varianz | dieselbe Mechanik · \|Q\| ∈ {4…32} | `STRUCTURE_RELATIONAL` 24/24 Screen |
| \|Q\|=2 Grenzfall | dieselbe Mechanik · \|Q\|=2 | `STRUCTURE_BREAKS` 0/6 Screen |
| completion_proof | Übergangs-Receipt (Mock-Z3/BHO) · \|Q\|=4 | `STRUCTURE_RELATIONAL` 18/18 Screen |
| wall_clock_verify | Verifikations-Wandzeit · \|Q\| ∈ {4…32} | `HYPOTHESIS_CONFIRMED` Screen |

---

## Antwort (completion_proof — Screen only)

**Frage:** Bleibt die relationale Trennung, wenn \(q\to q'\) einen deterministisch
verifizierbaren Nachweis braucht (`completion_proof` — **kein** kryptographisches PoW)?

**Seeds:** `20270601–06` · Gate wie Varianz-Screen · \|Q\|=4.

| Mode | Passes | Avg Margin | Brake | Verdict |
|------|--------|------------|-------|---------|
| baseline | 6/6 | 0,495 | 0 | `STRUCTURE_RELATIONAL` |
| always | 6/6 | 0,495 | 0 | `STRUCTURE_RELATIONAL` |
| lossy (~28%) | 6/6 | 0,431 | ≈0,28 | `STRUCTURE_RELATIONAL` |

**Hypothese: bestätigt.**  
`always ≡ baseline` bei den **Zustandsmetriken** — der always-Receipt lehnt nie ab
(kein Zustands-Bremsen); Wandzeit-Overhead der Verifikation ist **nicht** die Messgröße.
`lossy` bremst ~28% der Übergänge, Margin bleibt >0,4.  
Artefakte: `completion_proof_screen.py` · `completion_proof_results.json` · `COMPLETION_PROOF_PROTO.md`.

---

## Antwort (wall_clock_verify — Screen only)

**Frage:** Skaliert die Verifikations-Wandzeit (Mock-Z3/BHO über \(Q\times Q\)) mit \|Q\|,
während die relationale Struktur stabil bleibt?

**Freeze:** Seeds `20270701–06` · \|Q\| ∈ {4,8,16,32} · Work \(O(|Q|^2\times\mathrm{INNER})\),
\(\mathrm{INNER}=64\) (CPU, kein sleep) · Struktur = BINDEND-Zelle · Timing = 64 Samples/Zelle.

| \|Q\| | Passes | Avg Margin | mean ms/txn | tps | Verdict |
|------|--------|------------|-------------|-----|---------|
| 4 | 6/6 | 0,51 | **0,29** | ≈3425 | `STRUCTURE_RELATIONAL` |
| 8 | 6/6 | 0,79 | 1,16 | ≈862 | `STRUCTURE_RELATIONAL` |
| 16 | 6/6 | 0,91 | 4,72 | ≈212 | `STRUCTURE_RELATIONAL` |
| 32 | 6/6 | 0,92 | **19,0** | ≈53 | `STRUCTURE_RELATIONAL` |

**Hypothese: bestätigt** (`HYPOTHESIS_CONFIRMED`):
Struktur all \|Q\| relational · mean_ms(4)<1 · mean_ms(32)>10 · ms monoton steigend · tps fallend.  
Kein Live-HTTP zu `infra-z3` — Mock-Constraint-Matrix als Performance-Proxy.  
Artefakte: `wall_clock_verify_screen.py` · `wall_clock_verify_results.json`.

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

**Jetzt:** Studie 1 · Dissensus · \|Q\|-Varianz · \|Q\|=2-Grenze · completion_proof (18/18) · wall_clock_verify (CONFIRMED).

**Optional später:** Dissensus DRAFT/Pre-Reg/Sweep · Topologie · Failover `completion_load` / `two-choice tie-break` · Live-Z3-Wandzeit gegen `infra-z3`.

**Nicht erlaubt:** Studie 11 φ/ρ · Hybrid · Schwellen-Nachjustierung an versiegelten Artefakten · Strang-Negativ aus globaler Metrik.

---

## Verweise

| Dokument | Rolle |
|----------|-------|
| `docs/KOPPLUNG_SERIE_ABSCHLUSS.md` | φ/ρ versiegelt |
| `docs/STATEFUL_GRAPH_v0_DRAFT.md` / `_PREREG.md` | Studie 1 |
| `prototypes/v2_stateful_graph/` | diskret Sweep + \|Q\|-Varianz-Screen |
| `prototypes/v3_continuous_dissensus/` | Dissensus Screen + Dual-Metrik |
