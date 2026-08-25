# Hebel 1 Follow-up — Evaluator-Differenzierung (Pre-Registration)

**Status:** Pre-Registration — fixiert vor Implementierung, vor Datenblick.
**Datum:** 2026-08-17
**Bezug:** `docs/HEBEL1_EVALUATOR_REDUNDANZ_PREREG.md` (Ausgangspunkt),
Hebel-1-Befund in `scripts/test_evaluator_redundancy.py` (Rate≡0, tote Strictness).
**Sequenz:** Hebel 4 (Plastizität) bleibt zurückgestellt. Dieser Hebel adressiert
die Wurzel der Redundanz und ist Voraussetzung für Hebel-2-Wirksamkeit (Zustand).

---

## Bestätigte Entscheidungen (2026-08-17, vor Implementierung)

| Frage | Entscheidung |
|---|---|
| Wirksamkeitsschwellen | **0.01 / 0.10 / 0.30** bestätigt (siehe Begründung unten) |
| Strategie | **Strategie 1** (Regel-Differenzierung), mit Payload-Scope |
| IoT-/Geofence-Daten | **Nicht im Cluster-OFFER.** Keine Live-Anbindung in dieser Runde. |

Kein Nachjustieren dieser drei Punkte nach dem Datenblick.

---

## Ausgangspunkt (Hebel-1-Befund)

- Neun Evaluatoren (E01–E09), alle Instanzen derselben Klasse `EvaluatorAgent`.
- Alle wenden dieselbe Regel an: `holds = abs(delta) <= 0.01` (inline in `act()`).
- `strictness` ist tote Konfiguration (gesetzt, nie gelesen).
- Routing ist 1-von-9 via `StickySelector` (`hash(contract_id) % 9`).
- **Uneinigkeitsrate per Konstruktion ≡ 0** — neun Prüfer sind Replikation, nicht Verifikation.
- Die Evaluatoren-Namen (bho-checker, z3-prover, gobd-auditor, fraud-detector,
  tax-auditor, geofence, iot-verifier, qes-validator, compliance) deuten auf
  differenzierte Prüfungen hin, die nie implementiert wurden — dieselbe
  Kommentar-Code-Divergenz wie bei der toten Strictness.

## Hypothese

Differenzierung (Regeln ODER Datenquellen ODER Reduktion) erhöht die
Uneinigkeitsrate von ≡0 auf einen messbaren Wert über der Wirksamkeitsschwelle.

**Wichtig:** Diese Pre-Reg misst **Unabhängigkeit** (Uneinigkeitsrate), NICHT
**Qualität** (Korrektheit der Prüfungen). Ohne Ground Truth ist Korrektheit nicht
messbar; die Uneinigkeitsrate ist ein Proxy für Unabhängigkeit. Dieser Scope ist
bewusst und wird im Ergebnis-Dossier dokumentiert.

---

## Datenlage (Cluster-OFFER) — Scope für Strategie 1

`ProviderAgent.act()` sendet nur:

`contract_id`, `gross_amount`, `net_amount`, `tax_amount`, `retention_amount`, `inflated`

**Nicht im Payload:** IoT-Telemetrie, GPS/H3-Zellen, QES/X.509, GoBD-Hash-Ketten,
BZSt-IBANs, Fotos/EXIF. Die Compliance-Subagenten (PoPWEvidenceAuditor,
QESCryptoVerifier, GoBDIntegrityChecker, …) können in dieser Runde **nicht**
live aufgerufen werden — das wäre Strategie 2.

Konsequenz: Strategie 1 bedeutet **verschiedene Regeln auf denselben sechs Feldern**,
semantisch analog zu den Namens-Prüfungen, nicht ein Live-Call ins Compliance-Modul.
Ein immer-PASS-Stub für E05/E06/E07 wäre wieder tote Differenzierung und ist
**unzulässig**.

---

## Drei Differenzierungs-Strategien

### Strategie 1: Regel-Differenzierung (gewählt, erster Schritt)

Jeder Evaluator bekommt eine andere Prüfregel auf dem **gleichen OFFER-Payload**.
Mapping zu Compliance-Prüfungen ist analog, nicht live.

| Evaluator | Intendierte Prüfung | Payload-Regel (Scope dieser Runde) |
|---|---|---|
| E01-bho-checker | BHO-Zero-Sum | `abs(gross − (net+tax+ret)) ≤ 0.01` (Status-quo) |
| E02-z3-prover | Z3-Invarianz | Exakte Erhaltung: `gross == net+tax+ret` (kein ε-Band) — **nur** wenn das nicht der einzige Unterschied zu E01 bleibt; sonst zusätzliche Komponenten-Invariante (alle Beträge ≥ 0) |
| E03-gobd-auditor | GoBD-Vollständigkeit | Pflichtfelder vorhanden, Typen numerisch, `contract_id` nicht leer (Vollständigkeit, kein Hash) |
| E04-compliance | VOB/B §17 Einbehalt | `abs(retention/gross − 0.05) ≤ 0.001` (gross>0) |
| E05-iot-verifier | Evidenz-Kohärenz (Proxy) | `inflated` konsistent mit BHO-Verletzung: inflated ⇒ Δ>0.01; nicht-inflated ⇒ Δ≤0.01 |
| E06-qes-validator | Payload-Integrität (Proxy) | Beträge endlich, nicht-negativ, keine NaN/Inf |
| E07-geofence | Shard-/Rollen-Konsistenz (Proxy) | `contract_id` beginnt mit bekanntem Provider-Präfix (kein GPS) |
| E08-fraud-detector | Plausibilität | Round-Number / Extrem-Ratio (z.B. net/gross außerhalb [0.70, 0.90]) |
| E09-tax-auditor | Steuer-Split | `abs(tax/gross − 0.15) ≤ 0.001` (gross>0); analog §-Split, kein BZSt |

**Erwarteter Effekt:** Verschiedene Aspekte derselben Zahlen → Uneinigkeit, wenn
eine Regel greift und eine andere nicht.

**Nicht in dieser Runde:** Live-Z3-HTTP, Live-IoT, Live-QES, Live-Geofence.

### Strategie 2: Datenquellen-Differenzierung (zurückgestellt)

Neue Payload-Felder oder Anbindung Telemetrie/GPS. Aufwand hoch. Nur wenn
Strategie 1 NICHT WIRKSAM.

### Strategie 3: Reduktion (zurückgestellt)

Weniger, aber verschiedene Evaluatoren. Trade-off: Redundanzverlust ist bei
identischen Prüfern (Hebel 1) ohnehin wertlos. Nur wenn Strategie 1 NICHT WIRKSAM
oder wenn Payload-Proxies für E05–E07 als zu dünn bewertet werden — das wäre
eine **neue** Pre-Reg, keine Umdeutung dieser.

---

## Wirksamkeitsmetrik: Uneinigkeitsrate

### Definition (paarweise)

Für jede Transaktion `t` und jedes Paar `(i, j)` von Evaluatoren:

`disagreement(i, j, t) = 1` wenn `verdict_i(t) != verdict_j(t)`, sonst `0`.

`Uneinigkeitsrate = mean über alle t und alle Paare (i, j)`

C(9,2) = 36 Paare. Bei Reduktion auf N: C(N,2).

### Messbedingung (Routing)

Produktion/Cluster routet **1-von-9**. Paarweise Uneinigkeit ist dann **undefiniert**
(pro TX nur ein Verdikt). Die Messung **muss** Fan-out oder Replay derselben TX
an alle Evaluatoren nutzen. Das ist ein Mess-Harness, keine Produktionsänderung
in dieser Runde.

### Nullmodell

- **Nullmodell (identisch):** Neun identische Evaluatoren → Uneinigkeitsrate ≡ 0.
  Das ist der aktuelle Zustand (Hebel-1-Befund).
- **Referenz (zufällig):** Neun zufällig urteilende Evaluatoren → nahe dem
  theoretischen Maximum. Oberes Ende, kein Ziel.

### Wirksamkeitsschwellen (fixiert)

| Uneinigkeitsrate | Interpretation | Entscheidung |
|---|---|---|
| < 0.01 | Faktisch identisch | Differenzierung wirkt NICHT |
| 0.01 – 0.10 | Leichte Differenzierung | Differenzierung wirkt TEILWEISE |
| 0.10 – 0.30 | Moderate Differenzierung | Differenzierung wirkt GUT |
| > 0.30 | Starke Differenzierung | Differenzierung wirkt, aber Konsistenz prüfen |

**Begründung 0.01 (untere Schwelle):** Paarweises Mittel ist strenger als
„irgendein Paar pro TX“. Ein einziges Paar, das in 30 % der TXs uneinig ist,
liefert 0.30/36 ≈ 0.008 → NICHT WIRKSAM. Wirksam ab grob: ein Paar fast immer
uneinig (1/36 ≈ 0.028) **oder** mehrere Evaluatoren, die häufiger divergieren.
Das ist Absicht: ein seltener Einzelfall-Check zählt nicht als Differenzierung.

**0.10 / 0.30:** Bandbreiten für Stärke; >0.30 ist Warnschwelle (Inkonsistenz),
keine Erfolgsschwelle.

Diese Schwellen werden nach dem Datenblick NICHT angepasst.

## Entscheidungsregel (strikt, ohne Nachjustieren)

1. **Strategie-Wahl:** Strategie 1 zuerst (Payload-Scope oben). Wenn Rate < 0.01:
   Strategie 2 oder 3 in einer **neuen** Pre-Reg.
2. **Wirksamkeits-Bewertung:**
   - **WIRKSAM:** Rate ≥ 0.01
   - **NICHT WIRKSAM:** Rate < 0.01
   - **KONSISTENZ-WARNUNG:** Rate > 0.30 (Konsistenz prüfen, nicht automatisch Erfolg)
3. **Kein Nachjustieren.** Ein „fast wirksam“ wird nicht umgedeutet.

## Methodische Caveats (im Ergebnis-Dossier dokumentieren)

1. **Uneinigkeitsrate ≠ Qualität.** Unabhängigkeit, nicht Korrektheit.
2. **Ground-Truth-Problem.** Keine Messung, ob Verdikte richtig sind.
3. **Payload-Proxies ≠ intendierte Prüfung.** E05/E06/E07 ohne IoT/QES/GPS sind
   Analogien. Wirksamkeits-WIRKSAM heißt nicht „Geofence ist implementiert“.
4. **Reduktion vs. Redundanz.** Nur falls Strategie 1 scheitert; Trade-off bewusst.
5. **Hebel-2-Zusammenhang.** Differenzierung kann Zustand (verschiedene Laufzeiten)
   erzeugen — Nebeneffekt, nicht primäres Ziel.
6. **Fan-out nur Messung.** Sticky 1-von-9 in Produktion bleibt unangetastet,
   solange nicht separat pre-registriert.

## Sequenzierung

1. **Jetzt (erledigt):** Pre-Reg fixiert (Schwellen, Strategie, Payload-Scope).
2. **Dann:** Strategie 1 implementieren (Regel pro Evaluator, Adaption `act()`).
3. **Dann:** Uneinigkeitsrate messen (Fan-out/Replay, alle Paare × TXs).
4. **Dann:** Gegen Schwelle bewerten. Ergebnis-Dossier.
5. **Falls NICHT WIRKSAM:** Strategie 2 oder 3, neue Pre-Reg.
6. **Falls WIRKSAM:** Hebel 2 neu bewerten; dann ggf. Hebel 4.
