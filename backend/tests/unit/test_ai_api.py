import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.client import GeminiRawOutput, ToolCall
from app.ai.service import AiService
from app.api.routes.ai import build_ai_router
from tests.unit.conftest import DisabledClient, FakeClient, make_event


def build_app(ai):
    app = FastAPI()
    app.state.ai = ai
    app.include_router(build_ai_router(), prefix="/api/v1", tags=["AI"])
    app.include_router(build_ai_router(), prefix="/api", tags=["AI"])
    return app


def test_ai_status_endpoint(service):
    ai = AiService(service, None, client=FakeClient())
    app = build_app(ai)
    with TestClient(app) as test:
        response = test.get("/api/ai/status")
        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["available"] is True
        assert body["provider"] == "fake"


def test_ai_ask_endpoint_contract(service):
    final_json = json.dumps({
        "answer": "CAM-02 is offline right now.",
        "claims": [{"statement": "Camera CAM-02 is offline.", "references": [{"camera_id": "CAM-02"}]}],
        "actions": [{"type": "OPEN_CAMERA", "label": "Open camera", "camera_id": "CAM-02"}],
        "references": [{"camera_id": "CAM-02", "label": "camera"}],
    })
    client = FakeClient(outputs=[
        GeminiRawOutput(tool_calls=[ToolCall(name="get_camera_status", args={})]),
        GeminiRawOutput(text="x"),
        GeminiRawOutput(text=final_json),
    ])
    ai = AiService(service, None, client=client)
    app = build_app(ai)
    with TestClient(app) as test:
        response = test.post("/api/v1/ai/ask", json={"question": "Which cameras are offline?"})
        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == "CAM-02 is offline right now."
        assert body["grounded"] is True
        assert body["actions"][0]["type"] == "OPEN_CAMERA"
        assert body["actions"][0]["camera_id"] == "CAM-02"
        assert body["claims"][0]["references"][0]["camera_id"] == "CAM-02"


def test_ai_ask_at_task_specified_prefix(service):
    client = FakeClient(outputs=[
        GeminiRawOutput(text="gathering"),
        GeminiRawOutput(text='{"answer": "hi"}'),
    ])
    ai = AiService(service, None, client=client)
    app = build_app(ai)
    with TestClient(app) as test:
        response = test.post("/api/ai/ask", json={"question": "hi"})
        assert response.status_code == 200
        assert response.json()["answer"] == "hi"


def test_ai_ask_empty_question_validation(service):
    ai = AiService(service, None, client=FakeClient())
    app = build_app(ai)
    with TestClient(app) as test:
        response = test.post("/api/ai/ask", json={"question": ""})
        assert response.status_code == 422


def test_ai_event_explain_and_investigate_endpoints(service):
    event = make_event(service, object_type="UAV")
    ai = AiService(service, None, client=FakeClient())
    app = build_app(ai)
    with TestClient(app) as test:
        explain = test.get(f"/api/v1/ai/event/{event['event_id']}/explain")
        assert explain.status_code == 200
        body = explain.json()
        assert body["event_id"] == event["event_id"]
        assert body["narration"]
        assert body["ai_used"] is False

        report = test.post(f"/api/v1/ai/event/{event['event_id']}/investigate", json={})
        assert report.status_code == 200
        report_body = report.json()
        assert report_body["event_id"] == event["event_id"]
        assert report_body["explanation"]
        assert report_body["context"]["event"]["event_id"] == event["event_id"]

        not_found = test.get("/api/ai/event/EVT-NOPE/explain")
        assert not_found.status_code == 404


def test_ai_day_brief_endpoint(service):
    make_event(service, object_type="UAV")
    ai = AiService(service, None, client=FakeClient())
    app = build_app(ai)
    with TestClient(app) as test:
        response = test.get("/api/v1/ai/day-brief")
        assert response.status_code == 200
        body = response.json()
        assert body["date"]
        assert body["stats"]["total_events"] >= 1
        assert body["activity_summary"]


def test_ai_disabled_api_returns_graceful_constract(service):
    ai = AiService(service, None, client=DisabledClient())
    app = build_app(ai)
    with TestClient(app) as test:
        status = test.get("/api/v1/ai/status").json()
        assert status["enabled"] is False
        assert status["available"] is False
        ask = test.post("/api/v1/ai/ask", json={"question": "what happened?"})
        assert ask.status_code == 200
        assert ask.json()["ai_enabled"] is False