# HELIOS V1 FACIAL RECOGNITION SPECIFICATION

## System Specification: Biometric Perception & Identity Intelligence

**Project:** HELIOS  
**Document:** Facial Recognition, Feature Extraction & Identity Association Specification  
**Version:** 1.0 (Present Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Purpose

The HELIOS Facial Recognition module provides enterprise-grade biometric perception, identity enrollment, edge-optimized feature extraction, and automated face-to-human tracking association.

The system is designed for privacy-respecting, high-throughput surveillance operations:
- **Local / Edge Optimization**: Uses a lightweight MobileFaceNet ArcFace architecture (<5M parameters) producing 512-dimensional normalized embeddings suitable for real-time CPU/GPU edge execution.
- **Continuous Association**: Maps detected face bounding boxes to corresponding human body tracks (`tracks` table) using spatial containment and vertical aspect ratio heuristics.
- **Roster Management**: Supports enrollments with reference portrait images or direct webcam / live feed snapshots, along with role tagging and operational security notes.
- **Unknown Face Clustering**: Tracks unclassified individuals across camera handoffs before operator identity confirmation.

---

# 2. Architecture & Component Hierarchy

```
                               ┌───────────────────────────┐
                               │  Camera Stream / Ingestion│
                               └─────────────┬─────────────┘
                                             │ Frame (RGB)
                                             ▼
                               ┌───────────────────────────┐
                               │     Face Detector         │
                               │ (Roboflow / YOLO Face)    │
                               └─────────────┬─────────────┘
                                             │ Cropped Face Bounding Box
                                             ▼
                               ┌───────────────────────────┐
                               │   ArcFace Feature Extractor│
                               │   (MobileFaceNet 512-d)   │
                               └─────────────┬─────────────┘
                                             │ Normalized Embedding Vector
                                             ▼
                       ┌───────────────────────────────────────────┐
                       │       Recognition & Matching Engine       │
                       │  - Cosine Distance vs Registered Roster   │
                       │  - Thresholding (Similarity >= 0.42)      │
                       └─────────────┬─────────────────────────────┘
                                     │
           ┌─────────────────────────┴──────────────────────────┐
           ▼                                                    ▼
┌───────────────────────────────┐              ┌───────────────────────────────┐
│     Spatial Association       │              │    Persistence & Streaming    │
│  - Upper 25% human torso match│              │  - SQLite `face_recognitions` │
│  - Bounding Box Containment   │              │  - Evidence Snapshot Storage  │
│  - Track ID Linkage           │              │  - WebSocket `/api/v1/ws`     │
└───────────────────────────────┘              └───────────────────────────────┘
```

---

# 3. Model Architecture: MobileFaceNet ArcFace

### 3.1 Network Topology & Specifications
- **Base Architecture**: MobileFaceNet modified with ArcFace (Additive Angular Margin Loss) head.
- **Embedding Dimension**: 512 floats ($L_2$ normalized to unit hypersphere).
- **Input Dimension**: $112 \times 112$ RGB (or $128 \times 128$ normalized standard crop).
- **Parameter Count**: ~3.4 million parameters (fits within edge devices, Jetson Orin Nano, and CPU environments).
- **Device Support**: CUDA, Apple Silicon MPS, or Fallback CPU.

### 3.2 Matching Metric: Cosine Similarity
Given two normalized feature vectors $\mathbf{u}, \mathbf{v} \in \mathbb{R}^{512}$ with $\|\mathbf{u}\|_2 = \|\mathbf{v}\|_2 = 1$:
$$\text{Similarity}(\mathbf{u}, \mathbf{v}) = \mathbf{u} \cdot \mathbf{v} = \sum_{i=1}^{512} u_i v_i$$

### 3.3 Decision Thresholds
| Metric | Threshold | Operational Interpretation |
| :--- | :--- | :--- |
| **Match Threshold** | $\ge 0.42$ | Confirmed identity match with enrolled profile. |
| **High Confidence Match** | $\ge 0.65$ | Automated badge/roster confirmation without operator alert. |
| **Ambiguous / Watchlist** | $0.35 - 0.41$ | Flagged for operator secondary review; marked `UNCLASSIFIED`. |
| **Non-Match** | $< 0.35$ | Novel unclassified face; new tracking entity registered. |

---

# 4. Face-to-Human Spatial Association

Surveillance feeds often detect human bodies (YOLO26 detector) and faces (Face detector) independently. The `FaceAssociationEngine` links face detections to active human tracks:

### 4.1 Containment & Overlap Heuristics
1. **Vertical Constraint**: A human face must lie within the upper $25\%$ of the vertical extent of the human bounding box:
   $$y_{\text{face, center}} \le y_{\text{human, min}} + 0.35 \times h_{\text{human}}$$
2. **Horizontal Alignment**: The horizontal center of the face must fall within the horizontal boundaries of the human body box:
   $$x_{\text{human, min}} \le x_{\text{face, center}} \le x_{\text{human, max}}$$
3. **Scale Consistency**: The face box area cannot exceed $30\%$ of the human body area:
   $$\text{Area}_{\text{face}} \le 0.30 \times \text{Area}_{\text{human}}$$

If all constraints pass, the face recognition record is enriched with `track_id = human_track.track_id`, enabling real-time identity labeling across trajectory paths and activity threads.

---

# 5. Database Schema & Persistence

### 5.1 `registered_faces` Table
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `person_id` | TEXT | PRIMARY KEY | Unique UUID or alphanumeric ID (e.g., `PER-001`). |
| `name` | TEXT | NOT NULL | Full name of enrolled subject. |
| `role` | TEXT | NULLABLE | Role (e.g., `Staff`, `Visitor`, `VIP`, `Restricted`). |
| `notes` | TEXT | NULLABLE | Operational notes, clearance level, or restrictions. |
| `face_image_path`| TEXT | NULLABLE | Relative path to reference enrolled portrait image. |
| `embedding` | TEXT | NOT NULL | JSON-serialized 512-float vector. |
| `created_at` | TEXT | NOT NULL | ISO 8601 UTC creation timestamp. |
| `updated_at` | TEXT | NOT NULL | ISO 8601 UTC modification timestamp. |

### 5.2 `face_recognitions` Table
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `recognition_id`| TEXT | PRIMARY KEY | Unique recognition ID (`REC-...`). |
| `track_id` | TEXT | NULLABLE | Associated human track ID. |
| `camera_id` | TEXT | NOT NULL | Source camera stream. |
| `person_id` | TEXT | NULLABLE | Foreign key to `registered_faces` if identified. |
| `person_name` | TEXT | NOT NULL | Name or `"Unknown Person"`. |
| `status` | TEXT | NOT NULL | `RECOGNIZED` or `UNCLASSIFIED`. |
| `similarity` | REAL | NOT NULL | Highest similarity score ($0.0 - 1.0$). |
| `confidence` | REAL | NOT NULL | Detector confidence. |
| `bounding_box` | TEXT | NULLABLE | JSON `[x, y, w, h]` normalized coordinates. |
| `snapshot_path` | TEXT | NOT NULL | Disk path to cropped face snapshot in evidence storage. |
| `event_id` | TEXT | NULLABLE | Associated security event ID. |
| `first_seen` | TEXT | NOT NULL | ISO 8601 timestamp. |
| `last_seen` | TEXT | NOT NULL | ISO 8601 timestamp. |
| `detection_count`| INTEGER| DEFAULT 1 | Frequency of continuous detections. |

---

# 6. REST API Endpoints (`/api/v1/faces`)

### `GET /api/v1/faces/summary`
Returns aggregate statistics of the facial recognition engine.
```json
{
  "total_recognitions": 142,
  "recognized_count": 89,
  "unclassified_count": 53,
  "registered_persons_count": 12
}
```

### `GET /api/v1/faces/recognitions`
Lists recent recognition events. Supports query filters: `camera_id`, `status` (`RECOGNIZED` / `UNCLASSIFIED`), `limit`, `offset`.

### `POST /api/v1/faces/persons`
Enrolls a new identity. Accepts multipart form data with image file or JSON body with base64-encoded image:
- `name` (string, required)
- `role` (string, optional)
- `notes` (string, optional)
- `file` (binary image file)

### `POST /api/v1/faces/recognitions/{recognition_id}/associate`
Associates an unclassified face detection snapshot directly to an existing registered person or creates a new person roster entry from the snapshot.

### `DELETE /api/v1/faces/persons/{person_id}`
Removes a person from the active enrolled roster and purges reference embeddings from memory cache.

### `GET /api/v1/faces/snapshots/{filename}`
Streams the high-resolution face crop thumbnail directly to the dashboard interface.

---

# 7. Dashboard Integration: `FacialRecognitionView`

The frontend operational view provides:
1. **Summary Stat Strip**: Total recognitions, Identified matches, Unclassified captures, and Enrolled subjects.
2. **Real-time Live Stream Grid**: Active face sightings dynamically streaming via WebSocket broadcasts (`face_recognition` event type).
3. **Face Association Drawer**: Operator modal to inspect high-resolution crops, view similarity scores, and bind unknown sightings to identity roster records.
4. **Enrolled Roster Directory**: Complete management UI to upload portraits, edit security roles, and view sighting histories across all cameras.
