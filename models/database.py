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
    name = Column(String(255), unique=True, nullable=False)
    provider = Column(String(50), default="openai")
    description = Column(Text)
    api_key_hash = Column(String(64), unique=True) # ADD THIS LINE
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
    system_id = Column(UUID(as_uuid=True), ForeignKey('systems.id', ondelete='CASCADE'))
    subject = Column(Text, nullable=False)
    predicate = Column(Text, nullable=False)
    object = Column(Text, nullable=False)
    context = Column(Text)
    entity_hint = Column(String(100))
    embedding = Column(Vector(1536))
    vector_clock = Column(JSONB, default=dict)
    parent_hashes = Column(JSONB, default=list)
    is_historical = Column(Boolean, default=False) # F4.4 Compliance: Historical Data Flag
    extracted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    entity_id = Column(UUID(as_uuid=True), ForeignKey('entities.id', ondelete='SET NULL'), nullable=True)

class EntityBeliefState(Base):
    __tablename__ = 'entity_belief_states'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id = Column(UUID(as_uuid=True), ForeignKey('systems.id', ondelete='CASCADE'))
    entity_name = Column(String(255), nullable=False)
    centroid_embedding = Column(Vector(1536))
    sample_count = Column(Integer, default=0)
    last_updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (UniqueConstraint('system_id', 'entity_name', name='_system_entity_uc'),)

class Contradiction(Base):
    __tablename__ = 'contradictions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_a_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    claim_b_id = Column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    cosine_similarity = Column(Float, nullable=False)
    nli_score = Column(Float, nullable=False)
    severity = Column(String(50), nullable=False)
    status = Column(String(50), default='open')
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    entity_id = Column(UUID(as_uuid=True), ForeignKey('entities.id', ondelete='SET NULL'), nullable=True)
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