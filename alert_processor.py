"""
Core workflow orchestration.
Called as a FastAPI BackgroundTask — runs entirely async.

Flow:
  1. Sleep ALERT_WAIT_SECONDS (default 3 min)
  2. Check Zabbix: is trigger still active?
     NO  → delete alert record, stop (no notifications sent)
     YES → fetch top-N processes + history → analyze → notify → delete alert record

Notifications sent (each independently enabled via .env):
  - Email   : always sent when EMAIL_RECIPIENTS is set
  - Teams   : sent when TEAMS_ENABLED=true and TEAMS_WEBHOOK_URL is set

Alert records are deleted once the workflow completes (resolved or notifications sent).
ProcessSnapshot records are kept — they build the local 30-day history.
Only "error" records remain in the DB for debugging.
"""
import asyncio
import logging
from datetime import datetime

from database import SessionLocal
from models import Alert, ProcessSnapshot
from zabbix_client import ZabbixClient
from process_analyzer import analyze_processes
from email_notifier import send_alert_email
from teams_notifier import send_teams_notification
from config import settings

logger = logging.getLogger(__name__)


async def process_alert_workflow(alert_data: dict) -> None:
    alert_id     = alert_data["alert_id"]
    host         = alert_data["host"]
    alert_type   = alert_data["alert_type"]
    trigger_name = alert_data["trigger_name"]

    logger.info(
        f"[{alert_id}] Scheduled — will check in {settings.alert_wait_seconds}s."
    )
    await asyncio.sleep(settings.alert_wait_seconds)

    db     = SessionLocal()
    client = ZabbixClient()

    try:
        # ── Step 1: Is the alert still active? ──────────────────────────
        is_active = await client.is_trigger_active(host, trigger_name)

        if not is_active:
            logger.info(f"[{alert_id}] Resolved within wait window. No email sent.")
            _delete_alert(db, alert_id)
            return

        logger.info(f"[{alert_id}] Still active. Starting deep analysis.")

        # ── Step 2: Fetch current top-N processes ────────────────────────
        top5 = await client.get_top5_current(host, alert_type)
        if not top5:
            logger.error(f"[{alert_id}] No process data returned from Zabbix.")
            _set_status(db, alert_id, "error")
            return

        # ── Step 3: Fetch history ────────────────────────────────────────
        history = await client.get_process_history_30d(host, alert_type)

        # ── Step 4: Analyse ──────────────────────────────────────────────
        analysis = analyze_processes(top5, history, alert_type)

        # ── Step 5: Persist snapshot for local history ───────────────────
        _save_snapshot(db, alert_id, host, alert_type, analysis["top5_sorted"])

        # ── Step 6: Send email (sync → run in thread pool) ───────────────
        await asyncio.to_thread(send_alert_email, alert_data, analysis)

        # ── Step 6b: Send Teams notification (async, optional) ───────────
        await send_teams_notification(alert_data, analysis)

        # ── Step 7: Delete alert record — email is the record ────────────
        _delete_alert(db, alert_id)
        logger.info(f"[{alert_id}] Workflow complete. Notifications sent, alert record removed.")

    except Exception:
        logger.exception(f"[{alert_id}] Workflow failed.")
        _set_status(db, alert_id, "error")
    finally:
        db.close()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _set_status(db, alert_id: str, status: str) -> None:
    alert = db.query(Alert).filter_by(alert_id=alert_id).first()
    if alert:
        alert.status = status
        db.commit()


def _delete_alert(db, alert_id: str) -> None:
    """
    Remove the alert record once the workflow is done.
    ProcessSnapshot rows are intentionally kept — they build the 30-day history.
    Only 'error' status records remain in the DB.
    """
    alert = db.query(Alert).filter_by(alert_id=alert_id).first()
    if alert:
        db.delete(alert)
        db.commit()


def _save_snapshot(
    db,
    alert_id: str,
    host: str,
    alert_type: str,
    top5_sorted: list[tuple[str, float]],
) -> None:
    now = datetime.utcnow()
    for name, value in top5_sorted:
        db.add(ProcessSnapshot(
            alert_id      = alert_id,
            host          = host,
            alert_type    = alert_type,
            process_name  = name,
            process_value = value,
            snapshot_time = now,
        ))
    db.commit()
