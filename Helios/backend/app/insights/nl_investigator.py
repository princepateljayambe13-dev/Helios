"""Natural Language Investigation Engine: filters database in milliseconds, feeds structured evidence to Qwen3 4B, and persists grounded metadata."""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Generator

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

SYSTEM_INVESTIGATE_PROMPT = """You are HELIOS Surveillance Intelligence AI, powered by local Qwen.
Your role is to answer operator questions strictly and faithfully using verified records retrieved from the HELIOS database (observations, tracks, events, insights, alerts, and evidence snapshots).

RULES:
1. Base your answer EXCLUSIVELY on the provided structured HELIOS database records.
2. NEVER hallucinate or invent people counts, timestamps, cameras, zones, tracks, attire colors, or events not present in the database.
3. If no matching records exist in the database, explicitly state that no corresponding surveillance evidence was found in the HELIOS database.
4. Highlight movement behaviors (walking speed, pacing, dwell) and visual colors (attire, vehicle) when present in the database evidence.
5. Keep the answer concise (2-4 sentences), calm, professional, and military/enterprise grade.
6. Explicitly cite supporting cameras, zones, or observation records in your response.
"""


class NaturalLanguageInvestigator:
    """Executes fast intent extraction, database filtering, and LLM synthesis."""

    def __init__(
        self,
        db: sqlite3.Connection,
        ollama_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:4b",
    ):
        self.db = db
        self.ollama_url = (ollama_url or "http://127.0.0.1:11434").rstrip("/")
        self.model = model or "qwen3:4b"

    def investigate(self, question: str) -> dict[str, Any]:
        """Execute full investigation: intent -> db search -> Qwen explanation -> save metadata."""
        filters = self._extract_intent_filters(question)
        evidence_bundle = self._query_evidence(filters)

        # 1. Prompt local Qwen3 4B with HELIOS database bundle
        ai_result = self._prompt_qwen(question, evidence_bundle)

        # 2. Persist investigation metadata
        inv_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
        stamp = datetime.now(UTC).isoformat()

        metadata = {
            "filters": filters,
            "matched_counts": {
                "observations": len(evidence_bundle["observations"]),
                "events": len(evidence_bundle["events"]),
                "insights": len(evidence_bundle.get("insights", [])),
                "alerts": len(evidence_bundle.get("alerts", [])),
                "evidence_snapshots": len(evidence_bundle["evidence_snapshots"]),
                "face_recognitions": len(evidence_bundle.get("face_recognitions", [])),
            },
            "provider": ai_result.get("provider", "ollama:qwen3:4b"),
            "model": self.model,
        }

        try:
            self.db.execute(
                """INSERT INTO ai_investigations (
                    investigation_id, question, answer, confidence,
                    observation_ids, event_ids, evidence_ids, camera_ids, zone_ids,
                    metadata, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    inv_id,
                    question,
                    ai_result["answer"],
                    ai_result["confidence"],
                    json.dumps(ai_result["observation_ids"]),
                    json.dumps(ai_result["event_ids"]),
                    json.dumps(ai_result["evidence_ids"]),
                    json.dumps(ai_result["camera_ids"]),
                    json.dumps(ai_result["zone_ids"]),
                    json.dumps(metadata),
                    stamp,
                ),
            )
            self.db.commit()
        except Exception as exc:
            logger.error("Failed to persist investigation metadata: %s", exc)

        return {
            "investigation_id": inv_id,
            "question": question,
            "answer": ai_result["answer"],
            "confidence": ai_result["confidence"],
            "observation_ids": ai_result["observation_ids"],
            "event_ids": ai_result["event_ids"],
            "evidence_ids": ai_result["evidence_ids"],
            "insight_ids": [i["insight_id"] for i in evidence_bundle.get("insights", [])],
            "camera_ids": ai_result["camera_ids"],
            "zone_ids": ai_result["zone_ids"],
            "evidence_snapshots": evidence_bundle["evidence_snapshots"],
            "provider": ai_result.get("provider", "ollama:qwen3:4b"),
            "model": self.model,
            "metadata": metadata,
            "timestamp": stamp,
        }

    def investigate_stream(self, question: str) -> Generator[str, None, None]:
        """Stream the investigation response token by token or chunked text."""
        filters = self._extract_intent_filters(question)
        evidence_bundle = self._query_evidence(filters)

        # Try streaming from Ollama
        streamed = False
        full_text = ""
        if requests is not None:
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_INVESTIGATE_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"Question: {question}\n\n"
                                f"HELIOS Database Evidence: {json.dumps(evidence_bundle, indent=2)}\n\n"
                                "Provide a concise grounded answer with camera and observation references."
                            ),
                        },
                    ],
                    "stream": True,
                    "options": {"temperature": 0.1, "num_predict": 250},
                }
                resp = requests.post(
                    f"{self.ollama_url}/api/chat", json=payload, stream=True, timeout=(1.0, 20.0)
                )
                if resp.status_code == 200:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line.decode("utf-8"))
                            msg_content = (chunk.get("message") or {}).get("content", "")
                            if msg_content:
                                # Strip any thinking tags if present
                                clean_chunk = re.sub(r"<think>.*?</think>", "", msg_content, flags=re.DOTALL)
                                if clean_chunk:
                                    full_text += clean_chunk
                                    yield clean_chunk
                            if chunk.get("done"):
                                streamed = True
                                break
                        except Exception:
                            pass
            except Exception:
                streamed = False

        if not streamed:
            # Fallback
            fb = self._deterministic_answer(question, evidence_bundle)
            yield fb["answer"]
            full_text = fb["answer"]

        # Persist after streaming finishes
        try:
            inv_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
            stamp = datetime.now(UTC).isoformat()
            obs_ids = [o["observation_id"] for o in evidence_bundle["observations"]]
            ev_ids = [e["event_id"] for e in evidence_bundle["events"]]
            evd_ids = [s["evidence_id"] for s in evidence_bundle["evidence_snapshots"]]
            cams = list(set(o["camera_id"] for o in evidence_bundle["observations"]))
            zones = list(set(o["zone_id"] for o in evidence_bundle["observations"] if o.get("zone_id")))

            self.db.execute(
                """INSERT INTO ai_investigations (
                    investigation_id, question, answer, confidence,
                    observation_ids, event_ids, evidence_ids, camera_ids, zone_ids,
                    metadata, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    inv_id,
                    question,
                    full_text,
                    0.91,
                    json.dumps(obs_ids),
                    json.dumps(ev_ids),
                    json.dumps(evd_ids),
                    json.dumps(cams),
                    json.dumps(zones),
                    json.dumps({"streamed": True, "filters": filters}),
                    stamp,
                ),
            )
            self.db.commit()
        except Exception:
            pass

    def _extract_intent_filters(self, question: str) -> dict[str, Any]:
        """Convert natural language query into fast structured SQL query filters."""
        q = question.lower()
        filters: dict[str, Any] = {}

        # 1. Camera identification
        cam_match = re.search(r"\b(cam(?:era)?[-_\s]?\d+)\b", q)
        if cam_match:
            raw_cam = cam_match.group(1).upper().replace(" ", "").replace("CAMERA", "CAM")
            if "-" not in raw_cam:
                raw_cam = raw_cam.replace("CAM", "CAM-")
            filters["camera_id"] = raw_cam

        # 2. Zone identification
        zone_match = re.search(r"\b(zone[-_\s]?\d+)\b", q)
        if zone_match:
            raw_z = zone_match.group(1).upper().replace(" ", "").replace("ZONE", "ZONE-")
            filters["zone_id"] = raw_z
        elif "east" in q:
            filters["zone_keyword"] = "east"
        elif "west" in q:
            filters["zone_keyword"] = "west"
        elif "perimeter" in q or "gate" in q:
            filters["zone_keyword"] = "gate"

        # 3. Object type
        if "car" in q or "vehicle" in q or "truck" in q:
            filters["object_type"] = "VEHICLE"
        elif "person" in q or "people" in q or "human" in q or "pedestrian" in q:
            filters["object_type"] = "HUMAN"

        # 4. Time range
        now_dt = datetime.now(UTC)
        if "after midnight" in q:
            today_midnight = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            filters["start_time"] = today_midnight.isoformat()
        elif "last hour" in q or "past hour" in q:
            filters["start_time"] = (now_dt - timedelta(hours=1)).isoformat()
        elif "tonight" in q or "today" in q:
            filters["start_time"] = (now_dt - timedelta(hours=12)).isoformat()
        elif "24 hours" in q or "yesterday" in q:
            filters["start_time"] = (now_dt - timedelta(hours=24)).isoformat()
        else:
            # Default to last 6 hours for fast relevance
            filters["start_time"] = (now_dt - timedelta(hours=6)).isoformat()

        # 5. Biometric and face recognition intent
        if any(w in q for w in ["face", "who", "whom", "person", "identity", "recognized", "unclassified", "unknown", "arcface", "biometric"]):
            filters["include_faces"] = True
            if "recognized" in q:
                filters["face_status"] = "RECOGNIZED"
            elif "unclassified" in q or "unknown" in q:
                filters["face_status"] = "UNCLASSIFIED"

        return filters

    def _query_evidence(self, filters: dict[str, Any]) -> dict[str, Any]:
        """Fast database retrieval using indexed fields."""
        query = "SELECT * FROM observations WHERE 1=1"
        args: list[Any] = []

        if filters.get("camera_id"):
            query += " AND camera_id=?"
            args.append(filters["camera_id"])
        if filters.get("zone_id"):
            query += " AND zone_id=?"
            args.append(filters["zone_id"])
        if filters.get("object_type"):
            query += " AND object_type=?"
            args.append(filters["object_type"])
        if filters.get("start_time"):
            query += " AND last_seen >= ?"
            args.append(filters["start_time"])

        query += " ORDER BY first_seen DESC LIMIT 15"
        obs_rows = self.db.execute(query, tuple(args)).fetchall()

        observations = []
        all_event_ids: set[str] = set()
        all_evidence_ids: set[str] = set()

        for r in obs_rows:
            d = dict(r)
            evs = json.loads(d["event_ids"]) if d.get("event_ids") else []
            all_event_ids.update(evs)
            evds = json.loads(d["evidence_ids"]) if d.get("evidence_ids") else []
            all_evidence_ids.update(evds)
            observations.append({
                "observation_id": d["observation_id"],
                "track_id": d["track_id"],
                "camera_id": d["camera_id"],
                "zone_id": d["zone_id"],
                "object_type": d["object_type"],
                "first_seen": d["first_seen"],
                "last_seen": d["last_seen"],
                "dwell_seconds": d["dwell_seconds"],
                "movement_state": d["movement_state"],
                "direction": d["direction"],
                "speed": d["speed"],
            })

        # Fetch matching events
        events: list[dict[str, Any]] = []
        if all_event_ids:
            placeholders = ",".join("?" * len(all_event_ids))
            evt_rows = self.db.execute(
                f"SELECT event_id, event_type, camera_id, zone_id, timestamp, severity, description FROM events WHERE event_id IN ({placeholders}) LIMIT 10",
                tuple(all_event_ids),
            ).fetchall()
            events = [dict(e) for e in evt_rows]
        elif filters.get("camera_id") or filters.get("zone_id"):
            evt_query = "SELECT event_id, event_type, camera_id, zone_id, timestamp, severity, description FROM events WHERE 1=1"
            evt_args: list[Any] = []
            if filters.get("camera_id"):
                evt_query += " AND camera_id=?"
                evt_args.append(filters["camera_id"])
            if filters.get("zone_id"):
                evt_query += " AND zone_id=?"
                evt_args.append(filters["zone_id"])
            evt_query += " ORDER BY timestamp DESC LIMIT 10"
            events = [dict(e) for e in self.db.execute(evt_query, tuple(evt_args)).fetchall()]

        # Fetch evidence snapshots for respected zone events
        evidence_snapshots: list[dict[str, Any]] = []
        if all_evidence_ids:
            placeholders = ",".join("?" * len(all_evidence_ids))
            evd_rows = self.db.execute(
                f"SELECT evidence_id, event_id, type, storage_reference, timestamp, metadata FROM evidence WHERE evidence_id IN ({placeholders}) LIMIT 10",
                tuple(all_evidence_ids),
            ).fetchall()
            for ev in evd_rows:
                d = dict(ev)
                if d.get("metadata") and isinstance(d["metadata"], str):
                    try:
                        d["metadata"] = json.loads(d["metadata"])
                    except Exception:
                        d["metadata"] = {}
                evidence_snapshots.append(d)
        elif events:
            event_ids_for_evd = [e["event_id"] for e in events if e.get("event_id")]
            if event_ids_for_evd:
                placeholders = ",".join("?" * len(event_ids_for_evd))
                evd_rows = self.db.execute(
                    f"SELECT evidence_id, event_id, type, storage_reference, timestamp, metadata FROM evidence WHERE event_id IN ({placeholders}) LIMIT 10",
                    tuple(event_ids_for_evd),
                ).fetchall()
                for ev in evd_rows:
                    d = dict(ev)
                    if d.get("metadata") and isinstance(d["metadata"], str):
                        try:
                            d["metadata"] = json.loads(d["metadata"])
                        except Exception:
                            d["metadata"] = {}
                    evidence_snapshots.append(d)

        # Fetch recent relevant insights from database
        try:
            ins_rows = self.db.execute(
                "SELECT insight_id, type, priority, summary, camera_ids, zone_ids, created_at FROM insights ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
            insights = [dict(i) for i in ins_rows]
        except Exception:
            insights = []

        # Fetch active alerts from database
        try:
            alert_rows = self.db.execute(
                "SELECT alert_id, alert_type, severity, status, message, timestamp FROM alerts ORDER BY timestamp DESC LIMIT 5"
            ).fetchall()
            alerts = [dict(a) for a in alert_rows]
        except Exception:
            alerts = []

        # Fetch matching facial recognitions from database
        face_recognitions: list[dict[str, Any]] = []
        try:
            face_query = "SELECT recognition_id, track_id, camera_id, person_id, person_name, status, similarity, last_seen, detection_count, snapshot_path FROM face_recognitions WHERE 1=1"
            face_args: list[Any] = []
            if filters.get("camera_id"):
                face_query += " AND camera_id=?"
                face_args.append(filters["camera_id"])
            if filters.get("face_status"):
                face_query += " AND status=?"
                face_args.append(filters["face_status"])
            if filters.get("start_time"):
                face_query += " AND last_seen >= ?"
                face_args.append(filters["start_time"])
            face_query += " ORDER BY last_seen DESC LIMIT 10"
            face_rows = self.db.execute(face_query, tuple(face_args)).fetchall()
            face_recognitions = [dict(f) for f in face_rows]
        except Exception:
            face_recognitions = []

        return {
            "observations": observations,
            "events": events,
            "insights": insights,
            "alerts": alerts,
            "evidence_snapshots": evidence_snapshots,
            "face_recognitions": face_recognitions,
        }

    def _prompt_qwen(self, question: str, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
        """Prompt local Qwen3 4B with structured HELIOS database records only."""
        obs = evidence_bundle["observations"]
        events = evidence_bundle["events"]
        snapshots = evidence_bundle["evidence_snapshots"]
        insights = evidence_bundle.get("insights", [])
        alerts = evidence_bundle.get("alerts", [])
        faces = evidence_bundle.get("face_recognitions", [])

        obs_ids = [o["observation_id"] for o in obs]
        event_ids = [e["event_id"] for e in events]
        evidence_ids = [s["evidence_id"] for s in snapshots]
        insight_ids = [i["insight_id"] for i in insights]
        camera_ids = list(set(o["camera_id"] for o in obs) | set(e["camera_id"] for e in events if e.get("camera_id")) | set(f["camera_id"] for f in faces if f.get("camera_id")))
        zone_ids = list(set(o["zone_id"] for o in obs if o.get("zone_id")) | set(e["zone_id"] for e in events if e.get("zone_id")))

        if not obs and not events and not insights and not faces:
            return {
                "answer": "No surveillance observations, events, or biometric records matching the query criteria were recorded in the HELIOS database.",
                "confidence": 0.95,
                "observation_ids": [],
                "event_ids": [],
                "evidence_ids": [],
                "camera_ids": [],
                "zone_ids": [],
                "provider": "helios:deterministic",
            }

        if requests is not None:
            try:
                face_text = f"- Biometric Facial Recognitions ({len(faces)} records): {json.dumps(faces[:5])}\n" if faces else ""
                prompt_text = (
                    f"Operator Question: {question}\n\n"
                    f"VERIFIED HELIOS DATABASE RECORDS:\n"
                    f"- Observations & Movement Telemetry ({len(obs)} records): {json.dumps(obs[:6])}\n"
                    f"- Security Events ({len(events)} records): {json.dumps(events[:4])}\n"
                    f"- Active Insights & Situations ({len(insights)} records): {json.dumps(insights[:3])}\n"
                    f"- Security Alerts ({len(alerts)} records): {json.dumps(alerts[:3])}\n"
                    f"{face_text}"
                    f"- Evidence Snapshots Analyzed: {len(snapshots)} (attributes: {[s.get('metadata') for s in snapshots[:4] if s.get('metadata')]})\n\n"
                    "Respond with an authoritative, concise (2-3 sentences) answer strictly answering the operator's question using ONLY these verified HELIOS database records. "
                    "Explicitly cite cameras, zones, walking speeds/movement, recognized individuals/biometrics, and visual attire/object colors where available."
                )

                resp = requests.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_INVESTIGATE_PROMPT},
                            {"role": "user", "content": prompt_text},
                        ],
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 220},
                    },
                    timeout=(1.0, 15.0),
                )
                if resp.status_code == 200:
                    raw_text = (resp.json().get("message") or {}).get("content", "").strip()
                    clean = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
                    if clean:
                        return {
                            "answer": clean,
                            "confidence": 0.94,
                            "observation_ids": obs_ids,
                            "event_ids": event_ids,
                            "evidence_ids": evidence_ids,
                            "camera_ids": camera_ids,
                            "zone_ids": zone_ids,
                            "provider": f"ollama:{self.model}",
                        }
            except Exception as exc:
                logger.debug("Ollama Qwen prompt failed/skipped: %s", exc)

        return self._deterministic_answer(question, evidence_bundle)

    def _deterministic_answer(self, question: str, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
        """Robust deterministic synthesizer when local LLM is offline."""
        obs = evidence_bundle["observations"]
        events = evidence_bundle["events"]
        snapshots = evidence_bundle["evidence_snapshots"]
        insights = evidence_bundle.get("insights", [])
        faces = evidence_bundle.get("face_recognitions", [])

        obs_ids = [o["observation_id"] for o in obs]
        event_ids = [e["event_id"] for e in events]
        evidence_ids = [s["evidence_id"] for s in snapshots]
        cameras = list(set(o["camera_id"] for o in obs) | set(f["camera_id"] for f in faces if f.get("camera_id")))
        zones = list(set(o["zone_id"] for o in obs if o.get("zone_id")))

        if not obs and not events and not insights and not faces:
            answer = "No surveillance observations, events, or biometric records matching the query criteria were recorded in the HELIOS database."
        else:
            time_start = obs[-1]["first_seen"][-8:] if obs and len(obs[-1]["first_seen"]) >= 8 else "recently"
            time_end = obs[0]["last_seen"][-8:] if obs and len(obs[0]["last_seen"]) >= 8 else "now"
            cam_str = ", ".join(cameras) if cameras else "facility cameras"
            zone_str = f"in {zones[0]}" if zones else "across monitored zones"

            human_obs = [o for o in obs if o.get("object_type") == "HUMAN"]
            vehicle_obs = [o for o in obs if o.get("object_type") == "VEHICLE"]
            walking_obs = [o for o in human_obs if "WALK" in (o.get("movement_state") or "").upper() or (float(o.get("speed") or 0) >= 0.8)]

            # Colors from evidence snapshots
            detected_colors = []
            for s in snapshots:
                meta = s.get("metadata") or {}
                col = meta.get("detected_color") or meta.get("color_label")
                if col and col not in detected_colors:
                    detected_colors.append(col)

            color_clause = f" Visual evidence identified subjects with {', '.join(detected_colors[:2])} attire." if detected_colors else ""
            walk_clause = f" ({len(walking_obs)} actively walking)" if walking_obs else ""

            # Biometric telemetry clause
            rec_names = [f["person_name"] for f in faces if f.get("person_name") and (f.get("status") or "").upper() == "RECOGNIZED"]
            unclass_cnt = len([f for f in faces if (f.get("status") or "").upper() != "RECOGNIZED"])
            face_clauses = []
            if rec_names:
                unique_names = sorted(list(set(rec_names)))[:3]
                face_clauses.append(f"biometrically recognized {', '.join(unique_names)}")
            if unclass_cnt:
                face_clauses.append(f"{unclass_cnt} unclassified face detection(s)")
            biometric_clause = f" Facial recognition verified {' and '.join(face_clauses)}." if face_clauses else ""

            if obs or events:
                answer = (
                    f"HELIOS database query confirms {len(obs)} observation(s){walk_clause} and {len(events)} security event(s) "
                    f"between {time_start} and {time_end} on {cam_str} {zone_str}.{color_clause}{biometric_clause}"
                )
            else:
                answer = f"HELIOS biometric intelligence records {len(faces)} face detections on {cam_str}.{biometric_clause}"

        return {
            "answer": answer,
            "confidence": 0.91,
            "observation_ids": obs_ids,
            "event_ids": event_ids,
            "evidence_ids": evidence_ids,
            "camera_ids": cameras,
            "zone_ids": zones,
            "provider": "helios:deterministic-grounded",
        }
