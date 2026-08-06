# Observability & Kubernetes Deployment Spec (Welle 24+)

Status: Spezifikation (nicht implementiert). Benötigt K8s-Cluster + Redis + PostgreSQL.

## Prometheus Metrics

- `nonce_generated_total` (Counter, label: trader)
- `nonce_used_total` (Counter, label: trader)
- `trade_compliance_passed_total` / `trade_compliance_rejected_total` (Counter, labels: token, reason)
- `redis_connection_up` (Gauge)
- `pending_nonces_count` (Gauge)
- `nonce_generation_latency_seconds` (Histogram)
- `compliance_check_latency_seconds` (Histogram)

## Helm Chart

See `helm/compliance-stack/` (not yet created — requires K8s target cluster).

## NonceManager Schema (PostgreSQL)

```sql
CREATE TABLE compliance_nonces (
    id BIGSERIAL PRIMARY KEY,
    trader VARCHAR(42) NOT NULL,
    nonce NUMERIC(78,0) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    tx_hash VARCHAR(66),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (trader, nonce)
);
```

## Gas-Optimization (ComplianceVerifier)

- uint64 statt uint256 für nonce/deadline: ~1.200 Gas
- Prüfreihenfolge (timestamp vor recover): ~2.500 Gas bei invalid
- calldata statt memory für signature: ~300 Gas
- Gesamt: ~4.000 Gas (~5%) pro Trade
