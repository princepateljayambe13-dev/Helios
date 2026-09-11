"""Unit tests for Helios Movement and Speed Intelligence engine.

Validates:
1. MovementConfig & CameraCalibration (pixels/s to km/h)
2. DirectionCalculator (8 cardinal headings, camera perspective, angular differences)
3. HysteresisMovementClassifier (person state machine chatter prevention, vehicle speed bins)
4. MovementTracker (coordinate normalization, exponential smoothing, distance, change events)
5. Database schema & persistence in track_movements table
6. Helios service activity threads & timeline integration
7. REST API routes for track movements and movement_state filtering
8. AI tools & assistant local intelligence for speed/movement queries
"""

from __future__ import annotations

import math
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from main import app
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.tracking.movement import (
    CameraCalibration,
    DirectionCalculator,
    HysteresisMovementClassifier,
    MovementConfig,
    MovementTracker,
)
from app.tracking.tracker import ByteTrackTracker
from app.ai.tools import execute_tool
from app.ai.assistant import build_local_intel


class TestMovementConfigAndCalibration:
    def test_default_config(self):
        cfg = MovementConfig()
        assert cfg.stationary_threshold == 8.0
        assert cfg.walking_threshold == 35.0
        assert cfg.walking_entry_speed == 10.0
        assert cfg.running_entry_speed == 38.0
        assert cfg.running_exit_speed == 32.0
        assert cfg.walking_exit_speed == 6.0

    def test_camera_calibration_conversion(self):
        calib = CameraCalibration(camera_id="CAM-TEST", pixels_per_meter=20.0)
        assert calib.is_calibrated is True
        # 100 pixels = 5 meters
        assert calib.pixels_to_meters(100.0) == pytest.approx(5.0)
        # 100 px/s with 20 ppm: 5 m/s = 5 * 3.6 = 18.0 km/h
        kmh = calib.speed_to_kmh(100.0)
        assert kmh == pytest.approx(18.0)

    def test_uncalibrated_camera(self):
        calib = CameraCalibration(camera_id="CAM-UNSET")
        assert calib.is_calibrated is False
        assert calib.speed_to_kmh(100.0) is None


class TestDirectionCalculator:
    def test_stationary_direction(self):
        heading, cardinal, persp = DirectionCalculator.calculate_heading_and_direction(0.0, 0.0, speed=0.0)
        assert heading == 0.0
        assert cardinal == "STATIONARY"
        assert "STATIONARY" in persp

    def test_cardinal_directions(self):
        # East: dx > 0, dy = 0 -> 0 deg
        _, east, _ = DirectionCalculator.calculate_heading_and_direction(20.0, 0.0, speed=20.0)
        assert east == "EAST"

        # North: dx = 0, dy < 0 (moving up in frame) -> 90 deg
        _, north, persp_n = DirectionCalculator.calculate_heading_and_direction(0.0, -20.0, speed=20.0)
        assert north == "NORTH"
        assert "Receding" in persp_n

        # West: dx < 0, dy = 0 -> 180 deg
        _, west, _ = DirectionCalculator.calculate_heading_and_direction(-20.0, 0.0, speed=20.0)
        assert west == "WEST"

        # South: dx = 0, dy > 0 (moving down in frame) -> 270 deg
        _, south, persp_s = DirectionCalculator.calculate_heading_and_direction(0.0, 20.0, speed=20.0)
        assert south == "SOUTH"
        assert "Approaching" in persp_s

        # Northeast: dx > 0, dy < 0 -> ~45 deg
        _, ne, _ = DirectionCalculator.calculate_heading_and_direction(20.0, -20.0, speed=28.0)
        assert ne == "NORTH_EAST"

        # Southwest: dx < 0, dy > 0 -> ~225 deg
        _, sw, _ = DirectionCalculator.calculate_heading_and_direction(-20.0, 20.0, speed=28.0)
        assert sw == "SOUTH_WEST"

    def test_angular_difference(self):
        # Direct difference
        assert DirectionCalculator.angle_difference(10.0, 30.0) == pytest.approx(20.0)
        # Wrapping across 0/360 boundary
        assert DirectionCalculator.angle_difference(350.0, 10.0) == pytest.approx(20.0)
        assert DirectionCalculator.angle_difference(10.0, 350.0) == pytest.approx(20.0)


class TestHysteresisMovementClassifier:
    def test_person_hysteresis_ladder(self):
        classifier = HysteresisMovementClassifier()
        state = "STATIONARY"

        # Initial state is STATIONARY
        state = classifier.classify_human(0.0, state)
        assert state == "STATIONARY"

        # Speed 9 px/s: below entry threshold (10), remains STATIONARY
        state = classifier.classify_human(9.0, state)
        assert state == "STATIONARY"

        # Speed 11 px/s: crosses entry threshold (> 10), enters WALKING
        state = classifier.classify_human(11.0, state)
        assert state == "WALKING"

        # Drops to 7 px/s: above exit threshold (6), remains WALKING
        state = classifier.classify_human(7.0, state)
        assert state == "WALKING"

        # Drops to 5 px/s: below exit threshold (< 6), switches to STATIONARY
        state = classifier.classify_human(5.0, state)
        assert state == "STATIONARY"

        # Accelerates directly to 39 px/s: crosses running entry (> 38), enters RUNNING
        state = classifier.classify_human(39.0, state)
        assert state == "RUNNING"

        # Drops to 34 px/s: above running exit (> 32), remains RUNNING
        state = classifier.classify_human(34.0, state)
        assert state == "RUNNING"

        # Drops to 30 px/s: below running exit (< 32), switches to WALKING
        state = classifier.classify_human(30.0, state)
        assert state == "WALKING"

    def test_vehicle_classification(self):
        classifier = HysteresisMovementClassifier()
        assert classifier.classify_vehicle(3.0) == "STATIONARY"
        assert classifier.classify_vehicle(15.0) == "SLOW_MOVING"
        assert classifier.classify_vehicle(50.0) == "CRUISING"
        assert classifier.classify_vehicle(110.0) == "FAST"


class TestMovementTracker:
    def test_smoothing_and_change_detection(self):
        tracker = MovementTracker()
        camera_id = "CAM-01"
        track_id = "T-101"

        # First observation at t=0
        t0 = 1000.0
        box0 = [100.0, 100.0, 40.0, 80.0]
        s0 = tracker.update(track_id, camera_id, "HUMAN", box0, timestamp=t0)
        assert s0.speed == 0.0
        assert s0.movement_state == "STATIONARY"
        assert s0.movement_change is None

        # Step 1: Still stationary at t=1.0
        t1 = 1001.0
        s1 = tracker.update(track_id, camera_id, "HUMAN", box0, timestamp=t1)
        assert s1.movement_state == "STATIONARY"

        # Step 2: Starts walking fast towards East (dx = 25px in 1 sec -> 25 px/s)
        t2 = 1002.0
        box2 = [125.0, 100.0, 40.0, 80.0]
        s2 = tracker.update(track_id, camera_id, "HUMAN", box2, timestamp=t2)
        assert s2.speed > 10.0
        assert s2.movement_state == "WALKING"
        assert s2.direction == "EAST"
        assert s2.movement_change in ("STARTED_MOVING", "ACCELERATED")

        # Step 3: Continues at high speed (running: dx = 60px in 1 sec -> 60 px/s)
        t3 = 1003.0
        box3 = [185.0, 100.0, 40.0, 80.0]
        s3 = tracker.update(track_id, camera_id, "HUMAN", box3, timestamp=t3)
        assert s3.speed > 35.0
        assert s3.movement_state == "RUNNING"
        assert s3.movement_change == "ACCELERATED"

        # Step 4: Sudden turn towards South
        t4 = 1004.0
        box4 = [185.0, 160.0, 40.0, 80.0]
        s4 = tracker.update(track_id, camera_id, "HUMAN", box4, timestamp=t4)
        assert s4.direction == "SOUTH"
        assert s4.movement_change == "DIRECTION_CHANGED"

        # Step 5: Stops completely
        t5 = 1005.0
        tracker.update(track_id, camera_id, "HUMAN", box4, timestamp=t5)
        t6 = 1006.0
        tracker.update(track_id, camera_id, "HUMAN", box4, timestamp=t6)
        t7 = 1007.0
        s7 = tracker.update(track_id, camera_id, "HUMAN", box4, timestamp=t7)
        assert s7.movement_state == "STATIONARY"
        assert s7.speed < 6.0

    def test_normalized_coordinate_handling(self):
        tracker = MovementTracker()
        box_norm_0 = [0.1, 0.1, 0.05, 0.1]
        box_norm_1 = [0.12, 0.1, 0.05, 0.1]  # 0.02 delta_x in 1s on 1920 width = 38.4 px/s

        tracker.update("T-NORM", "CAM-01", "HUMAN", box_norm_0, timestamp=100.0)
        snap = tracker.update("T-NORM", "CAM-01", "HUMAN", box_norm_1, timestamp=101.0)
        assert snap.speed > 20.0
        assert snap.distance_travelled > 20.0


class TestByteTrackIntegration:
    def test_tracker_attaches_movement_to_tracks(self):
        tracker = ByteTrackTracker(camera_id="CAM-01")
        dets1 = [{"bounding_box": [100.0, 100.0, 40.0, 80.0], "confidence": 0.85, "object_type": "HUMAN"}]
        tracks1 = tracker.update(dets1)
        assert len(tracks1) == 1
        t1 = tracks1[0]
        assert hasattr(t1, "speed")
        assert hasattr(t1, "movement_state")
        assert t1.movement_state == "STATIONARY"


class TestDatabaseAndHeliosService:
    @pytest.fixture
    def helios_service(self, tmp_path):
        db = connect(tmp_path / "test_movement.db")
        settings = Settings(database_path=tmp_path / "test_movement.db")
        service = HeliosService(db, settings)
        yield service
        db.close()

    def test_movement_persistence_and_queries(self, helios_service):
        service = helios_service
        camera_id = "CAM-01"
        track_id = "#P-TEST01"

        now = "2026-09-06T12:00:00Z"
        service.db.execute(
            """INSERT INTO tracks (track_id, camera_id, object_type, created_at, last_seen_at, status, average_confidence, current_position, speed, direction, movement_state, attributes)
               VALUES (?, ?, ?, ?, ?, 'ACTIVE', 0.95, ?, 42.5, 'NORTH_EAST', 'RUNNING', '{}')""",
            (track_id, camera_id, "HUMAN", now, now, "[100, 100, 40, 80]"),
        )

        service.db.execute(
            """INSERT INTO track_movements (track_id, camera_id, object_type, timestamp, position, speed, speed_unit, speed_kmh, direction, heading_deg, movement_state, distance_travelled, movement_change)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (track_id, camera_id, "HUMAN", now, "[120, 140, 40, 80]", 42.5, "px/s", None, "NORTH_EAST", 45.0, "RUNNING", 150.0, "ACCELERATED"),
        )

        movements = service.get_track_movements(track_id)
        assert len(movements) == 1
        m = movements[0]
        assert m["track_id"] == track_id
        assert m["speed"] == 42.5
        assert m["movement_state"] == "RUNNING"
        assert m["direction"] == "NORTH_EAST"

        # Test activity thread integration
        thread = service.get_track_thread(track_id)
        assert thread is not None
        assert thread["movement_state"] == "RUNNING"
        assert thread["speed"] == 42.5
        assert thread["direction"] == "NORTH_EAST"

        # Test movement change node present in thread timeline
        timeline_types = [n["node_type"] for n in thread["timeline"]]
        assert "MOVEMENT_CHANGE" in timeline_types

        # Test movement state filter in get_all_threads
        running_threads = service.get_all_threads(movement_state="RUNNING")
        assert any(t["track_id"] == track_id for t in running_threads)

        walking_threads = service.get_all_threads(movement_state="WALKING")
        assert not any(t["track_id"] == track_id for t in walking_threads)


class TestApiAndAiTools:
    @pytest.fixture
    def client_and_service(self, tmp_path):
        db = connect(tmp_path / "test_api_movement.db")
        settings = Settings(database_path=tmp_path / "test_api_movement.db")
        service = HeliosService(db, settings)
        app.state.helios = service
        client = TestClient(app)
        yield client, service
        db.close()

    def test_api_track_movements_route(self, client_and_service):
        client, service = client_and_service
        track_id = "#V-FAST01"
        now = "2026-09-06T12:00:00Z"

        service.db.execute(
            """INSERT INTO tracks (track_id, camera_id, object_type, created_at, last_seen_at, status, average_confidence, current_position, speed, direction, movement_state, attributes)
               VALUES (?, ?, ?, ?, ?, 'ACTIVE', 0.92, ?, ?, ?, ?, '{}')""",
            (track_id, "CAM-01", "VEHICLE", now, now, "[200, 200, 100, 60]", 65.0, "EAST", "CRUISING"),
        )
        service.db.execute(
            """INSERT INTO track_movements (track_id, camera_id, object_type, timestamp, position, speed, speed_unit, speed_kmh, direction, heading_deg, movement_state, distance_travelled, movement_change)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (track_id, "CAM-01", "VEHICLE", now, "[250, 230, 100, 60]", 65.0, "px/s", None, "EAST", 0.0, "CRUISING", 200.0, "STARTED_MOVING"),
        )

        resp = client.get(f"/api/v1/tracks/{track_id}/movements")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["movement_state"] == "CRUISING"

        # Test threads filter by movement_state
        resp_threads = client.get("/api/v1/threads?movement_state=CRUISING")
        assert resp_threads.status_code == 200
        assert any(t["track_id"] == track_id for t in resp_threads.json())

    def test_ai_tool_get_track_movements(self, client_and_service):
        client, service = client_and_service
        track_id = "#P-RUNNER"
        service.db.execute(
            """INSERT INTO tracks (track_id, camera_id, object_type, created_at, last_seen_at, status, average_confidence, current_position, speed, direction, movement_state, attributes)
               VALUES (?, 'CAM-01', 'HUMAN', '2026-09-06T12:00:00Z', '2026-09-06T12:00:00Z', 'ACTIVE', 0.95, '[50, 50, 30, 60]', 45.0, 'NORTH', 'RUNNING', '{}')""",
            (track_id,),
        )
        res = execute_tool(service, "get_track_movements", {"track_id": track_id})
        assert "error" not in res
        assert res["track_id"] == track_id

    def test_assistant_local_intel_movement_questions(self, client_and_service):
        client, service = client_and_service
        track_id = "#P-RUNNER"
        service.db.execute(
            """INSERT INTO tracks (track_id, camera_id, object_type, created_at, last_seen_at, status, average_confidence, current_position, speed, direction, movement_state, attributes)
               VALUES (?, 'CAM-01', 'HUMAN', '2026-09-06T12:00:00Z', '2026-09-06T12:00:00Z', 'ACTIVE', 0.95, '[50, 50, 30, 60]', 45.0, 'NORTH', 'RUNNING', '{}')""",
            (track_id,),
        )
        # Ask assistant "is anyone running?"
        answer, claims, actions, refs = build_local_intel(service, "is anyone running?")
        assert "Movement intelligence" in answer
        assert "RUNNING" in answer
        assert len(actions) > 0
        assert actions[0].track_id == track_id
