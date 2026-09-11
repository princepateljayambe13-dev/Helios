"""Natural-language assistant over HELIOS data using the registered backend tools."""
from __future__ import annotations
from datetime import UTC, datetime
from typing import Any

from app.ai.client import GeminiRawOutput
from app.ai.prompts import AI_SYSTEM_PROMPT, ASSISTANT_FINAL_FORMAT
from app.ai.references import (collect_ids, parse_json_text, sanitize_actions,
                               sanitize_claims, sanitize_references)
from app.ai.schemas import AIResponse, AiAction, AiClaim, ChatMessage, Reference
from app.ai.tools import TOOL_DECLARATIONS, execute_tool


def disabled_response(client: Any, question: str) -> AIResponse:
    return AIResponse(
        answer=(
            "The HELIOS AI Intelligence Layer is not available. Enable it with HELIOS_AI_ENABLED=true "
            "to ask questions about HELIOS data."
        ),
        ai_enabled=False,
        ai_model=None,
        grounded=False,
        error_code=getattr(client, "error", None) or "HELIOS_AI_UNAVAILABLE",
    )


def build_dataset_context(helios) -> tuple[str, set[str]]:
    """Build a rich, zero-latency live facility snapshot (<3ms) to ground the AI and seed allowed IDs."""
    allowed: set[str] = set()
    if not helios or not getattr(helios, "db", None):
        return "", allowed

    try:
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        cams = [dict(r) for r in helios.db.execute("SELECT camera_id, name, status, location FROM cameras").fetchall()]
        for c in cams:
            if c.get("camera_id"):
                allowed.add(c["camera_id"])
        online_cams = [c for c in cams if c.get("status") == "ONLINE"]
        offline_cams = [c for c in cams if c.get("status") != "ONLINE"]

        alerts = [dict(r) for r in helios.db.execute("SELECT alert_id, alert_type, severity, status, message, timestamp FROM alerts WHERE status='ACTIVE' ORDER BY timestamp DESC LIMIT 6").fetchall()]
        for a in alerts:
            if a.get("alert_id"):
                allowed.add(a["alert_id"])

        events = [dict(r) for r in helios.db.execute("SELECT event_id, event_type, camera_id, timestamp, severity, object_type FROM events ORDER BY timestamp DESC LIMIT 6").fetchall()]
        for e in events:
            if e.get("event_id"):
                allowed.add(e["event_id"])
            if e.get("camera_id"):
                allowed.add(e["camera_id"])

        tracks = [dict(r) for r in helios.db.execute("SELECT track_id, object_type, camera_id, speed, direction, movement_state, attributes FROM tracks WHERE status='ACTIVE' LIMIT 10").fetchall()]
        for t in tracks:
            if t.get("track_id"):
                allowed.add(t["track_id"])
            if t.get("camera_id"):
                allowed.add(t["camera_id"])

        zones = [dict(r) for r in helios.db.execute("SELECT zone_id, name, zone_type, camera_id FROM zones WHERE enabled=1").fetchall()]
        for z in zones:
            if z.get("zone_id"):
                allowed.add(z["zone_id"])
            if z.get("camera_id"):
                allowed.add(z["camera_id"])

        online_summary = ", ".join(f"{c['camera_id']} ({c.get('name') or 'Cam'})" for c in online_cams) or "None"
        offline_summary = ", ".join(f"{c['camera_id']} ({c.get('name') or 'Cam'})" for c in offline_cams) or "None"
        alerts_summary = "; ".join(f"{a['alert_id']}: {a.get('message') or a.get('alert_type')} [{a.get('severity', 'WARN')}]" for a in alerts) if alerts else "0 active alerts (Perimeter secure)"
        tracks_summary = "; ".join(
            f"{t['track_id']} ({t.get('object_type')}) on {t['camera_id']}: {t.get('movement_state', 'UNKNOWN')} ({t.get('speed', 0.0):.1f} px/s, {t.get('direction', 'N/A')})"
            for t in tracks[:6]
        ) if tracks else "0 active tracks"
        now_utc = datetime.now(UTC)
        events_formatted: list[str] = []
        events_3m_cnt = 0
        for e in events:
            ts = e.get("timestamp") or ""
            time_label = ""
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    time_label = f" at {dt.strftime('%H:%M:%S')} UTC"
                    if (now_utc - dt).total_seconds() <= 180:
                        events_3m_cnt += 1
                except Exception:
                    time_label = f" at {ts[-8:]}" if len(ts) >= 8 else ""
            events_formatted.append(f"{e['event_id']} ({e.get('event_type')}) on {e.get('camera_id')}{time_label} [{e.get('severity')}]")

        events_summary = "; ".join(events_formatted) if events_formatted else "0 recent events"
        zones_summary = ", ".join(f"{z['name']} ({z['zone_id']}) on {z.get('camera_id', 'all')}" for z in zones) if zones else "None configured"

        today_iso = datetime.now(UTC).strftime("%Y-%m-%d 00:00:00")
        try:
            beh_today_cnt = helios.db.execute("SELECT COUNT(*) FROM behavioral_events WHERE timestamp >= ?", (today_iso,)).fetchone()[0]
            top_beh_rows = helios.db.execute("SELECT behavior_id, track_id, camera_id, zone_id, anomaly_score, behavior_type FROM behavioral_events ORDER BY anomaly_score DESC LIMIT 4").fetchall()
            for b in top_beh_rows:
                if b["behavior_id"]:
                    allowed.add(b["behavior_id"])
                if b["track_id"]:
                    allowed.add(b["track_id"])
            top_beh_summary = "; ".join(f"{b['behavior_id']} (Track {b['track_id']}, Score {b['anomaly_score']}, {b['behavior_type']}) on {b['camera_id']}" for b in top_beh_rows) if top_beh_rows else "0 logged anomalies"
        except Exception:
            beh_today_cnt = 0
            top_beh_summary = "N/A"

        snapshot = (
            f"[LIVE HELIOS FACILITY STATE - AS OF {now_str} UTC]\n"
            f"- Cameras ({len(cams)} total): {len(online_cams)} online [{online_summary}], {len(offline_cams)} offline [{offline_summary}]\n"
            f"- Active Alerts & Threats ({len(alerts)}): {alerts_summary}\n"
            f"- Active Tracking Targets ({len(tracks)}): {tracks_summary}\n"
            f"- Behavioral Anomalies ({beh_today_cnt} today): {top_beh_summary}\n"
            f"- Recent Events ({len(events_formatted)} listed, {events_3m_cnt} in last 3 mins): {events_summary}\n"
            f"- Surveillance Zones & Fences: {zones_summary}\n"
            f"- Access Note: You have 100% full access to this live dataset snapshot. Answer operator queries directly and on-point. Use your registered tools if specific historical or deep queries are needed."
        )
        return snapshot, allowed
    except Exception:
        return "", allowed


def build_local_intel(helios, question: str) -> tuple[str, list[AiClaim], list[AiAction], list[Reference]]:
    header = "[Local HELIOS AI]\n\n"
    if not helios or not getattr(helios, "db", None):
        return header + "Local monitoring is active, but database records are currently unavailable.", [], [], []

    q = (question or "").lower()
    claims: list[AiClaim] = []
    actions: list[AiAction] = []
    references: list[Reference] = []

    try:
        cameras = [dict(row) for row in helios.db.execute("SELECT camera_id, name, status, location FROM cameras").fetchall()]
        events = [dict(row) for row in helios.db.execute("SELECT event_id, event_type, camera_id, timestamp, severity, object_type FROM events ORDER BY timestamp DESC LIMIT 10").fetchall()]
        alerts = [dict(row) for row in helios.db.execute("SELECT alert_id, alert_type, severity, status, message, event_id FROM alerts WHERE status='ACTIVE' ORDER BY timestamp DESC").fetchall()]
        tracks = [dict(row) for row in helios.db.execute("SELECT track_id, object_type, camera_id, status, speed, direction, movement_state FROM tracks WHERE status='ACTIVE'").fetchall()]
    except Exception as exc:
        return header + f"Local system active, but unable to query current records: {exc}", [], [], []

    total_cams = len(cameras)
    online_cams = [c for c in cameras if c.get("status") == "ONLINE"]
    offline_cams = [c for c in cameras if c.get("status") != "ONLINE"]
    active_alerts_cnt = len(alerts)
    recent_events_cnt = len(events)
    active_tracks_cnt = len(tracks)

    online_names = ", ".join(f"{c.get('name') or c.get('camera_id')} ({c.get('camera_id')})" for c in online_cams) or "None"
    offline_names = ", ".join(f"{c.get('name') or c.get('camera_id')} ({c.get('camera_id')})" for c in offline_cams) or "None"

    import json
    import re
    today_iso = datetime.now(UTC).strftime("%Y-%m-%d 00:00:00")

    is_behavior_query = any(k in q for k in ("behavior", "behaviour", "anomaly", "anomalies", "flagged", "unusual"))
    is_zone_score_query = ("highest" in q or "top" in q) and ("score" in q or "anomaly" in q or "zone" in q)
    is_related_cam_query = "related" in q and ("camera" in q or "cam" in q or "behaviour" in q or "behavior" in q)

    # 0. Behavioral Analytics queries
    if is_behavior_query or is_zone_score_query or is_related_cam_query:
        try:
            beh_today_cnt = helios.db.execute("SELECT COUNT(*) FROM behavioral_events WHERE timestamp >= ?", (today_iso,)).fetchone()[0]
        except Exception:
            beh_today_cnt = 0

        # Sub-case A: How many behavioral anomalies happened today?
        if any(k in q for k in ("how many", "count", "number")) and any(k in q for k in ("today", "happened", "detected", "anomalies", "anomaly")):
            top_today = [dict(r) for r in helios.db.execute(
                "SELECT behavior_id, track_id, camera_id, zone_id, anomaly_score, behavior_type, timestamp FROM behavioral_events WHERE timestamp >= ? ORDER BY anomaly_score DESC LIMIT 3",
                (today_iso,),
            ).fetchall()]
            if beh_today_cnt > 0:
                h_parts = [f"Track #{b['track_id']} in {b.get('zone_id') or 'area'} ({b['behavior_type'].replace('_', ' ')}, Score {b['anomaly_score']})" for b in top_today]
                text = f"There have been {beh_today_cnt} behavioral anomal{'ies' if beh_today_cnt != 1 else 'y'} recorded today. Notable cases: " + "; ".join(h_parts) + "."
                for b in top_today:
                    actions.append(AiAction(type="OPEN_TRACK", track_id=b["track_id"], label=f"Track {b['track_id']}"))
                    references.append(Reference(track_id=b["track_id"], camera_id=b["camera_id"], label=f"Anomaly {b['anomaly_score']}"))
            else:
                text = "There have been 0 behavioral anomalies recorded today. All monitored movement, dwell, and zone activities remain within normal baseline parameters."
            claims.append(AiClaim(statement=text, basis="behavioral analytics registry", references=references))

        # Sub-case B: Which zone had the highest anomaly score?
        elif any(k in q for k in ("which zone", "highest anomaly score", "highest score", "highest anomaly", "highest")):
            top_z_row = helios.db.execute(
                """SELECT zone_id, camera_id, track_id, behavior_type, anomaly_score, anomaly_reasons
                   FROM behavioral_events
                   WHERE zone_id IS NOT NULL AND zone_id != ''
                   ORDER BY anomaly_score DESC LIMIT 1"""
            ).fetchone()
            if top_z_row:
                zid = top_z_row["zone_id"]
                zscore = top_z_row["anomaly_score"]
                btype = top_z_row["behavior_type"].replace("_", " ")
                cam = top_z_row["camera_id"]
                trk = top_z_row["track_id"]
                text = f"Zone {zid} had the highest behavioral anomaly score of {zscore}/100 ({btype} on {cam}, Track #{trk})."
                actions.append(AiAction(type="OPEN_TRACK", track_id=trk, label=f"Track #{trk}"))
                references.append(Reference(track_id=trk, camera_id=cam, zone_id=zid, label=f"Score {zscore}"))
            else:
                text = "No zone has recorded an elevated behavioral anomaly score. All zone activity remains at baseline levels."
            claims.append(AiClaim(statement=text, basis="behavioral spatial deviation database", references=references))

        # Sub-case C: Why was Track 184 flagged?
        elif "flagged" in q or "why was" in q or "why" in q:
            # Look up track mentioned in query
            matched_row = None
            found_tid = None
            all_beh = [dict(r) for r in helios.db.execute("SELECT * FROM behavioral_events ORDER BY timestamp DESC LIMIT 30").fetchall()]
            for row in all_beh:
                t_str = str(row["track_id"]).lower().lstrip("#")
                if t_str in q:
                    matched_row = row
                    found_tid = row["track_id"]
                    break
            if not matched_row and all_beh:
                # Get highest score or latest anomaly
                matched_row = all_beh[0]
                found_tid = matched_row["track_id"]

            if matched_row:
                reasons = []
                if matched_row.get("anomaly_reasons"):
                    try:
                        reasons = json.loads(matched_row["anomaly_reasons"])
                    except Exception:
                        reasons = [matched_row["anomaly_reasons"]]
                r_text = ". ".join(reasons) if reasons else "Observable deviation from site baseline."
                text = (
                    f"Track #{found_tid} was flagged with a Behavioral Anomaly Score of {matched_row['anomaly_score']}/100 "
                    f"({matched_row['behavior_type'].replace('_', ' ')}) in {matched_row.get('zone_id') or 'facility'} on {matched_row['camera_id']}. "
                    f"Main reasons: {r_text} (Movement: {matched_row.get('movement_state')}, Speed: {matched_row.get('speed', 0.0):.1f} px/s, Direction: {matched_row.get('direction')}, Dwell: {int(matched_row.get('dwell_duration', 0))}s)."
                )
                actions.append(AiAction(type="OPEN_TRACK", track_id=str(found_tid), label=f"Track #{found_tid}"))
                references.append(Reference(track_id=str(found_tid), camera_id=matched_row["camera_id"], label=f"Score {matched_row['anomaly_score']}"))
            else:
                text = "No flagged behavioral anomalies were found matching that identifier."
            claims.append(AiClaim(statement=text, basis="behavioral observation rationale records", references=references))

        # Sub-case D: How long did the unusual behaviour last?
        elif any(k in q for k in ("how long", "last", "duration", "dwell")):
            matched_row = None
            all_beh = [dict(r) for r in helios.db.execute("SELECT * FROM behavioral_events ORDER BY timestamp DESC LIMIT 20").fetchall()]
            for row in all_beh:
                t_str = str(row["track_id"]).lower().lstrip("#")
                if t_str in q:
                    matched_row = row
                    break
            if not matched_row and all_beh:
                matched_row = all_beh[0]

            if matched_row:
                dwell_sec = float(matched_row.get("dwell_duration") or 0.0)
                dwell_label = f"{dwell_sec / 60.0:.1f} minutes ({int(dwell_sec)} seconds)" if dwell_sec >= 60.0 else f"{int(dwell_sec)} seconds"
                text = (
                    f"The unusual behaviour for Track #{matched_row['track_id']} lasted {dwell_label} "
                    f"in {matched_row.get('zone_id') or 'monitored area'} on {matched_row['camera_id']} "
                    f"(Behavioral Anomaly Score: {matched_row['anomaly_score']}/100, Type: {matched_row['behavior_type'].replace('_', ' ')})."
                )
                actions.append(AiAction(type="OPEN_TRACK", track_id=matched_row["track_id"], label=f"Track #{matched_row['track_id']}"))
                references.append(Reference(track_id=matched_row["track_id"], camera_id=matched_row["camera_id"], label=dwell_label))
            else:
                text = "No extended dwell or unusual behavioral duration records were found."
            claims.append(AiClaim(statement=text, basis="behavioral dwell tracking records", references=references))

        # Sub-case E: Which cameras had related behaviour?
        elif any(k in q for k in ("which camera", "related camera", "related behaviour", "related behavior", "across camera")):
            cross_rows = [dict(r) for r in helios.db.execute(
                "SELECT * FROM behavioral_events WHERE related_cameras IS NOT NULL AND related_cameras != '[]' ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()]
            matched = None
            for r in cross_rows:
                t_str = str(r["track_id"]).lower().lstrip("#")
                if t_str in q:
                    matched = r
                    break
            if not matched and cross_rows:
                matched = cross_rows[0]

            if matched:
                rel_cams = []
                try:
                    rel_cams = json.loads(matched["related_cameras"])
                except Exception:
                    rel_cams = [matched["camera_id"]]
                cam_sequence = " → ".join(rel_cams) if len(rel_cams) > 1 else (rel_cams[0] if rel_cams else matched["camera_id"])
                text = (
                    f"Related behaviour was observed across cameras: {', '.join(rel_cams)} (traversal sequence: {cam_sequence}) "
                    f"for Track #{matched['track_id']} with a Behavioral Anomaly Score of {matched['anomaly_score']}/100."
                )
                for c in rel_cams:
                    actions.append(AiAction(type="OPEN_CAMERA", camera_id=c, label=f"Feed {c}"))
                    references.append(Reference(camera_id=c, track_id=matched["track_id"], label=c))
            else:
                text = "No cross-camera related behaviour has been recorded in the active observation window."
            claims.append(AiClaim(statement=text, basis="cross-camera behavioral correlation records", references=references))

        else:
            top_anomalies = [dict(r) for r in helios.db.execute(
                "SELECT * FROM behavioral_events ORDER BY anomaly_score DESC LIMIT 4"
            ).fetchall()]
            if top_anomalies:
                items = []
                for b in top_anomalies:
                    items.append(f"Track #{b['track_id']} on {b['camera_id']} in {b.get('zone_id') or 'area'} (Score {b['anomaly_score']}, {b['behavior_type'].replace('_', ' ')})")
                    actions.append(AiAction(type="OPEN_TRACK", track_id=b["track_id"], label=f"Track #{b['track_id']}"))
                    references.append(Reference(track_id=b["track_id"], camera_id=b["camera_id"], label=f"Score {b['anomaly_score']}"))
                text = f"Behavioral analytics summary: {len(top_anomalies)} notable anomaly pattern(s) recorded. Top entries: " + "; ".join(items) + "."
            else:
                text = "Behavioral analytics is active with 0 anomalies recorded. All observable motion and dwell metrics conform to site baseline."
            claims.append(AiClaim(statement=text, basis="behavioral analytics database", references=references))

    # 1. Camera queries
    elif any(k in q for k in ("camera", "feed", "stream", "cam")):
        text = (
            f"We have {total_cams} camera(s) configured. "
            f"{len(online_cams)} online ({online_names}), "
            f"{len(offline_cams)} offline ({offline_names})."
        )
        for c in online_cams[:3]:
            actions.append(AiAction(type="OPEN_CAMERA", camera_id=c["camera_id"], label=f"Feed {c['camera_id']}"))
            references.append(Reference(camera_id=c["camera_id"], label=c.get("name") or c["camera_id"]))
        claims.append(AiClaim(statement=text, basis="camera configuration", references=references))

    # 2. Alert & threat queries
    elif any(k in q for k in ("alert", "threat", "danger", "warning", "alarm")):
        if active_alerts_cnt > 0:
            alert_details = "; ".join(f"{a['alert_id']}: {a.get('message') or a.get('alert_type')} ({a.get('severity', 'WARN')})" for a in alerts[:4])
            text = f"There are currently {active_alerts_cnt} active alert(s): {alert_details}."
            for a in alerts[:4]:
                ref = Reference(alert_id=a["alert_id"])
                references.append(ref)
                if a.get("event_id"):
                    actions.append(AiAction(type="INVESTIGATE_EVENT", event_id=a["event_id"], label=f"Investigate {a['alert_id']}"))
            claims.append(AiClaim(statement=text, basis="active alert registry", references=references))
        else:
            text = "There are currently 0 active alerts. The facility perimeter is secure."
            claims.append(AiClaim(statement=text, basis="active alert registry"))

    # 3. Movement & Speed Intelligence queries
    elif any(k in q for k in ("speed", "fast", "running", "walking", "stationary", "direction", "heading", "moving fast", "velocity")) and not any(k in q for k in ("thread", "journey", "loiter", "dwell", "storyline")):
        all_threads = helios.get_all_threads(limit=30)
        is_running_query = "running" in q
        is_walking_query = "walking" in q
        is_stationary_query = any(k in q for k in ("stationary", "stopped", "idle"))
        is_fast_query = any(k in q for k in ("fast", "speeding", "high speed"))

        matching = list(all_threads)
        if is_running_query:
            matching = [t for t in all_threads if t.get("movement_state") == "RUNNING"]
        elif is_walking_query:
            matching = [t for t in all_threads if t.get("movement_state") == "WALKING"]
        elif is_stationary_query:
            matching = [t for t in all_threads if t.get("movement_state") == "STATIONARY"]
        elif is_fast_query:
            matching = [t for t in all_threads if t.get("movement_state") == "FAST" or (t.get("speed") or 0.0) > 30.0]

        if matching:
            matching.sort(key=lambda t: t.get("speed") or 0.0, reverse=True)
            summaries = []
            for t in matching[:4]:
                label = t.get("vehicle_label") or t.get("object_type", "Target").capitalize()
                spd = t.get("speed", 0.0)
                unit = t.get("speed_unit", "px/s")
                kmh_str = f" ({t['speed_kmh']:.1f} km/h)" if t.get("speed_kmh") is not None else ""
                dir_str = t.get("direction", "STATIONARY")
                state = t.get("movement_state", "UNKNOWN")
                dist = t.get("distance_travelled", 0.0)
                summaries.append(f"{label} ({t['track_id']}) on {t['camera_id']}: {state} at {spd:.1f} {unit}{kmh_str}, heading {dir_str}, distance {dist:.1f}px")
                actions.append(AiAction(type="OPEN_TRACK", track_id=t["track_id"], label=f"Track {t['track_id']}"))
                references.append(Reference(track_id=t["track_id"], camera_id=t["camera_id"], label=label))

            criteria_desc = "running targets" if is_running_query else ("walking targets" if is_walking_query else ("stationary targets" if is_stationary_query else "active movements"))
            text = f"Movement intelligence detected {len(matching)} matching target(s) for {criteria_desc}. Highlights: " + "; ".join(summaries) + "."
            claims.append(AiClaim(statement=text, basis="speed and trajectory movement tracking", references=references))
        else:
            text = f"Movement intelligence: No targets currently matching the requested movement state or speed criteria across {len(all_threads)} active/recent tracks."
            claims.append(AiClaim(statement=text, basis="speed and trajectory movement tracking"))

    # 4. Vehicle Intelligence & Classification queries
    elif any(k in q for k in ("vehicle", "car", "suv", "sedan", "pickup", "truck", "hatchback", "van", "minivan", "bus", "motorcycle", "bicycle", "emergency vehicle")):
        veh_threads = helios.get_all_threads(limit=30, object_type="VEHICLE")
        types_to_check = [
            "suv", "pickup truck", "pickup", "hatchback", "taxi", "sedan",
            "heavy truck", "truck", "van", "minivan", "bus", "motorcycle",
            "bicycle", "emergency vehicle", "car"
        ]
        colors_to_check = ["black", "white", "gray", "silver", "red", "blue", "green", "yellow", "brown", "orange"]

        req_type = next((vt for vt in types_to_check if vt in q), None)
        req_color = next((vc for vc in colors_to_check if vc in q), None)

        matching = veh_threads
        if req_type:
            req_t_lower = req_type.lower()
            def type_matches(v_t: str, v_lbl: str) -> bool:
                combined = f"{v_t} {v_lbl}".lower()
                if req_t_lower == "truck":
                    return "truck" in combined
                if req_t_lower == "pickup":
                    return "pickup" in combined
                if req_t_lower == "car":
                    return any(k in combined for k in ("car", "sedan", "hatchback", "suv", "vehicle"))
                return req_t_lower in combined

            matching = [t for t in matching if type_matches(t.get("vehicle_type") or "", t.get("vehicle_label") or "")]
        if req_color:
            matching = [t for t in matching if req_color in (t.get("vehicle_color") or "").lower() or req_color in (t.get("vehicle_label") or "").lower()]

        if matching:
            v_summaries = []
            for t in matching[:4]:
                v_label = t.get("vehicle_label") or t.get("vehicle_type") or "Vehicle"
                dyn = t.get("movement_dynamic", "NORMAL").replace("_", " ").lower()
                v_summaries.append(f"{v_label} ({t['track_id']}) on {t['camera_id']} [{t['status']}, {dyn} movement, {t.get('threat_level', 'LOW')} threat]")
                actions.append(AiAction(type="OPEN_TRACK", track_id=t["track_id"], label=f"Track {v_label}"))
                references.append(Reference(track_id=t["track_id"], camera_id=t["camera_id"], label=v_label))
            filter_desc = f" matching {f'{req_color} ' if req_color else ''}{req_type.upper() if req_type else 'vehicles'}" if (req_type or req_color) else ""
            text = f"Vehicle intelligence: {len(matching)} vehicle track(s){filter_desc} recorded across camera feeds. Highlights: " + "; ".join(v_summaries) + "."
            claims.append(AiClaim(statement=text, basis="vehicle intelligence pipeline and tracking records", references=references))
        else:
            filter_desc = f" matching {f'{req_color} ' if req_color else ''}{req_type.upper() if req_type else 'criteria'}" if (req_type or req_color) else ""
            text = f"No vehicle tracks{filter_desc} are currently detected. Total vehicle sessions in memory: {len(veh_threads)}."
            claims.append(AiClaim(statement=text, basis="vehicle intelligence tracking database"))

    # 5. Activity Threads & Trajectory queries
    elif any(k in q for k in ("thread", "journey", "story", "handoff", "transition", "loiter", "dwell", "path", "storyline")):
        import re
        trk_match = re.search(r'(#[A-Z]-[A-Z0-9]{4,12}\b|\bTRK-[A-Z0-9]+\b)', question, re.IGNORECASE)
        if trk_match:
            target_tid = trk_match.group(0).upper()
            single = helios.get_track_thread(target_tid)
            if single:
                text = f"Activity thread for {target_tid}: {single.get('activity_story')} Timeline contains {len(single.get('timeline', []))} node(s) and {single.get('positions_count', 0)} position capture(s)."
                actions.append(AiAction(type="OPEN_TRACK", track_id=single["track_id"], label=f"View Story {single['track_id']}"))
                references.append(Reference(track_id=single["track_id"], camera_id=single["camera_id"], label=single.get("vehicle_label") or single["object_type"]))
                claims.append(AiClaim(statement=text, basis="activity thread story reconstruction", references=references))
            else:
                text = f"Activity thread for {target_tid} was not located in active or recent tracking archives."
                claims.append(AiClaim(statement=text, basis="activity thread database"))
        else:
            all_threads = helios.get_all_threads(limit=5)
            if all_threads:
                stories = []
                for t in all_threads[:3]:
                    stories.append(f"{t.get('vehicle_label') or t['object_type'].capitalize()} ({t['track_id']}): {t.get('activity_story')}")
                    actions.append(AiAction(type="OPEN_TRACK", track_id=t["track_id"], label=f"Track {t['track_id']}"))
                    references.append(Reference(track_id=t["track_id"], camera_id=t["camera_id"]))
                text = f"Activity threads tracking overview: {len(all_threads)} session(s) followed across feeds. " + " ".join(stories)
                claims.append(AiClaim(statement=text, basis="multi-camera activity threads tracking", references=references))
            else:
                text = "There are currently no active or recent activity threads recorded."
                claims.append(AiClaim(statement=text, basis="activity threads database"))

    # 6. Zones & Perimeter Fences
    elif any(k in q for k in ("zone", "fence", "restricted", "boundary", "perimeter")):
        try:
            zone_rows = [dict(row) for row in helios.db.execute("SELECT zone_id, camera_id, name, zone_type, enabled, capacity FROM zones").fetchall()]
        except Exception:
            zone_rows = []
        if zone_rows:
            z_details = ", ".join(f"{z['name']} ({z['zone_id']}, {z['zone_type']}, camera {z.get('camera_id')})" for z in zone_rows[:5])
            text = f"We have {len(zone_rows)} surveillance zone(s) configured: {z_details}."
            for z in zone_rows[:3]:
                actions.append(AiAction(type="OPEN_ZONE", zone_id=z["zone_id"], label=f"Zone {z['zone_id']}"))
                references.append(Reference(zone_id=z["zone_id"], camera_id=z.get("camera_id"), label=z["name"]))
            claims.append(AiClaim(statement=text, basis="zone configuration registry", references=references))
        else:
            text = "There are currently no surveillance zones configured in the system."
            claims.append(AiClaim(statement=text, basis="zone configuration registry"))

    # 7. Evidence / ANPR License Plates / Face Recognition
    elif any(k in q for k in ("plate", "license", "anpr", "face", "evidence", "photo", "capture", "snapshot")):
        try:
            ev_rows = [dict(row) for row in helios.db.execute("SELECT evidence_id, event_id, type, timestamp, metadata FROM evidence ORDER BY timestamp DESC LIMIT 15").fetchall()]
        except Exception:
            ev_rows = []
        if any(k in q for k in ("plate", "license", "anpr")):
            plate_ev = [e for e in ev_rows if "PLATE" in (e.get("type") or "").upper() or "plate" in (e.get("metadata") or "").lower()]
            if plate_ev:
                plates = []
                for pe in plate_ev[:4]:
                    meta = pe.get("metadata") or ""
                    plates.append(f"{pe['evidence_id']} ({meta or pe['type']})")
                    actions.append(AiAction(type="VIEW_EVIDENCE", evidence_id=pe["evidence_id"], label=f"Evidence {pe['evidence_id']}"))
                    references.append(Reference(evidence_id=pe["evidence_id"]))
                text = f"ANPR & License Plate Intelligence: {len(plate_ev)} plate capture(s) recorded in evidence storage. Highlights: " + "; ".join(plates) + "."
                claims.append(AiClaim(statement=text, basis="ANPR evidence registry", references=references))
            else:
                text = "ANPR Intelligence: No license plate captures currently recorded in the active evidence storage."
                claims.append(AiClaim(statement=text, basis="ANPR evidence registry"))
        elif any(k in q for k in ("face", "person capture")):
            face_ev = [e for e in ev_rows if "FACE" in (e.get("type") or "").upper() or "face" in (e.get("metadata") or "").lower()]
            if face_ev:
                faces = []
                for fe in face_ev[:4]:
                    meta = fe.get("metadata") or ""
                    faces.append(f"{fe['evidence_id']} ({meta or fe['type']})")
                    actions.append(AiAction(type="VIEW_EVIDENCE", evidence_id=fe["evidence_id"], label=f"Face {fe['evidence_id']}"))
                    references.append(Reference(evidence_id=fe["evidence_id"]))
                text = f"Face Intelligence: {len(face_ev)} face capture(s) in evidence records. Highlights: " + "; ".join(faces) + "."
                claims.append(AiClaim(statement=text, basis="face recognition evidence", references=references))
            else:
                text = "Face Intelligence: No face recognition captures found in current evidence records."
                claims.append(AiClaim(statement=text, basis="face recognition evidence"))
        else:
            text = f"Evidence Storage: {len(ev_rows)} evidence record(s) on file across security events."
            for e in ev_rows[:3]:
                actions.append(AiAction(type="VIEW_EVIDENCE", evidence_id=e["evidence_id"], label=f"Evidence {e['evidence_id']}"))
                references.append(Reference(evidence_id=e["evidence_id"]))
            claims.append(AiClaim(statement=text, basis="evidence storage records", references=references))

    # 8. System Status / Health / Logs
    elif any(k in q for k in ("system", "health", "log", "diagnostic", "vital", "performance", "pipeline", "service")):
        try:
            log_rows = [dict(row) for row in helios.db.execute("SELECT log_id, level, component, message FROM system_logs ORDER BY timestamp DESC LIMIT 4").fetchall()]
        except Exception:
            log_rows = []
        log_details = "; ".join(f"[{l['level']}] {l.get('component')}: {l['message']}" for l in log_rows) if log_rows else "Clean pipeline operation"
        text = (
            f"System Health Overview: {total_cams} cameras ({len(online_cams)} online, {len(offline_cams)} offline), "
            f"{active_alerts_cnt} active alert(s), {active_tracks_cnt} active track(s). Recent logs: {log_details}."
        )
        claims.append(AiClaim(statement=text, basis="system health and logs snapshot"))

    # 9. Events / Daily overview queries
    elif any(k in q for k in ("event", "detect", "motion", "uav", "human", "fire", "smoke", "what happened", "summar", "today")):
        if recent_events_cnt > 0:
            top_event = events[0]
            desc = top_event.get("event_type", "Event").replace("_", " ").title()
            text = (
                f"Today's local overview: {recent_events_cnt} recent event(s) recorded across the facility. "
                f"Most recent: {desc} on camera {top_event.get('camera_id')} at {top_event.get('timestamp', '')[:19].replace('T', ' ')} UTC. "
                f"Active alerts: {active_alerts_cnt}. Cameras: {len(online_cams)} online, {len(offline_cams)} offline."
            )
            actions.append(AiAction(type="INVESTIGATE_EVENT", event_id=top_event["event_id"], label=f"Investigate {top_event['event_id']}"))
            references.append(Reference(event_id=top_event["event_id"], camera_id=top_event.get("camera_id")))
            claims.append(AiClaim(statement=text, basis="daily event log", references=references))
        else:
            text = (
                f"Today's local overview: 0 events and 0 active alerts recorded today. "
                f"Cameras: {len(online_cams)} online, {len(offline_cams)} offline. Perimeter is quiet."
            )
            claims.append(AiClaim(statement=text, basis="daily event log"))

    # 10. Tracking targets
    elif any(k in q for k in ("track", "target", "person")):
        if active_tracks_cnt > 0:
            text = f"There are currently {active_tracks_cnt} active track(s) being followed across surveillance cameras."
            for t in tracks[:3]:
                actions.append(AiAction(type="OPEN_TRACK", track_id=t["track_id"], label=f"Track {t['track_id']}"))
                references.append(Reference(track_id=t["track_id"], camera_id=t["camera_id"]))
            claims.append(AiClaim(statement=text, basis="live track registry", references=references))
        else:
            text = "There are currently no active tracking sessions in progress."
            claims.append(AiClaim(statement=text, basis="live track registry"))

    # 11. Generic fallback
    else:
        text = (
            f"Operating in local mode with live sensor data. "
            f"Currently monitoring {total_cams} cameras ({len(online_cams)} online, {len(offline_cams)} offline), "
            f"{active_alerts_cnt} active alert(s), and {recent_events_cnt} recent event(s)."
        )
        claims.append(AiClaim(statement=text, basis="system health snapshot"))

    return header + text, claims, actions, references


def build_local_answer(helios, question: str) -> str:
    text, _, _, _ = build_local_intel(helios, question)
    return text


def extract_grounded_entities(text: str, allowed: set[str]) -> tuple[list[Reference], list[AiAction]]:
    import re
    references: list[Reference] = []
    actions: list[AiAction] = []
    seen_refs = set()
    seen_actions = set()

    for item_id in allowed:
        if re.search(r"\b" + re.escape(item_id) + r"\b", text, re.IGNORECASE):
            if item_id.startswith("CAM-"):
                ref_key = f"cam:{item_id}"
                if ref_key not in seen_refs:
                    seen_refs.add(ref_key)
                    references.append(Reference(camera_id=item_id, label=item_id))
                act_key = f"open_cam:{item_id}"
                if act_key not in seen_actions:
                    seen_actions.add(act_key)
                    actions.append(AiAction(type="OPEN_CAMERA", camera_id=item_id, label=f"Feed {item_id}"))
            elif item_id.startswith("ALR-") or "ALERT" in item_id.upper():
                ref_key = f"alr:{item_id}"
                if ref_key not in seen_refs:
                    seen_refs.add(ref_key)
                    references.append(Reference(alert_id=item_id, label=item_id))
            elif item_id.startswith("EVT-"):
                ref_key = f"evt:{item_id}"
                if ref_key not in seen_refs:
                    seen_refs.add(ref_key)
                    references.append(Reference(event_id=item_id, label=item_id))
                act_key = f"inv_evt:{item_id}"
                if act_key not in seen_actions:
                    seen_actions.add(act_key)
                    actions.append(AiAction(type="INVESTIGATE_EVENT", event_id=item_id, label=f"Investigate {item_id}"))
            elif item_id.startswith("TRK-") or item_id.startswith("#"):
                ref_key = f"trk:{item_id}"
                if ref_key not in seen_refs:
                    seen_refs.add(ref_key)
                    references.append(Reference(track_id=item_id, label=item_id))
                act_key = f"open_trk:{item_id}"
                if act_key not in seen_actions:
                    seen_actions.add(act_key)
                    actions.append(AiAction(type="OPEN_TRACK", track_id=item_id, label=f"Track {item_id}"))
            elif item_id.startswith("ZONE-"):
                ref_key = f"zone:{item_id}"
                if ref_key not in seen_refs:
                    seen_refs.add(ref_key)
                    references.append(Reference(zone_id=item_id, label=item_id))
                act_key = f"open_zone:{item_id}"
                if act_key not in seen_actions:
                    seen_actions.add(act_key)
                    actions.append(AiAction(type="OPEN_ZONE", zone_id=item_id, label=f"Zone {item_id}"))
            elif item_id.startswith("EVD-"):
                ref_key = f"evd:{item_id}"
                if ref_key not in seen_refs:
                    seen_refs.add(ref_key)
                    references.append(Reference(evidence_id=item_id, label=item_id))
                act_key = f"view_evd:{item_id}"
                if act_key not in seen_actions:
                    seen_actions.add(act_key)
                    actions.append(AiAction(type="VIEW_EVIDENCE", evidence_id=item_id, label=f"Evidence {item_id}"))

    return references, actions


def local_helios_response(helios, question: str) -> AIResponse:
    answer, claims, actions, references = build_local_intel(helios, question)
    return AIResponse(
        answer=answer,
        ai_enabled=True,
        ai_model="local-helios-ai",
        grounded=bool(claims or references),
        error_code=None,
        claims=claims,
        actions=actions,
        references=references,
    )


def failed_response(client: Any, error_code: str, message: str = "") -> AIResponse:
    return AIResponse(
        answer=message or f"The HELIOS AI model encountered an error: {error_code}",
        ai_enabled=bool(getattr(client, "enabled", True)),
        ai_model=getattr(client, "model", None),
        grounded=False,
        error_code=error_code,
    )


def parse_ai_response(text: str, allowed: set[str], model: str | None, reasoning_details: Any = None) -> AIResponse:
    payload = parse_json_text(text)
    if payload is None:
        clean_text = text or ""
        import re
        ans_match = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', clean_text)
        if ans_match:
            try:
                import json
                extracted = json.loads(f'"{ans_match.group(1)}"')
                return AIResponse(
                    answer=extracted,
                    ai_enabled=True,
                    ai_model=model,
                    grounded=False,
                    error_code=None,
                    reasoning_details=reasoning_details,
                )
            except Exception:
                pass
        return AIResponse(
            answer=text or "The HELIOS AI returned an unreadable response.",
            ai_enabled=True,
            ai_model=model,
            grounded=False,
            error_code="INVALID_RESPONSE",
            reasoning_details=reasoning_details,
        )
    if isinstance(payload, dict) and "answer" not in payload:
        payload["answer"] = (
            payload.get("message") or
            payload.get("response") or
            payload.get("summary") or
            payload.get("text") or
            payload.get("output") or
            str(payload)
        )
    try:
        response = AIResponse(**payload)
    except Exception:
        answer = payload.get("answer") if isinstance(payload.get("answer"), str) else "The HELIOS AI response could not be validated."
        return AIResponse(
            answer=answer,
            ai_enabled=True,
            ai_model=model,
            grounded=False,
            error_code="SCHEMA_VALIDATION_FAILED",
            reasoning_details=reasoning_details,
        )
    response.answer = response.answer or "The HELIOS AI returned no answer."
    if response.answer.startswith("```"):
        lines = [l for l in response.answer.splitlines() if not l.startswith("```")]
        response.answer = "\n".join(lines).strip()
    response.claims = sanitize_claims(response.claims, allowed)
    response.actions = sanitize_actions(response.actions, allowed)
    response.references = sanitize_references(response.references, allowed)
    response.grounded = bool(response.references) or any(claim.references for claim in response.claims)
    response.ai_model = model
    response.reasoning_details = reasoning_details
    return response


def ask(helios, question: str, client: Any, history: list[ChatMessage] | None = None,
        max_rounds: int = 6, tools: list[dict[str, Any]] | None = None) -> AIResponse:
    question = (question or "").strip()
    if not question:
        return AIResponse(
            answer="Please provide a question about HELIOS data.",
            ai_enabled=bool(getattr(client, "available", False)),
            ai_model=getattr(client, "model", None),
            grounded=False,
            error_code="EMPTY_QUESTION",
        )
    if client is not None and (getattr(client, "error", None) == "HELIOS_AI_DISABLED" or not getattr(client, "enabled", True)):
        return disabled_response(client, question)
    if client is None or not getattr(client, "available", False):
        return local_helios_response(helios, question)

    snapshot, seed_allowed = build_dataset_context(helios)
    allowed: set[str] = set(seed_allowed)
    system_instruction = f"{AI_SYSTEM_PROMPT}\n\n{snapshot}" if snapshot else AI_SYSTEM_PROMPT

    declarations = tools if tools is not None else TOOL_DECLARATIONS
    messages: list[dict[str, Any]] = []
    for entry in history or []:
        role = "model" if entry.role == "assistant" else entry.role
        msg: dict[str, Any] = {"role": role, "parts": [{"text": entry.content}]}
        if getattr(entry, "reasoning_details", None) is not None:
            msg["reasoning_details"] = entry.reasoning_details
        messages.append(msg)
    messages.append({"role": "user", "parts": [{"text": question}]})

    if getattr(client, "provider", None) == "ollama":
        ollama_system = (
            "You are HELIOS AI, an intelligent security and surveillance assistant for facility monitoring.\n"
            "Use the live facility state snapshot below to answer operator questions accurately, concisely, and helpfully.\n\n"
            f"{snapshot}"
        ) if snapshot else AI_SYSTEM_PROMPT
        output = client.generate(
            contents=messages,
            system_instruction=ollama_system,
            tools=None,
            response_json=False,
        )
        if output.error or not output.text:
            return local_helios_response(helios, question)

        refs, acts = extract_grounded_entities(output.text, allowed)
        model_name = output.model or getattr(client, "model", "qwen3:4b")
        claims = (
            [AiClaim(statement=output.text[:200], basis=f"live facility telemetry and {model_name} analysis", references=refs)]
            if refs
            else []
        )
        return AIResponse(
            answer=output.text,
            claims=claims,
            actions=acts,
            references=refs,
            ai_enabled=True,
            ai_model=model_name,
            grounded=bool(refs or claims),
            error_code=None,
            reasoning_details=getattr(output, "reasoning_details", None),
        )

    rounds = max_rounds if max_rounds and max_rounds > 0 else 6
    interim: str | None = None
    tool_rounds = 0

    for _ in range(rounds):
        tool_rounds += 1
        output = client.generate(
            contents=messages, system_instruction=system_instruction,
            tools=declarations, response_json=False)
        if output.error and not output.tool_calls and not output.text:
            return local_helios_response(helios, question)
        if output.tool_calls:
            for call in output.tool_calls:
                result = execute_tool(helios, call.name, call.args)
                collect_ids(result, allowed)
                messages.append({"role": "function", "parts": [{
                    "function_response": {"name": call.name, "response": {"result": result}}}]})
            continue
        if output.text:
            interim = output.text
            # Fast-path: Check if output.text is already a complete valid JSON response matching AIResponse schema.
            # If so, return immediately without an unnecessary extra roundtrip to save 10-20 seconds!
            model_name = getattr(getattr(client, "_openrouter_client", None), "model", client.model) if getattr(output, "provider", None) == "openrouter" else getattr(client, "model", None)
            candidate_resp = parse_ai_response(
                interim,
                allowed,
                model=model_name,
                reasoning_details=getattr(output, "reasoning_details", None),
            )
            # If successfully parsed into a grounded answer with claims or references:
            if candidate_resp.error_code is None and candidate_resp.answer and not candidate_resp.answer.startswith("The HELIOS AI returned an unreadable response") and (candidate_resp.claims or candidate_resp.references):
                return candidate_resp
            break
        break

    messages.append({"role": "model", "parts": [{"text": interim or "I have gathered the relevant HELIOS data."}]})
    messages.append({"role": "user", "parts": [{"text": ASSISTANT_FINAL_FORMAT}]})

    final = client.generate(
        contents=messages, system_instruction=system_instruction,
        tools=None, response_json=True)
    if final.error and not final.text:
        # If final formatting failed but we had interim text from the model, return it directly
        if interim and interim != "Intermediate gathering.":
            return AIResponse(
                answer=interim,
                ai_enabled=True,
                ai_model=getattr(client, "model", None),
                grounded=bool(allowed),
                error_code=None,
            )
        return local_helios_response(helios, question)
    model_name = getattr(getattr(client, "_openrouter_client", None), "model", client.model) if getattr(final, "provider", None) == "openrouter" else getattr(client, "model", None)
    return parse_ai_response(
        final.text or "",
        allowed,
        model=model_name,
        reasoning_details=getattr(final, "reasoning_details", None),
    )


def ask_stream(helios, question: str, client: Any, history: list[ChatMessage] | None = None):
    question = (question or "").strip()
    if not question:
        yield "Please provide a question about HELIOS data."
        return
    if client is not None and (getattr(client, "error", None) == "HELIOS_AI_DISABLED" or not getattr(client, "enabled", True)):
        yield "The HELIOS AI Intelligence Layer is not available. Enable it with HELIOS_AI_ENABLED=true to ask questions about HELIOS data."
        return

    if client is not None and hasattr(client, "stream"):
        snapshot, _ = build_dataset_context(helios)
        ollama_system = (
            "You are HELIOS AI, an intelligent security and surveillance assistant for facility monitoring.\n"
            "Use the live facility state snapshot below to answer operator questions accurately, concisely, and helpfully.\n\n"
            f"{snapshot}"
        ) if snapshot else AI_SYSTEM_PROMPT
        messages: list[dict[str, Any]] = []
        for entry in history or []:
            role = "model" if entry.role == "assistant" else entry.role
            messages.append({"role": role, "parts": [{"text": entry.content}]})
        messages.append({"role": "user", "parts": [{"text": question}]})

        has_yielded = False
        try:
            for token in client.stream(contents=messages, system_instruction=ollama_system):
                has_yielded = True
                yield token
        except Exception:
            pass
        if has_yielded:
            return

    # Fallback to standard ask()
    resp = ask(helios, question, client, history=history)
    yield resp.answer