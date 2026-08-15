from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.session import Base


class KnowledgeState(Base):
    __tablename__ = "knowledge_states"
    __table_args__ = (
        UniqueConstraint("virtual_student_id", "knowledge_point", name="uq_student_knowledge_point"),
        CheckConstraint("mastery >= 0 AND mastery <= 1", name="ck_knowledge_mastery"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    virtual_student_id: Mapped[int] = mapped_column(
        ForeignKey("virtual_students.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_point: Mapped[str] = mapped_column(String(200), nullable=False)
    mastery: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    virtual_student: Mapped[VirtualStudent] = relationship(back_populates="knowledge_states")
