from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import sys
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PIL import Image

# Safety guard against decompression bomb attacks while supporting up to 50 MP phone photos
Image.MAX_IMAGE_PIXELS = 50_000_000

logger = logging.getLogger("photo_booth.api")


def _console_log(msg: str) -> None:
    """Always visible in the run-api-standalone / uvicorn terminal (stderr)."""
    print(f"[photo-booth] {msg}", flush=True, file=sys.stderr)


from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .services.compositor import PRINT_PRESETS, compose_image, get_canvas_config
from .services.storage import LocalStorageService, StorageService, get_storage_service

# Security Limits
MAX_IMAGE_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_FRAME_UPLOAD_BYTES = 5 * 1024 * 1024   # 5 MB
FRAME_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{0,40}$")

PHOTOBOOTH_ADMIN_TOKEN = os.getenv("PHOTOBOOTH_ADMIN_TOKEN", "").strip()


def verify_admin_token(authorization: str | None = Header(None)) -> str:
    """
    Validates Bearer token against PHOTOBOOTH_ADMIN_TOKEN.
    If PHOTOBOOTH_ADMIN_TOKEN is unset or empty, admin routes are disabled (return 401).
    """
    if not PHOTOBOOTH_ADMIN_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Admin access is disabled. PHOTOBOOTH_ADMIN_TOKEN is not configured on the server.",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected 'Bearer <token>'.",
        )
    token = authorization[7:].strip()
    if not secrets.compare_digest(token, PHOTOBOOTH_ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid admin token.")
    return token


def validate_image_magic_bytes(payload: bytes) -> str:
    """Validates magic bytes for image uploads. Returns file suffix (.jpg, .png, .webp)."""
    if len(payload) >= 2 and payload.startswith(b"\xff\xd8"):
        return ".jpg"
    if len(payload) >= 8 and payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return ".webp"
    raise HTTPException(
        status_code=415,
        detail="Unsupported media type. Image must be a valid JPEG, PNG, or WebP file.",
    )


def validate_frame_id(frame_id: str) -> str:
    fid = (frame_id or "").strip()
    if fid and not FRAME_ID_PATTERN.match(fid):
        raise HTTPException(status_code=400, detail="Invalid frame_id. Must be alphanumeric, dashes, or underscores.")
    return fid


def validate_size(size: str) -> str:
    s = (size or "").strip()
    if s and s not in PRINT_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unsupported size '{s}'. Supported: {list(PRINT_PRESETS.keys())}")
    return s or "4x6"


def _env_truthy(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on", "y")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logging
    _console_log("--- Photo Booth API: env snapshot (startup) ---")
    storage = get_storage_service()
    if isinstance(storage, LocalStorageService):
        _console_log(f"DATA_DIR={storage.data_dir}")
    _console_log(f"ADMIN_AUTH_ENABLED={bool(PHOTOBOOTH_ADMIN_TOKEN)}")
    if _env_truthy("PHOTOBOOTH_COPY_FINAL_TO_PRINT_QUEUE"):
        qdir = Path(os.getenv("PHOTOBOOTH_PRINT_QUEUE_DIR", "./data/print-queue")).expanduser().resolve()
        _console_log(f"print-queue: ON → {qdir}")
    else:
        _console_log("print-queue: OFF")
    if _env_truthy("PHOTOBOOTH_COPY_FINAL_TO_DROPZONE"):
        dz_raw = (os.getenv("PHOTOBOOTH_DROPZONE_DIR") or "").strip()
        if dz_raw:
            _console_log(f"dropzone: ON → {Path(dz_raw).expanduser().resolve()}")
        else:
            _console_log("dropzone: ERROR — enabled but PHOTOBOOTH_DROPZONE_DIR is empty")
    else:
        _console_log("dropzone: OFF")
    yield


app = FastAPI(title="Photo Booth API", version="1.0.0", lifespan=lifespan)

cors_origins_raw = os.getenv("PHOTOBOOTH_CORS_ORIGINS", "*").strip()
cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()] if cors_origins_raw != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRAMES_DIR = Path(os.getenv("FRAMES_DIR", "./shared/frames")).resolve()
DEFAULT_SIZE = os.getenv("DEFAULT_PRINT_SIZE", "4x6")

# In-memory queue store for print jobs
JOBS: dict[str, dict] = {}


def _resolve_frame_path(size: str, frame_id: str) -> Path | None:
    if not frame_id:
        return None
    validate_frame_id(frame_id)
    target = (FRAMES_DIR / size / frame_id / "frame.png").resolve()
    # Path traversal protection
    if not str(target).startswith(str(FRAMES_DIR)):
        raise HTTPException(status_code=400, detail="Invalid frame path")
    return target if target.is_file() else None


def _copy_final_to_dropzone_with_logging(final_path: Path, image_id: str) -> None:
    if not _env_truthy("PHOTOBOOTH_COPY_FINAL_TO_DROPZONE"):
        return
    dz_raw = (os.getenv("PHOTOBOOTH_DROPZONE_DIR") or "").strip()
    if not dz_raw:
        _console_log("dropzone: ERROR — PHOTOBOOTH_COPY_FINAL_TO_DROPZONE is on but PHOTOBOOTH_DROPZONE_DIR is empty")
        return
    dest_dir = Path(dz_raw).expanduser().resolve()
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        _console_log(f"dropzone: ERROR mkdir {dest_dir}: {e!r}")
        return

    stem = final_path.stem
    dest = dest_dir / f"{stem}.jpg"
    if dest.exists():
        dest = dest_dir / f"{stem}_{int(time.time())}.jpg"

    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            shutil.copy2(str(final_path), str(dest))
            _console_log(f"dropzone: OK → {dest} (attempt {attempt}) image_id={image_id}")
            return
        except Exception as e1:
            last_err = e1
            try:
                shutil.copyfile(str(final_path), str(dest))
                _console_log(f"dropzone: OK (copyfile fallback) → {dest} image_id={image_id}")
                return
            except Exception as e2:
                last_err = e2
                time.sleep(0.35 * attempt)

    _console_log(f"dropzone: FAILED after retries image_id={image_id} last_err={last_err!r}")


class PrintJobCreate(BaseModel):
    image_id: str
    frame_id: str = ""
    size: str = DEFAULT_SIZE
    orientation: str = Field(default="portrait", pattern="^(portrait|landscape)$")
    copies: int = Field(default=1, ge=1, le=10)


class FinalCreate(BaseModel):
    image_id: str
    frame_id: str = ""
    size: str = DEFAULT_SIZE
    orientation: str = Field(default="portrait", pattern="^(portrait|landscape)$")
    output_format: str = Field(default="png", pattern="^(png|jpeg|pdf)$")


class PreviewFromIdCreate(BaseModel):
    image_id: str
    frame_id: str = ""
    size: str = DEFAULT_SIZE
    orientation: str = Field(default="portrait", pattern="^(portrait|landscape)$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
def health() -> dict:
    """Health check endpoint. Redacts file paths unless PHOTOBOOTH_DEBUG=1."""
    storage = get_storage_service()
    resp: dict = {
        "status": "ok",
        "service": "photo-booth-api",
        "print_queue_copy_enabled": _env_truthy("PHOTOBOOTH_COPY_FINAL_TO_PRINT_QUEUE"),
        "dropzone_copy_enabled": _env_truthy("PHOTOBOOTH_COPY_FINAL_TO_DROPZONE"),
        "admin_auth_enabled": bool(PHOTOBOOTH_ADMIN_TOKEN),
    }
    if _env_truthy("PHOTOBOOTH_DEBUG") and isinstance(storage, LocalStorageService):
        resp["data_dir"] = str(storage.data_dir)
        resp["print_watch_mode"] = (os.getenv("PHOTOBOOTH_PRINT_WATCH_MODE") or "finals").strip().lower()
        qdir = Path(os.getenv("PHOTOBOOTH_PRINT_QUEUE_DIR", str(storage.data_dir / "print-queue"))).expanduser().resolve()
        resp["print_queue_dir"] = str(qdir)
        dz_path = (os.getenv("PHOTOBOOTH_DROPZONE_DIR") or "").strip()
        resp["dropzone_dir"] = str(Path(dz_path).expanduser().resolve()) if dz_path else None
    return resp


PRINT_STATUS_FILENAME = ".photobooth-print-status.json"


@app.get("/print/status")
def print_status() -> dict:
    storage = get_storage_service()
    if isinstance(storage, LocalStorageService):
        path = storage.data_dir / PRINT_STATUS_FILENAME
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {
                        "state": data.get("state", "idle"),
                        "message": data.get("message"),
                        "file": data.get("file"),
                        "updated_at_ms": data.get("updated_at_ms"),
                    }
            except Exception:
                pass
    return {"state": "idle", "message": None, "file": None, "updated_at_ms": None}


@app.get("/frames")
def list_frames(size: str = DEFAULT_SIZE) -> dict:
    size = validate_size(size)
    size_dir = FRAMES_DIR / size
    if not size_dir.exists():
        return {"size": size, "frames": []}
    frames = []
    for frame_png in sorted(size_dir.glob("*/frame.png")):
        frames.append(
            {
                "id": frame_png.parent.name,
                "size": size,
                "path": str(frame_png.relative_to(FRAMES_DIR)),
            }
        )
    return {"size": size, "frames": frames}


@app.get("/frames/template/{size}/{frame_id}")
def get_frame_template(size: str, frame_id: str):
    size = validate_size(size)
    path = _resolve_frame_path(size, frame_id)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Frame template not found")
    return FileResponse(path, media_type="image/png")


@app.post("/frames/upload")
async def upload_frame(
    size: str = Form(DEFAULT_SIZE),
    frame_name: str = Form(...),
    frame_file: UploadFile = File(...),
    _token: str = Depends(verify_admin_token),
) -> dict:
    if size not in PRINT_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unsupported size '{size}'")
    if not frame_file.filename:
        raise HTTPException(status_code=400, detail="Missing frame file")

    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", frame_name.strip().lower()).strip("-")
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid frame_name")

    payload = await frame_file.read(MAX_FRAME_UPLOAD_BYTES + 1)
    if len(payload) > MAX_FRAME_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Payload Too Large: frame file exceeds 5 MB limit.")
    if len(payload) < 8 or not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=415, detail="Unsupported media type. Frame must be a valid PNG image.")

    target_dir = FRAMES_DIR / size / slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "frame.png"
    target_path.write_bytes(payload)
    return {"ok": True, "size": size, "frame_id": slug, "path": str(target_path.relative_to(FRAMES_DIR))}


@app.get("/options")
def get_options(include_8x11: bool = False) -> dict:
    sizes = ["4x6", "5x7"]
    if include_8x11:
        sizes.append("8x11")
    return {
        "sizes": sizes,
        "orientations": ["portrait", "landscape"],
        "output_formats": ["png", "jpeg", "pdf"],
    }


@app.post("/compose/preview")
async def compose_preview(
    image: UploadFile = File(...),
    frame_id: str = Form(""),
    size: str = Form(DEFAULT_SIZE),
    orientation: str = Form("portrait"),
    display_name: str = Form(""),
    capture_ts: str = Form(""),
) -> dict:
    if not image.filename:
        raise HTTPException(status_code=400, detail="Missing image filename")

    size = validate_size(size)
    frame_id = validate_frame_id(frame_id)

    payload = await image.read(MAX_IMAGE_UPLOAD_BYTES + 1)
    if len(payload) > MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Payload Too Large: image exceeds 15 MB limit.")
    if not payload:
        raise HTTPException(status_code=400, detail="Empty image payload")

    suffix = validate_image_magic_bytes(payload)

    storage = get_storage_service()
    session_folder = storage.get_session_folder()
    image_id = storage.allocate_image_id(session_folder, display_name, capture_ts or None)
    original_path = storage.save_original(session_folder, image_id, suffix, payload)

    frame_path = _resolve_frame_path(size, frame_id)
    frame_applied = bool(frame_path and frame_path.exists())

    preview_path, preview_url = storage.preview_path_for(session_folder, image_id, size, orientation, frame_id)
    cfg = get_canvas_config(size=size, orientation=orientation)
    output = compose_image(original_path, frame_path=frame_path, cfg=cfg)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(preview_path, format="JPEG", quality=95)

    return {
        "image_id": image_id,
        "session_folder": session_folder,
        "size": size,
        "orientation": orientation,
        "frame_id": frame_id,
        "frame_applied": frame_applied,
        "preview_url": preview_url,
    }


def _safe_nested_filename(filename: str) -> None:
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=404, detail="Not found")


@app.get("/previews/{session}/{filename}")
def get_preview_in_session(session: str, filename: str):
    if not session.startswith("PhotoBooth_"):
        raise HTTPException(status_code=404, detail="Preview not found")
    _safe_nested_filename(filename)
    storage = get_storage_service()
    if isinstance(storage, LocalStorageService):
        path = storage.data_dir / session / "previews" / filename
        if path.exists() and path.is_file():
            return FileResponse(path)
    raise HTTPException(status_code=404, detail="Preview not found")


@app.get("/previews/{name}")
def get_preview_legacy_flat(name: str):
    storage = get_storage_service()
    if isinstance(storage, LocalStorageService):
        path = storage.previews_dir / name
        if path.exists() and path.is_file():
            return FileResponse(path)
    raise HTTPException(status_code=404, detail="Preview not found")


@app.post("/compose/preview-from-id")
def compose_preview_from_id(payload: PreviewFromIdCreate) -> dict:
    storage = get_storage_service()
    found = storage.find_original(payload.image_id)
    if not found:
        raise HTTPException(status_code=404, detail="Original image not found for image_id")
    original_path, session_folder = found

    size = validate_size(payload.size)
    frame_id = validate_frame_id(payload.frame_id)
    frame_path = _resolve_frame_path(size, frame_id)
    frame_applied = bool(frame_path and frame_path.exists())

    preview_path, preview_url = storage.preview_path_for(
        session_folder,
        payload.image_id,
        size,
        payload.orientation,
        frame_id,
    )

    if preview_path.exists():
        return {
            "image_id": payload.image_id,
            "session_folder": session_folder or None,
            "size": size,
            "orientation": payload.orientation,
            "frame_id": frame_id,
            "frame_applied": frame_applied,
            "preview_url": preview_url,
            "cached": True,
        }

    cfg = get_canvas_config(size=size, orientation=payload.orientation)
    output = compose_image(original_path, frame_path=frame_path, cfg=cfg)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(preview_path, format="JPEG", quality=95)

    return {
        "image_id": payload.image_id,
        "session_folder": session_folder or None,
        "size": size,
        "orientation": payload.orientation,
        "frame_id": frame_id,
        "frame_applied": frame_applied,
        "preview_url": preview_url,
        "cached": False,
    }


@app.post("/compose/final")
def compose_final(payload: FinalCreate) -> dict:
    try:
        return _compose_final_body(payload)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("compose_final failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


def _compose_final_body(payload: FinalCreate) -> dict:
    storage = get_storage_service()
    found = storage.find_original(payload.image_id)
    if not found:
        raise HTTPException(status_code=404, detail="Original image not found for image_id")
    original_path, session_folder = found

    size = validate_size(payload.size)
    frame_id = validate_frame_id(payload.frame_id)
    frame_path = _resolve_frame_path(size, frame_id)
    cfg = get_canvas_config(size=size, orientation=payload.orientation)
    output = compose_image(original_path, frame_path=frame_path, cfg=cfg)

    ext = payload.output_format.lower()
    final_path, final_url = storage.final_path_for(
        session_folder,
        payload.image_id,
        size,
        payload.orientation,
        frame_id,
        ext,
    )
    final_path.parent.mkdir(parents=True, exist_ok=True)
    if ext == "pdf":
        output.convert("RGB").save(final_path, format="PDF", resolution=300.0)
    elif ext == "jpeg":
        output.save(final_path, format="JPEG", quality=95)
    else:
        output.save(final_path, format="PNG")

    # Cleanup cached previews for this image_id once final output is prepared.
    storage.delete_cached_previews(session_folder, payload.image_id)

    # Optional: copy into print-queue
    if _env_truthy("PHOTOBOOTH_COPY_FINAL_TO_PRINT_QUEUE") and isinstance(storage, LocalStorageService):
        try:
            qdir = Path(os.getenv("PHOTOBOOTH_PRINT_QUEUE_DIR", str(storage.data_dir / "print-queue"))).expanduser().resolve()
            qdir.mkdir(parents=True, exist_ok=True)
            dest = qdir / f"{final_path.stem}_{uuid4().hex[:8]}{final_path.suffix}"
            shutil.copy2(final_path, dest)
            _console_log(f"print-queue OK: copied → {dest}")
        except OSError as e:
            _console_log(f"print-queue FAILED: {e}")

    # Optional: copy final to external folder (e.g. Google Drive)
    _copy_final_to_dropzone_with_logging(final_path, payload.image_id)

    return {
        "image_id": payload.image_id,
        "session_folder": session_folder or None,
        "size": size,
        "orientation": payload.orientation,
        "frame_id": frame_id,
        "output_format": ext,
        "final_url": final_url,
    }


@app.get("/finals/{session}/{filename}")
def get_final_in_session(session: str, filename: str):
    if not session.startswith("PhotoBooth_"):
        raise HTTPException(status_code=404, detail="Final output not found")
    _safe_nested_filename(filename)
    storage = get_storage_service()
    if isinstance(storage, LocalStorageService):
        path = storage.data_dir / session / "finals" / filename
        if path.exists() and path.is_file():
            return _file_response_final(path)
    raise HTTPException(status_code=404, detail="Final output not found")


@app.get("/finals/{name}")
def get_final_legacy_flat(name: str):
    storage = get_storage_service()
    if isinstance(storage, LocalStorageService):
        path = storage.finals_dir / name
        if path.exists() and path.is_file():
            return _file_response_final(path)
    raise HTTPException(status_code=404, detail="Final output not found")


def _file_response_final(path: Path) -> FileResponse:
    name = path.name
    lower = name.lower()
    if lower.endswith(".pdf"):
        media_type = "application/pdf"
    elif lower.endswith(".jpg") or lower.endswith(".jpeg"):
        media_type = "image/jpeg"
    else:
        media_type = "image/png"
    return FileResponse(path, media_type=media_type)


@app.post("/jobs/print")
def create_print_job(payload: PrintJobCreate) -> dict:
    storage = get_storage_service()
    found = storage.find_original(payload.image_id)
    if not found:
        raise HTTPException(status_code=404, detail="Original image not found for image_id")
    _original_path, session_folder = found
    preview_path, _ = storage.preview_path_for(
        session_folder,
        payload.image_id,
        payload.size,
        payload.orientation,
        payload.frame_id,
    )
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview does not exist for selection")

    job_id = uuid4().hex
    job = {
        "id": job_id,
        "image_id": payload.image_id,
        "session_folder": session_folder or None,
        "preview_name": preview_path.name,
        "copies": payload.copies,
        "status": "ready_to_print",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    JOBS[job_id] = job
    return job


@app.get("/jobs")
def list_jobs(status: str = "") -> dict:
    items = list(JOBS.values())
    if status:
        items = [j for j in items if j.get("status") == status]
    items.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return {"count": len(items), "jobs": items}


@app.post("/admin/cleanup")
def cleanup_runtime(
    days: int = 2,
    _token: str = Depends(verify_admin_token),
) -> dict:
    """Removes old preview/final files. Protected by PHOTOBOOTH_ADMIN_TOKEN."""
    if days < 0:
        raise HTTPException(status_code=400, detail="days must be >= 0")

    storage = get_storage_service()
    removed = storage.cleanup(days)
    return {"ok": True, "removed": removed}


# Optionally serve static web UI
WEB_DIR = Path(os.getenv("WEB_DIR", "")).resolve() if os.getenv("WEB_DIR") else None
if WEB_DIR and WEB_DIR.is_dir() and (WEB_DIR / "index.html").is_file():
    from fastapi.staticfiles import StaticFiles

    _console_log(f"Serving static web UI from {WEB_DIR}")
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
