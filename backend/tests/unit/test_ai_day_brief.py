import json

from app.ai.client import GeminiRawOutput
from app.ai.day_brief import (compute_day_statistics, deterministic_summary,
                              generate_day_brief)
from tests.unit.conftest import FakeClient, make_event


def test_day_brief_disabled_is_deterministic(service):
    brief = generate_day_brief(service, client=None)
    assert brief.date
    assert brief.activity_summary
    assert brief.evidence_summary
    assert brief.ai_used is False
    assert isinstance(brief.stats, dict)


def test_day_brief_stats_are_computed_server_side(service):
    make_event(service, object_type="UAV")
    make_event(service, object_type="UAV")
    brief = generate_day_brief(service, client=None)
    stats = brief.stats
    assert stats["total_events"] >= 2
    by_type = {entry["event_type"]: entry["count"] for entry in stats["events_by_type"]}
    assert by_type.get("UAV_DETECTED", 0) >= 2
    assert brief.ai_assessment


def test_day_brief_references_and_actions_use_real_ids(service):
    event = make_event(service, object_type="UAV")
    brief = generate_day_brief(service, client=None)
    ids = {reference.event_id for reference in brief.references if reference.event_id}
    assert event["event_id"] in ids
    action_types = {action.type for action in brief.actions}
    assert "INVESTIGATE_EVENT" in action_types


def test_day_brief_with_gemini_uses_model_synthesis(service):
    make_event(service, object_type="UAV")
    payload = json.dumps({
        "activity_summary": "A fairly quiet day with some UAV activity.",
        "evidence_summary": "No evidence collected.",
        "activity_patterns": ["Activity concentrated around CAM-01."],
        "ai_assessment": "No severe pattern was detected.",
    })
    client = FakeClient(outputs=[GeminiRawOutput(text=payload)])
    brief = generate_day_brief(service, client)
    assert brief.ai_used is True
    assert "UAV activity" in brief.activity_summary
    assert brief.activity_patterns


def test_day_brief_specific_date(service):
    make_event(service, object_type="UAV")
    brief = generate_day_brief(service, client=None, date="2026-01-01")
    assert brief.date == "2026-01-01"
    assert brief.stats["total_events"] == 0


def test_deterministic_summary_mentions_date(service):
    stats = compute_day_statistics(service, date="2026-01-01")
    summary = deterministic_summary(stats)
    assert "2026-01-01" in summary


def test_day_brief_fallback_on_model_error(service):
    make_event(service, object_type="UAV")
    client = FakeClient(outputs=[GeminiRawOutput(error="OPENROUTER_HTTP_500: Internal Server Error")])
    brief = generate_day_brief(service, client)
    assert brief.ai_used is False
    assert brief.ai_model == "local-helios-ai"
    assert "[Local HELIOS AI]" in brief.ai_assessment
    assert "24-Hour Tactical Intelligence Assessment:" in brief.ai_assessment
    assert "Threat Posture:" in brief.ai_assessment
    assert "Sensor Grid:" in brief.ai_assessment


def test_day_brief_fallback_when_client_unavailable(service):
    make_event(service, object_type="UAV")
    client = FakeClient()
    client.available = False
    brief = generate_day_brief(service, client)
    assert brief.ai_used is False
    assert brief.ai_model == "local-helios-ai"
    assert "[Local HELIOS AI]" in brief.ai_assessment