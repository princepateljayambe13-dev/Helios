"""Unit and pipeline integration tests for the HELIOS Fencing feature."""
import json
import pytest
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.spatial.geometry import box_bottom_center, point_in_polygon
from app.spatial.spatial_engine import SpatialEngine
from app.spatial.zone import Zone


def test_box_bottom_center():
    # Bounding box: [x, y, w, h] = [0.2, 0.3, 0.4, 0.5]
    # Center x: 0.2 + 0.4 / 2 = 0.4
    # Bottom y: 0.3 + 0.5 = 0.8
    bc = box_bottom_center([0.2, 0.3, 0.4, 0.5])
    assert bc == (0.4, 0.8)


def test_point_in_polygon():
    polygon = [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]]
    assert point_in_polygon((0.25, 0.25), polygon) is True
    assert point_in_polygon((0.6, 0.25), polygon) is False
    assert point_in_polygon((0.25, 0.6), polygon) is False


def test_zone_model():
    zone = Zone(
        zone_id="ZONE-01",
        camera_id="CAM-01",
        name="Perimeter Fence",
        zone_type="RESTRICTED",
        geometry=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]],
        enabled=True,
        object_types=["HUMAN"],
    )
    assert zone.contains_point((0.2, 0.2)) is True
    assert zone.contains_point((0.5, 0.5)) is False
    assert zone.applies_to("HUMAN") is True
    assert zone.applies_to("VEHICLE") is False
    assert zone.is_restricted() is True


def test_spatial_engine_debounce_and_single_trigger():
    engine = SpatialEngine(confirmation_frames=2, exit_confirmation_frames=2)
    zone = Zone(
        zone_id="ZONE-TEST",
        camera_id="CAM-01",
        name="Test Zone",
        zone_type="RESTRICTED",
        geometry=[[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
        enabled=True,
        object_types=["HUMAN"],
    )
    engine.add_or_update_zone(zone)

    # Frame 1: Observation is OUTSIDE zone
    # [x, y, w, h] = [0.0, 0.0, 0.1, 0.1] -> bottom-center: (0.05, 0.1) -> OUTSIDE
    obs_outside = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.9,
        "bounding_box": [0.0, 0.0, 0.1, 0.1],
        "timestamp": "2026-09-05T12:00:00Z",
    }
    intrusions = engine.process_observation(obs_outside, track_id="TRK-01")
    assert len(intrusions) == 0

    # Frame 2: Observation moves INSIDE zone (First inside frame - jitter debounce)
    # [x, y, w, h] = [0.4, 0.4, 0.1, 0.1] -> bottom-center: (0.45, 0.5) -> INSIDE
    obs_inside_1 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.92,
        "bounding_box": [0.4, 0.4, 0.1, 0.1],
        "timestamp": "2026-09-05T12:00:01Z",
    }
    intrusions = engine.process_observation(obs_inside_1, track_id="TRK-01")
    # Debounce requires 2 confirmation frames, so first frame inside does NOT trigger!
    assert len(intrusions) == 0

    # Frame 3: Observation remains INSIDE zone (Second consecutive inside frame - confirmed!)
    obs_inside_2 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.93,
        "bounding_box": [0.4, 0.4, 0.1, 0.1],
        "timestamp": "2026-09-05T12:00:02Z",
    }
    intrusions = engine.process_observation(obs_inside_2, track_id="TRK-01")
    assert len(intrusions) == 1
    assert intrusions[0]["direction"] == "OUTSIDE -> INSIDE"
    assert intrusions[0]["zone_id"] == "ZONE-TEST"
    assert intrusions[0]["track_id"] == "TRK-01"

    # Frame 4 & 5: Track remains INSIDE zone - must NOT trigger again (single trigger)
    obs_inside_3 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.94,
        "bounding_box": [0.42, 0.42, 0.1, 0.1],
        "timestamp": "2026-09-05T12:00:03Z",
    }
    intrusions = engine.process_observation(obs_inside_3, track_id="TRK-01")
    assert len(intrusions) == 0

    # Frame 6 & 7: Track moves OUTSIDE zone (Exit confirmed after 2 frames)
    intrusions = engine.process_observation(obs_outside, track_id="TRK-01")
    assert len(intrusions) == 0
    intrusions = engine.process_observation(obs_outside, track_id="TRK-01")
    assert len(intrusions) == 0

    # Frame 8 & 9: Track re-enters INSIDE zone
    intrusions = engine.process_observation(obs_inside_1, track_id="TRK-01")
    assert len(intrusions) == 0  # 1st inside frame debounce
    intrusions = engine.process_observation(obs_inside_2, track_id="TRK-01")
    assert len(intrusions) == 1  # Re-entry triggers new intrusion!


@pytest.mark.anyio
async def test_complete_fencing_pipeline(tmp_path):
    """Test full flow: Draw/Save Zone -> Object Tracking -> OUTSIDE to INSIDE -> INTRUSION Event -> Alert -> Evidence."""
    db_path = tmp_path / "helios_fencing.db"
    evidence_dir = tmp_path / "evidence"
    settings = Settings(
        database_path=db_path,
        evidence_directory=evidence_dir,
        cameras=[{
            "camera_id": "CAM-01",
            "name": "Perimeter East",
            "stream_reference": "",
            "location": "Sector 4",
        }],
        alert_rules=[{
            "rule_id": "intrusion-detected",
            "event_type": "INTRUSION",
            "severity": "HIGH",
            "cooldown_seconds": 5,
        }],
    )

    service = HeliosService(connect(settings.database_path), settings)
    service.seed()

    # 1. Create / Save Zone via Service API
    zone_payload = {
        "zone_id": "ZONE-PERIMETER-1",
        "camera_id": "CAM-01",
        "name": "Restricted Sector A",
        "zone_type": "RESTRICTED",
        "geometry": [[0.3, 0.3], [0.8, 0.3], [0.8, 0.8], [0.3, 0.8]],
        "enabled": True,
        "object_types": ["HUMAN"],
    }
    created_zone = service.create_zone(zone_payload)
    assert created_zone["zone_id"] == "ZONE-PERIMETER-1"
    assert created_zone["enabled"] is True

    # 2. Object starts OUTSIDE the restricted zone
    # [x, y, w, h] = [0.05, 0.05, 0.1, 0.1] -> bottom-center is (0.1, 0.15) outside [0.3, 0.8]
    obs_1 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.90,
        "bounding_box": [0.05, 0.05, 0.1, 0.1],
        "model_name": "yolo26",
        "model_version": "v1",
        "attributes": {"source_track_id": "det:101"},
    }
    res_1 = await service.ingest(obs_1)
    track_id = res_1["track_id"]
    assert track_id is not None
    assert res_1["event"]["event_type"] == "HUMAN_DETECTED"  # initial track birth

    # 3. Object moves INSIDE restricted zone - Frame 1 (debounce frame)
    # [x, y, w, h] = [0.4, 0.4, 0.1, 0.1] -> bottom-center is (0.45, 0.5) inside
    obs_2 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.92,
        "bounding_box": [0.4, 0.4, 0.1, 0.1],
        "model_name": "yolo26",
        "model_version": "v1",
        "attributes": {"source_track_id": "det:101"},
    }
    res_2 = await service.ingest(obs_2)
    assert res_2["event"] is None  # Waiting for debounce confirmation frame

    # 4. Object remains INSIDE restricted zone - Frame 2 (confirmation frame -> INTRUSION triggered!)
    obs_3 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.95,
        "bounding_box": [0.41, 0.41, 0.1, 0.1],
        "model_name": "yolo26",
        "model_version": "v1",
        "attributes": {"source_track_id": "det:101"},
    }
    res_3 = await service.ingest(obs_3)

    # Verify INTRUSION Event
    assert res_3["event"] is not None
    assert res_3["event"]["event_type"] == "INTRUSION"
    assert res_3["event"]["camera_id"] == "CAM-01"
    assert res_3["event"]["zone_id"] == "ZONE-PERIMETER-1"
    assert res_3["event"]["track_id"] == track_id
    assert res_3["event"]["direction"] == "OUTSIDE -> INSIDE"
    assert res_3["event"]["severity"] == "HIGH"

    # Verify Alert generated
    assert res_3["alert"] is not None
    assert res_3["alert"]["alert_type"] == "intrusion-detected"
    assert res_3["alert"]["severity"] == "HIGH"
    assert res_3["alert"]["status"] == "ACTIVE"

    # Verify Evidence recorded
    assert res_3["evidence"] is not None
    assert res_3["evidence"]["event_id"] == res_3["event"]["event_id"]

    # 5. Consecutive inside frame: does NOT repeatedly trigger while inside
    obs_4 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.95,
        "bounding_box": [0.42, 0.42, 0.1, 0.1],
        "model_name": "yolo26",
        "model_version": "v1",
        "attributes": {"source_track_id": "det:101"},
    }
    res_4 = await service.ingest(obs_4)
    assert res_4["event"] is None
    assert res_4["alert"] is None

    # 6. Test Zone Update API (Disable zone)
    updated = service.update_zone("ZONE-PERIMETER-1", {"enabled": False})
    assert updated["enabled"] is False

    # 7. Test Zone Delete API
    deleted = service.delete_zone("ZONE-PERIMETER-1")
    assert deleted is True
    assert service.get_zone("ZONE-PERIMETER-1") is None
