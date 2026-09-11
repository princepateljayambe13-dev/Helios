from pydantic import BaseModel, Field
from typing import Any

class CameraInput(BaseModel):
    camera_id: str
    name: str
    source_type: str = "PLACEHOLDER"
    stream_reference: str = Field(default="", exclude=True)
    location: str = ""
    enabled: bool = True

class ObservationInput(BaseModel):
    camera_id: str
    observation_type: str = "VISION"
    object_type: str
    confidence: float = Field(ge=0, le=1)
    bounding_box: list[float] = Field(min_length=4, max_length=4)
    timestamp: str | None = None
    zone_id: str | None = None
    model_name: str | None = "external-model"
    model_version: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

class AlertAction(BaseModel):
    operator: str = "operator"

class AlertsBatchAction(BaseModel):
    operator: str = "operator"
    alert_ids: list[str] | None = None

class EvidenceInput(BaseModel):
    event_id: str
    type: str
    storage_reference: str
    timestamp: str | None = None
    integrity_hash: str | None = None

class AudioObservationInput(BaseModel):
    source_id: str
    event_type: str
    confidence: float = Field(ge=0, le=1)
    timestamp: str | None = None
    evidence_reference: str | None = None

class ZoneInput(BaseModel):
    zone_id: str | None = None
    camera_id: str
    name: str
    zone_type: str = "RESTRICTED"
    geometry: list[list[float]] = Field(min_length=3)
    enabled: bool = True
    object_types: list[str] = Field(default_factory=lambda: ["HUMAN", "VEHICLE"])
    capacity: int | None = 10
    dwell_threshold_seconds: float | None = 20.0
    loitering_threshold_seconds: float | None = 50.0

class ZoneUpdateInput(BaseModel):
    name: str | None = None
    zone_type: str | None = None
    geometry: list[list[float]] | None = None
    enabled: bool | None = None
    object_types: list[str] | None = None
    capacity: int | None = None
    dwell_threshold_seconds: float | None = None
    loitering_threshold_seconds: float | None = None

class ZoneThresholdsInput(BaseModel):
    dwell_threshold_seconds: float = Field(ge=1.0, default=20.0)
    loitering_threshold_seconds: float = Field(ge=2.0, default=50.0)

