import asyncio
from datetime import UTC, datetime

from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService


def test_camera_recovery_resolves_its_active_offline_alert(tmp_path):
    service = HeliosService(connect(tmp_path / "helios.db"), Settings(database_path=tmp_path / "helios.db", alert_rules=[{"rule_id":"camera-offline", "event_type":"CAMERA_OFFLINE", "severity":"MEDIUM"}]))
    stamp = datetime.now(UTC).isoformat()
    service.db.execute("INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)", ("CAM-02", "Camera", "RTSP", "rtsp://test", "Test", stamp, stamp))
    asyncio.run(service.camera_status("CAM-02", "OFFLINE"))
    assert service.db.execute("SELECT status FROM alerts").fetchone()[0] == "ACTIVE"
    asyncio.run(service.camera_status("CAM-02", "ONLINE"))
    assert service.db.execute("SELECT status FROM alerts").fetchone()[0] == "RESOLVED"
