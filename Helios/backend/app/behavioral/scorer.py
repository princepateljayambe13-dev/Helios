"""Behavioral Anomaly Scorer for HELIOS.

Computes the 7-input weighted Behavioral Anomaly Score (0–100):
- Movement Deviation: 20%
- Spatial Deviation: 20%
- Temporal Deviation: 15%
- Dwell Deviation: 15%
- Activity/Density Deviation: 15%
- Cross-Camera Pattern: 10%
- Baseline Deviation: 5%
"""
from __future__ import annotations

from typing import Any
from app.behavioral.models import BehavioralAnomalyScoreBreakdown


WEIGHT_MOVEMENT = 0.20
WEIGHT_SPATIAL = 0.20
WEIGHT_TEMPORAL = 0.15
WEIGHT_DWELL = 0.15
WEIGHT_ACTIVITY_DENSITY = 0.15
WEIGHT_CROSS_CAMERA = 0.10
WEIGHT_BASELINE = 0.05


def _normalize(val: float | int | None) -> float:
    """Normalize input value to float range 0.0 - 100.0.

    Supports both ratio (0.0 - 1.0) and percentage (0.0 - 100.0).
    """
    v = float(val or 0.0)
    if 0.0 < v <= 1.0:
        return v * 100.0
    return max(0.0, min(100.0, v))


def calculate_behavioral_anomaly_score(
    movement_deviation: float = 0.0,
    spatial_deviation: float = 0.0,
    temporal_deviation: float = 0.0,
    dwell_deviation: float = 0.0,
    activity_density_deviation: float = 0.0,
    cross_camera_pattern: float = 0.0,
    baseline_deviation: float = 0.0,
) -> tuple[int, BehavioralAnomalyScoreBreakdown]:
    """Calculate the composite Behavioral Anomaly Score (0–100) and breakdown."""
    norm_mov = _normalize(movement_deviation)
    norm_spatial = _normalize(spatial_deviation)
    norm_temp = _normalize(temporal_deviation)
    norm_dwell = _normalize(dwell_deviation)
    norm_act = _normalize(activity_density_deviation)
    norm_cross = _normalize(cross_camera_pattern)
    norm_base = _normalize(baseline_deviation)

    raw_score = (
        WEIGHT_MOVEMENT * norm_mov
        + WEIGHT_SPATIAL * norm_spatial
        + WEIGHT_TEMPORAL * norm_temp
        + WEIGHT_DWELL * norm_dwell
        + WEIGHT_ACTIVITY_DENSITY * norm_act
        + WEIGHT_CROSS_CAMERA * norm_cross
        + WEIGHT_BASELINE * norm_base
    )

    final_score = int(round(max(0.0, min(100.0, raw_score))))

    breakdown = BehavioralAnomalyScoreBreakdown(
        movement_deviation=norm_mov,
        spatial_deviation=norm_spatial,
        temporal_deviation=norm_temp,
        dwell_deviation=norm_dwell,
        activity_density_deviation=norm_act,
        cross_camera_pattern=norm_cross,
        baseline_deviation=norm_base,
        composite_score=final_score,
    )

    return final_score, breakdown
