import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, ForeignKey, DateTime, Text, UniqueConstraint
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
    extracted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

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
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))