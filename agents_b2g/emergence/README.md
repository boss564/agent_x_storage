# Emergenz-Messung für Agentenschwärme

Drei Kennzahlen, die rot werden können. Sie beantworten getrennt, was „der
Schwarm erlebt Vernetzung" behaupten würde — und keine von ihnen kann durch
bloßes Hinzufügen weiterer Agenten grün werden.

```bash
python3 agents_b2g/emergence/self_test.py        # zuerst: sieht das Werkzeug?
python3 agents_b2g/emergence/adapter_agentx.py 128   # dann: was zeigt der Schwarm?
```

## Was gemessen wird

| Kennzahl | Frage | Rot bei |
|----------|-------|---------|
| **Divergenz D_dyn** | Unterscheiden sich die Agenten in dem, was sie *erwerben* — nicht in dem, wie sie *konfiguriert* wurden? | D_dyn ≈ 0 |
| **Graphstruktur** | Hat der Interaktionsgraph Struktur, die ein Zufallsgraph gleicher Gradsequenz nicht auch hätte? | \|z\| < 2 |
| **Kuramoto r** | Schwingen die Agenten aufeinander ein, stärker als phasenrandomisierte Surrogate erklären? | p ≥ 0.05 |

Statische und dynamische Zustandsdimensionen werden getrennt. Unterschiede in
`amount_multiplier` oder `strictness` sind Konfiguration — sie entstehen beim
Anlegen, nicht im Lauf. Nur `D_dyn` zählt.

Vor der Phasenschätzung wird linear detrendet. Ohne das dominieren kumulative
Größen (`total_volume`, `milestone_count`) die Hilbert-Transformation, und
alle Agenten wirken gleichphasig, obwohl sie unabhängig laufen. Der Selbsttest
hat genau diesen Fehler gefangen.

## Interpretationsmatrix

| D_dyn | Kuramoto | Urteil | Bedeutung |
|-------|----------|--------|-----------|
| ≈ 0 | beliebig | `TRIVIAL_SYNC` | Ein Prozess unter N Namen. r = 1 ist tautologisch. |
| > 0 | n.s. | `NO_COUPLING` | Agenten arbeiten nebeneinander, nicht miteinander. |
| > 0 | p < 0.05 | `COUPLED` | Kopplung nachgewiesen. |

Perfekte Synchronie identischer Agenten ist **keine** Emergenz. Deshalb ist
`TRIVIAL_SYNC` ein eigenes Urteil und nicht der Bestfall.

## Selbsttest

Fünf synthetische Fälle mit bekannter Grundwahrheit — identische Agenten,
unabhängige Oszillatoren, Kuramoto-gekoppelte Oszillatoren (K = 6), Stern- und
Zufallstopologie. Findet das Werkzeug hier nicht das Richtige, ist jede Messung
am echten Schwarm wertlos. Der Selbsttest hat während der Entwicklung zwei
eigene Fehler gefunden (Nabenmaß über Nachrichtenenden statt Nachrichten;
fehlendes Detrending vor der Phasenschätzung).

## Baseline: 27-Agenten-ABM, 128 Ticks (Stand 2026-08-16)

```
Agenten 27 · 15 Zustandsdimensionen · 51.660 zugestellte Nachrichten

D_dyn        0.947      Agenten divergieren dynamisch
Graph        Dichte 0.577 · hub_share 0.175 (Zufallserwartung 0.074)
             Nullmodell uninformativ — bei dieser Dichte kann gradbewahrendes
             Rewiring die Struktur nicht verändern
Kuramoto     r = 0.671  p = 0.582  (Dimension: total_volume)

Urteil:      NO_COUPLING
```

Die Agenten unterscheiden sich und arbeiten, aber ihre Rhythmen sind
voneinander unabhängig. Es gibt keine wechselseitige Einregelung.

## Zwei strukturelle Befunde aus der Messung

**1. `TickController.run()` stellt für diese Agenten nichts zu.**
Die Agenten adressieren Rollen (`receiver="evaluator"`, `"economic"`), der
Controller stellt aber nur bei `agent.id == msg.receiver` zu. Im 27-Agenten-Modus
heißt kein Agent so. Das Routing lebt stattdessen in `scripts/demo_producer_cluster.py`
als Archetyp-Dispatcher. Wer den Controller wiederverwendet, bekommt einen
stillen No-op. Der Adapter bildet deshalb das Routing der Demo nach.

**2. Die Arbeitsverteilung ist nicht reproduzierbar.** ~~BEHOBEN in 0.24.1~~
~~`idx = hash(contract_id) % len(economics)`~~ → jetzt `zlib.crc32(cid.encode()) % len(economics)`
in Adapter **und** Demo. PYTHONHASHSEED-unabhängig verifiziert.

## Was welche Kennzahl bewegen würde

**Damit das Nullmodell aussagekräftig wird** (Dichte senken): ~~Agenten müssen
konkrete Partner wählen statt an Rollen zu senden.~~ **BEHOBEN TIER 1 (0.24.1+):**
`StickySelector` / Least-Loaded; Dichte ≈0.13; Graph-z-Scores informativ.

**Damit Kuramoto etwas zeigen kann** (Kopplung erzeugen): Die Taktrate eines
Agenten muss von dem abhängen, was er bei anderen beobachtet — Rückstau aus
Queue-Längen, Gaspreise, Reputationsschwellen. Derzeit tickt jeder Agent
unbeeindruckt von den übrigen; dann *kann* keine Einregelung entstehen.

**Damit D_dyn mehr aussagt** (Differenzierung innerhalb der Rollen): Der
aktuelle Wert stammt überwiegend aus dem Unterschied zwischen den drei
Archetypen. Eine Divergenz *innerhalb* einer Rolle wäre die schärfere Frage —
neun Evaluatoren, die alle dasselbe prüfen, sind neun Kopien.

Die vorhandenen Bausteine dafür liegen bereit: `gas/` (Agenten können
verhungern), `valhalla/` (Reputation akkumuliert über Läufe), `crew/did_registry.py`
(Sperren mit Gedächtnis). Das sind die drei Stellen, an denen aus gleichen
Startbedingungen verschiedene Zukünfte entstehen.

## Methodische Herkunft

Resultierender Vektor, Rayleigh-Logik, Surrogatverfahren und die Warnung vor
multiplen Vergleichen stammen aus `astrocore/PHASENKOPPLUNG.md` (cherrystudio_projekte).
Was dort für Blockchain-Phasenquellen entworfen wurde, ist hier das Instrument
für die Frage, ob 27 Agenten sich aufeinander einschwingen.

## Kampagne 2026-08-16 — abgeschlossen

**Gate COUPLED** am Feuer-Korridor (Opt-in, nicht Default). Dossier:
[`docs/EMERGENZ_DOSSIER.md`](../../docs/EMERGENZ_DOSSIER.md).

```bash
# Nachweis reproduzieren (Opt-in)
python3 agents_b2g/emergence/adapter_agentx.py 512 --corridor 2 --gap 1

# Default: ungekoppelt
python3 agents_b2g/emergence/adapter_agentx.py 128
```
