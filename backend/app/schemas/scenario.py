from pydantic import BaseModel, ConfigDict


class TrainingScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    subject: str
    grade: str
    topic: str
    teaching_goal: str
    description: str
