from types import SimpleNamespace
from unittest.mock import MagicMock
from app.vision.roboflow_client import RoboflowHttpClient, LocalFallbackClient


def test_roboflow_http_client_infer_success(tmp_path):
    client = RoboflowHttpClient(api_url="https://test.roboflow.com", api_key="test_key")
    img_path = tmp_path / "test.jpg"
    img_path.write_bytes(b"dummy_image_data")

    mock_resp = SimpleNamespace(status_code=200, json=lambda: {"predictions": [{"x": 10, "y": 20, "width": 5, "height": 5, "confidence": 0.85, "class": "drone"}]})
    client._client.post = MagicMock(return_value=mock_resp)

    res = client.infer(img_path, "uav-model/1")
    assert "predictions" in res
    assert res["predictions"][0]["class"] == "drone"
    client.close()


def test_roboflow_http_client_infer_nonexistent_file(tmp_path):
    client = RoboflowHttpClient(api_url="https://test.roboflow.com", api_key="test_key")
    res = client.infer(tmp_path / "nonexistent.jpg", "uav-model/1")
    assert res == {"predictions": []}
    client.close()


def test_roboflow_http_client_workflow_success(tmp_path):
    client = RoboflowHttpClient(api_url="https://test.roboflow.com", api_key="test_key")
    img_path = tmp_path / "face.jpg"
    img_path.write_bytes(b"dummy_image_data")

    mock_resp = SimpleNamespace(status_code=200, json=lambda: [{"predictions": [{"x": 50, "y": 50, "width": 20, "height": 20, "confidence": 0.95, "class": "face"}]}])
    client._client.post = MagicMock(return_value=mock_resp)

    res = client.run_workflow("workspace", "workflow", {"image": str(img_path)})
    assert isinstance(res, list)
    assert res[0]["predictions"][0]["class"] == "face"
    client.close()


def test_local_fallback_client():
    client = LocalFallbackClient({"name": "test-model"})
    assert client.infer("dummy.jpg", "model/1") == {"predictions": []}
    wf_res = client.run_workflow("workspace", "workflow", {"image": "dummy.jpg"})
    assert isinstance(wf_res, list)
    assert wf_res[0]["model_predictions"]["predictions"] == []
