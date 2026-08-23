from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.session import Base

if TYPE_CHECKING:
    from .session import TeachingSession


class TeachingSessionSnapshot(Base):
    """Immutable inputs and persisted state used to keep session history stable."""

    __tablename__ = "teaching_session_snapshots"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("teaching_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    profile_json: Mapped[str] = mapped_column(Text, nullable=False)
    engine_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    cognitive_trace_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    session: Mapped[TeachingSession] = relationship(back_populates="snapshot")
