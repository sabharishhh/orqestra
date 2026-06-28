"""
Seed (or upsert) an organization from a vertical preset YAML.

Usage:
    docker compose exec api python -m scripts.seed_org \
        --name "Demo Fitness" \
        --slug demo-fitness \
        --preset consumer

    docker compose exec api python -m scripts.seed_org \
        --name "Acme Health" --slug acme-health --preset clinical

The CLI is idempotent — re-running with the same slug updates the org's
preset, config, canonical entities, aliases, category thresholds, and
PII allowlist to match the YAML. Existing operational data (claims,
contradictions, OBG) is never touched.
"""
import argparse
import logging
from observability import get_logger
import sys
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.database import SessionLocal
from models.database import (
    Organization,
    CanonicalEntity,
    EntityAlias,
    DetectionConfig,
    CategoryThreshold,
    PiiAllowlistToken,
)

logging.basicConfig(level=logging.INFO, format="[seed_org] %(message)s")
logger = get_logger(__name__)

PRESETS_DIR = Path(__file__).resolve().parent.parent / "presets"


def load_preset(preset_name: str) -> dict:
    """Load a vertical preset YAML by name."""
    path = PRESETS_DIR / f"{preset_name}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in PRESETS_DIR.glob("*.yaml"))
        raise FileNotFoundError(
            f"Preset '{preset_name}' not found at {path}. "
            f"Available: {available or '(none — create presets/ directory)'}"
        )
    with open(path) as f:
        return yaml.safe_load(f)


def upsert_organization(db: Session, name: str, slug: str, preset_name: str, description: Optional[str]) -> Organization:
    org = db.query(Organization).filter_by(slug=slug).first()
    if org:
        logger.info(f"Updating existing org '{slug}' ({org.id})")
        org.name = name
        org.vertical_preset = preset_name
        if description:
            org.description = description
    else:
        logger.info(f"Creating new org '{slug}'")
        org = Organization(
            name=name,
            slug=slug,
            vertical_preset=preset_name,
            description=description,
        )
        db.add(org)
    db.flush()
    return org


def upsert_detection_config(db: Session, org: Organization, cfg: dict):
    row = db.query(DetectionConfig).filter_by(org_id=org.id).first()
    if not row:
        row = DetectionConfig(org_id=org.id)
        db.add(row)
    for k, v in cfg.items():
        if not hasattr(row, k):
            logger.warning(f"detection_config: ignoring unknown key '{k}'")
            continue
        setattr(row, k, v)
    db.flush()
    logger.info(f"detection_config: {len(cfg)} fields set")


def upsert_category_thresholds(db: Session, org: Organization, items: list[dict]):
    for item in items:
        category = item["category"]
        row = db.query(CategoryThreshold).filter_by(org_id=org.id, category=category).first()
        if not row:
            row = CategoryThreshold(org_id=org.id, category=category,
                                    level_0_cosine=item["level_0_cosine"],
                                    level_3_cosine=item["level_3_cosine"],
                                    nli_floor=item.get("nli_floor"))
            db.add(row)
        else:
            row.level_0_cosine = item["level_0_cosine"]
            row.level_3_cosine = item["level_3_cosine"]
            row.nli_floor = item.get("nli_floor")
    db.flush()
    logger.info(f"category_thresholds: {len(items)} categories")


def upsert_canonical_entities(db: Session, org: Organization, items: list[dict]):
    for item in items:
        name = item["name"]
        ent = db.query(CanonicalEntity).filter_by(org_id=org.id, canonical_name=name).first()
        if not ent:
            ent = CanonicalEntity(
                org_id=org.id,
                canonical_name=name,
                description=item.get("description"),
                category=item.get("category", "general"),
                importance=item.get("importance", 0.5),
                severity_tier=item.get("severity_tier", "high"),
                cost_critical_usd=item.get("cost_critical_usd", 5000),
                cost_high_usd=item.get("cost_high_usd", 1000),
                source="preset",
            )
            db.add(ent)
            db.flush()
        else:
            ent.description = item.get("description", ent.description)
            ent.category = item.get("category", ent.category)
            ent.importance = item.get("importance", ent.importance)
            ent.severity_tier = item.get("severity_tier", ent.severity_tier)
            ent.cost_critical_usd = item.get("cost_critical_usd", ent.cost_critical_usd)
            ent.cost_high_usd = item.get("cost_high_usd", ent.cost_high_usd)
            db.flush()

        # Refresh aliases — delete current, re-insert from YAML to keep in sync
        db.query(EntityAlias).filter_by(canonical_entity_id=ent.id).delete()
        db.flush()
        aliases = item.get("aliases", []) or []
        for alias in aliases:
            db.add(EntityAlias(
                canonical_entity_id=ent.id,
                org_id=org.id,
                alias=alias.lower().strip().replace(" ", "_"),
            ))
        db.flush()
    logger.info(f"canonical_entities: {len(items)} entities (+ aliases)")


def upsert_pii_allowlist(db: Session, org: Organization, tokens: list[str]):
    # Replace wholesale — preset is the source of truth
    db.query(PiiAllowlistToken).filter_by(org_id=org.id).delete()
    db.flush()
    for tok in tokens:
        db.add(PiiAllowlistToken(org_id=org.id, token=tok.lower().strip()))
    db.flush()
    logger.info(f"pii_allowlist: {len(tokens)} tokens")


def seed(name: str, slug: str, preset_name: str, description: Optional[str] = None) -> str:
    preset = load_preset(preset_name)
    db: Session = SessionLocal()
    try:
        org = upsert_organization(db, name=name, slug=slug, preset_name=preset_name, description=description)

        if cfg := preset.get("detection_config"):
            upsert_detection_config(db, org, cfg)
        if items := preset.get("category_thresholds"):
            upsert_category_thresholds(db, org, items)
        if items := preset.get("canonical_entities"):
            upsert_canonical_entities(db, org, items)
        if tokens := preset.get("pii_allowlist"):
            upsert_pii_allowlist(db, org, tokens)

        db.commit()
        logger.info(f"✅ Org seeded: name='{name}' slug='{slug}' preset='{preset_name}' id={org.id}")
        return str(org.id)
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Seed failed: {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Seed/upsert an Orqestra org from a vertical preset.")
    parser.add_argument("--name", required=True, help='Display name, e.g. "Demo Fitness"')
    parser.add_argument("--slug", required=True, help="URL-safe identifier, e.g. 'demo-fitness'")
    parser.add_argument("--preset", required=True, help="Preset YAML stem under presets/, e.g. 'consumer'")
    parser.add_argument("--description", default=None, help="Optional human-readable description")
    args = parser.parse_args()

    try:
        seed(name=args.name, slug=args.slug, preset_name=args.preset, description=args.description)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()