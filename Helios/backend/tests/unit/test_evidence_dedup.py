import asyncio
from datetime import UTC, datetime
from pathlib import Path
import pytest
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService


def test_record_evidence_deduplication(tmp_path):
    db = connect(tmp_path / "test.db")
    settings = Settings(database_path=tmp_path / "test.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(db, settings)

    # First capture for EVT-1
    ev1 = service.record_evidence("EVT-1", "SNAPSHOT")
    assert ev1 is not None
    assert ev1["event_id"] == "EVT-1"

    # Second capture call for the same EVT-1
    ev2 = service.record_evidence("EVT-1", "SNAPSHOT")
    assert ev2["evidence_id"] == ev1["evidence_id"]

    # Verify database has strictly 1 evidence record for EVT-1
    count = service.db.execute("SELECT COUNT(*) FROM evidence WHERE event_id='EVT-1'").fetchone()[0]
    assert count == 1


def test_ingest_evidence_only_for_detections_and_single_capture(tmp_path):
    db = connect(tmp_path / "test.db")
    settings = Settings(database_path=tmp_path / "test.db", evidence_directory=tmp_path / "evidence")
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

    # First observation (is_new = True) -> creates event and 1 evidence capture
    res1 = asyncio.run(service.ingest(obs))
    assert res1["evidence"] is not None
    evt_id = res1["event"]["event_id"]

    # Ingest 10 more frames for the same continuous track (is_new = False)
    for i in range(10):
        res_sub = asyncio.run(service.ingest({
            **obs,
            "bounding_box": [0.1 + i * 0.01, 0.2, 0.3, 0.4]
        }))
        assert res_sub["evidence"] is None

    # Verify only 1 evidence record exists for this detection
    count = service.db.execute("SELECT COUNT(*) FROM evidence WHERE event_id=?", (evt_id,)).fetchone()[0]
    assert count == 1

    # Audio ingestion should not create evidence captures
    audio_res = asyncio.run(service.ingest_audio({
        "source_id": "MIC-01",
        "event_type": "GUNSHOT",
        "confidence": 0.98
    }))
    assert audio_res["evidence"] is None
    audio_evt_id = audio_res["event"]["event_id"]
    audio_ev_count = service.db.execute("SELECT COUNT(*) FROM evidence WHERE event_id=?", (audio_evt_id,)).fetchone()[0]
    assert audio_ev_count == 0


def test_threads_positions_optimization(tmp_path):
    db = connect(tmp_path / "test.db")
    settings = Settings(database_path=tmp_path / "test.db")
    service = HeliosService(db, settings)

    service.db.execute(
        "INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)",
        ("CAM-01", "Gate", "RTSP", "rtsp://gate", "Gate", datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat())
    )

    obs = {
        "camera_id": "CAM-01",
        "object_type": "VEHICLE",
        "confidence": 0.92,
        "bounding_box": [0.2, 0.2, 0.4, 0.4],
        "model_name": "vehicle-detector",
        "model_version": "v1",
        "attributes": {"source_track_id": "v:1"}
    }
    ingested = asyncio.run(service.ingest(obs))
    track_id = ingested["track_id"]

    # Ingest 5 positions
    for i in range(5):
        asyncio.run(service.ingest({**obs, "bounding_box": [0.2 + i * 0.01, 0.2, 0.4, 0.4]}))

    # In get_all_threads, include_positions=False -> positions is empty list, positions_count accurate
    all_threads = service.get_all_threads(limit=10)
    assert len(all_threads) == 1
    assert all_threads[0]["positions"] == []
    assert all_threads[0]["positions_count"] >= 5

    # In get_track_thread, include_positions=True -> positions has full list
    single = service.get_track_thread(track_id, include_positions=True)
    assert len(single["positions"]) >= 5
    assert single["positions_count"] == len(single["positions"])
