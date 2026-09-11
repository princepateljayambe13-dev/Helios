# HELIOS V1 PRD — Product Requirements Document

**Project:** HELIOS  
**Full Name:** Intelligent Surveillance & Threat Intelligence Operational Platform  
**Problem Statement:** SH26187  
**Version:** V1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

## 1. Product Overview

HELIOS is an enterprise-grade, software-defined intelligent surveillance and threat intelligence platform designed to transform standard CCTV and sensor infrastructure into an autonomous, real-time security operations center.

The platform continuously ingests multi-format video and audio streams, executing low-latency perception, object tracking, spatial reasoning, biometrics, incident correlation, and generative AI investigation.

HELIOS operates under the core design tenet:

> **"Every meaningful observation becomes a traceable, time-stamped, cross-correlated intelligence event with human-in-the-loop oversight."**

---

## 2. Core Problem & Market Opportunity

Conventional security control rooms suffer from critical vulnerabilities:
1. **Operator Fatigue & Cognitive Overload**: Human operators miss up to 95% of subtle scene anomalies after 20 minutes of multi-monitor monitoring.
2. **Fragmented Sensor Silos**: Camera feeds, audio sensors, and access logs operate independently, failing to correlate multi-stage incursions.
3. **Proprietary Hardware Lock-In**: Upgrading surveillance traditionally required replacing cameras with proprietary edge devices at extreme capital expense.
4. **Delayed Post-Incident Forensics**: Investigations require manual scrubbing through hours of video, rather than instant natural-language retrieval and automated timeline reconstruction.

HELIOS solves these challenges through a modular, software-only intelligence layer compatible with any RTSP, UDP, or USB video source.

---

## 3. Product Scope & Functional Modules

### 3.1 Multi-Modal Perception & Object Classification
- **Core Vision**: Real-time object detection (Human, Vehicle, UAV, License Plate ANPR) using YOLO26 and Roboflow specialized models.
- **Biometric Intelligence**: Edge-deployable ArcFace MobileFaceNet generating 512-dimensional embeddings for real-time facial recognition and identity roster verification.
- **Vehicle Intelligence**: Zero-shot OpenAI CLIP classification (SUV, sedan, truck, van, taxi, bus, motorcycle) combined with HSV color extraction and ANPR OCR.
- **Acoustic Detection**: Ingestion of audio streams for acoustic spike detection (gunshots, breaking glass, screams, vehicle revs).

### 3.2 Spatial Reasoning & Dynamic Fencing
- **Arbitrary Vector Polygons**: Polygon zones defined in normalized $[0.0, 1.0]$ screen coordinates.
- **Ground-Contact Tracking**: Evaluates the bottom-center foot position of objects, preventing false alarms from shadows or elevated perspective bounding boxes.
- **Virtual Tripwires**: Bi-directional and directional boundary crossing detection.
- **Loitering Engine**: Automatic state-machine tracking of dwell times and loitering sessions.

### 3.3 Movement & Speed Intelligence
- **Speed Estimation**: Pixel-to-metric velocity calibration delivering real-time km/h and px/s metrics.
- **Cardinal Direction Estimation**: 8-way heading classification (N, NE, E, SE, S, SW, W, NW).
- **Hysteresis Movement Classification**: Suppresses state chatter across STATIONARY, WALKING, RUNNING, and LOITERING states.

### 3.4 Cross-Camera Incident Correlation
- **Probabilistic Correlation**: Groups discrete events across adjacent cameras, spatial zones, and temporal windows into unified **Incidents**.
- **Incident Lifecycle**: Comprehensive state management (`DETECTED` $\to$ `CONFIRMED` $\to$ `ACTIVE` $\to$ `ACKNOWLEDGED` $\to$ `RESOLVED`).
- **Audit Trails**: Operator acknowledgement, resolution notes, and audit logging.

### 3.5 7-Signal Insights & Anomaly Detection
- **Composite Scoring**: Evaluates candidate observations across Anomaly, Persistence, Spatial Significance, Cross-Camera Correlation, Density/Activity Shift, Incident Relevance, and Camera Reliability ($0-100$ scale).
- **Normality Baselines**: Rolling hourly and diurnal baselines for each camera/zone.
- **"What Changed" Differential Engine**: Instant Z-score anomaly surfacing.
- **Operator RLHF Feedback**: Captures helpfulness ratings for automated scoring calibration.

### 3.6 Multi-Provider Generative AI Assistant & Investigation
- **Multi-LLM / VLM Support**: Google Gemini 1.5 Flash/Pro, OpenRouter (with reasoning token preservation), and local offline Ollama (`qwen3:4b`).
- **Gemma Multimodal Investigation**: Deep visual reasoning over high-resolution evidence snapshots.
- **Automated Daily Briefings**: Daily operational syntheses of 24-hour threat activity.
- **Operational Tool Use**: 10+ backend tools powering the `⌘ K` Global Search & AI Assistant modal.

### 3.7 High-Fidelity Glassmorphic Dashboard
- **12 Operational Views**: Overview, Live Feeds, Perimeter Fencing, Events (All / Tracked / Zone), Insights, Incidents, Alerts & Audit Logs, Evidence Gallery, Activity Threads, Facial Recognition, Settings, and Authentication.
- **Continuous WebSocket Stream**: Zero page-refresh architecture with sub-second telemetry updates.
- **Web Audio Engine**: Distinctive priority audio chimes for operational alerts.

---

## 4. User Personas & Core Workflows

| Persona | Primary Goal | Key HELIOS Workflow |
| :--- | :--- | :--- |
| **SOC Operator** | Immediate threat triage and verification. | Monitors Status Banner, receives real-time audio chimes, acknowledges alerts, and investigates live incident timelines. |
| **Security Supervisor**| Facility posture management and compliance. | Reviews daily AI briefings (`/api/v1/ai/day-brief`), audits incident resolution notes, and manages camera/zone configurations. |
| **Forensic Investigator**| Rapid evidence collection and suspect tracking. | Uses Natural Language Investigator (`⌘ K`), performs cross-camera track lookups, and exports evidence dossiers. |
| **System Administrator**| Sensor calibration and deployment health. | Manages `./start_helios.sh` runtime, verifies stream latencies, inspects model inference health, and enrolls facial rosters. |

---

## 5. Success Metrics & Non-Functional Requirements

- **Latency**: Perception-to-dashboard alert delivery under $500\text{ms}$.
- **Throughput**: Support for 4+ concurrent HD streams on edge hardware with CPU fallback.
- **Reliability**: 99.9% uptime with automated process resurrection and WebSocket auto-reconnect.
- **Privacy & Security**: Local-first processing; facial biometric embeddings stored as non-reversible mathematical vectors; full SQLite audit trail.
