"""HELIOS AI Intelligence Layer.

Gemini is used only for explanation, querying, and summarization. HELIOS data
remains the source of truth; the AI never writes to or changes HELIOS state.
"""
from app.ai.service import AiService

__all__ = ["AiService"]