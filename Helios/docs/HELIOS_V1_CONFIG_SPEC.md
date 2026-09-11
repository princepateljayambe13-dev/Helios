# HELIOS V1 CONFIGURATION SPECIFICATION

## System Specification: Configuration Hierarchies, Environment Variables & YAML Specs

**Project:** HELIOS  
**Document:** System Settings, YAML Schema Definitions & Runtime Overrides  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Configuration Hierarchy

HELIOS employs a three-tier configuration structure:
1. **Default Code Settings**: Hardcoded safe defaults defined in Pydantic models (`app/core/config.py`).
2. **YAML Configuration Files**: Structured declarations for complex entities (`config/*.yaml`).
3. **Environment Variables**: Overrides from `.env` or system environment variables for secrets, hostnames, and ports.

---

# 2. Environment Variables Specification (`.env`)

| Variable Name | Default Value | Required | Purpose |
| :--- | :--- | :--- | :--- |
| `HELIOS_ENV` | `development` | No | Operational mode (`development`, `production`, `test`). |
| `HELIOS_HOST` | `127.0.0.1` | No | Host IP for FastAPI binding. |
| `HELIOS_PORT` | `8000` | No | Port for backend REST and WebSocket server. |
| `HELIOS_DB_PATH` | `data/helios.db` | No | Filepath to SQLite database. |
| `HELIOS_STORAGE_DIR` | `storage/` | No | Root directory for evidence, crops, and face snapshots. |
| `GEMINI_API_KEY` | `""` | Optional | Google Gemini API key for frontier LLM & VLM capabilities. |
| `OPENROUTER_API_KEY` | `""` | Optional | OpenRouter key for frontier reasoning models (Nemotron, Gemma). |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434`| No | URL for local offline Ollama inference. |
| `OLLAMA_MODEL` | `qwen3:4b` | No | Default local LLM model tag. |
| `ROBOFLOW_API_KEY` | `""` | Optional | API key for hosted Roboflow drone/face models. |
| `ARCFACE_DEVICE` | `cpu` | No | PyTorch computation device (`cpu`, `cuda`, `mps`). |

---

# 3. YAML Configuration Files (`config/`)

### 3.1 `cameras.yaml`
Declares camera network endpoints, RTSP/UDP stream credentials, and pixel calibrations:
```yaml
cameras:
  - camera_id: "CAM-01"
    name: "Main Perimeter Gate"
    source_type: "udp"
    stream_reference: "udp://127.0.0.1:8080"
    location: "North Gate Entrance"
    enabled: true
    pixels_per_meter: 42.5
    calibration:
      sensor_width: 1920
      sensor_height: 1080
      elevation_meters: 4.5
      tilt_degrees: 35.0
```

### 3.2 `zones.yaml`
Defines polygon coordinates (normalized $[0.0, 1.0]$) and monitored object types:
```yaml
zones:
  - zone_id: "ZONE-01"
    camera_id: "CAM-01"
    name: "North Ingress Restricted Polygon"
    zone_type: "RESTRICTED"
    geometry:
      - [0.15, 0.25]
      - [0.55, 0.25]
      - [0.60, 0.80]
      - [0.10, 0.75]
    object_types: ["human", "vehicle"]
    loitering_threshold_seconds: 30.0
```

### 3.3 `models.yaml`
Specifies model weights, detection confidence thresholds, and IoU matching:
```yaml
models:
  yolo:
    model_path: "models/detection/yolo26s.pt"
    confidence_threshold: 0.45
    iou_threshold: 0.50
    classes: [0, 2, 7] # 0: person, 2: car, 7: truck
  arcface:
    model_name: "MobileFaceNet"
    embedding_dim: 512
    match_threshold: 0.42
  vehicle_classifier:
    model_name: "openai/clip-vit-base-patch32"
    device: "cpu"
```

### 3.4 `alerts.yaml`
Alert routing rules, cooldown periods, and severity mappings:
```yaml
alerts:
  default_cooldown_seconds: 60.0
  severity_rules:
    RESTRICTED_ZONE_BREACH: "CRITICAL"
    LOITERING_DETECTED: "HIGH"
    SPEED_EXCEEDED: "MEDIUM"
    UAV_DETECTED: "CRITICAL"
```

### 3.5 `system.yaml`
Global system limits, storage quotas, and telemetry frequencies:
```yaml
system:
  max_stored_evidence_gb: 50.0
  deduplication_threshold: 0.85
  frame_buffer_size: 30
  telemetry_broadcast_interval_ms: 250
```
