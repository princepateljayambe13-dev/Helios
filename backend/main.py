"""HELIOS V1 API entry point.

Run from this directory: uvicorn main:app --reload
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.api import router
from app.api.routes.ai import build_ai_router
from app.api.routes.insights import router as insights_router
from app.ai.service import AiService
from app.core.config import load_settings
from app.database.connection import connect
from app.services.helios_service import HeliosService
from app.ingestion.camera_manager import CameraStreamHub
from app.vision.yolo26 import VideoInferenceManager
from app.vision.roboflow_uav import RoboflowUavInferenceManager
from app.vision.roboflow_face import RoboflowFaceWorkflowManager
from app.vision.roboflow_anpr import RoboflowAnprInferenceManager
from app.vision.roboflow_special_vehicle import RoboflowSpecialVehicleInferenceManager
from app.vision.motion import Mog2MotionInferenceManager
from app.core.lifecycle import EngineSupervisor

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings=load_settings(); settings.evidence_directory.mkdir(parents=True,exist_ok=True)
    app.state.helios=HeliosService(connect(settings.database_path),settings); app.state.helios.seed()
    app.state.ai=AiService(app.state.helios, settings)
    app.state.camera_hub=CameraStreamHub(app.state.helios, settings.cameras)
    app.state.helios.camera_hub=app.state.camera_hub
    app.state.video_inference=VideoInferenceManager(app.state.helios, settings, app.state.camera_hub)
    app.state.uav_inference=RoboflowUavInferenceManager(app.state.helios, settings, app.state.camera_hub)
    app.state.face_inference=RoboflowFaceWorkflowManager(app.state.helios, settings, app.state.camera_hub)
    app.state.anpr_inference=RoboflowAnprInferenceManager(app.state.helios, settings, app.state.camera_hub)
    app.state.special_vehicle_inference=RoboflowSpecialVehicleInferenceManager(app.state.helios, settings, app.state.camera_hub)
    app.state.motion_inference=Mog2MotionInferenceManager(app.state.helios, settings, app.state.camera_hub)
    app.state.engine_supervisor=EngineSupervisor(settings.engine_restart_max_attempts,settings.engine_restart_backoff_seconds)
    for name,engine in (
        ("camera-ingestion",app.state.camera_hub),
        ("human-vehicle-inference",app.state.video_inference),
        ("uav-inference",app.state.uav_inference),
        ("face-inference",app.state.face_inference),
        ("anpr-inference",app.state.anpr_inference),
        ("special-vehicle-inference",app.state.special_vehicle_inference),
        ("motion-inference",app.state.motion_inference),
    ): app.state.engine_supervisor.register(name,engine)
    await app.state.engine_supervisor.start()
    yield
    await app.state.engine_supervisor.stop()
    app.state.helios.db.close()

app=FastAPI(title="HELIOS V1 API",version="1.0.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])
app.include_router(router,prefix="/api/v1",tags=["HELIOS"])
app.include_router(insights_router,prefix="/api/v1",tags=["Insights"])
app.include_router(build_ai_router(),prefix="/api/v1",tags=["AI"])
app.include_router(build_ai_router(),prefix="/api",tags=["AI"])

@app.websocket('/api/v1/ws')
async def websocket_endpoint(socket: WebSocket):
    await socket.accept(); app.state.helios.subscribers.add(socket)
    try:
        await socket.send_json({"topic":"system","data":app.state.helios.summary()})
        while True: await socket.receive_text()  # dashboard may send keep-alives
    except WebSocketDisconnect: pass
    finally: app.state.helios.subscribers.discard(socket)

@app.get('/')
def root(): return {"service":"HELIOS","docs":"/docs","api":"/api/v1"}
