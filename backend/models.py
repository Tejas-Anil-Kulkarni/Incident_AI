"""SQLAlchemy persistence records."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    service: Mapped[str] = mapped_column(String(300), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    signature: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
