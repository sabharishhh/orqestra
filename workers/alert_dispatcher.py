import os
import httpx
from dotenv import load_dotenv
import logging
from observability import get_logger
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Contradiction, Claim, Resolution, System

load_dotenv()

logger = get_logger(__name__)

# In production, this would be your real Slack/Discord Webhook URL
# For testing, you can grab a free one at https://webhook.site/
WEBHOOK_URL = os.environ.get("ORQESTRA_SLACK_WEBHOOK_URL", "https://webhook.site/03d57e80-62ea-4103-a5e1-3ae04cbc91db")

def send_slack_alert(resolution_id: str):
    """Worker 6 Phase: Dispatches high-severity alerts to external systems."""
    if not WEBHOOK_URL:
        logger.warning(f"No WEBHOOK_URL configured. Skipping alert for Resolution [{resolution_id}]")
        return

    db: Session = SessionLocal()
    try:
        res = db.query(Resolution).filter_by(id=resolution_id).first()
        if not res: return
        
        contra = db.query(Contradiction).filter_by(id=res.contradiction_id).first()
        claim_a = db.query(Claim).filter_by(id=contra.claim_a_id).first()
        claim_b = db.query(Claim).filter_by(id=contra.claim_b_id).first()
        sys_a = db.query(System).filter_by(id=claim_a.system_id).first()
        sys_b = db.query(System).filter_by(id=claim_b.system_id).first()

        # Format a Slack Block-Kit Message
        slack_payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🚨 High Severity AI Collision Detected: {claim_a.entity_hint.upper()}",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*System A ({sys_a.name}):*\n>\"{claim_a.subject} {claim_a.predicate} {claim_a.object}\""},
                        {"type": "mrkdwn", "text": f"*System B ({sys_b.name}):*\n>\"{claim_b.subject} {claim_b.predicate} {claim_b.object}\""}
                    ]
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Diagnostic Reason:*\n{res.why_they_contradict}\n\n*Business Risk:*\n`{res.risk_reason}`\n\n*Target Remediation URI:*\n`{res.target_uri}`"
                    }
                }
            ]
        }

        response = httpx.post(WEBHOOK_URL, json=slack_payload)
        response.raise_for_status()
        logger.info(f"✅ Successfully dispatched Slack alert for Resolution [{resolution_id}]")

    except Exception as e:
        logger.error(f"Failed to dispatch alert: {e}")
    finally:
        db.close()