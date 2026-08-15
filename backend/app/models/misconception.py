from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.session import Base


class Misconception(Base):
    __tablename__ = "misconceptions"
    __table_args__ = (
        CheckConstraint("strength >= 0 AND strength <= 1", name="ck_misconception_strength"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    virtual_student_id: Mapped[int] = mapped_column(
        ForeignKey("virtual_students.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    concept: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    correction_condition: Mapped[str] = mapped_column(Text, nullable=False)

    virtual_student: Mapped[VirtualStudent] = relationship(back_populates="misconceptions")
