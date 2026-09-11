"""API routes for HELIOS Intelligence & Insights Layer."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Body, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Any


router = APIRouter()


def svc(request: Request):
    return request.app.state.helios


class FeedbackInput(BaseModel):
    operator_feedback: str = Field(..., description="CONFIRM, DISMISS, or NOT_SURE")
    camera_id: str | None = None
    notes: str | None = None


class NLInvestigateInput(BaseModel):
    question: str = Field(..., min_length=2, description="Natural language question about surveillance evidence")


@router.get("/insights")
def list_insights(
    priority: str | None = None,
    status: str | None = None,
    type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    request: Request = None,
):
    """Retrieve prioritized insights feed."""
    return {"insights": svc(request).get_insights(priority=priority, status=status, type_=type, limit=limit, offset=offset)}


@router.get("/insights/summary")
def get_insights_summary(request: Request):
    """Retrieve high-level insight counts (Active, Important, Critical, New, Resolved)."""
    return svc(request).get_insights_summary()


@router.get("/insights/what-changed")
def get_what_changed(request: Request):
    """Retrieve 'What Changed' telemetry comparisons (Normal vs Current vs Significance)."""
    return {"changes": svc(request).get_what_changed()}


@router.get("/insights/summaries/rolling")
def get_rolling_summaries(window: str | None = None, request: Request = None):
    """Retrieve precomputed rolling summaries across windows (LIVE, 5MIN, 15MIN, 1HOUR, etc.)."""
    return svc(request).get_rolling_summaries(window=window)


@router.get("/insights/{insight_id}")
def get_insight_detail(insight_id: str, request: Request):
    """Retrieve detailed insight record including signals and reasoning factors."""
    ins = svc(request).get_insight(insight_id)
    if not ins:
        raise HTTPException(404, "insight not found")
    return ins


@router.post("/insights/{insight_id}/feedback")
def record_insight_feedback(
    insight_id: str,
    payload: FeedbackInput,
    request: Request,
):
    """Record operator confirmation, dismissal, or uncertainty for an insight."""
    res = svc(request).record_insight_feedback(
        insight_id=insight_id,
        operator_feedback=payload.operator_feedback,
        camera_id=payload.camera_id,
        notes=payload.notes,
    )
    return res


@router.post("/insights/investigate")
def natural_language_investigate(payload: NLInvestigateInput, request: Request):
    """Execute natural language investigation: filters database in milliseconds, prompts Qwen3 4B, and saves metadata."""
    return svc(request).investigate_nl(payload.question)


@router.post("/insights/investigate/stream")
def natural_language_investigate_stream(payload: NLInvestigateInput, request: Request):
    """Stream natural language investigation response directly to operator."""
    generator = svc(request).investigate_nl_stream(payload.question)
    return StreamingResponse(generator, media_type="text/plain")


@router.get("/observations")
def query_observations(
    camera_id: str | None = None,
    zone_id: str | None = None,
    track_id: str | None = None,
    object_type: str | None = None,
    movement_state: str | None = None,
    direction: str | None = None,
    min_dwell: float | None = None,
    max_dwell: float | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 50,
    offset: int = 0,
    request: Request = None,
):
    """Fast searchable evidence observation index with multi-field filtering."""
    results = svc(request).query_observations(
        camera_id=camera_id,
        zone_id=zone_id,
        track_id=track_id,
        object_type=object_type,
        movement_state=movement_state,
        direction=direction,
        min_dwell=min_dwell,
        max_dwell=max_dwell,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    return {"observations": results, "count": len(results)}


@router.get("/observations/count")
def count_observations(
    camera_id: str | None = None,
    zone_id: str | None = None,
    object_type: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    request: Request = None,
):
    """Fast count of matching observations."""
    return {
        "count": svc(request).count_observations(
            camera_id=camera_id,
            zone_id=zone_id,
            object_type=object_type,
            start_time=start_time,
            end_time=end_time,
        )
    }


# Behavioral Analytics Endpoints
@router.get("/behavioral/events")
def list_behavioral_events(
    camera_id: str | None = None,
    zone_id: str | None = None,
    track_id: str | None = None,
    behavior_type: str | None = None,
    min_score: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    request: Request = None,
):
    """Query logged behavioral events with score and spatial-temporal filters."""
    events = svc(request).get_behavioral_events(
        camera_id=camera_id,
        zone_id=zone_id,
        track_id=track_id,
        behavior_type=behavior_type,
        min_score=min_score,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"events": events, "count": len(events)}


@router.get("/behavioral/events/{behavior_id}")
def get_behavioral_event_detail(behavior_id: str, request: Request = None):
    """Retrieve full detail for a single behavioral event."""
    ev = svc(request).get_behavioral_event(behavior_id)
    if not ev:
        raise HTTPException(404, "behavioral event not found")
    return ev


@router.get("/behavioral/summary")
def get_behavioral_summary(request: Request = None):
    """Retrieve high-level behavioral anomaly counts and metrics."""
    return svc(request).get_behavioral_summary()

