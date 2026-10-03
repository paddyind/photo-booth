"""Unit tests for the image compositor (apps/api/app/services/compositor.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from apps.api.app.services.compositor import PRINT_PRESETS, CanvasConfig, compose_image, get_canvas_config

from .conftest import FRAMES_SRC, make_jpeg

RED = (200, 40, 40)
BLUE = (0, 0, 255)
GREEN = (0, 200, 0)
WHITE = (255, 255, 255)

# Small canvas keeps each compose in milliseconds; geometry logic is size-independent.
SMALL = CanvasConfig(width=300, height=450, top_margin=40, bottom_margin=50, padding=10)
HOLE = (75, 112, 225, 338)  # left, top, right, bottom of the photo cut-out in test frames


def close(px, expected, tol=24) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(px[:3], expected))


def write_photo(tmp_path: Path, w: int, h: int, color=RED, exif_orientation=None) -> Path:
    p = tmp_path / f"photo_{w}x{h}_{exif_orientation}.jpg"
    p.write_bytes(make_jpeg(w, h, color, exif_orientation))
    return p


def write_rgba_frame(tmp_path: Path, meta: dict | None = None, name: str = "frame") -> Path:
    """Opaque blue frame with a fully transparent rectangular hole."""
    d = tmp_path / name
    d.mkdir()
    frame = Image.new("RGBA", (SMALL.width, SMALL.height), (*BLUE, 255))
    frame.paste((0, 0, 0, 0), HOLE)
    path = d / "frame.png"
    frame.save(path)
    if meta is not None:
        (d / "meta.json").write_text(json.dumps(meta))
    return path


def content_bbox(img: Image.Image):
    """Bounding box of everything that is not the white canvas."""
    diff = ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, WHITE))
    return diff.convert("L").point(lambda p: 255 if p > 30 else 0).getbbox()


# ---------------------------------------------------------------- canvas presets

@pytest.mark.parametrize("size", sorted(PRINT_PRESETS))
def test_canvas_matches_preset_portrait(size):
    cfg = get_canvas_config(size, "portrait")
    assert (cfg.width, cfg.height) == PRINT_PRESETS[size]


@pytest.mark.parametrize("size", sorted(PRINT_PRESETS))
def test_canvas_landscape_swaps_dimensions(size):
    cfg = get_canvas_config(size, "landscape")
    w, h = PRINT_PRESETS[size]
    assert (cfg.width, cfg.height) == (h, w)


def test_unknown_size_falls_back_to_4x6():
    cfg = get_canvas_config("13x18", "portrait")
    assert (cfg.width, cfg.height) == PRINT_PRESETS["4x6"]


def test_margins_scale_with_canvas():
    small, large = get_canvas_config("4x6"), get_canvas_config("8x11")
    assert large.top_margin >= small.top_margin
    assert large.padding >= small.padding


# ---------------------------------------------------------------- no frame

def test_no_frame_output_size_and_white_margins(tmp_path):
    out = compose_image(write_photo(tmp_path, 400, 300), frame_path=None, cfg=SMALL)
    assert out.size == (SMALL.width, SMALL.height)
    assert out.mode == "RGB"
    assert close(out.getpixel((2, 2)), WHITE)  # margin stays white
    assert close(out.getpixel((SMALL.width // 2, SMALL.height // 2)), RED)  # photo centred


def test_missing_frame_path_behaves_like_no_frame(tmp_path):
    photo = write_photo(tmp_path, 400, 300)
    a = compose_image(photo, frame_path=None, cfg=SMALL)
    b = compose_image(photo, frame_path=tmp_path / "nope" / "frame.png", cfg=SMALL)
    assert ImageChops.difference(a, b).getbbox() is None


def test_exif_orientation_is_applied(tmp_path):
    """A landscape JPEG tagged 'rotate 90' must be laid out as portrait."""
    plain = content_bbox(compose_image(write_photo(tmp_path, 400, 200), None, SMALL))
    rotated = content_bbox(compose_image(write_photo(tmp_path, 400, 200, exif_orientation=6), None, SMALL))
    pw, ph = plain[2] - plain[0], plain[3] - plain[1]
    rw, rh = rotated[2] - rotated[0], rotated[3] - rotated[1]
    assert pw > ph, "untagged landscape photo should stay landscape"
    assert rh > rw, "EXIF orientation 6 should rotate the photo to portrait"


# ---------------------------------------------------------------- frames

def test_rgba_frame_hole_inferred_from_transparency(tmp_path):
    out = compose_image(write_photo(tmp_path, 300, 450), write_rgba_frame(tmp_path), SMALL)
    cx, cy = (HOLE[0] + HOLE[2]) // 2, (HOLE[1] + HOLE[3]) // 2
    assert close(out.getpixel((cx, cy)), RED), "photo should show through the hole"
    assert close(out.getpixel((5, 5)), BLUE), "frame should cover the border"


def test_fit_mode_contain_letterboxes_wide_photo(tmp_path):
    frame = write_rgba_frame(tmp_path, {"fit_mode": "contain"})
    out = compose_image(write_photo(tmp_path, 400, 100), frame, SMALL)
    cx = (HOLE[0] + HOLE[2]) // 2
    assert close(out.getpixel((cx, (HOLE[1] + HOLE[3]) // 2)), RED)
    assert close(out.getpixel((cx, HOLE[1] + 5)), WHITE), "contain leaves whitespace above a wide photo"


def test_fit_mode_cover_fills_hole(tmp_path):
    frame = write_rgba_frame(tmp_path, {"fit_mode": "cover"})
    out = compose_image(write_photo(tmp_path, 400, 100), frame, SMALL)
    cx = (HOLE[0] + HOLE[2]) // 2
    assert close(out.getpixel((cx, HOLE[1] + 5)), RED), "cover fills the hole edge to edge"


def test_fit_mode_auto_prefers_cover_for_very_wide_photo(tmp_path):
    frame = write_rgba_frame(tmp_path, {"fit_mode": "auto"})
    out = compose_image(write_photo(tmp_path, 400, 100), frame, SMALL)
    cx = (HOLE[0] + HOLE[2]) // 2
    assert close(out.getpixel((cx, HOLE[1] + 5)), RED)


def test_normalized_safe_area_overrides_transparency(tmp_path):
    # Safe area = top-left quarter of the hole; photo must land there, not hole centre.
    sa = {"x": HOLE[0] / SMALL.width, "y": HOLE[1] / SMALL.height,
          "w": 0.5 * (HOLE[2] - HOLE[0]) / SMALL.width, "h": 0.5 * (HOLE[3] - HOLE[1]) / SMALL.height}
    frame = write_rgba_frame(tmp_path, {"fit_mode": "cover", "safe_area": sa})
    out = compose_image(write_photo(tmp_path, 300, 450), frame, SMALL)
    assert close(out.getpixel((HOLE[0] + 10, HOLE[1] + 10)), RED)
    assert close(out.getpixel((HOLE[2] - 10, HOLE[3] - 10)), WHITE), "outside safe area stays canvas white"


def test_pixel_safe_area(tmp_path):
    sa = {"x": HOLE[0], "y": HOLE[1], "w": 60, "h": 60}
    frame = write_rgba_frame(tmp_path, {"fit_mode": "cover", "safe_area": sa})
    out = compose_image(write_photo(tmp_path, 300, 300), frame, SMALL)
    assert close(out.getpixel((HOLE[0] + 30, HOLE[1] + 30)), RED)
    assert close(out.getpixel((HOLE[0] + 100, HOLE[1] + 150)), WHITE)


def test_legacy_padding_safe_area(tmp_path):
    frame = write_rgba_frame(tmp_path, {"safe_area": {"padding": 10, "top_margin": 40, "bottom_margin": 50}})
    out = compose_image(write_photo(tmp_path, 300, 450), frame, SMALL)
    assert out.size == (SMALL.width, SMALL.height)
    assert close(out.getpixel((SMALL.width // 2, SMALL.height // 2)), RED)


def test_rgb_frame_near_black_is_keyed_transparent(tmp_path):
    """RGB/palette frames: near-black pixels become the photo window."""
    d = tmp_path / "rgbframe"
    d.mkdir()
    frame = Image.new("RGB", (SMALL.width, SMALL.height), GREEN)
    frame.paste((0, 0, 0), HOLE)
    frame.save(d / "frame.png")
    out = compose_image(write_photo(tmp_path, 300, 450), d / "frame.png", SMALL)
    assert close(out.getpixel(((HOLE[0] + HOLE[2]) // 2, (HOLE[1] + HOLE[3]) // 2)), RED)
    assert close(out.getpixel((5, 5)), GREEN)


def test_opaque_frame_without_hole_falls_back_to_margins(tmp_path):
    d = tmp_path / "opaque"
    d.mkdir()
    Image.new("RGBA", (SMALL.width, SMALL.height), (*BLUE, 128)).save(d / "frame.png")
    out = compose_image(write_photo(tmp_path, 300, 450), d / "frame.png", SMALL)
    assert out.size == (SMALL.width, SMALL.height)


def test_corrupt_meta_json_is_ignored(tmp_path):
    frame = write_rgba_frame(tmp_path)
    (frame.parent / "meta.json").write_text("{not json")
    out = compose_image(write_photo(tmp_path, 300, 450), frame, SMALL)
    assert close(out.getpixel(((HOLE[0] + HOLE[2]) // 2, (HOLE[1] + HOLE[3]) // 2)), RED)


# ---------------------------------------------------------------- shipped frame packs

# Known defect (NEXT_STEPS.md Phase 5, "aspect ratio correction"): these packs reuse the
# 1800x2700 4x6 artwork, so the compositor stretches them ~5% (5x7) / ~9% (8x11).
# strict=True: once the art is re-exported, the test passes and pytest flags the stale mark.
KNOWN_DISTORTED = {
    "5x7/classic-white", "5x7/neon-purple", "5x7/story-memories",
    "8x11/classic-white", "8x11/custom-story", "8x11/gold-celebration",
    "8x11/neon-purple", "8x11/story-memories",
}


def _shipped_frames():
    for png in sorted(FRAMES_SRC.glob("*/*/frame.png")):
        key = f"{png.parent.parent.name}/{png.parent.name}"
        marks = [pytest.mark.xfail(strict=True, reason="frame art aspect != print preset (stretched)")] \
            if key in KNOWN_DISTORTED else []
        yield pytest.param(png, id=key, marks=marks)


@pytest.mark.parametrize("frame_png", list(_shipped_frames()))
def test_shipped_frame_aspect_matches_print_size(frame_png):
    size = frame_png.parent.parent.name
    pw, ph = PRINT_PRESETS[size]
    with Image.open(frame_png) as im:
        fw, fh = im.size
    assert abs(fw / fh - pw / ph) / (pw / ph) < 0.01, f"{frame_png} is {fw}x{fh}, preset {size} is {pw}x{ph}"


@pytest.mark.parametrize("meta_path", sorted(FRAMES_SRC.glob("*/*/meta.json")), ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_shipped_meta_json_is_valid(meta_path):
    data = json.loads(meta_path.read_text())
    assert isinstance(data, dict)
    if "fit_mode" in data:
        assert data["fit_mode"] in ("auto", "contain", "cover")

