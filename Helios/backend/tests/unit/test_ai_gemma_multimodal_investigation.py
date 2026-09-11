import base64
import json
from unittest.mock import MagicMock, patch

from app.ai.client import GeminiClient, GeminiRawOutput, OpenRouterClient
from app.ai.investigator import (
    build_entity_timeline,
    build_evidence_investigation_context,
    build_track_investigation_context,
    investigate,
)
from tests.unit.conftest import FakeClient, make_event, stamp


def test_gemma_two_turn_reasoning_flow():
    """Verify google/gemma-4-31b-it:free two-turn reasoning flow and reasoning_details preservation."""
    client = OpenRouterClient(api_key="sk-or-v1-test", model="google/gemma-4-31b-it:free", reasoning_enabled=True)
    assert client.model == "google/gemma-4-31b-it:free"
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
                    "reasoning_details": "Let's spell: s-t-r-a-w-b-e-r-r-y. r at 3, 8, 9.",
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp1) as mock_post:
        out1 = client.generate(
            contents=[{"role": "user", "content": "How many r's are in the word 'strawberry'?"}]
        )
        assert out1.text == "There are 3 r's in strawberry."
        assert out1.reasoning_details == "Let's spell: s-t-r-a-w-b-e-r-r-y. r at 3, 8, 9."
        payload1 = json.loads(mock_post.call_args[1]["data"])
        assert payload1["model"] == "google/gemma-4-31b-it:free"
        assert payload1["reasoning"] == {"enabled": True}

    # Turn 2: preserved assistant message with reasoning_details
    messages = [
        {"role": "user", "content": "How many r's are in the word 'strawberry'?"},
        {
            "role": "assistant",
            "content": out1.text,
            "reasoning_details": out1.reasoning_details,
        },
        {"role": "user", "content": "Are you sure? Think carefully."},
    ]

    mock_resp2 = MagicMock()
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Yes, I am certain there are exactly 3 r's.",
                    "reasoning_details": "Re-verified: s-t-R-a-w-b-e-R-R-y.",
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp2) as mock_post2:
        out2 = client.generate(contents=messages)
        assert "3 r's" in out2.text
        payload2 = json.loads(mock_post2.call_args[1]["data"])
        assert payload2["model"] == "google/gemma-4-31b-it:free"
        assert payload2["reasoning"] == {"enabled": True}
        assert payload2["messages"][1]["role"] == "assistant"
        assert payload2["messages"][1]["reasoning_details"] == "Let's spell: s-t-r-a-w-b-e-r-r-y. r at 3, 8, 9."


def test_openrouter_multimodal_image_payload_construction():
    """Verify user message with image part is converted to OpenAI vision format."""
    client = OpenRouterClient(api_key="sk-or-v1-test", model="google/gemma-4-31b-it:free")
    fake_img = b"fake_jpeg_image_bytes"
    b64_img = base64.b64encode(fake_img).decode("utf-8")

    contents = [
        {
            "role": "user",
            "parts": [
                {"text": "Analyze this suspect capture"},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}},
            ],
        }
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Subject in dark jacket."}}]
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        out = client.generate(contents=contents)
        assert out.text == "Subject in dark jacket."
        payload = json.loads(mock_post.call_args[1]["data"])
        user_msg = payload["messages"][0]
        assert user_msg["role"] == "user"
        assert isinstance(user_msg["content"], list)
        assert user_msg["content"][0] == {"type": "text", "text": "Analyze this suspect capture"}
        assert user_msg["content"][1]["type"] == "image_url"
        assert user_msg["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_investigate_evidence_by_id_with_image_and_gemma(service, tmp_path):
    """Direct investigation by evidence_id passes image to google/gemma-4-31b-it:free."""
    result = make_event(service, object_type="HUMAN")
    eid = result["event_id"]
    evd_id = "EVD-TEST999"

    # Create dummy image on disk
    img_dir = service.settings.evidence_directory
    img_dir.mkdir(parents=True, exist_ok=True)
    (img_dir / f"{evd_id}.jpg").write_bytes(b"fake_camera_jpeg_capture")

    service.db.execute(
        "INSERT INTO evidence (evidence_id,event_id,type,storage_reference,timestamp,created_at) VALUES (?,?,?,?,?,?)",
        (evd_id, eid, "SNAPSHOT", f"{evd_id}.jpg", stamp(), stamp()),
    )
    service.db.commit()

    ai_json = json.dumps({
        "explanation": "Subject wearing dark clothing approached perimeter.",
        "image_description": "High resolution snapshot showing a single human figure near fence.",
        "claims": [{"statement": "Subject identified at fence.", "references": [{"evidence_id": evd_id}]}],
    })

    # Fake client simulating google/gemma-4-31b-it:free
    client = FakeClient(outputs=[GeminiRawOutput(text=ai_json)])
    client.model = "google/gemma-4-31b-it:free"

    report = investigate(service, evd_id, client)
    assert report is not None
    assert report.target_id == evd_id
    assert report.target_type == "evidence"
    assert report.ai_used is True
    assert report.ai_model == "google/gemma-4-31b-it:free"
    assert "Subject wearing dark clothing" in report.explanation
    assert "High resolution snapshot" in (report.image_description or "")
    assert len(report.entity_timeline) > 0

    # Verify image was passed into the prompt call
    call_parts = client.calls[0]["contents"][0]["parts"]
    assert any("image_url" in p for p in call_parts)


def test_investigate_track_by_id_entity_timeline(service):
    """Direct investigation by track_id follows the entity timeline across database."""
    result = make_event(service, object_type="VEHICLE")
    trk_id = result["track_id"]

    # Insert extra position waypoints
    service.db.execute(
        "INSERT INTO track_positions (track_id, timestamp, bounding_box, confidence) VALUES (?, ?, ?, ?)",
        (trk_id, stamp(), json.dumps([0.1, 0.1, 0.3, 0.3]), 0.95),
    )
    service.db.commit()

    timeline = build_entity_timeline(service, trk_id)
    assert len(timeline) >= 2
    step_types = [t["step_type"] for t in timeline]
    assert "FIRST_SEEN" in step_types
    assert "LAST_SEEN" in step_types

    ai_json = json.dumps({
        "explanation": "Vehicle track followed from entrance to loading bay.",
        "image_description": "",
        "claims": [{"statement": "Vehicle entered site.", "references": [{"track_id": trk_id}]}],
    })

    client = FakeClient(outputs=[GeminiRawOutput(text=ai_json)])
    client.model = "google/gemma-4-31b-it:free"

    report = investigate(service, trk_id, client)
    assert report is not None
    assert report.target_id == trk_id
    assert report.target_type == "track"
    assert report.ai_used is True
    assert "loading bay" in report.explanation
    assert len(report.entity_timeline) >= 2

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.ai.service import AiService
from app.api.routes.ai import build_ai_router


def build_app(ai: AiService) -> FastAPI:
    app = FastAPI()
    app.state.ai = ai
    app.include_router(build_ai_router(), prefix="/api/v1")
    return app


def test_ai_direct_investigation_endpoints(service):
    event = make_event(service, object_type="HUMAN")
    evd_id = "EVD-API-123"
    service.db.execute(
        "INSERT INTO evidence (evidence_id,event_id,type,storage_reference,timestamp,created_at) VALUES (?,?,?,?,?,?)",
        (evd_id, event["event_id"], "SNAPSHOT", f"{evd_id}.jpg", stamp(), stamp()),
    )
    service.db.commit()

    ai = AiService(service, None, client=FakeClient())
    app = build_app(ai)
    with TestClient(app) as test:
        # 1. Investigate evidence endpoint
        res_ev = test.post(f"/api/v1/ai/evidence/{evd_id}/investigate", json={})
        assert res_ev.status_code == 200
        b_ev = res_ev.json()
        assert b_ev["target_id"] == evd_id
        assert b_ev["target_type"] == "evidence"
        assert b_ev["explanation"]

        # 2. Investigate entity / track endpoint
        import urllib.parse
        encoded_track_id = urllib.parse.quote(event['track_id'], safe="")
        res_trk = test.post(f"/api/v1/ai/entity/{encoded_track_id}/investigate", json={})
        assert res_trk.status_code == 200
        b_trk = res_trk.json()
        assert b_trk["target_id"] == event["track_id"]
        assert b_trk["target_type"] == "track"
        assert len(b_trk["entity_timeline"]) > 0

        # Also test via /ai/track/{track_id}/investigate
        res_trk2 = test.post(f"/api/v1/ai/track/{encoded_track_id}/investigate", json={})
        assert res_trk2.status_code == 200

        # 3. Unified investigate endpoint
        res_uni = test.post("/api/v1/ai/investigate", json={"id": evd_id})
        assert res_uni.status_code == 200
        b_uni = res_uni.json()
        assert b_uni["target_id"] == evd_id
