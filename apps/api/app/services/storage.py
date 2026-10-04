from __future__ import annotations

import logging
import os
import re
import shutil
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger("photo_booth.storage")

_FILENAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_CAPTURE_TS_RE = re.compile(r"^\d{8}_\d{6}$")
COMPOSE_CACHE_VERSION = "fit3"


def safe_display_name(name: str) -> str:
    """Matches web client: optional name, filesystem-safe, max 60 chars."""
    val = (name or "").strip()
    if not val:
        return "NO_NAME"
    s = _FILENAME_SAFE_RE.sub("_", val)
    s = s[:60].strip("_")
    return s if s else "NO_NAME"


def safe_filename_component(value: str) -> str:
    value = (value or "").strip().lower()
    value = _FILENAME_SAFE_RE.sub("-", value).strip("-")
    return value if value else "noframe"


class StorageService(ABC):
    """Abstract interface for storing photo-booth originals, previews, and finals."""

    @abstractmethod
    def get_session_folder(self, dt: datetime | None = None) -> str:
        """Returns session folder name, e.g. PhotoBooth_DDMMYYYY."""
        ...

    @abstractmethod
    def allocate_image_id(self, session: str, display_name: str, capture_ts: str | None = None) -> str:
        """Allocates an unused, unique image_id."""
        ...

    @abstractmethod
    def save_original(self, session: str, image_id: str, suffix: str, data: bytes) -> Path:
        """Saves original camera capture."""
        ...

    @abstractmethod
    def find_original(self, image_id: str) -> tuple[Path, str] | None:
        """Finds original photo path and session folder name (or empty string for legacy)."""
        ...

    @abstractmethod
    def preview_path_for(
        self, session: str, image_id: str, size: str, orientation: str, frame_id: str
    ) -> tuple[Path, str]:
        """Returns (local_path, url_path) for a preview."""
        ...

    @abstractmethod
    def final_path_for(
        self, session: str, image_id: str, size: str, orientation: str, frame_id: str, ext: str
    ) -> tuple[Path, str]:
        """Returns (local_path, url_path) for a final image."""
        ...

    @abstractmethod
    def delete_cached_previews(self, session: str, image_id: str) -> int:
        """Removes cached preview files for an image_id after final creation."""
        ...

    @abstractmethod
    def cleanup(self, days: int) -> dict[str, int]:
        """Deletes preview and final files older than given days."""
        ...


class LocalStorageService(StorageService):
    """Local disk storage implementation using DATA_DIR."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = (data_dir or Path(os.getenv("DATA_DIR", "./data"))).resolve()
        self.originals_dir = self.data_dir / "originals"
        self.previews_dir = self.data_dir / "previews"
        self.finals_dir = self.data_dir / "finals"
        self.archive_dir = self.data_dir / "archive"
        for d in [self.originals_dir, self.previews_dir, self.finals_dir, self.archive_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def get_session_folder(self, dt: datetime | None = None) -> str:
        # Default to local time or timezone configured
        dt = dt or datetime.now()
        return f"PhotoBooth_{dt.day:02d}{dt.month:02d}{dt.year}"

    def _session_subdirs(self, session: str) -> tuple[Path, Path, Path]:
        base = self.data_dir / session
        return base / "originals", base / "previews", base / "finals"

    def _ensure_session_dirs(self, session: str) -> tuple[Path, Path, Path]:
        o, p, f = self._session_subdirs(session)
        o.mkdir(parents=True, exist_ok=True)
        p.mkdir(parents=True, exist_ok=True)
        f.mkdir(parents=True, exist_ok=True)
        return o, p, f

    def allocate_image_id(self, session: str, display_name: str, capture_ts: str | None = None) -> str:
        orig_dir, _, _ = self._ensure_session_dirs(session)
        cts = (capture_ts or "").strip()
        if _CAPTURE_TS_RE.match(cts):
            ts = cts
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{safe_display_name(display_name)}_{ts}"
        candidate = base
        while list(orig_dir.glob(f"{candidate}.*")):
            candidate = f"{base}_{uuid4().hex[:4]}"
        return candidate

    def save_original(self, session: str, image_id: str, suffix: str, data: bytes) -> Path:
        orig_dir, _, _ = self._ensure_session_dirs(session)
        path = orig_dir / f"{image_id}{suffix}"
        path.write_bytes(data)
        return path

    def find_original(self, image_id: str) -> tuple[Path, str] | None:
        # Check legacy flat originals
        for p in self.originals_dir.glob(f"{image_id}.*"):
            if p.is_file():
                return p, ""
        # Check session folders, newest first
        for session_dir in sorted(self.data_dir.glob("PhotoBooth_*"), reverse=True):
            od = session_dir / "originals"
            if not od.is_dir():
                continue
            for p in od.glob(f"{image_id}.*"):
                if p.is_file():
                    return p, session_dir.name
        return None

    def preview_path_for(
        self, session: str, image_id: str, size: str, orientation: str, frame_id: str
    ) -> tuple[Path, str]:
        short_stem = f"{image_id}__{safe_filename_component(frame_id)}.jpg"
        if session:
            _, prev_dir, _ = self._session_subdirs(session)
            prev_dir.mkdir(parents=True, exist_ok=True)
            path = prev_dir / short_stem
            url = f"/previews/{session}/{path.name}"
            return path, url
        legacy_name = f"{image_id}__{COMPOSE_CACHE_VERSION}__{size}__{orientation}__{safe_filename_component(frame_id)}.jpg"
        path = self.previews_dir / legacy_name
        return path, f"/previews/{path.name}"

    def final_path_for(
        self, session: str, image_id: str, size: str, orientation: str, frame_id: str, ext: str
    ) -> tuple[Path, str]:
        ext = ext.lower()
        filename_ext = "jpg" if ext == "jpeg" else ext
        if session:
            _, _, fin_dir = self._session_subdirs(session)
            fin_dir.mkdir(parents=True, exist_ok=True)
            path = fin_dir / f"{image_id}_final.{filename_ext}"
            url = f"/finals/{session}/{path.name}"
            return path, url
        legacy_name = f"{image_id}__{COMPOSE_CACHE_VERSION}__{size}__{orientation}__{safe_filename_component(frame_id)}.{filename_ext}"
        path = self.finals_dir / legacy_name
        return path, f"/finals/{path.name}"

    def delete_cached_previews(self, session: str, image_id: str) -> int:
        removed = 0
        search_dirs = []
        if session:
            search_dirs.append(self.data_dir / session / "previews")
        search_dirs.append(self.previews_dir)

        for sdir in search_dirs:
            if not sdir.is_dir():
                continue
            for fp in sdir.glob(f"{image_id}__*.jpg"):
                for attempt in range(5):
                    try:
                        fp.unlink(missing_ok=True)
                        removed += 1
                        break
                    except OSError:
                        time.sleep(0.05 * (attempt + 1))
        return removed

    def cleanup(self, days: int) -> dict[str, int]:
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
        removed = {"previews": 0, "finals": 0}

        def sweep(folder: Path, key: str) -> None:
            if not folder.is_dir():
                return
            for fp in folder.glob("*"):
                if not fp.is_file():
                    continue
                mtime = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc)
                if mtime < threshold:
                    fp.unlink(missing_ok=True)
                    removed[key] += 1

        for folder, key in [(self.previews_dir, "previews"), (self.finals_dir, "finals")]:
            sweep(folder, key)

        for session_dir in self.data_dir.glob("PhotoBooth_*"):
            sweep(session_dir / "previews", "previews")
            sweep(session_dir / "finals", "finals")

        return removed


# Default singleton instance (can be re-initialized if DATA_DIR changes)
_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = LocalStorageService()
    return _storage_service


def reset_storage_service(service: StorageService | None = None) -> None:
    """Helper for tests to rebind storage with temp paths."""
    global _storage_service
    _storage_service = service

