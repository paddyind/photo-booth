#!/usr/bin/env python3
"""
Used by run-api-standalone.sh / .bat:
  - resolve-port: pick a free TCP port (default: try API_PORT, then +1 … +24).
  - check-port: fail if busy (legacy / strict checks).
  - lan-ip: print likely LAN IPv4 for PHOTOBOOTH_API_BASE.

Env:
  PHOTOBOOTH_STRICT_PORT=1  — do not auto-pick another port; exit with help if preferred is busy.
"""
from __future__ import annotations

import errno
import os
import socket
import subprocess
import sys


def _strict_port() -> bool:
    v = (os.environ.get("PHOTOBOOTH_STRICT_PORT") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _port_busy(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
        return False
    except OSError as e:
        if e.errno == errno.EADDRINUSE or getattr(e, "winerror", None) == 10048:
            return True
        raise
    finally:
        s.close()


def _print_listener_details(port: int) -> None:
    """Best-effort: show what is holding the port (helps when kill/lsof mismatch)."""
    print("\n── What is using this port? (copy this if you need help) ──", file=sys.stderr)
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["cmd", "/c", f"netstat -ano | findstr :{port}"],
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
                    "Format-Table LocalAddress, LocalPort, State, OwningProcess -AutoSize",
                ],
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        for args in (
            ["lsof", "-nP", "-iTCP", f":{port}", "-sTCP:LISTEN"],
            ["lsof", "-nP", "-i", f":{port}"],
        ):
            try:
                subprocess.run(args, timeout=10)
            except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
                pass
    print("── end ──\n", file=sys.stderr)


def _print_kill_help(port: int) -> None:
    if sys.platform == "win32":
        print(f"Port {port} is already in use.", file=sys.stderr)
        print("Try one of:", file=sys.stderr)
        print(f'  1) Re-run without strict mode (default): we pick the next free port (8002, 8003, …).', file=sys.stderr)
        print(f"  2) Stop the other program: netstat -ano | findstr \":{port}\"  then  taskkill /PID <pid> /F", file=sys.stderr)
        print(f"  3) Use another port:  set API_PORT=8002", file=sys.stderr)
        try:
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue).OwningProcess",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            pids = [x.strip() for x in out.stdout.strip().splitlines() if x.strip().isdigit()]
            for pid in set(pids):
                print(f"  Listening PID: {pid}  ->  taskkill /PID {pid} /F", file=sys.stderr)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        print(f"Port {port} is already in use.", file=sys.stderr)
        print("Try one of:", file=sys.stderr)
        print("  1) Re-run this script as usual — it will use the next free port (8002, 8003, …) automatically.", file=sys.stderr)
        print(f"  2) Stop the other process:  kill $(lsof -tiTCP:{port} -sTCP:LISTEN)", file=sys.stderr)
        print("     If that does nothing, try:  kill -9 <pid>   (see PIDs below)", file=sys.stderr)
        print(f"  3) Use another port:  API_PORT=8002 ./scripts/run-api-standalone.sh", file=sys.stderr)
        try:
            out = subprocess.run(
                ["lsof", "-tiTCP", str(port), "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            pids = [x for x in out.stdout.strip().split() if x.isdigit()]
            for pid in set(pids):
                print(f"  PID {pid}  (kill -9 {pid} if normal kill did not work)", file=sys.stderr)
        except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
            pass


def _resolve_port(preferred: int, span: int = 25) -> tuple[int, bool]:
    """
    Returns (port, used_fallback).
    If strict and preferred busy, raises SystemExit(1).
    If non-strict, scans preferred .. preferred+span-1.
    """
    if _strict_port():
        if _port_busy(preferred):
            _print_kill_help(preferred)
            _print_listener_details(preferred)
            print(
                f"Strict mode: set PHOTOBOOTH_STRICT_PORT=0 (or unset) to auto-use another port, "
                f"or set API_PORT to a free port.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return preferred, False

    for p in range(preferred, preferred + span):
        if not _port_busy(p):
            return p, p != preferred
    print(
        f"No free TCP port between {preferred} and {preferred + span - 1}. "
        f"Close other apps or set API_PORT to a higher base.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass

    if sys.platform == "darwin":
        for iface in ("en0", "en1", "bridge100", "en2"):
            try:
                out = subprocess.run(
                    ["ipconfig", "getifaddr", iface],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if out.returncode == 0 and (ip := out.stdout.strip()) and not ip.startswith("127."):
                    return ip
            except (OSError, subprocess.TimeoutExpired):
                pass

    if sys.platform == "win32":
        try:
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254*' } | Select-Object -First 1 -ExpandProperty IPAddress)",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ip = out.stdout.strip().splitlines()[0].strip() if out.stdout.strip() else ""
            if ip:
                return ip
        except (OSError, subprocess.TimeoutExpired, IndexError):
            pass

    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2)
        if out.returncode == 0:
            for part in out.stdout.split():
                if part and not part.startswith("127.") and not part.startswith("169.254."):
                    return part
    except (OSError, subprocess.TimeoutExpired):
        pass

    return ""


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: standalone_preflight.py resolve-port <preferred> | check-port <port> | lan-ip",
            file=sys.stderr,
        )
        return 2
    cmd = sys.argv[1]
    if cmd == "resolve-port":
        preferred = int(sys.argv[2])
        span = int(sys.argv[3]) if len(sys.argv) > 3 else 25
        port, fallback = _resolve_port(preferred, span)
        if fallback:
            print(
                f"Note: port {preferred} was busy — using {port} instead. "
                f"(Phone URL must use :{port}. Strict fixed port: PHOTOBOOTH_STRICT_PORT=1.)",
                file=sys.stderr,
            )
        print(port)
        return 0
    if cmd == "check-port":
        port = int(sys.argv[2])
        if _port_busy(port):
            _print_kill_help(port)
            _print_listener_details(port)
            return 1
        return 0
    if cmd == "lan-ip":
        print(_lan_ip())
        return 0
    print("unknown command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
