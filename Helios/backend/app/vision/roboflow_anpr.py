"""Roboflow ANPR plate-detector adapter with rolling cropped evidence."""
from __future__ import annotations

import asyncio, logging, os, sys, tempfile, time
from pathlib import Path
from typing import Any
from app.core.config import Settings
from app.ingestion.camera_manager import CameraStreamHub
from app.services.helios_service import HeliosService
from app.vision.anpr.plate_detector import PlateEvidenceStore
from app.vision.model_manager import ModelManager
from app.vision.observation import normalized_observation
from app.vision.roboflow_client import LocalFallbackClient, RoboflowHttpClient

LOGGER=logging.getLogger(__name__)

class RoboflowAnprInferenceManager:
    def __init__(self, service: HeliosService, settings: Settings, camera_hub: CameraStreamHub) -> None:
        self.service,self.camera_hub=service,camera_hub
        self.configs = [
            m for m in settings.models
            if m.get("enabled") and (m.get("mode") == "roboflow-anpr" or "LICENSE_PLATE" in m.get("classes", []))
        ]
        self.clients={}; self.tasks=[]; self.stopping=False; self.evidence=PlateEvidenceStore(service)
    async def start(self) -> None:
        self.stopping=False
        cameras=[camera for camera in self.service.settings.cameras if camera.get("enabled",True) and camera.get("stream_reference")]
        for config in self.configs:
            secret=os.environ.get(config.get("api_key_env","UAV_ROBOFLOW_API_KEY"))
            if not secret:
                LOGGER.info("%s is running in local fallback mode (%s is not set).", config["name"], config.get("api_key_env", "UAV_ROBOFLOW_API_KEY"))
                self.clients[config["name"]] = LocalFallbackClient(config)
            else:
                try:
                    self.clients[config["name"]]=await asyncio.to_thread(self._client,config,secret)
                except Exception as error:
                    LOGGER.warning("%s could not initialize cloud client; falling back to local detector: %s",config["name"],error)
                    self.clients[config["name"]] = LocalFallbackClient(config)
            for camera in cameras:self.tasks.append(asyncio.create_task(self._run(camera["camera_id"],config),name=f"anpr:{camera['camera_id']}"))
    async def stop(self) -> None:
        self.stopping=True
        for task in self.tasks:task.cancel()
        if self.tasks:await asyncio.gather(*self.tasks,return_exceptions=True)
        self.tasks.clear()
        for client in self.clients.values():
            if hasattr(client, "close"):
                client.close()
    @staticmethod
    def _client(config:dict[str,Any],secret:str)->Any:
        try:
            from inference_sdk import InferenceConfiguration,InferenceHTTPClient
            return InferenceHTTPClient(api_url=config["api_url"],api_key=secret).configure(InferenceConfiguration(api_key_transport="header"))
        except Exception:
            return RoboflowHttpClient(api_url=config.get("api_url", "https://serverless.roboflow.com"), api_key=secret)
    async def _run(self,camera_id:str,config:dict[str,Any])->None:
        interval,sequence=1/max(float(config.get("inference_fps",1)),.1),0
        try:
            while not self.stopping:
                started=time.monotonic();frame=await self.camera_hub.next_frame(camera_id,sequence);sequence=frame.sequence
                for observation in await asyncio.to_thread(self._detect,frame.image,camera_id,config):
                    result=await self.service.ingest(observation);self.evidence.save(frame.image,observation["bounding_box"],result["event_id"],result["detection_id"])
                await asyncio.sleep(max(0,interval-(time.monotonic()-started)))
        except asyncio.CancelledError:raise
        except Exception:LOGGER.exception("Roboflow ANPR inference failed for %s",camera_id)
    def _detect(self,image:Any,camera_id:str,config:dict[str,Any])->list[dict[str,Any]]:
        import cv2
        client=self.clients.get(config["name"])
        if client is None: return []
        handle=tempfile.NamedTemporaryFile(suffix=".jpg",delete=False);path=Path(handle.name);handle.close()
        try:
            if not cv2.imwrite(str(path),image):return []
            if config.get("workflow_id"):
                workflow_output = client.run_workflow(
                    workspace_name=config.get("workspace_name", "pramukhs-workspace"),
                    workflow_id=config["workflow_id"],
                    images={"image": str(path)},
                    parameters=config.get("parameters", {"classes": "License_Plate"}),
                    use_cache=True,
                )
                from app.vision.roboflow_face import prediction_lists
                predictions = [p for preds in prediction_lists(workflow_output) for p in preds]
            else:
                result=client.infer(str(path),model_id=config.get("model_id", "anpr-tdrid/1"))
                predictions = result.get("predictions", []) if isinstance(result, dict) else []
        finally:path.unlink(missing_ok=True)
        height,width=image.shape[:2];observations=[]
        for prediction in predictions:
            confidence=float(prediction.get("confidence",0))
            if confidence<float(config.get("confidence_threshold",.5)):continue
            box_width,box_height=float(prediction["width"]),float(prediction["height"]);x1,y1=float(prediction["x"])-box_width/2,float(prediction["y"])-box_height/2
            observations.append(normalized_observation(camera_id=camera_id,object_type="LICENSE_PLATE",confidence=confidence,xyxy=[x1,y1,x1+box_width,y1+box_height],image_width=width,image_height=height,model_name=config["name"],model_version=config.get("version"),attributes={"source_class":str(prediction.get("class","license_plate")).lower()}))
        return observations
