"""SQLite storage for the HELIOS V1 metadata entities."""
from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS cameras (camera_id TEXT PRIMARY KEY, name TEXT NOT NULL, source_type TEXT, stream_reference TEXT, location TEXT, status TEXT NOT NULL DEFAULT 'UNKNOWN', enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS zones (zone_id TEXT PRIMARY KEY, camera_id TEXT, name TEXT NOT NULL, zone_type TEXT NOT NULL, geometry TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, object_types TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS detections (detection_id TEXT PRIMARY KEY, camera_id TEXT NOT NULL, timestamp TEXT NOT NULL, object_type TEXT NOT NULL, confidence REAL NOT NULL, bounding_box TEXT NOT NULL, model_name TEXT, model_version TEXT, track_id TEXT, zone_id TEXT, attributes TEXT);
CREATE TABLE IF NOT EXISTS tracks (track_id TEXT PRIMARY KEY, camera_id TEXT NOT NULL, object_type TEXT NOT NULL, created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, status TEXT NOT NULL, average_confidence REAL NOT NULL, current_position TEXT, source_track_id TEXT, ended_at TEXT, detection_count INTEGER NOT NULL DEFAULT 1, max_confidence REAL, event_id TEXT, attributes TEXT, speed REAL DEFAULT 0.0, heading REAL DEFAULT 0.0, direction TEXT, movement_state TEXT, parent_track_id TEXT, reliability_score REAL DEFAULT 1.0, recovery_count INTEGER DEFAULT 0, reid_embedding TEXT);
CREATE TABLE IF NOT EXISTS track_recoveries (recovery_id TEXT PRIMARY KEY, original_track_id TEXT NOT NULL, restored_track_id TEXT NOT NULL, camera_id TEXT NOT NULL, timestamp TEXT NOT NULL, appearance_similarity REAL, position_distance REAL, motion_consistency REAL, iou_score REAL, composite_cost REAL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_track_rec_orig ON track_recoveries(original_track_id);
CREATE INDEX IF NOT EXISTS idx_track_rec_cam_time ON track_recoveries(camera_id, timestamp);
CREATE TABLE IF NOT EXISTS track_positions (track_id TEXT NOT NULL, timestamp TEXT NOT NULL, bounding_box TEXT NOT NULL, confidence REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, timestamp TEXT NOT NULL, camera_id TEXT, track_id TEXT, zone_id TEXT, severity TEXT NOT NULL, status TEXT NOT NULL, confidence REAL, description TEXT, created_at TEXT NOT NULL, object_type TEXT, ended_at TEXT, duration_seconds REAL, direction TEXT);
CREATE TABLE IF NOT EXISTS alerts (alert_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, timestamp TEXT NOT NULL, alert_type TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, acknowledged_at TEXT, acknowledged_by TEXT, resolved_at TEXT, resolved_by TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence (evidence_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, type TEXT NOT NULL, storage_reference TEXT NOT NULL, timestamp TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audio_sources (source_id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS system_logs (log_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, level TEXT NOT NULL, component TEXT NOT NULL, message TEXT NOT NULL, context TEXT);
CREATE TABLE IF NOT EXISTS track_movements (id INTEGER PRIMARY KEY AUTOINCREMENT, track_id TEXT NOT NULL, camera_id TEXT NOT NULL, object_type TEXT NOT NULL, timestamp TEXT NOT NULL, position TEXT NOT NULL, speed REAL NOT NULL DEFAULT 0.0, speed_unit TEXT NOT NULL DEFAULT 'px/s', speed_kmh REAL, direction TEXT NOT NULL, heading_deg REAL NOT NULL DEFAULT 0.0, movement_state TEXT NOT NULL, distance_travelled REAL NOT NULL DEFAULT 0.0, movement_change TEXT);
CREATE INDEX IF NOT EXISTS idx_track_movements_track_time ON track_movements(track_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_track_movements_cam_time ON track_movements(camera_id, timestamp);
CREATE TABLE IF NOT EXISTS loitering_sessions (session_id TEXT PRIMARY KEY, camera_id TEXT NOT NULL, zone_id TEXT NOT NULL, track_id TEXT NOT NULL, object_type TEXT NOT NULL, status TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT, duration_seconds REAL DEFAULT 0.0, movement_state TEXT NOT NULL, event_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_loitering_sessions_zone ON loitering_sessions(zone_id, status);
CREATE INDEX IF NOT EXISTS idx_loitering_sessions_track ON loitering_sessions(track_id);
CREATE TABLE IF NOT EXISTS incidents (incident_id TEXT PRIMARY KEY, title TEXT NOT NULL, incident_type TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL, confidence REAL NOT NULL, start_time TEXT NOT NULL, end_time TEXT, last_seen_at TEXT NOT NULL, duration_seconds REAL DEFAULT 0.0, primary_camera_id TEXT, primary_zone_id TEXT, primary_track_id TEXT, object_type TEXT, summary TEXT, correlation_reasons TEXT, score_breakdown TEXT, event_count INTEGER DEFAULT 1, acknowledged_at TEXT, acknowledged_by TEXT, resolved_at TEXT, resolved_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents(created_at DESC);
CREATE TABLE IF NOT EXISTS incident_events (incident_id TEXT NOT NULL, event_id TEXT NOT NULL, correlation_score REAL NOT NULL, correlation_factors TEXT, added_at TEXT NOT NULL, PRIMARY KEY (incident_id, event_id));
CREATE INDEX IF NOT EXISTS idx_incident_events_inc ON incident_events(incident_id);
CREATE TABLE IF NOT EXISTS observations (observation_id TEXT PRIMARY KEY, track_id TEXT NOT NULL, camera_id TEXT NOT NULL, zone_id TEXT, object_type TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, entry_time TEXT, exit_time TEXT, dwell_seconds REAL DEFAULT 0.0, movement_state TEXT NOT NULL DEFAULT 'STATIONARY', direction TEXT NOT NULL DEFAULT 'STATIONARY', speed REAL DEFAULT 0.0, distance_travelled REAL DEFAULT 0.0, zone_transitions TEXT, related_tracks TEXT, related_cameras TEXT, event_ids TEXT, evidence_ids TEXT, confidence REAL NOT NULL DEFAULT 0.9, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_obs_camera_time ON observations(camera_id, first_seen, last_seen);
CREATE INDEX IF NOT EXISTS idx_obs_zone_time ON observations(zone_id, first_seen, last_seen);
CREATE INDEX IF NOT EXISTS idx_obs_track ON observations(track_id);
CREATE INDEX IF NOT EXISTS idx_obs_obj_type ON observations(object_type);
CREATE INDEX IF NOT EXISTS idx_obs_movement ON observations(movement_state, direction);
CREATE INDEX IF NOT EXISTS idx_obs_dwell ON observations(dwell_seconds);
CREATE INDEX IF NOT EXISTS idx_obs_first_seen ON observations(first_seen DESC);
CREATE TABLE IF NOT EXISTS insights (insight_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, type TEXT NOT NULL, summary TEXT NOT NULL, score INTEGER NOT NULL, confidence REAL NOT NULL, priority TEXT NOT NULL, camera_ids TEXT, zone_ids TEXT, track_ids TEXT, event_ids TEXT, evidence_ids TEXT, signals TEXT, baseline_comparison TEXT, reasoning_factors TEXT, status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_insights_status ON insights(status);
CREATE INDEX IF NOT EXISTS idx_insights_priority ON insights(priority);
CREATE INDEX IF NOT EXISTS idx_insights_type ON insights(type);
CREATE INDEX IF NOT EXISTS idx_insights_created ON insights(created_at DESC);
CREATE TABLE IF NOT EXISTS insight_feedback (feedback_id TEXT PRIMARY KEY, insight_id TEXT NOT NULL, camera_id TEXT, operator_feedback TEXT NOT NULL, notes TEXT, timestamp TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_insight_feedback_ins ON insight_feedback(insight_id);
CREATE TABLE IF NOT EXISTS ai_investigations (investigation_id TEXT PRIMARY KEY, question TEXT NOT NULL, answer TEXT NOT NULL, confidence REAL, observation_ids TEXT, event_ids TEXT, evidence_ids TEXT, camera_ids TEXT, zone_ids TEXT, metadata TEXT, timestamp TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_ai_investigations_time ON ai_investigations(timestamp DESC);
CREATE TABLE IF NOT EXISTS registered_faces (person_id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT, notes TEXT, face_image_path TEXT, embedding TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_registered_faces_name ON registered_faces(name);
CREATE TABLE IF NOT EXISTS face_recognitions (recognition_id TEXT PRIMARY KEY, track_id TEXT, camera_id TEXT NOT NULL, person_id TEXT, person_name TEXT NOT NULL, status TEXT NOT NULL, similarity REAL DEFAULT 0.0, confidence REAL DEFAULT 0.0, bounding_box TEXT, snapshot_path TEXT, event_id TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, detection_count INTEGER NOT NULL DEFAULT 1, embedding TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_face_rec_status ON face_recognitions(status);
CREATE INDEX IF NOT EXISTS idx_face_rec_track ON face_recognitions(track_id);
CREATE INDEX IF NOT EXISTS idx_face_rec_cam ON face_recognitions(camera_id);
CREATE INDEX IF NOT EXISTS idx_face_rec_last_seen ON face_recognitions(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_face_rec_person ON face_recognitions(person_id);
CREATE TABLE IF NOT EXISTS behavioral_events (
    behavior_id TEXT PRIMARY KEY,
    event_id TEXT,
    track_id TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    zone_id TEXT,
    timestamp TEXT NOT NULL,
    behavior_type TEXT NOT NULL,
    anomaly_score INTEGER NOT NULL,
    movement_deviation REAL NOT NULL DEFAULT 0.0,
    spatial_deviation REAL NOT NULL DEFAULT 0.0,
    temporal_deviation REAL NOT NULL DEFAULT 0.0,
    dwell_deviation REAL NOT NULL DEFAULT 0.0,
    activity_density_deviation REAL NOT NULL DEFAULT 0.0,
    cross_camera_pattern REAL NOT NULL DEFAULT 0.0,
    baseline_deviation REAL NOT NULL DEFAULT 0.0,
    movement_state TEXT NOT NULL DEFAULT 'STATIONARY',
    speed REAL NOT NULL DEFAULT 0.0,
    direction TEXT NOT NULL DEFAULT 'STATIONARY',
    dwell_duration REAL NOT NULL DEFAULT 0.0,
    activity_density_data TEXT,
    baseline_comparison TEXT,
    anomaly_reasons TEXT,
    movement_data TEXT,
    related_cameras TEXT,
    related_events TEXT,
    evidence_ids TEXT,
    confidence REAL NOT NULL DEFAULT 0.90,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_beh_track ON behavioral_events(track_id);
CREATE INDEX IF NOT EXISTS idx_beh_camera ON behavioral_events(camera_id);
CREATE INDEX IF NOT EXISTS idx_beh_zone ON behavioral_events(zone_id);
CREATE INDEX IF NOT EXISTS idx_beh_score ON behavioral_events(anomaly_score DESC);
CREATE INDEX IF NOT EXISTS idx_beh_time ON behavioral_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_beh_type ON behavioral_events(behavior_type);
CREATE TABLE IF NOT EXISTS camera_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    condition TEXT NOT NULL,
    reliability_score INTEGER NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT,
    started_at TEXT NOT NULL,
    resolved_at TEXT,
    duration_seconds REAL DEFAULT 0.0,
    details TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cam_cond_camera ON camera_conditions(camera_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_cam_cond_type ON camera_conditions(condition);
CREATE TABLE IF NOT EXISTS camera_metrics_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    brightness REAL,
    contrast REAL,
    laplacian_variance REAL,
    white_pixel_ratio REAL,
    edge_density REAL,
    frame_difference REAL,
    vertical_edge_ratio REAL,
    patch_occlusion_ratio REAL,
    raw_condition TEXT,
    reliability_score INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cam_metrics_cam_time ON camera_metrics_history(camera_id, timestamp DESC);
CREATE TABLE IF NOT EXISTS camera_reliability (
    camera_id TEXT PRIMARY KEY,
    reliability_score INTEGER DEFAULT 100,
    condition TEXT DEFAULT 'CLEAR',
    condition_confidence REAL DEFAULT 1.0,
    condition_started_at TEXT,
    condition_details TEXT,
    updated_at TEXT NOT NULL
);
'''

def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    columns={row[1] for row in connection.execute("PRAGMA table_info(evidence)")}
    if "integrity_hash" not in columns: connection.execute("ALTER TABLE evidence ADD COLUMN integrity_hash TEXT")
    if "metadata" not in columns: connection.execute("ALTER TABLE evidence ADD COLUMN metadata TEXT")
    for table, additions in {
        "tracks": {"source_track_id":"TEXT", "ended_at":"TEXT", "detection_count":"INTEGER NOT NULL DEFAULT 1", "max_confidence":"REAL", "event_id":"TEXT", "attributes":"TEXT", "speed":"REAL DEFAULT 0.0", "heading":"REAL DEFAULT 0.0", "direction":"TEXT", "movement_state":"TEXT", "parent_track_id":"TEXT", "reliability_score":"REAL DEFAULT 1.0", "recovery_count":"INTEGER DEFAULT 0", "reid_embedding":"TEXT"},
        "events": {"object_type":"TEXT", "ended_at":"TEXT", "duration_seconds":"REAL", "direction":"TEXT", "attributes":"TEXT", "incident_id":"TEXT"},
        "alerts": {"incident_id":"TEXT"},
        "evidence": {"metadata":"TEXT"},
        "zones": {"object_types":"TEXT", "capacity":"INTEGER DEFAULT 10", "dwell_threshold_seconds":"REAL DEFAULT 20.0", "loitering_threshold_seconds":"REAL DEFAULT 50.0"},
    }.items():
        columns={row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for column, definition in additions.items():
            if column not in columns: connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    connection.commit()
    return connection



