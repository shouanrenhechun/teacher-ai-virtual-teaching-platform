from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from .common import UTCModel
from uuid import uuid4

from .dialogue import DialogueRecordRead
from .cognitive import CognitiveTraceRead
from .evaluation import EvaluationReportRead
from .scenario import TrainingScenarioRead
from .student import VirtualStudentRead
from .teaching_behavior import TeachingBehaviorRecordRead, TeachingBehaviorSummaryRead


class TeachingSessionRead(UTCModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int
    virtual_student_id: int
    started_at: datetime
    ended_at: datetime | None
    status: str


class SessionHistoryItemRead(UTCModel):
    id: int
    started_at: datetime
    ended_at: datetime | None
    status: str
    scenario_id: int
    topic: str
    virtual_student_name: str
    virtual_student_id: int
    rubric_version: int = 1
    overall_score: float | None = Field(default=None, ge=0, le=100)


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: int = Field(gt=0)
    virtual_student_id: int = Field(gt=0)


class SessionMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    teacher_text: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=64)
    expected_version: int | None = Field(default=None, ge=0)

    @field_validator('teacher_text')
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('教师话语不能为空')
        return value


class SessionStateRead(BaseModel):
    understanding: float = Field(ge=0, le=1)
    confusion: float = Field(ge=0, le=1)
    engagement: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class TeachingSessionDetailRead(UTCModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int = 0
    scenario_id: int
    virtual_student_id: int
    started_at: datetime
    ended_at: datetime | None
    status: str
    scenario: TrainingScenarioRead
    virtual_student: VirtualStudentRead
    dialogue_records: list[DialogueRecordRead]
    behavior_records: list[TeachingBehaviorRecordRead]
    behavior_summary: TeachingBehaviorSummaryRead
    state: SessionStateRead
    cognitive_trace: CognitiveTraceRead
    evaluation: EvaluationReportRead | None = None
