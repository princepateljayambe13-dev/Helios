"""Hungarian Algorithm Matching Engine with 4-Signal Cost Matrix and Gating.

Implements optimal linear sum assignment for track-detection association and recovery:
- OSNet appearance similarity: 40%
- Position distance: 30%
- Motion consistency: 20%
- IoU / box similarity: 10%
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.tracking.reid.osnet import OSNetExtractor


def bbox_iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Compute Intersection-over-Union between two [x, y, w, h] boxes."""
    ax, ay, aw, ah = map(float, a[:4])
    bx, by, bw, bh = map(float, b[:4])
    left, top, right, bottom = max(ax, bx), max(ay, by), min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def angle_diff_deg(a: float, b: float) -> float:
    """Compute absolute angular difference in degrees accounting for wrap-around."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


@dataclass
class MatchingConfig:
    """Configurable weights, gates, and thresholds for Hungarian matching."""

    # 4-factor cost weights (must sum to 1.0)
    weight_appearance: float = 0.40
    weight_position: float = 0.30
    weight_motion: float = 0.20
    weight_iou: float = 0.10

    # Gating thresholds
    gate_position_distance: float = 0.45       # Max normalized distance allowed
    gate_min_appearance_sim: float = 0.15      # Minimum cosine appearance similarity
    gate_size_ratio_max: float = 4.0           # Maximum allowed area discrepancy ratio
    gate_size_ratio_min: float = 0.25          # Minimum allowed area discrepancy ratio

    # Matching acceptance cutoff
    max_matching_cost: float = 0.65            # Pairs with cost > this are rejected
    recovery_cost_threshold: float = 0.55      # Stricter threshold for restoring LOST tracks
    recovery_reid_threshold: float = 0.50      # Minimum appearance similarity to confirm recovery

    # Infinity cost for gated pairs
    gating_cost: float = 1e5


@dataclass
class MatchResult:
    """Output of Hungarian assignment."""

    matched_pairs: list[tuple[int, int]]       # (track_idx, det_idx)
    unmatched_tracks: list[int]
    unmatched_detections: list[int]
    cost_matrix: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))
    detailed_costs: list[dict[str, float]] = field(default_factory=list)


class HungarianMatcher:
    """Computes multi-modal matching cost matrices and executes Hungarian matching."""

    def __init__(self, config: MatchingConfig | None = None) -> None:
        self.config = config or MatchingConfig()

    @staticmethod
    def solve_linear_assignment(cost_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Solve linear sum assignment problem using SciPy, lap, or NumPy Munkres fallback."""
        if cost_matrix.size == 0:
            return np.array([], dtype=int), np.array([], dtype=int)

        # 1. Try SciPy linear_sum_assignment
        try:
            from scipy.optimize import linear_sum_assignment

            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            return np.asarray(row_ind, dtype=int), np.asarray(col_ind, dtype=int)
        except ImportError:
            pass

        # 2. Try LAP (Jonker-Volgenant)
        try:
            import lap

            _, x, _ = lap.lapjv(cost_matrix, extend_cost=True)
            row_ind = np.array([i for i, c in enumerate(x) if c >= 0], dtype=int)
            col_ind = np.array([c for c in x if c >= 0], dtype=int)
            return row_ind, col_ind
        except Exception:
            pass

        # 3. Greedy Hungarian fallback approximation
        rows, cols = cost_matrix.shape
        matched_rows: list[int] = []
        matched_cols: list[int] = []
        used_rows = set()
        used_cols = set()

        # Sort all elements by cost
        flat_indices = np.argsort(cost_matrix, axis=None)
        for idx in flat_indices:
            r, c = divmod(int(idx), cols)
            if r not in used_rows and c not in used_cols:
                used_rows.add(r)
                used_cols.add(c)
                matched_rows.append(r)
                matched_cols.append(c)
                if len(used_rows) == rows or len(used_cols) == cols:
                    break

        return np.array(matched_rows, dtype=int), np.array(matched_cols, dtype=int)

    def calculate_pair_cost(
        self,
        track_info: dict[str, Any],
        det_info: dict[str, Any],
    ) -> tuple[float, dict[str, float]]:
        """Calculate the 4-factor matching cost and check gating conditions between one track and detection.

        Returns:
            (cost, component_breakdown) where cost is in [0.0, 1.0] (or config.gating_cost if gated).
        """
        # 0. Strict category gating
        trk_type = str(track_info.get("object_type", "HUMAN")).upper()
        det_type = str(det_info.get("object_type", "HUMAN")).upper()
        if trk_type != det_type:
            return self.config.gating_cost, {"gated": 1.0, "reason": "object_type_mismatch"}

        trk_box = track_info.get("predicted_bbox") or track_info.get("bbox") or [0, 0, 0, 0]
        det_box = det_info.get("bounding_box") or det_info.get("bbox") or [0, 0, 0, 0]

        # Check area discrepancy gate
        area_trk = max(1e-6, trk_box[2] * trk_box[3])
        area_det = max(1e-6, det_box[2] * det_box[3])
        area_ratio = area_det / area_trk
        if area_ratio > self.config.gate_size_ratio_max or area_ratio < self.config.gate_size_ratio_min:
            return self.config.gating_cost, {"gated": 1.0, "reason": "area_ratio_gate"}

        # 1. Position Distance Cost (30%)
        # Euclidean center distance normalized by bounding box / frame scale
        cx_trk = trk_box[0] + trk_box[2] / 2.0
        cy_trk = trk_box[1] + trk_box[3] / 2.0
        cx_det = det_box[0] + det_box[2] / 2.0
        cy_det = det_box[1] + det_box[3] / 2.0

        pos_dist = math.hypot(cx_det - cx_trk, cy_det - cy_trk)
        if pos_dist > self.config.gate_position_distance:
            return self.config.gating_cost, {"gated": 1.0, "reason": "position_distance_gate"}

        c_pos = min(1.0, pos_dist / self.config.gate_position_distance)

        # 2. OSNet Appearance Cost (40%)
        trk_emb = track_info.get("reid_embedding") or track_info.get("reid_embeddings")
        det_emb = det_info.get("reid_embedding")

        # If track holds a gallery of embeddings, match against the representative or best embedding
        if isinstance(trk_emb, list) and len(trk_emb) > 0 and isinstance(trk_emb[0], list):
            # Compute maximum cosine similarity across recent gallery
            if det_emb is not None:
                sims = [OSNetExtractor.cosine_similarity(e, det_emb) for e in trk_emb]
                app_sim = max(sims) if sims else 0.0
            else:
                app_sim = 0.5
        elif trk_emb is not None and det_emb is not None:
            app_sim = OSNetExtractor.cosine_similarity(trk_emb, det_emb)
        else:
            # Neutral similarity if embeddings unavailable
            app_sim = 0.5

        # Check appearance similarity gate (only when appearance features are present on both)
        if trk_emb is not None and det_emb is not None:
            if app_sim < self.config.gate_min_appearance_sim:
                return self.config.gating_cost, {"gated": 1.0, "reason": "appearance_similarity_gate"}

        # Cost is inverse of positive similarity in [0, 1]
        c_app = 1.0 - max(0.0, min(1.0, app_sim))

        # 3. Motion Consistency Cost (20%)
        # Compare track's last known heading / direction with displacement vector to detection
        trk_heading = track_info.get("heading_deg", track_info.get("heading", 0.0))
        trk_speed = track_info.get("speed", 0.0)

        dx = cx_det - cx_trk
        dy = cy_det - cy_trk
        disp = math.hypot(dx, dy)

        if trk_speed >= 5.0 and disp >= 0.005:
            # Video space: -dy is positive northward
            disp_angle_rad = math.atan2(-dy, dx)
            disp_heading_deg = (math.degrees(disp_angle_rad) + 360.0) % 360.0
            angle_diff = angle_diff_deg(trk_heading, disp_heading_deg)
            # Motion consistency in [0.0, 1.0]: 1.0 when aligned, 0.0 when opposite (180 deg)
            motion_consistency = (1.0 + math.cos(math.radians(angle_diff))) / 2.0
            c_motion = 1.0 - motion_consistency
        else:
            # Stationary or very small displacement: no motion discrepancy penalty
            c_motion = 0.0
            motion_consistency = 1.0

        # 4. IoU / Box Similarity Cost (10%)
        iou_val = bbox_iou(trk_box, det_box)
        c_iou = 1.0 - iou_val

        # Composite Cost (0.40 app + 0.30 pos + 0.20 motion + 0.10 iou)
        total_cost = (
            self.config.weight_appearance * c_app
            + self.config.weight_position * c_pos
            + self.config.weight_motion * c_motion
            + self.config.weight_iou * c_iou
        )
        total_cost = max(0.0, min(1.0, total_cost))

        breakdown = {
            "appearance_cost": round(c_app, 4),
            "appearance_similarity": round(app_sim, 4),
            "position_cost": round(c_pos, 4),
            "position_distance": round(pos_dist, 4),
            "motion_cost": round(c_motion, 4),
            "motion_consistency": round(motion_consistency, 4),
            "iou_cost": round(c_iou, 4),
            "iou": round(iou_val, 4),
            "composite_cost": round(total_cost, 4),
        }
        return total_cost, breakdown

    def match(
        self,
        tracks: list[dict[str, Any]],
        detections: list[dict[str, Any]],
        max_cost_override: float | None = None,
    ) -> MatchResult:
        """Perform optimal one-to-one Hungarian matching on tracks and detections.

        Args:
            tracks: List of track dicts (with bbox/predicted_bbox, reid_embedding, heading, etc.).
            detections: List of detection dicts (with bounding_box, reid_embedding, etc.).
            max_cost_override: Optional custom acceptance cutoff threshold.

        Returns:
            MatchResult containing matched pairs and unmatched indices.
        """
        n_t = len(tracks)
        n_d = len(detections)

        if n_t == 0 or n_d == 0:
            return MatchResult(
                matched_pairs=[],
                unmatched_tracks=list(range(n_t)),
                unmatched_detections=list(range(n_d)),
                cost_matrix=np.empty((n_t, n_d), dtype=np.float32),
            )

        cutoff = max_cost_override if max_cost_override is not None else self.config.max_matching_cost
        cost_matrix = np.full((n_t, n_d), self.config.gating_cost, dtype=np.float32)
        detailed_matrix: list[list[dict[str, float]]] = [[{} for _ in range(n_d)] for _ in range(n_t)]

        for i, trk in enumerate(tracks):
            for j, det in enumerate(detections):
                cost, details = self.calculate_pair_cost(trk, det)
                cost_matrix[i, j] = cost
                detailed_matrix[i][j] = details

        row_ind, col_ind = self.solve_linear_assignment(cost_matrix)

        matched_pairs: list[tuple[int, int]] = []
        matched_details: list[dict[str, float]] = []
        assigned_tracks = set()
        assigned_dets = set()

        for r, c in zip(row_ind, col_ind, strict=False):
            cost_val = float(cost_matrix[r, c])
            # Check cutoff and gating
            if cost_val <= cutoff and cost_val < self.config.gating_cost:
                matched_pairs.append((int(r), int(c)))
                matched_details.append(detailed_matrix[r][c])
                assigned_tracks.add(int(r))
                assigned_dets.add(int(c))

        unmatched_tracks = [i for i in range(n_t) if i not in assigned_tracks]
        unmatched_dets = [j for j in range(n_d) if j not in assigned_dets]

        return MatchResult(
            matched_pairs=matched_pairs,
            unmatched_tracks=unmatched_tracks,
            unmatched_detections=unmatched_dets,
            cost_matrix=cost_matrix,
            detailed_costs=matched_details,
        )
