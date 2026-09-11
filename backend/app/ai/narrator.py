"""Event narrator: generates short factual descriptions from real HELIOS data."""
from __future__ import annotations
from typing import Any

from app.ai.prompts import AI_SYSTEM_PROMPT, narration_prompt
from app.ai.references import (collect_ids, default_actions, parse_json_text,
                               references_from_context, sanitize_actions,
                               sanitize_claims, sanitize_references)
from app.ai.schemas import AiClaim, EventInsight
from app.services.helios_service import item


def build_event_facts(helios, event_id: str) -> dict[str, Any] | None:
    event = item(helios.db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone())
    if not event:
        return None
    track = None
    if event.get("track_id"):
        track = item(helios.db.execute("SELECT * FROM tracks WHERE track_id=?", (event["track_id"],)).fetchone())
    camera = item(helios.db.execute(
        "SELECT camera_id,name,source_type,location,status FROM cameras WHERE camera_id=?",
        (event.get("camera_id", ""),)).fetchone())
    zone = item(helios.db.execute(
        "SELECT zone_id,camera_id,name,zone_type FROM zones WHERE zone_id=?",
        (event.get("zone_id", ""),)).fetchone())
    evidence = [dict(row) for row in helios.db.execute(
        "SELECT evidence_id,event_id,type,timestamp,integrity_hash FROM evidence WHERE event_id=? ORDER BY timestamp",
        (event_id,))]
    related = [dict(row) for row in helios.db.execute(
        "SELECT event_id,event_type,timestamp,camera_id,zone_id,severity,status FROM events "
        "WHERE event_id<>? AND (camera_id=? OR zone_id=? OR object_type=?) ORDER BY timestamp DESC LIMIT 10",
        (event_id, event.get("camera_id", ""), event.get("zone_id", ""), event.get("object_type", "")))]
    return {
        "event": event,
        "track": track,
        "camera": camera,
        "zone": zone,
        "evidence": evidence,
        "related_events": related,
    }


def deterministic_summary(facts: dict[str, Any]) -> str:
    event = facts["event"]
    sentence = (
        f"Event {event['event_id']} ({event['event_type']}) was recorded at {event['timestamp']} "
        f"with severity {event['severity']}, status {event['status']}, and confidence {event['confidence']:.2f}."
    )
    camera = facts.get("camera")
    if camera:
        sentence += f" Camera: {camera['camera_id']} ({camera['name']})."
    zone = facts.get("zone")
    if zone:
        sentence += f" Zone: {zone['zone_id']} ({zone['zone_type']})."
    track = facts.get("track")
    if track:
        sentence += f" Track: {track['track_id']} ({track['object_type']})."
        v_intel = (track.get("attributes") or {}).get("vehicle_intelligence")
        if v_intel:
            c = (v_intel.get("color") or "").title() if v_intel.get("color") and v_intel.get("color") != "unknown" else ""
            t = (v_intel.get("type") or "").title() if v_intel.get("type") and v_intel.get("type") != "unknown" else ""
            lbl = f"{c} {t}".strip() or t or c
            if lbl:
                sentence += f" Vehicle classified as {lbl}."
    if facts.get("evidence"):
        sentence += f" Evidence records: {len(facts['evidence'])}."
    if facts.get("related_events"):
        sentence += f" Related events: {len(facts['related_events'])}."
    return sentence


def deterministic_claims(facts: dict[str, Any]) -> list[AiClaim]:
    claims: list[AiClaim] = []
    event = facts["event"]
    references = references_from_context(facts)
    claims.append(AiClaim(
        statement=(
            f"Event {event['event_id']} is a {event['event_type']} recorded at {event['timestamp']} "
            f"with {event['severity']} severity."
        ),
        basis="event record",
        references=[reference for reference in references if reference.event_id],
    ))
    camera = facts.get("camera")
    if camera:
        claims.append(AiClaim(
            statement=f"Event {event['event_id']} occurred on camera {camera['camera_id']} ({camera['name']}).",
            basis="camera record",
            references=[reference for reference in references if reference.camera_id],
        ))
    zone = facts.get("zone")
    if zone:
        claims.append(AiClaim(
            statement=f"Event {event['event_id']} occurred inside zone {zone['zone_id']} ({zone['zone_type']}).",
            basis="zone record",
            references=[reference for reference in references if reference.zone_id],
        ))
    if facts.get("evidence"):
        claims.append(AiClaim(
            statement=f"Event {event['event_id']} has {len(facts['evidence'])} linked evidence record(s).",
            basis="evidence metadata",
            references=[reference for reference in references if reference.evidence_id],
        ))
    return claims


def narrate(helios, event_id: str, client: Any = None) -> EventInsight | None:
    facts = build_event_facts(helios, event_id)
    if facts is None:
        return None
    allowed = collect_ids(facts)
    summary = deterministic_summary(facts)
    narration = summary
    claims = deterministic_claims(facts)
    ai_used = False
    ai_model: str | None = None

    is_disabled = client is not None and (
        getattr(client, "error", None) == "HELIOS_AI_DISABLED" or not getattr(client, "enabled", True)
    )

    if not is_disabled:
        if client is not None and getattr(client, "available", False):
            try:
                prompt = narration_prompt(__import__("json").dumps(facts))
                output = client.generate(
                    contents=[{"role": "user", "parts": [{"text": prompt}]}],
                    system_instruction=AI_SYSTEM_PROMPT, response_json=True)
                if output.error:
                    narration = f"[Local HELIOS AI]\n\n{summary}"
                    ai_model = "local-helios-ai"
                elif output.text:
                    payload = parse_json_text(output.text)
                    if payload and isinstance(payload.get("narration"), str) and payload["narration"].strip():
                        narration = payload["narration"].strip()
                        ai_used = True
                        ai_model = client.model
                        claims = [AiClaim(**claim) for claim in payload.get("claims", []) if _valid_claim_shape(claim)]
                    else:
                        narration = f"[Local HELIOS AI]\n\n{summary}"
                        ai_model = "local-helios-ai"
                else:
                    narration = f"[Local HELIOS AI]\n\n{summary}"
                    ai_model = "local-helios-ai"
            except Exception:
                narration = f"[Local HELIOS AI]\n\n{summary}"
                ai_model = "local-helios-ai"
        elif client is not None:
            narration = f"[Local HELIOS AI]\n\n{summary}"
            ai_model = "local-helios-ai"

    claims = sanitize_claims(claims, allowed)
    references = sanitize_references(references_from_context(facts), allowed)
    return EventInsight(
        event_id=event_id,
        summary=summary,
        narration=narration,
        ai_used=ai_used,
        ai_model=ai_model,
        claims=claims,
        actions=sanitize_actions(default_actions(facts), allowed),
        references=references,
        facts=facts,
    )


def _valid_claim_shape(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("statement"), str)