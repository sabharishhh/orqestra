"""Timing: when were the 12 contradictions detected, relative to measurement runs?"""
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import text
from core.database import SessionLocal
from models.database import Organization

db = SessionLocal()
db.rollback()
org = db.query(Organization).filter_by(slug='demo-fitness').first()

# Load measurement JSONs to get run timestamps
outputs = Path('/mnt/user-data/outputs/sprint10_measurements')
measurement_runs = []
for phase in ('canon_on', 'canon_off'):
    with open(outputs / f'measurement_{phase}.json') as f:
        d = json.load(f)
    for run in d['per_run']:
        # Each run's fire_results has no explicit timestamp; use recorded_at
        # as an approximate end-of-phase marker, and infer run start from
        # phase_duration / runs. Coarse but fine for diagnostic.
        pass
    measurement_runs.append({
        'phase': phase,
        'recorded_at': datetime.fromtimestamp(d['recorded_at'], tz=timezone.utc),
        'phase_duration_s': d['phase_duration_s'],
        'runs': d['runs'],
    })

for m in measurement_runs:
    start = m['recorded_at'].timestamp() - m['phase_duration_s']
    print(f"phase={m['phase']:9s}  start={datetime.fromtimestamp(start, tz=timezone.utc)}  "
          f"end={m['recorded_at']}  duration={m['phase_duration_s']:.0f}s")

print()
print("=== All contradictions with detection time ===")
rows = db.execute(text("""
    SELECT c.detected_at, c.severity, sa.name AS sys_a, sb.name AS sys_b,
           ca.entity_hint, cb.entity_hint AS entity_b
    FROM contradictions c
    JOIN claims ca ON ca.id = c.claim_a_id
    JOIN claims cb ON cb.id = c.claim_b_id
    JOIN systems sa ON sa.id = ca.system_id
    JOIN systems sb ON sb.id = cb.system_id
    WHERE c.org_id = :o
    ORDER BY c.detected_at
"""), {'o': org.id}).all()
for r in rows:
    print(f"  {r.detected_at}  {r.severity:6s}  {r.sys_a:14s} vs {r.sys_b:14s}  "
          f"entities=({r.entity_hint}, {r.entity_b})")

db.close()