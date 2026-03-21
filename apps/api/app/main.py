from __future__ import annotations

import json
import os
import shutil
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

# Legacy flat layout (older captures / Docker default mount) — still supported for reads.
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


def _env_truthy(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on", "y")


def _safe_filename_component(value: str) -> str:
    value = (value or "").strip().lower()
    value = _FILENAME_SAFE_RE.sub("-", value).strip("-")
    return value if value else "noframe"


def _safe_display_name(name: str) -> str:
    """Match web client: optional name, filesystem-safe, max 60 chars."""
    val = (name or "").strip()
    if not val:
        return "NO_NAME"
    s = _FILENAME_SAFE_RE.sub("_", val)
    s = s[:60].strip("_")
    return s if s else "NO_NAME"


def _session_folder_name(dt: datetime | None = None) -> str:
    """Daily folder under DATA_DIR: PhotoBooth_DDMMYYYY (local time)."""
    dt = dt or datetime.now()
    return f"PhotoBooth_{dt.day:02d}{dt.month:02d}{dt.year}"


def _session_subdirs(session: str) -> tuple[Path, Path, Path]:
    base = DATA_DIR / session
    return base / "originals", base / "previews", base / "finals"


def _ensure_session_dirs(session: str) -> tuple[Path, Path, Path]:
    o, p, f = _session_subdirs(session)
    o.mkdir(parents=True, exist_ok=True)
    p.mkdir(parents=True, exist_ok=True)
    f.mkdir(parents=True, exist_ok=True)
    return o, p, f


_CAPTURE_TS_RE = re.compile(r"^\d{8}_\d{6}$")


def _allocate_image_id(display_name: str, originals_dir: Path, capture_ts: str | None = None) -> str:
    cts = (capture_ts or "").strip()
    if _CAPTURE_TS_RE.match(cts):
        ts = cts
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{_safe_display_name(display_name)}_{ts}"
    candidate = base
    while list(originals_dir.glob(f"{candidate}.*")):
        candidate = f"{base}_{uuid4().hex[:4]}"
    return candidate


def _find_original_path(image_id: str) -> tuple[Path, str] | None:
    """
    Locate original file. Returns (path, session_folder) where session_folder is
    "" for legacy flat layout, or e.g. PhotoBooth_14032026 for daily folders.
    """
    for p in ORIGINALS_DIR.glob(f"{image_id}.*"):
        if p.is_file():
            return p, ""
    for session_dir in sorted(DATA_DIR.glob("PhotoBooth_*"), reverse=True):
        od = session_dir / "originals"
        if not od.is_dir():
            continue
        for p in od.glob(f"{image_id}.*"):
            if p.is_file():
                return p, session_dir.name
    return None


def _preview_filename_legacy(image_id: str, size: str, orientation: str, frame_id: str) -> str:
    return f"{image_id}__{COMPOSE_CACHE_VERSION}__{size}__{orientation}__{_safe_filename_component(frame_id)}.jpg"


def _final_filename_legacy(image_id: str, size: str, orientation: str, frame_id: str, ext: str) -> str:
    ext = ext.lower()
    return f"{image_id}__{COMPOSE_CACHE_VERSION}__{size}__{orientation}__{_safe_filename_component(frame_id)}.{ext}"


def _preview_stem_short(image_id: str, frame_id: str) -> str:
    return f"{image_id}__{_safe_filename_component(frame_id)}"


def _preview_path_for(
    session_folder: str,
    image_id: str,
    size: str,
    orientation: str,
    frame_id: str,
) -> Path:
    if session_folder:
        _, prev_dir, _ = _session_subdirs(session_folder)
        return prev_dir / f"{_preview_stem_short(image_id, frame_id)}.jpg"
    return PREVIEWS_DIR / _preview_filename_legacy(image_id, size, orientation, frame_id)


def _final_path_for(session_folder: str, image_id: str, size: str, orientation: str, frame_id: str, ext: str) -> Path:
    ext = ext.lower()
    filename_ext = "jpg" if ext == "jpeg" else ext
    if session_folder:
        _, _, fin_dir = _session_subdirs(session_folder)
        return fin_dir / f"{image_id}_final.{filename_ext}"
    return FINALS_DIR / _final_filename_legacy(image_id, size, orientation, frame_id, filename_ext)


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


PRINT_STATUS_FILENAME = ".photobooth-print-status.json"


@app.get("/print/status")
def print_status() -> dict:
    """
    Latest host print_watcher state (written under DATA_DIR).
    Used by the web UI for 'Printing now…' and printer error visibility.
    """
    path = DATA_DIR / PRINT_STATUS_FILENAME
    if not path.is_file():
        return {"state": "idle", "message": None, "file": None, "updated_at_ms": None}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        return {
            "state": data.get("state", "idle"),
            "message": data.get("message"),
            "file": data.get("file"),
            "updated_at_ms": data.get("updated_at_ms"),
        }
    except (OSError, ValueError, json.JSONDecodeError):
        return {"state": "idle", "message": None, "file": None, "updated_at_ms": None}


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
def get_options(include_8x11: bool = False) -> dict:
    sizes = ["4x6", "5x7"]
    # 8x11 is intentionally hidden by default (enable via `?include_8x11=1`).
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

    suffix = Path(image.filename).suffix.lower() or ".jpg"
    session_folder = _session_folder_name()
    orig_dir, prev_dir, _fin_dir = _ensure_session_dirs(session_folder)
    image_id = _allocate_image_id(display_name, orig_dir, capture_ts or None)
    original_path = orig_dir / f"{image_id}{suffix}"

    payload = await image.read()
    original_path.write_bytes(payload)

    frame_path = FRAMES_DIR / size / frame_id / "frame.png" if frame_id else None
    frame_applied = bool(frame_path and frame_path.exists())
    preview_path = _preview_path_for(session_folder, image_id, size, orientation, frame_id)
    cfg = get_canvas_config(size=size, orientation=orientation)
    output = compose_image(original_path, frame_path=frame_path, cfg=cfg)
    output.save(preview_path, format="JPEG", quality=95)

    return {
        "image_id": image_id,
        "session_folder": session_folder,
        "size": size,
        "orientation": orientation,
        "frame_id": frame_id,
        "frame_applied": frame_applied,
        "preview_url": f"/previews/{session_folder}/{preview_path.name}",
    }


def _safe_nested_filename(filename: str) -> None:
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=404, detail="Not found")


@app.get("/previews/{session}/{filename}")
def get_preview_in_session(session: str, filename: str):
    if not session.startswith("PhotoBooth_"):
        raise HTTPException(status_code=404, detail="Preview not found")
    _safe_nested_filename(filename)
    path = DATA_DIR / session / "previews" / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(path)


@app.get("/previews/{name}")
def get_preview_legacy_flat(name: str):
    """Legacy single-segment URL (flat ./data/previews/...)."""
    path = PREVIEWS_DIR / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(path)


class PreviewFromIdCreate(BaseModel):
    image_id: str
    frame_id: str = ""
    size: str = DEFAULT_SIZE
    orientation: str = Field(default="portrait", pattern="^(portrait|landscape)$")


@app.post("/compose/preview-from-id")
def compose_preview_from_id(payload: PreviewFromIdCreate) -> dict:
    found = _find_original_path(payload.image_id)
    if not found:
        raise HTTPException(status_code=404, detail="Original image not found for image_id")
    original_path, session_folder = found

    frame_path = FRAMES_DIR / payload.size / payload.frame_id / "frame.png" if payload.frame_id else None
    frame_applied = bool(frame_path and frame_path.exists())

    preview_path = _preview_path_for(
        session_folder,
        payload.image_id,
        payload.size,
        payload.orientation,
        payload.frame_id,
    )

    if preview_path.exists():
        url = (
            f"/previews/{session_folder}/{preview_path.name}"
            if session_folder
            else f"/previews/{preview_path.name}"
        )
        return {
            "image_id": payload.image_id,
            "session_folder": session_folder or None,
            "size": payload.size,
            "orientation": payload.orientation,
            "frame_id": payload.frame_id,
            "frame_applied": frame_applied,
            "preview_url": url,
            "cached": True,
        }

    cfg = get_canvas_config(size=payload.size, orientation=payload.orientation)
    output = compose_image(original_path, frame_path=frame_path, cfg=cfg)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(preview_path, format="JPEG", quality=95)

    url = (
        f"/previews/{session_folder}/{preview_path.name}"
        if session_folder
        else f"/previews/{preview_path.name}"
    )
    return {
        "image_id": payload.image_id,
        "session_folder": session_folder or None,
        "size": payload.size,
        "orientation": payload.orientation,
        "frame_id": payload.frame_id,
        "frame_applied": frame_applied,
        "preview_url": url,
        "cached": False,
    }


@app.post("/compose/final")
def compose_final(payload: FinalCreate) -> dict:
    found = _find_original_path(payload.image_id)
    if not found:
        raise HTTPException(status_code=404, detail="Original image not found for image_id")
    original_path, session_folder = found

    frame_path = FRAMES_DIR / payload.size / payload.frame_id / "frame.png" if payload.frame_id else None
    cfg = get_canvas_config(size=payload.size, orientation=payload.orientation)
    output = compose_image(original_path, frame_path=frame_path, cfg=cfg)

    ext = payload.output_format.lower()
    final_path = _final_path_for(
        session_folder,
        payload.image_id,
        payload.size,
        payload.orientation,
        payload.frame_id,
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
    if session_folder:
        prev_dir = DATA_DIR / session_folder / "previews"
        for fp in prev_dir.glob(f"{payload.image_id}__*.jpg"):
            fp.unlink(missing_ok=True)
    else:
        for fp in PREVIEWS_DIR.glob(f"{payload.image_id}__*.jpg"):
            fp.unlink(missing_ok=True)
        legacy_preview = PREVIEWS_DIR / f"{payload.image_id}.jpg"
        legacy_preview.unlink(missing_ok=True)

    # Optional: drop a copy into print-queue for folder-based auto-print (see scripts/print_watcher.py queue mode).
    if _env_truthy("PHOTOBOOTH_COPY_FINAL_TO_PRINT_QUEUE"):
        qdir = Path(os.getenv("PHOTOBOOTH_PRINT_QUEUE_DIR", str(DATA_DIR / "print-queue"))).expanduser().resolve()
        qdir.mkdir(parents=True, exist_ok=True)
        dest = qdir / f"{final_path.stem}_{uuid4().hex[:8]}{final_path.suffix}"
        shutil.copy2(final_path, dest)

    final_url = (
        f"/finals/{session_folder}/{final_path.name}"
        if session_folder
        else f"/finals/{final_path.name}"
    )
    return {
        "image_id": payload.image_id,
        "session_folder": session_folder or None,
        "size": payload.size,
        "orientation": payload.orientation,
        "frame_id": payload.frame_id,
        "output_format": ext,
        "final_url": final_url,
    }


@app.get("/finals/{session}/{filename}")
def get_final_in_session(session: str, filename: str):
    if not session.startswith("PhotoBooth_"):
        raise HTTPException(status_code=404, detail="Final output not found")
    _safe_nested_filename(filename)
    path = DATA_DIR / session / "finals" / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Final output not found")
    return _file_response_final(path)


@app.get("/finals/{name}")
def get_final_legacy_flat(name: str):
    path = FINALS_DIR / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Final output not found")
    return _file_response_final(path)


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
    found = _find_original_path(payload.image_id)
    if not found:
        raise HTTPException(status_code=404, detail="Original image not found for image_id")
    _original_path, session_folder = found
    preview_path = _preview_path_for(
        session_folder,
        payload.image_id,
        payload.size,
        payload.orientation,
        payload.frame_id,
    )
    preview_name = preview_path.name
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview does not exist for selection")

    job_id = uuid4().hex
    job = {
        "id": job_id,
        "image_id": payload.image_id,
        "session_folder": session_folder or None,
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

    def sweep_folder(folder: Path, key: str) -> None:
        for fp in folder.glob("*"):
            if not fp.is_file():
                continue
            mtime = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc)
            if mtime < threshold:
                fp.unlink(missing_ok=True)
                removed[key] += 1

    for folder, key in [(PREVIEWS_DIR, "previews"), (FINALS_DIR, "finals")]:
        sweep_folder(folder, key)

    for session_dir in DATA_DIR.glob("PhotoBooth_*"):
        sweep_folder(session_dir / "previews", "previews")
        sweep_folder(session_dir / "finals", "finals")

    return {"ok": True, "removed": removed, "threshold": threshold.isoformat()}
