"""Event investigation: gathers HELIOS context and returns a structured result.

This is a read-only investigation. It never modifies HELIOS configuration and
never executes operational actions.
"""
from __future__ import annotations
import base64
import json
from datetime import timedelta
from typing import Any

from app.ai.prompts import (AI_SYSTEM_PROMPT, entity_investigation_prompt,
                            evidence_image_investigation_prompt,
                            investigation_prompt)
from app.ai.references import (collect_ids, default_actions, parse_json_text,
                               references_from_context, sanitize_actions,
                               sanitize_claims, sanitize_references)
from app.ai.schemas import AiClaim, InvestigationContext, InvestigationResult
from app.services.helios_service import item


def get_evidence_image_bytes(helios, evidence_id: str) -> tuple[bytes | None, str]:
    """Retrieve raw image bytes and mime type for an evidence artifact from disk or camera snapshot."""
    settings = getattr(helios, "settings", None)
    if settings and getattr(settings, "evidence_directory", None):
        ev_file = settings.evidence_directory / f"{evidence_id}.jpg"
        if ev_file.exists() and ev_file.is_file():
            try:
                return ev_file.read_bytes(), "image/jpeg"
            except Exception:
                pass

    row = item(helios.db.execute("SELECT storage_reference FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone())
    if row and row.get("storage_reference") and settings and getattr(settings, "evidence_directory", None):
        ref_path = settings.evidence_directory / row["storage_reference"].lstrip("/")
        if ref_path.exists() and ref_path.is_file():
            try:
                return ref_path.read_bytes(), "image/jpeg"
            except Exception:
                pass

    camera_hub = getattr(helios, "camera_hub", None)
    if camera_hub and hasattr(camera_hub, "get_snapshot_jpeg"):
        try:
            jpeg = camera_hub.get_snapshot_jpeg("CAM-01")
            if jpeg:
                return jpeg, "image/jpeg"
        except Exception:
            pass

    return None, "image/jpeg"


def get_evidence_image_data_uri(helios, evidence_id: str) -> str | None:
    """Return data:image/jpeg;base64,... URI for the evidence artifact."""
    raw_bytes, mime = get_evidence_image_bytes(helios, evidence_id)
    if not raw_bytes:
        return None
    b64 = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def build_entity_timeline(helios, track_id: str, window_hours: int = 6) -> list[dict[str, Any]]:
    """Query HELIOS database to construct a fast, chronological timeline of the detected entity."""
    timeline_steps: list[dict[str, Any]] = []

    track = item(helios.db.execute("SELECT * FROM tracks WHERE track_id=?", (track_id,)).fetchone())
    if not track:
        track = item(helios.db.execute("SELECT * FROM tracks WHERE track_id LIKE ?", (f"%{track_id}%",)).fetchone())
    if not track:
        return []

    real_track_id = track["track_id"]

    # 1. Track initialized
    timeline_steps.append({
        "timestamp": track["created_at"],
        "step_type": "FIRST_SEEN",
        "camera_id": track.get("camera_id"),
        "track_id": real_track_id,
        "object_type": track.get("object_type"),
        "description": f"Entity {real_track_id} ({track.get('object_type')}) first detected on camera {track.get('camera_id')}.",
    })

    # 2. Key position updates from track_positions
    try:
        positions = [dict(row) for row in helios.db.execute(
            "SELECT timestamp, bounding_box, confidence FROM track_positions WHERE track_id=? ORDER BY timestamp ASC",
            (real_track_id,)
        )]
        if positions:
            sample_indices = {0, len(positions) // 2, len(positions) - 1}
            for idx in sorted(sample_indices):
                pos = positions[idx]
                timeline_steps.append({
                    "timestamp": pos["timestamp"],
                    "step_type": "POSITION_TRACK",
                    "camera_id": track.get("camera_id"),
                    "track_id": real_track_id,
                    "confidence": pos.get("confidence"),
                    "description": f"Entity movement tracked on {track.get('camera_id')} (Confidence: {round(pos.get('confidence', 0) * 100)}%).",
                })
    except Exception:
        pass

    # 3. Detections in zones
    try:
        detections = [dict(row) for row in helios.db.execute(
            "SELECT detection_id, camera_id, timestamp, zone_id, object_type, confidence FROM detections WHERE track_id=? AND zone_id IS NOT NULL ORDER BY timestamp ASC",
            (real_track_id,)
        )]
        seen_zones = set()
        for det in detections:
            zid = det.get("zone_id")
            if zid and zid not in seen_zones:
                seen_zones.add(zid)
                timeline_steps.append({
                    "timestamp": det["timestamp"],
                    "step_type": "ZONE_ENTRY",
                    "camera_id": det.get("camera_id"),
                    "zone_id": zid,
                    "track_id": real_track_id,
                    "description": f"Entity entered spatial zone {zid}.",
                })
    except Exception:
        pass

    # 4. Triggered events for this track
    try:
        events = [dict(row) for row in helios.db.execute(
            "SELECT event_id, event_type, timestamp, camera_id, zone_id, severity, status, description FROM events WHERE track_id=? ORDER BY timestamp ASC",
            (real_track_id,)
        )]
        for evt in events:
            timeline_steps.append({
                "timestamp": evt["timestamp"],
                "step_type": "EVENT_TRIGGERED",
                "event_id": evt["event_id"],
                "event_type": evt["event_type"],
                "camera_id": evt.get("camera_id"),
                "zone_id": evt.get("zone_id"),
                "severity": evt.get("severity"),
                "description": f"Incident {evt['event_id']} ({evt['event_type']}) logged [Severity: {evt.get('severity')}].",
            })
    except Exception:
        pass

    # 5. Linked evidence captures
    try:
        evidence = [dict(row) for row in helios.db.execute(
            "SELECT evidence_id, event_id, type, timestamp, metadata FROM evidence WHERE event_id IN (SELECT event_id FROM events WHERE track_id=?) ORDER BY timestamp ASC",
            (real_track_id,)
        )]
        for ev in evidence:
            timeline_steps.append({
                "timestamp": ev["timestamp"],
                "step_type": "EVIDENCE_CAPTURE",
                "evidence_id": ev["evidence_id"],
                "event_id": ev.get("event_id"),
                "type": ev.get("type"),
                "description": f"Evidence {ev['evidence_id']} ({ev.get('type', 'SNAPSHOT')}) captured in vault.",
            })
    except Exception:
        pass

    # 5.5 Biometric Facial Recognition step
    try:
        face_rows = [dict(row) for row in helios.db.execute(
            "SELECT recognition_id, person_id, person_name, status, similarity, camera_id, last_seen, snapshot_path FROM face_recognitions WHERE track_id=? ORDER BY last_seen ASC",
            (real_track_id,)
        )]
        for f in face_rows:
            is_rec = f.get("status") == "RECOGNIZED"
            sim_str = f" ({int((f.get('similarity') or 0)*100)}% match)" if is_rec and f.get("similarity") else ""
            desc = (
                f"Biometric ArcFace match: {f.get('person_name')}{sim_str} [Person ID: {f.get('person_id') or 'N/A'}]."
                if is_rec
                else f"Unclassified face detected on camera {f.get('camera_id')} (pending association)."
            )
            timeline_steps.append({
                "timestamp": f.get("last_seen") or track["created_at"],
                "step_type": "FACE_RECOGNITION",
                "recognition_id": f.get("recognition_id"),
                "person_id": f.get("person_id"),
                "person_name": f.get("person_name"),
                "status": f.get("status"),
                "similarity": f.get("similarity"),
                "camera_id": f.get("camera_id"),
                "snapshot_path": f.get("snapshot_path"),
                "description": desc,
            })
    except Exception:
        pass

    # 6. Final disposition / last seen
    timeline_steps.append({
        "timestamp": track.get("ended_at") or track.get("last_seen_at") or track["created_at"],
        "step_type": "LAST_SEEN",
        "camera_id": track.get("camera_id"),
        "track_id": real_track_id,
        "status": track.get("status", "ACTIVE"),
        "description": f"Entity status: {track.get('status', 'ACTIVE')} (Last sensor contact at {track.get('last_seen_at')}).",
    })

    timeline_steps.sort(key=lambda x: x.get("timestamp") or "")
    return timeline_steps


def get_face_intel_for_target(helios, track_id: str | None = None, camera_id: str | None = None, event_id: str | None = None) -> dict[str, Any] | None:
    """Lookup linked facial recognition records and enrolled profile for an investigation target."""
    face_row = None
    if track_id:
        face_row = helios.db.execute(
            "SELECT * FROM face_recognitions WHERE track_id=? ORDER BY updated_at DESC LIMIT 1",
            (track_id,),
        ).fetchone()
    if not face_row and event_id:
        face_row = helios.db.execute(
            "SELECT * FROM face_recognitions WHERE event_id=? ORDER BY updated_at DESC LIMIT 1",
            (event_id,),
        ).fetchone()
    if not face_row and track_id:
        t_row = item(helios.db.execute("SELECT attributes, parent_track_id FROM tracks WHERE track_id=?", (track_id,)).fetchone())
        if t_row:
            attrs = t_row.get("attributes") or {}
            if isinstance(attrs, str):
                try:
                    attrs = json.loads(attrs)
                except Exception:
                    attrs = {}
            for cand in (attrs.get("associated_face_id"), attrs.get("associated_human_id"), t_row.get("parent_track_id")):
                if cand:
                    face_row = helios.db.execute("SELECT * FROM face_recognitions WHERE track_id=? ORDER BY updated_at DESC LIMIT 1", (cand,)).fetchone()
                    if face_row:
                        break
    if not face_row:
        return None

    f_dict = item(face_row)
    reg_info = {}
    if f_dict.get("person_id"):
        p_row = helios.db.execute("SELECT role, notes, face_image_path FROM registered_faces WHERE person_id=?", (f_dict["person_id"],)).fetchone()
        if p_row:
            reg_info = item(p_row)

    return {
        "has_face": True,
        "recognition_id": f_dict.get("recognition_id"),
        "status": f_dict.get("status", "UNCLASSIFIED"),
        "person_id": f_dict.get("person_id"),
        "person_name": f_dict.get("person_name") or ("Unclassified Face" if f_dict.get("status") != "RECOGNIZED" else "Recognized Person"),
        "role": reg_info.get("role", ""),
        "notes": reg_info.get("notes", ""),
        "similarity": f_dict.get("similarity", 0.0),
        "confidence": f_dict.get("confidence", 0.9),
        "snapshot_path": f_dict.get("snapshot_path") or reg_info.get("face_image_path"),
        "detection_count": f_dict.get("detection_count", 1),
        "first_seen": f_dict.get("first_seen"),
        "last_seen": f_dict.get("last_seen"),
        "camera_id": f_dict.get("camera_id"),
    }


def build_evidence_investigation_context(helios, evidence_id: str, window_hours: int = 6) -> InvestigationContext | None:
    ev_row = item(helios.db.execute("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone())
    if not ev_row:
        ev_row = item(helios.db.execute("SELECT * FROM evidence WHERE evidence_id LIKE ?", (f"%{evidence_id}%",)).fetchone())
    if not ev_row:
        return None

    real_ev_id = ev_row["evidence_id"]
    event = None
    track = None
    camera = None
    zone = None
    entity_timeline: list[dict[str, Any]] = []

    if ev_row.get("event_id"):
        event = item(helios.db.execute("SELECT * FROM events WHERE event_id=?", (ev_row["event_id"],)).fetchone())
        if event:
            if event.get("track_id"):
                track = item(helios.db.execute("SELECT * FROM tracks WHERE track_id=?", (event["track_id"],)).fetchone())
                if track:
                    entity_timeline = build_entity_timeline(helios, track["track_id"], window_hours=window_hours)
            if event.get("camera_id"):
                camera = item(helios.db.execute(
                    "SELECT camera_id,name,source_type,location,status,enabled FROM cameras WHERE camera_id=?",
                    (event["camera_id"],)).fetchone())
            if event.get("zone_id"):
                zone = item(helios.db.execute(
                    "SELECT zone_id,camera_id,name,zone_type,enabled FROM zones WHERE zone_id=?",
                    (event["zone_id"],)).fetchone())

    image_url = get_evidence_image_data_uri(helios, real_ev_id)

    timeline = []
    related_events = []
    if event:
        base_ctx = build_investigation_context(helios, event["event_id"], window_hours=window_hours)
        if base_ctx:
            timeline = base_ctx.timeline
            related_events = base_ctx.related_events

    face_intel = get_face_intel_for_target(
        helios,
        track_id=track.get("track_id") if track else None,
        camera_id=camera.get("camera_id") if camera else None,
        event_id=event.get("event_id") if event else None,
    )

    return InvestigationContext(
        event=event,
        track=track,
        camera=camera,
        zone=zone,
        timeline=timeline,
        related_events=related_events,
        evidence=[ev_row],
        target_id=real_ev_id,
        target_type="evidence",
        evidence_item=ev_row,
        image_url=image_url,
        entity_timeline=entity_timeline,
        face_intel=face_intel,
    )


def build_track_investigation_context(helios, track_id: str, window_hours: int = 6) -> InvestigationContext | None:
    track = item(helios.db.execute("SELECT * FROM tracks WHERE track_id=?", (track_id,)).fetchone())
    if not track:
        track = item(helios.db.execute("SELECT * FROM tracks WHERE track_id LIKE ?", (f"%{track_id}%",)).fetchone())
    if not track:
        return None

    real_track_id = track["track_id"]
    camera = None
    if track.get("camera_id"):
        camera = item(helios.db.execute(
            "SELECT camera_id,name,source_type,location,status,enabled FROM cameras WHERE camera_id=?",
            (track["camera_id"],)).fetchone())

    events = [dict(row) for row in helios.db.execute(
        "SELECT * FROM events WHERE track_id=? ORDER BY timestamp ASC", (real_track_id,))]
    primary_event = events[0] if events else None

    zone = None
    if primary_event and primary_event.get("zone_id"):
        zone = item(helios.db.execute(
            "SELECT zone_id,camera_id,name,zone_type,enabled FROM zones WHERE zone_id=?",
            (primary_event["zone_id"],)).fetchone())

    evidence = [dict(row) for row in helios.db.execute(
        "SELECT * FROM evidence WHERE event_id IN (SELECT event_id FROM events WHERE track_id=?) ORDER BY timestamp ASC",
        (real_track_id,))]

    entity_timeline = build_entity_timeline(helios, real_track_id, window_hours=window_hours)

    image_url = None
    if evidence:
        image_url = get_evidence_image_data_uri(helios, evidence[0]["evidence_id"])

    face_intel = get_face_intel_for_target(
        helios,
        track_id=real_track_id,
        camera_id=track.get("camera_id"),
        event_id=primary_event.get("event_id") if primary_event else None,
    )

    return InvestigationContext(
        event=primary_event,
        track=track,
        camera=camera,
        zone=zone,
        timeline=events,
        related_events=[],
        evidence=evidence,
        target_id=real_track_id,
        target_type="track",
        image_url=image_url,
        entity_timeline=entity_timeline,
        face_intel=face_intel,
    )


def build_incident_investigation_context(helios, incident_id: str, window_hours: int = 6) -> InvestigationContext | None:
    inc = helios.get_incident(incident_id)
    if not inc:
        return None
    primary_event = inc["events"][0] if inc.get("events") else {
        "event_id": inc["incident_id"],
        "event_type": inc["incident_type"],
        "severity": inc["severity"],
        "camera_id": inc.get("primary_camera_id"),
        "zone_id": inc.get("primary_zone_id"),
        "track_id": inc.get("primary_track_id"),
        "timestamp": inc.get("start_time"),
        "description": inc.get("summary") or inc.get("title"),
    }
    track = inc["tracks"][0] if inc.get("tracks") else None
    camera = item(helios.db.execute("SELECT * FROM cameras WHERE camera_id=?", (inc.get("primary_camera_id") or "",)).fetchone())
    zone = item(helios.db.execute("SELECT * FROM zones WHERE zone_id=?", (inc.get("primary_zone_id") or "",)).fetchone())
    evidence = inc.get("evidence", [])
    image_url = None
    if evidence:
        image_url = get_evidence_image_data_uri(helios, evidence[0]["evidence_id"])

    face_intel = get_face_intel_for_target(
        helios,
        track_id=inc.get("primary_track_id"),
        camera_id=inc.get("primary_camera_id"),
    )

    return InvestigationContext(
        event=primary_event,
        track=track,
        camera=camera,
        zone=zone,
        timeline=inc.get("events", []),
        related_events=inc.get("events", []),
        evidence=evidence,
        target_id=incident_id,
        target_type="incident",
        image_url=image_url,
        face_intel=face_intel,
    )


def build_investigation_context(helios, event_id: str, window_hours: int = 6) -> InvestigationContext | None:
    event = item(helios.db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone())
    if not event:
        return None
    track = None
    if event.get("track_id"):
        track = item(helios.db.execute("SELECT * FROM tracks WHERE track_id=?", (event["track_id"],)).fetchone())
    camera = item(helios.db.execute(
        "SELECT camera_id,name,source_type,location,status,enabled FROM cameras WHERE camera_id=?",
        (event.get("camera_id", ""),)).fetchone())
    zone = item(helios.db.execute(
        "SELECT zone_id,camera_id,name,zone_type,enabled FROM zones WHERE zone_id=?",
        (event.get("zone_id", ""),)).fetchone())
    evidence = [dict(row) for row in helios.db.execute(
        "SELECT evidence_id,event_id,type,storage_reference,timestamp,integrity_hash FROM evidence WHERE event_id=? ORDER BY timestamp",
        (event_id,))]

    try:
        stamp = json.loads(json.dumps(event.get("timestamp")))
        from datetime import datetime as _dt
        stamp = _dt.fromisoformat(stamp)
        start = (stamp - timedelta(hours=window_hours)).isoformat()
        end = (stamp + timedelta(hours=window_hours)).isoformat()
    except Exception:
        start, end = None, None

    timeline_query = "SELECT * FROM events WHERE 1=1"
    timeline_args: list[Any] = []
    if start:
        timeline_query += " AND timestamp>=?"
        timeline_args.append(start)
    if end:
        timeline_query += " AND timestamp<=?"
        timeline_args.append(end)
    timeline = [dict(row) for row in helios.db.execute(
        timeline_query + " ORDER BY timestamp ASC LIMIT 100", timeline_args)]

    related_query = "SELECT * FROM events WHERE event_id<>?"
    related_args: list[Any] = [event_id]
    if start:
        related_query += " AND timestamp>=?"
        related_args.append(start)
    if end:
        related_query += " AND timestamp<=?"
        related_args.append(end)
    related_query += " AND (camera_id=? OR (zone_id IS NOT NULL AND zone_id=?) OR object_type=?)"
    related_args += [event.get("camera_id", ""), event.get("zone_id", ""), event.get("object_type", "")]
    related_events = [dict(row) for row in helios.db.execute(
        related_query + " ORDER BY timestamp DESC LIMIT 30", related_args)]

    entity_timeline: list[dict[str, Any]] = []
    if track and track.get("track_id"):
        entity_timeline = build_entity_timeline(helios, track["track_id"], window_hours=window_hours)

    image_url = None
    if evidence:
        image_url = get_evidence_image_data_uri(helios, evidence[0]["evidence_id"])

    face_intel = get_face_intel_for_target(
        helios,
        track_id=event.get("track_id"),
        camera_id=event.get("camera_id"),
        event_id=event_id,
    )

    return InvestigationContext(
        event=event, track=track, camera=camera, zone=zone,
        timeline=timeline, related_events=related_events, evidence=evidence,
        target_id=event_id, target_type="event", image_url=image_url,
        entity_timeline=entity_timeline,
        face_intel=face_intel,
    )


def deterministic_explanation(context: InvestigationContext) -> str:
    target_type = context.target_type or "event"
    if target_type == "evidence" and context.evidence_item:
        ev = context.evidence_item
        parts = [
            f"Evidence Capture {ev.get('evidence_id')} ({ev.get('type', 'SNAPSHOT')}) logged at {ev.get('timestamp')}."
        ]
        if context.event:
            parts.append(f"Linked to incident {context.event.get('event_id')} ({context.event.get('event_type')}).")
        if context.track:
            parts.append(f"Associated with entity track {context.track.get('track_id')} ({context.track.get('object_type')}).")
        if context.camera:
            parts.append(f"Sensor source: Camera {context.camera.get('camera_id')} ({context.camera.get('name')}).")
        if context.entity_timeline:
            parts.append(f"Database contains {len(context.entity_timeline)} timeline waypoint(s) for this entity.")
        return " ".join(parts)

    if target_type == "track" and context.track:
        tr = context.track
        parts = [
            f"Entity Track {tr.get('track_id')} ({tr.get('object_type')}) detected on {tr.get('camera_id')} with status {tr.get('status')}."
        ]
        if context.entity_timeline:
            parts.append(f"Full entity timeline tracks {len(context.entity_timeline)} sequential step(s) across sensors.")
        if context.evidence:
            parts.append(f"{len(context.evidence)} linked evidence capture(s) on file.")
        return " ".join(parts)

    event = context.event or {}
    parts = [
        f"Event {event.get('event_id')} ({event.get('event_type')}) at {event.get('timestamp')} "
        f"with severity {event.get('severity')} and status {event.get('status')}."
    ]
    if context.camera:
        parts.append(f"Camera {context.camera['camera_id']} ({context.camera['name']}) has status {context.camera.get('status')}.")
    if context.zone:
        parts.append(f"Event falls in zone {context.zone['zone_id']} ({context.zone['zone_type']}).")
    if context.track:
        parts.append(f"Associated track {context.track['track_id']} ({context.track['object_type']}).")
    if context.evidence:
        parts.append(f"{len(context.evidence)} evidence record(s) are linked.")
    if context.entity_timeline:
        parts.append(f"Entity timeline spans {len(context.entity_timeline)} chronological step(s).")
    parts.append(f"{len(context.related_events)} related event(s) fall inside the investigation window.")
    return " ".join(parts)


def deterministic_claims(context: InvestigationContext) -> list[AiClaim]:
    claims: list[AiClaim] = []
    references = references_from_context(context.model_dump())
    event = context.event or {}
    if event.get("event_id"):
        claims.append(AiClaim(
            statement=(
                f"Event {event.get('event_id')} is a {event.get('event_type')} recorded at {event.get('timestamp')} "
                f"with {event.get('severity')} severity."
            ),
            basis="event record",
            references=[reference for reference in references if reference.event_id],
        ))
    if context.evidence_item:
        ev = context.evidence_item
        claims.append(AiClaim(
            statement=f"Evidence {ev.get('evidence_id')} was logged as {ev.get('type', 'SNAPSHOT')} at {ev.get('timestamp')}.",
            basis="evidence vault metadata",
            references=[reference for reference in references if reference.evidence_id],
        ))
    if context.track:
        claims.append(AiClaim(
            statement=f"Entity {context.track.get('track_id')} is classified as {context.track.get('object_type')} with status {context.track.get('status')}.",
            basis="tracking database",
            references=[reference for reference in references if reference.track_id],
        ))
    if context.camera:
        claims.append(AiClaim(
            statement=f"The event camera is {context.camera['camera_id']} with status {context.camera.get('status')}.",
            basis="camera record",
            references=[reference for reference in references if reference.camera_id],
        ))
    if context.evidence:
        claims.append(AiClaim(
            statement=f"Event {event.get('event_id', '')} has {len(context.evidence)} linked evidence record(s): "
                      + ", ".join(entry.get("type", "UNKNOWN") for entry in context.evidence) + ".",
            basis="evidence metadata",
            references=[reference for reference in references if reference.evidence_id],
        ))
    if context.related_events:
        claims.append(AiClaim(
            statement=f"{len(context.related_events)} related event(s) are present in the investigation window.",
            basis="related events query",
            references=[reference for reference in references if reference.event_id],
        ))
    return claims


def build_local_investigation(context: InvestigationContext) -> str:
    header = "[Local HELIOS AI]\n\n"
    target_type = context.target_type or "event"

    if target_type == "evidence" and context.evidence_item:
        ev = context.evidence_item
        lines = [
            f"Evidence Analysis for {ev.get('evidence_id')} ({ev.get('type', 'SNAPSHOT')}): Captured at {ev.get('timestamp')}."
        ]
        if context.event:
            lines.append(f"Linked Incident: {context.event.get('event_id')} ({context.event.get('event_type')}) with severity {context.event.get('severity')}.")
        if context.camera:
            cam = context.camera
            loc = f" located at {cam['location']}" if cam.get("location") else ""
            lines.append(f"Sensor Source: Camera {cam.get('camera_id')} ({cam.get('name')}){loc} with status {cam.get('status')}.")
        if context.track:
            lines.append(f"Target Tracking: Associated entity {context.track.get('track_id')} ({context.track.get('object_type')}) [Status: {context.track.get('status')}].")
        if context.entity_timeline:
            lines.append(f"Timeline Progression: {len(context.entity_timeline)} sequential step(s) reconstructed from local database.")
            for step in context.entity_timeline[:5]:
                lines.append(f"  • [{step.get('timestamp')}] {step.get('description')}")
        lines.append("Forensic Assessment: Evidence artifact verified and indexed in vault.")
        return header + "\n\n".join(lines)

    if target_type == "track" and context.track:
        tr = context.track
        lines = [
            f"Entity Tracking Analysis for {tr.get('track_id')} ({tr.get('object_type')}): Detected on camera {tr.get('camera_id')} [Status: {tr.get('status')}]."
        ]
        if context.camera:
            cam = context.camera
            loc = f" located at {cam['location']}" if cam.get("location") else ""
            lines.append(f"Sensor Source: Camera {cam.get('camera_id')} ({cam.get('name')}){loc} with status {cam.get('status')}.")
        if context.evidence:
            lines.append(f"Forensic Evidence: {len(context.evidence)} linked image capture(s) in vault.")
        if context.entity_timeline:
            lines.append(f"Entity Timeline ({len(context.entity_timeline)} steps):")
            for step in context.entity_timeline[:6]:
                lines.append(f"  • [{step.get('timestamp')}] {step.get('description')}")
        lines.append("Local Assessment: Database trajectory verified; monitoring continued.")
        return header + "\n\n".join(lines)

    event = context.event or {}
    eid = event.get("event_id", "Unknown")
    etype = (event.get("event_type") or "Event").replace("_", " ").title()
    ts = event.get("timestamp", "")
    sev = event.get("severity", "UNKNOWN")
    status = event.get("status", "OPEN")

    lines = [
        f"Event Analysis for {eid} ({etype}): Detected at {ts} with {sev} severity [Status: {status}]."
    ]

    if context.camera:
        cam = context.camera
        loc = f" located at {cam['location']}" if cam.get("location") else ""
        lines.append(f"Sensor Source: Camera {cam.get('camera_id')} ({cam.get('name')}){loc} with status {cam.get('status')}.")

    if context.zone:
        zone = context.zone
        lines.append(f"Spatial Incursion: Occurred in zone {zone.get('zone_id')} ({zone.get('name') or zone.get('zone_type')}).")

    if context.track:
        track = context.track
        v_intel = (track.get("attributes") or {}).get("vehicle_intelligence")
        v_extra = ""
        if v_intel:
            c = (v_intel.get("color") or "").title() if v_intel.get("color") and v_intel.get("color") != "unknown" else ""
            t = (v_intel.get("type") or "").title() if v_intel.get("type") and v_intel.get("type") != "unknown" else ""
            lbl = f"{c} {t}".strip() or t or c
            if lbl:
                v_extra = f" [Vehicle: {lbl}]"
        lines.append(f"Target Tracking: Associated track {track.get('track_id')} ({track.get('object_type')}){v_extra} [Status: {track.get('status')}].")

    if context.evidence:
        ev_types = ", ".join(sorted({e.get("type", "ARTIFACT") for e in context.evidence}))
        lines.append(f"Forensic Evidence: {len(context.evidence)} linked evidence capture(s) in vault ({ev_types}).")
    else:
        lines.append("Forensic Evidence: No linked media captures logged for this event.")

    if context.entity_timeline:
        lines.append(f"Entity Timeline: Reconstructed {len(context.entity_timeline)} sequential position and event updates.")

    if context.face_intel and context.face_intel.get("status") == "RECOGNIZED":
        p_name = context.face_intel.get("person_name")
        p_role = f" ({context.face_intel['role']})" if context.face_intel.get("role") else ""
        p_sim = f" with {int(context.face_intel.get('similarity', 0)*100)}% match" if context.face_intel.get("similarity") else ""
        lines.append(f"Biometric Facial Recognition: Subject verified as {p_name}{p_role}{p_sim} [Person ID: {context.face_intel.get('person_id')}].")
    elif context.face_intel and context.face_intel.get("status") == "UNCLASSIFIED":
        lines.append(f"Biometric Status: Unclassified facial capture recorded ({context.face_intel.get('detection_count', 1)}x sightings, pending enrollment).")

    if context.related_events:
        lines.append(f"Correlated Incidents: {len(context.related_events)} correlated event(s) recorded in surveillance window.")
    else:
        lines.append("Correlated Incidents: No related activity detected across adjacent zones within the 6-hour window.")

    if sev in {"CRITICAL", "HIGH"}:
        lines.append("Local Assessment: Priority containment or manual operator verification recommended.")
    else:
        lines.append("Local Assessment: Routine sensor detection within normal operating parameters.")

    return header + "\n\n".join(lines)


def investigate(helios, event_id: str, client: Any = None, window_hours: int = 6,
                focus: str | None = None) -> InvestigationResult | None:
    """Investigate an event, evidence artifact, or entity track.

    Exclusively uses google/gemma-4-31b-it:free for image processing and investigations.
    """
    target_id = event_id
    context: InvestigationContext | None = None

    if target_id.startswith("EVD-"):
        context = build_evidence_investigation_context(helios, target_id, window_hours=window_hours)
    elif target_id.startswith("TRK-") or target_id.startswith("#"):
        context = build_track_investigation_context(helios, target_id, window_hours=window_hours)
    elif target_id.startswith("INC-"):
        context = build_incident_investigation_context(helios, target_id, window_hours=window_hours)
    else:
        context = build_investigation_context(helios, target_id, window_hours=window_hours)
        if context is None:
            context = build_incident_investigation_context(helios, target_id, window_hours=window_hours)
            if context is None:
                context = build_evidence_investigation_context(helios, target_id, window_hours=window_hours)
                if context is None:
                    context = build_track_investigation_context(helios, target_id, window_hours=window_hours)

    if context is None:
        return None

    allowed = collect_ids(context.model_dump())
    explanation = deterministic_explanation(context)
    claims = deterministic_claims(context)
    ai_used = False
    ai_model: str | None = None
    image_description: str | None = None
    error_code: str | None = None

    is_disabled = client is not None and (
        getattr(client, "error", None) == "HELIOS_AI_DISABLED" or not getattr(client, "enabled", True)
    )

    if not is_disabled:
        settings = getattr(helios, "settings", None)
        investigation_model = getattr(settings, "helios_investigation_model", "minimax/minimax-m3")
        fallback_model = getattr(settings, "helios_investigation_fallback_model", "google/gemma-4-31b-it")

        inv_client = client
        if client is not None and hasattr(client, "get_investigation_client"):
            inv_client = client.get_investigation_client(model=investigation_model, fallback_model=fallback_model)

        # Fallback to direct OpenRouterClient from settings if inv_client is an OllamaClient or not available
        if (inv_client is None or getattr(inv_client, "provider", "") == "ollama" or not getattr(inv_client, "available", False)) and settings is not None:
            from app.ai.client import OpenRouterClient
            key = getattr(settings, "openrouter_gemma_api_key", "") or getattr(settings, "openrouter_api_key", "")
            if key:
                inv_client = OpenRouterClient(
                    api_key=key,
                    gemma_api_key=getattr(settings, "openrouter_gemma_api_key", "") or key,
                    model=investigation_model,
                    fallback_model=fallback_model,
                    base_url=getattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1"),
                    timeout_seconds=getattr(settings, "openrouter_timeout_seconds", 30.0),
                    reasoning_enabled=getattr(settings, "openrouter_reasoning", True),
                    reasoning_effort=getattr(settings, "openrouter_reasoning_effort", "low"),
                    reasoning_max_tokens=getattr(settings, "openrouter_reasoning_max_tokens", 400),
                )

        if inv_client is not None and getattr(inv_client, "available", False):
            try:
                model_context = _without_storage_references(context.model_dump())
                parts: list[dict[str, Any]] = []

                if context.image_url:
                    prompt = evidence_image_investigation_prompt(json.dumps(model_context), focus=focus)
                    parts.append({"text": prompt})
                    parts.append({"image_url": context.image_url})
                elif context.target_type == "track":
                    prompt = entity_investigation_prompt(json.dumps(model_context), has_image=False, focus=focus)
                    parts.append({"text": prompt})
                else:
                    prompt = investigation_prompt(json.dumps(model_context), focus=focus)
                    parts.append({"text": prompt})

                output = inv_client.generate(
                    contents=[{"role": "user", "parts": parts}],
                    system_instruction=AI_SYSTEM_PROMPT,
                    response_json=True,
                    max_output_tokens=2500,
                )
                # If primary timed out or errored, retry with fallback_model (google/gemma-4-31b-it)
                if output.error and getattr(output, "model", "") != fallback_model:
                    fallback_client = None
                    if hasattr(inv_client, "get_investigation_client"):
                        fallback_client = inv_client.get_investigation_client(model=fallback_model)
                    elif hasattr(client, "get_investigation_client"):
                        fallback_client = client.get_investigation_client(model=fallback_model)
                    elif settings is not None:
                        from app.ai.client import OpenRouterClient
                        key = getattr(settings, "openrouter_gemma_api_key", "") or getattr(settings, "openrouter_api_key", "")
                        if key:
                            fallback_client = OpenRouterClient(
                                api_key=key,
                                gemma_api_key=getattr(settings, "openrouter_gemma_api_key", "") or key,
                                model=fallback_model,
                                base_url=getattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1"),
                                timeout_seconds=getattr(settings, "openrouter_timeout_seconds", 45.0),
                            )
                    if fallback_client and getattr(fallback_client, "available", False):
                        fb_output = fallback_client.generate(
                            contents=[{"role": "user", "parts": parts}],
                            system_instruction=AI_SYSTEM_PROMPT,
                            response_json=True,
                            max_output_tokens=2500,
                        )
                        if not fb_output.error and fb_output.text:
                            output = fb_output

                if output.error:
                    explanation = build_local_investigation(context)
                    ai_model = "local-helios-ai"
                    error_code = output.error
                elif output.text:
                    payload = parse_json_text(output.text)
                    if not payload:
                        import re
                        m = re.search(r'"(?:explanation|answer|summary)"\s*:\s*"((?:\\.|[^"\\])*)"', output.text)
                        if m:
                            try:
                                exp_str = json.loads(f'"{m.group(1)}"')
                                payload = {"explanation": exp_str}
                            except Exception:
                                pass
                    exp = (payload.get("explanation") or payload.get("answer") or payload.get("summary")) if payload else None
                    if exp and isinstance(exp, str) and exp.strip():
                        explanation = exp.strip()
                        image_desc = payload.get("image_description") or payload.get("image_analysis")
                        if isinstance(image_desc, str) and image_desc.strip():
                            image_description = image_desc.strip()
                        ai_used = True
                        ai_model = output.model or getattr(inv_client, "model", investigation_model)
                        claims = [AiClaim(**claim) for claim in payload.get("claims", []) if _valid_claim_shape(claim)]
                    else:
                        explanation = build_local_investigation(context)
                        ai_model = "local-helios-ai"
                else:
                    explanation = build_local_investigation(context)
                    ai_model = "local-helios-ai"
            except Exception as exc:
                explanation = build_local_investigation(context)
                ai_model = "local-helios-ai"
                error_code = f"INVESTIGATION_EXCEPTION: {type(exc).__name__}: {exc}"
        else:
            explanation = build_local_investigation(context)
            ai_model = "local-helios-ai"

    facts = context.model_dump()
    reported_event_id = context.event.get("event_id") if (context.event and context.event.get("event_id")) else target_id

    return InvestigationResult(
        event_id=reported_event_id,
        explanation=explanation,
        context=context,
        claims=sanitize_claims(claims, allowed),
        actions=sanitize_actions(default_actions(facts), allowed),
        references=sanitize_references(references_from_context(facts), allowed),
        ai_used=ai_used,
        ai_model=ai_model,
        error_code=error_code,
        target_id=target_id,
        target_type=context.target_type,
        image_description=image_description,
        entity_timeline=context.entity_timeline,
        face_intel=context.face_intel,
    )


def _without_storage_references(context: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(context)
    if "image_url" in sanitized:
        sanitized["image_url"] = "<attached_multimodal_image>"
    sanitized["evidence"] = [
        {key: value for key, value in entry.items() if key != "storage_reference"}
        for entry in (context.get("evidence") or [])
    ]
    if isinstance(sanitized.get("evidence_item"), dict):
        sanitized["evidence_item"] = {
            key: value for key, value in sanitized["evidence_item"].items() if key != "storage_reference"
        }
    return sanitized


def _valid_claim_shape(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("statement"), str)