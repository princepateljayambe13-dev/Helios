"""Intelligent Incident Correlation Engine for HELIOS.

Continuously correlates security events across time, camera, zone, track ID,
object type, movement dynamics, and event sequences into unified developing incidents.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from app.incidents.incident import Incident


def _parse_iso(ts_str: str | None) -> datetime:
    if not ts_str:
        return datetime.now(timezone.utc)
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


SEVERITY_ORDER = {
    "CRITICAL": 5,
    "HIGH": 4,
    "ELEVATED": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "INFO": 0,
}

REVERSE_SEVERITY = {v: k for k, v in SEVERITY_ORDER.items()}


class IncidentCorrelator:
    """Intelligent Incident Correlation Engine.

    Correlates observations and events probabilistically without creating new detectors.
    Maintains incident lifecycles (DETECTED -> CONFIRMED -> ACTIVE -> ACKNOWLEDGED -> RESOLVED).
    """

    def __init__(
        self,
        db: Any,
        correlation_window_seconds: float = 180.0,
        correlation_threshold: float = 0.52,
        resolve_timeout_seconds: float = 300.0,
    ):
        self.db = db
        self.correlation_window_seconds = float(correlation_window_seconds)
        self.correlation_threshold = float(correlation_threshold)
        self.resolve_timeout_seconds = float(resolve_timeout_seconds)
        # Active incident cache (incident_id -> Incident)
        self.active_incidents: dict[str, Incident] = {}
        self._load_active_from_db()

    def _load_active_from_db(self) -> None:
        """Load open/active incidents from SQLite on startup."""
        try:
            rows = self.db.execute(
                "SELECT * FROM incidents WHERE status IN ('DETECTED', 'CONFIRMED', 'ACTIVE', 'ACKNOWLEDGED') ORDER BY last_seen_at DESC LIMIT 50"
            ).fetchall()
            for r in rows:
                inc = Incident.from_row(r)
                self.active_incidents[inc.incident_id] = inc
        except Exception as e:
            print(f"[IncidentCorrelator] Warning loading active incidents: {e}")

    def correlate_event(
        self,
        event: dict[str, Any],
        observation: dict[str, Any] | None = None,
        alert: dict[str, Any] | None = None,
    ) -> tuple[Incident, bool, bool]:
        """Correlate an incoming event with existing incidents.

        Returns:
            (incident, is_new_incident, is_alert_deduplicated)
        """
        self.prune_stale_incidents()

        event_ts = _parse_iso(event.get("timestamp") or event.get("created_at"))
        track_id = event.get("track_id")
        camera_id = event.get("camera_id")
        zone_id = event.get("zone_id")
        obj_type = event.get("object_type") or (observation.get("object_type") if observation else "HUMAN")
        event_type = event.get("event_type", "EVENT")
        ev_conf = float(event.get("confidence") or 0.8)
        ev_sev = event.get("severity", "MEDIUM")

        best_incident: Incident | None = None
        best_score = 0.0
        best_reasons: list[str] = []
        best_breakdown: dict[str, float] = {}

        # Evaluate match against all active incidents
        for inc_id, inc in list(self.active_incidents.items()):
            score, reasons, breakdown = self._score_correlation(inc, event, observation)
            if score > best_score:
                best_score = score
                best_incident = inc
                best_reasons = reasons
                best_breakdown = breakdown

        if best_incident and best_score >= self.correlation_threshold:
            # Correlate into existing incident
            is_dedup = self._update_incident_with_event(
                best_incident, event, observation, alert, best_score, best_reasons, best_breakdown
            )
            return best_incident, False, is_dedup

        # Otherwise create a new incident
        new_inc = self._create_incident_from_event(event, observation, alert)
        self.active_incidents[new_inc.incident_id] = new_inc
        return new_inc, True, False

    def _score_correlation(
        self,
        inc: Incident,
        event: dict[str, Any],
        observation: dict[str, Any] | None,
    ) -> tuple[float, list[str], dict[str, float]]:
        """Calculate multi-dimensional probabilistic correlation score between incident and event."""
        reasons = []
        breakdown = {}

        # 1. Temporal correlation (S_time)
        inc_last = _parse_iso(inc.last_seen_at)
        ev_ts = _parse_iso(event.get("timestamp") or event.get("created_at"))
        dt = abs((ev_ts - inc_last).total_seconds())

        if dt > self.correlation_window_seconds:
            return 0.0, [], {}

        if dt <= 15.0:
            s_time = 1.0
            reasons.append(f"Immediate temporal proximity ({dt:.1f}s after prior observation)")
        elif dt <= 60.0:
            s_time = 1.0 - (dt - 15.0) / 180.0
            reasons.append(f"Close temporal sequence (+{dt:.1f}s delta)")
        else:
            s_time = max(0.2, 0.75 * math.exp(-(dt - 60.0) / 90.0))
            reasons.append(f"Extended temporal continuity (+{dt:.0f}s within situation window)")
        breakdown["time"] = round(s_time, 3)

        # 2. Track ID continuity (S_track)
        ev_track = event.get("track_id")
        has_same_track = False
        if ev_track and inc.primary_track_id:
            if ev_track == inc.primary_track_id:
                s_track = 1.0
                has_same_track = True
                reasons.append(f"Exact track identity continuity ({ev_track})")
            else:
                s_track = 0.35
        else:
            s_track = 0.5
        breakdown["track"] = round(s_track, 3)

        # 3. Camera & Spatial Location (S_space)
        ev_cam = event.get("camera_id")
        ev_zone = event.get("zone_id")
        s_space = 0.3

        if ev_cam and inc.primary_camera_id:
            if ev_cam == inc.primary_camera_id:
                s_space = 0.85
                reasons.append(f"Co-located on camera {ev_cam}")
            else:
                # Potential adjacent camera handover
                s_space = 0.65
                reasons.append(f"Potential camera transition ({inc.primary_camera_id} → {ev_cam})")

        if ev_zone and inc.primary_zone_id:
            if ev_zone == inc.primary_zone_id:
                s_space = min(1.0, s_space + 0.15)
                reasons.append(f"Shared zone boundary {ev_zone}")

        breakdown["spatial"] = round(s_space, 3)

        # 4. Object Type & Vehicle Intelligence (S_attr)
        ev_obj = event.get("object_type") or (observation.get("object_type") if observation else None)
        s_attr = 0.5
        if ev_obj and inc.object_type:
            if ev_obj.upper() == inc.object_type.upper():
                s_attr = 0.85
                reasons.append(f"Matching entity category ({ev_obj})")

                # Check vehicle intelligence consistency if vehicle
                if ev_obj.upper() == "VEHICLE" and observation:
                    v_intel = (observation.get("attributes") or {}).get("vehicle_intelligence")
                    if v_intel and v_intel.get("color") and v_intel["color"] != "unknown":
                        reasons.append(f"Vehicle dynamic: {v_intel.get('color')} {v_intel.get('type') or 'vehicle'}")
                        s_attr = min(1.0, s_attr + 0.1)
            else:
                s_attr = 0.15
        breakdown["attribute"] = round(s_attr, 3)

        # 5. Threat Sequence Pattern (S_seq)
        ev_type = event.get("event_type", "")
        s_seq = 0.5
        if inc.incident_type:
            # Intrusion followed by loitering
            if ("INTRUSION" in inc.incident_type or "BREACH" in inc.incident_type) and ev_type == "LOITERING":
                s_seq = 1.0
                reasons.append("Behavioral escalation: Restricted perimeter entry followed by prolonged loitering")
            # Loitering followed by exit or movement
            elif "LOITERING" in inc.incident_type and (ev_type == "ZONE_EXIT" or "MOVEMENT" in ev_type):
                s_seq = 0.95
                reasons.append("Behavioral progression: Loitering phase transitioned to movement/departure")
            # Multi-zone breach sequence
            elif "INTRUSION" in inc.incident_type and ev_type == "INTRUSION":
                s_seq = 0.9
                reasons.append("Multi-point perimeter penetration sequence")
            elif ev_type in ("RESTRICTED_ZONE_ENTRY", "INTRUSION", "LOITERING"):
                s_seq = 0.85
        breakdown["sequence"] = round(s_seq, 3)

        # Weighted composite score
        if has_same_track:
            # When track is identical, high confidence in same situation
            weights = {"time": 0.25, "track": 0.40, "spatial": 0.15, "attribute": 0.10, "sequence": 0.10}
        else:
            # Across camera or potential handovers
            weights = {"time": 0.30, "track": 0.10, "spatial": 0.25, "attribute": 0.20, "sequence": 0.15}

        composite_score = sum(breakdown[k] * weights[k] for k in weights)
        return round(composite_score, 3), reasons, breakdown

    def _create_incident_from_event(
        self,
        event: dict[str, Any],
        observation: dict[str, Any] | None,
        alert: dict[str, Any] | None,
    ) -> Incident:
        """Create a new Incident from an initial trigger event."""
        inc_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        stamp = event.get("timestamp") or event.get("created_at") or _iso_now()
        ev_type = event.get("event_type", "SECURITY_EVENT")
        camera_id = event.get("camera_id")
        zone_id = event.get("zone_id")
        track_id = event.get("track_id")
        obj_type = event.get("object_type") or (observation.get("object_type") if observation else "HUMAN")
        initial_sev = event.get("severity", "MEDIUM")
        confidence = float(event.get("confidence") or 0.75)

        # Generate descriptive title
        cam_desc = f"on {camera_id}" if camera_id else ""
        zone_desc = f"in {zone_id}" if zone_id else ""
        if ev_type == "INTRUSION":
            title = f"Perimeter Intrusion {zone_desc} {cam_desc}".strip()
            inc_type = "PERIMETER_BREACH"
        elif ev_type == "LOITERING":
            title = f"Sustained Dwell / Loitering {zone_desc} {cam_desc}".strip()
            inc_type = "LOITERING_THREAT"
        elif ev_type == "RESTRICTED_ZONE_ENTRY":
            title = f"Restricted Sector Breach {zone_desc} {cam_desc}".strip()
            inc_type = "RESTRICTED_BREACH"
        else:
            title = f"Suspicious {obj_type.capitalize()} Activity {cam_desc}".strip()
            inc_type = "ACTIVITY_ANOMALY"

        summary = (
            f"Initial {ev_type.replace('_', ' ').lower()} observed with {obj_type.lower()} "
            f"(confidence {confidence:.0%}) {cam_desc} {zone_desc}. Developing situation monitoring initiated."
        ).strip()

        correlation_reasons = [
            f"Primary incident trigger: {ev_type} ({initial_sev})",
            f"Entity category identified as {obj_type}",
        ]
        if track_id:
            correlation_reasons.append(f"Assigned primary track continuity {track_id}")

        breakdown = {
            "time": 1.0,
            "track": 1.0 if track_id else 0.5,
            "spatial": 1.0,
            "attribute": 1.0,
            "sequence": 1.0,
        }

        inc = Incident(
            incident_id=inc_id,
            title=title,
            incident_type=inc_type,
            severity=initial_sev,
            status="DETECTED",
            confidence=round(confidence, 3),
            start_time=stamp,
            last_seen_at=stamp,
            duration_seconds=0.0,
            primary_camera_id=camera_id,
            primary_zone_id=zone_id,
            primary_track_id=track_id,
            object_type=obj_type,
            summary=summary,
            correlation_reasons=correlation_reasons,
            score_breakdown=breakdown,
            event_count=1,
            created_at=stamp,
            updated_at=stamp,
        )

        # Persist to database
        self.db.execute(
            "INSERT INTO incidents (incident_id, title, incident_type, severity, status, confidence, "
            "start_time, end_time, last_seen_at, duration_seconds, primary_camera_id, primary_zone_id, "
            "primary_track_id, object_type, summary, correlation_reasons, score_breakdown, event_count, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                inc.incident_id,
                inc.title,
                inc.incident_type,
                inc.severity,
                inc.status,
                inc.confidence,
                inc.start_time,
                None,
                inc.last_seen_at,
                inc.duration_seconds,
                inc.primary_camera_id,
                inc.primary_zone_id,
                inc.primary_track_id,
                inc.object_type,
                inc.summary,
                json.dumps(inc.correlation_reasons),
                json.dumps(inc.score_breakdown),
                inc.event_count,
                inc.created_at,
                inc.updated_at,
            ),
        )

        # Record event link
        if event.get("event_id"):
            self.db.execute(
                "INSERT INTO incident_events (incident_id, event_id, correlation_score, correlation_factors, added_at) "
                "VALUES (?, ?, 1.0, ?, ?)",
                (inc.incident_id, event["event_id"], json.dumps(correlation_reasons), stamp),
            )
            self.db.execute("UPDATE events SET incident_id=? WHERE event_id=?", (inc.incident_id, event["event_id"]))

        if alert and alert.get("alert_id"):
            self.db.execute("UPDATE alerts SET incident_id=? WHERE alert_id=?", (inc.incident_id, alert["alert_id"]))

        self.db.commit()
        return inc

    def _update_incident_with_event(
        self,
        inc: Incident,
        event: dict[str, Any],
        observation: dict[str, Any] | None,
        alert: dict[str, Any] | None,
        score: float,
        reasons: list[str],
        breakdown: dict[str, float],
    ) -> bool:
        """Merge a correlated event into an existing incident.

        Returns True if the associated alert was deduplicated.
        """
        now_ts = _parse_iso(event.get("timestamp") or event.get("created_at") or _iso_now())
        start_ts = _parse_iso(inc.start_time)
        duration = max(0.0, (now_ts - start_ts).total_seconds())

        inc.event_count += 1
        inc.last_seen_at = now_ts.isoformat()
        inc.duration_seconds = duration
        inc.updated_at = _iso_now()

        # Update status: DETECTED -> CONFIRMED -> ACTIVE
        if inc.status == "DETECTED":
            inc.status = "CONFIRMED"
        elif inc.status in ("CONFIRMED", "ACTIVE"):
            inc.status = "ACTIVE"

        # Probabilistic confidence combination (Noisy-OR)
        ev_conf = float(event.get("confidence") or 0.8)
        new_conf = 1.0 - (1.0 - inc.confidence) * (1.0 - ev_conf * score)
        inc.confidence = min(0.99, max(0.1, new_conf))

        # Dynamic severity escalation
        ev_sev = event.get("severity", "MEDIUM")
        current_rank = SEVERITY_ORDER.get(inc.severity, 2)
        event_rank = SEVERITY_ORDER.get(ev_sev, 2)

        # Escalation rules:
        # 1. Multi-event threat escalation
        if inc.event_count >= 3 and current_rank < SEVERITY_ORDER["HIGH"]:
            current_rank = SEVERITY_ORDER["HIGH"]

        # 2. Direct event severity promotion
        if event_rank > current_rank:
            current_rank = event_rank

        # 3. Compound critical combinations (e.g. Intrusion + Loitering)
        if ("INTRUSION" in inc.incident_type or "BREACH" in inc.incident_type) and event.get("event_type") == "LOITERING":
            current_rank = max(current_rank, SEVERITY_ORDER["CRITICAL"])
            inc.incident_type = "PERIMETER_BREACH_AND_LOITERING"
            inc.title = f"Escalated Intrusion & Loitering at {inc.primary_zone_id or inc.primary_camera_id or 'Sector'}"

        inc.severity = REVERSE_SEVERITY.get(current_rank, inc.severity)

        # Aggregate correlation reasons
        for r in reasons:
            if r not in inc.correlation_reasons:
                inc.correlation_reasons.append(r)
        # Keep latest 8 reasons
        inc.correlation_reasons = inc.correlation_reasons[-8:]
        inc.score_breakdown = breakdown

        # Update summary narrative
        ev_desc = event.get("description") or event.get("event_type", "activity")
        inc.summary = (
            f"Developing situation involving {inc.object_type.lower()} with {inc.event_count} correlated events "
            f"across {round(inc.duration_seconds)}s duration. Latest progression: {ev_desc} "
            f"(Confidence: {inc.confidence:.0%}, Threat Level: {inc.severity})."
        )

        # Alert deduplication check
        is_dedup = False
        if alert and alert.get("alert_id"):
            # Check if incident already has alerts within the cooldown
            existing_alert = self.db.execute(
                "SELECT alert_id FROM alerts WHERE incident_id=? AND alert_id != ? LIMIT 1",
                (inc.incident_id, alert["alert_id"]),
            ).fetchone()
            if existing_alert:
                is_dedup = True
            self.db.execute("UPDATE alerts SET incident_id=? WHERE alert_id=?", (inc.incident_id, alert["alert_id"]))

        # Persist incident updates to DB
        self.db.execute(
            "UPDATE incidents SET title=?, incident_type=?, severity=?, status=?, confidence=?, "
            "last_seen_at=?, duration_seconds=?, summary=?, correlation_reasons=?, score_breakdown=?, "
            "event_count=?, updated_at=? WHERE incident_id=?",
            (
                inc.title,
                inc.incident_type,
                inc.severity,
                inc.status,
                inc.confidence,
                inc.last_seen_at,
                inc.duration_seconds,
                inc.summary,
                json.dumps(inc.correlation_reasons),
                json.dumps(inc.score_breakdown),
                inc.event_count,
                inc.updated_at,
                inc.incident_id,
            ),
        )

        # Link event in incident_events join table
        if event.get("event_id"):
            self.db.execute(
                "INSERT OR IGNORE INTO incident_events (incident_id, event_id, correlation_score, correlation_factors, added_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (inc.incident_id, event["event_id"], score, json.dumps(reasons), _iso_now()),
            )
            self.db.execute("UPDATE events SET incident_id=? WHERE event_id=?", (inc.incident_id, event["event_id"]))

        self.db.commit()
        return is_dedup

    def prune_stale_incidents(self) -> int:
        """Auto-resolve incidents that have seen no activity past the timeout window."""
        now_dt = datetime.now(timezone.utc)
        resolved_count = 0

        for inc_id, inc in list(self.active_incidents.items()):
            last_dt = _parse_iso(inc.last_seen_at)
            elapsed = (now_dt - last_dt).total_seconds()

            if elapsed > self.resolve_timeout_seconds:
                # Resolve incident
                inc.status = "RESOLVED"
                inc.end_time = inc.last_seen_at
                inc.updated_at = _iso_now()
                self.db.execute(
                    "UPDATE incidents SET status='RESOLVED', end_time=?, updated_at=? WHERE incident_id=?",
                    (inc.end_time, inc.updated_at, inc.incident_id),
                )
                self.db.commit()
                del self.active_incidents[inc_id]
                resolved_count += 1

        return resolved_count

    def acknowledge_incident(self, incident_id: str, operator: str = "Operator") -> Incident | None:
        """Acknowledge an incident by operator."""
        now_str = _iso_now()
        self.db.execute(
            "UPDATE incidents SET status='ACKNOWLEDGED', acknowledged_at=?, acknowledged_by=?, updated_at=? WHERE incident_id=?",
            (now_str, operator, now_str, incident_id),
        )
        self.db.commit()
        row = self.db.execute("SELECT * FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
        if not row:
            return None
        inc = Incident.from_row(row)
        if inc.incident_id in self.active_incidents:
            self.active_incidents[inc.incident_id] = inc
        return inc

    def resolve_incident(self, incident_id: str, operator: str = "Operator") -> Incident | None:
        """Mark an incident as resolved."""
        now_str = _iso_now()
        self.db.execute(
            "UPDATE incidents SET status='RESOLVED', resolved_at=?, resolved_by=?, end_time=?, updated_at=? WHERE incident_id=?",
            (now_str, operator, now_str, now_str, incident_id),
        )
        self.db.commit()
        row = self.db.execute("SELECT * FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
        if not row:
            return None
        inc = Incident.from_row(row)
        if inc.incident_id in self.active_incidents:
            del self.active_incidents[inc.incident_id]
        return inc
