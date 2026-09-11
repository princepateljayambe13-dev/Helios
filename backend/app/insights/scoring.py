"""Priority scoring engine with multi-signal weighting and hysteresis."""
from __future__ import annotations

from typing import Any


PRIORITY_BANDS = [
    (75, 100, "CRITICAL"),
    (50, 74, "IMPORTANT"),
    (25, 49, "NOTABLE"),
    (0, 24, "INFORMATIONAL"),
]

# Hysteresis buffer in score points to avoid fluctuating states
HYSTERESIS_BUFFER = 3.0


def calculate_insight_score(
    anomaly: float = 0.0,
    persistence: float = 0.0,
    spatial_significance: float = 0.0,
    cross_camera_correlation: float = 0.0,
    density_activity_change: float = 0.0,
    incident_relevance: float = 0.0,
    camera_reliability: float = 1.0,
) -> tuple[int, dict[str, float]]:
    """Calculate the 7-signal composite priority score (0–100).

    Inputs can be 0.0-1.0 or 0-100; values <= 1.0 are scaled to 0-100.
    """
    def _norm(val: float) -> float:
        v = float(val or 0.0)
        if 0.0 <= v <= 1.0:
            return v * 100.0
        return max(0.0, min(100.0, v))

    s_anomaly = _norm(anomaly)
    s_persist = _norm(persistence)
    s_spatial = _norm(spatial_significance)
    s_cross = _norm(cross_camera_correlation)
    s_density = _norm(density_activity_change)
    s_incident = _norm(incident_relevance)
    s_cam = _norm(camera_reliability)

    raw = (
        0.25 * s_anomaly
        + 0.20 * s_persist
        + 0.15 * s_spatial
        + 0.15 * s_cross
        + 0.10 * s_density
        + 0.10 * s_incident
        + 0.05 * s_cam
    )
    final_score = int(round(max(0.0, min(100.0, raw))))

    breakdown = {
        "anomaly": round(s_anomaly, 1),
        "persistence": round(s_persist, 1),
        "spatial_significance": round(s_spatial, 1),
        "cross_camera_correlation": round(s_cross, 1),
        "density_activity_change": round(s_density, 1),
        "incident_relevance": round(s_incident, 1),
        "camera_reliability": round(s_cam, 1),
        "raw_score": round(raw, 2),
    }
    return final_score, breakdown


def get_priority(score: int, previous_priority: str | None = None) -> str:
    """Determine priority label with hysteresis to prevent oscillation."""
    base_priority = "INFORMATIONAL"
    if score >= 75:
        base_priority = "CRITICAL"
    elif score >= 50:
        base_priority = "IMPORTANT"
    elif score >= 25:
        base_priority = "NOTABLE"
    else:
        base_priority = "INFORMATIONAL"

    if not previous_priority:
        return base_priority

    # Apply hysteresis if previous state exists
    if previous_priority == "CRITICAL":
        if score < (75 - HYSTERESIS_BUFFER):
            return "IMPORTANT" if score >= 50 else "NOTABLE" if score >= 25 else "INFORMATIONAL"
        return "CRITICAL"
    elif previous_priority == "IMPORTANT":
        if score >= (75 + HYSTERESIS_BUFFER):
            return "CRITICAL"
        if score < (50 - HYSTERESIS_BUFFER):
            return "NOTABLE" if score >= 25 else "INFORMATIONAL"
        return "IMPORTANT"
    elif previous_priority == "NOTABLE":
        if score >= (50 + HYSTERESIS_BUFFER):
            return "IMPORTANT"
        if score < (25 - HYSTERESIS_BUFFER):
            return "INFORMATIONAL"
        return "NOTABLE"
    else:  # INFORMATIONAL
        if score >= (25 + HYSTERESIS_BUFFER):
            return "NOTABLE"
        return "INFORMATIONAL"
