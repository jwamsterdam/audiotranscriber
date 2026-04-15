"""Restart the desktop app when source files change.

This is a lightweight development helper. It does not preserve app state; it stops the
current Python process and starts a fresh one after edits.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WATCH_PATHS = [
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "pyproject.toml",
]
POLL_SECONDS = 0.8


def main() -> int:
    print("Watching src/ for changes. Press Ctrl+C to stop.")
    process = start_app()
    snapshot = file_snapshot()

    try:
        while True:
            time.sleep(POLL_SECONDS)
            current = file_snapshot()
            if current != snapshot:
                snapshot = current
                print("Change detected. Restarting app...")
                stop_app(process)
                process = start_app()
    except KeyboardInterrupt:
        print("Stopping dev watcher...")
        stop_app(process)
        return 0


def start_app() -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    command = [sys.executable, "-B", "-m", "audiotranscriber.main"]
    return subprocess.Popen(command, cwd=PROJECT_ROOT, env=env)


def stop_app(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        process.terminate()
    else:
        process.send_signal(signal.SIGTERM)

    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def file_snapshot() -> dict[Path, int]:
    snapshot: dict[Path, int] = {}
    for watch_path in WATCH_PATHS:
        if watch_path.is_file():
            snapshot[watch_path] = watch_path.stat().st_mtime_ns
            continue

        if not watch_path.exists():
            continue

        for path in watch_path.rglob("*"):
            if path.is_file() and should_watch(path):
                snapshot[path] = path.stat().st_mtime_ns
    return snapshot


def should_watch(path: Path) -> bool:
    if "__pycache__" in path.parts:
        return False
    return path.suffix in {".py", ".toml"}


if __name__ == "__main__":
    raise SystemExit(main())

