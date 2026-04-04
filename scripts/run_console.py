from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


API_HOST = os.getenv("JOB_CONSOLE_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("JOB_CONSOLE_API_PORT", "8000"))
FRONTEND_HOST = os.getenv("JOB_CONSOLE_FRONTEND_HOST", "127.0.0.1")
FRONTEND_PORT = int(os.getenv("JOB_CONSOLE_FRONTEND_PORT", "8501"))


def _terminate(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    api_url = f"http://{API_HOST}:{API_PORT}"
    frontend_url = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"
    env = os.environ.copy()
    env["JOB_CONSOLE_API_BASE_URL"] = api_url

    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "console.backend.app.main:app",
        "--host",
        API_HOST,
        "--port",
        str(API_PORT),
    ]
    frontend_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "console/frontend/streamlit_app.py",
        "--server.address",
        FRONTEND_HOST,
        "--server.port",
        str(FRONTEND_PORT),
    ]

    print(f"Starting backend: {api_url}")
    backend = subprocess.Popen(backend_cmd, env=env)
    print(f"Starting frontend: {frontend_url}")
    frontend = subprocess.Popen(frontend_cmd, env=env)

    def _handle_signal(signum: int, frame) -> None:
        del signum, frame
        _terminate(frontend)
        _terminate(backend)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while True:
            if backend.poll() is not None:
                _terminate(frontend)
                return int(backend.returncode or 0)
            if frontend.poll() is not None:
                _terminate(backend)
                return int(frontend.returncode or 0)
            time.sleep(0.5)
    finally:
        _terminate(frontend)
        _terminate(backend)


if __name__ == "__main__":
    raise SystemExit(main())
