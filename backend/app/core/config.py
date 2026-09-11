"""Typed configuration loader for HELIOS local deployments."""
from __future__ import annotations
from dataclasses import dataclass, field
from os import getenv
from pathlib import Path
from typing import Any
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
for env_path in (ROOT / ".env", ROOT / "backend" / ".env", Path.cwd() / ".env"):
    if env_path.exists():
        load_dotenv(env_path)

def _read(name: str) -> dict[str, Any]:
    path = ROOT / "config" / name
    return yaml.safe_load(path.read_text()) if path.exists() else {}

def _bool(value: str | None, default: bool = False) -> bool:
    if value is None: return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def _float(value: str | None, default: float = 30.0) -> float:
    try: return float(value)
    except (TypeError, ValueError): return default

def _int(value: str | None, default: int = 6) -> int:
    try: return int(value)
    except (TypeError, ValueError): return default

@dataclass
class Settings:
    database_path: Path = ROOT / "data" / "helios.db"
    evidence_directory: Path = ROOT / "data" / "evidence"
    api_prefix: str = "/api/v1"
    track_timeout_seconds: int = 12
    track_buffer_frames: int = 60
    tracker_high_thresh: float = 0.25
    tracker_low_thresh: float = 0.10
    tracker_match_thresh: float = 0.80
    tracker_new_track_thresh: float = 0.25
    reid_enabled: bool = True
    reid_weights_path: str = "models/reid/osnet_x0_25.pt"
    reid_device: str = "auto"
    reid_max_lost_seconds: float = 12.0
    reid_weight_appearance: float = 0.40
    reid_weight_position: float = 0.30
    reid_weight_motion: float = 0.20
    reid_weight_iou: float = 0.10
    reid_recovery_cost_threshold: float = 0.55
    engine_restart_max_attempts: int = 3
    engine_restart_backoff_seconds: float = 2
    cameras: list[dict[str, Any]] = field(default_factory=list)
    zones: list[dict[str, Any]] = field(default_factory=list)
    alert_rules: list[dict[str, Any]] = field(default_factory=list)
    models: list[dict[str, Any]] = field(default_factory=list)
    gemini_api_key: str = ""
    helios_ai_model: str = "gemini-3.5-flash-lite"
    helios_ai_enabled: bool = False
    helios_ai_timeout_seconds: float = 30.0
    helios_ai_gemini_timeout_seconds: float = 10.0
    helios_ai_max_tool_rounds: int = 6
    openrouter_api_key: str = ""
    openrouter_gemma_api_key: str = ""
    openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    openrouter_fallback_model: str = "nvidia/nemotron-3.5-lightning:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 45.0
    openrouter_reasoning: bool = True
    openrouter_reasoning_effort: str | None = "low"
    openrouter_reasoning_max_tokens: int | None = 400
    helios_investigation_model: str = "minimax/minimax-m3"
    helios_investigation_fallback_model: str = "google/gemma-4-31b-it"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: float = 60.0

def load_settings() -> Settings:
    system, storage, cameras, zones, alerts, models = (_read(n) for n in ("system.yaml", "storage.yaml", "cameras.yaml", "zones.yaml", "alerts.yaml", "models.yaml"))
    settings=Settings(
        database_path=ROOT / storage.get("database_path", "data/helios.db"),
        evidence_directory=ROOT / storage.get("evidence_directory", "data/evidence"),
        api_prefix=system.get("api_prefix", "/api/v1"),
        track_timeout_seconds=system.get("track_timeout_seconds", 12),
        track_buffer_frames=system.get("track_buffer_frames", 60),
        tracker_high_thresh=_float(str(system.get("tracker_high_thresh", 0.25)), 0.25),
        tracker_low_thresh=_float(str(system.get("tracker_low_thresh", 0.10)), 0.10),
        tracker_match_thresh=_float(str(system.get("tracker_match_thresh", 0.80)), 0.80),
        tracker_new_track_thresh=_float(str(system.get("tracker_new_track_thresh", 0.25)), 0.25),
        reid_enabled=bool(system.get("reid_enabled", True)),
        reid_weights_path=str(system.get("reid_weights_path", "models/reid/osnet_x0_25.pt")),
        reid_device=str(system.get("reid_device", "auto")),
        reid_max_lost_seconds=_float(str(system.get("reid_max_lost_seconds", 12.0)), 12.0),
        reid_weight_appearance=_float(str(system.get("reid_weight_appearance", 0.40)), 0.40),
        reid_weight_position=_float(str(system.get("reid_weight_position", 0.30)), 0.30),
        reid_weight_motion=_float(str(system.get("reid_weight_motion", 0.20)), 0.20),
        reid_weight_iou=_float(str(system.get("reid_weight_iou", 0.10)), 0.10),
        reid_recovery_cost_threshold=_float(str(system.get("reid_recovery_cost_threshold", 0.55)), 0.55),
        engine_restart_max_attempts=system.get("engine_restart_max_attempts", 3),
        engine_restart_backoff_seconds=system.get("engine_restart_backoff_seconds", 2),
        cameras=cameras.get("cameras", []), zones=zones.get("zones", []),
        alert_rules=alerts.get("rules", []), models=models.get("models", []),
        gemini_api_key=getenv("GEMINI_API_KEY", ""),
        helios_ai_model=getenv("HELIOS_AI_MODEL", "gemini-3.5-flash-lite"),
        helios_ai_enabled=_bool(getenv("HELIOS_AI_ENABLED")),
        helios_ai_timeout_seconds=_float(getenv("HELIOS_AI_TIMEOUT_SECONDS"), 30.0),
        helios_ai_gemini_timeout_seconds=_float(getenv("GEMINI_TIMEOUT_SECONDS") or getenv("HELIOS_AI_GEMINI_TIMEOUT_SECONDS"), 10.0),
        helios_ai_max_tool_rounds=_int(getenv("HELIOS_AI_MAX_TOOL_ROUNDS"), 6),
        openrouter_api_key=getenv("OPENROUTER_API_KEY", ""),
        openrouter_gemma_api_key=getenv("OPENROUTER_GEMMA_API_KEY") or getenv("GEMMA_OPENROUTER_API_KEY") or getenv("GEMMA_API_KEY", ""),
        openrouter_model=getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"),
        openrouter_fallback_model=getenv("OPENROUTER_FALLBACK_MODEL", "nvidia/nemotron-3.5-lightning:free"),
        openrouter_base_url=getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        openrouter_timeout_seconds=_float(getenv("OPENROUTER_TIMEOUT_SECONDS"), 45.0),
        openrouter_reasoning=_bool(getenv("OPENROUTER_REASONING"), True),
        openrouter_reasoning_effort=getenv("OPENROUTER_REASONING_EFFORT", "low"),
        openrouter_reasoning_max_tokens=_int(getenv("OPENROUTER_REASONING_MAX_TOKENS"), 400),
        helios_investigation_model=getenv("HELIOS_INVESTIGATION_MODEL", "minimax/minimax-m3"),
        helios_investigation_fallback_model=getenv("HELIOS_INVESTIGATION_FALLBACK_MODEL", "google/gemma-4-31b-it"),
        ollama_base_url=getenv("OLLAMA_BASE_URL") or getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        ollama_model=getenv("OLLAMA_MODEL", "qwen3:4b"),
        ollama_timeout_seconds=_float(getenv("OLLAMA_TIMEOUT_SECONDS"), 60.0),
    )
    camera_ids=[camera.get("camera_id") for camera in settings.cameras]
    if any(not value for value in camera_ids) or len(camera_ids)!=len(set(camera_ids)): raise ValueError("config/cameras.yaml must contain unique camera_id values")
    known=set(camera_ids)
    for zone in settings.zones:
        if not zone.get("zone_id") or zone.get("camera_id") not in known: raise ValueError(f"Zone {zone.get('zone_id','<unknown>')} references an unknown camera")
        geometry=zone.get("geometry", [])
        if len(geometry)<3 or any(len(point)!=2 or not all(0<=float(value)<=1 for value in point) for point in geometry): raise ValueError(f"Zone {zone['zone_id']} must have a normalized polygon")
    for model in settings.models:
        if model.get("enabled") and not model.get("mode"):
            raise ValueError(f"Model {model.get('name', '<unknown>')} must define a mode")
        classes=model.get("classes", [])
        if any(value not in {"HUMAN", "VEHICLE", "UAV", "FACE", "LICENSE_PLATE", "FIRE", "SMOKE", "UNCLASSIFIED", "MOTION"} for value in classes):
            raise ValueError("The V1 video adapters support HUMAN, VEHICLE, UAV, FACE, LICENSE_PLATE, FIRE, SMOKE, UNCLASSIFIED, and MOTION classes")
    return settings
