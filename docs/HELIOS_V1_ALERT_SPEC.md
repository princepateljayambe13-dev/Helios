# HELIOS V1 ALERT SPECIFICATION

## System Specification: Alert Rule Engine, Priority Escalation & Audio Notification

**Project:** HELIOS  
**Document:** Security Alerts, Deduplication, Notification Manager & Web Audio Specification  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Purpose

The HELIOS Alert Engine filters continuous sensor events into high-priority, actionable operator alerts. It ensures:
- **Deduplication & Cooldown Control**: Prevents alarm fatigue caused by continuous object detections within a zone.
- **Dynamic Severity Escalation**: Escalates alert priority based on target persistence, speed, nighttime hours, and zone criticality.
- **Multimodal Operator Alerting**: Combines visual glassmorphic status banners, animated threat rings, desktop notifications, and synthesized browser audio chimes.
- **Comprehensive Audit Trail**: Tracks acknowledgment timestamps, operator IDs, and resolution notes.

---

# 2. Alert Severity Hierarchy

| Severity Level | Numeric Rank | Visual Theme | Audio Tone | Tactical Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **`CRITICAL`** | 5 | Glowing Crimson (`#E53935`) | High-pitch dual-tone pulse | Immediate perimeter breach, weapon detection, or confirmed drone incursion. |
| **`HIGH`** | 4 | Vivid Orange (`#FB8C00`) | Rapid ascending chime | Unauthorized vehicle in staging area or repeated loitering breach. |
| **`ELEVATED`** | 3 | Amber Gold (`#C99A5B`) | Soft double beep | Unknown face lingering near sensitive infrastructure. |
| **`MEDIUM`** | 2 | Electric Yellow (`#FDD835`)| Single muted ping | Directional tripwire crossing during normal shift hours. |
| **`LOW`** | 1 | Ocean Blue (`#1E88E5`) | Silent / Visual only | Camera reconnected, track handoff, or routine gate egress. |
| **`INFO`** | 0 | Subtle Dim Slate (`#757575`)| Silent | System health heartbeat, log rotation, or baseline recalculation. |

---

# 3. Alert Generation & Deduplication Logic

Alerts are evaluated whenever an `event` record is created:
1. **Rule Matching**: Evaluates event against configured alert rules in `config/alerts.yaml`.
2. **Cooldown Suppression**: If an active alert exists for the same `(camera_id, zone_id, track_id)` within the configured cooldown window (default: $60\text{s}$), a new alert is suppressed and the existing alert's occurrence counter increments.
3. **Escalation Rules**:
   - If duration $> 120\text{s}$, elevate severity by +1 rank.
   - If speed $> 25\text{ km/h}$ in pedestrian zone, escalate to `HIGH`.
   - If timestamp falls within curfew window ($22:00 - 06:00$), escalate to `CRITICAL`.

---

# 4. Web Audio Synthesizer Engine (`dashboard/src/utils/alertAudio.js`)

To ensure cross-platform compatibility without external MP3 dependencies, the dashboard uses the Web Audio API (`AudioContext`) to synthesize procedural waveforms:
- **Critical Alert Tone**: Alternating square wave oscillators at $880\text{ Hz}$ and $1760\text{ Hz}$ with exponential gain decay.
- **High Alert Tone**: Smooth sine sweep from $440\text{ Hz}$ to $880\text{ Hz}$ over $250\text{ms}$.
- **Medium Alert Tone**: Soft $520\text{ Hz}$ bell tone with low-pass filtering.
- **Audio Mute Control**: Globally toggleable via the TopBar audio button with persistent `localStorage` preference.

---

# 5. Database Schema: `alerts` Table

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `alert_id` | TEXT | PRIMARY KEY | Unique ID (`ALT-...`). |
| `event_id` | TEXT | NOT NULL | Foreign key referencing triggering event. |
| `timestamp` | TEXT | NOT NULL | ISO 8601 creation timestamp. |
| `alert_type` | TEXT | NOT NULL | E.g., `PERIMETER_BREACH`, `LOITERING`, `SPEED_VIOLATION`. |
| `severity` | TEXT | NOT NULL | `CRITICAL`, `HIGH`, `ELEVATED`, `MEDIUM`, `LOW`, `INFO`. |
| `status` | TEXT | NOT NULL | `PENDING`, `ACKNOWLEDGED`, `RESOLVED`. |
| `message` | TEXT | NOT NULL | Human-readable alert summary. |
| `acknowledged_at`| TEXT | NULLABLE | Timestamp of operator acknowledgment. |
| `acknowledged_by`| TEXT | NULLABLE | Operator badge / username. |
| `resolved_at` | TEXT | NULLABLE | Resolution timestamp. |
| `resolved_by` | TEXT | NULLABLE | Resolving operator ID. |

---

# 6. REST API Endpoints (`/api/v1/alerts`)

- `GET /api/v1/alerts`: Returns list of alerts with optional status/severity filtering.
- `POST /api/v1/alerts/{alert_id}/acknowledge`: Sets status to `ACKNOWLEDGED`.
- `POST /api/v1/alerts/acknowledge-all`: Bulk clears pending alerts.

---

# 7. Dashboard Integration: `AlertsView` & `NotificationManager`

- **Global Status Banner**: Renders across top of UI; pulses red during unacknowledged critical alerts.
- **Notification Toast Stack**: Non-blocking toast notifications in top-right corner with direct `Acknowledge` action button.
- **Alerts View**: Dedicated management grid with filtering, CSV export, and audio playback test controls.
