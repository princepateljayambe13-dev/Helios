"""Data models for the HELIOS Intelligence & Insights layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Observation:
    """Lightweight structured observation record for a completed or active track."""
    observation_id: str
    track_id: str
    camera_id: str
    zone_id: str | None
    object_type: str
    first_seen: str
    last_seen: str
    entry_time: str | None = None
    exit_time: str | None = None
    dwell_seconds: float = 0.0
    movement_state: str = "STATIONARY"
    direction: str = "STATIONARY"
    speed: float = 0.0
    distance_travelled: float = 0.0
    zone_transitions: list[str] = field(default_factory=list)
    related_tracks: list[str] = field(default_factory=list)
    related_cameras: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.90
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "track_id": self.track_id,
            "camera_id": self.camera_id,
            "zone_id": self.zone_id,
            "object_type": self.object_type,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "dwell_seconds": round(self.dwell_seconds, 1),
            "movement_state": self.movement_state,
            "direction": self.direction,
            "speed": round(self.speed, 2),
            "distance_travelled": round(self.distance_travelled, 2),
            "zone_transitions": list(self.zone_transitions),
            "related_tracks": list(self.related_tracks),
            "related_cameras": list(self.related_cameras),
            "event_ids": list(self.event_ids),
            "evidence_ids": list(self.evidence_ids),
            "confidence": round(self.confidence, 3),
            "created_at": self.created_at,
        }


@dataclass
class Insight:
    """Actionable intelligence record combining multiple signals."""
    insight_id: str
    timestamp: str
    type: str  # ACTIVITY_CHANGE, DENSITY_CHANGE, BEHAVIOR_CHANGE, UNUSUAL_DWELL, etc.
    summary: str
    score: int
    confidence: float
    priority: str  # INFORMATIONAL, NOTABLE, IMPORTANT, CRITICAL
    camera_ids: list[str] = field(default_factory=list)
    zone_ids: list[str] = field(default_factory=list)
    track_ids: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)
    baseline_comparison: dict[str, Any] = field(default_factory=dict)
    reasoning_factors: list[str] = field(default_factory=list)
    status: str = "ACTIVE"  # DETECTED, ANALYZING, ACTIVE, ACKNOWLEDGED, RESOLVED
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "summary": self.summary,
            "score": self.score,
            "confidence": round(self.confidence, 3),
            "priority": self.priority,
            "camera_ids": list(self.camera_ids),
            "zone_ids": list(self.zone_ids),
            "track_ids": list(self.track_ids),
            "event_ids": list(self.event_ids),
            "evidence_ids": list(self.evidence_ids),
            "signals": dict(self.signals),
            "baseline_comparison": dict(self.baseline_comparison),
            "reasoning_factors": list(self.reasoning_factors),
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class WhatChangedItem:
    """Structured delta comparison between baseline and current state."""
    zone_id: str
    zone_name: str
    camera_id: str
    metric: str
    normal_val: Any
    current_val: Any
    significance: str  # LOW, MEDIUM, HIGH, CRITICAL
    change_pct: float
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "camera_id": self.camera_id,
            "metric": self.metric,
            "normal": self.normal_val,
            "current": self.current_val,
            "significance": self.significance,
            "change_pct": round(self.change_pct, 1),
            "description": self.description,
        }
