from app.ai.tools import (get_camera_status, get_daily_statistics, get_evidence,
                          get_event, get_event_timeline, get_recent_events,
                          get_related_events, get_track_history, get_zone_activity,
                          search_events, execute_tool)
from tests.unit.conftest import make_event, stamp


def test_get_recent_events_returns_created_events(service):
    make_event(service, object_type="UAV")
    make_event(service, object_type="HUMAN", camera_id="CAM-03")
    result = get_recent_events(service, limit=10)
    assert result["count"] == 2
    assert {event["object_type"] for event in result["events"]} == {"UAV", "HUMAN"}


def test_get_recent_events_filters_and_clamps_limit(service):
    make_event(service, object_type="UAV")
    result = get_recent_events(service, object_type="HUMAN", limit="banana")
    assert result["events"] == []
    result = get_recent_events(service, object_type="UAV", limit=9999)
    assert len(result["events"]) == 1 and result["limit"] == 100


def test_search_events_by_zone(service):
    event = make_event(service, object_type="VEHICLE", zone_id="ZONE-RESTRICTED-01")
    result = search_events(service, zone_id="ZONE-RESTRICTED-01")
    assert result["count"] == 1
    assert result["events"][0]["event_id"] == event["event_id"]


def test_get_event_returns_linked_context(service):
    result = make_event(service, object_type="UAV")
    data = get_event(service, result["event_id"])
    assert data["event"]["event_id"] == result["event_id"]
    assert data["track"]["track_id"] == result["track_id"]
    assert data["camera"]["camera_id"] == "CAM-01"


def test_get_event_unknown_returns_error(service):
    data = get_event(service, "EVT-NOPE")
    assert data["error"] == "event not found"


def test_get_track_history_returns_positions(service):
    result = make_event(service)
    data = get_track_history(service, result["track_id"])
    assert data["track"]["track_id"] == result["track_id"]
    assert data["position_count"] >= 1


def test_get_camera_status_lists_all_and_single(service):
    all_cameras = get_camera_status(service)
    assert all_cameras["count"] == 3
    cam_02 = get_camera_status(service, camera_id="CAM-02")
    assert cam_02["camera"]["status"] == "OFFLINE"
    assert cam_02["health"]["connection"] == "OFFLINE"


def test_get_zone_activity_for_matching_zone(service):
    service.db.execute("INSERT INTO zones (zone_id,camera_id,name,zone_type,geometry,enabled,created_at,updated_at) VALUES (?,?,?,?,?,1,?,?)",
                       ("ZONE-RESTRICTED-01", "CAM-01", "Restricted", "RESTRICTED", "[[0,0],[0,1],[1,1],[1,0]]", stamp(), stamp()))
    service.db.commit()
    make_event(service, object_type="VEHICLE", zone_id="ZONE-RESTRICTED-01")
    zone_result = get_zone_activity(service, "ZONE-RESTRICTED-01")
    assert zone_result["zone"]["zone_id"] == "ZONE-RESTRICTED-01"
    assert zone_result["count"] == 1


def test_get_evidence_excludes_storage_reference(service):
    result = make_event(service)
    service.db.execute("DELETE FROM evidence WHERE event_id=?", (result["event_id"],))
    service.db.execute("INSERT INTO evidence (evidence_id,event_id,type,storage_reference,timestamp,created_at) VALUES (?,?,?,?,?,?)",
                       ("EVD-REAL123456", result["event_id"], "IMAGE", "data/evidence/x.jpg", stamp(), stamp()))
    service.db.commit()
    data = get_evidence(service, event_id=result["event_id"])
    assert data["count"] == 1
    assert data["evidence"][0]["evidence_id"] == "EVD-REAL123456"
    assert "storage_reference" not in data["evidence"][0]


def test_daily_statistics_are_exact(service):
    make_event(service, object_type="UAV")
    make_event(service, object_type="UAV")
    stats = get_daily_statistics(service)
    assert stats["total_events"] >= 2
    by_type = {entry["event_type"]: entry["count"] for entry in stats["events_by_type"]}
    assert by_type.get("UAV_DETECTED", 0) >= 2


def test_get_event_timeline_chronological(service):
    make_event(service, object_type="UAV")
    make_event(service, object_type="HUMAN", camera_id="CAM-03")
    data = get_event_timeline(service)
    assert data["count"] >= 2
    stamps = [entry["timestamp"] for entry in data["entries"]]
    assert stamps == sorted(stamps)


def test_get_related_events(service):
    a = make_event(service, object_type="UAV")
    b = make_event(service, object_type="UAV")
    data = get_related_events(service, a["event_id"], radius_seconds=86400)
    assert any(event["event_id"] == b["event_id"] for event in data["related_events"])


def test_execute_tool_unknown_and_failure_are_safe(service, monkeypatch):
    result = execute_tool(service, "drop_table", {})
    assert "error" in result
    from app.ai.tools import TOOL_FUNCTIONS
    def boom(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setitem(TOOL_FUNCTIONS, "get_recent_events", boom)
    result = execute_tool(service, "get_recent_events", {})
    assert "error" in result
    assert "boom" in result["error"]


def test_get_alerts_and_filtering(service):
    from app.ai.tools import get_alerts
    evt = make_event(service, object_type="HUMAN")
    service.db.execute(
        "INSERT INTO alerts (alert_id, event_id, timestamp, alert_type, severity, status, message, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("ALR-001", evt["event_id"], stamp(), "INTRUSION", "CRITICAL", "ACTIVE", "Perimeter breach detected", stamp()),
    )
    service.db.commit()

    res = get_alerts(service, status="ACTIVE")
    assert res["count"] >= 1
    assert any(a["alert_id"] == "ALR-001" for a in res["alerts"])
    assert res["alerts"][0]["severity"] == "CRITICAL"


def test_list_zones_and_filtering(service):
    from app.ai.tools import list_zones
    service.db.execute(
        "INSERT INTO zones (zone_id, camera_id, name, zone_type, geometry, enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        ("ZONE-NORTH-GATE", "CAM-01", "North Gate Perimeter", "RESTRICTED", "[[0,0],[1,1]]", stamp(), stamp()),
    )
    service.db.commit()

    res = list_zones(service, camera_id="CAM-01")
    assert res["count"] >= 1
    assert any(z["zone_id"] == "ZONE-NORTH-GATE" for z in res["zones"])


def test_get_active_tracks_and_search_evidence(service):
    from app.ai.tools import get_active_tracks, search_evidence
    evt = make_event(service, object_type="VEHICLE")
    service.db.execute(
        "INSERT INTO evidence (evidence_id, event_id, type, storage_reference, timestamp, created_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("EVD-PLATE-01", evt["event_id"], "PLATE_READ", "plate.jpg", stamp(), stamp(), '{"plate_number": "KA-01-AB-1234"}'),
    )
    service.db.commit()

    res_ev = search_evidence(service, query="KA-01")
    assert res_ev["count"] >= 1
    assert res_ev["evidence"][0]["evidence_id"] == "EVD-PLATE-01"

    res_tracks = get_active_tracks(service, object_type="VEHICLE")
    assert isinstance(res_tracks["active_tracks"], list)


def test_system_overview_and_logs(service):
    from app.ai.tools import get_system_overview, get_system_logs
    service.db.execute(
        "INSERT INTO system_logs (log_id, timestamp, level, component, message) "
        "VALUES (?, ?, ?, ?, ?)",
        ("LOG-001", stamp(), "INFO", "pipeline", "Surveillance pipeline operational"),
    )
    service.db.commit()

    overview = get_system_overview(service)
    assert overview["cameras_total"] >= 1
    assert "online_cameras" in overview

    logs = get_system_logs(service, level="INFO")
    assert logs["count"] >= 1
    assert any(l["log_id"] == "LOG-001" for l in logs["logs"])