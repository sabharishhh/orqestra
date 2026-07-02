"""
Mint (or rotate) the DashboardViewer system for the demo-fitness org.
Prints the raw token for the operator to place in frontend/.env.local
as VITE_ORQESTRA_TOKEN. Idempotent — reruns rotate the token.
"""
import hashlib
import logging
import secrets
import sys

from core.database import SessionLocal
from models.database import CanonStore, Organization, System, SystemCanonSubscription

logging.basicConfig(level=logging.INFO, format="[mint_viewer] %(message)s")
logger = logging.getLogger(__name__)

ORG_SLUG = "demo-fitness"
VIEWER_NAME = "DashboardViewer"


def main():
    raw = "oq-" + secrets.token_hex(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()

    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug=ORG_SLUG).first()
        if not org:
            logger.error(f"org '{ORG_SLUG}' not found")
            sys.exit(1)

        viewer = db.query(System).filter_by(name=VIEWER_NAME).first()
        if viewer:
            viewer.api_key_hash = hashed
            viewer.org_id = org.id
            logger.info(f"rotated {VIEWER_NAME} token (id={viewer.id})")
        else:
            viewer = System(
                org_id=org.id,
                name=VIEWER_NAME,
                provider="internal",
                description="Read token for the dashboard frontend.",
                api_key_hash=hashed,
            )
            db.add(viewer)
            db.flush()
            logger.info(f"created {VIEWER_NAME} (id={viewer.id})")

        # Subscribe to default store so /canon/list resolves scope.
        store = db.query(CanonStore).filter_by(org_id=org.id, name="default").first()
        if store:
            exists = db.query(SystemCanonSubscription).filter_by(
                system_id=viewer.id, store_id=store.id
            ).first()
            if not exists:
                db.add(SystemCanonSubscription(
                    system_id=viewer.id, store_id=store.id, precedence_rank=0,
                ))
                logger.info("subscribed to default store")
        db.commit()

        print()
        print("=" * 64)
        print("Put this in frontend/.env.local :")
        print(f"VITE_ORQESTRA_TOKEN={raw}")
        print("=" * 64)
    finally:
        db.close()


if __name__ == "__main__":
    main()