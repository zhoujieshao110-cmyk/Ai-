from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys
import traceback
import warnings
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = APP_ROOT.parent
EXTRACT_ROOT = WORKSPACE_ROOT / "AwesomeShortVideoMaker.exe_extracted"
PYZ_ROOT = EXTRACT_ROOT / "PYZ.pyz_extracted"
INTERNAL_ROOT = WORKSPACE_ROOT / "_analysis" / "awesome_app_install" / "_internal"
FFMPEG_BIN_ROOT = WORKSPACE_ROOT / "_analysis" / "awesome_app_install" / "ffmpeg" / "bin"
SOURCE_TEMPLATES = INTERNAL_ROOT / "模板文件"
TARGET_TEMPLATES = EXTRACT_ROOT / "模板文件"
PYDANTIC_CORE_SOURCE = INTERNAL_ROOT / "pydantic_core" / "_pydantic_core.cp311-win_amd64.pyd"
PYDANTIC_CORE_TARGET = PYZ_ROOT / "pydantic_core" / "_pydantic_core.cp311-win_amd64.pyd"
JITER_SOURCE = INTERNAL_ROOT / "jiter" / "jiter.cp311-win_amd64.pyd"
JITER_TARGET = PYZ_ROOT / "jiter" / "jiter.cp311-win_amd64.pyd"
CURRENT_DATA_ROOT = APP_ROOT / "data"
CURRENT_PROJECTS_ROOT = CURRENT_DATA_ROOT / "projects"
CURRENT_TEMPLATES_ROOT = CURRENT_DATA_ROOT / "templates"
ORIGINAL_PRODUCTS_MIRROR_ROOT = CURRENT_DATA_ROOT / "_original_runtime" / "products"
INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*]+')


def ensure_original_assets() -> None:
    if SOURCE_TEMPLATES.exists() and not TARGET_TEMPLATES.exists():
        shutil.copytree(SOURCE_TEMPLATES, TARGET_TEMPLATES)
    if not PYZ_ROOT.exists():
        raise RuntimeError(f"Original runtime not found: {PYZ_ROOT}")
    if not INTERNAL_ROOT.exists():
        raise RuntimeError(f"Original dependency root not found: {INTERNAL_ROOT}")
    if PYDANTIC_CORE_SOURCE.exists() and not PYDANTIC_CORE_TARGET.exists():
        PYDANTIC_CORE_TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PYDANTIC_CORE_SOURCE, PYDANTIC_CORE_TARGET)
    if JITER_SOURCE.exists() and not JITER_TARGET.exists():
        JITER_TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(JITER_SOURCE, JITER_TARGET)


def apply_env(values: dict[str, str]) -> None:
    for key, value in values.items():
        if value is None:
            continue
        os.environ[str(key)] = str(value)
    if FFMPEG_BIN_ROOT.exists():
        path_parts = [str(FFMPEG_BIN_ROOT)]
        current_path = os.environ.get("PATH", "")
        if current_path:
            path_parts.append(current_path)
        os.environ["PATH"] = os.pathsep.join(path_parts)
    if not os.environ.get("VOLC_ASR_APP_KEY"):
        os.environ["VOLC_ASR_APP_KEY"] = os.environ.get("VOLC_TTS_APP_KEY", "")
    if not os.environ.get("VOLC_ASR_ACCESS_KEY"):
        os.environ["VOLC_ASR_ACCESS_KEY"] = os.environ.get("VOLC_TTS_ACCESS_KEY", "")


def bootstrap_imports() -> None:
    sys.path.insert(0, str(PYZ_ROOT))
    sys.path.insert(0, str(INTERNAL_ROOT))


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def safe_path_name(value: Any, default: str) -> str:
    cleaned = compact_text(value)
    cleaned = INVALID_PATH_CHARS_RE.sub("_", cleaned)
    cleaned = cleaned.strip(" .")
    return cleaned or default


def read_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def sync_current_projects_to_original_products(products_root: Path, template_key: str) -> None:
    template_name = safe_path_name(template_key, "template")
    template_root = products_root / template_name
    if template_root.exists():
        shutil.rmtree(template_root, ignore_errors=True)
    template_root.mkdir(parents=True, exist_ok=True)

    if not CURRENT_PROJECTS_ROOT.exists():
        return

    for project_dir in sorted(CURRENT_PROJECTS_ROOT.iterdir(), key=lambda item: item.name):
        if not project_dir.is_dir():
            continue
        meta = read_json_file(project_dir / "project.json", {})
        if not isinstance(meta, dict):
            continue
        if compact_text(meta.get("template")) != template_key:
            continue
        topic_name = compact_text(meta.get("topic_name"))
        if not topic_name:
            continue
        target_dir = template_root / safe_path_name(topic_name, project_dir.name)
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("brief.md", "content.md", "references.json", "summary.json"):
            source_path = project_dir / filename
            if source_path.exists():
                shutil.copy2(source_path, target_dir / filename)


def normalize_reference_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        title = compact_text(item.get("title"))
        url = compact_text(item.get("url"))
        snippet = compact_text(item.get("snippet") or item.get("summary") or item.get("content"))
        source = compact_text(item.get("source") or item.get("site") or item.get("provider"))
    else:
        title = compact_text(getattr(item, "title", ""))
        url = compact_text(getattr(item, "url", ""))
        snippet = compact_text(getattr(item, "snippet", "") or getattr(item, "summary", ""))
        source = compact_text(getattr(item, "source", "") or getattr(item, "site", ""))
    if not (title or url or snippet):
        return None
    return {
        "title": title or url or "Reference",
        "url": url,
        "snippet": snippet,
        "source": source,
    }


def load_original_references(topic_dir: Path) -> list[dict[str, Any]]:
    raw = read_json_file(topic_dir / "references.json", [])
    if isinstance(raw, dict):
        for key in ("references", "items", "results"):
            value = raw.get(key)
            if isinstance(value, list):
                raw = value
                break
        else:
            raw = []
    if not isinstance(raw, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in raw:
        normalized = normalize_reference_item(item)
        if normalized:
            refs.append(normalized)
    return refs


def optional_path(value: Any) -> Path | None:
    text = compact_text(value)
    return Path(text) if text else None


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def normalize_dialogue_payload(items: list[Any] | None) -> list[Any]:
    return list(items or [])


def run_tts(payload: dict[str, Any]) -> dict[str, Any]:
    from video_maker import tts_doubao

    output_path = Path(payload["output_path"])
    if output_path.exists():
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dialogue_lines = normalize_dialogue_payload(payload.get("dialogue_lines"))
    with contextlib.redirect_stdout(sys.stderr):
        result = tts_doubao.generate_podcast(
            str(payload.get("text", "")),
            output_path,
            dialogue_lines=dialogue_lines,
        )
    return {
        "ok": True,
        "output_path": str(result),
        "size": result.stat().st_size if result.exists() else 0,
    }


def run_asr(payload: dict[str, Any]) -> dict[str, Any]:
    from video_maker import asr_volcengine

    audio_path = Path(payload["audio_path"])
    srt_output = Path(payload["srt_output"])
    srt_output.parent.mkdir(parents=True, exist_ok=True)
    dialogue_lines = payload.get("dialogue_lines") or None
    with contextlib.redirect_stdout(sys.stderr):
        utterances, result_path = asr_volcengine.transcribe_to_srt(
            audio_path,
            srt_output,
            force=True,
            dialogue_lines=dialogue_lines,
        )
    return {
        "ok": True,
        "srt_output": str(result_path),
        "utterances": [
            {
                "start_ms": int(item.start_ms),
                "end_ms": int(item.end_ms),
                "text": str(item.text),
            }
            for item in utterances
        ],
    }


def run_scene_timeline(payload: dict[str, Any]) -> dict[str, Any]:
    from video_maker import scene_timeline

    audio_path = Path(payload["audio_path"])
    srt_path = Path(payload["srt_path"])
    output_path = Path(payload["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scene_prompts = [str(item) for item in (payload.get("scene_prompts") or []) if str(item).strip()]
    if not scene_prompts:
        raise RuntimeError("scene_prompts 为空，无法调用原版 scene_timeline。")
    dialogue_lines = payload.get("dialogue_lines") or None
    cover_duration = float(payload.get("cover_duration", 10.0) or 10.0)
    outro_duration = float(payload.get("outro_duration", 0.0) or 0.0)
    align_mode = str(payload.get("align_mode", "full") or "full")
    force = bool(payload.get("force", True))
    with contextlib.redirect_stdout(sys.stderr):
        result_path = scene_timeline.build_scene_timeline(
            audio_path=audio_path,
            srt_path=srt_path,
            scene_prompts=scene_prompts,
            output_path=output_path,
            cover_duration=cover_duration,
            outro_duration=outro_duration,
            dialogue_lines=dialogue_lines,
            align_mode=align_mode,
            force=force,
        )
    timeline = json.loads(result_path.read_text(encoding="utf-8"))
    scenes = timeline.get("scenes") if isinstance(timeline, dict) else []
    return {
        "ok": True,
        "output_path": str(result_path),
        "scene_count": len(scenes) if isinstance(scenes, list) else 0,
        "timeline": timeline,
    }


def run_content(payload: dict[str, Any]) -> dict[str, Any]:
    from video_maker import config, generate_content, templates

    topic_name = compact_text(payload.get("topic_name"))
    brief = str(payload.get("brief") or "")
    template_key = compact_text(payload.get("template_key"))
    tavily_topic = compact_text(payload.get("tavily_topic")) or "general"
    prompt_path_raw = compact_text(payload.get("prompt_path"))
    prompt_path = Path(prompt_path_raw) if prompt_path_raw else None

    if not topic_name:
        raise RuntimeError("Missing topic_name for content generation.")
    if not template_key:
        raise RuntimeError("Missing template_key for content generation.")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("Missing DEEPSEEK_API_KEY for original content generation.")

    ORIGINAL_PRODUCTS_MIRROR_ROOT.mkdir(parents=True, exist_ok=True)
    sync_current_projects_to_original_products(ORIGINAL_PRODUCTS_MIRROR_ROOT, template_key)

    os.environ["DEFAULT_TEMPLATE"] = template_key
    os.environ["TAVILY_TOPIC"] = tavily_topic

    if CURRENT_TEMPLATES_ROOT.exists():
        templates.TEMPLATES_DIR = CURRENT_TEMPLATES_ROOT
        with contextlib.suppress(Exception):
            templates.reload_templates()

    with contextlib.suppress(Exception):
        config.reload_runtime_config()
    config.PRODUCTS_DIR = ORIGINAL_PRODUCTS_MIRROR_ROOT
    config.DEFAULT_PRODUCTS_DIR = ORIGINAL_PRODUCTS_MIRROR_ROOT
    with contextlib.suppress(Exception):
        config.PROJECT_ROOT = WORKSPACE_ROOT
    with contextlib.suppress(Exception):
        config._ACTIVE_TEMPLATE = templates.get_template(template_key)

    stages: list[str] = []

    def on_stage(stage: str) -> None:
        text = compact_text(stage)
        if text:
            stages.append(text)
            print(f"[content] {text}", file=sys.stderr)

    with contextlib.redirect_stdout(sys.stderr):
        result_path = generate_content.write_content_md(
            topic_name,
            brief,
            template_key=template_key,
            prompt_path=prompt_path,
            tavily_topic=tavily_topic,
            on_stage=on_stage,
        )

    topic_dir = result_path.parent
    return {
        "ok": True,
        "provider": "deepseek-via-original",
        "content_path": str(result_path),
        "topic_dir": str(topic_dir),
        "content": result_path.read_text(encoding="utf-8"),
        "references": load_original_references(topic_dir),
        "stages": stages,
    }


def run_video(payload: dict[str, Any]) -> dict[str, Any]:
    from video_maker import video_composer

    cover_path = Path(payload["cover_path"])
    scene_paths = [Path(str(item)) for item in (payload.get("scene_paths") or []) if compact_text(item)]
    audio_path = Path(payload["audio_path"])
    output_path = Path(payload["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subtitle_path = optional_path(payload.get("subtitle_path"))
    scene_timeline_path = optional_path(payload.get("scene_timeline_path"))
    bgm_path = optional_path(payload.get("bgm_path"))
    highlights = [compact_text(item) for item in (payload.get("highlights") or []) if compact_text(item)] or None
    dialogue_texts = [compact_text(item) for item in (payload.get("dialogue_texts") or []) if compact_text(item)] or None
    scene_prompts = [compact_text(item) for item in (payload.get("scene_prompts") or []) if compact_text(item)] or None
    disclaimer = str(payload.get("disclaimer") or "")
    outro_duration = optional_float(payload.get("outro_duration"))
    bgm_volume = optional_float(payload.get("bgm_volume"))
    podcast_volume = optional_float(payload.get("podcast_volume"))
    brand_name = compact_text(payload.get("brand_name")) or None
    force = bool(payload.get("force", True))

    with contextlib.redirect_stdout(sys.stderr):
        result_path = video_composer.compose_video(
            cover_path=cover_path,
            scene_paths=scene_paths,
            audio_path=audio_path,
            output_path=output_path,
            highlights=highlights,
            disclaimer=disclaimer,
            outro_duration=outro_duration,
            dialogue_texts=dialogue_texts,
            scene_prompts=scene_prompts,
            subtitle_path=subtitle_path if subtitle_path and subtitle_path.exists() else None,
            scene_timeline_path=scene_timeline_path if scene_timeline_path and scene_timeline_path.exists() else None,
            bgm_path=bgm_path if bgm_path and bgm_path.exists() else None,
            bgm_volume=bgm_volume,
            podcast_volume=podcast_volume,
            brand_name=brand_name,
            force=force,
        )
    return {
        "ok": True,
        "output_path": str(result_path),
        "size": result_path.stat().st_size if result_path.exists() else 0,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(json.dumps({"ok": False, "error": "usage: bridge.py <tts|asr|scene_timeline|content|video> <payload.json>"}, ensure_ascii=False))
        return 2

    command = argv[1].strip().lower()
    payload_path = Path(argv[2])
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        ensure_original_assets()
        apply_env({str(k): str(v) for k, v in (payload.get("env") or {}).items()})
        bootstrap_imports()
        warnings.simplefilter("ignore")
        if command == "tts":
            result = run_tts(payload)
        elif command == "asr":
            result = run_asr(payload)
        elif command == "scene_timeline":
            result = run_scene_timeline(payload)
        elif command == "content":
            result = run_content(payload)
        elif command == "video":
            result = run_video(payload)
        else:
            raise RuntimeError(f"unknown bridge command: {command}")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        error = {
            "ok": False,
            "error": str(exc),
            "type": type(exc).__name__,
            "traceback": traceback.format_exc(limit=6),
        }
        print(json.dumps(error, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
