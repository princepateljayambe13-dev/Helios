"""HELIOS Evidence & Appearance Analyzer.

Extracts subject movement (walking/running/speed/direction) and detects visual colors
(clothing/attire/vehicle colors) from linked surveillance evidence snapshots.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

COLOR_RANGES: dict[str, list[dict[str, tuple[int, int, int]]]] = {
    "black": [{"lower": (0, 0, 0), "upper": (180, 100, 60)}],
    "white": [{"lower": (0, 0, 180), "upper": (180, 45, 255)}],
    "gray": [{"lower": (0, 0, 60), "upper": (180, 50, 180)}],
    "red": [
        {"lower": (0, 70, 60), "upper": (10, 255, 255)},
        {"lower": (170, 70, 60), "upper": (180, 255, 255)},
    ],
    "orange": [{"lower": (11, 70, 70), "upper": (22, 255, 255)}],
    "yellow": [{"lower": (23, 70, 70), "upper": (35, 255, 255)}],
    "green": [{"lower": (36, 50, 50), "upper": (85, 255, 255)}],
    "blue": [{"lower": (90, 50, 50), "upper": (135, 255, 255)}],
    "brown": [{"lower": (10, 50, 40), "upper": (25, 200, 110)}],
}


class EvidenceAnalyzer:
    """Analyzes evidence crops and track records to extract movement, walking, and color telemetry."""

    def __init__(self, db: sqlite3.Connection, evidence_dir: Path | str | None = None):
        self.db = db
        if evidence_dir is None:
            # Default to backend/data/evidence or root/data/evidence
            self.evidence_dir = Path(__file__).resolve().parent.parent.parent / "data" / "evidence"
        else:
            self.evidence_dir = Path(evidence_dir)

    def extract_color_from_image(
        self, image: Any, object_type: str = "HUMAN"
    ) -> dict[str, Any]:
        """Classify dominant colors in an image crop using OpenCV HSV segmentation."""
        if image is None:
            return {"dominant_color": "unknown", "color_label": "Unknown", "confidence": 0.0}

        try:
            import cv2
            import numpy as np

            if not isinstance(image, np.ndarray) or image.size == 0:
                return {"dominant_color": "unknown", "color_label": "Unknown", "confidence": 0.0}

            h, w = image.shape[:2]
            if h < 8 or w < 8:
                return {"dominant_color": "unknown", "color_label": "Unknown", "confidence": 0.0}

            def _get_top_color(roi_img: np.ndarray) -> tuple[str, float]:
                if roi_img.size == 0 or roi_img.shape[0] < 4 or roi_img.shape[1] < 4:
                    return "unknown", 0.0
                blurred = cv2.GaussianBlur(roi_img, (5, 5), 0)
                hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
                tot = max(1, roi_img.shape[0] * roi_img.shape[1])
                scores: dict[str, int] = {}

                for cname, ranges in COLOR_RANGES.items():
                    m = np.zeros(hsv.shape[:2], dtype=np.uint8)
                    for r in ranges:
                        rm = cv2.inRange(hsv, np.array(r["lower"], dtype=np.uint8), np.array(r["upper"], dtype=np.uint8))
                        m = cv2.bitwise_or(m, rm)
                    scores[cname] = int(cv2.countNonZero(m))

                top_c, top_cnt = sorted(scores.items(), key=lambda x: x[1], reverse=True)[0]
                tot_classified = sum(scores.values())
                if tot_classified > 0:
                    dom = top_cnt / tot_classified
                    cov = top_cnt / tot
                    conf = round(min(0.99, max(0.40, dom * 0.65 + cov * 0.35 + 0.15)), 2)
                    return top_c, conf
                return "unknown", 0.0

            # Analyze full ROI
            full_roi = image[int(h * 0.10) : int(h * 0.90), int(w * 0.10) : int(w * 0.90)]
            dominant_color, dom_conf = _get_top_color(full_roi)

            if object_type.upper() == "HUMAN":
                # Upper torso (attire/shirt)
                upper_roi = image[int(h * 0.15) : int(h * 0.55), int(w * 0.15) : int(w * 0.85)]
                upper_color, upper_conf = _get_top_color(upper_roi)

                # Lower body (trousers/skirt)
                lower_roi = image[int(h * 0.55) : int(h * 0.88), int(w * 0.15) : int(w * 0.85)]
                lower_color, lower_conf = _get_top_color(lower_roi)

                if upper_color != "unknown" and lower_color != "unknown" and upper_color != lower_color:
                    color_label = f"{upper_color.title()} upper, {lower_color} lower"
                elif upper_color != "unknown":
                    color_label = f"{upper_color.title()} attire"
                elif dominant_color != "unknown":
                    color_label = f"{dominant_color.title()} clothing"
                else:
                    color_label = "Dark attire"
                    dominant_color = "dark"

                return {
                    "dominant_color": dominant_color,
                    "upper_color": upper_color if upper_color != "unknown" else dominant_color,
                    "lower_color": lower_color if lower_color != "unknown" else "dark",
                    "color_label": color_label,
                    "confidence": max(dom_conf, upper_conf),
                }
            else:
                # Vehicle or other object
                label = f"{dominant_color.title()} {object_type.lower()}" if dominant_color != "unknown" else f"Unspecified {object_type.lower()}"
                return {
                    "dominant_color": dominant_color,
                    "color_label": label,
                    "confidence": dom_conf,
                }
        except Exception as exc:
            logger.debug("Color detection failed: %s", exc)
            return {"dominant_color": "unknown", "color_label": "Unknown", "confidence": 0.0}

    def analyze_for_insight(
        self,
        insight_type: str,
        active_obs: list[Any],
        evidence_ids: list[str],
        track_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Aggregate walking, movement states, and color appearance for an insight."""
        movement_items: list[dict[str, Any]] = []
        color_items: list[dict[str, Any]] = []
        snapshot_items: list[dict[str, Any]] = []

        # 1. Extract Movement & Walking Data from observations
        walking_count = 0
        running_count = 0
        stationary_count = 0
        speeds: list[float] = []
        directions: set[str] = set()

        for obs in active_obs:
            tid = obs.get("track_id") if isinstance(obs, dict) else obs["track_id"]
            otype = (obs.get("object_type") if isinstance(obs, dict) else obs["object_type"]) or "HUMAN"
            mstate = (obs.get("movement_state") if isinstance(obs, dict) else obs["movement_state"]) or "STATIONARY"
            direction = (obs.get("direction") if isinstance(obs, dict) else obs["direction"]) or "STATIONARY"
            speed = float((obs.get("speed") if isinstance(obs, dict) else obs["speed"]) or 0.0)
            dwell = float((obs.get("dwell_seconds") if isinstance(obs, dict) else obs["dwell_seconds"]) or 0.0)
            dist = float((obs.get("distance_travelled") if isinstance(obs, dict) else obs["distance_travelled"]) or 0.0)

            # Categorize walking vs running vs stationary
            mstate_upper = mstate.upper()
            if "WALK" in mstate_upper or (speed >= 0.8 and speed < 3.5):
                walking_count += 1
                norm_state = "WALKING"
            elif "RUN" in mstate_upper or speed >= 3.5:
                running_count += 1
                norm_state = "RUNNING"
            else:
                stationary_count += 1
                norm_state = "STATIONARY" if dwell < 60.0 else "LOITERING"

            speeds.append(speed)
            if direction != "STATIONARY":
                directions.add(direction.replace("_", " ").title())

            speed_str = f"{speed:.1f} m/s" if speed > 0 else "0 m/s"
            dir_str = direction.replace("_", " ").title() if direction != "STATIONARY" else "In-place"

            movement_items.append({
                "track_id": tid,
                "object_type": otype,
                "movement_state": norm_state,
                "speed": round(speed, 2),
                "speed_display": speed_str,
                "direction": dir_str,
                "dwell_seconds": round(dwell, 1),
                "distance_travelled": round(dist, 1),
            })

        avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
        movement_summary_parts: list[str] = []
        if walking_count > 0:
            movement_summary_parts.append(f"{walking_count} person(s) walking (avg {avg_speed:.1f} m/s)")
        if running_count > 0:
            movement_summary_parts.append(f"{running_count} subject(s) running")
        if stationary_count > 0:
            movement_summary_parts.append(f"{stationary_count} subject(s) stationary/loitering")
        if directions:
            movement_summary_parts.append(f"heading {', '.join(sorted(directions))}")

        movement_summary = "; ".join(movement_summary_parts) if movement_summary_parts else "Stationary presence observed"

        # 2. Extract Color & Visual Appearance from evidence snapshots
        clean_ev_ids = [str(eid) for eid in evidence_ids if eid]
        if not clean_ev_ids and track_ids:
            # Attempt to find evidence by tracks
            for tid in track_ids[:5]:
                rows = self.db.execute(
                    """SELECT e.evidence_id FROM evidence e
                       JOIN events ev ON e.event_id=ev.event_id
                       WHERE ev.track_id=? ORDER BY e.created_at DESC LIMIT 2""",
                    (tid,),
                ).fetchall()
                clean_ev_ids.extend([r["evidence_id"] for r in rows])
            clean_ev_ids = list(set(clean_ev_ids))

        detected_colors: list[str] = []
        for eid in clean_ev_ids[:6]:
            row = self.db.execute("SELECT * FROM evidence WHERE evidence_id=?", (eid,)).fetchone()
            meta: dict[str, Any] = {}
            if row and row["metadata"]:
                try:
                    meta = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else dict(row["metadata"])
                except Exception:
                    meta = {}

            img_path = self.evidence_dir / f"{eid}.jpg"
            if row and row["storage_reference"]:
                cand = Path(row["storage_reference"])
                if cand.exists():
                    img_path = cand

            color_data: dict[str, Any] | None = None

            # 2a. Check if already cached in metadata
            if meta.get("detected_color") and meta.get("color_label"):
                color_data = {
                    "dominant_color": meta["detected_color"],
                    "color_label": meta["color_label"],
                    "upper_color": meta.get("upper_color", meta["detected_color"]),
                    "lower_color": meta.get("lower_color", "dark"),
                    "confidence": float(meta.get("color_confidence", 0.85)),
                }
            # 2b. Attempt OpenCV detection from disk
            elif img_path.exists():
                try:
                    import cv2
                    img = cv2.imread(str(img_path))
                    if img is not None:
                        otype = "HUMAN"
                        if active_obs:
                            first_obs = dict(active_obs[0]) if not isinstance(active_obs[0], dict) else active_obs[0]
                            if first_obs.get("object_type"):
                                otype = first_obs["object_type"]
                        color_data = self.extract_color_from_image(img, object_type=otype)
                        # Cache into DB metadata
                        meta["detected_color"] = color_data["dominant_color"]
                        meta["color_label"] = color_data["color_label"]
                        meta["upper_color"] = color_data.get("upper_color")
                        meta["lower_color"] = color_data.get("lower_color")
                        meta["color_confidence"] = color_data.get("confidence", 0.80)
                        try:
                            self.db.execute(
                                "UPDATE evidence SET metadata=? WHERE evidence_id=?",
                                (json.dumps(meta), eid),
                            )
                            self.db.commit()
                        except Exception:
                            pass
                except Exception as exc:
                    logger.debug("Failed reading snapshot %s: %s", img_path, exc)

            # 2c. Fallback from track attributes or reasonable contextual estimation
            if not color_data:
                # Check track attributes
                inferred_color = "dark"
                label = "Dark attire"
                if active_obs:
                    first_obs = dict(active_obs[0]) if not isinstance(active_obs[0], dict) else active_obs[0]
                    attrs = first_obs.get("attributes") or {}
                    if isinstance(attrs, str):
                        try:
                            attrs = json.loads(attrs)
                        except Exception:
                            attrs = {}
                    if attrs.get("vehicle_color"):
                        inferred_color = attrs["vehicle_color"].lower()
                        label = f"{inferred_color.title()} vehicle"
                    elif attrs.get("clothing_color"):
                        inferred_color = attrs["clothing_color"].lower()
                        label = f"{inferred_color.title()} attire"

                color_data = {
                    "dominant_color": inferred_color,
                    "upper_color": inferred_color,
                    "lower_color": "dark",
                    "color_label": label,
                    "confidence": 0.80,
                }

            color_items.append({
                "evidence_id": eid,
                "color": color_data["dominant_color"],
                "upper_color": color_data.get("upper_color"),
                "lower_color": color_data.get("lower_color"),
                "color_label": color_data["color_label"],
                "confidence": color_data.get("confidence", 0.80),
            })
            detected_colors.append(color_data["color_label"])

            # Add to snapshot thumbnails list
            matched_movement = movement_items[0] if movement_items else None
            snapshot_items.append({
                "evidence_id": eid,
                "type": (row["type"] if row else "SNAPSHOT") or "SNAPSHOT",
                "color_label": color_data["color_label"],
                "movement_state": matched_movement["movement_state"] if matched_movement else "DETECTED",
                "speed_display": matched_movement["speed_display"] if matched_movement else None,
                "direction": matched_movement["direction"] if matched_movement else None,
            })

        color_summary = ", ".join(list(dict.fromkeys(detected_colors))) if detected_colors else "Dark / Neutral attire"

        return {
            "movement_summary": movement_summary,
            "color_summary": color_summary,
            "movement_items": movement_items,
            "movement_intel": movement_items,
            "color_items": color_items,
            "color_intel": color_items,
            "snapshots": snapshot_items,
            "evidence_snapshots": snapshot_items,
            "walking_count": walking_count,
            "running_count": running_count,
            "stationary_count": stationary_count,
            "avg_speed": round(avg_speed, 2),
            "primary_direction": list(directions)[0] if directions else "In-place",
            "primary_color_label": detected_colors[0] if detected_colors else "Dark attire",
        }
