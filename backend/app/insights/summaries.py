"""Precomputed and rolling telemetry summaries across multi-scale time windows."""
from __future__ import annotations

import json
import sqlite3
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any


WINDOWS = {
    "LIVE": 120,          # 2 minutes
    "5MIN": 300,          # 5 minutes
    "15MIN": 900,         # 15 minutes
    "1HOUR": 3600,        # 1 hour
    "6HOURS": 21600,      # 6 hours
    "24HOURS": 86400,     # 24 hours
    "7DAYS": 604800,      # 7 days
}


class RollingSummaryManager:
    """Maintains precomputed, fast-cached rolling summaries to avoid expensive on-demand scans."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._ttl_seconds = 3.0  # Cache duration

    def get_summary(self, window_key: str = "LIVE", force_refresh: bool = False) -> dict[str, Any]:
        """Retrieve precomputed summary for a given time window."""
        norm_key = window_key.upper().replace(" ", "").replace("_", "")
        if norm_key not in WINDOWS:
            norm_key = "LIVE"

        now_sec = time.monotonic()
        if not force_refresh and norm_key in self._cache:
            ts, val = self._cache[norm_key]
            if now_sec - ts < self._ttl_seconds:
                return val

        summary = self._compute_window_summary(norm_key)
        self._cache[norm_key] = (now_sec, summary)
        return summary

    def get_all_summaries(self) -> dict[str, dict[str, Any]]:
        """Retrieve all standard window summaries at once."""
        return {key: self.get_summary(key) for key in WINDOWS}

    def _compute_window_summary(self, window_key: str) -> dict[str, Any]:
        duration_sec = WINDOWS.get(window_key, 120)
        cutoff_dt = datetime.now(UTC) - timedelta(seconds=duration_sec)
        cutoff_str = cutoff_dt.isoformat()

        # Observations aggregation within window
        obs_rows = self.db.execute(
            """SELECT object_type, camera_id, zone_id, dwell_seconds, movement_state, speed
               FROM observations
               WHERE last_seen >= ?""",
            (cutoff_str,),
        ).fetchall()

        people_count = 0
        vehicle_count = 0
        camera_activity: dict[str, int] = defaultdict(int)
        zone_occupancy: dict[str, int] = defaultdict(int)
        movement_dist: dict[str, int] = defaultdict(int)
        dwells: list[float] = []
        speeds: list[float] = []

        for r in obs_rows:
            obj = r["object_type"].upper()
            if obj == "HUMAN":
                people_count += 1
            elif obj == "VEHICLE":
                vehicle_count += 1

            cam = r["camera_id"]
            camera_activity[cam] += 1

            if r["zone_id"]:
                zone_occupancy[r["zone_id"]] += 1

            mstate = r["movement_state"] or "STATIONARY"
            movement_dist[mstate] += 1

            dwell = float(r["dwell_seconds"] or 0.0)
            if dwell > 0:
                dwells.append(dwell)

            spd = float(r["speed"] or 0.0)
            if spd > 0:
                speeds.append(spd)

        avg_dwell = round(sum(dwells) / len(dwells), 1) if dwells else 0.0
        max_dwell = round(max(dwells), 1) if dwells else 0.0
        avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0.0

        # Events count within window
        events_row = self.db.execute(
            "SELECT COUNT(*) FROM events WHERE timestamp >= ?", (cutoff_str,)
        ).fetchone()
        event_count = events_row[0] if events_row else 0

        # High-severity / alert count
        alerts_row = self.db.execute(
            "SELECT COUNT(*) FROM alerts WHERE timestamp >= ?", (cutoff_str,)
        ).fetchone()
        alert_count = alerts_row[0] if alerts_row else 0

        # Incidents count within window
        try:
            inc_row = self.db.execute(
                "SELECT COUNT(*) FROM incidents WHERE last_seen_at >= ? OR start_time >= ?",
                (cutoff_str, cutoff_str),
            ).fetchone()
            incident_count = inc_row[0] if inc_row else 0
        except Exception:
            incident_count = 0

        # Face recognition telemetry within window
        faces_detected = 0
        faces_recognized = 0
        faces_unclassified = 0
        try:
            face_rows = self.db.execute(
                """SELECT status, COUNT(*) as cnt
                   FROM face_recognitions
                   WHERE last_seen >= ? OR first_seen >= ?
                   GROUP BY status""",
                (cutoff_str, cutoff_str),
            ).fetchall()
            for r in face_rows:
                cnt = r["cnt"] if isinstance(r, sqlite3.Row) else r[1]
                st = (r["status"] if isinstance(r, sqlite3.Row) else r[0]) or ""
                faces_detected += cnt
                if st.upper() == "RECOGNIZED":
                    faces_recognized += cnt
                else:
                    faces_unclassified += cnt
        except Exception:
            pass

        # Overall activity score (normalized 0-100)
        raw_act = (people_count * 5) + (vehicle_count * 8) + (event_count * 10) + (alert_count * 20)
        activity_index = min(100, int(round(raw_act)))

        # Anomaly level calculation based on alerts and unusual dwell
        anomaly_level = "NORMAL"
        if alert_count >= 3 or max_dwell > 300:
            anomaly_level = "CRITICAL" if alert_count >= 5 else "ELEVATED"
        elif alert_count > 0 or max_dwell > 120:
            anomaly_level = "MODERATE"

        return {
            "window": window_key,
            "duration_seconds": duration_sec,
            "people_count": people_count,
            "vehicle_count": vehicle_count,
            "total_objects": people_count + vehicle_count,
            "activity_index": activity_index,
            "average_dwell_seconds": avg_dwell,
            "max_dwell_seconds": max_dwell,
            "average_speed": avg_speed,
            "camera_activity": dict(camera_activity),
            "zone_occupancy": dict(zone_occupancy),
            "movement_distribution": dict(movement_dist),
            "event_count": event_count,
            "alert_count": alert_count,
            "incident_count": incident_count,
            "faces_detected": faces_detected,
            "faces_recognized": faces_recognized,
            "faces_unclassified": faces_unclassified,
            "anomaly_level": anomaly_level,
            "computed_at": datetime.now(UTC).isoformat(),
        }
