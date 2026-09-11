from types import SimpleNamespace

from app.vision.roboflow_uav import RoboflowUavInferenceManager


def test_roboflow_predictions_normalize_to_uav_observations(monkeypatch, tmp_path):
    manager = RoboflowUavInferenceManager.__new__(RoboflowUavInferenceManager)
    manager.clients = {"uav-detector": SimpleNamespace(infer=lambda *_args, **_kwargs: {"predictions":[{"x":50,"y":40,"width":20,"height":10,"confidence":.9,"class":"drone"}]})}
    image = SimpleNamespace(shape=(100, 100, 3))
    monkeypatch.setitem(__import__("sys").modules, "cv2", SimpleNamespace(imwrite=lambda *_args: True))
    config = {"name":"uav-detector","model_id":"uav-v1djs/3","confidence_threshold":.5,"version":"3"}

    observations = manager._detect(image, "CAM-01", config)

    assert observations == [{"camera_id":"CAM-01","object_type":"UAV","confidence":.9,"bounding_box":[.4,.35,.2,.1],"model_name":"uav-detector","model_version":"3","attributes":{"source_class":"drone"}}]


def test_roboflow_uav_workflow_predictions_normalize_to_uav_observations(monkeypatch):
    manager = RoboflowUavInferenceManager.__new__(RoboflowUavInferenceManager)
    manager.clients = {"uav-detector": SimpleNamespace(run_workflow=lambda **_kwargs: [{"model_predictions":{"predictions":[{"x":50,"y":40,"width":20,"height":10,"confidence":.95,"class":"drone"}]}}])}
    image = SimpleNamespace(shape=(100, 100, 3))
    monkeypatch.setitem(__import__("sys").modules, "cv2", SimpleNamespace(imwrite=lambda *_args: True))
    config = {"name":"uav-detector","workspace_name":"pramukhs-workspace","workflow_id":"general-segmentation-api-2","confidence_threshold":.5,"version":"1","parameters":{"classes":"drone"}}

    observations = manager._detect(image, "CAM-01", config)

    assert len(observations) == 1
    assert observations[0]["object_type"] == "UAV"
    assert observations[0]["confidence"] == .95
    assert observations[0]["bounding_box"] == [.4, .35, .2, .1]
    assert observations[0]["attributes"]["source_class"] == "drone"

