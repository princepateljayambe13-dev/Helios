"""Trajectory tracking and history management for HELIOS tracked objects."""
from __future__ import annotations

import math
from typing import Any


class Trajectory:
    """Maintains an ordered spatial-temporal history of track positions."""

    def __init__(self, points: list[dict[str, Any]] | None = None) -> None:
        self.points: list[dict[str, Any]] = points or []

    def add_point(
        self,
        timestamp: str,
        bounding_box: list[float],
        confidence: float,
        speed: float = 0.0,
        direction: str = "STATIONARY",
        movement_state: str = "STATIONARY",
        distance_travelled: float = 0.0,
        movement_change: str | None = None,
    ) -> dict[str, Any]:
        """Record a new observation position in the trajectory with movement metrics."""
        center = [
            round(bounding_box[0] + bounding_box[2] / 2.0, 4),
            round(bounding_box[1] + bounding_box[3] / 2.0, 4),
        ]
        point = {
            "timestamp": timestamp,
            "bounding_box": [round(val, 4) for val in bounding_box],
            "confidence": round(float(confidence), 4),
            "center": center,
            "speed": round(float(speed), 2),
            "direction": direction,
            "movement_state": movement_state,
            "distance_travelled": round(float(distance_travelled), 2),
            "movement_change": movement_change,
        }
        self.points.append(point)
        return point

    def to_list(self) -> list[dict[str, Any]]:
        return list(self.points)

    def last_point(self) -> dict[str, Any] | None:
        return self.points[-1] if self.points else None

    def __len__(self) -> int:
        return len(self.points)

    def current_speed(self) -> float:
        pt = self.last_point()
        return pt.get("speed", 0.0) if pt else 0.0

    def current_direction(self) -> str:
        pt = self.last_point()
        return pt.get("direction", "STATIONARY") if pt else "STATIONARY"

    def current_movement_state(self) -> str:
        pt = self.last_point()
        return pt.get("movement_state", "STATIONARY") if pt else "STATIONARY"

    def distance_traveled(self) -> float:
        """Calculate total Euclidean distance traversed across center coordinates."""
        if len(self.points) < 2:
            return 0.0
        last = self.points[-1]
        if last.get("distance_travelled", 0.0) > 0.0:
            return float(last["distance_travelled"])
        total = 0.0
        for i in range(1, len(self.points)):
            c1 = self.points[i - 1]["center"]
            c2 = self.points[i]["center"]
            total += math.hypot(c2[0] - c1[0], c2[1] - c1[1])
        return round(total, 4)
