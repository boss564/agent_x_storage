# Hebel 4 — Plastizität: Implementierungs-Spezifikation

**Status:** Spec fixiert nach Bestätigung (2026-08-17) — bereit zur Implementierung
**Pre-Reg:** `docs/HEBEL4_PLASTIZITAET_PREREG.md`
**Bezug:** `agents_b2g/smartgrid/simulation.py`, `docs/SMART_GRID_PREREG.md`

---

## 0. Bestätigungen (eingeflossen)

| # | Entscheidung | Spec-Konsequenz |
|---|---|---|
| 1 | Nur Class-B-Dispatch | Schattenpreise / Hebb / Aktive Inferenz = **bewusst ausgeklammert** (Folgestudie), nicht vergessen |
| 2 | Null inkl. passiver 0.4-Flex | Konstante `PASSIVE_FLEX_FRACTION = 0.4` als **Stub-Annahme**; Caveat im Dossier Pflicht |
| 3 | Verdict nur Leitungsausfall-H1 | Bewölkung/Spitzenlast nur deskriptiv + **Generalisierungs-Vorbehalt** im Dossier |
| 4 | IUT-Prüfung | siehe §1 — IUT bleibt korrekt |

---

## 1. IUT-Verifikation (Schwelle eingefroren)

Hebel-4-H1 hat **dieselbe Konjunktions-Struktur** wie SMART_GRID_PREREG H1:

| Teil | Bedingung | Test |
|---|---|---|
| **H1a** | median(ΔR_grid) < 0 | einseitiger Wilcoxon, α=0.01 |
| **H1b** | median(ΔW_dyn) ≥ 0 **UND** ≥ 7/10 Seeds mit ΔW_dyn ≥ 0 | operatives Kriterium |

**Intersection-Union-Test:** H1 CONFIRMED nur wenn **beide** Teilbedingungen halten.
Ein einzelner Wilcoxon auf ΔW_dyn allein wäre **falsch**, weil die Meta-Stabilitäts-
Hypothese zwei Achsen hat (Kohärenz opfern / Wohlfahrt halten).

- Flex-Dispatch adressiert primär **H1b** (W_dyn).
- **H1a** kommt mechanisch vom Leitungsausfall (Wind-Inverter drift, ΔR<0) —
  Dispatch ändert die Phasen-Injektion in dieser Runde **nicht**.
- Deshalb: IUT bleibt die richtige Form. Kein Wechsel auf einseitigen Wilcoxon-only.

Eingefroren. Kein Nachjustieren nach Datenblick.

---

## 2. Nullmodell (dokumentationspflichtig)

```text
PASSIVE_FLEX_FRACTION = 0.4   # STUB, nicht gemessen — eingefroren
```

**Null-Arm:**

- `_unit_act` bleibt `pass` (oder Flag `plasticity=False` → no-op).
- `_compute_power_balance`:
  `flex_available = Σ_{B} power_capacity × PASSIVE_FLEX_FRACTION`
- Unabhängig vom Defizit.

**Dossier-Pflicht (zwei Stellen):**

1. **Annahme:** „Null = heutige Stubs inkl. pauschaler 0.4-Flex.“
2. **Caveat:** POSITIVBEFUND gilt *gegenüber diesem Stub*, nicht gegenüber einem
   realistischen Flex-Modell. Unter-/Überschätzung von 0.4 verschiebt die Messlatte.

---

## 3. Treatment — Class-B-Dispatch

### 3.1 Zustand (pro Simulation)

| Feld | Bedeutung |
|---|---|
| `plasticity: bool` | `False` = Null, `True` = Treatment |
| `soc[uid]` | State of Charge ∈ [0, 1] für Batterie/EV; Wärmepumpe nutzt `shed_headroom` |
| `flex_dispatch[uid]` | aktueller Beitrag [kW] dieses Schritts |
| `last_deficit` | max(0, load − gen_total) vor Flex |
| `dispatch_volume_records` | Σ flex_dispatch über Stress-Fenster (deskriptiv) |

**Initial-SoC (fixiert, vor Datenblick):**

| Unit | Initial |
|---|---|
| `battery_storage` | SoC = 0.80 |
| `ev_mobility` | SoC = 0.60 |
| `heat_pump` | shed_headroom = 1.0 (volle Drosselbarkeit) |

### 3.2 Defizit-Signal (jeder `step`, vor Class-B-`_unit_act`)

```text
gen_total = … (wie heute, aus Inverter capacity_factor)
load      = … (wie heute, inkl. Spitzenlast-Faktor)
deficit   = max(0.0, load - gen_total)
```

Ohne Plastizität: Flex = passiv 0.4 (Null).
Mit Plastizität: Class B deckt `deficit` in fester Reihenfolge ab.

### 3.3 Dispatch-Reihenfolge und Anteile (fixiert)

**Reihenfolge (Wasserfall):** `battery_storage` → `ev_mobility` → `heat_pump`

**Begründung (Reaktionszeit × Degradationskosten):** Batterie reagiert am
schnellsten und hat die geringsten Opportunitätskosten; EV ist medium (Zyklus-
Degradation); Wärmepumpe ist am trägesten (thermische Trägheit, Komfortverlust).
Die Reihenfolge ist damit keine freie Design-Wahl, sondern an diese Kosten-
Hierarchie gebunden.

**Granularität:** Der Wasserfall deckt das Defizit **pro Schritt vollständig**,
solange Kapazität/SoC reichen. Reicht die Class-B-Summe nicht, bleibt ein
Rest-Defizit und W_dyn wird anteilig schlecht. Anteilige Drosselung pro Gerät
(außer Kapazitätsgrenze) gibt es nicht — H1b prüft damit ehrlich, ob Class-B-
Flex den Leitungsausfall kompensieren kann.

| Unit | Reaktion bei Defizit | Max. Beitrag / Schritt |
|---|---|---|
| **battery_storage** | Entladen | `min(remaining_deficit, power_capacity, SoC-Budget)` |
| **ev_mobility** | Entladen / Ladeverschiebung | `min(remaining_deficit, 0.7 × power_capacity, SoC-Budget)` |
| **heat_pump** | Last-Drosselung | `min(remaining_deficit, power_capacity × shed_headroom)` |

**Konstanten (eingefroren):**

```text
BATTERY_ENERGY_SCALE = power_capacity * 2.0   # grobes SoC→kW-Budget pro Act
EV_POWER_SHARE       = 0.70                   # EV nicht volle Nennleistung
EV_ENERGY_SCALE      = power_capacity * 1.0
SOC_FLOOR            = 0.10                   # nicht unter 10% entladen
DT_ACT_HOURS         = cycle_period / 60.0    # SoC-Update grob proportional
```

**SoC-Update nach Entladung:**

```text
energy_drawn ≈ flex_dispatch[uid] * DT_ACT_HOURS
soc -= energy_drawn / (power_capacity * HOURS_FULL)   # HOURS_FULL=2.0 Batterie, 1.0 EV
soc = max(SOC_FLOOR, soc)
```

Wärmepumpe: `shed_headroom` sinkt nicht dauerhaft unter Stress-Fenster-Mittel
(vereinfacht: pro Act `shed_headroom` unverändert = 1.0 in dieser Runde —
Drosselung ist lastseitig, kein SoC). Caveat: keine thermische Trägheit.

**Kein Defizit (`deficit == 0`):** Treatment setzt `flex_dispatch[uid] = 0` für
aktive Extra-Leistung; Leistungsbilanz nutzt dann **nicht** die Null-0.4-Pauschale
für Treatment — sondern:

```text
# Treatment:
flex_available = sum(flex_dispatch.values())   # nur aktiver Dispatch
# Optional Regeneration: battery/EV laden wenn gen_total > load (SoC↑),
# aber Laden erhöht flex_available nicht in demselben Schritt.
```

**Wichtig:** Treatment ersetzt die pauschale 0.4-Flex vollständig (kein
`max(0.4×cap, dispatch)`). Sonst wäre der Null-Beitrag im Treatment versteckt
und der Vergleich unsauber. Null = nur 0.4; Treatment = nur aktiver Dispatch.

### 3.4 `_unit_act` Pseudocode

```python
def _unit_act(self, unit):
    if not self.plasticity or unit.unit_class != "B":
        return
    # remaining_deficit wird in _dispatch_round() vor dem Act-Loop gesetzt
    # und von battery → ev → heat_pump sequentiell abgetragen.
    ...
```

Besser: **ein** `_run_flex_dispatch()` pro `step` nach Gen/Load-Berechnung,
statt drei unabhängige Acts mit Race. OODA-Zyklen triggern nur „darf dieses
Gerät in diesem Schritt reagieren“:

```text
eligible = {B-units with cycles_completed advanced this step OR always-eligible}
```

**Vereinfachung (Spec-Entscheidung):** Im Treatment-Arm läuft der Wasserfall
**jeden** `step` (dt=1), unabhängig vom OODA-Tick — OODA bleibt für Logging/
Phasen der Class A. Begründung: Defizit ist kontinuierlich; OODA-Gating würde
H1b künstlich schwächen. Caveat im Dossier: „Dispatch ist schritt-synchron,
nicht OODA-getaktet.“

### 3.5 Leistungsbilanz

```python
served = min(gen_total + flex_available, load)
w_dyn = served / load
```

Null: `flex_available = 0.4 * Σ_B capacity`
Treatment: `flex_available = Σ flex_dispatch`

---

## 4. Stress-Injektionen (unverändert)

Wie `SmartGridStressSimulation` heute:

| Typ | Injektion |
|---|---|
| `leitungsausfall` | Wind-Inverter: `capacity_factor=0`, `period=100` |
| `bewoelkung` | PV: `capacity_factor=0.1` |
| `spitzenlast` | `base_load *= 1.5` |

Keine phasenwirksame Erweiterung in dieser Runde.

---

## 5. Messung und Verdict

### 5.1 Metriken (alle drei Stressoren)

Pro Seed × Stress × Arm: `ΔR_grid`, `ΔW_dyn`, plus Treatment: `mean_dispatch_kw`
im Stress-Fenster.

### 5.2 Verdict (nur Leitungsausfall × Treatment)

```text
H1a: Wilcoxon(ΔR_grid, alternative=less), α=0.01
H1b: median(ΔW_dyn)≥0 AND count(ΔW_dyn≥0)≥7/10
H1  = H1a AND H1b   # IUT
```

- **WIRKSAM** wenn H1 CONFIRMED (Leitungsausfall, Treatment)
- **NICHT_WIRKSAM** sonst

Null × Leitungsausfall: Replikation erwartet NOT_CONFIRMED; berichten, nicht
Verdict-Bestandteil.

### 5.3 Deskriptiv (kein Verdict)

Bewölkung + Spitzenlast (Treatment, optional auch Null): ΔR, ΔW, Dispatch-Volumen.
**Kein** „fast signifikant“ → Bestätigung.

### 5.4 Generalisierungs-Vorbehalt (Dossier-Pflicht)

POSITIVBEFUND auf Leitungsausfall belegt Plastizität für **diesen** Störfall,
nicht für die Klasse aller Störfälle. Übertragbarkeit auf Bewölkung/Spitzenlast =
offene Folgestudie.

---

## 6. Dateien / API

| Datei | Änderung |
|---|---|
| `agents_b2g/smartgrid/simulation.py` | `plasticity` Flag; `_run_flex_dispatch`; Bilanz Null vs Treatment; Dispatch-Records |
| `agents_b2g/smartgrid/unit_base.py` | optional `soc` Feld — oder State nur auf Simulation |
| `scripts/run_hebel4_plastizitaet_study.py` | 10 Seeds × Leitungsausfall × {Null,Treatment} + deskriptiv Bewölkung/Spitzenlast Treatment |
| `scripts/test_hebel4_plastizitaet.py` | siehe §7 |
| `docs/HEBEL4_PLASTIZITAET_ERGEBNIS.md` | nach Lauf, inkl. Caveats §0/§2/§5.4 |

`SmartGridStressSimulation(..., plasticity: bool = False)`

---

## 7. Tests

1. **Null_act_is_noop:** `plasticity=False` → `_unit_act` ändert SoC nicht;
   `flex_available` ≡ 0.4×Σ_B.
2. **Treatment_dispatches_on_deficit:** künstliches Defizit → Batterie dispatch > 0,
   SoC sinkt.
3. **Waterfall_order:** bei knappen Ressourcen Batterie vor EV vor Wärmepumpe
   (mock: Batterie sättigt, Rest an EV).
4. **Treatment_no_passive_04:** bei deficit=0 und leerem Dispatch ist
   `flex_available == 0` (nicht 0.4×Σ).
5. **Soc_floor:** Entladung stoppt bei `SOC_FLOOR`.
6. **Leitungsausfall_injection_unchanged:** Wind `capacity_factor==0`, `period==100`.
7. **Verdict_helpers:** `classify_h1(deltas_r, deltas_w)` respektiert IUT
   (H1a-only → NOT_CONFIRMED; beide → CONFIRMED).

---

## 8. Runner-Ausgabe (Minimal)

```json
{
  "leitungsausfall": {
    "null": { "h1a": "...", "h1b": "...", "h1": "NOT_CONFIRMED", "delta_w": [...], "delta_r": [...] },
    "treatment": { "h1a": "...", "h1b": "...", "h1": "...", "mean_dispatch_kw": ... }
  },
  "bewoelkung_treatment_descriptive": { ... },
  "spitzenlast_treatment_descriptive": { ... },
  "verdict": "WIRKSAM | NICHT_WIRKSAM",
  "passive_flex_fraction": 0.4,
  "notes": ["IUT", "0.4 stub caveat", "generalization caveat", "consciously deferred: shadow/hebb/AI"]
}
```

---

## 9. Bewusst ausgeklammert (nicht vergessen)

- Schattenpreis-Kommunikation
- Hebb'sches Um-Routing
- Aktive Inferenz
- Phasenwirksame Bewölkung/Spitzenlast

Alle vier: **neue Pre-Reg** erforderlich.

---

## 10. Sequenz nach Spec

1. Implementieren laut §3–§6
2. Tests §7 grün
3. Studie §5
4. Dossier mit Caveats (0.4-Stub, Generalisierung, ausgeklammerte Hebel, IUT)
