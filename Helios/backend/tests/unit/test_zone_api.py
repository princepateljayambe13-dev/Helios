"""Unit tests for Zone REST API endpoints."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.api import router
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService


def test_zone_api_crud(tmp_path):
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)
    settings.cameras = [{"camera_id": "CAM-01", "name": "Main Entrance", "stream_reference": "http://stream1", "enabled": True}]
    service.seed()

    app = FastAPI()
    app.state.helios = service
    app.include_router(router, prefix="/api/v1")

    with TestClient(app) as client:
        # 1. Initially zones list is empty
        res = client.get("/api/v1/zones")
        assert res.status_code == 200
        assert res.json() == []

        # 2. Create a new zone
        payload = {
            "zone_id": "ZONE-GATE-1",
            "camera_id": "CAM-01",
            "name": "Gate Barrier Zone",
            "zone_type": "RESTRICTED",
            "geometry": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]],
            "enabled": True,
            "object_types": ["HUMAN", "VEHICLE"],
        }
        res = client.post("/api/v1/zones", json=payload)
        assert res.status_code == 201
        created = res.json()
        assert created["zone_id"] == "ZONE-GATE-1"
        assert created["name"] == "Gate Barrier Zone"
        assert created["object_types"] == ["HUMAN", "VEHICLE"]

        # 3. Get zones filtered by camera
        res = client.get("/api/v1/zones?camera_id=CAM-01")
        assert res.status_code == 200
        zones = res.json()
        assert len(zones) == 1
        assert zones[0]["zone_id"] == "ZONE-GATE-1"

        # 4. Get specific zone
        res = client.get("/api/v1/zones/ZONE-GATE-1")
        assert res.status_code == 200
        assert res.json()["zone_id"] == "ZONE-GATE-1"

        # 5. Update zone (change name and disabled)
        update_payload = {"name": "Gate Barrier Secured", "enabled": False}
        res = client.put("/api/v1/zones/ZONE-GATE-1", json=update_payload)
        assert res.status_code == 200
        updated = res.json()
        assert updated["name"] == "Gate Barrier Secured"
        assert updated["enabled"] is False

        # 6. Delete zone
        res = client.delete("/api/v1/zones/ZONE-GATE-1")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"

        # 7. Verify deletion
        res = client.get("/api/v1/zones/ZONE-GATE-1")
        assert res.status_code == 404
