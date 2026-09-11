"""Temporal Hysteresis Filter and State Tracker for Camera Visibility.

Prevents false alarms by requiring N consecutive degraded frames before triggering
an alert/state transition, and M consecutive clear frames before resolving.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.vision.visibility.detector import CameraMetrics, DetectionResult


@dataclass
class ConditionRecord:
    """Current state of a camera's visibility and reliability."""

    camera_id: str
    condition: str             # Current active condition (e.g. CLEAR, DEAD_FEED, BLURRED, etc.)
    reliability_score: int     # 0 to 100
    confidence: float          # 0.0 to 1.0
    reason: str                # Human-readable explanation
    metrics: CameraMetrics     # Latest quantitative vision metrics
    started_at: str            # ISO 8601 timestamp when current condition began
    last_updated_at: str       # ISO 8601 timestamp of last evaluation
    duration_seconds: float    # How long the current condition has persisted
    resolved_at: str | None = None # ISO 8601 timestamp if recovered to CLEAR

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["metrics"] = self.metrics.to_dict()
        return d


class CameraConditionTracker:
    """Tracks condition across consecutive frames with temporal hysteresis."""

    def __init__(
        self,
        camera_id: str,
        trigger_threshold: int = 3,
        recovery_threshold: int = 4,
        window_size: int = 20,
    ) -> None:
        self.camera_id = camera_id
        self.trigger_threshold = trigger_threshold
        self.recovery_threshold = recovery_threshold
        self.window_size = window_size

        now_iso = datetime.now(timezone.utc).isoformat()
        self.current_condition: str = "CLEAR"
        self.reliability_score: int = 100
        self.confidence: float = 1.0
        self.reason: str = "CCTV feed is clear and unobstructed"
        self.started_at: str = now_iso
        self.last_updated_at: str = now_iso
        self.resolved_at: str | None = None
        self.start_dt: datetime = datetime.now(timezone.utc)

        self._recent_detections: deque[DetectionResult] = deque(maxlen=window_size)
        self.latest_metrics: CameraMetrics = CameraMetrics(
            brightness=128.0,
            brightness_p5=30.0,
            brightness_p95=220.0,
            contrast=45.0,
            laplacian_variance=120.0,
            white_pixel_ratio=0.0,
            edge_density=0.04,
            frame_difference=5.0,
            vertical_edge_ratio=1.0,
            patch_occlusion_ratio=0.0,
        )

    def update(
        self,
        result: DetectionResult,
        now: datetime | None = None,
    ) -> tuple[bool, ConditionRecord]:
        """Process a single-frame detection result through temporal hysteresis.

        Returns:
            (is_state_changed, current_condition_record)
        """
        if now is None:
            now = datetime.now(timezone.utc)

        self._recent_detections.append(result)
        self.latest_metrics = result.metrics
        self.last_updated_at = now.isoformat()

        is_state_changed = False

        if self.current_condition == "CLEAR":
            if result.condition != "CLEAR":
                # Check if last N detections are all this same degraded condition
                if len(self._recent_detections) >= self.trigger_threshold:
                    tail = list(self._recent_detections)[-self.trigger_threshold:]
                    if all(r.condition == result.condition for r in tail):
                        # Trigger condition
                        self.current_condition = result.condition
                        self.reliability_score = result.reliability_score
                        self.confidence = float(sum(r.confidence for r in tail) / len(tail))
                        self.reason = result.reason
                        self.start_dt = now
                        self.started_at = now.isoformat()
                        self.resolved_at = None
                        is_state_changed = True
            else:
                # Still CLEAR, refresh reliability
                self.reliability_score = result.reliability_score
                self.confidence = result.confidence
                self.reason = result.reason

        else:
            # Currently in a degraded state
            if result.condition == "CLEAR":
                # Check for recovery confirmation (M consecutive CLEAR frames)
                if len(self._recent_detections) >= self.recovery_threshold:
                    tail = list(self._recent_detections)[-self.recovery_threshold:]
                    if all(r.condition == "CLEAR" for r in tail):
                        # Recovered!
                        self.resolved_at = now.isoformat()
                        self.current_condition = "CLEAR"
                        self.reliability_score = result.reliability_score
                        self.confidence = float(sum(r.confidence for r in tail) / len(tail))
                        self.reason = "Camera visibility fully recovered to normal clear feed"
                        self.start_dt = now
                        self.started_at = now.isoformat()
                        is_state_changed = True
            elif result.condition != self.current_condition:
                # Transitioning to a different degraded condition (e.g. FOG to DEAD_FEED)
                if len(self._recent_detections) >= self.trigger_threshold:
                    tail = list(self._recent_detections)[-self.trigger_threshold:]
                    if all(r.condition == result.condition for r in tail):
                        self.current_condition = result.condition
                        self.reliability_score = result.reliability_score
                        self.confidence = float(sum(r.confidence for r in tail) / len(tail))
                        self.reason = result.reason
                        self.start_dt = now
                        self.started_at = now.isoformat()
                        self.resolved_at = None
                        is_state_changed = True
            else:
                # Sustained same degraded condition - update score/confidence
                self.reliability_score = result.reliability_score
                self.confidence = result.confidence
                self.reason = result.reason

        duration = max(0.0, (now - self.start_dt).total_seconds())

        record = ConditionRecord(
            camera_id=self.camera_id,
            condition=self.current_condition,
            reliability_score=self.reliability_score,
            confidence=round(self.confidence, 3),
            reason=self.reason,
            metrics=self.latest_metrics,
            started_at=self.started_at,
            last_updated_at=self.last_updated_at,
            duration_seconds=round(duration, 1),
            resolved_at=self.resolved_at,
        )

        return is_state_changed, record

    def get_current_record(self) -> ConditionRecord:
        now = datetime.now(timezone.utc)
        duration = max(0.0, (now - self.start_dt).total_seconds())
        return ConditionRecord(
            camera_id=self.camera_id,
            condition=self.current_condition,
            reliability_score=self.reliability_score,
            confidence=round(self.confidence, 3),
            reason=self.reason,
            metrics=self.latest_metrics,
            started_at=self.started_at,
            last_updated_at=self.last_updated_at,
            duration_seconds=round(duration, 1),
            resolved_at=self.resolved_at,
        )
