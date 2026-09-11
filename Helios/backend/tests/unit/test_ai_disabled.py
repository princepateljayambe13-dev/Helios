import asyncio

from app.ai.service import AiService
from app.core.config import Settings
from tests.unit.conftest import DisabledClient, FakeClient, make_event


def test_disabled_service_status(service):
    ai = AiService(service, Settings(helios_ai_enabled=False), client=DisabledClient())
    status = ai.status()
    assert status.enabled is False
    assert status.available is False
    assert status.error == "HELIOS_AI_DISABLED"


def test_disabled_service_ask_is_graceful(service):
    ai = AiService(service, Settings(helios_ai_enabled=False), client=DisabledClient())
    response = ai.ask("What happened today?")
    assert response.ai_enabled is False
    assert response.error_code == "HELIOS_AI_DISABLED"
    assert not response.claims


def test_disabled_service_explain_investigate_day_brief(service):
    event = make_event(service, object_type="UAV")
    ai = AiService(service, Settings(helios_ai_enabled=False), client=DisabledClient())
    insight = ai.explain(event["event_id"])
    assert insight is not None and insight.ai_used is False and insight.narration
    report = ai.investigate(event["event_id"])
    assert report is not None and report.ai_used is False and report.explanation
    brief = ai.day_brief()
    assert brief.date and not brief.ai_used


def test_ai_enabled_service_status(service):
    ai = AiService(service, Settings(helios_ai_enabled=True), client=FakeClient())
    status = ai.status()
    assert status.enabled is True
    assert status.available is True
    assert status.provider == "fake"


def test_surveillance_pipeline_continues_with_ai_service_attached(service):
    ai = AiService(service, Settings(helios_ai_enabled=False), client=DisabledClient())
    assert ai.status().available is False
    result = make_event(service, object_type="HUMAN")
    assert result["event_id"]
    event = service.db.execute("SELECT * FROM events WHERE event_id=?", (result["event_id"],)).fetchone()
    assert event["event_type"] == "HUMAN_DETECTED"
    assert event["status"] == "OPEN"


def test_camera_alert_flow_works_when_ai_disabled(service):
    ai = AiService(service, Settings(helios_ai_enabled=False), client=DisabledClient())
    asyncio.run(service.camera_status("CAM-02", "OFFLINE"))
    assert service.db.execute("SELECT status FROM alerts").fetchone()[0] == "ACTIVE"
    assert ai.status().available is False