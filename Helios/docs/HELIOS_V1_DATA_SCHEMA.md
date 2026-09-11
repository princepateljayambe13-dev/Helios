# HELIOS V1 DATA SCHEMA SPECIFICATION

## Data Schemas, Domain Entities & Pydantic Serialization Models

**Project:** HELIOS  
**Document:** JSON Schemas, Pydantic Models & REST Serialization Contracts  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Core Perception Schemas

### 1.1 Detection Object
```json
{
  "detection_id": "DET-4A20D9DC",
  "camera_id": "CAM-01",
  "timestamp": "2026-09-10T08:15:30.120Z",
  "object_type": "human",
  "confidence": 0.92,
  "bounding_box": [0.35, 0.42, 0.12, 0.28],
  "model_name": "yolo26s",
  "track_id": "TRK-104",
  "zone_id": "ZONE-01"
}
```

### 1.2 Track Object
```json
{
  "track_id": "TRK-104",
  "camera_id": "CAM-01",
  "object_type": "human",
  "status": "ACTIVE",
  "average_confidence": 0.89,
  "current_position": [0.41, 0.70],
  "speed": 8.4,
  "speed_unit": "km/h",
  "heading": 135.0,
  "direction": "SE",
  "movement_state": "WALKING",
  "detection_count": 48,
  "first_seen": "2026-09-10T08:14:50Z",
  "last_seen_at": "2026-09-10T08:15:30Z"
}
```

---

# 2. Kinematics & Movement Schemas

### 2.1 Track Movement Item
```json
{
  "id": 142,
  "track_id": "TRK-104",
  "camera_id": "CAM-01",
  "timestamp": "2026-09-10T08:15:28Z",
  "position": [0.40, 0.68],
  "speed_kmh": 8.4,
  "speed_px_s": 95.2,
  "direction": "SE",
  "heading_deg": 135.0,
  "movement_state": "WALKING",
  "distance_travelled": 24.5,
  "movement_change": "SPEED_INCREASED"
}
```

---

# 3. Incident Correlation Schemas

### 3.1 Incident Dossier
```json
{
  "incident_id": "INC-009",
  "title": "Perimeter Incursion & Unauthorized Ingress at North Gate",
  "incident_type": "PERIMETER_BREACH",
  "severity": "CRITICAL",
  "status": "ACTIVE",
  "confidence": 0.88,
  "start_time": "2026-09-10T08:10:00Z",
  "last_seen_at": "2026-09-10T08:15:30Z",
  "duration_seconds": 330.0,
  "primary_camera_id": "CAM-01",
  "primary_zone_id": "ZONE-01",
  "primary_track_id": "TRK-104",
  "object_type": "human",
  "summary": "Track TRK-104 breached North Gate restricted perimeter zone and moved rapidly towards building egress.",
  "correlation_reasons": [
    "Identical track ID continuity within 45s",
    "Spatial zone boundary violation in Zone-01",
    "Topologically adjacent camera handoff CAM-01 to CAM-02"
  ],
  "score_breakdown": {
    "track_continuity": 1.0,
    "temporal_proximity": 0.95,
    "spatial_topology": 0.88,
    "zone_match": 1.0,
    "object_affinity": 1.0,
    "composite_score": 0.92
  },
  "event_count": 4,
  "events": [
    {
      "event_id": "EVT-881",
      "event_type": "PERIMETER_BREACH",
      "timestamp": "2026-09-10T08:10:05Z",
      "severity": "HIGH",
      "camera_id": "CAM-01"
    }
  ]
}
```

---

# 4. Biometric & Facial Recognition Schemas

### 4.1 Face Recognition Record
```json
{
  "recognition_id": "REC-779CB8FF",
  "track_id": "TRK-104",
  "camera_id": "CAM-01",
  "person_id": "PER-004",
  "person_name": "Alexander Vance",
  "status": "RECOGNIZED",
  "similarity": 0.78,
  "confidence": 0.94,
  "bounding_box": [0.42, 0.44, 0.05, 0.07],
  "snapshot_path": "storage/evidence/face/FAC-779CB8FF.jpg",
  "first_seen": "2026-09-10T08:15:10Z",
  "last_seen": "2026-09-10T08:15:30Z",
  "detection_count": 12
}
```

---

# 5. Strategic Insights Schemas

### 5.1 Insight Entity
```json
{
  "insight_id": "INS-20260910-01",
  "timestamp": "2026-09-10T08:15:00Z",
  "type": "ANOMALY",
  "summary": "Vehicle traffic at North Gate is 240% above baseline average for Thursday morning.",
  "score": 82,
  "confidence": 0.91,
  "priority": "CRITICAL",
  "camera_ids": ["CAM-01", "CAM-03"],
  "signals": {
    "anomaly": 85.0,
    "persistence": 72.0,
    "spatial_significance": 80.0,
    "cross_camera_correlation": 68.0,
    "density_activity_change": 92.0,
    "incident_relevance": 75.0,
    "camera_reliability": 98.0
  },
  "status": "ACTIVE"
}
```

---

# 6. Real-Time WebSocket Event Envelope

All messages dispatched across `ws://127.0.0.1:8000/api/v1/ws` adhere to this contract:
```json
{
  "type": "alert",
  "timestamp": "2026-09-10T08:15:30.500Z",
  "data": {
    "alert_id": "ALT-902",
    "alert_type": "PERIMETER_BREACH",
    "severity": "CRITICAL",
    "message": "Immediate perimeter breach detected in Zone-01",
    "camera_id": "CAM-01",
    "track_id": "TRK-104"
  }
}
```
