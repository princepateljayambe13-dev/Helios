# HELIOS V1 EVENT & THREAD SPECIFICATION

## System Specification: Canonical Security Events, Activity Threads & Narrative Generation

**Project:** HELIOS  
**Document:** Security Events, Trajectory Threads & Narrative Intelligence  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Purpose

The HELIOS Event Engine transforms continuous sensor streams and kinematic tracking coordinates into atomic, auditable, and correlated **Security Events**.

Core tenets:
- **Zero Ambiguity**: Every event records unambiguous timestamps, camera vantage point, associated track ID, and spatial zone reference.
- **Activity Threads**: Links sequential events from the same subject across camera handoffs into a singular chronological narrative thread.
- **Micro-Narratives**: Automatically generates natural-language operational summaries describing what occurred, where, and tactical relevance.

---

# 2. Event Types & Taxonomy

| Event Type | Trigger Origin | Default Severity | Description |
| :--- | :--- | :--- | :--- |
| **`PERIMETER_BREACH`** | Spatial Engine | `CRITICAL` | Object ground-point breached a `RESTRICTED` polygon boundary. |
| **`TRIPWIRE_CROSS`** | Spatial Engine | `HIGH` | Trajectory crossed a virtual line segment matching directional rule. |
| **`LOITERING_DETECTED`**| Spatial Engine | `HIGH` | Object remained inside monitored zone past dwell threshold. |
| **`UAV_INCURSION`** | Vision (Roboflow) | `CRITICAL` | Aerial drone detected in camera airspace. |
| **`SPEED_VIOLATION`** | Kinematics | `MEDIUM` | Object velocity exceeded zone speed limit (e.g. $>25\text{ km/h}$). |
| **`FACE_UNCLASSIFIED`** | Biometrics | `ELEVATED` | Unknown individual detected in secure facility sector. |
| **`FACE_RECOGNIZED`** | Biometrics | `INFO` | Confirmed identity matched with enrolled staff roster. |
| **`ACOUSTIC_THREAT`** | Audio Engine | `CRITICAL` | High-confidence gunshot, glass break, or scream detected. |

---

# 3. Activity Threads (`ActivityThreadsView`)

When an object travels through a facility, it may transition between camera views (`CAM-01` $\to$ `CAM-02` $\to$ `CAM-03`). The Activity Thread engine groups these sightings:
- **Thread ID**: Bound to parent entity track.
- **Thread Metrics**: Total lifespan, distance traveled (meters), average speed, and zone transitions.
- **Chronological Breadcrumb Trail**: Enables forensic investigators to replay an entity's complete path through the facility.

---

# 4. Database Schema: `events` Table

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `event_id` | TEXT | PRIMARY KEY | Unique ID (`EVT-...`). |
| `event_type` | TEXT | NOT NULL | One of the canonical event types. |
| `timestamp` | TEXT | NOT NULL | ISO 8601 UTC creation timestamp. |
| `camera_id` | TEXT | NOT NULL | Source camera stream. |
| `track_id` | TEXT | NULLABLE | Associated object track ID. |
| `zone_id` | TEXT | NULLABLE | Associated zone ID. |
| `severity` | TEXT | NOT NULL | `CRITICAL`, `HIGH`, `ELEVATED`, `MEDIUM`, `LOW`, `INFO`. |
| `status` | TEXT | NOT NULL | `NEW`, `PROCESSING`, `ACKNOWLEDGED`, `CLOSED`. |
| `confidence` | REAL | NOT NULL | Detection confidence score ($0.0 - 1.0$). |
| `description` | TEXT | NOT NULL | Natural-language event narrative. |
| `object_type` | TEXT | NULLABLE | `human`, `vehicle`, `uav`, `face`. |
| `duration_seconds`| REAL| DEFAULT 0.0 | Elapsed event duration. |
| `direction` | TEXT | NULLABLE | Cardinal heading (`N`, `SE`, etc.). |

---

# 5. REST API Endpoints (`/api/v1/events`)

- `GET /api/v1/events`: Lists events with query filters: `event_type`, `severity`, `camera_id`, `limit`, `offset`.
- `GET /api/v1/events/{event_id}`: Returns full event dossier with evidence snapshots and timeline.
- `DELETE /api/v1/events/clear`: Purges historical event records.
