# HELIOS V1 TEST PLAN & VERIFICATION MATRIX

## Quality Assurance, Unit Testing & Integration Verification Matrix

**Project:** HELIOS  
**Document:** Test Strategy, Automated Test Suites, Edge Case Coverage & CI Matrix  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Testing Strategy Overview

The HELIOS test architecture employs a pyramid methodology combining unit tests, mathematical algorithm verification, pipeline integration tests, and mock API client tests:
- **Zero Cloud Mocking Guarantee**: Unit and integration tests run entirely offline using synthetic frames, in-memory SQLite fixtures (`:memory:`), and deterministic mock responses.
- **Precision Ground Truth**: Validates exact geometric formulas (ray-casting PIP, vector cross-products, 7-signal composite scores, and 512-d ArcFace cosine math).
- **Execution Target**: Fast regression test suite executing $>100$ tests in under 30 seconds.

---

# 2. Automated Test Suite Inventory (`backend/tests/unit/`)

| Test File | Primary Focus / Subsystem Tested | Key Assertions / Invariants |
| :--- | :--- | :--- |
| **`test_arcface.py`** | MobileFaceNet model structure & embeddings | Verifies 512-dim embedding output, parameter count $<5\text{M}$, and cosine similarity bounds ($[-1, 1]$). |
| **`test_face_human_association.py`** | Spatial face-to-human body linkage | Validates upper 25% vertical torso containment rule and aspect ratio matching. |
| **`test_face_recognition.py`** | Recognition Manager & Roster Matching | Tests enrollment, similarity thresholding ($\ge 0.42$), and unknown face clustering. |
| **`test_face_api.py`** | REST `/api/v1/faces/*` endpoints | Verifies roster creation, raw photo uploads, face association, and snapshot serving. |
| **`test_fencing.py`** | Spatial Polygon & Ray-Casting PIP | Tests bottom-center foot coordinate projection, convex/concave polygon containment. |
| **`test_loitering.py`** | Loitering State Machine | Validates session creation (`PENDING` $\to$ `LOITERING`), dwell timing, and exit resolution. |
| **`test_movement_intelligence.py`** | Speed, Heading & Kinematics | Validates pixel-to-km/h calibration, 8-way cardinal headings, and hysteresis state switching. |
| **`test_people_density.py`** | Zone Density & Heatmaps | Asserts accurate real-time headcounts and dwell time distribution histograms. |
| **`test_incident_correlation.py`**| Multi-Signal Incident Correlator | Validates 6-factor affinity scoring, temporal decay windows, and incident lifecycle transitions. |
| **`test_insights.py`** | 7-Signal Composite Insights Layer | Verifies composite score formula weights, priority mapping, and operator feedback recording. |
| **`test_vehicle_intelligence.py`**| Zero-Shot CLIP & HSV Color Classifier | Verifies vehicle type classification (SUV, sedan, truck) and HSV color extraction. |
| **`test_vehicle_pipeline_integration.py`**| End-to-end vehicle pipeline | Verifies camera frame to vehicle observation, speed calculation, and database persistence. |
| **`test_ai_client.py`** | Unified AI Client Abstraction | Tests fallback chains across Gemini, OpenRouter, and local Ollama providers. |
| **`test_ai_ollama.py`** | Local Offline LLM Integration | Verifies local Ollama HTTP interaction, model default `qwen3:4b`, and offline safety. |
| **`test_ai_gemma_multimodal_investigation.py`**| Gemma Multimodal VLM Inspection | Tests two-turn reasoning flow, evidence crop inspection, and thinking token preservation. |
| **`test_ai_assistant.py`** | Natural Language Assistant (`⌘ K`) | Validates grounded entity extraction and tool-calling execution loops. |
| **`test_ai_tools.py`** | Operational Tool Registry | Asserts deterministic queries against `cameras`, `tracks`, `movements`, and `incidents`. |
| **`test_ai_day_brief.py`** | 24-Hour Day Brief Synthesizer | Validates generation of structured operational posture grades and threat summaries. |
| **`test_ai_narrator.py`** | Micro-Narrative Generator | Verifies natural-language descriptions of live tracking events. |
| **`test_alerts.py`** | Alert Rule Engine & Cooldowns | Tests severity rules, cooldown suppression ($60\text{s}$), and single/bulk acknowledgement. |
| **`test_events.py`** | Event Persistence & Lifecycle | Asserts correct database writes to `events` table and WebSocket message queuing. |
| **`test_evidence_dedup.py`** | Perceptual Hash Deduplication | Validates 64-bit dHash Hamming distance thresholding ($>85\%$ similarity suppression). |
| **`test_bounding_box_crop.py`** | High-Res Snapshot Cropping | Verifies coordinate normalization, aspect ratio retention, and edge clipping guards. |
| **`test_motion.py`** | Fast Motion Pre-Filter (MOG2) | Tests frame-differencing thresholding to bypass neural inference on static scenes. |
| **`test_roboflow_uav.py`** | Aerial Drone Incursion Detection | Asserts parsing of UAV bounding boxes and aerial threat alert generation. |
| **`test_tracking.py`** | IoU Tracker & Trajectory Smoothing | Verifies track lifecycle (`NEW` $\to$ `ACTIVE` $\to$ `ENDED`) and identity persistence across occlusions. |
| **`test_threads.py`** | Activity Threads & Cross-Camera Handoffs | Tests trajectory linkage across sequential camera vantage points. |
| **`test_zone_api.py`** | REST `/api/v1/zones/*` endpoints | Verifies CRUD operations for polygons, tripwires, and dwell thresholds. |

---

# 3. Running Test Suites

### Execute Full Test Suite
```bash
.venv/bin/pytest backend/tests
```

### Run with Verbose Output & Timing Summary
```bash
.venv/bin/pytest -v --durations=10 backend/tests
```

### Run Specific Subsystem Test Suites
```bash
# Biometrics & Face Recognition
.venv/bin/pytest backend/tests/unit/test_arcface.py backend/tests/unit/test_face_*.py

# Spatial Reasoning & Fencing
.venv/bin/pytest backend/tests/unit/test_fencing.py backend/tests/unit/test_loitering.py

# Incident Correlation & Insights
.venv/bin/pytest backend/tests/unit/test_incident_correlation.py backend/tests/unit/test_insights.py

# Multi-Provider AI & Investigation
.venv/bin/pytest backend/tests/unit/test_ai_*.py
```
