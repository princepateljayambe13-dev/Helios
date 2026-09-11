"""Spatial zone domain model for HELIOS perimeter defense and fencing."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Sequence

from app.spatial.geometry import point_in_polygon


@dataclass
class Zone:
    """Represents a configured spatial polygon region for a camera feed."""

    zone_id: str
    camera_id: str
    name: str
    zone_type: str = "RESTRICTED"
    geometry: list[list[float]] = field(default_factory=list)
    enabled: bool = True
    object_types: list[str] = field(default_factory=lambda: ["HUMAN", "VEHICLE"])
    capacity: int = 10
    dwell_threshold_seconds: float = 20.0
    loitering_threshold_seconds: float = 50.0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def contains_point(self, point: tuple[float, float]) -> bool:
        """Evaluate whether a camera-space (x, y) point is inside this polygon."""
        if not self.geometry or len(self.geometry) < 3:
            return False
        return point_in_polygon(point, self.geometry)

    def applies_to(self, object_type: str) -> bool:
        """Check whether this zone's object filters apply to the given object type."""
        if not self.object_types:
            return True
        normalized_types = {t.strip().upper() for t in self.object_types if t}
        if not normalized_types or "ALL" in normalized_types:
            return True
        return object_type.strip().upper() in normalized_types

    def is_restricted(self) -> bool:
        """Check if this zone triggers security breach/intrusion alarms."""
        return self.zone_type.upper() in {"RESTRICTED", "VIRTUAL_FENCE"}

    def to_dict(self) -> dict[str, Any]:
        """Convert zone instance to serializable dictionary."""
        return {
            "zone_id": self.zone_id,
            "camera_id": self.camera_id,
            "name": self.name,
            "zone_type": self.zone_type,
            "geometry": self.geometry,
            "enabled": self.enabled,
            "object_types": self.object_types,
            "capacity": self.capacity,
            "dwell_threshold_seconds": self.dwell_threshold_seconds,
            "loitering_threshold_seconds": self.loitering_threshold_seconds,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Zone:
        """Construct Zone from dictionary."""
        geometry = data.get("geometry", [])
        if isinstance(geometry, str):
            import json
            geometry = json.loads(geometry)
        object_types = data.get("object_types", ["HUMAN", "VEHICLE"])
        if isinstance(object_types, str):
            import json
            try:
                object_types = json.loads(object_types)
            except Exception:
                object_types = [t.strip() for t in object_types.split(",") if t.strip()]
        if not isinstance(object_types, list):
            object_types = ["HUMAN", "VEHICLE"]
        return cls(
            zone_id=str(data.get("zone_id", "")),
            camera_id=str(data.get("camera_id", "")),
            name=str(data.get("name", "")),
            zone_type=str(data.get("zone_type", "RESTRICTED")),
            geometry=geometry,
            enabled=bool(data.get("enabled", True)),
            object_types=object_types,
            capacity=int(data.get("capacity") or data.get("max_capacity") or 10),
            dwell_threshold_seconds=float(data.get("dwell_threshold_seconds") or 20.0),
            loitering_threshold_seconds=float(data.get("loitering_threshold_seconds") or 50.0),
            created_at=str(data.get("created_at") or datetime.now(UTC).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(UTC).isoformat()),
        )
