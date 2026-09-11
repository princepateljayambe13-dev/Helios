from app.ai.references import (collect_ids, event_ref, parse_json_text,
                               references_from_context, sanitize_actions,
                               sanitize_claims, sanitize_references)
from app.ai.schemas import AiAction, AiClaim, Reference


def test_collect_ids_walks_nested_results(service):
    payload = {
        "event": {"event_id": "EVT-1", "camera_id": "CAM-1"},
        "evidence": [{"evidence_id": "EVD-1"}, {"evidence_id": "EVD-2"}],
        "nested": {"track": {"track_id": "#P-1"}},
    }
    ids = collect_ids(payload)
    assert ids == {"EVT-1", "CAM-1", "EVD-1", "EVD-2", "#P-1"}


def test_reference_factories_build_real_ids():
    ref = event_ref("EVT-1", "test")
    assert ref.event_id == "EVT-1"
    assert ref.present_ids() == ["EVT-1"]


def test_sanitize_claims_drops_invented_references():
    allowed = {"EVT-1", "CAM-1"}
    claims = [
        AiClaim(statement="real", references=[Reference(event_id="EVT-1")]),
        AiClaim(statement="invented", references=[Reference(camera_id="CAM-99")]),
        AiClaim(statement="empty"),
    ]
    cleaned = sanitize_claims(claims, allowed)
    assert len(cleaned) == 3
    assert cleaned[0].references[0].event_id == "EVT-1"
    assert cleaned[1].references == []


def test_sanitize_actions_keeps_only_known_ids():
    allowed = {"EVT-1"}
    actions = [
        AiAction(type="OPEN_EVENT", label="x", event_id="EVT-1"),
        AiAction(type="OPEN_CAMERA", label="y", camera_id="CAM-99"),
        AiAction(type="REVIEW_ACTIVITY", label="z"),
    ]
    cleaned = sanitize_actions(actions, allowed)
    assert [action.type for action in cleaned] == ["OPEN_EVENT", "REVIEW_ACTIVITY"]


def test_sanitize_references_filters_invalid():
    allowed = {"EVD-1"}
    references = [Reference(evidence_id="EVD-1"), Reference(evidence_id="EVD-2")]
    cleaned = sanitize_references(references, allowed)
    assert len(cleaned) == 1
    assert cleaned[0].evidence_id == "EVD-1"


def test_references_from_context_covers_all_entities(service):
    context = {
        "event": {"event_id": "EVT-1"},
        "track": {"track_id": "#P-1"},
        "camera": {"camera_id": "CAM-1"},
        "zone": {"zone_id": "ZONE-1"},
        "evidence": [{"evidence_id": "EVD-1", "type": "IMAGE"}],
        "related_events": [{"event_id": "EVT-2"}],
    }
    references = references_from_context(context)
    assert {reference.event_id for reference in references if reference.event_id} == {"EVT-1", "EVT-2"}
    assert {reference.camera_id for reference in references if reference.camera_id} == {"CAM-1"}


def test_parse_json_text_handles_fences_and_noise():
    assert parse_json_text('{"a": 1}') == {"a": 1}
    assert parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_text("Here is the answer: {\"a\": {\"b\": 2}} trailing") == {"a": {"b": 2}}
    assert parse_json_text("not json") is None