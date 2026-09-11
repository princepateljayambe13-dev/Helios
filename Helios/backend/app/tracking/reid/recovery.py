"""Track Recovery Manager using Kalman Motion Prediction and OSNet Re-ID.

Maintains temporarily lost tracks, predicts future coordinates across occlusion gaps,
and executes Hungarian Re-ID matching to restore original persistent track identities.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.tracking.reid.matching import HungarianMatcher, MatchingConfig, MatchResult
from app.tracking.track import Track


@dataclass
class LostTrackRecord:
    """Represents an active track temporarily occluded or missed by detections."""

    track_id: str | int
    camera_id: str
    object_type: str
    last_bbox: list[float]
    last_seen: str
    lost_since: str
    speed: float = 0.0
    heading_deg: float = 0.0
    velocity_xy: tuple[float, float] = (0.0, 0.0)  # (vx, vy) normalized px/s
    reid_embeddings: list[list[float]] = field(default_factory=list)
    source_class: str = ""
    confidence: float = 0.90
    recovery_count: int = 0
    trajectory_boxes: list[list[float]] = field(default_factory=list)

    def predict_position(self, current_timestamp: str, max_extrapolation_sec: float = 5.0) -> list[float]:
        """Extrapolate predicted [x, y, w, h] position forward based on last velocity."""
        try:
            t0 = datetime.fromisoformat(self.last_seen.replace("Z", "+00:00")).astimezone(UTC)
            t1 = datetime.fromisoformat(current_timestamp.replace("Z", "+00:00")).astimezone(UTC)
            dt = max(0.0, min(max_extrapolation_sec, (t1 - t0).total_seconds()))
        except Exception:
            dt = 0.5

        bx, by, bw, bh = self.last_bbox
        vx, vy = self.velocity_xy

        pred_x = max(0.0, min(1.0 - bw, bx + vx * dt))
        pred_y = max(0.0, min(1.0 - bh, by + vy * dt))
        return [round(pred_x, 4), round(pred_y, 4), round(bw, 4), round(bh, 4)]


@dataclass
class RecoveryEvent:
    """Record of a successful track recovery."""

    original_track_id: str | int
    detection_idx: int
    camera_id: str
    timestamp: str
    appearance_similarity: float
    position_distance: float
    motion_consistency: float
    iou_score: float
    composite_cost: float


class TrackRecoveryManager:
    """Manages the temporal gallery of lost tracks and executes Re-ID recovery."""

    def __init__(
        self,
        matcher: HungarianMatcher | None = None,
        max_lost_seconds: float = 12.0,
    ) -> None:
        self.matcher = matcher or HungarianMatcher()
        self.max_lost_seconds = max_lost_seconds
        # camera_id -> dict of track_id -> LostTrackRecord
        self._lost_tracks: dict[str, dict[str | int, LostTrackRecord]] = {}
        self._recovery_history: list[RecoveryEvent] = []

    def record_lost(self, track: Track, timestamp: str) -> None:
        """Register a track entering LOST state into the recovery buffer."""
        cam_id = track.camera_id
        if cam_id not in self._lost_tracks:
            self._lost_tracks[cam_id] = {}

        # Compute velocity (dx/dt, dy/dt) in normalized coordinates from last trajectory points
        vx, vy = 0.0, 0.0
        traj_points = track.trajectory.points if hasattr(track, "trajectory") else []
        if len(traj_points) >= 2:
            p0 = traj_points[-2]
            p1 = traj_points[-1]
            try:
                t0_str = p0.get("timestamp") if isinstance(p0, dict) else getattr(p0, "timestamp", "")
                t1_str = p1.get("timestamp") if isinstance(p1, dict) else getattr(p1, "timestamp", "")
                box0 = p0.get("bounding_box") if isinstance(p0, dict) else getattr(p0, "bbox", [])
                box1 = p1.get("bounding_box") if isinstance(p1, dict) else getattr(p1, "bbox", [])

                t0 = datetime.fromisoformat(t0_str.replace("Z", "+00:00")).astimezone(UTC)
                t1 = datetime.fromisoformat(t1_str.replace("Z", "+00:00")).astimezone(UTC)
                dt = (t1 - t0).total_seconds()
                if dt > 0.01 and box0 and box1:
                    vx = (box1[0] - box0[0]) / dt
                    vy = (box1[1] - box0[1]) / dt
            except Exception:
                vx, vy = 0.0, 0.0

        # If velocity is zero but heading and speed are available, derive vx, vy
        if abs(vx) < 1e-5 and abs(vy) < 1e-5 and track.speed > 1.0:
            rad = math.radians(track.heading_deg)
            # screen space: 0 deg = east, 90 deg = north (-dy)
            # Assume 1920 width normalization for speed
            norm_speed = (track.speed / 1920.0)
            vx = norm_speed * math.cos(rad)
            vy = -norm_speed * math.sin(rad)

        recent_boxes = [p.get("bounding_box", track.bbox) if isinstance(p, dict) else getattr(p, "bbox", track.bbox) for p in traj_points[-5:]] if traj_points else [track.bbox]
        embeddings = getattr(track, "reid_embeddings", [])

        self._lost_tracks[cam_id][track.track_id] = LostTrackRecord(
            track_id=track.track_id,
            camera_id=cam_id,
            object_type=track.object_type,
            last_bbox=list(track.bbox),
            last_seen=track.last_seen,
            lost_since=timestamp,
            speed=track.speed,
            heading_deg=track.heading_deg,
            velocity_xy=(vx, vy),
            reid_embeddings=list(embeddings),
            source_class=track.source_class,
            confidence=track.confidence,
            recovery_count=getattr(track, "recovery_count", 0),
            trajectory_boxes=recent_boxes,
        )

    def purge_stale(self, camera_id: str, current_timestamp: str) -> list[str | int]:
        """Prune tracks that have exceeded max_lost_seconds."""
        if camera_id not in self._lost_tracks:
            return []

        expired_ids: list[str | int] = []
        try:
            curr_dt = datetime.fromisoformat(current_timestamp.replace("Z", "+00:00")).astimezone(UTC)
        except Exception:
            curr_dt = datetime.now(UTC)

        for tid, rec in list(self._lost_tracks[camera_id].items()):
            try:
                lost_dt = datetime.fromisoformat(rec.lost_since.replace("Z", "+00:00")).astimezone(UTC)
                if (curr_dt - lost_dt).total_seconds() > self.max_lost_seconds:
                    expired_ids.append(tid)
                    del self._lost_tracks[camera_id][tid]
            except Exception:
                pass

        return expired_ids

    def recover(
        self,
        unmatched_detections: list[dict[str, Any]],
        camera_id: str,
        timestamp: str,
    ) -> list[tuple[LostTrackRecord, int, RecoveryEvent]]:
        """Attempt to match unmatched detections with temporarily lost tracks via OSNet Re-ID.

        Returns:
            List of (lost_track_record, detection_idx, recovery_event) tuples.
        """
        if camera_id not in self._lost_tracks or not self._lost_tracks[camera_id]:
            return []

        if not unmatched_detections:
            return []

        self.purge_stale(camera_id, timestamp)
        lost_records = list(self._lost_tracks[camera_id].values())
        if not lost_records:
            return []

        # Prepare candidate track payloads with predicted bounding boxes
        candidate_tracks = []
        for rec in lost_records:
            pred_box = rec.predict_position(timestamp)
            candidate_tracks.append({
                "track_id": rec.track_id,
                "camera_id": rec.camera_id,
                "object_type": rec.object_type,
                "bbox": rec.last_bbox,
                "predicted_bbox": pred_box,
                "reid_embeddings": rec.reid_embeddings,
                "speed": rec.speed,
                "heading_deg": rec.heading_deg,
            })

        # Run Hungarian matching with stricter recovery thresholds
        result: MatchResult = self.matcher.match(
            tracks=candidate_tracks,
            detections=unmatched_detections,
            max_cost_override=self.matcher.config.recovery_cost_threshold,
        )

        successful_recoveries: list[tuple[LostTrackRecord, int, RecoveryEvent]] = []

        for pair_idx, (t_idx, d_idx) in enumerate(result.matched_pairs):
            rec = lost_records[t_idx]
            det = unmatched_detections[d_idx]
            details = result.detailed_costs[pair_idx] if pair_idx < len(result.detailed_costs) else {}

            app_sim = details.get("appearance_similarity", 0.5)
            # Require minimum appearance similarity if appearance is available
            if rec.reid_embeddings and det.get("reid_embedding"):
                if app_sim < self.matcher.config.recovery_reid_threshold:
                    continue

            event = RecoveryEvent(
                original_track_id=rec.track_id,
                detection_idx=d_idx,
                camera_id=camera_id,
                timestamp=timestamp,
                appearance_similarity=app_sim,
                position_distance=details.get("position_distance", 0.0),
                motion_consistency=details.get("motion_consistency", 1.0),
                iou_score=details.get("iou", 0.0),
                composite_cost=details.get("composite_cost", 0.0),
            )
            self._recovery_history.append(event)
            successful_recoveries.append((rec, d_idx, event))

            # Remove from lost tracks buffer since it is recovered
            self._lost_tracks[camera_id].pop(rec.track_id, None)

        return successful_recoveries

    def clear(self, camera_id: str | None = None) -> None:
        """Clear lost track states."""
        if camera_id:
            self._lost_tracks.pop(camera_id, None)
        else:
            self._lost_tracks.clear()
            self._recovery_history.clear()
