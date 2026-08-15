from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DialogueRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    speaker: str
    content: str
    sequence: int
    timestamp: datetime
