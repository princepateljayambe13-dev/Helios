"""Roboflow Workflow face-detection adapter; detection only, never identification."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.ingestion.camera_manager import CameraStreamHub
from app.services.helios_service import HeliosService
from app.vision.model_manager import ModelManager
from app.vision.observation import normalized_observation
from app.vision.roboflow_client import LocalFallbackClient, RoboflowHttpClient

LOGGER = logging.getLogger(__name__)


def prediction_lists(value: Any) -> Iterator[list[dict[str, Any]]]:
    """Find detection blocks within a Workflow response without coupling to block names."""
    if isinstance(value, dict):
        predictions = value.get("predictions")
        if isinstance(predictions, list) and all(isinstance(item, dict) for item in predictions):
            yield predictions
        elif isinstance(predictions, dict):
            yield from prediction_lists(predictions)
        for key, child in value.items():
            if key != "predictions": yield from prediction_lists(child)
    elif isinstance(value, list):
        for child in value: yield from prediction_lists(child)


class RoboflowFaceWorkflowManager:
    def __init__(self, service: HeliosService, settings: Settings, camera_hub: CameraStreamHub) -> None:
        self.service, self.camera_hub = service, camera_hub
        self.configs = ModelManager(settings).enabled("roboflow-workflow")
        self.clients: dict[str, Any] = {}; self.tasks: list[asyncio.Task[None]] = []; self.stopping = False

    async def start(self) -> None:
        self.stopping = False
        cameras = [camera for camera in self.service.settings.cameras if camera.get("enabled", True) and camera.get("stream_reference")]
        for config in self.configs:
            secret = os.environ.get(config.get("api_key_env", "UAV_ROBOFLOW_API_KEY"))
            if not secret:
                LOGGER.info("%s is running in local fallback mode (%s is not set).", config["name"], config.get("api_key_env", "UAV_ROBOFLOW_API_KEY"))
                self.clients[config["name"]] = LocalFallbackClient(config)
            else:
                try:
                    self.clients[config["name"]]=await asyncio.to_thread(self._client,config,secret)
                except Exception as error:
                    LOGGER.warning("%s could not initialize cloud client; falling back to local detector: %s",config["name"],error)
                    self.clients[config["name"]] = LocalFallbackClient(config)
            for camera in cameras: self.tasks.append(asyncio.create_task(self._run(camera["camera_id"], config), name=f"workflow:{config['name']}:{camera['camera_id']}"))

    async def stop(self) -> None:
        self.stopping = True
        for task in self.tasks: task.cancel()
        if self.tasks: await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        for client in self.clients.values():
            if hasattr(client, "close"):
                client.close()

    @staticmethod
    def _client(config: dict[str, Any], secret: str) -> Any:
        try:
            from inference_sdk import InferenceConfiguration, InferenceHTTPClient
            return InferenceHTTPClient(api_url=config["api_url"], api_key=secret).configure(InferenceConfiguration(api_key_transport="header"))
        except Exception:
            return RoboflowHttpClient(api_url=config.get("api_url", "https://serverless.roboflow.com"), api_key=secret)

    async def _run(self, camera_id: str, config: dict[str, Any]) -> None:
        interval, sequence = 1 / max(float(config.get("inference_fps", 1)), .1), 0
        try:
            while not self.stopping:
                started = time.monotonic(); frame = await self.camera_hub.next_frame(camera_id, sequence); sequence = frame.sequence
                for observation in await asyncio.to_thread(self._detect, frame.image, camera_id, config):
                    observation["image"] = frame.image
                    await self.service.ingest(observation)
                await asyncio.sleep(max(0, interval - (time.monotonic() - started)))
        except asyncio.CancelledError: raise
        except Exception: LOGGER.exception("Roboflow face workflow failed for %s", camera_id)

    def _detect(self, image: Any, camera_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
        import cv2
        client = self.clients.get(config["name"])
        if client is None: return []
        file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False); path = Path(file.name); file.close()
        try:
            if not cv2.imwrite(str(path), image): return []
            params = config.get("parameters", {"classes": "face"})
            result = client.run_workflow(workspace_name=config["workspace_name"], workflow_id=config["workflow_id"], images={"image":str(path)}, parameters=params, use_cache=True)
        finally: path.unlink(missing_ok=True)
        height, width = image.shape[:2]; observations=[]
        target_classes = [c.upper() for c in config.get("classes", ["FACE"])]
        for predictions in prediction_lists(result):
            for prediction in predictions:
                confidence = float(prediction.get("confidence", 0))
                if confidence < float(config.get("confidence_threshold", .5)): continue
                box_width, box_height = float(prediction["width"]), float(prediction["height"])
                x1, y1 = float(prediction["x"])-box_width/2, float(prediction["y"])-box_height/2
                source_cls = str(prediction.get("class", "face")).lower()
                if "fire" in source_cls or "flame" in source_cls:
                    object_type = "FIRE"
                elif "smoke" in source_cls:
                    object_type = "SMOKE"
                elif "HUMAN" in target_classes or "person" in source_cls or "people" in source_cls:
                    object_type = "HUMAN"
                elif "FACE" in target_classes or "face" in source_cls:
                    object_type = "FACE"
                elif "LICENSE_PLATE" in target_classes or "plate" in source_cls:
                    object_type = "LICENSE_PLATE"
                else:
                    object_type = target_classes[0] if target_classes else "OBJECT"
                attrs = {"source_class": source_cls}
                if "thermal" in config.get("name", "").lower() or "ir" in config.get("name", "").lower():
                    attrs["modality"] = "thermal"
                observations.append(normalized_observation(camera_id=camera_id, object_type=object_type, confidence=confidence, xyxy=[x1,y1,x1+box_width,y1+box_height], image_width=width, image_height=height, model_name=config["name"], model_version=config.get("version"), attributes=attrs))
        return observations
