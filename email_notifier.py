"""
Sends HTML alert-analysis email via Gmail SMTP (TLS, port 587).
Uses a Gmail App Password — NOT your account login password.
"""
import smtplib
import ssl
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config import settings

logger = logging.getLogger(__name__)

_template_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=True,
)


def send_alert_email(alert_data: dict, analysis: dict) -> None:
    """
    Renders the HTML template and sends it via Gmail SMTP.
    This is a synchronous function — call via asyncio.to_thread() from async code.
    """
    template = _template_env.get_template("alert_email.html")

    html_body = template.render(
        host         = alert_data["host"],
        alert_type   = alert_data["alert_type"].upper(),
        trigger_name = alert_data["trigger_name"],
        severity     = alert_data["severity"],
        alert_time   = alert_data["time"],
        unit         = "CPU%" if alert_data["alert_type"] == "cpu" else "MEM%",
        top5         = analysis["top5_sorted"],
        process_stats= analysis["process_stats"],
        summary      = analysis["summary"],
    )

    subject = (
        f"[{alert_data['severity']}] "
        f"{alert_data['alert_type'].upper()} Alert Analysis — "
        f"{alert_data['host']}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = settings.gmail_user
    msg["To"]      = ", ".join(settings.recipient_list)
    msg.attach(MIMEText(html_body, "html"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.ehlo()
        server.login(settings.gmail_user, settings.gmail_app_password)
        server.sendmail(settings.gmail_user, settings.recipient_list, msg.as_string())

    logger.info(
        f"Email sent — alert_id={alert_data['alert_id']} "
        f"recipients={settings.recipient_list}"
    )
