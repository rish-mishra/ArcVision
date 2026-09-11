"""FastAPI routes: upload, job status, results, video delivery, session history."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.config import CONFIG, PROJECT_ROOT, UPLOADS_DIR
from app.logging_config import get_logger
from app.pipeline.job_manager import job_manager
from app.pipeline.video_io import VideoValidationError, validate_video
from app.storage import repository

log = get_logger("api.routes")
router = APIRouter(prefix="/api")


@router.post("/sessions/upload")
async def upload_session(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in CONFIG.video.allowed_extensions:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {CONFIG.video.allowed_extensions}")

    safe_id = uuid.uuid4().hex[:16]
    dest = UPLOADS_DIR / f"{safe_id}{ext}"
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        await file.close()

    try:
        validate_video(dest)
    except VideoValidationError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, detail={"code": e.code, "message": str(e)})

    session_id = job_manager.submit(dest, file.filename or dest.name)
    return {"session_id": session_id}


@router.get("/sessions/{session_id}/status")
async def get_status(session_id: str):
    job = job_manager.get(session_id)
    if job is None:
        row = repository.get_session(session_id)
        if row is None:
            raise HTTPException(404, "Session not found")
        return {"session_id": session_id, "status": row["status"], "stage": row["status"],
                 "stage_label": row["status"].title(), "progress": 1.0 if row["status"] == "completed" else 0.0,
                 "error": row["error_message"], "created_at": row["created_at"]}
    return {
        "session_id": job.session_id, "status": job.status, "stage": job.stage,
        "stage_label": job.stage_label, "progress": job.progress, "error": job.error,
        "error_code": job.error_code, "created_at": job.created_at,
    }


@router.get("/sessions/{session_id}/results")
async def get_results(session_id: str):
    row = repository.get_session(session_id)
    if row is None:
        raise HTTPException(404, "Session not found")
    if row["status"] in ("failed", "interrupted"):
        raise HTTPException(422, detail={"message": row["error_message"]})
    if row["status"] != "completed" or not row["analysis_json"]:
        raise HTTPException(409, "Session is still processing")
    payload = json.loads(row["analysis_json"])
    payload["session_id"] = session_id
    payload["original_filename"] = row["original_filename"]
    payload["created_at"] = row["created_at"]
    payload["has_annotated_video"] = bool(row["annotated_video_path"])
    payload["has_diagnostic_video"] = bool(row["diagnostic_video_path"])
    return JSONResponse(payload)


@router.get("/sessions")
async def list_sessions():
    return repository.list_sessions()


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    repository.delete_session(session_id)
    return {"deleted": session_id}


@router.get("/sessions/{session_id}/video/{kind}")
async def get_video(session_id: str, kind: str):
    if kind not in ("annotated", "diagnostic"):
        raise HTTPException(400, "kind must be 'annotated' or 'diagnostic'")
    row = repository.get_session(session_id)
    if row is None:
        raise HTTPException(404, "Session not found")
    path_str = row["annotated_video_path"] if kind == "annotated" else row["diagnostic_video_path"]
    if not path_str or not Path(path_str).exists():
        raise HTTPException(404, f"{kind} video not available for this session")
    return FileResponse(path_str, media_type="video/mp4")


@router.get("/methodology")
async def get_methodology():
    doc_path = PROJECT_ROOT / "docs" / "METHODOLOGY.md"
    if not doc_path.exists():
        raise HTTPException(404, "Methodology document not found")
    return {"markdown": doc_path.read_text(encoding="utf-8")}
