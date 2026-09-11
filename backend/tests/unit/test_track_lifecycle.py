import asyncio
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService


def test_one_event_is_created_and_closed_for_a_bytetrack_lifecycle(tmp_path):
    service = HeliosService(connect(tmp_path / "helios.db"), Settings(database_path=tmp_path / "helios.db", track_timeout_seconds=1))
    service.db.execute("INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)", ("CAM-01", "Test", "RTSP", "rtsp://test", "Test", datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()))
    observation = {"camera_id":"CAM-01", "object_type":"HUMAN", "confidence":.9, "bounding_box":[.1,.2,.3,.4], "model_name":"human-detector", "model_version":"yolo26s", "attributes":{"source_track_id":"human-detector:7"}}

    first = asyncio.run(service.ingest(observation.copy()))
    asyncio.run(service.ingest({**observation, "confidence":.8, "bounding_box":[.12,.2,.3,.4]}))

    assert service.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    track = service.db.execute("SELECT * FROM tracks WHERE track_id=?", (first["track_id"],)).fetchone()
    service.db.execute("UPDATE tracks SET last_seen_at=? WHERE track_id=?", ((datetime.now(UTC)-timedelta(seconds=2)).isoformat(), track["track_id"]))
    assert service.expire_stale_tracks() == 1
    event = service.db.execute("SELECT * FROM events WHERE event_id=?", (track["event_id"],)).fetchone()
    assert event["status"] == "CLOSED"
    assert event["duration_seconds"] is not None
