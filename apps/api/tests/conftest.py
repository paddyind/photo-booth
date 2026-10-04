"""
Shared test setup.

`apps.api.app.main` reads DATA_DIR / FRAMES_DIR at import time and creates
directories there, so the environment must point at throwaway folders BEFORE
the app module is imported. Frames are copied into the temp dir because
`POST /frames/upload` writes into FRAMES_DIR and must never touch the real
`shared/frames` pack.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[3]
FRAMES_SRC = Path(os.getenv("TEST_FRAMES_SRC", REPO_ROOT / "shared" / "frames"))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="photobooth-tests-"))
TEST_DATA_DIR = _TMP_ROOT / "data"
TEST_FRAMES_DIR = _TMP_ROOT / "frames"
shutil.copytree(FRAMES_SRC, TEST_FRAMES_DIR)

TEST_ADMIN_TOKEN = "test-admin-secret-token"

os.environ["DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["FRAMES_DIR"] = str(TEST_FRAMES_DIR)
os.environ["PHOTOBOOTH_ADMIN_TOKEN"] = TEST_ADMIN_TOKEN

# Copy-out features must stay off so tests never write outside the temp dir.
for _var in ("PHOTOBOOTH_COPY_FINAL_TO_DROPZONE", "PHOTOBOOTH_COPY_FINAL_TO_PRINT_QUEUE", "WEB_DIR"):
    os.environ.pop(_var, None)

# Initialize storage singleton to isolated test directory
from apps.api.app.services.storage import LocalStorageService, reset_storage_service

reset_storage_service(LocalStorageService(TEST_DATA_DIR))


def make_jpeg(width: int = 640, height: int = 480, color=(200, 40, 40), exif_orientation: int | None = None) -> bytes:
    """Solid-colour JPEG, optionally tagged with an EXIF orientation."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        img.save(buf, format="JPEG", quality=95, exif=exif.tobytes())
    else:
        img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from apps.api.app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_ADMIN_TOKEN}"}


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return TEST_DATA_DIR


@pytest.fixture(scope="session")
def frames_dir() -> Path:
    return TEST_FRAMES_DIR


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)

