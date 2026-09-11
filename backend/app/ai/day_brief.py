"""Day Brief: exact HELIOS statistics plus Gemini-written daily synthesis.

HELIOS computes every statistic server-side; Gemini only writes the narrative
synthesis from those numbers and is never asked to calculate them.
"""
from __future__ import annotations
import json
from datetime import UTC, datetime
from typing import Any

from app.ai.prompts import AI_SYSTEM_PROMPT, day_brief_prompt
from app.ai.references import (collect_ids, default_actions, event_ref,
                               parse_json_text, sanitize_actions,
                               sanitize_references)
from app.ai.schemas import DayBrief, Reference
from app.ai.tools import get_daily_statistics


def compute_day_statistics(helios, date: str | None = None) -> dict[str, Any]:
    return get_daily_statistics(helios, date=date)


def deterministic_summary(stats: dict[str, Any]) -> str:
    date = stats.get("date") or datetime.now(UTC).date().isoformat()
    total = stats.get("total_events", 0)
    summary = f"On {date} HELIOS recorded {total} event(s) across {stats.get('cameras_total', 0)} camera(s)."
    if stats.get("events_by_type"):
        top = stats["events_by_type"][0]
        summary += f" Most frequent type: {top['event_type']} ({top['count']})."
    if stats.get("cameras_offline"):
        summary += f" {stats['cameras_offline']} camera(s) are offline."
    if stats.get("virtual_fence_events"):
        summary += f" {len(stats['virtual_fence_events'])} restricted-zone entry event(s) occurred."
    if stats.get("active_alerts"):
        summary += f" {stats['active_alerts']} alert(s) are currently active."
    if stats.get("vehicle_tracks_today"):
        summary += f" {stats['vehicle_tracks_today']} vehicle track(s) were monitored."
    if stats.get("active_threads"):
        summary += f" {stats['active_threads']} activity thread(s) are active."
    if stats.get("faces_detected_today"):
        det_f = stats["faces_detected_today"]
        rec_f = stats.get("faces_recognized_today", 0)
        unclass_f = stats.get("faces_unclassified_today", 0)
        p_names = stats.get("recognized_persons_today", [])
        p_str = f" ({', '.join(p_names[:3])})" if p_names else ""
        summary += f" Biometric sensors recorded {det_f} face sighting(s): {rec_f} recognized{p_str} and {unclass_f} unclassified."
    return summary


def deterministic_evidence_summary(stats: dict[str, Any]) -> str:
    total = stats.get("evidence_total", 0)
    text = f"HELIOS collected {total} evidence record(s) for {stats.get('date')}."
    if stats.get("evidence_by_type"):
        text += " Breakdown: " + ", ".join(
            f"{entry['type']} ({entry['count']})" for entry in stats["evidence_by_type"]) + "."
    return text


def deterministic_assessment(stats: dict[str, Any]) -> str:
    total = stats.get("total_events", 0)
    if not total:
        return "No HELIOS activity to assess for this date."
    high = sum(entry["count"] for entry in stats.get("events_by_severity", []) if entry["severity"] in {"CRITICAL", "HIGH"})
    if high:
        return f"{high} high/critical event(s) require operator attention."
    virtual_fence = stats.get("virtual_fence_events") or []
    if virtual_fence:
        return f"{len(virtual_fence)} restricted-zone entry event(s) were recorded and may require review."
    return "Activity was recorded but no severe pattern was detected."


def references_from_stats(stats: dict[str, Any]) -> list[Reference]:
    references: list[Reference] = []
    for event in stats.get("significant_events", []) or []:
        if event.get("event_id"):
            references.append(event_ref(event["event_id"], "significant event"))
    for event in stats.get("virtual_fence_events", []) or []:
        if event.get("event_id"):
            references.append(event_ref(event["event_id"], "virtual fence event"))
    for camera in stats.get("camera_health", []) or []:
        if camera.get("camera_id"):
            references.append(Reference(camera_id=camera["camera_id"], label="camera"))
    return references


def default_day_brief(stats: dict[str, Any]) -> DayBrief:
    summary = deterministic_summary(stats)
    return DayBrief(
        date=stats.get("date") or datetime.now(UTC).date().isoformat(),
        activity_summary=summary,
        significant_events=stats.get("significant_events", []),
        virtual_fence_events=stats.get("virtual_fence_events", []),
        camera_health=stats.get("camera_health", []),
        evidence_summary=deterministic_evidence_summary(stats),
        activity_patterns=_detect_patterns(stats),
        ai_assessment=deterministic_assessment(stats),
        references=sanitize_references(references_from_stats(stats), collect_ids(stats)),
        actions=sanitize_actions(_day_actions(stats), collect_ids(stats)),
        stats=stats,
        ai_used=False,
        ai_model=None,
    )


def _detect_patterns(stats: dict[str, Any]) -> list[str]:
    patterns: list[str] = []
    for entry in stats.get("hourly_activity", []) or []:
        if int(entry.get("count", 0)) > 0:
            patterns.append(f"{entry['hour']}:00 UTC: {entry['count']} event(s)")
            break
    top_hours = sorted(
        (entry for entry in stats.get("hourly_activity", []) or []),
        key=lambda entry: entry.get("count", 0), reverse=True)[:1]
    for entry in top_hours:
        if int(entry.get("count", 0)) > 0:
            patterns.append(f"Peak activity on {stats.get('date')} was at {entry['hour']}:00 UTC ({entry['count']} event(s)).")
    return patterns


def _day_actions(stats: dict[str, Any]) -> list[Any]:
    actions: list[Any] = []
    for event in stats.get("significant_events", []) or []:
        if event.get("event_id"):
            actions.append({"type": "INVESTIGATE_EVENT", "label": "Investigate", "event_id": event["event_id"]})
        break
    for event in stats.get("virtual_fence_events", []) or []:
        if event.get("event_id"):
            actions.append({"type": "REVIEW_ACTIVITY", "label": "Review activity", "zone_id": event.get("zone_id")})
        break
    if stats.get("cameras_offline"):
        actions.append({"type": "OPEN_CAMERA_HEALTH", "label": "Camera health"})
    if stats.get("evidence_total"):
        actions.append({"type": "VIEW_EVIDENCE", "label": "View evidence"})
    from app.ai.schemas import AiAction
    return [AiAction(**action) for action in actions]


def build_local_day_assessment(stats: dict[str, Any]) -> str:
    header = "[Local HELIOS AI]\n\n24-Hour Tactical Intelligence Assessment:\n"
    total = stats.get("total_events", 0)
    cams_total = stats.get("cameras_total", 0)
    cams_online = stats.get("cameras_online", 0)
    cams_offline = stats.get("cameras_offline", 0)
    alerts = stats.get("active_alerts", 0)
    virtual_fence = stats.get("virtual_fence_events") or []
    high_sev = sum(entry.get("count", 0) for entry in stats.get("events_by_severity", []) if entry.get("severity") in {"CRITICAL", "HIGH"})

    sections: list[str] = []

    # 1. Threat Posture
    if alerts > 0 or high_sev > 0 or len(virtual_fence) > 0:
        sections.append(
            f"• Threat Posture: ELEVATED — {alerts} active alert(s), {len(virtual_fence)} virtual fence breach(es), "
            f"and {high_sev} high/critical incident(s) flagged across the installation."
        )
    elif total > 0:
        sections.append(
            "• Threat Posture: NOMINAL — Facility perimeter is secure. Standard surveillance events logged with zero active alarms or perimeter breaches."
        )
    else:
        sections.append(
            "• Threat Posture: NOMINAL — All sectors quiet. Zero anomalous activity or intrusion attempts detected in this monitoring cycle."
        )

    # 2. Camera Grid Coverage
    if cams_offline > 0:
        sections.append(
            f"• Sensor Grid: DEGRADED — {cams_offline} of {cams_total} camera feed(s) are offline. Check sensor telemetry and network connections to eliminate blindspots."
        )
    else:
        sections.append(
            f"• Sensor Grid: 100% OPERATIONAL — All {cams_total} camera feeds are online and streaming telemetry across assigned security sectors."
        )

    # 3. Perimeter & Intrusion Synthesis
    if virtual_fence:
        zones = ", ".join(sorted({v.get("name") or v.get("zone_id", "Zone") for v in virtual_fence}))
        sections.append(
            f"• Perimeter Integrity: {len(virtual_fence)} restricted-zone breach(es) detected ({zones}). Verify identity and clearance of involved targets."
        )
    else:
        sections.append(
            "• Perimeter Integrity: Virtual fence lines intact. No unauthorized perimeter incursions recorded."
        )

    # 4. Activity Volume
    if total > 0:
        top_types = [f"{e['event_type']} ({e['count']})" for e in (stats.get("events_by_type") or [])[:3]]
        types_str = f" Top categories: {', '.join(top_types)}." if top_types else ""
        sections.append(f"• Activity Volume: {total} event(s) recorded.{types_str}")

    # 4.5 Biometric Facial Telemetry
    faces_det = stats.get("faces_detected_today", 0)
    faces_rec = stats.get("faces_recognized_today", 0)
    faces_unclass = stats.get("faces_unclassified_today", 0)
    p_names = stats.get("recognized_persons_today", [])
    if faces_det > 0:
        p_str = f" ({', '.join(p_names[:3])})" if p_names else ""
        sections.append(
            f"• Biometric Telemetry: {faces_det} face sighting(s) captured today — {faces_rec} verified identity match(es){p_str} and {faces_unclass} unclassified observation(s)."
        )

    # 5. Tactical Directives
    directives: list[str] = []
    if alerts > 0:
        directives.append(f"Triage {alerts} active alert(s) in the Alerts console.")
    if cams_offline > 0:
        directives.append(f"Inspect network status for {cams_offline} offline camera(s).")
    if virtual_fence:
        directives.append("Inspect recorded evidence snapshots for restricted-zone incursions.")
    if not directives:
        directives.append("Maintain standard surveillance watch. All systems nominal.")

    sections.append("• Tactical Directives: " + " ".join(directives))

    return header + "\n".join(sections)


def compact_day_statistics_for_ai(stats: dict[str, Any]) -> dict[str, Any]:
    """Strip bulky raw tracking telemetry, detector attributes, and polygon arrays

    from stats so the LLM prompt is concise, fast (<1,500 chars), and doesn't exhaust token budgets.
    """
    compact = dict(stats)
    if "significant_events" in compact and isinstance(compact["significant_events"], list):
        compact["significant_events"] = [
            {
                "event_id": e.get("event_id"),
                "event_type": e.get("event_type"),
                "camera_id": e.get("camera_id"),
                "severity": e.get("severity"),
                "timestamp": e.get("timestamp"),
                "description": e.get("description"),
            }
            for e in compact["significant_events"][:6]
            if isinstance(e, dict)
        ]
    if "virtual_fence_events" in compact and isinstance(compact["virtual_fence_events"], list):
        compact["virtual_fence_events"] = [
            {
                "event_id": e.get("event_id"),
                "event_type": e.get("event_type"),
                "zone_id": e.get("zone_id"),
                "camera_id": e.get("camera_id"),
                "severity": e.get("severity"),
                "timestamp": e.get("timestamp"),
            }
            for e in compact["virtual_fence_events"][:6]
            if isinstance(e, dict)
        ]
    return compact


def generate_day_brief(helios, client: Any = None, date: str | None = None) -> DayBrief:
    stats = compute_day_statistics(helios, date)
    result = default_day_brief(stats)

    is_disabled = client is not None and (
        getattr(client, "error", None) == "HELIOS_AI_DISABLED" or not getattr(client, "enabled", True)
    )
    if is_disabled:
        return result

    if client is None or not getattr(client, "available", False):
        result.ai_assessment = build_local_day_assessment(stats)
        result.ai_model = "local-helios-ai"
        result.ai_used = False
        return result

    ai_model: str | None = None
    allowed = collect_ids(stats)
    prompt_stats = compact_day_statistics_for_ai(stats)
    try:
        output = client.generate(
            contents=[{"role": "user", "parts": [{"text": day_brief_prompt(stats.get("date"), json.dumps(prompt_stats))}]}],
            system_instruction=AI_SYSTEM_PROMPT, response_json=True)
        if output.error or not output.text:
            result.ai_assessment = build_local_day_assessment(stats)
            result.ai_model = "local-helios-ai"
            result.ai_used = False
        else:
            payload = parse_json_text(output.text)
            if payload:
                if isinstance(payload.get("activity_summary"), str) and payload["activity_summary"].strip():
                    result.activity_summary = payload["activity_summary"].strip()
                if isinstance(payload.get("evidence_summary"), str) and payload["evidence_summary"].strip():
                    result.evidence_summary = payload["evidence_summary"].strip()
                if isinstance(payload.get("ai_assessment"), str) and payload["ai_assessment"].strip():
                    result.ai_assessment = payload["ai_assessment"].strip()
                if isinstance(payload.get("activity_patterns"), list):
                    patterns = [pattern for pattern in payload["activity_patterns"] if isinstance(pattern, str) and pattern.strip()]
                    if patterns:
                        result.activity_patterns = patterns
                ai_model = output.model or client.model
                result.ai_used = True
                result.ai_model = ai_model
            else:
                result.ai_assessment = build_local_day_assessment(stats)
                result.ai_model = "local-helios-ai"
                result.ai_used = False
    except Exception:
        result.ai_assessment = build_local_day_assessment(stats)
        result.ai_model = "local-helios-ai"
        result.ai_used = False

    result.references = sanitize_references(references_from_stats(stats), allowed)
    result.actions = sanitize_actions(result.actions, allowed)
    return result