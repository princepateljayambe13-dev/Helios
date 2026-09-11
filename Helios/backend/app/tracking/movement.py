"""Speed, Direction, and Movement Intelligence Engine for HELIOS.

Evaluates spatial-temporal trajectories from YOLO + ByteTrack detections to compute:
- Filtered pixel speeds (px/s) and physical speeds (km/h) via camera calibration hooks.
- Stateful hysteresis movement classification for persons (STATIONARY, WALKING, RUNNING).
- Vehicle movement states (STATIONARY, SLOW_MOVING, CRUISING, FAST).
- Camera-relative 8-cardinal directions (NORTH/Receding, SOUTH/Approaching, etc.) and headings.
- Cumulative distance traversed across trajectories.
- Discrete movement change events (STARTED_MOVING, STOPPED, ACCELERATED, DECELERATED, DIRECTION_CHANGED).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
from typing import Any


@dataclass
class MovementConfig:
    """Configurable thresholds for movement intelligence."""

    # Nominal human speed thresholds (px/s)
    stationary_threshold: float = 8.0
    walking_threshold: float = 35.0
    running_threshold: float = 35.0

    # Hysteresis transition thresholds for human movement (px/s)
    walking_entry_speed: float = 10.0   # STATIONARY -> WALKING entry: > 10 px/s
    running_entry_speed: float = 38.0   # WALKING/STATIONARY -> RUNNING entry: > 38 px/s
    running_exit_speed: float = 32.0    # RUNNING -> WALKING drop: < 32 px/s
    walking_exit_speed: float = 6.0     # WALKING -> STATIONARY drop: < 6 px/s

    # Vehicle speed thresholds (px/s)
    vehicle_stationary_threshold: float = 10.0
    vehicle_slow_threshold: float = 40.0
    vehicle_cruising_threshold: float = 100.0

    # Meaningful movement change thresholds
    min_moving_speed: float = 5.0             # Minimum speed to consider object actively moving for direction
    acceleration_speed_delta: float = 15.0    # Speed jump (px/s) to trigger ACCELERATED
    deceleration_speed_delta: float = -15.0   # Speed drop (px/s) to trigger DECELERATED
    direction_change_deg: float = 45.0        # Heading angle difference (deg) to trigger DIRECTION_CHANGED

    # Default reference frame dimensions when normalizing coordinates
    default_frame_width: float = 1920.0
    default_frame_height: float = 1080.0

    # Smoothing factor for exponential moving average of speed (0.0 to 1.0)
    speed_smoothing_alpha: float = 0.65


@dataclass
class CameraCalibration:
    """Camera spatial calibration for physical speed and metric measurements.

    Enables seamless conversion from pixels/second to km/h and meters.
    """

    camera_id: str
    pixels_per_meter: float | None = None
    frame_width: int = 1920
    frame_height: int = 1080
    ppm_depth_map: list[float] | None = None  # Optional depth-dependent scaling

    @property
    def is_calibrated(self) -> bool:
        return self.pixels_per_meter is not None and self.pixels_per_meter > 0

    def pixels_to_meters(self, pixels: float) -> float | None:
        if not self.is_calibrated or self.pixels_per_meter is None:
            return None
        return round(pixels / self.pixels_per_meter, 3)

    def speed_to_kmh(self, speed_px_per_sec: float) -> float | None:
        """Convert speed in px/s to km/h: (px/s / ppm) * 3.6."""
        if not self.is_calibrated or self.pixels_per_meter is None:
            return None
        meters_per_sec = speed_px_per_sec / self.pixels_per_meter
        return round(meters_per_sec * 3.6, 2)


@dataclass
class MovementSnapshot:
    """Point-in-time movement intelligence record for a tracked entity."""

    track_id: str
    camera_id: str
    object_type: str
    timestamp: str
    position: list[float]                 # Bounding box [x, y, w, h] or center
    speed: float                          # Speed in px/s (or primary unit)
    speed_unit: str = "px/s"
    speed_kmh: float | None = None        # Calibrated km/h if camera calibrated
    direction: str = "STATIONARY"         # 8-cardinal: NORTH, NORTH_EAST, EAST, etc.
    heading_deg: float = 0.0              # 0.0 - 360.0 degrees
    camera_direction_label: str = "STATIONARY" # Human-readable camera perspective
    movement_state: str = "STATIONARY"    # STATIONARY, WALKING, RUNNING, etc.
    distance_travelled: float = 0.0       # Cumulative distance in pixels (or meters)
    movement_change: str | None = None    # STARTED_MOVING, STOPPED, ACCELERATED, etc.
    acceleration: float = 0.0             # px/s^2

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["speed"] = round(self.speed, 2)
        data["heading_deg"] = round(self.heading_deg, 1)
        data["distance_travelled"] = round(self.distance_travelled, 2)
        data["acceleration"] = round(self.acceleration, 2)
        if self.speed_kmh is not None:
            data["speed_kmh"] = round(self.speed_kmh, 2)
        return data


class DirectionCalculator:
    """Calculates heading angles and camera-relative cardinal directions.

    In surveillance video coordinate space:
    - Origin (0,0) is top-left of camera frame.
    - x increases rightward (dx > 0 -> EAST / Left-to-Right).
    - y increases downward (dy > 0 -> SOUTH / Approaching camera; -dy > 0 -> NORTH / Receding from camera).
    """

    CARDINAL_SECTORS = [
        ("EAST", 0.0, 22.5, "EAST (Left-to-Right)"),
        ("NORTH_EAST", 22.5, 67.5, "NORTH-EAST (Receding Right)"),
        ("NORTH", 67.5, 112.5, "NORTH (Receding / Up)"),
        ("NORTH_WEST", 112.5, 157.5, "NORTH-WEST (Receding Left)"),
        ("WEST", 157.5, 202.5, "WEST (Right-to-Left)"),
        ("SOUTH_WEST", 202.5, 247.5, "SOUTH-WEST (Approaching Left)"),
        ("SOUTH", 247.5, 292.5, "SOUTH (Approaching / Down)"),
        ("SOUTH_EAST", 292.5, 337.5, "SOUTH-EAST (Approaching Right)"),
        ("EAST", 337.5, 360.0, "EAST (Left-to-Right)"),
    ]

    @classmethod
    def calculate_heading_and_direction(
        cls,
        dx: float,
        dy: float,
        speed: float,
        min_speed: float = 5.0,
        previous_heading: float = 0.0,
    ) -> tuple[float, str, str]:
        """Compute heading in degrees [0, 360), 8-cardinal direction, and camera label.

        Args:
            dx: Horizontal displacement in pixels.
            dy: Vertical displacement in pixels (screen space: positive is downward).
            speed: Current speed in px/s.
            min_speed: Speed threshold below which object is treated as STATIONARY.
            previous_heading: Last known heading degrees if movement is negligible.

        Returns:
            (heading_deg, direction_code, camera_direction_label)
        """
        dist = math.hypot(dx, dy)
        if speed < min_speed or dist < 2.0:
            return previous_heading, "STATIONARY", "STATIONARY (No Movement)"

        # Invert dy so that screen-upward movement (-dy) is positive Y (North / 90 deg)
        angle_rad = math.atan2(-dy, dx)
        heading_deg = (math.degrees(angle_rad) + 360.0) % 360.0

        direction_code = "EAST"
        camera_label = "EAST (Left-to-Right)"

        for code, lower, upper, label in cls.CARDINAL_SECTORS:
            if lower <= heading_deg < upper:
                direction_code = code
                camera_label = label
                break

        return heading_deg, direction_code, camera_label

    @staticmethod
    def angle_difference(a: float, b: float) -> float:
        """Compute absolute angular difference in degrees accounting for wrap-around."""
        diff = abs((a - b + 180.0) % 360.0 - 180.0)
        return diff


class HysteresisMovementClassifier:
    """Stateful movement classifier with hysteresis to prevent oscillation."""

    def __init__(self, config: MovementConfig | None = None) -> None:
        self.config = config or MovementConfig()

    def classify_human(
        self,
        speed: float,
        current_state: str | None = None,
    ) -> str:
        """Classify human movement state using hysteresis rules:

        - Walking entry: speed > 10 px/s
        - Running entry: speed > 38 px/s
        - Running -> Walking drop: speed < 32 px/s
        - Walking -> Stationary drop: speed < 6 px/s
        """
        curr = (current_state or "").upper()

        if curr == "RUNNING":
            if speed < self.config.walking_exit_speed:
                return "STATIONARY"
            if speed < self.config.running_exit_speed:
                return "WALKING"
            return "RUNNING"

        if curr == "WALKING":
            if speed > self.config.running_entry_speed:
                return "RUNNING"
            if speed < self.config.walking_exit_speed:
                return "STATIONARY"
            return "WALKING"

        if curr == "STATIONARY":
            if speed > self.config.running_entry_speed:
                return "RUNNING"
            if speed > self.config.walking_entry_speed:
                return "WALKING"
            return "STATIONARY"

        # Initial classification (no prior state)
        if speed >= self.config.running_threshold:
            return "RUNNING"
        if speed >= self.config.stationary_threshold:
            return "WALKING"
        return "STATIONARY"

    def classify_vehicle(
        self,
        speed: float,
        current_state: str | None = None,
    ) -> str:
        """Classify vehicle movement state."""
        if speed < self.config.vehicle_stationary_threshold:
            return "STATIONARY"
        if speed < self.config.vehicle_slow_threshold:
            return "SLOW_MOVING"
        if speed < self.config.vehicle_cruising_threshold:
            return "CRUISING"
        return "FAST"

    def classify(
        self,
        object_type: str,
        speed: float,
        current_state: str | None = None,
    ) -> str:
        """Classify movement state based on object type."""
        norm_type = (object_type or "OBJECT").upper()
        if norm_type in ("HUMAN", "PERSON"):
            return self.classify_human(speed, current_state)
        if norm_type in ("VEHICLE", "CAR", "TRUCK", "BUS", "VAN", "SUV"):
            return self.classify_vehicle(speed, current_state)
        # Generic objects (UAV, ANIMAL, etc.)
        if speed < self.config.stationary_threshold:
            return "STATIONARY"
        return "MOVING"


class MovementTracker:
    """Manages spatial movement intelligence, trajectories, and change detection."""

    def __init__(
        self,
        config: MovementConfig | None = None,
        calibrations: dict[str, CameraCalibration] | None = None,
    ) -> None:
        self.config = config or MovementConfig()
        self.classifier = HysteresisMovementClassifier(self.config)
        self.calibrations: dict[str, CameraCalibration] = calibrations or {}
        # track_id -> dict with tracking state
        self._track_states: dict[str, dict[str, Any]] = {}

    def set_calibration(self, camera_id: str, calibration: CameraCalibration) -> None:
        self.calibrations[camera_id] = calibration

    def get_calibration(self, camera_id: str) -> CameraCalibration:
        if camera_id not in self.calibrations:
            self.calibrations[camera_id] = CameraCalibration(camera_id=camera_id)
        return self.calibrations[camera_id]

    def _normalize_point(
        self,
        bbox_or_point: list[float],
        camera_id: str,
    ) -> tuple[float, float]:
        """Extract pixel (cx, cy) center point from bbox [x, y, w, h] or [cx, cy]."""
        cal = self.get_calibration(camera_id)
        fw = float(cal.frame_width or self.config.default_frame_width)
        fh = float(cal.frame_height or self.config.default_frame_height)

        if len(bbox_or_point) >= 4:
            x, y, w, h = (float(v) for v in bbox_or_point[:4])
            # If coordinates are normalized in [0.0, 1.0]
            if x <= 1.0 and y <= 1.0 and w <= 1.0 and h <= 1.0:
                cx = (x + w / 2.0) * fw
                cy = (y + h / 2.0) * fh
            else:
                cx = x + w / 2.0
                cy = y + h / 2.0
            return cx, cy
        if len(bbox_or_point) == 2:
            x, y = float(bbox_or_point[0]), float(bbox_or_point[1])
            if x <= 1.0 and y <= 1.0:
                return x * fw, y * fh
            return x, y
        return 0.0, 0.0

    @staticmethod
    def _parse_timestamp(ts: Any) -> float:
        """Parse ISO timestamp or float into epoch seconds."""
        if isinstance(ts, (int, float)):
            return float(ts)
        try:
            return datetime.fromisoformat(str(ts)).timestamp()
        except Exception:
            return datetime.now(UTC).timestamp()

    def update(
        self,
        track_id: str,
        camera_id: str,
        object_type: str,
        bounding_box: list[float],
        timestamp: str | None = None,
    ) -> MovementSnapshot:
        """Compute movement metrics for a new observation and return snapshot."""
        stamp_str = timestamp or datetime.now(UTC).isoformat()
        curr_t = self._parse_timestamp(stamp_str)
        cx, cy = self._normalize_point(bounding_box, camera_id)

        cal = self.get_calibration(camera_id)

        if track_id not in self._track_states:
            # First observation of track
            state = {
                "track_id": track_id,
                "camera_id": camera_id,
                "object_type": object_type,
                "last_pos": (cx, cy),
                "last_timestamp": curr_t,
                "raw_speed": 0.0,
                "smoothed_speed": 0.0,
                "heading_deg": 0.0,
                "direction": "STATIONARY",
                "camera_direction_label": "STATIONARY (Initiation)",
                "movement_state": "STATIONARY",
                "distance_travelled": 0.0,
                "acceleration": 0.0,
                "last_change": None,
            }
            self._track_states[track_id] = state
            return MovementSnapshot(
                track_id=track_id,
                camera_id=camera_id,
                object_type=object_type,
                timestamp=stamp_str,
                position=bounding_box,
                speed=0.0,
                speed_unit="px/s",
                speed_kmh=0.0 if cal.is_calibrated else None,
                direction="STATIONARY",
                heading_deg=0.0,
                camera_direction_label="STATIONARY",
                movement_state="STATIONARY",
                distance_travelled=0.0,
                movement_change=None,
                acceleration=0.0,
            )

        state = self._track_states[track_id]
        prev_cx, prev_cy = state["last_pos"]
        prev_t = state["last_timestamp"]
        prev_speed = state["smoothed_speed"]
        prev_heading = state["heading_deg"]
        prev_mstate = state["movement_state"]
        prev_distance = state["distance_travelled"]

        dt = max(0.01, curr_t - prev_t)
        dx = cx - prev_cx
        dy = cy - prev_cy
        step_distance = math.hypot(dx, dy)

        instant_speed = step_distance / dt

        # Smooth speed using exponential moving average
        alpha = self.config.speed_smoothing_alpha
        smoothed_speed = alpha * instant_speed + (1.0 - alpha) * prev_speed

        cumulative_distance = prev_distance + step_distance
        acceleration = (smoothed_speed - prev_speed) / dt

        # Compute heading and 8-cardinal direction
        heading_deg, direction_code, cam_label = DirectionCalculator.calculate_heading_and_direction(
            dx=dx,
            dy=dy,
            speed=smoothed_speed,
            min_speed=self.config.min_moving_speed,
            previous_heading=prev_heading,
        )

        # Hysteresis movement classification
        new_mstate = self.classifier.classify(
            object_type=object_type,
            speed=smoothed_speed,
            current_state=prev_mstate,
        )

        # Meaningful change detection
        movement_change = None
        speed_delta = smoothed_speed - prev_speed

        if prev_mstate == "STATIONARY" and new_mstate != "STATIONARY":
            movement_change = "STARTED_MOVING"
        elif prev_mstate != "STATIONARY" and new_mstate == "STATIONARY":
            movement_change = "STOPPED"
        elif speed_delta >= self.config.acceleration_speed_delta:
            movement_change = "ACCELERATED"
        elif speed_delta <= self.config.deceleration_speed_delta:
            movement_change = "DECELERATED"
        elif (
            smoothed_speed >= self.config.min_moving_speed
            and DirectionCalculator.angle_difference(heading_deg, prev_heading) >= self.config.direction_change_deg
        ):
            movement_change = "DIRECTION_CHANGED"

        # Update cached state
        state["last_pos"] = (cx, cy)
        state["last_timestamp"] = curr_t
        state["raw_speed"] = instant_speed
        state["smoothed_speed"] = smoothed_speed
        state["heading_deg"] = heading_deg
        state["direction"] = direction_code
        state["camera_direction_label"] = cam_label
        state["movement_state"] = new_mstate
        state["distance_travelled"] = cumulative_distance
        state["acceleration"] = acceleration
        if movement_change:
            state["last_change"] = movement_change

        speed_kmh = cal.speed_to_kmh(smoothed_speed)

        return MovementSnapshot(
            track_id=track_id,
            camera_id=camera_id,
            object_type=object_type,
            timestamp=stamp_str,
            position=bounding_box,
            speed=smoothed_speed,
            speed_unit="px/s",
            speed_kmh=speed_kmh,
            direction=direction_code,
            heading_deg=heading_deg,
            camera_direction_label=cam_label,
            movement_state=new_mstate,
            distance_travelled=cumulative_distance,
            movement_change=movement_change,
            acceleration=acceleration,
        )

    def get_track_snapshot(self, track_id: str) -> dict[str, Any] | None:
        """Return latest movement snapshot dictionary for track."""
        state = self._track_states.get(track_id)
        if not state:
            return None
        cal = self.get_calibration(state["camera_id"])
        speed = state["smoothed_speed"]
        return {
            "track_id": track_id,
            "camera_id": state["camera_id"],
            "object_type": state["object_type"],
            "speed": round(speed, 2),
            "speed_unit": "px/s",
            "speed_kmh": cal.speed_to_kmh(speed),
            "direction": state["direction"],
            "heading_deg": round(state["heading_deg"], 1),
            "camera_direction_label": state["camera_direction_label"],
            "movement_state": state["movement_state"],
            "distance_travelled": round(state["distance_travelled"], 2),
            "acceleration": round(state["acceleration"], 2),
            "last_change": state.get("last_change"),
        }

    def remove_track(self, track_id: str) -> None:
        """Purge movement cache when a track is removed or expired."""
        self._track_states.pop(track_id, None)

    def clear(self) -> None:
        self._track_states.clear()
