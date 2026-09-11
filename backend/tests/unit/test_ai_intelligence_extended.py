import json
import pytest
from app.services.helios_service import HeliosService
from app.ai.tools import (
    get_activity_threads,
    get_activity_thread_story,
    search_vehicles,
    execute_tool,
)
from app.ai.assistant import ask
from tests.unit.conftest import DisabledClient
from app.vision.vehicle_intelligence import VehicleClassifier, VehicleIntelligencePipeline


def test_vehicle_heuristic_classification():
    classifier = VehicleClassifier()
    # Wide box (aspect ratio 2.5: w=250, h=100) -> bus / truck / van
    result_wide = classifier.classify_heuristic(bounding_box=[0, 0, 250, 100], source_class="car")
    assert result_wide["type"].lower() in ["bus", "truck", "van"]
    assert result_wide["type_confidence"] > 0.4

    # Tall / narrow box (aspect ratio 0.6: w=60, h=100) -> motorcycle / bicycle
    result_narrow = classifier.classify_heuristic(bounding_box=[0, 0, 60, 100], source_class="car")
    assert result_narrow["type"].lower() in ["motorcycle", "bicycle"]

    # Direct source class mapping
    result_suv = classifier.classify_heuristic(source_class="suv")
    assert result_suv["type"].lower() == "suv"

    result_van = classifier.classify_heuristic(source_class="van")
    assert result_van["type"].lower() == "van"


def test_analyze_vehicle_with_heuristics():
    # Calling analyze_vehicle with dormant CLIP should produce heuristic vehicle_type
    pipeline = VehicleIntelligencePipeline(enable_heuristics=True)
    intel = pipeline.analyze_vehicle(
        image=None,
        source_class="pickup",
        bounding_box=[100, 100, 200, 120],
        vehicle_id="V-TEST-1",
    )
    assert intel["type"].lower() in ["pickup", "pickup truck", "truck", "suv"]


from datetime import datetime, UTC, timedelta


def test_activity_threads_tool_and_story(service):
    now_dt = datetime.now(UTC)
    t0_iso = (now_dt - timedelta(seconds=120)).isoformat()
    t1_iso = now_dt.isoformat()

    service.db.execute(
        """INSERT INTO tracks (track_id, camera_id, object_type, created_at, last_seen_at, status, average_confidence, detection_count, attributes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "T-101",
            "CAM-01",
            "CAR",
            t0_iso,
            t1_iso,
            "ACTIVE",
            0.9,
            5,
            json.dumps({
                "vehicle_intelligence": {
                    "type": "suv",
                    "color": "black",
                    "color_confidence": 0.88,
                    "type_confidence": 0.75,
                }
            }),
        ),
    )
    for i in range(5):
        stamp = (now_dt - timedelta(seconds=100 - i * 25)).isoformat()
        service.db.execute(
            """INSERT INTO detections (detection_id, camera_id, timestamp, object_type, confidence, bounding_box, track_id, zone_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (f"D-101-{i}", "CAM-01", stamp, "CAR", 0.9, "[100, 200, 50, 50]", "T-101", "PERIMETER_NORTH"),
        )
        service.db.execute(
            """INSERT INTO track_positions (track_id, timestamp, bounding_box, confidence)
               VALUES (?, ?, ?, ?)""",
            ("T-101", stamp, "[100, 200, 50, 50]", 0.9),
        )
    service.db.commit()

    threads = get_activity_threads(service, vehicle_type="suv")
    assert threads["count"] == 1
    assert threads["threads"][0]["track_id"] == "T-101"
    assert threads["threads"][0]["threat_level"] in ["LOW", "ELEVATED", "HIGH", "CRITICAL"]

    # Filter by non-matching type
    no_threads = get_activity_threads(service, vehicle_type="sedan")
    assert no_threads["count"] == 0

    # Test story reconstruction tool
    story_result = get_activity_thread_story(service, "T-101")
    assert story_result["track_id"] == "T-101"
    assert "activity_story" in story_result
    assert "threat_level" in story_result
    assert story_result["threat_level"] == "ELEVATED"  # Due to loitering duration in zone
    assert any(n["node_type"] == "ZONE_LOITERING" for n in story_result["timeline_highlights"])


def test_search_vehicles_tool(service):
    now_iso = datetime.now(UTC).isoformat()
    service.db.execute(
        """INSERT INTO tracks (track_id, camera_id, object_type, created_at, last_seen_at, status, average_confidence, detection_count, attributes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "T-202",
            "CAM-02",
            "VEHICLE",
            now_iso,
            now_iso,
            "ACTIVE",
            0.92,
            2,
            json.dumps({
                "vehicle_intelligence": {
                    "type": "van",
                    "color": "white",
                    "color_confidence": 0.92,
                }
            }),
        ),
    )
    service.db.commit()

    search_res = search_vehicles(service, vehicle_type="van", color="white")
    assert search_res["count"] == 1
    assert search_res["vehicles"][0]["track_id"] == "T-202"
    assert search_res["vehicles"][0]["vehicle_type"] == "van"

    # Search with different color
    search_red = search_vehicles(service, color="red")
    assert search_red["count"] == 0


def test_local_assistant_vehicle_intelligence_query(service):
    now_iso = datetime.now(UTC).isoformat()
    service.db.execute(
        """INSERT INTO tracks (track_id, camera_id, object_type, created_at, last_seen_at, status, average_confidence, detection_count, attributes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "T-303",
            "CAM-04",
            "VEHICLE",
            now_iso,
            now_iso,
            "ACTIVE",
            0.88,
            3,
            json.dumps({
                "vehicle_intelligence": {
                    "type": "truck",
                    "color": "blue",
                    "color_confidence": 0.85,
                    "type_confidence": 0.8,
                }
            }),
        ),
    )
    service.db.commit()

    # Ask local assistant about vehicle tracks
    response = ask(service, "Show me all blue vehicles or trucks detected on the perimeter", client=None)
    assert response.grounded is True
    assert "T-303" in response.answer
    assert any(action.type == "OPEN_TRACK" and action.track_id == "T-303" for action in response.actions)


def test_local_assistant_thread_activity_query(service):
    now_dt = datetime.now(UTC)
    t0_iso = (now_dt - timedelta(seconds=150)).isoformat()
    t1_iso = now_dt.isoformat()

    service.db.execute(
        """INSERT INTO tracks (track_id, camera_id, object_type, created_at, last_seen_at, status, average_confidence, detection_count, attributes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "T-404",
            "CAM-01",
            "VEHICLE",
            t0_iso,
            t1_iso,
            "ACTIVE",
            0.95,
            4,
            json.dumps({
                "vehicle_intelligence": {
                    "type": "suv",
                    "color": "black",
                }
            }),
        ),
    )
    for i in range(4):
        stamp = (now_dt - timedelta(seconds=100 - i * 35)).isoformat()
        service.db.execute(
            """INSERT INTO detections (detection_id, camera_id, timestamp, object_type, confidence, bounding_box, track_id, zone_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (f"D-404-{i}", "CAM-01", stamp, "VEHICLE", 0.95, "[50, 50, 30, 30]", "T-404", "GATE_ENTRY"),
        )
        service.db.execute(
            """INSERT INTO track_positions (track_id, timestamp, bounding_box, confidence)
               VALUES (?, ?, ?, ?)""",
            ("T-404", stamp, "[50, 50, 30, 30]", 0.95),
        )
    service.db.commit()

    response = ask(service, "Are there any loitering activity threads or suspicious movement dynamics?", client=None)
    assert response.grounded is True
    assert "T-404" in response.answer
    assert any("threat" in claim.statement.lower() or "elevated" in claim.statement.lower() or "loiter" in claim.statement.lower() for claim in response.claims)
