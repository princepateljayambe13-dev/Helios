# HELIOS V1 INSIGHTS & SPATIAL INTELLIGENCE SPECIFICATION

## System Specification: 7-Signal Composite Scoring, Anomaly Detection & Insights Layer

**Project:** HELIOS  
**Document:** Intelligence Insights, Normality Baselines, Natural Language Investigation & Feedback  
**Version:** 1.0 (Present Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Purpose

The HELIOS Insights layer is the strategic reasoning engine that sits above low-level computer vision detections. It answers higher-order operational questions such as:
- *"What is unusual about facility activity right now compared to baseline normal?"*
- *"Are crowd densities or vehicle speeds deviating from historical patterns?"*
- *"How do spatial tracks across multiple cameras indicate pre-incident reconnaissance?"*

The system combines:
1. **7-Signal Composite Scoring Formula**: Balances anomaly, persistence, spatial significance, cross-camera correlations, density shifts, incident relevance, and camera sensor health into an explainable 0–100 score.
2. **Dynamic Baseline Normality Engine**: Continuously learns expected activity patterns (time-of-day, day-of-week) for each camera and zone.
3. **Rolling Activity Summaries**: Maintains rolling 5-minute, 1-hour, and 24-hour synthesized intelligence digests.
4. **Interactive Natural Language Investigator**: Allows operators to query complex spatial scenarios in plain English with streaming reasoning.
5. **Operator Feedback Loop (RLHF)**: Incorporates explicit operator feedback (`HELPFUL`, `FALSE_POSITIVE`, `IRRELEVANT`) into scoring recalibration.

---

# 2. The 7-Signal Composite Scoring Formula

Each candidate insight is evaluated across 7 normalized dimensions ($0.0 - 100.0$):

$$\text{InsightScore} = \sum_{i=1}^7 w_i \cdot S_i$$

| Signal ($S_i$) | Weight ($w_i$) | Operational Meaning |
| :--- | :--- | :--- |
| **Anomaly Score** ($S_1$) | $0.22$ | Deviation from learned baseline traffic, speed, or object mix. |
| **Persistence Score** ($S_2$) | $0.18$ | Duration of condition (e.g. repeated loitering, lingering target). |
| **Spatial Significance** ($S_3$) | $0.18$ | Security criticality of the zone (e.g., Vault vs Public Walkway). |
| **Cross-Camera Correlation** ($S_4$) | $0.15$ | Co-occurrence of entity sightings across multiple vantage points. |
| **Density / Activity Shift** ($S_5$) | $0.12$ | Sudden crowd surge or unusual void in typically occupied spaces. |
| **Incident Relevance** ($S_6$) | $0.10$ | Direct association with an active or confirmed security incident. |
| **Camera Reliability** ($S_7$) | $0.05$ | Stream quality factor (penalizes noisy or dropped frames). |

### 2.1 Priority Mapping
- **`CRITICAL`**: Score $\ge 80$
- **`HIGH`**: Score $65 - 79$
- **`MEDIUM`**: Score $45 - 64$
- **`LOW`**: Score $25 - 44$
- **`INFO`**: Score $< 25$

---

# 3. Baseline Normality & "What Changed" Engine

The `BaselineEngine` tracks rolling averages and standard deviations for:
- Mean detection count per 15-minute time bucket per camera.
- Object type distribution percentages (Human vs Vehicle vs UAV).
- Average velocity and loitering duration.

### 3.1 "What Changed" Analysis
When invoked (`GET /api/v1/insights/what-changed`), the engine calculates the Z-score of the current window compared to the historical baseline:
$$Z = \frac{x_{\text{current}} - \mu_{\text{baseline}}}{\sigma_{\text{baseline}}}$$
Any metric where $|Z| > 2.0$ ($p < 0.05$) is surfaced as an active anomaly card with plain-language explanation.

---

# 4. Natural Language Investigator

Operators can interact with the natural language investigation engine via:
- **`POST /api/v1/insights/investigate`**: Returns a structured answer with supporting observation IDs, camera citations, and confidence scores.
- **`POST /api/v1/insights/investigate/stream`**: Server-Sent Events (SSE) streaming reasoning steps in real time.

---

# 5. Database Schema: `insights` & `insight_feedback`

### 5.1 `insights` Table
| Column | Type | Description |
| :--- | :--- | :--- |
| `insight_id` | TEXT PRIMARY KEY | Unique ID (`INS-...`). |
| `timestamp` | TEXT NOT NULL | ISO 8601 creation timestamp. |
| `type` | TEXT NOT NULL | `ANOMALY`, `PATTERN`, `RECONNAISSANCE`, `SECURITY_AUDIT`. |
| `summary` | TEXT NOT NULL | Narrative explanation of the insight. |
| `score` | INTEGER NOT NULL | Composite score ($0 - 100$). |
| `confidence` | REAL NOT NULL | Confidence factor ($0.0 - 1.0$). |
| `priority` | TEXT NOT NULL | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`. |
| `camera_ids` | TEXT | JSON list of involved cameras. |
| `zone_ids` | TEXT | JSON list of involved zones. |
| `track_ids` | TEXT | JSON list of involved tracks. |
| `signals` | TEXT | JSON breakdown of the 7 individual signal scores. |
| `baseline_comparison` | TEXT | Baseline comparison details. |
| `status` | TEXT NOT NULL | `ACTIVE`, `ACKNOWLEDGED`, `DISMISSED`. |

### 5.2 `insight_feedback` Table
- `feedback_id`: UUID primary key.
- `insight_id`: Foreign key reference.
- `camera_id`: Optional target camera.
- `operator_feedback`: `HELPFUL`, `FALSE_POSITIVE`, `IRRELEVANT`.
- `notes`: Operator qualitative review notes.
- `timestamp`: UTC ISO 8601 timestamp.

---

# 6. REST API Endpoints (`/api/v1/insights`)

- `GET /api/v1/insights`: List ranked active insights with query filters.
- `GET /api/v1/insights/summary`: Executive intelligence summary of the day.
- `GET /api/v1/insights/what-changed`: Anomaly delta report comparing current hour to baseline.
- `GET /api/v1/insights/summaries/rolling`: Rolling 5-minute, 1-hour, and 24-hour synthesized digests.
- `POST /api/v1/insights/{insight_id}/feedback`: Submit operator feedback for scoring calibration.
- `POST /api/v1/insights/investigate`: Submit targeted query to the Natural Language Investigator.
- `GET /api/v1/insights/observations`: Consolidated spatio-temporal observation layer records.

---

# 7. Dashboard Integration: `InsightsView`

- **Insight Cards Grid**: Interactive cards displaying 7-signal radial/bar breakdowns, AI summaries, and priority tags.
- **"What Changed" Differential Bar**: Visual delta comparing current metrics vs normal baseline.
- **Natural Language Query Bar**: Interactive prompt console with suggested investigation seeds.
- **Feedback Controls**: Thumb up/down and review notes trigger real-time feedback submissions.
