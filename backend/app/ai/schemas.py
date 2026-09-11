"""Pydantic schemas for the HELIOS AI Intelligence Layer API."""
from __future__ import annotations
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def _stamp() -> str:
    return datetime.now(UTC).isoformat()


ACTION_TYPES = {
    "INVESTIGATE_EVENT",
    "VIEW_EVIDENCE",
    "OPEN_EVENT",
    "OPEN_CAMERA",
    "OPEN_TRACK",
    "OPEN_TIMELINE",
    "VIEW_RELATED_EVENTS",
    "OPEN_ZONE",
    "REVIEW_ACTIVITY",
    "OPEN_CAMERA_HEALTH",
    "OPEN_ALERT",
    "OPEN_FACE_DIRECTORY",
    "VIEW_FACE_RECOGNITION",
}


class Reference(BaseModel):
    event_id: str | None = None
    track_id: str | None = None
    camera_id: str | None = None
    zone_id: str | None = None
    evidence_id: str | None = None
    alert_id: str | None = None
    recognition_id: str | None = None
    person_id: str | None = None
    label: str | None = None

    def present_ids(self) -> list[str]:
        return [
            value for value in (self.event_id, self.track_id, self.camera_id, self.zone_id, self.evidence_id, self.alert_id, self.recognition_id, self.person_id)
            if value
        ]


class AiClaim(BaseModel):
    statement: str
    basis: str | None = None
    confidence: str = "medium"
    references: list[Reference] = Field(default_factory=list)


class AiAction(BaseModel):
    type: str
    label: str = ""
    event_id: str | None = None
    track_id: str | None = None
    camera_id: str | None = None
    zone_id: str | None = None
    evidence_id: str | None = None
    alert_id: str | None = None
    recognition_id: str | None = None
    person_id: str | None = None

    @field_validator("type")
    @classmethod
    def known_action(cls, value: str) -> str:
        value = value.upper()
        if value not in ACTION_TYPES:
            raise ValueError(f"unknown action type {value}")
        return value


class AIResponse(BaseModel):
    answer: str
    claims: list[AiClaim] = Field(default_factory=list)
    actions: list[AiAction] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    ai_enabled: bool = True
    ai_model: str | None = None
    grounded: bool = False
    generated_at: str = Field(default_factory=_stamp)
    error_code: str | None = None
    reasoning_details: Any = None


class ChatMessage(BaseModel):
    role: Literal["user", "model", "assistant"]
    content: str
    reasoning_details: Any = None


class AiAskInput(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)


class AiInvestigateInput(BaseModel):
    id: str | None = None
    target_id: str | None = None
    context_window_hours: int = Field(default=6, ge=1, le=72)
    focus: str | None = None


class EventInsight(BaseModel):
    event_id: str
    summary: str
    narration: str
    ai_used: bool = False
    ai_model: str | None = None
    claims: list[AiClaim] = Field(default_factory=list)
    actions: list[AiAction] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=_stamp)


class InvestigationContext(BaseModel):
    event: dict[str, Any] | None = None
    track: dict[str, Any] | None = None
    camera: dict[str, Any] | None = None
    zone: dict[str, Any] | None = None
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    related_events: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    target_id: str | None = None
    target_type: str | None = None
    evidence_item: dict[str, Any] | None = None
    image_url: str | None = None
    entity_timeline: list[dict[str, Any]] = Field(default_factory=list)
    face_intel: dict[str, Any] | None = None


class InvestigationResult(BaseModel):
    event_id: str
    explanation: str
    context: InvestigationContext = Field(default_factory=InvestigationContext)
    claims: list[AiClaim] = Field(default_factory=list)
    actions: list[AiAction] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    ai_used: bool = False
    ai_model: str | None = None
    generated_at: str = Field(default_factory=_stamp)
    error_code: str | None = None
    target_id: str | None = None
    target_type: str | None = None
    image_description: str | None = None
    entity_timeline: list[dict[str, Any]] = Field(default_factory=list)
    face_intel: dict[str, Any] | None = None


class DayBrief(BaseModel):
    date: str
    activity_summary: str
    significant_events: list[dict[str, Any]] = Field(default_factory=list)
    virtual_fence_events: list[dict[str, Any]] = Field(default_factory=list)
    camera_health: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summary: str
    activity_patterns: list[str] = Field(default_factory=list)
    ai_assessment: str
    references: list[Reference] = Field(default_factory=list)
    actions: list[AiAction] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    ai_used: bool = False
    ai_model: str | None = None
    generated_at: str = Field(default_factory=_stamp)


class AiStatus(BaseModel):
    enabled: bool
    available: bool
    model: str | None = None
    provider: str | None = None
    error: str | None = None