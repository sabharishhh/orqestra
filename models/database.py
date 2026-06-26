import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, ForeignKey, DateTime, Text, UniqueConstraint, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class System(Base):
    __tablename__ = 'systems'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), unique=True, nullable=False)
    provider = Column(String(50), default="openai")
    description = Column(Text)
    api_key_hash = Column(String(64), unique=True) 
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Entity(Base):
    __tablename__ = 'entities'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name = Column(String(255), unique=True, nullable=False)
    aliases = Column(JSONB, default=list)
    entity_type = Column(String(50), default="general")
    importance = Column(Float, default=0.5)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class InductionCandidate(Base):
    __tablename__ = 'induction_candidates'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    suggested_name = Column(String(255), nullable=False)
    aliases = Column(JSONB, default=list)
    suggested_type = Column(String(50), default="general")
    suggested_importance = Column(Float, default=0.5)
    variance_score = Column(Float, default=0.0)
    claim_frequency = Column(Integer, default=0)
    sample_claims = Column(JSONB, default=dict)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Claim(Base):
    __tablename__ = 'claims'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)  # ← ADD
    system_id = Column(UUID(as_uuid=True), ForeignKey('systems.id', ondelete='CASCADE'))
    entity_id = Column(UUID(as_uuid=True), ForeignKey('entities.id', ondelete='SET NULL'), nullable=True)
    # --- PHASE 3 FIX: Structural Graph Integrity ---
    parent_claim_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='SET NULL'), nullable=True) 
    content_hash = Column(String(64), index=True) 
    logical_clock = Column(Integer, default=0)

    event_type = Column(String(50), default="CLAIM_EMITTED")
    
    subject = Column(Text, nullable=False)
    predicate = Column(Text, nullable=False)
    object = Column(Text, nullable=False)
    context = Column(Text)
    entity_hint = Column(String(100))
    embedding = Column(Vector(1536))
    vector_clock = Column(JSONB, default=dict)
    parent_hashes = Column(JSONB, default=list)
    is_historical = Column(Boolean, default=False) 
    extracted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class EntityBeliefState(Base):
    __tablename__ = 'entity_belief_states'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    system_id = Column(UUID(as_uuid=True), ForeignKey('systems.id', ondelete='CASCADE'))
    entity_name = Column(String(255), nullable=False)
    centroid_embedding = Column(Vector(1536))
    sample_count = Column(Integer, default=0)
    
    # --- PHASE 3 FIX: Welford's Math & Staleness Metrics ---
    belief_variance = Column(Float, default=0.0)
    staleness_score = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    recency_weight = Column(Float, default=1.0)
    first_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (UniqueConstraint('system_id', 'entity_name', name='_system_entity_uc'),)

class Contradiction(Base):
    __tablename__ = 'contradictions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)  # ← ADD

    claim_a_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    claim_b_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    entity_id = Column(UUID(as_uuid=True), ForeignKey('entities.id', ondelete='SET NULL'), nullable=True)
    regression_of = Column(UUID(as_uuid=True), ForeignKey('contradictions.id', ondelete='SET NULL'), nullable=True)
    # LCA: the earliest shared ancestor at which both systems still agreed
    lca_claim_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='SET NULL'), nullable=True)
    fork_distance_a = Column(Integer, default=0)   # hops from claim_a to LCA
    fork_distance_b = Column(Integer, default=0)   # hops from claim_b to LCA
    
    cosine_similarity = Column(Float, nullable=False)
    nli_score = Column(Float, nullable=False)
    severity = Column(String(50), nullable=False)
    cost_usd = Column(Integer, default=0)
    status = Column(String(50), default='open')
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (UniqueConstraint('claim_a_id', 'claim_b_id', name='unique_claim_pair'),)

class Resolution(Base):
    __tablename__ = 'resolutions'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contradiction_id = Column(UUID(as_uuid=True), ForeignKey('contradictions.id', ondelete='CASCADE'), unique=True)
    why_they_contradict = Column(Text, nullable=False)
    likely_stale_system = Column(String(255))
    risk_reason = Column(Text)
    recommended_action = Column(Text)
    estimated_cost = Column(String(255))
    target_uri = Column(String(512))
    status = Column(String(50), default="pending")
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class CoherenceScore(Base):
    __tablename__ = 'coherence_scores'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    system_id = Column(UUID(as_uuid=True), ForeignKey('systems.id', ondelete='CASCADE'), unique=True)
    score = Column(Float, default=1.0)
    active_contradictions = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    high_count = Column(Integer, default=0)
    medium_count = Column(Integer, default=0)
    low_count = Column(Integer, default=0)
    window_days = Column(Integer, default=30)
    computed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ContrastiveFeedback(Base):
    __tablename__ = 'contrastive_feedback'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contradiction_id = Column(UUID(as_uuid=True), ForeignKey('contradictions.id', ondelete='CASCADE'))
    claim_a_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    claim_b_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    entity_type = Column(String(50), default="general")
    nli_label = Column(String(50), nullable=False)
    is_hard_negative = Column(Boolean, default=False)
    feedback_source = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# =====================================================
# MULTI-TENANT CONFIG LAYER (Sprint 1.2)
# =====================================================

class Organization(Base):
    """Top-level tenant boundary. All claims, systems, configs scope here."""
    __tablename__ = 'organizations'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False)
    slug = Column(String(100), unique=True, nullable=False)   # e.g. 'demo-fitness'
    vertical_preset = Column(String(50), default="general")   # 'general' | 'consumer' | 'clinical' | 'finance' | 'legal' | 'policy'
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CanonicalEntity(Base):
    """Per-org closed vocabulary. Replaces hardcoded CANONICAL_ENTITIES."""
    __tablename__ = 'canonical_entities'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    canonical_name = Column(String(255), nullable=False)
    description = Column(Text)                                # human-readable; injected into extraction prompt
    category = Column(String(50), default="general", nullable=False)  # routes to category_thresholds
    importance = Column(Float, default=0.5)
    severity_tier = Column(String(50), default="high")        # 'critical' | 'high' | 'medium' | 'low'
    cost_critical_usd = Column(Integer, default=5000)
    cost_high_usd = Column(Integer, default=1000)
    source = Column(String(50), default="manual")             # 'preset' | 'manual' | 'induced'
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('org_id', 'canonical_name', name='_org_canonical_uc'),)


class EntityAlias(Base):
    """Flat alias→canonical lookup. One row per (canonical, alias) pair."""
    __tablename__ = 'entity_aliases'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_entity_id = Column(UUID(as_uuid=True), ForeignKey('canonical_entities.id', ondelete='CASCADE'), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)  # denorm for fast WHERE
    alias = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('org_id', 'alias', name='_org_alias_uc'),)


class DetectionConfig(Base):
    """Per-org tuning of all magic numbers in the funnel. 1:1 with Organization."""
    __tablename__ = 'detection_config'

    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True)
    # Funnel tuning
    bootstrap_min_samples = Column(Integer, default=3)
    high_variance_threshold = Column(Float, default=0.40)
    semantic_match_threshold = Column(Float, default=0.55)
    # Auto-induction
    cluster_min_size = Column(Integer, default=5)
    cluster_merge_threshold = Column(Float, default=0.20)
    induction_lookback_days = Column(Integer, default=7)
    induction_cluster_threshold = Column(Float, default=0.35)
    induction_min_cluster_size  = Column(Integer, default=5)
    induction_merge_threshold   = Column(Float, default=0.20)
    # Suppression / dedup
    regression_dedup_days = Column(Integer, default=7)
    semantic_suppression_distance = Column(Float, default=0.05)
    # Scoring
    coherence_window_days = Column(Integer, default=30)
    recency_decay_lambda = Column(Float, default=0.05)
    nli_confidence_floor = Column(Float, default=0.70)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CategoryThreshold(Base):
    """Per-org per-category cosine thresholds. Routes via CanonicalEntity.category."""
    __tablename__ = 'category_thresholds'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    category = Column(String(50), nullable=False)
    level_0_cosine = Column(Float, nullable=False)            # OBG centroid divergence threshold
    level_3_cosine = Column(Float, nullable=False)            # HNSW neighbor distance threshold
    nli_floor = Column(Float, nullable=True)                  # falls back to DetectionConfig.nli_confidence_floor
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('org_id', 'category', name='_org_category_uc'),)


class PiiAllowlistToken(Base):
    """Per-org PII scrubber allowlist (e.g. clinical: mg/ml/egfr; finance: bps/aum)."""
    __tablename__ = 'pii_allowlist'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('org_id', 'token', name='_org_token_uc'),)