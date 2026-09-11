import pytest
from datetime import UTC, datetime
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.tracking.face_association import (
    calculate_face_human_overlap,
    find_matching_human_track,
    find_matching_face_track,
)


def test_calculate_face_human_overlap_upper_body():
    """Face inside upper 25% of human body should produce a strong match."""
    human_box = [0.40, 0.20, 0.20, 0.60]  # x=0.40..0.60, y=0.20..0.80
    face_box = [0.45, 0.22, 0.08, 0.10]   # center at (0.49, 0.27), inside top section

    result = calculate_face_human_overlap(face_box, human_box)
    assert result["is_match"] is True
    assert result["score"] >= 0.70
    assert result["containment"] == pytest.approx(1.0)


def test_calculate_face_human_overlap_rejection():
    """Face outside human or near feet should be rejected."""
    human_box = [0.40, 0.20, 0.20, 0.60]

    # Face near feet (y=0.72)
    feet_face = [0.45, 0.70, 0.08, 0.10]
    res_feet = calculate_face_human_overlap(feet_face, human_box)
    assert res_feet["is_match"] is False

    # Face totally separated horizontally
    other_face = [0.80, 0.22, 0.08, 0.10]
    res_other = calculate_face_human_overlap(other_face, human_box)
    assert res_other["is_match"] is False


def test_find_matching_human_track():
    active_humans = [
        {"track_id": "#P-001", "current_position": [0.10, 0.20, 0.15, 0.50]},
        {"track_id": "#P-002", "current_position": [0.50, 0.10, 0.20, 0.65]},
    ]
    face_on_p2 = [0.55, 0.12, 0.08, 0.10]

    matched, score = find_matching_human_track(face_on_p2, active_humans)
    assert matched is not None
    assert matched["track_id"] == "#P-002"
    assert score > 0.75


@pytest.mark.anyio
async def test_human_face_ingestion_bidirectional_association(tmp_path):
    """Test full pipeline: Ingest human, then face. Verify parent_track_id, attributes, and thread timeline."""
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)

    # 1. Ingest Human observation
    human_obs = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.92,
        "bounding_box": [0.40, 0.20, 0.20, 0.60],
        "model_name": "yolo26s",
        "model_version": "1.0",
        "attributes": {},
    }
    r_human = await service.ingest(human_obs)
    human_track_id = r_human["track_id"]
    assert human_track_id.startswith("#P-")

    # 2. Ingest Face observation overlapping upper body of human
    face_obs = {
        "camera_id": "CAM-01",
        "object_type": "FACE",
        "confidence": 0.88,
        "bounding_box": [0.45, 0.22, 0.08, 0.10],
        "model_name": "roboflow-face-workflow",
        "model_version": "1.0",
        "attributes": {},
    }
    r_face = await service.ingest(face_obs)
    face_track_id = r_face["track_id"]
    assert face_track_id.startswith("#F-")

    # 3. Check database record for face track
    face_row = service.db.execute("SELECT * FROM tracks WHERE track_id=?", (face_track_id,)).fetchone()
    assert face_row["parent_track_id"] == human_track_id

    # 4. Check track thread for human
    human_thread = service.get_track_thread(human_track_id)
    assert human_thread is not None
    assert human_thread["face_intel"] is not None
    assert human_thread["face_intel"]["has_face"] is True
    assert human_thread["face_intel"]["face_track_id"] == face_track_id

    # Verify timeline has FACE_ASSOCIATION node
    face_nodes = [n for n in human_thread["timeline"] if n.get("node_type") == "FACE_ASSOCIATION"]
    assert len(face_nodes) == 1
    assert face_nodes[0]["associated_track_id"] == face_track_id
    assert "Facial signature" in face_nodes[0]["detail"]

    # Verify activity narrative mentions face link
    assert face_track_id in human_thread["activity_story"]

    # 5. Check track thread for face
    face_thread = service.get_track_thread(face_track_id)
    assert face_thread is not None
    assert face_thread["parent_track_id"] == human_track_id
    human_nodes = [n for n in face_thread["timeline"] if n.get("node_type") == "HUMAN_ASSOCIATION"]
    assert len(human_nodes) == 1
    assert human_nodes[0]["associated_track_id"] == human_track_id


@pytest.mark.anyio
async def test_face_first_then_human_association(tmp_path):
    """Test reverse arrival order: Face is detected first, then Human detector runs."""
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)

    # 1. Ingest Face first
    face_obs = {
        "camera_id": "CAM-02",
        "object_type": "FACE",
        "confidence": 0.85,
        "bounding_box": [0.30, 0.15, 0.07, 0.09],
        "model_name": "roboflow-face-workflow",
        "model_version": "1.0",
        "attributes": {},
    }
    r_face = await service.ingest(face_obs)
    face_track_id = r_face["track_id"]

    # 2. Ingest Human that encloses the face
    human_obs = {
        "camera_id": "CAM-02",
        "object_type": "HUMAN",
        "confidence": 0.91,
        "bounding_box": [0.26, 0.13, 0.16, 0.55],
        "model_name": "yolo26s",
        "model_version": "1.0",
        "attributes": {},
    }
    r_human = await service.ingest(human_obs)
    human_track_id = r_human["track_id"]

    # 3. Verify linkage occurred
    face_row = service.db.execute("SELECT * FROM tracks WHERE track_id=?", (face_track_id,)).fetchone()
    assert face_row["parent_track_id"] == human_track_id

    human_thread = service.get_track_thread(human_track_id)
    assert human_thread["associated_face_id"] == face_track_id
