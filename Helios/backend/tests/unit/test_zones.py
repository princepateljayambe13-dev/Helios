import pytest
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService

@pytest.mark.anyio
async def test_restricted_zone_entry_event(tmp_path):
    settings = Settings(
        database_path=tmp_path / "helios.db",
        evidence_directory=tmp_path / "evidence",
        zones=[{
            "zone_id": "ZONE-01",
            "camera_id": "CAM-01",
            "name": "Restricted Area",
            "zone_type": "RESTRICTED",
            "geometry": [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]],
            "enabled": True
        }]
    )
    service = HeliosService(connect(settings.database_path), settings)
    service.seed()

    # Observation inside restricted zone
    obs = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.9,
        "bounding_box": [0.1, 0.1, 0.1, 0.1],
        "model_name": "human-detector",
        "model_version": "1.0",
        "attributes": {}
    }
    result = await service.ingest(obs)
    assert result["event"] is not None
    assert result["event"]["event_type"] == "RESTRICTED_ZONE_ENTRY"
    assert result["event"]["severity"] == "HIGH"
