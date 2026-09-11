"""Modular Face Recognition Manager for HELIOS.

Orchestrates the YOLO Face Detection -> Face Crop -> ArcFace -> Database -> Dashboard pipeline.
Runs recognition efficiently using track-based rate limiting, supports face registration,
unclassified face tracking, and retroactive person association.
"""
from __future__ import annotations

import base64
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.core.config import Settings
from app.vision.face.arcface import ArcFaceRecognizer

LOGGER = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return dict(row)


class FaceRecognitionManager:
    """Coordinates ArcFace facial recognition, database persistence, and person management."""

    def __init__(
        self,
        db: sqlite3.Connection,
        settings: Settings,
        similarity_threshold: float = 0.60,
        unclassified_cooldown: float = 2.0,
    ) -> None:
        self.db = db
        self.settings = settings
        self.similarity_threshold = similarity_threshold
        self.unclassified_cooldown = unclassified_cooldown

        # Directory for face snapshots and registered profile photos
        self.storage_dir = Path(getattr(settings, "evidence_directory", Path("storage/evidence"))) / "face"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # ArcFace deep feature extractor
        weights_path = Path("models/face/arcface.pt")
        self.recognizer = ArcFaceRecognizer(
            weights_path=weights_path if weights_path.exists() else None,
            device="auto",
        )

        # In-memory caches
        self._registered_cache: list[dict[str, Any]] = []
        self._track_eval_cache: dict[str, dict[str, Any]] = {}  # track_id -> metadata

        # Preload registered persons into RAM for O(1) comparison
        self.reload_registered_faces()

    def reload_registered_faces(self) -> None:
        """Load all registered persons and their ArcFace embeddings into memory."""
        try:
            rows = self.db.execute("SELECT * FROM registered_faces ORDER BY name ASC").fetchall()
            loaded: list[dict[str, Any]] = []
            for r in rows:
                item = row_to_dict(r)
                emb_raw = item.get("embedding")
                if emb_raw:
                    try:
                        emb = np.asarray(json.loads(emb_raw), dtype=np.float32)
                        loaded.append({**item, "_emb_np": emb})
                    except Exception:
                        pass
            self._registered_cache = loaded
            LOGGER.info("Loaded %d registered faces into recognition cache.", len(loaded))
        except Exception as err:
            LOGGER.warning("Could not load registered faces: %s", err)

    def process_face_observation(
        self,
        observation: dict[str, Any],
        track_id: str | None,
        event_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Process an ingested face observation through ArcFace and database persistence.

        Efficient: Only runs ArcFace if track is new, or if unclassified cooldown has elapsed.
        """
        frame_image = observation.get("image")
        bbox = observation.get("bounding_box")
        camera_id = observation.get("camera_id", "CAM-01")
        confidence = float(observation.get("confidence", 0.0))

        if frame_image is None or not isinstance(frame_image, np.ndarray) or frame_image.size == 0:
            return None
        if not bbox or len(bbox) < 4:
            return None

        # Quality check: reject face crops that are too small
        ih, iw = frame_image.shape[:2]
        crop_w = bbox[2] * iw
        crop_h = bbox[3] * ih
        if crop_w < 20 or crop_h < 20:
            return None

        current_time = time.monotonic()
        stamp = now_iso()

        # Track-based rate limiting
        cached_eval = self._track_eval_cache.get(track_id) if track_id else None
        if cached_eval and track_id:
            time_since_eval = current_time - cached_eval["last_eval_time"]

            # If already RECOGNIZED with solid similarity, do not re-run heavy ArcFace every frame
            if cached_eval["status"] == "RECOGNIZED" and cached_eval["similarity"] >= self.similarity_threshold:
                cached_eval["last_eval_time"] = current_time
                cached_eval["detection_count"] += 1
                try:
                    self.db.execute(
                        "UPDATE face_recognitions SET last_seen=?, detection_count=detection_count+1 WHERE recognition_id=?",
                        (stamp, cached_eval["recognition_id"]),
                    )
                    self.db.commit()
                except Exception:
                    pass
                return cached_eval

            # If UNCLASSIFIED and within cooldown, avoid redundant neural passes
            if cached_eval["status"] == "UNCLASSIFIED" and time_since_eval < self.unclassified_cooldown:
                cached_eval["detection_count"] += 1
                try:
                    self.db.execute(
                        "UPDATE face_recognitions SET last_seen=?, detection_count=detection_count+1 WHERE recognition_id=?",
                        (stamp, cached_eval["recognition_id"]),
                    )
                    self.db.commit()
                except Exception:
                    pass
                return cached_eval

        # Generate ArcFace embedding
        embedding = self.recognizer.extract_embedding(frame_image, bbox)
        if embedding is None:
            return None

        # Compare against registered faces in database
        best_match: dict[str, Any] | None = None
        best_sim: float = -1.0
        for person in self._registered_cache:
            person_emb = person.get("_emb_np")
            if person_emb is not None:
                sim = self.recognizer.compute_similarity(embedding, person_emb)
                if sim > best_sim:
                    best_sim = sim
                    best_match = person

        is_recognized = best_match is not None and best_sim >= self.similarity_threshold
        status = "RECOGNIZED" if is_recognized else "UNCLASSIFIED"
        person_id = best_match["person_id"] if is_recognized else None
        person_name = best_match["name"] if is_recognized else "Unclassified"
        similarity = round(float(max(0.0, best_sim)), 4) if best_match else 0.0

        # Save face crop JPEG snapshot
        recognition_id = cached_eval["recognition_id"] if cached_eval else f"FAC-{uuid.uuid4().hex[:10].upper()}"
        filename = f"{recognition_id}.jpg"
        file_path = self.storage_dir / filename

        # Crop face with margin for storage
        margin_x = bbox[2] * 0.15
        margin_y = bbox[3] * 0.15
        x1 = max(0, int(round((bbox[0] - margin_x) * iw)))
        y1 = max(0, int(round((bbox[1] - margin_y) * ih)))
        x2 = min(iw, int(round((bbox[0] + bbox[2] + margin_x) * iw)))
        y2 = min(ih, int(round((bbox[1] + bbox[3] + margin_y) * ih)))
        if x2 > x1 and y2 > y1:
            face_crop = frame_image[y1:y2, x1:x2]
            cv2.imwrite(str(file_path), face_crop)
        else:
            cv2.imwrite(str(file_path), frame_image)

        snapshot_url = f"/api/v1/faces/snapshots/{filename}"
        emb_json = json.dumps(embedding.tolist())

        # Persist to face_recognitions table
        existing_row = None
        if track_id:
            existing_row = self.db.execute(
                "SELECT recognition_id, detection_count, first_seen FROM face_recognitions WHERE track_id=?",
                (track_id,),
            ).fetchone()

        if existing_row:
            rec_id = existing_row[0]
            self.db.execute(
                """UPDATE face_recognitions SET 
                    camera_id=?, person_id=?, person_name=?, status=?, similarity=?, confidence=?,
                    bounding_box=?, snapshot_path=?, event_id=?, last_seen=?, detection_count=detection_count+1,
                    embedding=?, updated_at=?
                   WHERE recognition_id=?""",
                (
                    camera_id,
                    person_id,
                    person_name,
                    status,
                    similarity,
                    confidence,
                    json.dumps(bbox),
                    snapshot_url,
                    event_id,
                    stamp,
                    emb_json,
                    stamp,
                    rec_id,
                ),
            )
            recognition_id = rec_id
            first_seen = existing_row[2]
            det_count = existing_row[1] + 1
        else:
            first_seen = stamp
            det_count = 1
            self.db.execute(
                """INSERT INTO face_recognitions (
                    recognition_id, track_id, camera_id, person_id, person_name, status,
                    similarity, confidence, bounding_box, snapshot_path, event_id,
                    first_seen, last_seen, detection_count, embedding, created_at, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    recognition_id,
                    track_id,
                    camera_id,
                    person_id,
                    person_name,
                    status,
                    similarity,
                    confidence,
                    json.dumps(bbox),
                    snapshot_url,
                    event_id,
                    first_seen,
                    stamp,
                    det_count,
                    emb_json,
                    stamp,
                    stamp,
                ),
            )
        self.db.commit()

        # Update evaluation cache
        eval_result = {
            "recognition_id": recognition_id,
            "track_id": track_id,
            "camera_id": camera_id,
            "person_id": person_id,
            "person_name": person_name,
            "status": status,
            "similarity": similarity,
            "confidence": confidence,
            "bounding_box": bbox,
            "snapshot_path": snapshot_url,
            "event_id": event_id,
            "first_seen": first_seen,
            "last_seen": stamp,
            "detection_count": det_count,
            "last_eval_time": current_time,
        }
        if track_id:
            self._track_eval_cache[track_id] = eval_result

        # Update track attributes in SQLite
        if track_id:
            try:
                track_row = self.db.execute("SELECT attributes FROM tracks WHERE track_id=?", (track_id,)).fetchone()
                if track_row:
                    attrs = {}
                    if track_row[0]:
                        try:
                            attrs = json.loads(track_row[0])
                        except Exception:
                            attrs = {}
                    attrs["face_intel"] = {
                        "recognition_id": recognition_id,
                        "status": status,
                        "person_id": person_id,
                        "person_name": person_name,
                        "similarity": similarity,
                        "snapshot_path": snapshot_url,
                        "last_seen": stamp,
                    }
                    self.db.execute(
                        "UPDATE tracks SET attributes=? WHERE track_id=?",
                        (json.dumps(attrs), track_id),
                    )
                    self.db.commit()
            except Exception as err:
                LOGGER.warning("Failed to update track %s face attributes: %s", track_id, err)

        return eval_result

    def register_person(
        self,
        name: str,
        person_id: str | None = None,
        role: str = "",
        notes: str = "",
        image_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """Register a new person with face image and compute their ArcFace embedding."""
        if not name or not name.strip():
            raise ValueError("Person name is required.")

        name = name.strip()
        person_id = (person_id.strip() if person_id else None) or f"PER-{uuid.uuid4().hex[:8].upper()}"

        if not image_bytes:
            raise ValueError("Face image is required to register a person.")

        # Decode image using OpenCV
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode face image.")

        # Compute ArcFace embedding
        embedding = self.recognizer.extract_embedding(img)
        if embedding is None:
            raise ValueError("Could not extract facial features from image.")

        # Save profile photo to storage
        filename = f"{person_id}.jpg"
        profile_path = self.storage_dir / filename
        cv2.imwrite(str(profile_path), img)
        image_path = f"/api/v1/faces/snapshots/{filename}"

        stamp = now_iso()
        emb_json = json.dumps(embedding.tolist())

        # Persist to registered_faces (INSERT or REPLACE)
        self.db.execute(
            """INSERT INTO registered_faces (person_id, name, role, notes, face_image_path, embedding, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(person_id) DO UPDATE SET
                   name=excluded.name,
                   role=excluded.role,
                   notes=excluded.notes,
                   face_image_path=excluded.face_image_path,
                   embedding=excluded.embedding,
                   updated_at=excluded.updated_at""",
            (person_id, name, role, notes, image_path, emb_json, stamp, stamp),
        )
        self.db.commit()

        # Reload cache
        self.reload_registered_faces()

        return {
            "person_id": person_id,
            "name": name,
            "role": role,
            "notes": notes,
            "face_image_path": image_path,
            "created_at": stamp,
            "updated_at": stamp,
        }

    def associate_unclassified_face(
        self,
        recognition_id: str,
        person_id: str | None = None,
        name: str | None = None,
        role: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """Associate an unclassified face record with an existing person or new person."""
        rec_row = self.db.execute(
            "SELECT * FROM face_recognitions WHERE recognition_id=?",
            (recognition_id,),
        ).fetchone()
        if not rec_row:
            raise KeyError(f"Face recognition '{recognition_id}' not found.")

        rec = row_to_dict(rec_row)
        face_emb_raw = rec.get("embedding")
        face_emb = np.asarray(json.loads(face_emb_raw), dtype=np.float32) if face_emb_raw else None

        stamp = now_iso()

        # Option A: Associate with existing registered person
        if person_id:
            person_row = self.db.execute(
                "SELECT * FROM registered_faces WHERE person_id=?",
                (person_id,),
            ).fetchone()
            if not person_row:
                raise KeyError(f"Person '{person_id}' does not exist.")
            person = row_to_dict(person_row)
            target_person_id = person["person_id"]
            target_name = person["name"]

            # Compute similarity
            p_emb_raw = person.get("embedding")
            p_emb = np.asarray(json.loads(p_emb_raw), dtype=np.float32) if p_emb_raw else None
            sim = self.recognizer.compute_similarity(face_emb, p_emb) if (face_emb is not None and p_emb is not None) else 0.95

        # Option B: Create a new person from this unclassified face
        elif name and name.strip():
            target_name = name.strip()
            target_person_id = f"PER-{uuid.uuid4().hex[:8].upper()}"
            img_path = rec.get("snapshot_path", "")

            # If we have the embedding, save person to registered_faces
            if face_emb is not None:
                self.db.execute(
                    """INSERT INTO registered_faces (person_id, name, role, notes, face_image_path, embedding, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (target_person_id, target_name, role, notes, img_path, face_emb_raw, stamp, stamp),
                )
                self.db.commit()
                self.reload_registered_faces()
            sim = 1.0
        else:
            raise ValueError("Either an existing person_id or a new person name must be provided.")

        similarity = round(float(sim), 4)

        # Update face_recognitions record
        self.db.execute(
            """UPDATE face_recognitions SET
                person_id=?, person_name=?, status='RECOGNIZED', similarity=?, updated_at=?
               WHERE recognition_id=?""",
            (target_person_id, target_name, similarity, stamp, recognition_id),
        )

        # Update tracks table if linked
        track_id = rec.get("track_id")
        if track_id:
            try:
                t_row = self.db.execute("SELECT attributes FROM tracks WHERE track_id=?", (track_id,)).fetchone()
                if t_row and t_row[0]:
                    t_attrs = json.loads(t_row[0])
                    if "face_intel" in t_attrs:
                        t_attrs["face_intel"]["status"] = "RECOGNIZED"
                        t_attrs["face_intel"]["person_id"] = target_person_id
                        t_attrs["face_intel"]["person_name"] = target_name
                        t_attrs["face_intel"]["similarity"] = similarity
                        self.db.execute("UPDATE tracks SET attributes=? WHERE track_id=?", (json.dumps(t_attrs), track_id))
            except Exception:
                pass

            # Invalidate/update in-memory track cache
            if track_id in self._track_eval_cache:
                self._track_eval_cache[track_id]["status"] = "RECOGNIZED"
                self._track_eval_cache[track_id]["person_id"] = target_person_id
                self._track_eval_cache[track_id]["person_name"] = target_name
                self._track_eval_cache[track_id]["similarity"] = similarity

        self.db.commit()

        updated_row = self.db.execute("SELECT * FROM face_recognitions WHERE recognition_id=?", (recognition_id,)).fetchone()
        return row_to_dict(updated_row)

    def get_recognitions(
        self,
        status: str | None = None,
        camera_id: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List face recognitions with optional filters."""
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        q = "SELECT * FROM face_recognitions WHERE 1=1"
        args: list[Any] = []

        if status and status.upper() != "ALL":
            q += " AND status=?"
            args.append(status.upper())
        if camera_id:
            q += " AND camera_id=?"
            args.append(camera_id)
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            q += " AND (LOWER(person_name) LIKE ? OR LOWER(person_id) LIKE ? OR LOWER(track_id) LIKE ?)"
            args.extend([term, term, term])

        q += " ORDER BY last_seen DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])

        rows = self.db.execute(q, args).fetchall()
        result = []
        for r in rows:
            item = row_to_dict(r)
            if item.get("bounding_box"):
                try:
                    item["bounding_box"] = json.loads(item["bounding_box"])
                except Exception:
                    pass
            # Don't expose raw 512-d embedding to web frontends
            item.pop("embedding", None)
            result.append(item)
        return result

    def get_recognition(self, recognition_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM face_recognitions WHERE recognition_id=?", (recognition_id,)).fetchone()
        if not row:
            return None
        item = row_to_dict(row)
        if item.get("bounding_box"):
            try:
                item["bounding_box"] = json.loads(item["bounding_box"])
            except Exception:
                pass
        item.pop("embedding", None)
        return item

    def get_registered_persons(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT person_id, name, role, notes, face_image_path, created_at, updated_at FROM registered_faces ORDER BY name ASC").fetchall()
        return [row_to_dict(r) for r in rows]

    def delete_registered_person(self, person_id: str) -> bool:
        cursor = self.db.execute("DELETE FROM registered_faces WHERE person_id=?", (person_id,))
        self.db.commit()
        self.reload_registered_faces()
        return cursor.rowcount > 0

    def get_summary(self) -> dict[str, int]:
        total = self.db.execute("SELECT COUNT(*) FROM face_recognitions").fetchone()[0]
        recognized = self.db.execute("SELECT COUNT(*) FROM face_recognitions WHERE status='RECOGNIZED'").fetchone()[0]
        unclassified = self.db.execute("SELECT COUNT(*) FROM face_recognitions WHERE status='UNCLASSIFIED'").fetchone()[0]
        persons = self.db.execute("SELECT COUNT(*) FROM registered_faces").fetchone()[0]
        return {
            "total_recognitions": total,
            "recognized_count": recognized,
            "unclassified_count": unclassified,
            "registered_persons_count": persons,
        }

    def clear_recognitions(self) -> int:
        cursor = self.db.execute("DELETE FROM face_recognitions")
        self.db.commit()
        self._track_eval_cache.clear()
        return cursor.rowcount
