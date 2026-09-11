# HELIOS V1 EVIDENCE SPECIFICATION

## System Specification: Forensic Evidence Capture, Bounding Box Crops & Deduplication

**Project:** HELIOS  
**Document:** Evidence Capture, Storage Hierarchy, Perceptual Hash Deduplication & File Serving  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Purpose

In surveillance and physical security, raw video feeds are too bulky to store indefinitely, while isolated metadata records lack visual verifiability.

The HELIOS Evidence Subsystem bridges this gap:
- **Instantaneous High-Res Capture**: When a security event fires, the uncompressed full-resolution frame is extracted from the camera's memory ring buffer.
- **Intelligent Object & Face Crops**: Extracts tightly bounded, normalized crops of the subject (e.g. human face, vehicle license plate) for fast visual triage and biometric verification.
- **Perceptual Hash Deduplication**: Calculates 64-bit difference hashes (`dHash`) across consecutive evidence captures, suppressing duplicate frames with similarity $> 85\%$.
- **Chain of Custody & Immutability**: All captures receive unique cryptographic IDs (`EVD-...`), UTC timestamps, and tamper-resistant storage references.

---

# 2. Storage Directory Organization

```
storage/evidence/
├── full/                 # Full-resolution camera frame captures (JPEG)
│   └── EVD-4A20D9DC.jpg
├── crops/                # Tightly bounded object detection crops
│   └── EVD-4A20D9DC_crop.jpg
├── face/                 # Biometric face recognition crops (112x112 / 128x128)
│   └── FAC-779CB8FF.jpg
├── anpr/                 # Vehicle license plate crops
│   └── PLT-5AE5232C.jpg
└── exports/              # Operator generated incident evidence export archives
```

---

# 3. Perceptual Hash Deduplication Engine

To avoid exhausting edge disk storage during prolonged incidents, HELIOS implements 64-bit difference hashing (`dHash`):
1. **Resize**: Resizes candidate image to $9 \times 8$ grayscale.
2. **Gradient Comparison**: Computes binary difference between adjacent pixels:
   $$P[x, y] > P[x+1, y] \implies 1 \quad \text{else} \quad 0$$
3. **Hamming Distance**: Compares the resulting 64-bit integer against recent evidence captures from the same camera:
   $$\text{HammingDistance}(H_1, H_2) = \text{popcount}(H_1 \oplus H_2)$$
   If $\text{Distance} \le 10$ (similarity $\ge 85\%$), the frame is identified as redundant and discarded.

---

# 4. Database Schema: `evidence` Table

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `evidence_id` | TEXT | PRIMARY KEY | Unique ID (`EVD-...`). |
| `event_id` | TEXT | NOT NULL | Associated security event foreign key. |
| `type` | TEXT | NOT NULL | `FULL_FRAME`, `OBJECT_CROP`, `FACE_CROP`, `ANPR_CROP`. |
| `storage_reference`| TEXT | NOT NULL | Relative disk path within `storage/`. |
| `timestamp` | TEXT | NOT NULL | ISO 8601 UTC timestamp. |
| `created_at` | TEXT | NOT NULL | Database insertion timestamp. |

---

# 5. REST API Endpoints (`/api/v1/evidence`)

- `GET /api/v1/evidence`: Lists captured evidence records with optional `camera_id` and `type` filters.
- `GET /api/v1/evidence/{evidence_id}`: Returns metadata for a specific evidence capture.
- `GET /api/v1/evidence/{evidence_id}/file`: Streams the raw binary JPEG image directly to the browser.
- `DELETE /api/v1/evidence/clear`: Cleans up expired evidence items according to storage retention rules.

---

# 6. Dashboard Integration: `EvidenceView`

- **Visual Forensic Gallery**: Displays responsive card grid with high-resolution image thumbnails, timestamp badges, and associated camera tags.
- **Lightbox Inspector**: Modal view with zoom/pan capabilities, bounding box overlays, and AI investigation triggers.
- **Direct Export**: Allows one-click JPEG download or bulk ZIP export for law enforcement handoff.
