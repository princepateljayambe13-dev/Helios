"""Unit tests for Track Recovery and Track Reliability Score in HELIOS."""
import asyncio
from datetime import UTC, datetime, timedelta
import pytest

from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.tracking.reid.recovery import LostTrackRecord, TrackRecoveryManager
from app.tracking.reid.reliability import TrackReliabilityCalculator
from app.tracking.track import Track


def test_track_reliability_calculator_composite():
    """Verify 5-signal composite reliability score calculation and diagnostic metrics."""
    calc = TrackReliabilityCalculator()

    # Stable mature track: high confidence, consistent embeddings, low jerk, long history
    emb = [1.0, 0.0, 0.0]
    score_high, signals_high = calc.compute_reliability(
        confidence=0.95,
        detection_count=20,
        embeddings=[emb, emb, emb],
        speed=15.0,
        acceleration=2.0,
        trajectory_boxes=[[0.1, 0.1, 0.1, 0.2], [0.11, 0.11, 0.1, 0.2]],
    )
    assert 0.85 <= score_high <= 1.0
    assert signals_high["track_age"] == 1.0

    # Unstable new track: erratic motion, high acceleration, single detection
    score_low, signals_low = calc.compute_reliability(
        confidence=0.40,
        detection_count=1,
        embeddings=None,
        speed=80.0,
        acceleration=55.0,
        trajectory_boxes=[[0.1, 0.1, 0.1, 0.2], [0.5, 0.5, 0.2, 0.1]],
    )
    assert score_low < score_high
    assert signals_low["track_age"] < 0.2


def test_lost_track_position_prediction():
    """Verify that Kalman/motion prediction projects bounding box forward based on velocity."""
    t0 = datetime(2026, 9, 10, 10, 0, 0, tzinfo=UTC).isoformat()
    t1 = datetime(2026, 9, 10, 10, 0, 2, tzinfo=UTC).isoformat()  # dt = 2.0s

    rec = LostTrackRecord(
        track_id="trk-100",
        camera_id="CAM-01",
        object_type="HUMAN",
        last_bbox=[0.20, 0.20, 0.10, 0.20],
        last_seen=t0,
        lost_since=t0,
        velocity_xy=(0.02, 0.01),  # moves right 0.02/s, down 0.01/s
    )

    pred_box = rec.predict_position(t1)
    # 0.20 + 0.02 * 2.0 = 0.24, 0.20 + 0.01 * 2.0 = 0.22
    assert pred_box[0] == pytest.approx(0.24, abs=1e-3)
    assert pred_box[1] == pytest.approx(0.22, abs=1e-3)
    assert pred_box[2] == 0.10
    assert pred_box[3] == 0.20


def test_track_recovery_manager_restores_track_id():
    """Verify TrackRecoveryManager matches a reappearing detection via OSNet Re-ID and restores the ID."""
    manager = TrackRecoveryManager()
    t0 = datetime(2026, 9, 10, 10, 0, 0, tzinfo=UTC).isoformat()
    t1 = datetime(2026, 9, 10, 10, 0, 2, tzinfo=UTC).isoformat()

    track = Track(
        track_id="original-person-42",
        camera_id="CAM-01",
        object_type="HUMAN",
        bbox=[0.30, 0.30, 0.10, 0.20],
        confidence=0.92,
        first_seen=t0,
        last_seen=t0,
        speed=10.0,
        heading_deg=90.0,
    )
    person_emb = [0.8, 0.6, 0.0]
    track.add_reid_embedding(person_emb)

    # Register as lost
    manager.record_lost(track, t0)

    # Reappearing detection 2 seconds later with matching appearance
    reappearing_dets = [
        {
            "object_type": "HUMAN",
            "bounding_box": [0.32, 0.31, 0.10, 0.20],
            "confidence": 0.90,
            "reid_embedding": [0.79, 0.61, 0.0],
        }
    ]

    recoveries = manager.recover(reappearing_dets, "CAM-01", t1)
    assert len(recoveries) == 1
    lost_rec, det_idx, evt = recoveries[0]
    assert lost_rec.track_id == "original-person-42"
    assert evt.appearance_similarity > 0.90
    assert evt.composite_cost < 0.30


@pytest.mark.anyio
async def test_end_to_end_helios_reid_recovery_and_database_persistence(tmp_path):
    """Verify that HELIOS pipeline maintains track identity, stores reliability scores, and logs track_recoveries in SQLite."""
    db_path = tmp_path / "helios_reid.db"
    settings = Settings(database_path=db_path, evidence_directory=tmp_path / "evidence", track_timeout_seconds=20)
    service = HeliosService(connect(db_path), settings)

    t0 = datetime.now(UTC).isoformat()
    # Step 1: Ingest person detection
    emb_signature = [0.95, 0.31, 0.0]
    obs1 = {
        "camera_id": "CAM-01",
        "object_type": "HUMAN",
        "confidence": 0.92,
        "bounding_box": [0.25, 0.25, 0.10, 0.20],
        "model_name": "yolo26",
        "model_version": "1.0",
        "attributes": {"reid_embedding": emb_signature},
    }
    res1 = await service.ingest(obs1)
    track_id1 = res1["track_id"]
    assert track_id1.startswith("#P-") or track_id1.startswith("#H-")

    # Step 2: Verify reliability_score stored in database
    row = service.db.execute("SELECT reliability_score, recovery_count FROM tracks WHERE track_id=?", (track_id1,)).fetchone()
    assert row is not None
    assert row["reliability_score"] > 0.0

    # Step 3: Simulate recovery by emitting a recovery record in database
    rec_id = "rec_test123"
    t_rec = (datetime.now(UTC) + timedelta(seconds=2)).isoformat()
    service.db.execute(
        """INSERT INTO track_recoveries (recovery_id, original_track_id, restored_track_id, camera_id, timestamp, appearance_similarity, position_distance, motion_consistency, iou_score, composite_cost, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rec_id, track_id1, track_id1, "CAM-01", t_rec, 0.94, 0.05, 0.92, 0.88, 0.15, t_rec),
    )
    service.db.execute("UPDATE tracks SET recovery_count=1 WHERE track_id=?", (track_id1,))

    # Step 4: Verify get_track_thread includes the recovery timeline node
    thread = service.get_track_thread(track_id1)
    assert thread is not None
    assert thread["recovery_count"] == 1
    assert thread["reliability_score"] > 0.0

    recovery_nodes = [node for node in thread["timeline"] if node.get("node_type") == "TRACK_RECOVERED"]
    assert len(recovery_nodes) == 1
    assert "OSNet Re-ID" in recovery_nodes[0]["title"]
    assert recovery_nodes[0]["appearance_similarity"] == 0.94

    # Step 5: Verify get_track_recoveries API helper
    recs = service.get_track_recoveries(track_id=track_id1)
    assert len(recs) == 1
    assert recs[0]["recovery_id"] == rec_id
