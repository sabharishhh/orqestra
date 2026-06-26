-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. BASE TABLES (No Foreign Keys)
CREATE TABLE IF NOT EXISTS systems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) UNIQUE NOT NULL,
    provider VARCHAR(50) DEFAULT 'openai',
    description TEXT,
    api_key_hash VARCHAR(64) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(255) UNIQUE NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    entity_type VARCHAR(50) DEFAULT 'general',
    importance FLOAT DEFAULT 0.5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS induction_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suggested_name VARCHAR(255) NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    suggested_type VARCHAR(50) DEFAULT 'general',
    suggested_importance FLOAT DEFAULT 0.5,
    variance_score FLOAT DEFAULT 0.0,
    claim_frequency INTEGER DEFAULT 0,
    sample_claims JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. FIRST-DEGREE RELATIONS
-- SCCG: Sparse Causal Claim Graph
CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID REFERENCES systems(id) ON DELETE CASCADE,
    entity_id UUID REFERENCES entities(id) ON DELETE SET NULL, 
    parent_claim_id UUID REFERENCES claims(id) ON DELETE SET NULL,
    content_hash VARCHAR(64),
    logical_clock INTEGER DEFAULT 0,
    event_type VARCHAR(50) NOT NULL DEFAULT 'CLAIM_EMITTED',
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    context TEXT,
    entity_hint VARCHAR(100),
    embedding vector(1536),
    vector_clock JSONB DEFAULT '{}'::jsonb,
    parent_hashes JSONB DEFAULT '[]'::jsonb,
    is_historical BOOLEAN DEFAULT FALSE,
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ON claims (content_hash);
CREATE INDEX IF NOT EXISTS idx_claims_event_type ON claims(event_type);
-- F1.6 Guardrail: STRICT HNSW INDEXING (No IVFFlat)
CREATE INDEX ON claims USING hnsw (embedding vector_cosine_ops);

-- OBG: Organizational Belief Graph (Running Centroids)
CREATE TABLE IF NOT EXISTS entity_belief_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID REFERENCES systems(id) ON DELETE CASCADE,
    entity_name VARCHAR(255) NOT NULL,
    centroid_embedding vector(1536),        
    sample_count INTEGER DEFAULT 0,         
    belief_variance FLOAT DEFAULT 0.0,
    staleness_score FLOAT DEFAULT 0.0,
    confidence FLOAT DEFAULT 0.0,
    recency_weight FLOAT DEFAULT 1.0,
    centroid_history JSONB DEFAULT '[]'::jsonb,
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(system_id, entity_name)
);

-- 3. SECOND-DEGREE RELATIONS
-- Detected Contradictions (The Edges)
CREATE TABLE IF NOT EXISTS contradictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_a_id UUID REFERENCES claims(id) ON DELETE CASCADE,
    claim_b_id UUID REFERENCES claims(id) ON DELETE CASCADE,
    entity_id UUID REFERENCES entities(id) ON DELETE SET NULL, 
    regression_of UUID REFERENCES contradictions(id) ON DELETE SET NULL,
    -- LCA: the earliest shared ancestor at which both systems still agreed
    lca_claim_id UUID REFERENCES claims(id) ON DELETE SET NULL,
    fork_distance_a INTEGER DEFAULT 0,  -- hops from claim_a to LCA
    fork_distance_b INTEGER DEFAULT 0,  -- hops from claim_b to LCA
    cosine_similarity FLOAT NOT NULL,
    nli_score FLOAT NOT NULL,
    severity VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'open',
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_claim_pair UNIQUE (claim_a_id, claim_b_id)
);

-- 4. THIRD-DEGREE RELATIONS
-- Resolutions (The Explainer Output)
CREATE TABLE IF NOT EXISTS resolutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contradiction_id UUID REFERENCES contradictions(id) ON DELETE CASCADE UNIQUE,
    why_they_contradict TEXT NOT NULL,
    likely_stale_system VARCHAR(255),
    risk_reason TEXT,
    recommended_action TEXT,
    estimated_cost VARCHAR(255),
    target_uri VARCHAR(512),
    status VARCHAR(50) DEFAULT 'pending',
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Estate Health Metrics
CREATE TABLE IF NOT EXISTS coherence_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID REFERENCES systems(id) ON DELETE CASCADE UNIQUE,
    score FLOAT DEFAULT 1.0,
    active_contradictions INTEGER DEFAULT 0,
    critical_count INTEGER DEFAULT 0,
    high_count INTEGER DEFAULT 0,
    medium_count INTEGER DEFAULT 0,
    low_count INTEGER DEFAULT 0,
    window_days INTEGER DEFAULT 30,
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Reinforcement Learning Dataset (F3.2)
CREATE TABLE IF NOT EXISTS contrastive_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contradiction_id UUID REFERENCES contradictions(id) ON DELETE CASCADE,
    claim_a_id UUID REFERENCES claims(id) ON DELETE CASCADE,
    claim_b_id UUID REFERENCES claims(id) ON DELETE CASCADE,
    entity_type VARCHAR(50) DEFAULT 'general',
    nli_label VARCHAR(50) NOT NULL,
    is_hard_negative BOOLEAN DEFAULT FALSE,
    feedback_source VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- MULTI-TENANT CONFIG LAYER (Sprint 1.1)
-- =====================================================

-- 5. ORGANIZATIONS
-- Top-level tenant boundary. All claims, systems, configs scoped here.
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) UNIQUE NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,             -- URL-safe identifier (e.g. 'demo-fitness')
    vertical_preset VARCHAR(50) DEFAULT 'general', -- 'general' | 'consumer' | 'clinical' | 'finance' | 'legal' | 'policy'
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_org_slug ON organizations(slug);


-- 6. CANONICAL ENTITIES (per-org closed vocabulary)
-- Replaces the hardcoded CANONICAL_ENTITIES dict in entity_resolver.py.
-- Each entity carries its category (for threshold routing) and severity weights.
CREATE TABLE IF NOT EXISTS canonical_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    canonical_name VARCHAR(255) NOT NULL,
    description TEXT,                              -- human-readable note (used in extraction prompt)
    category VARCHAR(50) NOT NULL DEFAULT 'general', -- routes to category_thresholds
    importance FLOAT DEFAULT 0.5,                  -- coherence-score weighting
    severity_tier VARCHAR(50) DEFAULT 'high',      -- 'critical' | 'high' | 'medium' | 'low'
    cost_critical_usd INTEGER DEFAULT 5000,        -- dollar weight when severity=critical
    cost_high_usd INTEGER DEFAULT 1000,            -- dollar weight when severity=high
    source VARCHAR(50) DEFAULT 'manual',           -- 'preset' | 'manual' | 'induced'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(org_id, canonical_name)
);

CREATE INDEX IF NOT EXISTS idx_canonical_org_name ON canonical_entities(org_id, canonical_name);
CREATE INDEX IF NOT EXISTS idx_canonical_org_category ON canonical_entities(org_id, category);


-- 7. ENTITY ALIASES (flat lookup table — O(1) resolution)
-- One row per (canonical, alias) pair. Faster than JSONB-array search.
CREATE TABLE IF NOT EXISTS entity_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_entity_id UUID NOT NULL REFERENCES canonical_entities(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,  -- denorm for fast WHERE
    alias VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(org_id, alias)
);

CREATE INDEX IF NOT EXISTS idx_alias_lookup ON entity_aliases(org_id, alias);


-- 8. DETECTION CONFIG (per-org tuning of all magic numbers in the funnel)
CREATE TABLE IF NOT EXISTS detection_config (
    org_id UUID PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    -- Funnel tuning
    bootstrap_min_samples INTEGER DEFAULT 3,
    high_variance_threshold FLOAT DEFAULT 0.40,
    semantic_match_threshold FLOAT DEFAULT 0.55,
    -- Auto-induction
    cluster_min_size INTEGER DEFAULT 5,
    cluster_merge_threshold FLOAT DEFAULT 0.20,
    induction_lookback_days INTEGER DEFAULT 7,
    induction_cluster_threshold FLOAT DEFAULT 0.35,
    -- Suppression / dedup
    regression_dedup_days INTEGER DEFAULT 7,
    semantic_suppression_distance FLOAT DEFAULT 0.05,
    -- Scoring
    coherence_window_days INTEGER DEFAULT 30,
    recency_decay_lambda FLOAT DEFAULT 0.05,
    nli_confidence_floor FLOAT DEFAULT 0.70,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- 9. CATEGORY THRESHOLDS (per-org per-category cosine thresholds)
-- Replaces the hardcoded COSINE_THRESHOLDS dict in services/detection_threshold.py.
CREATE TABLE IF NOT EXISTS category_thresholds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,
    level_0_cosine FLOAT NOT NULL,                 -- OBG centroid divergence threshold
    level_3_cosine FLOAT NOT NULL,                 -- HNSW neighbor distance threshold
    nli_floor FLOAT,                               -- nullable; falls back to detection_config.nli_confidence_floor
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(org_id, category)
);

CREATE INDEX IF NOT EXISTS idx_category_thresholds_lookup ON category_thresholds(org_id, category);


-- 10. PII ALLOWLIST (per-org, vertical-specific safe tokens)
-- Replaces the hardcoded CLINICAL_ALLOWLIST set in services/pii_scrubber.py.
CREATE TABLE IF NOT EXISTS pii_allowlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    token VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(org_id, token)
);

CREATE INDEX IF NOT EXISTS idx_pii_allowlist ON pii_allowlist(org_id);

-- =====================================================
-- SPRINT 1.3: org_id FK ROLLOUT
-- =====================================================
-- Tenant-scope all existing operational tables.
-- Backfill rows under a 'demo-fitness' organization before
-- adding the NOT NULL constraint so live data isn't disrupted.

-- Ensure demo org exists (idempotent)
INSERT INTO organizations (name, slug, vertical_preset, description)
VALUES ('Demo Fitness', 'demo-fitness', 'consumer', 'Default organization seeded for the original fitness demo')
ON CONFLICT (slug) DO NOTHING;

-- Add columns nullable first, backfill, then enforce NOT NULL
ALTER TABLE systems              ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;
ALTER TABLE claims               ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;
ALTER TABLE entity_belief_states ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;
ALTER TABLE contradictions       ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;
ALTER TABLE induction_candidates ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;
ALTER TABLE coherence_scores     ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

-- Backfill all existing rows to the demo org
UPDATE systems              SET org_id = (SELECT id FROM organizations WHERE slug = 'demo-fitness') WHERE org_id IS NULL;
UPDATE claims               SET org_id = (SELECT id FROM organizations WHERE slug = 'demo-fitness') WHERE org_id IS NULL;
UPDATE entity_belief_states SET org_id = (SELECT id FROM organizations WHERE slug = 'demo-fitness') WHERE org_id IS NULL;
UPDATE contradictions       SET org_id = (SELECT id FROM organizations WHERE slug = 'demo-fitness') WHERE org_id IS NULL;
UPDATE induction_candidates SET org_id = (SELECT id FROM organizations WHERE slug = 'demo-fitness') WHERE org_id IS NULL;
UPDATE coherence_scores     SET org_id = (SELECT id FROM organizations WHERE slug = 'demo-fitness') WHERE org_id IS NULL;

-- Lock it in: all future inserts MUST provide org_id
ALTER TABLE systems              ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE claims               ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE entity_belief_states ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE contradictions       ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE induction_candidates ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE coherence_scores     ALTER COLUMN org_id SET NOT NULL;

-- Indexes for fast tenant-scoped queries
CREATE INDEX IF NOT EXISTS idx_systems_org              ON systems(org_id);
CREATE INDEX IF NOT EXISTS idx_claims_org               ON claims(org_id);
CREATE INDEX IF NOT EXISTS idx_claims_org_entity        ON claims(org_id, entity_hint);
CREATE INDEX IF NOT EXISTS idx_obg_org                  ON entity_belief_states(org_id);
CREATE INDEX IF NOT EXISTS idx_contradictions_org       ON contradictions(org_id);
CREATE INDEX IF NOT EXISTS idx_induction_org            ON induction_candidates(org_id);
CREATE INDEX IF NOT EXISTS idx_coherence_org            ON coherence_scores(org_id);

-- =====================================================
-- SPRINT 3.1: cost_usd column on contradictions
-- Cost is now computed by services/severity_scorer.py at detection
-- time and persisted, so api/routers/roi.py can sum real values
-- instead of multiplying severity by hardcoded $1200/$150.
-- =====================================================
ALTER TABLE contradictions ADD COLUMN IF NOT EXISTS cost_usd INTEGER DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_contradictions_cost ON contradictions(cost_usd);

ALTER TABLE detection_config ADD COLUMN IF NOT EXISTS induction_min_cluster_size INTEGER DEFAULT 5, ADD COLUMN IF NOT EXISTS induction_merge_threshold FLOAT DEFAULT 0.20;

UPDATE detection_config SET induction_min_cluster_size = COALESCE(induction_min_cluster_size, 5), induction_merge_threshold  = COALESCE(induction_merge_threshold, 0.20);