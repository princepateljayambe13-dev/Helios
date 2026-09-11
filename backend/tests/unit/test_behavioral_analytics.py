"""Unit tests for HELIOS Behavioral Analytics feature."""
import json
import sqlite3
import pytest
from pathlib import Path

from app.behavioral.models import BehavioralAnomalyScoreBreakdown, BehavioralEvent
from app.behavioral.scorer import (
    calculate_behavioral_anomaly_score,
    WEIGHT_MOVEMENT,
    WEIGHT_SPATIAL,
    WEIGHT_TEMPORAL,
    WEIGHT_DWELL,
    WEIGHT_ACTIVITY_DENSITY,
    WEIGHT_CROSS_CAMERA,
    WEIGHT_BASELINE,
)
from app.behavioral.engine import BehavioralAnalyticsEngine
from app.insights.baseline import BaselineEngine
from app.database.connection import SCHEMA, connect
from app.ai.tools import execute_tool
from app.ai.assistant import build_local_intel, build_dataset_context


@pytest.fixture
def memory_db():
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def test_scorer_weights_and_formula():
    """Verify that the 7 input weights sum to 1.0 and match exact requirements."""
    assert WEIGHT_MOVEMENT == 0.20
    assert WEIGHT_SPATIAL == 0.20
    assert WEIGHT_TEMPORAL == 0.15
    assert WEIGHT_DWELL == 0.15
    assert WEIGHT_ACTIVITY_DENSITY == 0.15
    assert WEIGHT_CROSS_CAMERA == 0.10
    assert WEIGHT_BASELINE == 0.05
    assert round(
        WEIGHT_MOVEMENT
        + WEIGHT_SPATIAL
        + WEIGHT_TEMPORAL
        + WEIGHT_DWELL
        + WEIGHT_ACTIVITY_DENSITY
        + WEIGHT_CROSS_CAMERA
        + WEIGHT_BASELINE,
        4,
    ) == 1.0


def test_scorer_calculation_and_clamping():
    """Test score calculation for both zero, full, and mixed scores."""
    score_0, bd_0 = calculate_behavioral_anomaly_score()
    assert score_0 == 0
    assert bd_0.composite_score == 0

    score_100, bd_100 = calculate_behavioral_anomaly_score(
        movement_deviation=100.0,
        spatial_deviation=100.0,
        temporal_deviation=100.0,
        dwell_deviation=100.0,
        activity_density_deviation=100.0,
        cross_camera_pattern=100.0,
        baseline_deviation=100.0,
    )
    assert score_100 == 100
    assert bd_100.composite_score == 100

    # Test user prompt exact example calculation
    # Score 72 target
    score_mixed, bd_mixed = calculate_behavioral_anomaly_score(
        movement_deviation=80.0,      # 0.20 * 80 = 16
        spatial_deviation=90.0,       # 0.20 * 90 = 18
        temporal_deviation=60.0,      # 0.15 * 60 = 9
        dwell_deviation=80.0,         # 0.15 * 80 = 12
        activity_density_deviation=70.0, # 0.15 * 70 = 10.5
        cross_camera_pattern=50.0,    # 0.10 * 50 = 5
        baseline_deviation=40.0,      # 0.05 * 40 = 2
    )
    # Total = 16 + 18 + 9 + 12 + 10.5 + 5 + 2 = 72.5 -> 72 or 73
    assert score_mixed in (72, 73)
    assert bd_mixed.movement_deviation == 80.0
    assert bd_mixed.spatial_deviation == 90.0
    assert bd_mixed.cross_camera_pattern == 50.0


def test_behavioral_engine_unusual_dwell(memory_db):
    """Detect unusual dwell and verify database persistence."""
    baseline_eng = BaselineEngine(memory_db)
    engine = BehavioralAnalyticsEngine(memory_db, baseline_engine=baseline_eng)

    track = {
        "track_id": "184",
        "camera_id": "CAM-04",
        "object_type": "HUMAN",
        "created_at": "2026-09-10T08:00:00Z",
        "last_seen_at": "2026-09-10T08:04:00Z",  # 240 seconds (4 minutes)
        "speed": 0.0,
        "direction": "STATIONARY",
        "movement_state": "STATIONARY",
        "zone_id": "ZONE-03",
    }
    zone = {
        "zone_id": "ZONE-03",
        "name": "Warehouse Storage",
        "zone_type": "MONITORED",
        "loitering_threshold_seconds": 60.0,
    }

    event = engine.evaluate_track_behavior(track=track, zone_row=zone)
    assert event is not None
    assert event.track_id == "184"
    assert event.camera_id == "CAM-04"
    assert event.zone_id == "ZONE-03"
    assert event.dwell_duration >= 240.0
    assert event.score_breakdown.dwell_deviation > 50.0
    assert any("dwell" in r.lower() for r in event.anomaly_reasons)

    # Check persistence in database
    row = memory_db.execute("SELECT * FROM behavioral_events WHERE track_id='184'").fetchone()
    assert row is not None
    assert row["camera_id"] == "CAM-04"
    assert row["zone_id"] == "ZONE-03"
    assert row["anomaly_score"] > 0
    assert row["dwell_deviation"] > 0

    # Verify behavioral events do not pollute the insights table
    ins = memory_db.execute("SELECT * FROM insights WHERE track_ids LIKE '%184%'").fetchone()
    assert ins is None


def test_behavioral_engine_sudden_speed_and_direction_change(memory_db):
    """Test sudden acceleration and sharp heading change detection."""
    engine = BehavioralAnalyticsEngine(memory_db)

    # Insert movement history showing rapid turn
    memory_db.execute(
        """INSERT INTO track_movements (track_id, camera_id, object_type, timestamp, position, speed, direction, heading_deg, movement_state)
           VALUES ('TRK-99', 'CAM-01', 'HUMAN', '2026-09-10T10:00:00Z', '[0,0,10,10]', 5.0, 'NORTH', 0.0, 'WALKING')"""
    )

    track = {
        "track_id": "TRK-99",
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "speed": 42.0,
        "heading": 120.0,
        "direction": "SOUTH_EAST",
        "movement_state": "RUNNING",
    }
    mov_snap = {
        "speed": 42.0,
        "heading_deg": 120.0,
        "direction": "SOUTH_EAST",
        "movement_state": "RUNNING",
        "acceleration": 35.0,
        "movement_change": "ACCELERATED",
    }

    event = engine.evaluate_track_behavior(track=track, movement_snapshot=mov_snap)
    assert event is not None
    assert event.score_breakdown.movement_deviation >= 40.0
    assert any("acceleration" in r.lower() or "speed" in r.lower() for r in event.anomaly_reasons)
    assert any("course" in r.lower() or "direction" in r.lower() for r in event.anomaly_reasons)


def test_behavioral_engine_restricted_zone(memory_db):
    """Test restricted zone traversal flag."""
    engine = BehavioralAnalyticsEngine(memory_db)

    track = {
        "track_id": "P-55",
        "camera_id": "CAM-02",
        "object_type": "HUMAN",
        "zone_id": "SEC-VAULT",
    }
    zone = {
        "zone_id": "SEC-VAULT",
        "name": "Secure Vault Perimeter",
        "zone_type": "RESTRICTED",
    }

    event = engine.evaluate_track_behavior(track=track, zone_row=zone)
    assert event is not None
    assert event.behavior_type == "RESTRICTED_ZONE_MOVEMENT"
    assert event.score_breakdown.spatial_deviation >= 80.0
    assert any("restricted" in r.lower() for r in event.anomaly_reasons)


def test_behavioral_engine_repeated_zone_visits(memory_db):
    """Test repeated zone visits detection."""
    engine = BehavioralAnalyticsEngine(memory_db)

    # Insert previous zone visits
    memory_db.execute(
        "INSERT INTO events (event_id, event_type, timestamp, camera_id, track_id, zone_id, severity, status, created_at) VALUES ('EV-1', 'ZONE_ENTRY', '2026-09-10T10:00:00Z', 'CAM-01', 'TRK-LOOP', 'ZONE-A', 'INFO', 'CLOSED', '2026-09-10T10:00:00Z')"
    )
    memory_db.execute(
        "INSERT INTO events (event_id, event_type, timestamp, camera_id, track_id, zone_id, severity, status, created_at) VALUES ('EV-2', 'ZONE_ENTRY', '2026-09-10T10:15:00Z', 'CAM-01', 'TRK-LOOP', 'ZONE-A', 'INFO', 'CLOSED', '2026-09-10T10:15:00Z')"
    )

    track = {
        "track_id": "TRK-LOOP",
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "zone_id": "ZONE-A",
    }
    zone = {"zone_id": "ZONE-A", "name": "Zone Alpha", "zone_type": "MONITORED"}

    event = engine.evaluate_track_behavior(track=track, zone_row=zone)
    assert event is not None
    assert event.score_breakdown.spatial_deviation >= 40.0
    assert any("repeated" in r.lower() for r in event.anomaly_reasons)


def test_behavioral_engine_crowd_density_surge(memory_db):
    """Test crowd surge anomaly detection."""
    engine = BehavioralAnalyticsEngine(memory_db)

    track = {
        "track_id": "TRK-CROWD-1",
        "camera_id": "CAM-03",
        "object_type": "HUMAN",
        "zone_id": "ZONE-PLAZA",
    }
    zone = {"zone_id": "ZONE-PLAZA", "name": "Central Plaza", "zone_type": "MONITORED", "capacity": 5}
    density = {
        "people_count": 14,
        "capacity": 5,
        "is_anomaly": True,
    }

    event = engine.evaluate_track_behavior(track=track, zone_row=zone, density_data=density)
    assert event is not None
    assert event.score_breakdown.activity_density_deviation >= 80.0
    assert any("capacity" in r.lower() or "activity" in r.lower() for r in event.anomaly_reasons)


def test_behavioral_engine_cross_camera_pattern(memory_db):
    """Test cross-camera traversal telemetry."""
    engine = BehavioralAnalyticsEngine(memory_db)

    # Insert observation with cross-camera pattern
    memory_db.execute(
        """INSERT INTO observations (observation_id, track_id, camera_id, object_type, first_seen, last_seen, related_cameras, created_at)
           VALUES ('OBS-CC', 'TRK-ROAM', 'CAM-04', 'HUMAN', '2026-09-10T10:00:00Z', '2026-09-10T10:05:00Z', '["CAM-01", "CAM-02", "CAM-04"]', '2026-09-10T10:00:00Z')"""
    )

    track = {
        "track_id": "TRK-ROAM",
        "camera_id": "CAM-04",
        "object_type": "HUMAN",
    }

    event = engine.evaluate_track_behavior(track=track)
    assert event is not None
    assert len(event.related_cameras) >= 3
    assert event.score_breakdown.cross_camera_pattern >= 70.0
    assert any("cameras" in r.lower() for r in event.anomaly_reasons)


class MockHelios:
    """Mock HeliosService for testing AI assistant and registered tools."""
    def __init__(self, db):
        self.db = db
        self.engine = BehavioralAnalyticsEngine(db)

    def get_behavioral_events(self, **kwargs):
        return self.engine.get_events(**kwargs)

    def get_behavioral_event(self, behavior_id):
        return self.engine.get_event(behavior_id)

    def get_behavioral_summary(self):
        return self.engine.get_summary()


def test_ask_helios_behavioral_queries(memory_db):
    """Test Ask HELIOS queries for all required behavioral user queries."""
    helios = MockHelios(memory_db)

    # Populate sample behavioral anomalies
    track = {
        "track_id": "184",
        "camera_id": "CAM-04",
        "object_type": "HUMAN",
        "created_at": "2026-09-10T08:00:00Z",
        "last_seen_at": "2026-09-10T08:04:00Z",
        "speed": 18.5,
        "direction": "NORTH_WEST",
        "movement_state": "WALKING",
        "zone_id": "ZONE-03",
    }
    zone = {
        "zone_id": "ZONE-03",
        "name": "Restricted Sector 3",
        "zone_type": "RESTRICTED",
        "loitering_threshold_seconds": 60.0,
    }

    # Insert observation with related cameras
    memory_db.execute(
        """INSERT INTO observations (observation_id, track_id, camera_id, object_type, first_seen, last_seen, related_cameras, created_at)
           VALUES ('OBS-184', '184', 'CAM-04', 'HUMAN', '2026-09-10T08:00:00Z', '2026-09-10T08:04:00Z', '["CAM-01", "CAM-04"]', '2026-09-10T08:00:00Z')"""
    )
    helios.engine.evaluate_track_behavior(track=track, zone_row=zone)

    # 1. "How many behavioral anomalies happened today?"
    text_count, claims, actions, refs = build_local_intel(helios, "How many behavioral anomalies happened today?")
    assert "behavioral anomal" in text_count.lower()
    assert "1" in text_count

    # 2. "Which zone had the highest anomaly score?"
    text_zone, claims, actions, refs = build_local_intel(helios, "Which zone had the highest anomaly score?")
    assert "zone-03" in text_zone.lower()
    assert "highest" in text_zone.lower()

    # 3. "Why was Track 184 flagged?"
    text_why, claims, actions, refs = build_local_intel(helios, "Why was Track 184 flagged?")
    assert "track #184" in text_why.lower() or "track 184" in text_why.lower()
    assert "anomaly score" in text_why.lower()

    # 4. "How long did the unusual behaviour last?"
    text_duration, claims, actions, refs = build_local_intel(helios, "How long did the unusual behaviour last?")
    assert ("minute" in text_duration.lower() or "second" in text_duration.lower())
    assert "184" in text_duration

    # 5. "Which cameras had related behaviour?"
    text_cams, claims, actions, refs = build_local_intel(helios, "Which cameras had related behaviour?")
    assert "cam-04" in text_cams or "CAM-01" in text_cams


def test_ai_tool_execution(memory_db):
    """Test direct execution of registered backend behavioral tools."""
    helios = MockHelios(memory_db)

    track = {
        "track_id": "P-900",
        "camera_id": "CAM-02",
        "object_type": "HUMAN",
        "created_at": "2026-09-10T09:00:00Z",
        "last_seen_at": "2026-09-10T09:02:30Z",
        "speed": 0.0,
        "direction": "STATIONARY",
        "movement_state": "STATIONARY",
        "zone_id": "ZONE-VIP",
    }
    zone = {"zone_id": "ZONE-VIP", "name": "VIP Room", "zone_type": "RESTRICTED", "loitering_threshold_seconds": 30.0}
    beh = helios.engine.evaluate_track_behavior(track=track, zone_row=zone)

    # Tool: get_behavioral_anomalies
    res_list = execute_tool(helios, "get_behavioral_anomalies", {"camera_id": "CAM-02"})
    assert "behavioral_events" in res_list
    assert len(res_list["behavioral_events"]) >= 1

    # Tool: get_behavioral_anomaly_detail
    res_detail = execute_tool(helios, "get_behavioral_anomaly_detail", {"behavior_id": beh.behavior_id})
    assert "behavioral_event" in res_detail
    assert res_detail["behavioral_event"]["track_id"] == "P-900"
    assert "score_breakdown" in res_detail["behavioral_event"]

    # Tool: get_behavioral_analytics_summary
    res_sum = execute_tool(helios, "get_behavioral_analytics_summary", {})
    assert "total_behavioral_events" in res_sum
    assert res_sum["total_behavioral_events"] >= 1
