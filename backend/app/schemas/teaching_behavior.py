from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TeachingActionType(StrEnum):
    EXPLANATION = "explanation"
    QUESTION = "question"
    GUIDED_QUESTION = "guided_question"
    EXAMPLE = "example"
    FEEDBACK = "feedback"
    CORRECTION = "correction"
    UNDERSTANDING_CHECK = "understanding_check"
    DIRECT_ANSWER = "direct_answer"


class TeachingBehaviorAnalysis(BaseModel):
    """Validated, provider-neutral analysis of one teacher utterance."""

    model_config = ConfigDict(extra="forbid")

    action_type: TeachingActionType
    concept: str = Field(min_length=1, max_length=100)
    knowledge_accuracy: float = Field(ge=0, le=1)
    clarity: float = Field(ge=0, le=1)
    checked_understanding: bool
    gave_answer_directly: bool
    analysis_source: Literal["rules", "rules+llm", "fallback"] = "rules"
    analysis_error: str | None = Field(default=None, max_length=500)


class TeachingBehaviorRecordRead(TeachingBehaviorAnalysis):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    dialogue_record_id: int
    created_at: datetime


class TeachingBehaviorSummaryRead(BaseModel):
    explanation_count: int = Field(ge=0)
    question_count: int = Field(ge=0)
    guided_question_count: int = Field(ge=0)
    example_count: int = Field(ge=0)
    feedback_count: int = Field(ge=0)
    correction_count: int = Field(ge=0)
    understanding_check_count: int = Field(ge=0)
    direct_answer_count: int = Field(ge=0)
