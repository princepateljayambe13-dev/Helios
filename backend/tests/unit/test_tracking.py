import pytest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.tracking.tracker import ByteTrackTracker, iou
from app.tracking.track_manager import CameraTrackerManager
from app.vision.yolo26 import VideoInferenceManager


def test_iou_calculation():
    a = [0.1, 0.1, 0.2, 0.2]
    b = [0.1, 0.1, 0.2, 0.2]
    assert iou(a, b) == pytest.approx(1.0)

    c = [0.5, 0.5, 0.2, 0.2]
    assert iou(a, c) == 0.0


@pytest.mark.anyio
async def test_track_source_id_continuity(tmp_path):
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)

    obs1 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.9,
        "bounding_box": [0.1, 0.1, 0.1, 0.2],
        "model_name": "human-detector",
        "model_version": "1.0",
        "attributes": {"source_track_id": "detector:101"}
    }
    r1 = await service.ingest(obs1)
    track_id1 = r1["track_id"]

    obs2 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.88,
        "bounding_box": [0.8, 0.8, 0.1, 0.2],
        "model_name": "human-detector",
        "model_version": "1.0",
        "attributes": {"source_track_id": "detector:101"}
    }
    r2 = await service.ingest(obs2)
    assert r2["track_id"] == track_id1


@pytest.mark.anyio
async def test_bytetrack_moving_object_persistent_id(tmp_path):
    """Verify that a moving object across consecutive frames maintains the exact same track ID."""
    settings = Settings(database_path=tmp_path / "helios.db", evidence_directory=tmp_path / "evidence")
    service = HeliosService(connect(settings.database_path), settings)

    # Object moves smoothly across frames without upstream source_track_id
    frames_boxes = [
        [0.10, 0.10, 0.10, 0.20],
        [0.12, 0.12, 0.10, 0.20],
        [0.14, 0.14, 0.10, 0.20],
        [0.16, 0.16, 0.10, 0.20],
    ]

    track_ids = []
    for box in frames_boxes:
        obs = {
            "camera_id": "CAM-01",
            "object_type": "HUMAN",
            "confidence": 0.92,
            "bounding_box": box,
            "model_name": "human-detector",
            "model_version": "yolo26s",
        }
        res = await service.ingest(obs)
        track_ids.append(res["track_id"])

    # All frames must have the exact same track_id
    assert len(set(track_ids)) == 1, f"Expected 1 persistent track_id, got: {track_ids}"

    # Verify positions recorded
    positions = service.db.execute("SELECT COUNT(*) FROM track_positions WHERE track_id=?", (track_ids[0],)).fetchone()[0]
    assert positions == 4

    # Verify track detection count
    track_row = service.db.execute("SELECT detection_count FROM tracks WHERE track_id=?", (track_ids[0],)).fetchone()
    assert track_row["detection_count"] == 4


def test_bytetrack_tracker_multi_object_continuity():
    """Verify ByteTrackTracker tracks multiple objects simultaneously across frames."""
    tracker = ByteTrackTracker(camera_id="CAM-01", track_buffer=30)

    # Frame 1: Person at top-left, Vehicle at bottom-right
    f1_dets = [
        {"bounding_box": [0.10, 0.10, 0.08, 0.16], "confidence": 0.90, "object_type": "HUMAN", "source_class": "person"},
        {"bounding_box": [0.70, 0.70, 0.15, 0.15], "confidence": 0.85, "object_type": "VEHICLE", "source_class": "car"},
    ]
    t1 = tracker.update(f1_dets, image_shape=(1080, 1920))
    assert len(t1) == 2
    p_id1 = next(t.track_id for t in t1 if t.object_type == "HUMAN")
    v_id1 = next(t.track_id for t in t1 if t.object_type == "VEHICLE")

    # Frame 2: Both objects moved slightly
    f2_dets = [
        {"bounding_box": [0.12, 0.11, 0.08, 0.16], "confidence": 0.91, "object_type": "HUMAN", "source_class": "person"},
        {"bounding_box": [0.72, 0.71, 0.15, 0.15], "confidence": 0.86, "object_type": "VEHICLE", "source_class": "car"},
    ]
    t2 = tracker.update(f2_dets, image_shape=(1080, 1920))
    assert len(t2) == 2
    p_id2 = next(t.track_id for t in t2 if t.object_type == "HUMAN")
    v_id2 = next(t.track_id for t in t2 if t.object_type == "VEHICLE")

    assert p_id1 == p_id2
    assert v_id1 == v_id2
    assert p_id1 != v_id1


def test_bytetrack_camera_isolation():
    """Verify that different cameras maintain separate tracker states without interference."""
    manager = CameraTrackerManager()

    # Track on CAM-01
    cam1_dets = [{"bounding_box": [0.20, 0.20, 0.10, 0.20], "confidence": 0.90, "object_type": "HUMAN"}]
    cam1_tracks = manager.track("CAM-01", cam1_dets, image_shape=(1080, 1920))
    assert len(cam1_tracks) == 1
    cam1_id = cam1_tracks[0].track_id

    # Track on CAM-02 with same coordinates
    cam2_dets = [{"bounding_box": [0.20, 0.20, 0.10, 0.20], "confidence": 0.90, "object_type": "HUMAN"}]
    cam2_tracks = manager.track("CAM-02", cam2_dets, image_shape=(1080, 1920))
    assert len(cam2_tracks) == 1
    cam2_id = cam2_tracks[0].track_id

    # Trackers must be distinct instances
    assert manager.get_tracker("CAM-01") is not manager.get_tracker("CAM-02")
    assert cam1_tracks[0].camera_id == "CAM-01"
    assert cam2_tracks[0].camera_id == "CAM-02"


def test_bytetrack_occlusion_and_reappearance():
    """Verify that an object temporarily occluded maintains its track ID upon reappearing."""
    tracker = ByteTrackTracker(camera_id="CAM-01", track_buffer=30)

    # Frame 1: Object detected
    d1 = [{"bounding_box": [0.30, 0.30, 0.10, 0.20], "confidence": 0.92, "object_type": "HUMAN"}]
    t1 = tracker.update(d1, image_shape=(1000, 1000))
    assert len(t1) == 1
    initial_id = t1[0].track_id

    # Frame 2: Object continues
    d2 = [{"bounding_box": [0.32, 0.31, 0.10, 0.20], "confidence": 0.90, "object_type": "HUMAN"}]
    t2 = tracker.update(d2, image_shape=(1000, 1000))
    assert len(t2) == 1
    assert t2[0].track_id == initial_id

    # Frame 3: Occlusion (0 detections)
    t3 = tracker.update([], image_shape=(1000, 1000))
    assert len(t3) == 0
    # Track is marked as LOST in tracker state
    assert tracker._tracks[initial_id].state == "LOST"

    # Frame 4: Object reappears slightly moved
    d4 = [{"bounding_box": [0.34, 0.32, 0.10, 0.20], "confidence": 0.89, "object_type": "HUMAN"}]
    t4 = tracker.update(d4, image_shape=(1000, 1000))
    assert len(t4) == 1
    # Must recover the SAME track ID
    assert t4[0].track_id == initial_id
    assert t4[0].state == "TRACKED"


def test_bytetrack_video_inference_pipeline():
    """Verify that raw YOLO detections feed into ByteTrack and emit observations with persistent source_track_id."""
    manager = VideoInferenceManager.__new__(VideoInferenceManager)
    settings = Settings()
    manager.settings = settings
    manager.tracker_manager = CameraTrackerManager(settings)
    manager._model_config = {
        "classes": ["HUMAN", "VEHICLE"],
        "confidence_threshold": 0.5,
        "device": "cpu",
        "name": "human-detector",
        "version": "yolo26s",
    }

    # Model mock that produces raw boxes without IDs
    class FakeNum:
        def __init__(self, val): self.val = val
        def item(self): return self.val

    class FakeCoords:
        def __init__(self, val): self.val = val
        def tolist(self): return self.val

    frame = SimpleNamespace(shape=(1000, 1000, 3))

    # Frame 1
    boxes_f1 = [
        SimpleNamespace(cls=FakeNum(0), conf=FakeNum(0.90), xyxy=[FakeCoords([100, 100, 200, 300])]),
    ]
    manager._model = SimpleNamespace(predict=lambda *a, **k: [SimpleNamespace(names={0: "person", 2: "car"}, boxes=boxes_f1)])
    obs_f1 = manager._detect(frame, "CAM-01")
    assert len(obs_f1) == 1
    f1_source_id = obs_f1[0]["attributes"]["source_track_id"]
    assert f1_source_id.startswith("human-detector:")

    # Frame 2: Person moves
    boxes_f2 = [
        SimpleNamespace(cls=FakeNum(0), conf=FakeNum(0.88), xyxy=[FakeCoords([110, 110, 210, 310])]),
    ]
    manager._model = SimpleNamespace(predict=lambda *a, **k: [SimpleNamespace(names={0: "person", 2: "car"}, boxes=boxes_f2)])
    obs_f2 = manager._detect(frame, "CAM-01")
    assert len(obs_f2) == 1
    f2_source_id = obs_f2[0]["attributes"]["source_track_id"]

    # ByteTrack must give the exact same source_track_id across consecutive frames
    assert f1_source_id == f2_source_id


def test_bytetrack_alternating_detectors_and_empty_frames():
    """Verify that empty frames and alternating detector passes do not suppress YOLO detections."""
    manager = VideoInferenceManager.__new__(VideoInferenceManager)
    settings = Settings()
    manager.settings = settings
    manager.tracker_manager = CameraTrackerManager(settings)

    class FakeNum:
        def __init__(self, val): self.val = val
        def item(self): return self.val

    class FakeCoords:
        def __init__(self, val): self.val = val
        def tolist(self): return self.val

    frame = SimpleNamespace(shape=(1000, 1000, 3))

    config_human = {"classes": ["HUMAN"], "confidence_threshold": 0.5, "device": "cpu", "name": "human-detector", "version": "yolo26s"}
    config_vehicle = {"classes": ["VEHICLE"], "confidence_threshold": 0.5, "device": "cpu", "name": "vehicle-detector", "version": "yolo26s"}

    empty_model = SimpleNamespace(predict=lambda *a, **k: [SimpleNamespace(names={0: "person", 2: "car"}, boxes=[])])

    # 3 empty cycles
    for _ in range(3):
        manager._detect(frame, "CAM-01", empty_model, config_human)
        manager._detect(frame, "CAM-01", empty_model, config_vehicle)

    # Person appears on Frame 4
    boxes_h = [SimpleNamespace(cls=FakeNum(0), conf=FakeNum(0.92), xyxy=[FakeCoords([150, 150, 250, 350])])]
    human_model = SimpleNamespace(predict=lambda *a, **k: [SimpleNamespace(names={0: "person", 2: "car"}, boxes=boxes_h)])

    obs_h1 = manager._detect(frame, "CAM-01", human_model, config_human)
    obs_v1 = manager._detect(frame, "CAM-01", empty_model, config_vehicle)

    assert len(obs_h1) == 1, "Person must be detected immediately upon entering, even after empty frames"
    assert len(obs_v1) == 0
    t_id1 = obs_h1[0]["attributes"]["source_track_id"]

    # Frame 5: Person moves, vehicle still empty
    boxes_h2 = [SimpleNamespace(cls=FakeNum(0), conf=FakeNum(0.90), xyxy=[FakeCoords([160, 160, 260, 360])])]
    human_model2 = SimpleNamespace(predict=lambda *a, **k: [SimpleNamespace(names={0: "person", 2: "car"}, boxes=boxes_h2)])

    obs_h2 = manager._detect(frame, "CAM-01", human_model2, config_human)
    obs_v2 = manager._detect(frame, "CAM-01", empty_model, config_vehicle)

    assert len(obs_h2) == 1, "Person must continue to be detected across frames"
    assert obs_h2[0]["attributes"]["source_track_id"] == t_id1, "Track ID must remain persistent across motion"

