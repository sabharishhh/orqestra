-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Registered AI Systems (The Agents)
CREATE TABLE IF NOT EXISTS systems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) UNIQUE NOT NULL,
    provider VARCHAR(50) DEFAULT 'openai',
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- SCCG: Sparse Causal Claim Graph
CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID REFERENCES systems(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    context TEXT,
    entity_hint VARCHAR(100),
    embedding vector(1536),                 -- OpenAI text-embedding-3-small dimension
    vector_clock JSONB DEFAULT '{}'::jsonb, -- Tracks causal provenance
    parent_hashes JSONB DEFAULT '[]'::jsonb,-- Upstream claim lineage
    is_historical BOOLEAN DEFAULT FALSE,    -- F4.4 Compliance: Historical Data Flag
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- F1.6 Guardrail: STRICT HNSW INDEXING (No IVFFlat)
CREATE INDEX ON claims USING hnsw (embedding vector_cosine_ops);

-- OBG: Organizational Belief Graph (Running Centroids)
CREATE TABLE IF NOT EXISTS entity_belief_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID REFERENCES systems(id) ON DELETE CASCADE,
    entity_name VARCHAR(255) NOT NULL,
    centroid_embedding vector(1536),        -- The running mean of all claims for this entity
    sample_count INTEGER DEFAULT 0,         -- Used for Welford's online algorithm
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(system_id, entity_name)
);

-- Detected Contradictions (The Edges)
CREATE TABLE IF NOT EXISTS contradictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_a_id UUID REFERENCES claims(id) ON DELETE CASCADE,
    claim_b_id UUID REFERENCES claims(id) ON DELETE CASCADE,
    cosine_similarity FLOAT NOT NULL,
    nli_score FLOAT NOT NULL,
    severity VARCHAR(50) NOT NULL,          -- critical, high, medium, low
    status VARCHAR(50) DEFAULT 'open',      -- open, resolved, ignored
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- F1.4 Guardrail: Normalize claim pairs to prevent duplicate alerts
    CONSTRAINT unique_claim_pair UNIQUE (claim_a_id, claim_b_id)
);

-- Resolutions (The Explainer Output)
CREATE TABLE IF NOT EXISTS resolutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contradiction_id UUID REFERENCES contradictions(id) ON DELETE CASCADE UNIQUE,
    why_they_contradict TEXT NOT NULL,
    likely_stale_system VARCHAR(255),
    risk_reason TEXT,
    recommended_action TEXT,
    estimated_cost VARCHAR(255),
    target_uri VARCHAR(512),                -- F9.2 Guardrail: Must be a URI, not a description
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);