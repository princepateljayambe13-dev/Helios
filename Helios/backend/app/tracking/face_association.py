"""Spatial-temporal association between FACE detections/tracks and HUMAN targets.

In modern multi-modal surveillance pipelines, human detectors (YOLO full body)
and face detectors (Roboflow head/face workflows) operate asynchronously at
different frame rates. This module matches face bounding boxes into human bodies
using spatial containment, upper-torso alignment, and temporal persistence.
"""
from __future__ import annotations

import json
from typing import Any, Sequence


def _parse_box(box: Any) -> list[float] | None:
    if isinstance(box, (list, tuple)) and len(box) >= 4:
        return [float(v) for v in box[:4]]
    if isinstance(box, str):
        try:
            parsed = json.loads(box)
            if isinstance(parsed, (list, tuple)) and len(parsed) >= 4:
                return [float(v) for v in parsed[:4]]
        except Exception:
            return None
    return None


def calculate_face_human_overlap(
    face_box: Sequence[float],
    human_box: Sequence[float],
) -> dict[str, Any]:
    """Calculate spatial containment and torso alignment of a face within a human bounding box.

    Both bounding boxes are in normalized [x, y, w, h] format (0.0 to 1.0).

    Returns:
        Dictionary containing:
            - is_match (bool): True if face is convincingly associated with human
            - score (float): Association confidence (0.0 to 1.0)
            - containment (float): Ratio of face area inside the human box
            - face_center (tuple): (fcx, fcy)
    """
    fx, fy, fw, fh = (float(v) for v in face_box[:4])
    hx, hy, hw, hh = (float(v) for v in human_box[:4])

    if fw <= 0 or fh <= 0 or hw <= 0 or hh <= 0:
        return {"is_match": False, "score": 0.0, "containment": 0.0, "face_center": (0.0, 0.0)}

    fcx = fx + fw / 2.0
    fcy = fy + fh / 2.0
    hcx = hx + hw / 2.0

    # The expected head center of a standing or seated human is in the top 15% of the body box
    expected_head_y = hy + hh * 0.15

    # 1. Intersection area
    inter_x1 = max(fx, hx)
    inter_y1 = max(fy, hy)
    inter_x2 = min(fx + fw, hx + hw)
    inter_y2 = min(fy + fh, hy + hh)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    face_area = fw * fh

    containment = min(1.0, max(0.0, inter_area / face_area))

    # 2. Anatomical sanity boundaries:
    # Face center must be within or very close to horizontal bounds of human box
    horiz_margin = max(0.02, hw * 0.10)
    in_horiz = (hx - horiz_margin) <= fcx <= (hx + hw + horiz_margin)

    # Face center must be in the upper 60% of the body (head to upper chest)
    # Allows a slight margin above the top of the body box (hair, hat, tilted angle)
    vert_top_margin = max(0.03, hh * 0.08)
    in_vert = (hy - vert_top_margin) <= fcy <= (hy + hh * 0.60)

    if not in_horiz or not in_vert or containment < 0.35:
        return {
            "is_match": False,
            "score": 0.0,
            "containment": containment,
            "face_center": (fcx, fcy),
        }

    # 3. Quality score combination:
    # - 50% from containment percentage
    # - 30% from horizontal alignment with body center
    # - 20% from vertical proximity to expected head level
    horiz_dist_ratio = min(1.0, abs(fcx - hcx) / max(0.001, hw / 2.0))
    horiz_score = max(0.0, 1.0 - horiz_dist_ratio)

    vert_dist_ratio = min(1.0, abs(fcy - expected_head_y) / max(0.001, hh * 0.40))
    vert_score = max(0.0, 1.0 - vert_dist_ratio)

    score = (containment * 0.50) + (horiz_score * 0.30) + (vert_score * 0.20)
    score = min(1.0, max(0.0, score))

    is_match = score >= 0.45

    return {
        "is_match": is_match,
        "score": score,
        "containment": containment,
        "face_center": (fcx, fcy),
    }


def find_matching_human_track(
    face_box: Sequence[float],
    active_human_tracks: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any] | None, float]:
    """Find the best human track that encloses or matches the given face bounding box.

    Returns:
        Tuple of (best_human_track_or_none, match_score)
    """
    best_human: dict[str, Any] | None = None
    best_score: float = 0.0

    for human in active_human_tracks:
        pos = human.get("current_position") or human.get("bounding_box")
        human_box = _parse_box(pos)
        if not human_box:
            continue

        res = calculate_face_human_overlap(face_box, human_box)
        if res["is_match"] and res["score"] > best_score:
            best_score = res["score"]
            best_human = human

    return best_human, best_score


def find_matching_face_track(
    human_box: Sequence[float],
    active_face_tracks: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any] | None, float]:
    """Find the best face track that belongs inside the given human bounding box.

    Returns:
        Tuple of (best_face_track_or_none, match_score)
    """
    best_face: dict[str, Any] | None = None
    best_score: float = 0.0

    for face in active_face_tracks:
        pos = face.get("current_position") or face.get("bounding_box")
        face_box = _parse_box(pos)
        if not face_box:
            continue

        res = calculate_face_human_overlap(face_box, human_box)
        if res["is_match"] and res["score"] > best_score:
            best_score = res["score"]
            best_face = face

    return best_face, best_score
