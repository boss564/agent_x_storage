# Wirtschafts-Schwarm — Emergence-Messung: Gewaltenteilung und Phasenkohärenz

**Status:** Abgeschlossen — negativer Phasenkohärenz-Befund, robust gegen IFI-Shuffle-Gegenprobe
**Datum:** 2026-08-16
**Bausteine:** 1–5 (`6e05d7e0` … `7806a879`), Gegenprobe (`3fdb33f4`)
**Charakter:** Ergebnissoffene Messung. Das Dossier dokumentiert den artefaktbereinigten Befund, nicht das Roh-Ergebnis.

---

## 1. Fragestellung

Zeigt der Wirtschafts-Schwarm (9 Agenten, 3 Klassen, Gewaltenteilung) messbare
Kuramoto-Phasenkopplung, wenn seine Agenten über den Freigabe-Kreislauf
(`FREIGABE_REQUEST → ComplianceEngine → GRANT/DENY → Re-Execute`) und Delegation
interagieren?

**Hintergrund:** Die Emergence-Kampagne (Fire-Corridor, 27-Agenten-ABM) hatte
`COUPLED` über ein geteiltes Zeitfenster belegt (`docs/EMERGENZ_DOSSIER.md`).
Die offene Frage war, ob die **Gewaltenteilung** als alternatives Kopplungsmuster
ebenfalls Kuramoto-Phasenkohärenz erzeugt — oder ob sie eine andere Kopplungsart ist.

## 2. Das System

9 Wirtschaftsagenten in drei Klassen mit exklusiven Rechten und Defiziten
(Gewaltenteilung; Details in `agents_b2g/wirtschaft/`):

| Klasse | Agenten | Exklusive Rechte | Defizite → Delegationspfad |
|---|---|---|---|
| **A — Kapital & Liquidität** | Liquidity, Treasury, Staking | Pool-Zugriff, Token-Transfer, Staking | Compliance/Risiko → C · Ledger → B |
| **B — Ausführung & Abwicklung** | Minter, Settlement, Paymaster | Mint, Ledger-Finalisierung, Fee-Einzug | Governance-Freigabe → C |
| **C — Governance & Risiko** | Burn, Retention, RiskAuditor | Z3, Freigabe/Block, `AGENT_DRAIN` | Ausführung → B |

**Bausteine 1–5:**

| # | Baustein | Inhalt |
|---|---|---|
| 1 | Fundament | `WirtschaftAgent` + 5 Basis-Module (StateKeeper, Gas, WORM-Log, Crypto, MessageBus) |
| 2 | Funktionsschranken | `may()` + Freigabe-Routing, 9 Kompetenz-Profile (default-deny) |
| 3 | 9 Agenten | konkrete Subklassen + verteilter Freigabe-Kreislauf |
| 4 | Routing | KlassenResolver (crc32-Tie-Break) + Envelope↔AgentMessage |
| 5 | Evaluator | Sim → AstroCore-Kuramoto-Adapter + IFI-Shuffle-Gegenprobe |

## 3. Methodik

- **Antrieb:** `WirtschaftsSimulation`, 200 Ticks, Agent-Frequenzen **2/3/4 Ticks**,
  Freigabe-Rearm alle 10 Ticks. → 651 Events über 9 Agenten.
- **Metrik:** Kuramoto-Ordnungsparameter `r` aus Ereignis-Phasen
  (Inter-Firing-Intervalle, lineare Interpolation).
- **Nullhypothese 1 — IAAFT (AstroCore):** erhält Leistungsspektrum +
  Amplitudenverteilung, randomisiert Phase. Für **kontinuierliche Zeitreihen** konzipiert.
- **Nullhypothese 2 — IFI-Shuffle (`agents_b2g/emergence/measure.py`):** mischt die
  Inter-Firing-Intervalle pro Agent, erhält die Intervall-Verteilung, randomisiert die
  zeitliche Anordnung. Die **passende Nullhypothese für Punktprozesse/Ereignis-Züge**.
- **Monte-Carlo:** `+1`-Korrektur `(k+1)/(n+1)`; p-Minimum bei 500 Surrogaten
  = `1/501 ≈ 0.002`. Ein `p=0.0000` ohne Korrektur wird nicht berichtet.

## 4. Ergebnis

| Pfad | r | p | Urteil |
|---|---|---|---|
| IAAFT (AstroCore) | 0.535 | < 0.002 | **scheinbar COUPLED** |
| IFI-Shuffle (measure.py) | 0.538 | 1.0000 (`r_obs ≈ surr_mean`) | **NO_COUPLING** |

*(Die leichte r-Differenz 0.535 vs. 0.538 stammt aus den unterschiedlichen
Phasen-Schätzern von AstroCore und `measure.py`; sie ändert nichts am Befund.)*

## 5. Analyse — das IAAFT-Artefakt

Der Widerspruch löst sich über die **Art der Nullhypothese**:

1. **Die Sim treibt die Agenten mit festen Frequenzen 2/3/4.** Dadurch entstehen
   hochperiodische Ereignis-Züge mit ausgeprägten Spektral-Spitzen.
2. **IAAFT erhält genau dieses Spektrum**, randomisiert aber die Phase. Bei stark
   periodischen Punktprozessen ist IAAFT nicht die passende Nullhypothese — die
   Surrogate unterschätzen die Kohärenz, die die reine Periodizität erzeugt.
   Folge: `r_obs` erscheint signifikant → **scheinbar COUPLED**.
3. **IFI-Shuffle erhält die Intervall-Verteilung** (und damit die Frequenz-Struktur)
   und randomisiert nur die zeitliche Anordnung. Hier gilt `r_obs ≈ surr_mean`:
   die beobachtete Kohärenz ist **vollständig durch die Intervall-/Periodizitäts-Struktur
   erklärt**. Es bleibt keine zusätzliche, durch die Gewaltenteilung erzeugte
   Phasen-Kopplung übrig. → **NO_COUPLING**.

**Kausal:** Die Periodizität der Sim-Frequenzen 2/3/4 ist die Quelle der scheinbaren
Kohärenz. Der Freigabe-Kreislauf (die eigentliche Gewaltenteilungs-Interaktion)
erzeugt darüber hinaus **keine** messbare Phasen-Synchronisation.

## 6. Interpretation — zwei Arten von Kopplung

Die Gewaltenteilung ist eine **organisatorische/funktionale Kopplung**:
Agenten hängen über Freigaben und Delegationen voneinander ab (A braucht C, C weist B an).
Das strukturiert **Zuständigkeiten und Abhängigkeiten** — aber es erzeugt **keine
Kuramoto-Phasenkohärenz**. Das ist keine Schwäche des Systems, sondern eine präzise
Aussage über die *Art* der Kopplung.

> **Gewaltenteilung = organisatorische Kopplung. Keine Kuramoto-Phasenkohärenz.**

## 7. Abgrenzung zum Fire-Corridor

| | Fire-Corridor (27-ABM) | Gewaltenteilung (9-Agenten) |
|---|---|---|
| Kopplungsmechanismus | geteiltes Zeitfenster | Freigabe/Delegation |
| Kuramoto (passende Null) | **COUPLED** | **NO_COUPLING** |
| Art der Emergenz | **Timing-Emergenz** (belegt) | organisatorische Kopplung |

Der **Fire-Corridor bleibt die belegte Timing-Emergenz** des Projekts. Die
Gewaltenteilung ergänzt sie um eine funktionale, nicht-oszillatorische Kopplungsart.
Beide sind valide; sie sind **verschieden**, und dieses Dossier grenzt sie sauber ab.

## 8. Unabhängige Replikation — Frequenz-Nullmodell (AstroCore, 2026-08-17)

Dieselbe IAAFT-Falle trat in der zweiten Projekthälfte unabhängig auf:
Sonne vs. gleichperiodischer Oszillator (`indep_same`, alte Kontrolle `sun+0.25`)
bekam IAAFT **p=0.0020 SIG** — das alte Nullmodell konnte **nicht nein sagen**.

Ein Frequenz-Nullmodell (Validierung 5/5, Nachtrag in
[`PHASENKOPPLUNG.md`](/Volumes/THX_CORE_16TB/cherrystudio_projekte/astrocore/PHASENKOPPLUNG.md))
korrigiert beide Falsch-Positiven auf n.s.
und erkennt echtes Entrainment, sobald der Treiber fluktuiert
(verrauschter Treiber: eingeregelt **freq p=0.0040 SIG**, unabhängig gleiche
Periode **p=0.5669 n.s.**). ETH-Epoche unverändert n.s. (Periodenfaktor ~3385,
R=0.0002).

**Lehre (beide Hälften):** Die Grenze ist eine Eigenschaft der **Daten**, nicht
des Verfahrens. Gegen einen rauschfreien, streng periodischen Treiber gibt es
keine Signatur — Kopplungsaussagen sind nur zwischen Quellen *verschiedener*
Grundperiode interpretierbar. IAAFT auf gemeinsamer Periode ist in beiden
Projekthälften dasselbe Artefakt.

## 9. Einschränkungen & Ausblick

- Der Befund gilt für den konkreten Antrieb (Frequenzen 2/3/4, Rearm 10). Andere
  Antriebe (stochastische Frequenzen, lastabhängiges Ticken) sind nicht getestet.
- **Ausblick A:** stochastischer Antrieb, um Periodizität als Confound zu entfernen
  und die Gewaltenteilungs-Kopplung isoliert zu testen.
- **Ausblick B:** andere Kohärenz-Maße für organisatorische Kopplung
  (z. B. Kreuzkorrelation der Freigabe-Sequenzen, Graph-Metriken des Abhängigkeits-Graphen)
  statt Kuramoto — Kuramoto misst Oszillator-Synchronisation, nicht Abhängigkeits-Struktur.

## 10. Reproduktion

```bash
cd /Volumes/THX_OS_ULTRA\ -\ Data/Users/olivermueller/agent_x_storage

# Sim + IAAFT (AstroCore) — scheinbar COUPLED
python3 -m agents_b2g.wirtschaft.emergence_adapter

# IFI-Shuffle-Gegenprobe — NO_COUPLING
python3 scripts/cross_check_wirtschaft_ifi.py

# Test-Suiten (Bausteine 1–5 + Gegenprobe)
python3 -m pytest scripts/test_wirtschaft_base.py \
                  scripts/test_wirtschaft_schranken.py \
                  scripts/test_wirtschaft_agenten.py \
                  scripts/test_wirtschaft_routing.py \
                  scripts/test_wirtschaft_simulation.py \
                  scripts/test_wirtschaft_emergence.py -v
```
