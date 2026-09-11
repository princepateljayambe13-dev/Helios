import pytest
from pydantic import ValidationError

from app.ai.references import default_actions
from app.ai.schemas import ACTION_TYPES, AiAction


def test_action_types_contract():
    assert ACTION_TYPES == {
        "INVESTIGATE_EVENT", "VIEW_EVIDENCE", "OPEN_EVENT", "OPEN_CAMERA", "OPEN_TRACK",
        "OPEN_TIMELINE", "VIEW_RELATED_EVENTS", "OPEN_ZONE", "REVIEW_ACTIVITY", "OPEN_CAMERA_HEALTH",
    }


def test_example_action_object_is_valid():
    action = AiAction(type="INVESTIGATE_EVENT", label="Investigate", event_id="EVT-123")
    assert action.model_dump() == {
        "type": "INVESTIGATE_EVENT", "label": "Investigate", "event_id": "EVT-123",
        "track_id": None, "camera_id": None, "zone_id": None, "evidence_id": None}


def test_unknown_action_type_rejected():
    with pytest.raises(ValidationError):
        AiAction(type="DROP_DATABASE", label="nope")


def test_default_actions_for_event_context():
    context = {
        "event": {"event_id": "EVT-1"},
        "track": {"track_id": "#P-1"},
        "camera": {"camera_id": "CAM-1"},
        "zone": {"zone_id": "ZONE-1"},
        "evidence": [{"evidence_id": "EVD-1", "type": "IMAGE"}],
        "related_events": [{"event_id": "EVT-2"}],
    }
    actions = default_actions(context)
    types = {action.type for action in actions}
    assert "INVESTIGATE_EVENT" in types
    assert "OPEN_EVENT" in types
    assert "OPEN_TIMELINE" in types
    assert "VIEW_RELATED_EVENTS" in types
    assert "OPEN_CAMERA" in types
    assert "OPEN_CAMERA_HEALTH" in types
    assert "OPEN_TRACK" in types
    assert "OPEN_ZONE" in types
    assert "VIEW_EVIDENCE" in types
    assert "REVIEW_ACTIVITY" in types


def test_default_actions_use_real_ids():
    context = {"event": {"event_id": "EVT-1"}, "camera": {"camera_id": "CAM-1"}}
    actions = default_actions(context)
    by_type = {action.type: action for action in actions}
    assert by_type["OPEN_CAMERA"].camera_id == "CAM-1"
    assert by_type["INVESTIGATE_EVENT"].event_id == "EVT-1"