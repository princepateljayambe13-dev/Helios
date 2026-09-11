"""Spatial engine: evaluates track trajectory against configured zones and virtual fences."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.spatial.geometry import box_bottom_center
from app.spatial.zone import Zone

LOGGER = logging.getLogger(__name__)


@dataclass
class TrackZoneState:
    """Tracks state of a specific track with respect to a single zone."""

    status: str = "UNKNOWN"  # "UNKNOWN", "OUTSIDE", "INSIDE"
    consecutive_inside_count: int = 0
    consecutive_outside_count: int = 0
    has_triggered: bool = False
    last_position: tuple[float, float] | None = None
    last_seen_timestamp: str | None = None

    # Loitering & Dwell Intelligence
    entry_timestamp: str | None = None
    entry_epoch: float | None = None
    last_epoch: float | None = None
    total_inside_duration: float = 0.0
    stationary_duration: float = 0.0
    loitering_status: str = "NORMAL"  # "NORMAL", "DWELLING", "LOITERING"
    has_triggered_dwell: bool = False
    has_triggered_loiter: bool = False
    last_movement_state: str = "STATIONARY"
    consecutive_moving_count: int = 0
    object_type: str = "HUMAN"


class SpatialEngine:
    """Manages zones and evaluates spatial intrusion rules per camera feed."""

    def __init__(
        self,
        confirmation_frames: int = 2,
        exit_confirmation_frames: int = 2,
    ) -> None:
        self.confirmation_frames = max(1, confirmation_frames)
        self.exit_confirmation_frames = max(1, exit_confirmation_frames)
        # camera_id -> dict of zone_id -> Zone
        self.zones: dict[str, dict[str, Zone]] = defaultdict(dict)
        # (camera_id, track_id, zone_id) -> TrackZoneState
        self.track_states: dict[tuple[str, str, str], TrackZoneState] = {}

    def load_zones(self, zones_data: list[dict[str, Any]]) -> None:
        """Load or reload all zones from DB records or configurations."""
        self.zones.clear()
        for data in zones_data:
            zone = Zone.from_dict(data)
            self.zones[zone.camera_id][zone.zone_id] = zone

    def add_or_update_zone(self, zone_data: dict[str, Any] | Zone) -> Zone:
        """Register or update a single zone."""
        zone = zone_data if isinstance(zone_data, Zone) else Zone.from_dict(zone_data)
        self.zones[zone.camera_id][zone.zone_id] = zone
        return zone

    def remove_zone(self, zone_id: str) -> None:
        """Remove a zone from all cameras and purge associated track states."""
        for camera_id in list(self.zones.keys()):
            if zone_id in self.zones[camera_id]:
                del self.zones[camera_id][zone_id]
        # Purge track states matching this zone
        keys_to_remove = [k for k in self.track_states if k[2] == zone_id]
        for k in keys_to_remove:
            del self.track_states[k]

    def purge_track(self, camera_id: str, track_id: str) -> None:
        """Clean up spatial states for a concluded or expired track."""
        keys_to_remove = [k for k in self.track_states if k[0] == camera_id and k[1] == track_id]
        for k in keys_to_remove:
            del self.track_states[k]

    def get_zone_for_point(self, camera_id: str, point: tuple[float, float]) -> Zone | None:
        """Find the first enabled zone containing the given camera-space point."""
        cam_zones = self.zones.get(camera_id, {})
        for zone in cam_zones.values():
            if zone.enabled and zone.contains_point(point):
                return zone
        return None

    @staticmethod
    def _parse_epoch(timestamp: Any) -> float:
        """Parse ISO timestamp or numeric value into epoch seconds."""
        if isinstance(timestamp, (int, float)):
            return float(timestamp)
        try:
            from datetime import datetime, UTC
            return datetime.fromisoformat(str(timestamp)).timestamp()
        except Exception:
            import time
            return time.time()

    def process_observation(
        self,
        observation: dict[str, Any],
        track_id: str,
        is_new_track: bool = False,
        movement_state: str | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate observation against all active zones for the camera.

        Returns a list of confirmed spatial event descriptors (INTRUSION, LOITERING, etc.).
        """
        camera_id = observation["camera_id"]
        bbox = observation.get("bounding_box", [])
        if len(bbox) < 4:
            return []

        # Requirement: For each tracked object, use the bottom-center of its bounding box
        bottom_center = box_bottom_center(bbox)
        object_type = observation.get("object_type", "UNKNOWN").upper()
        confidence = float(observation.get("confidence", 0.9))
        timestamp = observation.get("timestamp")
        curr_epoch = self._parse_epoch(timestamp)

        # Movement state (from MovementTracker: STATIONARY, WALKING, RUNNING, SLOW_MOVING, CRUISING)
        mstate = (movement_state or observation.get("movement_state") or "STATIONARY").upper()

        cam_zones = self.zones.get(camera_id, {})
        if not cam_zones:
            return []

        events: list[dict[str, Any]] = []

        for zone_id, zone in cam_zones.items():
            if not zone.enabled:
                continue

            # Check if this zone filters by object type
            if not zone.applies_to(object_type):
                continue

            state_key = (camera_id, track_id, zone_id)
            state = self.track_states.get(state_key)
            if state is None:
                state = TrackZoneState()
                self.track_states[state_key] = state

            state.object_type = object_type
            is_inside = zone.contains_point(bottom_center)

            if is_inside:
                state.consecutive_inside_count += 1
                state.consecutive_outside_count = 0

                # Determine if entering zone for the first time
                just_entered = False
                if state.status == "OUTSIDE":
                    if state.consecutive_inside_count >= self.confirmation_frames and not state.has_triggered:
                        state.status = "INSIDE"
                        state.has_triggered = True
                        just_entered = True

                        if zone.is_restricted():
                            events.append({
                                "event_type": "INTRUSION",
                                "camera_id": camera_id,
                                "zone_id": zone.zone_id,
                                "zone_name": zone.name,
                                "zone_type": zone.zone_type,
                                "track_id": track_id,
                                "object_type": object_type,
                                "timestamp": timestamp,
                                "confidence": confidence,
                                "direction": "OUTSIDE -> INSIDE",
                                "bottom_center": list(bottom_center),
                                "bounding_box": bbox,
                            })
                elif state.status == "UNKNOWN":
                    if state.consecutive_inside_count >= self.confirmation_frames:
                        state.status = "INSIDE"
                        just_entered = True
                        if zone.is_restricted() and not state.has_triggered:
                            state.has_triggered = True
                            events.append({
                                "event_type": "INTRUSION",
                                "camera_id": camera_id,
                                "zone_id": zone.zone_id,
                                "zone_name": zone.name,
                                "zone_type": zone.zone_type,
                                "track_id": track_id,
                                "object_type": object_type,
                                "timestamp": timestamp,
                                "confidence": confidence,
                                "direction": "INITIATION_INSIDE",
                                "bottom_center": list(bottom_center),
                                "bounding_box": bbox,
                            })

                # Dwell & Loitering accumulation while INSIDE
                if state.status == "INSIDE":
                    if state.entry_epoch is None or just_entered:
                        state.entry_epoch = curr_epoch
                        state.entry_timestamp = timestamp
                        state.last_epoch = curr_epoch
                        state.total_inside_duration = 0.0
                        state.stationary_duration = 0.0
                        state.loitering_status = "NORMAL"
                        state.has_triggered_dwell = False
                        state.has_triggered_loiter = False
                        state.consecutive_moving_count = 0

                    # Time step since last observation inside this zone
                    dt = max(0.0, curr_epoch - (state.last_epoch or curr_epoch))
                    state.last_epoch = curr_epoch
                    state.total_inside_duration = max(0.0, curr_epoch - state.entry_epoch)
                    state.last_movement_state = mstate

                    # Movement state filtering:
                    # Continuously moving objects (WALKING, RUNNING, CRUISING, FAST) do NOT accumulate loitering penalty
                    is_moving_fast = mstate in ("WALKING", "RUNNING", "CRUISING", "FAST", "MOVING")
                    is_stationary_or_slow = mstate in ("STATIONARY", "SLOW_MOVING", "STOPPED", "UNKNOWN")

                    if is_stationary_or_slow:
                        state.stationary_duration += dt
                        state.consecutive_moving_count = 0
                    else:
                        state.consecutive_moving_count += 1
                        # If the entity is continuously moving through, actively decay stationary time
                        if state.consecutive_moving_count >= 3:
                            state.stationary_duration = max(0.0, state.stationary_duration - (dt * 0.5))

                    dwell_thresh = getattr(zone, "dwell_threshold_seconds", 20.0)
                    loiter_thresh = getattr(zone, "loitering_threshold_seconds", 50.0)

                    # State transitions: NORMAL -> DWELLING -> LOITERING
                    if state.stationary_duration >= loiter_thresh:
                        state.loitering_status = "LOITERING"
                        if not state.has_triggered_loiter:
                            state.has_triggered_loiter = True
                            events.append({
                                "event_type": "LOITERING",
                                "camera_id": camera_id,
                                "zone_id": zone.zone_id,
                                "zone_name": zone.name,
                                "zone_type": zone.zone_type,
                                "track_id": track_id,
                                "object_type": object_type,
                                "timestamp": timestamp,
                                "start_time": state.entry_timestamp or timestamp,
                                "duration_seconds": round(state.stationary_duration, 1),
                                "total_inside_seconds": round(state.total_inside_duration, 1),
                                "movement_state": mstate,
                                "loitering_status": "LOITERING",
                                "confidence": confidence,
                                "bottom_center": list(bottom_center),
                                "bounding_box": bbox,
                            })
                    elif state.stationary_duration >= dwell_thresh:
                        if state.loitering_status == "NORMAL":
                            state.loitering_status = "DWELLING"
                            state.has_triggered_dwell = True
                    else:
                        if not state.has_triggered_loiter:
                            state.loitering_status = "NORMAL"

            else:
                # Point is currently outside
                state.consecutive_outside_count += 1
                state.consecutive_inside_count = 0

                if state.status == "UNKNOWN":
                    if state.consecutive_outside_count >= 1:
                        state.status = "OUTSIDE"
                elif state.status == "INSIDE":
                    # Debounced exit
                    if state.consecutive_outside_count >= self.exit_confirmation_frames:
                        state.status = "OUTSIDE"
                        state.has_triggered = False  # Reset trigger so a future re-entry triggers an intrusion
                        # Notify session end for loitering/dwelling
                        if state.loitering_status in ("DWELLING", "LOITERING") or state.has_triggered_loiter:
                            events.append({
                                "event_type": "ZONE_EXIT",
                                "camera_id": camera_id,
                                "zone_id": zone.zone_id,
                                "zone_name": zone.name,
                                "track_id": track_id,
                                "object_type": object_type,
                                "timestamp": timestamp,
                                "start_time": state.entry_timestamp or timestamp,
                                "end_time": timestamp,
                                "duration_seconds": round(state.stationary_duration, 1),
                                "total_inside_seconds": round(state.total_inside_duration, 1),
                                "movement_state": mstate,
                                "loitering_status": state.loitering_status,
                            })
                        # Reset dwell timers
                        state.entry_epoch = None
                        state.entry_timestamp = None
                        state.stationary_duration = 0.0
                        state.total_inside_duration = 0.0
                        state.loitering_status = "NORMAL"
                        state.has_triggered_loiter = False
                        state.has_triggered_dwell = False

            state.last_position = bottom_center
            state.last_seen_timestamp = timestamp

        return events

    def get_active_dwell_tracks(
        self,
        camera_id: str | None = None,
        zone_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all active targets currently inside monitored zones with live dwell duration."""
        results: list[dict[str, Any]] = []
        for (cam, trk, z_id), state in self.track_states.items():
            if camera_id and cam != camera_id:
                continue
            if zone_id and z_id != zone_id:
                continue
            if state.status != "INSIDE":
                continue

            zone = self.zones.get(cam, {}).get(z_id)
            zone_name = zone.name if zone else z_id
            dwell_th = getattr(zone, "dwell_threshold_seconds", 20.0) if zone else 20.0
            loiter_th = getattr(zone, "loitering_threshold_seconds", 50.0) if zone else 50.0

            results.append({
                "camera_id": cam,
                "zone_id": z_id,
                "zone_name": zone_name,
                "track_id": trk,
                "object_type": state.object_type,
                "entry_time": state.entry_timestamp,
                "last_seen_time": state.last_seen_timestamp,
                "duration_seconds": round(state.total_inside_duration, 1),
                "stationary_duration": round(state.stationary_duration, 1),
                "movement_state": state.last_movement_state,
                "loitering_status": state.loitering_status,
                "dwell_threshold_seconds": dwell_th,
                "loitering_threshold_seconds": loiter_th,
                "position": state.last_position,
            })
        return results
