#!/usr/bin/env python3
"""
Watch PHOTOBOOTH_DATA_DIR (or --data-dir) for new files under any **/finals/** and send them to the default printer.

Same layout for Docker (host-mounted volume) and standalone:
  data[-standalone]/PhotoBooth_DDMMYYYY/finals/*.jpg
  data[-standalone]/finals/*              (legacy flat)

Windows: uses pywin32 GDI when available; otherwise os.startfile(..., "print").
macOS/Linux: uses `lp` (CUPS).

Usage:
  export PHOTOBOOTH_DATA_DIR=/path/to/data-standalone
  python scripts/print_watcher.py

  python scripts/print_watcher.py --data-dir ./data-standalone --printer "EPSON L3250"
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    print("Missing watchdog. Run: pip install -r scripts/requirements-print-watcher.txt", file=sys.stderr)
    sys.exit(1)

try:
    from PIL import Image, ImageOps
except ImportError:
    print("Missing Pillow. Run: pip install -r scripts/requirements-print-watcher.txt", file=sys.stderr)
    sys.exit(1)


PRINTABLE_EXT = {".jpg", ".jpeg", ".png", ".pdf"}


def _is_under_finals(path: Path) -> bool:
    try:
        return "finals" in path.resolve().parts
    except OSError:
        return "finals" in path.parts


def _is_printable(path: Path) -> bool:
    return path.suffix.lower() in PRINTABLE_EXT and _is_under_finals(path)


def _wait_stable(path: Path, attempts: int = 15, delay: float = 0.4) -> bool:
    last = -1
    for _ in range(attempts):
        try:
            if not path.is_file():
                time.sleep(delay)
                continue
            size = path.stat().st_size
            if size > 0 and size == last:
                # Verify image-ish files open (skip strict for pdf)
                suf = path.suffix.lower()
                if suf == ".pdf":
                    return True
                try:
                    with Image.open(path) as im:
                        im.verify()
                    return True
                except Exception:
                    pass
            last = size
        except OSError:
            pass
        time.sleep(delay)
    return False


def _print_win32_gdi(path: Path, printer_name: str | None) -> bool:
    try:
        import win32print
        import win32ui
        from PIL import ImageWin
    except ImportError:
        return False

    name = printer_name or win32print.GetDefaultPrinter()
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")

    hDC = win32ui.CreateDC()
    hDC.CreatePrinterDC(name)
    try:
        printable_area = hDC.GetDeviceCaps(8), hDC.GetDeviceCaps(10)
        printer_size = hDC.GetDeviceCaps(110), hDC.GetDeviceCaps(111)
        if not printer_size[0] or not printer_size[1]:
            printer_size = printable_area
        img_ratio = img.size[0] / img.size[1]
        pr_ratio = printer_size[0] / printer_size[1]
        if img_ratio > pr_ratio:
            new_w = printer_size[0]
            new_h = int(new_w / img_ratio)
        else:
            new_h = printer_size[1]
            new_w = int(new_h * img_ratio)
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        dib = ImageWin.Dib(resized)
        off_x = (printer_size[0] - new_w) // 2
        off_y = (printer_size[1] - new_h) // 2
        hDC.StartDoc(str(path))
        hDC.StartPage()
        dib.draw(hDC.GetHandleOutput(), (off_x, off_y, off_x + new_w, off_y + new_h))
        hDC.EndPage()
        hDC.EndDoc()
    finally:
        hDC.DeleteDC()
    return True


def _print_win32_shell(path: Path) -> None:
    os.startfile(str(path), "print")  # type: ignore[attr-defined]


def _print_lp(path: Path, printer_name: str | None) -> None:
    import subprocess

    cmd = ["lp"]
    if printer_name:
        cmd.extend(["-d", printer_name])
    cmd.append(str(path))
    subprocess.run(cmd, check=True)


def print_file(path: Path, printer_name: str | None) -> None:
    path = path.resolve()
    suf = path.suffix.lower()
    if sys.platform == "win32":
        if suf in (".jpg", ".jpeg", ".png"):
            if _print_win32_gdi(path, printer_name):
                return
        try:
            _print_win32_shell(path)
        except OSError as e:
            raise RuntimeError(f"Windows print failed: {e}") from e
        return

    # macOS / Linux
    _print_lp(path, printer_name)


class FinalsHandler(FileSystemEventHandler):
    def __init__(self, printer_name: str | None) -> None:
        self.printer_name = printer_name
        self._processed: set[str] = set()
        self._lock = threading.Lock()

    def _schedule(self, path: str) -> None:
        p = Path(path)
        if not _is_printable(p):
            return
        key = str(p.resolve())
        with self._lock:
            if key in self._processed:
                return
            self._processed.add(key)

        def run() -> None:
            try:
                if not _wait_stable(p):
                    print(f"[print-watcher] skip (unstable): {p}", flush=True)
                    with self._lock:
                        self._processed.discard(key)
                    return
                print(f"[print-watcher] printing: {p}", flush=True)
                print_file(p, self.printer_name)
                print(f"[print-watcher] done: {p}", flush=True)
            except Exception as e:
                print(f"[print-watcher] ERROR {p}: {e}", flush=True)
                with self._lock:
                    self._processed.discard(key)

        threading.Thread(target=run, daemon=True).start()

    def on_created(self, event):  # type: ignore[no-untyped-def]
        if event.is_directory:
            return
        self._schedule(event.src_path)

    def on_modified(self, event):  # type: ignore[no-untyped-def]
        if event.is_directory:
            return
        self._schedule(event.src_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print new photo-booth finals from DATA_DIR tree.")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PHOTOBOOTH_DATA_DIR", ""),
        help="Root data folder (same as DATA_DIR / data-standalone). Env: PHOTOBOOTH_DATA_DIR",
    )
    parser.add_argument(
        "--printer",
        default=os.environ.get("PHOTOBOOTH_PRINTER_NAME", "") or None,
        help="Printer name (Windows: device name; lp -d on Mac/Linux). Default: system default.",
    )
    args = parser.parse_args()
    root = Path(args.data_dir or "").expanduser().resolve()
    if not root.is_dir():
        print(f"DATA_DIR does not exist or is not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    print(f"[print-watcher] watching: {root}", flush=True)
    if args.printer:
        print(f"[print-watcher] printer: {args.printer}", flush=True)
    else:
        print("[print-watcher] printer: (system default)", flush=True)

    handler = FinalsHandler(printer_name=args.printer)
    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join(timeout=5)


if __name__ == "__main__":
    main()
