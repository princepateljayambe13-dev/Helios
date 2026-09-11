"""Camera Obstruction & Visibility Detection Module.

Exports detector, temporal tracker, and stream manager.
"""
from app.vision.visibility.detector import (
    CameraMetrics,
    CameraVisibilityDetector,
    DetectionResult,
)
from app.vision.visibility.manager import CameraVisibilityManager
from app.vision.visibility.temporal import (
    CameraConditionTracker,
    ConditionRecord,
)

__all__ = [
    "CameraMetrics",
    "DetectionResult",
    "CameraVisibilityDetector",
    "ConditionRecord",
    "CameraConditionTracker",
    "CameraVisibilityManager",
]
