"""Unit tests for the HELIOS Intelligence & Insights layer."""
import json
import sqlite3
import pytest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.core.config import Settings
from app.database.connection import connect
from app.insights.models import Observation, Insight
from app.insights.scoring import calculate_insight_score, get_priority
from app.insights.observation_layer import ObservationLayer
from app.insights.summaries import RollingSummaryManager
from app.insights.baseline import BaselineEngine
from app.insights.engine import InsightsEngine
from app.insights.nl_investigator import NaturalLanguageInvestigator
from app.services.helios_service import HeliosService


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_insights.db"
    return connect(db_file)


def test_scoring_formula():
    """Verify the 7-signal composite scoring formula."""
    score, breakdown = calculate_insight_score(
        anomaly=80.0,
        persistence=60.0,
        spatial_significance=70.0,
        cross_camera_correlation=50.0,
        density_activity_change=40.0,
        incident_relevance=30.0,
        camera_reliability=100.0,
    )
    # Expected: 0.25*80 + 0.20*60 + 0.15*70 + 0.15*50 + 0.10*40 + 0.10*30 + 0.05*100
    # = 20 + 12 + 10.5 + 7.5 + 4 + 3 + 5 = 62
    assert score == 62
    assert breakdown["anomaly"] == 80.0
    assert get_priority(score) == "IMPORTANT"


def test_priority_hysteresis():
    """Verify that priority transitions require a buffer to prevent bouncing."""
    # 74 is normally IMPORTANT, 75 is CRITICAL
    assert get_priority(76) == "CRITICAL"
    # If previously CRITICAL, dropping slightly to 73 stays CRITICAL due to hysteresis (buffer is 3)
    assert get_priority(73, previous_priority="CRITICAL") == "CRITICAL"
    # Dropping to 71 drops to IMPORTANT
    assert get_priority(71, previous_priority="CRITICAL") == "IMPORTANT"

    # If previously NOTABLE, rising to 51 stays NOTABLE (buffer is 3)
    assert get_priority(51, previous_priority="NOTABLE") == "NOTABLE"
    assert get_priority(54, previous_priority="NOTABLE") == "IMPORTANT"


def test_observation_layer_crud_and_indexing(test_db):
    """Verify structured observation creation, persistence, and fast querying."""
    layer = ObservationLayer(test_db)
    stamp = datetime.now(UTC).isoformat()

    track_data = {
        "track_id": "#P-101",
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "created_at": stamp,
        "last_seen_at": stamp,
        "status": "ENDED",
        "speed": 3.5,
        "direction": "EAST_TO_WEST",
        "movement_state": "WALKING",
        "confidence": 0.94,
        "attributes": {"distance_travelled": 15.2},
    }

    obs = layer.create_or_update_observation(
        track=track_data,
        events=[{"event_id": "EVT-01", "zone_id": "ZONE-EAST"}],
        evidence_ids=["EVD-99"],
        related_cameras=["CAM-01", "CAM-02"],
    )

    assert obs["observation_id"].startswith("OBS-")
    assert obs["track_id"] == "#P-101"
    assert obs["camera_id"] == "CAM-01"
    assert obs["zone_id"] == "ZONE-EAST"
    assert obs["object_type"] == "HUMAN"
    assert obs["speed"] == 3.5
    assert obs["distance_travelled"] == 15.2
    assert "EVT-01" in obs["event_ids"]
    assert "EVD-99" in obs["evidence_ids"]
    assert "CAM-02" in obs["related_cameras"]

    # Query by camera
    results = layer.query(camera_id="CAM-01")
    assert len(results) >= 1
    assert results[0]["track_id"] == "#P-101"

    # Query by object type
    human_results = layer.query(object_type="HUMAN")
    assert len(human_results) >= 1
    vehicle_results = layer.query(object_type="VEHICLE")
    assert len(vehicle_results) == 0

    # Count
    cnt = layer.count(camera_id="CAM-01")
    assert cnt >= 1


def test_rolling_summaries(test_db):
    """Verify rolling window aggregation for precomputed summaries."""
    layer = ObservationLayer(test_db)
    summary_mgr = RollingSummaryManager(test_db)
    now_str = datetime.now(UTC).isoformat()

    # Populate dummy observation
    layer.create_or_update_observation(
        track={
            "track_id": "#P-201",
            "camera_id": "CAM-02",
            "object_type": "HUMAN",
            "created_at": now_str,
            "last_seen_at": now_str,
            "status": "ACTIVE",
            "speed": 1.2,
            "direction": "NORTH",
            "movement_state": "WALKING",
            "confidence": 0.92,
        },
        events=[],
    )

    live_sum = summary_mgr.get_summary("LIVE", force_refresh=True)
    assert live_sum["window"] == "LIVE"
    assert live_sum["people_count"] >= 1
    assert "CAM-02" in live_sum["camera_activity"]


def test_baseline_and_what_changed(test_db):
    """Verify baseline calculation and What Changed comparison."""
    stamp = datetime.now(UTC).isoformat()
    test_db.execute(
        "INSERT INTO cameras VALUES ('CAM-01', 'Front Gate', 'RTSP', 'rtsp://gate', 'Gate', 'ONLINE', 1, ?, ?)",
        (stamp, stamp),
    )
    test_db.execute(
        "INSERT INTO zones (zone_id, camera_id, name, zone_type, geometry, enabled, capacity, created_at, updated_at) "
        "VALUES ('ZONE-01', 'CAM-01', 'North Gate Zone', 'MONITORED', '[]', 1, 5, ?, ?)",
        (stamp, stamp),
    )
    test_db.commit()

    engine = BaselineEngine(test_db)
    changes = engine.get_what_changed()
    assert len(changes) == 1
    item = changes[0]
    assert item["zone_id"] == "ZONE-01"
    assert "normal" in item
    assert "current" in item
    assert "significance" in item


def test_insights_engine_and_feedback(test_db):
    """Verify insights engine telemetry evaluation, deduplication, and feedback."""
    stamp = datetime.now(UTC).isoformat()
    test_db.execute(
        "INSERT INTO zones (zone_id, camera_id, name, zone_type, geometry, enabled, capacity, created_at, updated_at) "
        "VALUES ('ZONE-SURGE', 'CAM-03', 'East Lobby', 'MONITORED', '[]', 1, 2, ?, ?)",
        (stamp, stamp),
    )
    test_db.commit()

    layer = ObservationLayer(test_db)
    # Create 4 human observations in a capacity-2 zone
    for i in range(4):
        layer.create_or_update_observation(
            track={
                "track_id": f"#P-SURGE-{i}",
                "camera_id": "CAM-03",
                "object_type": "HUMAN",
                "created_at": stamp,
                "last_seen_at": stamp,
                "status": "ACTIVE",
                "speed": 0.5,
                "direction": "STATIONARY",
                "movement_state": "STATIONARY",
                "confidence": 0.95,
            },
            events=[{"event_id": f"EVT-S-{i}", "zone_id": "ZONE-SURGE"}],
        )

    engine = InsightsEngine(test_db)
    insights = engine.evaluate_telemetry()
    assert len(insights) >= 1
    surge = insights[0]
    assert surge["type"] == "DENSITY_CHANGE"
    assert surge["priority"] in ("IMPORTANT", "CRITICAL")
    assert "East Lobby" in surge["summary"] or "ZONE-SURGE" in surge["summary"]

    # Record operator feedback
    fb = engine.record_feedback(surge["insight_id"], operator_feedback="CONFIRM", notes="Crowd surge verified")
    assert fb["status"] == "RECORDED"
    assert fb["operator_feedback"] == "CONFIRM"

    updated_ins = engine.get_insight(surge["insight_id"])
    assert updated_ins["status"] == "ACKNOWLEDGED"

    # Header summary
    sum_data = engine.get_summary()
    assert sum_data["total_insights"] >= 1


def test_natural_language_investigator(test_db):
    """Verify natural language investigation with intent filtering and metadata persistence."""
    stamp = datetime.now(UTC).isoformat()
    layer = ObservationLayer(test_db)
    layer.create_or_update_observation(
        track={
            "track_id": "#P-NL-1",
            "camera_id": "CAM-04",
            "object_type": "HUMAN",
            "created_at": stamp,
            "last_seen_at": stamp,
            "status": "ENDED",
            "speed": 2.0,
            "direction": "NORTH",
            "movement_state": "WALKING",
            "confidence": 0.93,
        },
        events=[{"event_id": "EVT-NL-1", "zone_id": "ZONE-04"}],
        evidence_ids=["EVD-NL-1"],
    )

    investigator = NaturalLanguageInvestigator(test_db)
    result = investigator.investigate("How many people were in CAM-04 recently?")

    assert result["investigation_id"].startswith("INV-")
    assert result["answer"]
    assert "observation_ids" in result
    assert "evidence_snapshots" in result
    assert "insight_ids" in result
    assert "provider" in result
    assert "CAM-04" in result["camera_ids"]

    # Verify metadata saved to SQLite ai_investigations table
    saved = test_db.execute(
        "SELECT * FROM ai_investigations WHERE investigation_id=?", (result["investigation_id"],)
    ).fetchone()
    assert saved is not None
    assert saved["question"] == "How many people were in CAM-04 recently?"
    assert saved["answer"] == result["answer"]


def test_insights_api_endpoints():
    """Verify HTTP API endpoints for Insights & Observations."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        # Insights list
        res = client.get("/api/v1/insights")
        assert res.status_code == 200
        assert "insights" in res.json()

        # Insights summary
        sum_res = client.get("/api/v1/insights/summary")
        assert sum_res.status_code == 200
        data = sum_res.json()
        assert "active" in data
        assert "total_insights" in data

        # What Changed
        wc_res = client.get("/api/v1/insights/what-changed")
        assert wc_res.status_code == 200
        assert "changes" in wc_res.json()

        # Rolling Summaries
        roll_res = client.get("/api/v1/insights/summaries/rolling")
        assert roll_res.status_code == 200

        # Observations query
        obs_res = client.get("/api/v1/observations")
        assert obs_res.status_code == 200
        assert "observations" in obs_res.json()

        # Natural Language Investigation
        inv_res = client.post("/api/v1/insights/investigate", json={"question": "What happened in the facility?"})
        assert inv_res.status_code == 200
        inv_data = inv_res.json()
        assert "answer" in inv_data
        assert "investigation_id" in inv_data


def test_evidence_analyzer_color_and_walking(test_db, tmp_path):
    """Verify OpenCV color segmentation and walking telemetry extraction."""
    import cv2
    import numpy as np
    from app.insights.evidence_analyzer import EvidenceAnalyzer

    analyzer = EvidenceAnalyzer(test_db)

    # 1. Test synthetic image color segmentation
    # Create an image: upper half blue (BGR: 255, 0, 0), lower half dark/black
    img = np.zeros((100, 60, 3), dtype=np.uint8)
    img[:50, :] = [255, 0, 0]  # Blue in BGR
    img_path = str(tmp_path / "test_person_crop.jpg")
    cv2.imwrite(img_path, img)

    color_res = analyzer.extract_color_from_image(img, object_type="HUMAN")
    assert "blue" in color_res["dominant_color"].lower() or "blue" in color_res["color_label"].lower()
    assert color_res["upper_color"] == "blue"
    assert color_res["lower_color"] == "black"

    # 2. Test analyze_for_insight with observations and evidence
    now_str = datetime.now(UTC).isoformat()
    test_db.execute(
        "INSERT INTO evidence (evidence_id, event_id, type, storage_reference, timestamp, created_at, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("EVD-TEST-1", "EVT-TEST-1", "CROP", img_path, now_str, now_str, "{}"),
    )
    test_db.commit()

    obs = [{
        "track_id": "#P-WALK-1",
        "object_type": "HUMAN",
        "movement_state": "WALKING",
        "direction": "NORTH_TO_SOUTH",
        "speed": 1.4,
        "dwell_seconds": 65.0,
        "distance_travelled": 25.0,
    }]
    intel = analyzer.analyze_for_insight("DENSITY_CHANGE", active_obs=obs, evidence_ids=["EVD-TEST-1"])
    assert intel["walking_count"] == 1
    assert "walking" in intel["movement_summary"].lower()
    assert len(intel["color_intel"]) >= 1
    assert "blue" in intel["color_summary"].lower()


def test_critical_qwen_synthesis_and_factors():
    """Verify AiExplainer Qwen critical escalation synthesis and fallback."""
    from app.insights.ai_explainer import AiExplainer

    explainer = AiExplainer(model="qwen3:4b", timeout_seconds=1.0)
    signals = {
        "people_count": 8,
        "people_delta": "+500%",
        "duration_seconds": 120,
    }
    baseline = {"normal_people": 2, "normal_activity": 30}
    evidence_intel = {
        "movement_summary": "Walking: 4 (Avg 1.3 m/s, Pacing)",
        "color_summary": "Attire: Dark Upper, Blue Lower",
        "walking_count": 4,
        "avg_speed": 1.3,
        "primary_direction": "North-bound",
        "primary_color_label": "Dark / Blue",
    }

    res = explainer.summarize_critical_insight(
        insight_type="DENSITY_CHANGE",
        signals=signals,
        baseline=baseline,
        cameras=["CAM-EAST"],
        zones=["Perimeter"],
        evidence_intel=evidence_intel,
    )

    assert "summary" in res
    assert "CRITICAL" in res["summary"] or "surveillance" in res["summary"].lower()
    assert "Dark" in res["summary"] or "blue" in res["summary"].lower() or "attire" in res["summary"].lower()
    assert "Walking" in res["summary"] or "movement" in res["summary"].lower() or "speed" in res["summary"].lower()
    assert res["confidence"] >= 0.9
    assert len(res["reasoning_factors"]) >= 2
    assert any("Movement:" in f for f in res["reasoning_factors"])
    assert any("Attire & Colors:" in f for f in res["reasoning_factors"])


def test_critical_insight_escalation_with_intel(test_db, tmp_path):
    """Verify InsightsEngine escalates to CRITICAL with Qwen synthesis and telemetry signals."""
    import cv2
    import numpy as np

    now = datetime.now(UTC)
    now_str = now.isoformat()

    # Create synthetic snapshot
    img = np.zeros((80, 80, 3), dtype=np.uint8)
    img_path = str(tmp_path / "crop_crit.jpg")
    cv2.imwrite(img_path, img)

    # Insert zone and baseline
    test_db.execute(
        "INSERT INTO zones (zone_id, camera_id, name, zone_type, geometry, enabled, capacity, created_at, updated_at) "
        "VALUES ('ZONE-VAULT', 'CAM-05', 'Restricted Vault Zone', 'RESTRICTED', '[]', 1, 1, ?, ?)",
        (now_str, now_str),
    )
    test_db.commit()

    # Insert evidence
    test_db.execute(
        "INSERT INTO evidence (evidence_id, event_id, type, storage_reference, timestamp, created_at, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("EVD-CRIT-1", "EVT-CRIT-1", "CROP", img_path, now_str, now_str, "{}"),
    )
    test_db.commit()

    # Insert 10 active human observations with related cameras to reach CRITICAL score
    layer = ObservationLayer(test_db)
    t_first = (now - timedelta(minutes=3)).isoformat()
    for i in range(10):
        layer.create_or_update_observation(
            track={
                "track_id": f"#P-CRIT-{i}",
                "camera_id": "CAM-05",
                "object_type": "HUMAN",
                "created_at": t_first,
                "last_seen_at": now_str,
                "status": "ACTIVE",
                "speed": 1.5,
                "direction": "SOUTH",
                "movement_state": "WALKING",
                "confidence": 0.96,
                "attributes": {"dwell_seconds": 180.0, "distance_travelled": 40.0},
            },
            events=[{"event_id": f"EVT-C-{i}", "zone_id": "ZONE-VAULT"}],
            evidence_ids=["EVD-CRIT-1"],
            related_cameras=["CAM-05", "CAM-06"],
        )

    engine = InsightsEngine(test_db)
    insights = engine.evaluate_telemetry()
    assert len(insights) >= 1

    crit = [i for i in insights if i["priority"] == "CRITICAL"]
    assert len(crit) >= 1
    crit_ins = crit[0]

    assert crit_ins["priority"] == "CRITICAL"
    signals = crit_ins["signals"]
    assert "movement_intel" in signals
    assert "color_intel" in signals
    assert "evidence_snapshots" in signals
    assert "qwen_analysis" in signals
    assert crit_ins["summary"]


