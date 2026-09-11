"""Evidence and claim reference factories for the HELIOS AI Intelligence Layer.

Every AI reference is built from real HELIOS rows so that responses stay
traceable to the underlying event/evidence records and never invent IDs.
"""
from __future__ import annotations
import json
from typing import Any, Iterable

from app.ai.schemas import AiAction, AiClaim, Reference

ID_KEYS = {"event_id", "track_id", "camera_id", "zone_id", "evidence_id", "alert_id", "detection_id", "recognition_id", "person_id"}

ACTION_TYPES_ALLOWED = [
    "INVESTIGATE_EVENT", "VIEW_EVIDENCE", "OPEN_EVENT", "OPEN_CAMERA", "OPEN_TRACK",
    "OPEN_TIMELINE", "VIEW_RELATED_EVENTS", "OPEN_ZONE", "REVIEW_ACTIVITY", "OPEN_CAMERA_HEALTH",
    "OPEN_ALERT", "OPEN_FACE_DIRECTORY", "VIEW_FACE_RECOGNITION",
]


def collect_ids(payload: Any, into: set[str] | None = None) -> set[str]:
    """Walk a tool result and collect every known HELIOS id it contains."""
    seen = into if into is not None else set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in ID_KEYS and isinstance(value, str):
                seen.add(value)
            collect_ids(value, seen)
    elif isinstance(payload, (list, tuple)):
        for entry in payload:
            collect_ids(entry, seen)
    return seen


def event_ref(event_id: str, label: str | None = None) -> Reference:
    return Reference(event_id=event_id, label=label)


def track_ref(track_id: str, label: str | None = None) -> Reference:
    return Reference(track_id=track_id, label=label)


def camera_ref(camera_id: str, label: str | None = None) -> Reference:
    return Reference(camera_id=camera_id, label=label)


def zone_ref(zone_id: str, label: str | None = None) -> Reference:
    return Reference(zone_id=zone_id, label=label)


def evidence_ref(evidence_id: str, label: str | None = None) -> Reference:
    return Reference(evidence_id=evidence_id, label=label)


def references_from_context(context: dict[str, Any]) -> list[Reference]:
    references: list[Reference] = []
    event = context.get("event")
    if event and event.get("event_id"):
        references.append(event_ref(event["event_id"], "event"))
    track = context.get("track")
    if track and track.get("track_id"):
        references.append(track_ref(track["track_id"], "track"))
    camera = context.get("camera")
    if camera and camera.get("camera_id"):
        references.append(camera_ref(camera["camera_id"], "camera"))
    zone = context.get("zone")
    if zone and zone.get("zone_id"):
        references.append(zone_ref(zone["zone_id"], "zone"))
    for evidence in context.get("evidence", []) or []:
        if evidence.get("evidence_id"):
            references.append(evidence_ref(evidence["evidence_id"], evidence.get("type", "evidence")))
    for related in context.get("related_events", []) or []:
        if related.get("event_id"):
            references.append(event_ref(related["event_id"], "related event"))
    return references


def default_actions(context: dict[str, Any]) -> list[AiAction]:
    """Deterministic action objects derived from real HELIOS rows."""
    actions: list[AiAction] = []
    event = context.get("event") or {}
    event_id = event.get("event_id")
    if event_id:
        actions.append(AiAction(type="INVESTIGATE_EVENT", label="Investigate", event_id=event_id))
        actions.append(AiAction(type="OPEN_EVENT", label="Open event", event_id=event_id))
        actions.append(AiAction(type="OPEN_TIMELINE", label="Open timeline", event_id=event_id))
        if context.get("related_events"):
            actions.append(AiAction(type="VIEW_RELATED_EVENTS", label="Related events", event_id=event_id))
    if context.get("camera") and context["camera"].get("camera_id"):
        camera_id = context["camera"]["camera_id"]
        actions.append(AiAction(type="OPEN_CAMERA", label="Open camera", camera_id=camera_id))
        actions.append(AiAction(type="OPEN_CAMERA_HEALTH", label="Camera health", camera_id=camera_id))
        actions.append(AiAction(type="REVIEW_ACTIVITY", label="Review activity", camera_id=camera_id))
    if context.get("track") and context["track"].get("track_id"):
        actions.append(AiAction(type="OPEN_TRACK", label="Open track", track_id=context["track"]["track_id"]))
    if context.get("zone") and context["zone"].get("zone_id"):
        actions.append(AiAction(type="OPEN_ZONE", label="Open zone", zone_id=context["zone"]["zone_id"]))
    for evidence in context.get("evidence", []) or []:
        if evidence.get("evidence_id"):
            actions.append(AiAction(type="VIEW_EVIDENCE", label="View evidence", evidence_id=evidence["evidence_id"]))
    return actions


def parse_json_text(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from a (possibly fenced) model response."""
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    for _ in range(2):
        try:
            payload = json.loads(candidate)
            return payload if isinstance(payload, dict) else None
        except Exception:
            pass
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        candidate = candidate[start:end + 1]
    try:
        payload = json.loads(candidate)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def valid_reference(reference: Reference, allowed: set[str]) -> bool:
    present = reference.present_ids()
    if not present:
        return True
    return all(value in allowed for value in present)


def sanitize_claims(claims: Iterable[AiClaim], allowed: set[str]) -> list[AiClaim]:
    """Drop references that point at HELIOS objects we never showed the model."""
    cleaned: list[AiClaim] = []
    for claim in claims:
        if not claim.statement:
            continue
        claim.references = [reference for reference in claim.references if valid_reference(reference, allowed)]
        cleaned.append(claim)
    return cleaned


def sanitize_actions(actions: Iterable[AiAction], allowed: set[str]) -> list[AiAction]:
    cleaned: list[AiAction] = []
    for action in actions:
        present = [value for value in (action.event_id, action.track_id, action.camera_id, action.zone_id, action.evidence_id) if value]
        if present and not all(value in allowed for value in present):
            continue
        cleaned.append(action)
    return cleaned


def sanitize_references(references: Iterable[Reference], allowed: set[str]) -> list[Reference]:
    return [reference for reference in references if valid_reference(reference, allowed)]