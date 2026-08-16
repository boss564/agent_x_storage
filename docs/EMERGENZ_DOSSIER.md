# Emergenz-Dossier — COUPLED-Nachweis im 27-Agenten-ABM

**Datum:** 2026-08-16  
**System:** 27-Agenten-ABM (Provider/Evaluator/Economic), `scripts/demo_producer_cluster.py`  
**Messpfad:** `agents_b2g/emergence/`  
**Ergebnis:** Gate **COUPLED** am Betriebspunkt **W=2 / gap=1**  
**Betriebsstatus:** Befund dokumentiert; Korridor **Opt-in** (`--corridor`), **nicht** Default, **nicht** in B2G-Produktion verdrahtet.

## Kriterium

```
COUPLED  =  D_dyn > 0   UND   Kuramoto p < α_Bonferroni
```

Kein TRIVIAL_SYNC (D_dyn → 0). Bonferroni über die getesteten Kopplungspunkte der finalen Stufe.

## Methodik (TIER 0 → 2)

| Stufe | Frage | Ergebnis |
|-------|-------|----------|
| **TIER 0** | Mess-Validität | `hash()` → `zlib.crc32`; Routing-Wahrheit; PYTHONHASHSEED-unabhängig |
| **TIER 1** | Nullmodell-Aussagekraft | Partner-Selektion + Sticky; Settlement-Broadcast → 1 Provider; Dichte ~0.51 → **0.1325**; `directed_edge_swap` |
| **TIER 2a** | Rückstau (Gas) | homöostatisch, nicht synchronisierend |
| **ε** | Exzitation | Diskret-Ceiling (max. 1 Tick/Zyklus) |
| **TIER 2b** | Relaxations-Oszillator (M–S) | Puls korrekt, Sparse-Graph-Grenze |
| **TIER 2c** | Feuer-Korridor | **COUPLED** |
| **Messung** | ab 2b-Ende | ereignisbasierte Phase (`firing_ifi`), IFI-Shuffle-Surrogate, Bonferroni |

## Die drei echten Negative auf dem Weg

1. **2a Rückstau** — homöostatisch, nicht synchronisierend (D_dyn steigt, r flach).
2. **ε Exzitation** — Diskret-Ceiling: `factor < 1` kann die Tick-Rate nicht über 1×/Zyklus heben.
3. **2b Relaxations-Oszillator** — mechanisch korrekt (exzitatorisch, t+1), aber Sparse-Graph-Propagation + Frequenz-Dispersion reichen nicht zur globalen Kohärenz.

## Ergebnis: COUPLED am Feuer-Korridor (2c), W=2 / gap=1

| Kennzahl | Wert | Constraint / Einordnung |
|----------|------|-------------------------|
| r | 0.2709 | Formel-Baseline 1/√27 = **0.192** → ~**41 %** darüber (Oberkante; bei Burst/effektivem N kann die Null lokal höher liegen). Empirische IFI-Surrogate: Mittel **0.253** → r_obs nur ~**7 %** darüber — reales, aber **kleines** Signal. |
| p_raw | 0.002 | < α_Bonf ≈ 0.0083 ✓ (Signifikanz ≠ Effektstärke) |
| D_dyn | 1.052843 | > 0, kein TRIVIAL_SYNC ✓ |
| Dichte | 0.1581 flach | kein Topologie-Confound ✓ |
| Feuerrate | 3335 / 3522 = **94.7 %** Baseline | ≥ 90 % ✓ |
| Peak / zero_frac / regime | 16 / 0.333 / burst | Bündelung ✓ |
| Reproduzierbarkeit | 2× **byte-identisch** | ✓ |

**Kurz:** nachweisbar gekoppelt (`p`), schwach ausgeprägt (`r` nur moderat über Zufall/Surrogat-Mittel).

Primärer Betriebspunkt: **W=2 / gap=1** (einziger Punkt mit hart erfüllter Feuerrate unter den starken COUPLED-Kandidaten; W=4/gap=2 ebenfalls Gate, aber invasiver).

## Emergenz-Charakterisierung (ohne Überclaim)

| Aspekt | Status |
|--------|--------|
| **WANN** das Fenster öffnet | emergent — Agenten-`charge` + Lock-Erwerb (171 Öffnungen, 3 Lock-Holder) |
| **WIE LANG** offen/zu (`width` / `gap`) | Design-Parameter |
| Globaler Metronom | nicht implementiert |

**Interpretation:** geteilte Timing-Struktur mit agentengetriebenem Phasenstart.  
Kollektive Bündelung; keine aufgezwungene Wanduhr, aber auch keine reine Selbstorganisation der Struktur. Schwächer als „Struktur emergiert vollständig“, stärker als „externer Takt erzwingt Sync“.

## Mechanismus-Einordnung

**2c-Korridor ≠ 2b-Pulse.** Der Korridor bündelt das Feuer-Timing über eine geteilte Struktur, während die Akquisition divergent bleibt (D_dyn > 0). Er umgeht die Sparse-Graph-Propagation, weil er kein paarweises Signal durch den dünnen Graphen schicken muss, sondern ein Zeitfenster bereitstellt.

Bündelungsnachweis über **Peak-Höhe + zero_frac** (Burst-Regime), nicht Poisson-`excess_ge3` (bei Bursts irreführend negativ).

## Betriebspunkt & Reproduktion

```bash
REPO="/Volumes/THX_OS_ULTRA - Data/Users/olivermueller/agent_x_storage"
cd "$REPO"

# Primärer Betriebspunkt (2× für Repro-Check)
python3 agents_b2g/emergence/adapter_agentx.py 512 --corridor 2 --gap 1 | tee /tmp/emerg_w2g1_run1.log
python3 agents_b2g/emergence/adapter_agentx.py 512 --corridor 2 --gap 1 | tee /tmp/emerg_w2g1_run2.log
diff /tmp/emerg_w2g1_run1.log /tmp/emerg_w2g1_run2.log && echo "reproduzierbar"

# Default ohne Korridor (ungekoppelt) — Produktions-/Baseline-Pfad
python3 agents_b2g/emergence/adapter_agentx.py 128
```

Parameter: `W=2`, `gap=1`, `lock_trigger` aus `gas_profiles` / `oscillator_from_gas`, 512 Ticks, Methode `firing_ifi`.

## Scope / Nicht-Ziele

- Korridor ist **Forschungswerkzeug** auf dem 27-Agenten-ABM, kein B2G-277-Default.
- Opt-in behält Reproduzierbarkeit ohne Default-Durchsatz-Preis.
- Kampagnenziel war der **Nachweis**, nicht der Dauerbetrieb.
