"""Unit tests for Facial Recognition REST API endpoints."""
import base64
import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.api import router
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService


@pytest.fixture
def api_client(tmp_path):
    db_path = tmp_path / "helios.db"
    evidence_dir = tmp_path / "evidence"
    settings = Settings(database_path=db_path, evidence_directory=evidence_dir)
    settings.cameras = [{"camera_id": "CAM-01", "name": "Main Gate", "stream_reference": "rtsp://mock", "enabled": True}]
    conn = connect(db_path)
    service = HeliosService(conn, settings)
    service.seed()

    app = FastAPI()
    app.state.helios = service
    app.include_router(router, prefix="/api/v1")

    with TestClient(app) as client:
        yield client, service, tmp_path


def make_b64_image(color_val: int = 120) -> str:
    img = np.full((100, 100, 3), color_val, dtype=np.uint8)
    img[20:40, 20:40] = 0
    img[20:40, 60:80] = 0
    _, enc = cv2.imencode(".jpg", img)
    return "data:image/jpeg;base64," + base64.b64encode(enc.tobytes()).decode("utf-8")


def test_face_api_crud_and_association(api_client):
    client, service, _ = api_client

    # 1. Summary starts at 0
    res = client.get("/api/v1/faces/summary")
    assert res.status_code == 200
    assert res.json()["total_recognitions"] == 0
    assert res.json()["registered_persons_count"] == 0

    # 2. Register a person via JSON with base64 image
    reg_payload = {
        "name": "Sarah Connor",
        "person_id": "PER-SARAH",
        "role": "Security Specialist",
        "notes": "Access level 5",
        "image_base64": make_b64_image(150),
    }
    reg_res = client.post("/api/v1/faces/persons", json=reg_payload)
    assert reg_res.status_code == 201
    assert reg_res.json()["person"]["person_id"] == "PER-SARAH"

    # 3. List registered persons
    persons_res = client.get("/api/v1/faces/persons")
    assert persons_res.status_code == 200
    assert len(persons_res.json()) == 1
    assert persons_res.json()[0]["name"] == "Sarah Connor"

    # 4. Ingest an unclassified face observation
    full_frame = np.full((300, 300, 3), 50, dtype=np.uint8)
    service.db.execute(
        """INSERT INTO face_recognitions (
            recognition_id, track_id, camera_id, person_id, person_name, status,
            similarity, confidence, bounding_box, snapshot_path, first_seen, last_seen,
            detection_count, embedding, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "FAC-TEST-001",
            "#F-123",
            "CAM-01",
            None,
            "Unclassified",
            "UNCLASSIFIED",
            0.15,
            0.88,
            "[0.1, 0.1, 0.3, 0.3]",
            "/api/v1/faces/snapshots/FAC-TEST-001.jpg",
            "2026-09-09T12:00:00Z",
            "2026-09-09T12:00:00Z",
            1,
            None,
            "2026-09-09T12:00:00Z",
            "2026-09-09T12:00:00Z",
        ),
    )
    service.db.commit()

    # 5. List recognitions with filters
    rec_res = client.get("/api/v1/faces/recognitions?status=UNCLASSIFIED")
    assert rec_res.status_code == 200
    assert len(rec_res.json()) == 1
    assert rec_res.json()[0]["recognition_id"] == "FAC-TEST-001"

    # 6. Associate unclassified face with Sarah Connor
    assoc_res = client.post(
        "/api/v1/faces/recognitions/FAC-TEST-001/associate",
        json={"person_id": "PER-SARAH"},
    )
    assert assoc_res.status_code == 200
    assert assoc_res.json()["recognition"]["status"] == "RECOGNIZED"
    assert assoc_res.json()["recognition"]["person_name"] == "Sarah Connor"

    # 7. Verify recognition details endpoint
    detail_res = client.get("/api/v1/faces/recognitions/FAC-TEST-001")
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] == "RECOGNIZED"

    # 8. Delete registered person
    del_res = client.delete("/api/v1/faces/persons/PER-SARAH")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # 9. Clear recognitions
    clear_res = client.delete("/api/v1/faces/clear")
    assert clear_res.status_code == 200
    assert clear_res.json()["deleted"] >= 1
