from types import SimpleNamespace

from app.vision.roboflow_face import RoboflowFaceWorkflowManager


def test_face_workflow_output_normalizes_to_face_observation(monkeypatch):
    manager = RoboflowFaceWorkflowManager.__new__(RoboflowFaceWorkflowManager)
    manager.clients = {"face-detector": SimpleNamespace(run_workflow=lambda **_kwargs: [{"model_predictions":{"predictions":[{"x":50,"y":40,"width":20,"height":10,"confidence":.9,"class":"face"}]}}])}
    monkeypatch.setitem(__import__("sys").modules, "cv2", SimpleNamespace(imwrite=lambda *_args: True))
    config = {"name":"face-detector","workspace_name":"workspace","workflow_id":"workflow","confidence_threshold":.5,"version":"workflow-current"}

    observations = manager._detect(SimpleNamespace(shape=(100, 100, 3)), "CAM-01", config)

    assert observations[0]["object_type"] == "FACE"
    assert observations[0]["bounding_box"] == [.4, .35, .2, .1]


def test_thermal_person_workflow_output_normalizes_to_human_observation(monkeypatch):
    manager = RoboflowFaceWorkflowManager.__new__(RoboflowFaceWorkflowManager)
    manager.clients = {"thermal-person-detector": SimpleNamespace(run_workflow=lambda **_kwargs: [{"model_predictions":{"predictions":[{"x":50,"y":40,"width":20,"height":30,"confidence":.85,"class":"person"}]}}])}
    monkeypatch.setitem(__import__("sys").modules, "cv2", SimpleNamespace(imwrite=lambda *_args: True))
    config = {"name":"thermal-person-detector","workspace_name":"pramukhs-workspace","workflow_id":"general-segmentation-api-2","classes":["HUMAN"],"confidence_threshold":.5,"version":"1","parameters":{"classes":"person"}}

    observations = manager._detect(SimpleNamespace(shape=(100, 100, 3)), "CAM-01", config)

    assert len(observations) == 1
    assert observations[0]["object_type"] == "HUMAN"
    assert observations[0]["confidence"] == .85
    assert observations[0]["attributes"]["source_class"] == "person"
    assert observations[0]["attributes"]["modality"] == "thermal"


def test_fire_smoke_workflow_output_normalizes_to_fire_and_smoke_observations(monkeypatch):
    manager = RoboflowFaceWorkflowManager.__new__(RoboflowFaceWorkflowManager)
    manager.clients = {"fire-smoke-detector": SimpleNamespace(run_workflow=lambda **_kwargs: [{"model_predictions":{"predictions":[
        {"x": 30, "y": 40, "width": 10, "height": 15, "confidence": 0.92, "class": "fire"},
        {"x": 60, "y": 50, "width": 20, "height": 25, "confidence": 0.88, "class": "smoke"}
    ]}}])}
    monkeypatch.setitem(__import__("sys").modules, "cv2", SimpleNamespace(imwrite=lambda *_args: True))
    config = {"name":"fire-smoke-detector","workspace_name":"pramukhs-workspace","workflow_id":"general-segmentation-api-2","classes":["FIRE","SMOKE"],"confidence_threshold":.5,"version":"1","parameters":{"classes":"fire, smoke, Metal, object, 0"}}

    observations = manager._detect(SimpleNamespace(shape=(100, 100, 3)), "CAM-01", config)

    assert len(observations) == 2
    assert observations[0]["object_type"] == "FIRE"
    assert observations[0]["confidence"] == 0.92
    assert observations[0]["attributes"]["source_class"] == "fire"
    assert observations[1]["object_type"] == "SMOKE"
    assert observations[1]["confidence"] == 0.88
    assert observations[1]["attributes"]["source_class"] == "smoke"
