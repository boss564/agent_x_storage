-- Wave 28 Threat Engine — Variante A (rein defensiv)
-- =============================================================================
-- Leitplanken (bindend):
--   1. Keine Gewinn-Umleitung (kein Extrahieren fremder MEV-/Liquidationsgewinne)
--   2. Kein Clone-Architect (kein Nachbau angreifender Strategien)
--   3. Keine normative Stigmatisierung (Erfassung = objektive On-Chain-Metriken,
--      siehe docs/WAVE28_THREAT_CAPTURE_SPEC.md)
--
-- Kopplung: SwarmDetectionRadar → SwarmLearningAdapter → ThreatClassifierEngine
--           + Gatekeeper (Wave 38): BLOCKED nur mit cause, S(τ) ≤ 0
--
-- Requires: PostgreSQL 14+, CREATE EXTENSION vector (pgvector)
-- Embedding default: all-MiniLM-L6-v2 → vector(384)
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- ENUMs
-- ---------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE agent_signal_status AS ENUM ('RELEASED', 'BLOCKED');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE wave28_action_type AS ENUM (
        'SIGNATURE_OBSERVED',
        'SENSITIVITY_RAISED',
        'SENSITIVITY_CLEARED',
        'GATE_BLOCKED',
        'GATE_RELEASED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Optional: Roh-Adressen getrennt (nur bei konkretem Handlungsbedarf)
-- Zugriff bewusst enger halten (RLS / App-Layer), Radar arbeitet auf Pseudonym.
-- ---------------------------------------------------------------------------
-- Tenant-isoliert (Spec §1.1). Pattern tables are global; raw addresses are not.
CREATE TABLE IF NOT EXISTS wave28_eoa_raw_vault (
    tenant_user_id  VARCHAR(128) NOT NULL,
    eoa_pseudonym   CHAR(64) NOT NULL,             -- SHA-256(lower(address))
    eoa_address_raw VARCHAR(42) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_user_id, eoa_pseudonym),
    CONSTRAINT wave28_eoa_raw_format CHECK (eoa_address_raw ~ '^0x[0-9a-fA-F]{40}$'),
    CONSTRAINT wave28_eoa_raw_pseudonym CHECK (eoa_pseudonym ~ '^[0-9a-f]{64}$')
);

COMMENT ON TABLE wave28_eoa_raw_vault IS
    'Tenant-scoped raw EOA vault. Radar/ANN must use eoa_pseudonym only.';

-- ---------------------------------------------------------------------------
-- 1) Threat signatures (SwarmDetectionRadar) — monthly partitions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wave28_threat_signatures (
    signature_id        BIGSERIAL,
    eoa_pseudonym       CHAR(64) NOT NULL,
    chain               VARCHAR(32) NOT NULL,
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    -- Objective capture metrics (see WAVE28_THREAT_CAPTURE_SPEC.md)
    latency_ms_p50      DOUBLE PRECISION,
    latency_ms_p99      DOUBLE PRECISION,
    gas_priority_gwei   DOUBLE PRECISION,
    interaction_type    VARCHAR(64) NOT NULL,
    tx_count            INT NOT NULL DEFAULT 0,
    peer_cluster_size   INT NOT NULL DEFAULT 1,
    entropy_score       DOUBLE PRECISION,
    pattern_label       VARCHAR(64),               -- descriptive, not normative
    observed_by_user_id VARCHAR(128),              -- provenance only (Spec §1.1)
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (signature_id, created_at),
    CONSTRAINT wave28_sig_window CHECK (window_end >= window_start),
    CONSTRAINT wave28_sig_pseudonym CHECK (eoa_pseudonym ~ '^[0-9a-f]{64}$')
) PARTITION BY RANGE (created_at);

CREATE INDEX IF NOT EXISTS idx_wave28_sig_pseudonym
    ON wave28_threat_signatures (eoa_pseudonym);
CREATE INDEX IF NOT EXISTS idx_wave28_sig_active_created
    ON wave28_threat_signatures (is_active, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wave28_sig_chain_window
    ON wave28_threat_signatures (chain, window_start, window_end);

-- Default partitions (extend via cron / migration as needed)
CREATE TABLE IF NOT EXISTS wave28_threat_signatures_2026_08
    PARTITION OF wave28_threat_signatures
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE IF NOT EXISTS wave28_threat_signatures_2026_09
    PARTITION OF wave28_threat_signatures
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS wave28_threat_signatures_2026_10
    PARTITION OF wave28_threat_signatures
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE IF NOT EXISTS wave28_threat_signatures_default
    PARTITION OF wave28_threat_signatures DEFAULT;

COMMENT ON TABLE wave28_threat_signatures IS
    'Complementary pattern stream for SwarmDetectionRadar. Objective metrics only.';

-- ---------------------------------------------------------------------------
-- 2) Behavior embeddings (SwarmLearningAdapter)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wave28_behavior_embeddings (
    embedding_id        BIGSERIAL,
    signature_id        BIGINT NOT NULL,
    eoa_pseudonym       CHAR(64) NOT NULL,
    embedding           vector(384) NOT NULL,
    embedding_model     VARCHAR(100) NOT NULL,     -- e.g. all-MiniLM-L6-v2
    embedding_dim       INT NOT NULL,              -- must match vector(N)
    cluster_id          INT,
    similarity_ref      DOUBLE PRECISION,
    observed_by_user_id VARCHAR(128),              -- provenance only (Spec §1.1)
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (embedding_id, created_at),
    CONSTRAINT wave28_emb_dim CHECK (embedding_dim = 384),
    CONSTRAINT wave28_emb_pseudonym CHECK (eoa_pseudonym ~ '^[0-9a-f]{64}$')
) PARTITION BY RANGE (created_at);

CREATE INDEX IF NOT EXISTS idx_wave28_emb_pseudonym
    ON wave28_behavior_embeddings (eoa_pseudonym);
CREATE INDEX IF NOT EXISTS idx_wave28_emb_model
    ON wave28_behavior_embeddings (embedding_model, embedding_dim);
CREATE INDEX IF NOT EXISTS idx_wave28_emb_ivfflat
    ON wave28_behavior_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE IF NOT EXISTS wave28_behavior_embeddings_2026_08
    PARTITION OF wave28_behavior_embeddings
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE IF NOT EXISTS wave28_behavior_embeddings_2026_09
    PARTITION OF wave28_behavior_embeddings
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS wave28_behavior_embeddings_2026_10
    PARTITION OF wave28_behavior_embeddings
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE IF NOT EXISTS wave28_behavior_embeddings_default
    PARTITION OF wave28_behavior_embeddings DEFAULT;

COMMENT ON TABLE wave28_behavior_embeddings IS
    'Vector memory for SwarmLearningAdapter. Filter by embedding_model before ANN.';

-- ---------------------------------------------------------------------------
-- 3) Causal incidents (ThreatClassifier + Gatekeeper) — audit trail
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wave28_causal_incidents (
    incident_id             BIGSERIAL PRIMARY KEY,
    signature_id            BIGINT,
    eoa_pseudonym           CHAR(64) NOT NULL,
    action_type             wave28_action_type NOT NULL,
    -- Wave-38 style gate coupling (defensive only)
    agent_x_signal_status   agent_signal_status NOT NULL,
    block_cause             VARCHAR(64),           -- required iff BLOCKED
    s_tau                   DOUBLE PRECISION,      -- S(τ); BLOCKED path expects ≤ 0
    kfold_sensitivity       DOUBLE PRECISION,      -- raised/cleared resampling factor
    gatekeeper_job_id       VARCHAR(64),
    observed_by_user_id     VARCHAR(128),          -- provenance only (Spec §1.1)
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT wave28_inc_pseudonym CHECK (eoa_pseudonym ~ '^[0-9a-f]{64}$'),
    CONSTRAINT wave28_inc_blocked_has_cause CHECK (
        agent_x_signal_status <> 'BLOCKED'
        OR (block_cause IS NOT NULL AND length(trim(block_cause)) > 0)
    ),
    CONSTRAINT wave28_inc_blocked_s_tau CHECK (
        agent_x_signal_status <> 'BLOCKED'
        OR s_tau IS NULL
        OR s_tau <= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_wave28_inc_pseudonym_created
    ON wave28_causal_incidents (eoa_pseudonym, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wave28_inc_action
    ON wave28_causal_incidents (action_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wave28_inc_gate
    ON wave28_causal_incidents (agent_x_signal_status, gatekeeper_job_id);

COMMENT ON TABLE wave28_causal_incidents IS
    'Audit of defensive actions: sensitivity raises and Gatekeeper BLOCKED/RELEASED.';
COMMENT ON COLUMN wave28_causal_incidents.action_type IS
    'SENSITIVITY_RAISED/CLEARED make heightened K-Fold scrutiny auditable (no silent targeting).';

-- ---------------------------------------------------------------------------
-- Gatekeeper coupling helper (callable from app or AFTER INSERT)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION wave28_record_gate_coupling(
    p_signature_id          BIGINT,
    p_eoa_pseudonym         CHAR(64),
    p_action_type           wave28_action_type,
    p_signal_status         agent_signal_status,
    p_block_cause           VARCHAR(64),
    p_s_tau                 DOUBLE PRECISION,
    p_kfold_sensitivity     DOUBLE PRECISION,
    p_gatekeeper_job_id     VARCHAR(64),
    p_notes                 TEXT DEFAULT NULL,
    p_observed_by_user_id   VARCHAR(128) DEFAULT NULL
) RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    IF p_signal_status = 'BLOCKED' AND (p_block_cause IS NULL OR length(trim(p_block_cause)) = 0) THEN
        RAISE EXCEPTION 'BLOCKED requires block_cause (Wave-38 gate invariant)';
    END IF;
    IF p_signal_status = 'BLOCKED' AND p_s_tau IS NOT NULL AND p_s_tau > 0 THEN
        RAISE EXCEPTION 'BLOCKED with S(τ)>0 rejected — defensive coupling only when S(τ)≤0';
    END IF;

    INSERT INTO wave28_causal_incidents (
        signature_id, eoa_pseudonym, action_type,
        agent_x_signal_status, block_cause, s_tau,
        kfold_sensitivity, gatekeeper_job_id, observed_by_user_id, notes
    ) VALUES (
        p_signature_id, lower(p_eoa_pseudonym), p_action_type,
        p_signal_status, p_block_cause, p_s_tau,
        p_kfold_sensitivity, p_gatekeeper_job_id, p_observed_by_user_id, p_notes
    )
    RETURNING incident_id INTO v_id;

    RETURN v_id;
END;
$$;

-- ON INSERT threat_signatures → audit SIGNATURE_OBSERVED (RELEASED default;
-- Gatekeeper may later flip to BLOCKED via wave28_record_gate_coupling).
CREATE OR REPLACE FUNCTION wave28_on_signature_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO wave28_causal_incidents (
        signature_id,
        eoa_pseudonym,
        action_type,
        agent_x_signal_status,
        block_cause,
        s_tau,
        kfold_sensitivity,
        notes
    ) VALUES (
        NEW.signature_id,
        NEW.eoa_pseudonym,
        'SIGNATURE_OBSERVED',
        'RELEASED',
        NULL,
        NULL,
        NULL,
        format('auto: pattern=%s chain=%s', NEW.pattern_label, NEW.chain)
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_wave28_signature_audit ON wave28_threat_signatures;
CREATE TRIGGER trg_wave28_signature_audit
    AFTER INSERT ON wave28_threat_signatures
    FOR EACH ROW
    EXECUTE PROCEDURE wave28_on_signature_insert();

-- ---------------------------------------------------------------------------
-- Retention (DSGVO + ops)
-- Soft: is_active=FALSE after inactive_days
-- Hard: DROP / DELETE partitions older than retain_days
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION wave28_apply_retention(
    inactive_days INT DEFAULT 30,
    retain_days   INT DEFAULT 365
) RETURNS TABLE(action TEXT, affected BIGINT)
LANGUAGE plpgsql
AS $$
DECLARE
    n_soft BIGINT;
    n_hard_sig BIGINT;
    n_hard_emb BIGINT;
    n_hard_inc BIGINT;
    cutoff_inactive TIMESTAMPTZ := now() - make_interval(days => inactive_days);
    cutoff_hard     TIMESTAMPTZ := now() - make_interval(days => retain_days);
BEGIN
    UPDATE wave28_threat_signatures
       SET is_active = FALSE
     WHERE is_active = TRUE
       AND created_at < cutoff_inactive;
    GET DIAGNOSTICS n_soft = ROW_COUNT;
    action := 'soft_deactivate_signatures'; affected := n_soft; RETURN NEXT;

    UPDATE wave28_behavior_embeddings
       SET is_active = FALSE
     WHERE is_active = TRUE
       AND created_at < cutoff_inactive;
    GET DIAGNOSTICS n_soft = ROW_COUNT;
    action := 'soft_deactivate_embeddings'; affected := n_soft; RETURN NEXT;

    DELETE FROM wave28_threat_signatures WHERE created_at < cutoff_hard;
    GET DIAGNOSTICS n_hard_sig = ROW_COUNT;
    action := 'hard_delete_signatures'; affected := n_hard_sig; RETURN NEXT;

    DELETE FROM wave28_behavior_embeddings WHERE created_at < cutoff_hard;
    GET DIAGNOSTICS n_hard_emb = ROW_COUNT;
    action := 'hard_delete_embeddings'; affected := n_hard_emb; RETURN NEXT;

    DELETE FROM wave28_causal_incidents WHERE created_at < cutoff_hard;
    GET DIAGNOSTICS n_hard_inc = ROW_COUNT;
    action := 'hard_delete_incidents'; affected := n_hard_inc; RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION wave28_apply_retention IS
    'Schedule monthly: SELECT * FROM wave28_apply_retention(30, 365);';

-- =============================================================================
-- Censorship Resilience (Variante A extension — still ×9 agents)
-- Spec: docs/WAVE28_CENSORSHIP_RESILIENCE_SPEC.md
-- block_cause 'CENSORSHIP_DETECTED' is valid for wave28_record_gate_coupling
-- =============================================================================

CREATE TABLE IF NOT EXISTS wave28_censorship_watchlist (
    watch_id            BIGSERIAL PRIMARY KEY,
    address_pseudonym   CHAR(64) NOT NULL,
    source              VARCHAR(50) NOT NULL,      -- OFAC | EU_SANCTIONS | TREASURY | ADDRESS_POISONING
    list_version        VARCHAR(100) NOT NULL,
    first_seen          TIMESTAMPTZ NOT NULL DEFAULT now(),
    confidence          NUMERIC(5, 4) NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    observed_by_user_id VARCHAR(128),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT wave28_watch_pseudonym CHECK (address_pseudonym ~ '^[0-9a-f]{64}$'),
    CONSTRAINT wave28_watch_confidence CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT wave28_watch_source CHECK (
        source IN ('OFAC', 'EU_SANCTIONS', 'TREASURY', 'ADDRESS_POISONING')
    )
);

CREATE INDEX IF NOT EXISTS idx_wave28_watch_pseudo_active
    ON wave28_censorship_watchlist (address_pseudonym, is_active);

CREATE TABLE IF NOT EXISTS wave28_relayer_health (
    health_id           BIGSERIAL PRIMARY KEY,
    relayer_name        VARCHAR(100) NOT NULL,     -- OmniBridge | CCTP_V2 | LayerZero_V2
    chain_id            INT NOT NULL,
    asset_symbol        VARCHAR(20) NOT NULL,
    throughput_rate     NUMERIC(12, 4),            -- successful TX / minute
    drop_rate           NUMERIC(12, 4),            -- filtered TX / minute
    censorship_detected BOOLEAN NOT NULL DEFAULT FALSE,
    observed_by_user_id VARCHAR(128),
    observed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wave28_relayer_obs
    ON wave28_relayer_health (relayer_name, asset_symbol, observed_at DESC);

CREATE TABLE IF NOT EXISTS wave28_censorship_incidents (
    incident_id             BIGSERIAL PRIMARY KEY,
    watch_id                BIGINT REFERENCES wave28_censorship_watchlist (watch_id),
    relayer_name            VARCHAR(100),
    censorship_type         VARCHAR(50) NOT NULL,
    -- STABLECOIN_FREEZE | BUILDER_FILTER | RPC_BLOCK | RELAYER_DROP | ADDRESS_POISONING
    agent_x_signal_status   agent_signal_status NOT NULL,
    block_cause             VARCHAR(100),          -- CENSORSHIP_DETECTED when BLOCKED
    route_fallback          VARCHAR(100),          -- e.g. USDC→ETH native / alt RPC
    gatekeeper_job_id       VARCHAR(64),
    observed_by_user_id     VARCHAR(128),
    logged_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT wave28_cens_blocked_cause CHECK (
        agent_x_signal_status <> 'BLOCKED'
        OR (block_cause IS NOT NULL AND length(trim(block_cause)) > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_wave28_cens_inc_logged
    ON wave28_censorship_incidents (logged_at DESC);

COMMENT ON TABLE wave28_censorship_watchlist IS
    'Pseudonymized sanctions/poisoning watchlist — global swarm, no raw addresses.';
COMMENT ON TABLE wave28_relayer_health IS
    'Bridge relayer throughput/drop metrics for censorship-aware routing.';
COMMENT ON TABLE wave28_censorship_incidents IS
    'Audit of censorship detections; BLOCKED requires block_cause (CENSORSHIP_DETECTED).';
