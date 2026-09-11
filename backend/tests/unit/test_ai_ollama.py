import json
from unittest.mock import MagicMock, patch
import requests

from app.ai.assistant import ask, extract_grounded_entities
from app.ai.client import GeminiRawOutput, OllamaClient
from app.ai.schemas import ChatMessage
from app.ai.service import AiService
from app.core.config import Settings
from tests.unit.conftest import FakeClient, make_event


def test_ollama_client_defaults():
    client = OllamaClient()
    assert client.base_url == "http://127.0.0.1:11434"
    assert client.model == "qwen3:4b"
    assert client.provider == "ollama"
    assert client.available is True


def test_ollama_client_disabled():
    client = OllamaClient(enabled=False)
    assert client.available is False
    assert client.error == "HELIOS_AI_DISABLED"
    out = client.generate(contents=[{"role": "user", "parts": [{"text": "hello"}]}])
    assert out.error == "HELIOS_AI_DISABLED"


def test_ollama_client_message_conversion():
    client = OllamaClient()
    contents = [
        {"role": "user", "parts": [{"text": "Hello"}]},
        {"role": "assistant", "parts": [{"text": "Greetings"}]},
        {"role": "model", "content": "How can I help?"},
        {"role": "user", "content": "Status check"},
    ]
    converted = client._convert_contents(contents, system_instruction="You are HELIOS AI.")
    assert len(converted) == 5
    assert converted[0] == {"role": "system", "content": "You are HELIOS AI."}
    assert converted[1] == {"role": "user", "content": "Hello"}
    assert converted[2] == {"role": "assistant", "content": "Greetings"}
    assert converted[3] == {"role": "assistant", "content": "How can I help?"}
    assert converted[4] == {"role": "user", "content": "Status check"}


def test_ollama_client_generate_success():
    client = OllamaClient()
    fake_data = {
        "model": "qwen3:4b",
        "message": {
            "role": "assistant",
            "content": "CAM-01 is ONLINE. Perimeter is secure.",
            "thinking": "Facility check reveals CAM-01 active.",
        },
        "done": True,
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_data

    with patch("requests.post", return_value=mock_resp) as mock_post:
        out = client.generate(
            contents=[{"role": "user", "parts": [{"text": "Camera check"}]}],
            system_instruction="Security Assistant",
            temperature=0.2,
            max_output_tokens=1024,
        )
        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["url"] == "http://127.0.0.1:11434/api/chat"
        payload = call_kwargs["json"]
        assert payload["model"] == "qwen3:4b"
        assert payload["stream"] is False
        assert payload["options"]["temperature"] == 0.2
        assert payload["options"]["num_predict"] == 1024

        assert out.text == "CAM-01 is ONLINE. Perimeter is secure."
        assert out.reasoning_details == "Facility check reveals CAM-01 active."
        assert out.provider == "ollama"
        assert out.model == "qwen3:4b"


def test_ollama_client_generate_http_error():
    client = OllamaClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Ollama Error"

    with patch("requests.post", return_value=mock_resp):
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "ping"}]}])
        assert out.error is not None
        assert "OLLAMA_HTTP_500" in out.error


def test_ollama_client_generate_connection_failure():
    client = OllamaClient()
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "ping"}]}])
        assert out.error is not None
        assert "OLLAMA_REQUEST_FAILED" in out.error


def test_ollama_client_streaming():
    client = OllamaClient()
    lines = [
        json.dumps({"message": {"content": "Hello"}}).encode("utf-8"),
        json.dumps({"message": {"content": " from"}}).encode("utf-8"),
        json.dumps({"message": {"content": " Qwen3"}}).encode("utf-8"),
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_lines.return_value = lines

    with patch("requests.post", return_value=mock_resp):
        tokens = list(client.stream(contents=[{"role": "user", "parts": [{"text": "hi"}]}]))
        assert tokens == ["Hello", " from", " Qwen3"]


def test_extract_grounded_entities():
    allowed = {"CAM-01", "CAM-02", "ALR-99", "ZONE-NORTH"}
    text = "We observed movement on CAM-01 in ZONE-NORTH triggering alert ALR-99."
    refs, acts = extract_grounded_entities(text, allowed)
    cam_refs = [r.camera_id for r in refs if r.camera_id]
    assert "CAM-01" in cam_refs
    assert any(r.alert_id == "ALR-99" for r in refs)
    assert any(r.zone_id == "ZONE-NORTH" for r in refs)
    assert any(a.type == "OPEN_CAMERA" and a.camera_id == "CAM-01" for a in acts)


def test_assistant_ask_with_ollama_client(service):
    client = OllamaClient()
    fake_data = {
        "model": "qwen3:4b",
        "message": {
            "role": "assistant",
            "content": "All cameras online: CAM-01 and CAM-02 are active.",
            "thinking": "Inspecting cameras from facility snapshot.",
        },
        "done": True,
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_data

    with patch("requests.post", return_value=mock_resp):
        resp = ask(
            service,
            "Are all cameras online?",
            client,
            history=[ChatMessage(role="user", content="Hello")],
        )
        assert resp.ai_enabled is True
        assert resp.ai_model == "qwen3:4b"
        assert "CAM-01" in resp.answer
        assert resp.reasoning_details == "Inspecting cameras from facility snapshot."
        assert any(r.camera_id == "CAM-01" for r in resp.references)


def test_assistant_fallback_to_local_helios_ai_when_ollama_fails(service):
    """Verifies that local HELIOS AI acts as the last line of defense when Ollama fails."""
    client = OllamaClient()
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        resp = ask(service, "What is the camera status?", client)
        assert resp.ai_enabled is True
        assert resp.ai_model == "local-helios-ai"
        assert resp.answer.startswith("[Local HELIOS AI]")
        assert "camera" in resp.answer.lower()


def test_ai_service_initializes_ollama_client_by_default(service):
    settings = Settings(
        helios_ai_enabled=True,
        helios_ai_model="qwen3:4b",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3:4b",
    )
    ai_service = AiService(service, settings=settings)
    assert isinstance(ai_service.client, OllamaClient)
    assert ai_service.client.model == "qwen3:4b"
    assert ai_service.client.provider == "ollama"
    status = ai_service.status()
    assert status.enabled is True
    assert status.model == "qwen3:4b"
    assert status.provider == "ollama"


def test_multi_tier_cloud_super_selected_first():
    """Hierarchy Tier 1: Cloud Super responds first when online."""
    client = OllamaClient(openrouter_api_key="sk-test-key")
    fake_cloud_data = {
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Cloud Super response.",
            }
        }]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_cloud_data

    with patch("requests.post", return_value=mock_resp) as mock_post:
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "status"}]}])
        assert out.text == "Cloud Super response."
        assert out.model == "nvidia/nemotron-3-super-120b-a12b:free"
        assert out.provider == "openrouter"


def test_multi_tier_cloud_light_selected_when_super_fails():
    """Hierarchy Tier 2: Fails over to Cloud Light when Cloud Super errors."""
    client = OllamaClient(openrouter_api_key="sk-test-key")

    mock_fail = MagicMock()
    mock_fail.status_code = 503
    mock_fail.text = "Super unavailable"

    mock_light_ok = MagicMock()
    mock_light_ok.status_code = 200
    mock_light_ok.json.return_value = {
        "model": "nvidia/nemotron-3.5-lightning:free",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Cloud Light response.",
            }
        }]
    }

    with patch("requests.post", side_effect=[mock_fail, mock_light_ok]):
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "status"}]}])
        assert out.text == "Cloud Light response."
        assert out.model == "nvidia/nemotron-3.5-lightning:free"


def test_multi_tier_ollama_selected_when_cloud_unavailable():
    """Hierarchy Tier 3: Fails over to Local Ollama when OpenRouter connection fails (or offline)."""
    client = OllamaClient(openrouter_api_key="sk-test-key")

    mock_ollama_ok = MagicMock()
    mock_ollama_ok.status_code = 200
    mock_ollama_ok.json.return_value = {
        "model": "qwen3:4b",
        "message": {
            "role": "assistant",
            "content": "Local Ollama Qwen3 response.",
        },
        "done": True,
    }

    # Cloud Super fails, Cloud Light fails, local Ollama succeeds
    with patch(
        "requests.post",
        side_effect=[
            requests.exceptions.ConnectionError("No internet"),
            requests.exceptions.ConnectionError("No internet"),
            mock_ollama_ok,
        ],
    ):
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "status"}]}])
        assert out.text == "Local Ollama Qwen3 response."
        assert out.model == "qwen3:4b"
        assert out.provider == "ollama"


def test_multi_tier_local_helios_ai_last_line_of_defense(service):
    """Hierarchy Tier 4: Fails over to Local HELIOS AI when both cloud and local ollama fail."""
    client = OllamaClient(openrouter_api_key="sk-test-key")

    # Cloud fails and Ollama fails
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Offline")):
        resp = ask(service, "What is the facility status?", client)
        assert resp.ai_enabled is True
        assert resp.ai_model == "local-helios-ai"
        assert resp.answer.startswith("[Local HELIOS AI]")


def test_ollama_client_strips_think_tags():
    """Verify that <think>...</think> scratchpad blocks are stripped from user-facing text."""
    client = OllamaClient()
    fake_data = {
        "model": "qwen3:4b",
        "message": {
            "role": "assistant",
            "content": "<think>\nLet's evaluate the 5 recent events.\nOperator asks for count.\n</think>\nThere are 2 events in the last 3 minutes.",
        },
        "done": True,
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_data

    with patch("requests.post", return_value=mock_resp):
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "events count"}]}])
        assert "<think>" not in out.text
        assert "Let's evaluate" not in out.text
        assert out.text == "There are 2 events in the last 3 minutes."


def test_ollama_empty_content_does_not_leak_thinking(service):
    """Verify that if Ollama only provides internal thinking with empty content, it does not leak into user answer."""
    client = OllamaClient()
    fake_data = {
        "model": "qwen3:4b",
        "message": {
            "role": "assistant",
            "content": "",
            "thinking": "We are given the recent events list: 6 events. Wait, the list shows 5 events...",
        },
        "done": True,
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_data

    with patch("requests.post", return_value=mock_resp):
        # OllamaClient.generate directly returns EMPTY_RESPONSE error instead of thinking
        raw = client.generate(contents=[{"role": "user", "parts": [{"text": "how many events"}]}])
        assert raw.error == "EMPTY_RESPONSE"
        assert raw.text is None
        assert raw.reasoning_details is not None

        # And ask() safely falls back to local HELIOS AI rather than showing internal monologue
        resp = ask(service, "how many events in 3mins", client)
        assert resp.ai_model == "local-helios-ai"
        assert "We are given the recent events" not in resp.answer


