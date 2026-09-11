"""Model-neutral vision observation helpers."""
from __future__ import annotations

from typing import Any


def normalized_observation(*, camera_id: str, object_type: str, confidence: float, xyxy: list[float], image_width: int, image_height: int, model_name: str, model_version: str, attributes: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the observation contract consumed by HELIOS services."""
    x1, y1, x2, y2 = xyxy
    return {
        "camera_id": camera_id,
        "object_type": object_type,
        "confidence": confidence,
        "bounding_box": [max(0, x1 / image_width), max(0, y1 / image_height), min(1, max(0, x2 - x1) / image_width), min(1, max(0, y2 - y1) / image_height)],
        "model_name": model_name,
        "model_version": model_version,
        "attributes": attributes or {},
    }


def crop_bounding_box_jpeg(image: Any, bounding_box: list[float] | None = None, quality: int = 85) -> bytes | None:
    """Crop an OpenCV image array to a normalized [x, y, w, h] bounding box and encode to JPEG bytes."""
    if image is None:
        return None
    try:
        import cv2
        height, width = image.shape[:2]
        if bounding_box and len(bounding_box) == 4:
            x, y, bw, bh = (float(v) for v in bounding_box)
            x1 = max(0, min(width - 1, int(round(x * width))))
            y1 = max(0, min(height - 1, int(round(y * height))))
            x2 = max(x1 + 1, min(width, int(round((x + bw) * width))))
            y2 = max(y1 + 1, min(height, int(round((y + bh) * height))))
            if x2 > x1 and y2 > y1:
                crop = image[y1:y2, x1:x2]
                if crop.size > 0:
                    ok, encoded = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                    if ok:
                        return encoded.tobytes()
        # Fallback to full frame if bounding_box is None or crop fails
        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if ok:
            return encoded.tobytes()
    except Exception:
        pass
    return None
