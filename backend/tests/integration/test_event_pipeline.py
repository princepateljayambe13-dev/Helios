import pytest
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService

@pytest.mark.anyio
async def test_event_ingestion_and_query_flow(tmp_path):
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)
    
    obs = {
        "camera_id": "CAM-01",
        "object_type": "VEHICLE",
        "confidence": 0.95,
        "bounding_box": [0.2, 0.2, 0.3, 0.3],
        "model_name": "vehicle-detector",
        "model_version": "1.0",
        "attributes": {"source_track_id": "detector:201"}
    }
    result = await service.ingest(obs)
    assert result["event_id"] is not None
    
    summary = service.summary()
    assert summary["cameras"]["total"] == 0
