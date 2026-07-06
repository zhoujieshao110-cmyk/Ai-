from __future__ import annotations

import copy
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import storage


APP_NAME = "ShortVideoStudio"
LOG_CHAR_LIMIT = 160_000


class PackagingRuntime:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._task: dict[str, Any] | None = None
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None

    def project_root(self) -> Path:
        return storage.SOURCE_ROOT

    def workspace_root(self) -> Path:
        return self.project_root().parent

    def build_script(self) -> Path:
        return self.project_root() / "packaging" / "build_windows_exe.py"

    def python_bin(self) -> Path:
        venv_python = self.workspace_root() / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            return venv_python
        return Path(sys.executable).resolve()

    def output_root(self) -> Path:
        return self.project_root() / "build" / "windows-portable"

    def portable_dir(self) -> Path:
        return self.output_root() / APP_NAME

    def exe_path(self) -> Path:
        return self.portable_dir() / f"{APP_NAME}.exe"

    def zip_path(self) -> Path:
        return self.output_root() / f"{APP_NAME}-windows-portable.zip"

    def available(self) -> bool:
        return self.build_script().exists() and self.python_bin().exists()

    def open_target(self, target: str) -> Path:
        mapping = {
            "output": self.output_root(),
            "portable": self.portable_dir(),
            "exe": self.exe_path(),
            "zip": self.zip_path(),
        }
        path = mapping.get(target)
        if path is None:
            raise ValueError(f"Unknown packaging target: {target}")
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    def artifacts_payload(self) -> dict[str, Any]:
        output_root = self.output_root()
        portable_dir = self.portable_dir()
        exe_path = self.exe_path()
        zip_path = self.zip_path()
        zip_stat = zip_path.stat() if zip_path.exists() else None
        return {
            "output_root": str(output_root),
            "output_exists": output_root.exists(),
            "portable_dir": str(portable_dir),
            "portable_exists": portable_dir.exists(),
            "exe_path": str(exe_path),
            "exe_exists": exe_path.exists(),
            "zip_path": str(zip_path),
            "zip_exists": zip_path.exists(),
            "zip_size": zip_stat.st_size if zip_stat else 0,
            "zip_mtime": zip_stat.st_mtime if zip_stat else None,
        }

    def latest(self) -> dict[str, Any]:
        with self._lock:
            task = copy.deepcopy(self._task)
        return {
            "available": self.available(),
            "script_path": str(self.build_script()),
            "python_path": str(self.python_bin()),
            "artifacts": self.artifacts_payload(),
            "task": task,
        }

    def start(self, include_zip: bool = False) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("当前目录缺少打包脚本或 Python 环境，暂时无法导出 EXE。")
        with self._lock:
            if self._task and self._task.get("running"):
                raise RuntimeError("已有导出任务正在运行，请先等待当前任务结束。")
            command = [str(self.python_bin()), str(self.build_script())]
            if not include_zip:
                command.append("--skip-zip")
            task = {
                "id": int(time.time() * 1000),
                "status": "running",
                "running": True,
                "include_zip": include_zip,
                "mode": "portable+zip" if include_zip else "portable",
                "started_at": time.time(),
                "finished_at": None,
                "log": "",
                "error": "",
                "command": " ".join(command),
                "cwd": str(self.project_root()),
                "cancel_requested": False,
                "result": None,
            }
            self._task = task
            self._thread = threading.Thread(
                target=self._run_task,
                args=(task["id"], include_zip),
                daemon=True,
                name="packaging-runtime",
            )
            self._thread.start()
        return self.latest()

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            task = self._task
            process = self._process
            if not task or not task.get("running"):
                return self.latest()
            task["cancel_requested"] = True
            self._append_log_locked(task, "[packaging] cancel requested")
        if process is not None:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    process.terminate()
            except Exception:
                pass
        return self.latest()

    def _append_log_locked(self, task: dict[str, Any], line: str) -> None:
        current = str(task.get("log") or "")
        updated = f"{current}\n{line}".strip() if current else line
        if len(updated) > LOG_CHAR_LIMIT:
            updated = updated[-LOG_CHAR_LIMIT:]
        task["log"] = updated
        task["result"] = self.artifacts_payload()

    def _finish_task(self, task_id: int, status: str, error: str = "") -> None:
        with self._lock:
            if not self._task or self._task.get("id") != task_id:
                return
            self._task["running"] = False
            self._task["status"] = status
            self._task["finished_at"] = time.time()
            self._task["error"] = error
            self._task["result"] = self.artifacts_payload()
            self._process = None

    def _run_task(self, task_id: int, include_zip: bool) -> None:
        script_path = self.build_script()
        command = [str(self.python_bin()), str(script_path)]
        if not include_zip:
            command.append("--skip-zip")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                command,
                cwd=str(self.project_root()),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env={**os.environ, "PYTHONUTF8": "1"},
                creationflags=creationflags,
            )
        except Exception as exc:
            self._finish_task(task_id, "failed", f"启动打包进程失败：{exc}")
            return

        with self._lock:
            if not self._task or self._task.get("id") != task_id:
                try:
                    process.terminate()
                except Exception:
                    pass
                return
            self._process = process
            self._append_log_locked(self._task, f"[packaging] started -> {' '.join(command)}")

        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.rstrip()
                if not line:
                    continue
                with self._lock:
                    if not self._task or self._task.get("id") != task_id:
                        break
                    self._append_log_locked(self._task, line)

        return_code = process.wait()
        with self._lock:
            task = self._task if self._task and self._task.get("id") == task_id else None
            cancelled = bool(task and task.get("cancel_requested"))
            if task is not None:
                if cancelled:
                    self._append_log_locked(task, "[packaging] task cancelled")
                elif return_code == 0:
                    self._append_log_locked(task, "[packaging] task finished successfully")
                else:
                    self._append_log_locked(task, f"[packaging] task failed with exit code {return_code}")
        if cancelled:
            self._finish_task(task_id, "cancelled")
        elif return_code == 0:
            self._finish_task(task_id, "succeeded")
        else:
            self._finish_task(task_id, "failed", f"命令退出码 {return_code}")
