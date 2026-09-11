# HELIOS V1 INCIDENT CORRELATION SPECIFICATION

## System Specification: Multi-Signal Spatio-Temporal Incident Correlation

**Project:** HELIOS  
**Document:** Incident Correlation, Cross-Camera Threading & Incident Lifecycle Specification  
**Version:** 1.0 (Present Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Purpose

In conventional security environments, operators are inundated with disconnected event alerts (e.g., motion detected on Camera 1, fence breach on Camera 2, vehicle spotted on Camera 3).

The HELIOS Incident Correlation Engine (`IncidentCorrelator`) transforms fragmented alerts into cohesive, multi-camera, evolving security **Incidents**.
- **Probabilistic Signal Aggregation**: Correlates events across temporal proximity, camera spatial topology, zone overlaps, tracking continuity, object classification, and movement vectors.
- **Dynamic Incident Evolution**: Automatically associates new events to ongoing incidents instead of spawning duplicate operator alerts.
- **Complete Operational Lifecycle**: Manages status transitions (`DETECTED` $\to$ `CONFIRMED` $\to$ `ACTIVE` $\to$ `ACKNOWLEDGED` $\to$ `RESOLVED`).
- **Explainable Correlation Reasoning**: Preserves numeric score breakdowns and human-readable factors (e.g., *"Same track ID linked within 45s"*, *"Adjacent camera topological handoff"*).

---

# 2. Correlation Architecture & Pipeline

```
┌───────────────────────────────────────────────────────────┐
│               Security Events & Observations              │
│       (Perimeter Breach, ANPR, Face, UAV, Acoustic)       │
└─────────────────────────────┬─────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│                 Candidate Incident Search                 │
│      - Query active incidents within temporal window      │
│      - Default window: 180 seconds                        │
└─────────────────────────────┬─────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│              Multi-Dimensional Factor Scoring             │
│   S = w1·Time + w2·Track + w3·Topology + w4·Class + ...   │
└─────────────────────────────┬─────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
        Score >= Threshold          Score < Threshold
         (default: 0.52)                    │
                │                           ▼
                ▼                  ┌───────────────────┐
┌──────────────────────────────┐   │    Create New     │
│   Append Event to Incident   │   │  Incident Entity  │
│  - Update duration & bounds  │   │  (Status: DETECTED│
│  - Recalculate severity      │   └───────────────────┘
│  - Broadcast WebSocket sync  │
└──────────────────────────────┘
```

---

# 3. Probabilistic Scoring Model & Weights

When an event $E$ occurs, it is evaluated against active incident $I$ using a weighted sum of independent affinity factors:

$$S(E, I) = \sum_{k=1}^6 w_k \cdot f_k(E, I)$$

| Factor ($f_k$) | Weight ($w_k$) | Mathematical / Heuristic Formulation |
| :--- | :--- | :--- |
| **Track Continuity** | $0.35$ | $1.0$ if $E.\text{track\_id} \in I.\text{tracks}$; $0.8$ if child/parent track link; $0.0$ otherwise. |
| **Temporal Proximity** | $0.20$ | Exponential decay: $\exp\left(-\frac{\Delta t}{\tau}\right)$ where $\tau = 60\text{s}$. |
| **Camera Spatial Topology**| $0.18$ | $1.0$ if same camera; $0.75$ if topologically adjacent camera; $0.0$ otherwise. |
| **Zone / Area Match** | $0.12$ | $1.0$ if same zone or overlapping perimeter zone boundary. |
| **Object Class Affinity** | $0.10$ | $1.0$ if identical object type; $0.5$ if related (e.g., human + face); $0.0$ otherwise. |
| **Movement Direction Match** | $0.05$ | Cosine of angular heading difference: $\max\left(0, \cos(\theta_E - \theta_I)\right)$. |

If $S(E, I) \ge 0.52$, the event is merged into incident $I$. If multiple candidate incidents exceed the threshold, the event binds to the one with the maximum score.

---

# 4. Incident Lifecycle & Severity Dynamics

### 4.1 State Progression
1. **`DETECTED`**: Initial event triggered; awaiting confirmation or second supporting signal.
2. **`CONFIRMED`**: Multiple correlating events or single high-confidence critical alert confirmed.
3. **`ACTIVE`**: Incident in progress; continuous updates received within the timeout window.
4. **`ACKNOWLEDGED`**: Operator has viewed and taken operational ownership of the incident.
5. **`RESOLVED`**: Threat neutralized or cleared by operator, or auto-resolved after timeout without new events.

### 4.2 Dynamic Severity Escalation
An incident's severity is dynamically computed from its constituent events and confidence metrics:
$$\text{Severity} = \max_{e \in \text{Events}} (\text{Severity}(e)) \quad [\text{Escalated if event\_count} \ge 4]$$

---

# 5. Database Schema: `incidents` & `incident_events`

### 5.1 `incidents` Table
- `incident_id`: Primary key (`INC-...`).
- `title`: AI or heuristic title (e.g., *"Perimeter Breach & Unauthorized Vehicle at North Gate"*).
- `incident_type`: `PERIMETER_BREACH`, `INTRUSION`, `LOITERING`, `UAV_INCURSION`, `SUSPICIOUS_VEHICLE`.
- `severity`: `CRITICAL`, `HIGH`, `ELEVATED`, `MEDIUM`, `LOW`, `INFO`.
- `status`: `DETECTED`, `CONFIRMED`, `ACTIVE`, `ACKNOWLEDGED`, `RESOLVED`.
- `confidence`: Composite confidence score ($0.0 - 1.0$).
- `start_time`, `end_time`, `last_seen_at`, `duration_seconds`.
- `primary_camera_id`, `primary_zone_id`, `primary_track_id`, `object_type`.
- `summary`: Concise incident narrative.
- `correlation_reasons`: JSON array of explanatory text reasons.
- `score_breakdown`: JSON object storing numeric factor scores.
- `event_count`: Total correlated events.
- `acknowledged_at`, `acknowledged_by`, `resolved_at`, `resolved_by`.

### 5.2 `incident_events` Table
Composite primary key `(incident_id, event_id)` with `correlation_score`, `correlation_factors`, and `added_at`.

---

# 6. REST API Endpoints (`/api/v1/incidents`)

### `GET /api/v1/incidents`
Lists incidents with optional filtering by `status`, `severity`, `camera_id`, and pagination.

### `GET /api/v1/incidents/summary`
Returns high-level statistics: total active, critical count, mean resolution time, and 24-hour trends.

### `GET /api/v1/incidents/{incident_id}`
Returns complete incident dossier including correlated events list, camera thumbnails, tracks, and timeline.

### `POST /api/v1/incidents/{incident_id}/acknowledge`
Operator acknowledges the incident, logging timestamp and operator identifier.

### `POST /api/v1/incidents/{incident_id}/resolve`
Marks the incident resolved with operator closing notes.

---

# 7. Dashboard Integration: `IncidentsView`

- **Incident Triage Stream**: Priority-sorted cards showing severity badges, elapsed time counters, and camera previews.
- **Incident Timeline**: Chronological visual rail showing camera transitions, zone entries, and associated evidence thumbnails.
- **Correlation Factor Inspector**: Collapsible drawer showing exactly why events were linked together.
- **One-Click Action Bar**: Immediate access to `Acknowledge`, `Investigate with AI`, and `Export Incident Report`.
