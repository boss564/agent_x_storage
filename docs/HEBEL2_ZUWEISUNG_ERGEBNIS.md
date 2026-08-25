# Hebel 2 — Zuweisungs-Ergebnis (Assignment-Simulation)

**Status:** Abgeschlossen — **POSITIVBEFUND** (Durchsatz-Proxy),
**Charakter: validierend / diagnostisch, nicht therapeutisch**
**Datum:** 2026-08-16
**Pre-Reg:** `docs/HEBEL2_ZUWEISUNG_PREREG.md` (`6c927bc2`)
**Spezifikation:** Assignment + Eval laut User-Spec; Code: `scripts/hebel2_assignment.py`,
`scripts/eval_hebel2_zuweisung.py`
**Artefakt:** `hebel2_zuweisung_ergebnis.json` (gitignored)
**Tests:** `scripts/test_hebel2_zuweisung.py` — 11/11

---

## Ergebnis (strikt gegen Pre-Reg ±5%)

Metrik hier: **Durchsatz-Proxy** `1 / max_load` (Assignment-Simulation,
N=30 Trials × 1000 TX). Nicht der Live-`msg/tick`-Capture aus Hebel 3 —
siehe Limitationen.

| Arm | mean throughput_proxy | load_balance_cv |
|---|---|---|
| Nullmodell (uniform random) | 0.007981 | 0.0856 |
| Treatment (shortest inbox) | 0.008929 | 0.0028 |
| Status quo (sha256 % 9) | 0.008000 | 0.0724 |

| Vergleich | Δ | Klassifikation |
|---|---|---|
| Treatment vs Null | **+11.88%** | ≥ +5% → **POSITIVBEFUND** |
| Status quo vs Null (deskriptiv) | +0.24% | im ±5%-Band |

**VERDICT:** **POSITIVBEFUND**

---

## Interpretation

### Konstruktionsmerkmal der Simulation

Unter dem **akkumulierenden Inbox-Modell** (jede Zuweisung erhöht
`inbox_depth` beim Treatment) balanciert Least-Loaded messbar besser als
Würfeln: niedrigerer Max-Load → höherer Proxy, CV nahe 0.

Der Spec-Test „stateless → INCONCLUSIVE“ war falsch: Treatment akkumuliert
Zustand, Null/Status-quo nicht. Die Korrektur ist methodisch richtig — und
enthüllt: Least-Loaded *minimiert per Konstruktion* `max_load`; der Proxy
`1/max_load` misst genau das. Der POSITIVBEFUND ist daher eine
**Reproduktion der erwarteten Least-Loaded-Eigenschaft**, kein überraschender
Durchsatz-Fund. Last-Balancierung bleibt ein echter Mechanismus; die Lesart
ist Validierung der Konstruktion, nicht therapeutische Überraschung.

### Sim-Status-quo ≠ Produktions-Status-quo

| | Simulation | Produktion |
|---|---|---|
| Status-quo | Hash (`sha256 % 9`) | **Least-Loaded** (bereits) |
| Treatment | Least-Loaded | — |
| Befund | Least-Loaded > Hash (+11.9%) | Least-Loaded = Status-quo |

**Hebel 2 hat in der Produktion keinen weiteren Hebel:** der Befund bestätigt
den Produktions-Status-quo (validierend), verbessert ihn nicht (nicht
therapeutisch).

Status-quo-Hash vs. Null deskriptiv +0.24% — im ±5%-Band; konsistent mit
Hebel 1 („nicht besser als Würfeln“ ohne Zustand).

### Kopplung an Hebel 1

**Zustandslos (Inbox bleibt 0):** Treatment → deterministischer Tie-Break →
kein Vorteil. Least-Loaded wirkt nur bei Inbox > 0. Solange Evaluatoren
funktional identisch und faktisch zustandslos bleiben (Hebel-1-Befund), ist
Hebel 2 wirkungslos. **Hebel 2 braucht den Zustand, den Hebel 1 adressiert.**

---

## Echte Zustands-Schnittstelle

| Quelle | Feld |
|---|---|
| `BaseAgent` (`agents_b2g/protocol.py`) | `inbox: List[AgentMessage]` → Tiefe = `len(inbox)` |
| Status-Dump | `inbox_len` |
| Emergence-Adapter / Least-Loaded | `recv_load + len(a.inbox)` |

Helper im Code: `inbox_depth_from_agent(agent)` → `len(getattr(agent, "inbox", []) or [])`.

Adaption für Live-State-Aufbau:

```python
state[eid] = {"inbox_depth": recv_load.get(eid, 0) + len(agent.inbox)}
```

---

## Limitationen (dokumentiert)

1. **Proxy ≠ Pre-Reg-Live-Metrik:** Pre-Reg nennt `len(messages)/ticks` via
   `adapter_agentx`. Diese Runde misst Assignment-Balance-Proxy. Live-Wire
   (Sticky/Least-Loaded vs. random im TickController) bleibt optional Follow-up.
2. **Produktion nutzt bereits Last:** `adapter_agentx` Least-Loaded mit
   `recv_load + inbox_len`. Sim-Status-quo ist Hash-Shard, nicht Sticky —
   POSITIVBEFUND gilt für „Least-Loaded vs. Random“, nicht zwingend für
   „neues Treatment vs. heutiger Sticky“.
3. **Hebel-1:** Evaluatoren funktional identisch → Capability-Awareness
   bleibt wirkungslos; nur Last/Inbox kann helfen.

## Sequenz (neu priorisiert)

Hebel 2 abgeschlossen (validierend) → **nicht** Hebel 4 als Nächstes, sondern
**Hebel-1-Follow-up** (Differenzierung/Reduktion der Evaluatoren), danach
Hebel 2 bei Zustand neu bewertbar; Hebel 4 nach Freigabe.
