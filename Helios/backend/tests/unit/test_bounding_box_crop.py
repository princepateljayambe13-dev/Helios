import asyncio
from datetime import UTC, datetime
from pathlib import Path
import cv2
import numpy as np
import pytest
from app.core.config import Settings
from app.database.connection import connect
from app.ingestion.camera_manager import CameraStreamHub
from app.ingestion.frame import Frame
from app.services.helios_service import HeliosService
from app.vision.observation import crop_bounding_box_jpeg


def test_crop_bounding_box_jpeg_dimensions():
    # 200 high x 400 wide image
    image = np.zeros((200, 400, 3), dtype=np.uint8)
    image[40:120, 80:240] = [0, 255, 0]  # Green box: y in [40, 120] (h=80), x in [80, 240] (w=160)

    # Normalized bbox: x=80/400=0.2, y=40/200=0.2, w=160/400=0.4, h=80/200=0.4
    bbox = [0.2, 0.2, 0.4, 0.4]
    jpeg_bytes = crop_bounding_box_jpeg(image, bbox)
    assert jpeg_bytes is not None

    decoded = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[0] == 80   # Height cropped to person bbox
    assert decoded.shape[1] == 160  # Width cropped to person bbox


def test_crop_bounding_box_clamping_and_fallback():
    image = np.zeros((100, 100, 3), dtype=np.uint8)

    # Box with coordinates exceeding boundaries
    bbox = [-0.1, -0.1, 1.5, 1.5]
    jpeg_bytes = crop_bounding_box_jpeg(image, bbox)
    assert jpeg_bytes is not None

    # No bbox falls back to full image
    fallback_bytes = crop_bounding_box_jpeg(image, None)
    assert fallback_bytes is not None

    # None image returns None
    assert crop_bounding_box_jpeg(None, bbox) is None


def test_camera_hub_get_snapshot_jpeg_with_crop(tmp_path):
    db = connect(tmp_path / "test.db")
    settings = Settings(database_path=tmp_path / "test.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(db, settings)

    hub = CameraStreamHub(service, [{"camera_id": "CAM-01", "enabled": True, "stream_reference": "rtsp://mock"}])
    assert service.camera_hub is hub

    # Seed mock frame (300 x 300)
    image = np.zeros((300, 300, 3), dtype=np.uint8)
    _, full_jpeg = cv2.imencode(".jpg", image)
    hub.latest["CAM-01"] = Frame.create("CAM-01", image, 1, full_jpeg.tobytes())

    # Snapshot without bbox -> returns full frame
    full_snap = hub.get_snapshot_jpeg("CAM-01")
    assert full_snap == full_jpeg.tobytes()

    # Snapshot with bbox -> returns cropped frame
    crop_snap = hub.get_snapshot_jpeg("CAM-01", bounding_box=[0.1, 0.1, 0.5, 0.5])
    assert crop_snap is not None
    decoded = cv2.imdecode(np.frombuffer(crop_snap, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[0] == 150
    assert decoded.shape[1] == 150


def test_service_ingest_captures_cropped_evidence(tmp_path):
    db = connect(tmp_path / "test.db")
    evidence_dir = tmp_path / "evidence"
    settings = Settings(database_path=tmp_path / "test.db", evidence_directory=evidence_dir)
    service = HeliosService(db, settings)

    service.db.execute(
        "INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)",
        ("CAM-01", "Gate", "RTSP", "rtsp://gate", "Gate", datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat())
    )

    # 400 high x 600 wide synthetic camera frame
    full_image = np.zeros((400, 600, 3), dtype=np.uint8)

    # Person detected in bounding box: x=0.25 (150px), y=0.1 (40px), w=0.2 (120px), h=0.6 (240px)
    obs = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.95,
        "bounding_box": [0.25, 0.1, 0.2, 0.6],
        "model_name": "human-detector",
        "model_version": "yolo26s",
        "attributes": {"source_track_id": "h:1"},
        "image": full_image,  # Attached from YOLO inference
    }

    result = asyncio.run(service.ingest(obs))
    evidence = result["evidence"]
    assert evidence is not None

    evidence_file = evidence_dir / f"{evidence['evidence_id']}.jpg"
    assert evidence_file.exists()

    saved_crop = cv2.imread(str(evidence_file))
    assert saved_crop is not None
    # Verify the saved image is cropped to the person's bbox (240 x 120), NOT the whole frame (400 x 600)
    assert saved_crop.shape[0] == 240
    assert saved_crop.shape[1] == 120
