"""Unit and integration tests for Live People Density & Count in HELIOS Perimeter Fencing."""
import json
import pytest
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService


@pytest.fixture
def service_setup(tmp_path):
    db_path = tmp_path / "test_density.db"
    evidence_dir = tmp_path / "evidence"
    settings = Settings(
        database_path=db_path,
        evidence_directory=evidence_dir,
        cameras=[
            {
                "camera_id": "CAM-01",
                "name": "North Perimeter",
                "stream_reference": "",
                "location": "North gate",
            },
            {
                "camera_id": "CAM-02",
                "name": "Main Checkpoint",
                "stream_reference": "",
                "location": "Main entrance",
            },
        ],
        zones=[
            {
                "zone_id": "ZONE-GATE-01",
                "camera_id": "CAM-01",
                "name": "Gate Area",
                "zone_type": "MONITORED",
                "geometry": [[0.1, 0.1], [0.6, 0.1], [0.6, 0.6], [0.1, 0.6]],
                "enabled": True,
                "object_types": ["HUMAN"],
            },
            {
                "zone_id": "ZONE-RESTRICTED-01",
                "camera_id": "CAM-01",
                "name": "Perimeter Restricted Wall",
                "zone_type": "RESTRICTED",
                "geometry": [[0.7, 0.7], [0.9, 0.7], [0.9, 0.9], [0.7, 0.9]],
                "enabled": True,
                "object_types": ["HUMAN"],
            },
        ],
        alert_rules=[
            {
                "rule_id": "intrusion-detected",
                "event_type": "INTRUSION",
                "severity": "HIGH",
                "cooldown_seconds": 5,
            }
        ],
    )
    svc = HeliosService(connect(settings.database_path), settings)
    svc.seed()
    return svc


@pytest.mark.anyio
async def test_live_people_count_in_monitored_zone(service_setup):
    service = service_setup

    # Initially empty
    densities = service.get_live_people_density(camera_id="CAM-01")
    assert len(densities) == 1
    gate_data = densities[0]
    assert gate_data["zone_id"] == "ZONE-GATE-01"
    assert gate_data["zone_name"] == "Gate Area"
    assert gate_data["people_count"] == 0
    assert gate_data["density_status"] == "CLEAR"
    assert gate_data["is_anomaly"] is False
    assert gate_data["tracked_people"] == []

    # Ingest Person 1 inside Gate Area ([x, y, w, h] = [0.2, 0.2, 0.1, 0.2] -> bottom-center: (0.25, 0.40) inside)
    obs_p1 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.95,
        "bounding_box": [0.2, 0.2, 0.1, 0.2],
        "attributes": {"source_track_id": "det-p1"},
    }
    await service.ingest(obs_p1)

    densities = service.get_live_people_density(camera_id="CAM-01")
    assert len(densities) == 1
    gate_data = densities[0]
    assert gate_data["people_count"] == 1
    assert gate_data["density_status"] == "LOW"
    assert len(gate_data["tracked_people"]) == 1

    # Ingest Person 2 inside Gate Area ([x, y, w, h] = [0.3, 0.3, 0.1, 0.2] -> bottom-center: (0.35, 0.50) inside)
    obs_p2 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.94,
        "bounding_box": [0.3, 0.3, 0.1, 0.2],
        "attributes": {"source_track_id": "det-p2"},
    }
    await service.ingest(obs_p2)

    densities = service.get_live_people_density(camera_id="CAM-01")
    gate_data = densities[0]
    assert gate_data["people_count"] == 2
    assert gate_data["density_status"] == "LOW"
    assert len(gate_data["tracked_people"]) == 2

    # Ingest Person 3 OUTSIDE Gate Area ([x, y, w, h] = [0.8, 0.1, 0.1, 0.1] -> bottom-center: (0.85, 0.20) outside)
    obs_p3_outside = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.92,
        "bounding_box": [0.8, 0.1, 0.1, 0.1],
        "attributes": {"source_track_id": "det-p3"},
    }
    await service.ingest(obs_p3_outside)

    # Gate Area count must remain 2!
    densities = service.get_live_people_density(camera_id="CAM-01")
    assert densities[0]["people_count"] == 2

    # Ingest VEHICLE inside Gate Area ([x, y, w, h] = [0.2, 0.2, 0.2, 0.2])
    obs_veh = {
        "camera_id": "CAM-01",
        "object_type": "VEHICLE",
        "confidence": 0.98,
        "bounding_box": [0.2, 0.2, 0.2, 0.2],
        "attributes": {"source_track_id": "det-veh-1"},
    }
    await service.ingest(obs_veh)

    # Gate Area people count must strictly remain 2 (only humans counted)
    densities = service.get_live_people_density(camera_id="CAM-01")
    assert densities[0]["people_count"] == 2


@pytest.mark.anyio
async def test_monitored_zone_does_not_trigger_intrusion_alerts(service_setup):
    service = service_setup

    # Ingest human outside then inside MONITORED zone
    obs_outside = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.94,
        "bounding_box": [0.8, 0.1, 0.1, 0.1],
        "attributes": {"source_track_id": "det-monitored-test"},
    }
    await service.ingest(obs_outside)

    obs_inside_1 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.96,
        "bounding_box": [0.3, 0.3, 0.1, 0.2],
        "attributes": {"source_track_id": "det-monitored-test"},
    }
    res_1 = await service.ingest(obs_inside_1)
    assert res_1["event"] is None
    assert res_1["alert"] is None

    obs_inside_2 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.97,
        "bounding_box": [0.31, 0.31, 0.1, 0.2],
        "attributes": {"source_track_id": "det-monitored-test"},
    }
    res_2 = await service.ingest(obs_inside_2)

    # Must NOT produce INTRUSION alert because zone is MONITORED, not RESTRICTED!
    assert res_2["event"] is None or res_2["event"]["event_type"] != "INTRUSION"
    assert res_2["alert"] is None


@pytest.mark.anyio
async def test_density_anomaly_detection(service_setup):
    service = service_setup

    # Ingest 8 people into Gate Area to trigger threshold
    # Explicitly configure zone capacity to 6
    service.update_zone("ZONE-GATE-01", {"capacity": 6})

    for i in range(1, 9):
        obs = {
            "camera_id": "CAM-01",
            "object_type": "HUMAN",
            "confidence": 0.95,
            "bounding_box": [0.2 + (i * 0.03), 0.2 + (i * 0.03), 0.05, 0.15],
            "attributes": {"source_track_id": f"crowd-person-{i}"},
        }
        await service.ingest(obs)

    densities = service.get_live_people_density(zone_id="ZONE-GATE-01")
    assert len(densities) == 1
    gate_data = densities[0]
    assert gate_data["people_count"] == 8
    assert gate_data["capacity"] == 6
    assert gate_data["density_status"] == "OVERCROWDED"
    assert gate_data["is_anomaly"] is True
    assert "Crowd surge detected" in gate_data["anomaly_description"]


@pytest.mark.anyio
async def test_live_only_stale_track_expiration(service_setup):
    service = service_setup

    # Ingest person inside Gate Area
    obs = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.95,
        "bounding_box": [0.25, 0.25, 0.1, 0.2],
        "attributes": {"source_track_id": "person-will-expire"},
    }
    res = await service.ingest(obs)
    track_id = res["track_id"]

    densities = service.get_live_people_density(zone_id="ZONE-GATE-01")
    assert densities[0]["people_count"] == 1

    # Simulate track expiring (e.g. status changed to ENDED)
    service.db.execute("UPDATE tracks SET status='ENDED' WHERE track_id=?", (track_id,))
    service.db.commit()

    # Query again: must be 0 because it is LIVE ONLY!
    densities_after = service.get_live_people_density(zone_id="ZONE-GATE-01")
    assert densities_after[0]["people_count"] == 0
    assert densities_after[0]["density_status"] == "CLEAR"


def test_zones_density_fastapi_endpoints(service_setup):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes.api import router

    service = service_setup
    app = FastAPI()
    app.state.helios = service
    app.include_router(router, prefix="/api/v1")

    with TestClient(app) as client:
        # 1. Get all densities
        res = client.get("/api/v1/zones/density")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["zone_name"] == "Gate Area"
        assert data[0]["people_count"] == 0

        # 2. Filter by camera_id
        res_cam = client.get("/api/v1/zones/density?camera_id=CAM-01")
        assert res_cam.status_code == 200
        assert len(res_cam.json()) >= 1

        # 3. Get single zone density
        res_single = client.get("/api/v1/zones/ZONE-GATE-01/density")
        assert res_single.status_code == 200
        single_data = res_single.json()
        assert single_data["zone_id"] == "ZONE-GATE-01"
        assert single_data["density_status"] == "CLEAR"

        # 4. Non-existent zone density
        res_404 = client.get("/api/v1/zones/NONEXISTENT/density")
        assert res_404.status_code == 404
