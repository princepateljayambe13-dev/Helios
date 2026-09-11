"""OpenCV MOG2 Motion Detection and Classification Engine for HELIOS V1.

Uses cv2.createBackgroundSubtractorMOG2 to detect motion in camera feeds.
When motion is detected:
- Cross-references with active tracks/detections (Human, Vehicle, UAV, Face, Fire, Smoke, License Plate).
- If motion correlates with a known model detection, attributes the motion to that model.
- If no model detected an object in the motion area, classifies it as 'UNCLASSIFIED'
  and ingests a normalized observation to generate events and tracks.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import cv2
import numpy as np

from app.core.config import Settings
from app.ingestion.camera_manager import CameraStreamHub
from app.services.helios_service import HeliosService
from app.tracking.tracker import iou
from app.vision.observation import normalized_observation

LOGGER = logging.getLogger(__name__)


class Mog2MotionDetector:
    """Per-camera background subtraction using OpenCV MOG2."""

    def __init__(self, history: int = 500, var_threshold: float = 30.0, min_area_ratio: float = 0.005) -> None:
        self.history = history
        self.var_threshold = var_threshold
        self.min_area_ratio = min_area_ratio
        self._subtractors: dict[str, Any] = {}
        self._frame_counts: dict[str, int] = {}

    def get_subtractor(self, camera_id: str) -> Any:
        if camera_id not in self._subtractors:
            self._subtractors[camera_id] = cv2.createBackgroundSubtractorMOG2(
                history=self.history,
                varThreshold=self.var_threshold,
                detectShadows=True,
            )
        return self._subtractors[camera_id]

    def detect_motion_boxes(self, image: Any, camera_id: str) -> list[tuple[float, float, float, float]]:
        """Return list of normalized bounding boxes [x, y, w, h] where motion occurs."""
        subtractor = self.get_subtractor(camera_id)
        fg_mask = subtractor.apply(image)
        self._frame_counts[camera_id] = self._frame_counts.get(camera_id, 0) + 1
        if self._frame_counts[camera_id] <= 1:
            return []

        # Filter shadows (shadow pixels typically have value ~127 in MOG2)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        thresh = cv2.dilate(thresh, kernel, iterations=2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        height, width = image.shape[:2]
        min_area = (height * width) * self.min_area_ratio

        boxes: list[tuple[float, float, float, float]] = []
        for c in contours:
            if cv2.contourArea(c) < min_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            boxes.append((float(x) / width, float(y) / height, float(w) / width, float(h) / height))

        return boxes


class Mog2MotionInferenceManager:
    """Runs continuous MOG2 motion detection across active camera feeds."""

    def __init__(self, service: HeliosService, settings: Settings, camera_hub: CameraStreamHub) -> None:
        self.service, self.settings, self.camera_hub = service, settings, camera_hub
        self.tasks: list[asyncio.Task[None]] = []
        self.stopping = False
        self.configs = [m for m in settings.models if m.get("enabled") and (m.get("mode") == "opencv-mog2" or "UNCLASSIFIED" in m.get("classes", []))]
        cfg = self.configs[0] if self.configs else {}
        params = cfg.get("parameters", {}) if isinstance(cfg, dict) else {}
        history = int(params.get("history", 500))
        var_threshold = float(params.get("var_threshold", 30.0))
        min_area_ratio = float(params.get("min_area_ratio", 0.005))
        self.detector = Mog2MotionDetector(history=history, var_threshold=var_threshold, min_area_ratio=min_area_ratio)

    async def start(self) -> None:
        self.stopping = False
        cameras = [c for c in self.settings.cameras if c.get("enabled", True) and c.get("stream_reference")]
        for camera in cameras:
            self.tasks.append(
                asyncio.create_task(self._run(camera["camera_id"]), name=f"motion:{camera['camera_id']}")
            )

    async def stop(self) -> None:
        self.stopping = True
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    async def _run(self, camera_id: str) -> None:
        interval, sequence = 0.25, 0  # 4 FPS motion evaluation
        try:
            while not self.stopping:
                started = time.monotonic()
                frame = await self.camera_hub.next_frame(camera_id, sequence)
                sequence = frame.sequence
                observations = await asyncio.to_thread(self._process_frame, frame.image, camera_id)
                for obs in observations:
                    await self.service.ingest(obs)
                await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("MOG2 motion detection loop failed for %s", camera_id)

    def _process_frame(self, image: Any, camera_id: str) -> list[dict[str, Any]]:
        motion_boxes = self.detector.detect_motion_boxes(image, camera_id)
        if not motion_boxes:
            return []

        height, width = image.shape[:2]
        # Query active tracks currently tracked on this camera
        cursor = self.service.db.execute(
            "SELECT track_id, object_type, current_position FROM tracks WHERE camera_id=? AND status='ACTIVE'",
            (camera_id,),
        )
        import json
        active_tracks: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            try:
                pos = json.loads(row[2]) if isinstance(row[2], str) else row[2]
                active_tracks.append({"track_id": row[0], "object_type": row[1], "current_position": pos})
            except Exception:
                pass

        observations: list[dict[str, Any]] = []
        for mx, my, mw, mh in motion_boxes:
            # Check overlap with existing classified tracks
            matched_track = None
            highest_overlap = 0.0
            for tr in active_tracks:
                pos = tr.get("current_position")
                if not pos or len(pos) != 4:
                    continue
                # Calculate IoU
                overlap = iou([mx, my, mw, mh], pos)
                if overlap > 0.05 and overlap > highest_overlap:
                    highest_overlap = overlap
                    matched_track = tr

            if matched_track:
                # Motion was detected and classified by our models (Human, Vehicle, UAV, etc.)
                LOGGER.debug(
                    "MOG2 motion on %s correlated with %s track %s",
                    camera_id,
                    matched_track["object_type"],
                    matched_track["track_id"],
                )
            else:
                # Motion detected by MOG2, but NOT classified by any model -> UNCLASSIFIED
                x1, y1 = mx * width, my * height
                x2, y2 = (mx + mw) * width, (my + mh) * height
                observations.append(
                    normalized_observation(
                        camera_id=camera_id,
                        object_type="UNCLASSIFIED",
                        confidence=0.75,
                        xyxy=[x1, y1, x2, y2],
                        image_width=width,
                        image_height=height,
                        model_name="opencv-mog2",
                        model_version="mog2-v1",
                        attributes={
                            "source_class": "unclassified",
                            "motion_type": "UNCLASSIFIED",
                            "description": "Unclassified motion detected",
                        },
                    )
                )

        return observations
