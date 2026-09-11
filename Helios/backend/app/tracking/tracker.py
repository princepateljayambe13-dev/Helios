"""ByteTrack + OSNet Re-ID and Hungarian Multi-Object Tracker for HELIOS.

Integrates Ultralytics BYTETracker (Kalman + IoU association) with OSNet
appearance embeddings, 4-factor Hungarian matching cost (40% appearance, 30% position,
20% motion, 10% IoU), gating thresholds, lost-track Kalman recovery, and Track
Reliability Scoring.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import numpy as np
from ultralytics.engine.results import Boxes

from app.tracking.movement import MovementTracker
from app.tracking.reid.matching import HungarianMatcher, MatchingConfig
from app.tracking.reid.osnet import OSNetExtractor
from app.tracking.reid.recovery import RecoveryEvent, TrackRecoveryManager
from app.tracking.reid.reliability import TrackReliabilityCalculator
from app.tracking.track import Track

LOGGER = logging.getLogger(__name__)


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Compute Intersection-over-Union between two bounding boxes in [x, y, w, h] format."""
    ax, ay, aw, ah = map(float, a[:4])
    bx, by, bw, bh = map(float, b[:4])
    left, top, right, bottom = max(ax, bx), max(ay, by), min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union else 0.0


def _now() -> str:
    return datetime.now(UTC).isoformat()


CLASS_MAP = {"HUMAN": 0, "VEHICLE": 1, "UAV": 2, "ANIMAL": 3, "FACE": 4, "LICENSE_PLATE": 5}
REV_CLASS_MAP = {v: k for k, v in CLASS_MAP.items()}


class ByteTrackTracker:
    """Enhanced Multi-Object Tracker combining YOLO, ByteTrack, OSNet Re-ID, and Hungarian Recovery."""

    def __init__(
        self,
        camera_id: str,
        track_buffer: int = 60,
        track_high_thresh: float = 0.25,
        track_low_thresh: float = 0.10,
        match_thresh: float = 0.80,
        new_track_thresh: float = 0.25,
        fuse_score: bool = True,
        reid_enabled: bool = True,
        reid_extractor: OSNetExtractor | None = None,
        matching_config: MatchingConfig | None = None,
        max_lost_seconds: float = 12.0,
    ) -> None:
        self.camera_id = camera_id.split(":")[0]
        self.tracker_key = camera_id
        self.reid_enabled = reid_enabled
        self.args = SimpleNamespace(
            track_buffer=track_buffer,
            track_high_thresh=track_high_thresh,
            track_low_thresh=track_low_thresh,
            match_thresh=match_thresh,
            new_track_thresh=new_track_thresh,
            fuse_score=fuse_score,
        )
        self._tracker = self._build_tracker()
        self._tracks: dict[str | int, Track] = {}
        self._class_cache: dict[str | int, tuple[str, str]] = {}
        self.movement_tracker = MovementTracker()

        # OSNet Re-ID & Hungarian Recovery Engines
        self.reid_extractor = reid_extractor or (OSNetExtractor() if reid_enabled else None)
        self.matcher = HungarianMatcher(matching_config or MatchingConfig())
        self.recovery_manager = TrackRecoveryManager(self.matcher, max_lost_seconds=max_lost_seconds)
        self.reliability_calculator = TrackReliabilityCalculator()

        # Temporary buffer for recoveries emitted during the most recent update
        self.recent_recoveries: list[RecoveryEvent] = []

    def _build_tracker(self) -> Any:
        from ultralytics.trackers.byte_tracker import BYTETracker

        return BYTETracker(self.args)

    def reset(self) -> None:
        """Reset internal tracker, Kalman filter, Re-ID and recovery states."""
        self._tracker = self._build_tracker()
        self._tracks.clear()
        self._class_cache.clear()
        self.movement_tracker.clear()
        self.recovery_manager.clear(self.camera_id)
        self.recent_recoveries.clear()

    def update(
        self,
        detections: Sequence[dict[str, Any]] | Boxes | np.ndarray,
        image_shape: tuple[int, int] = (1000, 1000),
        timestamp: str | None = None,
        frame: np.ndarray | None = None,
    ) -> list[Track]:
        """Update tracker with frame detections, compute OSNet Re-ID, and perform Hungarian track recovery.

        Args:
            detections: List of detection dicts (with bounding_box/xyxy, confidence, object_type)
                        or Ultralytics Boxes / numpy array.
            image_shape: (height, width) of the frame.
            timestamp: ISO timestamp for the observation.
            frame: Optional BGR/RGB image ndarray for OSNet appearance crop extraction.

        Returns:
            List of actively tracked Track objects for the current frame.
        """
        stamp = timestamp or _now()
        height, width = max(1, image_shape[0]), max(1, image_shape[1])
        self.recent_recoveries.clear()

        # Parse and normalize incoming detections
        parsed_dets: list[dict[str, Any]] = []

        if isinstance(detections, Boxes):
            boxes_obj = detections
            orig_shape = getattr(boxes_obj, "orig_shape", image_shape)
            height, width = max(1, orig_shape[0]), max(1, orig_shape[1])
            raw_xyxy = boxes_obj.xyxy.cpu().numpy() if hasattr(boxes_obj.xyxy, "cpu") else np.asarray(boxes_obj.xyxy)
            raw_conf = boxes_obj.conf.cpu().numpy() if hasattr(boxes_obj.conf, "cpu") else np.asarray(boxes_obj.conf)
            raw_cls = boxes_obj.cls.cpu().numpy() if hasattr(boxes_obj.cls, "cpu") else np.asarray(boxes_obj.cls)
            for i in range(len(raw_xyxy)):
                cls_val = int(raw_cls[i]) if i < len(raw_cls) else 0
                obj_type = REV_CLASS_MAP.get(cls_val, "HUMAN")
                parsed_dets.append({
                    "x1": float(raw_xyxy[i][0]),
                    "y1": float(raw_xyxy[i][1]),
                    "x2": float(raw_xyxy[i][2]),
                    "y2": float(raw_xyxy[i][3]),
                    "confidence": float(raw_conf[i]),
                    "cls_val": cls_val,
                    "object_type": obj_type,
                    "source_class": obj_type.lower(),
                })
        elif isinstance(detections, np.ndarray):
            raw_arr = detections
            for i in range(len(raw_arr)):
                cls_val = int(raw_arr[i][5]) if raw_arr.shape[1] > 5 else 0
                obj_type = REV_CLASS_MAP.get(cls_val, "HUMAN")
                parsed_dets.append({
                    "x1": float(raw_arr[i][0]),
                    "y1": float(raw_arr[i][1]),
                    "x2": float(raw_arr[i][2]),
                    "y2": float(raw_arr[i][3]),
                    "confidence": float(raw_arr[i][4]) if raw_arr.shape[1] > 4 else 0.9,
                    "cls_val": cls_val,
                    "object_type": obj_type,
                    "source_class": obj_type.lower(),
                })
        else:
            for det in detections:
                conf = float(det.get("confidence", 0.9))
                obj_type = str(det.get("object_type", "HUMAN")).upper()
                source_cls = str(det.get("attributes", {}).get("source_class") or det.get("source_class") or obj_type.lower())
                cls_val = CLASS_MAP.get(obj_type, 0)

                if "xyxy" in det:
                    x1, y1, x2, y2 = map(float, det["xyxy"])
                elif "bounding_box" in det:
                    bx, by, bw, bh = map(float, det["bounding_box"])
                    if bw <= 1.0 and bh <= 1.0 and bx <= 1.0 and by <= 1.0:
                        x1 = bx * width
                        y1 = by * height
                        x2 = (bx + bw) * width
                        y2 = (by + bh) * height
                    else:
                        x1, y1, x2, y2 = bx, by, bx + bw, by + bh
                else:
                    continue

                det_dict: dict[str, Any] = {
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "confidence": conf,
                    "cls_val": cls_val,
                    "object_type": obj_type,
                    "source_class": source_cls,
                }
                # Forward existing embedding or crop if available
                if "reid_embedding" in det:
                    det_dict["reid_embedding"] = det["reid_embedding"]
                elif "crop" in det:
                    det_dict["crop"] = det["crop"]
                parsed_dets.append(det_dict)

        # Extract OSNet appearance embeddings for person detections
        for det in parsed_dets:
            bx = max(0.0, min(1.0, det["x1"] / width))
            by = max(0.0, min(1.0, det["y1"] / height))
            bw = max(0.0, min(1.0, (det["x2"] - det["x1"]) / width))
            bh = max(0.0, min(1.0, (det["y2"] - det["y1"]) / height))
            norm_bbox = [round(bx, 4), round(by, 4), round(bw, 4), round(bh, 4)]
            det["bounding_box"] = norm_bbox

            if "reid_embedding" not in det and self.reid_enabled and self.reid_extractor:
                crop_img = det.get("crop") if det.get("crop") is not None else frame
                emb = self.reid_extractor.extract_embedding(
                    image=crop_img,
                    bounding_box=norm_bbox,
                    synthetic_seed=f"{norm_bbox[0]}_{norm_bbox[1]}",
                )
                det["reid_embedding"] = emb

        # Build Boxes object for Ultralytics ByteTrack
        if len(parsed_dets) == 0:
            boxes_obj = Boxes(np.empty((0, 6), dtype=np.float32), orig_shape=(height, width))
        else:
            data = np.array(
                [[d["x1"], d["y1"], d["x2"], d["y2"], d["confidence"], d["cls_val"]] for d in parsed_dets],
                dtype=np.float32,
            )
            boxes_obj = Boxes(data, orig_shape=(height, width))

        # 1. Execute ByteTrack Kalman + IoU Association
        self._tracker.update(boxes_obj)
        for s in getattr(self._tracker, "tracked_stracks", []):
            s.is_activated = True
        tracks_output = self._tracker._format_output()

        active_tracks: list[Track] = []
        matched_det_indices = set()
        bytetrack_assignments: list[dict[str, Any]] = []

        if len(tracks_output) > 0:
            for row in tracks_output:
                x1, y1, x2, y2 = float(row[0]), float(row[1]), float(row[2]), float(row[3])
                track_id = int(row[4])
                score = float(row[5])
                cls_val = int(row[6])
                idx = int(row[7])

                matched_det_indices.add(idx)

                bx = max(0.0, min(1.0, x1 / width))
                by = max(0.0, min(1.0, y1 / height))
                bw = max(0.0, min(1.0, (x2 - x1) / width))
                bh = max(0.0, min(1.0, (y2 - y1) / height))
                bbox = [round(bx, 4), round(by, 4), round(bw, 4), round(bh, 4)]

                det_emb = None
                if 0 <= idx < len(parsed_dets):
                    obj_type = parsed_dets[idx]["object_type"]
                    source_class = parsed_dets[idx]["source_class"]
                    det_emb = parsed_dets[idx].get("reid_embedding")
                    self._class_cache[track_id] = (obj_type, source_class)
                elif track_id in self._class_cache:
                    obj_type, source_class = self._class_cache[track_id]
                else:
                    obj_type = REV_CLASS_MAP.get(cls_val, "HUMAN")
                    source_class = obj_type.lower()

                bytetrack_assignments.append({
                    "track_id": track_id,
                    "bbox": bbox,
                    "score": score,
                    "obj_type": obj_type,
                    "source_class": source_class,
                    "det_idx": idx,
                    "det_emb": det_emb,
                })

        # 2. Register tracks entering LOST or REMOVED state
        for lost_st in getattr(self._tracker, "lost_stracks", []):
            tid = getattr(lost_st, "track_id", None)
            if tid is not None and tid in self._tracks:
                trk = self._tracks[tid]
                trk.mark_lost(stamp)
                self.recovery_manager.record_lost(trk, stamp)

        for rem_st in getattr(self._tracker, "removed_stracks", []):
            tid = getattr(rem_st, "track_id", None)
            if tid is not None and tid in self._tracks:
                self._tracks[tid].mark_removed(stamp)

        # 3. Hungarian Track Recovery with OSNet Re-ID
        # Detections that were either newly assigned or not matched by ByteTrack are tested
        # against temporarily LOST tracks to restore their original persistent track identity.
        candidate_recoveries: list[dict[str, Any]] = []
        for assign in bytetrack_assignments:
            tid = assign["track_id"]
            # If this is a newly created track ID from ByteTrack (not in our existing active tracks)
            if tid not in self._tracks and assign["det_idx"] >= 0 and assign["det_idx"] < len(parsed_dets):
                candidate_recoveries.append(parsed_dets[assign["det_idx"]])

        if candidate_recoveries:
            recovered_matches = self.recovery_manager.recover(
                unmatched_detections=candidate_recoveries,
                camera_id=self.camera_id,
                timestamp=stamp,
            )
            for lost_rec, d_idx, recovery_evt in recovered_matches:
                self.recent_recoveries.append(recovery_evt)
                orig_id = lost_rec.track_id
                # Rebind the newly spawned track ID to the original track ID
                for assign in bytetrack_assignments:
                    if assign.get("det_idx") == d_idx or assign.get("bbox") == candidate_recoveries[d_idx].get("bounding_box"):
                        LOGGER.info(
                            "Track recovered via OSNet Re-ID! Restoring %s (replaces temp id %s, sim=%.3f, cost=%.3f)",
                            orig_id,
                            assign["track_id"],
                            recovery_evt.appearance_similarity,
                            recovery_evt.composite_cost,
                        )
                        assign["track_id"] = orig_id
                        assign["recovery_event"] = recovery_evt
                        break

        # 4. Finalize Active Tracks and Compute Movement + Reliability Scores
        for assign in bytetrack_assignments:
            track_id = assign["track_id"]
            bbox = assign["bbox"]
            score = assign["score"]
            obj_type = assign["obj_type"]
            source_class = assign["source_class"]
            det_emb = assign.get("det_emb")
            recovery_evt = assign.get("recovery_event")

            snap = self.movement_tracker.update(
                track_id=str(track_id),
                camera_id=self.camera_id,
                object_type=obj_type,
                bounding_box=bbox,
                timestamp=stamp,
            )

            if track_id in self._tracks:
                track = self._tracks[track_id]
                if det_emb:
                    track.add_reid_embedding(det_emb)

                rec_count = track.recovery_count + (1 if recovery_evt else 0)

                # Compute Track Reliability Score
                traj_boxes = [p.get("bounding_box", bbox) for p in track.trajectory.points] if hasattr(track, "trajectory") and track.trajectory else [bbox]
                rel_score, rel_signals = self.reliability_calculator.compute_reliability(
                    confidence=score,
                    detection_count=track.detection_count + 1,
                    embeddings=track.reid_embeddings,
                    speed=snap.speed,
                    acceleration=snap.acceleration,
                    trajectory_boxes=traj_boxes,
                )

                track.update(
                    bbox=bbox,
                    confidence=score,
                    timestamp=stamp,
                    state="TRACKED",
                    speed=snap.speed,
                    speed_unit=snap.speed_unit,
                    speed_kmh=snap.speed_kmh,
                    direction=snap.direction,
                    heading_deg=snap.heading_deg,
                    movement_state=snap.movement_state,
                    distance_travelled=snap.distance_travelled,
                    movement_change=snap.movement_change,
                    reliability_score=rel_score,
                    reliability_signals=rel_signals,
                    recovery_count=rec_count,
                    reid_embedding=det_emb,
                )
            else:
                initial_embeddings = [det_emb] if det_emb else []
                rel_score, rel_signals = self.reliability_calculator.compute_reliability(
                    confidence=score,
                    detection_count=1,
                    embeddings=initial_embeddings,
                    speed=snap.speed,
                    acceleration=snap.acceleration,
                    trajectory_boxes=[bbox],
                )

                track = Track(
                    track_id=track_id,
                    camera_id=self.camera_id,
                    object_type=obj_type,
                    bbox=bbox,
                    confidence=score,
                    first_seen=stamp,
                    last_seen=stamp,
                    state="TRACKED",
                    source_class=source_class,
                    source_track_id=f"bytetrack:{track_id}",
                    speed=snap.speed,
                    speed_unit=snap.speed_unit,
                    speed_kmh=snap.speed_kmh,
                    direction=snap.direction,
                    heading_deg=snap.heading_deg,
                    movement_state=snap.movement_state,
                    distance_travelled=snap.distance_travelled,
                    movement_change=snap.movement_change,
                    reliability_score=rel_score,
                    reliability_signals=rel_signals,
                    recovery_count=1 if recovery_evt else 0,
                    reid_embeddings=initial_embeddings,
                )
                self._tracks[track_id] = track

            active_tracks.append(track)

        return active_tracks
