"""Unit and integration tests for Camera Obstruction & Visibility Detection."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.api import router
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.vision.visibility.detector import CameraMetrics, CameraVisibilityDetector
from app.vision.visibility.manager import CameraVisibilityManager
from app.vision.visibility.temporal import CameraConditionTracker, ConditionRecord


def _make_checkerboard(h: int = 240, w: int = 320, cell: int = 20) -> np.ndarray:
    """Generate a crisp, high-contrast, high-edge checkerboard image."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for r in range(0, h, cell):
        for c in range(0, w, cell):
            if ((r // cell) + (c // cell)) % 2 == 0:
                img[r : r + cell, c : c + cell] = 220
            else:
                img[r : r + cell, c : c + cell] = 30
    return img


# ==============================================================================
# 1. Computer-Vision Metrics Extraction Tests
# ==============================================================================

def test_metrics_black_frame():
    """All-black frame yields 0 brightness, 0 contrast, 0 Laplacian variance."""
    black = np.zeros((240, 320, 3), dtype=np.uint8)
    m = CameraVisibilityDetector.calculate_metrics(black)
    assert m.brightness == 0.0
    assert m.contrast == 0.0
    assert m.laplacian_variance == 0.0
    assert m.white_pixel_ratio == 0.0
    assert m.patch_occlusion_ratio == 1.0


def test_metrics_white_frame():
    """All-white saturated frame yields ~255 brightness and ~1.0 white pixel ratio."""
    white = np.full((240, 320, 3), 255, dtype=np.uint8)
    m = CameraVisibilityDetector.calculate_metrics(white)
    assert m.brightness == 255.0
    assert m.white_pixel_ratio == 1.0
    assert m.contrast == 0.0


def test_metrics_checkerboard():
    """High-contrast checkerboard yields high contrast, sharp edges, and Laplacian variance."""
    img = _make_checkerboard()
    m = CameraVisibilityDetector.calculate_metrics(img)
    assert m.contrast > 50.0
    assert m.edge_density > 0.01
    assert m.laplacian_variance > 50.0


# ==============================================================================
# 2. Condition Classifier Rules Tests
# ==============================================================================

def test_classify_dead_feed():
    black = np.zeros((240, 320, 3), dtype=np.uint8)
    m = CameraVisibilityDetector.calculate_metrics(black)
    res = CameraVisibilityDetector.classify(m)
    assert res.condition == "DEAD_FEED"
    assert res.reliability_score == 5
    assert res.confidence >= 0.90


def test_classify_full_white_overexposure():
    white = np.full((240, 320, 3), 255, dtype=np.uint8)
    m = CameraVisibilityDetector.calculate_metrics(white)
    res = CameraVisibilityDetector.classify(m)
    assert res.condition == "FULL_WHITE_OVEREXPOSURE"
    assert res.reliability_score == 10
    assert res.confidence >= 0.90


def test_classify_partial_white_overexposure():
    # 35% saturated white spotlight, rest medium dark
    img = np.full((240, 320, 3), 140, dtype=np.uint8)
    img[:120, :160] = 255
    m = CameraVisibilityDetector.calculate_metrics(img)
    res = CameraVisibilityDetector.classify(m)
    assert res.condition == "PARTIAL_WHITE_OVEREXPOSURE"
    assert res.reliability_score == 65


def test_classify_blurred_feed():
    # Blurred version of checkerboard
    base = _make_checkerboard()
    blurred = cv2.GaussianBlur(base, (45, 45), 0)
    m = CameraVisibilityDetector.calculate_metrics(blurred)
    res = CameraVisibilityDetector.classify(m)
    assert res.condition == "BLURRED"
    assert res.reliability_score == 40


def test_classify_low_contrast():
    # Uniform flat gray with minor noise
    gray = np.full((240, 320, 3), 110, dtype=np.uint8)
    noise = np.random.randint(-5, 6, gray.shape, dtype=np.int16)
    gray = np.clip(gray.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    m = CameraVisibilityDetector.calculate_metrics(gray)
    res = CameraVisibilityDetector.classify(m)
    assert res.condition == "LOW_CONTRAST"
    assert res.reliability_score == 50


def test_classify_fog_haze():
    # Elevated floor, low edge contrast
    m = CameraMetrics(
        brightness=135.0,
        brightness_p5=45.0,
        brightness_p95=190.0,
        contrast=22.0,
        laplacian_variance=28.0,
        white_pixel_ratio=0.0,
        edge_density=0.005,
        frame_difference=3.0,
        vertical_edge_ratio=1.1,
        patch_occlusion_ratio=0.1,
    )
    res = CameraVisibilityDetector.classify(m)
    assert res.condition == "FOG_HAZE"
    assert res.reliability_score == 70


def test_classify_heavy_rain():
    # High vertical edge ratio and frame difference
    m = CameraMetrics(
        brightness=120.0,
        brightness_p5=20.0,
        brightness_p95=210.0,
        contrast=45.0,
        laplacian_variance=120.0,
        white_pixel_ratio=0.02,
        edge_density=0.035,
        frame_difference=9.5,
        vertical_edge_ratio=2.4,
        patch_occlusion_ratio=0.0,
    )
    res = CameraVisibilityDetector.classify(m)
    assert res.condition == "HEAVY_RAIN"
    assert res.reliability_score == 75


def test_classify_obstructed():
    # Large flat block occluding lens
    m = CameraMetrics(
        brightness=85.0,
        brightness_p5=10.0,
        brightness_p95=160.0,
        contrast=25.0,
        laplacian_variance=30.0,
        white_pixel_ratio=0.0,
        edge_density=0.008,
        frame_difference=1.0,
        vertical_edge_ratio=1.0,
        patch_occlusion_ratio=0.625,
    )
    res = CameraVisibilityDetector.classify(m)
    assert res.condition == "OBSTRUCTED"
    assert res.reliability_score == 20


def test_classify_clear_feed():
    img = _make_checkerboard()
    m = CameraVisibilityDetector.calculate_metrics(img)
    res = CameraVisibilityDetector.classify(m)
    assert res.condition == "CLEAR"
    assert res.reliability_score >= 95


# ==============================================================================
# 3. Temporal Hysteresis State Machine Tests
# ==============================================================================

def test_temporal_hysteresis_filter():
    """Verify state transitions require N consecutive trigger frames and M recovery frames."""
    tracker = CameraConditionTracker("CAM-01", trigger_threshold=3, recovery_threshold=4)
    assert tracker.current_condition == "CLEAR"

    dead_metrics = CameraMetrics(
        brightness=0.0, brightness_p5=0.0, brightness_p95=0.0, contrast=0.0,
        laplacian_variance=0.0, white_pixel_ratio=0.0, edge_density=0.0,
        frame_difference=0.0, vertical_edge_ratio=1.0, patch_occlusion_ratio=1.0
    )
    dead_res = CameraVisibilityDetector.classify(dead_metrics)

    clear_metrics = CameraMetrics(
        brightness=128.0, brightness_p5=30.0, brightness_p95=220.0, contrast=50.0,
        laplacian_variance=160.0, white_pixel_ratio=0.0, edge_density=0.05,
        frame_difference=4.0, vertical_edge_ratio=1.0, patch_occlusion_ratio=0.0
    )
    clear_res = CameraVisibilityDetector.classify(clear_metrics)

    # Frame 1 of DEAD_FEED (should NOT trigger transition yet)
    changed, rec = tracker.update(dead_res)
    assert not changed
    assert rec.condition == "CLEAR"

    # Frame 2 of DEAD_FEED (still NOT triggered)
    changed, rec = tracker.update(dead_res)
    assert not changed
    assert rec.condition == "CLEAR"

    # Intermittent CLEAR frame resets streak
    tracker.update(clear_res)
    changed, rec = tracker.update(dead_res)
    assert not changed
    assert rec.condition == "CLEAR"

    # Now 3 consecutive DEAD_FEED frames
    tracker.update(dead_res)
    changed, rec = tracker.update(dead_res)
    assert changed
    assert rec.condition == "DEAD_FEED"
    assert rec.reliability_score == 5

    # 1 to 3 CLEAR frames should NOT clear the condition
    for _ in range(3):
        changed, rec = tracker.update(clear_res)
        assert not changed
        assert rec.condition == "DEAD_FEED"

    # 4th consecutive CLEAR frame triggers recovery
    changed, rec = tracker.update(clear_res)
    assert changed
    assert rec.condition == "CLEAR"
    assert rec.reliability_score >= 95
    assert rec.resolved_at is not None


# ==============================================================================
# 4. Camera Visibility Manager Tests
# ==============================================================================

def test_visibility_manager_multi_camera():
    manager = CameraVisibilityManager(trigger_threshold=3, recovery_threshold=4)
    black = np.zeros((240, 320, 3), dtype=np.uint8)
    checker = _make_checkerboard()

    # Feed black to CAM-01 three times -> transitions to DEAD_FEED
    for _ in range(2):
        manager.process_frame("CAM-01", black)
    changed, rec = manager.process_frame("CAM-01", black)
    assert changed
    assert rec.condition == "DEAD_FEED"

    # Feed checker to CAM-02 -> stays CLEAR
    changed2, rec2 = manager.process_frame("CAM-02", checker)
    assert not changed2
    assert rec2.condition == "CLEAR"

    all_conds = manager.get_all_conditions()
    assert "CAM-01" in all_conds
    assert all_conds["CAM-01"].condition == "DEAD_FEED"
    assert "CAM-02" in all_conds
    assert all_conds["CAM-02"].condition == "CLEAR"


# ==============================================================================
# 5. Service, DB, Alert & Ingestion Modulation Integration Tests
# ==============================================================================

def test_service_record_and_recovery(tmp_path):
    db_path = tmp_path / "helios.db"
    service = HeliosService(connect(db_path), Settings(database_path=db_path))

    stamp = datetime.now(UTC).isoformat()
    service.db.execute("INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)", ("CAM-01", "Front Gate", "RTSP", "rtsp://gate", "Gate", stamp, stamp))
    service.db.commit()

    # Record degraded condition (OBSTRUCTED)
    metrics = {"brightness": 20.0, "contrast": 5.0, "laplacian_variance": 4.0}
    rec = service.record_camera_condition(
        camera_id="CAM-01",
        condition="OBSTRUCTED",
        reliability_score=20,
        confidence=0.92,
        reason="Lens obstructed by physical barrier",
        metrics=metrics,
        started_at=stamp,
        duration_seconds=12.0,
    )

    # Check camera_reliability table
    rel_row = service.db.execute("SELECT * FROM camera_reliability WHERE camera_id='CAM-01'").fetchone()
    assert rel_row is not None
    assert rel_row["reliability_score"] == 20
    assert rel_row["condition"] == "OBSTRUCTED"

    # Check camera_conditions history table
    cond_rows = service.db.execute("SELECT * FROM camera_conditions WHERE camera_id='CAM-01'").fetchall()
    assert len(cond_rows) == 1
    assert cond_rows[0]["condition"] == "OBSTRUCTED"

    # Check alert was created
    alerts = service.db.execute("SELECT * FROM alerts WHERE status='ACTIVE'").fetchall()
    assert len(alerts) >= 1
    assert alerts[0]["alert_type"] == "camera-obstruction"

    # Check get_camera_condition helper
    info = service.get_camera_condition("CAM-01")
    assert info["reliability_score"] == 20
    assert info["condition"] == "OBSTRUCTED"

    # Recover to CLEAR
    rec_clear = service.record_camera_condition(
        camera_id="CAM-01",
        condition="CLEAR",
        reliability_score=100,
        confidence=0.99,
        reason="CCTV feed restored to clear visibility",
        metrics=metrics,
        started_at=datetime.now(UTC).isoformat(),
        resolved_at=datetime.now(UTC).isoformat(),
        duration_seconds=35.0,
    )

    # Active alerts should now be resolved
    active_alerts = service.db.execute("SELECT * FROM alerts WHERE status='ACTIVE'").fetchall()
    assert len(active_alerts) == 0

    resolved_alerts = service.db.execute("SELECT * FROM alerts WHERE status='RESOLVED'").fetchall()
    assert len(resolved_alerts) >= 1


def test_confidence_modulation_in_ingest(tmp_path):
    """Degraded cameras smoothly reduce detection confidence without dropping tracking."""
    db_path = tmp_path / "helios.db"
    service = HeliosService(connect(db_path), Settings(database_path=db_path))

    stamp = datetime.now(UTC).isoformat()
    service.db.execute("INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)", ("CAM-01", "Gate", "RTSP", "rtsp://gate", "Gate", stamp, stamp))
    service.db.commit()

    # First ingest under normal 100% CLEAR camera
    obs1 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.90,
        "bounding_box": [0.2, 0.2, 0.1, 0.2],
    }
    asyncio.run(service.ingest(obs1))
    assert obs1["confidence"] == 0.90
    assert obs1["attributes"]["camera_reliability"] == 100
    assert obs1["attributes"]["camera_condition"] == "CLEAR"

    # Degrade camera to 16% reliability (OBSTRUCTED)
    service.record_camera_condition(
        camera_id="CAM-01",
        condition="OBSTRUCTED",
        reliability_score=16,
        confidence=0.90,
        reason="Blocked view",
        metrics={},
        started_at=stamp,
    )

    obs2 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.90,
        "bounding_box": [0.22, 0.22, 0.1, 0.2],
    }
    asyncio.run(service.ingest(obs2))
    # (16 / 100) ^ 0.25 = 0.4 ^ 0.5 = 0.6324 -> 0.90 * 0.6324 = 0.5692
    assert obs2["confidence"] < 0.90
    assert obs2["attributes"]["camera_reliability"] == 16
    assert obs2["attributes"]["camera_condition"] == "OBSTRUCTED"


# ==============================================================================
# 6. REST API Endpoints Tests
# ==============================================================================

def test_visibility_api_endpoints(tmp_path):
    db_path = tmp_path / "helios.db"
    settings = Settings(database_path=db_path)
    conn = connect(db_path)
    stamp = datetime.now(UTC).isoformat()
    conn.execute("INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)", ("CAM-01", "North Gate", "RTSP", "rtsp://test", "North", stamp, stamp))
    conn.commit()

    service = HeliosService(conn, settings)
    service.record_camera_condition(
        camera_id="CAM-01",
        condition="HEAVY_RAIN",
        reliability_score=75,
        confidence=0.82,
        reason="Heavy rain streaks detected",
        metrics={"vertical_edge_ratio": 2.2, "frame_difference": 7.5},
        started_at=stamp,
        duration_seconds=15.0,
    )

    app = FastAPI()
    app.state.helios = service
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    # 1. GET /cameras/conditions
    res_all = client.get("/api/v1/cameras/conditions")
    assert res_all.status_code == 200
    all_cams = res_all.json()
    assert len(all_cams) >= 1
    target = next((c for c in all_cams if c["camera_id"] == "CAM-01"), None)
    assert target is not None
    assert target["condition"] == "HEAVY_RAIN"
    assert target["reliability_score"] == 75

    # 2. GET /cameras/CAM-01/condition
    res_cond = client.get("/api/v1/cameras/CAM-01/condition")
    assert res_cond.status_code == 200
    data = res_cond.json()
    assert data["camera_id"] == "CAM-01"
    assert data["condition"] == "HEAVY_RAIN"
    assert data["reliability_score"] == 75

    # 3. GET /cameras/CAM-01/condition/history
    res_hist = client.get("/api/v1/cameras/CAM-01/condition/history")
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert len(hist) >= 1
    assert hist[0]["condition"] == "HEAVY_RAIN"

    # 4. GET /cameras/CAM-01/health
    res_health = client.get("/api/v1/cameras/CAM-01/health")
    assert res_health.status_code == 200
    health = res_health.json()
    assert health["camera_id"] == "CAM-01"
    assert health["condition"] == "HEAVY_RAIN"
    assert health["reliability_score"] == 75


def test_ai_tool_get_camera_condition(tmp_path):
    """Verify Ask HELIOS AI tool returns condition, score, and history."""
    from app.ai.tools import get_camera_condition

    db_path = tmp_path / "helios.db"
    settings = Settings(database_path=db_path)
    conn = connect(db_path)
    stamp = datetime.now(UTC).isoformat()
    conn.execute("INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)", ("CAM-01", "Gate", "RTSP", "rtsp://gate", "Gate", stamp, stamp))
    conn.commit()

    service = HeliosService(conn, settings)
    service.record_camera_condition(
        camera_id="CAM-01",
        condition="BLURRED",
        reliability_score=40,
        confidence=0.90,
        reason="Feed blurred or out of focus",
        metrics={"laplacian_variance": 12.0},
        started_at=stamp,
    )

    # Tool execution for single camera
    tool_res = get_camera_condition(service, camera_id="CAM-01")
    assert "current_condition" in tool_res
    assert tool_res["current_condition"]["condition"] == "BLURRED"
    assert tool_res["current_condition"]["reliability_score"] == 40
    assert len(tool_res["recent_history"]) >= 1

    # Tool execution for all cameras
    all_res = get_camera_condition(service)
    assert "cameras" in all_res
    assert len(all_res["cameras"]) >= 1


def test_insights_camera_degradation(tmp_path):
    """Verify Insights Engine generates an insight when camera is degraded."""
    from app.insights.engine import InsightsEngine

    db_path = tmp_path / "helios.db"
    settings = Settings(database_path=db_path)
    conn = connect(db_path)
    stamp = datetime.now(UTC).isoformat()
    conn.execute("INSERT INTO cameras VALUES (?,?,?,?,?,'ONLINE',1,?,?)", ("CAM-01", "Main Gate", "RTSP", "rtsp://gate", "Gate", stamp, stamp))
    conn.commit()

    service = HeliosService(conn, settings)
    service.record_camera_condition(
        camera_id="CAM-01",
        condition="DEAD_FEED",
        reliability_score=5,
        confidence=0.95,
        reason="Whole black/dead feed detected",
        metrics={"brightness": 0.0},
        started_at=stamp,
    )

    engine = InsightsEngine(service.db)
    insights = engine.evaluate_telemetry()
    cam_insights = [i for i in insights if i["type"] == "CAMERA_DEGRADED"]
    assert len(cam_insights) >= 1
    assert "Main Gate" in cam_insights[0]["summary"]
    assert cam_insights[0]["score"] >= 50
