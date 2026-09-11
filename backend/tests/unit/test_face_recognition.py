"""Unit tests for FaceRecognitionManager: detection, recognition, database persistence, and association."""
import json
import numpy as np
import pytest
import cv2
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.vision.face.recognition_manager import FaceRecognitionManager


def create_test_face_image(color_val: int = 150) -> np.ndarray:
    """Create a 160x160 synthetic face image with recognizable patterns."""
    img = np.full((160, 160, 3), color_val, dtype=np.uint8)
    # Eyes
    img[40:60, 35:60] = [20, 20, 20]
    img[40:60, 100:125] = [20, 20, 20]
    # Nose
    img[70:95, 75:85] = [200, 200, 200]
    # Mouth
    img[115:130, 50:110] = [220, 60, 60]
    return img


@pytest.fixture
def test_env(tmp_path):
    db_path = tmp_path / "helios.db"
    evidence_dir = tmp_path / "evidence"
    settings = Settings(database_path=db_path, evidence_directory=evidence_dir)
    settings.cameras = [{"camera_id": "CAM-01", "name": "Front Door", "stream_reference": "rtsp://mock", "enabled": True}]
    conn = connect(db_path)
    service = HeliosService(conn, settings)
    service.seed()
    return service, settings, tmp_path


def test_register_person_and_persistence(test_env):
    service, settings, _ = test_env
    mgr = service.face_recognition_manager

    face_img = create_test_face_image(140)
    _, encoded = cv2.imencode(".jpg", face_img)
    img_bytes = encoded.tobytes()

    person = mgr.register_person(
        name="Alice Walker",
        person_id="PER-001",
        role="Director of Operations",
        notes="Authorized high-security clearance",
        image_bytes=img_bytes,
    )

    assert person["person_id"] == "PER-001"
    assert person["name"] == "Alice Walker"

    # Verify database persistence
    db_row = service.db.execute("SELECT * FROM registered_faces WHERE person_id='PER-001'").fetchone()
    assert db_row is not None
    assert db_row["name"] == "Alice Walker"
    assert db_row["role"] == "Director of Operations"

    emb = json.loads(db_row["embedding"])
    assert len(emb) == 512

    # Verify summary
    summary = mgr.get_summary()
    assert summary["registered_persons_count"] == 1


@pytest.mark.anyio
async def test_unclassified_face_detection_and_later_association(test_env):
    service, settings, _ = test_env
    mgr = service.face_recognition_manager

    # 1. Ingest an unknown/unregistered face observation
    face_img = create_test_face_image(90)
    full_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Place face at normalized bbox: x=0.2, y=0.2, w=0.25, h=0.33
    full_frame[96:256, 128:288] = face_img

    obs = {
        "camera_id": "CAM-01",
        "object_type": "FACE",
        "confidence": 0.92,
        "bounding_box": [0.20, 0.20, 0.25, 0.33],
        "image": full_frame,
        "model_name": "yolo-face-detector",
    }

    res = await service.ingest(obs)
    track_id = res["track_id"]
    assert track_id.startswith("#F-")

    # 2. Verify face recognition record was created as UNCLASSIFIED
    rec_rows = mgr.get_recognitions(status="UNCLASSIFIED")
    assert len(rec_rows) >= 1
    unclassified_rec = rec_rows[0]
    assert unclassified_rec["status"] == "UNCLASSIFIED"
    assert unclassified_rec["person_name"] == "Unclassified"
    assert unclassified_rec["camera_id"] == "CAM-01"
    assert unclassified_rec["detection_count"] == 1
    assert unclassified_rec["snapshot_path"].startswith("/api/v1/faces/snapshots/")
    rec_id = unclassified_rec["recognition_id"]

    # 3. Associate unclassified face with a person later
    assoc_res = mgr.associate_unclassified_face(
        recognition_id=rec_id,
        name="Bob Vance",
        role="Facility Inspector",
        notes="Assigned to gate area",
    )

    assert assoc_res["status"] == "RECOGNIZED"
    assert assoc_res["person_name"] == "Bob Vance"
    assert assoc_res["person_id"].startswith("PER-")

    # 4. Verify database reflects association
    db_rec = service.db.execute("SELECT * FROM face_recognitions WHERE recognition_id=?", (rec_id,)).fetchone()
    assert db_rec["status"] == "RECOGNIZED"
    assert db_rec["person_name"] == "Bob Vance"

    # Verify registered_faces table has Bob Vance
    new_person = service.db.execute("SELECT * FROM registered_faces WHERE person_id=?", (db_rec["person_id"],)).fetchone()
    assert new_person is not None
    assert new_person["name"] == "Bob Vance"


@pytest.mark.anyio
async def test_recognized_face_detection_flow(test_env):
    service, settings, _ = test_env
    mgr = service.face_recognition_manager

    # 1. Register Charlie
    face_img = create_test_face_image(180)
    _, encoded = cv2.imencode(".jpg", face_img)
    mgr.register_person(
        name="Charlie Brown",
        person_id="PER-007",
        role="Lead Analyst",
        image_bytes=encoded.tobytes(),
    )

    # 2. Ingest matching face observation
    full_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    full_frame[100:260, 150:310] = face_img

    obs = {
        "camera_id": "CAM-01",
        "object_type": "FACE",
        "confidence": 0.95,
        "bounding_box": [0.23, 0.21, 0.25, 0.33],
        "image": full_frame,
        "model_name": "yolo-face-detector",
    }

    res = await service.ingest(obs)
    face_intel = res.get("face_recognition")
    assert face_intel is not None
    assert face_intel["status"] == "RECOGNIZED"
    assert face_intel["person_id"] == "PER-007"
    assert face_intel["person_name"] == "Charlie Brown"
    assert face_intel["similarity"] >= 0.60

    # 3. Verify rate limiting / debounce: Ingest second frame for same track
    res2 = await service.ingest(obs)
    # Detection count should increment without failing or running unneeded re-extractions
    updated_rec = mgr.get_recognition(face_intel["recognition_id"])
    assert updated_rec["detection_count"] >= 2
