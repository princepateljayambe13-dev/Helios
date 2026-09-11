"""HELIOS Observation Layer: transforms tracked entities and evidence into structured searchable metadata."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from app.insights.models import Observation


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ObservationLayer:
    """Manages the creation, persistence, and fast retrieval of structured observations."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def create_or_update_observation(
        self,
        track: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
        evidence_ids: list[str] | None = None,
        related_tracks: list[str] | None = None,
        related_cameras: list[str] | None = None,
    ) -> dict[str, Any]:
        """Convert a track record into a searchable structured observation."""
        track_id = str(track["track_id"])
        camera_id = track.get("camera_id", "unknown")
        object_type = str(track.get("object_type", "HUMAN")).upper()

        # Check existing observation for this track
        existing = self.db.execute(
            "SELECT * FROM observations WHERE track_id=? LIMIT 1", (track_id,)
        ).fetchone()

        obs_id = existing["observation_id"] if existing else f"OBS-{uuid.uuid4().hex[:6].upper()}"

        first_seen = track.get("created_at") or track.get("first_seen") or now_iso()
        last_seen = track.get("last_seen_at") or track.get("last_seen") or now_iso()

        # Calculate dwell seconds
        try:
            t0 = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            dwell_seconds = max(0.0, (t1 - t0).total_seconds())
        except Exception:
            dwell_seconds = 0.0

        entry_time = first_seen
        exit_time = track.get("ended_at") or (last_seen if track.get("status") == "ENDED" else None)

        movement_state = track.get("movement_state") or "STATIONARY"
        direction = track.get("direction") or "STATIONARY"
        speed = float(track.get("speed") or 0.0)

        # Distance travelled
        attrs = track.get("attributes") or {}
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except Exception:
                attrs = {}
        dist = float(attrs.get("distance_travelled") or 0.0)

        # Collect event IDs and zone information
        linked_event_ids: set[str] = set()
        if existing and existing["event_ids"]:
            try:
                linked_event_ids.update(json.loads(existing["event_ids"]))
            except Exception:
                pass

        if track.get("event_id"):
            linked_event_ids.add(track["event_id"])

        zone_id = None
        zone_transitions: list[str] = []

        if events:
            for ev in events:
                if ev.get("event_id"):
                    linked_event_ids.add(ev["event_id"])
                if ev.get("zone_id"):
                    zone_id = ev["zone_id"]
                    if zone_id not in zone_transitions:
                        zone_transitions.append(zone_id)

        if not zone_id and existing and existing["zone_id"]:
            zone_id = existing["zone_id"]

        # Collect evidence IDs
        linked_evidence_ids: set[str] = set()
        if existing and existing["evidence_ids"]:
            try:
                linked_evidence_ids.update(json.loads(existing["evidence_ids"]))
            except Exception:
                pass
        if evidence_ids:
            linked_evidence_ids.update(evidence_ids)

        # Related cameras and tracks
        rel_cams = list(related_cameras or [])
        if camera_id not in rel_cams:
            rel_cams.append(camera_id)
        rel_tracks = list(related_tracks or [])

        conf = float(track.get("average_confidence") or track.get("confidence") or 0.90)
        stamp = now_iso()

        self.db.execute(
            """INSERT INTO observations (
                observation_id, track_id, camera_id, zone_id, object_type,
                first_seen, last_seen, entry_time, exit_time, dwell_seconds,
                movement_state, direction, speed, distance_travelled,
                zone_transitions, related_tracks, related_cameras,
                event_ids, evidence_ids, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(observation_id) DO UPDATE SET
                last_seen=excluded.last_seen,
                exit_time=excluded.exit_time,
                dwell_seconds=excluded.dwell_seconds,
                movement_state=excluded.movement_state,
                direction=excluded.direction,
                speed=excluded.speed,
                distance_travelled=excluded.distance_travelled,
                zone_transitions=excluded.zone_transitions,
                related_tracks=excluded.related_tracks,
                related_cameras=excluded.related_cameras,
                event_ids=excluded.event_ids,
                evidence_ids=excluded.evidence_ids,
                confidence=excluded.confidence
            """,
            (
                obs_id,
                track_id,
                camera_id,
                zone_id,
                object_type,
                first_seen,
                last_seen,
                entry_time,
                exit_time,
                round(dwell_seconds, 1),
                movement_state,
                direction,
                round(speed, 2),
                round(dist, 2),
                json.dumps(zone_transitions),
                json.dumps(rel_tracks),
                json.dumps(rel_cams),
                json.dumps(sorted(linked_event_ids)),
                json.dumps(sorted(linked_evidence_ids)),
                round(conf, 3),
                stamp,
            ),
        )
        self.db.commit()

        row = self.db.execute("SELECT * FROM observations WHERE observation_id=?", (obs_id,)).fetchone()
        return self._format_row(row)

    def link_evidence_to_track(self, track_id: str, evidence_id: str) -> None:
        """Associate an evidence snapshot with a track's observation."""
        row = self.db.execute(
            "SELECT observation_id, evidence_ids FROM observations WHERE track_id=?", (track_id,)
        ).fetchone()
        if not row:
            return
        ev_list: list[str] = []
        if row["evidence_ids"]:
            try:
                ev_list = json.loads(row["evidence_ids"])
            except Exception:
                pass
        if evidence_id not in ev_list:
            ev_list.append(evidence_id)
            self.db.execute(
                "UPDATE observations SET evidence_ids=? WHERE observation_id=?",
                (json.dumps(ev_list), row["observation_id"]),
            )
            self.db.commit()

    def query(
        self,
        camera_id: str | None = None,
        zone_id: str | None = None,
        track_id: str | None = None,
        object_type: str | None = None,
        movement_state: str | None = None,
        direction: str | None = None,
        min_dwell: float | None = None,
        max_dwell: float | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fast indexed query across observations."""
        query = "SELECT * FROM observations WHERE 1=1"
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
        if object_type:
            query += " AND object_type=?"
            args.append(object_type.upper())
        if movement_state:
            query += " AND movement_state=?"
            args.append(movement_state.upper())
        if direction:
            query += " AND direction=?"
            args.append(direction.upper())
        if min_dwell is not None:
            query += " AND dwell_seconds >= ?"
            args.append(float(min_dwell))
        if max_dwell is not None:
            query += " AND dwell_seconds <= ?"
            args.append(float(max_dwell))
        if start_time:
            query += " AND last_seen >= ?"
            args.append(start_time)
        if end_time:
            query += " AND first_seen <= ?"
            args.append(end_time)

        query += " ORDER BY first_seen DESC LIMIT ? OFFSET ?"
        args.extend([max(1, min(200, limit)), max(0, offset)])

        rows = self.db.execute(query, tuple(args)).fetchall()
        return [self._format_row(r) for r in rows]

    def count(self, **kwargs) -> int:
        """Fast count of matching observations."""
        query = "SELECT COUNT(*) FROM observations WHERE 1=1"
        args: list[Any] = []
        if kwargs.get("camera_id"):
            query += " AND camera_id=?"
            args.append(kwargs["camera_id"])
        if kwargs.get("zone_id"):
            query += " AND zone_id=?"
            args.append(kwargs["zone_id"])
        if kwargs.get("object_type"):
            query += " AND object_type=?"
            args.append(kwargs["object_type"].upper())
        if kwargs.get("start_time"):
            query += " AND last_seen >= ?"
            args.append(kwargs["start_time"])
        if kwargs.get("end_time"):
            query += " AND first_seen <= ?"
            args.append(kwargs["end_time"])

        return self.db.execute(query, tuple(args)).fetchone()[0]

    def _format_row(self, row: sqlite3.Row | Any) -> dict[str, Any]:
        if not row:
            return {}
        d = dict(row)
        for field in ("zone_transitions", "related_tracks", "related_cameras", "event_ids", "evidence_ids"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    d[field] = []
            else:
                d[field] = []
        return d
