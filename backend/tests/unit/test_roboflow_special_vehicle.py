from types import SimpleNamespace
from unittest.mock import MagicMock

from app.vision.roboflow_special_vehicle import RoboflowSpecialVehicleInferenceManager


def test_roboflow_predictions_normalize_to_special_vehicle_observations(monkeypatch):
    manager = RoboflowSpecialVehicleInferenceManager.__new__(RoboflowSpecialVehicleInferenceManager)
    manager.clients = {
        "special-vehicle-detector": SimpleNamespace(
            infer=lambda *_args, **_kwargs: {
                "predictions": [
                    {"x": 80, "y": 70, "width": 40, "height": 20, "confidence": 0.88, "class": "ambulance"}
                ]
            }
        )
    }
    image = SimpleNamespace(shape=(200, 200, 3))
    monkeypatch.setitem(__import__("sys").modules, "cv2", SimpleNamespace(imwrite=lambda *_args: True))
    config = {
        "name": "special-vehicle-detector",
        "model_id": "emergency-vehicles-detection-xockh-af7sr/1",
        "confidence_threshold": 0.5,
        "version": "1",
    }

    observations = manager._detect(image, "CAM-01", config)

    assert len(observations) == 1
    obs = observations[0]
    assert obs["camera_id"] == "CAM-01"
    assert obs["object_type"] == "VEHICLE"
    assert obs["confidence"] == 0.88
    # x1 = 80 - 20 = 60 -> 60/200 = 0.3; y1 = 70 - 10 = 60 -> 60/200 = 0.3; w = 40/200 = 0.2; h = 20/200 = 0.1
    assert obs["bounding_box"] == [0.3, 0.3, 0.2, 0.1]
    assert obs["model_name"] == "special-vehicle-detector"
    assert obs["model_version"] == "1"
    assert obs["attributes"]["source_class"] == "ambulance"
    assert obs["attributes"]["vehicle_type"] == "ambulance"
    assert obs["attributes"]["is_special_vehicle"] is True


def test_roboflow_special_vehicle_confidence_filtering(monkeypatch):
    manager = RoboflowSpecialVehicleInferenceManager.__new__(RoboflowSpecialVehicleInferenceManager)
    manager.clients = {
        "special-vehicle-detector": SimpleNamespace(
            infer=lambda *_args, **_kwargs: {
                "predictions": [
                    {"x": 50, "y": 50, "width": 20, "height": 20, "confidence": 0.25, "class": "fire_truck"},
                    {"x": 50, "y": 50, "width": 20, "height": 20, "confidence": 0.75, "class": "police_car"},
                ]
            }
        )
    }
    image = SimpleNamespace(shape=(100, 100, 3))
    monkeypatch.setitem(__import__("sys").modules, "cv2", SimpleNamespace(imwrite=lambda *_args: True))
    config = {
        "name": "special-vehicle-detector",
        "model_id": "emergency-vehicles-detection-xockh-af7sr/1",
        "confidence_threshold": 0.50,
        "version": "1",
    }

    observations = manager._detect(image, "CAM-02", config)
    assert len(observations) == 1
    assert observations[0]["attributes"]["source_class"] == "police_car"
    assert observations[0]["confidence"] == 0.75


def test_roboflow_special_vehicle_military_model(monkeypatch):
    manager = RoboflowSpecialVehicleInferenceManager.__new__(RoboflowSpecialVehicleInferenceManager)
    manager.clients = {
        "special-vehicle-detector": SimpleNamespace(
            infer=lambda *_args, **_kwargs: {
                "predictions": [
                    {"x": 50, "y": 40, "width": 20, "height": 10, "confidence": 0.92, "class": "tank"}
                ]
            }
        )
    }
    image = SimpleNamespace(shape=(100, 100, 3))
    monkeypatch.setitem(__import__("sys").modules, "cv2", SimpleNamespace(imwrite=lambda *_args: True))
    config = {
        "name": "special-vehicle-detector",
        "model_id": "military-f5tbj/1",
        "confidence_threshold": 0.30,
        "version": "1",
    }

    observations = manager._detect(image, "CAM-01", config)
    assert len(observations) == 1
    assert observations[0]["object_type"] == "VEHICLE"
    assert observations[0]["attributes"]["source_class"] == "tank"
    assert observations[0]["attributes"]["vehicle_type"] == "tank"
    assert observations[0]["attributes"]["is_special_vehicle"] is True


def test_roboflow_special_vehicle_fallback_when_no_client():
    manager = RoboflowSpecialVehicleInferenceManager.__new__(RoboflowSpecialVehicleInferenceManager)
    manager.clients = {}
    image = SimpleNamespace(shape=(100, 100, 3))
    config = {"name": "special-vehicle-detector"}

    observations = manager._detect(image, "CAM-01", config)
    assert observations == []
