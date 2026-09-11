import numpy as np
import cv2
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.vision.motion import Mog2MotionDetector, Mog2MotionInferenceManager


def test_mog2_detector_detects_moving_object():
    detector = Mog2MotionDetector(history=10, var_threshold=16.0, min_area_ratio=0.001)

    # Frame 1: completely black background
    frame1 = np.zeros((200, 200, 3), dtype=np.uint8)
    boxes1 = detector.detect_motion_boxes(frame1, "CAM-01")
    # First frame has no motion relative to background
    assert len(boxes1) == 0

    # Frame 2: white rectangle suddenly appears in the center
    frame2 = np.zeros((200, 200, 3), dtype=np.uint8)
    frame2[50:150, 50:150] = 255
    boxes2 = detector.detect_motion_boxes(frame2, "CAM-01")

    assert len(boxes2) > 0
    x, y, w, h = boxes2[0]
    assert 0.0 <= x <= 1.0
    assert 0.0 <= y <= 1.0
    assert w > 0
    assert h > 0


def test_motion_manager_classifies_as_unclassified_when_no_model_detection(monkeypatch):
    service = SimpleNamespace(
        db=SimpleNamespace(
            execute=lambda *args, **kwargs: SimpleNamespace(fetchall=lambda: [])
        )
    )
    settings = SimpleNamespace(models=[], cameras=[])
    camera_hub = SimpleNamespace()
    manager = Mog2MotionInferenceManager(service, settings, camera_hub)

    # Mock detector to return one motion box
    manager.detector = SimpleNamespace(
        detect_motion_boxes=lambda img, cam: [(0.2, 0.2, 0.4, 0.4)]
    )

    test_image = np.zeros((100, 100, 3), dtype=np.uint8)
    observations = manager._process_frame(test_image, "CAM-01")

    assert len(observations) == 1
    assert observations[0]["object_type"] == "UNCLASSIFIED"
    assert observations[0]["attributes"]["motion_type"] == "UNCLASSIFIED"
    assert observations[0]["model_name"] == "opencv-mog2"


def test_motion_manager_attributes_motion_when_model_track_overlaps():
    import json
    # Mock database to return an active HUMAN track at [0.2, 0.2, 0.4, 0.4]
    mock_cursor = SimpleNamespace(
        fetchall=lambda: [
            ("P-123456", "HUMAN", json.dumps([0.2, 0.2, 0.4, 0.4]))
        ]
    )
    service = SimpleNamespace(
        db=SimpleNamespace(execute=lambda *args, **kwargs: mock_cursor)
    )
    settings = SimpleNamespace(models=[], cameras=[])
    camera_hub = SimpleNamespace()
    manager = Mog2MotionInferenceManager(service, settings, camera_hub)

    # Motion box perfectly overlaps the HUMAN track
    manager.detector = SimpleNamespace(
        detect_motion_boxes=lambda img, cam: [(0.2, 0.2, 0.4, 0.4)]
    )

    test_image = np.zeros((100, 100, 3), dtype=np.uint8)
    observations = manager._process_frame(test_image, "CAM-01")

    # Because it correlated with an existing HUMAN track, no UNCLASSIFIED observation is generated
    assert len(observations) == 0


def test_mog2_detector_ignores_minor_flinch():
    # Test that small micro-movements / flinches (below min_area_ratio) are suppressed
    detector = Mog2MotionDetector(history=10, var_threshold=30.0, min_area_ratio=0.005)

    frame1 = np.zeros((200, 200, 3), dtype=np.uint8)
    detector.detect_motion_boxes(frame1, "CAM-01")

    # Frame 2: tiny flinch (only 3x3 pixels = 9 px, which is 0.000225 of 40000 px, well below 0.005 = 200 px)
    frame_flinch = np.zeros((200, 200, 3), dtype=np.uint8)
    frame_flinch[100:103, 100:103] = 255
    boxes_flinch = detector.detect_motion_boxes(frame_flinch, "CAM-01")
    assert len(boxes_flinch) == 0

    # Frame 3: genuine substantial motion (50x50 pixels = 2500 px > 200 px)
    frame_motion = np.zeros((200, 200, 3), dtype=np.uint8)
    frame_motion[75:125, 75:125] = 255
    boxes_motion = detector.detect_motion_boxes(frame_motion, "CAM-01")
    assert len(boxes_motion) > 0


def test_motion_manager_loads_model_parameters():
    service = SimpleNamespace(db=SimpleNamespace())
    settings = SimpleNamespace(
        models=[
            {
                "name": "mog2-motion-detector",
                "mode": "opencv-mog2",
                "enabled": True,
                "classes": ["UNCLASSIFIED"],
                "parameters": {
                    "history": 300,
                    "var_threshold": 32.0,
                    "min_area_ratio": 0.008,
                },
            }
        ],
        cameras=[],
    )
    camera_hub = SimpleNamespace()
    manager = Mog2MotionInferenceManager(service, settings, camera_hub)

    assert manager.detector.history == 300
    assert manager.detector.var_threshold == 32.0
    assert manager.detector.min_area_ratio == 0.008

