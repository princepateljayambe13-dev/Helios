"""Incident data model for Intelligent Incident Correlation Engine."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Incident:
    incident_id: str
    title: str
    incident_type: str
    severity: str  # CRITICAL, HIGH, ELEVATED, MEDIUM, LOW
    status: str  # DETECTED, CONFIRMED, ACTIVE, ACKNOWLEDGED, RESOLVED
    confidence: float
    start_time: str
    last_seen_at: str
    created_at: str
    updated_at: str
    end_time: str | None = None
    duration_seconds: float = 0.0
    primary_camera_id: str | None = None
    primary_zone_id: str | None = None
    primary_track_id: str | None = None
    object_type: str = "HUMAN"
    summary: str = ""
    correlation_reasons: list[str] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)
    event_count: int = 1
    acknowledged_at: str | None = None
    acknowledged_by: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None

    # Transient / enriched fields for API payloads
    events: list[dict[str, Any]] = field(default_factory=list)
    tracks: list[dict[str, Any]] = field(default_factory=list)
    cameras: list[str] = field(default_factory=list)
    zones: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "incident_type": self.incident_type,
            "severity": self.severity,
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "last_seen_at": self.last_seen_at,
            "duration_seconds": round(self.duration_seconds, 1),
            "primary_camera_id": self.primary_camera_id,
            "primary_zone_id": self.primary_zone_id,
            "primary_track_id": self.primary_track_id,
            "object_type": self.object_type,
            "summary": self.summary,
            "correlation_reasons": self.correlation_reasons,
            "score_breakdown": self.score_breakdown,
            "event_count": self.event_count,
            "acknowledged_at": self.acknowledged_at,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": self.events,
            "tracks": self.tracks,
            "cameras": self.cameras,
            "zones": self.zones,
            "evidence": self.evidence,
            "timeline": self.timeline,
        }

    @classmethod
    def from_row(cls, row: Any) -> Incident:
        reasons = []
        breakdown = {}
        if row["correlation_reasons"]:
            try:
                reasons = json.loads(row["correlation_reasons"])
            except Exception:
                reasons = [str(row["correlation_reasons"])]
        if row["score_breakdown"]:
            try:
                breakdown = json.loads(row["score_breakdown"])
            except Exception:
                breakdown = {}

        return cls(
            incident_id=row["incident_id"],
            title=row["title"],
            incident_type=row["incident_type"],
            severity=row["severity"],
            status=row["status"],
            confidence=float(row["confidence"]),
            start_time=row["start_time"],
            end_time=row["end_time"],
            last_seen_at=row["last_seen_at"],
            duration_seconds=float(row["duration_seconds"] or 0.0),
            primary_camera_id=row["primary_camera_id"],
            primary_zone_id=row["primary_zone_id"],
            primary_track_id=row["primary_track_id"],
            object_type=row["object_type"] or "HUMAN",
            summary=row["summary"] or "",
            correlation_reasons=reasons,
            score_breakdown=breakdown,
            event_count=int(row["event_count"] or 1),
            acknowledged_at=row["acknowledged_at"],
            acknowledged_by=row["acknowledged_by"],
            resolved_at=row["resolved_at"],
            resolved_by=row["resolved_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
