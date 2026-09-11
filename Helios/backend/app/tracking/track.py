"""Persistent multi-object track representation for HELIOS."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.tracking.trajectory import Trajectory


@dataclass
class Track:
    """Represents an actively tracked object identified across multiple frames.

    Attributes:
        track_id: Persistent track identifier.
        camera_id: Camera stream where the object was observed.
        object_type: HELIOS normalized object type (e.g., 'HUMAN', 'VEHICLE').
        bbox: Normalized bounding box in [x, y, w, h] format.
        confidence: Current detection / track confidence (0.0 to 1.0).
        first_seen: ISO 8601 timestamp when the track was initiated.
        last_seen: ISO 8601 timestamp of the most recent observation.
        state: Tracking state ('NEW', 'TRACKED', 'LOST', 'REMOVED').
        trajectory: Spatial-temporal trajectory history.
        detection_count: Number of detections associated with this track.
        max_confidence: Maximum confidence observed over the track lifecycle.
        source_class: Upstream model class label (e.g. 'person', 'car').
        source_track_id: Upstream ByteTrack track reference.
    """

    track_id: str | int
    camera_id: str
    object_type: str
    bbox: list[float]
    confidence: float
    first_seen: str
    last_seen: str
    state: str = "TRACKED"
    trajectory: Trajectory = field(default_factory=Trajectory)
    detection_count: int = 1
    max_confidence: float = 0.0
    source_class: str = ""
    source_track_id: str | None = None
    speed: float = 0.0
    speed_unit: str = "px/s"
    speed_kmh: float | None = None
    direction: str = "STATIONARY"
    heading_deg: float = 0.0
    movement_state: str = "STATIONARY"
    distance_travelled: float = 0.0
    movement_change: str | None = None
    reliability_score: float = 1.0
    recovery_count: int = 0
    reid_embeddings: list[list[float]] = field(default_factory=list)
    reliability_signals: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.max_confidence:
            self.max_confidence = self.confidence
        if isinstance(self.trajectory, list):
            self.trajectory = Trajectory(self.trajectory)
        if len(self.trajectory) == 0 and self.bbox:
            self.trajectory.add_point(
                self.first_seen,
                self.bbox,
                self.confidence,
                speed=self.speed,
                direction=self.direction,
                movement_state=self.movement_state,
                distance_travelled=self.distance_travelled,
                movement_change=self.movement_change,
            )

    def add_reid_embedding(self, embedding: list[float] | Sequence[float], max_history: int = 10) -> None:
        """Add an OSNet Re-ID appearance embedding to the track's temporal gallery."""
        if embedding is not None and len(embedding) > 0:
            vec = [round(float(v), 6) for v in embedding]
            self.reid_embeddings.append(vec)
            if len(self.reid_embeddings) > max_history:
                self.reid_embeddings.pop(0)

    def get_representative_embedding(self) -> list[float] | None:
        """Return the most recent or mean OSNet embedding from the gallery."""
        if not self.reid_embeddings:
            return None
        return self.reid_embeddings[-1]

    def update(
        self,
        bbox: list[float],
        confidence: float,
        timestamp: str,
        state: str = "TRACKED",
        speed: float | None = None,
        speed_unit: str = "px/s",
        speed_kmh: float | None = None,
        direction: str | None = None,
        heading_deg: float | None = None,
        movement_state: str | None = None,
        distance_travelled: float | None = None,
        movement_change: str | None = None,
        reliability_score: float | None = None,
        reliability_signals: dict[str, float] | None = None,
        recovery_count: int | None = None,
        reid_embedding: list[float] | None = None,
    ) -> None:
        """Update track with a newly matched detection, Re-ID embedding, and movement attributes."""
        self.bbox = [round(v, 4) for v in bbox]
        self.confidence = round(float(confidence), 4)
        self.last_seen = timestamp
        self.state = state
        self.detection_count += 1
        self.max_confidence = max(self.max_confidence, self.confidence)
        if speed is not None:
            self.speed = round(float(speed), 2)
        if speed_unit:
            self.speed_unit = speed_unit
        if speed_kmh is not None:
            self.speed_kmh = round(float(speed_kmh), 2)
        if direction is not None:
            self.direction = direction
        if heading_deg is not None:
            self.heading_deg = round(float(heading_deg), 1)
        if movement_state is not None:
            self.movement_state = movement_state
        if distance_travelled is not None:
            self.distance_travelled = round(float(distance_travelled), 2)
        if movement_change is not None:
            self.movement_change = movement_change
        if reliability_score is not None:
            self.reliability_score = round(float(reliability_score), 3)
        if reliability_signals:
            self.reliability_signals = dict(reliability_signals)
        if recovery_count is not None:
            self.recovery_count = recovery_count
        if reid_embedding:
            self.add_reid_embedding(reid_embedding)

        self.trajectory.add_point(
            timestamp,
            self.bbox,
            self.confidence,
            speed=self.speed,
            direction=self.direction,
            movement_state=self.movement_state,
            distance_travelled=self.distance_travelled,
            movement_change=self.movement_change,
        )

    def mark_lost(self, timestamp: str | None = None) -> None:
        """Mark track as temporarily lost (occluded / missing detection)."""
        self.state = "LOST"
        if timestamp:
            self.last_seen = timestamp

    def mark_removed(self, timestamp: str | None = None) -> None:
        """Mark track as concluded / terminated."""
        self.state = "REMOVED"
        if timestamp:
            self.last_seen = timestamp

    def to_dict(self) -> dict[str, Any]:
        """Convert track instance into a serializable dictionary."""
        return {
            "track_id": str(self.track_id),
            "camera_id": self.camera_id,
            "object_type": self.object_type,
            "bbox": list(self.bbox),
            "confidence": self.confidence,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "state": self.state,
            "detection_count": self.detection_count,
            "max_confidence": self.max_confidence,
            "source_class": self.source_class,
            "source_track_id": self.source_track_id,
            "speed": self.speed,
            "speed_unit": self.speed_unit,
            "speed_kmh": self.speed_kmh,
            "direction": self.direction,
            "heading_deg": self.heading_deg,
            "movement_state": self.movement_state,
            "distance_travelled": self.distance_travelled,
            "movement_change": self.movement_change,
            "reliability_score": self.reliability_score,
            "recovery_count": self.recovery_count,
            "reliability_signals": dict(self.reliability_signals),
            "reid_embedding": self.get_representative_embedding(),
            "trajectory": self.trajectory.to_list(),
        }
