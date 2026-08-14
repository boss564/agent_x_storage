# Soft-Finality — Vertrag (Commit 1.5)

Dieser Vertrag definiert die Semantik der spekulativen Soft-Finality der
A-Schicht (A01–A09). Schwarm 2 (CAS-Bomber) und Schwarm 3 (Logistics)
konsumieren exakt die hier festgelegten State-Roots und Zustandsübergänge.
Kein Konsument darf von dieser Spezifikation abweichen.

## 1. Finality-Leiter

| Tier | Bedeutung | Rücknehmbar? |
|------|-----------|--------------|
| **L0 `SPECULATIVE`** | In flight, nur geroutet (A02-Ausgabe) | ja, folgenlos |
| **L1 `SOFT_FINAL`** | A03-Attestierung, State-Root im Cache | nur mit Kompensation |
| **L2 `HARD_FINAL`** | L1-Anker (Analogie: die 9.554 echten Anker aus dem 1M-Tsunami) | nein |

## 2. Zustandsmaschine

```
RECEIVED → VERIFIED → SOFT_FINAL → ANCHORED
                  ↘             ↘
                   ROLLED_BACK → COMPENSATED
```

**Kerninvariante:** Jedes `SOFT_FINAL`-Event endet entweder `ANCHORED` oder
`COMPENSATED` — niemals dangling. `ROLLED_BACK` ist ein transienter
Zwischenzustand, der zwingend in `COMPENSATED` übergeht.

Legale Übergänge (erzwungen durch `FINALITY_TRANSITIONS`):

| Von | Nach |
|-----|------|
| RECEIVED | VERIFIED |
| VERIFIED | SOFT_FINAL, ROLLED_BACK |
| SOFT_FINAL | ANCHORED, ROLLED_BACK, COMPENSATED |
| ANCHORED | — (terminal) |
| ROLLED_BACK | COMPENSATED |
| COMPENSATED | — (terminal) |

## 3. AttestationEnvelope

```python
AttestationEnvelope = {
    tx_hash, state_root, tier, signer, ts, expiry, epoch, seq
}
```

- **Fast-Path:** Single-ECDSA (die 13,8 µs müssen halten).
- **Eskalation:** Betrag > Schwelle oder Risiko ≥ Klasse D → 2 Attestierungen
  (analog Consensus Engine: 4 Validatoren, 3/4-Threshold).
- **Upgrade-Pfad:** MPC t=3,n=5 (`agents_b2g/bunker/`) oder Dilithium-5
  (Wave 33), sobald Soft-Finality ökonomisches Gewicht trägt.

## 4. State-Root-Cache

| Frage | Festlegung |
|-------|-----------|
| **TTL** | 500 ms–2 s bis zum CAS-Bestätigungsfenster; Ablauf → Degradierung auf L0 |
| **Invalidierung** | Poison-Fund (A03/A07), NATS-Redelivery, Checkpoint-Mismatch |
| **Poison-Schutz** | Nur hash-chained Roots cachen (GoBD-Ketten-Muster), nie Roh-Payloads |
| **Versionierung** | Einträge mit `(epoch, seq)` |
| **Eviction** | LRU; **Evict ≠ Rollback** — TX bleibt SOFT_FINAL, verliert nur den Fast-Path-Cache |
| **CAS-Konflikt** | Zwei Fast-Paths auf demselben Slot → genau ein Gewinner, Verlierer → Fallback (A08) |

## 5. Reversibilität & ökonomische Absicherung

- Soft-Final-Versprechen ist eine **Verbindlichkeit** → Bond/Slashing-Kopplung
  an Wave 29 (`SlashingAndPenaltyExecutor`-Muster).
- Rollback-Pfad: kompensierende TX → D02 Forensic Repair (`agents_b2g/settlement/`)
  → AWACS-Audit-Event (A09).
- **Rollback-Fenster:** bis zum nächsten Epochen-Flush; danach „ökonomisch
  final" auch ohne L1-Anker.

## 6. Idempotenz & Replay-Schutz

- Dedup-Key: `(sender, nonce, intent_hash)` statt `tx_hash` — NATS-Redeliveries
  müssen dasselbe Envelope zurückbekommen (idempotenter Ack).
- Vorbild: `IoTVerifier.sol` (Replay-Schutz als On-Chain-Präzedenz).

## 7. Observabilität (A09 konsumiert dieses Schema — jetzt eingefroren)

- Jeder Tier-Übergang → JSONL-Event über den EventBus.
- Metriken:
  - `air_soft_final_attestations_total{tier}`
  - `air_soft_final_rollback_total`
  - `air_cache_hit_ratio`
  - Latenz-Histogramm
