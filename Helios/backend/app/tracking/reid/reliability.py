"""Track Reliability Score Engine for HELIOS.

Evaluates multi-modal trajectory quality using 5 key signals:
1. Detection Confidence (25%): Average / EMA detector confidence.
2. Appearance Consistency (25%): Pairwise cosine similarity among OSNet Re-ID embeddings.
3. Motion Consistency (20%): Kinematic smoothness, low acceleration jerk.
4. Trajectory Stability (15%): Bounding box aspect-ratio stability and low spatial jitter.
5. Track Age / Maturity (15%): Lifecycle length and detection count maturity curve.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.tracking.reid.osnet import OSNetExtractor


@dataclass
class ReliabilityConfig:
    """Configurable weights and tuning thresholds for track reliability scoring."""

    weight_confidence: float = 0.25
    weight_appearance: float = 0.25
    weight_motion: float = 0.20
    weight_stability: float = 0.15
    weight_age: float = 0.15

    # Maturity threshold in detection count
    maturity_detection_count: int = 15

    # Maximum expected acceleration threshold (px/s^2) for normalization
    max_acceleration_threshold: float = 60.0


class TrackReliabilityCalculator:
    """Computes comprehensive reliability scores and diagnostic signals for active tracks."""

    def __init__(self, config: ReliabilityConfig | None = None) -> None:
        self.config = config or ReliabilityConfig()

    def compute_reliability(
        self,
        confidence: float,
        detection_count: int,
        embeddings: list[list[float]] | None = None,
        speed: float = 0.0,
        acceleration: float = 0.0,
        trajectory_boxes: list[list[float]] | None = None,
    ) -> tuple[float, dict[str, float]]:
        """Compute composite Track Reliability Score and signal breakdown.

        Returns:
            (composite_score, signal_breakdown) where composite_score is in [0.0, 1.0].
        """
        # 1. Detection Confidence Signal (25%)
        s_conf = max(0.0, min(1.0, float(confidence)))

        # 2. Appearance Consistency Signal (25%)
        if embeddings and len(embeddings) >= 2:
            sims: list[float] = []
            for i in range(len(embeddings) - 1):
                sim = OSNetExtractor.cosine_similarity(embeddings[i], embeddings[i + 1])
                sims.append(max(0.0, min(1.0, sim)))
            s_app = float(np.mean(sims)) if sims else 0.85
        else:
            # Baseline expectation for single or non-biometric detection
            s_app = 0.85

        # 3. Motion Consistency Signal (20%)
        # Penalize excessive acceleration / jerky velocity changes
        abs_acc = abs(float(acceleration))
        acc_penalty = min(1.0, abs_acc / self.config.max_acceleration_threshold)
        s_motion = max(0.0, 1.0 - acc_penalty)
        if speed < 5.0:
            # Stationary tracks have inherently stable motion
            s_motion = max(s_motion, 0.90)

        # 4. Trajectory Stability Signal (15%)
        # Check aspect ratio jitter between recent bounding boxes
        if trajectory_boxes and len(trajectory_boxes) >= 2:
            jitters: list[float] = []
            recent_boxes = trajectory_boxes[-5:]
            for i in range(len(recent_boxes) - 1):
                b0 = recent_boxes[i]
                b1 = recent_boxes[i + 1]
                ar0 = (b0[2] / b0[3]) if b0[3] > 0 else 1.0
                ar1 = (b1[2] / b1[3]) if b1[3] > 0 else 1.0
                diff = abs(ar1 - ar0) / max(ar0, ar1, 1e-4)
                jitters.append(diff)
            mean_jitter = float(np.mean(jitters)) if jitters else 0.0
            s_stab = max(0.0, min(1.0, 1.0 - 2.0 * mean_jitter))
        else:
            s_stab = 0.90

        # 5. Track Age / Maturity Signal (15%)
        s_age = min(1.0, max(1, detection_count) / float(self.config.maturity_detection_count))

        # Composite Reliability Score
        composite = (
            self.config.weight_confidence * s_conf
            + self.config.weight_appearance * s_app
            + self.config.weight_motion * s_motion
            + self.config.weight_stability * s_stab
            + self.config.weight_age * s_age
        )
        composite = round(max(0.0, min(1.0, composite)), 3)

        signals = {
            "detection_confidence": round(s_conf, 3),
            "appearance_consistency": round(s_app, 3),
            "motion_consistency": round(s_motion, 3),
            "trajectory_stability": round(s_stab, 3),
            "track_age": round(s_age, 3),
            "composite_score": composite,
        }
        return composite, signals
