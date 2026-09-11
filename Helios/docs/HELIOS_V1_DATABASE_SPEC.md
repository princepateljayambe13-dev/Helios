# HELIOS V1 DATABASE SPECIFICATION

## SQLite Relational Schema, Indexes & Persistence Architecture

**Project:** HELIOS  
**Database:** SQLite 3.37+ (WAL Mode Enabled)  
**File Location:** `data/helios.db`  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Database Architecture & Pragmas

HELIOS uses an embedded SQLite database engineered for high write concurrency, low latency, and zero-maintenance edge deployment:
- **Write-Ahead Logging (`PRAGMA journal_mode=WAL;`)**: Enables concurrent read operations without blocking or being blocked by active video pipeline writes.
- **Synchronous Normal (`PRAGMA synchronous=NORMAL;`)**: Provides optimal balance between write throughput and data integrity across system power cycles.
- **Foreign Key Enforcement (`PRAGMA foreign_keys=ON;`)**: Guarantees relational integrity between cameras, tracks, events, incidents, and evidence.
- **In-Memory Thread-Safe Connection Pooling**: Managed via `backend/app/database/connection.py`.

---

# 2. Complete 20-Table Relational Schema

### 2.1 Sensor & Ingestion Tables
1. **`cameras`**: Camera definitions, RTSP/UDP stream references, physical locations, operational status (`ONLINE`, `OFFLINE`), and pixel-to-meter calibrations.
2. **`audio_sources`**: Ingested audio sensors and status.

### 2.2 Spatial & Perimeter Tables
3. **`zones`**: Arbitrary $N$-point polygon coordinates (normalized JSON array), zone types (`RESTRICTED`, `PERIMETER_FENCE`, `TRIPWIRE`, `LOITERING`), and monitored classes.
4. **`loitering_sessions`**: Persistent loitering state sessions (`session_id`, `camera_id`, `zone_id`, `track_id`, `status`, `start_time`, `end_time`, `duration_seconds`, `movement_state`).

### 2.3 Computer Vision, Tracking & Kinematics Tables
5. **`detections`**: Raw perception detections (`detection_id`, `camera_id`, `timestamp`, `object_type`, `confidence`, `bounding_box`, `model_name`, `track_id`, `zone_id`).
6. **`tracks`**: Persistent object trajectories (`track_id`, `camera_id`, `object_type`, `status`, `average_confidence`, `speed`, `heading`, `direction`, `movement_state`, `parent_track_id`).
7. **`track_positions`**: Time-series bounding box trajectory coordinates for smoothing and history playback.
8. **`track_movements`**: Detailed movement logs (`track_id`, `speed_kmh`, `direction`, `heading_deg`, `movement_state`, `distance_travelled`, `movement_change`).

### 2.4 Events, Alerts & Incident Tables
9. **`events`**: Canonical security events (`event_id`, `event_type`, `camera_id`, `track_id`, `zone_id`, `severity`, `status`, `description`, `duration_seconds`, `direction`).
10. **`alerts`**: High-priority operator notifications (`alert_id`, `event_id`, `alert_type`, `severity`, `status`, `message`, `acknowledged_at`, `acknowledged_by`).
11. **`incidents`**: Correlated multi-event incident entities (`incident_id`, `title`, `incident_type`, `severity`, `status`, `confidence`, `start_time`, `end_time`, `summary`, `correlation_reasons`, `score_breakdown`, `event_count`).
12. **`incident_events`**: Mapping table binding events to incidents (`incident_id`, `event_id`, `correlation_score`, `correlation_factors`, `added_at`).

### 2.5 Biometric & Facial Recognition Tables
13. **`registered_faces`**: Roster of enrolled individuals (`person_id`, `name`, `role`, `notes`, `face_image_path`, `embedding` [512 floats serialized as JSON]).
14. **`face_recognitions`**: Log of detected faces (`recognition_id`, `track_id`, `camera_id`, `person_id`, `person_name`, `status`, `similarity`, `confidence`, `bounding_box`, `snapshot_path`).

### 2.6 Strategic Insights & Strategic Reasoning Tables
15. **`observations`**: High-level consolidated spatio-temporal entity observations (`observation_id`, `track_id`, `camera_id`, `zone_id`, `dwell_seconds`, `movement_state`, `speed`).
16. **`insights`**: 7-signal composite intelligence insights (`insight_id`, `type`, `summary`, `score`, `confidence`, `priority`, `signals`, `baseline_comparison`, `status`).
17. **`insight_feedback`**: Operator evaluation feedback (`feedback_id`, `insight_id`, `operator_feedback`, `notes`, `timestamp`).
18. **`ai_investigations`**: Natural language investigation question/answer audit logs (`investigation_id`, `question`, `answer`, `confidence`, `metadata`).

### 2.7 Evidence & System Audit Tables
19. **`evidence`**: Forensic image and video captures (`evidence_id`, `event_id`, `type`, `storage_reference`, `timestamp`).
20. **`system_logs`**: System audit and telemetry log events (`log_id`, `timestamp`, `level`, `component`, `message`, `context`).

---

# 3. Database Indexes & Query Optimization

To maintain sub-millisecond query response times under high event volume, the schema defines strategic indexes:
```sql
CREATE INDEX IF NOT EXISTS idx_tracks_camera_status ON tracks(camera_id, status);
CREATE INDEX IF NOT EXISTS idx_detections_track ON detections(track_id);
CREATE INDEX IF NOT EXISTS idx_events_camera_timestamp ON events(camera_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incident_events_event ON incident_events(event_id);
CREATE INDEX IF NOT EXISTS idx_recognitions_status ON face_recognitions(status);
CREATE INDEX IF NOT EXISTS idx_movements_track ON track_movements(track_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_loitering_status ON loitering_sessions(status);
```

---

# 4. Database Migration & Initialization (`scripts/init_database.py`)

Executing `python scripts/init_database.py` executes the declarative DDL script idempotently (`CREATE TABLE IF NOT EXISTS`), builds all indexes, and seeds default cameras and zones from configuration files.
