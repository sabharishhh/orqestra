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

-- F1.6 Guardrail: STRICT HNSW INDEXING (No IVFFlat)
CREATE INDEX ON claims USING hnsw (embedding vector_cosine_ops);

-- OBG: Organizational Belief Graph (Running Centroids)
CREATE TABLE IF NOT EXISTS entity_belief_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID REFERENCES systems(id) ON DELETE CASCADE,
    entity_name VARCHAR(255) NOT NULL,
    centroid_embedding vector(1536),        
    sample_count INTEGER DEFAULT 0,         
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
