from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8765
HEALTH_URL = f"http://{HOST}:{PORT}/"
APP_URL = f"http://{HOST}:{PORT}/studio/"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def app_root() -> Path:
    root = exe_root()
    internal = root / "_internal"
    return internal if internal.exists() else root


def data_root() -> Path:
    return exe_root() / "data"


def configure_runtime_env() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ["SHORT_VIDEO_STUDIO_APP_ROOT"] = str(app_root())
    os.environ["SHORT_VIDEO_STUDIO_DATA_ROOT"] = str(data_root())


def pid_file() -> Path:
    return exe_root() / "server.pid"


def stdout_log() -> Path:
    return exe_root() / "server.out.log"


def stderr_log() -> Path:
    return exe_root() / "server.err.log"


def append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8", errors="ignore") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def startup_timeout_seconds() -> int:
    raw = os.environ.get("SHORT_VIDEO_STUDIO_STARTUP_TIMEOUT", "").strip()
    if raw:
        try:
            return max(15, int(raw))
        except ValueError:
            append_log(stderr_log(), f"Invalid SHORT_VIDEO_STUDIO_STARTUP_TIMEOUT={raw!r}, fallback to 120s")
    return 120


def should_open_browser() -> bool:
    raw = os.environ.get("SHORT_VIDEO_STUDIO_OPEN_BROWSER", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def wait_for_health(timeout_seconds: int = 20) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(1)
    return False


def server_command() -> list[str]:
    if is_frozen():
        return [sys.executable, "--serve"]
    return [sys.executable, str(Path(__file__).resolve()), "--serve"]


def launch_server_subprocess() -> int:
    root = exe_root()
    root.mkdir(parents=True, exist_ok=True)
    data_root().mkdir(parents=True, exist_ok=True)
    configure_runtime_env()

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    with stdout_log().open("ab") as out_fp, stderr_log().open("ab") as err_fp:
        process = subprocess.Popen(
            server_command(),
            cwd=str(root),
            stdout=out_fp,
            stderr=err_fp,
            creationflags=creationflags,
            env=os.environ.copy(),
        )
    pid_file().write_text(str(process.pid), encoding="ascii")
    return process.pid


def open_app_browser() -> None:
    if not should_open_browser():
        return
    try:
        webbrowser.open(APP_URL)
    except Exception:
        pass


def run_server() -> int:
    try:
        configure_runtime_env()
        os.chdir(exe_root())
        from uvicorn import run

        append_log(stderr_log(), f"Server starting on http://{HOST}:{PORT}")
        run("app.main:app", host=HOST, port=PORT, log_level="info")
        append_log(stderr_log(), "Server exited normally")
        return 0
    except Exception:
        append_log(stderr_log(), "Unhandled server exception:\n" + traceback.format_exc())
        return 1


def run_launcher() -> int:
    configure_runtime_env()
    timeout = startup_timeout_seconds()
    if wait_for_health(timeout_seconds=2):
        open_app_browser()
        return 0

    child_pid = launch_server_subprocess()
    append_log(stderr_log(), f"Launcher spawned server pid={child_pid}, waiting up to {timeout}s")
    if not wait_for_health(timeout_seconds=timeout):
        append_log(stderr_log(), f"Server did not become healthy within {timeout}s")
        return 1

    append_log(stderr_log(), "Server became healthy")
    open_app_browser()
    return 0


def main() -> int:
    try:
        if "--serve" in sys.argv[1:]:
            return run_server()
        return run_launcher()
    except Exception:
        append_log(stderr_log(), "Unhandled launcher exception:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
