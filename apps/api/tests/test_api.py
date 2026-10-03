"""
Integration tests for the Photo Booth REST API (apps/api/app/main.py).

These pin down CURRENT behaviour so the Phase 2 security work and the Phase D
refactor can't silently change it. Tests marked "Phase 2" document gaps that
are intentionally open today and will flip when admin auth / limits land.
"""
from __future__ import annotations

import io
import re

import pytest
from PIL import Image

from .conftest import make_jpeg

SESSION_RE = re.compile(r"^PhotoBooth_\d{8}$")


def capture(client, *, frame_id="classic-white", size="4x6", orientation="portrait", name="Test Guest", ts=""):
    files = {"image": ("capture.jpg", make_jpeg(800, 600), "image/jpeg")}
    data = {"frame_id": frame_id, "size": size, "orientation": orientation, "display_name": name, "capture_ts": ts}
    res = client.post("/compose/preview", files=files, data=data)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------- health & options

def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "photo-booth-api"
    assert body["print_queue_copy_enabled"] is False
    assert body["dropzone_copy_enabled"] is False


def test_print_status_idle_when_no_watcher(client):
    assert client.get("/print/status").json()["state"] == "idle"


def test_options_hide_8x11_by_default(client):
    body = client.get("/options").json()
    assert body["sizes"] == ["4x6", "5x7"]
    assert set(body["output_formats"]) == {"png", "jpeg", "pdf"}


def test_options_can_include_8x11(client):
    assert "8x11" in client.get("/options", params={"include_8x11": "true"}).json()["sizes"]


# ---------------------------------------------------------------- frames

def test_list_frames_for_4x6(client):
    body = client.get("/frames", params={"size": "4x6"}).json()
    ids = {f["id"] for f in body["frames"]}
    assert {"classic-white", "gold-celebration", "neon-purple", "story-memories"} <= ids
    assert "default" not in ids, "folders without frame.png must not be listed"


def test_list_frames_unknown_size_is_empty(client):
    assert client.get("/frames", params={"size": "99x99"}).json()["frames"] == []


def test_frame_template_png(client):
    res = client.get("/frames/template/4x6/classic-white")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"


def test_frame_template_missing_is_404(client):
    assert client.get("/frames/template/4x6/does-not-exist").status_code == 404


def test_frame_upload_rejects_unknown_size(client):
    files = {"frame_file": ("f.png", b"x", "image/png")}
    res = client.post("/frames/upload", data={"size": "99x99", "frame_name": "x"}, files=files)
    assert res.status_code == 400


def test_frame_upload_slugifies_name(client, frames_dir):
    png = io.BytesIO()
    Image.new("RGBA", (180, 270), (0, 0, 0, 0)).save(png, format="PNG")
    files = {"frame_file": ("Party Time.png", png.getvalue(), "image/png")}
    res = client.post("/frames/upload", data={"size": "4x6", "frame_name": "  Party Time!! "}, files=files)
    assert res.status_code == 200, res.text
    assert res.json()["frame_id"] == "party-time"
    assert (frames_dir / "4x6" / "party-time" / "frame.png").is_file()


def test_phase2_gap_frame_upload_is_unauthenticated(client):
    """Phase 2 will require PHOTOBOOTH_ADMIN_TOKEN; then this must return 401."""
    png = io.BytesIO()
    Image.new("RGBA", (10, 10)).save(png, format="PNG")
    files = {"frame_file": ("a.png", png.getvalue(), "image/png")}
    assert client.post("/frames/upload", data={"size": "4x6", "frame_name": "anon"}, files=files).status_code == 200


# ---------------------------------------------------------------- capture → preview → final

def test_compose_preview_creates_session_and_preview(client, data_dir):
    body = capture(client, name="Asha & Ravi")
    assert SESSION_RE.match(body["session_folder"])
    assert body["image_id"].startswith("Asha_Ravi_")
    assert body["frame_applied"] is True
    assert body["preview_url"].startswith(f"/previews/{body['session_folder']}/")
    originals = data_dir / body["session_folder"] / "originals"
    assert any(originals.glob(f"{body['image_id']}.*"))

    res = client.get(body["preview_url"])
    assert res.status_code == 200
    with Image.open(io.BytesIO(res.content)) as im:
        assert im.format == "JPEG"
        assert im.size == (1800, 2700)  # Phase 5 will shrink previews; finals stay full size


def test_compose_preview_without_name_uses_placeholder(client):
    assert capture(client, name="").get("image_id").startswith("NO_NAME_")


def test_compose_preview_honours_capture_timestamp(client):
    body = capture(client, name="ts", ts="20261003_101500")
    assert body["image_id"].startswith("ts_20261003_101500")


def test_duplicate_capture_timestamp_gets_unique_id(client):
    a = capture(client, name="dup", ts="20261003_111111")
    b = capture(client, name="dup", ts="20261003_111111")
    assert a["image_id"] != b["image_id"]


def test_unknown_frame_composes_without_overlay(client):
    assert capture(client, frame_id="no-such-frame")["frame_applied"] is False


def test_landscape_preview_dimensions(client):
    body = capture(client, orientation="landscape")
    with Image.open(io.BytesIO(client.get(body["preview_url"]).content)) as im:
        assert im.size == (2700, 1800)


def test_preview_from_id_cache_hit_and_miss(client):
    body = capture(client, frame_id="classic-white")
    same = client.post("/compose/preview-from-id", json={"image_id": body["image_id"], "frame_id": "classic-white"})
    assert same.status_code == 200 and same.json()["cached"] is True
    other = client.post("/compose/preview-from-id", json={"image_id": body["image_id"], "frame_id": "neon-purple"})
    assert other.status_code == 200 and other.json()["cached"] is False
    assert client.get(other.json()["preview_url"]).status_code == 200


def test_preview_from_id_unknown_image_404(client):
    res = client.post("/compose/preview-from-id", json={"image_id": "ghost_20000101_000000", "frame_id": "classic-white"})
    assert res.status_code == 404


@pytest.mark.parametrize("fmt,media_type,magic", [
    ("png", "image/png", b"\x89PNG"),
    ("jpeg", "image/jpeg", b"\xff\xd8"),
    ("pdf", "application/pdf", b"%PDF"),
])
def test_compose_final_formats(client, fmt, media_type, magic):
    body = capture(client)
    res = client.post("/compose/final", json={"image_id": body["image_id"], "frame_id": "classic-white", "output_format": fmt})
    assert res.status_code == 200, res.text
    final_url = res.json()["final_url"]
    got = client.get(final_url)
    assert got.status_code == 200
    assert got.headers["content-type"] == media_type
    assert got.content.startswith(magic)


def test_compose_final_removes_cached_previews(client, data_dir):
    body = capture(client)
    previews = data_dir / body["session_folder"] / "previews"
    assert any(previews.glob(f"{body['image_id']}__*.jpg"))
    client.post("/compose/final", json={"image_id": body["image_id"], "frame_id": "classic-white", "output_format": "jpeg"})
    assert not any(previews.glob(f"{body['image_id']}__*.jpg"))


def test_compose_final_rejects_bad_format(client):
    body = capture(client)
    res = client.post("/compose/final", json={"image_id": body["image_id"], "output_format": "gif"})
    assert res.status_code == 422


def test_compose_final_unknown_image_404(client):
    assert client.post("/compose/final", json={"image_id": "ghost"}).status_code == 404


# ---------------------------------------------------------------- print jobs

def test_print_job_lifecycle(client):
    body = capture(client)
    res = client.post("/jobs/print", json={"image_id": body["image_id"], "frame_id": "classic-white", "copies": 2})
    assert res.status_code == 200, res.text
    job = res.json()
    assert job["status"] == "ready_to_print" and job["copies"] == 2
    listed = client.get("/jobs", params={"status": "ready_to_print"}).json()
    assert any(j["id"] == job["id"] for j in listed["jobs"])


def test_print_job_copies_bounded(client):
    body = capture(client)
    assert client.post("/jobs/print", json={"image_id": body["image_id"], "copies": 11}).status_code == 422


def test_print_job_without_preview_404(client):
    body = capture(client, frame_id="classic-white")
    res = client.post("/jobs/print", json={"image_id": body["image_id"], "frame_id": "neon-purple"})
    assert res.status_code == 404


# ---------------------------------------------------------------- file serving & traversal

@pytest.mark.parametrize("url", [
    "/previews/NotASession/x.jpg",
    "/previews/PhotoBooth_01012026/..secret.jpg",
    "/finals/NotASession/x.png",
    "/finals/PhotoBooth_01012026/..secret.png",
    "/previews/missing.jpg",
    "/finals/missing.png",
])
def test_file_routes_reject_bad_or_missing_paths(client, url):
    assert client.get(url).status_code == 404


# ---------------------------------------------------------------- admin

def test_cleanup_rejects_negative_days(client):
    assert client.post("/admin/cleanup", params={"days": -1}).status_code == 400


def test_cleanup_keeps_recent_files(client):
    body = capture(client)
    res = client.post("/admin/cleanup", params={"days": 2})
    assert res.status_code == 200 and res.json()["ok"] is True
    assert client.get(body["preview_url"]).status_code == 200


def test_phase2_gap_cleanup_is_unauthenticated(client):
    """Phase 2 will require PHOTOBOOTH_ADMIN_TOKEN; then this must return 401.
    Kept LAST in this module: days=0 wipes every preview/final in the temp DATA_DIR."""
    body = capture(client)
    res = client.post("/admin/cleanup", params={"days": 0})
    assert res.status_code == 200
    assert res.json()["removed"]["previews"] >= 1
    assert client.get(body["preview_url"]).status_code == 404

