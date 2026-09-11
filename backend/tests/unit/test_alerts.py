"""Unit tests for Alert REST API endpoints including Acknowledge All."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.api import router
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService


def test_alerts_acknowledge_all(tmp_path):
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)
    service.seed()

    # Insert test alerts matching the schema
    service.db.execute(
        "INSERT INTO alerts (alert_id, event_id, timestamp, alert_type, severity, status, message, created_at) "
        "VALUES (?, ?, datetime('now'), ?, ?, ?, ?, datetime('now'))",
        ("ALT-001", "EVT-01", "INTRUSION", "CRITICAL", "ACTIVE", "Perimeter breach detected"),
    )
    service.db.execute(
        "INSERT INTO alerts (alert_id, event_id, timestamp, alert_type, severity, status, message, created_at) "
        "VALUES (?, ?, datetime('now'), ?, ?, ?, ?, datetime('now'))",
        ("ALT-002", "EVT-02", "VEHICLE", "HIGH", "ACTIVE", "Unauthorized vehicle"),
    )
    service.db.execute(
        "INSERT INTO alerts (alert_id, event_id, timestamp, alert_type, severity, status, message, created_at) "
        "VALUES (?, ?, datetime('now'), ?, ?, ?, ?, datetime('now'))",
        ("ALT-003", "EVT-03", "SYSTEM", "LOW", "ACKNOWLEDGED", "Camera obstructed"),
    )
    service.db.commit()

    app = FastAPI()
    app.state.helios = service
    app.include_router(router, prefix="/api/v1")

    with TestClient(app) as client:
        # Check active alerts count
        res = client.get("/api/v1/alerts?status=ACTIVE")
        assert res.status_code == 200
        active = res.json()
        assert len(active) == 2

        # Acknowledge single alert via /alerts/{alert_id}/acknowledge
        res = client.post("/api/v1/alerts/ALT-001/acknowledge", json={"operator": "Officer Davis"})
        assert res.status_code == 200
        assert res.json()["status"] == "ACKNOWLEDGED"
        assert res.json()["acknowledged_by"] == "Officer Davis"

        # Verify ALT-001 is acknowledged
        row = service.db.execute("SELECT status, acknowledged_by FROM alerts WHERE alert_id='ALT-001'").fetchone()
        assert row[0] == "ACKNOWLEDGED"
        assert row[1] == "Officer Davis"

        # ALT-002 should still be ACTIVE
        row = service.db.execute("SELECT status FROM alerts WHERE alert_id='ALT-002'").fetchone()
        assert row[0] == "ACTIVE"

        # Now acknowledge all remaining active alerts
        res = client.post("/api/v1/alerts/acknowledge-all", json={"operator": "Commander Miller"})
        assert res.status_code == 200
        assert res.json()["acknowledged_count"] == 1

        # Verify all are now ACKNOWLEDGED
        active_remaining = client.get("/api/v1/alerts?status=ACTIVE").json()
        assert len(active_remaining) == 0

        # Subsequent acknowledge-all should acknowledge 0
        res = client.post("/api/v1/alerts/acknowledge-all", json={"operator": "Commander Miller"})
        assert res.status_code == 200
        assert res.json()["acknowledged_count"] == 0


def test_system_clear_cache(tmp_path):
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)
    service.seed()

    # Insert test evidence and ended track
    service.db.execute(
        "INSERT INTO evidence (evidence_id, event_id, type, storage_reference, timestamp, created_at) "
        "VALUES ('EVD-01', 'EVT-01', 'IMAGE', 'evidence/test.jpg', datetime('now'), datetime('now'))"
    )
    service.db.execute(
        "INSERT INTO tracks (track_id, camera_id, object_type, created_at, last_seen_at, status, average_confidence, ended_at) "
        "VALUES ('TRK-ENDED-1', 'CAM-01', 'HUMAN', datetime('now'), datetime('now'), 'ENDED', 0.9, datetime('now'))"
    )
    service.db.commit()

    app = FastAPI()
    app.state.helios = service
    app.include_router(router, prefix="/api/v1")

    with TestClient(app) as client:
        res = client.post("/api/v1/system/clear-cache")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "cleared"
        assert data["evidence_deleted"] == 1
        assert data["ended_threads_cleared"] == 1

        # Evidence table should now be empty
        assert service.db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0
        # Ended tracks should be cleared
        assert service.db.execute("SELECT COUNT(*) FROM tracks WHERE status = 'ENDED'").fetchone()[0] == 0
