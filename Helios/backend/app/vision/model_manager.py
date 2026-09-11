"""Configuration-backed registry for independently deployable vision models."""
from __future__ import annotations

from typing import Any

from app.core.config import Settings


class ModelManager:
    def __init__(self, settings: Settings) -> None:
        self._models = settings.models

    def enabled(self, mode: str | None = None) -> list[dict[str, Any]]:
        return [model for model in self._models if model.get("enabled") and (mode is None or model.get("mode") == mode)]

    def require(self, mode: str) -> dict[str, Any]:
        model = next(iter(self.enabled(mode)), None)
        if not model: raise LookupError(f"No enabled {mode} model is configured")
        return model
