from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps


@dataclass
class CanvasConfig:
    width: int = 1800
    height: int = 2700
    top_margin: int = 260
    bottom_margin: int = 320
    padding: int = 80


PRINT_PRESETS: dict[str, tuple[int, int]] = {
    "4x6": (1800, 2700),
    "5x7": (2100, 3000),
    "6x8": (2400, 3200),
}


def get_canvas_config(size: str = "4x6", orientation: str = "portrait") -> CanvasConfig:
    width, height = PRINT_PRESETS.get(size, PRINT_PRESETS["4x6"])
    if orientation.lower() == "landscape":
        width, height = height, width

    # Scale margins/padding relative to legacy 4x6 portrait baseline.
    base_w, base_h = PRINT_PRESETS["4x6"]
    ratio = min(width / base_w, height / base_h)
    return CanvasConfig(
        width=width,
        height=height,
        top_margin=max(0, int(260 * ratio)),
        bottom_margin=max(0, int(320 * ratio)),
        padding=max(0, int(80 * ratio)),
    )


def compose_image(
    input_path: Path,
    frame_path: Optional[Path] = None,
    cfg: CanvasConfig = CanvasConfig(),
) -> Image.Image:
    """
    Reused core logic from legacy photobooth:
    - EXIF transpose
    - frame-safe contain fit
    - white canvas background
    - RGBA frame overlay
    """
    img = Image.open(input_path)
    img = ImageOps.exif_transpose(img).convert("RGB")

    has_frame = bool(frame_path and frame_path.exists())
    canvas = Image.new("RGB", (cfg.width, cfg.height), (255, 255, 255))

    if not has_frame:
        # Legacy layout (no template overlay): keep margins + padding.
        usable_width = cfg.width - (2 * cfg.padding)
        usable_height = cfg.height - cfg.top_margin - cfg.bottom_margin - (2 * cfg.padding)
        top_anchor = cfg.top_margin + cfg.padding

        scale = min(usable_width / img.width, usable_height / img.height)
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        fitted = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        offset_x = (cfg.width - new_w) // 2
        offset_y = top_anchor + (usable_height - new_h) // 2
        canvas.paste(fitted, (offset_x, offset_y))
        return canvas

    # Frame-aware layout:
    # - make a consistent RGBA frame image (key near-black to alpha=0 when needed)
    # - infer the photo "cutout/safe area" from transparency bounding box
    # - fit the user photo into that inferred safe area
    # - overlay the frame on top

    frame = Image.open(frame_path)
    if frame.mode in ("RGB", "P"):
        rgba = frame.convert("RGBA")
        converted = []
        for r, g, b, a in rgba.getdata():
            if r < 15 and g < 15 and b < 15:
                converted.append((r, g, b, 0))
            else:
                converted.append((r, g, b, 255))
        rgba.putdata(converted)
        frame_rgba = rgba
    else:
        frame_rgba = frame.convert("RGBA")

    frame_rgba = frame_rgba.resize((cfg.width, cfg.height), Image.Resampling.LANCZOS)

    meta_path = frame_path.parent / "meta.json"
    meta = None
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            meta = None

    fit_mode = (meta or {}).get("fit_mode", "auto") if meta else "auto"
    transparency_threshold = int((meta or {}).get("transparency_threshold", 20)) if meta else 20

    safe_rect = None
    if meta and isinstance(meta.get("safe_area"), dict):
        sa = meta["safe_area"]
        # Normalized safe_area: {x,y,w,h} in 0..1
        if all(k in sa for k in ("x", "y", "w", "h")):
            x, y, w, h = sa["x"], sa["y"], sa["w"], sa["h"]
            if 0 <= x <= 1 and 0 <= y <= 1 and 0 <= w <= 1 and 0 <= h <= 1:
                left = int(x * cfg.width)
                top = int(y * cfg.height)
                right = int((x + w) * cfg.width)
                bottom = int((y + h) * cfg.height)
                safe_rect = (left, top, right, bottom)
            else:
                # Pixel safe_area: x,y,w,h
                left = int(x)
                top = int(y)
                right = int(x + w)
                bottom = int(y + h)
                safe_rect = (left, top, right, bottom)
        else:
            # Legacy-style safe_area: {padding, top_margin, bottom_margin}
            if "padding" in sa or "top_margin" in sa or "bottom_margin" in sa:
                padding = int(sa.get("padding", cfg.padding))
                top_margin = int(sa.get("top_margin", cfg.top_margin))
                bottom_margin = int(sa.get("bottom_margin", cfg.bottom_margin))
                left = padding
                right = cfg.width - padding
                top = top_margin + padding
                bottom = cfg.height - bottom_margin - padding
                safe_rect = (left, top, right, bottom)

    if safe_rect:
        left, top, right, bottom = safe_rect
        safe_w = max(1, right - left)
        safe_h = max(1, bottom - top)
    else:
        # Fallback: infer cutout box from transparency.
        alpha = frame_rgba.getchannel("A")
        transparent_mask = alpha.point(lambda p: 255 if p < transparency_threshold else 0)
        bbox = transparent_mask.getbbox()  # (left, top, right, bottom) or None
        if not bbox:
            # Fallback to legacy safe-area fit if frame has no transparent cutout.
            usable_width = cfg.width - (2 * cfg.padding)
            usable_height = cfg.height - cfg.top_margin - cfg.bottom_margin - (2 * cfg.padding)
            top_anchor = cfg.top_margin + cfg.padding
            scale = min(usable_width / img.width, usable_height / img.height)
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            fitted = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            offset_x = (cfg.width - new_w) // 2
            offset_y = top_anchor + (usable_height - new_h) // 2
            canvas.paste(fitted, (offset_x, offset_y))
            return Image.alpha_composite(canvas.convert("RGBA"), frame_rgba).convert("RGB")

        left, top, right, bottom = bbox
        safe_w = max(1, right - left)
        safe_h = max(1, bottom - top)

    # Dynamic fit mode:
    # - Contain: preserves full photo but may leave whitespace
    # - Cover: fills cutout better but may crop edges
    # Choose the mode with the smaller "badness" score.
    img_w, img_h = img.width, img.height

    # Contain
    scale_contain = min(safe_w / img_w, safe_h / img_h)
    w_contain = int(img_w * scale_contain)
    h_contain = int(img_h * scale_contain)
    empty_fraction = 1.0 - (w_contain * h_contain) / float(safe_w * safe_h)

    # Cover (center-cropped)
    scale_cover = max(safe_w / img_w, safe_h / img_h)
    w_cover = int(img_w * scale_cover)
    h_cover = int(img_h * scale_cover)
    crop_fraction = 1.0 - (safe_w * safe_h) / float(w_cover * h_cover)

    if fit_mode == "contain":
        fitted = img.resize((w_contain, h_contain), Image.Resampling.LANCZOS)
        offset_x = left + (safe_w - w_contain) // 2
        offset_y = top + (safe_h - h_contain) // 2
        canvas.paste(fitted, (offset_x, offset_y))
    elif fit_mode == "cover":
        fitted = img.resize((w_cover, h_cover), Image.Resampling.LANCZOS)
        crop_left = (w_cover - safe_w) // 2
        crop_top = (h_cover - safe_h) // 2
        cropped = fitted.crop((crop_left, crop_top, crop_left + safe_w, crop_top + safe_h))
        canvas.paste(cropped, (left, top))
    else:
        # auto: penalize whitespace more than cropping, but not too aggressively.
        score_contain = empty_fraction
        score_cover = crop_fraction * 0.45
        use_cover = score_cover < score_contain

        if use_cover:
            fitted = img.resize((w_cover, h_cover), Image.Resampling.LANCZOS)
            crop_left = (w_cover - safe_w) // 2
            crop_top = (h_cover - safe_h) // 2
            cropped = fitted.crop((crop_left, crop_top, crop_left + safe_w, crop_top + safe_h))
            canvas.paste(cropped, (left, top))
        else:
            fitted = img.resize((w_contain, h_contain), Image.Resampling.LANCZOS)
            offset_x = left + (safe_w - w_contain) // 2
            offset_y = top + (safe_h - h_contain) // 2
            canvas.paste(fitted, (offset_x, offset_y))

    return Image.alpha_composite(canvas.convert("RGBA"), frame_rgba).convert("RGB")
