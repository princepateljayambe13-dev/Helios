"""Application service: converts model-independent observations to persisted HELIOS records."""
from __future__ import annotations
from datetime import UTC, datetime, timedelta
import json, logging, sqlite3, uuid
from collections import defaultdict
from typing import Any

LOGGER = logging.getLogger("helios.service")
from app.core.config import Settings
from app.tracking.track_manager import CameraTrackerManager
from app.tracking.tracker import iou
from app.spatial.geometry import box_bottom_center, box_center, point_in_polygon
from app.spatial.spatial_engine import SpatialEngine
from app.spatial.zone import Zone
from app.tracking.movement import MovementTracker, MovementConfig, CameraCalibration
from app.vision.observation import crop_bounding_box_jpeg
from app.vision.vehicle_intelligence import VehicleIntelligencePipeline
from app.tracking.face_association import find_matching_human_track, find_matching_face_track
from app.incidents.correlator import IncidentCorrelator
from app.incidents.incident import Incident
from app.insights.observation_layer import ObservationLayer
from app.insights.engine import InsightsEngine
from app.insights.summaries import RollingSummaryManager
from app.insights.baseline import BaselineEngine
from app.insights.nl_investigator import NaturalLanguageInvestigator
from app.vision.face.recognition_manager import FaceRecognitionManager
from app.behavioral.engine import BehavioralAnalyticsEngine

def now() -> str: return datetime.now(UTC).isoformat()
def item(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None: return None
    value = dict(row)
    for key in ("bounding_box", "attributes", "current_position", "geometry", "object_types", "metadata", "vehicle_intelligence", "position"):
        if value.get(key):
            try: value[key] = json.loads(value[key])
            except Exception: pass
    if "enabled" in value: value["enabled"] = bool(value["enabled"])
    if "stream_configured" in value: value["stream_configured"] = bool(value["stream_configured"])
    return value

def rows(cursor: sqlite3.Cursor | Any) -> list[dict[str, Any]]:
    return [item(r) for r in cursor.fetchall()]

PREFIX = {"HUMAN":"P", "VEHICLE":"V", "UAV":"U", "ANIMAL":"A", "FACE":"F", "LICENSE_PLATE":"L", "UNCLASSIFIED":"M", "MOTION":"M"}
EVENT_FOR = {"FIRE":"FIRE_DETECTED", "SMOKE":"SMOKE_DETECTED", "GUNSHOT_LIKE":"GUNSHOT_LIKE_DETECTED", "EXPLOSION_LIKE":"EXPLOSION_LIKE_DETECTED", "UNCLASSIFIED":"UNCLASSIFIED_MOTION_DETECTED", "MOTION":"MOTION_DETECTED"}

class HeliosService:
    def __init__(self, db: sqlite3.Connection, settings: Settings, vehicle_pipeline: VehicleIntelligencePipeline | None = None, movement_tracker: MovementTracker | None = None):
        self.db, self.settings = db, settings
        self.tracker_manager = CameraTrackerManager(settings)
        self.spatial_engine = SpatialEngine(confirmation_frames=2, exit_confirmation_frames=2)
        self.vehicle_pipeline = vehicle_pipeline or VehicleIntelligencePipeline()
        self.movement_tracker = movement_tracker or MovementTracker()
        self.incident_correlator = IncidentCorrelator(self.db)
        self.observation_layer = ObservationLayer(self.db)
        self.insights_engine = InsightsEngine(self.db, ollama_url=getattr(settings, "ollama_base_url", "http://127.0.0.1:11434"))
        self.rolling_summaries = RollingSummaryManager(self.db)
        self.baseline_engine = BaselineEngine(self.db)
        self.nl_investigator = NaturalLanguageInvestigator(
            self.db,
            ollama_url=getattr(settings, "ollama_base_url", "http://127.0.0.1:11434"),
            model=getattr(settings, "ollama_model", "qwen3:4b"),
        )
        self.face_recognition_manager = FaceRecognitionManager(self.db, self.settings)
        self.behavioral_engine = BehavioralAnalyticsEngine(self.db, baseline_engine=self.baseline_engine)
        self.cooldowns: dict[tuple[str, str | None, str | None], datetime] = {}
        self.subscribers: set[Any] = set()

    def seed(self) -> None:
        stamp = now()
        configured_cam_ids = set()
        for camera in self.settings.cameras:
            cid = camera["camera_id"]
            configured_cam_ids.add(cid)
            stream_reference = camera.get("stream_reference", "")
            status = "OFFLINE" if not stream_reference else "CONNECTING"
            self.db.execute(
                "INSERT INTO cameras (camera_id,name,source_type,stream_reference,location,status,enabled,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(camera_id) DO UPDATE SET "
                "name=excluded.name,source_type=excluded.source_type,stream_reference=excluded.stream_reference,"
                "location=excluded.location,enabled=excluded.enabled,status=excluded.status,updated_at=excluded.updated_at",
                (cid, camera["name"], camera.get("source_type", "PLACEHOLDER"), stream_reference, camera.get("location", ""), status, int(camera.get("enabled", True)), stamp, stamp)
            )
            if not stream_reference:
                self.db.execute("UPDATE cameras SET status='OFFLINE',updated_at=? WHERE camera_id=? AND (stream_reference='' OR stream_reference IS NULL)", (stamp, cid))
        if configured_cam_ids:
            # Disable any database cameras that are no longer configured in cameras.yaml
            placeholders = ",".join("?" for _ in configured_cam_ids)
            self.db.execute(f"UPDATE cameras SET enabled=0, status='OFFLINE', updated_at=? WHERE camera_id NOT IN ({placeholders})", (stamp, *configured_cam_ids))
        for zone in self.settings.zones:
            obj_types = json.dumps(zone.get("object_types", ["HUMAN", "VEHICLE"]))
            self.db.execute("INSERT OR IGNORE INTO zones (zone_id,camera_id,name,zone_type,geometry,enabled,object_types,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (zone["zone_id"],zone.get("camera_id"),zone["name"],zone.get("zone_type", "RESTRICTED"),json.dumps(zone.get("geometry",[])),int(zone.get("enabled",True)),obj_types,stamp,stamp))
        
        # Load all zones from database into the spatial engine
        all_zones = rows(self.db.execute("SELECT * FROM zones"))
        self.spatial_engine.load_zones(all_zones)

        self.db.execute("UPDATE alerts SET status='RESOLVED',resolved_at=?,resolved_by='system' WHERE status='ACTIVE' AND event_id IN (SELECT events.event_id FROM events JOIN cameras ON cameras.camera_id=events.camera_id WHERE events.event_type='CAMERA_OFFLINE' AND cameras.status='ONLINE')", (stamp,))
        self.db.execute("UPDATE events SET description = 'Camera ' || camera_id || ' offline' WHERE event_type = 'CAMERA_OFFLINE' AND description = 'SYSTEM detected'")
        self.db.commit()

    def reload_zones(self) -> list[dict[str, Any]]:
        """Reload all zones from database into the spatial engine."""
        all_zones = rows(self.db.execute("SELECT * FROM zones"))
        self.spatial_engine.load_zones(all_zones)
        return all_zones

    refresh_zones_from_db = reload_zones


    async def broadcast(self, topic: str, data: dict[str, Any]) -> None:
        stale=[]
        for socket in self.subscribers:
            try: await socket.send_json({"topic":topic,"data":data})
            except Exception: stale.append(socket)
        self.subscribers.difference_update(stale)

    def expire_stale_tracks(self) -> int:
        """End lost tracks and close their one-per-track lifecycle event."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.track_timeout_seconds)
        active_tracks = self.db.execute("SELECT * FROM tracks WHERE status='ACTIVE'").fetchall()
        stale_tracks = [track for track in active_tracks if datetime.fromisoformat(track["last_seen_at"]).astimezone(UTC) < cutoff]
        for track in stale_tracks:
            started = datetime.fromisoformat(track["created_at"]).astimezone(UTC)
            ended = datetime.fromisoformat(track["last_seen_at"]).astimezone(UTC)
            duration = max(0.0, (ended - started).total_seconds())
            self.db.execute("UPDATE tracks SET status='ENDED',ended_at=? WHERE track_id=?", (track["last_seen_at"], track["track_id"]))
            if track["event_id"]:
                description = f"{track['object_type']} track {track['track_id']} ended after {duration:.1f}s ({track['detection_count']} detections)."
                self.db.execute("UPDATE events SET status='CLOSED',ended_at=?,duration_seconds=?,description=? WHERE event_id=?", (track["last_seen_at"], duration, description, track["event_id"]))
            self.spatial_engine.purge_track(track["camera_id"], track["track_id"])
            if hasattr(self.vehicle_pipeline, "stabilizer"):
                self.vehicle_pipeline.stabilizer.remove_track(track["track_id"])
            ended_track = item(self.db.execute("SELECT * FROM tracks WHERE track_id=?", (track["track_id"],)).fetchone())
            if ended_track:
                self.observation_layer.create_or_update_observation(ended_track)
                try:
                    import asyncio
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.broadcast("track", ended_track))
                except RuntimeError:
                    pass
        if stale_tracks:
            self.db.commit()
        return len(stale_tracks)


    def _track(self, observation: dict[str, Any], stamp: str) -> tuple[str, bool]:
        """Persist the tracker identity; ByteTrack associates moving objects across consecutive frames."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.track_timeout_seconds)
        active = self.db.execute("SELECT * FROM tracks WHERE status='ACTIVE'").fetchall()
        stale = [track["track_id"] for track in active if datetime.fromisoformat(track["last_seen_at"]).astimezone(UTC) < cutoff]
        if stale: self.expire_stale_tracks()
        source_track_id = observation.get("attributes", {}).get("source_track_id")
        candidates = [track for track in active if track["track_id"] not in stale and track["camera_id"] == observation["camera_id"] and track["object_type"] == observation["object_type"]]
        if source_track_id:
            best = next((track for track in candidates if track["source_track_id"] == source_track_id), None)
        else:
            best = None
        if best is None and not source_track_id:
            tracker_mgr = getattr(self, "tracker_manager", None)
            if tracker_mgr:
                matched_tracks = tracker_mgr.track(
                    camera_id=observation["camera_id"],
                    detections=[observation],
                    timestamp=stamp,
                    frame=observation.get("image"),
                )
                if matched_tracks:
                    trk = matched_tracks[0]
                    assigned_source_id = f"bytetrack:{trk.track_id}"
                    observation.setdefault("attributes", {})["source_track_id"] = assigned_source_id
                    observation["attributes"]["tracking_state"] = trk.state
                    observation["attributes"]["reliability_score"] = trk.reliability_score
                    observation["attributes"]["recovery_count"] = trk.recovery_count
                    if trk.reliability_signals:
                        observation["attributes"]["reliability_signals"] = trk.reliability_signals
                    if getattr(trk, "reid_embeddings", None):
                        observation["attributes"]["reid_embedding"] = trk.get_representative_embedding()
                    source_track_id = assigned_source_id
                    best = next((track for track in candidates if track["source_track_id"] == source_track_id), None)

                # Persist any recoveries emitted by the recovery manager
                recoveries = tracker_mgr.get_recent_recoveries(observation["camera_id"])
                for rec in recoveries:
                    try:
                        self.db.execute(
                            """INSERT INTO track_recoveries (recovery_id, original_track_id, restored_track_id, camera_id, timestamp, appearance_similarity, position_distance, motion_consistency, iou_score, composite_cost, created_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                f"rec_{uuid.uuid4().hex[:8]}",
                                str(rec.original_track_id),
                                str(rec.original_track_id),
                                rec.camera_id,
                                rec.timestamp,
                                rec.appearance_similarity,
                                rec.position_distance,
                                rec.motion_consistency,
                                rec.iou_score,
                                rec.composite_cost,
                                datetime.now(UTC).isoformat(),
                            ),
                        )
                    except Exception:
                        pass

            if best is None and not source_track_id:
                best = max(candidates, key=lambda track: iou(json.loads(track["current_position"]), observation["bounding_box"]), default=None)
                if best and iou(json.loads(best["current_position"]), observation["bounding_box"]) < 0.25:
                    best = None
        if best is None:
            # Reconnection check: if an object was briefly lost or occluded,
            # allow re-acquiring the same track rather than losing track of the object.
            recent_ended = self.db.execute(
                "SELECT * FROM tracks WHERE status='ENDED' AND camera_id=? AND object_type=? ORDER BY ended_at DESC LIMIT 5",
                (observation["camera_id"], observation["object_type"])
            ).fetchall()
            if recent_ended:
                try:
                    current_dt = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if "T" in stamp else datetime.now(UTC)
                    for cand in recent_ended:
                        cand_end_str = cand["ended_at"] or cand["last_seen_at"]
                        if not cand_end_str:
                            continue
                        cand_dt = datetime.fromisoformat(cand_end_str.replace("Z", "+00:00"))
                        gap_sec = abs((current_dt - cand_dt).total_seconds())
                        if gap_sec <= 10.0:
                            if source_track_id and cand["source_track_id"] == source_track_id:
                                best = cand
                                self.db.execute("UPDATE tracks SET status='ACTIVE', ended_at=NULL WHERE track_id=?", (cand["track_id"],))
                                break
                            if cand.get("current_position"):
                                try:
                                    cand_box = json.loads(cand["current_position"])
                                    if iou(cand_box, observation["bounding_box"]) >= 0.20:
                                        best = cand
                                        self.db.execute("UPDATE tracks SET status='ACTIVE', ended_at=NULL WHERE track_id=?", (cand["track_id"],))
                                        break
                                except Exception:
                                    pass
                except Exception:
                    pass
        if best:
            track_id = best["track_id"]
            is_new = False
        else:
            prefix = PREFIX.get(observation["object_type"], "O")
            track_id = f"#{prefix}-{uuid.uuid4().hex[:6].upper()}"
            is_new = True

        snap = self.movement_tracker.update(
            track_id=track_id,
            camera_id=observation["camera_id"],
            object_type=observation["object_type"],
            bounding_box=observation["bounding_box"],
            timestamp=stamp,
        )
        observation.setdefault("attributes", {})["movement"] = snap.to_dict()
        observation["attributes"]["speed"] = snap.speed
        observation["attributes"]["speed_unit"] = snap.speed_unit
        observation["attributes"]["speed_kmh"] = snap.speed_kmh
        observation["attributes"]["direction"] = snap.direction
        observation["attributes"]["heading"] = snap.heading_deg
        observation["attributes"]["movement_state"] = snap.movement_state
        observation["attributes"]["distance_travelled"] = snap.distance_travelled
        if snap.movement_change:
            observation["attributes"]["movement_change"] = snap.movement_change

        try:
            self.db.execute(
                """INSERT INTO track_movements (track_id, camera_id, object_type, timestamp, position, speed, speed_unit, speed_kmh, direction, heading_deg, movement_state, distance_travelled, movement_change)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    track_id,
                    observation["camera_id"],
                    observation["object_type"],
                    stamp,
                    json.dumps(observation["bounding_box"]),
                    snap.speed,
                    snap.speed_unit,
                    snap.speed_kmh,
                    snap.direction,
                    snap.heading_deg,
                    snap.movement_state,
                    snap.distance_travelled,
                    snap.movement_change,
                ),
            )
        except Exception:
            pass

        obs_attrs = observation.get("attributes", {})
        rel_score = float(obs_attrs.get("reliability_score", 1.0) or 1.0)
        rec_cnt = int(obs_attrs.get("recovery_count", 0) or 0)
        reid_emb = obs_attrs.get("reid_embedding")
        reid_str = json.dumps(reid_emb) if reid_emb else None

        if not is_new:
            average = (best["average_confidence"] + observation["confidence"]) / 2
            count = best["detection_count"] + 1
            maximum = max(best["max_confidence"] or best["average_confidence"], observation["confidence"])
            existing_attrs = best["attributes"] if "attributes" in best.keys() else {}
            if isinstance(existing_attrs, str):
                try: existing_attrs = json.loads(existing_attrs)
                except Exception: existing_attrs = {}
            elif not isinstance(existing_attrs, dict):
                existing_attrs = {}
            merged_attrs = {**existing_attrs, **obs_attrs}
            observation["attributes"] = merged_attrs
            if not rec_cnt and "recovery_count" in best.keys() and best["recovery_count"]:
                rec_cnt = best["recovery_count"]
            if not reid_str and "reid_embedding" in best.keys() and best["reid_embedding"]:
                reid_str = best["reid_embedding"]

            self.db.execute(
                "UPDATE tracks SET last_seen_at=?,average_confidence=?,current_position=?,detection_count=?,max_confidence=?,speed=?,heading=?,direction=?,movement_state=?,attributes=?,reliability_score=?,recovery_count=?,reid_embedding=? WHERE track_id=?",
                (
                    stamp,
                    average,
                    json.dumps(observation["bounding_box"]),
                    count,
                    maximum,
                    snap.speed,
                    snap.heading_deg,
                    snap.direction,
                    snap.movement_state,
                    json.dumps(merged_attrs),
                    rel_score,
                    rec_cnt,
                    reid_str,
                    best["track_id"],
                ),
            )
            self.db.execute("INSERT INTO track_positions VALUES (?,?,?,?)", (best["track_id"], stamp, json.dumps(observation["bounding_box"]), observation["confidence"]))
            return best["track_id"], False

        self.db.execute(
            "INSERT INTO tracks (track_id,camera_id,object_type,created_at,last_seen_at,status,average_confidence,current_position,source_track_id,max_confidence,speed,heading,direction,movement_state,attributes,reliability_score,recovery_count,reid_embedding) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                track_id,
                observation["camera_id"],
                observation["object_type"],
                stamp,
                stamp,
                "ACTIVE",
                observation["confidence"],
                json.dumps(observation["bounding_box"]),
                source_track_id,
                observation["confidence"],
                snap.speed,
                snap.heading_deg,
                snap.direction,
                snap.movement_state,
                json.dumps(observation["attributes"]),
                rel_score,
                rec_cnt,
                reid_str,
            ),
        )
        self.db.execute("INSERT INTO track_positions VALUES (?,?,?,?)", (track_id, stamp, json.dumps(observation["bounding_box"]), observation["confidence"]))
        return track_id, True

    def _zone_for(self, observation: dict[str, Any]) -> str | None:
        if observation.get("zone_id"): return observation["zone_id"]
        bbox = observation.get("bounding_box")
        if not bbox or len(bbox) < 4: return None
        bc = box_bottom_center(bbox)
        zone = self.spatial_engine.get_zone_for_point(observation["camera_id"], bc)
        if zone: return zone.zone_id
        for z in self.db.execute("SELECT zone_id,geometry FROM zones WHERE camera_id=? AND enabled=1",(observation["camera_id"],)):
            try:
                if point_in_polygon(bc, json.loads(z["geometry"])): return z["zone_id"]
            except Exception: pass
        return None

    def _associate_face_with_human(self, face_track_id: str, observation: dict[str, Any], stamp: str) -> str | None:
        """Associate an ingested FACE observation and its track with an active HUMAN target on the same camera."""
        face_box = observation.get("bounding_box")
        if not face_box:
            return None
        camera_id = observation["camera_id"]
        human_candidates = [
            item(r) for r in self.db.execute(
                "SELECT * FROM tracks WHERE camera_id=? AND object_type='HUMAN' AND status='ACTIVE'",
                (camera_id,),
            ).fetchall()
        ]
        matched_human, score = find_matching_human_track(face_box, human_candidates)
        if matched_human:
            human_id = matched_human["track_id"]
            face_attrs = observation.setdefault("attributes", {})
            face_attrs["associated_human_id"] = human_id
            face_attrs["associated_human_box"] = matched_human.get("current_position")
            face_attrs["face_human_match_score"] = round(score, 3)
            try:
                self.db.execute(
                    "UPDATE tracks SET parent_track_id=?, attributes=? WHERE track_id=?",
                    (human_id, json.dumps(face_attrs), face_track_id),
                )
            except Exception:
                self.db.execute(
                    "UPDATE tracks SET attributes=? WHERE track_id=?",
                    (json.dumps(face_attrs), face_track_id),
                )
            h_attrs = matched_human.get("attributes") or {}
            if isinstance(h_attrs, str):
                try: h_attrs = json.loads(h_attrs)
                except Exception: h_attrs = {}
            elif not isinstance(h_attrs, dict):
                h_attrs = {}
            h_attrs["has_face"] = True
            h_attrs["associated_face_id"] = face_track_id
            h_attrs["face_box"] = face_box
            h_attrs["face_confidence"] = observation["confidence"]
            h_attrs["face_last_seen_at"] = stamp
            h_attrs["face_match_score"] = round(score, 3)
            self.db.execute(
                "UPDATE tracks SET attributes=? WHERE track_id=?",
                (json.dumps(h_attrs), human_id),
            )
            return human_id
        return None

    def _associate_human_with_face(self, human_track_id: str, observation: dict[str, Any], stamp: str) -> str | None:
        """Associate an ingested HUMAN observation with active FACE targets on the same camera."""
        human_box = observation.get("bounding_box")
        if not human_box:
            return None
        camera_id = observation["camera_id"]
        face_candidates = [
            item(r) for r in self.db.execute(
                "SELECT * FROM tracks WHERE camera_id=? AND object_type='FACE' AND status='ACTIVE'",
                (camera_id,),
            ).fetchall()
        ]
        matched_face, score = find_matching_face_track(human_box, face_candidates)
        if matched_face:
            face_id = matched_face["track_id"]
            h_attrs = observation.setdefault("attributes", {})
            h_attrs["has_face"] = True
            h_attrs["associated_face_id"] = face_id
            face_pos = matched_face.get("current_position")
            if isinstance(face_pos, str):
                try: face_pos = json.loads(face_pos)
                except Exception: pass
            h_attrs["face_box"] = face_pos
            h_attrs["face_confidence"] = matched_face.get("average_confidence", 0.9)
            h_attrs["face_last_seen_at"] = stamp
            h_attrs["face_match_score"] = round(score, 3)
            self.db.execute(
                "UPDATE tracks SET attributes=? WHERE track_id=?",
                (json.dumps(h_attrs), human_track_id),
            )
            f_attrs = matched_face.get("attributes") or {}
            if isinstance(f_attrs, str):
                try: f_attrs = json.loads(f_attrs)
                except Exception: f_attrs = {}
            elif not isinstance(f_attrs, dict):
                f_attrs = {}
            f_attrs["associated_human_id"] = human_track_id
            f_attrs["associated_human_box"] = human_box
            f_attrs["face_human_match_score"] = round(score, 3)
            try:
                self.db.execute(
                    "UPDATE tracks SET parent_track_id=?, attributes=? WHERE track_id=?",
                    (human_track_id, json.dumps(f_attrs), face_id),
                )
            except Exception:
                self.db.execute(
                    "UPDATE tracks SET attributes=? WHERE track_id=?",
                    (json.dumps(f_attrs), face_id),
                )
            return face_id
        return None

    def _event(self, event_type: str, obs: dict[str, Any], track_id: str, stamp: str, severity: str="INFO") -> dict[str, Any]:
        event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}"
        if event_type == "CAMERA_OFFLINE":
            description = f"Camera {obs.get('camera_id', 'system')} offline"
        elif event_type in {"CAMERA_OBSTRUCTION", "CAMERA_VISIBILITY_DEGRADED"}:
            cond = (obs.get("attributes") or {}).get("condition", event_type)
            description = f"Camera {obs.get('camera_id', 'system')} {cond.replace('_', ' ').lower()}"
        elif obs.get("object_type") == "SYSTEM":
            description = f"System Event: {event_type.replace('_', ' ').title()}"
        elif obs.get("object_type") in {"UNCLASSIFIED", "MOTION"}:
            description = "Unclassified motion detected"
        elif obs.get("object_type") == "VEHICLE":
            v_intel = (obs.get("attributes") or {}).get("vehicle_intelligence") or {}
            c = (v_intel.get("color") or "").title() if v_intel.get("color") and v_intel.get("color") != "unknown" else ""
            t = (v_intel.get("type") or "").title() if v_intel.get("type") and v_intel.get("type") != "unknown" else ""
            if c and t:
                description = f"{c} {t} detected"
            elif c:
                description = f"{c} Vehicle detected"
            elif t:
                description = f"{t} detected"
            else:
                description = "Vehicle detected"
        else:
            description = f"{obs['object_type'].title()} detected"
        self.db.execute("INSERT INTO events (event_id,event_type,timestamp,camera_id,track_id,zone_id,severity,status,confidence,description,created_at,object_type,attributes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (event_id,event_type,stamp,obs["camera_id"],track_id,obs.get("zone_id"),severity,"OPEN",obs["confidence"],description,stamp,obs["object_type"],json.dumps(obs.get("attributes",{}))))
        return item(self.db.execute("SELECT * FROM events WHERE event_id=?",(event_id,)).fetchone())

    def _alert_for(self, event: dict[str, Any]) -> dict[str, Any] | None:
        matching=next((r for r in self.settings.alert_rules if r.get("event_type")==event["event_type"]),None)
        if not matching:
            if event.get("event_type") == "INTRUSION":
                matching = {"rule_id": "intrusion-detected", "event_type": "INTRUSION", "severity": "HIGH", "cooldown_seconds": 15}
            elif event.get("event_type") == "RESTRICTED_ZONE_ENTRY":
                matching = {"rule_id": "restricted-zone-entry", "event_type": "RESTRICTED_ZONE_ENTRY", "severity": "HIGH", "cooldown_seconds": 15}
            elif event.get("event_type") == "LOITERING":
                matching = {"rule_id": "loitering-detected", "event_type": "LOITERING", "severity": "HIGH", "cooldown_seconds": 20}
            elif event.get("event_type") == "CAMERA_OBSTRUCTION":
                matching = {"rule_id": "camera-obstruction", "event_type": "CAMERA_OBSTRUCTION", "severity": "CRITICAL", "cooldown_seconds": 30}
            elif event.get("event_type") == "CAMERA_VISIBILITY_DEGRADED":
                matching = {"rule_id": "camera-visibility-degraded", "event_type": "CAMERA_VISIBILITY_DEGRADED", "severity": "HIGH", "cooldown_seconds": 45}
            else:
                return None
        key=(matching["rule_id"],event.get("camera_id"),event.get("zone_id")); current=datetime.now(UTC)
        last=self.cooldowns.get(key)
        if last and (current-last).total_seconds()<matching.get("cooldown_seconds",30): return None
        self.cooldowns[key]=current
        alert_id=f"ALT-{uuid.uuid4().hex[:12].upper()}"; stamp=now()
        v_intel = (event.get("attributes") or {}).get("vehicle_intelligence") or {}
        v_suffix = ""
        if v_intel:
            c = (v_intel.get("color") or "").title() if v_intel.get("color") and v_intel.get("color") != "unknown" else ""
            t = (v_intel.get("type") or "").title() if v_intel.get("type") and v_intel.get("type") != "unknown" else ""
            if c and t: v_suffix = f" ({c} {t})"
            elif c: v_suffix = f" ({c} Vehicle)"
            elif t: v_suffix = f" ({t})"
        message=f"{event['event_type'].replace('_',' ').title()} at {event.get('camera_id') or 'system'}{v_suffix}"
        self.db.execute("INSERT INTO alerts (alert_id,event_id,timestamp,alert_type,severity,status,message,created_at) VALUES (?,?,?,?,?,'ACTIVE',?,?)",(alert_id,event["event_id"],stamp,matching["rule_id"],matching["severity"],message,stamp))
        return item(self.db.execute("SELECT * FROM alerts WHERE alert_id=?",(alert_id,)).fetchone())


    def record_evidence(self, event_id: str, evidence_type: str = "SNAPSHOT", storage_reference: str = "", integrity_hash: str | None = None, jpeg_bytes: bytes | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        # Enforce exactly one capture per unique event_id
        if event_id:
            existing = item(self.db.execute("SELECT * FROM evidence WHERE event_id=?", (event_id,)).fetchone())
            if existing:
                return existing

        evidence_id = f"EVD-{uuid.uuid4().hex[:12].upper()}"
        stamp = now()
        if not integrity_hash:
            integrity_hash = f"sha256:{uuid.uuid4().hex[:16]}"
        if not storage_reference or "/stream" in storage_reference:
            storage_reference = f"/api/v1/evidence/{evidence_id}/file"

        if jpeg_bytes:
            try:
                self.settings.evidence_directory.mkdir(parents=True, exist_ok=True)
                (self.settings.evidence_directory / f"{evidence_id}.jpg").write_bytes(jpeg_bytes)
            except Exception:
                pass

        self.db.execute(
            "INSERT INTO evidence (evidence_id,event_id,type,storage_reference,timestamp,created_at,integrity_hash,metadata) VALUES (?,?,?,?,?,?,?,?)",
            (evidence_id, event_id, evidence_type.upper(), storage_reference, stamp, stamp, integrity_hash, json.dumps(metadata or {}))
        )
        # Ring buffer: limit evidence cache to 30 items & purge files
        stale_evidence = [item(r) for r in self.db.execute("SELECT evidence_id FROM evidence WHERE evidence_id NOT IN (SELECT evidence_id FROM evidence ORDER BY created_at DESC LIMIT 30)").fetchall()]
        for st in stale_evidence:
            try:
                (self.settings.evidence_directory / f"{st['evidence_id']}.jpg").unlink(missing_ok=True)
            except Exception:
                pass
        self.db.execute(
            "DELETE FROM evidence WHERE evidence_id NOT IN (SELECT evidence_id FROM evidence ORDER BY created_at DESC LIMIT 30)"
        )
        self.db.commit()
        return item(self.db.execute("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone())

    def clear_evidence(self) -> int:
        stale_evidence = [item(r) for r in self.db.execute("SELECT evidence_id FROM evidence").fetchall()]
        for st in stale_evidence:
            try:
                (self.settings.evidence_directory / f"{st['evidence_id']}.jpg").unlink(missing_ok=True)
            except Exception:
                pass
        cursor = self.db.execute("DELETE FROM evidence")
        self.db.commit()
        return cursor.rowcount

    def clear_events(self, clear_alerts: bool = True) -> dict[str, int]:
        ev_cursor = self.db.execute("DELETE FROM events")
        ev_count = ev_cursor.rowcount
        al_count = 0
        if clear_alerts:
            al_cursor = self.db.execute("DELETE FROM alerts")
            al_count = al_cursor.rowcount
        self.db.execute("UPDATE tracks SET event_id = NULL WHERE event_id IS NOT NULL")
        self.db.execute("DELETE FROM incident_events WHERE event_id NOT IN (SELECT event_id FROM events)")
        self.db.execute("DELETE FROM incidents WHERE incident_id NOT IN (SELECT DISTINCT incident_id FROM incident_events)")
        self.db.commit()
        return {"events_cleared": ev_count, "alerts_cleared": al_count}

    def clear_all_cache(self) -> dict[str, Any]:
        """Purge temporary storage, evidence caches, ended track states, and transient buffers."""
        ev_count = self.clear_evidence()
        th_res = self.clear_ended_threads()
        th_count = th_res.get("cleared_count", 0)
        if hasattr(self, "tracker") and hasattr(self.tracker, "_class_cache"):
            self.tracker._class_cache.clear()
        if hasattr(self, "camera_hub") and hasattr(self.camera_hub, "latest_frames"):
            self.camera_hub.latest_frames.clear()
        return {
            "status": "cleared",
            "evidence_deleted": ev_count,
            "ended_threads_cleared": th_count,
        }

    def get_zones(self, camera_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve configured zones, optionally filtered by camera."""
        query = "SELECT * FROM zones"
        args: list[Any] = []
        if camera_id:
            query += " WHERE camera_id=?"
            args.append(camera_id)
        query += " ORDER BY created_at DESC, zone_id ASC"
        return rows(self.db.execute(query, tuple(args)))

    def get_zone(self, zone_id: str) -> dict[str, Any] | None:
        """Retrieve single zone by identifier."""
        return item(self.db.execute("SELECT * FROM zones WHERE zone_id=?", (zone_id,)).fetchone())

    def create_zone(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new spatial zone and register it with the spatial engine."""
        stamp = now()
        zone_id = payload.get("zone_id") or f"ZONE-{uuid.uuid4().hex[:6].upper()}"
        camera_id = payload["camera_id"]
        name = payload.get("name") or f"Zone {zone_id}"
        zone_type = str(payload.get("zone_type", "RESTRICTED")).upper()
        geometry = payload.get("geometry", [])
        enabled = int(payload.get("enabled", True))
        object_types = payload.get("object_types", ["HUMAN", "VEHICLE"])
        if not isinstance(object_types, list):
            object_types = ["HUMAN", "VEHICLE"]
        capacity = int(payload.get("capacity") or payload.get("max_capacity") or 10)

        self.db.execute(
            "INSERT INTO zones (zone_id, camera_id, name, zone_type, geometry, enabled, object_types, capacity, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (zone_id, camera_id, name, zone_type, json.dumps(geometry), enabled, json.dumps(object_types), capacity, stamp, stamp)
        )
        self.db.commit()
        created = self.get_zone(zone_id)
        if created:
            self.spatial_engine.add_or_update_zone(created)
        return created or {}

    def update_zone(self, zone_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing spatial zone and synchronize the spatial engine."""
        existing = self.get_zone(zone_id)
        if not existing:
            return None
        stamp = now()
        name = payload.get("name", existing["name"])
        zone_type = str(payload.get("zone_type") or existing.get("zone_type", "RESTRICTED")).upper()
        geometry = payload.get("geometry", existing["geometry"])
        enabled = int(payload.get("enabled", existing["enabled"]))
        object_types = payload.get("object_types", existing.get("object_types", ["HUMAN", "VEHICLE"]))
        if not isinstance(object_types, list):
            object_types = ["HUMAN", "VEHICLE"]
        capacity = int(payload.get("capacity") or payload.get("max_capacity") or existing.get("capacity") or 10)

        self.db.execute(
            "UPDATE zones SET name=?, zone_type=?, geometry=?, enabled=?, object_types=?, capacity=?, updated_at=? WHERE zone_id=?",
            (name, zone_type, json.dumps(geometry), enabled, json.dumps(object_types), capacity, stamp, zone_id)
        )
        self.db.commit()
        updated = self.get_zone(zone_id)
        if updated:
            self.spatial_engine.add_or_update_zone(updated)
        return updated

    def delete_zone(self, zone_id: str) -> bool:
        """Delete a spatial zone and purge its state from the spatial engine."""
        cursor = self.db.execute("DELETE FROM zones WHERE zone_id=?", (zone_id,))
        self.db.commit()
        if cursor.rowcount > 0:
            self.spatial_engine.remove_zone(zone_id)
            return True
        return False

    def get_live_people_density(
        self,
        camera_id: str | None = None,
        zone_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Continuously compute live people count, density status, and crowd anomaly for monitored zones.

        Reuses existing YOLO person detection and ByteTrack tracking architecture without adding new models.
        Live-only: stale tracks are expired before evaluation so counts strictly reflect currently present individuals.
        """
        stale_count = self.expire_stale_tracks()
        if stale_count > 0:
            self.db.commit()

        cameras_map = {c["camera_id"]: c["name"] for c in rows(self.db.execute("SELECT camera_id, name FROM cameras"))}

        query = "SELECT * FROM zones WHERE zone_type='MONITORED' AND enabled=1"
        args: list[Any] = []
        if zone_id:
            query += " AND zone_id=?"
            args.append(zone_id)
        elif camera_id:
            query += " AND camera_id=?"
            args.append(camera_id)
        query += " ORDER BY camera_id ASC, name ASC"

        monitored_zones = rows(self.db.execute(query, tuple(args)))
        if not monitored_zones and zone_id:
            alt = rows(self.db.execute("SELECT * FROM zones WHERE zone_id=?", (zone_id,)))
            if alt:
                monitored_zones = alt

        if not monitored_zones:
            return []

        active_human_tracks = rows(
            self.db.execute(
                "SELECT track_id, camera_id, current_position, last_seen_at FROM tracks WHERE status='ACTIVE' AND object_type='HUMAN'"
            )
        )

        tracks_by_camera: dict[str, list[tuple[str, tuple[float, float]]]] = defaultdict(list)
        for trk in active_human_tracks:
            pos = trk.get("current_position")
            if isinstance(pos, str):
                try:
                    pos = json.loads(pos)
                except Exception:
                    pos = None
            if pos and isinstance(pos, (list, tuple)) and len(pos) >= 4:
                bc = box_bottom_center(pos)
                tracks_by_camera[trk["camera_id"]].append((trk["track_id"], bc))

        results: list[dict[str, Any]] = []
        current_stamp = now()

        for z in monitored_zones:
            geom = z.get("geometry", [])
            if isinstance(geom, str):
                try:
                    geom = json.loads(geom)
                except Exception:
                    geom = []

            cam_id = z["camera_id"]
            cam_name = cameras_map.get(cam_id, cam_id)
            zone_name = z.get("name") or z["zone_id"]

            inside_tracks: list[str] = []
            if geom and len(geom) >= 3:
                for track_id, bc in tracks_by_camera.get(cam_id, []):
                    if point_in_polygon(bc, geom):
                        inside_tracks.append(track_id)

            unique_people_count = len(inside_tracks)
            max_capacity = max(1, int(z.get("capacity") or z.get("max_capacity") or 10))
            ratio = round(unique_people_count / max_capacity, 2)

            if unique_people_count == 0:
                density_status = "CLEAR"
            elif ratio <= 0.35:
                density_status = "LOW"
            elif ratio <= 0.75:
                density_status = "NORMAL"
            elif ratio <= 1.0:
                density_status = "HIGH"
            else:
                density_status = "OVERCROWDED"

            is_anomaly = unique_people_count > max_capacity
            anomaly_desc = (
                f"Crowd surge detected: {unique_people_count} people in {zone_name} (capacity: {max_capacity})"
                if is_anomaly
                else None
            )

            results.append({
                "zone_id": z["zone_id"],
                "zone_name": zone_name,
                "camera_id": cam_id,
                "camera_name": cam_name,
                "zone_type": z.get("zone_type", "MONITORED"),
                "enabled": bool(z.get("enabled", True)),
                "people_count": unique_people_count,
                "tracked_people": inside_tracks,
                "density_status": density_status,
                "density_ratio": min(1.0, ratio),
                "capacity": max_capacity,
                "max_capacity": max_capacity,
                "anomaly_threshold": max_capacity,
                "is_anomaly": is_anomaly,
                "anomaly_description": anomaly_desc,
                "geometry": geom,
                "last_updated": current_stamp,
            })

        return results

    async def ingest(self, observation: dict[str, Any]) -> dict[str, Any]:
        stamp = observation.get("timestamp") or now()
        observation["object_type"] = observation["object_type"].upper()
        observation["zone_id"] = self._zone_for(observation)
        detection_id = f"DET-{uuid.uuid4().hex[:12].upper()}"

        # Fetch camera reliability & condition to modulate confidence if degraded
        cam_id = observation.get("camera_id")
        cam_row = self.db.execute(
            "SELECT reliability_score, condition FROM camera_reliability WHERE camera_id=?",
            (cam_id,)
        ).fetchone() if cam_id else None

        rel_score = cam_row["reliability_score"] if (cam_row and cam_row["reliability_score"] is not None) else 100
        cam_cond = (cam_row["condition"] if cam_row else None) or "CLEAR"

        # Modulate confidence smoothly when reliability drops below nominal without dropping YOLO/tracking
        if rel_score < 100:
            scale_factor = (max(5, rel_score) / 100.0) ** 0.25
            raw_conf = float(observation.get("confidence", 0.9))
            observation["confidence"] = round(raw_conf * scale_factor, 4)

        observation.setdefault("attributes", {})
        observation["attributes"]["camera_reliability"] = rel_score
        observation["attributes"]["camera_condition"] = cam_cond

        track_id, is_new = self._track(observation, stamp)

        # Vehicle intelligence analysis for VEHICLE detections
        if observation["object_type"] == "VEHICLE":
            existing_vi = observation.get("attributes", {}).get("vehicle_intelligence")
            if not existing_vi:
                raw_image = observation.get("image")
                if raw_image is None and getattr(self, "camera_hub", None):
                    raw_jpeg = getattr(self.camera_hub, "get_snapshot_jpeg", lambda *a, **k: None)(observation["camera_id"])
                    if raw_jpeg:
                        try:
                            import cv2, numpy as np
                            raw_image = cv2.imdecode(np.frombuffer(raw_jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        except Exception:
                            raw_image = None
                source_cls = observation.get("attributes", {}).get("source_class")
                if raw_image is not None or source_cls:
                    existing_vi = self.vehicle_pipeline.analyze_vehicle(
                        raw_image,
                        observation.get("bounding_box"),
                        vehicle_id=track_id,
                        source_class=source_cls,
                    )
            if existing_vi:
                norm_vid = track_id.lstrip("#")
                existing_vi["vehicle_id"] = norm_vid
                observation.setdefault("attributes", {})["vehicle_intelligence"] = existing_vi
                if existing_vi.get("type"):
                    observation["attributes"]["vehicle_type"] = existing_vi["type"]
                if existing_vi.get("color"):
                    observation["attributes"]["vehicle_color"] = existing_vi["color"]
                try:
                    self.db.execute(
                        "UPDATE tracks SET attributes=? WHERE track_id=?",
                        (json.dumps(observation["attributes"]), track_id)
                    )
                except Exception:
                    pass

        # Cross-modal face & human tracking association
        if observation.get("object_type") == "FACE":
            self._associate_face_with_human(track_id, observation, stamp)
        elif observation.get("object_type") == "HUMAN":
            self._associate_human_with_face(track_id, observation, stamp)

        self.db.execute(
            "INSERT INTO detections VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                detection_id,
                observation["camera_id"],
                stamp,
                observation["object_type"],
                observation["confidence"],
                json.dumps(observation["bounding_box"]),
                observation.get("model_name"),
                observation.get("model_version"),
                track_id,
                observation.get("zone_id"),
                json.dumps(observation.get("attributes", {})),
            ),
        )

        # Evaluate spatial engine for confirmed intrusions, dwell, and loitering
        m_snap = self.movement_tracker.get_track_snapshot(track_id)
        mstate = m_snap["movement_state"] if m_snap else observation.get("movement_state", "STATIONARY")
        spatial_events = self.spatial_engine.process_observation(
            observation,
            track_id=track_id,
            is_new_track=is_new,
            movement_state=mstate,
        )

        event = None
        has_spatial_alert = False

        for s_evt in spatial_events:
            s_type = s_evt.get("event_type")
            if s_type == "INTRUSION":
                has_spatial_alert = True
                event_id = f"EVT-{uuid.uuid4().hex[:12].upper()}"
                direction = s_evt.get("direction", "OUTSIDE -> INSIDE")
                zone_name = s_evt.get("zone_name") or s_evt["zone_id"]
                obj_label = s_evt['object_type']
                if obj_label == "VEHICLE" and observation.get("attributes", {}).get("vehicle_intelligence"):
                    vi = observation["attributes"]["vehicle_intelligence"]
                    c = (vi.get("color") or "").title() if vi.get("color") and vi.get("color") != "unknown" else ""
                    t = (vi.get("type") or "").title() if vi.get("type") and vi.get("type") != "unknown" else ""
                    if c and t: obj_label = f"{c} {t}"
                    elif c: obj_label = f"{c} Vehicle"
                    elif t: obj_label = t
                desc = f"Intrusion detected: {obj_label} entered restricted zone {zone_name} ({direction})"
                self.db.execute(
                    "INSERT INTO events (event_id,event_type,timestamp,camera_id,track_id,zone_id,severity,status,confidence,description,created_at,object_type,direction,attributes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        event_id,
                        "INTRUSION",
                        stamp,
                        s_evt["camera_id"],
                        track_id,
                        s_evt["zone_id"],
                        "HIGH",
                        "OPEN",
                        s_evt["confidence"],
                        desc,
                        stamp,
                        s_evt["object_type"],
                        direction,
                        json.dumps(observation.get("attributes", {})),
                    ),
                )
                event = item(self.db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone())
                self.db.execute("UPDATE tracks SET event_id=? WHERE track_id=?", (event_id, track_id))

            elif s_type == "LOITERING":
                has_spatial_alert = True
                event_id = f"EVT-{uuid.uuid4().hex[:12].upper()}"
                zone_name = s_evt.get("zone_name") or s_evt["zone_id"]
                obj_label = s_evt['object_type']
                dur = s_evt.get("duration_seconds", 0.0)
                m_state = s_evt.get("movement_state", "STATIONARY")
                desc = f"Loitering alert: {obj_label} loitering in {zone_name} for {round(dur)}s (Movement: {m_state})"

                attrs = dict(observation.get("attributes", {}))
                attrs["loitering"] = {
                    "zone_id": s_evt["zone_id"],
                    "track_id": track_id,
                    "start_time": s_evt.get("start_time", stamp),
                    "duration_seconds": dur,
                    "movement_state": m_state,
                    "status": "LOITERING",
                }

                self.db.execute(
                    "INSERT INTO events (event_id,event_type,timestamp,camera_id,track_id,zone_id,severity,status,confidence,description,created_at,object_type,duration_seconds,attributes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        event_id,
                        "LOITERING",
                        stamp,
                        s_evt["camera_id"],
                        track_id,
                        s_evt["zone_id"],
                        "HIGH",
                        "OPEN",
                        s_evt["confidence"],
                        desc,
                        stamp,
                        s_evt["object_type"],
                        dur,
                        json.dumps(attrs),
                    ),
                )
                event = item(self.db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone())
                self.db.execute("UPDATE tracks SET event_id=? WHERE track_id=?", (event_id, track_id))

                # Save loitering session
                session_id = f"LOIT-{s_evt['zone_id']}-{track_id}"
                self.db.execute(
                    "INSERT INTO loitering_sessions (session_id,camera_id,zone_id,track_id,object_type,status,start_time,end_time,duration_seconds,movement_state,event_id,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(session_id) DO UPDATE SET status=excluded.status, duration_seconds=excluded.duration_seconds, movement_state=excluded.movement_state, event_id=excluded.event_id, updated_at=excluded.updated_at",
                    (
                        session_id,
                        s_evt["camera_id"],
                        s_evt["zone_id"],
                        track_id,
                        s_evt["object_type"],
                        "LOITERING",
                        s_evt.get("start_time", stamp),
                        None,
                        dur,
                        m_state,
                        event_id,
                        stamp,
                        stamp,
                    ),
                )

            elif s_type == "ZONE_EXIT":
                session_id = f"LOIT-{s_evt['zone_id']}-{track_id}"
                dur = s_evt.get("duration_seconds", 0.0)
                self.db.execute(
                    "UPDATE loitering_sessions SET status='RESOLVED', end_time=?, duration_seconds=?, updated_at=? WHERE session_id=?",
                    (stamp, dur, stamp, session_id),
                )
                self.db.execute(
                    "UPDATE events SET ended_at=?, duration_seconds=? WHERE track_id=? AND zone_id=? AND event_type='LOITERING' AND ended_at IS NULL",
                    (stamp, dur, track_id, s_evt["zone_id"]),
                )

        if not event and is_new:
            # Standard initial detection event (maintains backward compatibility)
            event_type = EVENT_FOR.get(observation["object_type"], f"{observation['object_type']}_DETECTED")
            severity = "INFO"
            if observation.get("zone_id"):
                zone = self.db.execute("SELECT zone_type FROM zones WHERE zone_id=?", (observation["zone_id"],)).fetchone()
                if zone and zone["zone_type"] == "RESTRICTED":
                    event_type, severity = "RESTRICTED_ZONE_ENTRY", "HIGH"
            event = self._event(event_type, observation, track_id, stamp, severity)
            self.db.execute("UPDATE tracks SET event_id=? WHERE track_id=?", (event["event_id"], track_id))

        alert = self._alert_for(event) if event else None

        # Auto-record evidence snapshot on visual events (intrusions, loitering, or initial detections)
        evidence = None
        if event and (has_spatial_alert or is_new):
            bbox = observation.get("bounding_box")
            jpeg_bytes = None
            if observation.get("image") is not None and bbox:
                jpeg_bytes = crop_bounding_box_jpeg(observation["image"], bbox)
            if not jpeg_bytes:
                hub = getattr(self, "camera_hub", None)
                if hub:
                    jpeg_bytes = hub.get_snapshot_jpeg(observation["camera_id"], bounding_box=bbox)
            evidence = self.record_evidence(
                event["event_id"],
                "SNAPSHOT",
                jpeg_bytes=jpeg_bytes,
                metadata=observation.get("attributes", {}),
            )
            self.db.commit()

        linked_event_id = event["event_id"] if event else (self.db.execute("SELECT event_id FROM tracks WHERE track_id=?", (track_id,)).fetchone() or [None])[0]

        # Facial Recognition Pipeline (YOLO Face Detection -> Face Crop -> ArcFace -> DB)
        face_result = None
        if observation.get("object_type") == "FACE" and hasattr(self, "face_recognition_manager"):
            try:
                face_result = self.face_recognition_manager.process_face_observation(
                    observation=observation,
                    track_id=track_id,
                    event_id=linked_event_id,
                )
            except Exception as f_err:
                LOGGER.warning("Face recognition processing failed: %s", f_err)

        # Intelligent Incident Correlation Engine
        incident = None
        is_dedup_alert = False
        if event:
            inc_obj, is_new_inc, is_dedup_alert = self.incident_correlator.correlate_event(
                event=event,
                observation=observation,
                alert=alert,
            )
            incident = inc_obj.to_dict()

        track_row = item(self.db.execute("SELECT * FROM tracks WHERE track_id=?", (track_id,)).fetchone())
        beh_event = None
        if track_row:
            self.observation_layer.create_or_update_observation(
                track=track_row,
                events=[event] if event else [],
                evidence_ids=[evidence["evidence_id"]] if evidence else [],
            )
            try:
                target_zone = track_row.get("zone_id") or observation.get("zone_id")
                z_row = item(self.db.execute("SELECT * FROM zones WHERE zone_id=?", (target_zone,)).fetchone()) if target_zone else None
                m_snap = self.movement_tracker.get_track_snapshot(track_id)
                density_info = None
                if observation.get("object_type") == "HUMAN" and target_zone:
                    dens_list = self.get_live_people_density(zone_id=target_zone)
                    if dens_list:
                        density_info = dens_list[0]

                beh_obj = self.behavioral_engine.evaluate_track_behavior(
                    track=track_row,
                    movement_snapshot=m_snap.to_dict() if hasattr(m_snap, "to_dict") else m_snap,
                    zone_row=z_row,
                    density_data=density_info,
                    events=[event] if event else [],
                    evidence_ids=[evidence["evidence_id"]] if evidence else [],
                )
                if beh_obj:
                    beh_event = beh_obj.to_dict()
            except Exception as b_err:
                LOGGER.warning("Behavioral analytics evaluation error: %s", b_err)

        result = {
            "detection_id": detection_id,
            "track_id": track_id,
            "track": track_row,
            "event": event,
            "event_id": linked_event_id,
            "alert": alert,
            "evidence": evidence,
            "incident": incident,
            "is_dedup_alert": is_dedup_alert,
            "face_recognition": face_result,
            "behavioral_event": beh_event,
        }
        await self.broadcast("observation", result)
        if track_row:
            await self.broadcast("track", track_row)
        if face_result:
            await self.broadcast("face_recognition", face_result)
        if beh_event:
            await self.broadcast("behavioral_anomaly", beh_event)
        if event:
            await self.broadcast("event", event)
        if alert and not is_dedup_alert:
            await self.broadcast("alert", alert)
        if incident:
            await self.broadcast("incident", incident)
        if evidence:
            await self.broadcast("evidence", evidence)
        if alert or incident or (beh_event and beh_event.get("anomaly_score", 0) >= 50):
            try:
                for ins in self.insights_engine.evaluate_telemetry():
                    await self.broadcast("insight", ins)
            except Exception:
                pass
        if observation.get("object_type") == "HUMAN":
            density_data = self.get_live_people_density(camera_id=observation["camera_id"])
            if density_data:
                await self.broadcast("zone_density", density_data)
        return result


    async def ingest_audio(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize an external acoustic classifier result into the shared event/alert flow."""
        source=payload["source_id"]; stamp=payload.get("timestamp") or now(); event_type=payload["event_type"].upper()
        self.db.execute("INSERT OR IGNORE INTO audio_sources VALUES (?,?, 'ONLINE', ?, ?)",(source,source,stamp,stamp))
        event=self._event(EVENT_FOR.get(event_type,"AUDIO_EVENT"),{"camera_id":source,"object_type":event_type,"confidence":payload["confidence"],"zone_id":None},"",stamp,"CRITICAL" if event_type=="EXPLOSION_LIKE" else "HIGH")
        alert=self._alert_for(event)
        self.db.commit(); result={"event":event,"alert":alert,"evidence":None}; await self.broadcast("audio",result); return result

    async def camera_status(self, camera_id: str, status: str) -> dict[str, Any]:
        stamp=now(); self.db.execute("UPDATE cameras SET status=?,updated_at=? WHERE camera_id=?",(status.upper(),stamp,camera_id)); self.db.commit()
        camera=item(self.db.execute("SELECT camera_id,name,source_type,location,status,enabled,created_at,updated_at FROM cameras WHERE camera_id=?",(camera_id,)).fetchone())
        if not camera: raise KeyError(camera_id)
        if status.upper()=="OFFLINE":
            existing = self.db.execute("SELECT 1 FROM events WHERE camera_id=? AND event_type='CAMERA_OFFLINE' AND status='OPEN'", (camera_id,)).fetchone()
            if not existing:
                event=self._event("CAMERA_OFFLINE",{"camera_id":camera_id,"object_type":"SYSTEM","confidence":1,"zone_id":None},"",stamp,"MEDIUM"); alert=self._alert_for(event); self.db.commit(); await self.broadcast("alert",alert or event)
        elif status.upper()=="ONLINE":
            self.db.execute("UPDATE events SET status='CLOSED',ended_at=? WHERE event_type='CAMERA_OFFLINE' AND camera_id=? AND status='OPEN'", (stamp, camera_id))
            self.db.execute("UPDATE alerts SET status='RESOLVED',resolved_at=?,resolved_by='system' WHERE status='ACTIVE' AND event_id IN (SELECT event_id FROM events WHERE event_type='CAMERA_OFFLINE' AND camera_id=?)", (stamp,camera_id))
            self.db.commit()
        await self.broadcast("camera",camera); return camera

    def camera_health(self, camera_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            """SELECT c.camera_id, c.status, c.enabled, c.stream_reference,
                      COALESCE(r.reliability_score, 100) AS reliability_score,
                      COALESCE(r.condition, 'CLEAR') AS condition,
                      COALESCE(r.condition_confidence, 1.0) AS condition_confidence,
                      r.condition_started_at, r.condition_details
               FROM cameras c
               LEFT JOIN camera_reliability r ON c.camera_id = r.camera_id
               WHERE c.camera_id = ?""",
            (camera_id,),
        ).fetchone()
        if not row: return None
        has_stream = bool(row["stream_reference"])
        rel_score = row["reliability_score"] if row["reliability_score"] is not None else 100
        cond = row["condition"] or "CLEAR"
        cond_conf = row["condition_confidence"] if row["condition_confidence"] is not None else 1.0
        details = {}
        if row["condition_details"]:
            try: details = json.loads(row["condition_details"])
            except Exception: pass
        return {
            "camera_id": row["camera_id"],
            "connection": row["status"],
            "stream_configured": has_stream,
            "stream_status": "AVAILABLE" if has_stream else "NOT_PROVIDED",
            "ai_status": "READY" if any(m.get("enabled") for m in self.settings.models) else "NOT_PROVIDED",
            "reliability_score": rel_score,
            "condition": cond,
            "condition_confidence": cond_conf,
            "condition_started_at": row["condition_started_at"],
            "metrics": details.get("metrics", {}),
            "reason": details.get("reason", None if has_stream else "No stream reference has been configured for this camera."),
            "fps": None,
            "latency_ms": None,
        }

    def record_camera_condition(
        self,
        camera_id: str,
        condition: str,
        reliability_score: int,
        confidence: float,
        reason: str,
        metrics: dict[str, Any],
        started_at: str,
        resolved_at: str | None = None,
        duration_seconds: float = 0.0,
    ) -> dict[str, Any]:
        """Update camera condition state, metrics history, and emit/resolve events and alerts."""
        stamp = now()
        details_json = json.dumps({"metrics": metrics, "reason": reason})

        # 1. Update camera_reliability table
        self.db.execute(
            """INSERT INTO camera_reliability
               (camera_id, reliability_score, condition, condition_confidence, condition_started_at, condition_details, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(camera_id) DO UPDATE SET
                   reliability_score = excluded.reliability_score,
                   condition = excluded.condition,
                   condition_confidence = excluded.condition_confidence,
                   condition_started_at = excluded.condition_started_at,
                   condition_details = excluded.condition_details,
                   updated_at = excluded.updated_at""",
            (camera_id, reliability_score, condition, confidence, started_at, details_json, stamp),
        )

        # 2. Insert into camera_metrics_history
        try:
            self.db.execute(
                """INSERT INTO camera_metrics_history
                   (camera_id, timestamp, brightness, contrast, laplacian_variance,
                    white_pixel_ratio, edge_density, frame_difference, vertical_edge_ratio,
                    patch_occlusion_ratio, raw_condition, reliability_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    camera_id,
                    stamp,
                    metrics.get("brightness", 0.0),
                    metrics.get("contrast", 0.0),
                    metrics.get("laplacian_variance", 0.0),
                    metrics.get("white_pixel_ratio", 0.0),
                    metrics.get("edge_density", 0.0),
                    metrics.get("frame_difference", 0.0),
                    metrics.get("vertical_edge_ratio", 1.0),
                    metrics.get("patch_occlusion_ratio", 0.0),
                    condition,
                    reliability_score,
                ),
            )
        except Exception:
            pass

        # 3. Handle camera_conditions table & events
        if condition != "CLEAR":
            # Record condition in camera_conditions table
            self.db.execute(
                """INSERT INTO camera_conditions
                   (camera_id, condition, reliability_score, confidence, reason, started_at, resolved_at, duration_seconds, details, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    camera_id,
                    condition,
                    reliability_score,
                    confidence,
                    reason,
                    started_at,
                    resolved_at,
                    duration_seconds,
                    details_json,
                    stamp,
                ),
            )

            # Determine event type & severity
            if condition in {"DEAD_FEED", "OBSTRUCTED", "FULL_WHITE_OVEREXPOSURE"}:
                evt_type = "CAMERA_OBSTRUCTION"
                severity = "CRITICAL"
            else:
                evt_type = "CAMERA_VISIBILITY_DEGRADED"
                severity = "HIGH"

            obs = {
                "camera_id": camera_id,
                "object_type": "CAMERA",
                "confidence": confidence,
                "attributes": {
                    "condition": condition,
                    "reliability_score": reliability_score,
                    "reason": reason,
                    "metrics": metrics,
                    "started_at": started_at,
                },
            }
            evt = self._event(evt_type, obs, f"trk_cam_{camera_id}", started_at, severity=severity)
            alert = self._alert_for(evt)
            if alert:
                try:
                    import asyncio
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.broadcast("alert", alert))
                except RuntimeError:
                    pass
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                loop.create_task(self.broadcast("event", evt))
            except RuntimeError:
                pass
        else:
            # Condition recovered to CLEAR: close open degraded events and alerts
            recovery_stamp = resolved_at or stamp
            self.db.execute(
                """UPDATE camera_conditions
                   SET resolved_at = ?, duration_seconds = ?
                   WHERE camera_id = ? AND resolved_at IS NULL""",
                (recovery_stamp, duration_seconds, camera_id),
            )
            self.db.execute(
                """UPDATE events
                   SET status = 'RESOLVED', ended_at = ?, duration_seconds = ?
                   WHERE camera_id = ? AND event_type IN ('CAMERA_VISIBILITY_DEGRADED', 'CAMERA_OBSTRUCTION') AND status = 'OPEN'""",
                (recovery_stamp, duration_seconds, camera_id),
            )
            self.db.execute(
                """UPDATE alerts
                   SET status = 'RESOLVED', resolved_at = ?, resolved_by = 'system'
                   WHERE status = 'ACTIVE' AND event_id IN (
                       SELECT event_id FROM events WHERE camera_id = ? AND event_type IN ('CAMERA_VISIBILITY_DEGRADED', 'CAMERA_OBSTRUCTION')
                   )""",
                (recovery_stamp, camera_id),
            )

        self.db.commit()

        # 4. Broadcast camera_condition update via WebSocket
        record_dict = {
            "camera_id": camera_id,
            "condition": condition,
            "reliability_score": reliability_score,
            "confidence": confidence,
            "reason": reason,
            "metrics": metrics,
            "started_at": started_at,
            "resolved_at": resolved_at,
            "duration_seconds": duration_seconds,
        }
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast("camera_condition", record_dict))
        except RuntimeError:
            pass

        return record_dict

    def get_camera_condition(self, camera_id: str) -> dict[str, Any] | None:
        """Get the latest condition and metrics for a camera."""
        cam = self.db.execute(
            """SELECT c.camera_id, c.name, c.status,
                      COALESCE(r.reliability_score, 100) AS reliability_score,
                      COALESCE(r.condition, 'CLEAR') AS condition,
                      COALESCE(r.condition_confidence, 1.0) AS condition_confidence,
                      r.condition_started_at, r.condition_details
               FROM cameras c
               LEFT JOIN camera_reliability r ON c.camera_id = r.camera_id
               WHERE c.camera_id = ?""",
            (camera_id,),
        ).fetchone()
        if not cam:
            return None

        recent_cond = self.db.execute(
            """SELECT * FROM camera_conditions WHERE camera_id = ? ORDER BY started_at DESC LIMIT 1""",
            (camera_id,),
        ).fetchone()

        details = {}
        if cam["condition_details"]:
            try: details = json.loads(cam["condition_details"])
            except Exception: pass
        metrics = details.get("metrics", {})
        reason = details.get("reason", "CCTV feed is clear and unobstructed" if (cam["condition"] or "CLEAR") == "CLEAR" else f"Condition: {cam['condition']}")

        now_dt = datetime.now(UTC)
        duration_s = 0.0
        if cam["condition_started_at"]:
            try:
                st = datetime.fromisoformat(cam["condition_started_at"]).astimezone(UTC)
                duration_s = max(0.0, (now_dt - st).total_seconds())
            except Exception:
                pass

        return {
            "camera_id": cam["camera_id"],
            "camera_name": cam["name"],
            "camera_status": cam["status"],
            "condition": cam["condition"] or "CLEAR",
            "reliability_score": cam["reliability_score"] if cam["reliability_score"] is not None else 100,
            "confidence": cam["condition_confidence"] if cam["condition_confidence"] is not None else 1.0,
            "reason": reason,
            "started_at": cam["condition_started_at"],
            "resolved_at": recent_cond["resolved_at"] if recent_cond else None,
            "duration_seconds": round(duration_s, 1),
            "metrics": metrics,
        }

    def get_camera_condition_history(self, camera_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get history of condition events for a camera."""
        rows_db = self.db.execute(
            """SELECT * FROM camera_conditions WHERE camera_id = ? ORDER BY started_at DESC LIMIT ?""",
            (camera_id, limit),
        ).fetchall()
        result = []
        for r in rows_db:
            d = dict(r)
            if d.get("details"):
                try:
                    d["details"] = json.loads(d["details"])
                except Exception:
                    pass
            result.append(d)
        return result

    def get_all_camera_conditions(self) -> list[dict[str, Any]]:
        """Get current condition for all configured cameras."""
        cams = self.db.execute(
            """SELECT camera_id FROM cameras ORDER BY camera_id"""
        ).fetchall()
        return [self.get_camera_condition(c["camera_id"]) for c in cams if c]

    def summary(self) -> dict[str, Any]:
        counts = defaultdict(int)
        for row in self.db.execute("SELECT status,COUNT(*) count FROM cameras GROUP BY status"):
            counts[row["status"].lower()] = row["count"]
        configured = self.db.execute("SELECT COUNT(*) FROM cameras WHERE stream_reference <> ''").fetchone()[0]
        evidence_total = self.db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        evidence_today = self.db.execute("SELECT COUNT(*) FROM evidence WHERE date(created_at)=date('now')").fetchone()[0]
        return {
            "cameras": {"online": counts["online"], "offline": counts["offline"], "configured": configured, "total": sum(counts.values())},
            "active_tracks": self.db.execute("SELECT COUNT(*) FROM tracks WHERE status='ACTIVE'").fetchone()[0],
            "total_tracks": self.db.execute("SELECT COUNT(*) FROM tracks").fetchone()[0],
            "events_today": self.db.execute("SELECT COUNT(*) FROM events WHERE date(timestamp)=date('now')").fetchone()[0],
            "total_events": self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "active_alerts": self.db.execute("SELECT COUNT(*) FROM alerts WHERE status='ACTIVE'").fetchone()[0],
            "evidence": {"total": evidence_total, "today": evidence_today},
            "evidence_count": evidence_total,
            "faces": self.face_recognition_manager.get_summary() if hasattr(self, "face_recognition_manager") else {"total_recognitions": 0, "recognized_count": 0, "unclassified_count": 0, "registered_persons_count": 0},
            "models": {"configured": sum(bool(m.get("enabled")) for m in self.settings.models), "total": len(self.settings.models)},
        }

    def get_analytics(self, timeframe: str = "24h") -> dict[str, Any]:
        timeframe = timeframe.lower()
        now_dt = datetime.now(UTC)
        max_ts_str = self.db.execute("SELECT MAX(timestamp) FROM events").fetchone()[0]
        if max_ts_str:
            max_dt = datetime.fromisoformat(max_ts_str).astimezone(UTC)
            ref_dt = max(now_dt, max_dt)
        else:
            ref_dt = now_dt

        if timeframe == "live":
            bucket_count = 12
            step = timedelta(minutes=5)
            format_str = "%H:%M"
            prev_start = ref_dt - timedelta(minutes=120)
            prev_end = ref_dt - timedelta(minutes=60)
        elif timeframe == "7d":
            bucket_count = 7
            step = timedelta(days=1)
            format_str = "%b %d"
            prev_start = ref_dt - timedelta(days=14)
            prev_end = ref_dt - timedelta(days=7)
        else:  # "24h"
            bucket_count = 24
            step = timedelta(hours=1)
            format_str = "%H:00"
            prev_start = ref_dt - timedelta(hours=48)
            prev_end = ref_dt - timedelta(hours=24)

        current_window_start = ref_dt - (step * bucket_count)
        buckets = []
        for i in range(bucket_count):
            b_start = current_window_start + (step * i)
            b_end = b_start + step
            label = b_start.strftime(format_str)
            b_start_iso, b_end_iso = b_start.isoformat(), b_end.isoformat()
            c_row = self.db.execute(
                "SELECT COUNT(*) as total, SUM(CASE WHEN severity IN ('CRITICAL', 'HIGH') THEN 1 ELSE 0 END) as restricted FROM events WHERE timestamp >= ? AND timestamp < ?",
                (b_start_iso, b_end_iso),
            ).fetchone()
            b_total = c_row["total"] if c_row else 0
            b_restricted = c_row["restricted"] if c_row and c_row["restricted"] else 0
            buckets.append({
                "label": label,
                "start": b_start_iso,
                "end": b_end_iso,
                "count": b_total,
                "restricted_count": b_restricted,
            })

        current_total = sum(b["count"] for b in buckets)
        prev_row = self.db.execute(
            "SELECT COUNT(*) FROM events WHERE timestamp >= ? AND timestamp < ?",
            (prev_start.isoformat(), prev_end.isoformat()),
        ).fetchone()
        prev_total = prev_row[0] if prev_row else 0

        if prev_total > 0:
            delta_pct = round(((current_total - prev_total) / prev_total) * 100)
            delta_str = f"{abs(delta_pct)}% {'↑' if delta_pct >= 0 else '↓'}"
        else:
            delta_str = "0% →" if current_total == 0 else f"+{current_total}"

        # Severity breakdown
        sev_counts = defaultdict(int)
        for r in self.db.execute("SELECT severity, COUNT(*) as c FROM events GROUP BY severity"):
            sev_counts[r["severity"].upper()] = r["c"]
        sev_total = sum(sev_counts.values()) or 1
        severities = {
            "critical": sev_counts["CRITICAL"],
            "high": sev_counts["HIGH"],
            "medium": sev_counts["MEDIUM"],
            "info": sev_counts["INFO"],
            "critical_pct": round((sev_counts["CRITICAL"] / sev_total) * 100, 1),
            "high_pct": round((sev_counts["HIGH"] / sev_total) * 100, 1),
            "medium_pct": round((sev_counts["MEDIUM"] / sev_total) * 100, 1),
            "info_pct": round((sev_counts["INFO"] / sev_total) * 100, 1),
        }

        # Peak hour in current window
        peak_b = max(buckets, key=lambda b: b["count"]) if buckets else None
        peak_hour = {"hour": peak_b["label"], "count": peak_b["count"]} if peak_b and peak_b["count"] > 0 else {"hour": "Nominal", "count": 0}
        avg_per_hour = round(current_total / max(1, bucket_count), 1)

        # Busiest camera
        busy_cam_row = self.db.execute(
            "SELECT camera_id, COUNT(*) as c FROM events WHERE timestamp >= ? GROUP BY camera_id ORDER BY c DESC LIMIT 1",
            (current_window_start.isoformat(),),
        ).fetchone()
        if not busy_cam_row:
            busy_cam_row = self.db.execute("SELECT camera_id, COUNT(*) as c FROM events GROUP BY camera_id ORDER BY c DESC LIMIT 1").fetchone()
        busiest_camera = busy_cam_row["camera_id"] if busy_cam_row else "CAM-01"

        # Median duration
        dur_rows = [r[0] for r in self.db.execute("SELECT duration_seconds FROM events WHERE duration_seconds IS NOT NULL AND duration_seconds > 0").fetchall()]
        if dur_rows:
            dur_rows.sort()
            median_duration = round(dur_rows[len(dur_rows) // 2], 1)
        else:
            median_duration = 24.0

        # Day / night split
        dn_row = self.db.execute(
            "SELECT SUM(CASE WHEN CAST(strftime('%H', timestamp) AS INTEGER) BETWEEN 6 AND 18 THEN 1 ELSE 0 END) as day_count, SUM(CASE WHEN CAST(strftime('%H', timestamp) AS INTEGER) NOT BETWEEN 6 AND 18 THEN 1 ELSE 0 END) as night_count FROM events"
        ).fetchone()
        day_count = dn_row["day_count"] if dn_row and dn_row["day_count"] else 0
        night_count = dn_row["night_count"] if dn_row and dn_row["night_count"] else 0
        dn_total = (day_count + night_count) or 1
        day_percent = round((day_count / dn_total) * 100)
        night_percent = 100 - day_percent

        # Camera breakdown
        cameras_list = []
        for cam in self.settings.cameras:
            cid = cam["camera_id"]
            ev_count = self.db.execute("SELECT COUNT(*) FROM events WHERE camera_id=?", (cid,)).fetchone()[0]
            al_count = self.db.execute("SELECT COUNT(*) FROM alerts WHERE event_id IN (SELECT event_id FROM events WHERE camera_id=?)", (cid,)).fetchone()[0]
            re_count = self.db.execute("SELECT COUNT(*) FROM events WHERE camera_id=? AND (severity IN ('CRITICAL', 'HIGH') OR zone_id IS NOT NULL)", (cid,)).fetchone()[0]
            cameras_list.append({
                "camera_id": cid,
                "name": cam.get("name", cid),
                "location": cam.get("location", ""),
                "status": cam.get("status", "ONLINE"),
                "events_count": ev_count,
                "alerts_count": al_count,
                "restricted_count": re_count,
            })

        # Object types breakdown
        obj_counts = defaultdict(int)
        for r in self.db.execute("SELECT object_type, COUNT(*) as c FROM tracks GROUP BY object_type"):
            obj_counts[r["object_type"].upper()] = r["c"]

        return {
            "timeframe": timeframe,
            "total_events": current_total,
            "delta_str": delta_str,
            "buckets": buckets,
            "severities": severities,
            "peak_hour": peak_hour,
            "avg_per_hour": avg_per_hour,
            "busiest_camera": busiest_camera,
            "median_duration_seconds": median_duration,
            "day_night": {
                "day_count": day_count,
                "night_count": night_count,
                "day_percent": day_percent,
                "night_percent": night_percent,
            },
            "cameras": cameras_list,
            "object_types": dict(obj_counts),
        }


    def get_track_thread(self, track_id: str, include_positions: bool = True) -> dict[str, Any] | None:
        track = item(self.db.execute("SELECT * FROM tracks WHERE track_id=?", (track_id,)).fetchone())
        if not track:
            track = item(self.db.execute("SELECT * FROM tracks WHERE track_id LIKE ?", (f"%{track_id}%",)).fetchone())
        if not track:
            return None

        tid = track["track_id"]
        if include_positions:
            positions = rows(self.db.execute("SELECT * FROM track_positions WHERE track_id=? ORDER BY timestamp ASC", (tid,)))
            positions_count = len(positions)
        else:
            positions = []
            positions_count = self.db.execute("SELECT COUNT(*) FROM track_positions WHERE track_id=?", (tid,)).fetchone()[0]

        events = rows(self.db.execute("SELECT * FROM events WHERE track_id=? OR (event_id=? AND event_id IS NOT NULL) ORDER BY timestamp ASC", (tid, track.get("event_id"))))
        detections = rows(self.db.execute("SELECT * FROM detections WHERE track_id=? ORDER BY timestamp ASC", (tid,)))
        
        event_ids = [e["event_id"] for e in events if e.get("event_id")]
        evidence_list = []
        if event_ids:
            placeholders = ",".join("?" * len(event_ids))
            evidence_list = rows(self.db.execute(f"SELECT * FROM evidence WHERE event_id IN ({placeholders}) ORDER BY created_at ASC", event_ids))

        v_intel = (track.get("attributes") or {}).get("vehicle_intelligence")
        if not v_intel:
            for d in detections:
                if (d.get("attributes") or {}).get("vehicle_intelligence"):
                    v_intel = d["attributes"]["vehicle_intelligence"]
                    break
        if not v_intel:
            for evt in events:
                if (evt.get("attributes") or {}).get("vehicle_intelligence"):
                    v_intel = evt["attributes"]["vehicle_intelligence"]
                    break

        veh_label = ""
        if v_intel:
            c = (v_intel.get("color") or "").title() if v_intel.get("color") and v_intel.get("color") != "unknown" else ""
            t = (v_intel.get("type") or "").title() if v_intel.get("type") and v_intel.get("type") != "unknown" else ""
            if c and t: veh_label = f"{c} {t}"
            elif c: veh_label = f"{c} Vehicle"
            elif t: veh_label = t

        timeline = []
        # 1. Initial Detection Node
        initial_title = f"Initial {veh_label or track['object_type']} Detection"
        timeline.append({
            "node_type": "CAMERA_DETECTION",
            "title": initial_title,
            "camera_id": track["camera_id"],
            "timestamp": track["created_at"],
            "detail": f"Detected on {track['camera_id']} with {int((track['average_confidence'] or 0.9)*100)}% avg confidence." + (f" ({veh_label})" if veh_label else ""),
        })

        # 2. Camera handoffs and zone observations from detections
        seen_cameras = {track["camera_id"]}
        seen_zones = set()
        zone_detections: dict[str, list[dict[str, Any]]] = {}
        for d in detections:
            cam = d.get("camera_id")
            if cam and cam not in seen_cameras:
                seen_cameras.add(cam)
                timeline.append({
                    "node_type": "CAMERA_HANDOFF",
                    "title": f"Handoff to {cam}",
                    "camera_id": cam,
                    "timestamp": d["timestamp"],
                    "detail": f"Target observed transitioning to {cam} ({int(d.get('confidence', 0.9)*100)}% confidence).",
                })
            zone = d.get("zone_id")
            if zone:
                zone_detections.setdefault(zone, []).append(d)
                if zone not in seen_zones:
                    seen_zones.add(zone)
                    timeline.append({
                        "node_type": "ZONE_OBSERVATION",
                        "title": f"Entered {zone}",
                        "camera_id": cam or track["camera_id"],
                        "zone_id": zone,
                        "timestamp": d["timestamp"],
                        "detail": f"Target detected entering monitoring zone {zone}.",
                    })

        # Dwell and loitering analysis across zones
        loitering_detected = False
        for zid, zdets in zone_detections.items():
            if len(zdets) >= 2:
                try:
                    zt1 = datetime.fromisoformat(zdets[0]["timestamp"]).astimezone(UTC)
                    zt2 = datetime.fromisoformat(zdets[-1]["timestamp"]).astimezone(UTC)
                    dwell = (zt2 - zt1).total_seconds()
                    if dwell >= 30.0:
                        loitering_detected = True
                        timeline.append({
                            "node_type": "ZONE_LOITERING",
                            "title": f"Dwell / Loitering Alert in {zid}",
                            "camera_id": zdets[-1].get("camera_id") or track["camera_id"],
                            "zone_id": zid,
                            "severity": "MEDIUM",
                            "timestamp": zdets[-1]["timestamp"],
                            "detail": f"Target continuously observed within zone {zid} for {dwell:.1f}s.",
                        })
                except Exception:
                    pass

        # 3. Events (breaches, restricted entries, alerts)
        for evt in events:
            is_critical = evt.get("severity") in ("CRITICAL", "HIGH") or "BREACH" in evt.get("event_type", "") or "RESTRICTED" in evt.get("event_type", "")
            timeline.append({
                "node_type": "EVENT_BREACH" if is_critical else "ZONE_OBSERVATION",
                "event_id": evt["event_id"],
                "title": evt.get("description") or evt["event_type"].replace("_", " ").title(),
                "camera_id": evt.get("camera_id") or track["camera_id"],
                "zone_id": evt.get("zone_id"),
                "severity": evt.get("severity", "INFO"),
                "timestamp": evt["timestamp"],
                "detail": f"Zone: {evt.get('zone_id') or 'Monitored Area'} · Severity: {evt.get('severity')}",
            })

        # Fetch time-series movement records
        movements = rows(self.db.execute("SELECT * FROM track_movements WHERE track_id=? ORDER BY timestamp ASC", (tid,)))

        # 3.5 Movement change events (started moving, stopped, accelerated, decelerated, direction changed)
        for m in movements:
            if m.get("movement_change"):
                chg = m["movement_change"]
                t_stamp = m.get("timestamp") or track["last_seen_at"]
                if chg == "STARTED_MOVING":
                    timeline.append({
                        "node_type": "MOVEMENT_CHANGE",
                        "title": "Target Started Moving",
                        "camera_id": m.get("camera_id") or track["camera_id"],
                        "timestamp": t_stamp,
                        "detail": f"Movement initiated ({m.get('movement_state')}, {m.get('speed', 0):.1f} px/s towards {m.get('direction', 'heading')}).",
                    })
                elif chg == "STOPPED":
                    timeline.append({
                        "node_type": "MOVEMENT_CHANGE",
                        "title": "Target Stopped",
                        "camera_id": m.get("camera_id") or track["camera_id"],
                        "timestamp": t_stamp,
                        "detail": "Target halted and became stationary.",
                    })
                elif chg == "ACCELERATED":
                    timeline.append({
                        "node_type": "MOVEMENT_CHANGE",
                        "title": "Target Accelerated",
                        "camera_id": m.get("camera_id") or track["camera_id"],
                        "timestamp": t_stamp,
                        "detail": f"Speed surged to {m.get('speed', 0):.1f} px/s heading {m.get('direction')}.",
                    })
                elif chg == "DECELERATED":
                    timeline.append({
                        "node_type": "MOVEMENT_CHANGE",
                        "title": "Target Decelerated",
                        "camera_id": m.get("camera_id") or track["camera_id"],
                        "timestamp": t_stamp,
                        "detail": f"Speed decreased to {m.get('speed', 0):.1f} px/s.",
                    })
                elif chg == "DIRECTION_CHANGED":
                    timeline.append({
                        "node_type": "MOVEMENT_CHANGE",
                        "title": f"Turned Towards {m.get('direction')}",
                        "camera_id": m.get("camera_id") or track["camera_id"],
                        "timestamp": t_stamp,
                        "detail": f"Heading changed to {m.get('direction')} ({m.get('heading_deg', 0):.0f}°).",
                    })

        # 3.8 Face / Human Cross-Modal Association & ArcFace Biometric Recognition
        track_attrs = track.get("attributes") or {}
        if isinstance(track_attrs, str):
            try:
                track_attrs = json.loads(track_attrs)
            except Exception:
                track_attrs = {}

        associated_face_id = track_attrs.get("associated_face_id")
        associated_human_id = track_attrs.get("associated_human_id") or track.get("parent_track_id")

        # Query face_recognitions for track or its associated face/human track
        face_row = None
        for candidate_tid in (tid, associated_face_id, associated_human_id):
            if candidate_tid:
                face_row = self.db.execute(
                    "SELECT * FROM face_recognitions WHERE track_id=? ORDER BY updated_at DESC LIMIT 1",
                    (candidate_tid,),
                ).fetchone()
                if face_row:
                    break

        face_intel = None
        if face_row:
            f_dict = item(face_row)
            reg_info = {}
            if f_dict.get("person_id"):
                p_row = self.db.execute("SELECT role, notes FROM registered_faces WHERE person_id=?", (f_dict["person_id"],)).fetchone()
                if p_row:
                    reg_info = item(p_row)
            face_intel = {
                "has_face": True,
                "recognition_id": f_dict.get("recognition_id"),
                "status": f_dict.get("status", "UNCLASSIFIED"),
                "person_id": f_dict.get("person_id"),
                "person_name": f_dict.get("person_name") or ("Unclassified Face" if f_dict.get("status") != "RECOGNIZED" else "Recognized Person"),
                "role": reg_info.get("role", ""),
                "notes": reg_info.get("notes", ""),
                "similarity": f_dict.get("similarity", 0.0),
                "confidence": f_dict.get("confidence", 0.9),
                "snapshot_path": f_dict.get("snapshot_path"),
                "detection_count": f_dict.get("detection_count", 1),
                "first_seen": f_dict.get("first_seen"),
                "last_seen": f_dict.get("last_seen"),
                "face_track_id": associated_face_id or tid,
                "face_box": track_attrs.get("face_box"),
                "face_confidence": track_attrs.get("face_confidence"),
                "face_match_score": track_attrs.get("face_match_score"),
            }
        elif track_attrs.get("face_intel"):
            raw_fi = track_attrs["face_intel"]
            face_intel = {
                "has_face": True,
                "recognition_id": raw_fi.get("recognition_id"),
                "status": raw_fi.get("status", "UNCLASSIFIED"),
                "person_id": raw_fi.get("person_id"),
                "person_name": raw_fi.get("person_name") or "Unclassified Face",
                "role": raw_fi.get("role", ""),
                "similarity": raw_fi.get("similarity", 0.0),
                "confidence": 0.9,
                "snapshot_path": raw_fi.get("snapshot_path"),
                "detection_count": 1,
                "last_seen": raw_fi.get("last_seen"),
                "face_track_id": associated_face_id or tid,
                "face_box": track_attrs.get("face_box"),
            }
        elif track["object_type"] == "HUMAN" and associated_face_id:
            face_intel = {
                "has_face": True,
                "face_track_id": associated_face_id,
                "face_box": track_attrs.get("face_box"),
                "face_confidence": track_attrs.get("face_confidence"),
                "face_match_score": track_attrs.get("face_match_score"),
                "status": "UNCLASSIFIED",
                "person_name": "Unclassified Face",
            }

        if track["object_type"] == "HUMAN" and associated_face_id:
            face_score = track_attrs.get("face_match_score", 0.9)
            face_conf = track_attrs.get("face_confidence", 0.9)
            timeline.append({
                "node_type": "FACE_ASSOCIATION",
                "title": "Face Linked to Person",
                "camera_id": track["camera_id"],
                "timestamp": track_attrs.get("face_last_seen_at") or track["created_at"],
                "detail": f"Facial signature {associated_face_id} positively linked to subject (Torso alignment score: {int(face_score*100)}%, face confidence: {int(face_conf*100)}%).",
                "associated_track_id": associated_face_id,
            })
        elif track["object_type"] == "FACE" and associated_human_id:
            face_score = track_attrs.get("face_human_match_score", 0.9)
            timeline.append({
                "node_type": "HUMAN_ASSOCIATION",
                "title": "Face Mapped to Human Target",
                "camera_id": track["camera_id"],
                "timestamp": track["created_at"],
                "detail": f"Face mapped to upper body of target {associated_human_id} (Spatial alignment score: {int(face_score*100)}%).",
                "associated_track_id": associated_human_id,
            })

        # Add Biometric FACE_RECOGNITION node if facial recognition info is available
        if face_intel and face_intel.get("recognition_id"):
            is_rec = face_intel["status"] == "RECOGNIZED"
            title = f"Face Identified: {face_intel['person_name']}" if is_rec else "Unclassified Face Sighting"
            sim_str = f" ({int(face_intel['similarity']*100)}% ArcFace match)" if is_rec and face_intel.get("similarity") else ""
            p_desc = f"Person ID: {face_intel.get('person_id')}" if face_intel.get("person_id") else "Pending association"
            role_desc = f" · Role: {face_intel['role']}" if face_intel.get("role") else ""
            detail = (
                f"Biometric ArcFace signature verified: {face_intel['person_name']}{sim_str}. {p_desc}{role_desc}."
                if is_rec
                else f"Unclassified face recorded on {track['camera_id']}. Observed {face_intel.get('detection_count', 1)} time(s), pending security enrollment."
            )
            timeline.append({
                "node_type": "FACE_RECOGNITION",
                "title": title,
                "camera_id": track["camera_id"],
                "timestamp": face_intel.get("last_seen") or face_intel.get("first_seen") or track["created_at"],
                "detail": detail,
                "person_name": face_intel["person_name"],
                "person_id": face_intel.get("person_id"),
                "status": face_intel["status"],
                "similarity": face_intel.get("similarity"),
                "snapshot_path": face_intel.get("snapshot_path"),
                "recognition_id": face_intel.get("recognition_id"),
            })

        # 3.9 OSNet Re-ID Track Recovery nodes
        track_recs = rows(self.db.execute("SELECT * FROM track_recoveries WHERE original_track_id=? OR restored_track_id=? ORDER BY timestamp ASC", (tid, tid)))
        for rec in track_recs:
            sim_pct = int((rec.get("appearance_similarity") or 0.8) * 100)
            cost_val = float(rec.get("composite_cost") or 0.0)
            timeline.append({
                "node_type": "TRACK_RECOVERED",
                "title": "Track Restored (OSNet Re-ID)",
                "camera_id": rec.get("camera_id") or track["camera_id"],
                "timestamp": rec["timestamp"],
                "detail": f"Restored track identity via OSNet Re-ID + Hungarian matching (Similarity: {sim_pct}%, Matching Cost: {cost_val:.2f}).",
                "appearance_similarity": rec.get("appearance_similarity"),
                "composite_cost": cost_val,
                "recovery_id": rec.get("recovery_id"),
            })

        # 4. Sort timeline chronologically
        timeline.sort(key=lambda n: n.get("timestamp") or "")

        # Compute duration
        duration_seconds = 0.0
        try:
            start_t = datetime.fromisoformat(track["created_at"]).astimezone(UTC)
            end_t = datetime.fromisoformat(track.get("ended_at") or track["last_seen_at"]).astimezone(UTC)
            duration_seconds = max(0.0, (end_t - start_t).total_seconds())
        except Exception:
            pass

        # Movement dynamics & velocity calculation
        movement_dynamic = "NORMAL"
        if positions and len(positions) >= 2:
            try:
                import math
                total_disp = 0.0
                for i in range(1, len(positions)):
                    b1 = json.loads(positions[i - 1]["bounding_box"]) if isinstance(positions[i - 1]["bounding_box"], str) else positions[i - 1]["bounding_box"]
                    b2 = json.loads(positions[i]["bounding_box"]) if isinstance(positions[i]["bounding_box"], str) else positions[i]["bounding_box"]
                    c1x, c1y = b1[0] + b1[2] / 2, b1[1] + b1[3] / 2
                    c2x, c2y = b2[0] + b2[2] / 2, b2[1] + b2[3] / 2
                    total_disp += math.hypot(c2x - c1x, c2y - c1y)
                effective_sec = max(1.0, duration_seconds)
                dyn_speed = total_disp / effective_sec
                if dyn_speed < 0.005:
                    movement_dynamic = "STATIONARY"
                elif dyn_speed < 0.04:
                    movement_dynamic = "SLOW_PACING"
                elif dyn_speed < 0.18:
                    movement_dynamic = "NORMAL"
                else:
                    movement_dynamic = "RAPID_TRANSIT"
            except Exception:
                movement_dynamic = "NORMAL"

        # Movement intelligence extraction
        m_snap = (track.get("attributes") or {}).get("movement")
        if not m_snap and movements:
            m_snap = movements[-1]
        if not m_snap:
            m_snap = self.movement_tracker.get_track_snapshot(tid) or {}

        cur_speed = float(m_snap.get("speed", track.get("speed", 0.0) or 0.0))
        speed_unit = m_snap.get("speed_unit", "px/s")
        speed_kmh = m_snap.get("speed_kmh")
        direction = m_snap.get("direction", track.get("direction") or "STATIONARY")
        heading_deg = float(m_snap.get("heading_deg", track.get("heading", 0.0) or 0.0))
        movement_state = m_snap.get("movement_state", track.get("movement_state") or "STATIONARY")
        distance_travelled = float(m_snap.get("distance_travelled", 0.0))
        camera_dir_label = m_snap.get("camera_direction_label", direction)

        # Threat Level scoring
        threat_level = "LOW"
        has_critical = any(e.get("severity") == "CRITICAL" for e in events)
        has_high = any(
            e.get("severity") == "HIGH" or "BREACH" in e.get("event_type", "") or "RESTRICTED" in e.get("event_type", "")
            for e in events
        )
        if has_critical:
            threat_level = "CRITICAL"
        elif has_high:
            threat_level = "HIGH"
        elif loitering_detected or (track["object_type"] == "VEHICLE" and (v_intel or {}).get("type") in ("heavy truck", "emergency vehicle")):
            threat_level = "ELEVATED"
        elif movement_state in ("RUNNING", "FAST") or seen_zones:
            threat_level = "ELEVATED"

        # 5. Concluding node if track ended
        if track.get("status") == "ENDED":
            duration_str = f" after {duration_seconds:.1f}s" if duration_seconds > 0 else ""
            timeline.append({
                "node_type": "TRACK_CONCLUDED",
                "title": f"{track['object_type'].capitalize()} Track Concluded",
                "camera_id": track["camera_id"],
                "timestamp": track.get("ended_at") or track["last_seen_at"],
                "detail": f"Track concluded{duration_str} · {positions_count} positions and {len(detections)} detections recorded.",
            })

        # Synthesize activity narrative story
        story_parts = []
        obj_name = veh_label or track["object_type"].capitalize()
        story_parts.append(f"{obj_name} ({tid}) detected on {track['camera_id']}")
        if len(seen_cameras) > 1:
            other_cams = [c for c in seen_cameras if c != track["camera_id"]]
            story_parts.append(f"transitioned across {', '.join(other_cams)}")
        if seen_zones:
            story_parts.append(f"entered {', '.join(sorted(seen_zones))}")
        if loitering_detected:
            story_parts.append("flagged for extended dwell/loitering")
        if movement_state in ("RUNNING", "FAST"):
            story_parts.append(f"moving at elevated velocity ({movement_state.lower()} at {cur_speed:.1f} px/s heading {direction})")
        elif movement_state != "STATIONARY":
            story_parts.append(f"observed {movement_state.lower()} heading {direction} ({cur_speed:.1f} px/s)")
        if face_intel and face_intel.get("status") == "RECOGNIZED":
            role_part = f" ({face_intel['role']})" if face_intel.get("role") else ""
            story_parts.append(f"biometrically recognized as {face_intel['person_name']}{role_part}")
        elif face_intel and face_intel.get("status") == "UNCLASSIFIED":
            f_id = face_intel.get("face_track_id") or associated_face_id
            f_str = f" ({f_id})" if f_id else ""
            story_parts.append(f"unclassified face sighting recorded{f_str}")
        elif track["object_type"] == "HUMAN" and associated_face_id:
            story_parts.append(f"facial signature linked ({associated_face_id})")
        elif track["object_type"] == "FACE" and associated_human_id:
            story_parts.append(f"associated with human target {associated_human_id}")
        if events:
            top_ev = events[-1]
            ev_desc = top_ev.get("description") or top_ev["event_type"].replace("_", " ").title()
            story_parts.append(f"triggered {ev_desc}")
        status_desc = "active and monitored" if track.get("status") == "ACTIVE" else f"concluded after {duration_seconds:.0f}s"
        story_parts.append(f"status is {status_desc} [{threat_level} threat]")
        activity_story = ". ".join(story_parts) + "."

        return {
            "track_id": tid,
            "object_type": track["object_type"],
            "camera_id": track["camera_id"],
            "status": track["status"],
            "created_at": track["created_at"],
            "last_seen_at": track["last_seen_at"],
            "positions_count": positions_count,
            "detections_count": len(detections),
            "timeline": timeline,
            "evidence": evidence_list,
            "positions": positions,
            "attributes": track.get("attributes") or {},
            "parent_track_id": track.get("parent_track_id") or associated_human_id,
            "associated_face_id": associated_face_id if track["object_type"] == "HUMAN" else None,
            "associated_human_id": associated_human_id if track["object_type"] == "FACE" else None,
            "face_intel": face_intel,
            "person_name": face_intel.get("person_name") if face_intel and face_intel.get("status") == "RECOGNIZED" else None,
            "person_id": face_intel.get("person_id") if face_intel else None,
            "face_status": face_intel.get("status") if face_intel else None,
            "vehicle_intelligence": v_intel,
            "vehicle_label": veh_label,
            "vehicle_type": v_intel.get("type") if v_intel else None,
            "vehicle_color": v_intel.get("color") if v_intel else None,
            "threat_level": threat_level,
            "movement_dynamic": movement_dynamic,
            "speed": round(cur_speed, 2),
            "speed_unit": speed_unit,
            "speed_kmh": round(speed_kmh, 2) if speed_kmh is not None else None,
            "direction": direction,
            "heading_deg": round(heading_deg, 1),
            "camera_direction_label": camera_dir_label,
            "movement_state": movement_state,
            "distance_travelled": round(distance_travelled, 2),
            "movements_count": len(movements),
            "duration_seconds": round(duration_seconds, 1),
            "loitering_detected": loitering_detected,
            "activity_story": activity_story,
            "reliability_score": float(track.get("reliability_score", 1.0) or 1.0),
            "recovery_count": int(track.get("recovery_count", 0) or 0),
            "recoveries": track_recs,
        }

    def get_track_recoveries(self, track_id: str | None = None, camera_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        query = "SELECT * FROM track_recoveries WHERE 1=1"
        args: list[Any] = []
        if track_id:
            query += " AND (original_track_id=? OR restored_track_id=?)"
            args.extend([track_id, track_id])
        if camera_id:
            query += " AND camera_id=?"
            args.append(camera_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        args.append(limit)
        return rows(self.db.execute(query, tuple(args)))

    def get_track_movements(self, track_id: str, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        return rows(self.db.execute("SELECT * FROM track_movements WHERE track_id=? ORDER BY timestamp ASC LIMIT ?", (track_id, limit)))

    def get_camera_movements(self, camera_id: str, since: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        query = "SELECT * FROM track_movements WHERE camera_id=?"
        args: list[Any] = [camera_id]
        if since:
            query += " AND timestamp>=?"
            args.append(since)
        query += " ORDER BY timestamp DESC LIMIT ?"
        args.append(limit)
        return rows(self.db.execute(query, tuple(args)))

    def get_all_threads(
        self,
        limit: int = 50,
        status: str | None = None,
        camera_id: str | None = None,
        object_type: str | None = None,
        vehicle_type: str | None = None,
        vehicle_color: str | None = None,
        threat_level: str | None = None,
        movement_state: str | None = None,
        person_name: str | None = None,
        face_status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM tracks WHERE 1=1"
        args = []
        if status:
            query += " AND status=?"
            args.append(status.upper())
        if camera_id:
            query += " AND camera_id=?"
            args.append(camera_id)
        if object_type:
            query += " AND object_type=?"
            args.append(object_type.upper())
        query += " ORDER BY CASE status WHEN 'ACTIVE' THEN 1 ELSE 2 END, CASE WHEN object_type IN ('HUMAN', 'VEHICLE', 'UAV') THEN 1 ELSE 2 END, detection_count DESC, last_seen_at DESC LIMIT ?"
        fetch_limit = limit * 2 if (vehicle_type or vehicle_color or threat_level or movement_state or person_name or face_status) else limit
        args.append(fetch_limit)
        tracks = rows(self.db.execute(query, tuple(args)))
        result = []
        for t in tracks:
            thread = self.get_track_thread(t["track_id"], include_positions=False)
            if not thread:
                continue
            if vehicle_type and (thread.get("vehicle_type") or "").lower() != vehicle_type.lower():
                continue
            if vehicle_color and (thread.get("vehicle_color") or "").lower() != vehicle_color.lower():
                continue
            if threat_level and (thread.get("threat_level") or "").upper() != threat_level.upper():
                continue
            if movement_state and (thread.get("movement_state") or "").upper() != movement_state.upper():
                continue
            if face_status and (thread.get("face_status") or "").upper() != face_status.upper():
                continue
            if person_name:
                p_curr = (thread.get("person_name") or "").lower()
                if person_name.lower() not in p_curr:
                    continue
            result.append(thread)
            if len(result) >= limit:
                break
        return result

    def clear_ended_threads(self) -> dict[str, int]:
        ended_rows = rows(self.db.execute("SELECT track_id FROM tracks WHERE status = 'ENDED'"))
        ended_ids = [r["track_id"] for r in ended_rows]
        if ended_ids:
            if hasattr(self.vehicle_pipeline, "stabilizer"):
                for tid in ended_ids:
                    self.vehicle_pipeline.stabilizer.remove_track(tid)
            for tid in ended_ids:
                self.movement_tracker.remove_track(tid)
            placeholders = ",".join("?" * len(ended_ids))
            self.db.execute(f"DELETE FROM track_movements WHERE track_id IN ({placeholders})", tuple(ended_ids))
            self.db.execute(f"DELETE FROM track_positions WHERE track_id IN ({placeholders})", tuple(ended_ids))
            self.db.execute(f"UPDATE detections SET track_id = NULL WHERE track_id IN ({placeholders})", tuple(ended_ids))
            self.db.execute(f"UPDATE events SET track_id = NULL WHERE track_id IN ({placeholders})", tuple(ended_ids))
            cur = self.db.execute("DELETE FROM tracks WHERE status = 'ENDED'")
            count = cur.rowcount
            self.db.commit()
            return {"cleared_count": count}
        return {"cleared_count": 0}

    def get_zone_dwell_tracks(self, camera_id: str | None = None, zone_id: str | None = None) -> list[dict[str, Any]]:
        """Return live targets currently dwelling inside zones with their duration and status."""
        return self.spatial_engine.get_active_dwell_tracks(camera_id, zone_id)

    def update_zone_thresholds(self, zone_id: str, dwell_seconds: float, loitering_seconds: float) -> dict[str, Any]:
        """Update configurable dwell and loitering thresholds for a specific zone."""
        dwell_val = float(dwell_seconds)
        loiter_val = float(loitering_seconds)
        self.db.execute(
            "UPDATE zones SET dwell_threshold_seconds=?, loitering_threshold_seconds=?, updated_at=datetime('now') WHERE zone_id=?",
            (dwell_val, loiter_val, zone_id),
        )
        self.db.commit()
        for cam_zones in self.spatial_engine.zones.values():
            if zone_id in cam_zones:
                cam_zones[zone_id].dwell_threshold_seconds = dwell_val
                cam_zones[zone_id].loitering_threshold_seconds = loiter_val
        return {
            "status": "updated",
            "zone_id": zone_id,
            "dwell_threshold_seconds": dwell_val,
            "loitering_threshold_seconds": loiter_val,
        }

    def update_default_thresholds(self, dwell_seconds: float, loitering_seconds: float) -> dict[str, Any]:
        """Update global default thresholds across all zones in the system."""
        dwell_val = float(dwell_seconds)
        loiter_val = float(loitering_seconds)
        self.db.execute(
            "UPDATE zones SET dwell_threshold_seconds=?, loitering_threshold_seconds=?, updated_at=datetime('now')",
            (dwell_val, loiter_val),
        )
        self.db.commit()
        for cam_zones in self.spatial_engine.zones.values():
            for zone in cam_zones.values():
                zone.dwell_threshold_seconds = dwell_val
                zone.loitering_threshold_seconds = loiter_val
        return {
            "status": "updated",
            "default_dwell_threshold_seconds": dwell_val,
            "default_loitering_threshold_seconds": loiter_val,
        }

    def get_loitering_history(self, limit: int = 50, zone_id: str | None = None) -> list[dict[str, Any]]:
        """Query logged loitering sessions."""
        query = "SELECT * FROM loitering_sessions WHERE 1=1"
        params = []
        if zone_id:
            query += " AND zone_id=?"
            params.append(zone_id)
        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        return rows(self.db.execute(query, tuple(params)))

    def get_incidents(
        self,
        status: str | None = None,
        severity: str | None = None,
        camera_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List incidents with optional filters."""
        limit = max(1, min(limit, 200))
        query = "SELECT * FROM incidents WHERE 1=1"
        params: list[Any] = []
        if status and status != "ALL":
            query += " AND status=?"
            params.append(status)
        if severity and severity != "ALL":
            query += " AND severity=?"
            params.append(severity)
        if camera_id and camera_id != "ALL":
            query += " AND (primary_camera_id=? OR incident_id IN (SELECT incident_id FROM events WHERE camera_id=?))"
            params.extend([camera_id, camera_id])
        query += " ORDER BY last_seen_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        raw_rows = self.db.execute(query, tuple(params)).fetchall()
        result = []
        for r in raw_rows:
            inc = Incident.from_row(r)
            result.append(inc.to_dict())
        return result

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        """Fetch comprehensive incident details with correlated events, tracks, cameras, evidence, and timeline."""
        row = self.db.execute("SELECT * FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
        if not row:
            return None
        inc = Incident.from_row(row)

        # 1. Correlated events
        ev_rows = rows(self.db.execute(
            "SELECT * FROM events WHERE incident_id=? OR event_id IN (SELECT event_id FROM incident_events WHERE incident_id=?) ORDER BY timestamp ASC",
            (incident_id, incident_id),
        ))
        inc.events = ev_rows

        # 2. Extract involved track IDs, cameras, zones
        track_ids = list({e["track_id"] for e in ev_rows if e.get("track_id")})
        cams = list({e["camera_id"] for e in ev_rows if e.get("camera_id")})
        if inc.primary_camera_id and inc.primary_camera_id not in cams:
            cams.append(inc.primary_camera_id)
        zones = list({e["zone_id"] for e in ev_rows if e.get("zone_id")})
        if inc.primary_zone_id and inc.primary_zone_id not in zones:
            zones.append(inc.primary_zone_id)

        inc.cameras = sorted(cams)
        inc.zones = sorted(zones)

        # 3. Correlated tracks detail
        if track_ids:
            placeholders = ",".join("?" * len(track_ids))
            inc.tracks = rows(self.db.execute(f"SELECT * FROM tracks WHERE track_id IN ({placeholders})", tuple(track_ids)))

        # 4. Correlated evidence
        ev_ids = [e["event_id"] for e in ev_rows if e.get("event_id")]
        if ev_ids:
            placeholders = ",".join("?" * len(ev_ids))
            inc.evidence = rows(self.db.execute(f"SELECT * FROM evidence WHERE event_id IN ({placeholders}) ORDER BY timestamp ASC", tuple(ev_ids)))
        if not inc.evidence and inc.primary_camera_id:
            inc.evidence = rows(self.db.execute("SELECT * FROM evidence WHERE event_id IN (SELECT event_id FROM events WHERE camera_id=?) ORDER BY timestamp DESC LIMIT 10", (inc.primary_camera_id,)))
        if not inc.evidence:
            inc.evidence = rows(self.db.execute("SELECT * FROM evidence ORDER BY created_at DESC LIMIT 10"))

        # 5. Build chronological developing situation timeline
        timeline = []
        for ev in ev_rows:
            etype = ev.get("event_type", "EVENT")
            t_stamp = ev.get("timestamp") or ev.get("created_at")
            t_cam = ev.get("camera_id") or "Camera"
            t_zone = ev.get("zone_id") or "Zone"
            t_track = ev.get("track_id") or "Entity"

            if etype == "INTRUSION":
                node_type = "INTRUSION"
                title = f"Perimeter Intrusion Detected ({t_zone})"
            elif etype == "LOITERING":
                dur = ev.get("duration_seconds") or 0
                node_type = "LOITERING"
                title = f"Sustained Dwell / Loitering ({dur:.0f}s) in {t_zone}"
            elif etype == "RESTRICTED_ZONE_ENTRY":
                node_type = "RESTRICTED_BREACH"
                title = f"Restricted Boundary Entry ({t_zone})"
            elif etype == "ZONE_EXIT":
                node_type = "ZONE_EXIT"
                title = f"Departed Zone ({t_zone})"
            else:
                node_type = "OBSERVATION"
                title = f"{etype.replace('_', ' ').title()} on {t_cam}"

            timeline.append({
                "node_type": node_type,
                "title": title,
                "camera_id": t_cam,
                "zone_id": t_zone,
                "track_id": t_track,
                "timestamp": t_stamp,
                "severity": ev.get("severity", "MEDIUM"),
                "detail": ev.get("description") or f"{etype} recorded by surveillance engine.",
            })

        inc.timeline = timeline
        return inc.to_dict()

    def acknowledge_incident(self, incident_id: str, operator: str = "Operator") -> dict[str, Any] | None:
        """Acknowledge an active incident."""
        inc = self.incident_correlator.acknowledge_incident(incident_id, operator)
        return inc.to_dict() if inc else None

    def resolve_incident(self, incident_id: str, operator: str = "Operator") -> dict[str, Any] | None:
        """Resolve an incident."""
        inc = self.incident_correlator.resolve_incident(incident_id, operator)
        return inc.to_dict() if inc else None

    def get_incidents_summary(self) -> dict[str, Any]:
        """Aggregate metrics for incident command center."""
        total = self.db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
        active = self.db.execute("SELECT COUNT(*) FROM incidents WHERE status IN ('DETECTED', 'CONFIRMED', 'ACTIVE')").fetchone()[0]
        critical = self.db.execute("SELECT COUNT(*) FROM incidents WHERE severity='CRITICAL' AND status != 'RESOLVED'").fetchone()[0]
        total_events = self.db.execute("SELECT COUNT(*) FROM incident_events").fetchone()[0]
        dedup_count = max(0, total_events - total)
        ratio = round((dedup_count / total_events) * 100, 1) if total_events > 0 else 0.0

        return {
            "total_incidents": total,
            "active_incidents": active,
            "critical_incidents": critical,
            "correlated_events": total_events,
            "deduplicated_events": dedup_count,
            "deduplication_ratio_pct": ratio,
        }

    # HELIOS Intelligence & Insights Layer Methods
    def get_insights(self, priority: str | None = None, status: str | None = None, type_: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return self.insights_engine.get_insights(priority=priority, status=status, type_=type_, limit=limit, offset=offset)

    def get_insight(self, insight_id: str) -> dict[str, Any] | None:
        return self.insights_engine.get_insight(insight_id)

    def get_insights_summary(self) -> dict[str, Any]:
        return self.insights_engine.get_summary()

    def record_insight_feedback(self, insight_id: str, operator_feedback: str, camera_id: str | None = None, notes: str | None = None) -> dict[str, Any]:
        return self.insights_engine.record_feedback(insight_id=insight_id, operator_feedback=operator_feedback, camera_id=camera_id, notes=notes)

    def get_what_changed(self) -> list[dict[str, Any]]:
        return self.baseline_engine.get_what_changed()

    def get_rolling_summaries(self, window: str | None = None) -> dict[str, Any]:
        if window:
            return self.rolling_summaries.get_summary(window)
        return self.rolling_summaries.get_all_summaries()

    def query_observations(self, **kwargs) -> list[dict[str, Any]]:
        return self.observation_layer.query(**kwargs)

    def count_observations(self, **kwargs) -> int:
        return self.observation_layer.count(**kwargs)

    def investigate_nl(self, question: str) -> dict[str, Any]:
        return self.nl_investigator.investigate(question)

    def investigate_nl_stream(self, question: str):
        return self.nl_investigator.investigate_stream(question)

    # HELIOS Behavioral Analytics Layer Methods
    def get_behavioral_events(
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
        """Query logged behavioral events with filters."""
        return self.behavioral_engine.get_events(
            camera_id=camera_id,
            zone_id=zone_id,
            track_id=track_id,
            behavior_type=behavior_type,
            min_score=min_score,
            status=status,
            limit=limit,
            offset=offset,
        )

    def get_behavioral_event(self, behavior_id: str) -> dict[str, Any] | None:
        """Retrieve single behavioral event record by ID."""
        return self.behavioral_engine.get_event(behavior_id)

    def get_behavioral_summary(self) -> dict[str, Any]:
        """Aggregate behavioral analytics summary."""
        return self.behavioral_engine.get_summary()


