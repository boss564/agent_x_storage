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
| **Shor** | **Ja** | Bricht RSA / ECC / DH asymmetrisch |
| Quantensensorik | Nein (operativ) | Physische Nähe / klassische Sensorik |
| Grover auf Graph-Cut | **Nein** | Narrative Ausschmückung; Min-Cut / Betweenness klassisch polynomial |
| Inverse Rekonstruktion | **Nein** | Zeitreihen / ML — klassisch |

Nur Shor ist nachweislich quantenspezifisch. Alles andere als „Quantenbedrohung“ zu
verkaufen, wäre dieselbe Falle wie der Eingangstext: Quantencomputer als Mythos statt
als Krypto-Brecher.

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
| `avg_latency` | partnerselektiv (\|ρ\|≈0.35 bei φ_L) | **Primäre Vorhersagefläche** (Fahrzeit-Proxy) |
| `interaction_count` | partnerselektiv (Ledger L2) | Frequenz / Sticky-Partner |
| Knoten-Zustände | `NONE_CLOSE` (\|ρ\|≈1) | kaum partnerunterscheidend |

Das ist keine neue Emergenzfrage. Es benennt konkret, welche Felder unter
Vektor 1 (Inverse Rekonstruktion) stehen.

---

## 2. Priorisierte Bedrohungsmatrix

| Prio | Vektor | Schwere | Quantenspez. | Kernaussage |
|-----:|--------|---------|:------------:|-------------|
| **1** | Inverse Rekonstruktion | **Hoch** | nein | Ledger-Historie → Verhaltensvorhersage |
| **2** | Shor + Harvest-now-decrypt-later | **Mittel** | **ja** | Heute sammeln, später brechen / langfristige Sensibilität |
| **3** | Graph-Cut / Mesh-Lahmlegung | Mittel | nein | Klassische Optimierung, nicht Grover |
| **4** | Physische OPSEC / Sensorik | Niedrig–mittel | nein | Überwachung, nicht „Quantenasphalt“ |

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
| **`avg_latency`** | **Hoch** (partnerselektiv, Timing) | Ja (additives / multiplikatives Rauschen, EWMA-Jitter) | Betriebsmetrik — nicht GoBD-pflichtig wie Buchung | Differential Privacy / Laplace auf Export; Aggregation (Bins); kein Roh-Export an Dritte |
| **`interaction_count`** | **Hoch** (Frequenz, Sticky) | Ja (Rounding, Top-k Truncation) | Betriebsmetrik | K-Anonymität über Zeitfenster; Cap + Noise |
| `trust_score` (α,β) | Mittel | Ja | Intern | Nur abgeleitete Buckets exportieren |
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

### 4.3 Bestehende Module

- Wave 33: `PQCSignerAgent` — ML-DSA-87 (Dilithium-5), ML-KEM-1024 (Kyber),
  SLH-DSA (SPHINCS+); Backend liboqs oder SHA3-Simulation  
- Bunker HSM: ECDSA heute — **Gap:** PQC-Signing im HSM-Adapter noch nicht
  Produktionsstandard  
- Modus `POST_QUANTUM` im Survival-Orchestrator: Umschaltung spezifiziert  

### 4.4 Gap (ehrlich)

Spezifikation und Demo/Simulation ≠ flächendeckende PQC in allen Kanälen
(Bridge, SEPA-Meta, Dashboard-TLS, Submodul-Ökosystem). HN-DL verlangt eine
**Kanal-Inventur**: welche Ciphertexte landen dauerhaft im WORM?

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
Heute:   Ledger-/Telemetry-Leak  →  ML-Vorhersage (Vektor 1)
         + Mitschnitt ciphertexts →  HN-DL-Archiv (Vektor 2)
2030+:   Shor auf geharvestete Asymmetrie  →  Langzeitgeheimnisse offen
parallel: Graph-Cut auf bekannter Topologie →  gezielte Disruption (Vektor 3)
```

Die gefährliche Kombination ist **Krypto-Brechen (zeitverzögert) + Verhaltensanalyse
(jetzt)** — nicht Quantensensorik + Grover.

---

## 8. Ableitung — Maßnahmenroadmap (ohne Pre-Reg)

| ID | Maßnahme | Prio | Abhängig von |
|----|----------|-----:|--------------|
| M1 | Export-Policy: `avg_latency` / `interaction_count` nur aggregiert + Noise | 1 | Ledger / Ops-API |
| M2 | Trennung Audit-WORM (Balance) vs. Ops-Timing (räuschbar) | 1 | GoBD / BHO |
| M3 | Party-ID-Pseudonymisierung in allen Nicht-Audit-Exports | 1 | DSGVO / DID |
| M4 | Kanal-Inventur HN-DL (was liegt 10–15 J. verschlüsselt im Archiv?) | 2 | Bridge / GoBD / Backup |
| M5 | Hybride KEM für Langzeitarchive; HSM-Pfad Richtung ML-DSA | 2 | Wave 33 / Bunker |
| M6 | Mesh-/Clearing-Redundanz gegen klassische Cuts | 3 | Survival / Clearing |

Keine dieser Maßnahmen ist eine Emergenz-Studie. Umsetzung = Engineering / Compliance.

---

## 9. Verweise

| Ressource | Rolle |
|-----------|-------|
| `docs/KOPPLUNG_SERIE_ABSCHLUSS.md` | Surface-Kartographie (partnerselektive Kanten) |
| `agents_b2g/emergence/kanten_ledger.py` | \(E_{ij}\) 5-Komponenten |
| `agents_b2g/survival/subagents/pqc_signer.py` | NIST PQC (Dilithium / Kyber / SPHINCS+) |
| `agents_b2g/bunker/hsm_adapter.py` | HSM heute (ECDSA) — PQC-Gap |
| Tag `v1.0-kopplung-serie-closed` | Serie versiegelt |

---

## 10. Status

```text
Dokument: docs/THREAT_MODEL_POST_QUANTUM_v0.md
Typ:      Threat-Surface-Landkarte (Analyse)
Nicht:    DRAFT / Pre-Reg / Sweep
Fokus:    Primär Rekonstruktion (Feldmapping) · Sekundär Shor/HN-DL (Zeithorizonte)
Disziplin: Quantenspezifisch nur Shor
```
