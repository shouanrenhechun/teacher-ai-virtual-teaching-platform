from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.session import Base

if TYPE_CHECKING:
    from .teaching_behavior import TeachingBehaviorRecord


class DialogueRecord(Base):
    __tablename__ = "dialogue_records"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_dialogue_session_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("teaching_sessions.id", ondelete="CASCADE"), nullable=False
    )
    speaker: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    session: Mapped[TeachingSession] = relationship(back_populates="dialogue_records")
    behavior_analysis: Mapped[TeachingBehaviorRecord | None] = relationship(
        back_populates="dialogue_record", uselist=False, cascade="all, delete-orphan"
    )
