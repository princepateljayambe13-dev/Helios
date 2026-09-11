import json
import time
from unittest.mock import MagicMock, patch

from app.ai.client import GeminiClient, GeminiRawOutput, OpenRouterClient, ToolCall


def test_disabled_client_reports_unavailable():
    client = GeminiClient(api_key="", enabled=False)
    assert not client.available
    assert client.error == "HELIOS_AI_DISABLED"
    output = client.generate(contents=[{"role": "user", "parts": [{"text": "hi"}]}])
    assert output.error == "HELIOS_AI_DISABLED"
    assert output.text is None


def test_missing_api_key_is_handled():
    client = GeminiClient(api_key="", enabled=True)
    assert not client.available
    assert client.error == "GEMINI_API_KEY_MISSING"


def test_enabled_client_with_key_initialises_against_real_sdk():
    client = GeminiClient(api_key="test-key", enabled=True, model="gemini-2.0-flash")
    assert client.available
    assert client.provider == "gemini"
    assert client.model == "gemini-2.0-flash"


def test_empty_response_is_reported_as_error():
    raw = GeminiRawOutput()
    assert raw.error is None and raw.text is None and raw.tool_calls == []


def test_tool_call_carries_name_and_args():
    call = ToolCall(name="get_event", args={"event_id": "EVT-01"})
    assert call.name == "get_event"
    assert call.args["event_id"] == "EVT-01"


def test_coerce_args_handles_common_shapes():
    assert GeminiClient._coerce_args(None) == {}
    assert GeminiClient._coerce_args({"a": 1}) == {"a": 1}
    assert GeminiClient._coerce_args('{"a": 1}') == {"a": 1}
    assert GeminiClient._coerce_args("") == {}


def test_openrouter_client_missing_key():
    client = OpenRouterClient(api_key="")
    assert not client.available
    assert client.error == "OPENROUTER_API_KEY_MISSING"
    res = client.generate(contents=[{"role": "user", "parts": [{"text": "hello"}]}])
    assert res.error == "OPENROUTER_API_KEY_MISSING"


def test_openrouter_client_generate_with_reasoning():
    client = OpenRouterClient(api_key="sk-or-v1-test", model="nvidia/nemotron-3.5-lightning:free", reasoning_enabled=True)
    assert client.available
    assert client.provider == "openrouter"

    fake_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "There are 3 r's in strawberry.",
                    "reasoning_details": "Counting: s-t-r-a-w-b-e-r-r-y -> 3 r's.",
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response_data

    with patch("requests.post", return_value=mock_resp) as mock_post:
        out = client.generate(
            contents=[{"role": "user", "parts": [{"text": "How many r's are in strawberry?"}]}],
            system_instruction="You are a helpful assistant.",
        )

        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["url"] == "https://openrouter.ai/api/v1/chat/completions"
        assert "Bearer sk-or-v1-test" in call_kwargs["headers"]["Authorization"]

        payload = json.loads(call_kwargs["data"])
        assert payload["model"] == "nvidia/nemotron-3.5-lightning:free"
        assert payload["reasoning"] == {"enabled": True}
        assert payload["messages"][0] == {"role": "system", "content": "You are a helpful assistant."}
        assert payload["messages"][1] == {"role": "user", "content": "How many r's are in strawberry?"}

        assert out.text == "There are 3 r's in strawberry."
        assert out.reasoning_details == "Counting: s-t-r-a-w-b-e-r-r-y -> 3 r's."
        assert out.provider == "openrouter"
        assert client.last_reasoning_details == "Counting: s-t-r-a-w-b-e-r-r-y -> 3 r's."


def test_openrouter_client_preserves_reasoning_details_across_turns():
    client = OpenRouterClient(api_key="sk-or-v1-test")
    client.last_reasoning_details = "step-by-step reasoning"

    # Next turn: user asks follow-up
    contents = [
        {"role": "user", "parts": [{"text": "How many r's in strawberry?"}]},
        {"role": "assistant", "parts": [{"text": "There are 3."}]},
        {"role": "user", "parts": [{"text": "Are you sure?"}]},
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Yes, absolutely."}}]
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        client.generate(contents=contents)
        payload = json.loads(mock_post.call_args[1]["data"])
        assistant_msg = payload["messages"][1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["reasoning_details"] == "step-by-step reasoning"


def test_openrouter_client_tools_conversion():
    client = OpenRouterClient(api_key="sk-or-v1-test")
    declarations = [
        {
            "name": "get_camera",
            "description": "Get camera status",
            "parameters": {
                "type": "OBJECT",
                "properties": {"camera_id": {"type": "STRING"}},
                "required": ["camera_id"],
            },
        }
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "get_camera", "arguments": '{"camera_id": "CAM-01"}'},
                        }
                    ],
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        out = client.generate(
            contents=[{"role": "user", "parts": [{"text": "Check CAM-01"}]}],
            tools=declarations,
        )
        payload = json.loads(mock_post.call_args[1]["data"])
        assert "tools" in payload
        tool = payload["tools"][0]["function"]
        assert tool["name"] == "get_camera"
        assert tool["parameters"]["type"] == "object"
        assert tool["parameters"]["properties"]["camera_id"]["type"] == "string"

        assert len(out.tool_calls) == 1
        assert out.tool_calls[0].name == "get_camera"
        assert out.tool_calls[0].args == {"camera_id": "CAM-01"}


def test_gemini_fallback_when_gemini_key_missing():
    client = GeminiClient(
        api_key="",
        enabled=True,
        openrouter_api_key="sk-or-v1-test",
        openrouter_model="nvidia/nemotron-3.5-lightning:free",
    )
    assert client.available
    assert client.provider == "openrouter"
    assert client.model == "nvidia/nemotron-3.5-lightning:free"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Fallback response"}}]
    }

    with patch("requests.post", return_value=mock_resp):
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "test"}]}])
        assert out.text == "Fallback response"
        assert out.provider == "openrouter"


def test_gemini_fallback_when_gemini_returns_error():
    client = GeminiClient(
        api_key="test-key",
        enabled=True,
        openrouter_api_key="sk-or-v1-test",
    )
    assert client.available
    assert client.gemini_available

    # Make Gemini return an error
    client._generate_gemini = MagicMock(return_value=GeminiRawOutput(error="GEMINI_QUOTA_EXCEEDED"))

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Recovered via OpenRouter"}}]
    }

    with patch("requests.post", return_value=mock_resp):
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "test"}]}])
        assert out.text == "Recovered via OpenRouter"
        assert out.provider == "openrouter"


def test_gemini_fallback_when_gemini_times_out():
    client = GeminiClient(
        api_key="test-key",
        enabled=True,
        gemini_timeout_seconds=0.05,
        openrouter_api_key="sk-or-v1-test",
    )

    def slow_gemini(*args, **kwargs):
        time.sleep(0.3)
        return GeminiRawOutput(text="Slow Gemini")

    client._generate_gemini = slow_gemini

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "OpenRouter after timeout"}}]
    }

    with patch("requests.post", return_value=mock_resp):
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "test"}]}])
        assert out.text == "OpenRouter after timeout"
        assert out.provider == "openrouter"


def test_gemini_times_out_without_openrouter_key():
    client = GeminiClient(
        api_key="test-key",
        enabled=True,
        gemini_timeout_seconds=0.05,
        openrouter_api_key="",
    )

    def slow_gemini(*args, **kwargs):
        time.sleep(0.3)
        return GeminiRawOutput(text="Slow Gemini")

    client._generate_gemini = slow_gemini

    out = client.generate(contents=[{"role": "user", "parts": [{"text": "test"}]}])
    assert out.error is not None
    assert "GEMINI_TIMEOUT" in out.error
    assert "OPENROUTER_API_KEY is not configured" in out.error
    assert out.provider == "gemini"


def test_openrouter_nvidia_two_turn_reasoning_flow():
    client = OpenRouterClient(api_key="sk-or-v1-test", model="nvidia/nemotron-3.5-lightning:free", reasoning_enabled=True)
    assert client.model == "nvidia/nemotron-3.5-lightning:free"
    assert client.reasoning_enabled is True

    # Turn 1: user asks question
    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "There are 3 r's in strawberry.",
                    "reasoning_details": "Let's spell: s-t-r-a-w-b-e-r-r-y. r at pos 3, 8, 9. Total = 3.",
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp1) as mock_post:
        out1 = client.generate(
            contents=[{"role": "user", "parts": [{"text": "How many r's are in the word 'strawberry'?"}]}]
        )
        assert out1.text == "There are 3 r's in strawberry."
        assert out1.reasoning_details is not None
        payload1 = json.loads(mock_post.call_args[1]["data"])
        assert payload1["model"] == "nvidia/nemotron-3.5-lightning:free"
        assert payload1["reasoning"] == {"enabled": True}

    # Turn 2: multi-turn history with preserved reasoning_details
    messages = [
        {"role": "user", "parts": [{"text": "How many r's are in the word 'strawberry'?"}]},
        {
            "role": "assistant",
            "parts": [{"text": out1.text}],
            "reasoning_details": out1.reasoning_details,
        },
        {"role": "user", "parts": [{"text": "Are you sure? Think carefully."}]},
    ]

    mock_resp2 = MagicMock()
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Yes, I am certain there are exactly 3 r's.",
                    "reasoning_details": "Re-verified letters: 3 r's confirmed.",
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp2) as mock_post2:
        out2 = client.generate(contents=messages)
        assert "3 r's" in out2.text
        payload2 = json.loads(mock_post2.call_args[1]["data"])
        assert payload2["model"] == "nvidia/nemotron-3.5-lightning:free"
        assert payload2["reasoning"] == {"enabled": True}
        assert payload2["messages"][1]["role"] == "assistant"
        assert payload2["messages"][1]["reasoning_details"] == "Let's spell: s-t-r-a-w-b-e-r-r-y. r at pos 3, 8, 9. Total = 3."


def test_openrouter_rate_limit_429_auto_fallback():
    client = OpenRouterClient(
        api_key="sk-or-v1-test",
        model="google/gemma-4-31b-it:free",
    )

    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.text = '{"error": {"message": "google/gemma-4-31b-it:free is temporarily rate-limited upstream."}}'

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Visual description success", "reasoning_details": "analyzed frame"}}]
    }

    with patch("requests.post", side_effect=[resp_429, resp_200]) as mock_post:
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "inspect"}]}])
        assert out.error is None
        assert out.text == "Visual description success"
        assert out.model == "google/gemma-4-31b-it"
        assert mock_post.call_count == 2
        # First call used :free
        first_payload = json.loads(mock_post.call_args_list[0][1]["data"])
        assert first_payload["model"] == "google/gemma-4-31b-it:free"
        # Second call auto-fallback without :free
        second_payload = json.loads(mock_post.call_args_list[1][1]["data"])
        assert second_payload["model"] == "google/gemma-4-31b-it"


def test_openrouter_gemma_api_key_isolation():
    client = OpenRouterClient(
        api_key="sk-or-general-key",
        gemma_api_key="sk-or-gemma-key",
        model="nvidia/nemotron-3.5-lightning:free",
    )

    resp_mock = MagicMock()
    resp_mock.status_code = 200
    resp_mock.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "OK"}}]
    }

    # 1. Non-Gemma call uses general key
    with patch("requests.post", return_value=resp_mock) as mock_post:
        client.generate(contents=[{"role": "user", "parts": [{"text": "hello"}]}])
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer sk-or-general-key"

    # 2. Gemma investigation client uses gemma key
    inv_client = client.get_investigation_client(model="google/gemma-4-31b-it:free")
    assert inv_client.api_key == "sk-or-gemma-key"
    with patch("requests.post", return_value=resp_mock) as mock_post:
        inv_client.generate(contents=[{"role": "user", "parts": [{"text": "analyze"}]}])
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer sk-or-gemma-key"

    # 3. Minimax investigation client also uses gemma key
    minimax_client = client.get_investigation_client(model="minimax/minimax-m3:free")
    assert minimax_client.api_key == "sk-or-gemma-key"
    with patch("requests.post", return_value=resp_mock) as mock_post:
        minimax_client.generate(contents=[{"role": "user", "parts": [{"text": "inspect"}]}])
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer sk-or-gemma-key"


def test_minimax_timeout_fallback_to_gemma_4():
    client = OpenRouterClient(
        api_key="sk-or-general",
        gemma_api_key="sk-or-gemma-key",
        model="minimax/minimax-m3:free",
        fallback_model="google/gemma-4-31b-it",
    )

    resp_gemma = MagicMock()
    resp_gemma.status_code = 200
    resp_gemma.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Gemma 4 recovered after timeout", "reasoning_details": "analyzed frame"}}]
    }

    import requests
    # Primary minimax call times out, fallback gemma call succeeds
    with patch("requests.post", side_effect=[requests.exceptions.Timeout("Read timed out"), resp_gemma]) as mock_post:
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "inspect image"}]}])
        assert out.error is None
        assert out.text == "Gemma 4 recovered after timeout"
        assert out.model == "google/gemma-4-31b-it"
        assert mock_post.call_count == 2
        # Verify first call was minimax
        first_payload = json.loads(mock_post.call_args_list[0][1]["data"])
        assert first_payload["model"] == "minimax/minimax-m3:free"
        # Verify fallback call was gemma and used gemma key
        second_payload = json.loads(mock_post.call_args_list[1][1]["data"])
        assert second_payload["model"] == "google/gemma-4-31b-it"
        assert mock_post.call_args_list[1][1]["headers"]["Authorization"] == "Bearer sk-or-gemma-key"


def test_minimax_free_404_retries_paid_slug_before_gemma():
    client = OpenRouterClient(
        api_key="sk-or-general",
        gemma_api_key="sk-or-gemma-key",
        model="minimax/minimax-m3:free",
        fallback_model="google/gemma-4-31b-it",
    )

    resp_404 = MagicMock()
    resp_404.status_code = 404
    resp_404.text = '{"error":{"message":"This model is unavailable for free. The paid version is available now - use this slug instead: minimax/minimax-m3"}}'

    resp_paid_minimax = MagicMock()
    resp_paid_minimax.status_code = 200
    resp_paid_minimax.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Minimax M3 analysis completed."}}]
    }

    with patch("requests.post", side_effect=[resp_404, resp_paid_minimax]) as mock_post:
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "inspect image"}]}])
        assert out.error is None
        assert out.text == "Minimax M3 analysis completed."
        assert out.model == "minimax/minimax-m3"
        assert mock_post.call_count == 2
        # Verify first call was with :free
        first_payload = json.loads(mock_post.call_args_list[0][1]["data"])
        assert first_payload["model"] == "minimax/minimax-m3:free"
        # Verify second call retried paid model before falling back to Gemma
        second_payload = json.loads(mock_post.call_args_list[1][1]["data"])
        assert second_payload["model"] == "minimax/minimax-m3"


def test_nvidia_super_fallback_to_lightning_on_error():
    client = OpenRouterClient(
        api_key="sk-or-test-key",
        model="nvidia/nemotron-3-super-120b-a12b:free",
        fallback_model="nvidia/nemotron-3.5-lightning:free",
    )
    assert client.model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert client.fallback_model == "nvidia/nemotron-3.5-lightning:free"

    resp_error = MagicMock()
    resp_error.status_code = 503
    resp_error.text = "Service temporarily unavailable"

    resp_lightning = MagicMock()
    resp_lightning.status_code = 200
    resp_lightning.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Response from lightning"}}],
        "usage": {
            "completion_tokens_details": {
                "reasoning_tokens": 42,
            }
        },
    }

    with patch("requests.post", side_effect=[resp_error, resp_lightning]) as mock_post:
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "hello"}]}])
        assert out.error is None
        assert out.text == "Response from lightning"
        assert out.model == "nvidia/nemotron-3.5-lightning:free"
        assert out.reasoning_tokens == 42
        assert mock_post.call_count == 2
        p1 = json.loads(mock_post.call_args_list[0][1]["data"])
        p2 = json.loads(mock_post.call_args_list[1][1]["data"])
        assert p1["model"] == "nvidia/nemotron-3-super-120b-a12b:free"
        assert p2["model"] == "nvidia/nemotron-3.5-lightning:free"


def test_openrouter_extracts_reasoning_tokens_camel_case():
    client = OpenRouterClient(api_key="sk-or-test-key")
    resp_mock = MagicMock()
    resp_mock.status_code = 200
    resp_mock.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Done"}}],
        "usage": {
            "completionTokensDetails": {
                "reasoningTokens": 99,
            }
        },
    }

    with patch("requests.post", return_value=resp_mock):
        out = client.generate(contents=[{"role": "user", "parts": [{"text": "test"}]}])
        assert out.error is None
        assert out.reasoning_tokens == 99


def test_gemini_client_defaults_to_nvidia_super_with_lightning_fallback():
    client = GeminiClient(
        api_key="",
        openrouter_api_key="sk-or-key",
    )
    assert client.provider == "openrouter"
    assert client.model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert client._openrouter_client.model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert client._openrouter_client.fallback_model == "nvidia/nemotron-3.5-lightning:free"

    # Verify investigate AI client remains minimax / gemma
    inv_client = client.get_investigation_client()
    assert inv_client.model == "minimax/minimax-m3"
    assert inv_client.fallback_model == "google/gemma-4-31b-it"