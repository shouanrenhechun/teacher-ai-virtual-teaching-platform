from pydantic import BaseModel, ConfigDict, Field


class MisconceptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    concept: str
    description: str
    strength: float = Field(ge=0, le=1)
    correction_condition: str
