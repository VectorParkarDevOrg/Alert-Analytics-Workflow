from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # ── Zabbix ────────────────────────────────────────────────────────────────
    zabbix_url: str
    zabbix_token: str

    # Zabbix item display names — must match your template exactly
    cpu_top_item_name: str    = "Top 5 Processes by CPU Utilization"
    memory_top_item_name: str = "Top 5 Processes by Memory Utilization"

    # How many days of Zabbix history to analyse
    history_days: int  = 30
    # Max historical snapshots to fetch per alert
    history_limit: int = 500
    # How many top processes to include in the report
    top_process_count: int = 5

    # ── Email / SMTP ──────────────────────────────────────────────────────────
    gmail_user: str
    gmail_app_password: str
    email_recipients: str   # comma-separated
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587

    # ── App ───────────────────────────────────────────────────────────────────
    db_path: str  = "./alert_analytics.db"
    app_port: int = 6666
    # Seconds to wait before re-checking Zabbix (default 180 = 3 minutes)
    alert_wait_seconds: int = 180

    @property
    def recipient_list(self) -> List[str]:
        return [e.strip() for e in self.email_recipients.split(",") if e.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
