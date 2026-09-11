# HELIOS V1 API SPECIFICATION

## REST & WebSocket API Reference

**Project:** HELIOS  
**Base URL:** `http://127.0.0.1:8000/api/v1`  
**WebSocket URL:** `ws://127.0.0.1:8000/api/v1/ws`  
**Interactive Docs:** `http://127.0.0.1:8000/docs` (OpenAPI Swagger UI)  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. System & Health Endpoints

### `GET /api/v1/system/health`
Returns system operational health, uptime, and database connectivity.
- **Response 200 OK**:
  ```json
  {
    "status": "HEALTHY",
    "timestamp": "2026-09-10T08:00:00Z",
    "database": "CONNECTED",
    "active_cameras": 4,
    "version": "1.0"
  }
  ```

### `GET /api/v1/system/summary`
Returns system-wide operational metrics: total cameras, active tracks, today's event count, active alerts, and unacknowledged incidents.

### `GET /api/v1/system/analytics`
Returns hourly event histograms and threat severity breakdowns for the dashboard charts.

### `POST /api/v1/system/clear-cache` (or `DELETE /api/v1/system/clear-cache`)
Clears in-memory frame buffers and temporary inference caches.

### `GET /api/v1/models`
Returns list of registered vision and AI models and their active status.

---

# 2. Camera Management Endpoints

### `GET /api/v1/cameras`
Lists all configured cameras with connection status, resolution, and stream type.

### `POST /api/v1/cameras` (Status 201)
Registers a new camera.
```json
{
  "camera_id": "CAM-05",
  "name": "East Gate Ingress",
  "source_type": "rtsp",
  "stream_reference": "rtsp://192.168.1.105:554/live",
  "location": "East Perimeter"
}
```

### `GET /api/v1/cameras/{camera_id}`
Returns details and operational parameters for a specific camera.

### `GET /api/v1/cameras/{camera_id}/health`
Returns real-time FPS, frame latency, and drop rate for the camera stream.

### `GET /api/v1/cameras/{camera_id}/snapshot`
Returns the latest decoded JPEG frame directly from the camera ring buffer.

### `POST /api/v1/cameras/{camera_id}/status`
Updates camera operational status (`ONLINE`, `OFFLINE`, `MAINTENANCE`).

---

# 3. Spatial Zones & Perimeter Fencing Endpoints

### `GET /api/v1/zones`
Lists all active polygon zones, tripwires, and perimeter boundaries.

### `POST /api/v1/zones` (Status 201)
Creates a new vector zone.
```json
{
  "zone_id": "ZONE-VAULT",
  "camera_id": "CAM-01",
  "name": "Secure Vault Perimeter",
  "zone_type": "RESTRICTED",
  "geometry": [[0.2, 0.3], [0.5, 0.3], [0.5, 0.7], [0.2, 0.7]],
  "object_types": ["human"]
}
```

### `PUT /api/v1/zones/{zone_id}`
Updates zone coordinates, enabled status, or monitored object classes.

### `DELETE /api/v1/zones/{zone_id}`
Removes a zone from the active surveillance configuration.

### `GET /api/v1/zones/density`
Returns real-time occupancy counts for each configured zone.

### `GET /api/v1/zones/dwell`
Returns dwell time statistics (average, max, total) per zone.

### `GET /api/v1/zones/loitering/history`
Returns active and historical loitering sessions.

### `PUT /api/v1/zones/{zone_id}/thresholds`
Sets custom dwell threshold seconds for loitering triggers in a specific zone.

---

# 4. Tracking, Movement & Kinematics Endpoints

### `GET /api/v1/tracks`
Lists currently active or historical object tracks.
- **Query Parameters**: `status` (`ACTIVE`, `ENDED`), `object_type` (`human`, `vehicle`), `camera_id`, `limit`.

### `GET /api/v1/tracks/{track_id}`
Returns track details, average confidence, bounding box, and lifespan.

### `GET /api/v1/tracks/{track_id}/movements`
Returns time-series movement log for a track: speed (km/h and px/s), heading angle, 8-way cardinal direction, and movement state.

### `GET /api/v1/tracks/{track_id}/thread` (or `/threads/{track_id}`)
Returns the complete cross-camera activity thread associated with the target track.

### `GET /api/v1/threads`
Lists active activity threads grouping related tracks.

### `DELETE /api/v1/tracks/ended`
Purges expired ended tracks from cache.

---

# 5. Events & Security Alerts Endpoints

### `GET /api/v1/events`
Lists security events with optional filters (`event_type`, `severity`, `camera_id`, `limit`, `offset`).

### `GET /api/v1/events/{event_id}`
Returns full event details, associated track IDs, evidence snapshots, and narrative.

### `DELETE /api/v1/events/clear`
Clears historical event records.

### `GET /api/v1/alerts`
Lists system alerts with priority filter (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`).

### `POST /api/v1/alerts/{alert_id}/acknowledge`
Acknowledges an alert, recording operator user ID and timestamp.

### `POST /api/v1/alerts/acknowledge-all`
Bulk acknowledges all currently pending alerts.

---

# 6. Evidence & Storage Endpoints

### `GET /api/v1/evidence`
Lists captured evidence records.

### `GET /api/v1/evidence/{evidence_id}`
Returns metadata for an evidence record (storage path, event ID, perceptual hash).

### `GET /api/v1/evidence/{evidence_id}/file`
Streams the JPEG binary image file with appropriate MIME headers (`image/jpeg`).

### `POST /api/v1/evidence` (Status 201)
Uploads an external evidence snapshot.

---

# 7. Incident Correlation Endpoints (`/api/v1/incidents`)

### `GET /api/v1/incidents`
Lists multi-signal correlated incidents. Filters: `status` (`DETECTED`, `CONFIRMED`, `ACTIVE`, `ACKNOWLEDGED`, `RESOLVED`), `severity`.

### `GET /api/v1/incidents/summary`
Returns aggregate statistics of current incidents and mean time to acknowledge.

### `GET /api/v1/incidents/{incident_id}`
Returns complete incident dossier including correlated events list, timeline, camera IDs, and factor scores.

### `POST /api/v1/incidents/{incident_id}/acknowledge`
Operator acknowledges the incident.

### `POST /api/v1/incidents/{incident_id}/resolve`
Marks incident resolved with operator closing notes.

---

# 8. Biometrics & Facial Recognition Endpoints (`/api/v1/faces`)

### `GET /api/v1/faces/summary`
Returns total recognitions, recognized count, unclassified count, and enrolled person count.

### `GET /api/v1/faces/recognitions`
Lists face detection sightings with similarity scores, names, and status (`RECOGNIZED` vs `UNCLASSIFIED`).

### `GET /api/v1/faces/persons`
Lists enrolled personnel roster with reference photos, roles, and clearance notes.

### `POST /api/v1/faces/persons` (Status 201)
Enrolls a new person via multipart image upload or base64 JSON payload.

### `POST /api/v1/faces/recognitions/{recognition_id}/associate`
Binds an unclassified face snapshot to an enrolled person.

### `DELETE /api/v1/faces/persons/{person_id}`
Deletes an enrolled person from the roster and purges in-memory feature embeddings.

### `GET /api/v1/faces/snapshots/{filename}`
Streams the high-resolution cropped face snapshot image.

---

# 9. Intelligence & Insights Endpoints (`/api/v1/insights`)

### `GET /api/v1/insights`
Lists ranked active insights with 7-signal composite score breakdowns.

### `GET /api/v1/insights/summary`
Returns an executive summary of facility patterns and top anomalies.

### `GET /api/v1/insights/what-changed`
Surfaces metrics that deviate by $|Z| > 2.0$ from historical baseline normality.

### `GET /api/v1/insights/summaries/rolling`
Returns rolling 5m, 1h, and 24h operational activity digests.

### `POST /api/v1/insights/{insight_id}/feedback`
Submits operator RLHF feedback (`HELPFUL`, `FALSE_POSITIVE`, `IRRELEVANT`).

### `POST /api/v1/insights/investigate`
Submits a natural language spatial query; returns grounded analysis with citations.

### `POST /api/v1/insights/investigate/stream`
Server-Sent Events (SSE) streaming real-time investigation reasoning tokens.

---

# 10. AI Assistant & Investigation Endpoints (`/api/v1/ai`)

### `POST /api/v1/ai/ask`
Interactive natural language chat endpoint supporting operational tools and grounded citations.
- **Request Body**:
  ```json
  {
    "message": "Summarize top threats from CAM-02 in the last 2 hours",
    "conversation_history": []
  }
  ```

### `GET /api/v1/ai/day-brief`
Synthesizes a structured 24-hour threat intelligence briefing.

### `POST /api/v1/ai/event/{event_id}/investigate`
Executes deep spatial-temporal investigation for a specific security event.

### `POST /api/v1/ai/evidence/{evidence_id}/investigate`
Multimodal visual analysis of an evidence snapshot using Gemma VLM.

---

# 11. Real-Time WebSocket (`/api/v1/ws`)

Connect to `ws://127.0.0.1:8000/api/v1/ws`.

### Broadcast Event Types
- **`observation`**: Real-time bounding box detection.
- **`track_update`**: Track coordinates, speed, and heading update.
- **`event`**: Newly triggered security event.
- **`alert`**: Security alert with priority level.
- **`incident_update`**: Real-time status update or event append on an incident.
- **`face_recognition`**: Face sighting with similarity score and name.
- **`camera_status`**: Camera online/offline state change.
