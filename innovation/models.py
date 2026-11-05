"""SQLite cache records for Hindsight Reflect answers."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class ReflectInsightCache(Base):
    __tablename__ = "reflect_insight_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    raw_text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30))
    success: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
