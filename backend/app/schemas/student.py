from pydantic import BaseModel, ConfigDict, Field

from .knowledge import KnowledgeStateRead


class VirtualStudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    grade: str
    base_level: float = Field(ge=0, le=1)
    personality_description: str
    initiative: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    knowledge_states: list[KnowledgeStateRead]
