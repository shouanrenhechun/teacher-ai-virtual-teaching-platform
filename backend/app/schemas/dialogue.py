from datetime import datetime

from pydantic import BaseModel, ConfigDict
from .common import UTCModel


class DialogueRecordRead(UTCModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    speaker: str
    content: str
    sequence: int
    timestamp: datetime
    request_id: str | None = None
    response_metadata: str | None = None
