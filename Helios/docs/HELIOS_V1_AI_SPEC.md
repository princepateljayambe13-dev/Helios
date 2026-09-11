# HELIOS V1 AI INTELLIGENCE SPECIFICATION

## System Specification: Multi-Provider LLM/VLM Core, Tools & Reasoning Architecture

**Project:** HELIOS  
**Document:** Generative AI Assistant, Multimodal Investigation & Reasoning Framework  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Purpose

The HELIOS AI Intelligence Layer provides autonomous reasoning, natural language command execution, multi-modal evidence inspection, and automated incident narrative generation.

Unlike generic chatbot wrappers, HELIOS AI is deeply coupled with the physical surveillance state:
- **Multi-Provider Hybrid Architecture**: Combines cloud frontier models (Google Gemini 1.5 Flash/Pro, OpenRouter reasoning models) with fully offline local LLMs via Ollama (`qwen3:4b`), guaranteeing operational continuity in air-gapped or bandwidth-constrained environments.
- **Gemma Multimodal Visual Investigation**: Performs frame-level inspection of high-resolution evidence crops to verify weapon presence, vehicle descriptions, or suspicious behavioral traits.
- **Operational Tool Grounding**: Uses functional tool calling to query active database tables (`tracks`, `incidents`, `cameras`, `movements`, `faces`) rather than hallucinating answers.
- **Structured Threat Narratives**: Translates low-level coordinate detections into actionable intelligence summaries for human security operators.

---

# 2. Multi-Provider Client Architecture (`app/ai/client.py`)

The AI subsystem uses an abstract provider interface with automated fallback chains:

```
                            [ User Query / Investigation Request ]
                                              │
                                              ▼
                                 ┌───────────────────────────┐
                                 │     Client Dispatcher     │
                                 └─────────────┬─────────────┘
                                               │
                   ┌───────────────────────────┼───────────────────────────┐
                   ▼                           ▼                           ▼
       ┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
       │     GeminiClient      │   │   OpenRouterClient    │   │     OllamaClient      │
       │ - Gemini 1.5 Flash    │   │ - Nemotron 3.5 Free   │   │ - Local Edge Inference│
       │ - Multimodal Vision   │   │ - Gemma 4 31B IT      │   │ - Qwen3:4b Model      │
       │ - Cloud High-Speed    │   │ - Preserves <think>   │   │ - 100% Offline / LAN  │
       └───────────────────────┘   └───────────────────────┘   └───────────────────────┘
```

### 2.1 Provider Implementations
1. **`GeminiClient`**: Primary cloud provider for ultra-fast response generation, native multimodal image inspection, and function calling.
2. **`OpenRouterClient`**: Secondary provider supporting frontier reasoning models (e.g., `nvidia/nemotron-3.5-lightning:free` and `google/gemma-4-31b-it:free`). Preserves and strips `<think>...</think>` internal tokens, exposing `reasoning_details` and `reasoning_tokens` for auditing.
3. **`OllamaClient`**: Local daemon client (`http://127.0.0.1:11434`), defaults to `qwen3:4b`. Enables complete offline autonomy without internet access.

---

# 3. Operational Tool Registry (`app/ai/tools.py`)

The assistant is equipped with deterministic operational tools that query live system state:

| Tool Name | Parameters | Purpose |
| :--- | :--- | :--- |
| `summarize_system` | `hours` (int) | Returns aggregate camera counts, active tracks, and today's alert breakdown. |
| `query_threats` | `severity`, `limit` | Queries active security alerts and unacknowledged threats. |
| `inspect_camera` | `camera_id` | Returns live FPS, operational status, recent detection count, and active zones. |
| `investigate_entity`| `entity_id`, `entity_type` | Retrieves full cross-camera track history, movements, and evidence snapshots. |
| `analyze_speed` | `track_id` | Fetches velocity time-series (km/h and px/s), acceleration, and directional heading. |
| `get_face_identity`| `recognition_id` | Resolves facial recognition sighting against enrolled personnel roster. |
| `generate_incident_report` | `incident_id` | Compiles a structured, exportable incident dossier with event timelines. |

---

# 4. Multimodal Investigation Engine (`app/ai/investigator.py`)

When an operator clicks **Investigate** on an evidence card or incident timeline:
1. **Context Synthesis**: Assembles temporal proximity data, camera calibration parameters, vehicle intelligence (CLIP class/color), and spatial zone breach records.
2. **Image Encoding**: Encodes the high-resolution JPEG crop as base64 data.
3. **Prompt Orchestration**: Constructs a structured reasoning prompt commanding the vision model to inspect:
   - Subject posture, orientation, and carried objects (bags, tools, weapons).
   - Ingress/egress trajectory plausibility.
   - Immediate tactical recommendations for security dispatchers.
4. **Output Schema**: Returns a validated Pydantic `InvestigationResult` with confidence score, key findings bullet list, and tactical action items.

---

# 5. Automated 24-Hour Daily Briefing (`app/ai/day_brief.py`)

Executed automatically at shift changeover or on-demand via `GET /api/v1/ai/day-brief`:
- Synthesizes 24-hour sensor telemetry across all cameras.
- Identifies peak threat windows (e.g. 02:00–04:00 perimeter alerts).
- Summarizes facial recognition logs, highlighting any unknown individuals who loitered near restricted zones.
- Generates executive-ready security posture grades (`SECURE`, `ELEVATED_VIGILANCE`, `THREAT_DETECTED`).

---

# 6. Real-Time Threat Narrator (`app/ai/narrator.py`)

Generates human-readable 1-sentence micro-narratives for live dashboard cards:
- *Example*: `"Track TRK-104 (Human) entered Restricted Perimeter Zone at 14:22:15, moving Southeast at 8.2 km/h."`
- These narratives update dynamically in the `NarrativeGrid` without page refreshes.
