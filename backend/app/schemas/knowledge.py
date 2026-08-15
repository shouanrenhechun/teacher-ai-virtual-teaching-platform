from pydantic import BaseModel, ConfigDict, Field


class KnowledgeStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_point: str
    mastery: float = Field(ge=0, le=1)
