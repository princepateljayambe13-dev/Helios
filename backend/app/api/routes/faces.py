"""FastAPI routes for HELIOS Facial Recognition module."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.database.models_face import (
    AssociateFaceInput,
    FaceRecognitionItem,
    FaceSummaryResponse,
    RegisteredPersonItem,
    RegisterPersonInput,
)

router = APIRouter()


def mgr(request: Request):
    """Retrieve FaceRecognitionManager from HeliosService."""
    helios = request.app.state.helios
    if not hasattr(helios, "face_recognition_manager"):
        raise HTTPException(500, "Face recognition manager is not initialized.")
    return helios.face_recognition_manager


@router.get("/summary", response_model=FaceSummaryResponse)
def get_face_summary(request: Request):
    """Get aggregate statistics for face recognition system."""
    return mgr(request).get_summary()


@router.get("/recognitions")
def get_recognitions(
    request: Request,
    status: str | None = Query(None, description="RECOGNIZED, UNCLASSIFIED, or ALL"),
    camera_id: str | None = Query(None),
    search: str | None = Query(None, description="Filter by person name, ID, or track"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List facial recognition events (both recognized and unclassified)."""
    return mgr(request).get_recognitions(
        status=status,
        camera_id=camera_id,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/recognitions/{recognition_id}")
def get_recognition(recognition_id: str, request: Request):
    """Fetch details of a single recognition event."""
    item = mgr(request).get_recognition(recognition_id)
    if not item:
        raise HTTPException(404, f"Face recognition '{recognition_id}' not found.")
    return item


@router.post("/recognitions/{recognition_id}/associate")
def associate_unclassified_face(
    recognition_id: str,
    payload: AssociateFaceInput,
    request: Request,
):
    """Associate an unclassified face with a person (existing person_id or new name)."""
    try:
        updated = mgr(request).associate_unclassified_face(
            recognition_id=recognition_id,
            person_id=payload.person_id,
            name=payload.name,
            role=payload.role,
            notes=payload.notes,
        )
        return {"status": "success", "recognition": updated}
    except KeyError as err:
        raise HTTPException(404, str(err))
    except ValueError as err:
        raise HTTPException(400, str(err))
    except Exception as err:
        raise HTTPException(500, f"Association failed: {err}")


@router.get("/persons")
def get_registered_persons(request: Request):
    """List all enrolled/registered persons."""
    return mgr(request).get_registered_persons()


@router.post("/persons", status_code=201)
async def register_person(
    request: Request,
    payload: RegisterPersonInput | None = None,
):
    """Enroll a new person with face photo and compute ArcFace embedding (JSON body)."""
    if payload is None:
        raise HTTPException(400, "Missing request body.")

    image_bytes = None
    if payload.image_base64:
        try:
            b64_str = payload.image_base64
            if "," in b64_str:
                b64_str = b64_str.split(",", 1)[1]
            image_bytes = base64.b64decode(b64_str)
        except Exception as err:
            raise HTTPException(400, f"Invalid base64 image data: {err}")
    else:
        raise HTTPException(400, "An image must be provided (image_base64).")

    try:
        person = mgr(request).register_person(
            name=payload.name,
            person_id=payload.person_id,
            role=payload.role,
            notes=payload.notes,
            image_bytes=image_bytes,
        )
        return {"status": "created", "person": person}
    except ValueError as err:
        raise HTTPException(400, str(err))
    except Exception as err:
        raise HTTPException(500, f"Registration failed: {err}")


@router.post("/persons/raw-upload", status_code=201)
async def register_person_raw_upload(
    request: Request,
    name: str = Query(...),
    person_id: str | None = Query(None),
    role: str = Query(""),
    notes: str = Query(""),
):
    """Enroll a new person with raw image bytes in request body."""
    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(400, "Request body is empty; expected image bytes.")

    try:
        person = mgr(request).register_person(
            name=name,
            person_id=person_id,
            role=role,
            notes=notes,
            image_bytes=image_bytes,
        )
        return {"status": "created", "person": person}
    except ValueError as err:
        raise HTTPException(400, str(err))
    except Exception as err:
        raise HTTPException(500, f"Registration failed: {err}")


@router.delete("/persons/{person_id}")
def delete_registered_person(person_id: str, request: Request):
    """Delete a registered person from the database."""
    ok = mgr(request).delete_registered_person(person_id)
    if not ok:
        raise HTTPException(404, f"Person '{person_id}' not found.")
    return {"status": "deleted", "person_id": person_id}


@router.get("/snapshots/{filename}")
def get_face_snapshot(filename: str, request: Request):
    """Serve a saved face snapshot JPEG with intelligent multi-directory and dynamic resolution."""
    import json
    safe_name = Path(filename).name
    m = mgr(request)

    # 1. Candidate filenames (with and without extension)
    candidate_names = [safe_name]
    if not safe_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        candidate_names.append(f"{safe_name}.jpg")

    # 2. Search candidate storage directories
    candidate_dirs = [
        m.storage_dir,
        Path("data/evidence/face"),
        Path("storage/evidence/face"),
        getattr(m.settings, "evidence_directory", Path("data/evidence")) / "face",
        getattr(m.settings, "evidence_directory", Path("data/evidence")),
    ]

    for c_dir in candidate_dirs:
        for c_name in candidate_names:
            candidate_path = Path(c_dir) / c_name
            if candidate_path.exists() and candidate_path.is_file():
                return FileResponse(candidate_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    # 3. Fallback: Lookup by recognition_id or person_id in SQLite
    clean_id = safe_name.replace(".jpg", "").replace(".png", "")
    row = m.db.execute(
        "SELECT bounding_box, camera_id, track_id FROM face_recognitions WHERE recognition_id=? OR snapshot_path LIKE ?",
        (clean_id, f"%{clean_id}%"),
    ).fetchone()

    if not row:
        row_p = m.db.execute("SELECT face_image_path FROM registered_faces WHERE person_id=?", (clean_id,)).fetchone()
        if row_p and row_p["face_image_path"]:
            p_ref = Path(row_p["face_image_path"].lstrip("/"))
            if p_ref.exists() and p_ref.is_file():
                return FileResponse(p_ref, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    # 4. Fallback: Dynamic frame crop from live camera stream if available
    if row and row["camera_id"]:
        hub = getattr(request.app.state, "camera_hub", None)
        if hub:
            bbox = None
            if row["bounding_box"]:
                try:
                    bbox = json.loads(row["bounding_box"]) if isinstance(row["bounding_box"], str) else row["bounding_box"]
                except Exception:
                    pass
            jpeg = hub.get_snapshot_jpeg(row["camera_id"], bounding_box=bbox)
            if jpeg:
                try:
                    (m.storage_dir / f"{clean_id}.jpg").write_bytes(jpeg)
                except Exception:
                    pass
                return Response(content=jpeg, media_type="image/jpeg")

    # 5. Stylized SVG avatar placeholder fallback
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">
        <rect width="300" height="300" fill="#080d12"/>
        <rect x="15" y="15" width="270" height="270" rx="12" fill="#101720" stroke="#212f40" stroke-width="2"/>
        <circle cx="150" cy="115" r="45" fill="#182330" stroke="#5c5c58" stroke-width="2"/>
        <path d="M75 240 C75 185, 225 185, 225 240" fill="#182330" stroke="#5c5c58" stroke-width="2"/>
        <text x="150" y="265" fill="#9a9a96" font-family="sans-serif" font-size="11" font-weight="bold" text-anchor="middle">FACIAL SNAPSHOT</text>
    </svg>"""
    return Response(content=svg.encode("utf-8"), media_type="image/svg+xml")


@router.delete("/clear")
def clear_face_recognitions(request: Request):
    """Clear recognition events history (retains registered persons)."""
    count = mgr(request).clear_recognitions()
    return {"status": "cleared", "deleted": count}
