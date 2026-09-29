from datetime import datetime

from .common import UTCModel
from pydantic import BaseModel, ConfigDict, Field


class EvaluationRead(UTCModel):
    model_config = ConfigDict(from_attributes=True)

    rubric_version: int = 1
    evidence: dict = Field(default_factory=dict)
    session_id: int
    knowledge_accuracy: float | None = Field(default=None, ge=0, le=100)
    questioning: float | None = Field(default=None, ge=0, le=100)
    feedback: float | None = Field(default=None, ge=0, le=100)
    misconception_diagnosis: float | None = Field(default=None, ge=0, le=100)
    scaffolding: float | None = Field(default=None, ge=0, le=100)
    overall_score: float | None = Field(default=None, ge=0, le=100)
    summary: str


class EvaluationQualitativeAnalysis(BaseModel):
    """LLM output schema; it cannot set or alter the numeric scores."""

    model_config = ConfigDict(extra="forbid")

    strengths: list[str] = Field(min_length=1, max_length=8)
    problems: list[str] = Field(min_length=1, max_length=8)
    suggestions: list[str] = Field(min_length=1, max_length=8)
    evidence_rounds: list[int] = Field(default_factory=list, max_length=8)


class KeyTeachingSnippet(BaseModel):
    round: int = Field(ge=1)
    action_type: str
    teacher_text: str
    student_text: str
    evidence: str


class EvaluationReportRead(EvaluationRead):
    strengths: list[str]
    problems: list[str]
    suggestions: list[str]
    key_teaching_snippets: list[KeyTeachingSnippet]
    disclaimer: str
    generated_at: datetime
    analysis_source: str
    analysis_error: str | None = None
