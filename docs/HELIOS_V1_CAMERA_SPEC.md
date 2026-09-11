# HELIOS V1 CAMERA INGESTION SPECIFICATION

## System Specification: Multi-Stream Video Ingestion, Buffering & Health Watchdog

**Project:** HELIOS  
**Document:** Camera Management, Streaming Protocols & Frame Buffer Specification  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Purpose

The HELIOS Camera Subsystem is responsible for acquiring, decoding, buffering, and monitoring continuous video streams from heterogeneous surveillance hardware.

Key architectural features:
- **Protocol Agnostic**: Ingests RTSP (H.264/H.265), UDP MPEG-TS (used in edge testing with FFmpeg), USB/V4L2, and local video loop files.
- **Ring Frame Buffering**: Maintains a memory-efficient circular buffer per camera for instantaneous snapshot extraction and zero-latency inference reads.
- **Automated Health Watchdog**: Monitors stream frame rates, detects dropped connections, and triggers auto-reconnect loops.
- **Perspective Calibration**: Stores metric calibration factors per camera enabling physical speed calculations (km/h).

---

# 2. Ingestion Pipeline & Protocol Support

```
   ┌─────────────────────────────────────────────────────────────┐
   │                    Supported Video Sources                  │
   │  - RTSP: rtsp://user:pass@host:554/stream                   │
   │  - UDP MPEG-TS: udp://127.0.0.1:8080                        │
   │  - Local Device: /dev/video0 or OpenCV index 0              │
   │  - File Loop: ffmpeg -re -stream_loop -1 -i test.mp4 ...   │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                   OpenCV / FFmpeg Demuxer                   │
   │      - Hardware acceleration (NVDEC, VideoToolbox, VAAPI)   │
   │      - Non-blocking threaded frame grabber                  │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                    Circular Frame Buffer                    │
   │      - Ring buffer capacity: 30 frames                      │
   │      - Lock-free latest frame access                        │
   │      - In-memory JPEG encoder for snapshot HTTP endpoint    │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                   ┌──────────────┴──────────────┐
                   ▼                             ▼
   ┌──────────────────────────────┐ ┌──────────────────────────────┐
   │   Inference Decimator (AI)   │ │  Dashboard Snapshot Endpoint │
   │   (Sample every Nth frame)   │ │   GET /cameras/{id}/snapshot │
   └──────────────────────────────┘ └──────────────────────────────┘
```

---

# 3. Camera Perspective Calibration

To enable the Movement Intelligence engine to compute real-world metric speeds ($\text{km/h}$), each camera config includes ground-plane calibration parameters:
- `pixels_per_meter`: Number of sensor pixels corresponding to 1 real-world meter at ground level.
- `perspective_matrix`: Optional $3 \times 3$ homography transformation matrix converting image coordinates $(u, v)$ to world ground coordinates $(X, Y)$.

---

# 4. Database Schema: `cameras` Table

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `camera_id` | TEXT | PRIMARY KEY | Unique ID (e.g., `CAM-01`). |
| `name` | TEXT | NOT NULL | Display name (e.g., `North Gate Approach`). |
| `source_type` | TEXT | NOT NULL | `rtsp`, `udp`, `file`, `device`, `synthetic`. |
| `stream_reference`| TEXT | NOT NULL | URI, file path, or UDP endpoint. |
| `location` | TEXT | NULLABLE | Physical area description. |
| `status` | TEXT | NOT NULL | `ONLINE`, `OFFLINE`, `DEGRADED`, `UNKNOWN`. |
| `enabled` | INTEGER | DEFAULT 1 | 1 if active, 0 if disabled. |
| `created_at` | TEXT | NOT NULL | ISO 8601 UTC timestamp. |
| `updated_at` | TEXT | NOT NULL | ISO 8601 UTC timestamp. |

---

# 5. REST API Endpoints (`/api/v1/cameras`)

- `GET /api/v1/cameras`: Returns list of configured cameras and current health status.
- `POST /api/v1/cameras`: Registers a new camera stream (Status 201).
- `GET /api/v1/cameras/{camera_id}`: Fetches configuration and zone bindings for target camera.
- `GET /api/v1/cameras/{camera_id}/health`: Real-time FPS, drop rate, and last frame timestamp.
- `GET /api/v1/cameras/{camera_id}/snapshot`: Directly streams the latest raw JPEG frame from the circular buffer.
- `POST /api/v1/cameras/{camera_id}/status`: Updates camera status (e.g. maintenance mode).

---

# 6. Dashboard Integration: `LiveFeedsView`

- **Multi-Camera Wall**: Grid layout ($2 \times 2$, $3 \times 3$, or focus view) displaying live streams with dynamic frame refresh.
- **Bounding Box & HUD Overlay**: Live SVG overlays showing active tracks, track IDs, speed readouts, and bounding box colors (Green = Human, Blue = Vehicle, Magenta = UAV, Gold = Face).
- **Stream Controls**: Pause, snapshot download, and full-screen modal inspector.
