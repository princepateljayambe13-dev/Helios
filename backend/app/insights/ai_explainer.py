"""Local AI Explainer: prompts local Qwen3 4B via Ollama to generate concise, evidence-grounded insight summaries."""
from __future__ import annotations

import json
import logging
from typing import Any

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are HELIOS Surveillance Intelligence AI.
Your job is to explain structured surveillance insights clearly and concisely to human security operators.
RULES:
1. Explain ONLY the facts given in the structured telemetry.
2. NEVER invent observations, times, cameras, zones, tracks, evidence, or measurements.
3. Keep explanation to 2 sentences maximum. Clear, calm, objective.
4. Highlight significant deltas (e.g. normal vs current counts or dwell times).
5. Output valid JSON matching the required schema.
"""

CRITICAL_SYSTEM_PROMPT = """You are HELIOS Surveillance Intelligence AI analyzing a CRITICAL facility surveillance situation.
Your job is to provide an authoritative, evidence-grounded tactical intelligence summary for security operators.
RULES:
1. Explain clearly WHY this situation escalated to CRITICAL status.
2. DETAIL HOW PEOPLE OR OBJECTS WERE MOVING: specifically state whether subjects were WALKING, RUNNING, LOITERING, PACING, or STATIONARY, along with speed (m/s) and direction vectors.
3. DETAIL EVIDENCE SNAPSHOT APPEARANCE & COLORS: explicitly mention the clothing/attire colors, tone, or vehicle colors identified in the evidence crops.
4. Keep the summary high-impact, professional, and within 3 concise sentences.
5. Ground everything strictly in the provided evidence. NEVER fabricate details.
"""


class AiExplainer:
    """Generates concise natural-language explanations from structured telemetry."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:4b",
        timeout_seconds: float = 12.0,
    ):
        self.base_url = (base_url or "http://127.0.0.1:11434").rstrip("/")
        self.model = model or "qwen3:4b"
        self.timeout_seconds = timeout_seconds

    def explain_insight(
        self,
        insight_type: str,
        signals: dict[str, Any],
        baseline: dict[str, Any],
        cameras: list[str],
        zones: list[str],
        evidence_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate structured explanation grounded entirely on provided evidence."""
        # 1. Attempt Ollama Qwen3 4B
        structured_input = {
            "insight_type": insight_type,
            "signals": signals,
            "baseline": baseline,
            "cameras": cameras,
            "zones": zones,
            "evidence_ids": evidence_ids or [],
        }

        if requests is not None:
            try:
                resp = requests.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": (
                                    "Explain this surveillance insight in 2 concise sentences. "
                                    f"Data: {json.dumps(structured_input)}"
                                ),
                            },
                        ],
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 150},
                    },
                    timeout=(1.0, self.timeout_seconds),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw_text = (data.get("message") or {}).get("content", "").strip()
                    # Strip any think tags
                    import re
                    clean_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
                    if clean_text:
                        return {
                            "summary": clean_text,
                            "confidence": 0.92,
                            "reasoning_factors": self._extract_factors(signals, baseline, cameras, zones),
                            "provider": "ollama:qwen3:4b",
                        }
            except Exception as exc:
                logger.debug("Ollama explainer skipped/failed: %s", exc)

        # 2. Resilient Deterministic Fallback (zero dependency on external processes)
        return self._deterministic_fallback(insight_type, signals, baseline, cameras, zones)

    def summarize_critical_insight(
        self,
        insight_type: str,
        signals: dict[str, Any],
        baseline: dict[str, Any],
        cameras: list[str],
        zones: list[str],
        evidence_intel: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate in-depth Qwen model intelligence brief for CRITICAL insights,
        incorporating subject walking/movement telemetry and evidence snapshot colors.
        """
        movement_summary = evidence_intel.get("movement_summary", "Motion activity observed")
        color_summary = evidence_intel.get("color_summary", "Dark / Neutral attire")
        walking_count = evidence_intel.get("walking_count", 0)
        avg_speed = evidence_intel.get("avg_speed", 0.0)
        direction = evidence_intel.get("primary_direction", "In-place")
        primary_color = evidence_intel.get("primary_color_label", "Dark attire")

        structured_payload = {
            "status": "CRITICAL_SITUATION",
            "insight_type": insight_type,
            "cameras": cameras,
            "zones": zones,
            "metrics": {
                "current_people": signals.get("people_count"),
                "people_delta": signals.get("people_delta"),
                "dwell_seconds": signals.get("duration_seconds"),
                "dwell_delta": signals.get("dwell_delta"),
                "activity_delta": signals.get("activity_delta"),
            },
            "baseline": baseline,
            "movement_and_walking_telemetry": {
                "summary": movement_summary,
                "walking_count": walking_count,
                "avg_speed_mps": avg_speed,
                "primary_direction": direction,
                "movement_items": evidence_intel.get("movement_items", [])[:4],
            },
            "evidence_snapshots_and_colors": {
                "color_summary": color_summary,
                "primary_color": primary_color,
                "snapshots_inspected": evidence_intel.get("snapshots", [])[:4],
            },
        }

        # 1. Attempt Ollama Qwen3 4B
        if requests is not None:
            try:
                prompt_content = (
                    "Synthesize this CRITICAL surveillance escalation for security operators. "
                    "In 2 to 3 sentences: state why it is critical, explicitly describe how people/objects were moving "
                    f"(walking speeds, direction, loitering), and state their clothing/attire or vehicle colors from evidence.\n"
                    f"Data: {json.dumps(structured_payload)}"
                )
                resp = requests.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": CRITICAL_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt_content},
                        ],
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 220},
                    },
                    timeout=(1.0, self.timeout_seconds),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw_text = (data.get("message") or {}).get("content", "").strip()
                    import re
                    clean_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
                    if clean_text:
                        factors = [
                            f"Movement: {movement_summary}",
                            f"Attire & Colors: {color_summary}",
                            *self._extract_factors(signals, baseline, cameras, zones),
                        ]
                        return {
                            "summary": clean_text,
                            "movement_summary": movement_summary,
                            "color_summary": color_summary,
                            "reasoning_factors": factors,
                            "confidence": 0.96,
                            "provider": "ollama:qwen3:4b",
                        }
            except Exception as exc:
                logger.debug("Qwen critical summarizer failed/offline: %s", exc)

        # 2. Resilient Deterministic Critical Synthesis (evidence-grounded)
        zone_str = zones[0] if zones else "monitored facility area"
        cam_str = cameras[0] if cameras else "surveillance feed"
        dur = int(signals.get("duration_seconds", 90))
        p_curr = signals.get("people_count", "multiple")

        if insight_type == "DENSITY_CHANGE":
            summary = (
                f"CRITICAL ESCALATION: High-density surge ({p_curr} individuals) in {zone_str} on {cam_str}. "
                f"Movement telemetry records {movement_summary} over {dur}s. "
                f"Evidence snapshots confirm subject(s) with {color_summary.lower()} exceeding safe baseline thresholds."
            )
        elif insight_type == "UNUSUAL_DWELL":
            summary = (
                f"CRITICAL ESCALATION: Sustained unusual loitering ({dur}s) detected in {zone_str} on {cam_str}. "
                f"Subject telemetry: {movement_summary}. "
                f"Evidence snapshot inspection identifies {color_summary.lower()} in restricted proximity."
            )
        else:
            summary = (
                f"CRITICAL ESCALATION in {zone_str} across {cam_str}: {movement_summary}. "
                f"Evidence snapshot analysis confirms subject presence with {color_summary.lower()} requiring immediate security review."
            )

        factors = [
            f"Movement: {movement_summary}",
            f"Attire & Colors: {color_summary}",
            *self._extract_factors(signals, baseline, cameras, zones),
        ]
        return {
            "summary": summary,
            "movement_summary": movement_summary,
            "color_summary": color_summary,
            "reasoning_factors": factors,
            "confidence": 0.92,
            "provider": "helios:qwen_deterministic_fallback",
        }

    def _extract_factors(
        self,
        signals: dict[str, Any],
        baseline: dict[str, Any],
        cameras: list[str],
        zones: list[str],
    ) -> list[str]:
        factors: list[str] = []
        if signals.get("people_delta"):
            factors.append(f"People: {signals['people_delta']}")
        elif signals.get("people_count") is not None:
            norm_p = baseline.get("normal_people", 3)
            factors.append(f"People: {norm_p} → {signals['people_count']}")

        if signals.get("activity_delta"):
            factors.append(f"Activity: {signals['activity_delta']}")
        elif signals.get("activity_score") is not None:
            norm_a = baseline.get("normal_activity", 30)
            factors.append(f"Activity: {norm_a} → {signals['activity_score']}")

        if signals.get("duration_seconds"):
            dur = signals["duration_seconds"]
            factors.append(f"Duration: {int(dur)}s")

        cam_count = len(cameras)
        if cam_count > 1:
            factors.append(f"{cam_count} related camera observations ({' → '.join(cameras[:3])})")
        elif cam_count == 1:
            factors.append(f"Observed on {cameras[0]}")

        return factors

    def _deterministic_fallback(
        self,
        insight_type: str,
        signals: dict[str, Any],
        baseline: dict[str, Any],
        cameras: list[str],
        zones: list[str],
    ) -> dict[str, Any]:
        """High-precision template fallback when local LLM is offline."""
        zone_label = zones[0] if zones else "monitored area"
        cam_label = f"across {len(cameras)} cameras ({', '.join(cameras[:2])})" if len(cameras) > 1 else (cameras[0] if cameras else "local feed")

        p_curr = signals.get("people_count", "N/A")
        p_norm = baseline.get("normal_people", 3)
        act_curr = signals.get("activity_score", "N/A")
        act_norm = baseline.get("normal_activity", 30)
        dur = signals.get("duration_seconds", 60)

        if insight_type == "ACTIVITY_CHANGE":
            summary = (
                f"Significant activity change detected in {zone_label}. "
                f"Activity index rose from {act_norm} to {act_curr} and remained elevated across {cam_label}."
            )
        elif insight_type == "DENSITY_CHANGE":
            summary = (
                f"Occupancy surge in {zone_label}: count increased from {p_norm} to {p_curr} individuals. "
                f"Sustained presence recorded for {int(dur)}s on {cam_label}."
            )
        elif insight_type == "UNUSUAL_DWELL":
            summary = (
                f"Unusual dwell duration identified in {zone_label}. "
                f"Target remained stationary for {int(dur)}s, exceeding the standard baseline dwell time."
            )
        elif insight_type == "CROSS_CAMERA_PATTERN":
            summary = (
                f"Correlated motion trajectory tracked across multiple cameras ({' → '.join(cameras)}). "
                f"Observation sequence observed in {zone_label} over {int(dur)}s."
            )
        elif insight_type == "BEHAVIOR_CHANGE":
            summary = (
                f"Movement anomaly detected in {zone_label} on {cam_label}. "
                f"Rapid transition observed with abnormal heading and directional velocity."
            )
        else:
            summary = (
                f"Surveillance event pattern recorded in {zone_label} on {cam_label}. "
                f"Metrics show current activity ({act_curr}) exceeding expected baseline ({act_norm})."
            )

        factors = self._extract_factors(signals, baseline, cameras, zones)
        return {
            "summary": summary,
            "confidence": 0.89,
            "reasoning_factors": factors,
            "provider": "helios:deterministic",
        }
