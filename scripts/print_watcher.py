#!/usr/bin/env python3
"""
Watch for new printable files and send them to the default printer.

Modes (Mac/Linux: `lp`; Windows: pywin32 GDI or os.startfile print):

1) **finals** (default) — recursive watch under DATA_DIR for paths under **/finals/**.
   Files stay in place after printing (legacy photo-booth layout).

2) **queue** — watch a single folder **print-queue** (configurable). After a successful
   print, the file is **moved** to **print-archive** so it is never printed twice.
   Pair with API env `PHOTOBOOTH_COPY_FINAL_TO_PRINT_QUEUE=1` so each composed final
   is copied into the queue.

Usage:
  export PHOTOBOOTH_DATA_DIR=/path/to/data-standalone
  python scripts/print_watcher.py

  python scripts/print_watcher.py --watch-mode queue --data-dir ./data-standalone --printer "EPSON L3250"

Env:
  PHOTOBOOTH_PRINT_WATCH_MODE=finals|queue
  PHOTOBOOTH_PRINT_QUEUE_DIR   (default: DATA_DIR/print-queue)
  PHOTOBOOTH_PRINT_ARCHIVE_DIR (default: DATA_DIR/print-archive)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path


def _write_print_status(status_root: Path, state: str, message: str = "", file_name: str = "") -> None:
    """Expose state to the API + web UI via DATA_DIR/.photobooth-print-status.json (atomic write)."""
    try:
        status_root.mkdir(parents=True, exist_ok=True)
        path = status_root / ".photobooth-print-status.json"
        tmp = path.with_suffix(".json.tmp")
        payload = {
            "state": state,
            "message": message,
            "file": file_name or None,
            "updated_at_ms": int(time.time() * 1000),
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        print(f"[print-watcher] status file write failed: {e}", flush=True)

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


def _is_printable_ext(path: Path) -> bool:
    return path.suffix.lower() in PRINTABLE_EXT


def _is_printable_final(path: Path) -> bool:
    return _is_printable_ext(path) and _is_under_finals(path)


def _wait_stable(path: Path, attempts: int = 15, delay: float = 0.4) -> bool:
    last = -1
    for _ in range(attempts):
        try:
            if not path.is_file():
                time.sleep(delay)
                continue
            size = path.stat().st_size
            if size > 0 and size == last:
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

    _print_lp(path, printer_name)


def _unique_archive_path(archive_dir: Path, original_name: str) -> Path:
    dest = archive_dir / original_name
    if not dest.exists():
        return dest
    stem = Path(original_name).stem
    suf = Path(original_name).suffix
    return archive_dir / f"{stem}_{uuid.uuid4().hex[:8]}{suf}"


def _move_to_archive(path: Path, archive_dir: Path) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = _unique_archive_path(archive_dir, path.name)
    last_err: OSError | None = None
    for _ in range(24):
        try:
            shutil.move(str(path), str(dest))
            return dest
        except OSError as e:
            last_err = e
            time.sleep(0.25)
    if last_err:
        raise last_err
    shutil.move(str(path), str(dest))
    return dest


class FinalsHandler(FileSystemEventHandler):
    def __init__(self, printer_name: str | None, status_root: Path) -> None:
        self.printer_name = printer_name
        self.status_root = status_root
        self._processed: set[str] = set()
        self._lock = threading.Lock()

    def _schedule(self, path: str) -> None:
        p = Path(path)
        if not _is_printable_final(p):
            return
        key = str(p.resolve())
        with self._lock:
            if key in self._processed:
                return
            self._processed.add(key)

        def run() -> None:
            name = p.name
            try:
                if not _wait_stable(p):
                    print(f"[print-watcher] skip (unstable): {p}", flush=True)
                    _write_print_status(
                        self.status_root,
                        "skipped",
                        "Print skipped: the file was not ready in time. Try preparing the final again.",
                        name,
                    )
                    with self._lock:
                        self._processed.discard(key)
                    return
                _write_print_status(self.status_root, "printing", f"Printing now: {name}", name)
                print(f"[print-watcher] printing: {p}", flush=True)
                print_file(p, self.printer_name)
                print(f"[print-watcher] done: {p}", flush=True)
                _write_print_status(self.status_root, "success", "Print finished successfully.", name)
            except Exception as e:
                err = str(e)
                print(f"[print-watcher] ERROR {p}: {e}", flush=True)
                _write_print_status(
                    self.status_root,
                    "error",
                    f"Printer error: {err}",
                    name,
                )
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


class QueuePrintHandler(FileSystemEventHandler):
    """Watch one directory (non-recursive); after print, move file to archive_dir."""

    def __init__(self, queue_dir: Path, archive_dir: Path, printer_name: str | None, status_root: Path) -> None:
        self.queue_dir = queue_dir.resolve()
        self.archive_dir = archive_dir.resolve()
        self.printer_name = printer_name
        self.status_root = status_root
        self._processed: set[str] = set()
        self._lock = threading.Lock()

    def _in_queue(self, p: Path) -> bool:
        try:
            return p.is_file() and p.parent.resolve() == self.queue_dir
        except OSError:
            return False

    def _schedule(self, path: str) -> None:
        p = Path(path)
        if not _in_queue(p) or not _is_printable_ext(p):
            return
        key = str(p.resolve())
        with self._lock:
            if key in self._processed:
                return
            self._processed.add(key)

        def run() -> None:
            name = p.name
            try:
                if not _wait_stable(p):
                    print(f"[print-watcher] queue skip (unstable): {p}", flush=True)
                    _write_print_status(
                        self.status_root,
                        "skipped",
                        "Print skipped: the file was not ready in time. Try again.",
                        name,
                    )
                    with self._lock:
                        self._processed.discard(key)
                    return
                _write_print_status(self.status_root, "printing", f"Printing now: {name}", name)
                print(f"[print-watcher] queue printing: {p}", flush=True)
                print_file(p, self.printer_name)
                if sys.platform == "win32":
                    time.sleep(0.35)
                archived = _move_to_archive(p, self.archive_dir)
                print(f"[print-watcher] queue archived: {archived}", flush=True)
                _write_print_status(
                    self.status_root,
                    "success",
                    f"Print finished — saved to print-archive as {archived.name}.",
                    name,
                )
            except Exception as e:
                err = str(e)
                print(f"[print-watcher] queue ERROR {p}: {e}", flush=True)
                _write_print_status(
                    self.status_root,
                    "error",
                    f"Printer error: {err}",
                    name,
                )
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
    parser = argparse.ArgumentParser(description="Print new photo-booth finals or print-queue files.")
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
    parser.add_argument(
        "--watch-mode",
        choices=("finals", "queue"),
        default=(os.environ.get("PHOTOBOOTH_PRINT_WATCH_MODE", "finals") or "finals").strip().lower(),
        help="finals=watch **/finals/** under data-dir; queue=watch print-queue only, then archive.",
    )
    parser.add_argument(
        "--queue-dir",
        default=os.environ.get("PHOTOBOOTH_PRINT_QUEUE_DIR", ""),
        help="Queue folder (queue mode). Default: DATA_DIR/print-queue",
    )
    parser.add_argument(
        "--archive-dir",
        default=os.environ.get("PHOTOBOOTH_PRINT_ARCHIVE_DIR", ""),
        help="Archive folder after successful print (queue mode). Default: DATA_DIR/print-archive",
    )
    args = parser.parse_args()
    root = Path(args.data_dir or "").expanduser().resolve()
    if not root.is_dir():
        print(f"DATA_DIR does not exist or is not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    mode = args.watch_mode
    if mode not in ("finals", "queue"):
        mode = "finals"

    print(f"[print-watcher] mode: {mode}", flush=True)
    print(f"[print-watcher] data-dir: {root}", flush=True)
    if args.printer:
        print(f"[print-watcher] printer: {args.printer}", flush=True)
    else:
        print("[print-watcher] printer: (system default)", flush=True)

    def _resolved_dir(cli: str, env_name: str, default: Path) -> Path:
        if (cli or "").strip():
            return Path(cli).expanduser().resolve()
        ev = (os.environ.get(env_name) or "").strip()
        if ev:
            return Path(ev).expanduser().resolve()
        return default

    observer = Observer()

    if mode == "queue":
        q = _resolved_dir(args.queue_dir, "PHOTOBOOTH_PRINT_QUEUE_DIR", root / "print-queue")
        a = _resolved_dir(args.archive_dir, "PHOTOBOOTH_PRINT_ARCHIVE_DIR", root / "print-archive")
        q.mkdir(parents=True, exist_ok=True)
        a.mkdir(parents=True, exist_ok=True)
        print(f"[print-watcher] queue dir: {q}", flush=True)
        print(f"[print-watcher] archive dir: {a}", flush=True)
        handler = QueuePrintHandler(queue_dir=q, archive_dir=a, printer_name=args.printer, status_root=root)
        observer.schedule(handler, str(q), recursive=False)
    else:
        print(f"[print-watcher] watching finals under: {root}", flush=True)
        handler = FinalsHandler(printer_name=args.printer, status_root=root)
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
