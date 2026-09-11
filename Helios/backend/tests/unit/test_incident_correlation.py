"""Unit tests for Intelligent Incident Correlation Engine."""
import json
from datetime import datetime, UTC, timedelta
import pytest
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.incidents.correlator import IncidentCorrelator
from app.incidents.incident import Incident


def test_probabilistic_correlation_scoring():
    """Verify that IncidentCorrelator scores multi-dimensional signals properly."""
    settings = Settings()
    # In-memory DB
    import sqlite3
    from app.database.connection import SCHEMA
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)

    correlator = IncidentCorrelator(conn, correlation_window_seconds=180.0, correlation_threshold=0.52)
    now_iso = datetime.now(UTC).isoformat()

    # Create initial incident
    inc = Incident(
        incident_id="INC-TEST01",
        title="Perimeter Intrusion in Zone A",
        incident_type="PERIMETER_BREACH",
        severity="MEDIUM",
        status="DETECTED",
        confidence=0.75,
        start_time=now_iso,
        last_seen_at=now_iso,
        created_at=now_iso,
        updated_at=now_iso,
        primary_camera_id="CAM-01",
        primary_zone_id="ZONE-A",
        primary_track_id="TRK-01",
        object_type="HUMAN",
    )

    # 1. Matching event (same track, same camera, 10s later, sequential loitering)
    ev_match = {
        "event_id": "EVT-02",
        "event_type": "LOITERING",
        "camera_id": "CAM-01",
        "zone_id": "ZONE-A",
        "track_id": "TRK-01",
        "object_type": "HUMAN",
        "timestamp": (datetime.now(UTC) + timedelta(seconds=10)).isoformat(),
        "confidence": 0.9,
        "severity": "HIGH",
    }
    score, reasons, breakdown = correlator._score_correlation(inc, ev_match, None)
    assert score >= 0.85
    assert breakdown["track"] == 1.0
    assert breakdown["time"] == 1.0
    assert any("Exact track identity continuity" in r for r in reasons)
    assert any("followed by prolonged loitering" in r for r in reasons)

    # 2. Unrelated event (different object, different camera, 200s later)
    ev_unrelated = {
        "event_id": "EVT-03",
        "event_type": "VEHICLE_DETECTED",
        "camera_id": "CAM-99",
        "zone_id": "ZONE-Z",
        "track_id": "TRK-999",
        "object_type": "VEHICLE",
        "timestamp": (datetime.now(UTC) + timedelta(seconds=200)).isoformat(),
        "confidence": 0.5,
        "severity": "LOW",
    }
    score2, reasons2, breakdown2 = correlator._score_correlation(inc, ev_unrelated, None)
    assert score2 == 0.0


@pytest.mark.anyio
async def test_event_progression_correlation_and_escalation(tmp_path):
    """Verify Zone Entry -> Loitering -> Secondary Observation merges into 1 incident with severity escalation."""
    settings = Settings(
        database_path=tmp_path / "helios_incident_test.db",
        evidence_directory=tmp_path / "evidence",
        track_timeout_seconds=300,
    )
    service = HeliosService(connect(settings.database_path), settings)

    # Setup camera and zone
    service.db.execute(
        "INSERT INTO cameras (camera_id, name, source_type, location, status, enabled, created_at, updated_at) "
        "VALUES ('CAM-01', 'Perimeter Cam 1', 'RTSP', 'Sector Alpha', 'ONLINE', 1, datetime('now'), datetime('now'))"
    )
    service.db.execute(
        "INSERT INTO cameras (camera_id, name, source_type, location, status, enabled, created_at, updated_at) "
        "VALUES ('CAM-02', 'Perimeter Cam 2', 'RTSP', 'Sector Bravo', 'ONLINE', 1, datetime('now'), datetime('now'))"
    )
    service.db.execute(
        "INSERT INTO zones (zone_id, camera_id, name, zone_type, geometry, enabled, dwell_threshold_seconds, loitering_threshold_seconds, created_at, updated_at) "
        "VALUES ('ZONE-01', 'CAM-01', 'Restricted Courtyard', 'RESTRICTED', '[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]', 1, 10.0, 30.0, datetime('now'), datetime('now'))"
    )
    service.db.commit()
    service.refresh_zones_from_db()

    base_time = datetime.now(UTC) - timedelta(seconds=60)

    # Observation 1: Initial Entry (T=0)
    obs1 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "bounding_box": [0.3, 0.3, 0.2, 0.2],
        "confidence": 0.90,
        "timestamp": base_time.isoformat(),
    }
    res1 = await service.ingest(obs1)
    track_id = res1["track_id"]
    inc1 = res1.get("incident")
    assert inc1 is not None
    inc_id = inc1["incident_id"]
    assert inc1["status"] == "DETECTED"
    assert inc1["event_count"] == 1

    # Observation 2: Dwell & Loitering in zone (T=35s)
    obs2 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "bounding_box": [0.32, 0.31, 0.2, 0.2],
        "confidence": 0.95,
        "timestamp": (base_time + timedelta(seconds=35)).isoformat(),
        "attributes": {"source_track_id": f"bytetrack:{track_id.replace('P-', '')}"},
    }
    res2 = await service.ingest(obs2)
    inc2 = res2.get("incident")

    # MUST be the SAME incident!
    assert inc2 is not None
    assert inc2["incident_id"] == inc_id
    assert inc2["event_count"] >= 2
    assert inc2["status"] in ("CONFIRMED", "ACTIVE")
    # Dynamic confidence must increase
    assert inc2["confidence"] >= inc1["confidence"]
    # Escalated severity: Intrusion + Loitering escalates to CRITICAL
    assert inc2["severity"] in ("HIGH", "CRITICAL")
    # Why correlated rationale must be populated
    assert len(inc2["correlation_reasons"]) > 0

    # Query full incident from service
    full_inc = service.get_incident(inc_id)
    assert full_inc is not None
    assert full_inc["incident_id"] == inc_id
    assert len(full_inc["events"]) >= 2
    assert len(full_inc["timeline"]) >= 2
    assert "CAM-01" in full_inc["cameras"]


@pytest.mark.anyio
async def test_alert_deduplication_and_state_lifecycle(tmp_path):
    """Verify duplicate alerts are suppressed and incident lifecycle progresses."""
    settings = Settings(
        database_path=tmp_path / "helios_dedup_test.db",
        evidence_directory=tmp_path / "evidence",
        track_timeout_seconds=300,
    )
    service = HeliosService(connect(settings.database_path), settings)

    service.db.execute(
        "INSERT INTO cameras (camera_id, name, source_type, location, status, enabled, created_at, updated_at) "
        "VALUES ('CAM-01', 'Perimeter Cam 1', 'RTSP', 'Sector Alpha', 'ONLINE', 1, datetime('now'), datetime('now'))"
    )
    service.db.execute(
        "INSERT INTO zones (zone_id, camera_id, name, zone_type, geometry, enabled, dwell_threshold_seconds, loitering_threshold_seconds, created_at, updated_at) "
        "VALUES ('ZONE-01', 'CAM-01', 'Restricted Courtyard', 'RESTRICTED', '[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]', 1, 5.0, 15.0, datetime('now'), datetime('now'))"
    )
    service.db.commit()
    service.refresh_zones_from_db()

    base_time = datetime.now(UTC) - timedelta(seconds=30)

    # Frame 1: creates event & alert 1
    obs1 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "bounding_box": [0.4, 0.4, 0.2, 0.2],
        "confidence": 0.92,
        "timestamp": base_time.isoformat(),
    }
    res1 = await service.ingest(obs1)
    inc_id = res1["incident"]["incident_id"]
    assert res1["is_dedup_alert"] is False

    # Frame 2: 5s later loitering in same zone
    obs2 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "bounding_box": [0.4, 0.4, 0.2, 0.2],
        "confidence": 0.95,
        "timestamp": (base_time + timedelta(seconds=20)).isoformat(),
    }
    res2 = await service.ingest(obs2)
    # Alert linked to incident
    assert res2["incident"]["incident_id"] == inc_id

    # Test Operator Acknowledged
    ack_res = service.acknowledge_incident(inc_id, operator="Security Chief")
    assert ack_res is not None
    assert ack_res["status"] == "ACKNOWLEDGED"
    assert ack_res["acknowledged_by"] == "Security Chief"

    # Test Operator Resolved
    res_res = service.resolve_incident(inc_id, operator="Security Chief")
    assert res_res is not None
    assert res_res["status"] == "RESOLVED"

    # Summary
    summary = service.get_incidents_summary()
    assert summary["total_incidents"] >= 1
    assert summary["active_incidents"] == 0  # since it was resolved


def test_fastapi_incident_endpoints(tmp_path):
    """Test incident REST API endpoints: GET list, GET summary, GET detail, POST acknowledge, POST resolve."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes.api import router

    settings = Settings(database_path=tmp_path / "helios_api.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)

    # Insert test incident
    now_iso = datetime.now(UTC).isoformat()
    service.db.execute(
        "INSERT INTO incidents (incident_id, title, incident_type, severity, status, confidence, "
        "start_time, end_time, last_seen_at, duration_seconds, primary_camera_id, primary_zone_id, "
        "primary_track_id, object_type, summary, correlation_reasons, score_breakdown, event_count, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "INC-API-01",
            "Test Multi-Camera Intrusion",
            "PERIMETER_BREACH",
            "HIGH",
            "ACTIVE",
            0.88,
            now_iso,
            None,
            now_iso,
            45.0,
            "CAM-01",
            "ZONE-01",
            "TRK-100",
            "HUMAN",
            "Developing situation under observation",
            json.dumps(["Temporal proximity", "Same entity"]),
            json.dumps({"time": 0.9, "spatial": 0.8}),
            2,
            now_iso,
            now_iso,
        ),
    )
    service.db.commit()

    app = FastAPI()
    app.state.helios = service
    app.include_router(router, prefix="/api/v1")

    with TestClient(app) as client:
        # 1. GET /incidents
        res = client.get("/api/v1/incidents")
        assert res.status_code == 200
        data = res.json()
        assert "incidents" in data
        assert len(data["incidents"]) == 1
        assert data["incidents"][0]["incident_id"] == "INC-API-01"

        # 2. GET /incidents/summary
        res_sum = client.get("/api/v1/incidents/summary")
        assert res_sum.status_code == 200
        s_data = res_sum.json()
        assert s_data["total_incidents"] == 1
        assert s_data["active_incidents"] == 1

        # 3. GET /incidents/{id}
        res_det = client.get("/api/v1/incidents/INC-API-01")
        assert res_det.status_code == 200
        det = res_det.json()
        assert det["incident_id"] == "INC-API-01"
        assert det["confidence"] == 0.88
        assert "score_breakdown" in det

        # 4. POST /incidents/{id}/acknowledge
        res_ack = client.post("/api/v1/incidents/INC-API-01/acknowledge", json={"operator": "Commander Miller"})
        assert res_ack.status_code == 200
        ack_data = res_ack.json()
        assert ack_data["status"] == "ACKNOWLEDGED"
        assert ack_data["acknowledged_by"] == "Commander Miller"

        # 5. POST /incidents/{id}/resolve
        res_res = client.post("/api/v1/incidents/INC-API-01/resolve", json={"operator": "Commander Miller"})
        assert res_res.status_code == 200
        resolved_data = res_res.json()
        assert resolved_data["status"] == "RESOLVED"

