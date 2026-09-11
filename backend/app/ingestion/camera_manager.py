"""Shared camera ingestion: one source connection, many consumers."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.ingestion.frame import Frame
from app.services.helios_service import HeliosService
from app.vision.observation import crop_bounding_box_jpeg
from app.vision.visibility import CameraVisibilityManager

LOGGER = logging.getLogger(__name__)


class CameraStreamHub:
    """Maintains the latest frame per configured camera for inference and MJPEG."""

    def __init__(self, service: HeliosService, cameras: list[dict[str, Any]], frame_rate: float = 8) -> None:
        self.service, self.cameras = service, cameras
        self.interval = 1 / max(frame_rate, 0.1)
        self._reconnect_delay = 5.0
        self.latest: dict[str, Frame] = {}
        self.visibility_manager = CameraVisibilityManager()
        self.tasks: list[asyncio.Task[None]] = []
        self._stopping = False
        self.service.camera_hub = self

    def get_snapshot_jpeg(self, camera_id: str, bounding_box: list[float] | None = None) -> bytes | None:
        frame = self.latest.get(camera_id)
        if not frame:
            return None
        if bounding_box is not None and frame.image is not None:
            crop_jpeg = crop_bounding_box_jpeg(frame.image, bounding_box)
            if crop_jpeg:
                return crop_jpeg
        return frame.jpeg

    def _create_synthetic_frame(self, camera_id: str, name: str, location: str, sequence: int) -> Frame:
        import numpy as np
        import cv2
        from datetime import datetime

        h, w = 480, 640
        img = np.zeros((h, w, 3), dtype=np.uint8)
        # Background gradient
        for y in range(h):
            val = int(14 + (y / h) * 20)
            img[y, :] = (val, val + 2, val + 5)

        # Subtle CCTV grid lines
        cv2.rectangle(img, (20, 20), (w - 20, h - 20), (32, 40, 48), 1)
        cv2.line(img, (20, h - 60), (w - 20, h - 60), (28, 35, 42), 1)
        cv2.line(img, (20, h - 60), (140, 260), (25, 30, 36), 1)
        cv2.line(img, (w - 20, h - 60), (w - 140, 260), (25, 30, 36), 1)

        # Dynamic live elements
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-4]
        pulse = 5 if (sequence % 16 < 8) else 4
        cv2.circle(img, (36, 36), pulse, (47, 204, 139), -1)
        cv2.putText(img, "LIVE", (48, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (47, 204, 139), 1, cv2.LINE_AA)
        cv2.putText(img, f"REC {ts} UTC", (w - 240, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 190, 200), 1, cv2.LINE_AA)

        cam_label = f"{camera_id} · {name.upper()}"
        cv2.putText(img, cam_label, (36, h - 36), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 230), 1, cv2.LINE_AA)
        cv2.putText(img, f"LOCATION: {location.upper()} · SITUATIONAL FEED", (36, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 130, 140), 1, cv2.LINE_AA)

        # Simulated dynamic patrol target
        t_x = int(w / 2 + np.sin(sequence * 0.08) * 140)
        t_y = int(220 + np.cos(sequence * 0.06) * 30)
        cv2.rectangle(img, (t_x - 12, t_y - 24), (t_x + 12, t_y + 24), (40, 80, 60), 1)
        cv2.circle(img, (t_x, t_y - 14), 4, (40, 80, 60), 1)

        ok, jpeg = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return Frame.create(camera_id, img, sequence, jpeg.tobytes() if ok else b"")

    async def _synthetic_capture(self, camera: dict[str, Any]) -> None:
        camera_id = camera["camera_id"]
        name = camera.get("name", camera_id)
        location = camera.get("location", "Sector")
        sequence = 0
        await self._set_status(camera_id, "ONLINE")
        try:
            while not self._stopping:
                started = time.monotonic()
                sequence += 1
                frame = self._create_synthetic_frame(camera_id, name, location, sequence)
                self.latest[camera_id] = frame
                await asyncio.sleep(max(0, self.interval - (time.monotonic() - started)))
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Synthetic capture failed for %s", camera_id)

    async def start(self) -> None:
        self._stopping = False
        try:
            db_cameras = [dict(r) for r in self.service.db.execute("SELECT * FROM cameras WHERE enabled=1").fetchall()]
        except Exception:
            db_cameras = []
        cameras_to_monitor = db_cameras if db_cameras else self.cameras
        for camera in cameras_to_monitor:
            if camera.get("enabled", True):
                if camera.get("stream_reference"):
                    self.tasks.append(asyncio.create_task(self._capture(camera), name=f"camera:{camera['camera_id']}"))
                else:
                    await self._set_status(camera["camera_id"], "OFFLINE")

    async def stop(self) -> None:
        self._stopping = True
        for task in self.tasks: task.cancel()
        if self.tasks: await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    async def next_frame(self, camera_id: str, after_sequence: int = 0) -> Frame:
        while not self._stopping:
            frame = self.latest.get(camera_id)
            if frame and frame.sequence > after_sequence:
                return frame
            await asyncio.sleep(.02)
        raise asyncio.CancelledError

    async def reload_cameras(self) -> None:
        """Reload camera configurations from disk/yaml and restart capture tasks."""
        await self.stop()
        from app.core.config import load_settings
        new_settings = load_settings()
        self.service.settings.cameras = new_settings.cameras
        self.service.seed()
        self.cameras = new_settings.cameras
        await self.start()

    async def mjpeg(self, camera_id: str) -> AsyncIterator[bytes]:
        sequence = 0
        while not self._stopping:
            try:
                frame = await asyncio.wait_for(self.next_frame(camera_id, sequence), timeout=3.0)
                sequence = frame.sequence
                if frame.jpeg:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame.jpeg + b"\r\n"
            except TimeoutError:
                row = self.service.db.execute("SELECT status, stream_reference FROM cameras WHERE camera_id=?", (camera_id,)).fetchone()
                if not row or not row["stream_reference"]:
                    break

    async def _set_status(self, camera_id: str, status: str) -> None:
        row = self.service.db.execute("SELECT status FROM cameras WHERE camera_id=?", (camera_id,)).fetchone()
        if row and row["status"] != status: await self.service.camera_status(camera_id, status)

    async def _capture(self, camera: dict[str, Any]) -> None:
        import cv2
        camera_id = camera["camera_id"]
        source = camera.get("stream_reference", "")
        
        # Robust source normalization:
        # Convert numeric string to integer for local webcam
        actual_source: Any = source
        if isinstance(source, int):
            actual_source = source
        elif isinstance(source, str) and source.strip().isdigit():
            actual_source = int(source.strip())
        elif isinstance(source, str) and source.startswith("rtsp://"):
            import os
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;5000000"

        sequence = 0
        capture: Any | None = None
        consecutive_failures = 0
        try:
            while not self._stopping:
                started = time.monotonic()
                if capture is None or not capture.isOpened():
                    if capture is not None:
                        await asyncio.to_thread(capture.release)
                    capture = await asyncio.to_thread(cv2.VideoCapture, actual_source)
                    if not capture.isOpened():
                        await self._set_status(camera_id, "OFFLINE")
                        await asyncio.sleep(self._reconnect_delay)
                        continue
                    await self._set_status(camera_id, "ONLINE")

                ok, image = await asyncio.to_thread(capture.read)
                if not ok:
                    # If it's a local video file, loop it seamlessly
                    if isinstance(actual_source, str) and not actual_source.startswith(("http://", "https://", "rtsp://", "udp://")):
                        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
                        if frame_count > 0:
                            await asyncio.to_thread(capture.set, cv2.CAP_PROP_POS_FRAMES, 0)
                            ok, image = await asyncio.to_thread(capture.read)

                if not ok:
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        await self._set_status(camera_id, "OFFLINE")
                        self.latest.pop(camera_id, None)
                        await asyncio.to_thread(capture.release)
                        capture = None
                        consecutive_failures = 0
                        await asyncio.sleep(self._reconnect_delay)
                    else:
                        await asyncio.sleep(0.2)
                    continue

                consecutive_failures = 0
                encoded, jpeg = await asyncio.to_thread(cv2.imencode, ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if encoded:
                    sequence += 1
                    self.latest[camera_id] = Frame.create(camera_id, image, sequence, jpeg.tobytes())
                    if sequence % 4 == 0:
                        try:
                            changed, cond_rec = self.visibility_manager.process_frame(camera_id, image)
                            if changed:
                                self.service.record_camera_condition(
                                    camera_id=camera_id,
                                    condition=cond_rec.condition,
                                    reliability_score=cond_rec.reliability_score,
                                    confidence=cond_rec.confidence,
                                    reason=cond_rec.reason,
                                    metrics=cond_rec.metrics.to_dict(),
                                    started_at=cond_rec.started_at,
                                    resolved_at=cond_rec.resolved_at,
                                    duration_seconds=cond_rec.duration_seconds,
                                )
                        except Exception:
                            LOGGER.exception("Visibility analysis failed for camera %s", camera_id)
                await asyncio.sleep(max(0, self.interval - (time.monotonic() - started)))
        except asyncio.CancelledError: raise
        except Exception:
            LOGGER.exception("Camera capture failed for %s", camera_id)
            await self._set_status(camera_id, "OFFLINE")
        finally:
            if capture is not None: await asyncio.to_thread(capture.release)
