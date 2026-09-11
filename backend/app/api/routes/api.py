from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import StreamingResponse, FileResponse, Response
from app.database.models import AlertAction, AlertsBatchAction, AudioObservationInput, CameraInput, EvidenceInput, ObservationInput, ZoneInput, ZoneUpdateInput, ZoneThresholdsInput
from app.services.helios_service import item, now
from app.api.routes.faces import router as faces_router
import uuid

router=APIRouter()
router.include_router(faces_router, prefix="/faces", tags=["Faces"])
def svc(request: Request): return request.app.state.helios
def rows(cursor): return [item(r) for r in cursor.fetchall()]

@router.get('/system/health')
def health(request: Request):
    engines=request.app.state.engine_supervisor.snapshot()
    status="healthy" if all(value["status"]=="READY" for value in engines.values() if value["name"] in {"camera-ingestion","human-vehicle-inference"}) else "degraded"
    return {"status":status,"service":"HELIOS","summary":svc(request).summary(),"engines":engines}
@router.get('/system/summary')
def summary(request: Request): return svc(request).summary()
@router.get('/system/analytics')
def analytics(request: Request, timeframe: str = '24h'):
    return svc(request).get_analytics(timeframe=timeframe)
@router.post('/system/clear-cache')
@router.delete('/system/clear-cache')
def clear_system_cache(request: Request):
    return svc(request).clear_all_cache()
@router.get('/models')
def models(request: Request):
    models=svc(request).settings.models
    active=next((model.get("mode") for model in models if model.get("enabled")), None)
    return {"models":[{**model,"status":"READY" if model.get("enabled") else "NOT_PROVIDED"} for model in models],"mode":active or "NOT_PROVIDED"}

@router.get('/cameras')
def cameras(request: Request):
    return rows(svc(request).db.execute(
        "SELECT c.camera_id, c.name, c.source_type, c.location, c.status, c.enabled, "
        "(c.stream_reference IS NOT NULL AND c.stream_reference != '') AS stream_configured, "
        "COALESCE(r.reliability_score, 100) AS reliability_score, "
        "COALESCE(r.condition, 'CLEAR') AS condition, "
        "COALESCE(r.condition_confidence, 1.0) AS condition_confidence, "
        "c.created_at, c.updated_at "
        "FROM cameras c LEFT JOIN camera_reliability r ON c.camera_id = r.camera_id "
        "WHERE c.enabled = 1 "
        "ORDER BY c.camera_id"
    ))

@router.post('/cameras/reload')
async def reload_cameras_endpoint(request: Request):
    """Reload camera configurations from config/cameras.yaml and restart capture workers."""
    hub = getattr(request.app.state, 'camera_hub', None)
    if hub and hasattr(hub, 'reload_cameras'):
        await hub.reload_cameras()
    else:
        svc(request).seed()
    return {"status": "reloaded", "cameras": len(svc(request).settings.cameras)}

@router.post('/cameras',status_code=201)
def create_camera(payload:CameraInput,request:Request):
    s=svc(request); stamp=__import__('datetime').datetime.now(__import__('datetime').UTC).isoformat()
    try: s.db.execute("INSERT INTO cameras VALUES (?,?,?,?,?,'UNKNOWN',?,?,?)",(payload.camera_id,payload.name,payload.source_type,payload.stream_reference,payload.location,int(payload.enabled),stamp,stamp));s.db.commit()
    except Exception as e: raise HTTPException(409,"camera already exists") from e
    return {**payload.model_dump(exclude={'stream_reference'}),"status":"UNKNOWN","stream_configured":bool(payload.stream_reference)}

@router.get('/cameras/conditions')
def all_camera_conditions(request: Request):
    """Retrieve current visibility conditions and reliability scores for all cameras."""
    return svc(request).get_all_camera_conditions()

@router.get('/cameras/{camera_id}')
def camera(camera_id:str,request:Request):
    result=item(svc(request).db.execute(
        "SELECT c.camera_id, c.name, c.source_type, c.location, c.status, c.enabled, "
        "(c.stream_reference IS NOT NULL AND c.stream_reference != '') AS stream_configured, "
        "COALESCE(r.reliability_score, 100) AS reliability_score, "
        "COALESCE(r.condition, 'CLEAR') AS condition, "
        "COALESCE(r.condition_confidence, 1.0) AS condition_confidence, "
        "r.condition_started_at, r.condition_details, c.created_at, c.updated_at "
        "FROM cameras c LEFT JOIN camera_reliability r ON c.camera_id = r.camera_id "
        "WHERE c.camera_id=?",(camera_id,)).fetchone())
    if not result: raise HTTPException(404,"camera not found")
    return result

@router.get('/cameras/{camera_id}/condition')
def camera_condition(camera_id: str, request: Request):
    """Retrieve current visibility condition, metrics, and reliability score for a camera."""
    result = svc(request).get_camera_condition(camera_id)
    if not result: raise HTTPException(404, "camera not found")
    return result

@router.get('/cameras/{camera_id}/condition/history')
def camera_condition_history(camera_id: str, request: Request, limit: int = 50):
    """Retrieve historical visibility condition transitions for a camera."""
    return svc(request).get_camera_condition_history(camera_id, limit=limit)

@router.get('/cameras/{camera_id}/health')
def camera_health(camera_id:str,request:Request):
    result=svc(request).camera_health(camera_id)
    if not result: raise HTTPException(404,"camera not found")
    return result

@router.get('/cameras/{camera_id}/stream')
async def camera_stream(camera_id:str,request:Request):
    """Serve shared camera frames as browser-safe MJPEG without returning its URL."""
    row=svc(request).db.execute("SELECT camera_id, status, stream_reference FROM cameras WHERE camera_id=? AND enabled=1",(camera_id,)).fetchone()
    if not row: raise HTTPException(404,"camera not found")
    if not row["stream_reference"]:
        raise HTTPException(503, "Camera stream not configured or offline")

    return StreamingResponse(request.app.state.camera_hub.mjpeg(camera_id),media_type="multipart/x-mixed-replace; boundary=frame",headers={"Cache-Control":"no-store"})

@router.get('/cameras/{camera_id}/snapshot')
def camera_snapshot(camera_id: str, request: Request):
    """Serve a single JPEG snapshot for the requested camera."""
    hub = getattr(request.app.state, 'camera_hub', None)
    if hub:
        jpeg = hub.get_snapshot_jpeg(camera_id)
        if jpeg:
            return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
        <rect width="640" height="360" fill="#080d12"/>
        <rect x="20" y="20" width="600" height="320" fill="#101720" rx="12" stroke="#212f40" stroke-width="2"/>
        <circle cx="320" cy="150" r="38" fill="#182330" stroke="#5c5c58" stroke-width="2"/>
        <text x="320" y="215" fill="#f2f2f0" font-family="sans-serif" font-weight="bold" font-size="14" text-anchor="middle">{camera_id} STANDBY</text>
        <text x="320" y="240" fill="#9a9a96" font-family="sans-serif" font-size="11" text-anchor="middle">STREAM INITIALIZING OR OFFLINE</text>
    </svg>'''
    return Response(content=svg.encode("utf-8"), media_type="image/svg+xml")

@router.post('/cameras/{camera_id}/status')
async def camera_status(camera_id:str,status:str,request:Request):
    try:return await svc(request).camera_status(camera_id,status)
    except KeyError:raise HTTPException(404,"camera not found")

@router.get('/zones')
def zones(request: Request, camera_id: str | None = None):
    return svc(request).get_zones(camera_id=camera_id)

@router.get('/zones/density')
def zones_density(request: Request, camera_id: str | None = None, zone_id: str | None = None):
    return svc(request).get_live_people_density(camera_id=camera_id, zone_id=zone_id)

@router.get('/zones/dwell')
def zones_dwell(request: Request, camera_id: str | None = None, zone_id: str | None = None):
    """Return live tracks dwelling inside zones with their duration and loitering status."""
    return svc(request).get_zone_dwell_tracks(camera_id=camera_id, zone_id=zone_id)

@router.get('/zones/loitering/history')
def zones_loitering_history(request: Request, limit: int = 50, zone_id: str | None = None):
    """Return logged loitering sessions."""
    return svc(request).get_loitering_history(limit=limit, zone_id=zone_id)

@router.put('/zones/thresholds/default')
async def update_default_thresholds(payload: ZoneThresholdsInput, request: Request):
    """Update global default dwell and loitering thresholds."""
    result = svc(request).update_default_thresholds(
        dwell_seconds=payload.dwell_threshold_seconds,
        loitering_seconds=payload.loitering_threshold_seconds,
    )
    await svc(request).broadcast("settings", result)
    return result

@router.put('/zones/{zone_id}/thresholds')
async def update_zone_thresholds(zone_id: str, payload: ZoneThresholdsInput, request: Request):
    """Update dwell and loitering thresholds for a specific zone."""
    result = svc(request).update_zone_thresholds(
        zone_id=zone_id,
        dwell_seconds=payload.dwell_threshold_seconds,
        loitering_seconds=payload.loitering_threshold_seconds,
    )
    await svc(request).broadcast("zone_thresholds", result)
    return result

@router.get('/zones/{zone_id}/density')
def single_zone_density(zone_id: str, request: Request):
    densities = svc(request).get_live_people_density(zone_id=zone_id)
    if not densities:
        raise HTTPException(404, "zone density not found")
    return densities[0]

@router.get('/zones/{zone_id}')
def zone(zone_id: str, request: Request):
    result = svc(request).get_zone(zone_id)
    if not result:
        raise HTTPException(404, "zone not found")
    return result

@router.post('/zones', status_code=201)
async def create_zone(payload: ZoneInput, request: Request):
    cam = item(svc(request).db.execute("SELECT camera_id FROM cameras WHERE camera_id=?", (payload.camera_id,)).fetchone())
    if not cam:
        raise HTTPException(404, f"camera {payload.camera_id} not found")
    created = svc(request).create_zone(payload.model_dump())
    await svc(request).broadcast("zone", created)
    return created

@router.put('/zones/{zone_id}')
async def update_zone(zone_id: str, payload: ZoneUpdateInput, request: Request):
    updated = svc(request).update_zone(zone_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(404, "zone not found")
    await svc(request).broadcast("zone", updated)
    return updated

@router.delete('/zones/{zone_id}')
async def delete_zone(zone_id: str, request: Request):
    deleted = svc(request).delete_zone(zone_id)
    if not deleted:
        raise HTTPException(404, "zone not found")
    await svc(request).broadcast("zone_deleted", {"zone_id": zone_id})
    return {"status": "deleted", "zone_id": zone_id}

@router.get('/tracks')
def tracks(request:Request,camera_id:str|None=None):
    if svc(request).expire_stale_tracks(): svc(request).db.commit()
    query="SELECT * FROM tracks";args=()
    if camera_id: query+=" WHERE camera_id=?";args=(camera_id,)
    return rows(svc(request).db.execute(query+" ORDER BY last_seen_at DESC",args))
@router.get('/tracks/{track_id}')
def track(track_id:str,request:Request):
    result=item(svc(request).db.execute("SELECT * FROM tracks WHERE track_id=?",(track_id,)).fetchone())
    if not result: raise HTTPException(404,"track not found")
    result['positions']=rows(svc(request).db.execute("SELECT * FROM track_positions WHERE track_id=? ORDER BY timestamp",(track_id,)))
    result['movements']=svc(request).get_track_movements(track_id)
    result['recoveries']=svc(request).get_track_recoveries(track_id=track_id)
    return result

@router.get('/tracks/{track_id}/movements')
def track_movements(track_id: str, request: Request, limit: int = 100):
    return svc(request).get_track_movements(track_id, limit=limit)

@router.get('/tracks/{track_id}/recoveries')
def track_recoveries(track_id: str, request: Request, limit: int = 50):
    return svc(request).get_track_recoveries(track_id=track_id, limit=limit)

@router.get('/tracking/recoveries')
def all_recoveries(request: Request, camera_id: str | None = None, limit: int = 50):
    return svc(request).get_track_recoveries(camera_id=camera_id, limit=limit)

@router.get('/threads')
def activity_threads(
    request: Request,
    limit: int = 50,
    status: str | None = None,
    camera_id: str | None = None,
    object_type: str | None = None,
    vehicle_type: str | None = None,
    vehicle_color: str | None = None,
    threat_level: str | None = None,
    movement_state: str | None = None,
    person_name: str | None = None,
    face_status: str | None = None,
):
    limit = max(1, min(limit, 200))
    return svc(request).get_all_threads(
        limit=limit,
        status=status,
        camera_id=camera_id,
        object_type=object_type,
        vehicle_type=vehicle_type,
        vehicle_color=vehicle_color,
        threat_level=threat_level,
        movement_state=movement_state,
        person_name=person_name,
        face_status=face_status,
    )
@router.delete('/threads/ended')
@router.delete('/tracks/ended')
def clear_ended_threads(request:Request):
    res = svc(request).clear_ended_threads()
    return {"status": "cleared", **res}
@router.get('/threads/{track_id}')
@router.get('/tracks/{track_id}/thread')
def activity_thread(track_id:str,request:Request):
    thread=svc(request).get_track_thread(track_id)
    if not thread: raise HTTPException(404,"activity thread not found")
    return thread
@router.get('/events')
def events(request:Request,camera_id:str|None=None,severity:str|None=None,limit:int=100,offset:int=0):
    limit=max(1,min(limit,500));offset=max(0,offset)
    query="SELECT * FROM events WHERE 1=1";args=[]
    if camera_id:query+=" AND camera_id=?";args.append(camera_id)
    if severity:query+=" AND severity=?";args.append(severity.upper())
    return rows(svc(request).db.execute(query+" ORDER BY timestamp DESC LIMIT ? OFFSET ?",[*args,limit,offset]))
@router.get('/events/{event_id}')
def event(event_id:str,request:Request):
    result=item(svc(request).db.execute("SELECT * FROM events WHERE event_id=?",(event_id,)).fetchone())
    if not result:raise HTTPException(404,"event not found")
    result['evidence']=rows(svc(request).db.execute("SELECT * FROM evidence WHERE event_id=?",(event_id,)));return result
@router.delete('/events/clear')
def clear_events(request:Request,include_alerts:bool=True):
    res=svc(request).clear_events(clear_alerts=include_alerts)
    return {"status":"cleared",**res}
@router.get('/alerts')
def alerts(request:Request,status:str|None=None):
    q="SELECT * FROM alerts";args=()
    if status:q+=" WHERE status=?";args=(status.upper(),)
    return rows(svc(request).db.execute(q+" ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END, timestamp DESC",args))
@router.post('/alerts/acknowledge-all')
def acknowledge_all(request:Request,payload:AlertsBatchAction=AlertsBatchAction()):
    s=svc(request)
    if payload.alert_ids:
        placeholders=",".join("?" for _ in payload.alert_ids)
        cursor=s.db.execute(f"UPDATE alerts SET status='ACKNOWLEDGED',acknowledged_at=datetime('now'),acknowledged_by=? WHERE status='ACTIVE' AND alert_id IN ({placeholders})",(payload.operator,*payload.alert_ids))
    else:
        cursor=s.db.execute("UPDATE alerts SET status='ACKNOWLEDGED',acknowledged_at=datetime('now'),acknowledged_by=? WHERE status='ACTIVE'",(payload.operator,))
    s.db.commit()
    return {"status":"ok","acknowledged_count":cursor.rowcount}
@router.post('/alerts/{alert_id}/acknowledge')
def acknowledge(alert_id:str,request:Request,payload:AlertAction=AlertAction()):
    s=svc(request); s.db.execute("UPDATE alerts SET status='ACKNOWLEDGED',acknowledged_at=datetime('now'),acknowledged_by=? WHERE alert_id=?",(payload.operator,alert_id));s.db.commit();result=item(s.db.execute("SELECT * FROM alerts WHERE alert_id=?",(alert_id,)).fetchone())
    if not result:raise HTTPException(404,"alert not found")
    return result
@router.get('/evidence')
def evidence(request:Request,event_id:str|None=None,limit:int=30):
    q="SELECT * FROM evidence";args=[]
    if event_id:q+=" WHERE event_id=?";args.append(event_id)
    return rows(svc(request).db.execute(q+" ORDER BY created_at DESC LIMIT ?",[*args,min(limit,30)]))
@router.delete('/evidence/clear')
def clear_evidence(request:Request):
    count=svc(request).clear_evidence()
    return {"status":"cleared","deleted":count,"cache_limit":30}
@router.get('/evidence/{evidence_id}')
def single_evidence(evidence_id: str, request: Request):
    result = item(svc(request).db.execute("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone())
    if not result: raise HTTPException(404, "evidence not found")
    return result
@router.get('/evidence/{evidence_id}/file')
def evidence_file(evidence_id: str, request: Request):
    s = svc(request)
    file_path = s.settings.evidence_directory / f"{evidence_id}.jpg"
    if file_path.exists():
        return FileResponse(file_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    row = item(s.db.execute("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone())
    if not row:
        raise HTTPException(404, "evidence not found")

    if row.get("storage_reference"):
        ref_path = s.settings.evidence_directory / row["storage_reference"].lstrip("/")
        if ref_path.exists() and ref_path.is_file():
            return FileResponse(ref_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    camera_id = "CAM-01"
    bounding_box = None
    if row.get("event_id"):
        evt = item(s.db.execute("SELECT camera_id, track_id FROM events WHERE event_id=?", (row["event_id"],)).fetchone())
        if evt:
            if evt.get("camera_id"):
                camera_id = evt["camera_id"]
            if evt.get("track_id"):
                det = item(s.db.execute("SELECT bounding_box FROM detections WHERE track_id=? ORDER BY timestamp ASC LIMIT 1", (evt["track_id"],)).fetchone())
                if det and det.get("bounding_box"):
                    bounding_box = det["bounding_box"]

    hub = getattr(request.app.state, 'camera_hub', None)
    if hub:
        jpeg = hub.get_snapshot_jpeg(camera_id, bounding_box=bounding_box)
        if jpeg:
            try:
                (s.settings.evidence_directory / f"{evidence_id}.jpg").write_bytes(jpeg)
            except Exception:
                pass
            return Response(content=jpeg, media_type="image/jpeg")

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
        <rect width="640" height="360" fill="#080d12"/>
        <rect x="20" y="20" width="600" height="320" fill="#101720" rx="12" stroke="#212f40" stroke-width="2"/>
        <circle cx="320" cy="150" r="38" fill="#182330" stroke="#2FCC8B" stroke-width="2"/>
        <path d="M308 150l8 8 16-16" fill="none" stroke="#2FCC8B" stroke-width="3" stroke-linecap="round"/>
        <text x="320" y="215" fill="#f2f2f0" font-family="sans-serif" font-weight="bold" font-size="14" text-anchor="middle">EVIDENCE {evidence_id}</text>
        <text x="320" y="240" fill="#9a9a96" font-family="sans-serif" font-size="11" text-anchor="middle">TYPE: {row.get("type", "SNAPSHOT")} | EVENT: {row.get("event_id", "N/A")}</text>
    </svg>'''
    return Response(content=svg.encode("utf-8"), media_type="image/svg+xml")

@router.post('/evidence',status_code=201)
def register_evidence(payload:EvidenceInput,request:Request):
    s=svc(request)
    if not s.db.execute("SELECT 1 FROM events WHERE event_id=?",(payload.event_id,)).fetchone(): raise HTTPException(404,"event not found")
    return s.record_evidence(payload.event_id,payload.type,payload.storage_reference,payload.integrity_hash)
@router.post('/observations',status_code=201)
async def observation(payload:ObservationInput,request:Request): return await svc(request).ingest(payload.model_dump())
@router.post('/audio/observations',status_code=201)
async def audio_observation(payload:AudioObservationInput,request:Request): return await svc(request).ingest_audio(payload.model_dump())

# Intelligent Incident Correlation Engine Endpoints
@router.get('/incidents')
def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    camera_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    request: Request = None,
):
    return {"incidents": svc(request).get_incidents(status=status, severity=severity, camera_id=camera_id, limit=limit, offset=offset)}

@router.get('/incidents/summary')
def get_incidents_summary(request: Request):
    return svc(request).get_incidents_summary()

@router.get('/incidents/{incident_id}')
def get_incident_detail(incident_id: str, request: Request):
    inc = svc(request).get_incident(incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    return inc

@router.post('/incidents/{incident_id}/acknowledge')
def acknowledge_incident(incident_id: str, payload: dict = Body(default={}), request: Request = None):
    operator = payload.get("operator", "Operator") if isinstance(payload, dict) else "Operator"
    inc = svc(request).acknowledge_incident(incident_id, operator)
    if not inc:
        raise HTTPException(404, "incident not found")
    return inc

@router.post('/incidents/{incident_id}/resolve')
def resolve_incident(incident_id: str, payload: dict = Body(default={}), request: Request = None):
    operator = payload.get("operator", "Operator") if isinstance(payload, dict) else "Operator"
    inc = svc(request).resolve_incident(incident_id, operator)
    if not inc:
        raise HTTPException(404, "incident not found")
    return inc

