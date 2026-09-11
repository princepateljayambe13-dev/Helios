import asyncio
from datetime import UTC, datetime
from pathlib import Path
import numpy as np
import pytest

from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.vision.vehicle_intelligence import (
    VehicleClassifier,
    VehicleColorClassifier,
    VehicleColorDetector,
    TrackColorStabilizer,
    VehicleIntelligencePipeline,
)


def test_vehicle_intelligence_end_to_end_flow(tmp_path):
    db_path = tmp_path / "test_vehicle.db"
    db = connect(db_path)
    settings = Settings(database_path=db_path, evidence_directory=tmp_path / "evidence")

    # Mock CLIP classifier that identifies "sedan" with 0.84 confidence
    def mock_clip(image, candidate_labels, hypothesis_template):
        return [
            {"label": "sedan", "score": 0.84},
            {"label": "SUV", "score": 0.10},
        ]

    classifier = VehicleClassifier(pipeline_instance=mock_clip)
    color_detector = VehicleColorDetector()
    pipeline = VehicleIntelligencePipeline(classifier=classifier, color_detector=color_detector)

    service = HeliosService(db, settings, vehicle_pipeline=pipeline)

    # Seed cameras & restricted zone
    now_iso = datetime.now(UTC).isoformat()
    service.db.execute(
        "INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)",
        ("CAM-01", "North Gate", "RTSP", "rtsp://camera", "Perimeter", now_iso, now_iso),
    )
    service.db.commit()

    # Create synthetic frame with a blue car at bbox [0.2, 0.2, 0.4, 0.4]
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    frame[40:120, 40:120] = (220, 40, 20)  # BGR blue

    observation = {
        "camera_id": "CAM-01",
        "object_type": "VEHICLE",
        "confidence": 0.92,
        "bounding_box": [0.2, 0.2, 0.4, 0.4],
        "image": frame,
        "model_name": "yolo26s",
        "model_version": "v1",
        "attributes": {
            "source_class": "car",
            "source_track_id": "yolo:42",
        },
    }

    # Run ingest
    result = asyncio.run(service.ingest(observation))

    # 1. Check detection result
    track_id = result["track_id"]
    event = result["event"]
    evidence = result["evidence"]
    alert = result["alert"]

    assert track_id.startswith("#V-")

    # 2. Check track record and thread view in database
    track_row = service.db.execute("SELECT * FROM tracks WHERE track_id=?", (track_id,)).fetchone()
    assert track_row is not None
    assert track_row["object_type"] == "VEHICLE"
    from app.services.helios_service import item
    det_row = service.db.execute("SELECT * FROM detections WHERE track_id=?", (track_id,)).fetchone()
    assert det_row is not None
    det_item = item(det_row)
    v_intel = det_item["attributes"]["vehicle_intelligence"]
    assert v_intel["vehicle_id"] == track_id.lstrip("#")
    assert v_intel["type"] == "sedan"
    assert v_intel["type_confidence"] == 0.84
    assert v_intel["color"] == "blue"
    assert v_intel["color_confidence"] >= 0.70

    # Verify thread view joins vehicle intelligence
    thread = service.get_track_thread(track_id)
    assert thread is not None
    assert thread["vehicle_intelligence"]["type"] == "sedan"
    assert thread["vehicle_intelligence"]["color"] == "blue"

    # 3. Check event record in database
    assert event is not None
    assert "Sedan detected" in event["description"]
    assert "Blue" in event["description"]
    event_item = item(service.db.execute("SELECT * FROM events WHERE event_id=?", (event["event_id"],)).fetchone())
    assert event_item["attributes"]["vehicle_intelligence"]["type"] == "sedan"
    assert event_item["attributes"]["vehicle_intelligence"]["color"] == "blue"

    # 4. Check evidence record in database
    assert evidence is not None
    evidence_item = item(service.db.execute("SELECT * FROM evidence WHERE evidence_id=?", (evidence["evidence_id"],)).fetchone())
    assert evidence_item.get("metadata") is not None
    assert evidence_item["metadata"]["vehicle_intelligence"]["type"] == "sedan"
    assert evidence_item["metadata"]["vehicle_intelligence"]["color"] == "blue"

    # 5. Check activity thread story reconstruction
    thread = service.get_track_thread(track_id)
    assert thread is not None
    assert thread["vehicle_intelligence"]["type"] == "sedan"
    assert thread["vehicle_intelligence"]["color"] == "blue"
    initial_node = thread["timeline"][0]
    assert "Sedan" in initial_node["title"]
    assert "Blue" in initial_node["title"]


def test_vehicle_intelligence_graceful_without_clip(tmp_path):
    db_path = tmp_path / "test_dormant.db"
    db = connect(db_path)
    settings = Settings(database_path=db_path, evidence_directory=tmp_path / "evidence")

    # Dormant CLIP classifier (transformers not installed / None pipeline)
    classifier = VehicleClassifier(pipeline_instance=False)
    color_classifier = VehicleColorClassifier(pipeline_instance=False)
    color_detector = VehicleColorDetector()
    pipeline = VehicleIntelligencePipeline(
        classifier=classifier,
        color_classifier=color_classifier,
        color_detector=color_detector,
    )

    service = HeliosService(db, settings, vehicle_pipeline=pipeline)

    now_iso = datetime.now(UTC).isoformat()
    service.db.execute(
        "INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)",
        ("CAM-01", "South Gate", "RTSP", "rtsp://camera", "Perimeter", now_iso, now_iso),
    )
    service.db.commit()

    # Red vehicle frame
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[:, :] = (20, 20, 220)  # BGR red

    observation = {
        "camera_id": "CAM-01",
        "object_type": "VEHICLE",
        "confidence": 0.88,
        "bounding_box": [0.1, 0.1, 0.8, 0.8],
        "image": frame,
        "model_name": "yolo26s",
        "model_version": "v1",
        "attributes": {"source_class": "truck"},
    }

    result = asyncio.run(service.ingest(observation))
    from app.services.helios_service import item
    det_item = item(service.db.execute("SELECT * FROM detections WHERE track_id=?", (result["track_id"],)).fetchone())
    vi = det_item["attributes"]["vehicle_intelligence"]

    # CLIP is dormant, so type is None, but OpenCV color detection ran successfully
    assert vi["type"] is None
    assert vi["type_confidence"] is None
    assert vi["color"] == "red"
    assert vi["color_confidence"] >= 0.70

    thread = service.get_track_thread(result["track_id"])
    assert thread is not None
    assert thread["vehicle_intelligence"]["color"] == "red"

    # Event description reflects color
    event_item = item(service.db.execute("SELECT * FROM events WHERE event_id=?", (result["event"]["event_id"],)).fetchone())
    assert event_item["description"] == "Red Vehicle detected"


def test_vehicle_pipeline_multi_frame_temporal_smoothing_and_cache(tmp_path):
    """Test that multiple video frames for the same track use temporal stabilization and avoid flickering."""
    db_path = tmp_path / "test_smoothing.db"
    db = connect(db_path)
    settings = Settings(database_path=db_path, evidence_directory=tmp_path / "evidence")

    # Counter to verify how many times classifier actually executed
    call_counts = {"type": 0, "color": 0}

    def counting_type_pipeline(image, candidate_labels, hypothesis_template):
        call_counts["type"] += 1
        return [{"label": "SUV", "score": 0.88}]

    def counting_color_pipeline(image, candidate_labels):
        call_counts["color"] += 1
        return [
            {"label": "a photo of a silver vehicle", "score": 0.82},
            {"label": "a photo of a gray vehicle", "score": 0.10},
        ]

    classifier = VehicleClassifier(pipeline_instance=counting_type_pipeline)
    color_classifier = VehicleColorClassifier(pipeline_instance=counting_color_pipeline)
    stabilizer = TrackColorStabilizer(alpha=0.35, min_interval_seconds=0.10)
    pipeline = VehicleIntelligencePipeline(
        classifier=classifier,
        color_classifier=color_classifier,
        stabilizer=stabilizer,
    )

    service = HeliosService(db, settings, vehicle_pipeline=pipeline)

    now_iso = datetime.now(UTC).isoformat()
    service.db.execute(
        "INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)",
        ("CAM-02", "East Entrance", "RTSP", "rtsp://camera", "Gate", now_iso, now_iso),
    )
    service.db.commit()

    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # Frame 1: new vehicle track
    res1 = asyncio.run(service.ingest({
        "camera_id": "CAM-02",
        "object_type": "VEHICLE",
        "confidence": 0.90,
        "bounding_box": [0.1, 0.1, 0.5, 0.5],
        "image": frame,
        "model_name": "yolo26s",
        "model_version": "v1",
        "attributes": {"source_track_id": "yolo:999"},
    }))

    track_id = res1["track_id"]
    from app.services.helios_service import item
    det1 = item(service.db.execute("SELECT * FROM detections WHERE track_id=?", (track_id,)).fetchone())
    vi1 = det1["attributes"]["vehicle_intelligence"]
    assert vi1["type"] == "suv"
    assert vi1["color"] == "silver"
    assert call_counts["color"] == 1

    # Frame 2: same vehicle 10ms later (high-speed stream)
    # Stabilizer fast-path should return cached stabilized state without blocking
    res2 = asyncio.run(service.ingest({
        "camera_id": "CAM-02",
        "object_type": "VEHICLE",
        "confidence": 0.92,
        "bounding_box": [0.12, 0.11, 0.5, 0.5],
        "image": frame,
        "model_name": "yolo26s",
        "model_version": "v1",
        "attributes": {"source_track_id": "yolo:999"},
    }))

    assert res2["track_id"] == track_id
    det2 = item(service.db.execute("SELECT * FROM detections WHERE track_id=? ORDER BY timestamp DESC", (track_id,)).fetchone())
    vi2 = det2["attributes"]["vehicle_intelligence"]
    assert vi2["type"] == "suv"
    assert vi2["color"] == "silver"
    # Call count should still be 1 because rapid consecutive frame hit the fast-path!
    assert call_counts["color"] == 1

