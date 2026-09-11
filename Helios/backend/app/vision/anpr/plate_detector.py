"""Rolling local storage for cropped licence-plate evidence."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.services.helios_service import HeliosService, now


class PlateEvidenceStore:
    """Retain a batch of at most 30 crops, then clear it before the next crop."""
    limit = 30

    def __init__(self, service: HeliosService) -> None:
        self.service = service
        self.directory = service.settings.evidence_directory / "anpr"
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, image: Any, bounding_box: list[float], event_id: str, detection_id: str) -> str | None:
        import cv2
        files = sorted(self.directory.glob("*.jpg"))
        if len(files) >= self.limit:
            for file in files: file.unlink()
            self.service.db.execute("DELETE FROM evidence WHERE type='LICENSE_PLATE_CROP' AND storage_reference LIKE 'anpr/%'")
        height, width = image.shape[:2]
        x, y, box_width, box_height = bounding_box
        x1, y1 = max(0, int(x * width)), max(0, int(y * height))
        x2, y2 = min(width, int((x + box_width) * width)), min(height, int((y + box_height) * height))
        crop = image[y1:y2, x1:x2]
        if crop.size == 0: return None
        filename = f"{detection_id}.jpg"; path = self.directory / filename
        if not cv2.imwrite(str(path), crop): return None
        evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}"; stamp=now()
        self.service.db.execute("INSERT INTO evidence (evidence_id,event_id,type,storage_reference,timestamp,created_at) VALUES (?,?,?,?,?,?)",(evidence_id,event_id,"LICENSE_PLATE_CROP",f"anpr/{filename}",stamp,stamp))
        self.service.db.commit()
        return str(path)
