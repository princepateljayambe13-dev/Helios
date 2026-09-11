"""Multi-camera tracker manager for HELIOS.

Ensures strict per-camera tracker isolation: each camera feed or stream maintains
its own dedicated ByteTrackTracker instance so tracks are never intermingled.
"""
from __future__ import annotations

from typing import Any, Sequence

from app.core.config import Settings
from app.tracking.track import Track
from app.tracking.tracker import ByteTrackTracker


class CameraTrackerManager:
    """Manages independent ByteTrack tracker instances for each camera stream."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings
        self._trackers: dict[str, ByteTrackTracker] = {}

    def get_tracker(self, camera_id: str) -> ByteTrackTracker:
        """Retrieve or initialize the isolated ByteTrack tracker for a camera."""
        if camera_id not in self._trackers:
            buffer_frames = getattr(self.settings, "track_buffer_frames", 30) if self.settings else 30
            high_thresh = getattr(self.settings, "tracker_high_thresh", 0.25) if self.settings else 0.25
            low_thresh = getattr(self.settings, "tracker_low_thresh", 0.10) if self.settings else 0.10
            match_thresh = getattr(self.settings, "tracker_match_thresh", 0.80) if self.settings else 0.80
            new_thresh = getattr(self.settings, "tracker_new_track_thresh", 0.25) if self.settings else 0.25
            reid_enabled = getattr(self.settings, "reid_enabled", True) if self.settings else True
            max_lost_sec = getattr(self.settings, "reid_max_lost_seconds", 12.0) if self.settings else 12.0

            self._trackers[camera_id] = ByteTrackTracker(
                camera_id=camera_id,
                track_buffer=buffer_frames,
                track_high_thresh=high_thresh,
                track_low_thresh=low_thresh,
                match_thresh=match_thresh,
                new_track_thresh=new_thresh,
                reid_enabled=reid_enabled,
                max_lost_seconds=max_lost_sec,
            )
        return self._trackers[camera_id]

    def track(
        self,
        camera_id: str,
        detections: Sequence[dict[str, Any]] | Any,
        image_shape: tuple[int, int] = (1000, 1000),
        timestamp: str | None = None,
        frame: Any = None,
    ) -> list[Track]:
        """Process detections for a specific camera and return active persistent tracks."""
        tracker = self.get_tracker(camera_id)
        return tracker.update(detections, image_shape=image_shape, timestamp=timestamp, frame=frame)

    def get_recent_recoveries(self, camera_id: str) -> list[Any]:
        """Retrieve any recoveries generated in the latest tracking cycle."""
        tracker = self._trackers.get(camera_id)
        return list(tracker.recent_recoveries) if tracker else []

    def reset(self, camera_id: str | None = None) -> None:
        """Reset tracker state for a given camera, or all cameras if None."""
        if camera_id:
            for k in list(self._trackers.keys()):
                if k == camera_id or k.startswith(f"{camera_id}:"):
                    self._trackers[k].reset()
        else:
            for tracker in self._trackers.values():
                tracker.reset()

    def remove(self, camera_id: str) -> None:
        """Clean up tracker when a camera is removed."""
        for k in list(self._trackers.keys()):
            if k == camera_id or k.startswith(f"{camera_id}:"):
                self._trackers.pop(k, None)
