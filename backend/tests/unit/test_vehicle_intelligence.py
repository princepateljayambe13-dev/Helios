import numpy as np
import pytest
from app.vision.vehicle_intelligence import (
    VehicleClassifier,
    VehicleColorClassifier,
    VehicleColorDetector,
    TrackColorStabilizer,
    ClipPipelineManager,
    VehicleIntelligencePipeline,
    VEHICLE_TYPES,
    VEHICLE_COLORS,
    CLIP_MODEL_NAME,
)


def test_vehicle_classifier_defaults_and_availability():
    classifier = VehicleClassifier()
    assert classifier.model_name == CLIP_MODEL_NAME
    assert set(classifier.candidate_labels) == set(VEHICLE_TYPES)

    # When dormant (or pipeline_instance=False), classify returns None gracefully
    dormant = VehicleClassifier(pipeline_instance=False)
    assert dormant.is_available() is False
    res = dormant.classify(np.zeros((50, 50, 3), dtype=np.uint8))
    assert res["type"] is None
    assert res["type_confidence"] is None
    assert res["is_low_confidence"] is False


def test_vehicle_classifier_with_mock_pipeline():
    # Simulate zero-shot pipeline response
    def fake_pipeline(image, candidate_labels, hypothesis_template):
        return [
            {"label": "sedan", "score": 0.842},
            {"label": "SUV", "score": 0.081},
            {"label": "hatchback", "score": 0.045},
            {"label": "taxi", "score": 0.015},
            {"label": "pickup truck", "score": 0.010},
            {"label": "heavy truck", "score": 0.007},
        ]

    classifier = VehicleClassifier(pipeline_instance=fake_pipeline)
    assert classifier.is_available() is True
    res = classifier.classify(np.zeros((60, 60, 3), dtype=np.uint8))
    assert res["type"] == "sedan"
    assert res["type_confidence"] == 0.84
    assert res["is_low_confidence"] is False


def test_vehicle_classifier_low_confidence_handling():
    def low_conf_pipeline(image, candidate_labels, hypothesis_template):
        return [
            {"label": "SUV", "score": 0.22},
            {"label": "sedan", "score": 0.20},
        ]

    classifier = VehicleClassifier(pipeline_instance=low_conf_pipeline, confidence_threshold=0.30)
    res = classifier.classify(np.zeros((60, 60, 3), dtype=np.uint8))
    assert res["type"] == "unknown"
    assert res["type_confidence"] == 0.22
    assert res["is_low_confidence"] is True


def test_vehicle_color_detector():
    detector = VehicleColorDetector()

    # Blue vehicle image: BGR = (200, 50, 20) -> strong blue
    blue_img = np.zeros((100, 100, 3), dtype=np.uint8)
    blue_img[:, :] = (200, 50, 20)
    res_blue = detector.detect_color(blue_img)
    assert res_blue["color"] == "blue"
    assert res_blue["color_confidence"] >= 0.70

    # Red vehicle image: BGR = (20, 20, 220) -> strong red
    red_img = np.zeros((100, 100, 3), dtype=np.uint8)
    red_img[:, :] = (20, 20, 220)
    res_red = detector.detect_color(red_img)
    assert res_red["color"] == "red"
    assert res_red["color_confidence"] >= 0.70

    # White vehicle image: BGR = (245, 245, 245) -> white
    white_img = np.full((100, 100, 3), 245, dtype=np.uint8)
    res_white = detector.detect_color(white_img)
    assert res_white["color"] == "white"
    assert res_white["color_confidence"] >= 0.70

    # Black vehicle image: BGR = (15, 15, 15) -> black
    black_img = np.full((100, 100, 3), 15, dtype=np.uint8)
    res_black = detector.detect_color(black_img)
    assert res_black["color"] == "black"
    assert res_black["color_confidence"] >= 0.70


def test_vehicle_intelligence_pipeline_output_format():
    def mock_clip(image, candidate_labels, hypothesis_template=None):
        # Can serve both type and color classification prompts
        if "sedan" in str(candidate_labels):
            return [{"label": "sedan", "score": 0.84}]
        if "photo of a blue vehicle" in str(candidate_labels) or "blue" in str(candidate_labels):
            return [
                {"label": "a photo of a blue vehicle", "score": 0.91},
                {"label": "a photo of a black vehicle", "score": 0.05},
            ]
        return [{"label": candidate_labels[0], "score": 0.80}]

    classifier = VehicleClassifier(pipeline_instance=mock_clip)
    color_classifier = VehicleColorClassifier(pipeline_instance=mock_clip)
    pipeline = VehicleIntelligencePipeline(classifier=classifier, color_classifier=color_classifier)

    # Frame with a blue car at normalized bbox [0.2, 0.2, 0.4, 0.4]
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    frame[40:120, 40:120] = (220, 40, 20)

    result = pipeline.analyze_vehicle(
        image=frame,
        bounding_box=[0.2, 0.2, 0.4, 0.4],
        vehicle_id="#V-001",
    )

    assert result["vehicle_id"] == "V-001"
    assert result["type"] == "sedan"
    assert result["type_confidence"] == 0.84
    assert result["color"] == "blue"
    assert result["color_confidence"] == 0.91


def test_vehicle_color_classifier_clip_prompts_and_dormant():
    from app.vision.vehicle_intelligence import VehicleColorClassifier, VEHICLE_COLORS

    # 1. Dormant fallback
    dormant = VehicleColorClassifier(pipeline_instance=False)
    assert dormant.is_available() is False
    assert dormant.colors == VEHICLE_COLORS
    assert "a photo of a red vehicle" in dormant.labels
    res_dormant = dormant.classify_color(np.zeros((50, 50, 3), dtype=np.uint8))
    assert res_dormant["color"] is None
    assert res_dormant["color_confidence"] is None

    # 2. Mock CLIP classification
    def mock_clip_color(image, candidate_labels):
        return [
            {"label": "a photo of a red vehicle", "score": 0.88},
            {"label": "a photo of an orange vehicle", "score": 0.07},
            {"label": "a photo of a brown vehicle", "score": 0.03},
        ]

    active = VehicleColorClassifier(pipeline_instance=mock_clip_color)
    res_active = active.classify_color(np.zeros((50, 50, 3), dtype=np.uint8))
    assert res_active["color"] == "red"
    assert res_active["color_confidence"] == 0.88
    assert "red" in res_active["color_scores"]
    assert res_active["color_scores"]["red"] == 0.88


def test_track_color_stabilizer_temporal_smoothing_and_anti_flicker():
    from app.vision.vehicle_intelligence import TrackColorStabilizer

    stabilizer = TrackColorStabilizer(alpha=0.35)
    track_id = "V-TRACK-101"

    # Frame 1: Model sees Blue with high confidence
    obs1 = {"blue": 0.90, "black": 0.05, "white": 0.05}
    col1, conf1 = stabilizer.stabilize_color(track_id, obs1)
    assert col1 == "blue"
    assert conf1 == 0.90

    # Frame 2: Model sees Blue again
    obs2 = {"blue": 0.88, "black": 0.06, "white": 0.06}
    col2, conf2 = stabilizer.stabilize_color(track_id, obs2)
    assert col2 == "blue"

    # Frame 3: A temporary specular glare or reflection momentarily spikes "white" in a single frame
    obs3_glare = {"white": 0.60, "blue": 0.30, "black": 0.10}
    col3, conf3 = stabilizer.stabilize_color(track_id, obs3_glare)
    # The stabilized color MUST NOT flicker to white! Temporal accumulation protects it:
    assert col3 == "blue"

    # Frame 4: Clear Blue frame returns
    obs4 = {"blue": 0.92, "black": 0.04, "white": 0.04}
    col4, conf4 = stabilizer.stabilize_color(track_id, obs4)
    assert col4 == "blue"
    assert conf4 >= 0.70


def test_track_color_stabilizer_zero_lag_inference_throttling():
    from app.vision.vehicle_intelligence import TrackColorStabilizer

    stabilizer = TrackColorStabilizer(min_interval_seconds=0.10, convergence_threshold=0.80)
    track_id = "V-SPEED-202"

    # Initially needs inference
    assert stabilizer.should_run_inference(track_id, current_time=100.0) is True

    # After observation 1
    stabilizer.stabilize_color(track_id, {"red": 0.85, "blue": 0.15}, current_time=100.0)

    # Immediate next frame at 100.03 (30ms later) should NOT run expensive inference (zero-lag cache)
    assert stabilizer.should_run_inference(track_id, current_time=100.03) is False

    # After 120ms, can run inference
    assert stabilizer.should_run_inference(track_id, current_time=100.12) is True


def test_track_color_stabilizer_prune_and_cleanup():
    from app.vision.vehicle_intelligence import TrackColorStabilizer

    stabilizer = TrackColorStabilizer()
    stabilizer.stabilize_color("T-1", {"silver": 0.85})
    stabilizer.stabilize_color("T-2", {"gray": 0.78})

    assert "T-1" in stabilizer._tracks
    assert "T-2" in stabilizer._tracks

    # Remove specific track
    stabilizer.remove_track("T-1")
    assert "T-1" not in stabilizer._tracks

    # Prune inactive
    stabilizer.prune_stale(active_track_ids={"T-3"})
    assert "T-2" not in stabilizer._tracks

