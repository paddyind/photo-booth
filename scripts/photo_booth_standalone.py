#!/usr/bin/env python3
"""
Single entry after venv + API deps are installed: starts optional print_watcher and uvicorn.

Loaded by run-api-standalone.sh / .bat. Print watcher lifecycle is tied to this process
(so Ctrl+C stops both on Mac, Linux, and Windows).

Print watcher auto-starts when PHOTOBOOTH_PRINTER_NAME is set, unless
PHOTOBOOTH_ENABLE_PRINT_WATCHER is explicitly 0/false/no/off.
"""
from __future__ import annotations

import atexit
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _strip_quotes(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def load_env_standalone() -> None:
    path = ROOT / ".env.standalone"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        if t.startswith("export "):
            t = t[7:].lstrip()
        if "=" not in t:
            continue
        k, _, v = t.partition("=")
        k = k.strip()
        v = _strip_quotes(v.strip())
        if k:
            os.environ[k] = v


def _watcher_enabled() -> bool:
    raw = (os.environ.get("PHOTOBOOTH_ENABLE_PRINT_WATCHER") or "").strip().lower()
    printer = _strip_quotes(os.environ.get("PHOTOBOOTH_PRINTER_NAME") or "").strip()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    # Auto: printer name in .env ⇒ enable folder printing without a second flag.
    return bool(printer)


def _resolve_port(preferred: str) -> int:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "standalone_preflight.py"), "resolve-port", preferred],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if r.stderr:
        print(r.stderr, file=sys.stderr, end="")
    r.check_returncode()
    lines = [ln for ln in r.stdout.strip().splitlines() if ln.strip()]
    return int(lines[-1])


def _lan_ip() -> str:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "standalone_preflight.py"), "lan-ip"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return ""
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _print_startup_banner(port: int, lan: str) -> None:
    """URLs + how to verify phone connectivity + printer alignment (printed once at startup)."""
    sep = "=" * 62
    print("", flush=True)
    print(sep, flush=True)
    print("  STANDALONE SERVER — URLs", flush=True)
    print(sep, flush=True)
    print(f"  Local (this PC):  http://127.0.0.1:{port}", flush=True)
    if lan:
        print(f"  LAN (phone/tablet): http://{lan}:{port}", flush=True)
        base = f"http://{lan}:{port}"
    else:
        print("  LAN: (not auto-detected — use this PC's Wi-Fi IPv4 from Settings / ipconfig)", flush=True)
        base = f"http://<THIS_PC_LAN_IP>:{port}"
    print("", flush=True)
    port_fallback = (os.environ.get("PHOTOBOOTH_PORT_FALLBACK") or "").strip().lower() in ("1", "true", "yes", "on")
    print(sep, flush=True)
    print("  MOBILE APP URL — stop/restart does NOT change this PC's Wi-Fi IP", flush=True)
    print(sep, flush=True)
    print("  • You do NOT need to rebuild the APK just because you stopped or restarted the server.", flush=True)
    print("  • The Wi-Fi IP (LAN line above) stays the same unless you change networks or DHCP gives a new one.", flush=True)
    if not port_fallback:
        print(
            f"  • Port is fixed to API_PORT ({port}) — anything listening here was cleared so PHOTOBOOTH_API_BASE can stay "
            f"http://{lan or '<LAN-IP>'}:{port}",
            flush=True,
        )
    else:
        print(
            "  • PHOTOBOOTH_PORT_FALLBACK=1 — if this port was busy, a higher port may have been chosen; update the app URL.",
            flush=True,
        )
    print("", flush=True)
    print(sep, flush=True)
    print("  PHONE / TABLET — check connectivity (before relying on the app)", flush=True)
    print(sep, flush=True)
    print("  1) Phone must reach THIS computer: same Wi‑Fi OR connected to this PC’s mobile hotspot.", flush=True)
    print("     (Hotspot counts as one LAN — use the LAN IP printed above, not the phone’s cellular data.)", flush=True)
    print("     Do not use 127.0.0.1 on the phone — that is the phone itself.", flush=True)
    if lan:
        print("  2) On the phone, open Chrome/Safari and type the URL EXACTLY (copy from a photo if needed):", flush=True)
        print(f"        {base}/health", flush=True)
        if lan.startswith("192.168."):
            print(
                "     TYPING TIP: addresses start with  192.168.  (digit 2 then 9 then 2).",
                flush=True,
            )
            print(
                "     If you type  198.168.…  you get ERR_ADDRESS_UNREACHABLE — that is the wrong number.",
                flush=True,
            )
    else:
        print("  2) On the phone browser, open:  http://<THIS_PC_LAN_IP>:%d/health" % port, flush=True)
    print('     Expected: JSON with "status":"ok" and "service":"photo-booth-api".', flush=True)
    print("  3) If the page does not load:", flush=True)
    if port_fallback:
        print("     • Confirm the URL uses the port shown above (it may not be 8001 if fallback picked another).", flush=True)
    else:
        print("     • Confirm the port matches API_PORT (default 8001) shown above.", flush=True)
    if sys.platform == "win32":
        print("     • Windows: allow inbound TCP on this port for Python (Firewall).", flush=True)
        print("       See scripts/README-WINDOWS-STANDALONE.txt or README (Windows).", flush=True)
    else:
        print("     • macOS: System Settings → Network → Firewall — allow Python if blocked.", flush=True)
    print("     • Turn off VPN on the phone if it blocks local network access.", flush=True)
    print("  4) Mobile APK: set PHOTOBOOTH_API_BASE to the LAN URL, then npm run prepare-www + cap sync.", flush=True)
    print("  5) Optional: rebuild with PHOTOBOOTH_CONNECTIVITY_DEBUG=1 for in-app /health + logs.", flush=True)
    print("", flush=True)
    print(sep, flush=True)
    print("  PRINTER — Mac & Windows (same .env.standalone, one script)", flush=True)
    print(sep, flush=True)
    print("  PHOTOBOOTH_PRINTER_NAME must match the OS print queue name exactly.", flush=True)
    print("  • macOS/Linux:  ./scripts/list-printers.sh   (or: lpstat -p)", flush=True)
    print("  • Windows:      powershell -File scripts/list-printers.ps1", flush=True)
    print("  Auto-print uses scripts/print_watcher.py (CUPS `lp` on Mac, GDI on Windows).", flush=True)
    print("", flush=True)
    print(sep, flush=True)
    print("  IF SOMETHING IS STUCK — NO TECH SUPPORT NEEDED", flush=True)
    print(sep, flush=True)
    if sys.platform == "win32":
        print("  • Stop everything for this booth:", flush=True)
        print("      scripts\\stop-photo-booth-standalone.bat", flush=True)
        print("    Then start again:", flush=True)
        print("      scripts\\run-api-standalone.bat", flush=True)
        print("  • Or one double-click:", flush=True)
        print("      scripts\\restart-photo-booth-standalone.bat", flush=True)
    else:
        print("  • Stop:", flush=True)
        print("      ./scripts/stop-photo-booth-standalone.sh", flush=True)
        print("  • Start again:", flush=True)
        print("      ./scripts/run-api-standalone.sh", flush=True)
        print("  • Or:", flush=True)
        print("      ./scripts/restart-photo-booth-standalone.sh", flush=True)
    print("  • This only affects Photo Booth in this folder — other apps are left alone.", flush=True)
    print("", flush=True)
    print(sep, flush=True)
    print("  DATA", flush=True)
    print(sep, flush=True)


def main() -> int:
    os.chdir(ROOT)
    load_env_standalone()

    if str(ROOT) not in (os.environ.get("PYTHONPATH") or ""):
        sep = ";" if sys.platform == "win32" else ":"
        prev = os.environ.get("PYTHONPATH", "").strip()
        os.environ["PYTHONPATH"] = str(ROOT) if not prev else f"{ROOT}{sep}{prev}"

    data_dir = Path(os.environ.get("DATA_DIR", str(ROOT / "data-standalone"))).expanduser().resolve()
    os.environ["DATA_DIR"] = str(data_dir)
    frames_dir = Path(os.environ.get("FRAMES_DIR", str(ROOT / "shared" / "frames"))).expanduser().resolve()
    os.environ["FRAMES_DIR"] = str(frames_dir)
    booth_data = Path(os.environ.get("PHOTOBOOTH_DATA_DIR", str(data_dir))).expanduser().resolve()
    os.environ["PHOTOBOOTH_DATA_DIR"] = str(booth_data)

    data_dir.mkdir(parents=True, exist_ok=True)

    watcher_proc: subprocess.Popen | None = None

    def stop_watcher() -> None:
        nonlocal watcher_proc
        if watcher_proc is None:
            return
        if watcher_proc.poll() is not None:
            watcher_proc = None
            return
        watcher_proc.terminate()
        try:
            watcher_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            watcher_proc.kill()
            watcher_proc.wait(timeout=5)
        watcher_proc = None

    atexit.register(stop_watcher)

    enable_watcher = _watcher_enabled()
    printer = _strip_quotes(os.environ.get("PHOTOBOOTH_PRINTER_NAME") or "").strip()
    pwm = (os.environ.get("PHOTOBOOTH_PRINT_WATCH_MODE") or "finals").strip().lower()

    if enable_watcher:
        print("Syncing print-watcher dependencies …", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(ROOT / "scripts" / "requirements-print-watcher.txt")],
            cwd=str(ROOT),
            check=True,
        )
        if sys.platform == "win32":
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "pywin32"],
                cwd=str(ROOT),
                capture_output=True,
            )
        wargs = [
            sys.executable,
            str(ROOT / "scripts" / "print_watcher.py"),
            "--data-dir",
            str(booth_data),
        ]
        if pwm == "queue":
            wargs.extend(["--watch-mode", "queue"])
            print("Print watcher: mode=queue (print-queue → print → print-archive)", flush=True)
        else:
            print("Print watcher: mode=finals (any **/finals/** under DATA_DIR)", flush=True)
        if printer:
            wargs.extend(["--printer", printer])
            print(f"Print watcher: printer={printer}", flush=True)
        else:
            print("Print watcher: printer=(system default)", flush=True)
        print(f"Print watcher: PHOTOBOOTH_DATA_DIR={booth_data}", flush=True)
        watcher_proc = subprocess.Popen(
            wargs,
            cwd=str(ROOT),
            env=os.environ.copy(),
        )
        print(f"Print watcher started (pid {watcher_proc.pid}). Stops when you stop the API (Ctrl+C).", flush=True)
    else:
        print(
            "Print watcher: off (set PHOTOBOOTH_PRINTER_NAME in .env.standalone, or PHOTOBOOTH_ENABLE_PRINT_WATCHER=1).",
            flush=True,
        )

    preferred = (os.environ.get("API_PORT") or "8001").strip()
    port = _resolve_port(preferred)
    os.environ["API_PORT"] = str(port)

    lan = _lan_ip()
    _print_startup_banner(port, lan)
    print(f"  DATA_DIR={data_dir}", flush=True)
    print(f"  FRAMES_DIR={frames_dir}", flush=True)
    print("", flush=True)
    print("  Uvicorn starting (Ctrl+C stops API + print watcher) …", flush=True)
    print("", flush=True)

    try:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "apps.api.app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(port),
            ],
            cwd=str(ROOT),
            env=os.environ.copy(),
        ).returncode
    except KeyboardInterrupt:
        return 130
    finally:
        stop_watcher()


if __name__ == "__main__":
    raise SystemExit(main())
