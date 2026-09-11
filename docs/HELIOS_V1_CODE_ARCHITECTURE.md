# HELIOS V1 CODE ARCHITECTURE

## Technical Code Organization & Module Hierarchy

**Project:** HELIOS  
**Document:** Source Code Architecture, Module Boundaries & Class Hierarchy  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Project Directory Structure

The present HELIOS codebase is organized into clean functional tiers:

```
Helios/
├── backend/
│   ├── main.py                       # FastAPI Application Entrypoint & Middleware
│   ├── requirements.txt              # Production Python Dependencies
│   └── app/
│       ├── ai/                       # Generative AI, LLM/VLM Clients, Tools & Reasoning
│       │   ├── assistant.py          # Operational Assistant, Prompt Execution & Grounding
│       │   ├── client.py             # Unified Gemini, OpenRouter & Ollama AI Clients
│       │   ├── day_brief.py          # 24-Hour Threat Briefing Synthesizer
│       │   ├── investigator.py       # Spatial-Temporal Investigation Engine
│       │   ├── narrator.py           # Real-Time Operational Threat Narrator
│       │   ├── prompts.py            # System Prompts & Tool Orchestration Templates
│       │   ├── references.py         # Grounded Camera/Entity Reference Encoders
│       │   ├── schemas.py            # Pydantic Schemas for AI Responses & Chats
│       │   ├── service.py            # AiService Facade
│       │   └── tools.py              # Operational Tool Definitions (10+ Tools)
│       ├── alerts/                   # Alert Rules & Notification Engine
│       ├── api/                      # REST Endpoints & WebSocket Managers
│       │   ├── routes/
│       │   │   ├── ai.py             # /api/v1/ai/* Endpoints
│       │   │   ├── api.py            # Core Surveillance, Cameras, Zones, Alerts Routes
│       │   │   ├── faces.py          # /api/v1/faces/* Endpoints & Roster Management
│       │   │   └── insights.py       # /api/v1/insights/* Endpoints & NL Investigator
│       │   └── websocket.py          # WebSocket Connection Manager & Broadcast Dispatcher
│       ├── core/                     # Application Settings & Configuration Loaders
│       │   └── config.py             # Pydantic BaseSettings (.env & YAML Bindings)
│       ├── database/                 # SQLite Connection Pool & Repositories
│       │   ├── connection.py         # DB Connect, WAL Initialization & 20-Table Schema
│       │   ├── models.py             # Core Pydantic Models
│       │   └── models_face.py        # Facial Recognition Schemas & Input Types
│       ├── incidents/                # Incident Correlation Engine
│       │   ├── correlator.py         # IncidentCorrelator Multi-Signal Aggregation
│       │   └── incident.py           # Incident Domain Entity
│       ├── ingestion/                # Stream Acquisition & Camera Management
│       │   ├── camera_manager.py     # Multi-Camera Lifecycle & Health Monitor
│       │   ├── frame_buffer.py       # Ring Buffering & Snapshot Storage
│       │   └── stream_hub.py         # RTSP / UDP / Synthetic Video Demuxing
│       ├── insights/                 # Strategic Intelligence & Anomaly Layer
│       │   ├── ai_explainer.py       # Plain-English Explanations for Score Factors
│       │   ├── baseline.py           # Normality Baseline Engine & Z-Score Tracker
│       │   ├── engine.py             # InsightsEngine Pipeline
│       │   ├── evidence_analyzer.py  # Evidence Correlation Helper
│       │   ├── models.py             # Observation & Insight Domain Entities
│       │   ├── nl_investigator.py    # Natural Language Investigator (SSE Streaming)
│       │   ├── observation_layer.py  # High-Level Spatio-Temporal Observation Store
│       │   ├── scoring.py            # 7-Signal Composite Scoring Formula
│       │   └── summaries.py          # Rolling 5m / 1h / 24h Summary Manager
│       ├── services/                 # Unified Application Domain Services
│       │   └── helios_service.py     # HeliosService Master Facade
│       ├── spatial/                  # Vector Geometry & Zone Engine
│       │   ├── fence.py              # Virtual Fence Domain Model
│       │   ├── geometry.py           # Ray-Casting PIP & Segment Cross Intersection
│       │   ├── spatial_engine.py     # Loitering, Tripwire & Intrusion Evaluator
│       │   └── zone.py               # Zone Domain Model & Thresholds
│       ├── tracking/                 # Multi-Object Tracking & Kinematics
│       │   ├── face_association.py   # Bounding Box Face-to-Human Track Linkage
│       │   ├── movement.py           # Speed, Heading & Hysteresis State Machine
│       │   ├── track.py              # Track Domain Model
│       │   ├── track_manager.py      # IoU Track Association & Age Management
│       │   ├── tracker.py            # Multi-Object Tracker Implementation
│       │   └── trajectory.py         # Position History & Smoothing
│       └── vision/                   # Neural Perception & Feature Extraction
│           ├── detectors/            # Model Detectors (Face, Vehicle, UAV)
│           ├── face/                 # ArcFace MobileFaceNet & Recognition Manager
│           │   ├── arcface.py        # PyTorch ArcFace Backbone (512-d Embeddings)
│           │   └── recognition_manager.py # Cosine Matching & Unknown Clustering
│           ├── motion.py             # MOG2 / Frame-Difference Fast Motion Detector
│           ├── observation.py        # Detection Bounding Box Standardizer
│           ├── roboflow_client.py    # Hosted Model Inference Bridge
│           ├── vehicle_intelligence.py# Zero-Shot CLIP & HSV Color Classifier
│           └── yolo26.py             # YOLO26 Model Loader & TensorRT/PyTorch Runner
├── config/                           # YAML Configuration Files
│   ├── alerts.yaml                   # Alert Thresholds & Notification Rules
│   ├── cameras.yaml                  # RTSP/UDP Stream Endpoints & Calibrations
│   ├── models.yaml                   # Vision & AI Model Parameters
│   ├── system.yaml                   # Global System Tuning & Storage Paths
│   └── zones.yaml                    # Pre-Configured Spatial Polygons & Tripwires
├── dashboard/                        # React 18 + Vite Frontend Application
│   ├── src/
│   │   ├── components/               # 20+ Production React Views & Widgets
│   │   ├── hooks/useHeliosWebSocket.js# Bidirectional WebSocket Hook
│   │   ├── services/api.js           # Axios/Fetch API Gateway
│   │   ├── utils/                    # Audio Synthesis & AI Action Helpers
│   │   ├── App.jsx                   # Shell Container & View Switcher
│   │   └── styles.css                # Dark Glassmorphic Theme Tokens
│   └── package.json
├── scripts/                          # Maintenance & Initialization Utilities
│   ├── init_database.py              # SQLite Table Creation & Seed Data
│   └── health_check.py               # API & Video Stream Latency Diagnostics
├── start_helios.sh                   # Unified Orchestration & Lifecycle Script
└── README.md
```

---

# 2. Key Domain Classes & Interfaces

### 2.1 `HeliosService` (`backend/app/services/helios_service.py`)
The master application service orchestrating state across perception, storage, and broadcasting. It encapsulates:
- Camera registrations and status updates.
- Track creation, movement updating, and activity thread management.
- Spatial evaluation delegating to `SpatialEngine`.
- Event and alert generation with rate-limiting and deduplication.
- Facial recognition query routing and roster updates.
- Background incident correlation via `IncidentCorrelator`.

### 2.2 `SpatialEngine` (`backend/app/spatial/spatial_engine.py`)
Encapsulates all geometric evaluations:
- `evaluate_point(point, zones)`: Ray-casting point-in-polygon tests.
- `evaluate_tripwire(segment, tripwires)`: Vector cross-product line crossing.
- `update_loitering(track, zone, timestamp)`: Manages active `loitering_sessions`.

### 2.3 `IncidentCorrelator` (`backend/app/incidents/correlator.py`)
- `correlate_event(event)`: Scans active incidents within the temporal window, calculates affinity scores across 6 factors, and appends to existing or creates new incident entities.
- `acknowledge_incident(incident_id, operator_id)`: Transitions state to `ACKNOWLEDGED`.
- `resolve_incident(incident_id, notes)`: Transitions state to `RESOLVED`.

### 2.4 `ArcFaceRecognizer` (`backend/app/vision/face/arcface.py`)
- `extract_embedding(image)`: Preprocesses image to $112 \times 112$, runs forward pass through `MobileFaceNetArcFace`, and outputs unit $L_2$-normalized 512-dimensional vector.
- `compute_similarity(emb1, emb2)`: Computes dot product cosine similarity.

---

# 3. State Management & Data Consistency

1. **Transactional SQLite Access**: All writes use parameterized queries via `sqlite3` connection wrappers with `PRAGMA journal_mode=WAL` to allow non-blocking concurrent reads.
2. **WebSocket Event Bus**: The backend maintains a centralized client set (`WebSocketManager`) broadcasting structured JSON payloads whenever an event, alert, track, or recognition occurs.
3. **Frontend Reactive State**: The React dashboard uses a central `App.jsx` context paired with `useHeliosWebSocket` hook to push incoming events directly into the active view without triggering full component re-renders.
