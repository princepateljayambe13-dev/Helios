import pytest
import numpy as np
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.vision.anpr.plate_detector import PlateEvidenceStore

def test_evidence_store_saving(tmp_path):
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)
    
    store = PlateEvidenceStore(service)
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    crop_path = store.save(image, [0.1, 0.1, 0.5, 0.5], "EVT-100", "DET-100")
    assert crop_path is not None
    assert (tmp_path / "evidence" / "anpr" / "DET-100.jpg").exists()

def test_evidence_cache_limit_30(tmp_path):
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)
    for i in range(40):
        service.record_evidence(f"EVT-{i}", "SNAPSHOT")
    rows = service.db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    assert rows == 30

