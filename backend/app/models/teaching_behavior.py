from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.session import Base

if TYPE_CHECKING:
    from .dialogue import DialogueRecord
    from .session import TeachingSession


class TeachingBehaviorRecord(Base):
    __tablename__ = "teaching_behavior_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("teaching_sessions.id", ondelete="CASCADE"), nullable=False
    )
    dialogue_record_id: Mapped[int] = mapped_column(
        ForeignKey("dialogue_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    concept: Mapped[str] = mapped_column(String(100), nullable=False)
    knowledge_accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    clarity: Mapped[float] = mapped_column(Float, nullable=False)
    checked_understanding: Mapped[bool] = mapped_column(Boolean, nullable=False)
    gave_answer_directly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    analysis_source: Mapped[str] = mapped_column(String(20), nullable=False, default="rules")
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    session: Mapped[TeachingSession] = relationship(back_populates="behavior_records")
    dialogue_record: Mapped[DialogueRecord] = relationship(back_populates="behavior_analysis")
