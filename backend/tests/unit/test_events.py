import pytest
from datetime import UTC, datetime
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService

@pytest.mark.anyio
async def test_audio_event_and_alert_generation(tmp_path):
    settings = Settings(
        database_path=tmp_path / "helios.db",
        evidence_directory=tmp_path / "evidence",
        alert_rules=[{"rule_id": "explosion-like", "event_type": "EXPLOSION_LIKE_DETECTED", "severity": "CRITICAL", "cooldown_seconds": 30}]
    )
    service = HeliosService(connect(settings.database_path), settings)

    payload = {
        "source_id": "AUDIO-01",
        "event_type": "EXPLOSION_LIKE",
        "confidence": 0.92,
        "evidence_reference": "audio/clip1.wav"
    }
    res = await service.ingest_audio(payload)
    assert res["event"]["event_type"] == "EXPLOSION_LIKE_DETECTED"
    assert res["alert"] is not None
    assert res["alert"]["severity"] == "CRITICAL"

    # Now clear events and linked alerts
    cleared = service.clear_events(clear_alerts=True)
    assert cleared["events_cleared"] == 1
    assert cleared["alerts_cleared"] == 1
    assert service.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert service.db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0

