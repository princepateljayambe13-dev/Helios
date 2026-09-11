# HELIOS V1 PIPELINE SPECIFICATION

## System Specification: End-to-End Perception, Tracking & Telemetry Execution Loop

**Project:** HELIOS  
**Document:** Processing Pipeline Stages, Latency Budgets & Execution Mechanics  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Pipeline Overview & Execution Stages

The HELIOS pipeline processes continuous video streams through 10 sequential stages, delivering sub-second threat detection from photon to operator dashboard:

```
[ Stage 1: Stream Ingestion & Decoding ]  ===>  5 - 10 ms
                │
                ▼
[ Stage 2: Motion Pre-Filter (MOG2) ]     ===>  1 - 3 ms (Suppresses static scenes)
                │
                ▼
[ Stage 3: Neural Perception (YOLO26) ]   ===>  15 - 35 ms
                │
                ▼
[ Stage 4: Multi-Object Tracking (IoU) ]  ===>  2 - 5 ms
                │
                ▼
[ Stage 5: Movement & Speed Intelligence ] ===> 1 - 2 ms
                │
                ▼
[ Stage 6: Biometric Feature Extraction ] ===>  10 - 20 ms (Triggered on human tracks)
                │
                ▼
[ Stage 7: Spatial Reasoning & Fencing ]  ===>  1 - 3 ms
                │
                ▼
[ Stage 8: Event & Alert Evaluation ]     ===>  2 - 4 ms
                │
                ▼
[ Stage 9: Cross-Camera Incident Engine ] ===>  5 - 10 ms (Async background thread)
                │
                ▼
[ Stage 10: WebSocket Telemetry Broadcast]===>  1 - 2 ms
```

**Total End-to-End Latency Budget:** $< 85\text{ms}$ per frame (exceeding 12 FPS real-time surveillance target on CPU/Edge GPU).

---

# 2. Stage Breakdown & Mechanics

### Stage 1: Stream Ingestion & Demuxing
Decodes incoming RTSP or UDP H.264 streams into RGB frames via hardware-accelerated OpenCV / FFmpeg decoders. Pushes raw decoded frame to the camera's circular memory ring buffer.

### Stage 2: Fast Motion Pre-Filtering
Executes lightweight Gaussian Mixture Model (MOG2) background subtraction. If pixel change is below $0.5\%$, heavy neural detector inference is bypassed for that frame to conserve compute.

### Stage 3: Object Detection
Passes active frames through YOLO26s (human, vehicle classes) and specialized Roboflow models (aerial UAVs). Non-Maximum Suppression (NMS) suppresses overlapping bounding boxes.

### Stage 4: Multi-Object Tracking & Smoothing
Associates detections with active tracks using Hungarian algorithm matching over spatial IoU and centroid distance. Smooths trajectory jitter with exponential moving averages.

### Stage 5: Movement & Speed Kinematics
Calculates instantaneous velocity ($\text{km/h}$ and $\text{px/s}$) using camera ground calibration. Determines 8-way cardinal heading and updates movement state machine (`STATIONARY`, `WALKING`, `RUNNING`, `LOITERING`).

### Stage 6: Face Detection & ArcFace Association
Extracts face crop, computes 512-dim ArcFace embedding, matches against enrolled roster via cosine similarity, and binds the identity to the human body track using vertical torso containment.

### Stage 7: Spatial Reasoning & Virtual Fencing
Projects the track's ground foot contact point $\left(x + \frac{w}{2}, y + h\right)$ against polygon zones via ray-casting PIP. Evaluates trajectory vectors against directional tripwires.

### Stage 8: Event Creation & Alert Generation
If a boundary is breached or dwell time exceeds loitering threshold, generates an atomic security `event` record, captures full frame and crop evidence, and triggers alert rules with cooldown suppression.

### Stage 9: Incident Correlation Clustering
Asynchronously correlates the new event against active facility incidents within a 180s temporal window, scoring temporal, spatial, and track affinity factors.

### Stage 10: WebSocket Broadcast
Serializes telemetry updates into JSON envelopes and dispatches across open WebSocket client connections to all active operator dashboards.
