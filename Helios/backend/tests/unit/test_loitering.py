import json
import pytest
from app.spatial.zone import Zone
from app.spatial.spatial_engine import SpatialEngine
from app.services.helios_service import HeliosService
from app.core.config import Settings


def test_zone_threshold_defaults_and_customization():
    zone = Zone(
        zone_id="ZONE-TEST-1",
        camera_id="CAM-01",
        name="Main Gate Area",
        geometry=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    )
    # Default dwell is 20s, loitering is 50s
    assert zone.dwell_threshold_seconds == 20.0
    assert zone.loitering_threshold_seconds == 50.0

    # Custom thresholds
    custom_zone = Zone.from_dict({
        "zone_id": "ZONE-CUSTOM",
        "camera_id": "CAM-01",
        "name": "Custom Secure Sector",
        "geometry": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        "dwell_threshold_seconds": 15.0,
        "loitering_threshold_seconds": 45.0,
    })
    assert custom_zone.dwell_threshold_seconds == 15.0
    assert custom_zone.loitering_threshold_seconds == 45.0
    assert custom_zone.to_dict()["dwell_threshold_seconds"] == 15.0
    assert custom_zone.to_dict()["loitering_threshold_seconds"] == 45.0


def test_stationary_object_progression_normal_dwelling_loitering():
    engine = SpatialEngine(confirmation_frames=1, exit_confirmation_frames=1)
    zone = Zone(
        zone_id="ZONE-ALPHA",
        camera_id="CAM-01",
        name="Restricted Courtyard",
        geometry=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        dwell_threshold_seconds=20.0,
        loitering_threshold_seconds=50.0,
    )
    engine.add_or_update_zone(zone)

    # Frame 1: Entry at t = 100.0 (OUTSIDE -> INSIDE)
    obs1 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "bounding_box": [0.4, 0.4, 0.2, 0.2],
        "confidence": 0.95,
        "timestamp": 100.0,
    }
    events = engine.process_observation(obs1, track_id="TRK-01", movement_state="STATIONARY")
    assert any(e["event_type"] == "INTRUSION" for e in events)

    state = engine.track_states[("CAM-01", "TRK-01", "ZONE-ALPHA")]
    assert state.status == "INSIDE"
    assert state.loitering_status == "NORMAL"

    # Frame 2: t = 110.0 (10s elapsed, under 20s dwell threshold)
    obs2 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "bounding_box": [0.4, 0.4, 0.2, 0.2],
        "confidence": 0.95,
        "timestamp": 110.0,
    }
    engine.process_observation(obs2, track_id="TRK-01", movement_state="STATIONARY")
    assert state.loitering_status == "NORMAL"
    assert state.stationary_duration == 10.0

    # Frame 3: t = 125.0 (25s elapsed, >= 20s -> DWELLING)
    obs3 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "bounding_box": [0.4, 0.4, 0.2, 0.2],
        "confidence": 0.95,
        "timestamp": 125.0,
    }
    engine.process_observation(obs3, track_id="TRK-01", movement_state="STATIONARY")
    assert state.loitering_status == "DWELLING"
    assert state.stationary_duration == 25.0

    # Check active dwell tracks method
    dwell_tracks = engine.get_active_dwell_tracks("CAM-01")
    assert len(dwell_tracks) == 1
    assert dwell_tracks[0]["track_id"] == "TRK-01"
    assert dwell_tracks[0]["loitering_status"] == "DWELLING"
    assert dwell_tracks[0]["stationary_duration"] == 25.0

    # Frame 4: t = 155.0 (55s elapsed, >= 50s -> LOITERING!)
    obs4 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "bounding_box": [0.4, 0.4, 0.2, 0.2],
        "confidence": 0.95,
        "timestamp": 155.0,
    }
    events4 = engine.process_observation(obs4, track_id="TRK-01", movement_state="STATIONARY")
    assert state.loitering_status == "LOITERING"
    loitering_events = [e for e in events4 if e["event_type"] == "LOITERING"]
    assert len(loitering_events) == 1
    loit = loitering_events[0]
    assert loit["track_id"] == "TRK-01"
    assert loit["zone_id"] == "ZONE-ALPHA"
    assert loit["duration_seconds"] == 55.0
    assert loit["movement_state"] == "STATIONARY"


def test_continuously_moving_object_not_flagged_as_loitering():
    engine = SpatialEngine(confirmation_frames=1, exit_confirmation_frames=1)
    zone = Zone(
        zone_id="ZONE-BETA",
        camera_id="CAM-01",
        name="Walkway Sector",
        geometry=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        dwell_threshold_seconds=20.0,
        loitering_threshold_seconds=50.0,
    )
    engine.add_or_update_zone(zone)

    # Object actively walking through over 60 seconds
    for t in [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0]:
        obs = {
            "camera_id": "CAM-01",
            "object_type": "HUMAN",
            "bounding_box": [0.2 + (t - 100) * 0.005, 0.5, 0.1, 0.2],
            "confidence": 0.92,
            "timestamp": t,
        }
        events = engine.process_observation(obs, track_id="TRK-WALKER", movement_state="WALKING")
        # Moving objects must NEVER trigger a LOITERING event
        assert not any(e["event_type"] == "LOITERING" for e in events)

    state = engine.track_states[("CAM-01", "TRK-WALKER", "ZONE-BETA")]
    # Status should remain NORMAL, never LOITERING
    assert state.loitering_status == "NORMAL"
    assert state.stationary_duration < 10.0


@pytest.mark.anyio
async def test_helios_service_loitering_alert_and_evidence(tmp_path):
    settings = Settings(
        database_path=tmp_path / "helios_test.db",
        evidence_directory=tmp_path / "evidence",
        track_timeout_seconds=120,
    )
    from app.database.connection import connect
    service = HeliosService(connect(settings.database_path), settings)
    service.db.execute(
        "INSERT INTO cameras (camera_id, name, source_type, location, status, enabled, created_at, updated_at) "
        "VALUES ('CAM-01', 'Perimeter Cam', 'RTSP', 'Sector 1', 'READY', 1, datetime('now'), datetime('now'))"
    )
    service.db.execute(
        "INSERT INTO zones (zone_id, camera_id, name, zone_type, geometry, enabled, dwell_threshold_seconds, loitering_threshold_seconds, created_at, updated_at) "
        "VALUES ('ZONE-01', 'CAM-01', 'Secure Yard', 'RESTRICTED', '[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]', 1, 20.0, 50.0, datetime('now'), datetime('now'))"
    )
    service.db.commit()
    service.refresh_zones_from_db()

    from datetime import datetime, UTC, timedelta
    base_time = datetime.now(UTC) - timedelta(seconds=80)

    # Stream frames every 10 seconds up to 65s (exceeding 50s loitering threshold)
    for sec in [0, 10, 20, 30, 40, 50, 60, 65]:
        stamp = (base_time + timedelta(seconds=sec)).isoformat()
        obs = {
            "camera_id": "CAM-01",
            "object_type": "HUMAN",
            "bounding_box": [0.4, 0.4, 0.2, 0.2],
            "confidence": 0.95,
            "timestamp": stamp,
        }
        await service.ingest(obs)

    # Verify event generated
    loit_events = service.db.execute("SELECT * FROM events WHERE event_type='LOITERING'").fetchall()
    assert len(loit_events) >= 1
    evt = loit_events[0]
    assert evt["zone_id"] == "ZONE-01"
    assert evt["severity"] == "HIGH"
    assert "Loitering alert" in evt["description"]

    # Verify alert triggered
    loit_alerts = service.db.execute("SELECT * FROM alerts WHERE alert_type='loitering-detected'").fetchall()
    assert len(loit_alerts) >= 1

    # Verify loitering session saved
    sessions = service.db.execute("SELECT * FROM loitering_sessions WHERE zone_id='ZONE-01'").fetchall()
    assert len(sessions) >= 1
    assert sessions[0]["status"] == "LOITERING"
    assert sessions[0]["duration_seconds"] >= 50.0

    # Test update_zone_thresholds
    up_res = service.update_zone_thresholds("ZONE-01", dwell_seconds=15.0, loitering_seconds=40.0)
    assert up_res["dwell_threshold_seconds"] == 15.0
    assert up_res["loitering_threshold_seconds"] == 40.0
    z_row = service.db.execute("SELECT dwell_threshold_seconds, loitering_threshold_seconds FROM zones WHERE zone_id='ZONE-01'").fetchone()
    assert z_row["dwell_threshold_seconds"] == 15.0
    assert z_row["loitering_threshold_seconds"] == 40.0
