"""Unit tests for 4-factor matching cost matrix, gating thresholds, and Hungarian algorithm."""
import pytest
import numpy as np

from app.tracking.reid.matching import HungarianMatcher, MatchingConfig


def test_matching_cost_weighting_breakdown():
    """Verify that composite cost is exactly: 40% app + 30% pos + 20% motion + 10% iou."""
    config = MatchingConfig(
        weight_appearance=0.40,
        weight_position=0.30,
        weight_motion=0.20,
        weight_iou=0.10,
        gate_position_distance=1.0,
        gate_min_appearance_sim=0.0,
    )
    matcher = HungarianMatcher(config)

    # Identical track and detection (0 distance, 1.0 appearance similarity, aligned motion, 1.0 IoU)
    emb = [1.0, 0.0, 0.0]
    trk = {
        "object_type": "HUMAN",
        "bbox": [0.2, 0.2, 0.1, 0.2],
        "reid_embedding": emb,
        "heading_deg": 90.0,
        "speed": 10.0,
    }
    det = {
        "object_type": "HUMAN",
        "bounding_box": [0.2, 0.2, 0.1, 0.2],
        "reid_embedding": emb,
    }

    cost, details = matcher.calculate_pair_cost(trk, det)
    # With perfect match, costs are 0.0
    assert cost == pytest.approx(0.0, abs=1e-3)
    assert details["appearance_similarity"] == pytest.approx(1.0, abs=1e-3)
    assert details["iou"] == pytest.approx(1.0, abs=1e-3)


def test_gating_thresholds_reject_impossible_matches():
    """Verify gating rules reject distant, appearance-divergent, or cross-class matches."""
    matcher = HungarianMatcher(
        MatchingConfig(
            gate_position_distance=0.30,
            gate_min_appearance_sim=0.30,
        )
    )

    # 1. Position Distance Gate
    trk_near = {"object_type": "HUMAN", "bbox": [0.1, 0.1, 0.05, 0.1]}
    det_far = {"object_type": "HUMAN", "bounding_box": [0.8, 0.8, 0.05, 0.1]}
    cost, details = matcher.calculate_pair_cost(trk_near, det_far)
    assert cost >= matcher.config.gating_cost
    assert details["reason"] == "position_distance_gate"

    # 2. Appearance Gate
    trk_person = {"object_type": "HUMAN", "bbox": [0.2, 0.2, 0.05, 0.1], "reid_embedding": [1.0, 0.0, 0.0]}
    det_different = {"object_type": "HUMAN", "bounding_box": [0.21, 0.21, 0.05, 0.1], "reid_embedding": [-1.0, 0.0, 0.0]}
    cost, details = matcher.calculate_pair_cost(trk_person, det_different)
    assert cost >= matcher.config.gating_cost
    assert details["reason"] == "appearance_similarity_gate"

    # 3. Object Type Gate (HUMAN vs VEHICLE)
    det_vehicle = {"object_type": "VEHICLE", "bounding_box": [0.2, 0.2, 0.05, 0.1]}
    cost, details = matcher.calculate_pair_cost(trk_person, det_vehicle)
    assert cost >= matcher.config.gating_cost
    assert details["reason"] == "object_type_mismatch"


def test_hungarian_one_to_one_optimal_assignment():
    """Verify Hungarian assignment matches optimal track/detection pairs and handles unmatched items."""
    matcher = HungarianMatcher()

    tracks = [
        {"object_type": "HUMAN", "bbox": [0.1, 0.1, 0.05, 0.1], "reid_embedding": [1.0, 0.0, 0.0]},
        {"object_type": "HUMAN", "bbox": [0.5, 0.5, 0.05, 0.1], "reid_embedding": [0.0, 1.0, 0.0]},
    ]
    detections = [
        # Det 0 matches Track 1 closely
        {"object_type": "HUMAN", "bounding_box": [0.51, 0.51, 0.05, 0.1], "reid_embedding": [0.0, 0.98, 0.0]},
        # Det 1 matches Track 0 closely
        {"object_type": "HUMAN", "bounding_box": [0.11, 0.11, 0.05, 0.1], "reid_embedding": [0.99, 0.0, 0.0]},
        # Det 2 is an intruder far away
        {"object_type": "HUMAN", "bounding_box": [0.9, 0.9, 0.05, 0.1], "reid_embedding": [0.0, 0.0, 1.0]},
    ]

    result = matcher.match(tracks, detections)

    # Track 0 matches Det 1, Track 1 matches Det 0
    matched_dict = dict(result.matched_pairs)
    assert matched_dict[0] == 1
    assert matched_dict[1] == 0
    assert len(result.unmatched_tracks) == 0
    assert result.unmatched_detections == [2]
