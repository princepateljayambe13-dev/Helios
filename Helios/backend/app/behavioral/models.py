"""Data models for HELIOS Behavioral Analytics."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class BehavioralAnomalyScoreBreakdown:
    """7-signal normalized deviation score breakdown (all 0.0 - 100.0)."""

    movement_deviation: float = 0.0          # 20%
    spatial_deviation: float = 0.0           # 20%
    temporal_deviation: float = 0.0          # 15%
    dwell_deviation: float = 0.0             # 15%
    activity_density_deviation: float = 0.0  # 15%
    cross_camera_pattern: float = 0.0        # 10%
    baseline_deviation: float = 0.0          # 5%
    composite_score: int = 0                 # 0 - 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "movement_deviation": round(self.movement_deviation, 1),
            "spatial_deviation": round(self.spatial_deviation, 1),
            "temporal_deviation": round(self.temporal_deviation, 1),
            "dwell_deviation": round(self.dwell_deviation, 1),
            "activity_density_deviation": round(self.activity_density_deviation, 1),
            "cross_camera_pattern": round(self.cross_camera_pattern, 1),
            "baseline_deviation": round(self.baseline_deviation, 1),
            "composite_score": int(self.composite_score),
            "weights": {
                "movement_deviation": 0.20,
                "spatial_deviation": 0.20,
                "temporal_deviation": 0.15,
                "dwell_deviation": 0.15,
                "activity_density_deviation": 0.15,
                "cross_camera_pattern": 0.10,
                "baseline_deviation": 0.05,
            },
        }


@dataclass
class BehavioralEvent:
    """Structured observable behavioral event record persisted to database."""

    behavior_id: str
    track_id: str
    camera_id: str
    zone_id: str | None
    timestamp: str
    behavior_type: str
    anomaly_score: int
    score_breakdown: BehavioralAnomalyScoreBreakdown
    movement_state: str = "STATIONARY"
    speed: float = 0.0
    direction: str = "STATIONARY"
    dwell_duration: float = 0.0
    activity_density_data: dict[str, Any] = field(default_factory=dict)
    baseline_comparison: dict[str, Any] = field(default_factory=dict)
    anomaly_reasons: list[str] = field(default_factory=list)
    movement_data: dict[str, Any] = field(default_factory=dict)
    related_cameras: list[str] = field(default_factory=list)
    related_events: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.90
    status: str = "ACTIVE"
    event_id: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "behavior_id": self.behavior_id,
            "event_id": self.event_id,
            "track_id": self.track_id,
            "camera_id": self.camera_id,
            "zone_id": self.zone_id,
            "timestamp": self.timestamp,
            "behavior_type": self.behavior_type,
            "anomaly_score": self.anomaly_score,
            "score_breakdown": self.score_breakdown.to_dict(),
            "movement_deviation": round(self.score_breakdown.movement_deviation, 1),
            "spatial_deviation": round(self.score_breakdown.spatial_deviation, 1),
            "temporal_deviation": round(self.score_breakdown.temporal_deviation, 1),
            "dwell_deviation": round(self.score_breakdown.dwell_deviation, 1),
            "activity_density_deviation": round(self.score_breakdown.activity_density_deviation, 1),
            "cross_camera_pattern": round(self.score_breakdown.cross_camera_pattern, 1),
            "baseline_deviation": round(self.score_breakdown.baseline_deviation, 1),
            "movement_state": self.movement_state,
            "speed": round(self.speed, 2),
            "direction": self.direction,
            "dwell_duration": round(self.dwell_duration, 1),
            "activity_density_data": dict(self.activity_density_data),
            "baseline_comparison": dict(self.baseline_comparison),
            "anomaly_reasons": list(self.anomaly_reasons),
            "movement_data": dict(self.movement_data),
            "related_cameras": list(self.related_cameras),
            "related_events": list(self.related_events),
            "evidence_ids": list(self.evidence_ids),
            "confidence": round(self.confidence, 3),
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
