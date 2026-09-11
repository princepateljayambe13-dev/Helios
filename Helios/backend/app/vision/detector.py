"""Interface that keeps HELIOS independent from a specific vision framework."""
from __future__ import annotations

from typing import Any, Protocol

from app.ingestion.frame import Frame


class VisionDetector(Protocol):
    name: str
    version: str

    def detect(self, frame: Frame) -> list[dict[str, Any]]: ...
