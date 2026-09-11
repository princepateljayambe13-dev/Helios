import pytest
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.ingestion.camera_manager import CameraStreamHub

@pytest.mark.anyio
async def test_camera_hub_lifecycle(tmp_path):
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)
    hub = CameraStreamHub(service, cameras=[])
    await hub.start()
    assert hub._stopping is False
    await hub.stop()
    assert hub._stopping is True
