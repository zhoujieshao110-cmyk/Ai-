from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import PyInstaller.__main__


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
BUILD_ROOT = PROJECT_ROOT / "build"
DIST_ROOT = BUILD_ROOT / "windows-portable"
PYI_DIST_ROOT = BUILD_ROOT / "pyinstaller-dist"
PYI_WORK_ROOT = BUILD_ROOT / "pyinstaller-work"
PYI_SPEC_ROOT = BUILD_ROOT / "pyinstaller-spec"
APP_NAME = "ShortVideoStudio"


def source_analysis_root() -> Path:
    return WORKSPACE_ROOT / "_analysis"


def target_app_root() -> Path:
    return DIST_ROOT / APP_NAME


def target_analysis_root() -> Path:
    return target_app_root() / "_analysis"


def clean() -> None:
    for path in [DIST_ROOT, PYI_DIST_ROOT, PYI_WORK_ROOT, PYI_SPEC_ROOT]:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def pyinstaller_args() -> list[str]:
    def data_arg(path: Path, dest: str) -> str:
        return f"{path};{dest}"

    return [
        str(PROJECT_ROOT / "packaging" / "windows_launcher.py"),
        "--name",
        APP_NAME,
        "--onedir",
        "--noconsole",
        "--clean",
        "--paths",
        str(PROJECT_ROOT),
        "--distpath",
        str(PYI_DIST_ROOT),
        "--workpath",
        str(PYI_WORK_ROOT),
        "--specpath",
        str(PYI_SPEC_ROOT),
        "--add-data",
        data_arg(PROJECT_ROOT / "app", "app"),
        "--add-data",
        data_arg(PROJECT_ROOT / "index.html", "."),
        "--add-data",
        data_arg(PROJECT_ROOT / "app.js", "."),
        "--add-data",
        data_arg(PROJECT_ROOT / "styles.css", "."),
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--collect-all",
        "fastapi",
        "--collect-all",
        "starlette",
        "--collect-all",
        "pydantic",
        "--collect-all",
        "openai",
        "--collect-all",
        "playwright",
        "--collect-all",
        "multipart",
        "--collect-all",
        "numpy",
        "--collect-all",
        "PIL",
    ]


def build_exe() -> None:
    PyInstaller.__main__.run(pyinstaller_args())


def copytree_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def copyfile_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def seed_runtime_data() -> None:
    app_root = target_app_root()
    data_root = app_root / "data"
    (data_root / "templates").mkdir(parents=True, exist_ok=True)
    (data_root / "projects").mkdir(parents=True, exist_ok=True)
    (data_root / "template-products").mkdir(parents=True, exist_ok=True)
    (data_root / "config").mkdir(parents=True, exist_ok=True)

    copytree_if_exists(PROJECT_ROOT / "data" / "templates", data_root / "templates")
    copyfile_if_exists(PROJECT_ROOT / "data" / "config" / "update_manifest.json", data_root / "config" / "update_manifest.json")


def seed_analysis_runtime() -> None:
    src_root = source_analysis_root()
    dst_root = target_analysis_root()
    copytree_if_exists(src_root / "py311", dst_root / "py311")
    copytree_if_exists(src_root / "awesome_app_install" / "_internal", dst_root / "awesome_app_install" / "_internal")
    copytree_if_exists(src_root / "awesome_app_install" / "ffmpeg", dst_root / "awesome_app_install" / "ffmpeg")
    copyfile_if_exists(src_root / "awesome_app_install" / "VERSION", dst_root / "awesome_app_install" / "VERSION")


def write_helpers() -> None:
    app_root = target_app_root()
    readme = app_root / "README.txt"
    stop_bat = app_root / "Stop Short Video Studio.bat"
    readme.write_text(
        "\n".join(
            [
                "Short Video Studio Windows Portable",
                "",
                "1. 双击 ShortVideoStudio.exe 启动。",
                "2. 首次启动会在当前目录创建 data 文件夹。",
                "3. 如需停止后台服务，运行“Stop Short Video Studio.bat”。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stop_bat.write_text(
        "\n".join(
            [
                "@echo off",
                "setlocal EnableExtensions",
                'cd /d "%~dp0"',
                'set "PID_FILE=%~dp0server.pid"',
                'if exist "%PID_FILE%" (',
                '  set /p PID=<"%PID_FILE%"',
                '  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Stop-Process -Id %PID% -Force -ErrorAction Stop; exit 0 } catch { exit 1 }"',
                '  del /q "%PID_FILE%" >nul 2>nul',
                ") else (",
                '  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess; if ($p) { Stop-Process -Id $p -Force }"',
                ")",
                "exit /b 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def assemble_portable_dist() -> Path:
    src_app = PYI_DIST_ROOT / APP_NAME
    dst_app = target_app_root()
    dst_app.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_app, dst_app, dirs_exist_ok=True)
    seed_runtime_data()
    seed_analysis_runtime()
    write_helpers()
    return dst_app


def create_zip(app_root: Path) -> Path:
    archive_base = DIST_ROOT / f"{APP_NAME}-windows-portable"
    archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=DIST_ROOT, base_dir=APP_NAME)
    return Path(archive_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Short Video Studio Windows portable app.")
    parser.add_argument("--skip-zip", action="store_true", help="Assemble the portable app directory only.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    clean()
    build_exe()
    app_root = assemble_portable_dist()
    print(f"Portable app: {app_root}")
    if args.skip_zip:
        print("Zip archive:  skipped")
        return
    zip_path = create_zip(app_root)
    print(f"Zip archive:  {zip_path}")


if __name__ == "__main__":
    main()
