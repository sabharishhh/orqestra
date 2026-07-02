import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Integer, ForeignKey, DateTime, Text,
    UniqueConstraint, Boolean, PrimaryKeyConstraint, Index,
)
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
    organization = relationship("Organization", lazy="joined")


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
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    system_id = Column(UUID(as_uuid=True), ForeignKey('systems.id', ondelete='CASCADE'))
    entity_id = Column(UUID(as_uuid=True), ForeignKey('entities.id', ondelete='SET NULL'), nullable=True)
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
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    claim_a_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    claim_b_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    entity_id = Column(UUID(as_uuid=True), ForeignKey('entities.id', ondelete='SET NULL'), nullable=True)
    regression_of = Column(UUID(as_uuid=True), ForeignKey('contradictions.id', ondelete='SET NULL'), nullable=True)
    lca_claim_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='SET NULL'), nullable=True)
    fork_distance_a = Column(Integer, default=0)
    fork_distance_b = Column(Integer, default=0)
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
    __tablename__ = 'organizations'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    vertical_preset = Column(String(50), default="general")
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CanonicalEntity(Base):
    """
    Per-store canonical vocabulary. The same canonical_name can exist in
    multiple stores within an org — that's what enables cross-store conflicts.

    Sprint 8 Task 3 (0003 migration): now also carries the DECLARED VALUE
    served to agents via /canon/resolve. `canonical_value IS NULL` means
    the row exists in the vocabulary but no human has declared its truth
    yet — resolve fails-null in that case (never falls back to consensus).
    Consensus lives in OBG and surfaces only as dashboard promotion
    candidates, not on the agent path.
    """
    __tablename__ = 'canonical_entities'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    store_id = Column(UUID(as_uuid=True), ForeignKey('canon_stores.id', ondelete='CASCADE'), nullable=False)
    canonical_name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(50), default="general", nullable=False)
    importance = Column(Float, default=0.5)
    severity_tier = Column(String(50), default="high")
    cost_critical_usd = Column(Integer, default=5000)
    cost_high_usd = Column(Integer, default=1000)
    source = Column(String(50), default="manual")  # 'preset' | 'manual' | 'declared' | 'promoted' | 'induced'

    # Sprint 8 Task 3: declared canonical value (the agent-facing truth)
    canonical_value = Column(Text, nullable=True)
    canonical_claim_text = Column(Text, nullable=True)
    declared_by = Column(String(255), nullable=True)
    declared_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('store_id', 'canonical_name', name='_store_canonical_uc'),)


class EntityAlias(Base):
    __tablename__ = 'entity_aliases'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_entity_id = Column(UUID(as_uuid=True), ForeignKey('canonical_entities.id', ondelete='CASCADE'), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    alias = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('org_id', 'alias', name='_org_alias_uc'),)


class DetectionConfig(Base):
    __tablename__ = 'detection_config'

    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True)
    bootstrap_min_samples = Column(Integer, default=3)
    high_variance_threshold = Column(Float, default=0.40)
    semantic_match_threshold = Column(Float, default=0.55)
    cluster_min_size = Column(Integer, default=5)
    cluster_merge_threshold = Column(Float, default=0.20)
    induction_lookback_days = Column(Integer, default=7)
    induction_cluster_threshold = Column(Float, default=0.35)
    induction_min_cluster_size = Column(Integer, default=5)
    induction_merge_threshold = Column(Float, default=0.20)
    regression_dedup_days = Column(Integer, default=7)
    semantic_suppression_distance = Column(Float, default=0.05)
    coherence_window_days = Column(Integer, default=30)
    recency_decay_lambda = Column(Float, default=0.05)
    nli_confidence_floor = Column(Float, default=0.70)
    blast_radius_decay = Column(Float, default=0.5)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CategoryThreshold(Base):
    __tablename__ = 'category_thresholds'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    category = Column(String(50), nullable=False)
    level_0_cosine = Column(Float, nullable=False)
    level_3_cosine = Column(Float, nullable=False)
    nli_floor = Column(Float, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('org_id', 'category', name='_org_category_uc'),)


class PiiAllowlistToken(Base):
    __tablename__ = 'pii_allowlist'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('org_id', 'token', name='_org_token_uc'),)


# =====================================================
# SUBSCRIPTION CANON LAYER (Sprint 8)
# =====================================================
# Canon is a set of scoped stores. Systems SUBSCRIBE to stores in
# precedence order. "Shared" and "scoped" are degenerate cases —
# a store everyone subscribes to at low precedence is shared;
# a store with narrow subscription at high precedence is scoped.
# All within one company. The company boundary (org_id) is the wall.

class CanonStore(Base):
    """
    A scoped canonical-knowledge store within an org.

    Day-one shape: one default store per org, auto-subscribed by every
    system. Multi-store setups (shared + team-scoped, etc.) are enabled
    by the schema but not yet the product surface.
    """
    __tablename__ = 'canon_stores'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    # owner_system_id NULL = org-level store; non-NULL = system-owned store.
    owner_system_id = Column(UUID(as_uuid=True), ForeignKey('systems.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", lazy="joined")

    __table_args__ = (
        UniqueConstraint('org_id', 'name', name='_org_store_name_uc'),
        Index('idx_canon_stores_org', 'org_id'),
    )


class SystemCanonSubscription(Base):
    """
    Ordered subscription list per system. Lower precedence_rank = higher
    priority in resolution. Resolution walks subscribed stores in rank
    order and returns the first definitive match.
    """
    __tablename__ = 'system_canon_subscriptions'

    system_id = Column(UUID(as_uuid=True), ForeignKey('systems.id', ondelete='CASCADE'), nullable=False)
    store_id = Column(UUID(as_uuid=True), ForeignKey('canon_stores.id', ondelete='CASCADE'), nullable=False)
    precedence_rank = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        PrimaryKeyConstraint('system_id', 'store_id', name='pk_system_canon_subscriptions'),
        Index('idx_scs_system_precedence', 'system_id', 'precedence_rank'),
    )


class CanonCrossStoreConflict(Base):
    """
    Log-only for Sprint 8. When resolution walks two subscribed stores
    that hold conflicting canonical values for the same canonical_name,
    higher precedence serves the agent (deterministic) AND the conflict
    is written here for human reconciliation. No dashboard surface yet.
    """
    __tablename__ = 'canon_cross_store_conflicts'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    canonical_name = Column(String(255), nullable=False)
    store_a_id = Column(UUID(as_uuid=True), ForeignKey('canon_stores.id', ondelete='CASCADE'), nullable=False)
    store_b_id = Column(UUID(as_uuid=True), ForeignKey('canon_stores.id', ondelete='CASCADE'), nullable=False)
    value_a = Column(Text)
    value_b = Column(Text)
    resolved_by_store_id = Column(UUID(as_uuid=True), ForeignKey('canon_stores.id', ondelete='SET NULL'), nullable=True)
    triggered_by_system_id = Column(UUID(as_uuid=True), ForeignKey('systems.id', ondelete='SET NULL'), nullable=True)
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_conflict_org_detected', 'org_id', 'detected_at'),
    )