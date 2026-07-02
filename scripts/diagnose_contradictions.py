"""Diagnostic: what opposing claims exist in demo-fitness, and did detection fire on them?"""
from sqlalchemy import text
from core.database import SessionLocal
from models.database import Organization

db = SessionLocal()
db.rollback()

print('=== FitnessAgent claims about squats/deadlifts ===')
rows = db.execute(text("""
    SELECT ca.subject, ca.predicate, ca.object, ca.entity_hint
    FROM claims ca JOIN systems s ON s.id = ca.system_id
    WHERE s.name = 'FitnessAgent'
      AND (ca.subject ILIKE '%squat%' OR ca.subject ILIKE '%deadlift%' OR
           ca.object ILIKE '%squat%' OR ca.object ILIKE '%deadlift%' OR
           ca.predicate ILIKE '%squat%' OR ca.predicate ILIKE '%deadlift%')
    ORDER BY ca.extracted_at DESC LIMIT 10
""")).all()
for r in rows:
    print(f'  [{r.entity_hint}] {r.subject!r} :: {r.predicate!r} :: {r.object!r}')

print()
print('=== MedicalAgent claims about heavy compound / squats / deadlifts ===')
rows = db.execute(text("""
    SELECT ca.subject, ca.predicate, ca.object, ca.entity_hint
    FROM claims ca JOIN systems s ON s.id = ca.system_id
    WHERE s.name = 'MedicalAgent'
      AND (ca.subject ILIKE '%compound%' OR ca.subject ILIKE '%squat%' OR ca.subject ILIKE '%deadlift%' OR
           ca.object ILIKE '%compound%' OR ca.object ILIKE '%squat%' OR ca.object ILIKE '%deadlift%' OR
           ca.predicate ILIKE '%contraindic%' OR ca.predicate ILIKE '%not appropriate%')
    ORDER BY ca.extracted_at DESC LIMIT 10
""")).all()
for r in rows:
    print(f'  [{r.entity_hint}] {r.subject!r} :: {r.predicate!r} :: {r.object!r}')

print()
print('=== ANY contradictions in demo-fitness right now ===')
org = db.query(Organization).filter_by(slug='demo-fitness').first()
n = db.execute(text('SELECT COUNT(*) FROM contradictions WHERE org_id = :o'), {'o': org.id}).scalar()
print(f'  total: {n}')
rows = db.execute(text("""
    SELECT c.severity, c.cosine_similarity, c.nli_score, sa.name AS sys_a, sb.name AS sys_b
    FROM contradictions c
    JOIN claims ca ON ca.id = c.claim_a_id
    JOIN claims cb ON cb.id = c.claim_b_id
    JOIN systems sa ON sa.id = ca.system_id
    JOIN systems sb ON sb.id = cb.system_id
    WHERE c.org_id = :o
    ORDER BY c.detected_at DESC LIMIT 10
"""), {'o': org.id}).all()
for r in rows:
    print(f'  {r.severity} cos={r.cosine_similarity:.2f} nli={r.nli_score:.2f} {r.sys_a} vs {r.sys_b}')

db.close()