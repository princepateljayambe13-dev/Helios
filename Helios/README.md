# HELIOS — AI Surveillance & Threat Intelligence Operational Platform

HELIOS is an enterprise-grade AI surveillance and threat intelligence platform designed for real-time camera ingestion, multi-object tracking (Human, Vehicle, UAV, License Plate ANPR), edge biometric facial recognition, cross-camera incident correlation, spatial perimeter fencing, and generative AI event investigation.

---

## 🌟 Key Capabilities of Present HELIOS

1. **High-Fidelity Defense Dashboard (12 Operational Views)**:
   - Built directly on the official HELIOS dark glassmorphic operational UI specification.
   - 12 comprehensive views: **Overview**, **Live Feeds**, **Perimeter Fencing**, **Events** (All / Tracked / Zone), **Insights**, **Incidents**, **Alerts & Audit Logs**, **Evidence Gallery**, **Activity Threads**, **Facial Recognition**, **Settings**, and **Operator Authentication**.
   - Animated status spectrum ring, 24-hour SVG sparklines, and procedural Web Audio alert chimes.

2. **Continuous Real-Time WebSocket Streaming (Zero Page Refresh)**:
   - High-throughput WebSocket server (`ws://127.0.0.1:8000/api/v1/ws`).
   - Real-time broadcast of detections, kinematic movements, zone breaches, biometric sightings, and correlated incidents.
   - Automatic reconnect logic with live telemetry pills (`LIVE`, `RECONNECTING`, `DISCONNECTED`).

3. **Biometric Perception & Identity Association (ArcFace)**:
   - Edge-deployable MobileFaceNet ArcFace producing 512-dimensional normalized embeddings.
   - Continuous spatial face-to-human body track association using upper-torso containment heuristics.
   - Full identity roster management, raw photo upload, similarity scoring, and unknown face clustering.

4. **Cross-Camera Incident Correlation Engine**:
   - Probabilistic 6-factor correlation engine (`IncidentCorrelator`) grouping multi-camera, multi-zone security events into evolving incident dossiers.
   - Complete incident state machine: `DETECTED` $\to$ `CONFIRMED` $\to$ `ACTIVE` $\to$ `ACKNOWLEDGED` $\to$ `RESOLVED`.
   - Chronological incident timelines with evidence snapshots and operator closing notes.

5. **Spatial Intelligence, Fencing & Movement Kinematics**:
   - Arbitrary vector polygon zones and directional tripwires evaluated via ray-casting Point-in-Polygon (PIP) on bottom-center ground contact points.
   - Real-time velocity estimation ($\text{km/h}$ and $\text{px/s}$), 8-way cardinal headings, and hysteresis state classification (`STATIONARY`, `WALKING`, `RUNNING`, `LOITERING`).
   - Loitering session lifecycle tracking with configurable dwell time thresholds.

6. **Strategic Insights & 7-Signal Anomaly Detection**:
   - 7-signal composite scoring engine (anomaly, persistence, spatial significance, cross-camera correlation, density shift, incident relevance, sensor reliability).
   - Dynamic normality baselines and instant Z-score "What Changed" anomaly reports.
   - Operator RLHF feedback loop for continuous scoring calibration.

7. **Multi-Provider Generative AI Assistant & Multimodal Investigation**:
   - Multi-LLM provider support: Google Gemini 1.5 Flash/Pro, OpenRouter reasoning models (Nemotron, Gemma), and 100% offline local Ollama (`qwen3:4b`).
   - Gemma Multimodal VLM inspection of high-resolution evidence snapshots.
   - 10+ operational tools powering the `⌘ K` Global Command & AI Assistant overlay.
   - Automated 24-hour threat briefings (`/api/v1/ai/day-brief`) and real-time micro-narratives.

---

## 🏗️ Architecture & Project Structure

```
Helios/
├── backend/                  # FastAPI Backend Application
│   ├── app/                  # Application Core, Services & Pipelines
│   │   ├── ai/               # Multi-Provider Clients, Tools, Investigator, Day Brief
│   │   ├── alerts/           # Rule Engine & Notification Manager
│   │   ├── api/              # REST Routes (/api/v1) & WebSocket Server
│   │   ├── database/         # SQLite Connection Pool & 20-Table Schema
│   │   ├── incidents/        # Cross-Camera Incident Correlation Engine
│   │   ├── ingestion/        # Multi-Stream Hub (RTSP/UDP/File) & Frame Buffer
│   │   ├── insights/         # 7-Signal Scoring, Baselines & NL Investigator
│   │   ├── services/         # HELIOS Master Application Service Facade
│   │   ├── spatial/          # Vector Polygons, Tripwires & Loitering Engine
│   │   ├── tracking/         # IoU Tracker, Kinematics & Face Association
│   │   └── vision/           # YOLO26, Roboflow, ArcFace & CLIP Classifiers
│   ├── main.py               # FastAPI Entrypoint (Port 8000)
│   └── requirements.txt      # Python Dependencies
├── config/                   # System Configuration (cameras, zones, models, alerts, system)
├── dashboard/                # React 18 + Vite Frontend Application
│   ├── src/
│   │   ├── components/       # 12 Production View Modules & Glassmorphic Widgets
│   │   ├── hooks/            # useHeliosWebSocket Hook
│   │   ├── services/         # REST API Client (api.js)
│   │   ├── utils/            # Web Audio Synthesizer & AI Action Helpers
│   │   ├── App.jsx           # Master Application Shell
│   │   └── styles.css        # Glassmorphic Theme Tokens
│   └── package.json
├── data/                     # Persistent SQLite Database & Evidence Storage
├── docs/                     # 23 Comprehensive Production Technical Specifications
├── scripts/                  # Database Initializer, Diagnostics & Setup Tools
├── start_helios.sh           # Unified Startup & Process Lifecycle Orchestrator
└── README.md
```

---

## 📚 Complete Documentation Sitemap (`docs/`)

| Specification Document | Focus Area |
| :--- | :--- |
| **[HELIOS_V1_PRD.md](docs/HELIOS_V1_PRD.md)** | Product Requirements Document, Core Objectives & User Personas |
| **[HELIOS_V1_ARCHITECTURE.md](docs/HELIOS_V1_ARCHITECTURE.md)** | End-to-End System Topology, 10-Layer Architecture & Workflows |
| **[HELIOS_V1_CODE_ARCHITECTURE.md](docs/HELIOS_V1_CODE_ARCHITECTURE.md)** | Code Directory Layout, Service Facades & Class Interfaces |
| **[HELIOS_V1_API.md](docs/HELIOS_V1_API.md)** | Comprehensive REST API Reference & Real-Time WebSocket Protocols |
| **[HELIOS_V1_FACIAL_RECOGNITION_SPEC.md](docs/HELIOS_V1_FACIAL_RECOGNITION_SPEC.md)** | ArcFace Biometrics, Roster Management & Face-Human Track Association |
| **[HELIOS_V1_SPATIAL_FENCING_SPEC.md](docs/HELIOS_V1_SPATIAL_FENCING_SPEC.md)** | Vector Polygons, Ray-Casting PIP, Tripwires & Loitering Engine |
| **[HELIOS_V1_INCIDENT_CORRELATION_SPEC.md](docs/HELIOS_V1_INCIDENT_CORRELATION_SPEC.md)** | Spatio-Temporal Cross-Camera Correlation & Incident State Machine |
| **[HELIOS_V1_INSIGHTS_SPEC.md](docs/HELIOS_V1_INSIGHTS_SPEC.md)** | 7-Signal Composite Scoring, Baseline Normality & NL Investigator |
| **[HELIOS_V1_AI_SPEC.md](docs/HELIOS_V1_AI_SPEC.md)** | Multi-Provider Clients (Gemini/OpenRouter/Ollama), Tools & Gemma VLM |
| **[HELIOS_V1_ALERT_SPEC.md](docs/HELIOS_V1_ALERT_SPEC.md)** | Alert Rule Engine, Cooldowns, Priority Levels & Web Audio Chimes |
| **[HELIOS_V1_AUDIO_SPEC.md](docs/HELIOS_V1_AUDIO_SPEC.md)** | Acoustic Threat Ingestion, Sound Event Classes & Cross-Modal Fusion |
| **[HELIOS_V1_CAMERA_SPEC.md](docs/HELIOS_V1_CAMERA_SPEC.md)** | RTSP/UDP Stream Ingestion, Ring Frame Buffering & Ground Calibration |
| **[HELIOS_V1_CONFIG_SPEC.md](docs/HELIOS_V1_CONFIG_SPEC.md)** | YAML Declarations (`config/*.yaml`) & `.env` Variable Schema |
| **[HELIOS_V1_DASHBOARD_SPEC.md](docs/HELIOS_V1_DASHBOARD_SPEC.md)** | React 18 Dashboard, 12 Production Views & Glassmorphic Design System |
| **[HELIOS_V1_DATABASE_SPEC.md](docs/HELIOS_V1_DATABASE_SPEC.md)** | SQLite 20-Table Schema, Indexes, Foreign Keys & WAL Mode |
| **[HELIOS_V1_DATA_SCHEMA.md](docs/HELIOS_V1_DATA_SCHEMA.md)** | JSON Data Contracts, Pydantic Schemas & WebSocket Envelopes |
| **[HELIOS_V1_DEPLOYMENT_SPEC.md](docs/HELIOS_V1_DEPLOYMENT_SPEC.md)** | Startup Orchestration (`start_helios.sh`), Nginx Proxy & Systemd Daemons |
| **[HELIOS_V1_EVENT_SPEC.md](docs/HELIOS_V1_EVENT_SPEC.md)** | Canonical Event Types, Trajectory Threads & Micro-Narratives |
| **[HELIOS_V1_EVIDENCE_SPEC.md](docs/HELIOS_V1_EVIDENCE_SPEC.md)** | Forensic Snapshots, Bounding Box Crops & 64-bit dHash Deduplication |
| **[HELIOS_V1_MODEL_SPEC.md](docs/HELIOS_V1_MODEL_SPEC.md)** | Model Registry: YOLO26, ArcFace, CLIP, Roboflow, Gemini & Ollama |
| **[HELIOS_V1_PIPELINE_SPEC.md](docs/HELIOS_V1_PIPELINE_SPEC.md)** | 10-Stage Execution Loop & Real-Time Latency Budgets ($<85\text{ms}$) |
| **[HELIOS_V1_SETUP.md](docs/HELIOS_V1_SETUP.md)** | Environment Prerequisites, Virtualenv Setup & Database Seeding |
| **[HELIOS_V1_TEST_PLAN.md](docs/HELIOS_V1_TEST_PLAN.md)** | 28 Automated Pytest Suites, Verification Matrices & Edge Cases |

---

## 🚀 Quickstart Guide

### Prerequisites
- **Python**: 3.10+ (tested with Python 3.14)
- **Node.js**: 18+ & **npm**

---

### Single-Command Startup (Recommended)

Launch both the backend API and frontend dashboard simultaneously with health checking and automatic process management:

```bash
./start_helios.sh -k -o
```

**Common Flags:**
- `./start_helios.sh -o` — Open dashboard automatically in browser once services are healthy.
- `./start_helios.sh -k` — Automatically terminate any conflicting processes on ports 8000 or 5173.
- `./start_helios.sh -d` — Initialize and re-seed the SQLite database before start.
- `./start_helios.sh --backend-only` — Run only the FastAPI backend server.
- `./start_helios.sh --frontend-only` — Run only the React Vite dashboard.
- `./start_helios.sh --help` — Display full options.

---

### Manual Startup

#### Step 1: Start Backend
```bash
source .venv/bin/activate
uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```
> API starts at `http://127.0.0.1:8000`. Interactive documentation is at `http://127.0.0.1:8000/docs`.

#### Step 2: Start Dashboard
```bash
cd dashboard
npm install
npm run dev
```
> Dashboard starts at `http://localhost:5173`. Automatically connects to `ws://127.0.0.1:8000/api/v1/ws`.

---

## 🧪 Testing & Verification

Run the entire 28-file automated test suite covering all perception, tracking, biometrics, incident correlation, insights, and AI logic:

```bash
.venv/bin/pytest backend/tests
```

Run specific test subsystems:
```bash
# Face recognition & biometric association
.venv/bin/pytest backend/tests/unit/test_arcface.py backend/tests/unit/test_face_*.py

# Incident correlation engine
.venv/bin/pytest backend/tests/unit/test_incident_correlation.py

# Spatial fencing & loitering
.venv/bin/pytest backend/tests/unit/test_fencing.py backend/tests/unit/test_loitering.py

# 7-Signal Insights
.venv/bin/pytest backend/tests/unit/test_insights.py
```

---

## ⌨️ Keyboard Shortcuts & Operational Controls

- **`⌘ K` / `Ctrl K`**: Open Global Search & AI Chatbot modal.
- **Daily Brief**: Click the flame-accented Daily Brief button in the header.
- **Investigate Threat**: Click *Investigate* on any narrative card, incident row, or evidence crop.
- **Acknowledge Alert**: Single-click `Acknowledge` on any toast or banner alert.
