from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .dialogue import DialogueRecordRead
from .evaluation import EvaluationReportRead
from .scenario import TrainingScenarioRead
from .student import VirtualStudentRead
from .teaching_behavior import TeachingBehaviorRecordRead, TeachingBehaviorSummaryRead


class TeachingSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int
    virtual_student_id: int
    started_at: datetime
    ended_at: datetime | None
    status: str


class SessionHistoryItemRead(BaseModel):
    id: int
    started_at: datetime
    ended_at: datetime | None
    status: str
    scenario_id: int
    topic: str
    virtual_student_name: str
    overall_score: float | None = Field(default=None, ge=0, le=100)


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: int = Field(gt=0)
    virtual_student_id: int = Field(gt=0)


class SessionMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    teacher_text: str = Field(min_length=1, max_length=4000)


class SessionStateRead(BaseModel):
    understanding: float = Field(ge=0, le=1)
    confusion: float = Field(ge=0, le=1)
    engagement: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class TeachingSessionDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
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
    evaluation: EvaluationReportRead | None = None
