from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.session import Base

if TYPE_CHECKING:
    from .session import TeachingSession
    from .evaluation_report import EvaluationNarrative


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        CheckConstraint("knowledge_accuracy >= 0 AND knowledge_accuracy <= 100", name="ck_eval_knowledge_accuracy"),
        CheckConstraint("questioning >= 0 AND questioning <= 100", name="ck_eval_questioning"),
        CheckConstraint("feedback >= 0 AND feedback <= 100", name="ck_eval_feedback"),
        CheckConstraint("misconception_diagnosis >= 0 AND misconception_diagnosis <= 100", name="ck_eval_misconception_diagnosis"),
        CheckConstraint("scaffolding >= 0 AND scaffolding <= 100", name="ck_eval_scaffolding"),
        CheckConstraint("overall_score >= 0 AND overall_score <= 100", name="ck_eval_overall_score"),
    )

    session_id: Mapped[int] = mapped_column(
        ForeignKey("teaching_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    questioning: Mapped[float] = mapped_column(Float, nullable=False)
    feedback: Mapped[float] = mapped_column(Float, nullable=False)
    misconception_diagnosis: Mapped[float] = mapped_column(Float, nullable=False)
    scaffolding: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    session: Mapped[TeachingSession] = relationship(back_populates="evaluation")
    narrative: Mapped[EvaluationNarrative | None] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan", uselist=False
    )
