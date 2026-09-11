import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from app.ai.client import GeminiRawOutput
from app.core.config import Settings
from app.database.connection import connect
from app.services.helios_service import HeliosService

def stamp() -> str:
    return datetime.now(UTC).isoformat()


class FakeClient:
    """Duck-typed replacement for GeminiClient used across the AI tests."""

    def __init__(self, outputs=None, model="gemini-fake"):
        self.outputs = list(outputs or [])
        self.calls = []
        self.model = model
        self.enabled = True
        self.provider = "fake"
        self.error = None

    @property
    def available(self):
        return getattr(self, "_available", True)

    @available.setter
    def available(self, val):
        self._available = val

    def generate(self, contents, system_instruction=None, tools=None, temperature=0.2,
                 max_output_tokens=2048, response_json=True):
        self.calls.append({
            "contents": contents,
            "tools": tools,
            "system_instruction": system_instruction,
            "response_json": response_json,
        })
        if self.outputs:
            return self.outputs.pop(0)
        return GeminiRawOutput(text="{}", error=None)


class DisabledClient:
    available = False
    enabled = False
    provider = None
    model = None
    error = "HELIOS_AI_DISABLED"

    def generate(self, *args, **kwargs):
        return GeminiRawOutput(error="HELIOS_AI_DISABLED")


@pytest.fixture
def service(tmp_path):
    helios = HeliosService(
        connect(tmp_path / "helios.db"),
        Settings(database_path=tmp_path / "helios.db", alert_rules=[
            {"rule_id": "camera-offline", "event_type": "CAMERA_OFFLINE", "severity": "MEDIUM"}]))
    for camera in (
        ("CAM-01", "North Perimeter", "RTSP", "rtsp://cam-01", "North", "ONLINE"),
        ("CAM-02", "Vehicle Entrance", "HTTP", "", "Entrance", "OFFLINE"),
        ("CAM-03", "Storage Approach", "HTTP", "http://cam-03", "Storage", "ONLINE"),
    ):
        helios.db.execute(
            "INSERT INTO cameras VALUES (?,?,?,?,?,?,1,?,?)",
            (*camera, stamp(), stamp()))
    helios.db.commit()
    return helios


def make_event(helios, object_type="UAV", camera_id="CAM-01", **extra):
    observation = {
        "camera_id": camera_id,
        "object_type": object_type,
        "confidence": 0.9,
        "bounding_box": [0.1, 0.2, 0.3, 0.4],
        "model_name": "test-model",
        "model_version": "fake",
        "attributes": {"source_track_id": f"fake:{uuid.uuid4().hex[:8]}"},
    }
    observation.update(extra)
    return asyncio.run(helios.ingest(observation))