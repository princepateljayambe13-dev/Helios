"""Per-Camera Visibility Management and Tracking.

Coordinates metric calculation, frame differencing, and temporal state tracking
for all active video streams in the HELIOS system.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import cv2
import numpy as np

from app.vision.visibility.detector import CameraMetrics, CameraVisibilityDetector, DetectionResult
from app.vision.visibility.temporal import CameraConditionTracker, ConditionRecord


class CameraVisibilityManager:
    """Manages visibility analysis and condition tracking across multiple cameras."""

    def __init__(
        self,
        trigger_threshold: int = 3,
        recovery_threshold: int = 4,
    ) -> None:
        self.trigger_threshold = trigger_threshold
        self.recovery_threshold = recovery_threshold
        self._trackers: dict[str, CameraConditionTracker] = {}
        self._prev_images: dict[str, np.ndarray] = {}

    def get_tracker(self, camera_id: str) -> CameraConditionTracker:
        if camera_id not in self._trackers:
            self._trackers[camera_id] = CameraConditionTracker(
                camera_id=camera_id,
                trigger_threshold=self.trigger_threshold,
                recovery_threshold=self.recovery_threshold,
            )
        return self._trackers[camera_id]

    def process_frame(
        self,
        camera_id: str,
        image: np.ndarray,
        timestamp: datetime | None = None,
    ) -> tuple[bool, ConditionRecord]:
        """Analyze a frame for the specified camera and update its condition state.

        Args:
            camera_id: Identifier of the camera.
            image: OpenCV BGR/RGB image array.
            timestamp: Optional evaluation timestamp (defaults to UTC now).

        Returns:
            Tuple of (is_state_changed, ConditionRecord).
        """
        tracker = self.get_tracker(camera_id)
        prev_image = self._prev_images.get(camera_id)

        # Calculate metrics
        metrics = CameraVisibilityDetector.calculate_metrics(image, prev_image=prev_image)

        # Cache a small grayscale representation for future frame differencing to save memory
        if image is not None and image.size > 0:
            if image.ndim == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image
            if gray.shape[1] > 320:
                scale = 320.0 / gray.shape[1]
                small = cv2.resize(gray, (320, int(gray.shape[0] * scale)), interpolation=cv2.INTER_AREA)
            else:
                small = gray
            self._prev_images[camera_id] = small

        # Classify single frame
        raw_result = CameraVisibilityDetector.classify(metrics)

        # Update through temporal hysteresis
        is_state_changed, record = tracker.update(raw_result, now=timestamp)

        return is_state_changed, record

    def get_condition(self, camera_id: str) -> ConditionRecord | None:
        """Get the current condition record for a camera if tracked."""
        tracker = self._trackers.get(camera_id)
        if tracker is None:
            return None
        return tracker.get_current_record()

    def get_all_conditions(self) -> dict[str, ConditionRecord]:
        """Get the latest condition records for all tracked cameras."""
        return {
            camera_id: tracker.get_current_record()
            for camera_id, tracker in self._trackers.items()
        }
