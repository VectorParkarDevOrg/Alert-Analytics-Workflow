"""
Alert Analytics Workflow — FastAPI entry point.

Endpoints:
  POST /alert              — receive alert from Zabbix / monitoring system
  GET  /alert/{id}/status  — check processing status
  GET  /alerts             — list recent alerts
  GET  /health             — liveness check
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from database import init_db, get_db
from models import Alert
from alert_processor import process_alert_workflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialised.")
    yield


app = FastAPI(
    title="Alert Analytics Workflow",
    description="Intelligent CPU/Memory alert analysis with Zabbix + Gmail.",
    version="1.0.0",
    lifespan=lifespan,
)


# Zabbix numeric severity → string label
_SEVERITY_MAP = {
    0: "Not classified",
    1: "Information",
    2: "Warning",
    3: "Average",
    4: "High",
    5: "Disaster",
}


# ── Request schema ────────────────────────────────────────────────────────────

class AlertPayload(BaseModel):
    alert_id:     str
    host:         str
    alert_type:   str   # "cpu" | "memory"
    trigger_name: str
    severity:     str
    time:         str   # "YYYY-MM-DD HH:MM:SS"


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/zabbix/events", status_code=200)
async def zabbix_connector_events(request: Request, background_tasks: BackgroundTasks):
    """
    Receives event stream from Zabbix Connector (Zabbix 6.4+).
    Payload: {"events": [{eventid, name, value, severity, clock, hosts:[{host}]}, ...]}
    Filters: only PROBLEM events (value==1) for CPU or Memory triggers.
    """
    try:
        body = await request.json()
    except Exception:
        logger.warning("Zabbix connector: invalid JSON body received.")
        return {"status": "error", "reason": "invalid JSON"}

    # Zabbix 7.x sends one event per request as a flat object.
    # Guard against wrapped {"events":[...]} or bare list too.
    if isinstance(body, dict) and "events" in body:
        events = body["events"]
    elif isinstance(body, dict):
        events = [body]          # single event object — standard Zabbix 7.x format
    elif isinstance(body, list):
        events = body
    else:
        return {"status": "error", "reason": "unexpected payload structure"}

    accepted, skipped = [], 0

    for event in events:
        # Only PROBLEM events
        if event.get("value") != 1:
            skipped += 1
            continue

        trigger_name = event.get("name", "")
        name_lower   = trigger_name.lower()

        # Classify alert type from trigger name
        if "cpu" in name_lower or "processor" in name_lower:
            alert_type = "cpu"
        elif "memory" in name_lower or "mem" in name_lower or "ram" in name_lower:
            alert_type = "memory"
        else:
            skipped += 1
            continue

        # Extract host
        hosts = event.get("hosts", [])
        if not hosts:
            skipped += 1
            continue
        host = hosts[0].get("host", "")
        if not host:
            skipped += 1
            continue

        alert_id   = str(event.get("eventid", ""))
        severity   = _SEVERITY_MAP.get(int(event.get("severity", 0)), "Unknown")
        clock      = int(event.get("clock", 0))
        alert_time = datetime.utcfromtimestamp(clock)

        db = next(get_db())
        if db.query(Alert).filter_by(alert_id=alert_id).first():
            db.close()
            skipped += 1
            continue

        alert = Alert(
            alert_id     = alert_id,
            host         = host,
            alert_type   = alert_type,
            trigger_name = trigger_name,
            severity     = severity,
            alert_time   = alert_time,
            status       = "pending",
        )
        db.add(alert)
        db.commit()
        db.close()

        payload = {
            "alert_id":     alert_id,
            "host":         host,
            "alert_type":   alert_type,
            "trigger_name": trigger_name,
            "severity":     severity,
            "time":         alert_time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        background_tasks.add_task(process_alert_workflow, payload)
        accepted.append(alert_id)

        logger.info(
            f"Connector event accepted — id={alert_id}, host={host}, type={alert_type}"
        )

    return {"status": "ok", "accepted": len(accepted), "skipped": skipped}


@app.post("/alert", status_code=202)
async def receive_alert(payload: AlertPayload, background_tasks: BackgroundTasks):
    """
    Accepts an alert from the monitoring system.
    Only CPU and Memory alert types are processed; others are ignored.
    Analysis runs 3 minutes later in the background.
    """
    alert_type = payload.alert_type.strip().lower()

    if alert_type not in ("cpu", "memory"):
        return {
            "status":  "ignored",
            "reason":  f"alert_type '{payload.alert_type}' is not supported (cpu/memory only)",
            "alert_id": payload.alert_id,
        }

    db = next(get_db())

    # Deduplicate — same alert_id received twice
    if db.query(Alert).filter_by(alert_id=payload.alert_id).first():
        db.close()
        return {"status": "duplicate", "alert_id": payload.alert_id}

    # Validate time format
    try:
        alert_time = datetime.strptime(payload.time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        db.close()
        raise HTTPException(
            status_code=422,
            detail="Field 'time' must be in format 'YYYY-MM-DD HH:MM:SS'",
        )

    # Persist to DB
    alert = Alert(
        alert_id     = payload.alert_id,
        host         = payload.host,
        alert_type   = alert_type,
        trigger_name = payload.trigger_name,
        severity     = payload.severity,
        alert_time   = alert_time,
        status       = "pending",
    )
    db.add(alert)
    db.commit()
    db.close()

    # Schedule background workflow
    background_tasks.add_task(process_alert_workflow, payload.model_dump())

    logger.info(
        f"Alert accepted — id={payload.alert_id}, host={payload.host}, "
        f"type={alert_type}"
    )
    return {
        "status":   "accepted",
        "alert_id": payload.alert_id,
        "message":  "Alert received. Analysis will run in 3 minutes.",
    }


@app.get("/alert/{alert_id}/status")
def get_alert_status(alert_id: str):
    """Returns the current processing status of a specific alert."""
    db   = next(get_db())
    alert = db.query(Alert).filter_by(alert_id=alert_id).first()
    db.close()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        "alert_id":    alert.alert_id,
        "host":        alert.host,
        "alert_type":  alert.alert_type,
        "trigger_name":alert.trigger_name,
        "severity":    alert.severity,
        "alert_time":  str(alert.alert_time),
        "status":      alert.status,
        "created_at":  str(alert.created_at),
    }


@app.get("/alerts")
def list_alerts(limit: int = 50):
    """Lists the most recent alerts (latest first)."""
    db     = next(get_db())
    alerts = (
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .all()
    )
    db.close()

    return [
        {
            "alert_id":   a.alert_id,
            "host":       a.host,
            "alert_type": a.alert_type,
            "severity":   a.severity,
            "status":     a.status,
            "created_at": str(a.created_at),
        }
        for a in alerts
    ]


@app.get("/health")
def health():
    return {"status": "ok"}
