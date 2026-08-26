# Threat Model — Agent X unter Post-Quanten-Bedingungen

**Arbeitstitel:** `THREAT_MODEL_POST_QUANTUM_v0`  
**Status:** ANALYSE (kein DRAFT · keine Pre-Reg · keine Sweep-Planung)  
**Charakter:** Bedrohungsanalyse auf bestehender Architektur — Threat-Surface-Landkarte  
**Abgrenzung:** Neuer Strang. Keine Fortsetzung der Kopplungsserie.  
**Stand:** 2026-08-25 · Serie-Schluss `f0178aa5` / Tag `v1.0-kopplung-serie-closed`

---

## 0. Zweck und Grenzen

### 0.1 Was dieses Dokument ist

Systematische Bedrohungsmatrix für Agent X (Kurier-Metapher als Surface-Landkarte),
abgestützt auf bestehende Module: Kanten-Ledger, Wave 33 PQC, Bunker-HSM, BHO,
GoBD-WORM. Ableitung von Gegenmaßnahmen — **keine** neue Emergenzfrage.

### 0.2 Was es nicht ist

- Kein DRAFT / keine Pre-Reg / keine Versuchsreihe  
- Keine Fortsetzung von `KOPPLUNG_*`  
- Keine Behauptung, Quantenrechner seien ein Allzweck-Angreifer  

### 0.3 Quantenspezifität (bindende Disziplin)

| Vektor | Quantenspezifisch überlegen? | Begründung |
|--------|------------------------------|------------|
| **Shor** (inkl. kurvenbasierte SNARK-Soundness) | **Ja** | Bricht RSA / ECC / DH; trifft auch pairing-basierte Beweise |
| Inverse Rekonstruktion | **Nein** | Zeitreihen / ML — klassisch |
| Timing-Poisoning (Delay Attacks auf \(\ell_{ij}\)) | **Nein** | Aktiver Side-Channel in verteilten Systemen |
| Sybil über `interaction_count` | **Nein** | Spam ohne Volumenbezug |
| Quantensensorik | Nein (operativ) | Physische Nähe / klassische Sensorik |
| Grover auf Graph-Cut | **Nein** | Narrative Ausschmückung; Min-Cut / Betweenness klassisch polynomial |

Nur Shor (und damit verwandte kurvenbasierte Annahmen) ist nachweislich
quantenspezifisch. Alles andere als „Quantenbedrohung“ zu verkaufen, wäre dieselbe
Falle wie der Eingangstext: Quantencomputer als Mythos statt als Krypto-Brecher.

---

## 1. Surface-Landkarte (Kurier ↔ Agent X)

| Kurier-Metapher | Agent-X-Entsprechung | Modul / Artefakt |
|-----------------|----------------------|------------------|
| 9 Kuriere | 9 Agenten (Rollen A/W/F bzw. Provider/Evaluator/Economic) | Swarm / Waves |
| Verschlüsselte Übergabezettel | Z3-Proofs + HSM-Signaturen | `services/z3_solver`, `agents_b2g/bunker` |
| Fahrzeiten \(S_{ij}=\ell_{ij}\) | Kanten-Latenzen | `kanten_ledger.py` · `avg_latency` |
| Anonyme Kontakte | \(E_{ij}\)-Kantenmatrix | Ledger 5-Komponenten |
| Dezentrale Übergaben | BHO-Nullsummen-Settlements | Treasury / Clearing |

### 1.1 Ertrag der Kopplungsserie als Angriffsflächen-Kartographie

Die versiegelte Serie war Kopplungsforschung — und nebenbei **Surface-Kartographie**:

| Ledger-Feld | Screen-Befund (Serie) | Relevanz für Threat |
|-------------|----------------------|---------------------|
| `avg_latency` | partnerselektiv (\|ρ\|≈0.35 bei φ_L) · **Vorher-Zustand** (EWMA) | **Primäre Vorhersagefläche** (Fahrzeit-Proxy) |
| `interaction_count` | partnerselektiv (\|ρ\|≈0.156) · **Vorher-Zustand** | Frequenz / Sticky-Partner |
| Knoten-Zustände | `NONE_CLOSE` (\|ρ\|≈1) | kaum partnerunterscheidend |

Das ist keine neue Emergenzfrage. Es benennt konkret, welche Felder unter
Vektor 1 (Inverse Rekonstruktion) stehen. **Zahlen der versiegelten Serie
gelten nur für die damalige Intake-Definition** (siehe §3.5.1 / §3.6).

---

## 2. Priorisierte Bedrohungsmatrix

| Prio | Vektor | Schwere | Quantenspez. | Kernaussage |
|-----:|--------|---------|:------------:|-------------|
| **1** | Inverse Rekonstruktion | **Hoch** | nein | Ledger-Historie → Verhaltensvorhersage |
| **1** | Timing-Poisoning (Delay Attacks) | **Hoch** | nein | Manipuliertes \(\ell_{ij}\) steuert abgeleitete Schwellen / \(\theta\) |
| **2** | Shor + HN-DL (+ SNARK-Soundness) | **Mittel** | **ja** | Harvest now; ab 2030+ Asymmetrie + pairing-SNARKs |
| **2** | Sybil über Interaktionszählung | **Mittel** | nein | `interaction_count` ohne Volumenbezug spam-bar |
| **3** | Graph-Cut / Mesh-Lahmlegung | Mittel | nein | Klassische Optimierung, nicht Grover |
| **4** | Physische OPSEC / Sensorik | Niedrig–mittel | nein | Überwachung, nicht „Quantenasphalt“ |

Entmythologisiert (kein eigener Schweregrad): Grover, Quantensensorik.

---

## 3. Primär — Inverse Rekonstruktion (klassisch, hoch)

### 3.1 Angreiferziel

Aus historischen Kantenzeitreihen vorhersagen: *wer trifft wen wann*  
(„Kurier 3 in 4 Minuten über die Ostbrücke“).

Voraussetzung: Lesezugriff oder Leak auf Ledger-/Telemetry-Historie, nicht auf
Quantenhardware.

### 3.2 Feldmapping \(E_{ij}\) / \(\ell_{ij}\)

Komponenten laut `KANTEN_LEDGER_v1` (`COMPONENT_NAMES`):

| Feld | Identifizierend? | Rauschbar? | Retention / WORM | Gegenmaßnahme (konkret) |
|------|:----------------:|:----------:|------------------|-------------------------|
| **`avg_latency`** | **Hoch** (partnerselektiv, Timing) | Ja (Export: Noise; **Intake:** Trimmed Mean / Median — M7) | Betriebsmetrik — nicht GoBD-pflichtig wie Buchung | DP auf Export; **kein** Roh-EWMA allein gegen Delay Attacks (→ §3.5 / M7) |
| **`interaction_count`** | **Hoch** (Frequenz, Sticky) | Ja (Rounding, Top-k Truncation) | Betriebsmetrik | Cap + Noise; **nicht** allein Trust steuern (→ §3.6 / M9) |
| `trust_score` (α,β) | Mittel | Ja | Intern | An BHO-Volumen koppeln (M9); Buckets im Export |
| `bilateral_balance` | **Hoch** (Wertfluss) | Eingeschränkt (BHO-Invariante!) | **GoBD / BHO** — WORM, Δ=0 | **Nicht** wegrauschen; Pseudonymisierung der Party-IDs; getrennte Audit- vs. Ops-Sichten |
| `edge_risk` | Mittel | Ja | Intern | Abgeleiteter Score, kurze TTL |
| Party-IDs \(i,j\) | **Hoch** | Nein (Identität) | GoBD-Bezug möglich | Pseudonyme / DIDs; getrennte Mapping-Tabelle mit strikter ACL |
| Sticky-Map / Partnerwahl | **Hoch** | Ja (selten) | Runtime | Nicht persistieren über Screening hinaus; Freeze nur in versiegelten Studienartefakten |

**Leitregel:** Die Frage ist nicht *ob* Anonymisierung, sondern **welches Feld,
welches Rauschen, welche Retention**.

- Identifizierende Ops-Felder (`avg_latency`, `interaction_count`): Rauschen + Aggregation.  
- Wertfelder (`bilateral_balance`): **keine** Verfälschung der BHO-Nullsumme — nur
  Identitätsabschirmung und Zugriffstrennung.  
- Versiegelte Sweep-Artefakte: HARKing-Sperre bleibt; keine Re-Analyse als
  „Threat-Trainingsdaten“ ohne neues Mandat.

### 3.3 Bestehende Anknüpfungspunkte

- Wave 15 / 25: ZK-Privacy / DSGVO-Schild (Citizen-facing)  
- GoBD-WORM: Audit-Trail — nicht Ops-Timing-Export  
- Ledger: Update nur bei Interaktion — Leak-Oberfläche = Persistenz + Export-API  

### 3.4 Residualrisiko

Selbst mit DP bleibt Graphstruktur (wer mit wem jemals interagierte) schwer zu
verbergen. Mesh-Redundanz und Rollenrotation mindern Nutzen der Vorhersage, löschen
sie nicht.

### 3.5 Timing-Poisoning — aktiver Side-Channel auf \(\ell_{ij}\) (Prio 1)

**Angriff:** Verzögerte oder künstlich gestreckte Antworten verzerren
`avg_latency` (EWMA in `LedgerBook.update`). Weil \(\ell_{ij}\) abgeleitete
Reaktions-/Schwellengrößen speist (u. a. \(\theta\)-Skalierung in \(R_{ij}\),
Intervallmodulation), ist das **kein** bloßes Leak, sondern ein **aktiver**
Steuerkanal.

**Gegenmaßnahme M7:** Intake-Robustheit statt nur Export-Noise:

- Latenzproben pro Kante als Fenster speichern (nicht nur EWMA-Punkt).  
- **Trimmed Mean** oder **Median** über das Fenster für das kanonische
  \(\ell_{ij}\); EWMA höchstens als sekundärer Trend.  
- Ausreißer-Regel nur bei ausreichender Fenstergröße (→ §3.5.2).  
- Anker: `agents_b2g/emergence/kanten_ledger.py` (`LATENCY_EWMA` heute = 0.3).

#### 3.5.1 Messkontinuität — Serie beschreibt den Vorher-Zustand

M7 **ändert die Größe**, auf der die versiegelte Kopplungsserie beruht.
`avg_latency` war L1 in `KOPPLUNG_LEDGER_v1` / φ_L-Signal mit
`LATENCY_EWMA = 0.3` und sticky-ℓ \|ρ\| ≈ **0,348**. Trimmed Mean / Median
über ein Fenster hat andere Statistik (geringere Varianz, stärkere Glättung,
weniger Einfluss einzelner Beobachtungen) und wirkt vermutlich **gegen**
Partnerselektivität: Glättung entfernt idiosynkratische Ausschläge, die Kanten
unterscheiden. \|ρ\| = 0,348 könnte nach M7 näher an der 0,90-Schwelle liegen.

Das ist **kein** Argument gegen M7 — Schutz vor einem aktiven Steuerkanal wiegt
schwerer als eine Vorbedingung eines **geschlossenen** Strangs. Bindend:

> Die Messungen der Kopplungsserie beschreiben den **Vorher-Zustand** und
> übertragen sich nicht. Wer die Architekturfrage je wieder aufmacht, muss
> sticky-ℓ **neu messen** und darf 0,348 nicht zitieren.

Ohne diesen Satz wird in Monaten eine Zahl für eine Implementierung herangezogen,
die es dann nicht mehr gibt. HARKing-Sperre bleibt; Neuvermessung = neuer Strang.

#### 3.5.2 MAD-Regel — Mindestfenstergröße

`> k·MAD` setzt genügend Proben je Kante voraus. `KANTEN_LEDGER_v1` dokumentiert
bereits Untersampling (`bilateral_balance` n_corr = 9/64, `edge_risk` = 7/64;
S-G erst ab `n_corr ≥ 14` prüfbar). Auf kurzen Fenstern ist MAD instabil und
verwirft entweder zu viel oder nichts.

**Regel (bindend für M7-Implementierung):**

| Fenstergröße \(n\) | Verhalten |
|--------------------|-----------|
| \(n < n_{\min}\) (Vorschlag: \(n_{\min} = 14\), analog S-G) | **Kein** Trimming / kein MAD-Reject. \(\ell\) als „nicht bewertbar“ markieren **oder** Eskalation in `edge_risk` — nicht stillschweigend EWMA fortschreiben als „robust“. |
| \(n \ge n_{\min}\) | Trimmed Mean / Median + optional MAD-Filter |

Sonst greift die Robustheitsmaßnahme genau auf den **dünnen** Kanten nicht, die
ein Angreifer am billigsten bespielt.

#### 3.5.3 M7 als eigene Angriffsfläche — Mehrheit vs. Ausreißer

Ein Median verwirft Ausreißer; ein Angreifer, der die **Mehrheit** der Proben
auf einer Kante stellt, verschiebt den Median vollständig und wird dabei *nicht*
als Ausreißer erkannt. Robuste Schätzer schützen gegen wenige Extreme, nicht
gegen viele moderate Proben. Auf dünn belegten Kanten ist die Mehrheit billig.

**Natürliche Ergänzung zu M9:** Das **Gewicht einer Latenzprobe** soll am
Settlement-Bezug hängen (\(\Delta \neq 0\)), nicht nur an ihrer Existenz —
dieselbe Grundlage wie Trust (→ §3.7).

### 3.6 Sybil über `interaction_count` (Prio 2)

**Angriff:** Viele billige Interaktionen ohne Wertfluss blähen
`interaction_count` und damit indirekt Trust/Sticky auf.

**Gegenmaßnahme M9:** `trust_score` an **BHO-Volumen** koppeln:

- Trust-Update nur (oder dominant), wenn die Kante einen Settlement-Bezug mit
  \(\Delta \neq 0\) (echte Buchungsbewegung) hat — Spam ohne Volumen bleibt teuer
  bzw. wirkungslos.  
- `interaction_count` bleibt Ops-Metrik; steuert Trust nicht allein.  
- Anker: Ledger `trust_score` (α/β) + BHO-Invariante (Treasury / Clearing).

**Messkontinuität:** L2 sticky-ℓ \|ρ\| ≈ **0,156** gilt für den Vorher-Zustand
(Zählung jeder Interaktion). Trust an BHO-Volumen zu koppeln ändert, **was
gezählt / gewichtet wird** — dieselbe Regel wie §3.5.1: Zahl nicht auf
Post-M9-Architektur übertragen; Neuvermessung bei Wiederaufnahme.

### 3.7 Gemeinsame Grundlage M7 ∪ M9 — Einfluss ∝ Buchungsbewegung

M7 und M9 sollen **kein** Paar getrennter Mechanismen bleiben:

| Mechanismus | Heute (Risiko) | Ziel |
|-------------|----------------|------|
| Latenzprobe → \(\ell_{ij}\) | jede Probe gleich | Gewicht ∝ Settlement-Bezug (\(\Delta \neq 0\)), sonst nur `edge_risk` / „unbewertet“ |
| Interaktion → Trust | `interaction_count` spam-bar | Update ∝ BHO-Volumen (\(\Delta \neq 0\)) |

**Leitregel:** Einfluss auf Steuergrößen (\(\ell\), Trust) proportional zu echter
Buchungsbewegung. Existenz einer Nachricht allein reicht nicht.

---

## 4. Sekundär — Shor und Harvest-now-decrypt-later

### 4.1 Zwei verschiedene Dringlichkeiten

| Bedrohung | Zeithorizont | Was betroffen ist | Dringlichkeit |
|-----------|--------------|-------------------|---------------|
| **Shor bricht morgen RSA-2048** | NIST-Schätzung typ. **2030+** für kryptanalytisch relevante logische Qubits | Live-Auth, Signaturen, Key-Exchange *ab Kipppunkt* | Migration planen, nicht panisch rotieren |
| **Harvest now, decrypt later** | **Sofort** (Sammlung heute) | Alle Ciphertexte, die **10–15+ Jahre** noch sensibel sind | **Jetzt** PQC oder hybride KEM für Langzeitgeheimnisse |

HN-DL ist die operative Bedrohung 2026: Angreifer speichern TLS/Messenger/Archiv
heute und warten. Das ist **nicht** dasselbe wie „Shor ist morgen da“.

### 4.2 Datenklassen und Migrationspriorität

| Datenklasse | Sensibilität nach 10–15 J. | Maßnahme |
|-------------|----------------------------|----------|
| BHO / GoBD-Archiv, Verträge, Steuer | Hoch | Hybride KEM (klassisch + ML-KEM) für Archive at rest / in transit; Key-Rotation mit PQC |
| Session-Tokens, kurzlebige Ops | Niedrig | Klassisch akzeptabel bis Migrationsfenster |
| HSM-Signaturen (NitroKey / SoftHSM) | Hoch (Integrität) | ML-DSA / Dilithium-Pfad (Wave 33 bereits spezifiziert) |
| Z3-Proof-Artefakte | Mittel (Integrität > Geheimhaltung) | Signatur-PQC; Inhalt oft ohnehin verifizierbar |
| ZK-Settlement (Groth16/PLONK) | **Hoch (Soundness)** | **M8:** Migration Richtung STARK / hash-basiert |

### 4.3 SNARK-Soundness unter Shor (M8, Prio 2)

Kurvenbasierte SNARKs (Groth16, PLONK auf pairing-freundlichen Kurven) verlieren
unter Shor nicht nur Vertraulichkeit von Setup-Material, sondern **Soundness**:
gefälschte Beweise werden möglich. Das ist strengere Schadenklasse als
„Ciphertext später lesen“.

| Heute in Agent X | Risiko | Zielbild |
|------------------|--------|----------|
| Settlement / Protocol: `Groth16_BN254` | Soundness-Bruch ab Shor-Kipppunkt | Hash-basierte STARKs (FRI) |
| Wave 33: `zk_compression` (STARK/FRI, SHA3) | bereits PQ-freundlich spezifiziert | Produktionspfad ausbauen |
| Valhalla / Privacy Groth16 (Wave 25) | gleiches Kurvenrisiko | STARK- oder hash-basierte Alternative planen |

**Zeithorizont:** Kipppunkt typ. **2030+** — architektonisch **jetzt** planen
(Beweisformat, Verifier on-chain/off-chain, Gas/Größe), Migration gestaffelt.
Kein Grund, morgen alle Groth16-Demos zu löschen; Grund, keine neuen
Langzeit-Invarianten ausschließlich an pairing-SNARKs zu binden.

### 4.4 Bestehende Module

- Wave 33: `PQCSignerAgent` — ML-DSA-87 (Dilithium-5), ML-KEM-1024 (Kyber),
  SLH-DSA (SPHINCS+); Backend liboqs oder SHA3-Simulation  
- Wave 33: ZK-STARK-Kompression (`zk_compression.py`) — Anknüpfungspunkt M8  
- Bunker HSM: ECDSA heute — **Gap:** PQC-Signing im HSM-Adapter noch nicht
  Produktionsstandard  
- Modus `POST_QUANTUM` im Survival-Orchestrator: Umschaltung spezifiziert  
- Settlement/Protocol: noch `Groth16_BN254` — **Gap:** M8  

### 4.5 Gap (ehrlich)

Spezifikation und Demo/Simulation ≠ flächendeckende PQC in allen Kanälen
(Bridge, SEPA-Meta, Dashboard-TLS, Submodul-Ökosystem). HN-DL verlangt eine
**Kanal-Inventur**: welche Ciphertexte landen dauerhaft im WORM?
Zusätzlich: welche **Beweisformate** müssen nach 2030 noch sound sein?

---

## 5. Tertiär — Graph-Cut / Lahmlegung (klassisch)

„Zwei Kreuzungen sperren“ = Min-Cut / Betweenness — **kein** Grover-Vorteil nötig.

| Maßnahme | Agent-X-Anker |
|----------|---------------|
| Redundante Routen / Mesh | Wave 33 LoRaWAN / Peer-Discovery |
| Keine Single-Choke-Settlement-Pfade | Clearing multilateral; Fallback SEPA |
| Betweenness-Monitoring | Macro Cartel / SystemicRisk (klassisch) |

Grover gehört in diesem Dokument **nicht** als Bedrohungsvektor mit eigenem
Schweregrad — nur als Hinweis, narrative Überhöhung zu vermeiden.

---

## 6. Quartär — Physische OPSEC / Sensorik

Abwärme, IR, Drohnen, Satelliten: klassische Überwachung. Gegenmaßnahmen:
OPSEC, Standortwahl Bunker, keine Ableitung aus „Quantensensorik“-Mythos.
Relevant für Off-Grid (Wave 33), nicht für Ledger-κ.

---

## 7. Kombinierter Angreifer (realistischstes Szenario)

```text
Heute:   Delay Attack auf ℓ_ij     →  Timing-Poisoning (M7-Fläche)
         + Ledger-Leak             →  ML-Vorhersage (Rekonstruktion)
         + Spam-Interaktionen      →  Sybil ohne Volumen (M9-Fläche)
         + Mitschnitt ciphertexts  →  HN-DL-Archiv
2030+:   Shor auf Asymmetrie       →  Langzeitgeheimnisse offen
         + Shor auf pairing-SNARK  →  Soundness-Bruch (M8-Fläche)
parallel: Graph-Cut auf Topologie  →  Disruption (klassisch)
```

Die gefährliche Kombination ist **aktives Timing + Verhaltensanalyse +
zeitverzögertes Krypto-/Beweisbrechen** — nicht Quantensensorik + Grover.

---

## 8. Ableitung — Maßnahmenroadmap (ohne Pre-Reg)

| ID | Maßnahme | Prio | Abhängig von |
|----|----------|-----:|--------------|
| M1 | Export-Policy: `avg_latency` / `interaction_count` nur aggregiert + Noise | 1 | Ledger / Ops-API |
| M2 | Trennung Audit-WORM (Balance) vs. Ops-Timing (räuschbar) | 1 | GoBD / BHO |
| M3 | Party-ID-Pseudonymisierung in allen Nicht-Audit-Exports | 1 | DSGVO / DID |
| **M7** | **Trimmed Mean / Median-Intake `ℓ_ij`** + \(n_{\min}\); Gewicht ∝ \(\Delta\neq0\) (§3.7) | **1** | `kanten_ledger.py` |
| M4 | Kanal-Inventur HN-DL (was liegt 10–15 J. verschlüsselt im Archiv?) | 2 | Bridge / GoBD / Backup |
| M5 | Hybride KEM für Langzeitarchive; HSM-Pfad Richtung ML-DSA | 2 | Wave 33 / Bunker |
| **M8** | **SNARK → STARK** (Soundness unter Shor; Wave-33-Pfad ausbauen) | **2** | Settlement / ZK / Survival |
| **M9** | **Trust (+ Latenzgewicht) an BHO-Volumen** (\(\Delta \neq 0\)); kein Spam-Trust | **2** | Ledger Trust + BHO |
| M6 | Mesh-/Clearing-Redundanz gegen klassische Cuts | 3 | Survival / Clearing |

Keine dieser Maßnahmen ist eine Emergenz-Studie. Umsetzung = Engineering / Compliance.

---

## 9. Verweise

| Ressource | Rolle |
|-----------|-------|
| `docs/KOPPLUNG_SERIE_ABSCHLUSS.md` | Surface-Kartographie (partnerselektive Kanten) |
| `agents_b2g/emergence/kanten_ledger.py` | \(E_{ij}\) 5-Komponenten |
| `agents_b2g/survival/subagents/pqc_signer.py` | NIST PQC (Dilithium / Kyber / SPHINCS+) |
| `agents_b2g/survival/subagents/zk_compression.py` | STARK/FRI — Anker M8 |
| `agents_b2g/bunker/hsm_adapter.py` | HSM heute (ECDSA) — PQC-Gap |
| `agents_b2g/settlement/` · `protocol.py` | Groth16 heute — Gap M8 |
| Tag `v1.0-kopplung-serie-closed` | Serie versiegelt |

---

## 10. Status

```text
Dokument: docs/THREAT_MODEL_POST_QUANTUM_v0.md
Typ:      Threat-Surface-Landkarte (Analyse)
Nicht:    DRAFT / Pre-Reg / Sweep
Vektoren: Rekonstruktion · Timing-Poisoning · Shor/HN-DL(+SNARK) · Sybil
Roadmap:  M1–M9 (M7∪M9: Einfluss ∝ Buchungsbewegung · n_min für MAD)
M7-Status: PRODUCTION — default `trimmed_m7` · MAD-Reject vor Append · Poison-Log
           (`kanten_ledger.py` · `scripts/test_m7_latency_poison.py`)
           Vorher-Zustand: `latency_mode=ewma` / env `AGENT_X_LATENCY_MODE=ewma`
Serie:    sticky-ℓ |ρ|≈0.348 / 0.156 = Vorher-Zustand — nicht übertragbar nach M7/M9
Entmythologisiert: Grover · Quantensensorik
Disziplin: Quantenspezifisch nur Shor (+ pairing-SNARK-Soundness)
```
