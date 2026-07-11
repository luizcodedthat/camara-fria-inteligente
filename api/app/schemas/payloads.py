from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


class Esp32Payload(BaseModel):
    device_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    temperature_internal: float
    door_state: str = Field(pattern="^(open|closed)$")


class Thresholds(BaseModel):
    temp_min: float = 19.0
    temp_max: float = 25.0


class AnomalyResult(BaseModel):
    label: str
    score: float


class ConsolidatedResponse(BaseModel):
    current: dict
    anomaly: AnomalyResult
    thresholds: Thresholds