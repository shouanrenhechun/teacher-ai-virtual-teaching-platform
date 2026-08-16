from __future__ import annotations

from pydantic import BaseModel, Field


class CognitiveStateRead(BaseModel):
    understanding: float = Field(ge=0, le=1)
    confusion: float = Field(ge=0, le=1)
    engagement: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    surface_recall: float = Field(ge=0, le=1)


class MisconceptionStateRead(BaseModel):
    name: str
    concept: str
    description: str
    semantic_type: str
    strength: float = Field(ge=0, le=1)
    status: str
    triggered: bool
    correction_started: bool
    corrected: bool
    stable_correct_evidence_count: int = Field(ge=0)
    transfer_evidence: int = Field(ge=0)


class StudentResponseEvidenceRead(BaseModel):
    states_correct_conclusion: bool
    conclusion_level: str
    explains_reason_correctly: bool
    shows_residual_misconception: bool
    shows_uncertainty: bool
    linguistic_hedging: bool
    conceptual_uncertainty: bool
    knowledge_precision: str
    evidence_insufficient: bool
    parrots_teacher: bool
    transfer_success: bool
    evidence_level: int = Field(ge=0)


class CorrectionOpportunityRead(BaseModel):
    correction_opportunity: bool
    opportunity_strength: float = Field(ge=0, le=1)


class CognitiveTraceRoundRead(BaseModel):
    round: int = Field(gt=0)
    teacher_text: str
    student_text: str
    action_type: str | None = None
    state_before: CognitiveStateRead
    state_after: CognitiveStateRead
    misconception_before: MisconceptionStateRead | None = None
    misconception_after: MisconceptionStateRead | None = None
    evidence: StudentResponseEvidenceRead | None = None
    correction_opportunity: CorrectionOpportunityRead
    prompt_mode: str | None = None


class CognitiveTraceRead(BaseModel):
    initial_state: CognitiveStateRead
    initial_misconception: MisconceptionStateRead | None = None
    current_state: CognitiveStateRead
    current_misconception: MisconceptionStateRead | None = None
    rounds: list[CognitiveTraceRoundRead]
