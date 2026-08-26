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

### Zwei Angriffspunkte

1. **Lebendigkeit an Arbeitsnachweis** — `recv_load` zählt Empfang, nicht
   Verarbeitung. Last braucht einen Abschluss-Term (wie M7/M9: Einfluss ∝
   nachgewiesener Bewegung).
2. **Winner-take-all entschärfen** — Power-of-two-choices (2 ziehen, leichteren
   nehmen) streut bei kleinen Margen.

`H0_REMOVAL_OK` (Share = 0): Entfernen aus der Kandidatenliste funktioniert.
Das Problem ist **Erkennung** (untätig vs. tot), nicht die Filter-Umleitung.

## Nicht in diesem Screen

Podman stop/start P5/P8 · Kanten-Ledger ℓ-Pfad · M7 Spike-Filter unter Kill ·
Po2-Implementierung (Follow-up).
