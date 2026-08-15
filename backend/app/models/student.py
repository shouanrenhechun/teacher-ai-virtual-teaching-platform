from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.session import Base

if TYPE_CHECKING:
    from .knowledge import KnowledgeState
    from .misconception import Misconception
    from .session import TeachingSession


class VirtualStudent(Base):
    __tablename__ = "virtual_students"
    __table_args__ = (
        CheckConstraint("base_level >= 0 AND base_level <= 1", name="ck_student_base_level"),
        CheckConstraint("initiative >= 0 AND initiative <= 1", name="ck_student_initiative"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_student_confidence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    grade: Mapped[str] = mapped_column(String(100), nullable=False)
    base_level: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    personality_description: Mapped[str] = mapped_column(Text, nullable=False)
    initiative: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    knowledge_states: Mapped[list[KnowledgeState]] = relationship(
        back_populates="virtual_student",
        cascade="all, delete-orphan",
    )
    misconceptions: Mapped[list[Misconception]] = relationship(
        back_populates="virtual_student",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list[TeachingSession]] = relationship(back_populates="virtual_student")
