"""Roboflow serverless special vehicle detector adapter.

Detects emergency, military, construction, and specialized vehicles using Roboflow
inference models, normalizing them into the HELIOS VEHICLE observation pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.ingestion.camera_manager import CameraStreamHub
from app.services.helios_service import HeliosService
from app.vision.observation import normalized_observation
from app.vision.roboflow_client import LocalFallbackClient, RoboflowHttpClient

LOGGER = logging.getLogger(__name__)


class RoboflowSpecialVehicleInferenceManager:
    """Manages Roboflow special vehicle detection inference across active camera streams."""

    def __init__(self, service: HeliosService, settings: Settings, camera_hub: CameraStreamHub) -> None:
        self.service, self.camera_hub = service, camera_hub
        self.configs = [
            m for m in settings.models
            if m.get("enabled") and (
                m.get("mode") == "roboflow-special-vehicle"
                or "special-vehicle" in m.get("name", "")
            )
        ]
        self.tasks: list[asyncio.Task[None]] = []
        self.stopping = False
        self.clients: dict[str, Any] = {}

    async def start(self) -> None:
        self.stopping = False
        if not self.configs:
            return
        cameras = [
            camera for camera in self.service.settings.cameras
            if camera.get("enabled", True) and camera.get("stream_reference")
        ]
        for config in self.configs:
            secret = (
                os.environ.get(config.get("api_key_env", "ROBOFLOW_API_KEY"))
                or os.environ.get("ROBOFLOW_API_KEY")
                or os.environ.get("SPECIAL_VEHICLE_ROBOFLOW_API_KEY")
                or os.environ.get("UAV_ROBOFLOW_API_KEY")
            )
            if not secret:
                LOGGER.info(
                    "%s is running in local fallback mode (no Roboflow API key configured).",
                    config["name"],
                )
                self.clients[config["name"]] = LocalFallbackClient(config)
            else:
                try:
                    self.clients[config["name"]] = await asyncio.to_thread(self._client, config, secret)
                except Exception as error:
                    LOGGER.warning(
                        "%s could not initialize cloud client; falling back to local standby: %s",
                        config["name"],
                        error,
                    )
                    self.clients[config["name"]] = LocalFallbackClient(config)

            for camera in cameras:
                self.tasks.append(
                    asyncio.create_task(
                        self._run(camera["camera_id"], config),
                        name=f"special_vehicle:{camera['camera_id']}",
                    )
                )

    async def stop(self) -> None:
        self.stopping = True
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        for client in self.clients.values():
            if hasattr(client, "close"):
                client.close()

    @staticmethod
    def _client(config: dict[str, Any], secret: str) -> Any:
        try:
            from inference_sdk import InferenceConfiguration, InferenceHTTPClient
            return InferenceHTTPClient(
                api_url=config.get("api_url", "https://serverless.roboflow.com"),
                api_key=secret,
            ).configure(InferenceConfiguration(api_key_transport="header"))
        except Exception:
            return RoboflowHttpClient(
                api_url=config.get("api_url", "https://serverless.roboflow.com"),
                api_key=secret,
            )

    async def _run(self, camera_id: str, config: dict[str, Any]) -> None:
        interval, sequence = 1 / max(float(config.get("inference_fps", 1)), 0.1), 0
        try:
            while not self.stopping:
                started = time.monotonic()
                frame = await self.camera_hub.next_frame(camera_id, sequence)
                sequence = frame.sequence
                observations = await asyncio.to_thread(self._detect, frame.image, camera_id, config)
                for observation in observations:
                    observation["image"] = frame.image
                    await self.service.ingest(observation)
                await asyncio.sleep(max(0, interval - (time.monotonic() - started)))
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Roboflow special vehicle inference failed for camera %s", camera_id)

    def _detect(self, image: Any, camera_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
        import cv2
        client = self.clients.get(config["name"])
        if client is None:
            return []

        handle = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        path = Path(handle.name)
        handle.close()
        try:
            if not cv2.imwrite(str(path), image):
                return []
            if config.get("workflow_id"):
                workflow_output = client.run_workflow(
                    workspace_name=config.get("workspace_name", "pramukhs-workspace"),
                    workflow_id=config["workflow_id"],
                    images={"image": str(path)},
                    parameters=config.get("parameters", {"classes": "emergency vehicle"}),
                    use_cache=True,
                )
                from app.vision.roboflow_face import prediction_lists
                predictions = [p for preds in prediction_lists(workflow_output) for p in preds]
            else:
                model_id = config.get("model_id", "military-f5tbj/1")
                result = client.infer(str(path), model_id=model_id)
                predictions = result.get("predictions", []) if isinstance(result, dict) else []
        finally:
            path.unlink(missing_ok=True)

        height, width = image.shape[:2]
        observations = []
        conf_thresh = float(config.get("confidence_threshold", 0.30))

        for prediction in predictions:
            confidence = float(prediction.get("confidence", 0))
            if confidence < conf_thresh:
                continue

            box_width, box_height = float(prediction["width"]), float(prediction["height"])
            x1 = float(prediction["x"]) - box_width / 2
            y1 = float(prediction["y"]) - box_height / 2
            source_class = str(prediction.get("class", "special_vehicle")).lower()

            attributes: dict[str, Any] = {
                "source_class": source_class,
                "vehicle_type": source_class,
                "is_special_vehicle": True,
            }

            observations.append(
                normalized_observation(
                    camera_id=camera_id,
                    object_type="VEHICLE",
                    confidence=confidence,
                    xyxy=[x1, y1, x1 + box_width, y1 + box_height],
                    image_width=width,
                    image_height=height,
                    model_name=config["name"],
                    model_version=config.get("version", "1"),
                    attributes=attributes,
                )
            )
        return observations
