"""Registered backend tools that give Gemini controlled read-only access to HELIOS data.

Every tool executes against the existing ``HeliosService``/database layer. The AI
model is never handed SQL, Python, shell, filesystem, or network capabilities.
"""
from __future__ import annotations
from datetime import UTC, datetime
from typing import Any, Callable

from app.services.helios_service import item


def _rows(cursor) -> list[dict[str, Any]]:
    return [item(row) for row in cursor.fetchall()]


def _limit(value: Any, default: int = 20, minimum: int = 1, maximum: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    if len(value) == 10 and value[4:5] == "-" and value[7:8] == "-":
        return value + "T00:00:00"
    if "Z" not in value.upper() and "+" not in value:
        return value + "Z"
    return value


def get_recent_events(helios, camera_id: Any = None, object_type: Any = None, severity: Any = None, limit: Any = 20) -> dict[str, Any]:
    query = "SELECT event_id,event_type,timestamp,camera_id,zone_id,severity,status,confidence,description,object_type FROM events WHERE 1=1"
    args: list[Any] = []
    if camera_id:
        query += " AND camera_id=?"
        args.append(str(camera_id))
    if object_type:
        query += " AND object_type=?"
        args.append(str(object_type).upper())
    if severity:
        query += " AND severity=?"
        args.append(str(severity).upper())
    limit = _limit(limit)
    events = _rows(helios.db.execute(query + " ORDER BY timestamp DESC LIMIT ?", [*args, limit]))
    return {"events": events, "count": len(events), "limit": limit}


def search_events(helios, event_type: Any = None, camera_id: Any = None, zone_id: Any = None,
                  since: Any = None, until: Any = None, limit: Any = 50) -> dict[str, Any]:
    query = "SELECT * FROM events WHERE 1=1"
    args: list[Any] = []
    if event_type:
        query += " AND event_type=?"
        args.append(str(event_type).upper())
    if camera_id:
        query += " AND camera_id=?"
        args.append(str(camera_id))
    if zone_id:
        query += " AND zone_id=?"
        args.append(str(zone_id))
    since, until = _iso(since), _iso(until)
    if since:
        query += " AND timestamp>=?"
        args.append(since)
    if until:
        query += " AND timestamp<=?"
        args.append(until)
    limit = _limit(limit, 50)
    events = _rows(helios.db.execute(query + " ORDER BY timestamp DESC LIMIT ?", [*args, limit]))
    return {"events": events, "count": len(events), "limit": limit}


def get_event(helios, event_id: str) -> dict[str, Any]:
    event = item(helios.db.execute("SELECT * FROM events WHERE event_id=?", (str(event_id),)).fetchone())
    if not event:
        return {"error": "event not found", "event_id": str(event_id)}
    track = None
    if event.get("track_id"):
        track = item(helios.db.execute("SELECT * FROM tracks WHERE track_id=?", (event["track_id"],)).fetchone())
    camera = item(helios.db.execute(
        "SELECT camera_id,name,source_type,location,status,enabled FROM cameras WHERE camera_id=?",
        (event.get("camera_id", ""),)).fetchone())
    zone = item(helios.db.execute(
        "SELECT zone_id,camera_id,name,zone_type,enabled FROM zones WHERE zone_id=?",
        (event.get("zone_id", ""),)).fetchone())
    evidence = _rows(helios.db.execute(
        "SELECT evidence_id,event_id,type,timestamp,integrity_hash,metadata FROM evidence WHERE event_id=? ORDER BY timestamp",
        (str(event_id),)))
    return {"event": event, "track": track, "camera": camera, "zone": zone, "evidence": evidence}


def get_track_history(helios, track_id: str) -> dict[str, Any]:
    track = item(helios.db.execute("SELECT * FROM tracks WHERE track_id=?", (str(track_id),)).fetchone())
    if not track:
        return {"error": "track not found", "track_id": str(track_id)}
    positions = _rows(helios.db.execute(
        "SELECT track_id,timestamp,bounding_box,confidence FROM track_positions WHERE track_id=? ORDER BY timestamp",
        (str(track_id),)))
    return {"track": track, "positions": positions, "position_count": len(positions)}


def get_zone_activity(helios, zone_id: str, since: Any = None, until: Any = None, limit: Any = 50) -> dict[str, Any]:
    zone = item(helios.db.execute(
        "SELECT zone_id,camera_id,name,zone_type,enabled FROM zones WHERE zone_id=?", (str(zone_id),)).fetchone())
    if not zone:
        return {"error": "zone not found", "zone_id": str(zone_id)}
    query = "SELECT * FROM events WHERE zone_id=?"
    args: list[Any] = [str(zone_id)]
    since, until = _iso(since), _iso(until)
    if since:
        query += " AND timestamp>=?"
        args.append(since)
    if until:
        query += " AND timestamp<=?"
        args.append(until)
    limit = _limit(limit, 50)
    events = _rows(helios.db.execute(query + " ORDER BY timestamp DESC LIMIT ?", [*args, limit]))
    detections = _rows(helios.db.execute(
        "SELECT detection_id,camera_id,timestamp,object_type,confidence,track_id,zone_id FROM detections WHERE zone_id=? ORDER BY timestamp DESC LIMIT ?",
        (str(zone_id), limit)))
    return {"zone": zone, "events": events, "detections": detections, "count": len(events)}


def get_camera_status(helios, camera_id: Any = None, limit: Any = 10) -> dict[str, Any]:
    limit = _limit(limit, 10)
    if camera_id:
        camera = item(helios.db.execute(
            "SELECT camera_id,name,source_type,location,status,enabled FROM cameras WHERE camera_id=?",
            (str(camera_id),)).fetchone())
        if not camera:
            return {"error": "camera not found", "camera_id": str(camera_id)}
        health = helios.camera_health(str(camera_id))
        recent_events = _rows(helios.db.execute(
            "SELECT event_id,event_type,timestamp,severity,status FROM events WHERE camera_id=? ORDER BY timestamp DESC LIMIT ?",
            (str(camera_id), limit)))
        active_alerts = _rows(helios.db.execute(
            "SELECT alert_id,event_id,alert_type,severity,status,message,timestamp FROM alerts WHERE status='ACTIVE' "
            "AND event_id IN (SELECT event_id FROM events WHERE camera_id=?) LIMIT ?", (str(camera_id), limit)))
        return {"camera": camera, "health": health, "recent_events": recent_events, "active_alerts": active_alerts}
    cameras = _rows(helios.db.execute(
        "SELECT camera_id,name,source_type,location,status,enabled FROM cameras ORDER BY camera_id"))
    return {"cameras": cameras, "count": len(cameras)}


def get_camera_condition(helios, camera_id: Any = None) -> dict[str, Any]:
    """Retrieve camera obstruction, visibility status, reliability score and vision metrics."""
    if camera_id:
        cond = helios.get_camera_condition(str(camera_id))
        if not cond:
            return {"error": "camera not found", "camera_id": str(camera_id)}
        history = helios.get_camera_condition_history(str(camera_id), limit=10)
        return {"current_condition": cond, "recent_history": history}
    return {"cameras": helios.get_all_camera_conditions()}


def get_daily_statistics(helios, date: Any = None) -> dict[str, Any]:
    if date is None:
        date = datetime.now(UTC).date().isoformat()
    dates = str(date)[:10]
    start = dates + "T00:00:00"
    end = dates + "T23:59:59.999999"
    total_events = helios.db.execute("SELECT COUNT(*) FROM events WHERE timestamp>=? AND timestamp<=?", (start, end)).fetchone()[0]
    events_by_type = [dict(row) for row in helios.db.execute(
        "SELECT event_type,COUNT(*) AS count FROM events WHERE timestamp>=? AND timestamp<=? GROUP BY event_type ORDER BY count DESC", (start, end))]
    events_by_severity = [dict(row) for row in helios.db.execute(
        "SELECT severity,COUNT(*) AS count FROM events WHERE timestamp>=? AND timestamp<=? GROUP BY severity ORDER BY count DESC", (start, end))]
    virtual_fence = [dict(row) for row in helios.db.execute(
        "SELECT * FROM events WHERE event_type='RESTRICTED_ZONE_ENTRY' AND timestamp>=? AND timestamp<=? ORDER BY timestamp DESC LIMIT 20", (start, end))]
    significant_events = [dict(row) for row in helios.db.execute(
        "SELECT * FROM events WHERE timestamp>=? AND timestamp<=? "
        "ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END, timestamp DESC LIMIT 8", (start, end))]
    evidence_total = helios.db.execute(
        "SELECT COUNT(*) FROM evidence WHERE event_id IN (SELECT event_id FROM events WHERE timestamp>=? AND timestamp<=?)", (start, end)).fetchone()[0]
    evidence_by_type = [dict(row) for row in helios.db.execute(
        "SELECT type,COUNT(*) AS count FROM evidence WHERE event_id IN (SELECT event_id FROM events WHERE timestamp>=? AND timestamp<=?) "
        "GROUP BY type ORDER BY count DESC", (start, end))]
    alerts_created = helios.db.execute(
        "SELECT COUNT(*) FROM alerts WHERE event_id IN (SELECT event_id FROM events WHERE timestamp>=? AND timestamp<=?)", (start, end)).fetchone()[0]
    active_alerts = helios.db.execute("SELECT COUNT(*) FROM alerts WHERE status='ACTIVE'").fetchone()[0]
    zone_activity = [dict(row) for row in helios.db.execute(
        "SELECT zone_id,COUNT(*) AS count FROM events WHERE zone_id IS NOT NULL AND timestamp>=? AND timestamp<=? GROUP BY zone_id ORDER BY count DESC", (start, end))]
    top_cameras = [dict(row) for row in helios.db.execute(
        "SELECT camera_id,COUNT(*) AS count FROM events WHERE camera_id IS NOT NULL AND timestamp>=? AND timestamp<=? GROUP BY camera_id ORDER BY count DESC", (start, end))]
    hourly = [dict(row) for row in helios.db.execute(
        "SELECT substr(timestamp,12,2) AS hour,COUNT(*) AS count FROM events WHERE timestamp>=? AND timestamp<=? GROUP BY hour ORDER BY hour", (start, end))]
    camera_rows = [dict(row) for row in helios.db.execute(
        "SELECT camera_id,name,status FROM cameras ORDER BY camera_id")]
    active_threads = helios.db.execute("SELECT COUNT(*) FROM tracks WHERE status='ACTIVE'").fetchone()[0]
    total_tracks_today = helios.db.execute("SELECT COUNT(*) FROM tracks WHERE created_at>=? AND created_at<=?", (start, end)).fetchone()[0]
    vehicle_tracks_today = helios.db.execute("SELECT COUNT(*) FROM tracks WHERE object_type='VEHICLE' AND created_at>=? AND created_at<=?", (start, end)).fetchone()[0]

    faces_detected_today = 0
    faces_recognized_today = 0
    faces_unclassified_today = 0
    recognized_persons_today = []
    try:
        faces_detected_today = helios.db.execute(
            "SELECT COUNT(*) FROM face_recognitions WHERE (created_at>=? AND created_at<=?) OR (last_seen>=? AND last_seen<=?)",
            (start, end, start, end),
        ).fetchone()[0]
        faces_recognized_today = helios.db.execute(
            "SELECT COUNT(*) FROM face_recognitions WHERE status='RECOGNIZED' AND ((created_at>=? AND created_at<=?) OR (last_seen>=? AND last_seen<=?))",
            (start, end, start, end),
        ).fetchone()[0]
        faces_unclassified_today = helios.db.execute(
            "SELECT COUNT(*) FROM face_recognitions WHERE status!='RECOGNIZED' AND ((created_at>=? AND created_at<=?) OR (last_seen>=? AND last_seen<=?))",
            (start, end, start, end),
        ).fetchone()[0]
        rec_p_rows = helios.db.execute(
            "SELECT DISTINCT person_name FROM face_recognitions WHERE status='RECOGNIZED' AND ((created_at>=? AND created_at<=?) OR (last_seen>=? AND last_seen<=?))",
            (start, end, start, end),
        ).fetchall()
        recognized_persons_today = [r[0] for r in rec_p_rows if r[0]]
    except Exception:
        pass

    return {
        "date": dates,
        "total_events": total_events,
        "events_by_type": events_by_type,
        "events_by_severity": events_by_severity,
        "virtual_fence_events": virtual_fence,
        "significant_events": significant_events,
        "evidence_total": evidence_total,
        "evidence_by_type": evidence_by_type,
        "alerts_created": alerts_created,
        "active_alerts": active_alerts,
        "zone_activity": zone_activity,
        "top_cameras": top_cameras,
        "hourly_activity": hourly,
        "camera_health": camera_rows,
        "cameras_total": len(camera_rows),
        "cameras_online": sum(1 for row in camera_rows if row.get("status") == "ONLINE"),
        "cameras_offline": sum(1 for row in camera_rows if row.get("status") == "OFFLINE"),
        "active_threads": active_threads,
        "total_tracks_today": total_tracks_today,
        "vehicle_tracks_today": vehicle_tracks_today,
        "faces_detected_today": faces_detected_today,
        "faces_recognized_today": faces_recognized_today,
        "faces_unclassified_today": faces_unclassified_today,
        "recognized_persons_today": recognized_persons_today,
    }


def get_event_timeline(helios, camera_id: Any = None, zone_id: Any = None,
                       since: Any = None, until: Any = None, limit: Any = 100) -> dict[str, Any]:
    limit = _limit(limit, 100)
    query = "SELECT * FROM events WHERE 1=1"
    args: list[Any] = []
    if camera_id:
        query += " AND camera_id=?"
        args.append(str(camera_id))
    if zone_id:
        query += " AND zone_id=?"
        args.append(str(zone_id))
    since, until = _iso(since), _iso(until)
    if since:
        query += " AND timestamp>=?"
        args.append(since)
    if until:
        query += " AND timestamp<=?"
        args.append(until)
    events = _rows(helios.db.execute(query + " ORDER BY timestamp ASC LIMIT ?", [*args, limit]))
    detection_query = "SELECT detection_id,camera_id,timestamp,object_type,confidence,track_id,zone_id FROM detections WHERE 1=1"
    detection_args: list[Any] = []
    if camera_id:
        detection_query += " AND camera_id=?"
        detection_args.append(str(camera_id))
    if zone_id:
        detection_query += " AND zone_id=?"
        detection_args.append(str(zone_id))
    if since:
        detection_query += " AND timestamp>=?"
        detection_args.append(since)
    if until:
        detection_query += " AND timestamp<=?"
        detection_args.append(until)
    detections = _rows(helios.db.execute(detection_query + " ORDER BY timestamp ASC LIMIT ?", [*detection_args, limit]))
    entries = []
    for event in events:
        entries.append({"kind": "EVENT", **event})
    for detection in detections:
        entries.append({"kind": "DETECTION", **detection})
    entries.sort(key=lambda entry: (entry.get("timestamp") or "", entry.get("kind")))
    return {"entries": entries[:limit], "count": len(entries)}


def get_evidence(helios, event_id: Any = None, evidence_id: Any = None, limit: Any = 50) -> dict[str, Any]:
    limit = _limit(limit, 50)
    columns = "evidence_id,event_id,type,timestamp,integrity_hash,metadata"
    if evidence_id:
        evidence = item(helios.db.execute(
            f"SELECT {columns} FROM evidence WHERE evidence_id=?", (str(evidence_id),)).fetchone())
        if not evidence:
            return {"error": "evidence not found", "evidence_id": str(evidence_id)}
        return {"evidence": [evidence], "count": 1}
    if event_id:
        evidence = _rows(helios.db.execute(
            f"SELECT {columns} FROM evidence WHERE event_id=? ORDER BY timestamp DESC LIMIT ?", (str(event_id), limit)))
    else:
        evidence = _rows(helios.db.execute(
            f"SELECT {columns} FROM evidence ORDER BY timestamp DESC LIMIT ?", (limit,)))
    return {"evidence": evidence, "count": len(evidence), "limit": limit}


def get_related_events(helios, event_id: str, radius_seconds: Any = 3600, limit: Any = 20) -> dict[str, Any]:
    event = item(helios.db.execute("SELECT * FROM events WHERE event_id=?", (str(event_id),)).fetchone())
    if not event:
        return {"error": "event not found", "event_id": str(event_id)}
    try:
        radius = int(radius_seconds)
    except (TypeError, ValueError):
        radius = 3600
    radius = max(60, min(radius, 86400))
    limit = _limit(limit, 20)
    try:
        stamp = datetime.fromisoformat(str(event["timestamp"]))
    except ValueError:
        stamp = datetime.now(UTC)
    start = (stamp - __import__("datetime").timedelta(seconds=radius)).isoformat()
    end = (stamp + __import__("datetime").timedelta(seconds=radius)).isoformat()
    related = _rows(helios.db.execute(
        "SELECT * FROM events WHERE event_id<>? AND timestamp>=? AND timestamp<=? AND "
        "(camera_id=? OR (zone_id IS NOT NULL AND zone_id=?) OR object_type=?) "
        "ORDER BY timestamp DESC LIMIT ?",
        (str(event_id), start, end, event.get("camera_id", ""), event.get("zone_id", ""), event.get("object_type", ""), limit)))
    return {"event": event, "related_events": related, "count": len(related), "radius_seconds": radius}


def get_activity_threads(
    helios,
    status: Any = None,
    object_type: Any = None,
    camera_id: Any = None,
    vehicle_type: Any = None,
    threat_level: Any = None,
    movement_state: Any = None,
    limit: Any = 20,
) -> dict[str, Any]:
    limit = _limit(limit, 20, 1, 100)
    threads = helios.get_all_threads(
        limit=limit,
        status=str(status).upper() if status else None,
        camera_id=str(camera_id) if camera_id else None,
        object_type=str(object_type).upper() if object_type else None,
        vehicle_type=str(vehicle_type).lower() if vehicle_type else None,
        threat_level=str(threat_level).upper() if threat_level else None,
        movement_state=str(movement_state).upper() if movement_state else None,
    )
    summary_list = []
    for t in threads:
        summary_list.append({
            "track_id": t["track_id"],
            "object_type": t["object_type"],
            "camera_id": t["camera_id"],
            "status": t["status"],
            "vehicle_label": t.get("vehicle_label"),
            "vehicle_type": t.get("vehicle_type"),
            "vehicle_color": t.get("vehicle_color"),
            "threat_level": t.get("threat_level", "LOW"),
            "movement_dynamic": t.get("movement_dynamic", "NORMAL"),
            "speed": t.get("speed", 0.0),
            "speed_unit": t.get("speed_unit", "px/s"),
            "speed_kmh": t.get("speed_kmh"),
            "direction": t.get("direction", "STATIONARY"),
            "heading_deg": t.get("heading_deg", 0.0),
            "movement_state": t.get("movement_state", "STATIONARY"),
            "distance_travelled": t.get("distance_travelled", 0.0),
            "duration_seconds": t.get("duration_seconds", 0),
            "loitering_detected": t.get("loitering_detected", False),
            "activity_story": t.get("activity_story"),
        })
    return {"threads": summary_list, "count": len(summary_list), "limit": limit}


def get_activity_thread_story(helios, track_id: str) -> dict[str, Any]:
    thread = helios.get_track_thread(str(track_id), include_positions=False)
    if not thread:
        return {"error": "activity thread not found", "track_id": str(track_id)}
    return {
        "track_id": thread["track_id"],
        "object_type": thread["object_type"],
        "camera_id": thread["camera_id"],
        "status": thread["status"],
        "vehicle_label": thread.get("vehicle_label"),
        "vehicle_type": thread.get("vehicle_type"),
        "vehicle_color": thread.get("vehicle_color"),
        "threat_level": thread.get("threat_level", "LOW"),
        "movement_dynamic": thread.get("movement_dynamic", "NORMAL"),
        "speed": thread.get("speed", 0.0),
        "speed_unit": thread.get("speed_unit", "px/s"),
        "speed_kmh": thread.get("speed_kmh"),
        "direction": thread.get("direction", "STATIONARY"),
        "heading_deg": thread.get("heading_deg", 0.0),
        "movement_state": thread.get("movement_state", "STATIONARY"),
        "distance_travelled": thread.get("distance_travelled", 0.0),
        "duration_seconds": thread.get("duration_seconds", 0),
        "loitering_detected": thread.get("loitering_detected", False),
        "activity_story": thread.get("activity_story"),
        "timeline_nodes_count": len(thread.get("timeline", [])),
        "timeline_highlights": [
            {"node_type": n.get("node_type"), "title": n.get("title"), "timestamp": n.get("timestamp"), "detail": n.get("detail")}
            for n in thread.get("timeline", [])
        ],
    }


def get_track_movements(
    helios,
    track_id: Any = None,
    camera_id: Any = None,
    movement_state: Any = None,
    limit: Any = 50,
) -> dict[str, Any]:
    limit = _limit(limit, 50, 1, 200)
    if track_id:
        movements = helios.get_track_movements(str(track_id), limit=limit)
        return {
            "track_id": str(track_id),
            "movements": movements,
            "count": len(movements),
            "limit": limit,
        }
    query = "SELECT * FROM track_movements WHERE 1=1"
    args: list[Any] = []
    if camera_id:
        query += " AND camera_id=?"
        args.append(str(camera_id))
    if movement_state:
        query += " AND movement_state=?"
        args.append(str(movement_state).upper())
    query += " ORDER BY timestamp DESC LIMIT ?"
    args.append(limit)
    rows = _rows(helios.db.execute(query, args))
    return {
        "movements": rows,
        "count": len(rows),
        "limit": limit,
    }


def search_vehicles(
    helios,
    vehicle_type: Any = None,
    color: Any = None,
    camera_id: Any = None,
    limit: Any = 20,
) -> dict[str, Any]:
    limit = _limit(limit, 20, 1, 100)
    threads = helios.get_all_threads(
        limit=limit,
        object_type="VEHICLE",
        camera_id=str(camera_id) if camera_id else None,
        vehicle_type=str(vehicle_type).lower() if vehicle_type else None,
        vehicle_color=str(color).lower() if color else None,
    )
    results = []
    for t in threads:
        results.append({
            "track_id": t["track_id"],
            "camera_id": t["camera_id"],
            "status": t["status"],
            "vehicle_label": t.get("vehicle_label") or "Vehicle",
            "vehicle_type": t.get("vehicle_type"),
            "vehicle_color": t.get("vehicle_color"),
            "threat_level": t.get("threat_level", "LOW"),
            "activity_story": t.get("activity_story"),
        })
    return {"vehicles": results, "count": len(results), "limit": limit}


def get_alerts(
    helios,
    status: Any = "ACTIVE",
    severity: Any = None,
    camera_id: Any = None,
    limit: Any = 20,
) -> dict[str, Any]:
    limit = _limit(limit, 20, 1, 100)
    query = "SELECT a.*, e.camera_id, e.event_type FROM alerts a LEFT JOIN events e ON a.event_id=e.event_id WHERE 1=1"
    args: list[Any] = []
    if status and str(status).upper() != "ALL":
        query += " AND a.status=?"
        args.append(str(status).upper())
    if severity:
        query += " AND a.severity=?"
        args.append(str(severity).upper())
    if camera_id:
        query += " AND e.camera_id=?"
        args.append(str(camera_id))
    query += " ORDER BY a.timestamp DESC LIMIT ?"
    args.append(limit)
    rows = _rows(helios.db.execute(query, args))
    return {"alerts": rows, "count": len(rows), "limit": limit}


def list_zones(
    helios,
    camera_id: Any = None,
    enabled: Any = None,
    zone_type: Any = None,
    limit: Any = 50,
) -> dict[str, Any]:
    limit = _limit(limit, 50, 1, 100)
    query = "SELECT zone_id, camera_id, name, zone_type, enabled, object_types, capacity FROM zones WHERE 1=1"
    args: list[Any] = []
    if camera_id:
        query += " AND camera_id=?"
        args.append(str(camera_id))
    if enabled is not None:
        query += " AND enabled=?"
        args.append(1 if enabled else 0)
    if zone_type:
        query += " AND zone_type=?"
        args.append(str(zone_type).upper())
    query += " ORDER BY name LIMIT ?"
    args.append(limit)
    rows = _rows(helios.db.execute(query, args))
    return {"zones": rows, "count": len(rows), "limit": limit}


def get_active_tracks(
    helios,
    object_type: Any = None,
    camera_id: Any = None,
    movement_state: Any = None,
    limit: Any = 25,
) -> dict[str, Any]:
    limit = _limit(limit, 25, 1, 100)
    query = "SELECT track_id, camera_id, object_type, status, speed, direction, heading, movement_state, attributes, last_seen_at FROM tracks WHERE status='ACTIVE'"
    args: list[Any] = []
    if object_type:
        query += " AND object_type=?"
        args.append(str(object_type).upper())
    if camera_id:
        query += " AND camera_id=?"
        args.append(str(camera_id))
    if movement_state:
        query += " AND movement_state=?"
        args.append(str(movement_state).upper())
    query += " ORDER BY last_seen_at DESC LIMIT ?"
    args.append(limit)
    rows = _rows(helios.db.execute(query, args))
    return {"active_tracks": rows, "count": len(rows), "limit": limit}


def search_evidence(
    helios,
    type: Any = None,
    query: Any = None,
    camera_id: Any = None,
    event_id: Any = None,
    limit: Any = 20,
) -> dict[str, Any]:
    limit = _limit(limit, 20, 1, 100)
    sql = "SELECT ev.evidence_id, ev.event_id, ev.type, ev.timestamp, ev.integrity_hash, ev.metadata, e.camera_id, e.object_type FROM evidence ev LEFT JOIN events e ON ev.event_id=e.event_id WHERE 1=1"
    args: list[Any] = []
    if type:
        sql += " AND (ev.type=? OR ev.type LIKE ?)"
        args.extend([str(type).upper(), f"%{type}%"])
    if camera_id:
        sql += " AND e.camera_id=?"
        args.append(str(camera_id))
    if event_id:
        sql += " AND ev.event_id=?"
        args.append(str(event_id))
    if query:
        sql += " AND (ev.metadata LIKE ? OR ev.evidence_id LIKE ? OR ev.event_id LIKE ?)"
        q_wild = f"%{query}%"
        args.extend([q_wild, q_wild, q_wild])
    sql += " ORDER BY ev.timestamp DESC LIMIT ?"
    args.append(limit)
    rows = _rows(helios.db.execute(sql, args))
    return {"evidence": rows, "count": len(rows), "limit": limit}


def get_system_overview(helios) -> dict[str, Any]:
    cams = [dict(r) for r in helios.db.execute("SELECT camera_id, name, status, location FROM cameras").fetchall()]
    online_cams = [c for c in cams if c.get("status") == "ONLINE"]
    offline_cams = [c for c in cams if c.get("status") != "ONLINE"]
    active_alerts = [dict(r) for r in helios.db.execute("SELECT alert_id, alert_type, severity, message, timestamp FROM alerts WHERE status='ACTIVE' ORDER BY timestamp DESC LIMIT 5").fetchall()]
    active_tracks = [dict(r) for r in helios.db.execute("SELECT track_id, object_type, camera_id, speed, movement_state, direction FROM tracks WHERE status='ACTIVE' ORDER BY last_seen_at DESC LIMIT 10").fetchall()]
    recent_events = [dict(r) for r in helios.db.execute("SELECT event_id, event_type, camera_id, severity, timestamp FROM events ORDER BY timestamp DESC LIMIT 5").fetchall()]
    zones = [dict(r) for r in helios.db.execute("SELECT zone_id, name, zone_type FROM zones WHERE enabled=1").fetchall()]
    return {
        "cameras_total": len(cams),
        "cameras_online": len(online_cams),
        "cameras_offline": len(offline_cams),
        "online_cameras": [c["camera_id"] for c in online_cams],
        "offline_cameras": [c["camera_id"] for c in offline_cams],
        "active_alerts_count": len(active_alerts),
        "active_alerts": active_alerts,
        "active_tracks_count": len(active_tracks),
        "active_tracks_sample": active_tracks,
        "recent_events_count": len(recent_events),
        "recent_events": recent_events,
        "zones_count": len(zones),
    }


def get_system_logs(
    helios,
    level: Any = None,
    component: Any = None,
    limit: Any = 20,
) -> dict[str, Any]:
    limit = _limit(limit, 20, 1, 100)
    sql = "SELECT log_id, timestamp, level, component, message, context FROM system_logs WHERE 1=1"
    args: list[Any] = []
    if level:
        sql += " AND level=?"
        args.append(str(level).upper())
    if component:
        sql += " AND component=?"
        args.append(str(component))
    sql += " ORDER BY timestamp DESC LIMIT ?"
    args.append(limit)
    rows = _rows(helios.db.execute(sql, args))
    return {"logs": rows, "count": len(rows), "limit": limit}


def search_faces(
    helios,
    person_name: Any = None,
    status: Any = None,
    camera_id: Any = None,
    limit: Any = 20,
) -> dict[str, Any]:
    limit = _limit(limit, 20, 1, 100)
    sql = "SELECT recognition_id, track_id, camera_id, person_id, person_name, status, similarity, confidence, snapshot_path, detection_count, first_seen, last_seen FROM face_recognitions WHERE 1=1"
    args: list[Any] = []
    if status and str(status).upper() != "ALL":
        sql += " AND status=?"
        args.append(str(status).upper())
    if camera_id:
        sql += " AND camera_id=?"
        args.append(str(camera_id))
    if person_name:
        sql += " AND (person_name LIKE ? OR person_id LIKE ?)"
        args.extend([f"%{person_name}%", f"%{person_name}%"])
    sql += " ORDER BY last_seen DESC LIMIT ?"
    args.append(limit)
    rows = _rows(helios.db.execute(sql, args))
    return {"faces": rows, "count": len(rows), "limit": limit}


def get_face_intel(
    helios,
    track_id: Any = None,
    person_id: Any = None,
    recognition_id: Any = None,
) -> dict[str, Any]:
    rec = None
    if recognition_id:
        rec = item(helios.db.execute("SELECT * FROM face_recognitions WHERE recognition_id=?", (str(recognition_id),)).fetchone())
    elif track_id:
        rec = item(helios.db.execute("SELECT * FROM face_recognitions WHERE track_id=? ORDER BY updated_at DESC LIMIT 1", (str(track_id),)).fetchone())
    elif person_id:
        rec = item(helios.db.execute("SELECT * FROM face_recognitions WHERE person_id=? ORDER BY last_seen DESC LIMIT 1", (str(person_id),)).fetchone())

    target_person_id = (rec.get("person_id") if rec else None) or (str(person_id) if person_id else None)
    registered_profile = None
    if target_person_id:
        registered_profile = item(helios.db.execute(
            "SELECT person_id, name, role, notes, face_image_path, created_at, updated_at FROM registered_faces WHERE person_id=?",
            (target_person_id,)
        ).fetchone())

    sightings = []
    if target_person_id:
        sightings = _rows(helios.db.execute(
            "SELECT recognition_id, camera_id, track_id, similarity, detection_count, last_seen, snapshot_path FROM face_recognitions WHERE person_id=? ORDER BY last_seen DESC LIMIT 10",
            (target_person_id,)
        ))

    return {
        "recognition": rec,
        "registered_profile": registered_profile,
        "sightings": sightings,
        "sightings_count": len(sightings),
    }


def list_registered_persons(
    helios,
    query: Any = None,
    limit: Any = 25,
) -> dict[str, Any]:
    limit = _limit(limit, 25, 1, 100)
    sql = "SELECT person_id, name, role, notes, face_image_path, created_at, updated_at FROM registered_faces WHERE 1=1"
    args: list[Any] = []
    if query:
        sql += " AND (name LIKE ? OR person_id LIKE ? OR role LIKE ? OR notes LIKE ?)"
        q_wild = f"%{query}%"
        args.extend([q_wild, q_wild, q_wild, q_wild])
    sql += " ORDER BY name ASC LIMIT ?"
    args.append(limit)
    rows = _rows(helios.db.execute(sql, args))
    return {"registered_persons": rows, "count": len(rows), "limit": limit}


def get_behavioral_anomalies(
    helios,
    camera_id: Any = None,
    zone_id: Any = None,
    track_id: Any = None,
    behavior_type: Any = None,
    min_score: Any = None,
    since: Any = None,
    limit: Any = 20,
) -> dict[str, Any]:
    """Query logged behavioral anomalies with 7-signal score and telemetry filters."""
    limit = _limit(limit, 20, 1, 100)
    events = helios.get_behavioral_events(
        camera_id=camera_id,
        zone_id=zone_id,
        track_id=track_id,
        behavior_type=behavior_type,
        min_score=min_score,
        limit=limit,
    )
    if since:
        s_iso = _iso(since)
        if s_iso:
            events = [e for e in events if e.get("timestamp", "") >= s_iso]
    return {"behavioral_events": events, "count": len(events), "limit": limit}


def get_behavioral_anomaly_detail(
    helios,
    behavior_id: Any = None,
    track_id: Any = None,
) -> dict[str, Any]:
    """Get full details of a behavioral anomaly, including all 7 input scores and reasons."""
    if behavior_id:
        ev = helios.get_behavioral_event(str(behavior_id))
        if ev:
            return {"behavioral_event": ev}
    if track_id:
        events = helios.get_behavioral_events(track_id=str(track_id), limit=1)
        if events:
            return {"behavioral_event": events[0]}
    return {"error": "behavioral event not found", "behavior_id": behavior_id, "track_id": track_id}


def get_behavioral_analytics_summary(helios) -> dict[str, Any]:
    """Get facility-wide behavioral anomaly summary, counts, and highest anomaly zones."""
    return helios.get_behavioral_summary()


TOOL_FUNCTIONS: dict[str, Callable] = {
    "get_recent_events": get_recent_events,
    "search_events": search_events,
    "get_event": get_event,
    "get_track_history": get_track_history,
    "get_zone_activity": get_zone_activity,
    "get_camera_status": get_camera_status,
    "get_daily_statistics": get_daily_statistics,
    "get_event_timeline": get_event_timeline,
    "get_evidence": get_evidence,
    "get_related_events": get_related_events,
    "get_activity_threads": get_activity_threads,
    "get_activity_thread_story": get_activity_thread_story,
    "get_track_movements": get_track_movements,
    "search_vehicles": search_vehicles,
    "get_alerts": get_alerts,
    "list_zones": list_zones,
    "get_active_tracks": get_active_tracks,
    "search_evidence": search_evidence,
    "get_system_overview": get_system_overview,
    "get_system_logs": get_system_logs,
    "search_faces": search_faces,
    "get_face_intel": get_face_intel,
    "list_registered_persons": list_registered_persons,
    "get_behavioral_anomalies": get_behavioral_anomalies,
    "get_behavioral_anomaly_detail": get_behavioral_anomaly_detail,
    "get_behavioral_analytics_summary": get_behavioral_analytics_summary,
    "get_camera_condition": get_camera_condition,
}

TOOL_PARAMS: dict[str, tuple[str, ...]] = {
    "get_recent_events": ("camera_id", "object_type", "severity", "limit"),
    "search_events": ("event_type", "camera_id", "zone_id", "since", "until", "limit"),
    "get_event": ("event_id",),
    "get_track_history": ("track_id",),
    "get_zone_activity": ("zone_id", "since", "until", "limit"),
    "get_camera_status": ("camera_id", "limit"),
    "get_camera_condition": ("camera_id",),
    "get_daily_statistics": ("date",),
    "get_event_timeline": ("camera_id", "zone_id", "since", "until", "limit"),
    "get_evidence": ("event_id", "evidence_id", "limit"),
    "get_related_events": ("event_id", "radius_seconds", "limit"),
    "get_activity_threads": ("status", "object_type", "camera_id", "vehicle_type", "threat_level", "movement_state", "limit"),
    "get_activity_thread_story": ("track_id",),
    "get_track_movements": ("track_id", "camera_id", "movement_state", "limit"),
    "search_vehicles": ("vehicle_type", "color", "camera_id", "limit"),
    "get_alerts": ("status", "severity", "camera_id", "limit"),
    "list_zones": ("camera_id", "enabled", "zone_type", "limit"),
    "get_active_tracks": ("object_type", "camera_id", "movement_state", "limit"),
    "search_evidence": ("type", "query", "camera_id", "event_id", "limit"),
    "get_system_overview": (),
    "get_system_logs": ("level", "component", "limit"),
    "search_faces": ("person_name", "status", "camera_id", "limit"),
    "get_face_intel": ("track_id", "person_id", "recognition_id"),
    "list_registered_persons": ("query", "limit"),
    "get_behavioral_anomalies": ("camera_id", "zone_id", "track_id", "behavior_type", "min_score", "since", "limit"),
    "get_behavioral_anomaly_detail": ("behavior_id", "track_id"),
    "get_behavioral_analytics_summary": (),
}


def execute_tool(helios, name: str, args: dict[str, Any]) -> dict[str, Any]:
    args = args or {}
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return {"error": f"unknown tool {name}"}
    allowed = TOOL_PARAMS.get(name, ())
    filtered = {key: value for key, value in args.items() if key in allowed}
    try:
        return function(helios, **filtered)
    except Exception as exc:
        return {"error": f"{name} failed: {type(exc).__name__}: {exc}"}


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "OBJECT", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _string(description: str) -> dict[str, Any]:
    return {"type": "STRING", "description": description}


def _integer(description: str) -> dict[str, Any]:
    return {"type": "INTEGER", "description": description}


TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "get_recent_events",
        "description": "Returns the most recent HELIOS events, optionally filtered by camera, object type, or severity.",
        "parameters": _object({
            "camera_id": _string("Camera id such as CAM-01."),
            "object_type": _string("Object type such as HUMAN, VEHICLE, UAV, or FACE."),
            "severity": _string("Severity such as INFO, MEDIUM, HIGH, or CRITICAL."),
            "limit": _integer("Maximum number of events to return (1-100)."),
        }),
    },
    {
        "name": "search_events",
        "description": "Searches HELIOS events by event type, camera, zone, and ISO time range.",
        "parameters": _object({
            "event_type": _string("Event type such as UAV_DETECTED or RESTRICTED_ZONE_ENTRY."),
            "camera_id": _string("Camera id such as CAM-01."),
            "zone_id": _string("Zone id such as ZONE-RESTRICTED-01."),
            "since": _string("ISO timestamp or date (YYYY-MM-DD) for the lower bound."),
            "until": _string("ISO timestamp or date (YYYY-MM-DD) for the upper bound."),
            "limit": _integer("Maximum number of events to return (1-100)."),
        }),
    },
    {
        "name": "get_event",
        "description": "Returns a single HELIOS event with its linked track, camera, zone, and evidence.",
        "parameters": _object({"event_id": _string("Event id such as EVT-A1B2C3D4E5F6.")}, required=["event_id"]),
    },
    {
        "name": "get_track_history",
        "description": "Returns a HELIOS track and its position history.",
        "parameters": _object({"track_id": _string("Track id such as #P-A1B2C3.")}, required=["track_id"]),
    },
    {
        "name": "get_zone_activity",
        "description": "Returns events and detections recorded in a HELIOS zone.",
        "parameters": _object({
            "zone_id": _string("Zone id such as ZONE-RESTRICTED-01."),
            "since": _string("ISO timestamp or date (YYYY-MM-DD) for the lower bound."),
            "until": _string("ISO timestamp or date (YYYY-MM-DD) for the upper bound."),
            "limit": _integer("Maximum number of events to return (1-100)."),
        }, required=["zone_id"]),
    },
    {
        "name": "get_camera_status",
        "description": "Returns camera status and health; pass camera_id for one camera or omit for all.",
        "parameters": _object({
            "camera_id": _string("Camera id such as CAM-01. Omit to list all cameras."),
            "limit": _integer("Maximum number of recent events to include (1-100)."),
        }),
    },
    {
        "name": "get_daily_statistics",
        "description": "Returns exact daily HELIOS statistics for a date (YYYY-MM-DD) or today.",
        "parameters": _object({"date": _string("Date in YYYY-MM-DD format. Defaults to today.")}),
    },
    {
        "name": "get_event_timeline",
        "description": "Returns a chronological timeline of HELIOS events and detections.",
        "parameters": _object({
            "camera_id": _string("Camera id such as CAM-01."),
            "zone_id": _string("Zone id such as ZONE-RESTRICTED-01."),
            "since": _string("ISO timestamp or date (YYYY-MM-DD) for the lower bound."),
            "until": _string("ISO timestamp or date (YYYY-MM-DD) for the upper bound."),
            "limit": _integer("Maximum number of entries to return (1-100)."),
        }),
    },
    {
        "name": "get_evidence",
        "description": "Returns HELIOS evidence records, optionally for a specific event or evidence id.",
        "parameters": _object({
            "event_id": _string("Event id such as EVT-A1B2C3D4E5F6."),
            "evidence_id": _string("Evidence id such as EVD-A1B2C3D4E5F6."),
            "limit": _integer("Maximum number of records to return (1-100)."),
        }),
    },
    {
        "name": "get_related_events",
        "description": "Returns HELIOS events related to a given event by camera, zone, or object type near its timestamp.",
        "parameters": _object({
            "event_id": _string("Event id such as EVT-A1B2C3D4E5F6."),
            "radius_seconds": _integer("Time window radius in seconds (60-86400). Defaults to 3600."),
            "limit": _integer("Maximum number of related events to return (1-100)."),
        }, required=["event_id"]),
    },
    {
        "name": "get_activity_threads",
        "description": "Returns activity threads tracking journeys of detected entities (humans, vehicles, UAVs), including vehicle classifications, movement dynamics, loitering, and threat levels.",
        "parameters": _object({
            "status": _string("Thread status such as ACTIVE or ENDED."),
            "object_type": _string("Object type such as HUMAN, VEHICLE, or UAV."),
            "camera_id": _string("Camera id such as CAM-01."),
            "vehicle_type": _string("Specific vehicle type like SUV, sedan, pickup truck, van, heavy truck, bus, or motorcycle."),
            "threat_level": _string("Threat level such as LOW, ELEVATED, HIGH, or CRITICAL."),
            "movement_state": _string("Movement state such as STATIONARY, WALKING, RUNNING, SLOW_MOVING, CRUISING, or FAST."),
            "limit": _integer("Maximum number of threads to return (1-100)."),
        }),
    },
    {
        "name": "get_activity_thread_story",
        "description": "Returns a comprehensive activity thread story and chronological timeline highlights for a specific target track ID.",
        "parameters": _object({"track_id": _string("Track id such as #V-A1B2C3 or #P-A1B2C3.")}, required=["track_id"]),
    },
    {
        "name": "get_track_movements",
        "description": "Returns high-resolution chronological speed, heading, movement state, and change history for a specific track or across cameras.",
        "parameters": _object({
            "track_id": _string("Track id such as #V-A1B2C3 or #P-A1B2C3. Optional if camera_id or movement_state is provided."),
            "camera_id": _string("Camera id such as CAM-01."),
            "movement_state": _string("Movement state filter such as RUNNING, WALKING, FAST, or CRUISING."),
            "limit": _integer("Maximum number of movement snapshots to return (1-200). Defaults to 50."),
        }),
    },
    {
        "name": "search_vehicles",
        "description": "Searches and filters vehicle intelligence records across cameras by classification (SUV, sedan, pickup truck, van, heavy truck, bus, motorcycle), color, and camera.",
        "parameters": _object({
            "vehicle_type": _string("Vehicle classification type (SUV, sedan, pickup truck, van, heavy truck, bus, motorcycle)."),
            "color": _string("Vehicle color (e.g., white, black, silver, red, blue, gray)."),
            "camera_id": _string("Camera id such as CAM-01."),
            "limit": _integer("Maximum number of vehicle tracks to return (1-100)."),
        }),
    },
    {
        "name": "get_alerts",
        "description": "Returns facility alerts and top threats, optionally filtered by status (ACTIVE, ACKNOWLEDGED, RESOLVED), severity (CRITICAL, HIGH, WARN, INFO), or camera.",
        "parameters": _object({
            "status": _string("Alert status: ACTIVE, ACKNOWLEDGED, RESOLVED, or ALL. Defaults to ACTIVE."),
            "severity": _string("Severity filter: CRITICAL, HIGH, WARN, or INFO."),
            "camera_id": _string("Camera id such as CAM-01."),
            "limit": _integer("Maximum number of alerts to return (1-100). Defaults to 20."),
        }),
    },
    {
        "name": "list_zones",
        "description": "Returns configured surveillance zones, restricted areas, perimeter fences, and their capacities and geometry.",
        "parameters": _object({
            "camera_id": _string("Filter zones by camera id such as CAM-01."),
            "enabled": _integer("Filter by enabled status (1 for active zones, 0 for disabled)."),
            "zone_type": _string("Filter by zone type like RESTRICTED or OCCUPANCY."),
            "limit": _integer("Maximum number of zones to return (1-100). Defaults to 50."),
        }),
    },
    {
        "name": "get_active_tracks",
        "description": "Returns currently active tracking sessions for persons, vehicles, and UAVs, with real-time speed, direction, heading, and movement classification.",
        "parameters": _object({
            "object_type": _string("Filter by object type such as HUMAN, VEHICLE, or UAV."),
            "camera_id": _string("Filter by camera id such as CAM-01."),
            "movement_state": _string("Filter by movement state: STATIONARY, WALKING, RUNNING, SLOW_MOVING, CRUISING, or FAST."),
            "limit": _integer("Maximum number of active tracks to return (1-100). Defaults to 25."),
        }),
    },
    {
        "name": "search_evidence",
        "description": "Searches captured evidence records, including ANPR license plates, face recognition captures, UAV photos, and metadata queries.",
        "parameters": _object({
            "type": _string("Evidence type such as PLATE_READ, FACE, UAV, or FRAME_SNAPSHOT."),
            "query": _string("Text search query matching license plate numbers, face identities, or metadata terms."),
            "camera_id": _string("Camera id such as CAM-01."),
            "event_id": _string("Event id such as EVT-A1B2C3D4E5F6."),
            "limit": _integer("Maximum number of evidence records to return (1-100). Defaults to 20."),
        }),
    },
    {
        "name": "get_system_overview",
        "description": "Returns a high-level operational snapshot of the entire facility: total cameras, online/offline cameras, active alert counts, active tracking count, and recent event statistics.",
        "parameters": _object({}),
    },
    {
        "name": "get_system_logs",
        "description": "Returns operational system logs and diagnostics, optionally filtered by log level (ERROR, WARN, INFO) or component.",
        "parameters": _object({
            "level": _string("Log level: ERROR, WARN, or INFO."),
            "component": _string("Component name such as pipeline, camera, or detector."),
            "limit": _integer("Maximum number of logs to return (1-100). Defaults to 20."),
        }),
    },
    {
        "name": "search_faces",
        "description": "Searches facial recognition records, sightings, and detections across cameras, filtered by person name, status (RECOGNIZED, UNCLASSIFIED), or camera ID.",
        "parameters": _object({
            "person_name": _string("Person name or ID to search for."),
            "status": _string("Face status: RECOGNIZED, UNCLASSIFIED, or ALL."),
            "camera_id": _string("Camera id such as CAM-01."),
            "limit": _integer("Maximum number of face sightings to return (1-100). Defaults to 20."),
        }),
    },
    {
        "name": "get_face_intel",
        "description": "Returns detailed facial recognition intelligence, registered profile (role, notes), and historical sightings for a track ID, person ID, or recognition ID.",
        "parameters": _object({
            "track_id": _string("Track ID to check face intelligence for."),
            "person_id": _string("Person ID to lookup registered profile and sightings for."),
            "recognition_id": _string("Face recognition sighting ID such as FAC-0123456789."),
        }),
    },
    {
        "name": "list_registered_persons",
        "description": "Lists enrolled personnel in the facial recognition database with their person ID, name, role, notes, and profile snapshot.",
        "parameters": _object({
            "query": _string("Optional search query matching person name, role, or ID."),
            "limit": _integer("Maximum number of registered persons to return (1-100). Defaults to 25."),
        }),
    },
    {
        "name": "get_behavioral_anomalies",
        "description": "Returns detected behavioral anomalies with 7-signal composite scores (0-100), including unusual dwell, sudden speed/direction changes, restricted zone movement, crowd surges, and off-hours activity.",
        "parameters": _object({
            "camera_id": _string("Camera ID such as CAM-01."),
            "zone_id": _string("Zone ID such as ZONE-03."),
            "track_id": _string("Track ID such as #184."),
            "behavior_type": _string("Behavior type such as UNUSUAL_DWELL, SUDDEN_SPEED_CHANGE, SUDDEN_DIRECTION_CHANGE, RESTRICTED_ZONE_MOVEMENT, or UNUSUAL_ACTIVITY_DENSITY."),
            "min_score": _integer("Minimum anomaly score threshold (0-100)."),
            "since": _string("ISO timestamp or date string to filter events after."),
            "limit": _integer("Maximum number of behavioral anomalies to return (1-100). Defaults to 20."),
        }),
    },
    {
        "name": "get_behavioral_anomaly_detail",
        "description": "Returns full telemetry breakdown, reasons, trajectory, normal vs current comparison, and all 7 deviation scores for a specific behavioral anomaly or track ID.",
        "parameters": _object({
            "behavior_id": _string("Behavioral anomaly ID such as BEH-12345678."),
            "track_id": _string("Track ID such as #184 to fetch recent behavioral anomaly for."),
        }),
    },
    {
        "name": "get_behavioral_analytics_summary",
        "description": "Returns high-level statistics of facility behavioral anomalies: today's anomaly count, average score, top flagged zones, and highest recorded anomaly scores.",
        "parameters": _object({}),
    },
    {
        "name": "get_camera_condition",
        "description": "Returns camera obstruction and visual visibility diagnostics, including reliability score (0-100), condition status (CLEAR, DEAD_FEED, BLURRED, LOW_CONTRAST, FULL_WHITE_OVEREXPOSURE, PARTIAL_WHITE_OVEREXPOSURE, FOG_HAZE, HEAVY_RAIN, OBSTRUCTED), active duration, confidence, and vision metrics (contrast, focus/Laplacian, edge density, brightness).",
        "parameters": _object({
            "camera_id": _string("Camera ID such as CAM-01 to inspect visibility condition for. If omitted, returns condition for all cameras."),
        }),
    },
]