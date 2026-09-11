import pytest
from datetime import UTC, datetime
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService

def test_camera_crud_and_status(tmp_path):
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)
    
    # Test camera health query on empty db
    health = service.camera_health("CAM-01")
    assert health is None

    # Seed cameras
    settings.cameras = [{"camera_id": "CAM-01", "name": "North Cam", "stream_reference": "http://stream1", "enabled": True}]
    service.seed()

    # Query health
    health = service.camera_health("CAM-01")
    assert health is not None
    assert health["camera_id"] == "CAM-01"
    assert health["stream_configured"] is True

    # Check summary
    summary = service.summary()
    assert summary["cameras"]["total"] == 1
