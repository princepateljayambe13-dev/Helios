# HELIOS V1 backend

The V1 backend is a FastAPI service with SQLite metadata storage. It ingests OpenCV/FFmpeg-compatible video sources (including RTSP and HTTP/HLS), performs configured local inference, and exposes browser-safe MJPEG playback. WebRTC playback is not implemented.

## Start

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python scripts/init_database.py
cd backend && uvicorn main:app --reload
```

If you are already inside the `backend/` directory:

```bash
cd ..
source .venv/bin/activate
python scripts/init_database.py
cd backend && uvicorn main:app --reload
```

Interactive API documentation: `http://127.0.0.1:8000/docs`.

## Main endpoints

- `GET /api/v1/system/health` and `/system/summary`
- `GET, POST /api/v1/cameras`; `GET /cameras/{camera_id}/health`; `POST /cameras/{camera_id}/status?status=OFFLINE`
- `GET /api/v1/zones`, `/tracks`, `/tracks/{track_id}`, `/events?limit=100&offset=0`, `/alerts`, `/evidence`; `POST /evidence` to register evidence metadata and optional integrity hash
- `POST /api/v1/observations` — integration entry point for normalized AI output
- `POST /api/v1/audio/observations` — normalized acoustic classifier input
- `POST /api/v1/alerts/{alert_id}/acknowledge`
- `WS /api/v1/ws` — publishes `observation`, `camera`, and `alert` messages

## AI adapter contract

Post standard observations with `camera_id`, `object_type`, `confidence` (0–1), and `[x, y, width, height]` `bounding_box`; optional `zone_id`, model metadata, timestamp, and attributes are accepted. The service persists a detection, creates a temporary track, creates an event, then evaluates `config/alerts.yaml` with cooldown de-duplication.

Tracks use a lightweight IoU association fallback and maintain persisted position history. A configured polygon zone is automatically evaluated using the normalized bounding-box center; a supplied `zone_id` remains authoritative. A production tracker/model can replace this adapter without changing the observation API.

For a production adapter, the external stream/model worker should call this endpoint after it normalizes model output to the HELIOS observation schema. Store stream credentials outside these API responses and use a secure secret manager in a production deployment.

## No stream or model yet

Configured cameras without a `stream_reference` are intentionally reported as `OFFLINE`, with `stream_status: NOT_PROVIDED` in the camera health endpoint. Disabled entries in `config/models.yaml` are returned as `NOT_PROVIDED`. This is the expected state until you supply a secure stream adapter and enable a model; no synthetic video or synthetic detections are generated.

## Enable YOLO26s video detection

HELIOS now includes a local YOLO26s adapter for `HUMAN` and `VEHICLE` detections. Install the backend requirements, then set each camera's `stream_reference` in `config/cameras.yaml` to a local file, RTSP URL, or other OpenCV-compatible video source. Keep credentials out of source control (for example, inject the URL when deploying).

```yaml
cameras:
  - camera_id: CAM-01
    name: North Perimeter
    source_type: RTSP
    stream_reference: "rtsp://user:password@camera.example/stream"
    location: North perimeter
    enabled: true
```

On startup, HELIOS loads `models/detection/yolo26s.pt`. Place the deployed checkpoint there before starting the backend; the checkpoint is intentionally not committed to source control. HELIOS then opens every enabled configured feed and emits only detections above the configured threshold. The configured default is 4 inference frames per second. Restart the backend after changing `config/cameras.yaml` so the new feed is loaded.

The dashboard displays a configured feed through `GET /api/v1/cameras/{camera_id}/stream`, which proxies it as MJPEG. This endpoint keeps the configured source URL and its credentials on the backend.

Object association uses ByteTrack. HELIOS creates one linked lifecycle event per human or vehicle track, updates the track while it is visible, and closes the event with the start/end time, duration, and detection count after `track_timeout_seconds` without a new observation.

## Configure the Roboflow UAV model

Roboflow's `inference-sdk` currently requires Python 3.10–3.12. Run the backend with one of those versions to enable the cloud UAV, face, and ANPR adapters. On Python 3.13+, HELIOS continues to run its local camera and YOLO pipeline, but logs those cloud models as unavailable instead of failing startup.

`config/models.yaml` includes the separate `uav-detector` model (`uav-v1djs/3`). Set `UAV_ROBOFLOW_API_KEY` in the backend deployment environment before starting HELIOS. Do not place the secret in YAML, source code, or Git. The adapter uses header-based authentication, sends one sampled frame per second by default, and converts UAV results into the regular tracks, events, alerts, and dashboard overlays.

The same environment key is used by the separate `face-detector` Workflow (`pramukhs-workspace/general-segmentation-api-2`). It sends the `classes=face` parameter and produces location-only `FACE` observations; no identity or recognition data is created.

## Configure the Roboflow ANPR model

The same local key enables `license-plate-detector` (`anpr-tdrid/1`). It detects plates (it does not yet read plate text), creates `LICENSE_PLATE` tracks/events, and stores a cropped image under `data/evidence/anpr`. The temporary store holds 30 crops; the next crop clears that entire batch and starts a new one. The associated evidence record retains the detection and event linkage for the active batch.

## Gemini AI Intelligence Layer

HELIOS now exposes a Gemini-based intelligence layer for natural-language querying, event narration, investigation, and daily briefings. It is a backend-only, read-only capability: HELIOS remains the source of truth, and Gemini is used only for explanation, querying, and summarization. Gemini is never given direct database access, SQL, Python, shell, filesystem, or network capabilities — it can only call the registered backend tools below.

### Configuration

```env
GEMINI_API_KEY=your-key-here
HELIOS_AI_MODEL=gemini-2.5-flash
HELIOS_AI_ENABLED=true
HELIOS_AI_TIMEOUT_SECONDS=30
HELIOS_AI_MAX_TOOL_ROUNDS=6
```

Set these in `backend/.env` (or the process environment). `HELIOS_AI_ENABLED=false` (the default when unset) keeps the normal surveillance pipeline fully operational; the AI endpoints then return deterministic, data-only responses.

### Endpoints

All AI endpoints are exposed under both the v1 prefix (`/api/v1/ai/...`) and the task-specified prefix (`/api/ai/...`).

| Endpoint | Description |
|---|---|
| `GET /api/v1/ai/status` | AI capability status (`enabled`, `available`, `model`, `provider`, `error`) — never exposes the API key. |
| `POST /api/v1/ai/ask` | Ask a natural-language question about HELIOS data. Body: `{"question": "...", "history": [{"role": "user", "content": "..."}]}`. The assistant calls registered tools and answers only from returned data. |
| `GET /api/v1/ai/event/{event_id}/explain` | Short factual narration of an event (`EventInsight`). |
| `POST /api/v1/ai/event/{event_id}/investigate` | Structured read-only investigation. Optional body: `{"context_window_hours": 6, "focus": "..."}`. |
| `GET /api/v1/ai/day-brief?date=YYYY-MM-DD` | Daily brief. HELIOS computes all statistics server-side; Gemini writes the synthesis. |

### Registered AI tools

`get_recent_events`, `search_events`, `get_event`, `get_track_history`, `get_zone_activity`, `get_camera_status`, `get_daily_statistics`, `get_event_timeline`, `get_evidence`, `get_related_events`.

### Response schema highlights

Every AI response carries traceable references and action objects:

```text
AIResponse          -> answer, claims[], actions[], references[], grounded
AiClaim             -> statement, basis, references[] (event_id/track_id/camera_id/zone_id/evidence_id)
AiAction            -> type, label, event_id/track_id/camera_id/zone_id/evidence_id
EventInsight        -> summary, narration, facts, references[], actions[]
InvestigationResult -> explanation, context (event/track/camera/zone/timeline/related_events/evidence), references[], actions[]
DayBrief            -> activity_summary, evidence_summary, activity_patterns, ai_assessment, stats, references[], actions[]
```

Action types: `INVESTIGATE_EVENT`, `VIEW_EVIDENCE`, `OPEN_EVENT`, `OPEN_CAMERA`, `OPEN_TRACK`, `OPEN_TIMELINE`, `VIEW_RELATED_EVENTS`, `OPEN_ZONE`, `REVIEW_ACTIVITY`, `OPEN_CAMERA_HEALTH`. IDs are never invented — claims referencing objects the model was never shown are discarded before responses are returned.
