from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime

from database import Base


class Alert(Base):
    """Stores every incoming alert and tracks its workflow status."""
    __tablename__ = "alerts"

    id           = Column(Integer, primary_key=True)
    alert_id     = Column(String, unique=True, index=True, nullable=False)
    host         = Column(String, nullable=False)
    alert_type   = Column(String, nullable=False)   # cpu | memory
    trigger_name = Column(String)
    severity     = Column(String)
    alert_time   = Column(DateTime)
    # pending → deleted on completion (resolved/email_sent) | error stays
    status       = Column(String, default="pending")
    created_at   = Column(DateTime, default=datetime.utcnow)


class ProcessSnapshot(Base):
    """
    Stores top-N process data captured at analysis time.
    Kept permanently — builds the local history used for recurring process detection.
    """
    __tablename__ = "process_snapshots"

    id            = Column(Integer, primary_key=True)
    alert_id      = Column(String, index=True)
    host          = Column(String, nullable=False)
    alert_type    = Column(String, nullable=False)  # cpu | memory
    process_name  = Column(String, nullable=False)
    process_value = Column(Float)
    snapshot_time = Column(DateTime, default=datetime.utcnow)
