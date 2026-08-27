# Stateful Graph — Serie v0 (Konsolidierung)

**Status:** Studie 1 · … · topology · async · agent_scale · failover_ring · 2026-08-26  
**Charakter:** Neue Architekturfamilie — **nicht** Studie 11 der φ/ρ-Kopplung  
**Sandbox diskret:** `prototypes/v2_stateful_graph/`  
**Sandbox Dissensus:** `prototypes/v3_continuous_dissensus/` · **kein** Runner-Transfer

```text
Kopplungsfamilie:     FAMILIE GESCHLOSSEN (10 Studien) — Kohärenz nicht relational
Stateful Graph v0:    STRUCTURE_RELATIONAL (diskret, |Q|=4) — Sweep 6/6
Dissens-Gegenprobe:   PROTO_PASS (kontinuierlich, matched gate) — kein Pre-Reg
|Q|-Varianz-Screen:   STRUCTURE_RELATIONAL für |Q| ∈ {4, 8, 16, 32} — 24/24
|Q|=2 Grenzfall:      STRUCTURE_BREAKS — 0/6 · untere Leistungsgrenze |Q|=4
completion_proof:     STRUCTURE_RELATIONAL unter Receipt-Gate — 18/18
wall_clock_verify:    HYPOTHESIS_CONFIRMED — ms↑ mit |Q| · tps↓
topology:             HYPOTHESIS_FALSIFIED — nur sparse Ring relational
async_verify:         HYPOTHESIS_CONFIRMED — async D=4 ≈4× tps · Margin_Δ=0
agent_scale:          HYPOTHESIS_CONFIRMED — N≤36 relational · Makespan∝N · tps flach (async)
failover_ring:        STRUCTURE_RECOVERS 6/6 — Kill-1 + Ring-Reform hält Margin
Korrektur:            Topologie = Zentrum · ⟨k⟩=1 randständig · H-Gate nicht normiert · Option 1 Charter
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
| topology | Signalgraph complete/sparse/hub · \|Q\|=4 | `HYPOTHESIS_FALSIFIED` Screen |
| async_verify | sync D=1 vs async D=4 · sparse Ring | `HYPOTHESIS_CONFIRMED` Screen |
| agent_scale | N∈{9,18,27,36} · sparse Ring · async D=4 | `HYPOTHESIS_CONFIRMED` Screen |
| failover_ring | Kill-1 · Ring-Reform · \|Q\|=4 | `STRUCTURE_RECOVERS` 6/6 Screen |

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

## Antwort (topology — Screen only)

**Frage:** Bleibt `STRUCTURE_RELATIONAL`, wenn die **Signal-Topologie** wechselt
(vollständig / spärlich / Hub-Spoke), bei fixem \|Q\|=4?

**Freeze:** Seeds `20270801–06` · Metrik-Partner = Ring (sticky M) · Topologie steuert nur σ ·
Arm C = π(Peer_B) · Gate wie Varianz-Screen.

| Topologie | ⟨k⟩ | Passes | Avg Margin | Verdict |
|-----------|-----|--------|------------|---------|
| complete | 8,0 | **0/6** | ≈0,00 | `STRUCTURE_BREAKS` |
| sparse (Ring) | 1,0 | **6/6** | 0,52 | `STRUCTURE_RELATIONAL` |
| hub (G01) | 1,8 | **0/6** | ≈−0,11 | `STRUCTURE_BREAKS` |

**Hypothese: falsifiziert** (`HYPOTHESIS_FALSIFIED`).  
Relationale Trennung ist **kein** Topologie-Invariants: sie hängt am **spärlichen
1:1-Signal** (Ring = Studie-1). Vollständige Mischung und Hub-Broadcast machen B≈C
(Margin≈0). Onset-Proxy differenzierte hier nicht (alle früh ≥ Schwelle) — sekundär.  
**Lehre:** Sticky-Partner-Metrik allein reicht nicht — die Signalgraph-Form ist
Vorbedingung für Arm-C-Bruch. **Wahrheit vor Optik.**  
Artefakte: `topology_screen.py` · `topology_results.json`.

---

## Antwort (async_verify — Screen only)

**Frage:** Erhöht Pipeline-Verifikation (async) den Durchsatz, ohne sparse-Ring
`STRUCTURE_RELATIONAL` zu brechen?

**Freeze:** Seeds `20270901–06` · \|Q\|=4 · Topologie = sparse Ring · Mock-Z3/BHO
\(O(|Q|^2\times 64)\) · sync D=1 vs async D=4 · tps = accounted Makespan
(Parallel-Worker-Modell über gemessene per-Txn-ms; Event-Order identisch).

| Mode | D | Passes | Avg Margin | Avg tps | Verdict |
|------|---|--------|------------|---------|---------|
| sync | 1 | 6/6 | 0,48 | ≈3432 | `STRUCTURE_RELATIONAL` |
| async | 4 | 6/6 | 0,48 | ≈13687 | `STRUCTURE_RELATIONAL` |

**Hypothese: bestätigt** (`HYPOTHESIS_CONFIRMED`):
Struktur beide Modi relational · Margin_Δ=0 · **Speedup ≈ 3,99×** (≈D).  
Vorbedingung: Topologie bleibt Ring (topology-Screen). Async ersetzt nicht denselben.  
Artefakte: `async_verify_screen.py` · `async_verify_results.json`.

---

## Antwort (agent_scale — Screen only)

**Frage:** Bleibt `STRUCTURE_RELATIONAL` bei N>9 auf dem sparse Ring, und wie skaliert
die Verifikations-Makespan unter async D=4?

**Freeze:** Seeds `20271001–06` · \|Q\|=4 · sparse Ring · N∈{9,18,27,36} · async D=4 ·
Heavy-Verify auf Arm B · Gate wie Varianz-Screen.

| N | Passes | Avg Margin | Makespan ms | tps | Verdict |
|---|--------|------------|-------------|-----|---------|
| 9 | 6/6 | 0,47 | ≈74 | ≈13694 | `STRUCTURE_RELATIONAL` |
| 18 | 6/6 | 0,48 | ≈146 (×1,98) | ≈13831 | `STRUCTURE_RELATIONAL` |
| 27 | 6/6 | 0,50 | ≈220 (×2,99) | ≈13757 | `STRUCTURE_RELATIONAL` |
| 36 | 6/6 | 0,49 | ≈293 (×3,98) | ≈13766 | `STRUCTURE_RELATIONAL` |

**Hypothese: bestätigt** (`HYPOTHESIS_CONFIRMED`):
Struktur all N · Makespan ≈ linear in N (Ratio→4 bei N=36).  
**Txn-tps bleibt flach** unter festem async D=4 (kein Drop) — Verfeinerung:
„Durchsatz sinkt“ gilt für **Gesamt-Makespan/Arbeit**, nicht für Pipeline-tps.  
Sparse Ring bleibt die getestete (kritische) Topologie; complete/hub nicht erneut.  
Artefakte: `agent_scale_screen.py` · `agent_scale_results.json`.

---

## Antwort (failover_ring — Screen only)

**Frage (offen):** Fällt ein Agent im sparse Ring aus und formieren die Überlebenden
den Ring neu — erholt sich die relationale Trennung, oder bricht sie dauerhaft?

**Freeze:** Seeds `20271101–06` · \|Q\|=4 · N=9 · Warmup=32 · Pre=40 · Post=80 ·
Victim seed-bestimmt · Reform = Cycle auf Survivors · Gate pre & post.

| Seed | Victim | Margin pre | Margin post | Outcome |
|------|--------|------------|-------------|---------|
| 01–06 | G01–G04 | 0,42–0,57 | 0,36–0,54 | **RECOVERS** 6/6 |

**Verdict: `STRUCTURE_RECOVERS`** (`HYPOTHESIS_RESOLVED`).  
Avg Margin pre≈0,48 · post≈0,45 · Recovery-Onset-Proxy ≈16 Post-Events.  
**Lesart mit Serien-Korrektur:** Die Reform stellt wieder ⟨k⟩=1 her — dieselbe
Vorbedingung wie Studie 1. Erholung heißt nicht „Topologie egal“, sondern
„1:1-Ring unter Survivors reicht erneut“. Ohne Reform wäre Bruch erwartbar
(nicht Gegenstand dieses Screens).

**Neben v4 Load-Trap (nicht derselbe Screen, dasselbe Bild):**

| Toter in der Liste | Toter aus der Liste |
|--------------------|---------------------|
| **`H1_CONFIRMED`** — Zombie zieht Verkehr (`load_of` = Untätigkeit) | **`STRUCTURE_RECOVERS` / `H0_REMOVAL_OK`** — Ring-Reform bzw. Filter |

Quelle: `prototypes/v4_failover_loadtrap/FAILOVER_PROTO.md`.  
Artefakte: `failover_ring_screen.py` · `failover_ring_results.json`.

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
dieselbe Definition wie in Studie 1. Ein früherer Dissensus-`PROTO_FAIL` war
genau dieser Messfehler und wurde korrigiert, dokumentiert — nicht stillschweigend
ersetzt. **Wahrheit vor Optik.**

---

## Serien-Korrektur (bindend lesen) — Topologie & Gate-Normierung

Stand 2026-08-26. Diese Lesart **überstimmt** zu optimistische Robustheits-Lektüren
der Screen-Tabelle oben.

### 1. Topologie ist der zentrale Befund — nicht ein Nebenstrang

Alle übrigen Screens (|Q|-Varianz, |Q|=2, completion_proof, wall_clock, async,
agent_scale) liefen auf der **einen** Topologie, die den Arm-C-Bruch trägt:
**Ring mit Grad ⟨k⟩=1**.

| Label im Screen | Tatsache |
|-----------------|----------|
| „spärlich“ | **nicht** robust-spärlich: ⟨k⟩=1 ist das **Minimum eines zusammenhängenden Graphen** |
| complete / hub | Margin≈0 bzw. negativ — **erwartbar**, kein Messversagen |

**Mechanismus:** Bei genau einem Signalpartner **ist die Partneridentität das gesamte
Signal**. Arm C tauscht diesen einen Sender — der Agent liest eine andere Reihe.
Bei `complete` (⟨k⟩=8) liest er eine Mischung; die Permutation ändert *welche* acht,
aber die Mischung mittelt Identitäten weg. Margin≈0 ist die Folge, nicht das Versagen.

**Engere Bedeutung von `STRUCTURE_RELATIONAL`:** nicht „Beziehungen erzeugen Struktur“,
sondern näher: **bei genau einem Partner ist die gemessene Struktur die Beziehung**.
Das grenzt an eine Tautologie. Wer die **24/24** aus dem |Q|-Screen als
Topologie-Robustheit liest, liest falsch — jene Screens **setzen** den Ring voraus.

### 2. H-Gate ist nicht über |Q| normiert

Feste Schwelle \(H\geq 2{,}0\) bei \(H_{\max}=\log_2(|Q|^2)\):

| \|Q\| | H (typ.) | H_max | H/H_max | Gate 2,0 |
|------|----------|-------|---------|----------|
| 2 | ≈1,99 | 2 | ≈100 % | knapp verfehlt |
| 4 | ≈2,99 | 4 | ≈75 % | erfüllt |
| 8 | ≈3,98 | 6 | ≈66 % | erfüllt |
| 16 | ≈4,96 | 8 | ≈62 % | erfüllt |
| 32 | ≈5,92 | 10 | ≈59 % | erfüllt |

Relative Information **sinkt** mit \|Q\|, absolute H steigt, das feste Gate wird
leichter. Dieselbe Klasse wie ein absoluter `r_floor` über wechselnden Wertebereichen.
Vergleichbar über \|Q\| wäre z. B. \(H/H_{\max}\geq 0{,}5\) — **nicht** nachträglich an
versiegelte Artefakte gezogen; nur als methodische Schuld / künftige Screen-Form notiert.

### 3. Was trotzdem steht

- Dual-Metrik-Korrektur (relational vs. global) — gültig und dokumentiert
- |Q|=2-Grenze und wall_clock/async/scale: **unter Ring-Voraussetzung** gültig
- topology-Falsifikation: wissenschaftlicher Gewinn, kein Schönheitsfehler

### 4. Handels-/Execution-Frage (nicht übergangen)

Bereits bindend in Map §9 / Charter: **Option 1 — Analyse/Simulation**, Scope
`DEFENSIVE_CAUSAL_GROUNDING`. Keine Order-Ausführung, keine Arb-/Liquidations-Execution.
`infra-gate`: `live_execution=false` immer. Wave 39 setzt Negativklausel zur Laufzeit durch.
**Kein** Weiterarbeiten an Execution-Pfaden in diesem Strang.

---

## Status & offene Türen

**Jetzt:** Serie methodisch korrigiert · **failover_ring: `STRUCTURE_RECOVERS` 6/6**
(Reform stellt ⟨k⟩=1 wieder her).

**Optional später (nur mit neuer Hypothese):** Grad-Kontinuum ⟨k⟩∈{2…} · normiertes
H-Gate · Failover **ohne** Reform (Kontrolle) · Dissensus Pre-Reg · `completion_load` /
`two-choice` · Live-Z3 · async lossy/Stale.

**Nicht erlaubt:** Studie 11 φ/ρ · Hybrid · Schwellen-Nachjustierung an versiegelten
Artefakten · Strang-Negativ aus globaler Metrik · |Q|-24/24 als Topologie-Robustheit verkaufen ·
Execution/Order-Pfade entgegen Charter.

---

## Verweise

| Dokument | Rolle |
|----------|-------|
| `docs/KOPPLUNG_SERIE_ABSCHLUSS.md` | φ/ρ versiegelt |
| `docs/STATEFUL_GRAPH_v0_DRAFT.md` / `_PREREG.md` | Studie 1 |
| `docs/AGENT_X_CHARTER.md` | Defensive Scope · Negativklausel |
| `docs/AGENT_SWARM_P9_MAP_v0.md` §9–§10 | Option 1 · fail-closed Gate |
| `prototypes/v2_stateful_graph/` | diskret Sweep + Screens |
| `prototypes/v3_continuous_dissensus/` | Dissensus Screen + Dual-Metrik |
