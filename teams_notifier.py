"""
Sends Teams channel notifications via Incoming Webhook or Workflow Connector.

Setup (pick ONE):
  Option A — Legacy Incoming Webhook (classic Teams):
    Teams channel → ··· → Connectors → Incoming Webhook → Configure → copy URL

  Option B — Workflow Connector (new Teams / recommended by Microsoft):
    Teams channel → Workflows → "Post to a channel when a webhook request is received"
    → copy the generated HTTPS URL

Both options accept the same JSON payload format used here.
Set TEAMS_WEBHOOK_URL in .env to enable; leave blank to disable.
"""
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Adaptive Card color per Zabbix severity
_SEVERITY_COLOR: dict[str, str] = {
    "disaster":        "Attention",   # red
    "critical":        "Attention",
    "high":            "Attention",
    "average":         "Warning",     # yellow
    "warning":         "Warning",
    "information":     "Accent",      # blue
    "not classified":  "Default",
}


def _build_adaptive_card(alert_data: dict, analysis: dict) -> dict:
    host         = alert_data["host"]
    alert_type   = alert_data["alert_type"].upper()
    severity     = alert_data["severity"]
    trigger_name = alert_data["trigger_name"]
    alert_time   = alert_data["time"]
    unit         = "CPU%" if alert_data["alert_type"] == "cpu" else "MEM%"

    color = _SEVERITY_COLOR.get(severity.lower(), "Default")

    # ── Process rows ──────────────────────────────────────────────────────────
    process_facts: list[dict] = []
    for name, value in analysis["top5_sorted"]:
        stats      = analysis["process_stats"].get(name, {})
        seen       = stats.get("seen_before", False)
        hist_count = stats.get("historical_count", 0)
        tag        = "Recurring" if seen else "New"
        process_facts.append({
            "title": name,
            "value": f"{value:.1f} {unit}  |  {tag} ({hist_count}x in 30d)",
        })

    # ── Classification text blocks ────────────────────────────────────────────
    classification_blocks: list[dict] = []
    recurring  = analysis.get("recurring_processes", [])
    new_procs  = analysis.get("new_processes", [])

    if recurring:
        classification_blocks.append({
            "type":    "TextBlock",
            "text":    f"Recurring Processes: {', '.join(recurring)}",
            "wrap":    True,
            "color":   "Warning",
            "spacing": "Small",
        })
    if new_procs:
        classification_blocks.append({
            "type":    "TextBlock",
            "text":    f"New Issues Detected: {', '.join(new_procs)}",
            "wrap":    True,
            "color":   "Attention",
            "spacing": "Small",
        })

    card: dict = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type":    "AdaptiveCard",
        "version": "1.4",
        "body": [
            # ── Header ────────────────────────────────────────────────────────
            {
                "type":  "Container",
                "style": "emphasis",
                "bleed": True,
                "items": [
                    {
                        "type":   "TextBlock",
                        "text":   f"{alert_type} Alert — {host}",
                        "weight": "Bolder",
                        "size":   "Large",
                        "color":  color,
                        "wrap":   True,
                    },
                    {
                        "type":     "TextBlock",
                        "text":     trigger_name,
                        "wrap":     True,
                        "spacing":  "None",
                        "isSubtle": True,
                    },
                ],
            },
            # ── Alert metadata ────────────────────────────────────────────────
            {
                "type":    "FactSet",
                "spacing": "Medium",
                "facts": [
                    {"title": "Host",     "value": host},
                    {"title": "Type",     "value": alert_type},
                    {"title": "Severity", "value": severity.capitalize()},
                    {"title": "Time",     "value": str(alert_time)},
                ],
            },
            # ── Top processes ─────────────────────────────────────────────────
            {
                "type":      "TextBlock",
                "text":      f"**Top {len(analysis['top5_sorted'])} Processes**",
                "weight":    "Bolder",
                "spacing":   "Medium",
                "separator": True,
            },
            {
                "type":  "FactSet",
                "facts": process_facts,
            },
            # ── Recurring / new classification ────────────────────────────────
            *classification_blocks,
            # ── Summary ───────────────────────────────────────────────────────
            {
                "type":      "TextBlock",
                "text":      "**Analysis Summary**",
                "weight":    "Bolder",
                "spacing":   "Medium",
                "separator": True,
            },
            {
                "type":     "TextBlock",
                "text":     analysis["summary"],
                "wrap":     True,
                "spacing":  "Small",
                "isSubtle": True,
            },
        ],
    }
    return card


async def send_teams_notification(alert_data: dict, analysis: dict) -> None:
    """
    Posts an Adaptive Card to the configured Teams channel webhook.
    No-op if TEAMS_WEBHOOK_URL is not set or TEAMS_ENABLED is false.
    """
    if not settings.teams_enabled:
        return
    if not settings.teams_webhook_url:
        logger.warning("TEAMS_ENABLED=true but TEAMS_WEBHOOK_URL is not set — skipping.")
        return

    card = _build_adaptive_card(alert_data, analysis)

    # Both legacy Incoming Webhooks and the new Workflow Connector accept
    # the "message + adaptive card attachment" envelope below.
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl":  None,
                "content":     card,
            }
        ],
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            settings.teams_webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()

    logger.info(
        "Teams notification sent — alert_id=%s host=%s",
        alert_data["alert_id"],
        alert_data["host"],
    )
