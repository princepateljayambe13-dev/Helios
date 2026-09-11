"""AiService orchestrates the HELIOS AI Intelligence Layer behind the API."""
from __future__ import annotations
from typing import Any

from app.ai.client import GeminiClient, OllamaClient
from app.ai.schemas import AIResponse, AiStatus, DayBrief, EventInsight, InvestigationResult


class AiService:
    def __init__(self, helios, settings: Any = None, client: Any = None):
        self.helios = helios
        self.settings = settings if settings is not None else getattr(helios, "settings", None)
        self._client = client
        if client is None and settings is not None:
            model = getattr(settings, "helios_ai_model", "qwen3:4b") or "qwen3:4b"
            if model == "qwen3:4b" or model.lower().startswith("qwen") or model.lower().startswith("ollama"):
                self._client = OllamaClient(
                    base_url=getattr(settings, "ollama_base_url", "http://127.0.0.1:11434"),
                    model=getattr(settings, "ollama_model", "qwen3:4b"),
                    timeout_seconds=getattr(settings, "ollama_timeout_seconds", 60.0),
                    enabled=getattr(settings, "helios_ai_enabled", True),
                    openrouter_api_key=getattr(settings, "openrouter_api_key", ""),
                    openrouter_gemma_api_key=getattr(settings, "openrouter_gemma_api_key", ""),
                    openrouter_model=getattr(settings, "openrouter_model", "nvidia/nemotron-3-super-120b-a12b:free"),
                    openrouter_fallback_model=getattr(settings, "openrouter_fallback_model", "nvidia/nemotron-3.5-lightning:free"),
                    openrouter_base_url=getattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1"),
                    openrouter_timeout_seconds=getattr(settings, "openrouter_timeout_seconds", 30.0),
                    openrouter_reasoning=getattr(settings, "openrouter_reasoning", True),
                    openrouter_reasoning_effort=getattr(settings, "openrouter_reasoning_effort", "low"),
                    openrouter_reasoning_max_tokens=getattr(settings, "openrouter_reasoning_max_tokens", 400),
                )
            else:
                self._client = GeminiClient(
                    api_key=getattr(settings, "gemini_api_key", ""),
                    model=model,
                    enabled=getattr(settings, "helios_ai_enabled", False),
                    timeout_seconds=getattr(settings, "helios_ai_timeout_seconds", 30.0),
                    gemini_timeout_seconds=getattr(settings, "helios_ai_gemini_timeout_seconds", 10.0),
                    openrouter_api_key=getattr(settings, "openrouter_api_key", ""),
                    openrouter_gemma_api_key=getattr(settings, "openrouter_gemma_api_key", ""),
                    openrouter_model=getattr(settings, "openrouter_model", "nvidia/nemotron-3-super-120b-a12b:free"),
                    openrouter_fallback_model=getattr(settings, "openrouter_fallback_model", "nvidia/nemotron-3.5-lightning:free"),
                    openrouter_base_url=getattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1"),
                    openrouter_timeout_seconds=getattr(settings, "openrouter_timeout_seconds", 30.0),
                    openrouter_reasoning=getattr(settings, "openrouter_reasoning", True),
                    openrouter_reasoning_effort=getattr(settings, "openrouter_reasoning_effort", "low"),
                    openrouter_reasoning_max_tokens=getattr(settings, "openrouter_reasoning_max_tokens", 400),
                )

    @property
    def client(self) -> Any:
        return self._client

    def status(self) -> AiStatus:
        if self._client is None:
            return AiStatus(enabled=False, available=False, model=None, provider=None, error="HELIOS_AI_UNAVAILABLE")
        return AiStatus(
            enabled=getattr(self._client, "enabled", False),
            available=getattr(self._client, "available", False),
            model=getattr(self._client, "model", None),
            provider=getattr(self._client, "provider", None),
            error=getattr(self._client, "error", None))

    def _rounds(self) -> int:
        value = getattr(self.settings, "helios_ai_max_tool_rounds", 6) if self.settings is not None else 6
        return value if value and value > 0 else 6

    def ask(self, question: str, history: list[Any] | None = None) -> AIResponse:
        from app.ai.assistant import ask as assistant_ask
        return assistant_ask(self.helios, question, self._client, history=history, max_rounds=self._rounds())

    def ask_stream(self, question: str, history: list[Any] | None = None):
        from app.ai.assistant import ask_stream as assistant_ask_stream
        return assistant_ask_stream(self.helios, question, self._client, history=history)

    def explain(self, event_id: str) -> EventInsight | None:
        from app.ai.narrator import narrate
        return narrate(self.helios, event_id, self._client)

    def get_investigation_client(
        self,
        model: str | None = None,
        fallback_model: str | None = None,
    ) -> Any:
        inv_model = model or getattr(self.settings, "helios_investigation_model", "minimax/minimax-m3")
        fb_model = fallback_model or getattr(self.settings, "helios_investigation_fallback_model", "google/gemma-4-31b-it")
        if self._client is not None and hasattr(self._client, "get_investigation_client"):
            return self._client.get_investigation_client(model=inv_model, fallback_model=fb_model)
        from app.ai.client import OpenRouterClient
        key = getattr(self.settings, "openrouter_gemma_api_key", "") or getattr(self.settings, "openrouter_api_key", "")
        return OpenRouterClient(
            api_key=key,
            gemma_api_key=getattr(self.settings, "openrouter_gemma_api_key", "") or key,
            model=inv_model,
            fallback_model=fb_model,
            base_url=getattr(self.settings, "openrouter_base_url", "https://openrouter.ai/api/v1"),
            timeout_seconds=getattr(self.settings, "openrouter_timeout_seconds", 30.0),
            reasoning_enabled=getattr(self.settings, "openrouter_reasoning", True),
            reasoning_effort=getattr(self.settings, "openrouter_reasoning_effort", "low"),
            reasoning_max_tokens=getattr(self.settings, "openrouter_reasoning_max_tokens", 400),
        )

    def investigate(self, event_id: str, window_hours: int = 6, focus: str | None = None) -> InvestigationResult | None:
        from app.ai.investigator import investigate as run_investigation
        inv_client = self.get_investigation_client()
        return run_investigation(self.helios, event_id, inv_client, window_hours=window_hours, focus=focus)

    def investigate_evidence(self, evidence_id: str, window_hours: int = 6, focus: str | None = None) -> InvestigationResult | None:
        return self.investigate(evidence_id, window_hours=window_hours, focus=focus)

    def investigate_entity(self, entity_id: str, window_hours: int = 6, focus: str | None = None) -> InvestigationResult | None:
        return self.investigate(entity_id, window_hours=window_hours, focus=focus)

    def day_brief(self, date: str | None = None) -> DayBrief:
        from app.ai.day_brief import generate_day_brief
        return generate_day_brief(self.helios, self._client, date=date)