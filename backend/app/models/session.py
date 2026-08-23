from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.session import Base

if TYPE_CHECKING:
    from .dialogue import DialogueRecord
    from .evaluation import Evaluation
    from .scenario import TrainingScenario
    from .student import VirtualStudent
    from .teaching_behavior import TeachingBehaviorRecord
    from .session_snapshot import TeachingSessionSnapshot


class TeachingSession(Base):
    __tablename__ = "teaching_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("training_scenarios.id"), nullable=False)
    virtual_student_id: Mapped[int] = mapped_column(
        ForeignKey("virtual_students.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_started")

    scenario: Mapped[TrainingScenario] = relationship(back_populates="sessions")
    virtual_student: Mapped[VirtualStudent] = relationship(back_populates="sessions")
    dialogue_records: Mapped[list[DialogueRecord]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="DialogueRecord.sequence",
    )
    behavior_records: Mapped[list[TeachingBehaviorRecord]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TeachingBehaviorRecord.id",
    )
    evaluation: Mapped[Evaluation | None] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )
    snapshot: Mapped[TeachingSessionSnapshot | None] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )
