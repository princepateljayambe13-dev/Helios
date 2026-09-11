from types import SimpleNamespace
from app.vision.roboflow_anpr import RoboflowAnprInferenceManager


def test_roboflow_anpr_predictions_normalize_to_license_plate_observations(monkeypatch):
    manager = RoboflowAnprInferenceManager.__new__(RoboflowAnprInferenceManager)
    manager.clients = {
        "license-plate-detector": SimpleNamespace(
            infer=lambda *_args, **_kwargs: {
                "predictions": [{"x": 100, "y": 80, "width": 40, "height": 20, "confidence": 0.88, "class": "license_plate"}]
            }
        )
    }
    image = SimpleNamespace(shape=(200, 200, 3))
    monkeypatch.setitem(__import__("sys").modules, "cv2", SimpleNamespace(imwrite=lambda *_args: True))
    config = {"name": "license-plate-detector", "model_id": "anpr-tdrid/1", "confidence_threshold": 0.5, "version": "1"}

    observations = manager._detect(image, "CAM-01", config)

    assert len(observations) == 1
    assert observations[0]["object_type"] == "LICENSE_PLATE"
    assert observations[0]["confidence"] == 0.88
    assert observations[0]["bounding_box"] == [0.4, 0.35, 0.2, 0.1]
    assert observations[0]["attributes"]["source_class"] == "license_plate"
