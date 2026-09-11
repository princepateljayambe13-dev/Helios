from datetime import UTC, datetime

import numpy as np

from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.vision.anpr.plate_detector import PlateEvidenceStore


def test_plate_evidence_clears_the_previous_batch_after_thirty(tmp_path):
    settings=Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service=HeliosService(connect(settings.database_path),settings)
    stamp=datetime.now(UTC).isoformat()
    service.db.execute("INSERT INTO events (event_id,event_type,timestamp,camera_id,severity,status,created_at) VALUES ('EVT-1','LICENSE_PLATE_DETECTED',?,'CAM-01','INFO','OPEN',?)",(stamp,stamp))
    store=PlateEvidenceStore(service); image=np.zeros((100,100,3),dtype=np.uint8)
    for number in range(30): store.save(image,[.1,.1,.5,.2],"EVT-1",f"DET-{number}")
    assert len(list(store.directory.glob("*.jpg")))==30
    store.save(image,[.1,.1,.5,.2],"EVT-1","DET-30")
    assert [file.name for file in store.directory.glob("*.jpg")]==["DET-30.jpg"]
    assert service.db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]==1
