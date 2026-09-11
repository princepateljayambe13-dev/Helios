# HELIOS V1 SYSTEM ARCHITECTURE

## System Architecture Specification

**Project:** HELIOS  
**Full Name:** Intelligent Surveillance & Threat Intelligence Operational Platform  
**Problem Statement:** SH26187  
**Version:** V1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Architectural Overview & System Topology

HELIOS is architected as an event-driven, micro-modular platform comprising:
1. **Sensor & Ingestion Hub**: RTSP, UDP MPEG-TS, and synthetic video stream pipelines with unified frame buffering and snapshot proxying.
2. **AI Perception Layer**: Heterogeneous model inference pipelines (YOLO26, Roboflow UAV/Face, MobileFaceNet ArcFace, CLIP Zero-Shot, and Audio detectors).
3. **Tracking & Kinematics Engine**: IoU/ByteTrack tracking, foot-point spatial grounding, 8-way directional heading, and velocity calibration.
4. **Spatial Reasoning & Fencing**: Arbitrary polygon point-in-polygon evaluation, tripwires, and loitering state machines.
5. **Biometric Identity Association**: 512-dim ArcFace embedding extraction, cosine similarity matching, and face-to-human track linkage.
6. **Cross-Camera Incident Correlator**: Spatio-temporal event aggregation, incident lifecycle state machine, and timeline synthesis.
7. **Intelligence & Insights Engine**: 7-signal composite scoring, baseline normality modeling, and "What Changed" anomaly engine.
8. **Generative AI & Natural Language Core**: Multi-provider client (Gemini, OpenRouter with reasoning preservation, and offline Ollama `qwen3:4b`), Gemma multimodal investigation, and daily briefing synthesis.
9. **Persistence & Evidence Store**: SQLite 20-table relational database in WAL mode, structured JPEG thumbnail storage, and perceptual hash deduplication.
10. **Real-Time Operational Dashboard**: React 18 + Vite frontend with glassmorphic dark operational UI, 12 navigation views, and bidirectional WebSocket streaming.

---

# 2. Detailed Architecture Diagram

```
                                  CAMERA SOURCES
            [RTSP IP Cams]     [UDP MPEG-TS Streams]     [USB / Local Files]
                   │                     │                        │
                   └─────────────────────┼────────────────────────┘
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │       Ingestion Hub & Frame Buffer            │
                 │   - Stream Hub        - Snapshot Proxy        │
                 │   - Frame Decimator   - Health Watchdog       │
                 └───────────────────────┬───────────────────────┘
                                         │
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │            AI Perception Layer                │
                 │  - YOLO26 (Human/Vehicle)                     │
                 │  - Roboflow (UAV Incursion / Face)            │
                 │  - ArcFace (MobileFaceNet 512-d Biometrics)   │
                 │  - CLIP & HSV (Vehicle Model & Color)         │
                 │  - Acoustic Threat Detector                   │
                 └───────────────────────┬───────────────────────┘
                                         │ Detections & Embeddings
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │          Tracking & Kinematics Engine         │
                 │  - Kalman / IoU Tracking  - Speed Calibration │
                 │  - Foot-Point Grounding   - 8-Way Heading     │
                 │  - Face-Human Association                     │
                 └───────────────────────┬───────────────────────┘
                                         │ Tracks & Movements
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │           Spatial Engine & Fencing            │
                 │  - Vector Polygon PIP    - Loitering Sessions │
                 │  - Directed Tripwires    - Density Heatmaps   │
                 └───────────────────────┬───────────────────────┘
                                         │ Events & Breaches
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │    Incident Correlator & Alert Manager        │
                 │  - Probabilistic Multi-Signal Correlation     │
                 │  - Incident Lifecycle (DETECTED -> RESOLVED)  │
                 │  - Alert Priority Escalation & Audio Chimes   │
                 └───────────────┬───────────────────────────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         ▼                                               ▼
┌─────────────────────────────────┐     ┌─────────────────────────────────┐
│     Insights & Anomaly Engine   │     │    Generative AI & Assistant    │
│  - 7-Signal Composite Scoring   │     │  - Gemini 1.5 & OpenRouter      │
│  - Baseline Normality Z-Scores  │     │  - Offline Local Ollama         │
│  - "What Changed" Analysis      │     │  - Gemma Multimodal VLM         │
│  - Operator Feedback Loop (RLHF)│     │  - 10+ Operational Tools        │
└────────────────┬────────────────┘     └────────────────┬────────────────┘
                 │                                       │
                 └───────────────────┬───────────────────┘
                                     │
                                     ▼
                 ┌───────────────────────────────────────────────┐
                 │            Data & Storage Layer               │
                 │  - SQLite (20 Tables, WAL Mode, Indexes)      │
                 │  - Evidence Bounding Box Crops & Full JPEGs   │
                 │  - Perceptual Hash Deduplication Engine       │
                 └───────────────────────┬───────────────────────┘
                                         │
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │         API & Streaming Interface             │
                 │  - FastAPI REST Endpoints (/api/v1/*)         │
                 │  - WebSocket Server (/api/v1/ws)              │
                 └───────────────────────┬───────────────────────┘
                                         │
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │       Glassmorphic Operational Dashboard      │
                 │  - 12 Production Views (Overview, Feeds, etc) │
                 │  - Real-time SVG Charts & Surveillance Globe  │
                 │  - Global Search & AI Chat Modal (⌘ K)        │
                 └───────────────────────────────────────────────┘
```

---

# 3. Component Boundaries & Interaction Patterns

### 3.1 Synchronous vs Asynchronous Workflows
- **Synchronous In-Memory Processing**: Frame decoding, detection inference, IoU track assignment, and spatial boundary checking execute within the low-latency pipeline loop ($<60\text{ms}$ per frame).
- **Asynchronous Persistence & Intelligence**: Heavy database writes, evidence cropping, incident correlation, 7-signal insight calculation, and LLM reasoning run via background tasks or thread pools to avoid blocking video ingestion.

### 3.2 Resilience & Process Isolation
- The unified orchestrator (`start_helios.sh`) traps signals (`SIGINT`, `SIGTERM`, `EXIT`) and manages child processes with automatic port reclamation (`-k`).
- The WebSocket client in React implements exponential backoff reconnection with live status indicator pills (`LIVE`, `RECONNECTING`, `DISCONNECTED`).

---

# 4. Data Flow Walkthrough: Incursion to Resolution

1. **Ingestion**: Camera `CAM-02` captures video stream; frame is stored in memory buffer.
2. **Perception**: YOLO26 detects a `human` bounding box; ArcFace extracts facial embedding.
3. **Tracking & Kinematics**: Track ID `TRK-882` is assigned; foot position calculated; velocity computed as $12.4\text{ km/h}$ heading `SE`.
4. **Spatial Reasoning**: Foot position breaches polygon `ZONE-01` (`RESTRICTED`), triggering event `EVT-042`.
5. **Incident Correlation**: `IncidentCorrelator` merges `EVT-042` with an earlier perimeter breach into Incident `INC-009` (Score: $0.84$).
6. **Insight & Alerts**: 7-signal score reaches $88$ (`CRITICAL`); alert banner flashes; audio chime sounds; WebSocket pushes event to all dashboard operators.
7. **AI Investigation**: Operator presses `⌘ K` and requests *"Investigate INC-009"*; Gemma multimodal inspects crop snapshot and returns spatial-temporal reasoning.
8. **Resolution**: Operator acknowledges threat, dispatches security team, and marks `INC-009` `RESOLVED` with audit notes.
