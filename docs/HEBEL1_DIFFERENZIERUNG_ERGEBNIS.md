# Hebel 1 Follow-up — Evaluator-Differenzierung: Ergebnis-Dossier

**Status:** Abgeschlossen — Wirksamkeit auf realen Daten **NICHT_WIRKSAM** (Pre-Reg-konform), Divergenz-Kapazität der Regeln **GUT_WIRKSAM**
**Datum:** 2026-08-17
**Pre-Registration:** `docs/HEBEL1_DIFFERENZIERUNG_PREREG.md`
**Charakter:** Vorab registrierte Auswertungsregel, ergebnissoffen durchgeführt.
Die Schwellen (0.01 / 0.10 / 0.30) wurden **NICHT** nachjustiert.
**Artefakt:** `hebel1_differenzierung_ergebnis.json` (gitignored)
**Tests:** `scripts/test_hebel1_differenzierung.py` — 11/11;
`scripts/test_evaluator_redundancy.py` — 4/4 (Strictness tot, Routing 1-von-9)

---

## 1. Hypothese und vorab registrierte Regel

Aus `HEBEL1_DIFFERENZIERUNG_PREREG.md`:

- **Hypothese:** Differenzierung (verschiedene Regeln auf denselben Feldern) erhöht
  die paarweise Uneinigkeitsrate von ≡ 0 auf einen Wert über der Wirksamkeitsschwelle.
- **Wirksamkeitsmetrik:** paarweise Uneinigkeitsrate über alle C(9,2)=36 Paare.
- **Schwellen (fixiert):** < 0.01 NICHT_WIRKSAM · 0.01–0.10 TEILWEISE_WIRKSAM ·
  0.10–0.30 GUT_WIRKSAM · > 0.30 KONSISTENZ_WARNUNG.
- **Strategie 1:** verschiedene Regeln auf denselben Feldern (`net_amount`,
  `tax_amount`, `retention_amount`, `gross_amount`, `inflated`, `contract_id`),
  keine Live-Calls ins Compliance-Modul, kein immer-PASS für E05/E06/E07.
- **Messung:** Replay derselben TX an alle neun (Fan-out), nicht das 1-von-9-Routing.
- **Zwei Datensätze:** (a) natürliche Provider-OFFERs, (b) angereicherte Grenzfälle.

## 2. Ergebnis

### Dataset (a): natural_provider_offers — Wirksamkeit auf realen Daten

| Metrik | Wert |
|---|---|
| Source | `provider_capture cycles=128` |
| Transactions | 249 |
| Inflated | 50 |
| Pairwise disagreement rate | **0.000000** |
| Classification | **NICHT_WIRKSAM** |
| Dead rules | `[]` (keine) |
| Fail counts | **alle neun Regeln: 50** |

### Dataset (b): enriched_edge_cases — Divergenz-Kapazität der Regeln

| Metrik | Wert |
|---|---|
| Transactions | 10 |
| Pairwise disagreement rate | **0.277778** |
| Classification | **GUT_WIRKSAM** |
| Dead rules | `[]` (keine) |
| Fail counts | E01:1 E02:1 E03:2 E04:3 E05:3 E06:1 E07:3 E08:1 E09:4 |

## 3. Interpretation: Datenverteilung, nicht tote Regeln

Das scheinbare Paradox — Regeln können divergieren, tun es aber auf realen Daten
nicht — löst sich über die Datenverteilung auf:

- Die **199 cleanen OFFERs** haben `delta ≈ 0` und plausible Werte → **alle neun
  Regeln PASSen**.
- Die **50 inflated OFFERs** haben `|Δ| ≈ 3%` → **alle neun Regeln FAILen am
  Balance-Gate** (`abs(delta) <= 0.01`, der erste Check in jeder Regel), **bevor**
  die spezifische Prüflogik überhaupt erreicht wird.

Die Uneinigkeit ≡ 0 ist daher eine Eigenschaft der **Datenverteilung**, nicht der
Regeln. Die Regeln sind nicht tot — der Dead-Rule-Detektor zeigt `[]`, und alle
neun Regeln FAILen auf exakt denselben 50 inflated OFFERs. Aber sie FAILen
**gleichzeitig und aus demselben Grund** (Balance-Gate), daher entsteht keine
paarweise Uneinigkeit.

Der **enriched-Datensatz beweist die Divergenz-Kapazität**: Auf Grenzfällen, die
den Balance-Check PASSen, aber eine spezifische Prüfung verletzen (hohe Steuerrate,
hohe Retention, kurzes `contract_id`, etc.), divergieren die Regeln wie entworfen
(GUT_WIRKSAM, keine toten Regeln, Fail-Counts über alle neun verteilt).

## 4. Der zentrale Befund: Der Balance-Check ist der dominante Diskriminator

Die wichtigste strukturelle Erkenntnis dieser Messung:

> **Der Balance-Check (`abs(delta) <= 0.01`) trennt die natürlichen OFFERs
> perfekt in „clean" und „inflated". Weil alle neun Regeln mit diesem Check
> beginnen, schlagen alle auf den inflated OFFERs gemeinsam fehl. Die
> spezifische Prüflogik (Steuerrate, Retention, Format, etc.) kommt nur zum
> Tragen, wenn der Balance-Check PASSt — und das ist bei den inflated OFFERs
> nie der Fall.**

Das bedeutet: Auf der aktuellen natürlichen Datenverteilung ist der Balance-Check
**hinreichend**, um die inflated OFFERs zu erkennen. Die spezifischen Prüfungen
sind auf diesen Daten **redundant**, weil es keine Transaktion gibt, die den
Balance-Check PASSt, aber eine spezifische Prüfung FAILt.

Die Differenzierung wird erst dann funktional wirksam, wenn die Daten Transaktionen
enthalten, die **arithmetisch ausgeglichen, aber inhaltlich suspekt** sind (z.B.
korrekte Summe, aber Steuerrate 40%, oder Retention 15%). Solche Transaktionen
fehlen in den natürlichen Provider-OFFERs.

## 5. Implikationen für Hebel 1

Das ursprüngliche Hebel-1-Problem war: neun identische Evaluatoren, tote Strictness,
Uneinigkeit ≡ 0. Die Lösung war: Regeln differenzieren. Das Ergebnis zeigt eine
**zweigeteilte Auflösung**:

- **Das strukturelle Problem ist gelöst.** Die Regeln sind jetzt genuinely
  verschieden (bewiesen durch enriched: GUT_WIRKSAM, keine toten Regeln,
  verschiedene Fail-Counts). Die tote Strictness und die identische Regel sind
  beseitigt.
- **Das funktionale Problem ist auf den natürlichen Daten nicht gelöst.** Die
  Evaluatoren produzieren auf den realen OFFERs weiterhin identische Verdikte,
  weil die Datenverteilung die Unterschiede nicht ausreizt.

Die Differenzierung ist damit eine **notwendige, aber nicht hinreichende** Bedingung
für wirksame Differenzierung. Sie ist technisch korrekt, aber ihr funktionaler
Nutzen hängt von der Datenverteilung ab.

## 6. Methodische Caveats

1. **Uneinigkeitsrate ≠ Qualität:** Die Messung zeigt Unabhängigkeit (oder deren
   Fehlen), nicht Korrektheit. Eine hohe Uneinigkeit wäre nicht automatisch besser
   gewesen; eine niedrige ist nicht automatisch schlechter.
2. **Balance-Check-Dominanz ist eine Design-Eigenschaft:** Dass alle Regeln mit
   dem Balance-Check beginnen, ist gewollt (arithmetische Integrität als
   Grundvoraussetzung). Es ist kein Bug, begrenzt aber die Wirksamkeit der
   spezifischen Prüfungen auf Daten, die den Balance-Check PASSen.
3. **Datensatz-Abhängigkeit:** Das Ergebnis hängt fundamental von der
   Datenverteilung ab. Ein ProviderAgent, der auch OFFERs mit ausgeglichener
   Bilanz, aber suspekten Einzelwerten erzeugt, würde ein anderes Ergebnis liefern.
4. **Keine Schwellen-Nachjustierung:** Die Pre-Reg-Schwellen wurden nicht
   angepasst. Das Ergebnis NICHT_WIRKSAM auf realen Daten ist Pre-Reg-konform
   und wird als solches akzeptiert.

## 7. Nächste Schritte (Optionen)

1. **Ergebnis akzeptieren:** Differenzierung technisch korrekt, auf aktueller
   Datenverteilung funktional wirkungslos. Kein unmittelbarer Handlungsbedarf.
2. **Datenverteilung untersuchen:** OFFERs mit ausgeglichener Bilanz, aber
   suspekten Einzelwerten — falls realistisch, ProviderAgent erweitern und
   Messung wiederholen (neue Pre-Reg, falls Schwellen/Regeln geändert werden).
3. **Balance-Check-Rolle überdenken:** Dominanter Diskriminator vs. differenzierte
   Fehlerklassen auch bei Balance-Verletzung — nur mit neuer Pre-Reg.
4. **Hebel 4 (Plastizität):** Nächster Hebel der Serie, wenn strukturelle
   Anpassungsfähigkeit adressiert werden soll.

## 8. Reproduktion

```bash
cd /Volumes/THX_OS_ULTRA\ -\ Data/Users/olivermueller/agent_x_storage

# Tests (inkl. act()-Registry + Strictness-Test)
python3 -m pytest scripts/test_hebel1_differenzierung.py scripts/test_evaluator_redundancy.py -v

# Messung: natürliche Capture (cycles=128) + enriched
python3 scripts/run_hebel1_differenzierung_messung.py --cycles 128
# oder mit bestehendem Dump:
python3 scripts/run_hebel1_differenzierung_messung.py natural_offers.json
```
