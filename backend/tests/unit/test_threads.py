import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, load_settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from main import app


def test_helios_service_threads(tmp_path):
    db = connect(tmp_path / "test.db")
    settings = Settings(database_path=tmp_path / "test.db")
    service = HeliosService(db, settings)

    service.db.execute(
        "INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)",
        ("CAM-01", "Gate", "RTSP", "rtsp://gate", "Gate", datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat())
    )
    obs = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.95,
        "bounding_box": [0.1, 0.2, 0.3, 0.4],
        "model_name": "human-detector",
        "model_version": "v1",
        "attributes": {"source_track_id": "h:1"}
    }
    ingested = asyncio.run(service.ingest(obs))
    track_id = ingested["track_id"]

    # Ingest a second observation for the same track
    asyncio.run(service.ingest({**obs, "bounding_box": [0.12, 0.22, 0.3, 0.4]}))

    threads = service.get_all_threads(limit=10)
    assert len(threads) == 1
    thread = threads[0]
    assert thread["track_id"] == track_id
    assert thread["object_type"] == "HUMAN"
    assert thread["camera_id"] == "CAM-01"
    assert thread["positions_count"] >= 2
    assert len(thread["timeline"]) >= 1
    assert thread["timeline"][0]["node_type"] == "CAMERA_DETECTION"

    # Specific track thread
    single = service.get_track_thread(track_id)
    assert single is not None
    assert single["track_id"] == track_id

    # Filter by object_type
    vehicle_threads = service.get_all_threads(limit=10, object_type="VEHICLE")
    assert len(vehicle_threads) == 0

    human_threads = service.get_all_threads(limit=10, object_type="HUMAN")
    assert len(human_threads) == 1


def test_api_threads_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/v1/threads")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            import urllib.parse
            track_id = data[0]["track_id"]
            track_res = client.get(f"/api/v1/threads/{urllib.parse.quote(track_id)}")
            assert track_res.status_code == 200
            assert track_res.json()["track_id"] == track_id

        del_res = client.delete("/api/v1/threads/ended")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "cleared"


def test_clear_ended_threads_service(tmp_path):
    db = connect(tmp_path / "test_clear.db")
    settings = Settings(database_path=tmp_path / "test_clear.db")
    service = HeliosService(db, settings)

    now_iso = datetime.now(UTC).isoformat()
    # Insert one ACTIVE and one ENDED track
    service.db.execute(
        "INSERT INTO tracks (track_id,camera_id,object_type,created_at,last_seen_at,status,average_confidence,current_position,source_track_id,ended_at,detection_count,max_confidence,event_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("T-ACTIVE", "CAM-01", "HUMAN", now_iso, now_iso, "ACTIVE", 0.9, None, None, None, 5, 0.95, None)
    )
    service.db.execute(
        "INSERT INTO tracks (track_id,camera_id,object_type,created_at,last_seen_at,status,average_confidence,current_position,source_track_id,ended_at,detection_count,max_confidence,event_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("T-ENDED", "CAM-01", "VEHICLE", now_iso, now_iso, "ENDED", 0.85, None, None, now_iso, 3, 0.9, None)
    )
    service.db.execute("INSERT INTO track_positions VALUES (?,?,?,?)", ("T-ENDED", now_iso, "[0,0,10,10]", 0.85))
    service.db.commit()

    all_threads = service.get_all_threads(limit=10)
    assert len(all_threads) == 2

    res = service.clear_ended_threads()
    assert res["cleared_count"] == 1

    remaining = service.get_all_threads(limit=10)
    assert len(remaining) == 1
    assert remaining[0]["track_id"] == "T-ACTIVE"

