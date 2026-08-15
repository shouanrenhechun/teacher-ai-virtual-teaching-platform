from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMRespondRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    teacher_text: str = Field(min_length=1, max_length=4000)
    student_name: str = Field(default="学生 A", max_length=100)
    scenario_topic: str = Field(default="一次函数 k 与 b 的意义", max_length=200)


class LLMRespondResponse(BaseModel):
    provider: Literal["mock", "real"]
    student_text: str
