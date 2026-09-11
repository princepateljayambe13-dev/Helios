"""AI Intelligence Layer routes for the HELIOS V1 backend."""
from fastapi import APIRouter, HTTPException, Request

from app.ai.schemas import (AIResponse, AiAskInput, AiInvestigateInput,
                            AiStatus, DayBrief, EventInsight, InvestigationResult)


def build_ai_router() -> APIRouter:
    router = APIRouter()

    def ai(request: Request):
        return request.app.state.ai

    @router.post("/ai/ask", response_model=AIResponse)
    def ai_ask(payload: AiAskInput, request: Request):
        return ai(request).ask(payload.question, history=payload.history)

    @router.post("/ai/ask/stream")
    def ai_ask_stream(payload: AiAskInput, request: Request):
        from fastapi.responses import StreamingResponse
        generator = ai(request).ask_stream(payload.question, history=payload.history)
        return StreamingResponse(generator, media_type="text/plain")

    @router.get("/ai/status", response_model=AiStatus)
    def ai_status(request: Request):
        return ai(request).status()

    @router.get("/ai/event/{event_id}/explain", response_model=EventInsight)
    def ai_explain(event_id: str, request: Request):
        result = ai(request).explain(event_id)
        if result is None:
            raise HTTPException(404, "event not found")
        return result

    @router.post("/ai/event/{event_id}/investigate", response_model=InvestigationResult)
    def ai_investigate(event_id: str, request: Request, payload: AiInvestigateInput | None = None):
        result = ai(request).investigate(
            event_id,
            window_hours=payload.context_window_hours if payload else 6,
            focus=payload.focus if payload else None)
        if result is None:
            raise HTTPException(404, "event not found")
        return result

    @router.post("/ai/evidence/{evidence_id}/investigate", response_model=InvestigationResult)
    def ai_investigate_evidence(evidence_id: str, request: Request, payload: AiInvestigateInput | None = None):
        result = ai(request).investigate(
            evidence_id,
            window_hours=payload.context_window_hours if payload else 6,
            focus=payload.focus if payload else None)
        if result is None:
            raise HTTPException(404, "evidence not found")
        return result

    @router.post("/ai/entity/{entity_id}/investigate", response_model=InvestigationResult)
    def ai_investigate_entity(entity_id: str, request: Request, payload: AiInvestigateInput | None = None):
        result = ai(request).investigate(
            entity_id,
            window_hours=payload.context_window_hours if payload else 6,
            focus=payload.focus if payload else None)
        if result is None:
            raise HTTPException(404, "entity track not found")
        return result

    @router.post("/ai/track/{track_id}/investigate", response_model=InvestigationResult)
    def ai_investigate_track(track_id: str, request: Request, payload: AiInvestigateInput | None = None):
        return ai_investigate_entity(track_id, request, payload)

    @router.post("/ai/investigate", response_model=InvestigationResult)
    def ai_investigate_any(payload: AiInvestigateInput, request: Request):
        target_id = payload.id or payload.target_id
        if not target_id:
            raise HTTPException(400, "target id is required")
        result = ai(request).investigate(
            target_id,
            window_hours=payload.context_window_hours,
            focus=payload.focus)
        if result is None:
            raise HTTPException(404, f"target '{target_id}' not found")
        return result

    @router.get("/ai/day-brief", response_model=DayBrief)
    def ai_day_brief(request: Request, date: str | None = None):
        return ai(request).day_brief(date)

    return router