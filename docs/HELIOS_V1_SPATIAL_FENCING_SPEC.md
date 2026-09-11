# HELIOS V1 SPATIAL FENCING & PERIMETER SPECIFICATION

## System Specification: Virtual Fencing, Tripwires & Spatial Intelligence

**Project:** HELIOS  
**Document:** Spatial Fencing, Geometry Engine, Loitering & Zone Boundary Specification  
**Version:** 1.0 (Present Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Purpose

The HELIOS Spatial Fencing module delivers high-precision perimeter security, virtual tripwire enforcement, restricted area ingress/egress monitoring, and loitering session management.

Traditional camera systems rely on rectangular bounding-box overlaps, producing severe false alarm rates. HELIOS solves this via:
- **Vector Polygon Geometries**: Arbitrary $N$-point convex and non-convex polygons defined in normalized $[0.0, 1.0]$ coordinate space.
- **Foot-Point Ground Contact Grounding**: Tests the bottom-center of the object bounding box $\left(x + \frac{w}{2}, y + h\right)$ against polygon geometries, eliminating false triggers caused by shadows or upper-body perspectives.
- **Virtual Directional Tripwires**: Line-segment intersection mathematics evaluating entry, exit, or bi-directional boundary crossing.
- **Continuous Loitering State Engine**: Tracks per-zone dwell times, transition events, and stationary versus erratic movement thresholds.

---

# 2. Geometric Algorithms & Mathematical Formulations

### 2.1 Object Ground Contact Point
Given a normalized bounding box $[x, y, w, h]$ where $x, y \in [0.0, 1.0]$ represents the top-left origin:
$$P_{\text{ground}} = \left(x + \frac{w}{2},\; y + h\right)$$

### 2.2 Ray-Casting Point-in-Polygon (PIP) Algorithm
For an arbitrary polygon $V = [v_0, v_1, \dots, v_{n-1}]$ where $v_i = (x_i, y_i)$:
A horizontal test ray is cast from $P_{\text{ground}} = (P_x, P_y)$ towards $+\infty$. For each edge $(v_i, v_j)$ where $j = (i+1) \pmod n$:
$$\text{intersects} = (y_i > P_y) \neq (y_j > P_y) \;\land\; \left(P_x < \frac{(x_j - x_i)(P_y - y_i)}{(y_j - y_i)} + x_i\right)$$
The point is inside the zone if and only if the total count of intersections is odd.

### 2.3 Tripwire Segment Intersection
A tripwire is defined by line segment $L_1 = (A, B)$. An object's trajectory between timestamp $t-1$ and $t$ is line segment $L_2 = (P_{t-1}, P_t)$.
Intersection is computed via vector cross-products:
$$\mathbf{r} = B - A, \quad \mathbf{s} = P_t - P_{t-1}$$
If cross-products verify crossing, the 2D cross product $(\mathbf{r} \times \mathbf{s})$ sign dictates the directional vector (e.g., `INGRESS` vs `EGRESS`).

---

# 3. Zone Types & Operational Semantics

| Zone Type | Operational Behavior | Trigger Conditions |
| :--- | :--- | :--- |
| **`RESTRICTED`** | Immediate security breach upon entry. | Any authorized/unauthorized object ground point inside polygon. |
| **`PERIMETER_FENCE`** | Boundary buffer; tracks outer approach. | Proximity or crossing of outer fence boundary. |
| **`TRIPWIRE`** | Directed line boundary crossing. | Trajectory intersection with directional sign match. |
| **`LOITERING`** | Dwell time monitoring zone. | Object remains inside polygon longer than `loitering_threshold_seconds` (default: 30s). |
| **`EXCLUSION`** | Sensor dead-zone / ignore zone. | Detections within this polygon are suppressed (e.g. tree sway, highway background). |

---

# 4. Loitering State Machine & Session Tracking

Loitering is tracked via persistent `loitering_sessions`:

```
                 [ Track Enters Zone ]
                           │
                           ▼
                 ┌───────────────────┐
                 │      PENDING      │  (dwell_time < threshold)
                 └─────────┬─────────┘
                           │ dwell_time >= threshold (e.g. 30s)
                           ▼
                 ┌───────────────────┐  ==> Emits LOITERING_DETECTED Event
                 │     LOITERING     │  ==> Fires Security Alert
                 └─────────┬─────────┘
                           │
           ┌───────────────┴───────────────┐
           ▼                               ▼
┌─────────────────────┐         ┌─────────────────────┐
│       RESOLVED      │         │       EXPIRED       │
│ (Track Exits Zone)  │         │ (Track Lost > 60s)  │
└─────────────────────┘         └─────────────────────┘
```

### 4.1 Loitering Session Schema (`loitering_sessions`)
- `session_id`: Unique session UUID (`LOIT-...`).
- `camera_id`, `zone_id`, `track_id`, `object_type`.
- `status`: `PENDING`, `ACTIVE`, `RESOLVED`, `EXPIRED`.
- `start_time`, `end_time`, `duration_seconds`.
- `movement_state`: `STATIONARY`, `ERRATIC`, `PACING`.
- `event_id`: Link to security event.

---

# 5. REST API Endpoints (`/api/v1/zones`)

### `GET /api/v1/zones`
Lists all active zones and virtual fences with coordinates, types, and camera associations.

### `POST /api/v1/zones` (Status 201)
Creates a new perimeter polygon or tripwire.
```json
{
  "zone_id": "ZONE-NORTH-GATE",
  "camera_id": "CAM-01",
  "name": "North Perimeter Gate",
  "zone_type": "RESTRICTED",
  "geometry": [[0.1, 0.2], [0.4, 0.2], [0.4, 0.6], [0.1, 0.6]],
  "object_types": ["human", "vehicle"]
}
```

### `GET /api/v1/zones/density`
Returns real-time occupancy counts across all zones.

### `GET /api/v1/zones/dwell`
Returns average and maximum dwell times per zone over the last 24 hours.

### `GET /api/v1/zones/loitering/history`
Returns active and historical loitering sessions.

### `PUT /api/v1/zones/{zone_id}/thresholds`
Updates dwell thresholds and sensitivity parameters for a specific zone.

---

# 6. Dashboard Integration: `FencingView` & `ZoneEventsView`

1. **Interactive Canvas Overlay**: Renders camera stream snapshots with SVG overlays representing polygons, tripwires, and live object foot-point coordinates.
2. **Zone Creator**: Allows operators to click-to-draw polygonal boundaries, define directional arrows for tripwires, and bind custom alert rules.
3. **Real-time Breach Visualizer**: Flashes neon red boundary highlights when a perimeter violation occurs, accompanied by directional indicators and audio alerts.
4. **Zone Analytics Tab**: Displays bar graphs of intrusion frequency, peak occupancy hours, and dwell distributions.
