import json

from app.ai.assistant import ask
from app.ai.client import GeminiRawOutput, ToolCall
from app.ai.schemas import ChatMessage
from tests.unit.conftest import DisabledClient, FakeClient, make_event, stamp


def test_assistant_calls_tools_then_returns_grounded_answer(service):
    final_json = json.dumps({
        "answer": "CAM-02 is offline right now.",
        "claims": [{"statement": "Camera CAM-02 is offline.", "basis": "camera status", "references": [{"camera_id": "CAM-02"}]}],
        "actions": [{"type": "OPEN_CAMERA", "label": "Open camera", "camera_id": "CAM-02"}],
        "references": [{"camera_id": "CAM-02", "label": "camera"}],
    })
    client = FakeClient(outputs=[
        GeminiRawOutput(tool_calls=[ToolCall(name="get_camera_status", args={})]),
        GeminiRawOutput(text="Intermediate gathering."),
        GeminiRawOutput(text=final_json),
    ])

    response = ask(service, "Which cameras are offline?", client)

    assert response.ai_enabled
    assert response.grounded
    assert "CAM-02" in response.answer
    assert response.claims[0].references[0].camera_id == "CAM-02"
    assert response.actions[0].type == "OPEN_CAMERA"
    assert len(client.calls) == 3
    function_round = client.calls[1]["contents"]
    roles = [message["role"] for message in function_round]
    assert "function" in roles


def test_assistant_passes_tool_results_back_to_model(service):
    client = FakeClient(outputs=[
        GeminiRawOutput(tool_calls=[ToolCall(name="get_camera_status", args={})]),
        GeminiRawOutput(text='{"answer": "ok", "references": [{"camera_id": "CAM-02"}]}'),
    ])
    ask(service, "list cameras", client)
    function_messages = [
        message for message in client.calls[1]["contents"] if message["role"] == "function"]
    assert function_messages
    response_part = function_messages[0]["parts"][0]["function_response"]
    assert response_part["name"] == "get_camera_status"
    assert response_part["response"]["result"]["count"] == 3


def test_assistant_disabled_returns_graceful_response(service):
    response = ask(service, "What happened in Zone 3?", DisabledClient())
    assert response.ai_enabled is False
    assert response.error_code == "HELIOS_AI_DISABLED"
    assert response.answer


def test_assistant_unknown_tool_is_handled_safely(service):
    client = FakeClient(outputs=[
        GeminiRawOutput(tool_calls=[ToolCall(name="not_a_tool", args={})]),
        GeminiRawOutput(text='{"answer": "still fine", "references": []}'),
    ])
    response = ask(service, "question", client)
    assert response.answer
    executed = [
        message for message in client.calls[1]["contents"] if message["role"] == "function"]
    assert "unknown tool" in executed[0]["parts"][0]["function_response"]["response"]["result"]["error"]


def test_assistant_invalid_json_is_reported(service):
    client = FakeClient(outputs=[
        GeminiRawOutput(text="gathering"),
        GeminiRawOutput(text="not json at all"),
    ])
    response = ask(service, "question", client)
    assert response.error_code == "INVALID_RESPONSE"
    assert not response.grounded


def test_assistant_sanitizes_invented_ids(service):
    final_json = json.dumps({
        "answer": "CAM-02 is offline.",
        "claims": [{"statement": "CAM-02 is offline.", "references": [{"camera_id": "CAM-02"}, {"camera_id": "CAM-99"}]}],
        "references": [{"camera_id": "CAM-02"}],
    })
    client = FakeClient(outputs=[
        GeminiRawOutput(tool_calls=[ToolCall(name="get_camera_status", args={})]),
        GeminiRawOutput(text='{"answer": "x"}'),
        GeminiRawOutput(text=final_json),
    ])
    response = ask(service, "Which cameras are offline?", client)
    assert response.claims[0].references[0].camera_id == "CAM-02"
    assert len(response.claims[0].references) == 1


def test_assistant_empty_question(service):
    client = FakeClient()
    response = ask(service, "   ", client)
    assert response.error_code == "EMPTY_QUESTION"


def test_assistant_uses_history(service):
    client = FakeClient(outputs=[
        GeminiRawOutput(text='{"answer": "hello"}'),
    ])
    ask(service, "hi", client, history=[ChatMessage(role="user", content="previous")])
    first_call = client.calls[0]["contents"]
    assert first_call[0]["parts"][0]["text"] == "previous"
    assert first_call[1]["parts"][0]["text"] == "hi"


def test_assistant_response_has_reference_to_real_event(service):
    event = make_event(service, object_type="UAV")
    tool_json = json.dumps({"camera_id": "CAM-01", "event_id": event["event_id"]})
    client = FakeClient(outputs=[
        GeminiRawOutput(tool_calls=[ToolCall(name="get_event", args={"event_id": event["event_id"]})]),
        GeminiRawOutput(text="gathering"),
        GeminiRawOutput(text=f'{{"answer": "uav", "references": [{tool_json}]}}'),
    ])
    response = ask(service, "explain the uav event", client)
    ids = {reference.event_id for reference in response.references}
    assert event["event_id"] in ids


def test_assistant_local_answer_when_no_client_or_network(service):
    # When client is None, it should return a local answer with header [Local HELIOS AI]
    response = ask(service, "What is the camera status?", client=None)
    assert response.ai_enabled is True
    assert response.ai_model == "local-helios-ai"
    assert response.answer.startswith("[Local HELIOS AI]")
    assert "camera" in response.answer.lower()
    assert "CAM-01" in response.answer


def test_assistant_local_answer_when_model_fails(service):
    # When model fails with an error, it should automatically fall back to local answer
    failing_client = FakeClient(outputs=[
        GeminiRawOutput(error="NETWORK_ERROR: Connection refused"),
    ])
    response = ask(service, "Summarize today", client=failing_client)
    assert response.ai_enabled is True
    assert response.ai_model == "local-helios-ai"
    assert response.answer.startswith("[Local HELIOS AI]")
    assert "local overview" in response.answer.lower()


def test_assistant_fast_single_pass_when_grounded_json_returned(service):
    """Verify that when a model outputs valid grounded JSON on turn 1, it returns in 1 pass."""
    grounded_json = json.dumps({
        "answer": "All perimeter zones are secure with 2 online cameras.",
        "claims": [{"statement": "2 cameras are currently online.", "basis": "live snapshot", "references": [{"camera_id": "CAM-01"}]}],
        "actions": [{"type": "OPEN_CAMERA", "label": "Feed CAM-01", "camera_id": "CAM-01"}],
        "references": [{"camera_id": "CAM-01"}],
    })
    client = FakeClient(outputs=[
        GeminiRawOutput(text=grounded_json),
    ])
    response = ask(service, "Are the cameras online?", client)
    assert response.ai_enabled is True
    assert response.grounded is True
    assert "perimeter zones" in response.answer
    assert response.claims[0].references[0].camera_id == "CAM-01"
    # Crucial assertion: executed in exactly 1 call without redundant roundtrip
    assert len(client.calls) == 1


def test_assistant_dataset_snapshot_injected_into_prompt(service):
    """Verify that system_instruction includes live facility snapshot."""
    client = FakeClient(outputs=[
        GeminiRawOutput(text='{"answer": "Acknowledged.", "references": [{"camera_id": "CAM-01"}]}'),
    ])
    ask(service, "Facility check", client)
    call_kwargs = client.calls[0]
    sys_inst = call_kwargs.get("system_instruction") or ""
    assert "[LIVE HELIOS FACILITY STATE" in sys_inst
    assert "CAM-01" in sys_inst


def test_assistant_local_intel_handles_alerts_zones_and_plates(service):
    # 1. Alert query
    service.db.execute(
        "INSERT INTO alerts (alert_id, event_id, timestamp, alert_type, severity, status, message, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("ALR-TEST-99", "EVT-FAKE", stamp(), "TRESPASS", "HIGH", "ACTIVE", "Motion inside warehouse", stamp()),
    )
    service.db.commit()
    res_alert = ask(service, "What are the active alerts?", client=None)
    assert "ALR-TEST-99" in res_alert.answer
    assert any(act.type == "INVESTIGATE_EVENT" and act.event_id == "EVT-FAKE" for act in res_alert.actions)
    assert any(ref.alert_id == "ALR-TEST-99" for ref in res_alert.references)

    # 2. Zone query
    service.db.execute(
        "INSERT INTO zones (zone_id, camera_id, name, zone_type, geometry, enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        ("ZONE-WEST", "CAM-01", "West Perimeter", "RESTRICTED", "[[0,0],[1,1]]", stamp(), stamp()),
    )
    service.db.commit()
    res_zone = ask(service, "What zones exist?", client=None)
    assert "West Perimeter" in res_zone.answer
    assert any(act.type == "OPEN_ZONE" for act in res_zone.actions)

    # 3. License plate query
    service.db.execute(
        "INSERT INTO evidence (evidence_id, event_id, type, storage_reference, timestamp, created_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("EVD-PLATE-99", "EVT-FAKE", "PLATE_READ", "ref.jpg", stamp(), stamp(), '{"plate": "DL-01-XY-9999"}'),
    )
    service.db.commit()
    res_plate = ask(service, "Were any license plates scanned?", client=None)
    assert "EVD-PLATE-99" in res_plate.answer
    assert "ANPR" in res_plate.answer