from app.vision.observation import normalized_observation
from app.spatial.geometry import box_center, point_in_polygon

def test_normalized_observation_and_geometry():
    obs = normalized_observation(
        camera_id="CAM-01",
        object_type="HUMAN",
        confidence=0.85,
        xyxy=[100, 100, 300, 400],
        image_width=1000,
        image_height=1000,
        model_name="yolo26s",
        model_version="1.0"
    )
    assert obs["camera_id"] == "CAM-01"
    assert obs["object_type"] == "HUMAN"
    assert obs["confidence"] == 0.85
    assert len(obs["bounding_box"]) == 4

    center = box_center(obs["bounding_box"])
    polygon = [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]]
    assert point_in_polygon(center, polygon) is True
