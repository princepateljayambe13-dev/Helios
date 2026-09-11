from types import SimpleNamespace

from app.vision.yolo26 import VideoInferenceManager


class FakeNumber:
    def __init__(self, value): self.value = value
    def item(self): return self.value


class FakeCoordinates:
    def __init__(self, values): self.values = values
    def tolist(self): return self.values


class FakeTrackId(FakeNumber): pass


def test_yolo26_normalizes_person_and_vehicle_boxes():
    manager = VideoInferenceManager.__new__(VideoInferenceManager)
    manager._model_config = {"classes": ["HUMAN", "VEHICLE"], "confidence_threshold": .5, "device": "cpu", "name": "human-vehicle-detector", "version": "yolo26s"}
    boxes = [
        SimpleNamespace(cls=FakeNumber(0), conf=FakeNumber(.9), xyxy=[FakeCoordinates([10, 20, 50, 60])], id=FakeTrackId(7)),
        SimpleNamespace(cls=FakeNumber(2), conf=FakeNumber(.8), xyxy=[FakeCoordinates([20, 30, 80, 90])]),
        SimpleNamespace(cls=FakeNumber(16), conf=FakeNumber(.7), xyxy=[FakeCoordinates([0, 0, 10, 10])]),
    ]
    manager._model = SimpleNamespace(predict=lambda *args, **kwargs: [SimpleNamespace(names={0: "person", 2: "car", 16: "dog"}, boxes=boxes)])
    frame = SimpleNamespace(shape=(100, 100, 3))

    observations = manager._detect(frame, "CAM-01")

    assert [(item["object_type"], item["bounding_box"]) for item in observations] == [("HUMAN", [.1, .2, .4, .4]), ("VEHICLE", [.2, .3, .6, .6])]
    assert observations[0]["attributes"]["source_track_id"] == "human-vehicle-detector:7"
