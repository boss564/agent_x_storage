# Failover Load-Trap — Proto Gate (Screen)

**Status:** SCREEN only · kein Pre-Reg · 2026-08-26  
**Sandbox:** `prototypes/v4_failover_loadtrap/`  
**Runner:** `python3 prototypes/v4_failover_loadtrap/failover_proto.py`

## Strukturbefund

| Annahme (Test-Plan) | Ist-Zustand |
|---------------------|-------------|
| Pfad-Länge P1→P9 | **existiert nicht** |
| Totlock >30s ohne Pfad-Änderung | **nicht anwendbar** |
| Umleitungsschicht | **ja:** `StickySelector` + Least-Loaded, **1-von-9** (nicht Fan-Out) |

Quellen: `agents_b2g/emergence/partner_select.py`, `adapter_agentx.deliver`,
`scripts/demo_producer_cluster.py`.

## Hypothese H1

> Bei Ausfall von Evaluator E5 (Zombie: bleibt Kandidat, Inbox leer / unverarbeitet)
> steigt sein Anteil am zugewiesenen Verkehr — `load_of` liest Untätigkeit als Verfügbarkeit;
> `recv_load` zerfällt nie.

**Kontrolle H0:** E5 aus Kandidaten **entfernen** → Anteil → 0 (Filter-Failover).

## Gate

- 3 Seeds `20270501–03`
- Wandzeit < 16 s
- Verdict: `H1_CONFIRMED` | `H1_FALSIFIED` | `H1_INCONCLUSIVE`

## Screen-Ergebnis (2026-08-26)

| Arm | Befund |
|-----|--------|
| Strukturell | kein P1→P9-Pfad · Umleitung = Sticky 1-von-9 |
| H1 Zombie + Live-Backlog | **`H1_CONFIRMED`** · Δshare ≈ +0,096 (0,111 → 0,207) · 3/3 |
| H0 Removed | **`H0_REMOVAL_OK`** · share_post = 0 |
| Budget | 1,1 s < 16 s |

### Schärfung: Winner-take-all bei marginaler Last

`load_post` (Beispiel Seed): lebende E1–E4 ≈ 344–350, Zombie E5 = 344 —
Differenz **0–6 auf ~345 (< 2 %)**, Share dennoch **verdoppelt** (0,111 → 0,207).

Ursache: Least-Loaded ist hartes `argmin` ohne Dämpfung. Wer marginal am
niedrigsten liegt, gewinnt jede Runde; beim Blackhole bleibt `len(inbox)=0`,
während `recv_load` bei allen mitwächst — der Zombie holt nie auf.

**Erweiterung:** Nicht nur „Tote sehen untätig aus“. Jede systematische
Unterschätzung der Last (langsamer Zähler, verzögerte Buchung, abweichende
Metrik) konzentriert Verkehr — ohne Ausfall.

### Zwei Follow-ups (neutral benannt)

1. **`completion_load`** — `recv_load` zählt Empfang, nicht Verarbeitung.
   Last braucht einen Abschluss-Term (Klasse M7/M9: Einfluss ∝ nachgewiesener
   Bewegung). Kein kryptographisches Proof-of-Work.
2. **`two-choice tie-break`** — bei Near-Ties zwei Kandidaten ziehen, den
   leichteren nehmen (gegen hartes `argmin`). Keine Aussage über kompromittierte
   Agenten-Paare.

`H0_REMOVAL_OK` (Share = 0): Entfernen aus der Kandidatenliste funktioniert.
Das Problem ist **Erkennung** (untätig vs. tot), nicht die Filter-Umleitung.

## Zwei Befunde nebeneinander

| Liste | Was passiert | Verdict | Ort |
|-------|----------------|---------|-----|
| Toter **bleibt** Kandidat (Zombie, Inbox leer) | `load_of` liest Untätigkeit als Verfügbarkeit → Verkehr **steigt** | **`H1_CONFIRMED`** | dieser Proto |
| Toter **aus der Liste** (Filter / Ring-Reform auf Survivors) | Share → 0 · relationale Trennung erholt sich | **`H0_REMOVAL_OK`** · **`STRUCTURE_RECOVERS` 6/6** | dieser Proto · `docs/STATEFUL_GRAPH_SERIE_v0.md` (failover_ring) |

Dasselbe Bild, zwei Messungen: **drinbleiben zieht; draußen erholt sich die Struktur.**
Kein Widerspruch — die Topologie heilt nicht den Zombie in der Liste.

Serie-Screen (Kill-1 + Cycle auf Survivors): `prototypes/v2_stateful_graph/failover_ring_screen.py`.

## Nicht in diesem Screen

Podman stop/start P5/P8 · Kanten-Ledger ℓ-Pfad · M7 Spike-Filter unter Kill ·
`completion_load` / `two-choice tie-break` Implementierung (Follow-up).
