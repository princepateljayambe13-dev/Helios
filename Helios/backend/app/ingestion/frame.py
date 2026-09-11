"""Common frame object passed from ingestion to processing consumers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class Frame:
    camera_id: str
    image: Any
    sequence: int
    captured_at: datetime
    jpeg: bytes | None = None

    @classmethod
    def create(cls, camera_id: str, image: Any, sequence: int, jpeg: bytes | None = None) -> "Frame":
        return cls(camera_id=camera_id, image=image, sequence=sequence, captured_at=datetime.now(UTC), jpeg=jpeg)
