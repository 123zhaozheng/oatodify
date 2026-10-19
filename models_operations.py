"""Persistent records for Celery work shown by the operations console.

All datetimes in this table are stored as naive UTC values. The rest of this
project uses ``timestamp without time zone`` columns with UTC deployment
semantics, so the same convention keeps PostgreSQL and SQLite behavior aligned.
"""

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func

from models import Base


class JobRun(Base):
    """One durable lifecycle record per tracked Celery task ID."""

    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(100), nullable=False, unique=True, index=True)
    task_name = Column(String(255), nullable=False, index=True)
    kind = Column(String(40), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="queued", index=True)
    started_at = Column(DateTime(timezone=False), index=True)
    finished_at = Column(DateTime(timezone=False), index=True)
    counts = Column(JSON, nullable=False, default=dict)
    error = Column(Text)
    message = Column(Text)
    attempt_count = Column(Integer, nullable=False, default=0)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<JobRun(id={self.id}, task_id={self.task_id}, kind={self.kind}, status={self.status})>"
