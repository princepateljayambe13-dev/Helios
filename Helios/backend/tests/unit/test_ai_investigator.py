import json

from app.ai.client import GeminiRawOutput
from app.ai.investigator import (build_investigation_context, investigate,
                                 deterministic_explanation)
from tests.unit.conftest import FakeClient, make_event, stamp


def test_investigation_gathers_full_context(service):
    result = make_event(service, object_type="UAV")
    context = build_investigation_context(service, result["event_id"])
    assert context.event["event_id"] == result["event_id"]
    assert context.track["track_id"] == result["track_id"]
    assert context.camera["camera_id"] == "CAM-01"
    assert isinstance(context.timeline, list)
    assert isinstance(context.related_events, list)


def test_investigate_deterministic_without_ai(service):
    result = make_event(service, object_type="UAV")
    report = investigate(service, result["event_id"])
    assert report is not None
    assert report.event_id == result["event_id"]
    assert report.explanation
    assert report.ai_used is False
    assert report.context.event["event_id"] == result["event_id"]
    assert any(reference.event_id == result["event_id"] for reference in report.references)
    assert any(action.type == "INVESTIGATE_EVENT" for action in report.actions)


def test_investigate_uses_gemini_explanation(service):
    result = make_event(service, object_type="UAV")
    payload = json.dumps({
        "explanation": "A UAV event on the north perimeter, uncorrelated to other camera activity.",
        "claims": [{"statement": "A UAV event occurred on the north perimeter.", "references": [{"camera_id": "CAM-01"}]}],
        "references": [{"event_id": result["event_id"], "label": "event"}],
    })
    client = FakeClient(outputs=[GeminiRawOutput(text=payload)])
    report = investigate(service, result["event_id"], client)
    assert report.ai_used is True
    assert "north perimeter" in report.explanation
    assert report.context.event["event_id"] == result["event_id"]


def test_investigation_never_sends_storage_references_to_model(service):
    result = make_event(service, object_type="UAV")
    service.db.execute("INSERT INTO evidence (evidence_id,event_id,type,storage_reference,timestamp,created_at) VALUES (?,?,?,?,?,?)",
                       ("EVD-REAL123456", result["event_id"], "IMAGE", "data/evidence/x.jpg", stamp(), stamp()))
    service.db.commit()
    client = FakeClient(outputs=[GeminiRawOutput(text='{"explanation": "ok"}')])
    investigate(service, result["event_id"], client)
    prompt = client.calls[0]["contents"][0]["parts"][0]["text"]
    assert "storage_reference" not in prompt


def test_investigate_missing_event_returns_none(service):
    assert investigate(service, "EVT-NOPE") is None


def test_deterministic_explanation_mentions_event_id(service):
    result = make_event(service, object_type="UAV")
    context = build_investigation_context(service, result["event_id"])
    text = deterministic_explanation(context)
    assert result["event_id"] in text


def test_investigate_fallback_on_model_error(service):
    result = make_event(service, object_type="UAV")
    client = FakeClient(outputs=[GeminiRawOutput(error="TIMEOUT")])
    report = investigate(service, result["event_id"], client)
    assert report.ai_used is False
    assert report.ai_model == "local-helios-ai"
    assert "[Local HELIOS AI]" in report.explanation
    assert result["event_id"] in report.explanation
    assert "Sensor Source:" in report.explanation


def test_investigate_fallback_when_client_unavailable(service):
    result = make_event(service, object_type="UAV")
    client = FakeClient()
    client.available = False
    report = investigate(service, result["event_id"], client)
    assert report.ai_used is False
    assert report.ai_model == "local-helios-ai"
    assert "[Local HELIOS AI]" in report.explanation


def test_investigate_routes_to_minimax_openrouter_when_chat_is_ollama(service):
    from unittest.mock import patch
    from app.ai.service import AiService
    from app.core.config import Settings

    settings = Settings(
        helios_ai_enabled=True,
        helios_ai_model="qwen3:4b",
        openrouter_api_key="sk-or-test-key",
        openrouter_gemma_api_key="sk-or-gemma-test-key",
        helios_investigation_model="minimax/minimax-m3",
        helios_investigation_fallback_model="google/gemma-4-31b-it",
    )
    ai = AiService(service, settings)
    assert ai.client.provider == "ollama"

    inv_client = ai.get_investigation_client()
    assert inv_client.provider == "openrouter"
    assert inv_client.model == "minimax/minimax-m3"
    assert inv_client.fallback_model == "google/gemma-4-31b-it"

    event = make_event(service, object_type="UAV")
    payload = json.dumps({
        "explanation": "Minimax M3 reasoning analysis: Detected UAV hovering in restricted airspace.",
        "claims": [{"statement": "UAV detected in restricted airspace.", "references": []}],
    })

    with patch("app.ai.client.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": payload}}]
        }
        res = ai.investigate(event["event_id"])
        assert res is not None
        assert res.ai_used is True
        assert res.ai_model == "minimax/minimax-m3"
        assert "Minimax M3" in res.explanation
        sent_payload = json.loads(mock_post.call_args[1]["data"])
        assert sent_payload["model"] == "minimax/minimax-m3"