from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .services.compositor import PRINT_PRESETS, compose_image, get_canvas_config

app = FastAPI(title="Photo Booth API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT_DIR = Path("/app")
DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
FRAMES_DIR = Path(os.getenv("FRAMES_DIR", "./shared/frames")).resolve()
DEFAULT_SIZE = os.getenv("DEFAULT_PRINT_SIZE", "4x6")

ORIGINALS_DIR = DATA_DIR / "originals"
PREVIEWS_DIR = DATA_DIR / "previews"
FINALS_DIR = DATA_DIR / "finals"
ARCHIVE_DIR = DATA_DIR / "archive"
for d in [ORIGINALS_DIR, PREVIEWS_DIR, FINALS_DIR, ARCHIVE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Simple v1 in-memory queue store; can be moved to Redis/DB later.
JOBS: dict[str, dict] = {}

_FILENAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]+")
COMPOSE_CACHE_VERSION = "fit3"


def _safe_filename_component(value: str) -> str:
    value = (value or "").strip().lower()
    value = _FILENAME_SAFE_RE.sub("-", value).strip("-")
    return value if value else "noframe"


def _preview_filename(image_id: str, size: str, orientation: str, frame_id: str) -> str:
    return f"{image_id}__{COMPOSE_CACHE_VERSION}__{size}__{orientation}__{_safe_filename_component(frame_id)}.jpg"


def _final_filename(image_id: str, size: str, orientation: str, frame_id: str, ext: str) -> str:
    ext = ext.lower()
    return f"{image_id}__{COMPOSE_CACHE_VERSION}__{size}__{orientation}__{_safe_filename_component(frame_id)}.{ext}"


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "photo-booth-api"}


@app.get("/frames")
def list_frames(size: str = DEFAULT_SIZE) -> dict:
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
    path = FRAMES_DIR / size / frame_id / "frame.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Frame template not found")
    return FileResponse(path, media_type="image/png")


@app.post("/frames/upload")
async def upload_frame(
    size: str = Form(DEFAULT_SIZE),
    frame_name: str = Form(...),
    frame_file: UploadFile = File(...),
) -> dict:
    if size not in PRINT_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unsupported size '{size}'")
    if not frame_file.filename:
        raise HTTPException(status_code=400, detail="Missing frame file")

    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", frame_name.strip().lower()).strip("-")
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid frame_name")

    target_dir = FRAMES_DIR / size / slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "frame.png"
    target_path.write_bytes(await frame_file.read())
    return {"ok": True, "size": size, "frame_id": slug, "path": str(target_path.relative_to(FRAMES_DIR))}


@app.get("/options")
def get_options() -> dict:
    return {
        "sizes": list(PRINT_PRESETS.keys()),
        "orientations": ["portrait", "landscape"],
        "output_formats": ["png", "jpeg", "pdf"],
    }


@app.post("/compose/preview")
async def compose_preview(
    image: UploadFile = File(...),
    frame_id: str = Form(""),
    size: str = Form(DEFAULT_SIZE),
    orientation: str = Form("portrait"),
) -> dict:
    if not image.filename:
        raise HTTPException(status_code=400, detail="Missing image filename")

    suffix = Path(image.filename).suffix.lower() or ".jpg"
    image_id = uuid4().hex
    original_path = ORIGINALS_DIR / f"{image_id}{suffix}"

    payload = await image.read()
    original_path.write_bytes(payload)

    frame_path = FRAMES_DIR / size / frame_id / "frame.png" if frame_id else None
    frame_applied = bool(frame_path and frame_path.exists())
    preview_path = PREVIEWS_DIR / _preview_filename(
        image_id=image_id,
        size=size,
        orientation=orientation,
        frame_id=frame_id,
    )
    cfg = get_canvas_config(size=size, orientation=orientation)
    output = compose_image(original_path, frame_path=frame_path, cfg=cfg)
    output.save(preview_path, format="JPEG", quality=95)

    return {
        "image_id": image_id,
        "size": size,
        "orientation": orientation,
        "frame_id": frame_id,
        "frame_applied": frame_applied,
        "preview_url": f"/previews/{preview_path.name}",
    }


@app.get("/previews/{name}")
def get_preview(name: str):
    path = PREVIEWS_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(path)


class PreviewFromIdCreate(BaseModel):
    image_id: str
    frame_id: str = ""
    size: str = DEFAULT_SIZE
    orientation: str = Field(default="portrait", pattern="^(portrait|landscape)$")


@app.post("/compose/preview-from-id")
def compose_preview_from_id(payload: PreviewFromIdCreate) -> dict:
    original_candidates = list(ORIGINALS_DIR.glob(f"{payload.image_id}.*"))
    if not original_candidates:
        raise HTTPException(status_code=404, detail="Original image not found for image_id")
    original_path = original_candidates[0]

    frame_path = FRAMES_DIR / payload.size / payload.frame_id / "frame.png" if payload.frame_id else None
    frame_applied = bool(frame_path and frame_path.exists())

    preview_path = PREVIEWS_DIR / _preview_filename(
        image_id=payload.image_id,
        size=payload.size,
        orientation=payload.orientation,
        frame_id=payload.frame_id,
    )

    if preview_path.exists():
        return {
            "image_id": payload.image_id,
            "size": payload.size,
            "orientation": payload.orientation,
            "frame_id": payload.frame_id,
            "frame_applied": frame_applied,
            "preview_url": f"/previews/{preview_path.name}",
            "cached": True,
        }

    cfg = get_canvas_config(size=payload.size, orientation=payload.orientation)
    output = compose_image(original_path, frame_path=frame_path, cfg=cfg)
    output.save(preview_path, format="JPEG", quality=95)

    return {
        "image_id": payload.image_id,
        "size": payload.size,
        "orientation": payload.orientation,
        "frame_id": payload.frame_id,
        "frame_applied": frame_applied,
        "preview_url": f"/previews/{preview_path.name}",
        "cached": False,
    }


@app.post("/compose/final")
def compose_final(payload: FinalCreate) -> dict:
    original_candidates = list(ORIGINALS_DIR.glob(f"{payload.image_id}.*"))
    if not original_candidates:
        raise HTTPException(status_code=404, detail="Original image not found for image_id")
    original_path = original_candidates[0]

    frame_path = FRAMES_DIR / payload.size / payload.frame_id / "frame.png" if payload.frame_id else None
    cfg = get_canvas_config(size=payload.size, orientation=payload.orientation)
    output = compose_image(original_path, frame_path=frame_path, cfg=cfg)

    ext = payload.output_format.lower()
    filename_ext = ext
    if ext == "jpeg":
        filename_ext = "jpg"
    final_path = FINALS_DIR / _final_filename(
        image_id=payload.image_id,
        size=payload.size,
        orientation=payload.orientation,
        frame_id=payload.frame_id,
        ext=filename_ext,
    )
    if ext == "pdf":
        output.convert("RGB").save(final_path, format="PDF", resolution=300.0)
    elif ext == "jpeg":
        output.save(final_path, format="JPEG", quality=95)
    else:
        output.save(final_path, format="PNG")

    # Cleanup all cached previews for this image_id once final output is prepared.
    for fp in PREVIEWS_DIR.glob(f"{payload.image_id}__*.jpg"):
        fp.unlink(missing_ok=True)
    legacy_preview = PREVIEWS_DIR / f"{payload.image_id}.jpg"
    legacy_preview.unlink(missing_ok=True)

    return {
        "image_id": payload.image_id,
        "size": payload.size,
        "orientation": payload.orientation,
        "frame_id": payload.frame_id,
        "output_format": ext,
        "final_url": f"/finals/{final_path.name}",
    }


@app.get("/finals/{name}")
def get_final(name: str):
    path = FINALS_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Final output not found")
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
    preview_path = PREVIEWS_DIR / _preview_filename(
        image_id=payload.image_id,
        size=payload.size,
        orientation=payload.orientation,
        frame_id=payload.frame_id,
    )
    preview_name = preview_path.name
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview does not exist for selection")

    job_id = uuid4().hex
    job = {
        "id": job_id,
        "image_id": payload.image_id,
        "preview_name": preview_name,
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
def cleanup_runtime(days: int = 2) -> dict:
    """
    Remove old preview/final files to keep kiosk storage manageable.
    """
    if days < 0:
        raise HTTPException(status_code=400, detail="days must be >= 0")

    threshold = datetime.now(timezone.utc) - timedelta(days=days)
    removed = {"previews": 0, "finals": 0}

    for folder, key in [(PREVIEWS_DIR, "previews"), (FINALS_DIR, "finals")]:
        for fp in folder.glob("*"):
            if not fp.is_file():
                continue
            mtime = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc)
            if mtime < threshold:
                fp.unlink(missing_ok=True)
                removed[key] += 1

    return {"ok": True, "removed": removed, "threshold": threshold.isoformat()}
