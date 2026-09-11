"""Core Behavioral Analytics Engine for HELIOS.

Evaluates observable surveillance telemetry from YOLO, ByteTrack, spatial zones,
movement intelligence, density metrics, loitering sessions, and normality baselines.
Computes the 7-signal Behavioral Anomaly Score (0–100) and persists events to SQLite.
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.behavioral.models import BehavioralAnomalyScoreBreakdown, BehavioralEvent, now_iso
from app.behavioral.scorer import calculate_behavioral_anomaly_score


class BehavioralAnalyticsEngine:
    """Detects, scores, and persists observable unusual behaviors across facilities."""

    def __init__(self, db: sqlite3.Connection, baseline_engine: Any = None):
        self.db = db
        self.baseline_engine = baseline_engine

    def evaluate_track_behavior(
        self,
        track: dict[str, Any],
        movement_snapshot: dict[str, Any] | None = None,
        zone_row: dict[str, Any] | None = None,
        density_data: dict[str, Any] | None = None,
        loitering_session: dict[str, Any] | None = None,
        events: list[dict[str, Any]] | None = None,
        evidence_ids: list[str] | None = None,
    ) -> BehavioralEvent | None:
        """Evaluate a track's observable telemetry and compute behavioral anomaly score."""
        track_id = str(track["track_id"])
        camera_id = str(track.get("camera_id") or "unknown")
        now_str = now_iso()

        # Extract movement state, speed, direction
        mov_state = (
            (movement_snapshot and movement_snapshot.get("movement_state"))
            or track.get("movement_state")
            or "STATIONARY"
        )
        speed = float(
            (movement_snapshot and movement_snapshot.get("speed"))
            or track.get("speed")
            or 0.0
        )
        direction = (
            (movement_snapshot and movement_snapshot.get("direction"))
            or track.get("direction")
            or "STATIONARY"
        )
        heading_deg = float(
            (movement_snapshot and movement_snapshot.get("heading_deg"))
            or track.get("heading")
            or 0.0
        )
        accel = float((movement_snapshot and movement_snapshot.get("acceleration")) or 0.0)
        mov_change = movement_snapshot.get("movement_change") if movement_snapshot else None

        # Zone & dwell info
        zone_id = (zone_row and zone_row.get("zone_id")) or track.get("zone_id")
        if not zone_id and zone_row:
            zone_id = zone_row.get("zone_id")

        first_seen = track.get("created_at") or track.get("first_seen") or now_str
        last_seen = track.get("last_seen_at") or track.get("last_seen") or now_str
        dwell_seconds = 0.0
        try:
            t0 = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            dwell_seconds = max(0.0, (t1 - t0).total_seconds())
        except Exception:
            dwell_seconds = 0.0

        if loitering_session and loitering_session.get("duration_seconds"):
            dwell_seconds = max(dwell_seconds, float(loitering_session["duration_seconds"]))

        # Retrieve zone baseline
        normal_dwell = 25.0
        normal_people = 3
        normal_activity = 30
        if self.baseline_engine and zone_id:
            try:
                base = self.baseline_engine.get_zone_baseline(zone_id)
                normal_dwell = float(base.get("normal_dwell_median") or 25.0)
                normal_people = int(base.get("normal_people_count") or 3)
                normal_activity = int(base.get("normal_activity") or 30)
            except Exception:
                pass

        # Query recent movement history for trajectory analysis
        recent_movements = self.db.execute(
            "SELECT speed, heading_deg, direction, movement_state, movement_change, timestamp FROM track_movements WHERE track_id=? ORDER BY timestamp DESC LIMIT 12",
            (track_id,),
        ).fetchall()

        # -------------------------------------------------------------
        # 1. MOVEMENT DEVIATION (20%)
        # Sudden speed change, sudden direction change, unusual movement pattern
        # -------------------------------------------------------------
        mov_dev = 0.0
        anomaly_reasons: list[str] = []
        behavior_types: list[str] = []

        # Sudden speed change evaluation
        if abs(accel) >= 25.0 or (speed >= 38.0 and mov_state == "RUNNING"):
            mov_dev += 45.0
            if accel > 0:
                anomaly_reasons.append(f"Sudden acceleration ({speed:.1f} px/s, +{accel:.1f} px/s²)")
            else:
                anomaly_reasons.append(f"Sudden deceleration ({speed:.1f} px/s, {accel:.1f} px/s²)")
            behavior_types.append("SUDDEN_SPEED_CHANGE")
        elif mov_change in ("ACCELERATED", "DECELERATED"):
            mov_dev += 25.0
            anomaly_reasons.append(f"Speed change detected: {mov_change.lower()}")
            behavior_types.append("SUDDEN_SPEED_CHANGE")

        # Sudden direction change evaluation
        has_sharp_turn = False
        if len(recent_movements) >= 1:
            h_curr = heading_deg
            h_prev = float(recent_movements[0]["heading_deg"] or 0.0)
            h_diff = abs(h_curr - h_prev)
            if h_diff > 180.0:
                h_diff = 360.0 - h_diff
            if h_diff >= 90.0 and speed >= 10.0:
                has_sharp_turn = True
                mov_dev += 35.0
                anomaly_reasons.append(f"Sudden course change ({int(h_diff)}° shift to {direction})")
                behavior_types.append("SUDDEN_DIRECTION_CHANGE")

        # Unusual movement pattern (erratic pacing / zig-zag / looping)
        if len(recent_movements) >= 5:
            headings = [float(r["heading_deg"] or 0.0) for r in recent_movements]
            changes = 0
            for i in range(len(headings) - 1):
                diff = abs(headings[i] - headings[i + 1])
                if diff > 180.0:
                    diff = 360.0 - diff
                if diff >= 60.0:
                    changes += 1
            if changes >= 3:
                mov_dev += 40.0
                anomaly_reasons.append("Unusual movement pattern (erratic directional oscillations)")
                behavior_types.append("UNUSUAL_MOVEMENT_PATTERN")

        mov_dev = min(100.0, mov_dev)

        # -------------------------------------------------------------
        # 2. SPATIAL DEVIATION (20%)
        # Restricted-zone movement, repeated zone visits
        # -------------------------------------------------------------
        spatial_dev = 0.0
        zone_type = (zone_row and zone_row.get("zone_type")) or "MONITORED"

        if zone_type == "RESTRICTED":
            spatial_dev += 85.0
            z_name = (zone_row and zone_row.get("name")) or zone_id or "Restricted Zone"
            anomaly_reasons.append(f"Restricted-zone movement: {z_name}")
            behavior_types.append("RESTRICTED_ZONE_MOVEMENT")
        elif zone_id:
            spatial_dev += 15.0

        # Repeated zone visits check
        if zone_id:
            past_visits = self.db.execute(
                """SELECT COUNT(DISTINCT timestamp) FROM events
                   WHERE track_id=? AND zone_id=? AND event_type IN ('ZONE_ENTRY', 'RESTRICTED_ZONE_ENTRY')""",
                (track_id, zone_id),
            ).fetchone()
            visit_cnt = past_visits[0] if past_visits else 0
            if visit_cnt >= 2:
                spatial_dev += 40.0
                anomaly_reasons.append(f"Repeated zone visits: entered {zone_id} {visit_cnt} times")
                behavior_types.append("REPEATED_ZONE_VISITS")

        spatial_dev = min(100.0, spatial_dev)

        # -------------------------------------------------------------
        # 3. TEMPORAL DEVIATION (15%)
        # Unusual activity for specific time (e.g. off-hours / night)
        # -------------------------------------------------------------
        temporal_dev = 0.0
        try:
            curr_hour = datetime.fromisoformat(last_seen.replace("Z", "+00:00")).hour
        except Exception:
            curr_hour = datetime.now(UTC).hour

        is_off_hours = curr_hour < 6 or curr_hour >= 22
        if is_off_hours:
            temporal_dev += 65.0
            anomaly_reasons.append(f"Unusual activity for time ({curr_hour:02d}:00 off-hours window)")
            behavior_types.append("OFF_HOURS_ACTIVITY")
        else:
            temporal_dev += 10.0

        temporal_dev = min(100.0, temporal_dev)

        # -------------------------------------------------------------
        # 4. DWELL DEVIATION (15%)
        # Unusual dwell / loitering duration vs baseline
        # -------------------------------------------------------------
        dwell_dev = 0.0
        zone_loiter_thresh = float((zone_row and zone_row.get("loitering_threshold_seconds")) or 50.0)

        if dwell_seconds > zone_loiter_thresh:
            ratio = dwell_seconds / max(1.0, zone_loiter_thresh)
            dwell_dev = min(100.0, 40.0 + (ratio * 20.0))
            dwell_min = dwell_seconds / 60.0
            dwell_label = f"{dwell_min:.1f} min" if dwell_min >= 1.0 else f"{int(dwell_seconds)}s"
            anomaly_reasons.append(f"Unusual dwell: {dwell_label} (normal ~{int(normal_dwell)}s)")
            behavior_types.append("UNUSUAL_DWELL")
        elif dwell_seconds > (normal_dwell * 2.0):
            ratio = dwell_seconds / normal_dwell
            dwell_dev = min(75.0, 30.0 + (ratio * 15.0))
            anomaly_reasons.append(f"Dwell duration above baseline ({int(dwell_seconds)}s)")
            behavior_types.append("UNUSUAL_DWELL")

        dwell_dev = min(100.0, dwell_dev)

        # -------------------------------------------------------------
        # 5. ACTIVITY / DENSITY DEVIATION (15%)
        # Unusual activity or crowd density surge
        # -------------------------------------------------------------
        act_density_dev = 0.0
        current_people_cnt = 1
        zone_capacity = 10
        if density_data:
            current_people_cnt = int(density_data.get("people_count") or 1)
            zone_capacity = max(1, int(density_data.get("capacity") or 10))
            if density_data.get("is_anomaly") or current_people_cnt > zone_capacity:
                act_density_dev += 85.0
                anomaly_reasons.append(
                    f"Activity/crowd density above capacity ({current_people_cnt} people / cap {zone_capacity})"
                )
                behavior_types.append("UNUSUAL_ACTIVITY_DENSITY")
            elif current_people_cnt > normal_people:
                surge_pct = ((current_people_cnt - normal_people) / max(1, normal_people)) * 100.0
                act_density_dev += min(70.0, 30.0 + (surge_pct * 0.4))
                anomaly_reasons.append(f"Activity above normal ({current_people_cnt} present vs {normal_people} expected)")
                behavior_types.append("UNUSUAL_ACTIVITY_DENSITY")
        else:
            act_density_dev = 10.0

        act_density_dev = min(100.0, act_density_dev)

        # -------------------------------------------------------------
        # 6. CROSS-CAMERA PATTERN (10%)
        # Related movement across cameras
        # -------------------------------------------------------------
        cross_cam_dev = 0.0
        related_cams: list[str] = [camera_id]

        # Check observations or track transitions across cameras
        obs_row = self.db.execute(
            "SELECT related_cameras, zone_transitions FROM observations WHERE track_id=? LIMIT 1",
            (track_id,),
        ).fetchone()
        if obs_row and obs_row["related_cameras"]:
            try:
                cams = json.loads(obs_row["related_cameras"])
                for c in cams:
                    if c not in related_cams:
                        related_cams.append(c)
            except Exception:
                pass

        # Check other tracks within close temporal proximity across other cameras
        if len(related_cams) >= 2:
            cross_cam_dev += min(100.0, 50.0 + len(related_cams) * 20.0)
            anomaly_reasons.append(f"Related movement across cameras ({' → '.join(related_cams)})")
            behavior_types.append("CROSS_CAMERA_MOVEMENT")
        else:
            cross_cam_dev = 5.0

        cross_cam_dev = min(100.0, cross_cam_dev)

        # -------------------------------------------------------------
        # 7. BASELINE DEVIATION (5%)
        # Difference between historical site baseline and current state
        # -------------------------------------------------------------
        base_dev = 0.0
        dwell_diff = abs(dwell_seconds - normal_dwell)
        if dwell_diff > 30.0:
            base_dev += 50.0
        if current_people_cnt > normal_people:
            base_dev += 40.0
        base_dev = min(100.0, max(5.0, base_dev))

        # -------------------------------------------------------------
        # COMPOSITE SCORE CALCULATION
        # -------------------------------------------------------------
        score, breakdown = calculate_behavioral_anomaly_score(
            movement_deviation=mov_dev,
            spatial_deviation=spatial_dev,
            temporal_deviation=temporal_dev,
            dwell_deviation=dwell_dev,
            activity_density_deviation=act_density_dev,
            cross_camera_pattern=cross_cam_dev,
            baseline_deviation=base_dev,
        )

        # Determine primary behavior type
        primary_behavior_type = behavior_types[0] if behavior_types else "OBSERVABLE_MOVEMENT"
        if "RESTRICTED_ZONE_MOVEMENT" in behavior_types:
            primary_behavior_type = "RESTRICTED_ZONE_MOVEMENT"
        elif "UNUSUAL_DWELL" in behavior_types and dwell_dev >= 50.0:
            primary_behavior_type = "UNUSUAL_DWELL"
        elif "SUDDEN_SPEED_CHANGE" in behavior_types and mov_dev >= 40.0:
            primary_behavior_type = "SUDDEN_SPEED_CHANGE"
        elif "UNUSUAL_ACTIVITY_DENSITY" in behavior_types and act_density_dev >= 60.0:
            primary_behavior_type = "UNUSUAL_ACTIVITY_DENSITY"

        # Construct related events and evidence lists
        rel_events: list[str] = []
        if events:
            for ev in events:
                if ev.get("event_id") and ev["event_id"] not in rel_events:
                    rel_events.append(ev["event_id"])
        if track.get("event_id") and track["event_id"] not in rel_events:
            rel_events.append(track["event_id"])

        rel_evidence: list[str] = list(evidence_ids or [])

        # Construct baseline comparison payload
        baseline_comp = {
            "normal_dwell_seconds": normal_dwell,
            "current_dwell_seconds": round(dwell_seconds, 1),
            "dwell_delta": f"Normal ~{int(normal_dwell)}s → Current {int(dwell_seconds)}s",
            "normal_people_count": normal_people,
            "current_people_count": current_people_cnt,
            "people_delta": f"{normal_people} → {current_people_cnt}",
            "normal_activity": normal_activity,
            "is_off_hours": is_off_hours,
        }

        # Activity density payload
        act_data = {
            "people_count": current_people_cnt,
            "capacity": zone_capacity,
            "is_anomaly": current_people_cnt > zone_capacity,
            "status": (
                "OVERCROWDED"
                if current_people_cnt > zone_capacity
                else "NORMAL"
                if current_people_cnt > 0
                else "CLEAR"
            ),
        }

        # Movement data payload
        mov_data = {
            "speed": round(speed, 2),
            "heading_deg": round(heading_deg, 1),
            "direction": direction,
            "movement_state": mov_state,
            "acceleration": round(accel, 2),
            "movement_change": mov_change,
            "recent_positions_count": len(recent_movements),
        }

        if not anomaly_reasons:
            anomaly_reasons.append("Standard observable motion within baseline parameters.")

        # Check existing behavioral event for this track
        existing = self.db.execute(
            "SELECT behavior_id, anomaly_score, event_id FROM behavioral_events WHERE track_id=? ORDER BY created_at DESC LIMIT 1",
            (track_id,),
        ).fetchone()

        behavior_id = existing["behavior_id"] if existing else f"BEH-{uuid.uuid4().hex[:8].upper()}"
        event_id = (events and events[0].get("event_id")) or (existing and existing["event_id"]) or track.get("event_id")

        beh_event = BehavioralEvent(
            behavior_id=behavior_id,
            event_id=event_id,
            track_id=track_id,
            camera_id=camera_id,
            zone_id=zone_id,
            timestamp=now_str,
            behavior_type=primary_behavior_type,
            anomaly_score=score,
            score_breakdown=breakdown,
            movement_state=mov_state,
            speed=speed,
            direction=direction,
            dwell_duration=dwell_seconds,
            activity_density_data=act_data,
            baseline_comparison=baseline_comp,
            anomaly_reasons=anomaly_reasons,
            movement_data=mov_data,
            related_cameras=related_cams,
            related_events=rel_events,
            evidence_ids=rel_evidence,
            confidence=float(track.get("average_confidence") or track.get("confidence") or 0.90),
            status="ACTIVE",
            created_at=now_str,
            updated_at=now_str,
        )

        # Persist to database
        self.persist_behavioral_event(beh_event)

        return beh_event

    def persist_behavioral_event(self, event: BehavioralEvent) -> None:
        """Insert or update behavioral event record into SQLite database."""
        sql = """INSERT INTO behavioral_events (
            behavior_id, event_id, track_id, camera_id, zone_id,
            timestamp, behavior_type, anomaly_score,
            movement_deviation, spatial_deviation, temporal_deviation,
            dwell_deviation, activity_density_deviation, cross_camera_pattern,
            baseline_deviation, movement_state, speed, direction,
            dwell_duration, activity_density_data, baseline_comparison,
            anomaly_reasons, movement_data, related_cameras, related_events,
            evidence_ids, confidence, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(behavior_id) DO UPDATE SET
            event_id=excluded.event_id,
            camera_id=excluded.camera_id,
            zone_id=excluded.zone_id,
            timestamp=excluded.timestamp,
            behavior_type=excluded.behavior_type,
            anomaly_score=excluded.anomaly_score,
            movement_deviation=excluded.movement_deviation,
            spatial_deviation=excluded.spatial_deviation,
            temporal_deviation=excluded.temporal_deviation,
            dwell_deviation=excluded.dwell_deviation,
            activity_density_deviation=excluded.activity_density_deviation,
            cross_camera_pattern=excluded.cross_camera_pattern,
            baseline_deviation=excluded.baseline_deviation,
            movement_state=excluded.movement_state,
            speed=excluded.speed,
            direction=excluded.direction,
            dwell_duration=excluded.dwell_duration,
            activity_density_data=excluded.activity_density_data,
            baseline_comparison=excluded.baseline_comparison,
            anomaly_reasons=excluded.anomaly_reasons,
            movement_data=excluded.movement_data,
            related_cameras=excluded.related_cameras,
            related_events=excluded.related_events,
            evidence_ids=excluded.evidence_ids,
            confidence=excluded.confidence,
            status=excluded.status,
            updated_at=excluded.updated_at
        """
        self.db.execute(
            sql,
            (
                event.behavior_id,
                event.event_id,
                event.track_id,
                event.camera_id,
                event.zone_id,
                event.timestamp,
                event.behavior_type,
                event.anomaly_score,
                round(event.score_breakdown.movement_deviation, 1),
                round(event.score_breakdown.spatial_deviation, 1),
                round(event.score_breakdown.temporal_deviation, 1),
                round(event.score_breakdown.dwell_deviation, 1),
                round(event.score_breakdown.activity_density_deviation, 1),
                round(event.score_breakdown.cross_camera_pattern, 1),
                round(event.score_breakdown.baseline_deviation, 1),
                event.movement_state,
                round(event.speed, 2),
                event.direction,
                round(event.dwell_duration, 1),
                json.dumps(event.activity_density_data),
                json.dumps(event.baseline_comparison),
                json.dumps(event.anomaly_reasons),
                json.dumps(event.movement_data),
                json.dumps(event.related_cameras),
                json.dumps(event.related_events),
                json.dumps(event.evidence_ids),
                round(event.confidence, 3),
                event.status,
                event.created_at,
                event.updated_at,
            ),
        )
        self.db.commit()



    def get_events(
        self,
        camera_id: str | None = None,
        zone_id: str | None = None,
        track_id: str | None = None,
        behavior_type: str | None = None,
        min_score: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query logged behavioral anomaly events with filters."""
        query = "SELECT * FROM behavioral_events WHERE 1=1"
        args: list[Any] = []

        if camera_id:
            query += " AND camera_id=?"
            args.append(camera_id)
        if zone_id:
            query += " AND zone_id=?"
            args.append(zone_id)
        if track_id:
            query += " AND track_id=?"
            args.append(track_id)
        if behavior_type:
            query += " AND behavior_type=?"
            args.append(behavior_type.upper())
        if min_score is not None:
            query += " AND anomaly_score>=?"
            args.append(int(min_score))
        if status:
            query += " AND status=?"
            args.append(status.upper())

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        args.extend([max(1, min(100, limit)), max(0, offset)])

        rows = self.db.execute(query, tuple(args)).fetchall()
        return [self._format_row(r) for r in rows]

    def get_event(self, behavior_id: str) -> dict[str, Any] | None:
        """Retrieve single behavioral event by identifier."""
        row = self.db.execute(
            "SELECT * FROM behavioral_events WHERE behavior_id=?", (behavior_id,)
        ).fetchone()
        if not row:
            return None
        return self._format_row(row)

    def get_summary(self) -> dict[str, Any]:
        """Aggregate summary counts of behavioral anomalies."""
        today_start = datetime.now(UTC).strftime("%Y-%m-%d 00:00:00")
        total = self.db.execute("SELECT COUNT(*) FROM behavioral_events").fetchone()[0]
        today_cnt = self.db.execute(
            "SELECT COUNT(*) FROM behavioral_events WHERE timestamp >= ?", (today_start,)
        ).fetchone()[0]

        high_anomalies = self.db.execute(
            "SELECT COUNT(*) FROM behavioral_events WHERE anomaly_score >= 50"
        ).fetchone()[0]

        top_zone_row = self.db.execute(
            """SELECT zone_id, MAX(anomaly_score) as max_s, COUNT(*) as cnt
               FROM behavioral_events
               WHERE zone_id IS NOT NULL AND zone_id != ''
               GROUP BY zone_id
               ORDER BY max_s DESC LIMIT 1"""
        ).fetchone()

        top_zone = top_zone_row["zone_id"] if top_zone_row else None
        top_zone_max_score = top_zone_row["max_s"] if top_zone_row else 0

        avg_score_row = self.db.execute(
            "SELECT AVG(anomaly_score) FROM behavioral_events"
        ).fetchone()
        avg_score = round(float(avg_score_row[0] or 0.0), 1)

        return {
            "total_behavioral_events": total,
            "today_count": today_cnt,
            "high_anomalies_count": high_anomalies,
            "average_anomaly_score": avg_score,
            "highest_anomaly_zone": top_zone,
            "highest_anomaly_score": top_zone_max_score,
        }

    def _format_row(self, row: sqlite3.Row | Any) -> dict[str, Any]:
        if not row:
            return {}
        d = dict(row)
        for field in ("activity_density_data", "baseline_comparison", "movement_data"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    d[field] = {}
            else:
                d[field] = {}
        for field in ("anomaly_reasons", "related_cameras", "related_events", "evidence_ids"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    d[field] = []
            else:
                d[field] = []

        d["score_breakdown"] = {
            "movement_deviation": round(float(d.get("movement_deviation") or 0.0), 1),
            "spatial_deviation": round(float(d.get("spatial_deviation") or 0.0), 1),
            "temporal_deviation": round(float(d.get("temporal_deviation") or 0.0), 1),
            "dwell_deviation": round(float(d.get("dwell_deviation") or 0.0), 1),
            "activity_density_deviation": round(float(d.get("activity_density_deviation") or 0.0), 1),
            "cross_camera_pattern": round(float(d.get("cross_camera_pattern") or 0.0), 1),
            "baseline_deviation": round(float(d.get("baseline_deviation") or 0.0), 1),
            "composite_score": int(d.get("anomaly_score") or 0),
        }
        return d
