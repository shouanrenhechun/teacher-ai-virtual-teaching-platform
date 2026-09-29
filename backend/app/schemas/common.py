from datetime import UTC, datetime
from pydantic import BaseModel, field_serializer


class UTCModel(BaseModel):
    @field_serializer('*', check_fields=False)
    def serialize_datetime(self, value):
        if isinstance(value, datetime):
            return (value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)).isoformat()
        return value
