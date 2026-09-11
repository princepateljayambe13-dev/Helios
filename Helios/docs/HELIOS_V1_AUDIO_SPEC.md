# HELIOS V1 AUDIO & ACOUSTIC SPECIFICATION

## System Specification: Acoustic Threat Ingestion & Sound Event Classification

**Project:** HELIOS  
**Document:** Audio Pipeline, Sound Event Detection & Acoustic Surveillance  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Purpose

Vision systems face natural blind spots: corners, heavy foliage, complete darkness, or camera tampering. The HELIOS Audio module complements visual cameras by continuously monitoring acoustic feeds for violent or suspicious sound events.

Key capabilities:
- **Demuxed Stream & Dedicated Microphones**: Accepts audio embedded in RTSP camera streams (AAC/PCM) as well as dedicated IP acoustic sensors.
- **Fast Acoustic Threat Detection**: Spectral analysis identifying gunshots, explosions, breaking glass, human screams, and vehicle engine acceleration.
- **Cross-Modal Event Fusing**: Automatically associates acoustic observations with the nearest visual camera to trigger snapshot capture and camera PTZ slew.

---

# 2. Audio Processing Architecture

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│     RTSP Stream Audio Track     │       │     Dedicated USB/IP Sensor     │
└────────────────┬────────────────┘       └────────────────┬────────────────┘
                 │                                         │
                 └───────────────────┬─────────────────────┘
                                     │ 16kHz Mono PCM Stream
                                     ▼
                 ┌───────────────────────────────────────┐
                 │     Sliding Window Audio Buffer       │
                 │   (1.0s window, 50% overlap / hop)    │
                 └───────────────────┬───────────────────┘
                                     │
                                     ▼
                 ┌───────────────────────────────────────┐
                 │       Log-Mel Spectrogram FFT         │
                 │   (64 Mel bins, 20ms frame length)    │
                 └───────────────────┬───────────────────┘
                                     │
                                     ▼
                 ┌───────────────────────────────────────┐
                 │     Acoustic Threat Classifier        │
                 │   (YAMNet / Lightweight Audio CNN)    │
                 └───────────────────┬───────────────────┘
                                     │ Probability >= 0.65
                                     ▼
                 ┌───────────────────────────────────────┐
                 │        Acoustic Event Dispatcher      │
                 │  - Persists to `events` table         │
                 │  - Fires Audio Security Alert         │
                 │  - Triggers Nearest Camera Snapshot   │
                 └───────────────────────────────────────┘
```

---

# 3. Classified Acoustic Threat Categories

| Sound Class | Frequency Characteristics | Minimum Confidence | Triggered Severity |
| :--- | :--- | :--- | :--- |
| **`GUNSHOT`** | Sharp transient onset ($<5\text{ms}$), broadband decay ($1-4\text{ kHz}$). | $0.70$ | `CRITICAL` |
| **`EXPLOSION`** | High-energy low-frequency resonance ($<250\text{ Hz}$) with pressure wave. | $0.65$ | `CRITICAL` |
| **`GLASS_BREAK`** | High-frequency shattering harmonics ($3-8\text{ kHz}$). | $0.68$ | `HIGH` |
| **`SCREAM / DISTRESS`** | Harmonic formant structure ($1-3\text{ kHz}$) with rapid pitch modulation. | $0.60$ | `HIGH` |
| **`VEHICLE_REV`** | Rising harmonic engine frequencies with RPM spikes. | $0.65$ | `MEDIUM` |

---

# 4. Database Schema: `audio_sources` Table

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `source_id` | TEXT | PRIMARY KEY | Unique audio source ID (e.g. `AUD-01`). |
| `name` | TEXT | NOT NULL | Human-readable name (e.g., `North Gate Mic`). |
| `status` | TEXT | NOT NULL | `ONLINE`, `OFFLINE`, `MUTED`. |
| `created_at` | TEXT | NOT NULL | ISO 8601 UTC timestamp. |
| `updated_at` | TEXT | NOT NULL | ISO 8601 UTC timestamp. |

---

# 5. REST API Endpoints

### `POST /api/v1/audio/observations` (Status 201)
Ingests an externally classified acoustic observation.
```json
{
  "source_id": "AUD-01",
  "sound_type": "GLASS_BREAK",
  "confidence": 0.82,
  "decibels": 88.5,
  "timestamp": "2026-09-10T08:15:30Z"
}
```

---

# 6. Cross-Modal Sensor Fusion

When an acoustic threat is logged:
1. The system queries `config/cameras.yaml` to identify cameras with spatial proximity to `source_id`.
2. The `CameraManager` captures immediate high-resolution frame snapshots from the candidate cameras.
3. The `IncidentCorrelator` binds the acoustic event and the visual snapshots into a unified incident dossier.
