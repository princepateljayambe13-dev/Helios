from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class RegisterPersonInput(BaseModel):
    name: str = Field(min_length=1)
    person_id: str | None = None
    role: str = ""
    notes: str = ""
    image_base64: str | None = None  # Base64 encoded JPEG/PNG image if not uploading via multipart


class AssociateFaceInput(BaseModel):
    person_id: str | None = None  # Existing person ID to associate with
    name: str | None = None       # If creating a new person on the spot
    role: str = ""
    notes: str = ""


class RegisteredPersonItem(BaseModel):
    person_id: str
    name: str
    role: str = ""
    notes: str = ""
    face_image_path: str = ""
    created_at: str
    updated_at: str


class FaceRecognitionItem(BaseModel):
    recognition_id: str
    track_id: str | None = None
    camera_id: str
    person_id: str | None = None
    person_name: str
    status: str  # RECOGNIZED | UNCLASSIFIED
    similarity: float = 0.0
    confidence: float = 0.0
    bounding_box: list[float] | None = None
    snapshot_path: str = ""
    event_id: str | None = None
    first_seen: str
    last_seen: str
    detection_count: int = 1
    created_at: str
    updated_at: str


class FaceSummaryResponse(BaseModel):
    total_recognitions: int = 0
    recognized_count: int = 0
    unclassified_count: int = 0
    registered_persons_count: int = 0
