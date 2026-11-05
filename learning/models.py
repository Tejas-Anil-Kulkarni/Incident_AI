"""Database records for engineer feedback and simulated action approvals."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class FeedbackRecord(Base):
    __tablename__ = "incident_feedback"

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    verified_cause: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(20), index=True)
    steps_json: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    memory_retained: Mapped[bool] = mapped_column(Boolean, default=False)


class ActionApproval(Base):
    __tablename__ = "action_approvals"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), primary_key=True)
    action_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    action: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str] = mapped_column(String(300))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActionSimulation(Base):
    __tablename__ = "action_simulations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    action_id: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(Text)
    simulated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="simulated")
