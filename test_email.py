"""
SMTP test — renders the HTML template with sample data and sends a real email
to all configured recipients.

Usage:
    python test_email.py
"""
from email_notifier import send_alert_email
from config import settings

SAMPLE_ALERT = {
    "alert_id":     "TEST-EMAIL-001",
    "host":         "test-server-01",
    "alert_type":   "cpu",
    "trigger_name": "High CPU utilization",
    "severity":     "High",
    "time":         "2026-04-14 10:00:00",
}

SAMPLE_ANALYSIS = {
    "top5_sorted": [
        ("java",        82.4),
        ("python3",     41.2),
        ("mysqld",      12.1),
        ("nginx",        8.3),
        ("node",         4.1),
    ],
    "process_stats": {
        "java":    {"value": 82.4, "unit": "CPU%", "historical_count": 14, "last_seen": "2026-04-10 08:22:00", "seen_before": True},
        "python3": {"value": 41.2, "unit": "CPU%", "historical_count":  7, "last_seen": "2026-04-11 14:05:00", "seen_before": True},
        "mysqld":  {"value": 12.1, "unit": "CPU%", "historical_count":  3, "last_seen": "2026-04-08 19:44:00", "seen_before": True},
        "nginx":   {"value":  8.3, "unit": "CPU%", "historical_count":  0, "last_seen": None,                  "seen_before": False},
        "node":    {"value":  4.1, "unit": "CPU%", "historical_count":  0, "last_seen": None,                  "seen_before": False},
    },
    "summary": (
        "Top 5 CPU-consuming processes on this host: java, python3, mysqld, nginx, node.\n\n"
        "Historical analysis (last 30 days):\n"
        "  • java: seen 14 time(s), last on 2026-04-10 08:22:00\n"
        "  • python3: seen 7 time(s), last on 2026-04-11 14:05:00\n"
        "  • mysqld: seen 3 time(s), last on 2026-04-08 19:44:00\n"
        "  • nginx: not seen before in previous alerts\n"
        "  • node: not seen before in previous alerts\n\n"
        "This appears to be a recurring issue. 'java' is the primary contributor "
        "(appeared 14 time(s) in the last 30 days)."
    ),
}

if __name__ == "__main__":
    print(f"Sending test email to: {settings.recipient_list}")
    print(f"SMTP: {settings.smtp_host}:{settings.smtp_port}")
    try:
        send_alert_email(SAMPLE_ALERT, SAMPLE_ANALYSIS)
        print("✓ Email sent successfully — check your inbox.")
    except Exception as e:
        print(f"✗ Failed to send email: {e}")
