import json

from app.ai.client import GeminiRawOutput
from app.ai.narrator import deterministic_summary, narrate
from tests.unit.conftest import FakeClient, make_event, stamp


def test_narrate_without_ai_is_deterministic(service):
    result = make_event(service, object_type="UAV")
    insight = narrate(service, result["event_id"])
    assert insight is not None
    assert insight.summary
    assert insight.narration == insight.summary
    assert insight.ai_used is False
    assert insight.event_id == result["event_id"]
    assert insight.facts["event"]["event_type"] == "UAV_DETECTED"


def test_narrate_includes_references_and_actions(service):
    result = make_event(service, object_type="UAV")
    service.db.execute("INSERT INTO evidence (evidence_id,event_id,type,storage_reference,timestamp,created_at) VALUES (?,?,?,?,?,?)",
                       ("EVD-REAL123456", result["event_id"], "IMAGE", "data/evidence/x.jpg", stamp(), stamp()))
    service.db.commit()
    insight = narrate(service, result["event_id"])
    event_ids = {reference.event_id for reference in insight.references}
    evidence_ids = {reference.evidence_id for reference in insight.references}
    action_types = {action.type for action in insight.actions}
    assert result["event_id"] in event_ids
    assert "EVD-REAL123456" in evidence_ids
    assert "INVESTIGATE_EVENT" in action_types
    assert "VIEW_EVIDENCE" in action_types


def test_narrate_with_gemini_uses_model_narration(service):
    result = make_event(service, object_type="UAV")
    narration = json.dumps({
        "narration": "A UAV was detected on CAM-01.",
        "claims": [{"statement": "A UAV was detected.", "references": [{"event_id": result["event_id"]}]}],
        "references": [{"event_id": result["event_id"], "label": "event"}],
    })
    client = FakeClient(outputs=[GeminiRawOutput(text=narration)])
    insight = narrate(service, result["event_id"], client)
    assert insight.ai_used is True
    assert insight.ai_model == "gemini-fake"
    assert insight.narration == "A UAV was detected on CAM-01."
    assert insight.claims[0].references[0].event_id == result["event_id"]


def test_narrate_drops_invented_evidence_references(service):
    result = make_event(service, object_type="UAV")
    service.db.execute("INSERT INTO evidence (evidence_id,event_id,type,storage_reference,timestamp,created_at) VALUES (?,?,?,?,?,?)",
                       ("EVD-REAL123456", result["event_id"], "IMAGE", "data/evidence/x.jpg", stamp(), stamp()))
    service.db.commit()
    narration = json.dumps({
        "narration": "UAV on CAM-01.",
        "claims": [{"statement": "UAV on CAM-01.", "references": [
            {"evidence_id": "EVD-REAL123456"}, {"evidence_id": "EVD-INVENTED1"}]}],
        "references": [],
    })
    client = FakeClient(outputs=[GeminiRawOutput(text=narration)])
    insight = narrate(service, result["event_id"], client)
    references = insight.claims[0].references
    assert len(references) == 1
    assert references[0].evidence_id == "EVD-REAL123456"


def test_narrate_missing_event_returns_none(service):
    assert narrate(service, "EVT-NOPE") is None


def test_deterministic_summary_is_factual(service):
    result = make_event(service, object_type="UAV")
    from app.ai.narrator import build_event_facts
    facts = build_event_facts(service, result["event_id"])
    summary = deterministic_summary(facts)
    assert result["event_id"] in summary
    assert "CAM-01" in summary
    assert result["event_id"] in facts["event"]["event_id"]


def test_narrate_fallback_on_model_error(service):
    result = make_event(service, object_type="UAV")
    client = FakeClient(outputs=[GeminiRawOutput(error="NETWORK_ERROR")])
    insight = narrate(service, result["event_id"], client)
    assert insight.ai_used is False
    assert insight.ai_model == "local-helios-ai"
    assert "[Local HELIOS AI]" in insight.narration
    assert result["event_id"] in insight.narration


def test_narrate_fallback_when_client_unavailable(service):
    result = make_event(service, object_type="UAV")
    client = FakeClient()
    client.available = False
    insight = narrate(service, result["event_id"], client)
    assert insight.ai_used is False
    assert insight.ai_model == "local-helios-ai"
    assert "[Local HELIOS AI]" in insight.narration