from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.session import Base

if TYPE_CHECKING:
    from .evaluation import Evaluation


class EvaluationNarrative(Base):
    """Structured qualitative part of an evaluation, stored as JSON text."""

    __tablename__ = "evaluation_narratives"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.session_id", ondelete="CASCADE"), primary_key=True
    )
    strengths_json: Mapped[str] = mapped_column(Text, nullable=False)
    problems_json: Mapped[str] = mapped_column(Text, nullable=False)
    suggestions_json: Mapped[str] = mapped_column(Text, nullable=False)
    snippets_json: Mapped[str] = mapped_column(Text, nullable=False)
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    analysis_source: Mapped[str] = mapped_column(String(20), nullable=False)
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    evaluation: Mapped[Evaluation] = relationship(back_populates="narrative")
