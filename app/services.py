from __future__ import annotations

import asyncio
import base64
import contextlib
import html
import io
import json
import math
import os
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import wave
from collections import Counter
from pathlib import Path
from typing import Any, Callable

try:
    import numpy as np
except Exception:  # pragma: no cover - optional at runtime
    np = None

try:
    from PIL import Image, ImageFilter, ImageStat
except Exception:  # pragma: no cover - optional at runtime
    Image = None
    ImageFilter = None
    ImageStat = None

try:
    from openai import APIConnectionError, APIStatusError, OpenAI
except Exception:  # pragma: no cover - fallback when dependency is absent
    OpenAI = None

    class APIConnectionError(Exception):
        pass

    class APIStatusError(Exception):
        status_code: int | None = None


from . import storage


ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
ARK_IMAGE_MODEL_ALIASES = {
    "seedream-5.0": "doubao-seedream-5-0-260128",
    "doubao-seedream-5.0-lite": "doubao-seedream-5-0-260128",
    "doubao-seedream-5-0-260128": "doubao-seedream-5-0-260128",
    "seedream-4.5": "doubao-seedream-4.5",
    "doubao-seedream-4.5": "doubao-seedream-4.5",
}
APIYI_IMAGE_MODEL_ALIASES = {
    "gpt-image-2": "gpt-image-2-all",
    "gpt-image-2-all": "gpt-image-2-all",
}
RASTER_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
SCENE_IMAGE_SIZE = "2560x1440"
COVER_LANDSCAPE_SIZE = "2560x1440"
COVER_STORY_SIZE = "2304x1728"
COVER_PORTRAIT_SIZE = "1728x2304"
COVER_IMAGE_TARGETS = {
    "landscape": {
        "filename": "cover_landscape.png",
        "label": "横屏封面",
        "size": COVER_LANDSCAPE_SIZE,
        "kind": "landscape",
    },
    "cover_landscape": {
        "filename": "cover_landscape.png",
        "label": "横屏封面",
        "size": COVER_LANDSCAPE_SIZE,
        "kind": "landscape",
    },
    "story": {
        "filename": "cover_story.png",
        "label": "图文封面",
        "size": COVER_STORY_SIZE,
        "kind": "story",
    },
    "cover_story": {
        "filename": "cover_story.png",
        "label": "图文封面",
        "size": COVER_STORY_SIZE,
        "kind": "story",
    },
    "portrait": {
        "filename": "cover_portrait.png",
        "label": "竖屏封面",
        "size": COVER_PORTRAIT_SIZE,
        "kind": "portrait",
    },
    "cover_portrait": {
        "filename": "cover_portrait.png",
        "label": "竖屏封面",
        "size": COVER_PORTRAIT_SIZE,
        "kind": "portrait",
    },
}
TIMELINE_COVER_MS = 5000
TIMELINE_OUTRO_MS = 1500
VIDEO_OUTPUT_WIDTH = 1920
VIDEO_OUTPUT_HEIGHT = 1080
VIDEO_OUTPUT_FPS = 30
VIDEO_WORKING_WIDTH = 2560
VIDEO_WORKING_HEIGHT = 1440
VIDEO_DEFAULT_TRANSITION_SECONDS = 0.45
VIDEO_MIN_TRANSITION_SECONDS = 0.18
APIYI_IMAGE_TIMEOUT_SECONDS = 480.0
APIYI_IMAGE_RETRIES = 3
IMAGE_PROMPT_REWRITE_ATTEMPTS = 3
IMAGE_AUDIT_MIN_STDDEV = 18.0
IMAGE_AUDIT_MIN_FOREGROUND_RATIO = 0.075
IMAGE_AUDIT_MIN_COVERAGE_WIDTH = 0.42
IMAGE_AUDIT_MIN_COVERAGE_HEIGHT = 0.34
DEFAULT_IMAGE_ABSTRACTION_LEVEL = "balanced"
IMAGE_ABSTRACTION_OPTIONS = (
    {"value": "literal", "label": "贴着口播"},
    {"value": "balanced", "label": "平衡"},
    {"value": "conceptual", "label": "更抽象"},
)
IMAGE_AUDIT_TEXT_COMPONENT_DENSITY = 28.0
ORIGINAL_VIDEO_DURATION_TOLERANCE_SECONDS = 4.0
SUBTITLE_END_PADDING_SECONDS = 1.5
TARGET_SCENE_MS = 30_000
SCENE_COUNT_BUCKETS = (
    (int(3.5 * 60_000), 5, 7),
    (int(5.5 * 60_000), 8, 11),
    (int(7.5 * 60_000), 10, 14),
    (10**12, 14, 21),
)


DDG_RESULT_RE = re.compile(
    r'(?is)<a[^>]+class="[^"]*\bresult__a\b[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="[^"]*\bresult__a\b|</body>)'
)
DDG_SNIPPET_RE = re.compile(
    r'(?is)<a[^>]+class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(.*?)</a>|<div[^>]+class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(.*?)</div>'
)
HTML_TAG_RE = re.compile(r"(?is)<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
CHINESE_OR_WORD_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9._-]{1,}")
SPEAKER_PREFIX_RE = re.compile(r"^[\[\【]([^】\]]+)[\]\】]\s*(.+?)\s*$")


class ContentGenerationError(RuntimeError):
    pass


def runtime_env() -> dict[str, str]:
    env = dict(storage.DEFAULT_ENV)
    env.update(storage.parse_env())
    return env


def workspace_root() -> Path:
    return storage.APP_ROOT.parent


def tts_previews_root() -> Path:
    original = workspace_root() / "_analysis" / "awesome_app_install" / "_internal" / "web" / "static" / "tts-previews"
    if original.exists():
        return original
    fallback = storage.DATA_ROOT / "tts-previews"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def tts_preview_manifest() -> dict[str, Any]:
    manifest_path = tts_previews_root() / "manifest.json"
    payload = storage.read_json(manifest_path, {"preview_text": "", "voices": []})
    if not isinstance(payload, dict):
        return {"preview_text": "", "voices": []}
    voices = payload.get("voices")
    if not isinstance(voices, list):
        voices = []
    return {
        "preview_text": clean_text(str(payload.get("preview_text", ""))),
        "generated_at": int(payload.get("generated_at", 0) or 0),
        "voices": [item for item in voices if isinstance(item, dict)],
    }


def original_python_path() -> Path:
    return workspace_root() / "_analysis" / "py311" / "embed" / "python.exe"


def original_bridge_path() -> Path:
    return storage.APP_ROOT / "app" / "original_runtime_bridge.py"


def original_runtime_env(env: dict[str, str]) -> dict[str, str]:
    resolved = dict(env)
    if not resolved.get("VOLC_ASR_APP_KEY"):
        resolved["VOLC_ASR_APP_KEY"] = resolved.get("VOLC_TTS_APP_KEY", "")
    if not resolved.get("VOLC_ASR_ACCESS_KEY"):
        resolved["VOLC_ASR_ACCESS_KEY"] = resolved.get("VOLC_TTS_ACCESS_KEY", "")
    return resolved


def run_original_bridge(command: str, payload: dict[str, Any], env: dict[str, str], timeout: int = 420) -> dict[str, Any]:
    python_path = original_python_path()
    bridge_path = original_bridge_path()
    if not python_path.exists():
        raise RuntimeError(f"Missing Python 3.11 bridge runtime: {python_path}")
    if not bridge_path.exists():
        raise RuntimeError(f"Missing original bridge script: {bridge_path}")

    merged_payload = dict(payload)
    merged_payload["env"] = original_runtime_env(env)
    payload_file = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(merged_payload, handle, ensure_ascii=False)
            payload_file = Path(handle.name)
        result = subprocess.run(
            [str(python_path), str(bridge_path), command, str(payload_file)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(workspace_root()),
            env={
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
        )
    finally:
        if payload_file and payload_file.exists():
            payload_file.unlink(missing_ok=True)

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    parsed: dict[str, Any] | None = None
    if stdout:
        try:
            parsed = json.loads(stdout.splitlines()[-1])
        except Exception:
            parsed = None
    if result.returncode != 0:
        if parsed and isinstance(parsed, dict) and parsed.get("error"):
            raise RuntimeError(str(parsed["error"]))
        detail = stderr or stdout or f"bridge failed with exit code {result.returncode}"
        raise RuntimeError(detail)
    if not isinstance(parsed, dict):
        raise RuntimeError(stderr or "bridge returned invalid JSON")
    if not parsed.get("ok", False):
        raise RuntimeError(str(parsed.get("error") or "bridge returned failure"))
    return parsed


def clean_text(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value or "").strip()


def truncate(value: str, limit: int = 220) -> str:
    value = clean_text(value)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def strip_code_fences(text: str) -> str:
    text = (text or "").strip()
    match = re.match(r"^```(?:markdown|md|text)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def html_to_text(raw: str) -> str:
    text = HTML_TAG_RE.sub(" ", raw or "")
    text = html.unescape(text)
    return clean_text(text)


def extract_tokens(text: str) -> set[str]:
    tokens = {item.lower() for item in CHINESE_OR_WORD_RE.findall(text or "")}
    stop_words = {
        "为什么",
        "什么",
        "怎么",
        "如何",
        "关于",
        "以及",
        "今天",
        "最近",
        "最新",
        "topic",
        "brief",
        "video",
        "story",
        "content",
    }
    return {token for token in tokens if token not in stop_words}


def overlap_score(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    haystack = clean_text(text).lower()
    matched = sum(1 for token in query_tokens if token in haystack)
    return matched / max(1, len(query_tokens))


def first_heading(content: str) -> str:
    for line in (content or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def extract_section(content: str, title: str, level: int = 2) -> str:
    hashes = "#" * level
    heading_breaks = "|".join(re.escape("#" * depth) for depth in range(1, level + 1))
    pattern = re.compile(
        rf"(?ms)^{re.escape(hashes)}[ \t]+{re.escape(title)}[^\r\n]*\r?\n(.*?)(?=^(?:{heading_breaks})[ \t]+|\Z)"
    )
    match = pattern.search(content or "")
    return match.group(1).strip() if match else ""


def extract_subsection(content: str, title: str) -> str:
    pattern = re.compile(
        rf"(?ms)^###[ \t]+{re.escape(title)}[^\r\n]*\r?\n(.*?)(?=^###[ \t]+|^##[ \t]+|\Z)"
    )
    match = pattern.search(content or "")
    return match.group(1).strip() if match else ""


def bullet_field_pattern(label: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?m)^\s*[-*]\s*(?:\*\*)?\s*{re.escape(label)}\s*(?:\*\*)?\s*[：:]\s*(.+?)\s*$"
    )


def clean_bullet_value(value: str) -> str:
    cleaned = (value or "").strip()
    cleaned = re.sub(r"^\*\*\s*|\s*\*\*$", "", cleaned).strip()
    return clean_text(cleaned)


def extract_meta_field(content: str, label: str) -> str:
    meta = extract_section(content, "Meta", level=2)
    if not meta:
        return ""
    match = bullet_field_pattern(label).search(meta)
    return clean_bullet_value(match.group(1)) if match else ""


def extract_bullet_field(content: str, label: str) -> str:
    match = bullet_field_pattern(label).search(content or "")
    return clean_bullet_value(match.group(1)) if match else ""


def replace_section(content: str, title: str, body: str, level: int = 2) -> str:
    source = content or ""
    hashes = "#" * level
    heading_breaks = "|".join(re.escape("#" * depth) for depth in range(1, level + 1))
    pattern = re.compile(
        rf"(?ms)^{re.escape(hashes)}[ \t]+{re.escape(title)}[^\r\n]*\r?\n.*?(?=^(?:{heading_breaks})[ \t]+|\Z)"
    )
    replacement = f"{hashes} {title}\n\n{body.strip()}\n\n"
    if pattern.search(source):
        return pattern.sub(replacement, source, count=1)
    reference_match = re.search(r"(?m)^##[ \t]+参考资料[^\r\n]*\r?\n", source)
    if reference_match:
        head = source[: reference_match.start()].rstrip()
        tail = source[reference_match.start() :].lstrip()
        return f"{head}\n\n{replacement.rstrip()}\n\n{tail}"
    return f"{source.rstrip()}\n\n{replacement}".strip() + "\n"


COMPACT_META_LABELS = (
    "封面副标题",
    "核心观点",
    "时长",
    "推荐发布标题",
    "钩子",
    "互动钩子",
    "免责声明",
)

VERBOSE_META_LABELS = {
    "HKR判断",
    "评分等级",
    "低分处理",
    "叙事原型",
    "人格",
    "说服策略",
    "callback设计",
    "黄金前三句",
    "情绪曲线",
    "节奏策略",
    "钩子策略",
    "前3秒视觉钩子",
    "合规自检",
    "输入类型",
    "题材类型",
    "选题评分",
    "备选标题",
    "备选钩子",
    "备选导语",
}


def compact_content_meta(content: str) -> str:
    source = content or ""
    meta = extract_section(source, "Meta", level=2)
    if not meta:
        return source

    values: dict[str, str] = {}
    for raw in meta.splitlines():
        line = raw.strip()
        match = re.match(r"^[-*]\s*(?:\*\*)?\s*([^：:]+?)\s*(?:\*\*)?\s*[：:]\s*(.*?)\s*$", line)
        if not match:
            continue
        label = clean_text(match.group(1))
        value = clean_bullet_value(match.group(2))
        if label in COMPACT_META_LABELS and label not in values:
            values[label] = value

    if "核心观点" not in values:
        core = extract_bullet_field(source, "核心观点") or extract_bullet_field(source, "核心知识点")
        if core:
            values["核心观点"] = summarize_scene_text(core, 72)
    if "钩子" not in values:
        hook = extract_bullet_field(source, "钩子") or first_nonempty_dialogue_line(source)
        if hook:
            values["钩子"] = summarize_scene_text(strip_dialogue_speaker(hook), 72)
    if "互动钩子" not in values:
        dialogue = parse_dialogue_lines(source, "video")
        tail = strip_dialogue_speaker(dialogue[-1]) if dialogue else ""
        if tail and ("？" in tail or "?" in tail or "评论" in tail):
            values["互动钩子"] = summarize_scene_text(tail, 72)

    lines = []
    for label in COMPACT_META_LABELS:
        if label not in values:
            continue
        value = values.get(label, "")
        lines.append(f"- {label}: {value}".rstrip())
    if not lines:
        return source
    return replace_section(source, "Meta", "\n".join(lines), level=2)


def first_nonempty_dialogue_line(content: str) -> str:
    for line in parse_dialogue_lines(content, "video"):
        cleaned = clean_text(line)
        if cleaned:
            return cleaned
    return ""


def extract_numbered_items(block: str) -> list[str]:
    items = []
    for match in re.finditer(r"(?m)^\s*\d+\.\s+(.+?)\s*$", block or ""):
        items.append(clean_text(match.group(1)))
    return items


def extract_numbered_blocks(block: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for raw in (block or "").splitlines():
        line = raw.rstrip()
        start = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if start:
            if current:
                items.append("\n".join(current).strip())
            current = [start.group(1).strip()]
            continue
        if current:
            current.append(line.strip())
    if current:
        items.append("\n".join(current).strip())

    normalized: list[str] = []
    for item in items:
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", item)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            normalized.append(text)
    return normalized


def fallback_cover_title(topic: str) -> str:
    title = clean_text(topic)
    return title[:12] if len(title) > 12 else title


def compact_cover_title_for_prompt(title: str, topic: str = "") -> str:
    cleaned = clean_text(title) or fallback_cover_title(topic)
    cleaned = re.sub(r"[？?！!。；;：:].*$", "", cleaned).strip()
    cleaned = re.sub(r"[“”\"'《》]", "", cleaned).strip()
    if len(cleaned) <= 8:
        return cleaned
    return cleaned[:8]


def fallback_publish_title(topic: str) -> str:
    return f"{clean_text(topic)}，到底为什么这么容易被讲成爆款？"


def fallback_cover_subtitle(topic: str) -> str:
    return f"{clean_text(topic)}背后的关键逻辑"


def parse_scene_prompts(content: str, mode: str) -> list[str]:
    section = (
        extract_section(content, "图片提示词", level=2)
        or extract_section(content, "场景图提示词", level=2)
        or extract_subsection(content, "场景图")
    )
    prompts = extract_numbered_blocks(section)
    if prompts:
        return prompts

    heading_source = section or content or ""
    heading_blocks: list[str] = []
    current: list[str] = []
    in_scene_block = False
    for raw in heading_source.splitlines():
        line = raw.rstrip()
        if re.match(r"^###[ \t]+场景图\s*[\d一二三四五六七八九十]*[：:、.\-]?", line):
            if current:
                heading_blocks.append("\n".join(current).strip())
            title = re.sub(r"^###[ \t]+", "", line).strip()
            current = [title]
            in_scene_block = True
            continue
        if in_scene_block and re.match(r"^###[ \t]+", line):
            if current:
                heading_blocks.append("\n".join(current).strip())
            current = []
            in_scene_block = False
            continue
        if in_scene_block:
            current.append(line.strip())
    if current:
        heading_blocks.append("\n".join(current).strip())

    normalized_blocks: list[str] = []
    for item in heading_blocks:
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", item)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            normalized_blocks.append(text)
    if normalized_blocks:
        return normalized_blocks

    if mode == "article":
        image_count = len(re.findall(r"(?m)^\[配图\d+\]\s*$", content or ""))
        if image_count:
            return [f"围绕主题「{first_heading(content) or '本期图文'}」生成第 {idx} 张正文配图" for idx in range(1, image_count + 1)]
    return []


def strip_scene_prompt_label(prompt: str) -> str:
    return re.sub(r"^\s*场景\s*\d+\s*[：:]\s*", "", clean_text(prompt))


def scene_count_range_for_audio(audio_ms: int) -> tuple[int, int]:
    safe_audio_ms = max(0, int(audio_ms or 0))
    for upper_ms, minimum, maximum in SCENE_COUNT_BUCKETS:
        if safe_audio_ms <= upper_ms:
            return minimum, maximum
    return SCENE_COUNT_BUCKETS[-1][1], SCENE_COUNT_BUCKETS[-1][2]


def suggest_scene_count(audio_ms: int, candidate_count: int) -> dict[str, int]:
    minimum, maximum = scene_count_range_for_audio(audio_ms)
    target = max(minimum, min(maximum, round(max(1, audio_ms) / TARGET_SCENE_MS)))
    if candidate_count <= 0:
        final = target
    elif candidate_count < minimum:
        final = target
    elif candidate_count > maximum:
        final = maximum
    else:
        final = candidate_count
    return {
        "minimum": minimum,
        "maximum": maximum,
        "target": target,
        "final": max(1, final),
    }


def clamp_scene_count(value: Any, default: int = 6) -> int:
    try:
        count = int(value or default)
    except Exception:
        count = default
    return max(1, min(count, 24))


def parse_duration_text_ms(text: str) -> int:
    cleaned = clean_text(text)
    if not cleaned:
        return 0
    match = re.search(r"(\d{1,2})\s*[:：]\s*(\d{1,2})", cleaned)
    if match:
        return (int(match.group(1)) * 60 + int(match.group(2))) * 1000
    range_match = re.search(r"(\d+(?:\.\d+)?)\s*[-~～至到]\s*(\d+(?:\.\d+)?)\s*(分钟|分|秒)", cleaned)
    if range_match:
        value = (float(range_match.group(1)) + float(range_match.group(2))) / 2.0
        unit = range_match.group(3)
        return int(value * (60_000 if unit != "秒" else 1000))
    minute_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:分钟|分)", cleaned)
    second_match = re.search(r"(\d+(?:\.\d+)?)\s*秒", cleaned)
    total_ms = 0
    if minute_match:
        total_ms += int(float(minute_match.group(1)) * 60_000)
    if second_match:
        total_ms += int(float(second_match.group(1)) * 1000)
    return total_ms


def estimate_content_audio_ms(content: str, mode: str) -> int:
    duration_ms = parse_duration_text_ms(extract_meta_field(content, "时长"))
    if duration_ms:
        return duration_ms
    if mode == "article":
        return 0
    dialogue = " ".join(strip_dialogue_speaker(item) for item in parse_dialogue_lines(content, mode))
    char_count = len(re.sub(r"\s+", "", dialogue))
    if char_count:
        return max(90_000, int(char_count / 4.2 * 1000))
    body_count = len(re.sub(r"\s+", "", content or ""))
    return max(90_000, int(body_count / 4.5 * 1000)) if body_count else 0


def project_scene_count_settings(project_id: int | None) -> dict[str, Any]:
    if not project_id:
        return storage.normalize_project_settings({})
    return storage.get_project_settings(project_id)


def resolve_project_scene_count(
    project: dict[str, Any],
    content: str,
    mode: str,
    *,
    candidate_count: int = 0,
    audio_ms: int = 0,
) -> dict[str, Any]:
    project_id = int(project.get("id", 0) or 0)
    settings = project_scene_count_settings(project_id)
    count_mode = clean_text(str(settings.get("scene_count_mode") or "auto")).lower()
    if count_mode == "fixed":
        fixed_count = clamp_scene_count(settings.get("scene_count_fixed", 6))
        return {
            "mode": "fixed",
            "final": fixed_count,
            "target": fixed_count,
            "minimum": fixed_count,
            "maximum": fixed_count,
            "audio_ms": max(0, int(audio_ms or 0)),
        }
    if mode == "article":
        final = clamp_scene_count(candidate_count or 4, 4)
        return {"mode": "auto", "final": final, "target": final, "minimum": 1, "maximum": 12, "audio_ms": 0}
    estimated_ms = max(0, int(audio_ms or 0)) or estimate_content_audio_ms(content, mode)
    suggestion = suggest_scene_count(estimated_ms, candidate_count)
    return {
        "mode": "auto",
        **suggestion,
        "audio_ms": estimated_ms,
    }


def scene_group_duration_ms(group: list[dict[str, Any]]) -> int:
    if not group:
        return 0
    return max(0, int(group[-1].get("end_ms", 0) or 0) - int(group[0].get("start_ms", 0) or 0))


def rebalance_scene_groups(groups: list[list[dict[str, Any]]], scene_count: int) -> list[list[dict[str, Any]]]:
    normalized = [group for group in groups if group]
    while normalized and len(normalized) < scene_count:
        split_index = max(
            range(len(normalized)),
            key=lambda index: (len(normalized[index]), scene_group_duration_ms(normalized[index])),
        )
        group = normalized[split_index]
        if len(group) <= 1:
            break
        pivot = max(1, len(group) // 2)
        normalized[split_index : split_index + 1] = [group[:pivot], group[pivot:]]
    while len(normalized) > scene_count:
        merge_index = 0
        merge_score: tuple[int, int] | None = None
        for index in range(len(normalized) - 1):
            merged = normalized[index] + normalized[index + 1]
            score = (scene_group_duration_ms(merged), len(merged))
            if merge_score is None or score < merge_score:
                merge_score = score
                merge_index = index
        normalized[merge_index : merge_index + 2] = [normalized[merge_index] + normalized[merge_index + 1]]
    return normalized


def partition_utterances_into_scenes(utterances: list[dict[str, Any]], scene_count: int) -> list[list[dict[str, Any]]]:
    if not utterances:
        return []
    capped_count = max(1, min(scene_count, len(utterances)))
    if capped_count == 1:
        return [utterances]

    timeline_start = int(utterances[0].get("start_ms", 0) or 0)
    timeline_end = int(utterances[-1].get("end_ms", 0) or 0)
    window_ms = max(1.0, (timeline_end - timeline_start) / float(capped_count))
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    next_boundary = timeline_start + window_ms

    for index, item in enumerate(utterances):
        current.append(item)
        if len(groups) >= capped_count - 1:
            continue
        remaining_items = len(utterances) - index - 1
        remaining_groups = capped_count - len(groups) - 1
        if remaining_items <= remaining_groups:
            groups.append(current)
            current = []
            next_boundary = timeline_start + window_ms * (len(groups) + 1)
            continue
        if int(item.get("end_ms", 0) or 0) >= next_boundary:
            groups.append(current)
            current = []
            next_boundary = timeline_start + window_ms * (len(groups) + 1)

    if current:
        groups.append(current)
    return rebalance_scene_groups(groups, capped_count)


def summarize_scene_text(text: str, limit: int = 88) -> str:
    cleaned = clean_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def compact_visual_anchor_text(text: str, limit: int = 88) -> str:
    cleaned = clean_text(text)
    if len(cleaned) <= limit:
        return cleaned
    shortened = cleaned[:limit]
    for sep in ("。", "；", "，", ",", "、"):
        cut = shortened.rfind(sep)
        if cut >= max(12, limit // 2):
            return shortened[:cut].strip("，,。；、 ")
    return shortened.rstrip("，,。；、 ")


def choose_scene_prompt_index(candidate_count: int, group_index: int, group_count: int) -> int:
    if candidate_count <= 1 or group_count <= 1:
        return 0
    ratio = (group_index + 0.5) / float(group_count)
    selected = round(ratio * candidate_count - 0.5)
    return max(0, min(candidate_count - 1, selected))


def aligned_scene_prompt(
    candidate_prompts: list[str],
    group_index: int,
    group_count: int,
    group_text: str,
) -> str:
    if not candidate_prompts:
        summary = summarize_scene_text(group_text, 96)
        return summary or f"场景 {group_index + 1}"

    selected_index = choose_scene_prompt_index(len(candidate_prompts), group_index, group_count)
    base = compact_visual_image_prompt(strip_scene_prompt_label(candidate_prompts[selected_index]), limit=1200)
    focus = summarize_scene_text(group_text)
    return base or focus or f"场景 {group_index + 1}"


def timeline_scene_prompts(project_id: int) -> list[str]:
    payload = storage.read_json(storage.project_file(project_id, "audio/scene_timeline.json"), {})
    scenes = payload.get("scenes") if isinstance(payload, dict) else None
    if isinstance(scenes, list):
        prompts = [clean_text(str(item.get("prompt", ""))) for item in scenes if isinstance(item, dict)]
        prompts = [prompt for prompt in prompts if prompt]
        if prompts:
            return prompts

    plan_payload = storage.read_json(storage.project_file(project_id, "audio/scene_plan.json"), {})
    plan_scenes = plan_payload.get("scenes") if isinstance(plan_payload, dict) else None
    if isinstance(plan_scenes, list):
        plan_prompts = [
            clean_text(
                str(
                    item.get("source_prompt")
                    or item.get("visual_anchor")
                    or item.get("speech_summary")
                    or ""
                )
            )
            for item in plan_scenes
            if isinstance(item, dict)
        ]
        plan_prompts = [prompt for prompt in plan_prompts if prompt]
        if plan_prompts:
            return plan_prompts
    return []


def current_scene_prompts(
    project_id: int,
    content: str,
    mode: str,
    topic_name: str,
    prefer_timeline: bool = True,
) -> list[str]:
    def normalize_for_settings(prompts: list[str]) -> list[str]:
        project = storage.get_project(project_id)
        count_info = resolve_project_scene_count(project, content, mode, candidate_count=len(prompts))
        if count_info.get("mode") == "fixed":
            return normalize_scene_prompt_count(prompts, int(count_info.get("final", len(prompts)) or len(prompts) or 1), topic_name, mode)
        return prompts

    timeline_path = storage.project_file(project_id, "audio/scene_timeline.json")
    plan_path = storage.project_file(project_id, "audio/scene_plan.json")
    content_path = storage.project_file(project_id, "content.md")
    spec_prompts = video_spec_scene_prompts(project_id)
    if spec_prompts:
        return normalize_for_settings(spec_prompts)
    timeline_fresh = timeline_path.exists() and timeline_path.stat().st_mtime >= content_path.stat().st_mtime
    plan_fresh = plan_path.exists() and plan_path.stat().st_mtime >= content_path.stat().st_mtime
    if prefer_timeline and (timeline_fresh or plan_fresh):
        prompts = timeline_scene_prompts(project_id)
        if prompts:
            return normalize_for_settings(prompts)
    parsed = parse_scene_prompts(content, mode)
    if len(parsed) >= 2 or mode == "article":
        return normalize_for_settings(parsed or generic_scene_lines(topic_name, mode))
    try:
        project = storage.get_project(project_id)
        template_key = clean_text(project.get("template") or "")
        template = storage.get_template(template_key) if template_key else {}
        derived = build_content_scene_prompt_lines(project, template, content)
    except Exception:
        derived = []
    if len(derived) > len(parsed):
        return normalize_for_settings(derived)
    return normalize_for_settings(parsed or generic_scene_lines(topic_name, mode))


def parse_highlights(content: str) -> list[str]:
    section = extract_section(content, "重点字幕", level=2)
    return extract_numbered_items(section)


STAGE_DIRECTION_HINTS = (
    "开头",
    "前",
    "中段",
    "后段",
    "结尾",
    "钩子",
    "留住",
    "拆解",
    "转折",
    "做法",
    "互动",
    "回扣",
    "铺垫",
    "痛点",
)


def is_stage_direction_line(text: str) -> bool:
    cleaned = clean_text(text)
    if not cleaned:
        return True
    if re.fullmatch(r"[（(][^（）()]{1,60}[）)]", cleaned):
        return True
    if cleaned.startswith(("（", "(")) and any(token in cleaned for token in STAGE_DIRECTION_HINTS):
        return True
    return False


def looks_like_visual_direction(text: str) -> bool:
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) > 110:
        return False
    hints = ("镜头", "画面", "表情", "语气", "手里", "坐在", "站在", "看着", "略带", "轻松地", "认真但", "不紧张")
    hit_count = sum(1 for token in hints if token in cleaned)
    has_direct_speech = bool(re.search(r"[“”\"'？?！!]", cleaned))
    return hit_count >= 2 and not has_direct_speech


def parse_dialogue_lines(content: str, mode: str) -> list[str]:
    if mode == "article":
        body = extract_section(content, "正文", level=2)
        lines: list[str] = []
        for raw in body.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("### ") or re.fullmatch(r"\[配图\d+\]", stripped):
                continue
            if stripped.startswith("- "):
                stripped = stripped[2:].strip()
            lines.append(clean_text(stripped))
        return [line for line in lines if line]

    script = (
        extract_section(content, "对话脚本", level=2)
        or extract_section(content, "口播脚本", level=2)
        or extract_section(content, "视频脚本", level=2)
        or extract_section(content, "脚本", level=2)
    )
    lines = []
    for raw in script.splitlines():
        raw_stripped = raw.strip()
        stripped = raw_stripped
        if not stripped:
            continue
        if stripped.startswith(("### ", "## ", "# ")):
            continue
        if stripped.startswith(("- ", "* ")):
            stripped = stripped[2:].strip()
        raw_is_bold_line = bool(re.fullmatch(r"\*\*[^*]{1,80}\*\*", stripped))
        stripped = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped).strip()
        if is_stage_direction_line(stripped):
            continue
        marker_match = SPEAKER_PREFIX_RE.match(stripped)
        if marker_match and is_script_marker_speaker(marker_match.group(1), marker_match.group(2)):
            continue
        if re.fullmatch(r"[【\[][^】\]]{1,24}[】\]][：:]?", stripped):
            continue
        parsed = parse_dialogue_speaker_line(stripped, max_speaker_len=16)
        if parsed:
            speaker, spoken = parsed
            if raw_is_bold_line and len(spoken) <= 18 and not re.search(r"[，。！？；：,.!?;:]", spoken):
                continue
            if not spoken or is_stage_direction_line(spoken) or looks_like_visual_direction(spoken):
                continue
            lines.append(f"【{speaker}】{spoken}")
            continue
        lines.extend(split_script_into_caption_segments(stripped, limit=54))
    return lines


def is_script_marker_speaker(speaker: str, text: str) -> bool:
    speaker_text = clean_text(speaker)
    body_text = clean_text(text)
    if not speaker_text:
        return False
    if not any(token in speaker_text for token in ("开场", "钩子", "前30秒", "中段", "后段", "结尾", "镜头", "场景", "操作演示", "预防提醒")):
        return False
    return len(body_text) <= 28 or bool(re.search(r"\d+\s*[秒分]|阶段|^\(?\d", body_text))


def parse_dialogue_speaker_line(line: str, max_speaker_len: int = 16) -> tuple[str, str] | None:
    stripped = clean_text(line)
    if not stripped:
        return None
    match = SPEAKER_PREFIX_RE.match(stripped)
    if match:
        speaker = clean_text(match.group(1))
        text = clean_text(match.group(2))
        if is_script_marker_speaker(speaker, text):
            return None
        return (speaker, text) if speaker and text else None
    for sep in ("：", ":"):
        if sep not in stripped:
            continue
        speaker, text = stripped.split(sep, 1)
        speaker = clean_text(speaker).strip("【】[]")
        text = clean_text(text)
        if is_script_marker_speaker(speaker, text):
            return None
        if (
            speaker
            and text
            and len(speaker) <= max_speaker_len
            and not re.search(r"[，,。！？!?；;、/\\]", speaker)
        ):
            return speaker, text
        break
    return None


def split_dialogue_line(line: str) -> tuple[str, str]:
    stripped = clean_text(line)
    if not stripped:
        return "", ""
    parsed = parse_dialogue_speaker_line(stripped, max_speaker_len=16)
    if parsed:
        return parsed
    return "", stripped


def bridge_dialogue_payload(lines: list[str]) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    anonymous_index = 0
    for line in lines:
        speaker, text = split_dialogue_line(line)
        if not text:
            continue
        if not speaker:
            speaker = "speaker_a" if anonymous_index % 2 == 0 else "speaker_b"
            anonymous_index += 1
        payload.append({"speaker": speaker, "text": text})
    return payload


def plain_dialogue_text(lines: list[str]) -> str:
    parts: list[str] = []
    for line in lines:
        _, text = split_dialogue_line(line)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def content_tts_text(content: str, mode: str, dialogue_lines: list[str], scene_lines: list[str], topic_name: str) -> str:
    if mode == "article":
        body = extract_section(content, "正文", level=2)
        cleaned: list[str] = []
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("### ") or re.fullmatch(r"\[配图\d+\]", line):
                continue
            cleaned.append(clean_text(line.removeprefix("- ").strip()))
        text = "\n".join(item for item in cleaned if item)
        if text:
            return text

    for section_name in ("口播脚本", "对话脚本", "视频脚本", "脚本", "正文"):
        section = extract_section(content, section_name, level=2)
        if section:
            return section

    dialogue_text = plain_dialogue_text(dialogue_lines)
    if dialogue_text:
        return dialogue_text
    if scene_lines:
        return "\n".join(scene_lines)
    return clean_text(content) or topic_name


def utterances_to_plain_text(utterances: list[dict[str, Any]]) -> str:
    parts = [clean_text(str(item.get("text", ""))) for item in utterances]
    return "\n".join(item for item in parts if item).strip()


def srt_time_to_ms(value: str) -> int:
    text = (value or "").strip()
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", text)
    if not match:
        return 0
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + millis


def parse_srt_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    chunks = re.split(r"\r?\n\r?\n+", (text or "").strip())
    for chunk in chunks:
        lines = [line.strip("\ufeff") for line in chunk.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        time_line = lines[1] if re.search(r"-->", lines[1]) else lines[0]
        if "-->" not in time_line:
            continue
        start_raw, end_raw = [part.strip() for part in time_line.split("-->", 1)]
        body_lines = lines[2:] if time_line == lines[1] else lines[1:]
        body = clean_text(" ".join(body_lines))
        if not body:
            continue
        entries.append(
            {
                "start_ms": srt_time_to_ms(start_raw),
                "end_ms": srt_time_to_ms(end_raw),
                "text": body,
            }
        )
    return entries


def load_srt_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return parse_srt_entries(path.read_text(encoding="utf-8", errors="ignore"))


def ms_to_srt_time(value: int) -> str:
    safe = max(0, int(value or 0))
    hours, remainder = divmod(safe, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def split_caption_sentence(text: str, limit: int = 20) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    pieces = re.split(r"(?<=[，,、；：:。！？!?])", cleaned)
    segments: list[str] = []
    current = ""
    for piece in pieces:
        part = clean_text(piece)
        if not part:
            continue
        if not current:
            current = part
            continue
        if len(current) + len(part) <= limit:
            current += part
            continue
        segments.append(current)
        current = part
    if current:
        segments.append(current)

    wrapped: list[str] = []
    for segment in segments:
        if len(segment) <= limit:
            wrapped.append(segment)
            continue
        start = 0
        while start < len(segment):
            wrapped.append(segment[start : start + limit].strip())
            start += limit
    return [segment for segment in wrapped if segment]


def split_script_into_caption_segments(text: str, limit: int = 20) -> list[str]:
    segments: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = clean_text(raw_line)
        if not line:
            continue
        segments.extend(split_caption_sentence(line, limit=limit))
    return segments


def wrap_subtitle_display_text(text: str, line_limit: int = 16) -> str:
    segments = split_script_into_caption_segments(text, limit=line_limit)
    if not segments:
        return clean_text(text)
    lines: list[str] = []
    current = ""
    for segment in segments:
        if not current:
            current = segment
            continue
        if len(current) + len(segment) <= line_limit:
            current += segment
            continue
        lines.append(current)
        current = segment
    if current:
        lines.append(current)
    return "\n".join(lines)


def merge_subtitle_display_entries(
    entries: list[dict[str, Any]],
    *,
    max_chars: int = 30,
    max_duration_ms: int = 5200,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for item in entries:
        text = clean_text(str(item.get("text", "")))
        if not text:
            continue
        start_ms = int(item.get("start_ms", 0) or 0)
        end_ms = max(start_ms, int(item.get("end_ms", 0) or 0))
        candidate = {"start_ms": start_ms, "end_ms": end_ms, "text": text}
        if current is None:
            current = candidate
            continue
        combined_text = f"{current['text']}{text}"
        combined_duration = end_ms - int(current.get("start_ms", 0) or 0)
        current_ends_sentence = bool(re.search(r"[，。！？；：…,.!?;:]$", str(current.get("text", ""))))
        next_starts_fresh = bool(re.match(r'^[“"\'【（(《<\[]', text))
        if (not current_ends_sentence) and (not next_starts_fresh) and len(combined_text) <= max_chars and combined_duration <= max_duration_ms:
            current["text"] = combined_text
            current["end_ms"] = end_ms
            continue
        merged.append(current)
        current = candidate
    if current is not None:
        merged.append(current)
    return merged


def write_srt_entries(path: Path, entries: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    for index, entry in enumerate(entries, start=1):
        lines.append(str(index))
        lines.append(
            f"{ms_to_srt_time(int(entry.get('start_ms', 0) or 0))} --> {ms_to_srt_time(int(entry.get('end_ms', 0) or 0))}"
        )
        lines.append(wrap_subtitle_display_text(str(entry.get("text", ""))))
        lines.append("")
    storage.write_text(path, "\n".join(lines).strip() + "\n")


def subtitle_coverage_ratio(utterances: list[dict[str, Any]], audio_duration_ms: int) -> float:
    if not utterances or audio_duration_ms <= 0:
        return 0.0
    covered_until = max(int(item.get("end_ms", 0) or 0) for item in utterances)
    return min(1.0, covered_until / float(audio_duration_ms))


def build_script_timed_subtitles(
    script_text: str,
    audio_duration_ms: int,
    *,
    max_chars: int = 20,
    lead_in_ms: int = 250,
) -> list[dict[str, Any]]:
    segments = split_script_into_caption_segments(script_text, limit=max_chars)
    if not segments:
        return []

    start_ms = max(0, int(lead_in_ms))
    usable_ms = max(len(segments) * 900, int(audio_duration_ms) - start_ms)
    weights = [max(1, len(re.sub(r"\s+", "", segment))) for segment in segments]
    current_start = start_ms
    consumed = 0
    entries: list[dict[str, Any]] = []

    for index, segment in enumerate(segments):
        remaining_weight = sum(weights[index:]) or weights[index]
        remaining_ms = max(900, usable_ms - consumed)
        if index == len(segments) - 1:
            duration_ms = remaining_ms
        else:
            duration_ms = max(900, round(remaining_ms * (weights[index] / float(remaining_weight))))
        current_end = min(int(audio_duration_ms), current_start + duration_ms)
        if current_end <= current_start:
            current_end = current_start + 900
        entries.append({"start_ms": current_start, "end_ms": current_end, "text": segment})
        consumed += max(0, current_end - current_start)
        current_start = current_end

    if entries:
        entries[-1]["end_ms"] = max(entries[-1]["start_ms"] + 900, int(audio_duration_ms))
    return entries


def build_scene_timeline_from_utterances(utterances: list[dict[str, Any]], scene_lines: list[str]) -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    if utterances and scene_lines:
        audio_ms = int(utterances[-1].get("end_ms", 0) or 0)
        suggestion = suggest_scene_count(audio_ms, len(scene_lines))
        groups = partition_utterances_into_scenes(utterances, suggestion["final"])
        previous_end_ms = TIMELINE_COVER_MS
        for idx, group in enumerate(groups, start=1):
            group_text = " ".join(clean_text(str(item.get("text", ""))) for item in group).strip()
            prompt = aligned_scene_prompt(scene_lines, idx - 1, len(groups), group_text)
            end_ms = TIMELINE_COVER_MS + int(group[-1].get("end_ms", 0) or 0)
            scenes.append(
                {
                    "index": idx,
                    "start_ms": previous_end_ms,
                    "end_ms": max(previous_end_ms + 1, end_ms),
                    "prompt": prompt,
                    "text": group_text,
                }
            )
            previous_end_ms = scenes[-1]["end_ms"]
        audio_duration_ms = previous_end_ms + TIMELINE_OUTRO_MS
    elif utterances:
        previous_end_ms = TIMELINE_COVER_MS
        for idx, item in enumerate(utterances, start=1):
            text = clean_text(str(item.get("text", "")))
            end_ms = TIMELINE_COVER_MS + int(item.get("end_ms", 0) or 0)
            scenes.append(
                {
                    "index": idx,
                    "start_ms": previous_end_ms,
                    "end_ms": max(previous_end_ms + 1, end_ms),
                    "prompt": text,
                    "text": text,
                }
            )
            previous_end_ms = scenes[-1]["end_ms"]
        audio_duration_ms = previous_end_ms + TIMELINE_OUTRO_MS
    else:
        for idx, prompt in enumerate(scene_lines, start=1):
            scenes.append(
                {
                    "index": idx,
                    "start_ms": (idx - 1) * 4000,
                    "end_ms": idx * 4000,
                    "prompt": prompt,
                    "text": prompt,
                }
            )
        audio_duration_ms = max(TIMELINE_COVER_MS + (scenes[-1]["end_ms"] if scenes else 0), 9000)

    last_end_ms = scenes[-1]["end_ms"] if scenes else 0
    audio_body_ms = max(0, last_end_ms - TIMELINE_COVER_MS)
    suggestion = suggest_scene_count(audio_body_ms, len(scene_lines))
    return {
        "cover_duration_ms": TIMELINE_COVER_MS,
        "audio_duration_ms": max(audio_duration_ms, 9000),
        "outro_duration_ms": TIMELINE_OUTRO_MS,
        "candidate_scene_count": len(scene_lines),
        "scene_count_range": {"min": suggestion["minimum"], "max": suggestion["maximum"]},
        "target_scene_count": suggestion["target"],
        "final_scene_count": len(scenes),
        "scenes": scenes,
    }


def normalize_scene_prompt_count(scene_lines: list[str], desired_count: int, topic_name: str, mode: str) -> list[str]:
    desired = max(1, int(desired_count or 1))
    prompts = [clean_text(str(item)) for item in scene_lines if clean_text(str(item))]
    fallback_prompts = generic_scene_lines(topic_name, mode)
    fallback_index = 0
    while len(prompts) < desired:
        if fallback_index < len(fallback_prompts):
            prompts.append(fallback_prompts[fallback_index])
        else:
            prompts.append(f"围绕「{topic_name}」承接口播第 {len(prompts) + 1} 段，生成主体明确、信息有推进的场景图")
        fallback_index += 1
    return prompts[:desired]


def utterance_text_for_window(utterances: list[dict[str, Any]], start_ms: int, end_ms: int) -> str:
    parts: list[str] = []
    for item in utterances:
        item_start = int(item.get("start_ms", 0) or 0)
        item_end = int(item.get("end_ms", item_start) or item_start)
        if item_end <= start_ms or item_start >= end_ms:
            continue
        text = clean_text(str(item.get("text", "")))
        if text:
            parts.append(text)
    return " ".join(parts).strip()


def build_scene_timeline_for_scene_count(
    utterances: list[dict[str, Any]],
    scene_lines: list[str],
    scene_count: int,
    audio_duration_ms: int,
) -> dict[str, Any]:
    desired_count = max(1, int(scene_count or len(scene_lines) or 1))
    body_ms = max(
        desired_count * 900,
        int(audio_duration_ms or 0),
        max((int(item.get("end_ms", 0) or 0) for item in utterances), default=0),
    )
    scenes: list[dict[str, Any]] = []
    previous_end_ms = TIMELINE_COVER_MS
    for index in range(desired_count):
        body_start = round(index * body_ms / desired_count)
        body_end = round((index + 1) * body_ms / desired_count)
        if index == desired_count - 1:
            body_end = max(body_end, body_ms)
        group_text = utterance_text_for_window(utterances, body_start, body_end)
        prompt = aligned_scene_prompt(scene_lines, index, desired_count, group_text)
        scene_end = max(previous_end_ms + 1, TIMELINE_COVER_MS + int(body_end))
        scenes.append(
            {
                "index": index + 1,
                "start_ms": previous_end_ms,
                "end_ms": scene_end,
                "prompt": prompt,
                "text": group_text or prompt,
            }
        )
        previous_end_ms = scene_end

    minimum, maximum = scene_count_range_for_audio(body_ms)
    target = max(minimum, min(maximum, round(max(1, body_ms) / TARGET_SCENE_MS)))
    return {
        "cover_duration_ms": TIMELINE_COVER_MS,
        "audio_duration_ms": max(TIMELINE_COVER_MS + body_ms + TIMELINE_OUTRO_MS, 9000),
        "outro_duration_ms": TIMELINE_OUTRO_MS,
        "candidate_scene_count": len(scene_lines),
        "scene_count_range": {"min": minimum, "max": maximum},
        "target_scene_count": target,
        "final_scene_count": len(scenes),
        "scenes": scenes,
        "repair": {
            "forced_scene_count": desired_count,
            "generated_at": storage.now_ts(),
            "source": "subtitles.srt + current scene assets",
        },
    }


def narrative_state_for_scene(index: int, total: int) -> str:
    if total <= 1:
        return "核心观点"
    position = (index - 1) / max(1, total - 1)
    if index == 1:
        return "前三秒钩子/痛点"
    if position < 0.25:
        return "背景铺垫"
    if position < 0.5:
        return "冲突或误区"
    if position < 0.75:
        return "机制拆解/证据"
    if index == total:
        return "结论回扣/互动"
    return "应用场景"


def infer_visual_type(prompt: str, text: str) -> str:
    source = f"{prompt}\n{text}"
    if any(token in source for token in ("时间轴", "过去", "现在", "未来", "年份")) or ("三段" in source and "阶段" in source):
        return "timeline"
    if any(token in source for token in ("对比", "vs", "VS", "左栏", "右栏", "三栏")):
        return "comparison"
    life_tokens = ("真实空间", "客厅", "沙发", "饭桌", "书桌", "家人", "长辈", "爸妈", "人物", "表情", "手部", "手机", "账单", "扣费短信")
    diagram_tokens = ("架构图", "流程图", "链路图", "机制图", "关系图", "系统图", "节点图", "因果链图")
    if any(token in source for token in life_tokens) and not any(token in source for token in diagram_tokens):
        return "life_scene"
    if any(token in source for token in ("架构图", "流程图", "链路图", "机制图", "关系图", "系统图", "因果链", "连接线", "节点")):
        return "mechanism_diagram"
    if any(token in source for token in ("数据", "增长", "比例", "市场", "趋势")):
        return "data_card"
    if any(token in source for token in ("客厅", "家庭", "场景", "人物", "手机", "房间")):
        return "life_scene"
    return "editorial_collage"


def scene_motion_for_type(visual_type: str, index: int) -> str:
    motions = {
        "timeline": "slow_pan_top_to_bottom",
        "comparison": "slow_pan_left_to_right",
        "mechanism_diagram": "gentle_push_in",
        "data_card": "micro_zoom_then_hold",
        "life_scene": "slow_push_in",
        "editorial_collage": "ken_burns_subtle",
    }
    if index == 1:
        return "quick_push_in"
    return motions.get(visual_type, "ken_burns_subtle")


def scene_material_hint(visual_type: str) -> str:
    hints = {
        "timeline": "AI 图，必要时叠加后期字幕解释节点",
        "comparison": "AI 图或后期分屏卡片",
        "mechanism_diagram": "AI 图优先，复杂结构可后期叠加图标",
        "data_card": "后期图表卡片优先，AI 图只做背景",
        "life_scene": "可混合真实素材或 AI 图",
        "editorial_collage": "AI 图",
    }
    return hints.get(visual_type, "AI 图")


def scene_transition_for_index(index: int, total: int, visual_type: str) -> str:
    if index == 1:
        return "hard_cut_from_cover"
    if index == total:
        return "soft_fade_to_end"
    if visual_type in {"timeline", "mechanism_diagram"}:
        return "match_cut_or_push"
    return "crossfade_8_frames"


def build_scene_plan(project: dict[str, Any], content: str, timeline: dict[str, Any], scene_lines: list[str]) -> dict[str, Any]:
    mode = clean_text(project.get("template_mode") or "video")
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    scenes_raw = timeline.get("scenes") if isinstance(timeline, dict) else []
    scenes_raw = scenes_raw if isinstance(scenes_raw, list) else []
    summary = summarize_content(content, mode)
    total = len(scenes_raw)
    scenes: list[dict[str, Any]] = []

    for idx, item in enumerate(scenes_raw, start=1):
        if not isinstance(item, dict):
            continue
        source_prompt = clean_text(str(item.get("prompt") or ""))
        speech_text = clean_text(str(item.get("text") or ""))
        if not source_prompt and idx <= len(scene_lines):
            source_prompt = clean_text(scene_lines[idx - 1])
        visual_type = infer_visual_type(source_prompt, speech_text)
        visual_anchor = composer_scene_prompt(source_prompt or speech_text)
        prompt_basis = visual_anchor or source_prompt or speech_text
        speech_focus = summarize_scene_text(speech_text or source_prompt, 84)
        if speech_focus and speech_focus not in prompt_basis:
            prompt_basis = "，".join(item for item in (prompt_basis, speech_focus) if clean_text(item))
        image_prompt = optimize_visual_generation_prompt(prompt_basis, template, "scene")
        start_ms = int(item.get("start_ms", 0) or 0)
        end_ms = int(item.get("end_ms", start_ms) or start_ms)
        scenes.append(
            {
                "index": idx,
                "start_ms": start_ms,
                "end_ms": max(start_ms + 1, end_ms),
                "duration_ms": max(1, end_ms - start_ms),
                "source_prompt": source_prompt or speech_text or visual_anchor,
                "narrative_state": narrative_state_for_scene(idx, total),
                "speech_summary": summarize_scene_text(speech_text or source_prompt, 80),
                "visual_type": visual_type,
                "material_style": classify_material_style(source_prompt or speech_text or visual_anchor, template, "scene"),
                "visual_anchor": visual_anchor,
                "image_prompt": image_prompt,
                "motion": scene_motion_for_type(visual_type, idx),
                "transition": scene_transition_for_index(idx, total, visual_type),
                "material_hint": scene_material_hint(visual_type),
                "safe_text_policy": "场景图可保留 1-3 个清晰短标签；字幕、免责声明和长段正文由后期叠加层处理。",
            }
        )

    return {
        "generated_at": storage.now_ts(),
        "topic": clean_text(project.get("topic_name") or ""),
        "title": summary.get("publish_title") or summary.get("video_title") or clean_text(project.get("topic_name") or ""),
        "scene_count": len(scenes),
        "timeline_source": "audio/scene_timeline.json",
        "cover_duration_ms": timeline.get("cover_duration_ms", TIMELINE_COVER_MS) if isinstance(timeline, dict) else TIMELINE_COVER_MS,
        "outro_duration_ms": timeline.get("outro_duration_ms", TIMELINE_OUTRO_MS) if isinstance(timeline, dict) else TIMELINE_OUTRO_MS,
        "workflow_notes": [
            "先由脚本和字幕对齐得到时间轴。",
            "每镜使用叙事状态约束画面，不让图片 prompt 承担文字说明。",
            "画面中文字、标题和重点字幕留给后期成片层叠加。",
        ],
        "scenes": scenes,
    }


def write_scene_plan(project_id: int, project: dict[str, Any], content: str, timeline: dict[str, Any], scene_lines: list[str]) -> dict[str, Any]:
    plan = build_scene_plan(project, content, timeline, scene_lines)
    storage.write_json(storage.project_file(project_id, "audio/scene_plan.json"), plan)
    return plan


def _spec_field(content: str, labels: list[str]) -> str:
    for label in labels:
        value = extract_meta_field(content, label) or extract_bullet_field(content, label)
        if value:
            return clean_text(value)
    return ""


def _video_spec_checks(spec: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    basics = spec.get("basics") if isinstance(spec.get("basics"), dict) else {}
    scenes = spec.get("scenes") if isinstance(spec.get("scenes"), list) else []

    def add(level: str, where: str, issue: str, fix: str) -> None:
        checks.append({"level": level, "where": where, "issue": issue, "fix": fix})

    if not basics.get("audience"):
        add("warn", "受众", "没有识别到明确目标受众。", "在 brief 或 content.md 里补一句“目标受众：谁在什么场景看”。")
    if not basics.get("core_message"):
        add("warn", "核心信息", "没有识别到 12-20 字左右的核心记忆点。", "补一个“核心观点/核心信息”，后续封面和场景图都围绕它。")
    if not basics.get("hook"):
        add("risk", "开头钩子", "没有识别到明确钩子。", "补一句具体、反常识、有动作感的开头，不要只写泛泛结论。")
    if len(scenes) < 3 and basics.get("mode") != "article":
        add("risk", "分镜", "可用场景少于 3 个。", "先重建图片提示词或补充口播段落，再进入生图。")

    prompt_texts = [clean_text(str(item.get("image_prompt") or "")) for item in scenes if isinstance(item, dict)]
    normalized_heads = [re.sub(r"第\s*\d+\s*张|^\d+[.、]\s*", "", text[:90]) for text in prompt_texts]
    if len(normalized_heads) >= 3 and len(set(normalized_heads)) <= max(1, len(normalized_heads) // 2):
        add("warn", "场景差异", "多张场景图开头描述过于相似，可能又会生成同一类画面。", "逐镜绑定不同台词锚点、人物动作、空间或物件。")

    forbidden_residue = ("视频扣费", "纸样", "旧纸片", "复古档案", "牛皮纸", "手账")
    residue_hits = sorted({token for token in forbidden_residue if any(token in text for text in prompt_texts)})
    if residue_hits:
        add("warn", "提示词残留", f"发现疑似上期或固定风格残留：{', '.join(residue_hits)}。", "清理频道模板里的固定画面词，只保留频道气质。")
    return checks


def build_video_spec(project_id: int, content: str | None = None) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    content_text = content if content is not None else storage.get_content(project_id)
    if not clean_text(content_text):
        raise ValueError("当前项目还没有 content.md，无法生成编导规格。")

    summary = summarize_content(content_text, mode)
    topic = clean_text(project.get("topic_name") or summary.get("video_title") or first_heading(content_text) or "本期主题")
    platform = infer_platform_profile(project, template)
    style_source = "\n".join(
        filter(
            None,
            [
                topic,
                _spec_field(content_text, ["目标受众", "受众", "人群"]),
                _spec_field(content_text, ["核心观点", "核心信息", "核心知识点"]),
                _spec_field(content_text, ["钩子", "前3秒钩子", "前 3 秒钩子"]),
                content_text[:1600],
            ],
        )
    )
    style = classify_material_style(style_source, template, "scene")
    domain = classify_visual_prompt_domain(style_source, "scene")
    count_info = resolve_project_scene_count(project, content_text, mode)
    desired_count = clamp_scene_count(count_info.get("final", 0), 4 if mode == "article" else 6)
    beats = derive_content_scene_beats(content_text, mode, topic, style=style, source=style_source, desired_count=desired_count)
    dialogue_anchors = select_dialogue_scene_anchors(content_text, mode, max(len(beats), 1), limit=100)
    audience = _spec_field(content_text, ["目标受众", "目标人群", "受众", "人群"])
    if not audience and (
        "爸妈" in style_source
        or "爸、妈" in style_source
        or "爸爸妈妈" in style_source
        or "长辈" in style_source
        or "老人" in style_source
        or "中老年" in style_source
        or "爸妈" in clean_text(template.get("name") or template_key)
    ):
        audience = "45-70 岁中老年用户，以及会转发给父母的子女。"
    hook = _spec_field(content_text, ["钩子", "前3秒钩子", "前 3 秒钩子", "开头钩子"])
    if not hook and dialogue_anchors:
        hook = summarize_scene_text(dialogue_anchors[0], 110)
    core_message = _spec_field(content_text, ["核心观点", "核心信息", "核心知识点"])
    if not core_message:
        core_message = summarize_scene_text(summary.get("cover_title") or summary.get("publish_title") or topic, 40)
    scene_lines = build_content_scene_prompt_lines(project, template, content_text)
    scene_count = max(len(beats), len(scene_lines), 1)
    scenes: list[dict[str, Any]] = []
    for idx in range(1, scene_count + 1):
        beat = beats[min(idx - 1, len(beats) - 1)] if beats else f"{topic} 场景 {idx}"
        dialogue = dialogue_anchors[min(idx - 1, len(dialogue_anchors) - 1)] if dialogue_anchors else beat
        source_prompt = scene_lines[min(idx - 1, len(scene_lines) - 1)] if scene_lines else beat
        visual_type = infer_visual_type(source_prompt, dialogue)
        narrative = narrative_state_for_scene(idx, scene_count)
        scenes.append(
            {
                "index": idx,
                "narrative_state": narrative,
                "dialogue_anchor": dialogue,
                "scene_beat": beat,
                "information_load": summarize_scene_text(dialogue or beat, 70),
                "visual_type": visual_type,
                "material_style": classify_material_style(f"{source_prompt}\n{dialogue}", template, "scene"),
                "motion": scene_motion_for_type(visual_type, idx),
                "transition": scene_transition_for_index(idx, scene_count, visual_type),
                "text_policy": "场景图默认不渲染可读文字；口播里的服务名、金额、按钮名和平台名只作为语义锚点。",
                "safe_area": "主体不压底部字幕区，手机屏幕和人物动作留在画面中上区域。",
                "image_prompt": source_prompt,
            }
        )

    covers = {
        "landscape": {
            "label": "横屏封面",
            "size": COVER_LANDSCAPE_SIZE,
            "prompt": build_content_cover_prompt(project, template, content_text, "landscape"),
        },
        "story": {
            "label": "图文封面",
            "size": COVER_STORY_SIZE,
            "prompt": build_content_cover_prompt(project, template, content_text, "story"),
        },
        "portrait": {
            "label": "竖屏封面",
            "size": COVER_PORTRAIT_SIZE,
            "prompt": build_content_cover_prompt(project, template, content_text, "portrait"),
        },
    }
    if mode == "article":
        covers = {"landscape": covers["landscape"]}

    spec: dict[str, Any] = {
        "schema": "short-video-studio.video-spec.v1",
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "template": {
            "key": template_key,
            "name": template.get("name") or template_key,
            "brand_name": template.get("brand_name") or template.get("name") or template_key,
            "mode": mode,
            "cover_style": template.get("cover_style") or "default",
        },
        "basics": {
            "topic": topic,
            "mode": mode,
            "platform": platform,
            "duration": summary.get("duration") or _spec_field(content_text, ["时长"]),
            "audience": audience,
            "core_message": core_message,
            "hook": hook,
            "publish_title": summary.get("publish_title") or "",
            "cover_title": summary.get("cover_title") or "",
            "cover_subtitle": summary.get("cover_subtitle") or "",
        },
        "visual_rules": {
            "style": style,
            "domain": domain,
            "channel_binding": channel_visual_style_hint(template, "scene"),
            "scene_text_policy": "场景图尽量无字，文字信息交给字幕和后期叠加。",
            "cover_text_policy": "只有封面主标题、副标题和频道角标可以清晰可读。",
        },
        "scene_count": len(scenes),
        "scene_count_policy": count_info,
        "scenes": scenes,
        "covers": covers,
        "workflow_notes": [
            "先把视频想清楚，再生成图片；图片提示词必须服务当前台词锚点。",
            "频道只提供统一气质，不能把某一期的具体物件、页面或流程写死到所有主题。",
            "每个镜头必须有信息载荷；没有信息载荷的镜头应删除或合并。",
        ],
    }
    spec["checks"] = _video_spec_checks(spec)
    return spec


def save_video_spec(project_id: int, content: str | None = None) -> dict[str, Any]:
    spec = build_video_spec(project_id, content)
    storage.write_json(storage.project_file(project_id, "video_spec.json"), spec)
    return spec


def load_fresh_video_spec(project_id: int) -> dict[str, Any]:
    spec_path = storage.project_file(project_id, "video_spec.json")
    content_path = storage.project_file(project_id, "content.md")
    if not spec_path.exists():
        return {}
    if content_path.exists() and spec_path.stat().st_mtime + 0.5 < content_path.stat().st_mtime:
        return {}
    payload = storage.read_json(spec_path, {})
    return payload if isinstance(payload, dict) else {}


def video_spec_scene_prompts(project_id: int) -> list[str]:
    payload = load_fresh_video_spec(project_id)
    scenes = payload.get("scenes") if isinstance(payload, dict) else None
    if not isinstance(scenes, list):
        return []
    prompts = [
        clean_text(str(item.get("image_prompt") or item.get("scene_beat") or item.get("dialogue_anchor") or ""))
        for item in scenes
        if isinstance(item, dict)
    ]
    return [prompt for prompt in prompts if prompt]


def video_spec_cover_prompt(project_id: int, kind: str) -> str:
    payload = load_fresh_video_spec(project_id)
    covers = payload.get("covers") if isinstance(payload, dict) else None
    if not isinstance(covers, dict):
        return ""
    cover = covers.get(kind)
    if not isinstance(cover, dict):
        cover = covers.get(str(normalize_cover_target(kind).get("kind") or kind)) if kind in COVER_IMAGE_TARGETS else None
    return clean_text(str(cover.get("prompt") or "")) if isinstance(cover, dict) else ""


def transcribe_audio_to_text(audio_path: Path) -> str:
    env = runtime_env()
    tmp_srt = storage.CONFIG_ROOT / f"brief-import-{storage.now_ms()}.srt"
    try:
        run_original_bridge(
            "asr",
            {
                "audio_path": str(audio_path),
                "srt_output": str(tmp_srt),
                "dialogue_lines": [],
            },
            env,
            timeout=300,
        )
        utterances = load_srt_entries(tmp_srt)
        text = utterances_to_plain_text(utterances)
        if text:
            return text
        if tmp_srt.exists():
            return clean_text(tmp_srt.read_text(encoding="utf-8", errors="ignore"))
        return ""
    finally:
        tmp_srt.unlink(missing_ok=True)


def env_flag(value: str | bool | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def resolve_ark_image_model(env: dict[str, str]) -> str:
    raw = (env.get("ARK_IMAGE_MODEL", "") or "").strip()
    if not raw:
        return "doubao-seedream-5-0-260128"
    return ARK_IMAGE_MODEL_ALIASES.get(raw, raw)


def resolve_apiyi_image_model(env: dict[str, str]) -> str:
    raw = (env.get("APIYI_IMAGE_MODEL", "") or "").strip()
    if not raw:
        return "gpt-image-2-all"
    return APIYI_IMAGE_MODEL_ALIASES.get(raw, raw)


def resolve_third_party_image_model(env: dict[str, str]) -> str:
    raw = (env.get("THIRD_PARTY_IMAGE_MODEL", "") or "").strip()
    if not raw:
        return "gpt-image-2-all"
    return APIYI_IMAGE_MODEL_ALIASES.get(raw, raw)


def normalize_openai_compatible_base_url(value: str) -> str:
    text = clean_text(value).rstrip("/")
    if not text:
        return ""
    lowered = text.lower()
    suffixes = (
        "/v1/images/generations",
        "/images/generations",
        "/v1/chat/completions",
        "/chat/completions",
        "/v1/responses",
        "/responses",
        "/v1/models",
        "/models",
    )
    for suffix in suffixes:
        if lowered.endswith(suffix):
            text = text[: -len(suffix)]
            lowered = text.lower()
            break
    if not lowered.endswith("/v1"):
        text = f"{text}/v1"
    return text


def normalize_openai_compatible_image_size(size: str) -> str:
    match = re.fullmatch(r"(\d+)x(\d+)", (size or "").strip())
    if not match:
        return "1024x1024"
    width, height = (int(match.group(1)), int(match.group(2)))
    if width > height:
        return "1536x1024"
    if width < height:
        return "1024x1536"
    return "1024x1024"


def apiyi_image_timeout(env: dict[str, str]) -> float:
    value = clean_text(env.get("APIYI_IMAGE_TIMEOUT_SECONDS") or env.get("IMAGE_GENERATION_TIMEOUT_SECONDS") or "")
    if not value:
        return APIYI_IMAGE_TIMEOUT_SECONDS
    try:
        return max(300.0, min(float(value), 1800.0))
    except ValueError:
        return APIYI_IMAGE_TIMEOUT_SECONDS


def third_party_image_timeout(env: dict[str, str]) -> float:
    value = clean_text(
        env.get("THIRD_PARTY_IMAGE_TIMEOUT_SECONDS")
        or env.get("IMAGE_GENERATION_TIMEOUT_SECONDS")
        or ""
    )
    if not value:
        return APIYI_IMAGE_TIMEOUT_SECONDS
    try:
        return max(300.0, min(float(value), 1800.0))
    except ValueError:
        return APIYI_IMAGE_TIMEOUT_SECONDS


def apiyi_image_retries(env: dict[str, str]) -> int:
    value = clean_text(env.get("APIYI_IMAGE_RETRIES") or "")
    if not value:
        return APIYI_IMAGE_RETRIES
    try:
        return max(1, min(int(value), 8))
    except ValueError:
        return APIYI_IMAGE_RETRIES


def third_party_image_retries(env: dict[str, str]) -> int:
    value = clean_text(env.get("THIRD_PARTY_IMAGE_RETRIES") or "")
    if not value:
        return APIYI_IMAGE_RETRIES
    try:
        return max(1, min(int(value), 8))
    except ValueError:
        return APIYI_IMAGE_RETRIES


def chatgpt_image_wait_seconds(env: dict[str, str]) -> float:
    value = clean_text(env.get("CHATGPT_IMAGE_WAIT_SECONDS") or "")
    if not value:
        return 900.0
    try:
        return max(60.0, min(float(value), 7200.0))
    except ValueError:
        return 900.0


def build_apiyi_size_hint(size: str) -> str:
    match = re.fullmatch(r"(\d+)x(\d+)", (size or "").strip())
    if not match:
        return ""
    width, height = (int(match.group(1)), int(match.group(2)))
    if width == height:
        return f"{width}x{height} 方形"
    divisor = math.gcd(width, height) or 1
    ratio = f"{width // divisor}:{height // divisor}"
    orientation = "横版" if width > height else "竖版"
    return f"{orientation} {ratio}"


def compact_visual_image_prompt(prompt: str, limit: int = 900) -> str:
    text = normalize_image_prompt(prompt)
    if not text:
        return text
    for marker in ("补充镜头：", "补充镜头:", "本段口播重点：", "本段口播重点:", "口播重点：", "口播重点:"):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
            break
    blocks = [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]
    text = "\n\n".join(blocks[:2]).strip() if blocks else text
    if len(text) <= limit:
        return text
    shortened = text[:limit]
    last_break = max(shortened.rfind("。"), shortened.rfind("\n"), shortened.rfind("；"), shortened.rfind(","), shortened.rfind("，"))
    if last_break > limit // 2:
        shortened = shortened[: last_break + 1]
    return shortened.strip()


def template_brand_marker(template: dict[str, Any]) -> str:
    brand = clean_text(template.get("brand_name") or template.get("name") or template.get("key") or "")
    if brand:
        return f"左上角保留清晰频道角标「{brand}」，作为个人 IP 识别"
    return "左上角保留一个很小的频道识别角标"


def template_footer_marker(template: dict[str, Any]) -> str:
    del template
    return "底部不要脚注小字，只保留干净环境细节或细线装饰"


def split_prompt_clauses(text: str) -> list[str]:
    normalized = normalize_image_prompt(text)
    if not normalized:
        return []
    parts = re.split(r"[。；]\s*", normalized)
    return [part.strip(" ，,") for part in parts if part.strip(" ，,")]


SCENE_STAGE_VISUAL_CLAUSES = {
    "前三秒钩子/痛点": "第一眼先给出最抓人的痛点瞬间，人物表情、手部动作或关键物件正在发生",
    "背景铺垫": "让背景关系一眼可懂，但画面里必须已经有情绪、动作或距离感",
    "冲突或误区": "把冲突双方、错误动作或误判瞬间放进同一帧里，别做平静说明图",
    "机制拆解/证据": "把关键证据、触发动作或因果链拍清楚，像正在发生的现场瞬间",
    "应用场景": "把观点落进真实生活瞬间，让人物正在做、正在看、正在反应",
    "结论回扣/互动": "收在一个态度鲜明的回看瞬间，让人想继续评论或转给家人",
}

PROMPT_DIALOGUE_PREFIXES = (
    "这张图必须对应这句口播",
    "这张图优先对应这句口播",
    "对应口播",
    "封面优先对应开头这句口播",
    "封面优先对应这个主题锚点",
    "开头口播锚点",
)

PROMPT_SCAFFOLD_STARTS = (
    "根据 brief 和台词选择人物",
    "根据本期主题选择人物",
    "每张场景图只服务对应段落",
    "每张图只服务当前对应口播段落",
    "主视觉优先从本张对应口播里提到的人物关系、动作、空间和关键物件里选一个最能承载本期主题的瞬间",
    "主视觉优先让",
    "主视觉优先是",
    "不固定成",
    "主体跟本期素材变化",
    "保留后期字幕空间",
    "可在画面内加入 1-3 个清晰短标签或警示词",
    "不要生成长段正文",
    "主体明确",
)

PROMPT_SCAFFOLD_CONTAINS = (
    "频道只决定",
    "题材跟着本期主题和这句口播走",
    "不挪用别的主题流程或物件",
    "不把其他主题的固定流程和固定道具硬套进来",
    "导演提示",
    "后期叠加层处理",
)


def extract_prompt_dialogue_hint(text: str, limit: int = 60) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    for prefix in PROMPT_DIALOGUE_PREFIXES:
        if prefix not in cleaned:
            continue
        segment = cleaned.split(prefix, 1)[1].strip(" ：:，。")
        for stop in (
            "构图",
            "根据 brief",
            "具体画面",
            "镜头变化",
            "叙事阶段",
            "频道视觉基调",
            "频道气质",
            "主视觉",
            "画面重点是",
            "主体明确",
            "保留后期字幕空间",
            "可在画面内加入",
            "不要生成长段正文",
            "频道只决定",
            "题材跟着本期主题",
        ):
            if stop in segment:
                segment = segment.split(stop, 1)[0].strip(" ，。")
        return compact_visual_anchor_text(segment, limit)
    return ""


def extract_prompt_dialogue_hint_full(text: str) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    for prefix in PROMPT_DIALOGUE_PREFIXES:
        if prefix not in cleaned:
            continue
        segment = cleaned.split(prefix, 1)[1].strip(" ：:，。")
        for stop in (
            "根据 brief",
            "具体画面",
            "镜头变化",
            "叙事阶段",
            "频道视觉基调",
            "频道气质",
            "主视觉",
            "画面重点是",
            "主体明确",
            "保留后期字幕空间",
            "可在画面内加入",
            "不要生成长段正文",
            "频道只决定",
            "题材跟着本期主题",
        ):
            if stop in segment:
                segment = segment.split(stop, 1)[0].strip(" ，。")
        return clean_text(segment)
    return ""


def split_dense_prompt_clauses(text: str) -> list[str]:
    result: list[str] = []
    for part in split_prompt_clauses(text):
        normalized = clean_text(part)
        if not normalized:
            continue
        if any(prefix in normalized for prefix in PROMPT_DIALOGUE_PREFIXES):
            for prefix in PROMPT_DIALOGUE_PREFIXES:
                if prefix not in normalized:
                    continue
                before, after = normalized.split(prefix, 1)
                if clean_text(before):
                    result.append(clean_text(before))
                result.append(f"{prefix}：{clean_text(after)}")
                normalized = ""
                break
            if not normalized:
                continue
        comma_count = normalized.count("，") + normalized.count(",")
        if len(normalized) > 72 and comma_count >= 4:
            for sub in re.split(r"[，,、]\s*", normalized):
                cleaned = clean_text(sub)
                if len(cleaned) >= 5:
                    result.append(cleaned)
            continue
        result.append(normalized)
    return [clean_text(item) for item in result if clean_text(item)]


def rewrite_scene_stage_clause(text: str) -> str:
    normalized = clean_text(text)
    for label, clause in SCENE_STAGE_VISUAL_CLAUSES.items():
        if label in normalized:
            return clause
    return ""


def strip_prompt_scaffolding(text: str) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    stage_clause = rewrite_scene_stage_clause(cleaned)
    if stage_clause:
        return stage_clause
    for prefix in PROMPT_DIALOGUE_PREFIXES:
        if prefix in cleaned and not cleaned.startswith(prefix):
            before = clean_text(cleaned.split(prefix, 1)[0])
            if before:
                cleaned = before
            else:
                return extract_prompt_dialogue_hint(cleaned, 56)
    for prefix in PROMPT_DIALOGUE_PREFIXES:
        if cleaned.startswith(prefix):
            return extract_prompt_dialogue_hint(cleaned, 56)
    if cleaned.startswith("画面重点是"):
        cleaned = cleaned.split("画面重点是", 1)[1].strip("：:，, ")
        return summarize_scene_text(cleaned, 60)
    if any(marker in cleaned for marker in PROMPT_SCAFFOLD_CONTAINS):
        return ""
    for prefix in PROMPT_SCAFFOLD_STARTS:
        if cleaned.startswith(prefix):
            return ""
    cleaned = re.sub(r"^16:9\s*横屏[，,]?", "", cleaned)
    cleaned = re.sub(r"^4:3\s*横屏封面[，,]?", "", cleaned)
    cleaned = re.sub(r"^3:4\s*竖屏封面[，,]?", "", cleaned)
    cleaned = re.sub(r"^第\s*\d+\s*张场景图[，,]?", "", cleaned)
    cleaned = re.sub(r"^围绕[「“].+?[」”]展开[，,]?", "", cleaned)
    cleaned = re.sub(r"^围绕[「“].+?[」”]做短视频封面[，,]?", "", cleaned)
    cleaned = re.sub(r"[，,]?人物、生活物件和关系冲突必须根据本期主题选择[，,]?", "", cleaned)
    cleaned = re.sub(r"[，,]?不固定成[^，。]*", "", cleaned)
    cleaned = re.sub(r"^可在画面内加入\s*1-3\s*个清晰短标签或警示词.*$", "", cleaned)
    cleaned = re.sub(r"^不要生成长段正文.*$", "", cleaned)
    cleaned = re.sub(r"^保留后期字幕空间.*$", "", cleaned)
    cleaned = re.sub(r"^主体明确.*$", "", cleaned)
    return clean_text(cleaned).strip("，,")


def strip_forbidden_visual_text(text: str) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    cleaned = re.sub(
        r"左上角[^。；]*(?:双人讲故事|单人讲故事|单人图文|品牌位|栏目名|刊名)[^。；]*",
        "左上角只保留抽象图形角标",
        cleaned,
    )
    cleaned = re.sub(
        r"底部[^。；]*(?:内容基于公开资料整理|仅作知识科普|免责声明|免责|脚注)[^。；]*",
        "底部保持干净",
        cleaned,
    )
    cleaned = re.sub(r"合规自检[:：]?.*$", "", cleaned)
    for marker in ("双人讲故事", "单人讲故事", "单人图文", "内容基于公开资料整理", "仅作知识科普", "免责声明", "合规自检", "品牌位", "刊名"):
        cleaned = cleaned.replace(marker, "")
    cleaned = re.sub(r"\s*[，,]\s*(?:\)|）)", "", cleaned)
    cleaned = cleaned.replace("+底部", "，底部")
    cleaned = re.sub(r"[\u4e00-\u9fffA-Za-z0-9_-]*logo(?:剪影|图形|标志)?", "抽象品牌符号", cleaned, flags=re.IGNORECASE)
    return clean_text(cleaned)


def abstract_textual_clause(clause: str, purpose: str) -> str:
    source_text = clean_text(clause) if purpose == "cover" else strip_forbidden_visual_text(clause)
    text = strip_prompt_scaffolding(neutralize_materialized_style(source_text))
    if not text:
        return ""
    annotation_strips = (
        (r"[，,](?:旁边|上方|下方|卡片下方|节点旁|箭头旁|相框下方|人物旁边|人旁边)[^。；，]*(?:写|标注|标出|显示|一行小字)[^。；，]*", ""),
        (r"(?:每格|每栏|每个节点|每一格|三栏上方各有)[^。；]*(?:依次写|写|标注|标出|显示)[^。；]*", "三段对照节点"),
        (r"[（(][^()（）]{0,40}(?:墨黑字|关键字|中性灰|原文写出|墨黑线)[^()（）]{0,60}[）)]", ""),
    )
    for pattern, replacement in annotation_strips:
        text = re.sub(pattern, replacement, text)
    text = clean_text(text)
    if not text:
        return ""
    if "1+2+N" in text:
        return "一张结构关系图，一台中心主机连接两层控制链路和多个设备节点，层级清晰，图标化表达"
    if "时间轴" in text and re.search(r"\d{4}", text):
        return "一条三节点时间轴，表现早期探索、中期转折、近期成熟三个阶段，用图标、箭头和印章区分阶段，不出现具体年份文字"
    has_quoted_text = bool(re.search(r"[「“\"].+?[」”\"]", text))
    mentions_writing = any(token in text for token in ("写", "标题", "副标题", "小字", "大字", "铅笔字", "文字", "字样", "便签", "标签", "贴纸", "印章", "邮票", "卷轴", "标注", "标出", "一行", "显示", "按钮"))
    if not (has_quoted_text or mentions_writing):
        return text
    if has_quoted_text and not mentions_writing:
        return text
    if purpose == "cover":
        return text
    if any(token in text for token in ("标题", "副标题", "主标题", "大字")):
        if purpose == "cover":
            return "保留一块干净标题安全区作为后期叠字位置，但图内不要直接渲染任何可读标题"
        return "保留一块无字视觉焦点区域，只呈现图形、色块或物体关系，不出现可读标题"
    cleaned = text
    cleaned = re.sub(r"[「“\"].+?[」”\"]", "抽象不可读图形标记", cleaned)
    cleaned = re.sub(r"\b\d{4}\s*年?", "阶段节点", cleaned)
    cleaned = re.sub(r"\b\d+\s*[:：]\s*\d+\b", "结构节点", cleaned)
    cleaned = re.sub(r"(小字|铅笔字|手写黑体|字样|文字|一行|标注|标出|显示)", "不可读图形", cleaned)
    cleaned = cleaned.replace("不可读图形抽象不可读图形标记", "用无字图形符号表示")
    cleaned = cleaned.replace("可读不可读图形", "可读文字")
    cleaned = re.sub(r"(按钮)", "无字按钮图形", cleaned)
    cleaned = clean_text(cleaned)
    if not cleaned:
        return "所有说明信息只用无字图形、短横线、图标和色块表示，不出现可读中文、英文或数字"
    if any(token in clause for token in ("印章", "便签", "标签", "贴纸", "邮票", "卷轴", "纸胶带", "纸片")):
        cleaned += "，所有标记都只保留为无字图形符号"
    cleaned = cleaned.replace("呈现抽象不可读笔迹", "用无字图形符号表示")
    cleaned = cleaned.replace("抽象不可读图形标记", "无字图标")
    cleaned = cleaned.replace("抽象不可读笔迹", "无字图标")
    cleaned = cleaned.replace("不可读图形字", "无字图形")
    cleaned = cleaned.replace("警示红红色警示符号", "警示红符号")
    cleaned = cleaned.replace("旧抽象角标", "抽象角标")
    cleaned = re.sub(r"(不可读图形){2,}", "无字图标", cleaned)
    cleaned = re.sub(r"(无字图标)(?:用无字图形符号表示)+", r"\1", cleaned)
    cleaned = clean_text(cleaned)
    cleaned = collapse_placeholder_noise(cleaned)
    if placeholder_noise_score(cleaned) >= 2 and not has_primary_visual_object(cleaned):
        simplified = simplify_auxiliary_clause(text, purpose)
        return neutralize_materialized_style(clean_text(simplified))
    return neutralize_materialized_style(cleaned)


def dedupe_clauses(items: list[str]) -> list[str]:
    seen: set[str] = set()
    signatures: list[str] = []
    result: list[str] = []
    for item in items:
        normalized = clean_text(item)
        if not normalized or normalized in seen:
            continue
        signature = re.sub(r"[\s，,。；：:、“”‘’\"'（）()\[\]【】《》<>!?！？—\\/_-]+", "", normalized)
        if not signature:
            continue
        if any(signature == existing for existing in signatures):
            continue
        if len(signature) >= 10 and any(signature in existing or existing in signature for existing in signatures):
            continue
        seen.add(normalized)
        signatures.append(signature)
        result.append(normalized)
    return result


GENERIC_VISUAL_META_TOKENS = (
    "短视频分镜",
    "主体完整",
    "信息密度高",
    "画面铺满全幅",
    "场景图优先表达",
    "按主体、动作、环境、构图、光线、材质组织画面",
    "所有说明区域都只用",
    "不渲染任何可读",
    "不要出现左上角",
    "根据文案素材决定视觉风格",
    "采用领域路由生成提示词",
    "画面要像短视频导演分镜",
    "抓眼的短视频主视觉",
    "风格必须服从当前文案素材",
    "主体尽量占画面",
    "优先用一个主角物体",
    "保留 1 到 3 个最关键的视觉锚点",
)


CONCRETE_VISUAL_TOKENS = (
    "左侧", "右侧", "中间", "上方", "下方", "前景", "背景", "客厅", "卧室", "书房", "沙发", "墙",
    "人物", "手", "眼神", "动作", "设备", "主机", "网关", "路由器", "电线", "插座", "灯", "窗帘",
    "传感器", "手机", "屏幕", "奖杯", "球场", "球员", "观众", "比分", "冠军", "大脑", "分子", "细胞",
    "实验", "器官", "芯片", "汽车", "城市", "建筑", "地图", "时间轴", "箭头", "节点", "图标", "剪影",
)

PRIMARY_VISUAL_OBJECT_TOKENS = (
    "人物", "手", "设备", "主机", "网关", "路由器", "电线", "插座", "灯", "窗帘", "传感器", "手机", "屏幕",
    "奖杯", "球场", "球员", "大脑", "分子", "细胞", "实验", "器官", "芯片", "汽车", "城市", "建筑", "地图",
    "地铁", "自行车", "户型", "客厅", "卧室", "书房", "沙发", "小鼠", "基因", "孔雀", "实验室", "奖牌",
)

PLACEHOLDER_NOISE_TOKENS = (
    "无字图形符号",
    "无字图标",
    "抽象不可读",
    "不可读图形",
    "抽象品牌符号",
    "抽象角标",
)

VISUAL_ENTITY_LIBRARY = {
    "tech_cinematic": [
        (("路由器", "wifi", "mesh"), "路由器与穿墙信号"),
        (("plc", "电线", "插座", "电力线", "相线"), "墙内电力线链路"),
        (("中控", "主机", "网关", "控制中心"), "中控主机"),
        (("户型", "客厅", "卧室", "书房", "家居"), "真实家庭户型空间"),
        (("灯", "窗帘", "传感器", "空调", "门锁"), "被联动的家居设备"),
        (("芯片", "ai", "主板", "信号"), "发光芯片与信号链路"),
        (("屏幕", "手机", "app"), "控制界面与屏幕光"),
    ],
    "smart_home": [
        (("路由器", "wifi", "mesh"), "路由器与穿墙信号"),
        (("plc", "电线", "插座", "电力线", "相线"), "墙内电力线链路"),
        (("中控", "主机", "网关", "控制中心"), "中控主机"),
        (("灯", "灯光"), "被同时点亮的灯光"),
        (("窗帘", "窗帘轨道"), "自动联动的窗帘"),
        (("空调", "门锁", "传感器"), "空调、门锁和传感器"),
        (("户型", "客厅", "卧室", "书房"), "真实家庭户型空间"),
        (("手机", "屏幕", "app"), "手机控制界面"),
    ],
    "sports_tension": [
        (("奖杯", "大力神杯"), "奖杯"),
        (("球场", "草坪", "球门"), "球场与门前区域"),
        (("球员", "前锋", "守门员"), "高速动作中的球员"),
        (("赔率", "概率", "排名", "比分"), "悬浮的数据光带"),
        (("国旗", "球队"), "对峙的两队标识"),
    ],
    "science_explainer": [
        (("大脑", "神经"), "大脑剖面"),
        (("多巴胺", "分子", "化学式"), "分子结构与神经回路"),
        (("实验", "实验室", "小鼠"), "实验装置与样本"),
        (("基因", "细胞", "器官"), "细胞、器官与基因链"),
    ],
    "history_epic": [
        (("皇帝", "王朝", "帝国"), "人物与权力器物"),
        (("地图", "疆域"), "地图与疆域线"),
        (("宫殿", "城墙", "战场"), "时代建筑场景"),
        (("士兵", "战役", "革命"), "冲突中的人物群像"),
    ],
    "business_editorial": [
        (("公司", "品牌", "产品"), "主角产品或品牌实体"),
        (("市场", "份额", "增长", "财报", "营收"), "少量数据体量块"),
        (("城市", "会议", "办公"), "城市与会议空间"),
        (("工厂", "供应链"), "工业生产链条"),
    ],
    "documentary_portrait": [
        (("人物", "老师", "学生", "父母"), "主人公半身像"),
        (("采访", "麦克风"), "采访道具"),
        (("家庭", "房间", "餐桌"), "真实生活空间"),
        (("情绪", "关系", "成长"), "人物表情与手势"),
    ],
    "storyboard_comic": [
        (("人物", "主角"), "夸张动作中的主角"),
        (("道具", "物件"), "清楚可辨的道具"),
        (("问号", "感叹号"), "漫画式强调符号"),
    ],
    "editorial_dynamic": [
        (("人物", "主角"), "一个占画面的主角"),
        (("产品", "物件", "器物"), "一个清楚的核心物件"),
        (("空间", "房间", "街道", "城市"), "有层次的真实空间"),
    ],
}

GENERIC_VISUAL_ENTITY_LIBRARY = [
    (("问号", "疑问"), "一个醒目的问号形符号"),
    (("打叉", "叉", "否"), "一个红色叉号"),
    (("对勾", "勾", "通过"), "一个发光对勾"),
    (("箭头", "连接"), "少量连接箭头"),
    (("时间轴", "阶段"), "三段推进节点"),
    (("流程", "链路"), "三段动作链"),
    (("关系图", "网络"), "放射关系线"),
]

STYLE_CAMERA_CLAUSES = {
    "elder_life": "温暖真实的生活提醒布光，主视觉优先抓人物表情、关键动作和正在发生的家庭瞬间",
    "tech_cinematic": "现代家庭或样板间空间，冷蓝与暖金对比照明，玻璃、金属和屏幕光塑造科技海报感",
    "sports_tension": "赛场灯光压低背景，速度感和临场张力要像比赛直播前一秒",
    "science_explainer": "实验室或脑内机制空间，冷色主光配少量高亮重点，层次清楚",
    "history_epic": "电影概念场景光线，空气里有年代感与体积光，人物器物沉浸真实",
    "business_editorial": "商业杂志大片布光，城市或会议空间干净锐利，主物体体量明确",
    "documentary_portrait": "真实纪实空间，窗边光或室内单侧光，让人物状态先说话",
    "storyboard_comic": "明快色块和夸张动作，像自媒体故事分镜封面，不做萌化",
    "editorial_dynamic": "高对比海报式布光，主次清楚，留出呼吸但不能发空",
}

VISUAL_LAYOUT_CLAUSES = {
    "timeline": "把信息压成同一张宽画幅里的三段推进场景，阶段变化一眼可见",
    "comparison": "画面左右或前后形成强对照，一侧是问题状态，另一侧是解决状态",
    "mechanism_diagram": "把机制画成从左到右正在发生的动作链，而不是静态流程框",
    "data_card": "用一个主物体配少量数据体量线索，不做表格和说明页",
    "life_scene": "优先做真实空间里的一个瞬间，让人物或物体关系自己讲故事",
    "editorial_collage": "一个主锤点压住画面，另外两三个视觉线索围绕它展开",
}


def clause_detail_score(clause: str) -> int:
    text = clean_text(clause)
    if not text:
        return -999
    score = 0
    score += min(6, sum(1 for token in CONCRETE_VISUAL_TOKENS if token in text)) * 3
    score += min(len(text) // 24, 4)
    if any(token in text for token in ("画面采用", "左侧画", "右侧画", "中间画", "从左到右", "节点", "连接", "对比", "剪影")):
        score += 5
    if any(token in text for token in GENERIC_VISUAL_META_TOKENS):
        score -= 6
    if any(token in text for token in ("无字图标", "信息模块", "信息槽", "三段对照节点", "状态色块")):
        score -= 4
    return score


def prioritize_visual_clauses(items: list[str]) -> list[str]:
    ranked = sorted(
        enumerate(items),
        key=lambda pair: (clause_detail_score(pair[1]), -pair[0]),
        reverse=True,
    )
    return [items[index] for index, _ in ranked]


def extract_prompt_focus_hint(text: str, limit: int = 70) -> str:
    cleaned = clean_text(text)
    for label in ("本镜头先画", "封面先画"):
        value = extract_labeled_prompt_value(cleaned, label, limit)
        if value:
            return value
    if not cleaned or "画面重点是" not in cleaned:
        return ""
    segment = cleaned.split("画面重点是", 1)[1].strip(" ：:，。")
    for stop in (
        "体现",
        "主体明确",
        "保留后期字幕空间",
        "可在画面内加入",
        "不要生成长段正文",
        "文字必须",
        "主标题必须",
        "副标题",
    ):
        if stop in segment:
            segment = segment.split(stop, 1)[0].strip(" ，。")
    return compact_visual_anchor_text(segment, limit)


PROMPT_FIELD_STOP_MARKERS = (
    "对应口播",
    "具体画面",
    "封面具体画面",
    "镜头变化",
    "叙事阶段",
    "频道气质",
    "构图要求",
    "与前后镜头",
    "主体明确",
    "主标题必须",
    "副标题",
    "文字必须",
    "开头口播锚点",
    "再用",
    "可再带出",
)


def extract_labeled_prompt_value(text: str, label: str, limit: int = 92) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    start = -1
    marker_len = 0
    for marker in (f"{label}：", f"{label}:"):
        start = cleaned.find(marker)
        if start >= 0:
            marker_len = len(marker)
            break
    if start < 0:
        return ""
    tail = cleaned[start + marker_len :].strip(" ，。")
    stop_positions: list[int] = []
    for stop in PROMPT_FIELD_STOP_MARKERS:
        if stop == label:
            continue
        for prefix in (f"，{stop}", f"。{stop}", f"；{stop}"):
            pos = tail.find(prefix)
            if pos > 0:
                stop_positions.append(pos)
    if stop_positions:
        tail = tail[: min(stop_positions)]
    return compact_visual_anchor_text(tail.strip(" ，。；"), limit)


def explicit_visual_directives(raw_text: str, purpose: str) -> list[str]:
    labels = (
        ("封面先画", "封面主画面"),
        ("封面具体画面", "封面具体画面"),
        ("开头口播锚点", "开头口播锚点"),
    ) if purpose == "cover" else (
        ("本镜头先画", "本镜头先画"),
        ("具体画面", "具体画面"),
        ("镜头变化", "镜头变化"),
        ("对应口播", "对应口播"),
    )
    directives: list[str] = []
    for label, prefix in labels:
        value = extract_labeled_prompt_value(raw_text, label, 110 if label in {"具体画面", "封面具体画面"} else 78)
        if value:
            if purpose != "cover":
                value = neutralize_scene_rendered_text_targets(value)
            directives.append(f"{prefix}：{value}")
    return dedupe_clauses(directives)


def extract_cover_title_hint(text: str) -> str:
    cleaned = clean_text(text)
    patterns = (
        r"主标题必须作为清晰可读中文大字出现[：:]\s*([^，。；]+)",
        r"围绕[「“](.+?)[」”]做短视频封面",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return clean_text(match.group(1))
    return ""


def extract_cover_subtitle_hint(text: str) -> str:
    cleaned = clean_text(text)
    match = re.search(r"副标题可作为较小清晰中文出现[：:]\s*([^，。；]+)", cleaned)
    return clean_text(match.group(1)) if match else ""


def neutralize_scene_rendered_text_targets(text: str) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    cleaned = re.sub(
        r"(?:[A-Za-z\u4e00-\u9fff]{2,12}[、/]){1,}[A-Za-z\u4e00-\u9fff]{2,12}(?=(?:三条|两条|几条|多条|不同|相关)?(?:无字)?(?:扣费|支付|授权|渠道|通道|入口))",
        "多个相关渠道",
        cleaned,
    )
    cleaned = re.sub(r"[「“\"']([^」”\"']{1,30})[」”\"']", "对应概念", cleaned)
    cleaned = re.sub(r"[A-Za-z0-9\u4e00-\u9fff]{1,16}会员", "某项服务", cleaned)
    cleaned = re.sub(r"(?:¥|￥)?\d+(?:\.\d+)?\s*(?:元|块|角|毛|人民币)?", "金额符号", cleaned)
    cleaned = re.sub(r"(?:手机|屏幕|系统|扣费|付款|账单|服务|应用|App)?(?:短信|通知|弹窗|提示)", "无字提醒", cleaned)
    cleaned = re.sub(r"(?:手机|付款|扣费|消费|服务|应用|App)?账单", "无字账单卡片", cleaned)
    cleaned = cleaned.replace("无字账单卡片提醒", "无字账单卡片")
    cleaned = cleaned.replace("多个相关渠道通道", "多个相关渠道")
    if _contains_any(cleaned, ("短信", "通知", "账单", "页面", "按钮", "列表", "表格", "评论区", "标签", "标题", "弹窗", "卡片")):
        cleaned = f"{cleaned}；所有界面文字不可读，只保留图标、色块、短线和动作关系"
    return cleaned


def concrete_visual_hint_from_anchor(anchor_text: str, raw_text: str = "", purpose: str = "scene") -> str:
    anchor = clean_text(anchor_text)
    source = clean_text(f"{anchor} {raw_text}")
    if not anchor:
        return ""

    prefix = "封面具体画面" if purpose == "cover" else "具体画面"
    if _contains_any(source, ("自动续费", "扣费", "订阅", "会员", "免密支付", "自动扣款", "连续包月", "关闭服务", "取消订阅", "微信", "支付宝", "苹果支付")):
        if _contains_any(anchor, ("短信", "扣费", "续费", "想不起来", "几十块")) or re.search(r"(?:¥|￥)?\d+(?:\.\d+)?\s*(?:元|块|角|毛)", anchor):
            return f"{prefix}：手机上无字扣款通知或账单卡片在前景亮起，长辈/用户拿着手机停住，旁边家人凑近提醒，钱被悄悄扣走的瞬间清楚"
        if _contains_any(anchor, ("免费体验", "1块钱", "1元", "默认勾选", "到期自动续费", "试用")):
            return f"{prefix}：手机开通会员页面只露出无字勾选框和价格牌形图标，手指正要点击，旁边有一枚小警示符号"
        if _contains_any(anchor, ("App里", "取消订阅", "还在扣", "真正的开关", "水管总阀")):
            return f"{prefix}：手机里一个已关闭按钮在前景，但背景还有几条无字支付授权通道继续发光，误区一眼可见"
        if _contains_any(anchor, ("微信", "扣费服务", "服务", "三个点", "关闭服务")):
            return f"{prefix}：支付应用里的授权管理列表以无字卡片呈现，手指点向关闭入口，家人站在旁边确认，操作动作真实可见"
        if _contains_any(anchor, ("支付宝", "免密支付", "自动扣款", "支付设置")):
            return f"{prefix}：支付设置页面以无字列表呈现，手指停在关闭入口，桌面上有账单和老花镜做生活线索"
        if _contains_any(anchor, ("苹果", "头像", "订阅", "取消订阅")):
            return f"{prefix}：手机系统订阅设置页面以无字列表呈现，头像入口和订阅卡片用图形暗示，手指正在确认取消"
        if _contains_any(anchor, ("查一遍", "每个月", "省", "口袋", "清掉")):
            return f"{prefix}：餐桌或书桌上手机展示已关闭的无字扣费项目，旁边放着账单和零钱，人物表情从紧张变成放心"
        if _contains_any(anchor, ("评论区", "告诉我", "转发", "家里人", "下期见")):
            return f"{prefix}：用户把手机递给家人一起查看评论和转发动作，屏幕只露少量无字气泡，结尾互动感清楚"
        return f"{prefix}：以无字手机通知、订阅入口、账单卡片和家人提醒动作做主画面，把自动续费正在被发现或关闭的瞬间拍清楚"

    elder_terms = (
        "老人", "长辈", "中老年", "爸妈", "父母", "记性", "健忘", "忘事", "痴呆", "认知",
        "社区医院", "老年科", "画钟", "记忆力", "钥匙", "吃饭", "吃过饭", "吃了没",
        "早上", "下午", "散步", "打牌", "算账", "评论区", "更多人看到",
    )
    if _contains_any(source, elder_terms):
        if _contains_any(anchor, ("钥匙", "刚放", "东西转头", "名字", "提醒", "想起来")):
            return f"{prefix}：中老年人站在客厅茶几或玄关旁寻找刚放下的钥匙/手机，桌上有老花镜，家人停下动作关切看向他"
        if _contains_any(anchor, ("吃过饭", "吃了没", "早上", "下午", "性格突然", "暴躁", "多疑")):
            return f"{prefix}：饭桌或客厅里的真实家庭瞬间，一位长辈困惑地看着饭碗/墙上时钟，家人表情从担心到警觉"
        if _contains_any(anchor, ("出门", "走丢", "找不到", "回家", "不认识人")):
            return f"{prefix}：小区门口或街道路口，一位长辈拿着手机停住，背景有家人焦急寻找的动作，空间方向感清楚"
        if _contains_any(anchor, ("社区医院", "老年科", "认知测试", "画钟", "记忆力测试", "测试", "筛")):
            return f"{prefix}：社区医院诊室里，医生把简易认知测试纸推到桌前，长辈拿笔画钟，家人坐在旁边陪同"
        if _contains_any(anchor, ("聊天", "散步", "数字游戏", "打牌", "算账", "运转")):
            return f"{prefix}：家人和长辈在餐桌/公园长椅旁互动，打牌、算账或散步正在发生，画面温暖但动作明确"
        if _contains_any(anchor, ("评论区", "怎么判断", "类似情况", "更多人看到")):
            return f"{prefix}：子女和长辈坐在沙发边看手机评论，屏幕只露出少量无字气泡图标，人物正在讨论和回应"
        if _contains_any(anchor, ("害怕", "焦虑", "痴呆", "别急", "警惕", "信号", "留意")):
            return f"{prefix}：中年人握着手机查资料显得紧张，长辈在旁边停顿看向他，画面用一个小警示符号点出风险"
        return f"{prefix}：真实家庭或社区空间里，一位长辈、家人和关键生活物件同框，用表情和手部动作表现这句口播里的判断点"

    if _contains_any(source, ("路由器", "wifi", "WiFi", "PLC", "插座", "传感器", "网关", "主机", "智能家居", "设备")):
        return f"{prefix}：真实家居空间里把核心设备放大成主角，墙体/插座/手机控制界面形成清楚连接关系，光线突出技术冲突"
    if _contains_any(source, ("世界杯", "足球", "篮球", "比赛", "冠军", "球员", "比分", "奖杯")):
        return f"{prefix}：球场灯光下的关键动作瞬间，球员、奖杯或观众反应形成强对峙，胜负压力一眼能看懂"
    if _contains_any(source, ("实验", "细胞", "基因", "器官", "大脑", "医学", "药物", "分子")):
        return f"{prefix}：实验室或人体结构可视化场景，把核心机制落成一个正在观察/检测/变化的瞬间，不做平面讲义"
    if _contains_any(source, ("公司", "市场", "行业", "增长", "营收", "融资", "品牌", "销量")):
        return f"{prefix}：商业现场或城市空间里，一个产品、人物决策或体量对比压住画面，用光影和空间层次表现结果"
    if _contains_any(source, ("历史", "古代", "皇帝", "战争", "朝代", "帝国", "革命")):
        return f"{prefix}：把历史观点放进真实时代场景，人物、器物、建筑和权力关系同框，像电影剧照而不是旧纸资料"

    concrete_terms = [
        term
        for term in CONCRETE_VISUAL_TOKENS
        if term in source and term not in ("人物", "动作", "图标", "节点", "箭头")
    ][:4]
    if concrete_terms:
        return f"{prefix}：把{ '、'.join(concrete_terms) }放进同一真实空间，用一个正在发生的动作或状态变化承载观点"
    return f"{prefix}：把这句口播里的主角、动作、物件和结果放到同一真实现场，先让观众看到正在发生什么，再补少量辅助线索"


def image_text_policy_clauses(raw_text: str, purpose: str) -> list[str]:
    if purpose == "cover":
        return [
            "只有封面主标题、副标题和频道角标可以作为可读文字",
            "口播里的服务名、金额、按钮名、平台名和引号内容只作为语义锚点，不额外原样写进画面",
        ]
    return [
        "场景图默认不渲染可读文字；手机屏幕、账单、按钮、通知、评论区和表格都用无字界面、模糊短线、图标、色块或动作关系表达",
        "口播里的服务名、金额、按钮名、平台名和引号内容只作为语义锚点，不原样变成画面文字",
        "每张图只服务当前口播段落，不把前一段的示例、名词或页面样式扩散到其它镜头",
    ]


def visual_anchor_details(raw_text: str, purpose: str) -> list[str]:
    anchors: list[str] = []
    if purpose == "cover":
        title = extract_cover_title_hint(raw_text)
        subtitle = extract_cover_subtitle_hint(raw_text)
        full_dialogue = extract_prompt_dialogue_hint_full(raw_text)
        dialogue = compact_visual_anchor_text(full_dialogue, 62) if full_dialogue else extract_prompt_dialogue_hint(raw_text, 62)
        focus = extract_prompt_focus_hint(raw_text, 62)
        concrete = concrete_visual_hint_from_anchor(full_dialogue or dialogue or focus or title, raw_text, purpose)
        if title:
            anchors.append(f"封面主题必须围绕：{title}")
        if subtitle:
            anchors.append(f"封面可读短副标题：{subtitle}")
        if dialogue:
            anchors.append(f"封面第一眼对应开头口播：{dialogue}")
        if focus:
            anchors.append(f"封面视觉焦点：{focus}")
        if concrete:
            anchors.append(concrete)
    else:
        full_dialogue = extract_prompt_dialogue_hint_full(raw_text)
        dialogue = compact_visual_anchor_text(full_dialogue, 70) if full_dialogue else extract_prompt_dialogue_hint(raw_text, 70)
        focus = extract_prompt_focus_hint(raw_text, 70)
        concrete = concrete_visual_hint_from_anchor(full_dialogue or dialogue or focus, raw_text, purpose)
        if dialogue:
            anchors.append(f"本张场景的核心瞬间必须来自口播：{dialogue}")
        if focus and focus != dialogue:
            anchors.append(f"画面重点必须围绕：{focus}")
        if concrete:
            anchors.append(concrete)
    return dedupe_clauses(anchors)


def has_primary_visual_object(text: str) -> bool:
    return any(token in clean_text(text) for token in PRIMARY_VISUAL_OBJECT_TOKENS)


def placeholder_noise_score(text: str) -> int:
    normalized = clean_text(text)
    return sum(normalized.count(token) for token in PLACEHOLDER_NOISE_TOKENS)


def collapse_placeholder_noise(text: str) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    cleaned = re.sub(
        r"(?:纸片、印章和标签上的符号全部抽象不可读|几何色块、强调符号和标签上的符号全部抽象不可读|所有标记都只保留为无字图形符号)",
        "",
        cleaned,
    )
    cleaned = cleaned.replace("呈现抽象无字图形符号", "带少量无字图标")
    cleaned = cleaned.replace("呈现抽象不可读图形标记", "带少量无字图标")
    cleaned = cleaned.replace("呈现抽象不可读笔迹", "带少量无字图标")
    cleaned = cleaned.replace("抽象不可读图形标记", "无字图标")
    cleaned = cleaned.replace("抽象不可读笔迹", "无字图标")
    cleaned = cleaned.replace("无字图形符号", "无字图标")
    cleaned = re.sub(r"(?:无字图标[，、和及与 ]*){2,}", "少量无字图标", cleaned)
    cleaned = re.sub(r"(?:少量无字图标[，、和及与 ]*){2,}", "少量无字图标", cleaned)
    cleaned = re.sub(r"(?:干净背景[，、和及与 ]*){2,}", "干净背景", cleaned)
    cleaned = re.sub(r"[\s，,]*$", "", cleaned)
    return clean_text(cleaned)


def resolve_visual_position(text: str) -> str:
    for token in ("左上角", "右上角", "左侧", "右侧", "中间", "上方", "下方", "前景", "背景"):
        if token in text:
            return token
    return ""


def simplify_auxiliary_clause(text: str, purpose: str) -> str:
    normalized = collapse_placeholder_noise(text)
    if not normalized:
        return ""
    position = resolve_visual_position(normalized)
    prefix = f"{position}" if position else ""
    if "角标" in normalized or "抽象品牌符号" in normalized:
        if purpose == "cover":
            return f"{prefix}保留清晰频道角标或作者名，形成个人 IP 识别".strip()
        return f"{prefix}保留一个很小的抽象角标，不出现可读文字".strip()
    if "状态条" in normalized or "状态牌" in normalized:
        return f"{prefix}保留一条简洁状态色块辅助说明".strip()
    if "价格标签" in normalized or "标签样式" in normalized:
        return f"{prefix}点缀一枚价格牌形图标，不出现可读文字".strip()
    if "对话框" in normalized or "气泡" in normalized:
        return f"{prefix}点缀一个气泡形图标辅助表达".strip()
    if any(token in normalized for token in ("信息模块", "信息面板", "卡片")):
        return f"{prefix}保留一块简洁信息面板，只做无字辅助说明".strip()
    if any(token in normalized for token in ("标签", "便签", "贴纸", "按钮", "说明区域")):
        if purpose == "cover":
            return "只保留少量清晰短标签和色块辅助说明"
        return f"{prefix}只保留少量无字图标、箭头和色块辅助说明".strip()
    if placeholder_noise_score(normalized) >= 2:
        return "只保留少量无字图标和色块辅助说明"
    return normalized


def clause_is_prompt_noise(clause: str) -> bool:
    text = clean_text(clause)
    if not text:
        return True
    if text.startswith(("里提到的人物", "物件、动作、空间", "情绪冲突里选择")):
        return True
    if text.startswith(("采用领域路由生成提示词", "根据文案素材决定视觉风格", "画面要像短视频导演分镜")):
        return True
    if text.startswith(("所有说明区域只用", "不要出现左上角栏目名", "不要出现左上角", "底部保持干净")):
        return True
    if any(marker in text for marker in ("不从代码预设题材里选择", "每张图都要有不同的主体动作", "不复用上一张图的构图")):
        return True
    if text.startswith(PROMPT_DIALOGUE_PREFIXES + PROMPT_SCAFFOLD_STARTS):
        return True
    if any(marker in text for marker in PROMPT_SCAFFOLD_CONTAINS):
        return True
    if placeholder_noise_score(text) >= 3 and not has_primary_visual_object(text):
        return True
    return False


def choose_visual_entities(source: str, style: str, domain: str, limit: int = 4) -> list[str]:
    source_lower = clean_text(source).lower()
    entities: list[str] = []

    def append_matches(candidates: list[tuple[tuple[str, ...], str]], *, allow_symbolic: bool = True) -> None:
        for keywords, label in candidates:
            if len(entities) >= limit:
                break
            if not allow_symbolic and any(token in clean_text(label) for token in ("叉号", "问号", "对勾", "箭头", "推进节点", "动作链", "关系线")):
                continue
            if any(keyword.lower() in source_lower for keyword in keywords) and label not in entities:
                entities.append(label)

    append_matches(VISUAL_ENTITY_LIBRARY.get(style, []), allow_symbolic=False)
    append_matches(VISUAL_ENTITY_LIBRARY.get(domain, []), allow_symbolic=False)
    append_matches(GENERIC_VISUAL_ENTITY_LIBRARY, allow_symbolic=False)
    append_matches(GENERIC_VISUAL_ENTITY_LIBRARY, allow_symbolic=True)
    return entities[:limit]


def infer_visual_tension(source: str, style: str, visual_type: str, purpose: str) -> str:
    lowered = clean_text(source).lower()
    if purpose == "cover":
        return "把最核心的冲突压成单帧爆点，先让人停下来，再给后期标题叠加位置"
    if style == "elder_life":
        return "不靠惊悚，靠真实生活里的紧张一秒抓人：关键物件突然成焦点、人物动作停住、家人伸手提醒、表情一顿或代际对视中的一种必须清楚可见"
    if any(token in lowered for token in ("打叉", "断开", "失败", "挡住", "误区", "孤岛", "冲突")):
        return "问题状态要真实可见，阻塞点、断点或失效点必须一眼能看懂"
    if any(token in lowered for token in ("点亮", "联动", "统一", "控制", "连接", "协同")):
        return "让联动或控制链路处于正在发生的状态，不要静态摆拍"
    if style == "sports_tension":
        return "悬念、压迫感和即将分出胜负的瞬间要比解释更强"
    if style == "science_explainer":
        return "把抽象机制落到一瞬间的行为反应、实验反馈或结构剖面上"
    if visual_type == "comparison":
        return "对比边界要清楚，别做成三栏说明板"
    return ""


def visual_hook_clauses(style: str, domain: str, purpose: str, visual_type: str, source: str = "") -> list[str]:
    source_text = clean_text(source)
    if style == "elder_life":
        topic_kind = classify_elder_life_topic_kind(source_text)
        if purpose == "cover":
            if topic_kind == "anti_fraud":
                return [
                    "封面默认抓最有戏的 1 秒：长辈皱眉看屏幕、子女伸手拦住、手机提示突然亮起、验证码或共享风险被及时打断，四选一做主锤点",
                    "别把人物平均摆开，优先近景半身、手部入画、屏幕反光、前景遮挡或回头对视中的一种，让画面像民生短视频封面而不是温吞插图",
                ]
            if topic_kind == "network_hotword":
                return [
                    "封面抓住听到某个称呼后的那 1 秒：长辈表情一顿、年轻人想解释又停住、手机评论区刚好映在脸上，三选一做主锤点",
                    "别做平视合影，优先用近景表情、身体距离、手势停顿或评论区反光，让代际气氛一下子出来",
                ]
            if topic_kind == "health":
                return [
                    "封面抓住最能劝停的 1 秒：筷子停在半空、饭盒刚被打开又停住、长辈拿着药盒或体检单回头看家人，三选一做主锤点",
                    "让食物、药盒、体检单或家人提醒动作同框，优先近景、手部动作和表情变化，不做平静科普插图",
                ]
            if topic_kind == "life_safety":
                return [
                    "封面抓住最危险又被及时发现的 1 秒：火苗、插座、门锁、燃气、积水或热源突然成为焦点，人物动作正停住或回头",
                    "让关键风险物件压住画面，再用家人提醒、手部动作或空间反差补出情绪，不做平均分布的说明图",
                ]
            return [
                "封面默认抓住与本期题材直接相关的那 1 秒：关键物件突然成焦点、人物动作停住、家人提醒或表情一顿，选一个做主锤点",
                "别把人物平均摆开，优先近景半身、手部入画、前景遮挡、回头对视或局部特写中的一种，让画面像短视频封面而不是温吞插图",
            ]
        if topic_kind == "anti_fraud":
            return [
                "场景图里至少要有一个正在发生的动作：伸手、停顿、回头、挂断、凑近屏幕、递眼镜、指向提醒，别让人物只是坐着摆拍",
                "同样是温暖题材，也要有第一眼情绪点：表情一顿、动作被拦下、视线冲突、近大远小或屏幕亮点中的一种必须出现",
            ]
        if topic_kind == "network_hotword":
            return [
                "场景图里至少要有一个正在发生的交流瞬间：听到称呼后表情变化、年轻人准备解释、长辈看向评论区或家人之间出现距离感",
                "把冲突放在称呼、语气、表情和身体距离上，不要再套手机反诈流程，也别做平静站桩图",
            ]
        if topic_kind == "health":
            return [
                "场景图里至少要有一个真实生活动作：打开饭盒、闻一闻、筷子停住、翻药盒、看体检单、家人伸手提醒，别只做概念配图",
                "把食物、药盒、体检单、水杯、冰箱或餐桌中的一个做主锤点，再用表情和手势补出情绪",
            ]
        if topic_kind == "life_safety":
            return [
                "场景图里至少要有一个真实动作：关火、拔插头、回头检查门锁、避开积水、伸手挡住风险源，别做平静说明图",
                "让燃气、火苗、热源、插座、楼道、窗户或门锁中的一个先压住画面，再用人物动作补出紧张感",
            ]
        return [
            "场景图里至少要有一个正在发生的动作：停顿、回头、伸手、拿起、放下、检查、提醒或对视，别让人物只是坐着摆拍",
            "同样是温暖题材，也要有第一眼情绪点：表情一顿、动作被拦下、视线冲突、近大远小或关键物件亮出来中的一种必须出现",
        ]
    if style == "tech_cinematic":
        return [
            "优先用近景设备、发光链路、空间剖面、手部触发或前景遮挡制造科技短视频主视觉，不要平均铺开",
        ]
    if style == "sports_tension":
        return [
            "优先抓住发力、对峙、冲刺、压迫或奖杯临门一脚的瞬间，别退成赛况说明图",
        ]
    if style == "documentary_portrait":
        return [
            "人物不要正对镜头站桩，优先让表情变化、手势、回头、低头、停顿或道具互动形成抓眼瞬间",
        ]
    if visual_type == "comparison":
        return [
            "对比场景默认采用近大远小、明暗反差或同一空间双状态，不要做平行陈列说明板",
        ]
    if purpose == "cover":
        return [
            "封面优先选择最有冲突或最有情绪峰值的一秒，不做平均平视全景；允许近景、低机位、前景遮挡、反光或局部特写中的一种",
        ]
    return [
        "场景图默认要像短视频分镜，不要像配图；至少保留一个动作峰值、情绪峰值或空间反差峰值",
    ]


def build_visual_planner_clauses(prompt: str, template: dict[str, Any], purpose: str) -> list[str]:
    style = classify_material_style(prompt, template, purpose)
    domain = classify_visual_prompt_domain(prompt, purpose)
    visual_type = infer_visual_type(prompt, prompt)
    clauses: list[str] = []

    camera = STYLE_CAMERA_CLAUSES.get(style)
    if camera:
        clauses.append(camera)
    layout = VISUAL_LAYOUT_CLAUSES.get(visual_type)
    if layout:
        clauses.append(layout)

    entities = choose_visual_entities(prompt, style, domain)
    if entities:
        if purpose == "cover":
            clauses.append(f"主锤点围绕{entities[0]}展开，另外用{ '、'.join(entities[1:3]) }做辅助线索" if len(entities) > 1 else f"主锤点围绕{entities[0]}展开")
        elif len(entities) >= 3:
            clauses.append(f"画面围绕{entities[0]}、{entities[1]}和{entities[2]}展开")
        elif len(entities) == 2:
            clauses.append(f"画面围绕{entities[0]}与{entities[1]}展开")
        else:
            clauses.append(f"画面围绕{entities[0]}展开")

    tension = infer_visual_tension(prompt, style, visual_type, purpose)
    if tension:
        clauses.append(tension)
    clauses.extend(visual_hook_clauses(style, domain, purpose, visual_type, prompt))

    auxiliary = simplify_auxiliary_clause(prompt, purpose)
    if auxiliary and not has_primary_visual_object(auxiliary):
        clauses.append(auxiliary)

    return dedupe_clauses([collapse_placeholder_noise(item) for item in clauses if item])


def _contains_any(source: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in source for keyword in keywords)


STYLE_LOCK_TOKENS = (
    "手绘档案",
    "复古档案",
    "手账",
    "做旧",
    "牛皮纸",
    "古籍米白",
    "旧纸",
    "纸张颗粒",
    "斑驳",
    "纸胶带",
    "邮戳",
    "回形针",
    "便签",
    "档案标签",
    "档案卡片",
    "旧报纸",
    "剪报",
    "卷宗",
    "博物馆",
    "纸片",
    "纸底",
    "纸调",
)


STYLE_LOCK_REPLACEMENTS = (
    ("手绘档案手账风格，", ""),
    ("复古档案手账拼贴风格，", ""),
    ("复古档案拼贴 editorial storyboard 风格", "电影化知识短视频主视觉"),
    ("档案手账", "知识短视频"),
    ("档案拼贴", "视觉线索组合"),
    ("旧档案纸片", "干净标题安全区"),
    ("不规则旧档案纸片", "干净标题安全区"),
    ("旧档案卡片", "无字信息面板"),
    ("档案卡片", "无字信息面板"),
    ("档案标签", "无字状态牌"),
    ("便签", "无字状态色块"),
    ("贴纸条", "高亮色块"),
    ("贴纸", "高亮色块"),
    ("纸片", "几何色块"),
    ("纸胶带", "细长色块"),
    ("邮戳", "抽象角标"),
    ("回形针", "细线装饰"),
    ("印章", "红色警示符号"),
    ("朱砂红", "警示红"),
    ("契约藏青", "科技蓝"),
    ("古铜金", "暖金色"),
    ("赭石褐", "暖棕色"),
    ("抽象笔迹", "无字图形符号"),
    ("不可读笔迹", "无字图形符号"),
)


def neutralize_materialized_style(text: str) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    substitutions = (
        (r"(?:手绘档案手账风格|复古档案手账拼贴风格|复古档案拼贴(?:\s*editorial storyboard)?风格|档案手账风格|档案手账|手账风格?)", "知识短视频主视觉"),
        (r"(?:做旧米黄纸底|古籍米白做旧纸(?:张)?背景(?:带轻微纸张颗粒与淡斑驳质感)?|牛皮纸黄做旧纸(?:张)?背景|牛皮纸黄做旧纸底|古籍米白做旧纸底|旧纸张背景|旧纸张底|旧纸底|纸张颗粒|淡斑驳质感|斑驳质感|米黄纸调|纸底|纸调)", "干净背景"),
        (r"(?:旧档案卡片|档案卡片)", "信息模块"),
        (r"(?:档案标签)", "状态条"),
        (r"(?:档案格|档案格线|档案槽)", "信息槽"),
        (r"(?:便签|贴纸条|贴纸)", "信息色块"),
        (r"(?:纸胶带)", "细长色块"),
        (r"(?:邮戳|邮票)", "角标符号"),
        (r"(?:印章|封蜡印章)", "强调符号"),
        (r"(?:回形针)", "细线装饰"),
        (r"(?:纸片)", "几何色块"),
        (r"(?:旧报纸|剪报)", "信息纹理"),
        (r"(?:卷宗|博物馆展陈卡|博物馆档案的封页|老档案馆卷宗|旧书页手账)", "资料质感"),
    )
    for pattern, replacement in substitutions:
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = re.sub(r"(?:外层一圈[^。；]*|墨黑粗手绘不规则圆角矩形边框[^。；]*|墨黑粗手绘圆角外框[^。；]*|外框与画面四边[^。；]*|四边安全区[^。；]*)", "", cleaned)
    cleaned = re.sub(r"(?:左上角只保留一个很小的抽象频道角标，不出现可读文字\s*){2,}", "左上角只保留一个很小的抽象频道角标，不出现可读文字", cleaned)
    cleaned = re.sub(r"(?:底部不要脚注小字，只保留干净环境细节或细线装饰\s*){2,}", "底部不要脚注小字，只保留干净环境细节或细线装饰", cleaned)
    cleaned = re.sub(r"[，,]\s*[，,]+", "，", cleaned)
    return clean_text(cleaned).strip("，,。；")


def clause_is_style_lock(clause: str) -> bool:
    text = clean_text(clause)
    if not text:
        return True
    if text.startswith(("左上角", "顶部小号", "底部", "整张图用", "整张图配色", "四边安全区")):
        return True
    style_hits = sum(1 for token in STYLE_LOCK_TOKENS if token in text)
    visual_hits = sum(1 for token in ("画", "路由器", "电线", "灯", "窗帘", "传感器", "主机", "手机", "墙", "人物", "沙发", "地铁", "自行车", "WiFi", "PLC") if token in text)
    return style_hits >= 2 and visual_hits == 0


def remove_visual_style_lock(text: str) -> str:
    cleaned = neutralize_materialized_style(normalize_image_prompt(text))
    for old, new in STYLE_LOCK_REPLACEMENTS:
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"[\u3000 ]*外层一圈[^。；]*", "", cleaned)
    cleaned = re.sub(r"[\u3000 ]*外框与画面四边[^。；]*", "", cleaned)
    cleaned = re.sub(r"[\u3000 ]*古籍米白[^。；]*(?:背景|质感|纸底)[^。；]*", "", cleaned)
    cleaned = re.sub(r"[\u3000 ]*牛皮纸黄[^。；]*(?:背景|质感|纸底)[^。；]*", "", cleaned)
    clauses = [neutralize_materialized_style(clause) for clause in split_prompt_clauses(cleaned)]
    clauses = [clause for clause in clauses if not clause_is_style_lock(clause)]
    return "。".join(dedupe_clauses(clauses))


def classify_visual_prompt_domain(prompt: str, purpose: str) -> str:
    source = f"{prompt}\n{purpose}".lower()
    if _contains_any(source, ("智能家居", "全屋智能", "中控", "网关", "传感器", "灯光", "窗帘", "家电", "wifi", "mesh", "router")):
        return "smart_home"
    if _contains_any(source, ("客厅", "沙发", "饭桌", "书桌", "家人", "长辈", "爸妈", "人物", "表情", "手部", "手机", "账单", "扣费短信")) and not _contains_any(
        source,
        ("架构图", "机制图", "链路图", "系统图", "关系图", "流程图", "1+2+n"),
    ):
        return "person_story"
    if _contains_any(source, ("架构图", "机制图", "链路图", "系统图", "关系图", "流程图", "节点图", "1+2+n", "闭环图")):
        return "mechanism"
    if _contains_any(source, ("对比", "vs", "左栏", "右栏", "两边", "差异", "误区", "反差", "替代")):
        return "comparison"
    if _contains_any(source, ("时间轴", "过去", "现在", "未来", "历史", "演进", "年份")) or ("三段" in source and "阶段" in source):
        return "timeline"
    if _contains_any(source, ("数据", "增长", "比例", "市场", "趋势", "价格", "成本", "销量", "份额")):
        return "data"
    if _contains_any(source, ("产品", "商品", "手机", "汽车", "设备", "主机", "商业摄影", "包装", "展台")):
        return "product"
    if _contains_any(source, ("人物", "主播", "主理人", "作者", "男性", "女性", "表情", "手势", "采访", "对话")):
        return "person_story"
    return "editorial"


def visual_domain_frame(domain: str) -> list[str]:
    frames = {
        "smart_home": [
            "智能家居领域：画面必须落到真实家庭空间，包含中控屏、手机、网关或路由器、灯光、窗帘、传感器等可识别对象",
            "制造一个第一眼能懂的冲突：旧遥控器与新中控对峙、信号被切断、多个设备被一条控制链路同时点亮，选择最贴合主题的一种",
        ],
        "mechanism": [
            "机制拆解领域：用一个主物体承载因果关系，连接线和节点只是辅助，避免全画面流程图",
            "把抽象机制转成可见动作，比如插拔、断裂、汇聚、分流、锁定、点亮或被一只手触发",
        ],
        "comparison": [
            "对比领域：左右或前后两种状态的反差要清楚，用光线、距离、姿态和环境变化表现差异",
            "只保留一个核心矛盾，不堆满多组小卡片，让观众第一眼看到胜负、误区或转折",
        ],
        "timeline": [
            "时间轴领域：用三个场景层次或物件年代差异表现演进，不直接生成年份、数字或可读标签",
            "画面要有从旧到新的空间方向，靠材质、光线和物件状态形成时间感",
        ],
        "data": [
            "数据趋势领域：把数据抽象成体量、密度、堆叠、流向或高低落差，不直接生成数字图表",
            "给画面一个可感知的尺度差，比如巨大装置、小人物参照、堆积物、分层空间或流动光带",
        ],
        "product": [
            "产品领域：突出产品本体的体积、工艺和使用场景，采用低机位、近景或半拆解视角",
            "加入手部操作、环境反差或局部结构透视，让产品不是静态摆拍，而是正在解决一个问题",
        ],
        "person_story": [
            "人物叙事领域：用人物表情、手势、视线和道具推动观点，保留自然皮肤、衣物和空间细节",
            "人物不能像证件照，要有正在讲述、发现问题、做出选择或被结果震住的瞬间",
        ],
        "editorial": [
            "知识短视频领域：用一个强物件或现场瞬间作为封面式锤点，再用少量道具补充线索",
            "避免普通配图感，加入遮挡、撕裂、聚光、反射、透视切面或手部动作中的一种视觉钩子",
        ],
    }
    return frames.get(domain, frames["editorial"])


def classify_material_style(prompt: str, template: dict[str, Any], purpose: str) -> str:
    cover_style = clean_text(str(template.get("cover_style") or "")).lower()
    source = "\n".join(
        filter(
            None,
            (
                prompt,
                clean_text(str(template.get("name") or "")),
                clean_text(str(template.get("brand_name") or "")),
                cover_style,
                purpose,
            ),
        )
    ).lower()
    if _contains_any(
        source,
        (
            "明白人慢慢讲",
            "爸妈",
            "父母",
            "老人",
            "中老年",
            "子女",
            "养老",
            "反诈",
            "防骗",
            "扣费",
            "客服",
            "验证码",
            "屏幕共享",
            "问家人",
        ),
    ):
        return "elder_life"
    if _contains_any(source, ("智能家居", "全屋智能", "华为", "鸿蒙", "芯片", "ai", "router", "wifi", "plc", "传感器", "网关", "主机", "手机", "设备", "中控")):
        return "tech_cinematic"
    if _contains_any(source, ("世界杯", "足球", "篮球", "比赛", "联赛", "夺冠", "冠军", "球员", "赔率", "比分", "奖杯", "战绩")):
        return "sports_tension"
    if _contains_any(source, ("多巴胺", "大脑", "心理", "神经", "实验", "医学", "细胞", "基因", "药物", "病理", "生理", "器官")):
        return "science_explainer"
    if _contains_any(source, ("王朝", "帝国", "古代", "朝代", "历史", "皇帝", "战争", "革命", "战役", "中世纪", "清朝", "明朝")):
        return "history_epic"
    if _contains_any(source, ("市场", "份额", "商业", "公司", "财报", "融资", "创业", "品牌", "销量", "估值", "行业", "增长", "营收")):
        return "business_editorial"
    if _contains_any(source, ("人物", "对话", "采访", "讲述", "故事", "家庭", "老师", "学生", "父母", "情绪", "关系", "成长")):
        return "documentary_portrait"
    if cover_style == "forbes":
        return "business_editorial"
    if cover_style == "doodle":
        return "storyboard_comic"
    return "editorial_dynamic"


def material_style_frame(prompt: str, template: dict[str, Any], purpose: str) -> list[str]:
    style = classify_material_style(prompt, template, purpose)
    frames = {
        "elder_life": [
            "题材风格：给爸妈看的生活提醒短视频，真实人物、日常物件、家庭或社区空间围着本期主题走",
            "画面要温暖、清楚、可信，但不能温吞；重点放在本期事件正在发生的瞬间、人物关系和动作停顿，不做站桩插图、实验室、器官剖面、科技展板或冰冷示意图",
            "同频道不同题材必须更换主体：网络热词可用手机评论区、家庭聊天和代际表情；反诈才用来电、验证码、转账、屏幕共享；生活安全才用门锁、燃气灶、药盒等",
        ],
        "tech_cinematic": [
            "题材风格：科技电影感知识可视化，真实空间里的设备、玻璃、金属、屏幕光和控制链路清楚可见",
            "把技术观点落成正在发生的动作，比如设备被同时点亮、信号穿过空间、一个核心硬件压住画面，不做纸面拼贴",
            "如果是封面，优先做现代科技海报感，不要撕纸边、旧纸肌理、卷边和资料桌质感",
        ],
        "sports_tension": [
            "题材风格：赛事导播海报风，球场灯光、速度感、奖杯或关键动作形成高压瞬间",
            "赔率、比分和排名只转成胜负氛围、对峙关系和压迫感，不做纸质表格或旧资料板",
        ],
        "science_explainer": [
            "题材风格：实验室科普大片风，器官、分子、实验装置和光线层次清楚，不做做旧纸面笔记",
            "把抽象原理变成一个能看懂的实验瞬间、结构剖面或微观到宏观的可见连接",
        ],
        "history_epic": [
            "题材风格：历史电影概念场景风，人物、器物、建筑和时代氛围沉浸真实，不做卷宗式拼贴",
            "历史信息依靠场景、服饰、器具和权力关系表达，不用旧纸标签堆信息",
        ],
        "business_editorial": [
            "题材风格：商业杂志大片风，高对比光影、城市或会议空间、产品与数据体量结合",
            "数据只转成体量、堆叠、层级和对比，不做纸片报表、旧报剪报或桌面资料堆砌",
        ],
        "documentary_portrait": [
            "题材风格：纪录片人物叙事风，用人物表情、视线、手势、空间和道具推动故事",
            "把观点放进一个真实瞬间，不画成教程卡片、资料桌或固定模板背景",
        ],
        "storyboard_comic": [
            "题材风格：自媒体知识分镜风，明快色块、夸张动作、清晰道具关系，适合故事化表达",
            "可以有少量漫画式强调符号，但不要统一变成纸片手账背景",
        ],
        "editorial_dynamic": [
            "题材风格：杂志级动态科普封面风，强主体、少量辅助物件、清楚空间层次和情绪方向",
            "风格必须服从当前文案素材，同频道不同选题可以明显不同，不统一套用纸面手账或固定背景",
        ],
    }
    return frames.get(style, frames["editorial_dynamic"])


def template_identity_frame(template: dict[str, Any], purpose: str) -> list[str]:
    if purpose != "cover":
        return []
    brand = clean_text(
        str(
            template.get("brand_name")
            or template.get("name")
            or template.get("key")
            or ""
        )
    )
    cover_style = clean_text(str(template.get("cover_style") or ""))
    cover_style_hint = {
        "notebook": "信息密度高、层次清楚、系列感强，但不能固化成纸面手账背景",
        "doodle": "轮廓简洁、动作夸张、识别度高，但整体气质仍然服从题材",
        "forbes": "商业封面感强、主视觉清楚、秩序干净，但不能只剩杂志排版",
    }.get(cover_style.lower(), "")
    clauses = [
        "个人 IP 视觉签名：封面固定保留一个可复用的识别系统，比如同一枚频道角标、专属色块、主理人视角道具或人物剪影，形成系列感",
    ]
    if brand:
        clauses.append(f"频道关联：这个封面属于「{brand}」系列，允许把「{brand}」作为清晰频道名或作者角标出现")
    if cover_style_hint:
        clauses.append(f"频道视觉习惯：{cover_style_hint}")
    elif cover_style and cover_style != "default":
        clauses.append(f"封面风格锚点：{cover_style}，只作为弱参考，整体风格服从当前题材")
    return clauses


def build_prompt_generator_frame(prompt: str, template: dict[str, Any], purpose: str) -> list[str]:
    domain = classify_visual_prompt_domain(prompt, purpose)
    frame = [
        "所有关键词都只是导演提示，不直接画成可读文字",
        "风格跟着文案素材走，同频道不同题材允许明显变化",
    ]
    frame.extend(build_visual_planner_clauses(prompt, template, purpose))
    frame.extend(visual_domain_frame(domain)[:1])
    frame.extend(material_style_frame(prompt, template, purpose)[:2])
    frame.extend(template_identity_frame(template, purpose))
    return frame


def optimize_visual_generation_prompt(prompt: str, template: dict[str, Any], purpose: str, attempt: int = 1, audit_reasons: list[str] | None = None) -> str:
    raw_text = expand_scene_prompt_shorthand(prompt, template)
    text = remove_visual_style_lock(raw_text)
    clauses = split_dense_prompt_clauses(text)
    rewritten = [collapse_placeholder_noise(neutralize_materialized_style(abstract_textual_clause(clause, purpose))) for clause in clauses]
    rewritten = dedupe_clauses([item for item in rewritten if item and not clause_is_prompt_noise(item)])
    prioritized_rewritten = prioritize_visual_clauses(rewritten)

    prompt_frame = dedupe_clauses(build_prompt_generator_frame(raw_text, template, purpose))
    base_rules = [
        "抓眼的短视频主视觉，强主体，高反差，第一眼就能看懂冲突或转折，画面铺满全幅",
        "风格必须服从当前文案素材，不要把所有选题都做成同一种纸面手账、档案卡或旧资料桌",
        "主体尽量占画面 55% 到 75%，前中后景分明，光线和材质有戏剧性，不做安静的平铺说明板",
        "优先用一个主角物体、人物动作或空间冲突承载观点，而不是堆满卡片、标签、流程框和教程排版",
        "保留 1 到 3 个最关键的视觉锚点，用图标、关系线、局部装置或环境细节辅助表达，不要把信息撒满整个画面",
        "默认不要正中平视平均铺开；优先近景、半身、低机位、前景遮挡、屏幕反光、手部入画、近大远小或局部特写中的一种",
        "整体像知识类爆款短视频的电影化分镜，不要像 PPT、教辅页、产品说明书或俯拍资料桌面",
    ]
    if purpose == "cover":
        base_rules.insert(1, "封面要有一个能压住画面的主锤点和明显情绪方向，像短视频爆款封面，而不是冷静的示意图")
        base_rules.insert(2, "封面必须有情绪峰值、动作峰值或反差峰值三者之一，让人愿意停下来，不做温吞插图")
        base_rules.insert(2, "封面文字允许直接生成，主标题、短副标题、频道角标要清晰可读，避免长段正文、脚注、免责声明、水印或乱码")
        base_rules.insert(3, "给后期二次叠字留出安全区域，但画面本身必须先有吸引力和记忆点，不能只靠后期补救")
        base_rules.insert(3, "封面默认不要撕纸、卷边、旧纸肌理、胶带、旧海报残边或手账桌面，除非题材本身就是复古纸面对象")
    else:
        base_rules.insert(1, "场景图优先表达物体、关系、动作和空间张力，让观众即使静音也能感到正在发生什么")
        base_rules.insert(2, "每张场景图都要有一个可感知的动作峰值、情绪峰值或空间反差峰值，别让人物只是摆拍")
        base_rules.append("场景图默认不渲染任何可读文字；信息通过人物动作、物件关系、无字界面、图标、色块、光线和空间层次表达")
        base_rules.append("不要出现左上角栏目名、底部免责声明、产品品牌字、服务名、按钮名、金额、大片印章文字或便签正文")

    if audit_reasons:
        if any("text" in reason for reason in audit_reasons):
            base_rules.append("去掉画面里所有疑似文字块，改用图标、线条、色块、箭头和无字图形符号表达信息")
        if any("top_left_text" in reason for reason in audit_reasons):
            base_rules.append("左上角保持干净，只保留小图形装饰，不出现任何字样")
        if any("bottom_text" in reason for reason in audit_reasons):
            base_rules.append("底部保持干净，不要脚注、小字或字幕")
        if any("empty" in reason or "foreground" in reason or "coverage" in reason for reason in audit_reasons):
            base_rules.append("主体放大并占据更多画面，减少空白背景，避免内容只缩在中间一小块")
        if any("flat" in reason for reason in audit_reasons):
            base_rules.append("增强主体层次、材质起伏和前中后景对比，避免平铺、发空和廉价说明图质感")

    if attempt > 1:
        if purpose == "cover":
            base_rules.append("这是重绘修正版：保留清晰短标题和频道角标，清除乱码、页脚、水印和长段正文，同时把主体做得更完整、更有视觉冲击")
        else:
            base_rules.append("这是重绘修正版：只保留必要短标签，清除长段文字、页脚和水印，同时把主体做得更完整、更清晰、更有视觉冲击")

    explicit_details = explicit_visual_directives(raw_text, purpose)
    if explicit_details and purpose != "cover":
        anchor_details = explicit_details
    else:
        fallback_anchor_details = visual_anchor_details(raw_text, purpose)
        if explicit_details:
            fallback_anchor_details = [
                item
                for item in fallback_anchor_details
                if not item.startswith(("封面第一眼对应", "封面具体画面", "封面视觉焦点"))
            ]
        anchor_details = dedupe_clauses(explicit_details + fallback_anchor_details)
    anchor_details = dedupe_clauses(anchor_details + image_text_policy_clauses(raw_text, purpose))
    anchor_signatures = {
        re.sub(r"[\s，,。；：:、“”‘’\"'（）()\[\]【】《》<>!?！？—\\/_-]+", "", item)
        for item in anchor_details
    }
    non_anchor_details = [
        item
        for item in prioritized_rewritten
        if re.sub(r"[\s，,。；：:、“”‘’\"'（）()\[\]【】《》<>!?！？—\\/_-]+", "", item) not in anchor_signatures
    ]
    if explicit_details:
        non_anchor_details = [
            item
            for item in non_anchor_details
            if not item.startswith(("本镜头先画", "对应口播", "具体画面", "镜头变化", "封面主画面", "封面具体画面", "开头口播锚点"))
        ]
    primary_details = non_anchor_details[:2 if purpose == "cover" else 1]
    focused_frame = prompt_frame[2:] if len(prompt_frame) > 2 else prompt_frame
    framing_rules = focused_frame[:2 if purpose == "cover" else 1]
    quality_rules = dedupe_clauses(base_rules)[:2] if purpose == "cover" else []
    secondary_details = non_anchor_details[2:3] if purpose == "cover" else []
    final_prompt = "。".join(
        dedupe_clauses(
            [
                collapse_placeholder_noise(item)
                for item in (anchor_details + primary_details + framing_rules + quality_rules + secondary_details)
                if item
            ]
        )
    ).strip("。")
    return compact_visual_image_prompt(final_prompt, limit=900 if purpose == "cover" else 780)


def read_image_audit(output_path: Path) -> dict[str, Any]:
    audit = storage.read_json(output_path.with_suffix(".audit.json"), {})
    return audit if isinstance(audit, dict) else {}


def read_generated_prompt(output_path: Path, fallback: str = "") -> str:
    prompt = storage.read_text(output_path.with_suffix(".md")).strip()
    return prompt or normalize_image_prompt(fallback)


def composer_scene_prompt(prompt: str) -> str:
    expanded = expand_scene_prompt_shorthand(prompt, {})
    clauses = split_dense_prompt_clauses(expanded)
    visual_clauses: list[str] = []
    for clause in clauses:
        rewritten = neutralize_materialized_style(abstract_textual_clause(clause, "scene"))
        if not rewritten:
            continue
        if any(token in rewritten for token in ("不出现", "不渲染", "不要", "不可读", "水印", "脚注", "字幕")):
            continue
        visual_clauses.append(rewritten)
    dialogue_hint = extract_prompt_dialogue_hint(expanded, 52)
    anchor_details = visual_anchor_details(expanded, "scene")
    if dialogue_hint and not anchor_details:
        anchor_details.append(f"本张场景的核心瞬间必须来自口播：{dialogue_hint}")
    if not visual_clauses:
        visual_clauses = ["知识短视频场景图，主体明确，结构关系清晰，画面有强对比和空间层次"]
    return compact_visual_image_prompt("；".join(dedupe_clauses(anchor_details + visual_clauses)[:5]), limit=260)


def composer_scene_prompts(project_id: int, scene_paths: list[Path], fallback_prompts: list[str]) -> list[str]:
    prompt_records = storage.read_json(storage.project_file(project_id, "scenes/scene_prompts.json"), [])
    by_filename: dict[str, str] = {}
    if isinstance(prompt_records, list):
        for item in prompt_records:
            if not isinstance(item, dict):
                continue
            filename = clean_text(str(item.get("filename", "")))
            prompt = clean_text(str(item.get("source_prompt") or item.get("prompt") or ""))
            if filename and prompt:
                by_filename[filename] = prompt
    prompts: list[str] = []
    for idx, path in enumerate(scene_paths):
        source = by_filename.get(path.name)
        if not source and idx < len(fallback_prompts):
            source = fallback_prompts[idx]
        prompts.append(composer_scene_prompt(source or ""))
    return prompts


def expand_scene_prompt_shorthand(prompt: str, template: dict[str, Any]) -> str:
    text = normalize_image_prompt(prompt)
    if not text:
        return text
    brand_marker = template_brand_marker(template)
    footer_marker = template_footer_marker(template)
    replacements = [
        (r"左上角品牌位\+小(?:标签|图章|邮戳)", brand_marker),
        (r"品牌位\+小(?:标签|图章|邮戳)", brand_marker),
        (r"左上角品牌位", brand_marker),
        (r"底部极小字免责文字", footer_marker),
        (r"底部小字免责文字", footer_marker),
        (r"底部免责小字", footer_marker),
        (r"底部免责文字", footer_marker),
    ]
    for pattern, replacement in replacements:
        if replacement:
            text = re.sub(pattern, replacement, text)
    return text


def apply_apiyi_prompt_conventions(prompt: str, size: str) -> str:
    clean_prompt = compact_visual_image_prompt(prompt)
    if not clean_prompt:
        return clean_prompt
    if re.search(r"(\d+\s*[:：]\s*\d+)|(\d{3,4}\s*[x×]\s*\d{3,4})|方形|横版|竖版", clean_prompt):
        return clean_prompt
    hint = build_apiyi_size_hint(size)
    if not hint:
        return clean_prompt
    return f"{hint}，{clean_prompt}"


def normalize_image_prompt(prompt: str) -> str:
    text = (prompt or "").strip()
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _count_small_dark_components(region_gray: Any, threshold: float) -> int:
    if np is None:
        return 0
    dark = np.asarray(region_gray < threshold, dtype=bool)
    height, width = dark.shape
    visited = np.zeros((height, width), dtype=bool)
    components = 0
    for y in range(height):
        for x in range(width):
            if not dark[y, x] or visited[y, x]:
                continue
            stack = [(y, x)]
            visited[y, x] = True
            area = 0
            while stack:
                cy, cx = stack.pop()
                area += 1
                if area > 800:
                    break
                for ny in range(max(0, cy - 1), min(height, cy + 2)):
                    for nx in range(max(0, cx - 1), min(width, cx + 2)):
                        if not visited[ny, nx] and dark[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((ny, nx))
            if 6 <= area <= 400:
                components += 1
    return components


def audit_generated_image(path: Path, size: str, purpose: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "ok": True,
        "severity": "ok",
        "reasons": [],
        "size_hint": size,
        "purpose": purpose,
    }
    if Image is None or np is None:
        report["skipped"] = "missing_image_audit_deps"
        return report
    if not path.exists():
        report["ok"] = False
        report["severity"] = "hard"
        report["reasons"] = ["missing_file"]
        return report

    try:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            pixels = np.asarray(rgb, dtype=np.float32)
            audit_width = min(640, width)
            audit_height = max(1, int(height * (audit_width / max(1, width))))
            audit_gray = np.asarray(
                rgb.resize((audit_width, audit_height)).convert("L"),
                dtype=np.float32,
            )
    except Exception as exc:
        report["ok"] = False
        report["severity"] = "hard"
        report["reasons"] = [f"open_failed:{type(exc).__name__}"]
        return report

    gray = pixels.mean(axis=2)
    stddev = float(gray.std())
    report["width"] = int(width)
    report["height"] = int(height)
    report["stddev"] = round(stddev, 2)

    if stddev < IMAGE_AUDIT_MIN_STDDEV:
        report["reasons"].append("flat_low_variance")

    patch_h = max(8, height // 14)
    patch_w = max(8, width // 14)
    corners = np.concatenate(
        [
            pixels[:patch_h, :patch_w].reshape(-1, 3),
            pixels[:patch_h, -patch_w:].reshape(-1, 3),
            pixels[-patch_h:, :patch_w].reshape(-1, 3),
            pixels[-patch_h:, -patch_w:].reshape(-1, 3),
        ],
        axis=0,
    )
    background = np.median(corners, axis=0)
    diff = np.abs(pixels - background).mean(axis=2)
    foreground = diff > 18.0
    foreground_ratio = float(foreground.mean())
    report["foreground_ratio"] = round(foreground_ratio, 4)
    if foreground_ratio < IMAGE_AUDIT_MIN_FOREGROUND_RATIO:
        report["reasons"].append("foreground_too_small")

    coords = np.argwhere(foreground)
    if coords.size:
        top, left = coords.min(axis=0)
        bottom, right = coords.max(axis=0)
        coverage_width = float((right - left + 1) / max(1, width))
        coverage_height = float((bottom - top + 1) / max(1, height))
        report["coverage_width"] = round(coverage_width, 4)
        report["coverage_height"] = round(coverage_height, 4)
        if coverage_width < IMAGE_AUDIT_MIN_COVERAGE_WIDTH:
            report["reasons"].append("coverage_too_narrow")
        if coverage_height < IMAGE_AUDIT_MIN_COVERAGE_HEIGHT:
            report["reasons"].append("coverage_too_short")
    else:
        report["reasons"].append("empty_foreground")

    if purpose in {"scene", "cover"}:
        top_left = gray[: max(32, int(height * 0.2)), : max(32, int(width * 0.32))]
        bottom_strip = gray[int(height * 0.84) :, :]
        audit_mean = float(audit_gray.mean())
        if audit_mean > 115:
            text_components = _count_small_dark_components(audit_gray, audit_mean - 24)
            component_density = text_components / max(1.0, (audit_width * audit_height) / 10_000.0)
            report["text_component_density"] = round(component_density, 2)
            if component_density >= IMAGE_AUDIT_TEXT_COMPONENT_DENSITY:
                report["reasons"].append("text_like_marks_suspected")
        if top_left.size:
            top_left_mean = float(top_left.mean())
            if top_left_mean > 135:
                top_left_components = _count_small_dark_components(top_left, top_left_mean - 25)
                report["top_left_components"] = int(top_left_components)
                if top_left_components >= 14:
                    report["reasons"].append("top_left_text_suspected")
        if bottom_strip.size:
            bottom_mean = float(bottom_strip.mean())
            if bottom_mean > 135:
                bottom_components = _count_small_dark_components(bottom_strip, bottom_mean - 22)
                report["bottom_components"] = int(bottom_components)
                if bottom_components >= 24:
                    report["reasons"].append("bottom_text_suspected")

    hard_reasons = {
        "missing_file",
        "flat_low_variance",
        "foreground_too_small",
        "coverage_too_narrow",
        "coverage_too_short",
        "empty_foreground",
    }
    severity = "ok"
    if report["reasons"]:
        severity = "soft"
    if any(reason in hard_reasons for reason in report["reasons"]):
        severity = "hard"
    report["severity"] = severity
    report["ok"] = not report["reasons"]
    return report


def build_ark_extra_body(env: dict[str, str], purpose: str) -> dict[str, Any]:
    extra: dict[str, Any] = {"watermark": False}
    key = "ARK_IMAGE_WEB_SEARCH_COVER" if purpose == "cover" else "ARK_IMAGE_WEB_SEARCH_SCENE"
    if env_flag(env.get(key)):
        extra["tools"] = [{"type": "web_search"}]
    return extra


def generate_ark_image(prompt: str, output_path: Path, size: str, purpose: str, env: dict[str, str]) -> Path:
    if OpenAI is None:
        raise RuntimeError("当前环境缺少 openai 依赖，无法调用火山方舟文生图。")
    api_key = (env.get("ARK_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("ARK_API_KEY 未配置，无法生成场景图。")

    model = resolve_ark_image_model(env)
    client = OpenAI(api_key=api_key, base_url=ARK_BASE_URL, timeout=240.0)
    clean_prompt = normalize_image_prompt(prompt)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    response = client.images.generate(
        model=model,
        prompt=clean_prompt,
        size=size,
        response_format="b64_json",
        extra_body=build_ark_extra_body(env, purpose),
    )
    image_data = base64.b64decode(response.data[0].b64_json)
    output_path.write_bytes(image_data)
    storage.write_text(output_path.with_suffix(".md"), clean_prompt + "\n")
    return output_path


def _request_provider_json(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: float = 240.0,
) -> dict[str, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method.upper())
    for key, value in headers.items():
        request.add_header(key, value)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="ignore")
            parsed = json.loads(text or "{}")
            if not isinstance(parsed, dict):
                raise RuntimeError("兼容接口返回的不是 JSON 对象。")
            return parsed
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        if "域名解析错误" in body:
            raise RuntimeError("当前 OpenAI 兼容网关返回“域名解析错误”，说明这条 Base URL 没有正确转发到图片接口。") from exc
        detail = clean_text(body)[:400]
        raise RuntimeError(f"HTTP {exc.code}: {detail or '图片接口返回错误'}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None) or exc
        raise RuntimeError(f"网络请求失败：{reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"image request timed out after {timeout:.0f}s: {exc}") from exc
    except OSError as exc:
        if "timed out" in str(exc).lower():
            raise RuntimeError(f"image request timed out after {timeout:.0f}s: {exc}") from exc
        raise
    except json.JSONDecodeError as exc:
        raise RuntimeError("兼容接口返回了无法解析的 JSON。") from exc


def _download_provider_binary(url: str, timeout: float = 240.0) -> bytes:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"image download timed out after {timeout:.0f}s: {exc}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None) or exc
        raise RuntimeError(f"image download failed: {reason}") from exc
    except OSError as exc:
        if "timed out" in str(exc).lower():
            raise RuntimeError(f"image download timed out after {timeout:.0f}s: {exc}") from exc
        raise RuntimeError(f"image download failed: {exc}") from exc


def _extract_provider_image_bytes(payload: dict[str, Any], timeout: float = 240.0) -> bytes:
    data = payload.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise RuntimeError("兼容出图接口未返回 data[0]。")
    item = data[0]
    encoded = item.get("b64_json") or item.get("b64")
    if isinstance(encoded, str) and encoded.strip():
        encoded_text = encoded.strip()
        if encoded_text.startswith("data:image") and "," in encoded_text:
            encoded_text = encoded_text.split(",", 1)[1]
        try:
            return base64.b64decode(encoded_text)
        except Exception as exc:
            raise RuntimeError("兼容出图接口返回的图片数据无法解码。") from exc
    image_url = item.get("url")
    if isinstance(image_url, str) and image_url.strip():
        return _download_provider_binary(image_url.strip(), timeout=timeout)
    raise RuntimeError("兼容出图接口未返回 b64_json 或 url。")


def chatgpt_handoff_dir(output_path: Path) -> Path:
    return output_path.parent / "_chatgpt_handoff"


def build_chatgpt_handoff_prompt(prompt: str, size: str, purpose: str) -> str:
    ratio_hint = build_apiyi_size_hint(size)
    purpose_hint = "短视频封面图" if purpose == "cover" else "短视频分镜场景图"
    lines = [
        f"请直接生成一张{purpose_hint}，不要先解释。",
        f"画幅要求：{ratio_hint or size}。",
        "风格要求：真实、有主体、有传播感，适合中文短视频；保留干净字幕空间；不要加水印、二维码、品牌 Logo。",
        "如果画面里需要文字，只保留短而可读的中文标题或提示词，不要出现乱码长段落。",
        "",
        "画面提示词：",
        normalize_image_prompt(prompt),
    ]
    return "\n".join(lines).strip() + "\n"


def write_chatgpt_handoff_page(prompt: str, output_path: Path, size: str, purpose: str, env: dict[str, str]) -> Path:
    handoff_dir = storage.ensure_dir(chatgpt_handoff_dir(output_path))
    stem = output_path.stem
    prompt_path = handoff_dir / f"{stem}.prompt.txt"
    page_path = handoff_dir / f"{stem}.html"
    storage.write_text(prompt_path, prompt)
    chatgpt_url = clean_text(env.get("CHATGPT_IMAGE_WEB_URL") or "https://chatgpt.com/") or "https://chatgpt.com/"
    target_path = str(output_path.resolve())
    prompt_js = json.dumps(prompt, ensure_ascii=False)
    html_doc = f"""<!doctype html>
<meta charset="utf-8" />
<title>ChatGPT 图片接力 - {html.escape(output_path.name)}</title>
<style>
  body {{ font-family: "Microsoft YaHei", Arial, sans-serif; margin: 32px; line-height: 1.6; color: #0f172a; }}
  .wrap {{ max-width: 980px; margin: 0 auto; }}
  .path, textarea {{ font-family: Consolas, "Cascadia Code", monospace; }}
  textarea {{ width: 100%; min-height: 360px; padding: 14px; border: 1px solid #cbd5e1; border-radius: 10px; }}
  .box {{ border: 1px solid #dbeafe; background: #f8fbff; border-radius: 12px; padding: 14px 16px; margin: 14px 0; }}
  button, a.btn {{ display: inline-block; border: 1px solid #cbd5e1; background: #2563eb; color: #fff; padding: 10px 14px; border-radius: 8px; text-decoration: none; cursor: pointer; margin-right: 8px; }}
  button.secondary {{ background: #fff; color: #0f172a; }}
</style>
<div class="wrap">
  <h1>ChatGPT 图片接力：{html.escape(output_path.name)}</h1>
  <div class="box">
    <strong>目标保存路径</strong>
    <div class="path">{html.escape(target_path)}</div>
    <p>在 ChatGPT 生成图片后，请下载 PNG，并保存/复制到上面的路径。程序检测到这个文件出现后会自动继续下一步。</p>
  </div>
  <p>
    <a class="btn" href="{html.escape(chatgpt_url)}" target="_blank" rel="noreferrer">打开 ChatGPT 网页</a>
    <button class="secondary" onclick="navigator.clipboard.writeText(PROMPT).then(()=>alert('已复制提示词'))">复制提示词</button>
  </p>
  <textarea readonly id="prompt"></textarea>
</div>
<script>
const PROMPT = {prompt_js};
document.getElementById("prompt").value = PROMPT;
</script>
"""
    storage.write_text(page_path, html_doc)
    storage.write_json(
        handoff_dir / f"{stem}.handoff.json",
        {
            "output_path": target_path,
            "prompt_path": str(prompt_path),
            "page_path": str(page_path),
            "purpose": purpose,
            "size": size,
            "created_at": storage.now_ts(),
        },
    )
    return page_path


def copy_text_to_clipboard(text: str) -> None:
    if os.name != "nt":
        return
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
            input=text,
            text=True,
            encoding="utf-8",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except Exception:
        pass


def open_chatgpt_handoff(page_path: Path, env: dict[str, str], prompt: str) -> None:
    if not env_flag(env.get("CHATGPT_IMAGE_AUTO_OPEN", "true")):
        return
    copy_text_to_clipboard(prompt)
    targets = {clean_text(env.get("CHATGPT_IMAGE_OPEN_TARGET") or "web").lower() or "web"}
    if "both" in targets:
        targets = {"web", "desktop"}
    with contextlib.suppress(Exception):
        os.startfile(str(page_path))  # type: ignore[attr-defined]
    if "web" in targets:
        url = clean_text(env.get("CHATGPT_IMAGE_WEB_URL") or "https://chatgpt.com/") or "https://chatgpt.com/"
        with contextlib.suppress(Exception):
            os.startfile(url)  # type: ignore[attr-defined]
    if "desktop" in targets:
        desktop_path = clean_text(env.get("CHATGPT_IMAGE_DESKTOP_PATH") or "")
        if desktop_path and (desktop_path.startswith("chatgpt://") or desktop_path.startswith("ms-")):
            with contextlib.suppress(Exception):
                os.startfile(desktop_path)  # type: ignore[attr-defined]
        elif desktop_path and Path(desktop_path).exists():
            with contextlib.suppress(Exception):
                subprocess.Popen([desktop_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif not desktop_path:
            with contextlib.suppress(Exception):
                os.startfile("chatgpt://")  # type: ignore[attr-defined]


def wait_for_external_image(output_path: Path, timeout_seconds: float, log: Callable[[str], None] | None = None) -> Path:
    deadline = time.monotonic() + timeout_seconds
    last_size = -1
    stable_since = 0.0
    while time.monotonic() < deadline:
        if output_path.exists() and output_path.stat().st_size > 4096:
            size = output_path.stat().st_size
            now = time.monotonic()
            if size == last_size:
                if not stable_since:
                    stable_since = now
                if now - stable_since >= 1.5:
                    return output_path
            else:
                last_size = size
                stable_since = now
        time.sleep(2.0)
    handoff = chatgpt_handoff_dir(output_path) / f"{output_path.stem}.html"
    raise RuntimeError(
        "ChatGPT 接力等待超时：请在 ChatGPT 生成图片后，把 PNG 保存到 "
        f"{output_path}，然后重试当前图片或重新运行图片步骤。接力页：{handoff}"
    )


def cleanup_chatgpt_handoff_artifacts(output_path: Path, log: Callable[[str], None] | None = None) -> None:
    handoff_dir = chatgpt_handoff_dir(output_path)
    stem = output_path.stem
    removed: list[str] = []
    for path in (
        handoff_dir / f"{stem}.html",
        handoff_dir / f"{stem}.prompt.txt",
        handoff_dir / f"{stem}.handoff.json",
    ):
        try:
            path.unlink()
            removed.append(path.name)
        except FileNotFoundError:
            continue
        except Exception:
            continue
    with contextlib.suppress(Exception):
        if handoff_dir.exists() and not any(handoff_dir.iterdir()):
            handoff_dir.rmdir()
    if log and removed:
        log(f"[images] 已清理 ChatGPT 接力提示词文件：{', '.join(removed)}")


def generate_chatgpt_handoff_image(
    prompt: str,
    output_path: Path,
    size: str,
    purpose: str,
    env: dict[str, str],
    log: Callable[[str], None] | None = None,
) -> Path:
    clean_prompt = build_chatgpt_handoff_prompt(prompt, size, purpose)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    backup_paths: list[tuple[Path, Path]] = []
    backup_stamp = storage.now_ms()
    for current_path in (output_path, output_path.with_suffix(".md"), output_path.with_suffix(".audit.json")):
        if not current_path.exists():
            continue
        backup_path = current_path.with_name(f".{current_path.name}.handoff-backup-{backup_stamp}")
        current_path.replace(backup_path)
        backup_paths.append((current_path, backup_path))
    try:
        storage.write_text(output_path.with_suffix(".md"), normalize_image_prompt(prompt) + "\n")
        page_path = write_chatgpt_handoff_page(clean_prompt, output_path, size, purpose, env)
        if log:
            log(f"[images] ChatGPT 接力页已生成：{page_path}")
            log(f"[images] 已复制提示词，请在 ChatGPT 生成图片后保存到：{output_path}")
        open_chatgpt_handoff(page_path, env, clean_prompt)
        result = wait_for_external_image(output_path, chatgpt_image_wait_seconds(env), log=log)
        cleanup_chatgpt_handoff_artifacts(output_path, log=log)
        for _current_path, backup_path in backup_paths:
            backup_path.unlink(missing_ok=True)
        return result
    except Exception:
        for current_path, backup_path in backup_paths:
            if backup_path.exists():
                current_path.unlink(missing_ok=True)
                backup_path.replace(current_path)
        cleanup_chatgpt_handoff_artifacts(output_path, log=log)
        raise


def default_chatgpt_browser_profile_dir() -> Path:
    return storage.CONFIG_ROOT / "chatgpt-browser-profile"


def resolve_chatgpt_browser_path(env: dict[str, str]) -> str | None:
    configured = clean_text(env.get("CHATGPT_IMAGE_BROWSER_PATH") or "")
    if configured and Path(configured).exists():
        return configured
    candidates = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def chatgpt_browser_user_data_dir(env: dict[str, str]) -> Path:
    configured = clean_text(env.get("CHATGPT_IMAGE_USER_DATA_DIR") or "")
    if configured:
        return Path(configured)
    return default_chatgpt_browser_profile_dir()


def open_chatgpt_login_window(env: dict[str, str], url: str | None = None) -> dict[str, Any]:
    login_url = clean_text(url or env.get("CHATGPT_IMAGE_WEB_URL") or "https://chatgpt.com/") or "https://chatgpt.com/"
    browser_path = resolve_chatgpt_browser_path(env)
    profile_dir = storage.ensure_dir(chatgpt_browser_user_data_dir(env))
    if browser_path:
        try:
            subprocess.Popen(
                [
                    browser_path,
                    "--new-window",
                    f"--user-data-dir={profile_dir}",
                    "--window-size=1480,1120",
                    "--window-position=120,80",
                    login_url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "ok": True,
                "url": login_url,
                "browser_path": browser_path,
                "profile_dir": str(profile_dir),
                "launch_mode": "browser-path",
            }
        except Exception:
            pass
    try:
        if os.name == "nt":
            os.startfile(login_url)  # type: ignore[attr-defined]
        else:
            webbrowser.open(login_url, new=1)
    except Exception as exc:
        raise RuntimeError(f"无法打开 ChatGPT 登录页：{exc}") from exc
    return {
        "ok": True,
        "url": login_url,
        "browser_path": browser_path or "",
        "profile_dir": str(profile_dir),
        "launch_mode": "system-default",
    }


def clear_chatgpt_login_state(env: dict[str, str]) -> dict[str, Any]:
    configured_dir = clean_text(env.get("CHATGPT_IMAGE_USER_DATA_DIR") or "")
    profile_dir = chatgpt_browser_user_data_dir(env)
    default_dir = default_chatgpt_browser_profile_dir()
    resolved_profile = profile_dir.resolve()
    resolved_default = default_dir.resolve()
    resolved_config = storage.CONFIG_ROOT.resolve()

    if configured_dir and not (resolved_profile == resolved_default or resolved_config in resolved_profile.parents):
        raise RuntimeError(
            "当前配置了自定义 ChatGPT 自动化登录资料夹。为避免误删你的真实浏览器数据，"
            f"请手动清理这个目录，或先把 CHATGPT_IMAGE_USER_DATA_DIR 留空：{profile_dir}"
        )

    existed = profile_dir.exists()
    removed_files = 0
    if existed:
        for _root, _dirs, files in os.walk(profile_dir):
            removed_files += len(files)

        def onerror(func: Callable[..., Any], path: str, _exc_info: Any) -> None:
            try:
                os.chmod(path, 0o700)
                func(path)
            except Exception as exc:
                raise RuntimeError(f"无法清理 ChatGPT 登录资料夹，请先关闭弹出的 ChatGPT/Chrome 窗口后再试：{path}") from exc

        try:
            shutil.rmtree(profile_dir, onerror=onerror)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"无法清理 ChatGPT 登录资料夹，请先关闭弹出的 ChatGPT/Chrome 窗口后再试：{profile_dir}") from exc

    storage.ensure_dir(profile_dir)
    return {
        "ok": True,
        "existed": existed,
        "removed_files": removed_files,
        "profile_dir": str(profile_dir),
        "message": "ChatGPT 自动化登录状态已清空。下次生图会重新打开登录页。",
    }


def _surface_chatgpt_login(page: Any, env: dict[str, str], log: Callable[[str], None] | None = None) -> None:
    try:
        current_url = clean_text(str(page.url or ""))
    except Exception:
        current_url = ""
    if env_flag(env.get("CHATGPT_IMAGE_HEADLESS")):
        try:
            opened = open_chatgpt_login_window(env, url=current_url or None)
        except Exception as exc:
            if log:
                log(f"[images] 自动打开 ChatGPT 登录页失败：{exc}")
            return
        if log:
            log(f"[images] 已自动打开可见的 ChatGPT 登录页：{opened.get('url')}")
            log("[images] 请先完成登录，再回到短片工坊重试当前图片。")
        return
    with contextlib.suppress(Exception):
        page.bring_to_front()
    if log:
        log("[images] 已切到 ChatGPT 浏览器窗口，请先完成重新登录后再重试。")


def _write_image_bytes_as_png(data: bytes, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if Image is not None:
        try:
            image = Image.open(io.BytesIO(data))
            image.save(output_path, format="PNG")
            return
        except Exception:
            pass
    output_path.write_bytes(data)


def _large_chatgpt_images_script() -> str:
    return """
() => Array.from(document.images)
  .map((img, index) => ({
    index,
    src: img.currentSrc || img.src || "",
    width: img.naturalWidth || img.width || 0,
    height: img.naturalHeight || img.height || 0,
    complete: Boolean(img.complete),
    alt: img.alt || ""
  }))
  .filter((item) => item.complete && item.src && item.width >= 256 && item.height >= 256)
"""


def _chatgpt_login_required(page: Any) -> bool:
    try:
        current_url = clean_text(str(page.url or "")).lower()
    except Exception:
        current_url = ""
    if any(token in current_url for token in ("/auth", "/login", "signin", "session", "verify")):
        return True
    selectors = [
        "button:has-text('登录')",
        "button:has-text('Log in')",
        "button:has-text('Sign in')",
        "a:has-text('登录')",
        "a:has-text('Log in')",
        "a:has-text('Sign in')",
        "button:has-text('Continue with Google')",
        "button:has-text('Continue with Microsoft')",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible(timeout=400):
                return True
        except Exception:
            continue
    try:
        body_text = clean_text(page.locator("body").inner_text(timeout=1200)).lower()
    except Exception:
        body_text = ""
    login_tokens = (
        "log in",
        "sign in",
        "continue with google",
        "continue with microsoft",
        "继续使用 google",
        "继续使用 microsoft",
        "登录",
        "注册",
    )
    return "chatgpt" in body_text and any(token in body_text for token in login_tokens)


def _raise_chatgpt_login_required(page: Any) -> None:
    try:
        current_url = clean_text(str(page.url or ""))
    except Exception:
        current_url = ""
    suffix = f" 当前页面：{current_url}" if current_url else ""
    raise RuntimeError(
        "ChatGPT 登录态已失效，请先重新登录 ChatGPT 后再重试生图。"
        " 如果你当前开的是无头模式，请先切到可见浏览器完成一次登录。"
        + suffix
    )


def _fetch_image_b64_script() -> str:
    return """
async (src) => {
  const response = await fetch(src);
  const blob = await response.blob();
  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return { b64: btoa(binary), type: blob.type || "" };
}
"""


def _find_chatgpt_composer(page: Any, timeout_seconds: float = 180.0) -> tuple[Any, str]:
    selectors = [
        "textarea#prompt-textarea",
        "#prompt-textarea",
        "textarea",
        "div.ProseMirror",
        "[contenteditable='true']",
    ]
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        if _chatgpt_login_required(page):
            _raise_chatgpt_login_required(page)
        for selector in selectors:
            locator = page.locator(selector).last
            try:
                if locator.count() and locator.is_visible(timeout=800):
                    return locator, selector
            except Exception as exc:
                last_error = str(exc)
        page.wait_for_timeout(1200)
    if _chatgpt_login_required(page):
        _raise_chatgpt_login_required(page)
    raise RuntimeError(
        "ChatGPT 网页自动化没有找到输入框。请在弹出的 Chrome 里登录 ChatGPT，确认能正常发送消息后重试。"
        + (f" 最近错误：{last_error}" if last_error else "")
    )


def _fill_chatgpt_composer(
    page: Any,
    prompt: str,
    env: dict[str, str] | None = None,
    log: Callable[[str], None] | None = None,
    timeout_seconds: float = 180.0,
) -> None:
    deadline = time.monotonic() + max(30.0, timeout_seconds)
    last_error = ""
    login_hint_logged = False
    waiting_hint_logged = False
    next_progress_at = 0.0
    while time.monotonic() < deadline:
        try:
            composer, selector = _find_chatgpt_composer(page, timeout_seconds=12.0)
            if selector.startswith("textarea"):
                composer.evaluate(
                    """
(el, text) => {
  el.scrollIntoView({ block: "center", inline: "nearest" });
  el.focus();
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
  if (setter) setter.call(el, text);
  else el.value = text;
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}
""",
                    prompt,
                )
            else:
                composer.evaluate(
                    """
(el, text) => {
  el.scrollIntoView({ block: "center", inline: "nearest" });
  el.focus();
  document.execCommand("selectAll", false, null);
  document.execCommand("insertText", false, text);
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
}
""",
                    prompt,
                )
            return
        except Exception as exc:
            last_error = str(exc)
            login_required = _chatgpt_login_required(page)
            if login_required:
                if env is not None:
                    _surface_chatgpt_login(page, env, log=log)
                if log and not login_hint_logged:
                    log("[images] 检测到 ChatGPT 还没完成登录，正在轮询等待你登录成功后自动继续")
                    login_hint_logged = True
            elif log and not waiting_hint_logged:
                log("[images] ChatGPT 输入框暂时不可编辑，正在轮询等待页面加载完成")
                waiting_hint_logged = True
            if log and time.monotonic() >= next_progress_at:
                remaining = max(0, int(deadline - time.monotonic()))
                log(f"[images] ChatGPT 页面等待中，剩余约 {remaining}s")
                next_progress_at = time.monotonic() + 20.0
            page.wait_for_timeout(1800)
    if _chatgpt_login_required(page):
        raise RuntimeError(
            "ChatGPT 登录等待超时：请确认已在弹出的 Chrome 中完成登录，并能正常打开会话输入框后重试。"
        )
    raise RuntimeError(
        "ChatGPT 输入框长时间不可编辑，请确认已登录且页面完全加载后重试。"
        + (f" 最近错误：{last_error}" if last_error else "")
    )


def _click_chatgpt_send(page: Any) -> None:
    selectors = [
        "button[data-testid='send-button']",
        "button[aria-label*='Send']",
        "button[aria-label*='发送']",
        "button:has-text('发送')",
        "button:has-text('Send')",
    ]
    for _ in range(30):
        for selector in selectors:
            button = page.locator(selector).last
            try:
                if button.count() and button.is_visible(timeout=500) and button.is_enabled(timeout=500):
                    button.click(timeout=5000)
                    return
            except Exception:
                continue
        page.wait_for_timeout(500)
    page.keyboard.press("Enter")


def _save_latest_chatgpt_image(
    page: Any,
    before_indexes: set[int],
    output_path: Path,
    timeout_seconds: float,
    log: Callable[[str], None] | None = None,
) -> Path:
    deadline = time.monotonic() + timeout_seconds
    candidate: dict[str, Any] | None = None
    next_progress_at = 0.0
    last_error = ""
    while time.monotonic() < deadline:
        try:
            images = page.evaluate(_large_chatgpt_images_script())
        except Exception as exc:
            last_error = str(exc)
            raise RuntimeError(
                "ChatGPT 浏览器连接中断：请确认弹出的 Chrome 窗口没有被关闭，账号没有跳到重新登录页。"
                + (f" 最近错误：{last_error}" if last_error else "")
            ) from exc
        if isinstance(images, list):
            new_images = [
                item
                for item in images
                if isinstance(item, dict) and int(item.get("index", -1)) not in before_indexes
            ]
            if new_images:
                candidate = new_images[-1]
                break
            if images:
                candidate = images[-1]
        if log and time.monotonic() >= next_progress_at:
            remaining = max(0, int(deadline - time.monotonic()))
            log(f"[images] ChatGPT 图片生成等待中，剩余约 {remaining}s")
            next_progress_at = time.monotonic() + 20.0
        page.wait_for_timeout(2500)
    if not candidate:
        raise RuntimeError("ChatGPT 已发送提示词，但没有检测到新生成图片。请确认账号具备生图能力后重试。")

    src = str(candidate.get("src") or "")
    index = int(candidate.get("index", -1))
    if src:
        try:
            payload = page.evaluate(_fetch_image_b64_script(), src)
            if isinstance(payload, dict) and payload.get("b64"):
                _write_image_bytes_as_png(base64.b64decode(str(payload["b64"])), output_path)
                return output_path
        except Exception:
            pass

    if index >= 0:
        image_locator = page.locator("img").nth(index)
        image_locator.screenshot(path=str(output_path), timeout=30000)
        return output_path
    raise RuntimeError("检测到 ChatGPT 图片，但无法下载或截图保存。")


def chatgpt_delete_after_save_enabled(env: dict[str, str]) -> bool:
    value = clean_text(env.get("CHATGPT_IMAGE_DELETE_AFTER_SAVE") or "")
    return True if not value else env_flag(value)


def _click_chatgpt_text_action(page: Any, labels: list[str], timeout_ms: int = 2500) -> str:
    pattern = re.compile("|".join(re.escape(label) for label in labels), re.IGNORECASE)
    locators = []
    for role in ("menuitem", "button"):
        locators.append(page.get_by_role(role, name=pattern).last)
    for label in labels:
        locators.extend(
            [
                page.locator(f"button:has-text('{label}')").last,
                page.locator(f"[role='menuitem']:has-text('{label}')").last,
                page.locator(f"text={label}").last,
            ]
        )
    for locator in locators:
        try:
            if locator.count() and locator.is_visible(timeout=400):
                text = clean_text(locator.inner_text(timeout=600))
                locator.click(timeout=timeout_ms)
                return text or labels[0]
        except Exception:
            continue
    raise RuntimeError(f"没有找到可点击的按钮：{'/'.join(labels)}")


def _open_chatgpt_current_conversation_menu(page: Any) -> str:
    result = page.evaluate(
        """
() => {
  const isVisible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  };
  const buttonText = (button) => [
    button.innerText || "",
    button.getAttribute("aria-label") || "",
    button.getAttribute("title") || "",
    button.dataset?.testid || ""
  ].join(" ").trim();
  const clickMenuButtonNear = (root) => {
    let node = root;
    for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
      const buttons = Array.from(node.querySelectorAll("button")).filter((button) => {
        if (!isVisible(button) || button.disabled) return false;
        const text = buttonText(button).toLowerCase();
        return text.includes("more")
          || text.includes("options")
          || text.includes("menu")
          || text.includes("conversation")
          || text.includes("更多")
          || text.includes("选项")
          || text.includes("操作")
          || text.includes("菜单")
          || text.includes("对话");
      });
      const allButtons = Array.from(node.querySelectorAll("button")).filter((button) => isVisible(button) && !button.disabled);
      const target = buttons[buttons.length - 1] || allButtons[allButtons.length - 1];
      if (target) {
        target.scrollIntoView({ block: "center", inline: "nearest" });
        target.click();
        return { ok: true, text: buttonText(target) };
      }
    }
    return { ok: false, reason: "nearby menu button not found" };
  };
  const pathMatch = location.pathname.match(/\\/c\\/([^/?#]+)/);
  const currentId = pathMatch ? pathMatch[1] : "";
  const candidates = [];
  if (currentId && window.CSS && CSS.escape) {
    candidates.push(...document.querySelectorAll(`a[href*="/c/${CSS.escape(currentId)}"]`));
  }
  candidates.push(...document.querySelectorAll('nav a[aria-current="page"][href*="/c/"], aside a[aria-current="page"][href*="/c/"]'));
  for (const selected of document.querySelectorAll('nav [aria-selected="true"], aside [aria-selected="true"], nav [data-active="true"], aside [data-active="true"]')) {
    candidates.push(...selected.querySelectorAll('a[href*="/c/"]'));
  }
  for (const link of candidates) {
    if (!isVisible(link)) continue;
    const clicked = clickMenuButtonNear(link);
    if (clicked.ok) return clicked;
  }
  return { ok: false, reason: currentId ? `conversation ${currentId} not found in sidebar` : "current chat has no /c/ id yet" };
}
"""
    )
    if isinstance(result, dict) and result.get("ok"):
        return clean_text(str(result.get("text") or ""))
    reason = ""
    if isinstance(result, dict):
        reason = clean_text(str(result.get("reason") or ""))
    raise RuntimeError(reason or "没有打开当前会话菜单")


def _confirm_chatgpt_conversation_delete(page: Any) -> bool:
    pattern = re.compile("删除|Delete", re.IGNORECASE)
    containers = [
        page.get_by_role("dialog").last,
        page.get_by_role("alertdialog").last,
        page.locator("[role='dialog']").last,
        page.locator("[role='alertdialog']").last,
    ]
    for container in containers:
        try:
            if not container.count() or not container.is_visible(timeout=500):
                continue
            actions = [
                container.get_by_role("button", name=pattern).last,
                container.locator("button:has-text('删除')").last,
                container.locator("button:has-text('Delete')").last,
            ]
            for action in actions:
                try:
                    if action.count() and action.is_visible(timeout=400) and action.is_enabled(timeout=400):
                        action.click(timeout=3000)
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def cleanup_chatgpt_conversation_after_save(page: Any, env: dict[str, str], log: Callable[[str], None] | None = None) -> None:
    if not chatgpt_delete_after_save_enabled(env):
        return
    try:
        page.wait_for_timeout(800)
        _open_chatgpt_current_conversation_menu(page)
        page.wait_for_timeout(500)
        _click_chatgpt_text_action(page, ["删除", "Delete"])
        page.wait_for_timeout(700)
        if not _confirm_chatgpt_conversation_delete(page):
            with contextlib.suppress(Exception):
                page.keyboard.press("Enter")
        page.wait_for_timeout(1200)
        if log:
            log("[images] 已删除本次 ChatGPT 生图会话，避免左侧历史列表堆积")
    except Exception as exc:
        if log:
            log(f"[images] ChatGPT 会话自动删除未完成：{exc}；图片已保存，不影响后续流程")


def close_chatgpt_browser_context(context: Any, log: Callable[[str], None] | None = None) -> None:
    closed = False
    try:
        for page in list(getattr(context, "pages", []) or []):
            with contextlib.suppress(Exception):
                page.close()
                closed = True
    except Exception:
        pass
    try:
        context.close()
        closed = True
    except Exception as exc:
        if log:
            log(f"[images] ChatGPT 浏览器关闭时返回了非致命错误：{exc}")
    if log and closed:
        log("[images] 已关闭本次 ChatGPT 生图窗口")


def generate_chatgpt_web_auto_image(
    prompt: str,
    output_path: Path,
    size: str,
    purpose: str,
    env: dict[str, str],
    log: Callable[[str], None] | None = None,
) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("ChatGPT 网页自动化需要 playwright，请先运行 pip install playwright。") from exc

    clean_prompt = build_chatgpt_handoff_prompt(prompt, size, purpose)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    storage.write_text(output_path.with_suffix(".md"), normalize_image_prompt(prompt) + "\n")

    browser_path = resolve_chatgpt_browser_path(env)
    profile_dir = storage.ensure_dir(chatgpt_browser_user_data_dir(env))
    chatgpt_url = clean_text(env.get("CHATGPT_IMAGE_WEB_URL") or "https://chatgpt.com/") or "https://chatgpt.com/"
    timeout_seconds = chatgpt_image_wait_seconds(env)
    if log:
        log(f"[images] ChatGPT 网页自动化打开浏览器 profile={profile_dir}")
        log("[images] 第一次使用请在弹出的 Chrome 中登录 ChatGPT；登录后任务会继续尝试。")

    with sync_playwright() as playwright:
        launch_kwargs: dict[str, Any] = {
            "headless": env_flag(env.get("CHATGPT_IMAGE_HEADLESS")),
            "accept_downloads": True,
            "viewport": {"width": 1440, "height": 1100},
            "locale": "zh-CN",
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if browser_path:
            launch_kwargs["executable_path"] = browser_path
        context = playwright.chromium.launch_persistent_context(str(profile_dir), **launch_kwargs)
        saved_ok = False
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(chatgpt_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            before_images = page.evaluate(_large_chatgpt_images_script())
            before_indexes = {
                int(item.get("index", -1))
                for item in before_images
                if isinstance(item, dict) and int(item.get("index", -1)) >= 0
            } if isinstance(before_images, list) else set()
            _fill_chatgpt_composer(
                page,
                clean_prompt,
                env=env,
                log=log,
                timeout_seconds=min(chatgpt_image_wait_seconds(env), 300.0),
            )
            _click_chatgpt_send(page)
            if log:
                log("[images] ChatGPT 提示词已发送，正在等待生成图片")
            result = _save_latest_chatgpt_image(page, before_indexes, output_path, timeout_seconds, log=log)
            saved_ok = True
            if log:
                log(f"[images] ChatGPT 网页自动化已保存 {output_path.name}")
            cleanup_chatgpt_conversation_after_save(page, env, log=log)
            return result
        finally:
            close_chatgpt_browser_context(context, log=log if saved_ok else None)


def prepare_chatgpt_handoff_request(
    prompt: str,
    output_path: Path,
    size: str,
    purpose: str,
    env: dict[str, str],
    template: dict[str, Any] | None = None,
) -> dict[str, Any]:
    template_stub = dict(template or {})
    template_stub.update(
        {
            "brand_name": template_stub.get("brand_name", ""),
            "cover_footnote_line_1": template_stub.get("cover_footnote_line_1", ""),
            "cover_footnote_line_2": template_stub.get("cover_footnote_line_2", ""),
        }
    )
    prepared_prompt = optimize_visual_generation_prompt(prompt, template_stub, purpose)
    handoff_prompt = build_chatgpt_handoff_prompt(prepared_prompt, size, purpose)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    storage.write_text(output_path.with_suffix(".md"), prepared_prompt + "\n")
    page_path = write_chatgpt_handoff_page(handoff_prompt, output_path, size, purpose, env)
    open_chatgpt_handoff(page_path, env, handoff_prompt)
    return {
        "needs_handoff": True,
        "page_path": str(page_path),
        "output_path": str(output_path.resolve()),
        "prompt": prepared_prompt,
    }


def apiyi_image_available(env: dict[str, str]) -> bool:
    api_key = (env.get("APIYI_API_KEY", "") or "").strip()
    base_url = normalize_openai_compatible_base_url(env.get("APIYI_BASE_URL", "") or "")
    return bool(api_key and base_url)


def third_party_image_available(env: dict[str, str]) -> bool:
    api_key = (env.get("THIRD_PARTY_IMAGE_API_KEY", "") or "").strip()
    base_url = normalize_openai_compatible_base_url(env.get("THIRD_PARTY_IMAGE_BASE_URL", "") or "")
    return bool(api_key and base_url)


def resolve_image_provider(env: dict[str, str]) -> dict[str, str]:
    preference = clean_text(env.get("IMAGE_PROVIDER") or "auto").lower() or "auto"
    prefer_apiyi = env_flag(env.get("APIYI_IMAGE_REPLACE_ARK"))
    has_apiyi = apiyi_image_available(env)
    has_third_party = third_party_image_available(env)
    has_ark = bool((env.get("ARK_API_KEY", "") or "").strip())

    if preference in {"chatgpt_web_auto", "chatgpt-auto", "chatgpt_auto", "chatgpt_browser"}:
        return {"key": "chatgpt_web_auto", "label": "ChatGPT 网页自动化", "model": "chatgpt-account"}
    if preference in {"chatgpt", "chatgpt_handoff", "chatgpt-web", "chatgpt_web"}:
        return {"key": "chatgpt_handoff", "label": "ChatGPT 网页/桌面接力", "model": "chatgpt-account"}
    if preference in {"third_party", "third-party", "custom_openai", "custom-openai", "openai_custom", "openai-custom"}:
        if not has_third_party:
            raise RuntimeError("已选择第三方 OpenAI 兼容出图，但 THIRD_PARTY_IMAGE_API_KEY 或 THIRD_PARTY_IMAGE_BASE_URL 还没填完整。")
        return {"key": "third_party", "label": "第三方 OpenAI 兼容文生图", "model": resolve_third_party_image_model(env)}
    if preference in {"apiyi"}:
        if not has_apiyi:
            raise RuntimeError("已选择 OpenAI 兼容/API易出图，但 APIYI_API_KEY 或 APIYI_BASE_URL 还没填完整。")
        return {"key": "apiyi", "label": "API易 / OpenAI 兼容文生图", "model": resolve_apiyi_image_model(env)}
    if preference in {"openai_compatible", "openai-compatible"}:
        if has_third_party:
            return {"key": "third_party", "label": "第三方 OpenAI 兼容文生图", "model": resolve_third_party_image_model(env)}
        if has_apiyi:
            return {"key": "apiyi", "label": "API易 / OpenAI 兼容文生图", "model": resolve_apiyi_image_model(env)}
        raise RuntimeError("已选择 OpenAI 兼容出图，但第三方/APIYI 配置都不完整。")
    if preference in {"ark", "seedream", "doubao"}:
        if not has_ark:
            raise RuntimeError("已选择火山方舟出图，但 ARK_API_KEY 还没填写。")
        return {"key": "ark", "label": "火山方舟 Seedream", "model": resolve_ark_image_model(env)}

    if prefer_apiyi:
        if not has_apiyi:
            raise RuntimeError("已开启 OpenAI 兼容出图，但 APIYI_API_KEY 或 APIYI_BASE_URL 还没填完整。")
        return {"key": "apiyi", "label": "API易 / OpenAI 兼容文生图", "model": resolve_apiyi_image_model(env)}
    if has_ark:
        return {"key": "ark", "label": "火山方舟 Seedream", "model": resolve_ark_image_model(env)}
    if has_third_party:
        return {"key": "third_party", "label": "第三方 OpenAI 兼容文生图", "model": resolve_third_party_image_model(env)}
    if has_apiyi:
        return {"key": "apiyi", "label": "API易 / OpenAI 兼容文生图", "model": resolve_apiyi_image_model(env)}
    raise RuntimeError("未配置可用的文生图服务。请先配置方舟密钥，或填写 OpenAI 兼容文生图配置。")


def resolve_image_provider_queue(env: dict[str, str]) -> list[dict[str, str]]:
    """Return image providers in failover order.

    auto_no_apiyi intentionally skips third-party/OpenAI-compatible accounts so
    image generation never waits on those services. Explicit IMAGE_PROVIDER
    values are strict and do not silently fall back to another provider.
    """
    preference = clean_text(env.get("IMAGE_PROVIDER") or "auto").lower() or "auto"
    has_ark = bool((env.get("ARK_API_KEY", "") or "").strip())
    has_apiyi = apiyi_image_available(env)
    has_third_party = third_party_image_available(env)
    allow_chatgpt_auto = not env.get("CHATGPT_IMAGE_AUTO_OPEN") or env_flag(env.get("CHATGPT_IMAGE_AUTO_OPEN"))

    def record(key: str) -> dict[str, str]:
        if key == "ark":
            return {"key": "ark", "label": "火山方舟 Seedream", "model": resolve_ark_image_model(env)}
        if key == "apiyi":
            return {"key": "apiyi", "label": "API易 / OpenAI 兼容文生图", "model": resolve_apiyi_image_model(env)}
        if key == "third_party":
            return {"key": "third_party", "label": "第三方 OpenAI 兼容文生图", "model": resolve_third_party_image_model(env)}
        if key == "chatgpt_web_auto":
            return {"key": "chatgpt_web_auto", "label": "ChatGPT 网页自动化", "model": "chatgpt-account"}
        if key == "chatgpt_handoff":
            return {"key": "chatgpt_handoff", "label": "ChatGPT 网页/桌面接力", "model": "chatgpt-account"}
        raise RuntimeError(f"未知图片生成供应商：{key}")

    if preference in {"auto_no_apiyi", "no_apiyi", "auto_without_apiyi", "skip_apiyi"}:
        providers: list[dict[str, str]] = []
        if has_ark:
            providers.append(record("ark"))
        if allow_chatgpt_auto:
            providers.append(record("chatgpt_web_auto"))
        if providers:
            return providers
        raise RuntimeError("未配置可用的非第三方图片生成渠道。")

    if preference in {"ark", "seedream", "doubao"}:
        if not has_ark:
            raise RuntimeError("已选择火山方舟出图，但 ARK_API_KEY 还没填写。")
        return [record("ark")]

    if preference in {"chatgpt_web_auto", "chatgpt-auto", "chatgpt_auto", "chatgpt_browser"}:
        return [record("chatgpt_web_auto")]
    if preference in {"chatgpt", "chatgpt_handoff", "chatgpt-web", "chatgpt_web"}:
        return [record("chatgpt_handoff")]
    if preference in {"third_party", "third-party", "custom_openai", "custom-openai", "openai_custom", "openai-custom"}:
        if not has_third_party:
            raise RuntimeError("已选择第三方 OpenAI 兼容出图，但第三方配置不完整。")
        return [record("third_party")]
    if preference in {"apiyi"}:
        if not has_apiyi:
            raise RuntimeError("已选择 APIYI，但 APIYI 配置不完整。")
        return [record("apiyi")]
    if preference in {"openai_compatible", "openai-compatible"}:
        if has_third_party:
            return [record("third_party")]
        if has_apiyi:
            return [record("apiyi")]
        raise RuntimeError("已选择 OpenAI 兼容出图，但第三方/APIYI 配置都不完整。")

    return [resolve_image_provider(env)]


def describe_image_provider_queue(env: dict[str, str]) -> str:
    providers = resolve_image_provider_queue(env)
    preference = clean_text(env.get("IMAGE_PROVIDER") or "auto").lower() or "auto"
    labels = " -> ".join(
        f"{provider['label']}({provider.get('model') or 'default'})"
        for provider in providers
    )
    if preference in {"auto", "auto_no_apiyi", "no_apiyi", "auto_without_apiyi", "skip_apiyi"}:
        return f"自动选择队列：{labels}"
    return f"已锁定图片入口：{labels}；失败将直接报错，不自动切换"


def openai_compatible_image_config(env: dict[str, str], provider_key: str) -> dict[str, Any]:
    if provider_key == "third_party":
        return {
            "key": "third_party",
            "label": "第三方 OpenAI 兼容文生图",
            "api_key": (env.get("THIRD_PARTY_IMAGE_API_KEY", "") or "").strip(),
            "base_url": normalize_openai_compatible_base_url(env.get("THIRD_PARTY_IMAGE_BASE_URL", "") or ""),
            "model": resolve_third_party_image_model(env),
            "timeout": third_party_image_timeout(env),
            "retries": third_party_image_retries(env),
        }
    return {
        "key": "apiyi",
        "label": "API易 / OpenAI 兼容文生图",
        "api_key": (env.get("APIYI_API_KEY", "") or "").strip(),
        "base_url": normalize_openai_compatible_base_url(env.get("APIYI_BASE_URL", "") or ""),
        "model": resolve_apiyi_image_model(env),
        "timeout": apiyi_image_timeout(env),
        "retries": apiyi_image_retries(env),
    }


def generate_openai_compatible_image(
    prompt: str,
    output_path: Path,
    size: str,
    purpose: str,
    env: dict[str, str],
    log: Callable[[str], None] | None = None,
    provider_key: str = "apiyi",
) -> Path:
    del purpose
    config = openai_compatible_image_config(env, provider_key)
    api_key = str(config["api_key"])
    base_url = str(config["base_url"])
    label = str(config["label"])
    if not api_key:
        raise RuntimeError(f"{label} API Key 未配置，无法调用 OpenAI 兼容文生图。")
    if not base_url:
        raise RuntimeError(f"{label} Base URL 未配置，无法调用 OpenAI 兼容文生图。")

    model = str(config["model"])
    clean_prompt = apply_apiyi_prompt_conventions(prompt, size)
    payload: dict[str, Any] = {
        "model": model,
        "prompt": clean_prompt,
        "response_format": "b64_json",
    }
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    last_exc: RuntimeError | None = None
    request_timeout = float(config["timeout"])
    max_retries = int(config["retries"])
    endpoint = f"{base_url}/images/generations"
    for attempt in range(1, max_retries + 1):
        payload["response_format"] = "b64_json"
        try:
            started = time.monotonic()
            if log:
                log(
                    f"[images] {label} POST /v1/images/generations model={model} "
                    f"response_format=b64_json attempt={attempt}/{max_retries} timeout={request_timeout:.0f}s"
                )
            try:
                response = _request_provider_json(
                    "POST",
                    endpoint,
                    headers,
                    payload=payload,
                    timeout=request_timeout,
                )
            except RuntimeError as exc:
                message = str(exc).lower()
                if "response_format" in message or "b64_json" in message:
                    payload["response_format"] = "url"
                    if log:
                        log(f"[images] {label} b64_json response_format not accepted; retrying same attempt with url")
                    response = _request_provider_json(
                        "POST",
                        endpoint,
                        headers,
                        payload=payload,
                        timeout=request_timeout,
                    )
                else:
                    raise
            if log:
                log(f"[images] {label} response received in {time.monotonic() - started:.1f}s; downloading/decoding image")
            image_data = _extract_provider_image_bytes(response, timeout=request_timeout)
            output_path.write_bytes(image_data)
            storage.write_text(output_path.with_suffix(".md"), clean_prompt + "\n")
            if log:
                log(f"[images] {label} saved {output_path.name} ({len(image_data) / 1048576.0:.1f} MB)")
            return output_path
        except RuntimeError as exc:
            last_exc = exc
            if log:
                elapsed = time.monotonic() - started if "started" in locals() else 0.0
                log(f"[images] {label} attempt {attempt}/{max_retries} failed after {elapsed:.1f}s: {exc}")
            if attempt >= max_retries:
                break
            delay = min(6, attempt * 2)
            if log:
                log(f"[images] {label} retrying in {delay}s")
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("OpenAI 兼容文生图调用失败。")


def generate_configured_image(
    prompt: str,
    output_path: Path,
    size: str,
    purpose: str,
    env: dict[str, str],
    log: Callable[[str], None] | None = None,
    template: dict[str, Any] | None = None,
) -> Path:
    providers = resolve_image_provider_queue(env)
    template_stub = dict(template or {})
    template_stub.update(
        {
            "brand_name": template_stub.get("brand_name", ""),
            "cover_footnote_line_1": template_stub.get("cover_footnote_line_1", ""),
            "cover_footnote_line_2": template_stub.get("cover_footnote_line_2", ""),
        }
    )
    last_error: Exception | None = None

    for provider_index, provider in enumerate(providers, start=1):
        audit_report: dict[str, Any] | None = None
        last_path: Path | None = None
        if log and len(providers) > 1:
            log(f"[images] provider {provider_index}/{len(providers)} -> {provider['label']}")
        try:
            for attempt in range(1, IMAGE_PROMPT_REWRITE_ATTEMPTS + 1):
                prepared_prompt = optimize_visual_generation_prompt(
                    prompt,
                    template_stub,
                    purpose,
                    attempt=attempt,
                    audit_reasons=audit_report.get("reasons", []) if audit_report else None,
                )
                display_name = output_path.name
                if display_name.startswith(".") and ".gen-" in display_name:
                    display_name = display_name[1:].split(".gen-", 1)[0] + output_path.suffix
                if log:
                    log(
                        f"[images] 使用 {provider['label']} 生成 {display_name}"
                        f"（model={provider.get('model') or 'default'}，attempt={attempt}/{IMAGE_PROMPT_REWRITE_ATTEMPTS}）"
                    )
                if provider["key"] == "chatgpt_web_auto":
                    last_path = generate_chatgpt_web_auto_image(prepared_prompt, output_path, size, purpose, env, log=log)
                elif provider["key"] == "chatgpt_handoff":
                    last_path = generate_chatgpt_handoff_image(prepared_prompt, output_path, size, purpose, env, log=log)
                elif provider["key"] in {"apiyi", "third_party"}:
                    last_path = generate_openai_compatible_image(
                        prepared_prompt,
                        output_path,
                        size,
                        purpose,
                        env,
                        log=log,
                        provider_key=provider["key"],
                    )
                else:
                    last_path = generate_ark_image(prepared_prompt, output_path, size, purpose, env)

                audit_report = audit_generated_image(last_path, size, purpose)
                audit_report["attempt"] = attempt
                audit_report["provider"] = provider["key"]
                audit_report["provider_label"] = provider["label"]
                audit_report["prompt"] = prepared_prompt
                storage.write_text(output_path.with_suffix(".md"), prepared_prompt + "\n")
                storage.write_json(output_path.with_suffix(".audit.json"), audit_report)

                if audit_report.get("ok"):
                    return last_path
                if attempt >= IMAGE_PROMPT_REWRITE_ATTEMPTS:
                    break

            if last_path is None:
                raise RuntimeError("图片生成失败，未得到任何输出。")
            if audit_report and audit_report.get("severity") == "hard":
                reasons = ", ".join(audit_report.get("reasons", []))
                raise RuntimeError(f"图片生成后自检未通过：{reasons}")
            return last_path
        except Exception as exc:
            last_error = exc
            if output_path.name.startswith("."):
                _cleanup_generated_tmp(output_path)
            if log:
                if provider_index < len(providers):
                    log(f"[images] {provider['label']} 失败：{exc}；切换到下一个图片入口")
                else:
                    log(f"[images] {provider['label']} 失败：{exc}")
            if provider_index < len(providers):
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("未配置可用的图片生成渠道。")


def find_scene_image_paths(project_id: int) -> list[Path]:
    scene_dir = storage.project_file(project_id, "scenes")
    paths: list[Path] = []
    if not scene_dir.exists():
        return paths
    for path in sorted(scene_dir.iterdir()):
        if not path.is_file():
            continue
        if not re.fullmatch(r"s_\d+", path.stem):
            continue
        if path.suffix.lower() not in RASTER_IMAGE_SUFFIXES:
            continue
        paths.append(path)
    return paths


def find_cover_path(project_id: int) -> Path | None:
    cover_dir = storage.project_file(project_id, "covers")
    for name in (
        "cover_landscape.png",
        "cover_landscape.jpg",
        "cover_landscape.jpeg",
        "cover_story.png",
        "cover_story.jpg",
        "cover_story.jpeg",
    ):
        candidate = cover_dir / name
        if candidate.exists():
            return candidate
    scene_paths = find_scene_image_paths(project_id)
    return scene_paths[0] if scene_paths else None


def find_bgm_path(project_id: int, template_key: str | None = None) -> Path | None:
    project_candidate = storage.project_file(project_id, "bgm.mp3")
    if project_candidate.exists():
        return project_candidate
    if template_key:
        template_candidate = storage.TEMPLATES_ROOT / template_key / "bgm.mp3"
        if template_candidate.exists():
            return template_candidate
    return None


def ffmpeg_binary() -> Path:
    candidate = workspace_root() / "_analysis" / "awesome_app_install" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if candidate.exists():
        return candidate
    return Path("ffmpeg")


def ffprobe_binary() -> Path:
    candidate = workspace_root() / "_analysis" / "awesome_app_install" / "ffmpeg" / "bin" / "ffprobe.exe"
    if candidate.exists():
        return candidate
    return Path("ffprobe")


def probe_media_duration(media_path: Path) -> float:
    result = subprocess.run(
        [
            str(ffprobe_binary()),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=60,
    )
    try:
        return float((result.stdout or "0").strip() or "0")
    except ValueError:
        return 0.0


def probe_audio_duration(audio_path: Path) -> float:
    return probe_media_duration(audio_path)


def probe_stream_start_time(media_path: Path, stream_selector: str) -> float:
    result = subprocess.run(
        [
            str(ffprobe_binary()),
            "-v",
            "error",
            "-select_streams",
            stream_selector,
            "-show_entries",
            "stream=start_time",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=60,
    )
    try:
        return float((result.stdout or "0").strip() or "0")
    except ValueError:
        return 0.0


def normalize_media_timeline(output_path: Path) -> None:
    video_start = probe_stream_start_time(output_path, "v:0")
    audio_start = probe_stream_start_time(output_path, "a:0")
    if abs(video_start) < 0.05 and abs(audio_start) < 0.05:
        return

    with tempfile.TemporaryDirectory(prefix="svs-retime-") as temp_dir_name:
        temp_output = Path(temp_dir_name) / output_path.name
        cmd = [
            str(ffmpeg_binary()),
            "-y",
            "-i",
            str(output_path),
            "-vf",
            "setpts=PTS-STARTPTS",
            "-af",
            "asetpts=PTS-STARTPTS",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(temp_output),
        ]
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=1800,
        )
        temp_output.replace(output_path)


def write_shifted_srt(source_path: Path, target_path: Path, offset_ms: int) -> Path:
    entries = load_srt_entries(source_path)
    if not entries or offset_ms == 0:
        return source_path
    shifted: list[dict[str, Any]] = []
    for entry in entries:
        start_ms = max(0, int(entry.get("start_ms", 0) or 0) + offset_ms)
        end_ms = max(start_ms + 1, int(entry.get("end_ms", 0) or 0) + offset_ms)
        shifted.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": clean_text(str(entry.get("text", ""))),
            }
        )
    write_srt_entries(target_path, shifted)
    return target_path


def subtitle_end_duration(subtitle_path: Path | None) -> float | None:
    if not subtitle_path or not subtitle_path.exists():
        return None
    entries = load_srt_entries(subtitle_path)
    if not entries:
        return None
    end_ms = max(int(item.get("end_ms", 0) or 0) for item in entries)
    if end_ms <= 0:
        return None
    return end_ms / 1000.0


def load_timeline_durations(project_id: int, scene_count: int) -> tuple[float, list[float], float] | None:
    timeline_path = storage.project_file(project_id, "audio/scene_timeline.json")
    if not timeline_path.exists():
        return None
    data = storage.read_json(timeline_path, {})
    if not isinstance(data, dict):
        return None
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != scene_count or not scenes:
        return None
    try:
        audio_ms = int(data.get("audio_duration_ms", 0) or 0)
        cover_ms = int(data.get("cover_duration_ms", scenes[0].get("start_ms", 0)) or 0)
        last_end_ms = int(scenes[-1].get("end_ms", 0) or 0)
        scene_durations = []
        previous_end = cover_ms
        for scene in scenes:
            start_ms = int(scene.get("start_ms", 0) or 0)
            end_ms = int(scene.get("end_ms", 0) or 0)
            if end_ms <= start_ms or start_ms < previous_end:
                return None
            scene_durations.append((end_ms - start_ms) / 1000.0)
            previous_end = end_ms
        outro_ms = max(0, int(data.get("outro_duration_ms", 0) or 0))
        if outro_ms == 0 and audio_ms > last_end_ms:
            outro_ms = audio_ms - last_end_ms
        return cover_ms / 1000.0, scene_durations, outro_ms / 1000.0
    except Exception:
        return None


def expected_video_duration(
    project_id: int,
    scene_count: int,
    audio_path: Path,
    subtitle_path: Path | None,
) -> float:
    candidates: list[float] = []
    audio_duration = probe_audio_duration(audio_path)
    if audio_duration > 0:
        candidates.append(audio_duration)

    subtitle_duration = subtitle_end_duration(subtitle_path)
    if subtitle_duration is not None and subtitle_duration > 0:
        candidates.append(subtitle_duration + SUBTITLE_END_PADDING_SECONDS)

    timing = load_timeline_durations(project_id, scene_count)
    if timing:
        cover_duration, scene_durations, outro_duration = timing
        candidates.append(cover_duration + sum(scene_durations) + outro_duration)

    return max(candidates, default=0.0)


def video_duration_tolerance_seconds(expected_duration: float) -> float:
    if expected_duration <= 0:
        return ORIGINAL_VIDEO_DURATION_TOLERANCE_SECONDS
    return max(2.5, min(8.0, max(expected_duration * 0.015, ORIGINAL_VIDEO_DURATION_TOLERANCE_SECONDS)))


def ensure_video_duration_matches(output_path: Path, expected_duration: float) -> float:
    if expected_duration <= 0:
        return probe_media_duration(output_path)
    actual_duration = probe_media_duration(output_path)
    tolerance = video_duration_tolerance_seconds(expected_duration)
    delta = actual_duration - expected_duration
    if actual_duration <= 0:
        raise RuntimeError(f"无法读取成片时长：{output_path}")
    if abs(delta) > tolerance:
        direction = "过长" if delta > 0 else "过短"
        raise RuntimeError(
            f"原版 composer 输出时长{direction}：预期约 {expected_duration:.1f}s，实际 {actual_duration:.1f}s，偏差 {delta:+.1f}s"
        )
    return actual_duration


def ffmpeg_concat_quote(path: Path) -> str:
    return path.resolve().as_posix().replace("'", r"'\''")


def ffmpeg_subtitle_path(path: Path) -> str:
    return path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")


def write_concat_list(path: Path, entries: list[tuple[Path, float]]) -> None:
    lines = ["ffconcat version 1.0"]
    for image_path, duration in entries:
        lines.append(f"file '{ffmpeg_concat_quote(image_path)}'")
        lines.append(f"duration {max(0.04, duration):.3f}")
    if entries:
        lines.append(f"file '{ffmpeg_concat_quote(entries[-1][0])}'")
    storage.write_text(path, "\n".join(lines) + "\n")


def load_scene_plan_entries(project_id: int) -> list[dict[str, Any]]:
    plan_path = storage.project_file(project_id, "audio/scene_plan.json")
    if not plan_path.exists():
        return []
    data = storage.read_json(plan_path, {})
    scenes = data.get("scenes") if isinstance(data, dict) else []
    if not isinstance(scenes, list):
        return []
    return [item for item in scenes if isinstance(item, dict)]


def resolve_video_transition_recipe(label: str, pair_index: int) -> tuple[str, float]:
    token = clean_text(label).lower()
    if "match_cut" in token or "push" in token:
        return ("slideleft" if pair_index % 2 else "slideright", 0.52)
    if "soft_fade" in token:
        return ("fade", 0.60)
    if "crossfade" in token:
        return ("fade", 0.36)
    if "hard_cut" in token:
        return ("fade", 0.28)
    return ("fade", VIDEO_DEFAULT_TRANSITION_SECONDS)


def clamp_video_transition_duration(requested: float, previous_visible: float, current_visible: float) -> float:
    max_allowed = min(
        max(previous_visible - 0.10, 0.0),
        max(current_visible - 0.10, 0.0),
        min(previous_visible, current_visible) * 0.35,
    )
    if max_allowed <= 0:
        return 0.0
    duration = min(requested, max_allowed)
    if duration < VIDEO_MIN_TRANSITION_SECONDS and max_allowed >= VIDEO_MIN_TRANSITION_SECONDS:
        duration = VIDEO_MIN_TRANSITION_SECONDS
    return max(0.0, duration)


def zoompan_motion_expressions(motion: str, frames: int) -> tuple[str, str, str]:
    progress = f"(on/{max(frames - 1, 1)})"
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    token = clean_text(motion)
    if token == "slow_pan_left_to_right":
        return "1.12", f"(iw-iw/zoom)*{progress}", center_y
    if token == "slow_pan_top_to_bottom":
        return "1.10", center_x, f"(ih-ih/zoom)*{progress}"
    if token == "micro_zoom_then_hold":
        hold_frame = max(1, int(frames * 0.45))
        return f"if(lte(on,{hold_frame}),min(1+on*0.0011,1.08),1.08)", center_x, center_y
    if token == "quick_push_in":
        return "min(max(zoom,pzoom)+0.0019,1.18)", center_x, center_y
    if token == "slow_push_in":
        return "min(max(zoom,pzoom)+0.0013,1.15)", center_x, center_y
    if token == "gentle_push_in":
        return "min(max(zoom,pzoom)+0.0010,1.12)", center_x, center_y
    if token == "ken_burns_subtle":
        return (
            "min(max(zoom,pzoom)+0.0009,1.10)",
            f"(iw-iw/zoom)*(0.44+0.08*{progress})",
            f"(ih-ih/zoom)*(0.52-0.05*{progress})",
        )
    return "min(max(zoom,pzoom)+0.0010,1.11)", center_x, center_y


def build_zoompan_filter(input_index: int, motion: str, duration: float) -> str:
    safe_duration = max(0.6, float(duration))
    frames = max(2, int(round(safe_duration * VIDEO_OUTPUT_FPS)))
    z_expr = "1"
    x_expr = "iw/2-(iw/zoom/2)"
    y_expr = "ih/2-(ih/zoom/2)"
    return (
        f"[{input_index}:v]"
        f"scale={VIDEO_WORKING_WIDTH}:{VIDEO_WORKING_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WORKING_WIDTH}:{VIDEO_WORKING_HEIGHT},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:"
        f"s={VIDEO_OUTPUT_WIDTH}x{VIDEO_OUTPUT_HEIGHT}:fps={VIDEO_OUTPUT_FPS},"
        f"trim=duration={safe_duration:.3f},"
        "setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
        f"[v{input_index}]"
    )


def build_local_video_segments(
    project_id: int,
    cover_path: Path,
    scene_paths: list[Path],
    cover_duration: float,
    scene_durations: list[float],
    outro_duration: float,
) -> list[dict[str, Any]]:
    plan_entries = load_scene_plan_entries(project_id)
    segments: list[dict[str, Any]] = [
        {
            "path": cover_path,
            "visible_duration": max(1.0, cover_duration),
            "motion": "quick_push_in",
            "transition_label": "",
        }
    ]
    for index, scene_path in enumerate(scene_paths, start=1):
        plan_entry = plan_entries[index - 1] if index - 1 < len(plan_entries) else {}
        motion = clean_text(str(plan_entry.get("motion") or "")) or scene_motion_for_type("editorial_collage", index)
        transition_label = clean_text(str(plan_entry.get("transition") or "")) or "crossfade_8_frames"
        segments.append(
            {
                "path": scene_path,
                "visible_duration": max(1.0, float(scene_durations[index - 1])),
                "motion": motion,
                "transition_label": transition_label,
            }
        )
    if outro_duration > 0 and scene_paths:
        last_plan = plan_entries[-1] if plan_entries else {}
        segments.append(
            {
                "path": scene_paths[-1],
                "visible_duration": max(0.8, float(outro_duration)),
                "motion": clean_text(str(last_plan.get("motion") or "")) or "micro_zoom_then_hold",
                "transition_label": "soft_fade_to_end",
            }
        )
    for segment in segments:
        segment["incoming_transition"] = 0.0
        segment["transition_name"] = ""
        segment["source_duration"] = float(segment["visible_duration"])
    return segments


def compose_final_video(
    project_id: int,
    title: str,
    scene_paths: list[Path],
    audio_path: Path,
    subtitle_path: Path | None,
    output_path: Path,
) -> Path:
    if not scene_paths:
        raise RuntimeError("还没有生成场景图，无法合成视频。")
    if not audio_path.exists():
        raise RuntimeError("podcast.mp3 不存在，无法合成视频。")

    cover_path = find_cover_path(project_id) or scene_paths[0]
    audio_duration = probe_audio_duration(audio_path)
    timing = load_timeline_durations(project_id, len(scene_paths))
    if timing:
        cover_duration, scene_durations, outro_duration = timing
    else:
        cover_duration = 5.0
        outro_duration = 0.0
        usable = max(audio_duration - cover_duration - outro_duration, 1.0)
        per_scene = usable / max(1, len(scene_paths))
        scene_durations = [per_scene] * len(scene_paths)

    total_duration = cover_duration + sum(scene_durations) + outro_duration
    if total_duration < audio_duration and scene_durations:
        scene_durations[-1] += audio_duration - total_duration
    elif total_duration > audio_duration and scene_durations:
        overflow = total_duration - audio_duration
        scene_durations[-1] = max(1.0, scene_durations[-1] - overflow)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="svs-video-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        subtitle_source_path = subtitle_path
        segments = build_local_video_segments(
            project_id,
            cover_path,
            scene_paths,
            cover_duration,
            scene_durations,
            outro_duration,
        )
        filter_parts = [
            build_zoompan_filter(index, str(segment.get("motion") or ""), float(segment.get("source_duration") or 0.0))
            for index, segment in enumerate(segments)
        ]
        if len(segments) == 1:
            final_video_label = "v0"
        else:
            final_video_label = "vseq"
            concat_inputs = "".join(f"[v{index}]" for index in range(len(segments)))
            filter_parts.append(f"{concat_inputs}concat=n={len(segments)}:v=1:a=0[{final_video_label}]")
        if subtitle_source_path and subtitle_source_path.exists():
            subtitle_input_label = final_video_label
            final_video_label = "vout"
            filter_parts.append(
                f"[{subtitle_input_label}]subtitles='{ffmpeg_subtitle_path(subtitle_source_path)}'"
                ":force_style='FontName=Microsoft YaHei,FontSize=22,Alignment=2,Outline=2,Shadow=0,MarginV=28'"
                f"[{final_video_label}]"
            )
        filter_complex = ";".join(filter_parts)
        audio_input_index = len(segments)

        cmd = [
            str(ffmpeg_binary()),
            "-y",
        ]
        for segment in segments:
            cmd.extend(["-i", str(Path(segment["path"]))])
        cmd.extend(
            [
                "-i",
                str(audio_path),
                "-filter_complex",
                filter_complex,
                "-map",
                f"[{final_video_label}]",
                "-map",
                f"{audio_input_index}:a",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(VIDEO_OUTPUT_FPS),
                "-shortest",
                "-t",
                f"{max(audio_duration, 1.0):.3f}",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                timeout=1800,
            )
            normalize_media_timeline(output_path)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError((exc.stderr or exc.stdout or str(exc)).strip()[:500]) from exc
    storage.write_text(storage.project_file(project_id, "releases/final-video.txt"), f"{title}\n{output_path.name}\n")
    return output_path


def compose_original_video(
    project_id: int,
    project: dict[str, Any],
    template: dict[str, Any],
    content: str,
    scene_paths: list[Path],
    audio_path: Path,
    subtitle_path: Path | None,
    output_path: Path,
) -> Path:
    cover_path = find_cover_path(project_id)
    if not cover_path or not cover_path.exists():
        raise RuntimeError("未找到封面图，无法调用原版成片链路。")
    if not scene_paths:
        raise RuntimeError("未找到场景图，无法调用原版成片链路。")
    if not audio_path.exists():
        raise RuntimeError("podcast.mp3 不存在，无法调用原版成片链路。")

    env = runtime_env()
    mode = project.get("template_mode", "video")
    template_key = clean_text(
        template.get("key")
        or template.get("name")
        or project.get("template")
        or ""
    )
    bgm_path = find_bgm_path(project_id, template_key)
    disclaimer = extract_meta_field(content, "免责声明")
    dialogue_texts = parse_dialogue_lines(content, mode)
    scene_prompts = composer_scene_prompts(
        project_id,
        scene_paths,
        current_scene_prompts(project_id, content, mode, project["topic_name"], prefer_timeline=True),
    )
    highlights = parse_highlights(content)
    timeline_path = storage.project_file(project_id, "audio/scene_timeline.json")

    payload = {
        "cover_path": str(cover_path),
        "scene_paths": [str(path) for path in scene_paths],
        "audio_path": str(audio_path),
        "output_path": str(output_path),
        "highlights": highlights,
        "disclaimer": disclaimer,
        "dialogue_texts": dialogue_texts,
        "scene_prompts": scene_prompts,
        "subtitle_path": str(subtitle_path) if subtitle_path and subtitle_path.exists() else "",
        "scene_timeline_path": str(timeline_path) if timeline_path.exists() else "",
        "outro_duration": 0.0,
        "bgm_path": str(bgm_path) if bgm_path and bgm_path.exists() else "",
        "bgm_volume": float(clean_text(env.get("BGM_VOLUME", "")) or 0.09) if bgm_path and bgm_path.exists() else None,
        "brand_name": "",
        "force": True,
    }
    result = run_original_bridge("video", payload, env, timeout=1800)
    result_path = Path(str(result.get("output_path") or output_path))
    storage.write_text(storage.project_file(project_id, "releases/final-video.txt"), f"{first_heading(content) or project['topic_name']}\n{result_path.name}\n")
    return result_path


def compose_original_video(
    project_id: int,
    project: dict[str, Any],
    template: dict[str, Any],
    content: str,
    scene_paths: list[Path],
    audio_path: Path,
    subtitle_path: Path | None,
    output_path: Path,
) -> Path:
    cover_path = find_cover_path(project_id)
    if not cover_path or not cover_path.exists():
        raise RuntimeError("未找到封面图，无法调用原版成片链路。")
    if not scene_paths:
        raise RuntimeError("未找到场景图，无法调用原版成片链路。")
    if not audio_path.exists():
        raise RuntimeError("podcast.mp3 不存在，无法调用原版成片链路。")

    env = runtime_env()
    mode = project.get("template_mode", "video")
    template_key = clean_text(
        template.get("key")
        or template.get("name")
        or project.get("template")
        or ""
    )
    bgm_path = find_bgm_path(project_id, template_key)
    disclaimer = extract_meta_field(content, "免责声明")
    dialogue_texts = parse_dialogue_lines(content, mode)
    scene_prompts = composer_scene_prompts(
        project_id,
        scene_paths,
        current_scene_prompts(project_id, content, mode, project["topic_name"], prefer_timeline=True),
    )
    highlights = parse_highlights(content)
    timeline_path = storage.project_file(project_id, "audio/scene_timeline.json")
    expected_duration = expected_video_duration(project_id, len(scene_paths), audio_path, subtitle_path)

    payload = {
        "cover_path": str(cover_path),
        "scene_paths": [str(path) for path in scene_paths],
        "audio_path": str(audio_path),
        "output_path": str(output_path),
        "highlights": highlights,
        "disclaimer": disclaimer,
        "dialogue_texts": dialogue_texts,
        "scene_prompts": scene_prompts,
        "subtitle_path": str(subtitle_path) if subtitle_path and subtitle_path.exists() else "",
        "scene_timeline_path": str(timeline_path) if timeline_path.exists() else "",
        "outro_duration": 0.0,
        "bgm_path": str(bgm_path) if bgm_path and bgm_path.exists() else "",
        "bgm_volume": float(clean_text(env.get("BGM_VOLUME", "")) or 0.09) if bgm_path and bgm_path.exists() else None,
        "brand_name": "",
        "force": True,
    }
    result = run_original_bridge("video", payload, env, timeout=1800)
    result_path = Path(str(result.get("output_path") or output_path))
    if not result_path.exists():
        raise RuntimeError(f"原版 composer 未输出视频文件：{result_path}")
    ensure_video_duration_matches(result_path, expected_duration)
    storage.write_text(storage.project_file(project_id, "releases/final-video.txt"), f"{first_heading(content) or project['topic_name']}\n{result_path.name}\n")
    return result_path


def generic_scene_lines(topic: str, mode: str) -> list[str]:
    if mode == "article":
        return [
            f"围绕「{topic}」点题，让读者知道这篇文章到底要解决什么问题",
            f"拆掉「{topic}」最常见的一个误解，制造阅读继续下去的动力",
            f"解释「{topic}」背后的关键机制，把复杂概念讲清楚",
            f"拿一个贴近现实的例子，说明「{topic}」为什么值得关注",
            f"回到读者能立刻用上的场景，把全文结论落下来",
        ]
    return [
        f"用一个最抓人的反常识问题切入「{topic}」",
        f"补上「{topic}」的背景，让观众知道它为什么值得听",
        f"拆掉「{topic}」的旧理解和常见误区",
        f"讲清真正影响结果的关键变量和转折点",
        f"用具体案例把「{topic}」讲成能看见的画面",
        f"回扣开头，把「{topic}」真正的答案落下来",
    ]


WEAK_OPENING_TOKENS = (
    "大家好",
    "今天我们",
    "这期我们",
    "本期我们",
    "让我们",
    "众所周知",
    "话说",
    "随着",
    "首先",
)

HOOK_SIGNAL_TOKENS = (
    "你以为",
    "其实",
    "偏偏",
    "结果",
    "真相",
    "别急",
    "先别",
    "为什么",
    "怎么",
    "居然",
    "反而",
    "但",
    "不过",
)

RETENTION_SIGNAL_TOKENS = (
    "但",
    "不过",
    "结果",
    "后来",
    "偏偏",
    "真正关键",
    "更关键",
    "问题是",
    "你以为",
    "其实",
    "先别急",
    "先看",
    "再看",
    "比如",
    "例如",
    "这时候",
    "这个时候",
)

INTERACTION_SIGNAL_TOKENS = (
    "你遇到过",
    "你家里",
    "你会怎么",
    "你是哪种",
    "评论区",
    "留言",
    "说说",
    "聊聊",
    "有没有",
    "会不会",
    "你更",
)

CALLBACK_STOPWORDS = {
    "今天",
    "这个",
    "那个",
    "我们",
    "他们",
    "你们",
    "因为",
    "所以",
    "其实",
    "如果",
    "一个",
    "这种",
    "那个",
}


def content_body_lines(content: str, mode: str) -> list[str]:
    if mode != "article":
        dialogue_lines = [strip_dialogue_speaker(item) for item in parse_dialogue_lines(content, mode) if clean_text(item)]
        if dialogue_lines:
            return dialogue_lines
    lines: list[str] = []
    for raw in content.splitlines():
        line = clean_text(raw)
        if not line:
            continue
        if line.startswith("#") or line.startswith("- "):
            continue
        if re.match(r"^\d+\.\s", line):
            continue
        if line.startswith("[配图") or line.startswith("[场景"):
            continue
        lines.append(line)
    return lines


def content_engagement_report(content: str, mode: str) -> dict[str, Any]:
    lines = content_body_lines(content, mode)
    opening_lines = lines[:3]
    opening_text = "\n".join(opening_lines)
    middle_lines = lines[3:-2] if len(lines) > 6 else lines[2:-1]
    ending_lines = lines[-2:] if len(lines) >= 2 else lines[-1:]
    ending_text = "\n".join(ending_lines)

    weak_opening = any(token in opening_text for token in WEAK_OPENING_TOKENS)
    hook_signal_count = sum(
        1
        for ok in (
            any(token in opening_text for token in HOOK_SIGNAL_TOKENS),
            bool(re.search(r"[0-9一二三四五六七八九十百千万]", opening_text)),
            bool(re.search(r"[？?！!]", opening_text)),
            any(token in opening_text for token in ("不是", "反而", "结果", "真相", "居然", "偏偏")),
            len(opening_text) <= 56,
        )
        if ok
    )

    retention_turns = sum(1 for line in middle_lines if any(token in line for token in RETENTION_SIGNAL_TOKENS))
    has_example = any(token in "\n".join(middle_lines) for token in ("比如", "例如", "拿", "就像", "有一次", "举个例子"))
    question_turns = sum(1 for line in lines if "？" in line or "?" in line)

    opening_tokens = {token for token in extract_tokens(opening_text) if len(token) >= 2 and token not in CALLBACK_STOPWORDS}
    ending_tokens = {token for token in extract_tokens(ending_text) if len(token) >= 2 and token not in CALLBACK_STOPWORDS}
    has_callback = bool(opening_tokens & ending_tokens)
    has_interaction = any(token in ending_text for token in INTERACTION_SIGNAL_TOKENS) or bool(re.search(r"[？?]", ending_text))
    generic_cta = any(token in ending_text for token in ("欢迎关注", "点赞收藏", "下期见", "谢谢观看"))

    opening_score = 2.2 + min(hook_signal_count, 4) * 0.7 - (1.5 if weak_opening else 0.0) + (0.2 if question_turns else 0.0)
    retention_score = 2.0 + min(retention_turns, 4) * 0.55 + (0.5 if has_example else 0.0) + (0.3 if len(middle_lines) >= 4 else 0.0)
    interaction_score = 1.8 + (1.5 if has_interaction else 0.0) + (0.6 if has_callback else 0.0) + (0.4 if "你" in ending_text else 0.0) - (0.8 if generic_cta and not has_interaction else 0.0)

    opening_score = round(max(0.0, min(5.0, opening_score)), 1)
    retention_score = round(max(0.0, min(5.0, retention_score)), 1)
    interaction_score = round(max(0.0, min(5.0, interaction_score)), 1)
    overall = round(max(0.0, min(5.0, opening_score * 0.42 + retention_score * 0.36 + interaction_score * 0.22)), 1)

    issues: list[dict[str, str]] = []
    if opening_score < 3.8:
        issues.append(
            {
                "where": "开头钩子",
                "issue": "前 3 句还不够像短视频开场，缺少反差、危险、结果先行或尖锐提问。",
                "fix": "把第一句改成可单独截图的钩子句，优先用“你以为…其实…”“先别…”“最容易出事的就是…”这类句式。",
            }
        )
    if retention_score < 3.5:
        issues.append(
            {
                "where": "中段追看欲",
                "issue": "中段解释偏多、推进偏少，容易像说明文，缺少追问、反转、例子和代价。",
                "fix": "每 2-3 句增加一次信息推进动作：追问、误区纠正、具体案例、旧认知 vs 真机制。",
            }
        )
    if interaction_score < 3.4:
        issues.append(
            {
                "where": "结尾互动",
                "issue": "结尾更像收尾总结，还没有把观众自然推到评论区。",
                "fix": "结尾同时做三件事：回扣开头、落到现实、抛一个低门槛互动问题，别只喊“你怎么看”。",
            }
        )

    performance_read = "开头能抓住人，中段有推进，结尾能带互动。"
    if overall < 4.0:
        performance_read = "结构可能已经成型，但还需要把‘抓人、追看、互动’再压实，避免像平铺解释。"

    verdict = "表达张力达标，可直接进入生产。"
    if overall < 4.0 or opening_score < 3.8 or interaction_score < 3.4:
        verdict = "建议先做一轮总编式重写，把开头钩子、中段推进和结尾互动抬起来。"

    return {
        "overall_score": overall,
        "opening_score": opening_score,
        "retention_score": retention_score,
        "interaction_score": interaction_score,
        "has_callback": has_callback,
        "has_interaction": has_interaction,
        "hook_signal_count": hook_signal_count,
        "retention_turns": retention_turns,
        "issues": issues,
        "performance_read": performance_read,
        "verdict": verdict,
        "needs_rewrite": overall < 4.0 or opening_score < 3.8 or retention_score < 3.5 or interaction_score < 3.4,
    }


def channel_learning_prompt_block(project: dict[str, Any], template: dict[str, Any], max_projects: int = 12) -> str:
    template_key = clean_text(str(template.get("key") or project.get("template") or ""))
    if not template_key:
        return ""
    current_id = int(project.get("id", 0) or 0)
    rows: list[dict[str, Any]] = []
    keywords: Counter[str] = Counter()
    weaknesses: Counter[str] = Counter()

    for meta in storage.projects_for_template(template_key)[: max_projects * 3]:
        pid = int(meta.get("id", 0) or 0)
        if pid and pid == current_id:
            continue
        content_path = storage.project_file(pid, "content.md")
        content = storage.read_text(content_path) if content_path.exists() else ""
        summary = storage.get_summary(pid)
        mode = clean_text(str(meta.get("template_mode") or template.get("mode") or "video"))
        engagement = content_engagement_report(content, mode) if clean_text(content) else {}
        hook = _first_content_hook(content, mode) if clean_text(content) else ""
        title = clean_text(str(summary.get("publish_title") or summary.get("video_title") or meta.get("topic_name") or ""))
        release_signals = [release_performance_signal(item) for item in storage.get_release_links(pid) if isinstance(item, dict)]
        best_release = max(release_signals, key=lambda item: int(item.get("performance_score", 0) or 0), default=None)
        performance_score = int((best_release or {}).get("performance_score", 0) or 0)
        for token in _history_keyword_tokens(" ".join([title, hook, clean_text(str(summary.get("summary") or ""))])):
            keywords[token] += 1
        for issue in _project_quality_issues(pid):
            label = clean_text(str(issue.get("where") or issue.get("issue") or ""))
            if label:
                weaknesses[label[:32]] += 1
        rows.append(
            {
                "project_id": pid,
                "topic": clean_text(str(meta.get("topic_name") or "")),
                "title": title,
                "hook": hook,
                "opening_score": float(engagement.get("opening_score", 0) or 0),
                "performance_score": performance_score,
                "best_release": best_release,
            }
        )
        if len(rows) >= max_projects:
            break

    if not rows:
        return "频道历史学习：暂无历史项目或投放反馈，本次以频道 prompt.md 和当前 brief 为准。"

    by_hook = sorted(rows, key=lambda item: (item["performance_score"], item["opening_score"]), reverse=True)[:3]
    by_release = [item for item in sorted(rows, key=lambda item: item["performance_score"], reverse=True) if item["performance_score"] > 0][:3]
    memory_lines = [
        "频道历史学习（必须作为参考，但不能照抄旧稿）：",
        f"- 历史项目数：{len(rows)}；有真实投放数据：{sum(1 for item in rows if item['performance_score'] > 0)}。",
    ]
    if keywords:
        memory_lines.append("- 高频素材/题材词：" + "、".join(key for key, _ in keywords.most_common(6)) + "。")
    if by_hook:
        memory_lines.append("- 可借鉴的高抓力开头：")
        for item in by_hook:
            if item["hook"]:
                memory_lines.append(f"  * #{item['project_id']}「{item['topic']}」开头：{item['hook']}")
    if by_release:
        memory_lines.append("- 表现更好的投放样本：")
        for item in by_release:
            metrics = (item.get("best_release") or {}).get("metrics", {}) or {}
            interaction = (
                int(metrics.get("likes", 0) or 0)
                + int(metrics.get("comments", 0) or 0)
                + int(metrics.get("shares", 0) or 0)
                + int(metrics.get("favorites", 0) or 0)
            )
            memory_lines.append(
                f"  * #{item['project_id']}「{item['title'] or item['topic']}」表现分 {item['performance_score']}，"
                f"播放 {metrics.get('views', 0)}，互动 {interaction}，完播 {metrics.get('completion_rate', 0)}%。"
            )
    if weaknesses:
        memory_lines.append("- 历史常见问题：" + "；".join(f"{key}({count})" for key, count in weaknesses.most_common(4)) + "。")
    memory_lines.append("- 本次生成要求：延续频道有效口吻和钩子类型，但主题、画面主体、具体案例必须跟当前 brief 重新生成。")
    return "\n".join(memory_lines)


def build_common_content_system_rules() -> str:
    return """
你现在要为短片工坊生成最终可落地的 content.md。
优先级：
1. 当前频道模板 prompt.md 是最高优先级。频道的人设、语气、角色关系、栏目结构、时长、封面气质、镜头语言、禁忌和发布习惯，都必须服从频道模板；但最终 Meta 字段和图片提示词长度按下方精简规则执行，旧模板里的分析字段不要输出。
2. 当前主题和 brief 只提供本期素材，不得覆盖频道模板风格。不同频道必须生成不同口吻和不同视觉气质。
3. 下方通用要求只用于保证短片工坊生产链路能解析，不允许把所有频道改写成同一种“通用爆款腔”。
硬性要求：
1. 只输出最终的 Markdown 成品，不要解释，不要前言，不要致谢。
2. 第一行必须直接从 # 或 ## 标题开始。
3. 如果给了历史稿参考，只能借鉴风格、视角和连续创作语气，不能照抄旧稿。
4. 如果给了联网资料，涉及最新事实、时间、金额、排名、参数时优先以联网资料为准；不确定就保守表达。
5. 你的输出必须严格遵守当前模板 prompt 约定的章节、角色标签、图片提示词和时长要求。
6. 如果主题依赖事实、新闻、专业知识或具体数据，但 brief 与参考资料不足以支撑结论，停止生成完整脚本，只输出：# 资料不足、## 需要补充的资料、## 建议检索方向；不得自行补充事实。
7. 如果频道模板没有明确章节，按精简兼容结构输出：# 标题、## Meta、## 原始材料简述、视频频道输出 ## 对话脚本 或 ## 口播脚本、## 重点字幕、## 图片提示词、## 参考资料；图文频道输出 ## 正文、## 图片提示词、## 参考资料。
8. Meta 只保留这些字段：封面副标题、核心观点、时长、推荐发布标题、钩子、互动钩子、免责声明。HKR、评分、叙事原型、说服策略、情绪曲线、节奏策略、callback、黄金前三句都只能内部思考，不要输出到 content.md。
9. 视频频道的图片提示词必须包含 ### 横屏封面图 (4:3)、### 竖屏封面图 (3:4)、### 场景图；场景图用 1. 2. 3. 编号，数量要匹配脚本时长和语音节奏。
10. 图片提示词按“频道视觉策略 -> 本期主题 -> 当前口播锚点”分工：频道只给统一质感，单张图只写主体、构图、动作、情绪和字幕安全区；不要把公共风格在每张图里重复 600 字。
11. 封面标题控制在 5-8 个中文字左右，只配一句短副标题；场景图默认不生成可读文字，必要时只保留 1-3 个短标签，避免长段正文、脚注、免责声明、水印和乱码。
12. 每张场景图必须根据对应脚本段落和本期素材重新设计，不要把风格写死成统一背景模板；除非频道模板明确要求。
""".strip()


def build_viral_content_rules(project: dict[str, Any], template: dict[str, Any]) -> str:
    template_name = clean_text(template.get("name") or template.get("key") or project.get("template") or "")
    voice_mode = clean_text(template.get("voice_mode") or "")
    profile = channel_profile_text(template)
    learning = channel_learning_prompt_block(project, template)
    is_dual = "双人" in template_name or voice_mode == "dual"
    role_rule = (
        "双人模式里，【女】负责掐点抛钩子和追问，不能只是礼貌接话；【男】负责解答，但每轮答完都要留下新的好奇点给下一轮承接。"
        if is_dual
        else "单人模式里，【主播】不能一路平铺解释；每 2-3 句就要用一次自问自答、反问、转折或小结，把节奏继续往前推。"
    )
    return f"""
爆款表达增强指令（强约束，但不能破坏频道 prompt.md 的人设和结构）：
频道中枢：
{profile or "未填写结构化频道中枢，以 prompt.md 为准。"}

{learning}

一、开头必须有吸引力
1. 第一口播句必须像短视频开场，不像文章导语；最好 10-24 个字，最迟前三句必须回答“我为什么要继续看”。
2. 禁止弱开头：大家好、今天我们来聊聊、这期我们说、让我们走进、众所周知、随着时代发展、首先其次最后。
3. 开头优先从以下入口选择最适合本期的一种：结果先行、反常识、风险/代价、情绪冲突、身份冲突、具体细节、没说完的问题。
4. 前三句里至少满足以下三项中的两项：出现具体对象/数字/时间；出现反差词（其实/结果/偏偏/反而/真相）；出现一个未说完的问题或悬念。

二、中段必须让人愿意继续看
1. 不能连续 3 句只解释概念；每讲一个观点，紧跟一个画面、人物动作、案例、旧误区或现实后果。
2. 每 2-3 轮对话或每 80-140 字，必须出现至少一个“信息推进动作”：追问、反问、反转、误区纠正、案例、对比、证据、代价、回扣。
3. 允许卖关子，但 1-2 轮内必须给答案，不能空转。
4. 中段至少出现一次“你以为……其实……”“表面看……真正关键是……”这类认知翻转。
5. {role_rule}

三、结尾必须让人想互动
1. 结尾不能只做总结，必须同时完成三件事：回扣开头、落到今天的现实、抛一个低门槛互动问题。
2. 互动问题要具体、好回答，优先引导观众回忆经历、站队、补充经验、代入家庭/工作/消费场景；不要只写“你怎么看”。
3. 最后一轮要让观众自然想在评论区接一句，而不是礼貌结束。

四、语言质感
1. 全文必须是能说出口的短视频口语，不要写成作文、报告、百科解释。
2. 多用短句、追问句、转折句，少用空泛抽象词；每 2-4 句最好就有一次语气变化。
3. 允许 1-2 处金句，但不能满篇端着；重点是让观点一直往前走，不要原地打转。

五、生成前自检
1. 如果开头像文章导语，重写。
2. 如果中段连续解释没有推进，重写。
3. 如果结尾没有互动欲，重写。
""".strip()


def compose_deepseek_rewrite_messages(
    project: dict[str, Any],
    template: dict[str, Any],
    content: str,
    report: dict[str, Any],
) -> list[dict[str, str]]:
    template_name = clean_text(template.get("name") or template.get("key") or project.get("template") or "")
    learning = channel_learning_prompt_block(project, template)
    issues = report.get("issues") or []
    issue_lines = "\n".join(
        f"- {item.get('where')}: {item.get('issue')} 修法：{item.get('fix')}"
        for item in issues[:4]
        if isinstance(item, dict)
    ) or "- 开头不够抓人，中段推进不够密，结尾互动不够强。"
    return [
        {
            "role": "system",
            "content": (
                "你是短视频内容总编。你的任务不是改结构，而是在保留频道风格、角色标签、章节名、事实信息、时长档位、图片章节结构的前提下，"
                "把稿子的开头钩子、中段追看欲、结尾互动全部拉起来。只输出修订后的完整 content.md。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"频道：{template_name}\n"
                "请重写下面这份稿子的表达张力，但不要改掉章节结构，不要删角色标签，不要改成别的频道风格。\n"
                "必须做到：开头更抓人，中段每隔 2-3 句有推进，结尾有具体互动问题，并且回扣开头。\n"
                f"{learning}\n\n"
                f"当前问题：\n{issue_lines}\n\n"
                "当前稿件：\n"
                f"{content}\n"
            ),
        },
    ]


def strip_dialogue_speaker(text: str) -> str:
    cleaned = clean_text(text)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"^[【\[][^】\]]+[】\]]\s*", "", cleaned)
    return cleaned.strip("：: ")


VISUAL_ANCHOR_SUBJECT_TERMS = (
    "老人", "长辈", "爸妈", "父母", "家人", "子女", "自己", "用户", "孩子", "医生", "老师",
    "手机", "屏幕", "钥匙", "饭", "客厅", "饭桌", "社区医院", "老年科", "路", "门口",
    "路由器", "设备", "产品", "球员", "奖杯", "实验", "城市", "公司",
)

VISUAL_ANCHOR_ACTION_TERMS = (
    "拿", "放", "找", "问", "说", "提醒", "想起", "走", "回家", "查", "做", "画", "测试",
    "聊天", "散步", "打牌", "算账", "看", "递", "停住", "打开", "关掉", "评论",
)

VISUAL_ANCHOR_CONFLICT_TERMS = (
    "害怕", "警惕", "信号", "风险", "焦虑", "暴躁", "多疑", "走丢", "忘", "不认识",
    "别急", "晚了", "误区", "冲突", "反差", "真相", "结果",
)

VISUAL_ANCHOR_WEAK_PATTERNS = (
    "今天咱们不讲",
    "到底是怎么回事",
    "咱们应该怎么做",
    "三件事",
    "第一种",
    "第二种",
    "所以",
    "而是",
    "这种忘",
    "来评论区聊聊",
)


def dialogue_visual_anchor_score(text: str) -> int:
    cleaned = clean_text(text)
    if not cleaned:
        return -999
    score = min(len(cleaned) // 12, 5)
    score += sum(5 for token in VISUAL_ANCHOR_SUBJECT_TERMS if token in cleaned)
    score += sum(4 for token in VISUAL_ANCHOR_ACTION_TERMS if token in cleaned)
    score += sum(4 for token in VISUAL_ANCHOR_CONFLICT_TERMS if token in cleaned)
    if any(token in cleaned for token in ("比如", "好比", "像")):
        score += 5
    if any(token in cleaned for token in ("钥匙", "吃过饭", "早上", "下午", "出门", "社区医院", "画钟", "散步", "打牌", "算账")):
        score += 8
    if any(pattern in cleaned for pattern in VISUAL_ANCHOR_WEAK_PATTERNS):
        score -= 8
    if len(cleaned) <= 12:
        score -= 10
    if not any(token in cleaned for token in VISUAL_ANCHOR_SUBJECT_TERMS + VISUAL_ANCHOR_ACTION_TERMS):
        score -= 8
    return score


def select_dialogue_scene_anchor_indexes(content: str, mode: str, desired: int) -> list[int]:
    dialogue_lines = [strip_dialogue_speaker(item) for item in parse_dialogue_lines(content, mode) if clean_text(item)]
    if desired <= 0 or not dialogue_lines:
        return []
    if len(dialogue_lines) <= desired:
        return list(range(len(dialogue_lines)))
    if desired == 1:
        return [0]

    last_index = len(dialogue_lines) - 1
    bases = [round(slot * last_index / max(1, desired - 1)) for slot in range(desired)]
    indexes: list[int] = []
    for slot, base in enumerate(bases):
        start = 0 if slot == 0 else (bases[slot - 1] + base) // 2 + 1
        end = last_index if slot == desired - 1 else (base + bases[slot + 1]) // 2
        candidates = [idx for idx in range(start, end + 1) if idx not in indexes]
        if not candidates:
            candidates = [idx for idx in range(len(dialogue_lines)) if idx not in indexes]
        if not candidates:
            break
        chosen = max(
            candidates,
            key=lambda idx: (
                dialogue_visual_anchor_score(dialogue_lines[idx]),
                -abs(idx - base),
                -idx,
            ),
        )
        indexes.append(chosen)
    return sorted(indexes)[:desired]


def select_dialogue_scene_anchors(content: str, mode: str, desired: int, limit: int = 84) -> list[str]:
    dialogue_lines = [strip_dialogue_speaker(item) for item in parse_dialogue_lines(content, mode) if clean_text(item)]
    if desired <= 0 or not dialogue_lines:
        return []
    indexes = select_dialogue_scene_anchor_indexes(content, mode, desired)
    return [summarize_scene_text(dialogue_lines[index], limit) for index in indexes]


def compact_prompt_focus_text(text: str, limit: int = 50) -> str:
    cleaned = strip_dialogue_speaker(text)
    cleaned = re.sub(r"^(?:你知道吗|你以为|很多人以为|很多人不知道|其实|原来|所以)[，,、\s]*", "", cleaned)
    return summarize_scene_text(cleaned, limit)


def compact_cover_focus_text(text: str, style: str, domain: str, limit: int = 50) -> str:
    cleaned = compact_prompt_focus_text(text, max(limit + 18, 68))
    lowered = cleaned.lower()
    if domain == "smart_home" and any(token in lowered for token in ("wifi", "路由器")) and any(token in lowered for token in ("电线", "plc", "插座", "电力线")):
        return "路由器、墙体剖面与墙内电力线同框"
    replacements = [
        (r"(?:wifi|路由器)[^，。；]*?(?:大红叉|红叉|打叉|被打叉|被画红叉)", "路由器与受阻的 WiFi 穿墙状态"),
        (r"(?:大|巨大)?红叉", "受阻状态"),
        (r"感叹号(?:印章|标记)?", "警示信号"),
        (r"形成(?:视觉)?颠覆", ""),
        (r"被画了一个|上画了一个|被打了一个", ""),
    ]
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[，,、 ]{2,}", "，", cleaned)
    return summarize_scene_text(cleaned, limit)


def template_prompt(template: dict[str, Any] | None) -> str:
    return str((template or {}).get("prompt") or "")


def channel_profile_text(template: dict[str, Any] | None) -> str:
    template = template or {}
    rows = [
        ("频道名", template.get("brand_name") or template.get("name") or template.get("key") or ""),
        ("目标受众", template.get("target_audience") or ""),
        ("口吻语气", template.get("channel_voice") or ""),
        ("视觉策略", template.get("visual_strategy") or ""),
        ("禁忌边界", template.get("forbidden_rules") or ""),
        ("互动目标", template.get("interaction_goal") or ""),
        ("挖题方向", template.get("topic_mining_hint") or ""),
        ("发布标签", template.get("release_tags") or ""),
        ("封面风格", template.get("cover_style") or ""),
    ]
    lines = [f"- {label}: {clean_text(str(value))}" for label, value in rows if clean_text(str(value))]
    return "\n".join(lines)


def template_bullet_value(template: dict[str, Any] | None, label: str) -> str:
    prompt = template_prompt(template)
    if not prompt:
        return ""
    pattern = re.compile(rf"(?m)^\s*-\s*{re.escape(label)}\s*[：:]\s*(.+?)\s*$")
    match = pattern.search(prompt)
    return clean_text(match.group(1)) if match else ""


def template_section_bullets(template: dict[str, Any] | None, title: str, limit: int = 4) -> list[str]:
    section = extract_section(template_prompt(template), title, level=2)
    bullets: list[str] = []
    for raw in section.splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        text = clean_text(line[2:])
        if text:
            bullets.append(text)
        if len(bullets) >= limit:
            break
    return bullets


def channel_visual_style_hint(template: dict[str, Any] | None, purpose: str) -> str:
    structured = clean_text(str((template or {}).get("visual_strategy") or ""))
    if structured:
        return structured
    style = template_bullet_value(template, "频道统一风格")
    if style:
        return style
    section_title = "封面图规则" if purpose == "cover" else "图片生成总原则"
    for bullet in template_section_bullets(template, section_title, limit=8):
        if any(token in bullet for token in ("真实", "主体", "情绪", "传播感", "主题强关联")):
            return bullet
    return "真实、有主体、有情绪点、有传播感；画面必须服从当前频道、本期主题和对应口播"


def channel_visual_binding_hints(template: dict[str, Any] | None, source: str = "") -> list[str]:
    hints = []
    for label in ("本期主题决定主视觉", "当前文案段落决定画面重点"):
        value = template_bullet_value(template, label)
        if value:
            hints.append(value)
    if not hints:
        hints = [
            "根据本期主题选择人物、空间、物件和动作关系",
            "每张图只服务当前对应口播段落，不复用其他主题的固定流程",
        ]
    source_text = clean_text(source)
    if source_text and not any(token in source_text for token in ("手机", "屏幕", "界面", "评论区", "APP", "App", "app", "来电", "弹窗")):
        hints = [
            re.sub(r"[、，,]?屏幕内容[、，,]?", "、", item).replace("、、", "、").strip("、，, ")
            for item in hints
        ]
    return hints


def generic_scene_grounding_hints(narrative: str, visual_type: str) -> list[str]:
    hints = [
        "主视觉必须从本张对应口播里提到的人物、物件、动作、空间或情绪冲突里选择，不从代码预设题材里选择",
        "频道只决定统一视觉气质和账号辨识度，本期主题决定画面主体，当前口播段落决定正在发生的瞬间",
        "每张图都要有不同的主体动作或空间关系，不要复用上一张图的构图、物件和流程",
    ]
    if visual_type == "mechanism_diagram":
        hints.append("机制拆解也要落到本期素材里的真实关系、动作或物件，不做冷冰冰流程图")
    if "应用场景" in narrative:
        hints.append("应用场景必须来自本期脚本里的具体例子，不套用其它主题的生活提醒场景")
    if "结论回扣" in narrative:
        hints.append("结尾图要承接本期观点和互动动作，不额外引入新的剧情流程")
    return hints


def generic_cover_grounding_hints() -> list[str]:
    return [
        "封面主视觉必须由本期标题、钩子和口播第一屏共同决定，不从代码预设题材里选择",
        "频道只决定统一视觉气质和账号辨识度，本期主题决定人物关系、空间、物件和冲突点",
        "封面要抓一个能压住画面的真实主体或强情绪瞬间，避免变成通用提示卡或无关流程图",
    ]


def content_scene_style_hint(style: str, template: dict[str, Any] | None = None) -> str:
    del style
    return channel_visual_style_hint(template, "scene")


def content_cover_style_hint(style: str, template: dict[str, Any] | None = None) -> str:
    del style
    return channel_visual_style_hint(template, "cover")


def content_visual_layout_hint(visual_type: str) -> str:
    hints = {
        "timeline": "用前后阶段或时间推进表现变化，不做静态说明板",
        "comparison": "用明显对比承载观点，让两边差异一眼可懂",
        "mechanism_diagram": "把链路或因果画成正在发生的动作，不做流程表",
        "data_card": "数据只做辅助体量或强弱对比，不把表格当主角",
        "life_scene": "把人物、设备或环境放进真实空间瞬间里，优先近景、动作和前后景层次",
        "editorial_collage": "用一个主主体压住画面，少量辅助线索补充信息，同时让画面有明确情绪峰值或冲突点",
    }
    return hints.get(visual_type, "用一个主主体压住画面，少量辅助线索补充信息，同时让第一眼有冲击")


SCENE_VIEWPOINT_ROTATION = (
    "近景半身，人物表情和手部动作先入眼",
    "手机/关键物件特写，屏幕光或物体细节做前景",
    "过肩视角，让观众像站在旁边看见正在发生的事",
    "同一空间前后景对照，问题点和人物反应同时出现",
    "低机位或侧逆光，把关键动作做得更有停顿感",
    "收束镜头，人物回看、转发、确认或松一口气的动作清楚",
)


def scene_viewpoint_hint(index: int, total: int, visual_type: str) -> str:
    if visual_type == "comparison":
        return "同一空间双状态对照，前景是问题状态，后景是人物反应"
    if visual_type == "mechanism_diagram":
        return "用真实物件和动作链表现机制，镜头从触发点推到结果点"
    if visual_type == "timeline":
        return "用三个递进空间层次表现前后变化，避免平面时间表"
    if visual_type == "data_card":
        return "主物体或人物在前景，数据只做少量体量光块辅助"
    if total > 0 and index >= total:
        return SCENE_VIEWPOINT_ROTATION[-1]
    return SCENE_VIEWPOINT_ROTATION[(max(1, index) - 1) % len(SCENE_VIEWPOINT_ROTATION)]


def compact_prompt_rule(text: str, limit: int = 82) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    if cleaned.startswith(PROMPT_DIALOGUE_PREFIXES + PROMPT_SCAFFOLD_STARTS):
        return ""
    if any(marker in cleaned for marker in PROMPT_SCAFFOLD_CONTAINS):
        return ""
    cleaned = re.sub(r"^主视觉(?:必须|优先)?", "主视觉", cleaned)
    cleaned = re.sub(r"频道只决定统一视觉气质和账号辨识度，?", "频道只定气质，", cleaned)
    cleaned = re.sub(r"本期主题决定画面主体，当前口播段落决定正在发生的瞬间", "主题和当前口播决定主体与瞬间", cleaned)
    return summarize_scene_text(cleaned, limit)


def classify_elder_life_topic_kind(source: str) -> str:
    text = clean_text(source)
    if _contains_any(text, ("客服", "扣费", "转账", "验证码", "屏幕共享", "会议软件", "来电", "电话", "诈骗", "骗子", "挂断")):
        return "anti_fraud"
    if _contains_any(text, ("老登", "网络词", "热词", "称呼", "网络标签", "调侃", "爹味", "守旧", "对号入座", "网络流行")):
        return "network_hotword"
    if _contains_any(text, ("药", "医院", "体检", "血压", "保健品", "慢病", "医保", "看病")):
        return "health"
    if _contains_any(text, ("燃气", "门锁", "冰箱", "厨房", "插座", "电器", "小区", "社区")):
        return "life_safety"
    return "generic"


def elder_life_subject_hints(source: str, narrative: str, purpose: str) -> list[str]:
    topic_kind = classify_elder_life_topic_kind(source)
    if topic_kind == "anti_fraud":
        return [
            "主视觉从本期反诈情节选择：手机来电、扣费提示、验证码、屏幕共享或家人制止动作，选择最贴合这一段、最有停顿感的一个瞬间",
            "优先让亮起的手机屏幕、伸手制止、皱眉停顿、挂断动作或对视反应进入前景，图标和箭头只做小面积辅助",
        ]
    if topic_kind == "network_hotword":
        return [
            "主视觉从本期网络热词素材选择：手机评论区、家庭聊天、长辈听到称呼后的表情、年轻人与长辈沟通的距离感，优先挑最刺人的一秒",
            "用表情、评论区语境、家人解释和代际沟通承载冲突，让画面围绕称呼误解、尊重边界和家人沟通展开，不要做温吞站桩插图",
        ]
    if topic_kind == "health":
        return [
            "主视觉从健康生活场景选择：药盒、体检单、社区医院、家人陪同咨询或老人查看说明书",
            "提醒符号只做辅助，重点是真实生活里的选择、询问、核对和家人陪伴动作",
        ]
    if topic_kind == "life_safety":
        return [
            "主视觉从本期生活安全物件选择：燃气灶、门锁、冰箱、插座、社区公告栏或小区场景",
            "人物动作和风险点要真实可见，提醒标签只做辅助，让安全细节落在真实生活物件上",
        ]
    return [
        "主视觉必须从本期脚本段落提取具体人物、物件和生活场景，不默认老人手机饭桌",
        "用本期对应的人物动作、物件关系和生活空间承载冲突，不引入无关流程",
    ]


def scene_subject_priority_hints(style: str, domain: str, visual_type: str, narrative: str, source: str = "") -> list[str]:
    if style == "elder_life":
        topic_kind = classify_elder_life_topic_kind(source)
        hints = [
            "主视觉优先从本张对应口播里提到的人物关系、动作、空间和关键物件里选一个最能承载本期主题的瞬间",
            "频道只决定统一视觉气质和受众表达，题材跟着本期主题和这句口播走，不挪用别的主题流程或物件",
            "默认不要所有人平视站着或坐着，优先选表情变化、伸手动作、关键物件特写、回头对视、近景半身或手部入画中的一种",
        ]
        if topic_kind != "anti_fraud":
            hints.append("除非这句口播明确提到，否则不要出现银行、转账、验证码、扣费、诈骗弹窗、陌生来电、会议软件或屏幕共享")
        if "机制拆解" in narrative or visual_type == "mechanism_diagram":
            hints.append("机制拆解也要落到本期素材里的真实动作或关系，不做冷冰冰流程图")
        elif "应用场景" in narrative:
            hints.append("应用场景要换成本期对应生活瞬间，不用同一张家庭提醒卡反复套")
        return hints

    if domain == "smart_home":
        hints = [
            "主视觉优先让路由器、墙体剖面、插座或墙内电力线链路同框",
            "设备、空间和线路做主角，红叉、问号、对勾和印章只做小面积辅助符号",
        ]
        if visual_type == "comparison":
            hints.append("同一空间里同时看见 WiFi 受阻和电力线直达，不做三栏说明板")
        elif visual_type == "mechanism_diagram":
            hints.append("让墙内链路、中控主机和被联动的设备处于正在发生的状态")
        elif visual_type == "data_card":
            hints.append("样板间或家庭空间做主画面，数据只做少量发光对比块")
        elif "应用场景" in narrative:
            hints.append("让真实人物或居住空间里的灯光、窗帘、空调出现被同时触发的瞬间")
        return hints

    if visual_type == "comparison":
        return [
            "主视觉优先让问题状态和解决状态同时出现在同一空间里",
            "对比靠物体、光线和距离体现，不靠大面积符号压画面",
        ]
    if visual_type == "mechanism_diagram":
        return [
            "主视觉优先是一个核心装置和一条清楚可见的动作链路",
            "箭头、节点和图标只做辅助，不压住主物体",
        ]
    if visual_type == "data_card":
        return [
            "主视觉优先是产品、人物或空间，数据只做少量体量辅助",
            "数字牌、印章和对勾不要变成画面主体",
        ]

    fallback = {
        "elder_life": [
            "主视觉优先是本期素材里的真实人物、物件或生活瞬间",
            "提醒章、短标签和箭头只做辅助，不压过真实关系和动作",
        ],
        "tech_cinematic": [
            "主视觉优先是真实设备、空间剖面或控制链路",
            "强调符号和状态标记只做辅助，不压过主体",
        ],
        "science_explainer": [
            "主视觉优先是结构剖面、实验装置或器官反应",
            "说明性图标只做辅助，不压过真实主体",
        ],
        "documentary_portrait": [
            "主视觉优先是人物、手势和关键道具",
            "环境信息和图标只做辅助，不压过人物状态",
        ],
    }
    return fallback.get(
        style,
        [
            "主视觉优先是一个真实主角物体、人物或空间瞬间",
            "所有符号和角标都只做辅助，不压过主体",
        ],
    )


def refine_scene_focus_text(
    beat: str,
    content: str,
    style: str,
    domain: str,
    visual_type: str,
    narrative: str,
    limit: int = 56,
) -> str:
    base = compact_prompt_focus_text(beat, max(limit + 18, 72))
    anchor = compact_prompt_focus_text(extract_bullet_field(content, "人物或场景锚点"), 52)
    analogy = compact_prompt_focus_text(extract_bullet_field(content, "新比喻或新意象"), 52)

    if domain == "smart_home":
        if narrative == "前三秒钩子/痛点":
            return "同一户型里，路由器的 WiFi 被墙体削弱，同时墙内电力线把控制信号直达灯和插座"
        if narrative == "背景铺垫":
            if anchor:
                return f"{anchor}，客厅路由器到卧室和书房的穿墙衰减一眼可见"
            return "真实户型中，客厅路由器到卧室和书房的 WiFi 穿墙衰减一眼可见"
        if narrative == "冲突或误区" or visual_type == "comparison":
            return "一侧是 WiFi 穿墙变弱和设备掉线，另一侧是电力线沿墙内直达各房间"
        if "机制拆解" in narrative and visual_type == "mechanism_diagram":
            return "墙体剖面里，中控主机把信号叠加到电力线，灯光、窗帘和空调被同时联动"
        if visual_type == "data_card":
            return "样板间里多设备稳定联动，旁边只用少量发光份额对比块点出领先"
        if narrative == "应用场景":
            if analogy:
                return f"{analogy}，同时让家里的灯光和窗帘在真实空间中联动"
            return "真实家庭里，灯光、窗帘和空调被一条墙内链路同时点亮和控制"
        if narrative == "结论回扣/互动":
            return "有人站在装修平面图前比较 WiFi 和 PLC 两条连接路线，准备做选择"

    if visual_type == "comparison":
        return summarize_scene_text(f"{base}，同一空间里并排出现问题状态和解决状态", limit)
    if visual_type == "mechanism_diagram":
        return summarize_scene_text(f"{base}，一个核心装置触发一条清楚可见的动作链", limit)
    if visual_type == "data_card":
        return summarize_scene_text(f"{base}，主角物体在前景，少量数据体量做辅助", limit)
    if narrative == "应用场景":
        return summarize_scene_text(f"{base}，放进真实生活空间里正在发生", limit)
    return summarize_scene_text(base, limit)


def cover_variant_layout_hint(kind: str) -> str:
    hints = {
        "landscape": "4:3 横屏封面，主体压住一侧，另一侧或上方留干净叠标题区域",
        "story": "4:3 图文封面，主体稍偏左或偏下，留出清楚的标题安全区",
        "portrait": "3:4 竖屏封面，上半部先给主锤点，下半部或右下留标题区",
    }
    return hints.get(kind, "短视频封面构图，先有主锤点，再留后期标题区")


def cover_subject_priority_hints(style: str, domain: str, source: str = "") -> list[str]:
    if style == "elder_life":
        topic_kind = classify_elder_life_topic_kind(source)
        emotional_moment = "关键物件突然成为焦点、子女伸手拦住、长辈一愣、两代人对视、表情从防备到松动"
        if topic_kind != "anti_fraud":
            emotional_moment = "关键物件突然成为焦点、子女伸手拦住、长辈一愣、两代人对视、表情从防备到松动"
        return [
            "封面主视觉优先从本期主题和开头口播里提到的人物、动作、空间或关键物件中选一个最能抓住人的瞬间",
            "频道只决定统一视觉气质和受众表达，不把其他主题的固定流程和固定道具硬套进来",
            f"优先选择最有情绪峰值的一秒：{emotional_moment}，至少命中一种",
        ]

    hints = {
        "smart_home": [
            "主视觉优先让路由器、墙体剖面、插座或墙内电力线链路同框",
            "设备、空间和线路做主角，红叉、问号、印章和对勾只做小面积辅助冲突符号",
        ],
        "mechanism": [
            "主视觉优先让一个核心装置和一条正在发生的动作链路同框",
            "图标、箭头和对勾只做辅助提示，不压住主物体",
        ],
        "comparison": [
            "主视觉优先让问题状态和解决状态同时出现在同一空间里",
            "对比靠物体、光线和距离体现，不靠大面积符号压画面",
        ],
        "data": [
            "主视觉优先是产品、人物或空间，数据体量只做少量辅助块",
            "不要把数字牌、对勾或红叉做成画面主体",
        ],
        "person_story": [
            "主视觉优先让人物表情、手势和关键道具同框",
            "强调符号只做辅助，不压过人物状态",
        ],
    }
    if domain in hints:
        return hints[domain]
    fallback = {
        "elder_life": [
            "主视觉优先是本期素材里的真实人物、物件或生活瞬间",
            "提醒章、短标签和角标只做辅助，不压住人物状态",
        ],
        "tech_cinematic": [
            "主视觉优先是真实设备、空间剖面或控制链路",
            "冲突符号只做小面积辅助，不要盖住主体",
        ],
        "sports_tension": [
            "主视觉优先是人物动作、球场关系和奖杯体量",
            "比分、标记和符号只做辅助，不压过现场张力",
        ],
        "science_explainer": [
            "主视觉优先是结构剖面、实验装置或器官反应",
            "说明性图标只做辅助，不压过真实主体",
        ],
        "business_editorial": [
            "主视觉优先是产品、人物或空间体量",
            "符号、角标和涨跌提示只做辅助，不压住主角",
        ],
    }
    return fallback.get(
        style,
        [
            "主视觉优先是一个真实主角物体、人物或空间瞬间",
            "所有符号和角标都只做辅助，不压过主体",
        ],
    )


def elder_life_network_hotword_term(topic: str, content: str) -> str:
    source = "\n".join(
        filter(
            None,
            [
                topic,
                extract_meta_field(content, "封面副标题"),
                extract_bullet_field(content, "钩子"),
                extract_bullet_field(content, "主体"),
                extract_bullet_field(content, "核心知识点"),
            ],
        )
    )
    for match in re.findall(r"[“\"']([^”\"']{1,12})[”\"']", source):
        term = clean_text(match)
        if term:
            return term
    return clean_text(topic) or "这个词"


def is_elder_life_offtopic_antifraud_text(text: str) -> bool:
    return _contains_any(
        clean_text(text),
        (
            "骗老人",
            "骗子",
            "诈骗",
            "套路",
            "拉黑",
            "扣费",
            "验证码",
            "共享屏幕",
            "会议软件",
            "陌生电话",
            "陌生人",
            "转账",
            "挂断电话",
            "假客服",
            "免费礼品",
            "花言巧语",
            "套住",
            "勾走",
        ),
    )


def normalize_elder_life_network_hotword_beat(text: str, term: str) -> str:
    source = clean_text(text)
    if not source or is_elder_life_offtopic_antifraud_text(source):
        return ""
    if _contains_any(source, ("不是好话", "不尊重", "瞧不起", "轻蔑", "不太尊敬")):
        return f"{term}不是好听称呼，背后带着轻视意味"
    if _contains_any(source, ("来源", "东北", "老家伙", "老头儿", "网络流行", "网络新词", "流行词")):
        return f"{term}从老说法变成网络热词，语气也跟着变了"
    if _contains_any(source, ("不知道", "不懂", "误会", "玩笑", "外号", "对号入座")):
        return f"很多长辈第一次听见{term}，会把它当成普通玩笑"
    if _contains_any(source, ("家人", "沟通", "聊聊", "解释", "子女")):
        return f"家人要把{term}的语境讲清楚，别让误会越攒越深"
    if _contains_any(source, ("尊重", "称呼", "边界", "说话")):
        return f"别拿{term}随口打趣，称呼里也有尊重边界"
    return summarize_scene_text(source, 54)


def derive_elder_life_network_hotword_beats(content: str, mode: str, topic: str) -> list[str]:
    desired = 4 if mode == "article" else 6
    term = elder_life_network_hotword_term(topic, content)
    candidates: list[str] = []
    for item in (
        extract_bullet_field(content, "钩子"),
        extract_bullet_field(content, "主体"),
        extract_bullet_field(content, "核心知识点"),
        extract_bullet_field(content, "核心观点"),
        extract_bullet_field(content, "反常识点"),
        extract_bullet_field(content, "联系现实的角度"),
    ):
        if clean_text(item):
            candidates.append(item)

    candidates.extend(parse_highlights(content))
    candidates.extend(strip_dialogue_speaker(item) for item in parse_dialogue_lines(content, mode))

    beats = [
        normalize_elder_life_network_hotword_beat(item, term)
        for item in candidates
        if clean_text(item)
    ]
    beats.extend(
        [
            f"{term}这个词最近总被人挂在嘴边",
            f"{term}听着像外号，其实带着网络语境里的情绪",
            f"很多长辈第一次听见{term}，会把它当成随口玩笑",
            f"别急着对号入座，先把{term}的意思和语气讲明白",
            f"家人沟通时少拿{term}打趣，多解释语境和边界",
            "网络词是别人的，家里的称呼和尊重要留住",
        ]
    )
    return dedupe_clauses([summarize_scene_text(item, 54) for item in beats if clean_text(item)])[:desired]


def derive_content_scene_beats(
    content: str,
    mode: str,
    topic: str,
    style: str = "",
    source: str = "",
    desired_count: int | None = None,
) -> list[str]:
    desired = clamp_scene_count(desired_count, 4 if mode == "article" else 6) if desired_count else (4 if mode == "article" else 6)
    if style == "elder_life" and classify_elder_life_topic_kind(source or f"{topic}\n{content[:1800]}") == "network_hotword":
        beats = derive_elder_life_network_hotword_beats(content, mode, topic)
        if beats:
            return normalize_scene_prompt_count(beats, desired, topic, mode)

    dialogue_beats = select_dialogue_scene_anchors(content, mode, desired, limit=54)
    if dialogue_beats:
        return normalize_scene_prompt_count(dedupe_clauses(dialogue_beats), desired, topic, mode)

    highlights = [summarize_scene_text(item, 54) for item in parse_highlights(content) if clean_text(item)]
    if highlights:
        return normalize_scene_prompt_count(dedupe_clauses(highlights), desired, topic, mode)

    beats: list[str] = []
    for item in (
        extract_bullet_field(content, "钩子"),
        extract_bullet_field(content, "核心观点"),
        extract_bullet_field(content, "反常识点"),
        extract_bullet_field(content, "人物或场景锚点"),
        extract_bullet_field(content, "新比喻或新意象"),
    ):
        if item:
            beats.append(summarize_scene_text(item, 54))

    dialogue_lines = [strip_dialogue_speaker(item) for item in parse_dialogue_lines(content, mode)]
    if dialogue_lines:
        step = max(1, len(dialogue_lines) // max(1, desired))
        for idx in range(0, len(dialogue_lines), step):
            beats.append(summarize_scene_text(dialogue_lines[idx], 54))
            if len(beats) >= desired:
                break

    if not beats:
        beats = generic_scene_lines(topic, mode)
    return normalize_scene_prompt_count(dedupe_clauses([item for item in beats if item]), desired, topic, mode)


def build_content_scene_prompt_lines(project: dict[str, Any], template: dict[str, Any], content: str) -> list[str]:
    mode = clean_text(template.get("mode") or project.get("template_mode") or "video")
    topic = clean_text(project.get("topic_name") or first_heading(content) or "本期主题")
    style_source = "\n".join(
        filter(
            None,
            [
                topic,
                extract_bullet_field(content, "核心观点"),
                extract_bullet_field(content, "反常识点"),
                extract_bullet_field(content, "人物或场景锚点"),
                extract_bullet_field(content, "新比喻或新意象"),
                content[:1600],
            ],
        )
    )
    style = classify_material_style(style_source, template, "scene")
    domain = classify_visual_prompt_domain(style_source, "scene")
    scene_count_info = resolve_project_scene_count(project, content, mode)
    desired_count = clamp_scene_count(scene_count_info.get("final", 0), 4 if mode == "article" else 6)
    beats = derive_content_scene_beats(content, mode, topic, style=style, source=style_source, desired_count=desired_count)
    total = len(beats)
    dialogue_anchors = select_dialogue_scene_anchors(content, mode, max(total, 1), limit=78)
    lines: list[str] = []
    for idx, beat in enumerate(beats, start=1):
        visual_type = infer_visual_type(beat, beat)
        narrative = narrative_state_for_scene(idx, total)
        focus = refine_scene_focus_text(beat, content, style, domain, visual_type, narrative)
        dialogue_anchor = dialogue_anchors[min(idx - 1, len(dialogue_anchors) - 1)] if dialogue_anchors else beat
        channel_hints = channel_visual_binding_hints(template, f"{topic}\n{beat}\n{dialogue_anchor}")
        if channel_hints:
            subject_hints = [
                *channel_hints,
                *generic_scene_grounding_hints(narrative, visual_type),
            ]
        else:
            subject_hints = scene_subject_priority_hints(
                style,
                domain,
                visual_type,
                narrative,
                f"{topic}\n{beat}\n{dialogue_anchor}\n{content[:900]}",
            )
        subject_rules = dedupe_clauses(
            [compact_prompt_rule(item, 58) for item in subject_hints if clean_text(item)]
        )[:2]
        concrete_hint = concrete_visual_hint_from_anchor(
            focus or dialogue_anchor,
            f"{topic}\n{beat}\n{dialogue_anchor}\n{content[:600]}",
            "scene",
        )
        stage_clause = SCENE_STAGE_VISUAL_CLAUSES.get(narrative, "")
        clauses = [
            f"16:9 横屏，第 {idx} 张场景图",
            f"本镜头先画：{focus}",
            f"对应口播：{dialogue_anchor}",
            concrete_hint,
            f"镜头变化：{scene_viewpoint_hint(idx, total, visual_type)}",
            f"叙事阶段：{narrative}，{stage_clause}" if stage_clause else f"叙事阶段：{narrative}",
            f"频道气质：{compact_prompt_rule(content_scene_style_hint(style, template), 48)}",
            *subject_rules,
            f"构图：{content_visual_layout_hint(visual_type)}",
            "纪录片镜头感，真实摄影质感，主体突出，高对比光影，有前后景层次",
            "与前后镜头换主体动作、空间关系或视角",
            "留出后期字幕安全区；默认不生成可读文字，信息用无字界面、图标、色块和动作关系表达",
        ]
        line = compact_prompt_rule("，".join(dedupe_clauses([item for item in clauses if clean_text(item)])), 360).strip("，,。") + "。"
        lines.append(line)
    return lines


def build_content_cover_prompt(project: dict[str, Any], template: dict[str, Any], content: str, kind: str) -> str:
    mode = clean_text(template.get("mode") or project.get("template_mode") or "video")
    topic = clean_text(project.get("topic_name") or first_heading(content) or "本期主题")
    summary = summarize_content(content, mode)
    cover_title = clean_text(summary.get("cover_title") or first_heading(content) or topic)
    cover_short_title = compact_cover_title_for_prompt(cover_title, topic)
    subtitle = clean_text(summary.get("cover_subtitle") or extract_bullet_field(content, "封面副标题"))
    brand = clean_text(template.get("brand_name") or template.get("name") or template.get("key") or project.get("template") or "")
    style_source = "\n".join(
        filter(
            None,
            [
                topic,
                cover_title,
                subtitle,
                extract_bullet_field(content, "钩子"),
                extract_bullet_field(content, "核心观点"),
                extract_bullet_field(content, "反常识点"),
            ],
        )
    )
    style = classify_material_style(style_source, template, "cover")
    domain = classify_visual_prompt_domain(style_source, "cover")
    cover_anchor_lines = select_dialogue_scene_anchors(content, mode, 1, limit=86)
    cover_anchor = cover_anchor_lines[0] if cover_anchor_lines else clean_text(extract_bullet_field(content, "钩子"))
    channel_hints = channel_visual_binding_hints(template, f"{topic}\n{cover_title}\n{subtitle}\n{cover_anchor}")
    if channel_hints:
        subject_hints = [
            *channel_hints,
            *generic_cover_grounding_hints(),
        ]
    else:
        subject_hints = cover_subject_priority_hints(style, domain, f"{topic}\n{cover_title}\n{subtitle}\n{content[:900]}")
    focus_candidates = [
        subtitle,
        extract_bullet_field(content, "核心观点"),
        extract_bullet_field(content, "反常识点"),
        extract_bullet_field(content, "人物或场景锚点"),
        extract_bullet_field(content, "新比喻或新意象"),
        extract_bullet_field(content, "前3秒视觉钩子"),
        extract_bullet_field(content, "钩子"),
    ]
    if style == "elder_life" and classify_elder_life_topic_kind(style_source) == "network_hotword":
        focus_candidates = [
            item
            for item in focus_candidates
            if clean_text(item) and not is_elder_life_offtopic_antifraud_text(item)
        ]
    focus_candidates.extend(derive_content_scene_beats(content, mode, topic, style=style, source=style_source)[:3])
    focuses = dedupe_clauses([compact_cover_focus_text(item, style, domain, 50) for item in focus_candidates if clean_text(item)])
    concrete_hint = concrete_visual_hint_from_anchor(
        (focuses[0] if focuses else "") or cover_anchor or cover_title or topic,
        f"{topic}\n{cover_title}\n{subtitle}\n{cover_anchor}\n{content[:600]}",
        "cover",
    )
    subject_rules = dedupe_clauses(
        [compact_prompt_rule(item, 58) for item in subject_hints if clean_text(item)]
    )[:2]

    clauses = [
        cover_variant_layout_hint(kind),
        f"封面先画：{focuses[0]}" if focuses else f"封面先画：{cover_title or topic}",
        concrete_hint,
        f"频道气质：{compact_prompt_rule(content_cover_style_hint(style, template), 52)}",
        "纪录片封面镜头感，真实摄影质感，主体突出，高对比光影",
    ]
    clauses.extend(subject_rules)
    if cover_anchor:
        clauses.append(f"开头口播锚点：{cover_anchor}")
    if len(focuses) > 1:
        clauses.append(f"再用{focuses[1]}补出冲突、结果或空间关系")
    if len(focuses) > 2:
        clauses.append(f"可再带出{focuses[2]}作为辅助线索")
    if cover_short_title:
        clauses.append(f"主标题 5-8 字清晰大字：{cover_short_title}")
    if subtitle:
        clauses.append(f"副标题一句短字：{summarize_scene_text(subtitle, 18)}")
    if brand:
        clauses.append(f"左上角或固定角标放频道名/作者名：{brand}")
    clauses.append("文字必须短、清楚、少量，避免长段正文、脚注、免责声明")
    clauses.append("除主标题、副标题和频道角标外，口播里的服务名、金额、按钮名、平台名和引号内容不要额外原样写进画面")
    clauses.append("保留后期叠标题和字幕的安全区域")
    clauses.append("保留一个固定角标或专属色块形成频道系列感")
    return compact_prompt_rule("，".join(dedupe_clauses([item for item in clauses if item])), 320)


def build_dynamic_image_prompt_section(project: dict[str, Any], template: dict[str, Any], content: str) -> str:
    mode = clean_text(template.get("mode") or project.get("template_mode") or "video")
    scene_lines = build_content_scene_prompt_lines(project, template, content)
    duration = extract_meta_field(content, "时长") or summarize_content(content, mode).get("duration", "")
    if mode == "article":
        section_lines = [
            "### 横屏封面图（头图，16:9 横屏）",
            build_content_cover_prompt(project, template, content, "landscape"),
            "",
            f"### 场景图（正文配图，全部 16:9 横屏，共 {len(scene_lines)} 张）",
        ]
        section_lines.extend(f"{idx}. {line}" for idx, line in enumerate(scene_lines, start=1))
        return "\n".join(section_lines).strip()

    count_line = f"### 场景图（全部16:9横屏，按目标时长 {duration or '3-10分钟'}，共{len(scene_lines)}张）"
    section_lines = [
        "### 横屏封面图 (4:3)",
        build_content_cover_prompt(project, template, content, "landscape"),
        "",
        "### 竖屏封面图 (3:4)",
        build_content_cover_prompt(project, template, content, "portrait"),
        "",
        count_line,
        "",
    ]
    section_lines.extend(f"{idx}. {line}" for idx, line in enumerate(scene_lines, start=1))
    return "\n".join(section_lines).strip()


def refresh_content_image_prompts(project: dict[str, Any], template: dict[str, Any], content: str) -> str:
    rebuilt = build_dynamic_image_prompt_section(project, template, content)
    return replace_section(content, "图片提示词", rebuilt, level=2)


def summarize_content(content: str, mode: str) -> dict[str, Any]:
    title = first_heading(content)
    meta_publish_title = extract_meta_field(content, "发布标题")
    cover_title = extract_meta_field(content, "封面主标题") or meta_publish_title or title or ""
    cover_subtitle = extract_meta_field(content, "封面副标题")
    publish_title = extract_meta_field(content, "推荐发布标题") or meta_publish_title or title
    duration = extract_meta_field(content, "时长")
    scene_prompts = parse_scene_prompts(content, mode)
    highlights = parse_highlights(content)
    dialogue_lines = parse_dialogue_lines(content, mode)

    if not duration:
        if mode == "article":
            duration = "图文"
        elif len(dialogue_lines) >= 36:
            duration = "9-10分钟"
        elif len(dialogue_lines) >= 26:
            duration = "7-8分钟"
        elif len(dialogue_lines) >= 18:
            duration = "5-6分钟"
        else:
            duration = "3-4分钟"

    score_text = extract_meta_field(content, "选题评分")
    score_match = re.search(r"=\s*([0-5](?:\.\d)?)|([0-5](?:\.\d)?)\s*分", score_text)
    topic_score = score_match.group(1) or score_match.group(2) if score_match else ""
    if not topic_score:
        heuristic = min(5.0, 3.4 + min(len(scene_prompts), 12) * 0.1)
        topic_score = f"{heuristic:.1f}"

    body_len = len(re.sub(r"\s+", "", content or ""))
    return {
        "video_title": title,
        "cover_title": cover_title or fallback_cover_title(title or publish_title or "短片工坊"),
        "cover_subtitle": cover_subtitle,
        "publish_title": publish_title,
        "duration": duration,
        "dialogue_count": len(dialogue_lines),
        "scene_count": len(scene_prompts),
        "body_len": body_len,
        "highlight_count": len(highlights),
        "topic_score": topic_score,
        "mode": mode,
    }


def topic_score_report(project: dict[str, Any], brief: str) -> dict[str, Any]:
    topic = clean_text(project["topic_name"])
    excerpt = clean_text(brief or topic)
    familiarity = 1.0 if len(topic) <= 18 else 0.7
    contrast = 0.9 if "为什么" in topic or "怎么" in topic or "真相" in topic else 0.7
    story = 0.9 if len(excerpt) >= 18 else 0.6
    reality = 0.8 if any(word in excerpt for word in ["用户", "生活", "今天", "现实", "场景"]) else 0.6
    visual = 0.9 if any(word in excerpt for word in ["对比", "案例", "画面", "人物", "场景"]) else 0.7
    total = round(familiarity + contrast + story + reality + visual, 1)
    return {
        "topic": topic,
        "brief_excerpt": excerpt[:120],
        "total_score": total,
        "scorecard": [
            {"name": "熟悉度", "score": familiarity, "reason": "主题是否能让普通观众一眼明白在讲什么。"},
            {"name": "反常识", "score": contrast, "reason": "是否存在明显的认知反转或隐藏机制。"},
            {"name": "故事性", "score": story, "reason": "是否能拆成起因、经过、结果的一条线。"},
            {"name": "现实连接", "score": reality, "reason": "结尾能不能自然回到今天的生活场景。"},
            {"name": "可视化", "score": visual, "reason": "能否拆成多张有明确信息点的场景图。"},
        ],
        "verdict": "分数达标时适合进入脚本生成；分数偏低时应先换角度或缩短篇幅。",
    }


def viral_doctor_report(project: dict[str, Any], content: str) -> dict[str, Any]:
    scene_count = len(parse_scene_prompts(content, project.get("template_mode", "video")))
    has_hook = any(token in content for token in ["你以为", "你知道吗", "但你猜", "为什么"])
    overall = round(min(5.0, 3.0 + scene_count * 0.15 + (0.4 if has_hook else 0.0)), 1)
    return {
        "overall_score": overall,
        "top_issues": [
            {
                "where": "开头钩子",
                "issue": "如果第一句不够反常识，用户滑走会非常快。",
                "fix": "把结论后置半句，先抛反常识问题或具体细节。",
            },
            {
                "where": "中段转折",
                "issue": "如果全程都在解释，没有案例和转折，信息会显得很平。",
                "fix": "在中段加入一个更具体的例子，或者旧做法 vs 新理解的对比。",
            },
        ],
        "performance_read": "当前稿子已经具备成片结构，但是否像爆款，还取决于开头和中段的抓力。",
        "verdict": "可以直接生产；想更像原软件的成稿风格，优先强化钩子、字幕金句和场景图对应关系。",
    }


def viral_doctor_report(project: dict[str, Any], content: str) -> dict[str, Any]:
    mode = clean_text(project.get("template_mode") or "video")
    scene_count = len(parse_scene_prompts(content, mode))
    engagement = content_engagement_report(content, mode)
    return {
        "overall_score": engagement["overall_score"],
        "opening_score": engagement["opening_score"],
        "retention_score": engagement["retention_score"],
        "interaction_score": engagement["interaction_score"],
        "scene_count": scene_count,
        "top_issues": engagement["issues"][:3]
        or [
            {
                "where": "整体表达",
                "issue": "结构完整，但金句、推进和互动还可以继续抬高。",
                "fix": "继续收紧首句、关键转折句和结尾评论钩子。",
            }
        ],
        "performance_read": engagement["performance_read"],
        "verdict": engagement["verdict"],
    }


def title_cover_ab_report(project: dict[str, Any], content: str, count: int = 6) -> dict[str, Any]:
    summary = summarize_content(content, project.get("template_mode", "video"))
    base_title = summary.get("publish_title") or project["topic_name"]
    base_cover = summary.get("cover_title") or fallback_cover_title(project["topic_name"])
    subtitle = summary.get("cover_subtitle") or fallback_cover_subtitle(project["topic_name"])
    hook_types = ["反常识", "疑问句", "结果先行", "误区纠正", "数字冲击", "现实连接"]
    variants = []
    for idx in range(count):
        variants.append(
            {
                "video_title": f"{base_title}（方案 {idx + 1}）",
                "cover_title": f"{base_cover}",
                "cover_subtitle": subtitle,
                "hook_type": hook_types[idx % len(hook_types)],
                "risk": "低",
                "why": "保留熟悉对象，同时在句式上做差异化测试，更接近原软件的标题 A/B 工作流。",
            }
        )
    return {
        "recommended_index": 0,
        "variants": variants,
        "verdict": "默认先用第 1 套，再根据平台反馈替换钩子句式。",
    }


def infer_platform_profile(project: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    template_name = clean_text(template.get("name") or template.get("key") or project.get("template") or "")
    if mode == "article":
        return {
            "platform": "图文平台",
            "format": "图文卡片/长图文",
            "voice": "密度高、标题明确、每屏一个观点",
            "success_signals": ["首屏标题有冲突", "每页只讲一个点", "评论区有表达空间"],
        }
    if "双人" in template_name:
        return {
            "platform": "抖音/视频号",
            "format": "双人播客式横屏短视频",
            "voice": "一问一答、追问拆解、生活吐槽带出技术或观点",
            "success_signals": ["前三秒反常识", "两人轮替节奏清楚", "每 20-40 秒有一个新信息点"],
        }
    return {
        "platform": "抖音/视频号",
        "format": "单人口播横屏短视频",
        "voice": "朋友式讲故事、反常识开场、案例推动",
        "success_signals": ["开头问题尖锐", "中段有转折", "结尾能落到现实用途"],
    }


def classify_title_strategy(text: str) -> str:
    title = clean_text(text)
    if re.search(r"\d", title):
        return "数字冲击"
    if any(token in title for token in ("为什么", "怎么", "吗", "？", "?")):
        return "疑问钩子"
    if any(token in title for token in ("不是", "真相", "误区", "反而", "其实", "藏在")):
        return "反常识"
    if any(token in title for token in ("你家", "普通人", "别再", "总是", "痛点", "废了")):
        return "痛点共鸣"
    if any(token in title for token in ("最好", "最强", "第一", "必看")):
        return "强判断"
    return "结果先行"


def content_strategy_report(
    project: dict[str, Any],
    template: dict[str, Any],
    brief: str,
    tavily_topic: str = "general",
    references: list[dict[str, Any]] | None = None,
    content: str = "",
) -> dict[str, Any]:
    topic = clean_text(project.get("topic_name") or "")
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    source = clean_text("\n".join([topic, brief, content]))
    summary = summarize_content(content, mode) if content else {}
    score = topic_score_report(project, brief)
    title = clean_text(summary.get("publish_title") or summary.get("video_title") or topic)
    platform = infer_platform_profile(project, template)
    refs = references or []
    ref_titles = [clean_text(str(item.get("title") or "")) for item in refs[:5] if isinstance(item, dict)]

    contradiction = "旧理解和真实机制之间的反差"
    if any(token in source for token in ("断网", "掉线", "废铁", "失效")):
        contradiction = "用户以为是网络问题，真正关键可能在底层连接方式"
    elif any(token in source for token in ("便宜", "贵", "成本", "价格")):
        contradiction = "表面看是价格问题，背后其实是价值和风险判断"
    elif any(token in source for token in ("AI", "模型", "自动化")):
        contradiction = "大家只看工具热闹，真正差异在流程和验证能力"

    emotion_curve = ["好奇", "共鸣", "意外", "理解", "想试/想评论"]
    if mode == "article":
        emotion_curve = ["被标题钩住", "发现误区", "逐页拆解", "得到结论", "愿意收藏"]

    return {
        "generated_at": storage.now_ts(),
        "topic": topic,
        "template": clean_text(template.get("name") or template.get("key") or project.get("template") or ""),
        "platform_profile": platform,
        "tavily_topic": tavily_topic or "general",
        "reference_count": len(refs),
        "reference_titles": ref_titles,
        "topic_score": score,
        "insights": {
            "core_viewpoint": clean_text(extract_meta_field(content, "核心观点")) if content else f"{topic}最值得讲的不是表面结论，而是背后的因果机制",
            "counter_intuition": contradiction,
            "audience_pain": "观众已经遇到过类似场景，但不知道真正原因是什么",
            "knowledge_payload": "把概念拆成起因、机制、证据、应用四段",
            "story_engine": "痛点开场 -> 旧理解失效 -> 新机制解释 -> 现实场景回扣",
            "persuasion_strategy": "先共情，再反转，再用具体画面降低理解成本",
            "title_strategy": classify_title_strategy(title),
            "opening_hook": clean_text(extract_meta_field(content, "钩子")) if content else f"你以为「{topic}」只是普通问题？真正关键藏在另一层。",
            "golden_three_seconds": clean_text(extract_meta_field(content, "前3秒视觉钩子")) if content else "先给一个强痛点画面，再抛反常识问题。",
            "emotion_curve": emotion_curve,
            "interaction_hook": clean_text(extract_meta_field(content, "互动钩子")) or "你遇到过类似情况吗？评论区聊聊。",
        },
        "output_contract": {
            "content_md": "标题、Meta、脚本/正文、重点字幕、图片提示词、参考资料",
            "content_audit": "平台适配、AI味、事实风险、标题策略、前三秒钩子",
            "scene_plan": "每镜的叙事状态、视觉锚点、生图提示词、运动和转场建议",
        },
    }


def content_audit_report(
    project: dict[str, Any],
    template: dict[str, Any],
    brief: str,
    content: str,
    references: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    summary = summarize_content(content, mode)
    dialogue_lines = parse_dialogue_lines(content, mode)
    scene_prompts = parse_scene_prompts(content, mode)
    highlights = parse_highlights(content)
    title = clean_text(summary.get("publish_title") or summary.get("video_title") or project.get("topic_name") or "")
    plain = clean_text(content)
    issues: list[dict[str, str]] = []

    def add_issue(level: str, where: str, issue: str, fix: str) -> None:
        issues.append({"level": level, "where": where, "issue": issue, "fix": fix})

    hook_text = "\n".join(dialogue_lines[:3]) if dialogue_lines else plain[:160]
    if not any(token in hook_text for token in ("你", "为什么", "怎么", "以为", "知道", "断网", "废", "真相", "其实")):
        add_issue("warn", "前三秒钩子", "开头缺少直接问题、痛点或反常识信号。", "第一句改成观众能立刻代入的问题或具体痛点。")
    if mode != "article" and len(dialogue_lines) < 8:
        add_issue("warn", "脚本长度", "对话/口播句数偏少，成片可能显得薄。", "补足起因、机制、例子、回扣四段。")
    if len(scene_prompts) < (4 if mode == "article" else 6):
        add_issue("warn", "场景图", "场景图数量偏少，画面变化不够支撑短视频节奏。", "按音频长度补到 6-10 个明确镜头。")
    if not highlights and mode != "article":
        add_issue("warn", "重点字幕", "没有重点字幕，后续高亮字幕缺少依据。", "抽 4-8 条短句作为金句/转折句。")
    if len(references or []) == 0:
        add_issue("info", "事实依据", "当前没有参考资料记录，事实型选题可追溯性偏弱。", "补联网资料或历史稿引用，保留 references.json。")

    ai_smell_tokens = ["首先", "其次", "最后", "综上", "总而言之", "在当今社会", "值得注意的是", "不可忽视"]
    ai_smell_hits = [token for token in ai_smell_tokens if token in plain]
    if len(ai_smell_hits) >= 2:
        add_issue("warn", "表达风格", f"存在较明显 AI 公文感词汇：{', '.join(ai_smell_hits[:4])}。", "改成更口语的追问、吐槽、具体细节和短句。")

    risky_tokens = ["保证", "稳赚", "百分百", "治疗", "治愈", "最权威", "绝对", "内幕消息"]
    risk_hits = [token for token in risky_tokens if token in plain]
    if risk_hits:
        add_issue("risk", "平台风险", f"疑似绝对化或高风险词：{', '.join(risk_hits)}。", "改成来源限定、概率表达或经验判断。")

    title_strategy = classify_title_strategy(title)
    viral = viral_doctor_report(project, content)
    ab = title_cover_ab_report(project, content, 6)
    score = 100
    score -= sum(18 for item in issues if item["level"] == "risk")
    score -= sum(9 for item in issues if item["level"] == "warn")
    score -= sum(3 for item in issues if item["level"] == "info")
    score = max(0, min(100, score))
    if score >= 86:
        verdict = "可以直接进入生产。"
    elif score >= 70:
        verdict = "可以生产，但建议先修开头、标题或场景图。"
    else:
        verdict = "建议先重写关键段落再进入生产。"

    return {
        "generated_at": storage.now_ts(),
        "score": score,
        "verdict": verdict,
        "rewrite_recommended": score < 70 or any(item["level"] == "risk" for item in issues),
        "summary": summary,
        "platform_profile": infer_platform_profile(project, template),
        "title_strategy": title_strategy,
        "metrics": {
            "dialogue_count": len(dialogue_lines),
            "scene_prompt_count": len(scene_prompts),
            "highlight_count": len(highlights),
            "reference_count": len(references or []),
            "body_len": summary.get("body_len", len(plain)),
        },
        "issues": issues,
        "viral_doctor": viral,
        "title_cover_ab": ab,
    }


def build_content_artifacts(
    project: dict[str, Any],
    template: dict[str, Any],
    brief: str,
    tavily_topic: str,
    references: list[dict[str, Any]],
    content: str,
) -> dict[str, Any]:
    strategy = content_strategy_report(project, template, brief, tavily_topic, references, content)
    audit = content_audit_report(project, template, brief, content, references)
    return {"strategy": strategy, "audit": audit}


def unwrap_ddg_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url or "")
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = urllib.parse.parse_qs(parsed.query)
        target = query.get("uddg", [""])[0]
        if target:
            return urllib.parse.unquote(target)
    return url


def local_article_references(project: dict[str, Any], template: dict[str, Any], brief: str) -> list[dict[str, Any]]:
    query_tokens = extract_tokens(f"{project['topic_name']} {brief}")
    refs: list[dict[str, Any]] = []
    for meta in storage.list_projects():
        if meta["id"] == project["id"]:
            continue
        if meta.get("template") != project.get("template"):
            continue
        content = storage.get_content(meta["id"])
        if not clean_text(content):
            continue
        score = overlap_score(query_tokens, f"{meta.get('topic_name', '')}\n{content[:4000]}")
        if score <= 0:
            continue
        summary = storage.get_summary(meta["id"])
        refs.append(
            {
                "index": 0,
                "title": summary.get("publish_title") or summary.get("video_title") or meta["topic_name"],
                "url": storage.project_file(meta["id"], "content.md").as_posix(),
                "source": "历史稿",
                "query": project["topic_name"],
                "snippet": truncate(content),
                "score": round(score, 3),
                "has_content": True,
            }
        )
    refs.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return refs[:3]


def search_tavily(query: str, tavily_topic: str, limit: int) -> list[dict[str, Any]]:
    env = runtime_env()
    api_key = clean_text(env.get("TAVILY_API_KEY", ""))
    if not api_key:
        return []
    payload = {
        "api_key": api_key,
        "query": query,
        "topic": tavily_topic or env.get("TAVILY_TOPIC", "general") or "general",
        "search_depth": "basic",
        "max_results": max(1, min(limit, 10)),
        "include_raw_content": False,
    }
    request = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    refs = []
    for index, item in enumerate(body.get("results", []), start=1):
        snippet = item.get("content") or item.get("snippet") or ""
        refs.append(
            {
                "index": index - 1,
                "title": clean_text(item.get("title") or f"检索结果 {index}"),
                "url": clean_text(item.get("url") or ""),
                "source": "Tavily",
                "query": query,
                "snippet": truncate(snippet),
                "score": round(float(item.get("score") or 0.0), 3),
                "has_content": bool(clean_text(snippet)),
            }
        )
    return refs


def search_duckduckgo(query: str, limit: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query})
    request = urllib.request.Request(
        f"https://duckduckgo.com/html/?{params}",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw_html = response.read().decode("utf-8", "ignore")
    except Exception:
        return []

    refs = []
    for index, match in enumerate(DDG_RESULT_RE.finditer(raw_html), start=1):
        href, title_html, block = match.groups()
        snippet_match = DDG_SNIPPET_RE.search(block)
        snippet_html = ""
        if snippet_match:
            snippet_html = snippet_match.group(1) or snippet_match.group(2) or ""
        refs.append(
            {
                "index": index - 1,
                "title": html_to_text(title_html) or f"DuckDuckGo 结果 {index}",
                "url": unwrap_ddg_url(href),
                "source": "DuckDuckGo",
                "query": query,
                "snippet": truncate(html_to_text(snippet_html)),
                "score": round(max(0.0, 1.0 - index * 0.08), 3),
                "has_content": bool(clean_text(snippet_html)),
            }
        )
        if len(refs) >= limit:
            break
    return refs


def dedupe_references(references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in references:
        key = clean_text(item.get("url") or "") or clean_text(item.get("title") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        entry = dict(item)
        entry["index"] = len(deduped)
        deduped.append(entry)
    return deduped


def read_reference_preview(project_id: int, index: int) -> dict[str, Any]:
    references = storage.get_references(project_id)
    if index < 0 or index >= len(references):
        raise IndexError(index)

    reference = dict(references[index])
    url = clean_text(reference.get("url") or "")
    snippet = clean_text(reference.get("snippet") or "")
    content = ""
    content_type = "snippet"
    resolved_path = ""

    if url:
        candidate = Path(url)
        if candidate.exists() and candidate.is_file():
            resolved_path = str(candidate.resolve())
            content = candidate.read_text(encoding="utf-8", errors="ignore")
            content_type = "markdown" if candidate.suffix.lower() in {".md", ".markdown"} else "text"
        elif url.startswith(("http://", "https://")):
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    payload = response.read().decode("utf-8", "ignore")
                    content = html_to_text(payload)
                    content_type = "html"
            except Exception:
                content = ""

    if not content:
        title = clean_text(reference.get("title") or "未命名参考")
        lines = [f"# {title}", ""]
        if url:
            lines.append(f"链接: {url}")
        if reference.get("source"):
            lines.append(f"来源: {reference['source']}")
        if snippet:
            lines.extend(["", "摘要", snippet])
        content = "\n".join(lines).strip()

    return {
        "index": index,
        "reference": reference,
        "content": content,
        "content_type": content_type,
        "resolved_path": resolved_path,
    }


def build_reference_context(project: dict[str, Any], template: dict[str, Any], brief: str, tavily_topic: str) -> dict[str, Any]:
    env = runtime_env()
    max_refs = max(3, min(int(env.get("TAVILY_MAX_REFERENCES", "20") or 20), 20))
    topic = clean_text(project["topic_name"])
    compact_brief = truncate(brief, 200)
    query = topic if not compact_brief else f"{topic} {compact_brief}"

    local_refs = local_article_references(project, template, brief)
    web_refs = search_tavily(query, tavily_topic, max_refs)
    if not web_refs:
        web_refs = search_duckduckgo(query, min(max_refs, 8))

    refs = dedupe_references(local_refs + web_refs)[:max_refs]
    return {
        "query": query,
        "local_refs": local_refs,
        "web_refs": web_refs,
        "references": refs,
    }


def format_reference_block(title: str, refs: list[dict[str, Any]]) -> str:
    if not refs:
        return f"{title}\n- 无"
    lines = [title]
    for item in refs:
        snippet = item.get("snippet") or ""
        lines.append(
            f"- 标题: {item.get('title') or '未命名'}\n"
            f"  来源: {item.get('source') or '未知'}\n"
            f"  链接: {item.get('url') or '无'}\n"
            f"  摘要: {snippet or '无'}"
        )
    return "\n".join(lines)


def message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(getattr(item, "text", "") or getattr(item, "content", "") or ""))
        return "\n".join(part for part in parts if part).strip()
    return str(content or "").strip()


def compose_deepseek_messages(
    project: dict[str, Any],
    template: dict[str, Any],
    brief: str,
    tavily_topic: str,
    context: dict[str, Any],
) -> list[dict[str, str]]:
    template_prompt = str(template.get("prompt") or "").strip()
    mode = clean_text(template.get("mode") or project.get("template_mode") or "video")
    voice_mode = clean_text(template.get("voice_mode") or "")
    template_identity = {
        "key": template.get("key") or project.get("template") or "",
        "name": template.get("name") or template.get("key") or "",
        "brand_name": template.get("brand_name") or template.get("name") or "",
        "mode": mode,
        "voice_mode": voice_mode,
        "target_audience": template.get("target_audience") or "",
        "channel_voice": template.get("channel_voice") or "",
        "visual_strategy": template.get("visual_strategy") or "",
        "forbidden_rules": template.get("forbidden_rules") or "",
        "interaction_goal": template.get("interaction_goal") or "",
        "topic_mining_hint": template.get("topic_mining_hint") or "",
        "cover_style": template.get("cover_style") or "",
        "release_tags": template.get("release_tags") or "",
    }
    channel_profile = channel_profile_text(template)
    learning = channel_learning_prompt_block(project, template)
    system_rules = """
你现在要为短片工坊生成最终可落地的 content.md。

优先级：
1. 当前频道模板 prompt.md 是最高优先级。频道的人设、语气、角色关系、栏目结构、时长、封面气质、镜头语言、禁忌和发布习惯，都必须服从频道模板。
2. 当前主题和 brief 只提供本期素材，不得覆盖频道模板风格。不同频道必须生成不同口吻和不同视觉气质。
3. 下方通用要求只用于保证短片工坊生产链路能解析，不允许把所有频道改写成同一种“通用知识科普/爆款反常识”风格。

硬性要求：
1. 只输出最终的 Markdown 成品，不要解释，不要前言，不要致谢。
2. 第一行必须直接从 # 或 ## 标题开始。
3. 如果给了历史稿参考，只能借鉴风格、视角和连续创作语气，不能照搬旧稿。
4. 如果给了联网资料，涉及最新事实、时间、金额、排名、参数时优先以联网资料为准；不确定就保守表述。
5. 你的输出必须严格遵守当前模板 prompt 约定的章节、角色标签、图片提示词和时长要求。
6. 如果频道模板没有明确章节，按原版兼容结构输出：## Meta、## 原始材料简述、视频频道输出 ## 对话脚本 或 ## 口播脚本、## 重点字幕、## 图片提示词、## 参考资料；图文频道输出 ## 正文、## 图片提示词、## 参考资料。
7. 视频频道的图片提示词必须包含 ### 横屏封面图 (4:3)、### 竖屏封面图 (3:4)、### 场景图；场景图用 1. 2. 3. 编号，数量要匹配脚本时长和语音节奏，通常 3-4 分钟 6 张左右、5-6 分钟 7-10 张左右。
8. 封面提示词要和频道个人 IP 强关联，允许直接生成清晰可读的中文主标题、短副标题和频道名/作者角标；场景图只允许 1-3 个短标签或警示词，避免长段正文、脚注、免责声明、水印和乱码。
9. 每张场景图必须根据对应脚本段落和本期素材重新设计，不要复制同一种纸面手账、档案卡、旧纸、胶带、拼贴背景；除非频道模板或题材明确要求。
""".strip()

    user_parts = [
        f"当前频道配置：{json.dumps(template_identity, ensure_ascii=False)}",
        f"频道中枢：\n{channel_profile or '未填写结构化频道中枢，请严格以 prompt.md 为准。'}",
        learning,
        f"当前主题：{clean_text(project['topic_name'])}",
        f"联网话题：{tavily_topic or 'general'}",
        "",
        "原始 brief：",
        brief.strip() or "无",
        "",
        format_reference_block("历史稿参考：", context.get("local_refs", [])),
        "",
        format_reference_block("公开资料参考：", context.get("web_refs", [])),
        "",
        "请严格基于上面的模板规则与材料，一次性写出完整 content.md。",
    ]

    return [
        {"role": "system", "content": template_prompt + "\n\n" + system_rules},
        {"role": "user", "content": "\n".join(user_parts).strip()},
    ]


def render_fallback_story_content(
    project: dict[str, Any],
    template: dict[str, Any],
    brief: str,
    refs: list[dict[str, Any]],
    speaker_mode: str,
) -> str:
    topic = clean_text(project["topic_name"])
    cover_title = fallback_cover_title(topic)
    publish_title = fallback_publish_title(topic)
    cover_subtitle = fallback_cover_subtitle(topic)
    scene_lines = generic_scene_lines(topic, "video")
    duration = "5-6分钟" if len(brief) > 60 else "3-4分钟"

    reference_summary = "；".join(item["title"] for item in refs[:3]) or f"{topic}的公开资料"
    if speaker_mode == "dual":
        dialogue = [
            f"【女】你以为「{topic}」只是表面这个问题？其实真正有意思的，是它背后的那套逻辑。",
            f"【男】对，而且这事最容易被忽略的地方，不是答案本身，而是它为什么会变成今天这个样子。",
            f"【女】那我们就别绕了，先说最关键的起点，到底是哪一步让它开始变味的。",
            f"【男】通常要先把背景讲清楚。只看结果，大家会觉得这是常识；把过程摊开，才发现里面全是转折。",
            f"【女】也就是说，观众真正想听的，不是定义，而是这件事怎么一步步走到这里。",
            f"【男】没错。所以我们会先拆误区，再拿例子，最后再回到今天的人为什么还会被这个问题困住。",
            f"【女】那中间最容易讲错的地方是什么？",
            f"【男】最容易错的是把它讲成概念清单。真正有效的讲法，是让人看到一条完整的因果线。",
            f"【女】所以你最后想让观众记住的，不是术语，而是那个一听就懂的判断。",
            f"【男】对。你下次再遇到「{topic}」，至少知道先看哪个关键点，而不是被表面信息带着跑。",
        ]
    else:
        dialogue = [
            f"【主播】你以为「{topic}」只是个普通话题？真正难的，从来不是定义，而是它背后的那条因果线。",
            f"【主播】很多人一上来就急着下结论，但这事最值得听的，恰恰是它怎么一步步演变成今天这样。",
            f"【主播】如果只背概念，你会觉得它很抽象。可一旦把背景、转折和结果摊开，它就像一个很完整的故事。",
            f"【主播】先说起点。每个类似问题之所以会反复出现，往往都不是因为答案没人知道，而是大家盯错了地方。",
            f"【主播】接着看中段。真正拉开差距的，通常不是表面动作，而是那个被忽略的关键变量。",
            f"【主播】再往下拆，你就会发现，很多我们以为的常识，其实只是讲了半截的旧理解。",
            f"【主播】这时候最有效的办法，不是继续堆术语，而是拿一个具体例子，把它讲成看得见的画面。",
            f"【主播】最后回到今天。下次你再碰到「{topic}」，至少知道先看哪里，而不是被表面信息牵着走。",
        ]

    highlight_lines = [
        f"{topic}真正难的，从来不是表面定义",
        "把背景、转折、结果讲成一条线，内容才会成立",
        "别只背概念，先找那个真正影响结果的变量",
        "回到现实场景，观众才会觉得这期内容有用",
    ]

    scene_prompt_lines = [
        f"16:9 横屏，围绕「{topic}」做第 {idx + 1} 张场景图，画面重点是：{line}。可加入 1-3 个清晰短标签或警示词，底部不要脚注、免责声明或长段正文。"
        for idx, line in enumerate(scene_lines)
    ]

    refs_block = "\n".join(f"- [{item['title']}]({item['url']}) - {item['snippet']}" for item in refs) or "- 无"

    return (
        f"# {cover_title}\n\n"
        f"## Meta\n"
        f"- 封面副标题: {cover_subtitle}\n"
        f"- 核心观点: {topic}真正值得讲的，是背后那条因果线\n"
        f"- 时长: {duration}\n"
        f"- 推荐发布标题: {publish_title}\n"
        f"- 钩子: 你以为「{topic}」只是个普通问题？真正有意思的是它背后的那套逻辑。\n"
        f"- 互动钩子: 你自己最容易在哪一步想当然？评论区留一句。\n"
        f"- 免责声明:\n\n"
        f"## 原始材料简述\n"
        f"- 主体: {topic}\n"
        f"- 核心知识点: 把这个主题讲成能听懂、能记住、能落地的一条线\n"
        f"- 反常识点: 大家通常只看表面，不看真正的关键变量\n"
        f"- 本期差异化抓手: {reference_summary}\n"
        f"- 联系现实的角度: 下次再次遇到这个主题时，用户知道先看哪里\n\n"
        f"## 对话脚本\n\n"
        + "\n\n".join(dialogue)
        + "\n\n## 重点字幕\n"
        + "\n".join(f"{idx + 1}. {line}" for idx, line in enumerate(highlight_lines))
        + "\n\n## 图片提示词\n\n"
        + "### 横屏封面图 (4:3)\n"
        + f"围绕「{topic}」制作 4:3 横屏封面，主标题「{cover_title}」要清晰可读，副标题「{cover_subtitle}」可小字出现，频道名保持固定角标，文字短而醒目。\n\n"
        + "### 竖屏封面图 (3:4)\n"
        + f"围绕「{topic}」制作 3:4 竖屏封面，主标题「{cover_title}」要清晰可读，副标题「{cover_subtitle}」可小字出现，频道名保持固定角标，文字短而醒目。\n\n"
        + "### 场景图\n"
        + "\n".join(f"{idx + 1}. {line}" for idx, line in enumerate(scene_prompt_lines))
        + "\n\n## 参考资料\n"
        + refs_block
        + "\n"
    )


def render_fallback_article_content(project: dict[str, Any], template: dict[str, Any], brief: str, refs: list[dict[str, Any]]) -> str:
    topic = clean_text(project["topic_name"])
    title = fallback_cover_title(topic)
    subtitle = fallback_cover_subtitle(topic)
    publish_title = f"{topic}，这件事为什么总被大家讲偏？"
    points = [
        f"先把「{topic}」的核心问题点明，让读者知道这篇文章到底要解决什么。",
        f"拆掉围绕「{topic}」最常见的一个误区，制造继续往下读的动力。",
        f"解释「{topic}」真正的关键机制，让抽象概念落成看得见的因果链。",
        f"拿一个现实案例说明「{topic}」为什么值得今天的人重新理解。",
    ]
    image_prompts = [
        f"16:9 横屏，第 {idx + 1} 张正文配图，围绕「{topic}」表现：{line}。可加入 1-3 个清晰短标签或栏目角标，不生成长段正文。"
        for idx, line in enumerate(points, start=1)
    ]
    refs_block = "\n".join(f"- [{item['title']}]({item['url']}) - {item['snippet']}" for item in refs) or "- 无"
    return (
        f"# {title}\n\n"
        f"## Meta\n"
        f"- 封面副标题: {subtitle}\n"
        f"- 核心观点: {topic}真正值得看的，是那条容易被忽略的逻辑链\n"
        f"- 推荐发布标题: {publish_title}\n"
        f"- 钩子: 你有没有发现，很多人聊「{topic}」时，真正重要的那一步反而最少被提到？\n"
        f"- 互动钩子: 你平时最容易在哪一步被带偏，评论区聊聊。\n"
        f"- 免责声明:\n\n"
        f"## 正文\n\n"
        f"很多人一提到「{topic}」，往往会直接跳到结论。但真正决定读者能不能看进去的，不是结论，而是你有没有把那条最关键的逻辑链讲清楚。\n\n"
        f"### 先把问题点明\n\n"
        f"{points[0]}\n\n"
        f"[配图1]\n\n"
        f"### 为什么总会讲偏\n\n"
        f"{points[1]}\n\n"
        f"- 表面信息通常最容易传播\n"
        f"- 真正关键的转折往往被省掉\n"
        f"- 一旦省掉因果，内容就会变成概念堆砌\n\n"
        f"[配图2]\n\n"
        f"### 真正该看的关键点\n\n"
        f"{points[2]}\n\n"
        f"[配图3]\n\n"
        f"### 回到现实场景\n\n"
        f"{points[3]}\n\n"
        f"[配图4]\n\n"
        f"### 写在最后\n\n"
        f"所以这篇内容真正想留下来的，不是一个孤立答案，而是你下次再碰到「{topic}」时，知道先看哪里。你平时最容易在哪一步被带偏，评论区聊聊。\n\n"
        f"## 图片提示词\n\n"
        f"### 横屏封面图（头图，16:9 横屏）\n"
        f"16:9 横屏头图，商业杂志头图风，主视觉围绕「{topic}」，主标题「{title}」和副标题「{subtitle}」清晰可读，文字短而醒目，保留后期叠字安全区。\n\n"
        f"### 场景图（正文配图，全部 16:9 横屏，按正文配图数 4-8 张）\n"
        + "\n".join(f"{idx + 1}. {prompt}" for idx, prompt in enumerate(image_prompts))
        + "\n\n## 参考资料\n"
        + refs_block
        + "\n"
    )


def build_fallback_dialogue_lines(topic: str, speaker_mode: str) -> list[str]:
    if speaker_mode == "dual":
        return [
            f"【女】先别急着给「{topic}」下定义，很多人一开口就讲偏了，最关键那一步反而没人提。",
            f"【男】对，这种题最容易写成解释文，但观众真正想听的，是它到底卡在哪儿，为什么会一步步变成现在这样。",
            f"【女】也就是说，咱们今天别上来背概念，先说那个最容易让人误判的瞬间，行吗？",
            f"【男】行。很多时候表面现象看着已经很明显了，可真正决定结果的，往往是后面那个被忽略的小动作。",
            f"【女】这就有意思了，表面看是一个问题，真正关键其实藏在另一层？",
            f"【男】没错。所以中间一定得拆两步：第一步讲大家原来怎么想，第二步讲为什么这种想法会把人带偏。",
            f"【女】那别空讲，你举个具体点的例子，不然观众听到这儿还是会觉得抽象。",
            f"【男】最有效的讲法，就是把它放进一个真实场景里。你一看到人物、动作、结果，马上就知道问题到底出在哪儿。",
            f"【女】所以这期真正要记住的，不是一个大词，而是那个“原来我一直忽略这里”的瞬间。",
            f"【男】对。下次你再碰到「{topic}」，先别急着顺着表面往下想，先找那个真正决定结果的点。",
            f"【女】你平时最容易在哪一步想当然？",
            f"【男】把你第一反应留在评论区，我们就知道下一期该先拆哪种误区了。",
        ]
    return [
        f"【主播】先别急着聊结论，「{topic}」这种题最容易把人带偏的，往往不是答案，而是开头第一步。",
        f"【主播】很多稿子一上来就在解释名词，可短视频观众不等这个，他们更想知道：这事到底为什么会卡住我？",
        f"【主播】所以咱们今天不绕，先抓那个最容易误判的瞬间。你一旦看懂这一步，后面很多问题都顺了。",
        f"【主播】表面看，大家以为问题就在眼前；但真正关键，通常藏在后面那个不起眼的动作里。",
        f"【主播】这也是为什么同一个题，有人越听越明白，有人却越听越空，因为前者在讲过程，后者只在讲结论。",
        f"【主播】那过程怎么讲才不空？最简单，就是把它塞进一个真实场景里：谁在做、怎么做、结果怎样，一下就清楚了。",
        f"【主播】你会发现，很多旧理解不是完全错，而是只讲了半截。真正把人留住的，是后面那半截反转。",
        f"【主播】所以这期别只记一个词，记住那个决定结果的小细节。下次再碰到「{topic}」，先看那里。",
        f"【主播】你自己最容易在哪一步想当然？评论区留一句，我按这个顺序继续拆。",
    ]


def render_fallback_story_content_v2(
    project: dict[str, Any],
    template: dict[str, Any],
    brief: str,
    refs: list[dict[str, Any]],
    speaker_mode: str,
) -> str:
    topic = clean_text(project["topic_name"])
    cover_title = fallback_cover_title(topic)
    publish_title = fallback_publish_title(topic)
    cover_subtitle = fallback_cover_subtitle(topic)
    scene_lines = generic_scene_lines(topic, "video")
    duration = "5-6分钟" if len(clean_text(brief)) > 160 else "3-4分钟"
    dialogue = build_fallback_dialogue_lines(topic, speaker_mode)
    reference_summary = "；".join(item.get("title") or "" for item in refs[:3] if isinstance(item, dict) and clean_text(item.get("title") or "")) or f"{topic} 的公开资料"
    highlight_lines = [
        f"别急着聊「{topic}」的结论，最关键的是第一步。",
        "表面看是一个问题，真正关键往往藏在另一层。",
        "别只背概念，要把它放进真实场景里看。",
        "下次再碰到类似情况，先找那个决定结果的小细节。",
    ]
    scene_prompt_lines = [
        f"16:9 横屏，第 {idx + 1} 张场景图，围绕「{topic}」展开，画面重点是：{line}。保留字幕空间，可加入 1-3 个清晰短标签，不要长段正文。"
        for idx, line in enumerate(scene_lines)
    ]
    refs_block = "\n".join(
        f"- [{item.get('title') or '参考资料'}]({item.get('url') or ''}) - {item.get('snippet') or ''}"
        for item in refs
        if isinstance(item, dict)
    ) or "- 暂无参考资料"
    hook = dialogue[0].replace("【女】", "").replace("【男】", "").replace("【主播】", "").strip()
    interaction_hook = "你自己最容易在哪一步想当然？评论区留一句。"
    return (
        f"# {cover_title}\n\n"
        f"## Meta\n"
        f"- 封面副标题: {cover_subtitle}\n"
        f"- 核心观点: 真正能把「{topic}」讲明白的，不是表面结论，而是那条因果链。\n"
        f"- 时长: {duration}\n"
        f"- 推荐发布标题: {publish_title}\n"
        f"- 钩子: {hook}\n"
        f"- 互动钩子: {interaction_hook}\n"
        f"- 免责声明:\n\n"
        f"## 原始材料简述\n"
        f"- 主体: {topic}\n"
        f"- 核心知识点: 不是只讲是什么，而是讲清为什么、怎么一步步发生。\n"
        f"- 反常识点: 大家以为问题在表面，真正关键却在更后面的细节。\n"
        f"- 本期差异化抓手: {reference_summary}\n"
        f"- 联系现实的角度: 下次再碰到类似情况，观众知道先看哪一步。\n\n"
        f"## 对话脚本\n\n"
        + "\n\n".join(dialogue)
        + "\n\n## 重点字幕\n"
        + "\n".join(f"{idx + 1}. {line}" for idx, line in enumerate(highlight_lines))
        + "\n\n## 图片提示词\n"
        + "### 横屏封面图 (4:3)\n"
        + f"围绕「{topic}」制作 4:3 横屏封面，主标题「{cover_title}」清晰可读，副标题「{cover_subtitle}」可小字出现，保留频道角标位置，整体抓眼但不堆字。\n\n"
        + "### 竖屏封面图 (3:4)\n"
        + f"围绕「{topic}」制作 3:4 竖屏封面，主标题「{cover_title}」清晰可读，副标题「{cover_subtitle}」可小字出现，画面留出后期标题区。\n\n"
        + "### 场景图\n"
        + "\n".join(f"{idx + 1}. {line}" for idx, line in enumerate(scene_prompt_lines))
        + "\n\n## 参考资料\n"
        + refs_block
        + "\n"
    )


def render_fallback_article_content_v2(
    project: dict[str, Any],
    template: dict[str, Any],
    brief: str,
    refs: list[dict[str, Any]],
) -> str:
    topic = clean_text(project["topic_name"])
    title = fallback_cover_title(topic)
    subtitle = fallback_cover_subtitle(topic)
    publish_title = f"{topic}，很多人从第一步就看偏了"
    points = [
        f"先把「{topic}」最容易让人误判的那个瞬间点出来，让读者一上来就知道这篇内容为什么值得继续看。",
        f"拆掉围绕「{topic}」最常见的一层旧理解，把“你以为”和“其实”拉开。",
        f"用具体场景把真正的机制讲出来，不讲空概念，只讲看得见的动作和结果。",
        f"最后把它拉回现实，让读者知道下次遇到类似情况该先看哪里。",
    ]
    image_prompts = [
        f"16:9 横屏，第 {idx + 1} 张正文配图，围绕「{topic}」表现：{line}。可加入 1-3 个清晰短标签，不生成长段正文。"
        for idx, line in enumerate(points, start=1)
    ]
    refs_block = "\n".join(
        f"- [{item.get('title') or '参考资料'}]({item.get('url') or ''}) - {item.get('snippet') or ''}"
        for item in refs
        if isinstance(item, dict)
    ) or "- 暂无参考资料"
    return (
        f"# {title}\n\n"
        f"## Meta\n"
        f"- 封面副标题: {subtitle}\n"
        f"- 核心观点: 真正值得讲的不是表面定义，而是观众最容易漏掉的那个关键动作。\n"
        f"- 推荐发布标题: {publish_title}\n"
        f"- 钩子: 很多人聊「{topic}」时，最重要的那一步反而最少被提到。\n"
        f"- 互动钩子: 你最容易在哪一步看偏，评论区聊聊。\n"
        f"- 免责声明:\n\n"
        f"## 正文\n\n"
        f"很多内容一提到「{topic}」，上来就忙着解释是什么。可真正决定读者会不会继续往下看的，往往不是定义，而是你有没有先指出那个最容易误判的瞬间。\n\n"
        f"### 先说最容易讲偏的地方\n\n"
        f"{points[0]}\n\n"
        f"[配图1]\n\n"
        f"### 为什么大家总会在这里看偏\n\n"
        f"{points[1]}\n\n"
        f"[配图2]\n\n"
        f"### 真正要看的是哪一步\n\n"
        f"{points[2]}\n\n"
        f"[配图3]\n\n"
        f"### 回到今天，怎么用上这件事\n\n"
        f"{points[3]}\n\n"
        f"[配图4]\n\n"
        f"### 写在最后\n\n"
        f"所以这篇内容真正想留下来的，不是一个孤零零的结论，而是你下次再碰到「{topic}」时，知道先看哪里。你自己最容易在哪一步想当然？评论区聊聊。\n\n"
        f"## 图片提示词\n"
        f"### 横屏封面图（头图，16:9 横屏）\n"
        f"16:9 横屏头图，围绕「{topic}」，主标题「{title}」和副标题「{subtitle}」清晰可读，首屏抓人，保留后期文字安全区。\n"
        f"### 场景图（正文配图，全部 16:9 横屏）\n"
        + "\n".join(f"{idx + 1}. {prompt}" for idx, prompt in enumerate(image_prompts))
        + "\n\n## 参考资料\n"
        + refs_block
        + "\n"
    )


def render_fallback_content(
    project: dict[str, Any],
    template: dict[str, Any],
    brief: str,
    tavily_topic: str,
    context: dict[str, Any],
) -> str:
    refs = context.get("references", [])
    mode = template.get("mode", "video")
    voice_mode = template.get("voice_mode", "")
    if mode == "article":
        return render_fallback_article_content_v2(project, template, brief, refs)
    if voice_mode == "single":
        return render_fallback_story_content_v2(project, template, brief, refs, speaker_mode="single")
    return render_fallback_story_content_v2(project, template, brief, refs, speaker_mode="dual")


def render_deepseek_content(
    project: dict[str, Any],
    template: dict[str, Any],
    brief: str,
    tavily_topic: str,
    context: dict[str, Any],
) -> str:
    env = runtime_env()
    api_key = clean_text(env.get("DEEPSEEK_API_KEY", ""))
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    if not api_key:
        return render_fallback_content(project, template, brief, tavily_topic, context)
    if OpenAI is None:
        raise ContentGenerationError("当前环境缺少 openai 依赖，无法调用 DeepSeek。")

    base_url = clean_text(env.get("DEEPSEEK_BASE_URL", "")) or "https://api.deepseek.com"
    model = clean_text(env.get("DEEPSEEK_MODEL", "")) or "deepseek-v4-flash"
    thinking_type = clean_text(env.get("DEEPSEEK_THINKING_TYPE", "")) or "enabled"
    reasoning_effort = clean_text(env.get("DEEPSEEK_REASONING_EFFORT", "")) or "high"
    messages = compose_deepseek_messages(project, template, brief, tavily_topic, context)
    if messages:
        messages[0]["content"] = str(messages[0].get("content") or "").strip() + "\n\n" + build_common_content_system_rules() + "\n\n" + build_viral_content_rules(project, template)
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

    extra_body: dict[str, Any] = {"reasoning_effort": reasoning_effort}
    if thinking_type in {"enabled", "disabled"}:
        extra_body["thinking"] = {"type": thinking_type}

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=12000,
            extra_body=extra_body,
        )
    except APIConnectionError as exc:
        raise ContentGenerationError(f"连接 DeepSeek 失败，请检查网络或代理后重试：{exc}") from exc
    except APIStatusError as exc:
        status_code = getattr(exc, "status_code", None)
        if status_code == 402:
            raise ContentGenerationError(
                "DeepSeek 账户余额不足，当前无法生成脚本。请先前往 https://platform.deepseek.com/top_up 充值后再试。"
            ) from exc
        if status_code in {401, 403}:
            raise ContentGenerationError("DeepSeek API Key 无效或没有权限，请检查配置页里的密钥。") from exc
        if status_code == 429:
            raise ContentGenerationError("DeepSeek 请求过于频繁或额度已用尽，请稍后再试。") from exc
        raise ContentGenerationError(f"调用 DeepSeek 失败（HTTP {status_code or 'unknown'}）。") from exc
    except Exception as exc:
        raise ContentGenerationError(f"调用 DeepSeek 失败：{exc}") from exc

    choice = response.choices[0] if getattr(response, "choices", None) else None
    if not choice:
        raise ContentGenerationError("DeepSeek 没有返回可用结果。")
    if getattr(choice, "finish_reason", "") == "length":
        raise ContentGenerationError("DeepSeek 输出被截断了，请缩短 brief 或稍后改成更聚焦的话题再试。")

    raw_content = message_content_to_text(choice.message.content if getattr(choice, "message", None) else "")
    content = strip_code_fences(raw_content)
    content = re.sub(r"(?is)^<think>.*?</think>\s*", "", content).strip()
    if not content.startswith("#"):
        raise ContentGenerationError("DeepSeek 已响应，但返回内容不是完整的 content.md，请重试。")
    engagement = content_engagement_report(content, mode)
    if engagement.get("needs_rewrite"):
        try:
            rewrite_response = client.chat.completions.create(
                model=model,
                messages=compose_deepseek_rewrite_messages(project, template, content, engagement),
                temperature=0.65,
                max_tokens=12000,
                extra_body=extra_body,
            )
            rewrite_choice = rewrite_response.choices[0] if getattr(rewrite_response, "choices", None) else None
            rewritten = message_content_to_text(rewrite_choice.message.content if getattr(rewrite_choice, "message", None) else "")
            rewritten = strip_code_fences(rewritten)
            rewritten = re.sub(r"(?is)^<think>.*?</think>\s*", "", rewritten).strip()
            if rewritten.startswith("#"):
                content = rewritten
        except Exception:
            pass
    content = compact_content_meta(content)
    return content + ("\n" if not content.endswith("\n") else "")


def render_original_content(
    project: dict[str, Any],
    template: dict[str, Any],
    brief: str,
    tavily_topic: str,
) -> dict[str, Any]:
    env = runtime_env()
    if not clean_text(env.get("DEEPSEEK_API_KEY", "")):
        raise ContentGenerationError("原版脚本生成需要先配置 DeepSeek API Key。")

    template_key = clean_text(
        template.get("key")
        or template.get("name")
        or project.get("template")
        or ""
    )
    if not template_key:
        raise ContentGenerationError("当前项目缺少模板信息，无法调用原版脚本链路。")

    prompt_path = storage.TEMPLATES_ROOT / template_key / "prompt.md"
    result = run_original_bridge(
        "content",
        {
            "project_id": int(project["id"]),
            "topic_name": clean_text(project["topic_name"]),
            "brief": brief,
            "template_key": template_key,
            "tavily_topic": tavily_topic,
            "prompt_path": str(prompt_path) if prompt_path.exists() else "",
        },
        env,
        timeout=1800,
    )
    content = strip_code_fences(str(result.get("content") or "")).strip()
    if not content.startswith("#"):
        raise ContentGenerationError("原版脚本链路已返回，但 content.md 结构不完整。")

    references = result.get("references", [])
    if not isinstance(references, list):
        references = []
    normalized_references: list[dict[str, Any]] = []
    for item in references:
        if not isinstance(item, dict):
            continue
        title = clean_text(str(item.get("title") or ""))
        url = clean_text(str(item.get("url") or ""))
        snippet = clean_text(str(item.get("snippet") or ""))
        source = clean_text(str(item.get("source") or ""))
        if not (title or url or snippet):
            continue
        normalized_references.append(
            {
                "title": title or url or "Reference",
                "url": url,
                "snippet": snippet,
                "source": source,
            }
        )

    stages = result.get("stages", [])
    if not isinstance(stages, list):
        stages = []
    return {
        "content": content + ("\n" if not content.endswith("\n") else ""),
        "references": normalized_references,
        "stages": [clean_text(str(item)) for item in stages if clean_text(str(item))],
        "provider": "original",
    }


def scene_prompt(project_id: int, filename: str) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    prompt_cache_path = storage.project_file(project_id, "scenes/scene_prompts.json")
    content_path = storage.project_file(project_id, "content.md")
    prompt_cache_fresh = prompt_cache_path.exists() and (
        not content_path.exists() or prompt_cache_path.stat().st_mtime >= content_path.stat().st_mtime
    )
    if prompt_cache_fresh:
        scene_records = storage.read_json(prompt_cache_path, [])
        for record in scene_records:
            if record.get("filename") == filename:
                source_prompt = clean_text(str(record.get("source_prompt") or record.get("prompt") or record.get("label") or ""))
                prompt_source = composer_scene_prompt(source_prompt) or source_prompt
                prompt = optimize_visual_generation_prompt(prompt_source, template, "scene") if source_prompt else ""
                return {"filename": filename, "prompt": prompt}

    summary = storage.get_summary(project_id)
    content = storage.get_content(project_id)
    mode = project.get("template_mode", "video")
    prompts = parse_scene_prompts(content, mode) or generic_scene_lines(project["topic_name"], mode)
    scene_index_matches = re.findall(r"(\d+)", filename)
    scene_index = int(scene_index_matches[0]) if scene_index_matches else 1
    prompt_text = prompts[scene_index - 1] if 0 < scene_index <= len(prompts) else f"围绕「{summary.get('video_title') or project['topic_name']}」生成配图"
    prompt_text = composer_scene_prompt(prompt_text) or prompt_text
    prompt_text = optimize_visual_generation_prompt(prompt_text, template, "scene")
    return {"filename": filename, "prompt": prompt_text}


def _image_review_path(project_id: int) -> Path:
    return storage.project_file(project_id, "image_review.json")


def _scene_output_paths(project_id: int) -> list[Path]:
    return [storage.project_file(project_id, f"scenes/{item['filename']}") for item in storage.scene_status(project_id).get("existing", [])]


def _cover_output_paths(project_id: int) -> list[Path]:
    return [
        storage.project_file(project_id, "covers/cover_landscape.png"),
        storage.project_file(project_id, "covers/cover_story.png"),
        storage.project_file(project_id, "covers/cover_portrait.png"),
    ]


def _asset_fingerprint(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        stat = path.stat()
        records.append(
            {
                "path": path.as_posix(),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return records


def image_review_status(project_id: int) -> dict[str, Any]:
    raw = storage.read_json(_image_review_path(project_id), {})
    if not isinstance(raw, dict):
        raw = {}
    scene_status_payload = storage.scene_status(project_id)
    scene_ready = bool(
        scene_status_payload.get("complete")
        and int(scene_status_payload.get("expected_count", 0) or 0) > 0
        and int(scene_status_payload.get("generated_count", 0) or 0) >= int(scene_status_payload.get("expected_count", 0) or 0)
    )
    cover_paths = _cover_output_paths(project_id)
    cover_generated = sum(1 for path in cover_paths if path.exists())
    covers_ready = cover_generated == len(cover_paths)
    fingerprint = {
        "scenes": _asset_fingerprint(_scene_output_paths(project_id)),
        "covers": _asset_fingerprint(cover_paths),
    }
    required = bool(raw.get("required", True))
    stored_fingerprint = raw.get("fingerprint")
    confirmed = bool(raw.get("confirmed")) and stored_fingerprint == fingerprint
    ready_to_confirm = scene_ready and covers_ready
    return {
        "required": required,
        "confirmed": confirmed,
        "can_generate_video": (not required) or confirmed,
        "ready_to_confirm": ready_to_confirm,
        "scene_ready": scene_ready,
        "covers_ready": covers_ready,
        "scene_expected": scene_status_payload.get("expected_count", 0),
        "scene_generated": scene_status_payload.get("generated_count", 0),
        "cover_expected": len(cover_paths),
        "cover_generated": cover_generated,
        "updated_at": raw.get("updated_at"),
        "confirmed_at": raw.get("confirmed_at") if confirmed else None,
        "dirty_reason": "" if confirmed else str(raw.get("dirty_reason") or ""),
    }


def save_image_review_status(project_id: int, *, required: bool | None = None, confirmed: bool | None = None) -> dict[str, Any]:
    raw = storage.read_json(_image_review_path(project_id), {})
    if not isinstance(raw, dict):
        raw = {}
    current_required = bool(raw.get("required", True))
    if required is not None:
        raw["required"] = bool(required)
    elif "required" not in raw:
        raw["required"] = current_required

    if confirmed is not None:
        if confirmed:
            status = image_review_status(project_id)
            if not status.get("ready_to_confirm"):
                raise ValueError("场景图和封面图还没有全部生成，暂时不能确认。")
            raw["confirmed"] = True
            raw["confirmed_at"] = storage.now_ts()
            raw["dirty_reason"] = ""
            raw["fingerprint"] = {
                "scenes": _asset_fingerprint(_scene_output_paths(project_id)),
                "covers": _asset_fingerprint(_cover_output_paths(project_id)),
            }
        else:
            raw["confirmed"] = False
            raw["confirmed_at"] = None
            raw["fingerprint"] = None
            raw["dirty_reason"] = raw.get("dirty_reason") or "图片等待重新确认"

    raw["updated_at"] = storage.now_ts()
    storage.write_json(_image_review_path(project_id), raw)
    return image_review_status(project_id)


def mark_image_review_dirty(project_id: int, reason: str) -> dict[str, Any]:
    raw = storage.read_json(_image_review_path(project_id), {})
    if not isinstance(raw, dict):
        raw = {}
    raw["required"] = bool(raw.get("required", True))
    raw["confirmed"] = False
    raw["confirmed_at"] = None
    raw["fingerprint"] = None
    raw["dirty_reason"] = reason
    raw["updated_at"] = storage.now_ts()
    storage.write_json(_image_review_path(project_id), raw)
    return image_review_status(project_id)


def assert_images_confirmed_for_video(project_id: int) -> None:
    status = image_review_status(project_id)
    if status.get("can_generate_video"):
        return
    raise RuntimeError("当前项目开启了图片确认关卡。请先确认场景图和封面图，再开始成片合成。")


def sync_project_subtitle_files(project_id: int) -> dict[str, Any]:
    audio_srt = storage.project_file(project_id, "audio/subtitles.srt")
    root_srt = storage.project_file(project_id, "subtitles.srt")
    audio_txt = storage.project_file(project_id, "audio/subtitles.txt")
    root_txt = storage.project_file(project_id, "subtitles.txt")
    actions: list[str] = []

    def newer(left: Path, right: Path) -> Path:
        if not left.exists():
            return right
        if not right.exists():
            return left
        return left if left.stat().st_mtime >= right.stat().st_mtime else right

    if audio_srt.exists() or root_srt.exists():
        source = newer(audio_srt, root_srt)
        target = root_srt if source == audio_srt else audio_srt
        if source.exists() and (not target.exists() or source.stat().st_size != target.stat().st_size or source.stat().st_mtime > target.stat().st_mtime + 0.001):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            actions.append(f"{source.relative_to(storage.project_dir(project_id)).as_posix()} -> {target.relative_to(storage.project_dir(project_id)).as_posix()}")

    if audio_txt.exists() or root_txt.exists():
        source = newer(audio_txt, root_txt)
        target = root_txt if source == audio_txt else audio_txt
        if source.exists() and (not target.exists() or source.stat().st_size != target.stat().st_size or source.stat().st_mtime > target.stat().st_mtime + 0.001):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            actions.append(f"{source.relative_to(storage.project_dir(project_id)).as_posix()} -> {target.relative_to(storage.project_dir(project_id)).as_posix()}")

    return {
        "audio_srt_exists": audio_srt.exists(),
        "root_srt_exists": root_srt.exists(),
        "audio_srt_path": str(audio_srt),
        "root_srt_path": str(root_srt),
        "actions": actions,
    }


def video_preflight_report(project_id: int) -> dict[str, Any]:
    subtitle_sync = sync_project_subtitle_files(project_id)
    content_path = storage.project_file(project_id, "content.md")
    audio_path = storage.project_file(project_id, "audio/podcast.mp3")
    subtitle_path = storage.project_file(project_id, "audio/subtitles.srt")
    root_subtitle_path = storage.project_file(project_id, "subtitles.srt")
    timeline_path = storage.project_file(project_id, "audio/scene_timeline.json")
    scene_paths = find_scene_image_paths(project_id)
    scene_status_payload = storage.scene_status(project_id)
    review_status = image_review_status(project_id)
    cover_paths = _cover_output_paths(project_id)
    cover_generated = sum(1 for path in cover_paths if path.exists())
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    content_mtime = content_path.stat().st_mtime if content_path.exists() else 0.0

    def stale_after_content(path: Path, tolerance: float = 1.0) -> bool:
        return bool(content_mtime and path.exists() and path.stat().st_mtime + tolerance < content_mtime)

    scene_expected = int(scene_status_payload.get("expected_count", 0) or 0)
    scene_generated = int(scene_status_payload.get("generated_count", 0) or len(scene_paths))
    if not review_status.get("can_generate_video"):
        blockers.append(quality_issue("risk", "图片确认", "当前场景图/封面图还没有确认。", "先在生产页检查图片，满意后点击“确认当前图片”。"))
    if scene_expected <= 0:
        blockers.append(quality_issue("risk", "场景图", "没有识别到场景图计划。", "先完成字幕对齐或重建图片提示词。"))
    elif scene_generated < scene_expected:
        blockers.append(quality_issue("risk", "场景图", f"场景图缺失：已生成 {scene_generated}/{scene_expected}。", "使用“补缺失场景图”或单张生成缺失图片。"))
    if not scene_paths:
        blockers.append(quality_issue("risk", "场景图", "没有可用于合成的场景图片。", "先生成场景图。"))

    hard_audits: list[str] = []
    for path in scene_paths:
        audit = read_image_audit(path)
        if str(audit.get("severity") or "") == "hard":
            hard_audits.append(path.name)
    if hard_audits:
        blockers.append(quality_issue("risk", "图片自检", f"{', '.join(hard_audits[:5])} 自检硬失败。", "先重绘这些图片，避免黑屏或空画面进入成片。"))

    stale_scene_images = [path.name for path in scene_paths if stale_after_content(path, tolerance=1.0)]
    if stale_scene_images:
        blockers.append(
            quality_issue(
                "risk",
                "场景图版本",
                f"有 {len(stale_scene_images)}/{len(scene_paths)} 张场景图早于最新 content.md。",
                "文案改过后请重新生成场景图，避免画面仍对应旧稿。",
            )
        )

    if cover_generated < len(cover_paths):
        warnings.append(quality_issue("warn", "封面图", f"封面未完整生成：已生成 {cover_generated}/{len(cover_paths)}。", "建议补齐横屏、图文、竖屏封面后再发布。"))
    stale_cover_images = [path.name for path in cover_paths if stale_after_content(path, tolerance=1.0)]
    if stale_cover_images:
        warnings.append(
            quality_issue(
                "warn",
                "封面版本",
                f"有 {len(stale_cover_images)}/{len(cover_paths)} 张封面早于最新 content.md。",
                "建议重生封面，让封面钩子和最新版文案一致。",
            )
        )

    audio_duration = safe_probe_duration(audio_path)
    if not audio_path.exists():
        blockers.append(quality_issue("risk", "音频", "缺少 podcast.mp3。", "先生成配音。"))
    elif audio_duration <= 0:
        blockers.append(quality_issue("risk", "音频", "无法读取音频时长。", "重新生成配音或检查音频文件。"))
    elif stale_after_content(audio_path):
        blockers.append(quality_issue("risk", "音频版本", "podcast.mp3 早于最新 content.md。", "文案改过后请重新生成配音。"))

    subtitle_entries = load_srt_entries(subtitle_path) if subtitle_path.exists() else []
    subtitle_end = subtitle_end_duration(subtitle_path) or 0.0
    subtitle_coverage = 0.0
    if not subtitle_path.exists():
        blockers.append(quality_issue("risk", "字幕", "缺少 subtitles.srt。", "先完成字幕对齐。"))
    elif not subtitle_entries:
        blockers.append(quality_issue("risk", "字幕", "字幕文件为空或无法解析。", "重新生成字幕。"))
    elif stale_after_content(subtitle_path):
        blockers.append(quality_issue("risk", "字幕版本", "subtitles.srt 早于最新 content.md。", "文案改过后请重新生成字幕/ASR。"))
    elif audio_duration > 0:
        subtitle_coverage = subtitle_coverage_ratio(subtitle_entries, int(audio_duration * 1000))
        if subtitle_coverage < 0.95:
            blockers.append(quality_issue("risk", "字幕覆盖", f"字幕只覆盖音频约 {subtitle_coverage * 100:.0f}%。", "重新 ASR/字幕对齐，避免尾段没字幕。"))
        elif subtitle_coverage < 0.985:
            warnings.append(quality_issue("warn", "字幕覆盖", f"字幕覆盖音频约 {subtitle_coverage * 100:.0f}%。", "建议重新对齐字幕，让尾段更稳。"))
        if subtitle_end > audio_duration + 3:
            blockers.append(quality_issue("risk", "字幕时轴", "字幕结束时间明显超过音频。", "重新对齐字幕，避免字幕延迟或错位。"))

    timeline = storage.read_json(timeline_path, {}) if timeline_path.exists() else {}
    timeline_scenes = timeline.get("scenes") if isinstance(timeline, dict) else []
    timeline_count = len(timeline_scenes) if isinstance(timeline_scenes, list) else 0
    timeline_audio_ms = int(timeline.get("audio_duration_ms", 0) or 0) if isinstance(timeline, dict) else 0
    timeline_cover_ms = int(timeline.get("cover_duration_ms", 0) or 0) if isinstance(timeline, dict) else 0
    timeline_outro_ms = int(timeline.get("outro_duration_ms", 0) or 0) if isinstance(timeline, dict) else 0
    timeline_audio_sec = round(float(timeline_audio_ms) / 1000.0, 3) if timeline_audio_ms > 0 else 0.0
    timeline_body_sec = round(float(max(0, timeline_audio_ms - timeline_cover_ms - timeline_outro_ms)) / 1000.0, 3) if timeline_audio_ms > 0 else 0.0
    if not timeline_path.exists():
        blockers.append(quality_issue("risk", "场景时轴", "缺少 audio/scene_timeline.json。", "先运行字幕对齐，生成按语音时长切分的场景时间轴。"))
    elif timeline_count <= 0:
        blockers.append(quality_issue("risk", "场景时轴", "场景时间轴为空。", "重新运行字幕对齐。"))
    elif stale_after_content(timeline_path):
        blockers.append(quality_issue("risk", "场景时轴版本", "scene_timeline.json 早于最新 content.md。", "重新字幕对齐，让场景时轴跟最新版口播一致。"))
    elif scene_generated and timeline_count != scene_generated:
        blockers.append(quality_issue("risk", "场景时轴", f"时轴 {timeline_count} 段，场景图 {scene_generated} 张。", "使用“补缺失场景图”或重新字幕对齐，让段数一致。"))
    if audio_duration > 0 and timeline_audio_sec > 0:
        closest_delta = min(abs(timeline_audio_sec - audio_duration), abs(timeline_body_sec - audio_duration) if timeline_body_sec > 0 else 9999)
        if closest_delta > 3:
            warnings.append(
                quality_issue(
                    "warn",
                    "时长基准",
                    f"时间轴语音 {timeline_body_sec or timeline_audio_sec:.1f}s，实际音频 {audio_duration:.1f}s。",
                    "建议重新字幕对齐，确保视频长度跟音频一致。",
                )
            )

    rhythm = script_rhythm_report(project_id)
    rhythm_score = int(rhythm.get("score", 0) or 0)
    rhythm_metrics = rhythm.get("metrics", {}) if isinstance(rhythm.get("metrics"), dict) else {}
    if rhythm_score < 72:
        blockers.append(quality_issue("risk", "文案节奏", f"节奏体检只有 {rhythm_score} 分。", "先用“节奏增强”或手动优化长句和中段转折。"))
    elif rhythm_score < 84:
        warnings.append(quality_issue("warn", "文案节奏", f"节奏体检 {rhythm_score} 分。", "建议先优化中段追问、转折和长句，再合成成片。"))

    return {
        "passed": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "metrics": {
            "audio_exists": audio_path.exists(),
            "audio_duration_sec": audio_duration,
            "audio_fresh": not stale_after_content(audio_path) if audio_path.exists() else False,
            "subtitle_exists": subtitle_path.exists(),
            "root_subtitle_exists": root_subtitle_path.exists(),
            "subtitle_fresh": not stale_after_content(subtitle_path) if subtitle_path.exists() else False,
            "subtitle_count": len(subtitle_entries),
            "subtitle_end_sec": round(subtitle_end, 3),
            "subtitle_coverage": round(subtitle_coverage, 4),
            "subtitle_sync": subtitle_sync,
            "timeline_exists": timeline_path.exists(),
            "timeline_fresh": not stale_after_content(timeline_path) if timeline_path.exists() else False,
            "timeline_scene_count": timeline_count,
            "timeline_audio_sec": timeline_audio_sec,
            "timeline_body_sec": timeline_body_sec,
            "scene_expected": scene_expected,
            "scene_generated": scene_generated,
            "scene_stale_count": len(stale_scene_images),
            "cover_expected": len(cover_paths),
            "cover_generated": cover_generated,
            "cover_stale_count": len(stale_cover_images),
            "images_confirmed": bool(review_status.get("can_generate_video")),
            "rhythm_score": rhythm_score,
            "rhythm_max_plain_gap": rhythm_metrics.get("max_plain_gap"),
            "rhythm_long_line_count": rhythm_metrics.get("long_line_count"),
        },
        "next_actions": [
            item.get("fix") or item.get("issue")
            for item in [*blockers, *warnings]
            if item.get("fix") or item.get("issue")
        ][:8],
    }


def repair_scene_timeline(project_id: int) -> dict[str, Any]:
    before = video_preflight_report(project_id)
    project = storage.get_project(project_id)
    content = storage.get_content(project_id)
    mode = project.get("template_mode", "video")
    topic_name = clean_text(project.get("topic_name") or "")
    audio_path = storage.project_file(project_id, "audio/podcast.mp3")
    subtitle_path = storage.project_file(project_id, "audio/subtitles.srt")
    timeline_path = storage.project_file(project_id, "audio/scene_timeline.json")
    plan_path = storage.project_file(project_id, "audio/scene_plan.json")
    if not audio_path.exists():
        raise RuntimeError("缺少 audio/podcast.mp3，无法按语音重建场景时轴。")
    if not subtitle_path.exists():
        raise RuntimeError("缺少 audio/subtitles.srt，无法按字幕重建场景时轴。")
    utterances = load_srt_entries(subtitle_path)
    if not utterances:
        raise RuntimeError("subtitles.srt 为空或无法解析，无法重建场景时轴。")

    scene_paths = find_scene_image_paths(project_id)
    scene_status_payload = storage.scene_status(project_id)
    summary = storage.get_summary(project_id)
    prompt_records = storage.read_json(storage.project_file(project_id, "scenes/scene_prompts.json"), [])
    prompt_count = len(prompt_records) if isinstance(prompt_records, list) else 0
    desired_count = max(
        len(scene_paths),
        prompt_count,
        int(scene_status_payload.get("generated_count", 0) or 0),
        int(scene_status_payload.get("expected_count", 0) or 0),
        int(summary.get("scene_count_script", 0) or 0),
        int(summary.get("scene_count", 0) or 0),
        1,
    )

    prompts_by_index: dict[int, str] = {}
    if isinstance(prompt_records, list):
        for record in prompt_records:
            if not isinstance(record, dict):
                continue
            raw_index = record.get("index")
            if raw_index is None:
                filename = clean_text(str(record.get("filename") or ""))
                match = re.search(r"(\d+)", filename)
                raw_index = match.group(1) if match else 0
            try:
                index = int(raw_index or 0)
            except Exception:
                index = 0
            prompt = clean_text(str(record.get("source_prompt") or record.get("prompt") or ""))
            if index > 0 and prompt:
                prompts_by_index[index] = prompt

    scene_lines = [
        prompts_by_index[index]
        for index in range(1, desired_count + 1)
        if prompts_by_index.get(index)
    ]
    if len(scene_lines) < desired_count:
        for prompt in current_scene_prompts(project_id, content, mode, topic_name, prefer_timeline=False):
            if clean_text(prompt) and clean_text(prompt) not in scene_lines:
                scene_lines.append(prompt)
            if len(scene_lines) >= desired_count:
                break
    scene_lines = normalize_scene_prompt_count(scene_lines, desired_count, topic_name, mode)

    audio_duration = safe_probe_duration(audio_path)
    if audio_duration <= 0:
        audio_duration = subtitle_end_duration(subtitle_path)
    audio_duration_ms = max(1000, round(audio_duration * 1000))
    timeline = build_scene_timeline_for_scene_count(utterances, scene_lines, desired_count, audio_duration_ms)
    storage.write_json(timeline_path, timeline)
    aligned_lines = [
        clean_text(str(item.get("prompt", "")))
        for item in timeline.get("scenes", [])
        if isinstance(item, dict) and clean_text(str(item.get("prompt", "")))
    ]
    scene_plan = write_scene_plan(project_id, project, content, timeline, aligned_lines or scene_lines)

    summary["scene_count_script"] = int(summary.get("scene_count_script", desired_count) or desired_count)
    summary["scene_count"] = len(aligned_lines) or desired_count
    summary["scene_count_aligned"] = len(aligned_lines) or desired_count
    storage.save_summary(project_id, summary)

    after = video_preflight_report(project_id)
    return {
        "ok": True,
        "before": before,
        "after": after,
        "scene_count": len(timeline.get("scenes", [])),
        "timeline_path": str(timeline_path),
        "scene_plan_path": str(plan_path),
        "scene_plan": scene_plan,
    }


def assert_video_preflight(project_id: int) -> None:
    report = video_preflight_report(project_id)
    if report.get("passed"):
        return
    messages = [
        f"{item.get('where', '检查')}: {item.get('issue', '')}"
        for item in report.get("blockers", [])
        if isinstance(item, dict)
    ]
    raise RuntimeError("成片前总检未通过：" + "；".join(messages[:5]))


def quality_issue(level: str, where: str, issue: str, fix: str = "") -> dict[str, str]:
    return {"level": level, "where": where, "issue": issue, "fix": fix}


def quality_score_from_issues(issues: list[dict[str, Any]], base: int = 100) -> int:
    score = base
    for item in issues:
        level = str(item.get("level") or "")
        if level == "risk":
            score -= 22
        elif level == "warn":
            score -= 10
        elif level == "info":
            score -= 3
    return max(0, min(100, score))


def quality_verdict(score: int) -> str:
    if score >= 88:
        return "质量稳定，可以进入下一步。"
    if score >= 72:
        return "可以继续，但建议先修掉报告里的警告项。"
    return "建议先返工，当前质量风险会明显影响成片效果。"


def safe_probe_duration(path: Path) -> float:
    if not path.exists():
        return 0.0
    try:
        return round(float(probe_media_duration(path)), 3)
    except Exception:
        return 0.0


def prompt_similarity_score(prompts: list[str]) -> float:
    token_sets = [set(extract_tokens(prompt)) for prompt in prompts if clean_text(prompt)]
    token_sets = [tokens for tokens in token_sets if tokens]
    if len(token_sets) < 2:
        return 0.0
    scores: list[float] = []
    for left_index, left in enumerate(token_sets):
        for right in token_sets[left_index + 1 :]:
            scores.append(len(left & right) / max(1, len(left | right)))
    return round(max(scores, default=0.0), 3)


def image_average_hash(path: Path, size: int = 8) -> str:
    if Image is None:
        return ""
    try:
        with Image.open(path) as image:
            gray = image.convert("L").resize((size, size))
            pixels = list(gray.getdata())
    except Exception:
        return ""
    average = sum(pixels) / max(1, len(pixels))
    return "".join("1" if value >= average else "0" for value in pixels)


def hash_similarity(left: str, right: str) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    same = sum(1 for a, b in zip(left, right) if a == b)
    return round(same / len(left), 3)


IMAGE_APPEAL_SUBJECT_TERMS = ("人物", "老人", "孩子", "妈妈", "爸爸", "用户", "主角", "主体", "人脸", "表情", "手部", "手机", "产品")
IMAGE_APPEAL_ACTION_TERMS = ("动作", "拿起", "递给", "挂断", "对视", "打开", "指向", "停住", "冲进", "靠近", "正在", "瞬间")
IMAGE_APPEAL_CONFLICT_TERMS = ("冲突", "反差", "误区", "骗局", "警惕", "别急", "小心", "真相", "结果", "风险", "痛点", "质疑", "悬念")
IMAGE_APPEAL_SCENE_TERMS = ("客厅", "饭桌", "街头", "办公室", "门口", "社区", "柜台", "评论区", "聊天", "屏幕", "现场", "空间")
IMAGE_APPEAL_TEXT_TERMS = ("短标签", "警示词", "标题区", "字幕空间", "留白", "角标", "封面", "可读")


def clamp_number(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def image_prompt_context_map(project_id: int, content: str = "", mode: str = "video") -> dict[str, str]:
    root = storage.project_dir(project_id)
    prompts: dict[str, str] = {}
    prompt_cache_path = storage.project_file(project_id, "scenes/scene_prompts.json")
    content_path = storage.project_file(project_id, "content.md")
    prompt_cache_fresh = prompt_cache_path.exists() and (
        not content_path.exists() or prompt_cache_path.stat().st_mtime >= content_path.stat().st_mtime
    )
    scene_records = storage.read_json(prompt_cache_path, []) if prompt_cache_fresh else []
    if not isinstance(scene_records, list):
        scene_records = []
    scene_prompts = [
        clean_text(str(record.get("source_prompt") or record.get("prompt") or ""))
        for record in scene_records
        if isinstance(record, dict)
    ]
    if not scene_prompts and content:
        scene_prompts = parse_scene_prompts(content, mode)
    for index, prompt in enumerate(scene_prompts, start=1):
        prompts[f"scenes/s_{index:02d}.png"] = prompt

    for path in _cover_output_paths(project_id):
        md_path = path.with_suffix(".md")
        if md_path.exists():
            with contextlib.suppress(Exception):
                prompts[str(path.relative_to(root)).replace("\\", "/")] = clean_text(storage.read_text(md_path))
    return prompts


def score_term_presence(text: str, terms: tuple[str, ...], weight: float) -> float:
    if not text:
        return 0.0
    hits = sum(1 for term in terms if term and term in text)
    return min(weight, hits * (weight / 2.0))


def image_appeal_score(item: dict[str, Any], prompt: str = "", *, is_cover: bool = False) -> dict[str, Any]:
    score = 45.0
    reasons: list[str] = []
    suggestions: list[str] = []

    if not item.get("ok"):
        return {
            "score": 0,
            "grade": "不可用",
            "reasons": ["图片不可用或无法读取。"],
            "suggestions": ["先重新生成这张图片。"],
        }

    mean_luma = float(item.get("mean_luma", 0) or 0)
    contrast = float(item.get("contrast", 0) or 0)
    edge_score = float(item.get("edge_score", 0) or 0)
    width = int(item.get("width", 0) or 0)
    height = int(item.get("height", 0) or 0)

    if 52 <= mean_luma <= 205:
        score += 10
    elif mean_luma < 32:
        score -= 18
        reasons.append("整体偏暗，首帧容易被划走。")
        suggestions.append("提高主体亮度，加入明确光源或更干净的前景。")
    elif mean_luma > 230:
        score -= 10
        reasons.append("整体过亮，层次和主体可能被冲淡。")
        suggestions.append("降低背景亮度，用阴影或色块把主体托出来。")

    if contrast >= 36:
        score += 15
    elif contrast >= 24:
        score += 8
    else:
        score -= 14
        reasons.append("对比度偏低，画面可能显得太素。")
        suggestions.append("增强明暗反差、前后景分离或加入醒目的色彩冲突。")

    if edge_score >= 8:
        score += 12
    elif edge_score >= 5:
        score += 6
    else:
        score -= 10
        reasons.append("细节密度偏低，主体抓眼度不足。")
        suggestions.append("换成近景人物、清晰物件动作或更具体的场景。")

    if width >= 1280 and height >= 720:
        score += 6
    else:
        score -= 8
        reasons.append("分辨率偏低，不适合做短视频主图。")
        suggestions.append("按 16:9 场景图或对应封面尺寸重绘。")

    prompt_score = 0.0
    prompt_score += score_term_presence(prompt, IMAGE_APPEAL_SUBJECT_TERMS, 8)
    prompt_score += score_term_presence(prompt, IMAGE_APPEAL_ACTION_TERMS, 7)
    prompt_score += score_term_presence(prompt, IMAGE_APPEAL_CONFLICT_TERMS, 10)
    prompt_score += score_term_presence(prompt, IMAGE_APPEAL_SCENE_TERMS, 6)
    prompt_score += score_term_presence(prompt, IMAGE_APPEAL_TEXT_TERMS, 4 if is_cover else 2)
    if prompt:
        score += prompt_score
    else:
        score -= 8
        reasons.append("没有找到对应提示词，无法确认画面是否绑定口播。")
        suggestions.append("重新生成提示词，让图片绑定频道、主题和本段口播。")

    if is_cover:
        title_terms = ("标题", "主标题", "副标题", "钩子", "封面", "角标", "频道", "作者", "短标签")
        if any(term in prompt for term in title_terms):
            score += 6
        else:
            score -= 8
            reasons.append("封面缺少点击理由或个人 IP 标识。")
            suggestions.append("封面提示词加入主标题、短标签、频道角标和一个强主体。")
    else:
        if any(term in prompt for term in ("口播", "阶段", "画面重点", "对应")):
            score += 5
        else:
            score -= 5
            reasons.append("场景图提示词与口播绑定不够明显。")
            suggestions.append("把本段最关键的一句口播改成画面动作或人物关系。")

    if not reasons and score < 78:
        reasons.append("画面基础指标可用，但还缺少更强的第一眼冲击。")
        suggestions.append("增加人物表情、动作冲突或具体物件，让画面一眼能读懂。")

    final_score = int(round(clamp_number(score, 0, 100)))
    if final_score >= 85:
        grade = "强"
    elif final_score >= 70:
        grade = "可用"
    elif final_score >= 55:
        grade = "偏弱"
    else:
        grade = "需重绘"
    return {
        "score": final_score,
        "grade": grade,
        "prompt_signal_score": round(prompt_score, 1),
        "reasons": reasons[:4],
        "suggestions": list(dict.fromkeys(suggestions))[:4],
    }


def image_asset_metrics(path: Path, project_id: int) -> dict[str, Any]:
    record: dict[str, Any] = {
        "file": str(path.relative_to(storage.project_dir(project_id))),
        "exists": path.exists(),
        "ok": False,
        "issues": [],
    }
    if not path.exists():
        record["issues"].append("文件不存在")
        return record
    try:
        stat = path.stat()
        record["size"] = stat.st_size
        if Image is None or ImageStat is None:
            record["ok"] = stat.st_size > 0
            record["issues"].append("当前环境缺少 Pillow，无法做图像视觉指标")
            return record
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            gray = rgb.convert("L")
            stat_luma = ImageStat.Stat(gray)
            mean_luma = round(float(stat_luma.mean[0]), 2)
            std_luma = round(float(stat_luma.stddev[0]), 2)
            extrema = gray.getextrema()
            width, height = rgb.size
            aspect = round(width / max(1, height), 4)
            edge_score = 0.0
            with contextlib.suppress(Exception):
                if ImageFilter is not None:
                    edges = gray.resize((240, max(1, round(240 * height / max(1, width))))).filter(ImageFilter.FIND_EDGES)
                    edge_score = round(float(ImageStat.Stat(edges).mean[0]), 2)
            record.update(
                {
                    "ok": True,
                    "width": width,
                    "height": height,
                    "aspect_ratio": aspect,
                    "mean_luma": mean_luma,
                    "contrast": std_luma,
                    "min_luma": int(extrema[0]),
                    "max_luma": int(extrema[1]),
                    "edge_score": edge_score,
                    "hash": image_average_hash(path),
                }
            )
            if mean_luma < 8:
                record["issues"].append("疑似黑图或极暗")
            elif mean_luma < 32:
                record["issues"].append("整体偏暗，短视频首帧吸引力可能不足")
            if std_luma < 18:
                record["issues"].append("画面对比度偏低，可能显得太素")
            if edge_score and edge_score < 4:
                record["issues"].append("边缘/细节偏少，主体可能不够抓眼")
    except Exception as exc:
        record["issues"].append(str(exc))
    return record


def visual_image_quality_report(project_id: int, content: str = "", mode: str = "video") -> dict[str, Any]:
    scene_paths = find_scene_image_paths(project_id)
    cover_paths = [path for path in _cover_output_paths(project_id) if path.exists()]
    assets = [image_asset_metrics(path, project_id) for path in [*scene_paths, *cover_paths]]
    prompt_map = image_prompt_context_map(project_id, content, mode)
    issues: list[dict[str, Any]] = []
    for item in assets:
        file = str(item.get("file") or "").replace("\\", "/")
        prompt = prompt_map.get(file, "")
        appeal = image_appeal_score(item, prompt, is_cover=file.startswith("covers/"))
        item["appeal"] = appeal
        if int(appeal.get("score", 0) or 0) < 60:
            fix = "；".join(str(text) for text in appeal.get("suggestions", [])[:2]) or "单张重绘，强化主体、动作和冲突。"
            issues.append(
                quality_issue(
                    "warn",
                    file,
                    f"图片吸引力偏弱：{appeal.get('score')} 分，{'; '.join(str(x) for x in appeal.get('reasons', [])[:2])}",
                    fix,
                )
            )
    for item in assets:
        file = str(item.get("file") or "")
        for issue in item.get("issues", [])[:3]:
            level = "risk" if "黑图" in str(issue) or "不存在" in str(issue) else "warn"
            issues.append(quality_issue(level, file, str(issue), "单张重绘或换一版更强主体的提示词。"))

    duplicate_pairs: list[dict[str, Any]] = []
    scene_assets = [item for item in assets if str(item.get("file", "")).startswith("scenes/") and item.get("hash")]
    for left_index, left in enumerate(scene_assets):
        for right in scene_assets[left_index + 1 :]:
            similarity = hash_similarity(str(left.get("hash", "")), str(right.get("hash", "")))
            if similarity >= 0.91:
                duplicate_pairs.append({"left": left.get("file"), "right": right.get("file"), "similarity": similarity})
    if duplicate_pairs:
        issues.append(
            quality_issue(
                "warn",
                "场景图重复",
                f"检测到 {len(duplicate_pairs)} 组视觉相似度较高的场景图。",
                "建议重绘相邻重复图，让每段口播对应不同动作、物件或镜头距离。",
            )
        )

    scene_lumas = [float(item.get("mean_luma", 0) or 0) for item in scene_assets if item.get("ok")]
    appeal_scores = [int(item.get("appeal", {}).get("score", 0) or 0) for item in assets if item.get("ok")]
    low_appeal_assets = [
        {
            "file": item.get("file"),
            "score": item.get("appeal", {}).get("score"),
            "grade": item.get("appeal", {}).get("grade"),
            "reasons": item.get("appeal", {}).get("reasons", []),
            "suggestions": item.get("appeal", {}).get("suggestions", []),
        }
        for item in assets
        if int(item.get("appeal", {}).get("score", 0) or 0) < 60
    ]
    if scene_lumas and max(scene_lumas) - min(scene_lumas) < 18:
        issues.append(quality_issue("info", "画面节奏", "场景图明暗变化较小，整条视频可能显得节奏单一。", "可让部分段落使用更强光影、近景或动作冲突。"))
    if appeal_scores and sum(appeal_scores) / len(appeal_scores) < 68:
        issues.append(quality_issue("warn", "图片吸引力", "本组图片平均吸引力偏弱，视频可能看起来平。", "优先重绘低分图片，把每张图改成强主体、明确动作、具体冲突。"))

    score = quality_score_from_issues(issues)
    return {
        "score": score,
        "verdict": quality_verdict(score),
        "assets": [
            {key: value for key, value in item.items() if key != "hash"}
            for item in assets
        ],
        "duplicate_pairs": duplicate_pairs[:20],
        "metrics": {
            "asset_count": len(assets),
            "scene_count": len(scene_paths),
            "cover_count": len(cover_paths),
            "duplicate_pair_count": len(duplicate_pairs),
            "avg_scene_luma": round(sum(scene_lumas) / len(scene_lumas), 2) if scene_lumas else 0,
            "avg_appeal_score": round(sum(appeal_scores) / len(appeal_scores), 1) if appeal_scores else 0,
            "low_appeal_count": len(low_appeal_assets),
        },
        "low_appeal_assets": low_appeal_assets[:12],
        "issues": issues,
    }


def content_quality_report(project: dict[str, Any], template: dict[str, Any], brief: str, content: str, references: list[dict[str, Any]]) -> dict[str, Any]:
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    audit = content_audit_report(project, template, brief, content, references)
    engagement = content_engagement_report(content, mode)
    issues: list[dict[str, Any]] = [dict(item) for item in audit.get("issues", []) if isinstance(item, dict)]
    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else summarize_content(content, mode)
    dialogue_lines = parse_dialogue_lines(content, mode)
    opening = clean_text(dialogue_lines[0] if dialogue_lines else content[:120])

    if engagement.get("opening_score", 0) < 3.5:
        issues.append(quality_issue("warn", "开头吸引力", "前三秒钩子偏弱，观众可能不知道为什么要继续看。", "第一句改成具体痛点、反常识问题或结果先行。"))
    if engagement.get("retention_score", 0) < 3.5:
        issues.append(quality_issue("warn", "中段留存", "中段推进偏平，缺少持续的信息差或转折。", "每 20-40 秒安排一个新问题、反转或具体案例。"))
    if engagement.get("interaction_score", 0) < 3.2:
        issues.append(quality_issue("info", "结尾互动", "结尾互动钩子不够明确。", "用一个低门槛问题引导评论，例如“你遇到过哪一种？”"))
    if opening and any(opening.startswith(token) for token in WEAK_OPENING_TOKENS):
        issues.append(quality_issue("warn", "开头句式", "开头仍有常见口播套话。", "删掉寒暄，直接从冲突、场景或问题开始。"))

    score = min(int(audit.get("score", 100) or 100), quality_score_from_issues(issues))
    return {
        "score": score,
        "verdict": quality_verdict(score),
        "rewrite_recommended": score < 72 or any(str(item.get("level")) == "risk" for item in issues),
        "summary": summary,
        "engagement": {
            "overall_score": engagement.get("overall_score"),
            "opening_score": engagement.get("opening_score"),
            "retention_score": engagement.get("retention_score"),
            "interaction_score": engagement.get("interaction_score"),
        },
        "metrics": audit.get("metrics", {}),
        "issues": issues,
    }


def image_director_report(project_id: int, project: dict[str, Any], template: dict[str, Any], content: str) -> dict[str, Any]:
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    scene_status_payload = storage.scene_status(project_id)
    prompt_cache_path = storage.project_file(project_id, "scenes/scene_prompts.json")
    content_path = storage.project_file(project_id, "content.md")
    prompt_cache_fresh = prompt_cache_path.exists() and (
        not content_path.exists() or prompt_cache_path.stat().st_mtime >= content_path.stat().st_mtime
    )
    scene_records = storage.read_json(prompt_cache_path, []) if prompt_cache_fresh else []
    if not isinstance(scene_records, list):
        scene_records = []
    scene_prompts = [
        clean_text(str(record.get("source_prompt") or record.get("prompt") or ""))
        for record in scene_records
        if isinstance(record, dict)
    ]
    if not scene_prompts:
        scene_prompts = parse_scene_prompts(content, mode)
    if len(scene_prompts) < 2:
        derived_prompts = current_scene_prompts(
            project_id,
            content,
            mode,
            str(project.get("topic_name") or ""),
            prefer_timeline=False,
        )
        if len(derived_prompts) > len(scene_prompts):
            scene_prompts = derived_prompts
    scene_paths = find_scene_image_paths(project_id)
    cover_paths = _cover_output_paths(project_id)
    cover_generated = sum(1 for path in cover_paths if path.exists())
    expected = int(scene_status_payload.get("expected_count", 0) or len(scene_prompts) or 0)
    generated = int(scene_status_payload.get("generated_count", 0) or len(scene_paths))
    issues: list[dict[str, Any]] = []

    if expected <= 0:
        issues.append(quality_issue("warn", "图片计划", "没有识别到场景图计划。", "先生成或修正 content.md 里的图片提示词。"))
    elif generated < expected:
        issues.append(quality_issue("risk", "场景图数量", f"场景图缺失：已生成 {generated}/{expected}。", "补齐缺失场景图后再合成视频。"))
    if cover_generated < len(cover_paths):
        issues.append(quality_issue("warn", "封面图", f"封面未完整生成：已生成 {cover_generated}/{len(cover_paths)}。", "补齐横屏、图文、竖屏封面，方便不同平台发布。"))

    similarity = prompt_similarity_score(scene_prompts)
    repeated_style_tokens = ["纸", "档案", "手账", "复古", "卡片", "便签", "拼贴"]
    repeated_style_hits = {
        token: sum(1 for prompt in scene_prompts if token in prompt)
        for token in repeated_style_tokens
    }
    repeated_style = [
        token for token, count in repeated_style_hits.items()
        if scene_prompts and count / max(1, len(scene_prompts)) >= 0.72 and count >= 3
    ]
    if similarity >= 0.78:
        issues.append(quality_issue("warn", "场景差异度", "多张场景图提示词过于相似，画面容易显得重复。", "让每张图绑定不同口播句、人物动作和场景关系。"))
    if repeated_style:
        issues.append(quality_issue("warn", "固定画风", f"提示词高频重复同一类画风：{', '.join(repeated_style[:4])}。", "把画风从频道统一感改为主题驱动，避免每期都像同一套纸面。"))

    anchor_bound = sum(1 for prompt in scene_prompts if any(token in prompt for token in ("口播", "画面重点", "这张图必须对应", "阶段")))
    if scene_prompts and anchor_bound / max(1, len(scene_prompts)) < 0.75:
        issues.append(quality_issue("warn", "口播绑定", "部分场景图没有明确绑定对应口播。", "按“频道 -> 主题 -> 当前口播句”重写每张图提示词。"))

    brand = clean_text(template.get("brand_name") or template.get("name") or template.get("key") or project.get("template") or "")
    cover_prompt_text = "\n".join(storage.read_text(path.with_suffix(".md")) for path in cover_paths if path.with_suffix(".md").exists())
    if brand and cover_prompt_text and brand not in cover_prompt_text:
        issues.append(quality_issue("info", "个人 IP", "封面提示词没有明显带频道名/作者名。", "封面固定加入频道名、作者名或专属角标，增强个人 IP 识别。"))

    audit_records: list[dict[str, Any]] = []
    for path in [*scene_paths, *[item for item in cover_paths if item.exists()]]:
        audit = read_image_audit(path)
        if audit:
            audit_records.append({"file": str(path.relative_to(storage.project_dir(project_id))), **audit})
            severity = str(audit.get("severity") or "")
            if severity == "hard":
                issues.append(quality_issue("risk", path.name, f"图片自检硬失败：{', '.join(str(x) for x in audit.get('reasons', []))}", "重绘这张图片。"))
            elif severity == "soft":
                issues.append(quality_issue("info", path.name, f"图片自检提示：{', '.join(str(x) for x in audit.get('reasons', []))}", "必要时重绘或换提示词。"))

    visual_report = visual_image_quality_report(project_id, content, mode)
    for issue in visual_report.get("issues", []):
        if isinstance(issue, dict):
            issues.append(dict(issue))
    layer_report = image_prompt_layer_report(project_id, content)
    for issue in layer_report.get("issues", []):
        if isinstance(issue, dict):
            issues.append(dict(issue))

    score = quality_score_from_issues(issues)
    return {
        "score": score,
        "verdict": quality_verdict(score),
        "metrics": {
            "scene_expected": expected,
            "scene_generated": generated,
            "cover_expected": len(cover_paths),
            "cover_generated": cover_generated,
            "scene_prompt_count": len(scene_prompts),
            "prompt_similarity_max": similarity,
            "anchor_bound_count": anchor_bound,
            "prompt_cache_fresh": prompt_cache_fresh,
            "visual_score": visual_report.get("score"),
            "visual_asset_count": visual_report.get("metrics", {}).get("asset_count"),
            "visual_duplicate_pair_count": visual_report.get("metrics", {}).get("duplicate_pair_count"),
            "avg_image_appeal_score": visual_report.get("metrics", {}).get("avg_appeal_score"),
            "low_image_appeal_count": visual_report.get("metrics", {}).get("low_appeal_count"),
            "image_prompt_layer_score": layer_report.get("metrics", {}).get("avg_layer_score"),
            "weak_image_prompt_count": layer_report.get("metrics", {}).get("weak_prompt_count"),
        },
        "issues": issues,
        "image_audits": audit_records[:20],
        "visual": visual_report,
        "prompt_layers": layer_report,
    }


def image_prompt_layer_entry(prompt: str, *, kind: str, topic: str, brand: str) -> dict[str, Any]:
    text = normalize_image_prompt(prompt)
    layer_checks = {
        "channel": bool(brand and brand in text) or any(token in text for token in ("频道", "系列感", "角标", "视觉基调", "专属色块")),
        "topic": bool(topic and any(part and part in text for part in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", topic)[:4])) or any(token in text for token in ("本期", "主题", "围绕")),
        "script_anchor": any(token in text for token in ("口播", "对应", "开头这句", "画面重点", "阶段")),
        "subject_action": any(token in text for token in IMAGE_APPEAL_SUBJECT_TERMS) and any(token in text for token in IMAGE_APPEAL_ACTION_TERMS),
        "emotion_conflict": any(token in text for token in IMAGE_APPEAL_CONFLICT_TERMS) or any(token in text for token in ("焦虑", "惊讶", "犹豫", "对比", "反差", "误判", "追问")),
        "text_rules": any(token in text for token in IMAGE_APPEAL_TEXT_TERMS) or any(token in text for token in ("中文", "可读", "标题", "字幕空间", "留白")),
        "safety": any(token in text for token in ("不要", "避免", "禁止", "不生成", "无水印", "免责声明", "脚注", "乱码")),
    }
    weights = {
        "channel": 12 if kind == "cover" else 8,
        "topic": 14,
        "script_anchor": 16 if kind == "scene" else 10,
        "subject_action": 18,
        "emotion_conflict": 14,
        "text_rules": 14,
        "safety": 12,
    }
    score = sum(weights[key] for key, ok in layer_checks.items() if ok)
    missing = [key for key, ok in layer_checks.items() if not ok]
    suggestions = []
    if "channel" in missing:
        suggestions.append("补频道气质/固定角标/个人 IP 识别，不要只写本期画面。")
    if "topic" in missing:
        suggestions.append("补本期主题关键词或核心观点，让画面不是通用素材图。")
    if "script_anchor" in missing:
        suggestions.append("补对应口播句或阶段，保证每张图绑定当前文案。")
    if "subject_action" in missing:
        suggestions.append("补一个明确主体和正在发生的动作。")
    if "emotion_conflict" in missing:
        suggestions.append("补痛点、反差、误区、表情或冲突关系，提高第一眼吸引力。")
    if "text_rules" in missing:
        suggestions.append("说明文字只允许短标题/短标签，并保留字幕空间。")
    if "safety" in missing:
        suggestions.append("补不要长段正文、脚注、免责声明、水印或乱码等禁止项。")
    return {
        "score": int(round(clamp_number(score, 0, 100))),
        "layers": layer_checks,
        "missing_layers": missing,
        "suggestions": suggestions[:4],
    }


def image_prompt_layer_report(project_id: int, content: str | None = None) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    content_text = content if content is not None else storage.get_content(project_id)
    topic = clean_text(str(project.get("topic_name") or first_heading(content_text) or ""))
    brand = clean_text(str(template.get("brand_name") or template.get("name") or template.get("key") or template_key))
    scene_prompts = parse_scene_prompts(content_text, mode)
    if not scene_prompts:
        scene_prompts = build_content_scene_prompt_lines(project, template, content_text)

    entries: list[dict[str, Any]] = []
    cover_prompts = [
        ("cover_landscape", "横屏封面", build_content_cover_prompt(project, template, content_text, "landscape")),
        ("cover_portrait", "竖屏封面", build_content_cover_prompt(project, template, content_text, "portrait")),
    ]
    if mode == "article":
        cover_prompts = [("cover_landscape", "横屏封面", build_content_cover_prompt(project, template, content_text, "landscape"))]
    for target, label, prompt in cover_prompts:
        layer = image_prompt_layer_entry(prompt, kind="cover", topic=topic, brand=brand)
        entries.append({"kind": "cover", "target": target, "label": label, "prompt": prompt, **layer})
    for index, prompt in enumerate(scene_prompts, start=1):
        layer = image_prompt_layer_entry(prompt, kind="scene", topic=topic, brand=brand)
        entries.append({"kind": "scene", "target": f"s_{index:02d}.png", "label": f"场景 {index}", "prompt": prompt, **layer})

    issues: list[dict[str, Any]] = []
    for item in entries:
        if int(item.get("score", 0) or 0) < 72:
            issues.append(
                quality_issue(
                    "warn",
                    str(item.get("label") or item.get("target") or ""),
                    f"图片提示词分层不足：{item.get('score')} 分，缺少 {', '.join(item.get('missing_layers', [])[:4])}。",
                    "；".join(str(text) for text in item.get("suggestions", [])[:2]) or "重建图片提示词。",
                )
            )
    repeated_style_tokens = ["纸", "档案", "手账", "复古", "卡片", "便签", "拼贴"]
    repeated = [
        token
        for token in repeated_style_tokens
        if scene_prompts and sum(1 for prompt in scene_prompts if token in prompt) / max(1, len(scene_prompts)) >= 0.72
    ]
    if repeated:
        issues.append(
            quality_issue(
                "warn",
                "画风同质化",
                f"场景图提示词过度重复同一类画风：{', '.join(repeated[:4])}。",
                "让频道只决定气质，主题和当前口播决定主体、动作、空间和冲突。",
            )
        )

    scores = [int(item.get("score", 0) or 0) for item in entries]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    return {
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "topic": topic,
        "score": int(round(avg_score)),
        "verdict": quality_verdict(int(round(avg_score))),
        "metrics": {
            "prompt_count": len(entries),
            "scene_prompt_count": len(scene_prompts),
            "avg_layer_score": avg_score,
            "weak_prompt_count": sum(1 for score in scores if score < 72),
            "repeated_style_tokens": repeated,
        },
        "entries": entries,
        "issues": issues,
        "next_actions": [item.get("fix") or item.get("issue") for item in issues[:6]],
    }


def rhythm_signal_for_line(line: str, index: int, total: int) -> str:
    text = clean_text(line)
    if index <= 2 and any(token in text for token in HOOK_SIGNAL_TOKENS):
        return "hook"
    if any(token in text for token in ("比如", "例如", "拿", "有一次", "举个例子", "真实")):
        return "case"
    if any(token in text for token in ("但是", "可", "其实", "结果", "反而", "偏偏", "真正", "表面")):
        return "turn"
    if any(token in text for token in RETENTION_SIGNAL_TOKENS) or "？" in text or "?" in text:
        return "push"
    if index >= total - 2 and any(token in text for token in INTERACTION_SIGNAL_TOKENS):
        return "interaction"
    return "explain"


def script_rhythm_report(project_id: int, content: str | None = None) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    content_text = content if content is not None else storage.get_content(project_id)
    lines = content_body_lines(content_text, mode)
    dialogue_lines = [strip_dialogue_speaker(line) for line in parse_dialogue_lines(content_text, mode)] or lines
    engagement = content_engagement_report(content_text, mode)
    issues: list[dict[str, Any]] = []

    if not lines:
        issues.append(quality_issue("risk", "节奏", "没有可分析的正文/口播内容。", "先生成或粘贴 content.md。"))

    signals = [rhythm_signal_for_line(line, idx, len(lines)) for idx, line in enumerate(lines)]
    push_indexes = [idx for idx, signal in enumerate(signals) if signal in {"hook", "case", "turn", "push", "interaction"}]
    max_plain_gap = 0
    previous = -1
    for idx in [*push_indexes, len(lines)]:
        max_plain_gap = max(max_plain_gap, idx - previous - 1)
        previous = idx
    long_lines = [line for line in dialogue_lines if len(clean_text(line)) > 46]
    ultra_short_lines = [line for line in dialogue_lines if 0 < len(clean_text(line)) < 8]
    scene_count = len(parse_scene_prompts(content_text, mode))
    audio_duration = safe_probe_duration(storage.project_file(project_id, "audio/podcast.mp3"))
    avg_scene_hold = round(audio_duration / scene_count, 2) if audio_duration > 0 and scene_count else 0

    if float(engagement.get("opening_score", 0) or 0) < 3.8:
        issues.append(quality_issue("warn", "前三秒", "开头钩子不足，第一屏缺少明确代价、反差或悬念。", "第一句改成结果先行/反常识/具体痛点，并控制在 10-24 字。"))
    if max_plain_gap >= 5:
        issues.append(quality_issue("warn", "中段推进", f"最长连续 {max_plain_gap} 句都缺少追问、转折、案例或反差。", "每 2-4 句插入一次追问、误区纠正、具体案例或“表面/真正”转折。"))
    if dialogue_lines and len(long_lines) / max(1, len(dialogue_lines)) > 0.28:
        issues.append(quality_issue("warn", "口播句长", f"长句偏多：{len(long_lines)}/{len(dialogue_lines)} 句超过 46 字。", "把长句拆成短句，给字幕和语音留停顿。"))
    if len(ultra_short_lines) >= max(4, len(dialogue_lines) // 4):
        issues.append(quality_issue("info", "口播碎片", "过短句偏多，可能显得碎。", "把连续短句合并成“短句 + 解释”结构。"))
    if float(engagement.get("interaction_score", 0) or 0) < 3.4:
        issues.append(quality_issue("warn", "结尾互动", "结尾没有形成低门槛互动。", "结尾问一个具体经历/站队/补充建议问题，不要只写“你怎么看”。"))
    if avg_scene_hold > 55:
        issues.append(quality_issue("warn", "画面停留", f"按当前音频估算，每张场景图平均停留 {avg_scene_hold:.0f} 秒，画面可能拖。", "补更多场景图或把时轴切得更细，每张图最好服务一个观点/转折。"))
    elif avg_scene_hold and avg_scene_hold < 8:
        issues.append(quality_issue("info", "画面停留", f"每张场景图平均停留 {avg_scene_hold:.0f} 秒，切换可能过快。", "确认字幕能读完，必要时合并相近镜头。"))

    score = quality_score_from_issues(issues)
    beats = [
        {
            "index": idx + 1,
            "signal": signal,
            "text": summarize_scene_text(line, 70),
            "chars": len(clean_text(line)),
        }
        for idx, (line, signal) in enumerate(zip(lines, signals))
    ]
    return {
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "topic": project.get("topic_name", ""),
        "score": score,
        "verdict": quality_verdict(score),
        "engagement": {
            "overall_score": engagement.get("overall_score"),
            "opening_score": engagement.get("opening_score"),
            "retention_score": engagement.get("retention_score"),
            "interaction_score": engagement.get("interaction_score"),
        },
        "metrics": {
            "line_count": len(lines),
            "dialogue_count": len(dialogue_lines),
            "push_signal_count": len(push_indexes),
            "max_plain_gap": max_plain_gap,
            "long_line_count": len(long_lines),
            "ultra_short_line_count": len(ultra_short_lines),
            "scene_prompt_count": scene_count,
            "audio_duration_sec": audio_duration,
            "avg_scene_hold_sec": avg_scene_hold,
        },
        "beats": beats[:80],
        "issues": issues,
        "next_actions": [item.get("fix") or item.get("issue") for item in issues[:6]],
    }


SCRIPT_SECTION_TITLES = ("对话脚本", "口播脚本", "视频脚本", "脚本")


def detect_script_section_title(content: str) -> str:
    for title in SCRIPT_SECTION_TITLES:
        if extract_section(content, title, level=2):
            return title
    return "口播脚本"


def split_spoken_text_for_rhythm(text: str, limit: int = 42) -> list[str]:
    cleaned = clean_text(text)
    if len(cleaned) <= limit:
        return [cleaned] if cleaned else []
    parts = [part for part in re.split(r"(?<=[。！？!?；;])\s*", cleaned) if clean_text(part)]
    if len(parts) <= 1:
        parts = [part for part in re.split(r"[，,]\s*", cleaned) if clean_text(part)]

    result: list[str] = []
    current = ""
    for part in parts:
        part = clean_text(part)
        if not part:
            continue
        candidate = f"{current}{part}" if not current else f"{current}{part}"
        if current and len(candidate) > limit:
            result.append(current)
            current = part
        else:
            current = candidate
    if current:
        result.append(current)

    normalized: list[str] = []
    for item in result:
        if len(item) <= limit + 8:
            normalized.append(item)
            continue
        chunk = item
        while len(chunk) > limit + 8:
            cut = max(chunk.rfind("，", 0, limit), chunk.rfind(",", 0, limit), chunk.rfind("、", 0, limit))
            if cut < 14:
                cut = limit
            normalized.append(chunk[:cut].strip("，,、 "))
            chunk = chunk[cut:].strip("，,、 ")
        if chunk:
            normalized.append(chunk)
    return [item for item in normalized if item]


def rhythm_bridge_line(topic: str, index: int) -> str:
    source = clean_text(topic)
    if any(token in source for token in ("自动续费", "扣费", "订阅", "免密", "支付")):
        variants = [
            "先别急，关键不是你点没点取消，而是钱到底从哪里扣。",
            "很多人以为关掉 App 就结束了，其实真正的开关在支付渠道里。",
            "记住这个判断：看见便宜试用，先找自动续费这一行。",
        ]
    else:
        variants = [
            "先别急，真正容易忽略的点在后面。",
            "很多人以为到这一步就结束了，其实关键还没出现。",
            "这里换个角度看，问题就清楚了。",
        ]
    return variants[index % len(variants)]


def interaction_line_for_topic(topic: str) -> str:
    source = clean_text(topic)
    if any(token in source for token in ("自动续费", "扣费", "订阅", "免密", "支付")):
        return "如果你也收到过扣费短信，评论区告诉我：你手机里关掉了几个自动扣费项目？"
    return "你也可以按这个方法试一次，评论区告诉我：你遇到的是哪一种情况？"


def format_rhythm_dialogue_line(speaker: str, text: str) -> str:
    clean_speaker = clean_text(speaker) or "主播"
    clean_spoken = clean_text(text)
    return f"【{clean_speaker}】{clean_spoken}" if clean_spoken else ""


def enhance_script_section_rhythm(script: str, topic: str, mode: str) -> tuple[str, dict[str, Any]]:
    if mode == "article":
        return script, {"changed": False, "split_count": 0, "bridge_count": 0, "interaction_added": False}
    output: list[str] = []
    split_count = 0
    bridge_count = 0
    plain_gap = 0
    bridge_index = 0
    last_speaker = "主播"

    def emit_spoken_segments(speaker_name: str, spoken_text: str, prefix_text: str = "") -> None:
        nonlocal split_count, bridge_count, plain_gap, bridge_index
        speaker = clean_text(speaker_name) or last_speaker
        spoken = clean_text(spoken_text)
        if not spoken:
            return
        segments = split_spoken_text_for_rhythm(spoken)
        if len(segments) > 1:
            split_count += len(segments) - 1
        for segment in segments:
            signal = rhythm_signal_for_line(segment, len(output), len(output) + 1)
            if signal == "explain":
                plain_gap += 1
            else:
                plain_gap = 0
            if plain_gap >= 4:
                bridge = rhythm_bridge_line(topic, bridge_index)
                output.append(format_rhythm_dialogue_line(speaker, bridge))
                bridge_count += 1
                bridge_index += 1
                plain_gap = 0
            line = format_rhythm_dialogue_line(speaker, segment)
            output.append(f"{prefix_text}{line}" if prefix_text else line)

    for raw in script.splitlines():
        original = raw.rstrip()
        stripped = original.strip()
        if not stripped:
            output.append(original)
            continue
        prefix = ""
        body = stripped
        if body.startswith(("- ", "* ")):
            prefix = body[:2]
            body = body[2:].strip()
        normalized = re.sub(r"\*\*(.*?)\*\*", r"\1", body).strip()
        parsed = parse_dialogue_speaker_line(normalized, max_speaker_len=18)
        if not parsed:
            if is_stage_direction_line(normalized) or normalized.startswith(("### ", "## ", "# ")) or is_script_marker_speaker(normalized, ""):
                output.append(original)
                plain_gap = 0
                continue
            if clean_text(normalized) and len(clean_text(normalized)) > 34 and re.search(r"[，。！？；：,.!?;:]", normalized):
                emit_spoken_segments(last_speaker, normalized, prefix)
                continue
            output.append(original)
            continue

        speaker = clean_text(parsed[0]) or last_speaker
        spoken = clean_text(parsed[1])
        last_speaker = speaker
        if not spoken:
            output.append(original)
            continue
        if is_stage_direction_line(spoken) or looks_like_visual_direction(spoken):
            output.append(original)
            plain_gap = 0
            continue
        emit_spoken_segments(speaker, spoken, prefix)

    dialogue_parts: list[str] = []
    for line in output:
        parsed = parse_dialogue_speaker_line(line.strip().removeprefix("- ").removeprefix("* ").strip(), max_speaker_len=18)
        if parsed:
            dialogue_parts.append(parsed[1])
    dialogue_text = "\n".join(dialogue_parts)
    interaction_added = False
    tail = dialogue_text[-220:]
    needs_topic_callback = any(token in clean_text(topic) for token in ("自动续费", "扣费", "订阅", "免密", "支付")) and "扣费短信" not in tail
    if needs_topic_callback or not any(token in tail for token in INTERACTION_SIGNAL_TOKENS) or not any(token in tail for token in ("你遇到过", "你家里", "你是哪种", "你查到", "评论区告诉我")):
        output.append(format_rhythm_dialogue_line(last_speaker, interaction_line_for_topic(topic)))
        interaction_added = True

    return "\n".join(output).strip(), {
        "changed": split_count > 0 or bridge_count > 0 or interaction_added,
        "split_count": split_count,
        "bridge_count": bridge_count,
        "interaction_added": interaction_added,
    }


def enhance_content_rhythm(project_id: int, content: str | None = None, *, save: bool = True) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    original = content if content is not None else storage.get_content(project_id)
    if not clean_text(original):
        raise ValueError("当前项目还没有 content.md，无法做节奏增强。")
    before = script_rhythm_report(project_id, original)
    title = detect_script_section_title(original)
    script = extract_section(original, title, level=2)
    if not script:
        raise ValueError("没有找到可增强的脚本区块。")

    topic = clean_text(project.get("topic_name") or first_heading(original) or "")
    enhanced_script, edit_stats = enhance_script_section_rhythm(script, topic, mode)
    enhanced = replace_section(original, title, enhanced_script, level=2)
    enhanced = compact_content_meta(enhanced)
    if enhanced != original:
        enhanced = refresh_content_image_prompts(project, template, enhanced)
    summary = summarize_content(enhanced, mode)
    after = script_rhythm_report(project_id, enhanced)
    report = {
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "section": title,
        "changed": enhanced != original,
        "edits": edit_stats,
        "before": {
            "score": before.get("score"),
            "metrics": before.get("metrics", {}),
            "issues": before.get("issues", []),
        },
        "after": {
            "score": after.get("score"),
            "metrics": after.get("metrics", {}),
            "issues": after.get("issues", []),
        },
    }

    report_path = storage.save_report(project_id, "script_rhythm_enhance", report)
    if save and enhanced != original:
        storage.save_content(project_id, enhanced)
        storage.save_summary(project_id, summary)
        storage.save_report(project_id, "script_rhythm", after)
        mark_image_review_dirty(project_id, "文案节奏已增强，图片提示词已跟随口播重建，图片需要重新确认")
    return {
        "ok": True,
        "content": enhanced,
        "summary": summary,
        "report_path": str(report_path),
        "result": report,
        "rhythm": after,
    }


def video_quality_report(project_id: int) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    audio_path = storage.project_file(project_id, "audio/podcast.mp3")
    subtitle_path = storage.project_file(project_id, "audio/subtitles.srt")
    video_path = storage.project_file(project_id, "releases/final-video.mp4")
    scene_paths = find_scene_image_paths(project_id)
    scene_status_payload = storage.scene_status(project_id)
    scene_count = int(scene_status_payload.get("generated_count", 0) or len(scene_paths))
    audio_duration = safe_probe_duration(audio_path)
    video_duration = safe_probe_duration(video_path)
    subtitle_entries = load_srt_entries(subtitle_path) if subtitle_path.exists() else []
    subtitle_end = subtitle_end_duration(subtitle_path) or 0.0
    expected_duration = 0.0
    if audio_path.exists():
        try:
            expected_duration = round(expected_video_duration(project_id, max(1, scene_count), audio_path, subtitle_path if subtitle_path.exists() else None), 3)
        except Exception:
            expected_duration = audio_duration

    if not audio_path.exists():
        issues.append(quality_issue("risk", "音频", "缺少 podcast.mp3。", "先生成配音。"))
    if not subtitle_path.exists():
        issues.append(quality_issue("warn", "字幕", "缺少 subtitles.srt。", "先生成或重新对齐字幕。"))
    if not video_path.exists():
        issues.append(quality_issue("risk", "成片", "缺少 final-video.mp4。", "先合成成片。"))
    if audio_duration > 0 and video_duration > 0:
        delta = round(video_duration - audio_duration, 3)
        tolerance = video_duration_tolerance_seconds(audio_duration)
        if abs(delta) > tolerance:
            issues.append(quality_issue("risk", "时长", f"视频和音频时长差异 {delta:+.1f}s。", "重新按音频时长合成视频，避免后半段黑屏或无声。"))
    if audio_duration > 0 and subtitle_entries:
        coverage = subtitle_coverage_ratio(subtitle_entries, int(audio_duration * 1000))
        if coverage < 0.96:
            issues.append(quality_issue("warn", "字幕覆盖", f"字幕只覆盖音频约 {coverage * 100:.0f}%。", "重新 ASR 或字幕对齐，确保尾段不丢字幕。"))
        if subtitle_end > audio_duration + 3:
            issues.append(quality_issue("warn", "字幕时轴", "字幕结束时间明显超过音频。", "重新对齐字幕，避免字幕延迟或错位。"))
    else:
        coverage = 0.0

    timeline = storage.read_json(storage.project_file(project_id, "audio/scene_timeline.json"), {})
    timeline_scenes = timeline.get("scenes") if isinstance(timeline, dict) else []
    if isinstance(timeline_scenes, list) and timeline_scenes and scene_count and len(timeline_scenes) != scene_count:
        issues.append(quality_issue("warn", "场景时轴", f"时轴 {len(timeline_scenes)} 段，场景图 {scene_count} 张。", "重新生成字幕/场景图时轴，保持段数一致。"))

    score = quality_score_from_issues(issues)
    return {
        "score": score,
        "verdict": quality_verdict(score),
        "metrics": {
            "audio_exists": audio_path.exists(),
            "subtitle_exists": subtitle_path.exists(),
            "video_exists": video_path.exists(),
            "audio_duration_sec": audio_duration,
            "video_duration_sec": video_duration,
            "expected_duration_sec": expected_duration,
            "subtitle_end_sec": round(subtitle_end, 3),
            "subtitle_count": len(subtitle_entries),
            "subtitle_coverage": round(coverage, 4),
            "scene_count": scene_count,
            "timeline_scene_count": len(timeline_scenes) if isinstance(timeline_scenes, list) else 0,
        },
        "issues": issues,
    }


def _project_asset_url(project_id: int, path: Path) -> str:
    try:
        rel = path.relative_to(storage.project_dir(project_id)).as_posix()
    except Exception:
        rel = path.name
    return f"/data/projects/{project_id}/{rel}"


def _project_status_item(key: str, label: str, status: str, detail: str = "", action: str = "") -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "action": action,
    }


def project_status_report(project_id: int) -> dict[str, Any]:
    project = storage.get_project(project_id)
    brief = clean_text(storage.get_brief(project_id))
    content = clean_text(storage.get_content(project_id))
    scene_status_payload = storage.scene_status(project_id)
    image_review = image_review_status(project_id)
    video_quality = video_quality_report(project_id)
    audio_path = storage.project_file(project_id, "audio/podcast.mp3")
    subtitle_path = storage.project_file(project_id, "audio/subtitles.srt")
    final_video_path = storage.project_file(project_id, "releases/final-video.mp4")
    cover_paths = _cover_output_paths(project_id)
    audio_duration = safe_probe_duration(audio_path)
    subtitle_entries = load_srt_entries(subtitle_path) if subtitle_path.exists() else []
    subtitle_coverage = subtitle_coverage_ratio(subtitle_entries, int(audio_duration * 1000)) if audio_duration > 0 else 0.0
    scene_expected = int(scene_status_payload.get("expected_count", 0) or 0)
    scene_generated = int(scene_status_payload.get("generated_count", 0) or 0)
    covers_generated = sum(1 for path in cover_paths if path.exists())
    steps = [
        _project_status_item(
            "brief",
            "简报",
            "ok" if brief else "warn",
            "已填写 brief.md" if brief else "brief.md 还是空的",
            "先补齐主题、素材和频道要求。" if not brief else "",
        ),
        _project_status_item(
            "content",
            "文案",
            "ok" if content else "risk",
            "content.md 已生成" if content else "缺少 content.md",
            "先生成或粘贴文案。" if not content else "",
        ),
        _project_status_item(
            "audio",
            "音频",
            "ok" if audio_duration > 0 else "warn",
            f"podcast.mp3 {audio_duration:.1f}s" if audio_duration > 0 else "缺少 podcast.mp3",
            "先生成配音。" if audio_duration <= 0 else "",
        ),
        _project_status_item(
            "subtitles",
            "字幕",
            "ok" if subtitle_path.exists() and subtitle_coverage >= 0.96 else ("warn" if subtitle_path.exists() else "risk"),
            f"{len(subtitle_entries)} 条，覆盖 {subtitle_coverage * 100:.0f}%" if subtitle_path.exists() else "缺少 subtitles.srt",
            "重新 ASR 或字幕对齐。" if not subtitle_path.exists() or subtitle_coverage < 0.96 else "",
        ),
        _project_status_item(
            "images",
            "图片",
            "ok" if scene_expected > 0 and scene_generated >= scene_expected and covers_generated == len(cover_paths) else "warn",
            f"场景 {scene_generated}/{scene_expected or 0}，封面 {covers_generated}/{len(cover_paths)}",
            "补齐场景图和横屏/图文/竖屏封面。" if scene_generated < scene_expected or covers_generated < len(cover_paths) else "",
        ),
        _project_status_item(
            "image_review",
            "图片确认",
            "ok" if image_review.get("can_generate_video") else "warn",
            "已确认" if image_review.get("can_generate_video") else ("可确认，等待人工确认" if image_review.get("ready_to_confirm") else "图片还未齐"),
            "确认图片后再合成成片。" if not image_review.get("can_generate_video") else "",
        ),
        _project_status_item(
            "video",
            "成片",
            "ok" if final_video_path.exists() and int(video_quality.get("score", 0) or 0) >= 72 else ("warn" if final_video_path.exists() else "risk"),
            f"final-video.mp4，{video_quality.get('metrics', {}).get('video_duration_sec', 0)}s，{video_quality.get('score', 0)} 分" if final_video_path.exists() else "缺少 final-video.mp4",
            "运行成片自检，确认无黑屏、字幕覆盖和时长问题。" if final_video_path.exists() else "先合成视频。",
        ),
    ]
    status_rank = {"ok": 0, "info": 1, "warn": 2, "risk": 3}
    worst = max(steps, key=lambda item: status_rank.get(item["status"], 1)) if steps else None
    return {
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "topic": project.get("topic_name", ""),
        "overall_status": worst["status"] if worst else "ok",
        "ready_for_video": all(item["status"] == "ok" for item in steps[:6]),
        "ready_for_release": final_video_path.exists() and covers_generated == len(cover_paths),
        "steps": steps,
        "metrics": {
            "audio_duration_sec": audio_duration,
            "subtitle_coverage": round(subtitle_coverage, 4),
            "scene_expected": scene_expected,
            "scene_generated": scene_generated,
            "cover_expected": len(cover_paths),
            "cover_generated": covers_generated,
            "video_quality_score": video_quality.get("score", 0),
        },
    }


def production_resume_plan(project_id: int) -> dict[str, Any]:
    scene_status_payload = storage.scene_status(project_id)
    audio_path = storage.project_file(project_id, "audio/podcast.mp3")
    subtitle_path = storage.project_file(project_id, "audio/subtitles.srt")
    final_video_path = storage.project_file(project_id, "releases/final-video.mp4")
    cover_paths = _cover_output_paths(project_id)
    image_review = image_review_status(project_id)
    scene_expected = int(scene_status_payload.get("expected_count", 0) or 0)
    scene_generated = int(scene_status_payload.get("generated_count", 0) or 0)
    cover_generated = sum(1 for path in cover_paths if path.exists())
    steps: list[str] = []
    reasons: list[str] = []

    if not audio_path.exists():
        steps.extend(["audio", "subtitles"])
        reasons.append("缺少配音，需要先生成音频并重新对齐字幕。")
    elif not subtitle_path.exists():
        steps.append("subtitles")
        reasons.append("缺少字幕，需要重新 ASR/对齐字幕。")

    if scene_expected <= 0:
        steps.extend(["subtitles", "images"])
        reasons.append("没有场景时轴或场景图计划，建议从字幕对齐后重建图片。")
    elif scene_generated < scene_expected:
        steps.append("images_missing")
        reasons.append(f"场景图缺失 {scene_generated}/{scene_expected}，建议只补缺失场景图。")

    if cover_generated < len(cover_paths):
        steps.append("covers_missing")
        reasons.append(f"封面缺失 {cover_generated}/{len(cover_paths)}，建议只补缺失封面。")

    if not final_video_path.exists():
        if image_review.get("can_generate_video"):
            steps.append("video")
            reasons.append("图片已确认但缺少成片，建议只合成视频。")
        else:
            reasons.append("图片尚未确认，先确认图片后再合成视频。")

    ordered = []
    for step in steps:
        if step not in ordered:
            ordered.append(step)
    if not ordered and final_video_path.exists():
        reasons.append("当前产物完整，无需续跑；如要提升质量，可先做成片自检或单张重绘。")

    return {
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "recommended_steps": ordered,
        "can_resume": bool(ordered),
        "reasons": reasons,
        "image_review": image_review,
        "scene_expected": scene_expected,
        "scene_generated": scene_generated,
        "cover_expected": len(cover_paths),
        "cover_generated": cover_generated,
    }


def _video_self_check_sample_times(duration: float) -> list[float]:
    if duration <= 0:
        return []
    raw = [3.0, duration * 0.18, duration * 0.34, duration * 0.50, duration * 0.66, duration * 0.82, max(1.0, duration - 8.0), max(1.0, duration - 2.0)]
    samples: list[float] = []
    for value in raw:
        safe = max(0.5, min(duration - 0.2, float(value)))
        if not any(abs(safe - existing) < 1.5 for existing in samples):
            samples.append(round(safe, 2))
    return samples[:8]


def _make_frame_contact_sheet(frame_paths: list[Path], target_path: Path) -> None:
    if Image is None or not frame_paths:
        return
    thumbs = []
    for path in frame_paths:
        try:
            with Image.open(path) as image:
                thumb = image.convert("RGB")
                thumb.thumbnail((360, 203))
                canvas = Image.new("RGB", (360, 203), "#101827")
                canvas.paste(thumb, ((360 - thumb.width) // 2, (203 - thumb.height) // 2))
                thumbs.append(canvas)
        except Exception:
            continue
    if not thumbs:
        return
    cols = 2
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * 360, rows * 203), "#101827")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % cols) * 360, (index // cols) * 203))
    storage.ensure_dir(target_path.parent)
    sheet.save(target_path, quality=90)


def run_video_self_check(project_id: int) -> dict[str, Any]:
    video_path = storage.project_file(project_id, "releases/final-video.mp4")
    audio_path = storage.project_file(project_id, "audio/podcast.mp3")
    subtitle_path = storage.project_file(project_id, "audio/subtitles.srt")
    reports_dir = storage.project_file(project_id, "reports")
    frames_dir = reports_dir / "video-self-check-frames"
    storage.ensure_dir(frames_dir)
    issues: list[dict[str, Any]] = []
    frame_records: list[dict[str, Any]] = []
    black_segments: list[dict[str, float]] = []

    audio_duration = safe_probe_duration(audio_path)
    video_duration = safe_probe_duration(video_path)
    subtitle_entries = load_srt_entries(subtitle_path) if subtitle_path.exists() else []
    subtitle_end = subtitle_end_duration(subtitle_path) or 0.0
    subtitle_coverage = subtitle_coverage_ratio(subtitle_entries, int(audio_duration * 1000)) if audio_duration > 0 else 0.0
    timeline = storage.read_json(storage.project_file(project_id, "audio/scene_timeline.json"), {})
    timeline_scenes = timeline.get("scenes") if isinstance(timeline, dict) else []
    scene_count = len(find_scene_image_paths(project_id))

    if not video_path.exists():
        issues.append(quality_issue("risk", "成片", "缺少 final-video.mp4。", "先完成成片合成。"))
    if audio_duration > 0 and video_duration > 0:
        delta = round(video_duration - audio_duration, 3)
        if abs(delta) > video_duration_tolerance_seconds(audio_duration):
            issues.append(quality_issue("risk", "时长", f"视频与音频差异 {delta:+.1f}s。", "重新按音频时长合成。"))
    if subtitle_entries and audio_duration > 0:
        if subtitle_coverage < 0.96:
            issues.append(quality_issue("warn", "字幕覆盖", f"字幕覆盖约 {subtitle_coverage * 100:.0f}%。", "重新 ASR 或字幕对齐。"))
        if audio_duration - subtitle_end > 3:
            issues.append(quality_issue("warn", "字幕尾段", f"字幕比音频提前结束 {audio_duration - subtitle_end:.1f}s。", "重新生成字幕。"))
        long_lines = []
        for entry in subtitle_entries:
            display = wrap_subtitle_display_text(str(entry.get("text") or ""))
            if any(len(line) > 22 for line in display.splitlines()):
                long_lines.append(entry)
        if len(long_lines) > max(5, len(subtitle_entries) * 0.18):
            issues.append(quality_issue("warn", "字幕换行", "较多字幕行偏长，可能在横屏中压边。", "缩短单句或重新生成字幕换行。"))
    elif not subtitle_path.exists():
        issues.append(quality_issue("warn", "字幕", "缺少 subtitles.srt。", "先生成字幕。"))
    if isinstance(timeline_scenes, list) and timeline_scenes and scene_count and len(timeline_scenes) != scene_count:
        issues.append(quality_issue("warn", "场景时轴", f"时轴 {len(timeline_scenes)} 段，场景图 {scene_count} 张。", "重新生成 scene_timeline，保持段数一致。"))

    if video_path.exists() and video_duration > 0:
        for index, sample_time in enumerate(_video_self_check_sample_times(video_duration), start=1):
            frame_path = frames_dir / f"frame_{index:02d}_{int(sample_time * 1000)}ms.jpg"
            cmd = [
                str(ffmpeg_binary()),
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{sample_time:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-y",
                str(frame_path),
            ]
            ok = False
            mean_luma = 0.0
            try:
                subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45, check=True)
                ok = frame_path.exists() and frame_path.stat().st_size > 0
                if ok and Image is not None and ImageStat is not None:
                    with Image.open(frame_path) as image:
                        gray = image.convert("L")
                        mean_luma = round(float(ImageStat.Stat(gray).mean[0]), 2)
                        if mean_luma < 8:
                            issues.append(quality_issue("risk", "抽帧黑屏", f"{sample_time:.1f}s 抽帧疑似黑屏。", "检查该时间点场景图和合成链路。"))
                        elif mean_luma < 24:
                            issues.append(quality_issue("warn", "抽帧偏暗", f"{sample_time:.1f}s 画面偏暗。", "考虑重绘该段图片或提升合成亮度。"))
            except Exception as exc:
                frame_records.append({"time_sec": sample_time, "ok": False, "error": str(exc)})
                continue
            frame_records.append(
                {
                    "time_sec": sample_time,
                    "ok": ok,
                    "mean_luma": mean_luma,
                    "file": str(frame_path.relative_to(storage.project_dir(project_id))) if ok else "",
                    "url": _project_asset_url(project_id, frame_path) if ok else "",
                }
            )

        contact_sheet_path = reports_dir / "final_video_frame_contact_sheet.jpg"
        _make_frame_contact_sheet([Path(storage.project_dir(project_id) / item["file"]) for item in frame_records if item.get("file")], contact_sheet_path)

        try:
            result = subprocess.run(
                [
                    str(ffmpeg_binary()),
                    "-hide_banner",
                    "-i",
                    str(video_path),
                    "-vf",
                    "blackdetect=d=0.8:pix_th=0.10",
                    "-an",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            black_log = (result.stderr or "") + "\n" + (result.stdout or "")
            for match in re.finditer(r"black_start:(?P<start>[\d.]+)\s+black_end:(?P<end>[\d.]+)\s+black_duration:(?P<duration>[\d.]+)", black_log):
                black_segments.append(
                    {
                        "start": round(float(match.group("start")), 3),
                        "end": round(float(match.group("end")), 3),
                        "duration": round(float(match.group("duration")), 3),
                    }
                )
            if black_segments:
                issues.append(quality_issue("risk", "黑屏检测", f"检测到 {len(black_segments)} 段黑屏。", "重新合成并检查对应图片/转场。"))
        except Exception as exc:
            issues.append(quality_issue("info", "黑屏检测", f"黑屏检测未完成：{exc}", "可稍后重新运行成片自检。"))
    else:
        contact_sheet_path = reports_dir / "final_video_frame_contact_sheet.jpg"

    score = quality_score_from_issues(issues)
    result = {
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "score": score,
        "verdict": quality_verdict(score),
        "metrics": {
            "audio_duration_sec": audio_duration,
            "video_duration_sec": video_duration,
            "duration_delta_sec": round(video_duration - audio_duration, 3) if audio_duration and video_duration else 0,
            "subtitle_count": len(subtitle_entries),
            "subtitle_end_sec": round(subtitle_end, 3),
            "subtitle_coverage": round(subtitle_coverage, 4),
            "scene_count": scene_count,
            "timeline_scene_count": len(timeline_scenes) if isinstance(timeline_scenes, list) else 0,
            "sampled_frame_count": len(frame_records),
            "black_segment_count": len(black_segments),
        },
        "frames": frame_records,
        "black_segments": black_segments,
        "contact_sheet": str(contact_sheet_path.relative_to(storage.project_dir(project_id))) if contact_sheet_path.exists() else "",
        "contact_sheet_url": _project_asset_url(project_id, contact_sheet_path) if contact_sheet_path.exists() else "",
        "issues": issues,
    }
    storage.save_report(project_id, "video_self_check", result)
    return result


def release_checklist_report(project_id: int) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    summary = storage.get_summary(project_id)
    video_quality = video_quality_report(project_id)
    self_check = storage.get_report(project_id, "video_self_check") or {}
    final_video = storage.project_file(project_id, "releases/final-video.mp4")
    cover_paths = _cover_output_paths(project_id)
    title = clean_text(str(summary.get("publish_title") or summary.get("video_title") or project.get("topic_name") or ""))
    tags = clean_text(str(template.get("release_tags") or summary.get("release_tags") or ""))
    description = clean_text(str(summary.get("description") or summary.get("summary") or ""))
    issues: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    def add(key: str, label: str, ok: bool, detail: str, fix: str = "", level: str = "warn") -> None:
        status = "ok" if ok else level
        checks.append({"key": key, "label": label, "status": status, "detail": detail, "fix": "" if ok else fix})
        if not ok:
            issues.append(quality_issue("risk" if level == "risk" else "warn", label, detail, fix))

    add("video", "成片文件", final_video.exists(), "final-video.mp4 已生成" if final_video.exists() else "缺少 final-video.mp4", "先合成成片。", "risk")
    cover_generated = sum(1 for path in cover_paths if path.exists())
    add("covers", "封面", cover_generated == len(cover_paths), f"封面 {cover_generated}/{len(cover_paths)}", "补齐横屏、图文、竖屏封面。", "risk")
    add("title", "发布标题", 8 <= len(title) <= 36, f"标题 {len(title)} 字：{title}", "把标题压到 8-36 字，保留明确痛点或反差。")
    add("tags", "发布标签", bool(tags), f"标签：{tags or '未填写'}", "在频道里配置 release_tags，或在投放页填写平台标签。")
    add("description", "发布描述", bool(description) or bool(title), "已有摘要/标题可用于发布描述" if description or title else "缺少发布描述素材", "补一个核心观点 + 互动问题。")
    add("video_quality", "成片质量", int(video_quality.get("score", 0) or 0) >= 72, f"成片质量 {video_quality.get('score', 0)} 分", "先修复质量总检里的成片问题。", "risk")
    self_score = int(self_check.get("score", 0) or 0)
    add("self_check", "成片自检", self_score >= 72, f"自检 {self_score or '未运行'} 分", "先运行“一键成片自检”，确认无黑屏、字幕和时长风险。")
    subtitle_coverage = float(video_quality.get("metrics", {}).get("subtitle_coverage", 0) or 0)
    add("subtitle", "字幕覆盖", subtitle_coverage >= 0.96, f"字幕覆盖 {subtitle_coverage * 100:.0f}%", "重新 ASR 或字幕对齐。")

    score = quality_score_from_issues(issues)
    return {
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "topic": project.get("topic_name", ""),
        "score": score,
        "passed": not any(item.get("level") == "risk" for item in issues),
        "verdict": quality_verdict(score),
        "checks": checks,
        "issues": issues,
        "publish_assets": {
            "title": title,
            "tags": tags,
            "description": description,
            "final_video": str(final_video),
            "covers": [str(path) for path in cover_paths if path.exists()],
        },
    }


def quality_gate_report(project_id: int, brief: str | None = None, content: str | None = None) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    brief_text = brief if brief is not None else storage.get_brief(project_id)
    content_text = content if content is not None else storage.get_content(project_id)
    references = storage.get_references(project_id)
    sections = {
        "content": content_quality_report(project, template, brief_text, content_text, references) if clean_text(content_text) else {
            "score": 0,
            "verdict": "还没有 content.md，无法检查文案。",
            "issues": [quality_issue("risk", "文案", "缺少 content.md。", "先生成或粘贴脚本。")],
            "metrics": {},
        },
        "images": image_director_report(project_id, project, template, content_text),
        "video": video_quality_report(project_id),
    }
    scores = [int(section.get("score", 0) or 0) for section in sections.values()]
    overall = min(scores) if scores else 0
    return {
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "topic": project.get("topic_name", ""),
        "overall_score": overall,
        "verdict": quality_verdict(overall),
        "sections": sections,
        "next_actions": [
            item.get("fix") or item.get("issue")
            for section in sections.values()
            for item in section.get("issues", [])
            if isinstance(item, dict) and str(item.get("level") or "") in {"risk", "warn"} and (item.get("fix") or item.get("issue"))
        ][:8],
    }


def creative_optimization_plan(project_id: int, content: str | None = None) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    content_text = content if content is not None else storage.get_content(project_id)
    has_content = bool(clean_text(content_text))
    quality = quality_gate_report(project_id, content=content_text) if has_content else {}
    rhythm = script_rhythm_report(project_id, content_text) if has_content else {}
    layers = image_prompt_layer_report(project_id, content_text) if has_content else {}
    resume = production_resume_plan(project_id)
    status = project_status_report(project_id)
    history = channel_history_report(project_id)
    image_review = image_review_status(project_id)
    release_check = storage.get_report(project_id, "release_checklist") or {}

    actions: list[dict[str, Any]] = []

    def add_action(key: str, label: str, reason: str, priority: int, *, action_type: str = "manual", payload: dict[str, Any] | None = None) -> None:
        actions.append(
            {
                "key": key,
                "label": label,
                "reason": reason,
                "priority": priority,
                "action_type": action_type,
                "payload": payload or {},
            }
        )

    if not has_content:
        add_action("generate_content", "先生成 content.md", "当前还没有脚本成稿，无法做后续生产判断。", 100, action_type="open_content")
    else:
        rhythm_score = int(rhythm.get("score", 0) or 0)
        opening_score = float(rhythm.get("engagement", {}).get("opening_score", 0) or 0)
        retention_score = float(rhythm.get("engagement", {}).get("retention_score", 0) or 0)
        interaction_score = float(rhythm.get("engagement", {}).get("interaction_score", 0) or 0)
        if rhythm_score < 82 or opening_score < 3.8 or retention_score < 3.5 or interaction_score < 3.4:
            add_action(
                "viral_rewrite",
                "执行总编优化",
                "节奏体检显示开头、中段或结尾还有提升空间，建议先改稿再出图。",
                95,
                action_type="viral_rewrite",
            )
        layer_score = int(layers.get("score", 0) or 0)
        weak_prompts = int(layers.get("metrics", {}).get("weak_prompt_count", 0) or 0)
        if layer_score < 82 or weak_prompts > 0:
            add_action(
                "repair_image_prompts",
                "重建图片提示词",
                f"图片提示词分层 {layer_score} 分，弱提示词 {weak_prompts} 条，建议先修提示词再生图。",
                88,
                action_type="repair_image_prompts",
            )

    recommended_steps = list(resume.get("recommended_steps") or [])
    if recommended_steps:
        add_action(
            "apply_resume_steps",
            "应用续跑步骤",
            "当前产物不完整，建议按续跑建议补齐缺失环节。",
            78,
            action_type="apply_resume_steps",
            payload={"steps": recommended_steps},
        )
    elif has_content and not recommended_steps:
        final_video = storage.project_file(project_id, "releases/final-video.mp4")
        if not final_video.exists() and image_review.get("can_generate_video"):
            add_action("open_produce", "去生产成片", "脚本与图片条件基本具备，可以进入成片合成。", 70, action_type="open_produce")
        elif not image_review.get("confirmed") and image_review.get("required"):
            add_action("confirm_images", "确认图片后成片", "当前开启了图片确认关卡，成片前需要先确认场景图和封面图。", 68, action_type="open_produce")
        elif final_video.exists():
            add_action("release_checklist", "做发布前检查", "成片已经存在，下一步建议检查封面、标题、标签和字幕风险。", 62, action_type="release_checklist")

    if not actions and has_content:
        add_action("ready", "可以继续生产/发布", "当前没有明显阻塞项，可按你的目标进入生产或投放。", 40, action_type="open_produce")

    actions.sort(key=lambda item: int(item.get("priority", 0) or 0), reverse=True)
    scores = [
        int(quality.get("overall_score", 100) or 100) if quality else 0,
        int(rhythm.get("score", 100) or 100) if rhythm else 0,
        int(layers.get("score", 100) or 100) if layers else 0,
    ]
    overall = min(scores) if scores else 0
    if not has_content:
        overall = 0
    return {
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "topic": project.get("topic_name", ""),
        "score": overall,
        "verdict": quality_verdict(overall),
        "summary": {
            "quality_score": quality.get("overall_score", 0) if quality else 0,
            "rhythm_score": rhythm.get("score", 0) if rhythm else 0,
            "image_layer_score": layers.get("score", 0) if layers else 0,
            "history_count": history.get("history_count", 0),
            "release_metrics_count": history.get("with_release_metrics_count", 0),
            "ready_for_video": status.get("ready_for_video", False),
            "ready_for_release": status.get("ready_for_release", False),
        },
        "actions": actions[:8],
        "reports": {
            "quality_gate": quality,
            "rhythm": rhythm,
            "image_layers": layers,
            "resume_plan": resume,
            "project_status": status,
            "channel_history": {
                "recommendations": history.get("recommendations", []),
                "best_hooks": history.get("best_hooks", [])[:3],
                "top_keywords": history.get("top_keywords", [])[:6],
            },
            "release_checklist": release_check,
        },
    }


def repair_image_prompt_section(project_id: int, content: str | None = None) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    brief = storage.get_brief(project_id)
    references = storage.get_references(project_id)
    tavily_topic = storage.get_project_settings(project_id).get("tavily_topic", "general")
    original_content = content if content is not None else storage.get_content(project_id)
    old_scene_prompts = parse_scene_prompts(original_content, mode)
    old_similarity = prompt_similarity_score(old_scene_prompts)

    repaired_content = refresh_content_image_prompts(project, template, original_content)
    new_scene_prompts = parse_scene_prompts(repaired_content, mode)
    new_similarity = prompt_similarity_score(new_scene_prompts)
    changed = repaired_content != original_content

    storage.save_content(project_id, repaired_content)
    summary = summarize_content(repaired_content, mode)
    storage.save_summary(project_id, summary)
    artifacts = build_content_artifacts(project, template, brief, tavily_topic, references, repaired_content)
    storage.write_json(storage.project_file(project_id, "content_strategy.json"), artifacts["strategy"])
    storage.write_json(storage.project_file(project_id, "content_audit.json"), artifacts["audit"])
    storage.save_report(project_id, "topic_score", artifacts["strategy"]["topic_score"])
    storage.save_report(project_id, "viral_doctor", artifacts["audit"]["viral_doctor"])
    storage.save_report(project_id, "title_cover_ab", artifacts["audit"]["title_cover_ab"])
    mark_image_review_dirty(project_id, "图片提示词已按频道、主题和口播重新生成，图片需要重新确认")

    report = quality_gate_report(project_id, brief=brief, content=repaired_content)
    report_path = storage.save_report(project_id, "quality_gate", report)
    return {
        "ok": True,
        "changed": changed,
        "content": repaired_content,
        "summary": summary,
        "before": {
            "scene_prompt_count": len(old_scene_prompts),
            "prompt_similarity_max": old_similarity,
        },
        "after": {
            "scene_prompt_count": len(new_scene_prompts),
            "prompt_similarity_max": new_similarity,
        },
        "quality_gate": report,
        "report_path": str(report_path),
    }


def optimize_project_content(project_id: int, content: str | None = None) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    brief = storage.get_brief(project_id)
    original_content = content if content is not None else storage.get_content(project_id)
    if not clean_text(original_content):
        raise ValueError("当前项目还没有 content.md，先生成或粘贴文案。")

    before_engagement = content_engagement_report(original_content, mode)
    optimized_content = original_content
    provider = "no-op"
    deepseek_error = ""
    env = runtime_env()
    api_key = clean_text(env.get("DEEPSEEK_API_KEY", ""))
    if api_key and OpenAI is not None:
        base_url = clean_text(env.get("DEEPSEEK_BASE_URL", "")) or "https://api.deepseek.com"
        model = clean_text(env.get("DEEPSEEK_MODEL", "")) or "deepseek-v4-flash"
        thinking_type = clean_text(env.get("DEEPSEEK_THINKING_TYPE", "")) or "enabled"
        reasoning_effort = clean_text(env.get("DEEPSEEK_REASONING_EFFORT", "")) or "high"
        extra_body: dict[str, Any] = {"reasoning_effort": reasoning_effort}
        if thinking_type in {"enabled", "disabled"}:
            extra_body["thinking"] = {"type": thinking_type}
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
            messages = compose_deepseek_rewrite_messages(project, template, original_content, before_engagement)
            messages[0]["content"] = (
                str(messages[0].get("content") or "").strip()
                + "\n\n"
                + build_common_content_system_rules()
                + "\n\n"
                + build_viral_content_rules(project, template)
            )
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.66,
                max_tokens=12000,
                extra_body=extra_body,
            )
            choice = response.choices[0] if getattr(response, "choices", None) else None
            rewritten = message_content_to_text(choice.message.content if choice and getattr(choice, "message", None) else "")
            rewritten = strip_code_fences(rewritten)
            rewritten = re.sub(r"(?is)^<think>.*?</think>\s*", "", rewritten).strip()
            if not rewritten.startswith("#"):
                raise ContentGenerationError("DeepSeek 返回内容不是完整 content.md。")
            optimized_content = rewritten
            provider = "deepseek"
        except Exception as exc:
            deepseek_error = str(exc)
            provider = "deepseek-failed"
    elif not api_key:
        deepseek_error = "未配置 DeepSeek API Key，无法做整稿总编式改写。"
    else:
        deepseek_error = "当前环境缺少 openai 依赖，无法调用 DeepSeek。"

    optimized_content = compact_content_meta(optimized_content)
    image_refreshed_content = refresh_content_image_prompts(project, template, optimized_content)
    changed = image_refreshed_content != original_content
    summary = summarize_content(image_refreshed_content, mode)
    references = storage.get_references(project_id)
    tavily_topic = storage.get_project_settings(project_id).get("tavily_topic", "general")
    artifacts = build_content_artifacts(project, template, brief, tavily_topic, references, image_refreshed_content)
    storage.save_content(project_id, image_refreshed_content)
    storage.save_summary(project_id, summary)
    storage.write_json(storage.project_file(project_id, "content_strategy.json"), artifacts["strategy"])
    storage.write_json(storage.project_file(project_id, "content_audit.json"), artifacts["audit"])
    storage.save_report(project_id, "topic_score", artifacts["strategy"]["topic_score"])
    storage.save_report(project_id, "viral_doctor", artifacts["audit"]["viral_doctor"])
    storage.save_report(project_id, "title_cover_ab", artifacts["audit"]["title_cover_ab"])
    if changed:
        mark_image_review_dirty(project_id, "content.md 已做总编优化/图片提示词重建，图片需要重新确认")
    report = quality_gate_report(project_id, brief=brief, content=image_refreshed_content)
    report_path = storage.save_report(project_id, "quality_gate", report)
    after_engagement = content_engagement_report(image_refreshed_content, mode)
    return {
        "ok": True,
        "changed": changed,
        "provider": provider,
        "deepseek_error": deepseek_error,
        "content": image_refreshed_content,
        "summary": summary,
        "before": before_engagement,
        "after": after_engagement,
        "quality_gate": report,
        "report_path": str(report_path),
    }


def coerce_non_negative_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return max(0, int(float(value)))
    except Exception:
        return 0


def coerce_non_negative_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return max(0.0, float(value))
    except Exception:
        return 0.0


def normalize_release_metrics(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    completion_rate = coerce_non_negative_float(raw.get("completion_rate"))
    if completion_rate <= 1 and completion_rate > 0:
        completion_rate *= 100
    completion_rate = round(clamp_number(completion_rate, 0, 100), 2)
    metrics = {
        "views": coerce_non_negative_int(raw.get("views")),
        "likes": coerce_non_negative_int(raw.get("likes")),
        "comments": coerce_non_negative_int(raw.get("comments")),
        "shares": coerce_non_negative_int(raw.get("shares")),
        "favorites": coerce_non_negative_int(raw.get("favorites")),
        "completion_rate": completion_rate,
        "notes": clean_text(str(raw.get("notes") or "")),
        "updated_at": storage.now_ts(),
    }
    return metrics


def release_performance_signal(item: dict[str, Any]) -> dict[str, Any]:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    metrics = normalize_release_metrics(metrics)
    views = metrics["views"]
    engagement = metrics["likes"] + metrics["comments"] + metrics["shares"] + metrics["favorites"]
    engagement_rate = round(engagement / views * 100, 2) if views else 0.0
    score = (
        views
        + metrics["likes"] * 20
        + metrics["comments"] * 55
        + metrics["shares"] * 80
        + metrics["favorites"] * 30
        + metrics["completion_rate"] * 120
    )
    return {
        "release_id": item.get("id"),
        "platform": item.get("platform", ""),
        "url": item.get("url", ""),
        "title": item.get("title", ""),
        "note": item.get("note", ""),
        "metrics": metrics,
        "engagement": engagement,
        "engagement_rate": engagement_rate,
        "performance_score": int(round(score)),
        "has_metrics": any(metrics.get(key, 0) for key in ("views", "likes", "comments", "shares", "favorites", "completion_rate")),
    }


def update_release_metrics(project_id: int, release_id: int, raw_metrics: dict[str, Any]) -> dict[str, Any]:
    links = storage.get_release_links(project_id)
    for item in links:
        if int(item.get("id", 0) or 0) == int(release_id):
            item["metrics"] = normalize_release_metrics(raw_metrics)
            storage.save_release_links(project_id, links)
            return item
    raise ValueError("release not found")


def _history_keyword_tokens(text: str) -> list[str]:
    stopwords = {
        "这个",
        "一个",
        "为什么",
        "怎么",
        "不是",
        "可以",
        "没有",
        "视频",
        "内容",
        "主题",
        "标题",
        "发布",
        "时候",
        "我们",
        "他们",
        "你们",
        "自己",
    }
    tokens = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z0-9][A-Za-z0-9_\-]{1,20}", clean_text(text))
    return [token for token in tokens if token not in stopwords and len(token) >= 2]


def _first_content_hook(content: str, mode: str) -> str:
    dialogue = [strip_dialogue_speaker(item) for item in parse_dialogue_lines(content, mode) if clean_text(item)]
    for line in dialogue[:8]:
        line = clean_text(line)
        if len(line) >= 8:
            return line[:90]
    for line in content.splitlines():
        line = clean_text(line).lstrip("#").strip()
        if len(line) >= 8:
            return line[:90]
    return ""


def _project_quality_issues(project_id: int) -> list[dict[str, Any]]:
    reports = [
        storage.get_report(project_id, "quality_gate") or {},
        {"sections": {"content": storage.read_json(storage.project_file(project_id, "content_audit.json"), {})}},
    ]
    issues: list[dict[str, Any]] = []
    for report in reports:
        sections = report.get("sections") if isinstance(report, dict) else {}
        if not isinstance(sections, dict):
            continue
        for section_name, section in sections.items():
            if not isinstance(section, dict):
                continue
            for issue in section.get("issues", []) or []:
                if isinstance(issue, dict):
                    issues.append({"section": section_name, **issue})
    return issues


def channel_history_report(project_id: int) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(str(project.get("template") or ""))
    template = storage.get_template(template_key) if template_key else {}
    mode = clean_text(str(project.get("template_mode") or template.get("mode") or "video"))
    projects = sorted(storage.projects_for_template(template_key), key=lambda item: int(item.get("id", 0) or 0), reverse=True)
    project_rows: list[dict[str, Any]] = []
    keyword_counter: Counter[str] = Counter()
    weakness_counter: Counter[str] = Counter()
    best_hooks: list[dict[str, Any]] = []

    for meta in projects[:40]:
        pid = int(meta.get("id", 0) or 0)
        content_path = storage.project_file(pid, "content.md")
        content = storage.read_text(content_path) if content_path.exists() else ""
        summary = storage.get_summary(pid)
        title = clean_text(str(summary.get("publish_title") or summary.get("video_title") or meta.get("topic_name") or ""))
        engagement = content_engagement_report(content, mode) if clean_text(content) else {}
        releases = storage.get_release_links(pid)
        release_signals = [release_performance_signal(item) for item in releases if isinstance(item, dict)]
        best_release = max(release_signals, key=lambda item: int(item.get("performance_score", 0) or 0), default=None)
        hook = _first_content_hook(content, mode)
        for token in _history_keyword_tokens(" ".join([title, hook, clean_text(str(summary.get("summary") or ""))])):
            keyword_counter[token] += 1
        for issue in _project_quality_issues(pid):
            key = clean_text(str(issue.get("where") or issue.get("issue") or ""))
            if key:
                weakness_counter[key[:36]] += 1
        row = {
            "project_id": pid,
            "topic": meta.get("topic_name", ""),
            "title": title,
            "hook": hook,
            "status": meta.get("last_job_status", ""),
            "engagement": {
                "overall_score": engagement.get("overall_score", 0),
                "opening_score": engagement.get("opening_score", 0),
                "retention_score": engagement.get("retention_score", 0),
                "interaction_score": engagement.get("interaction_score", 0),
            },
            "release_count": len(release_signals),
            "best_release": best_release,
            "performance_score": int((best_release or {}).get("performance_score", 0) or 0),
        }
        project_rows.append(row)
        if hook:
            best_hooks.append(row)

    best_hooks = sorted(
        best_hooks,
        key=lambda item: (
            int(item.get("performance_score", 0) or 0),
            float(item.get("engagement", {}).get("opening_score", 0) or 0),
            int(item.get("project_id", 0) or 0),
        ),
        reverse=True,
    )
    top_projects = sorted(
        project_rows,
        key=lambda item: (
            int(item.get("performance_score", 0) or 0),
            float(item.get("engagement", {}).get("overall_score", 0) or 0),
            int(item.get("project_id", 0) or 0),
        ),
        reverse=True,
    )[:8]
    metric_projects = [row for row in project_rows if (row.get("best_release") or {}).get("has_metrics")]

    recommendations: list[str] = []
    if best_hooks:
        recommendations.append(f"开头继续走“{best_hooks[0].get('hook', '')[:32]}”这类具体痛点/反差句，少用泛泛铺垫。")
    if keyword_counter:
        hot = "、".join(token for token, _ in keyword_counter.most_common(5))
        recommendations.append(f"频道近期高频素材词：{hot}，新选题要么深化其中一个，要么主动避开重复。")
    if weakness_counter:
        weak = weakness_counter.most_common(1)[0][0]
        recommendations.append(f"历史反复出现的问题是“{weak}”，下一条生成后优先检查这一项。")
    if not metric_projects:
        recommendations.append("还没有投放表现数据，发布后回填播放/互动/完播率，频道学习才会更准。")
    else:
        recommendations.append("已有投放数据，下一轮选题会优先参考表现更好的标题、开头和互动方式。")

    report = {
        "generated_at": storage.now_ts(),
        "project_id": project_id,
        "template_key": template_key,
        "channel_name": template.get("name") or template_key,
        "history_count": len(project_rows),
        "with_release_metrics_count": len(metric_projects),
        "top_keywords": [{"keyword": key, "count": count} for key, count in keyword_counter.most_common(12)],
        "common_weaknesses": [{"issue": key, "count": count} for key, count in weakness_counter.most_common(8)],
        "best_hooks": [
            {
                "project_id": item.get("project_id"),
                "topic": item.get("topic"),
                "hook": item.get("hook"),
                "opening_score": item.get("engagement", {}).get("opening_score"),
                "performance_score": item.get("performance_score"),
            }
            for item in best_hooks[:8]
        ],
        "top_projects": top_projects,
        "recommendations": recommendations,
    }
    return report


def normalize_scene_image_filename(target: str) -> str:
    name = Path(str(target or "")).name
    matches = re.findall(r"(\d+)", name)
    index = int(matches[0]) if matches else 1
    index = max(1, min(index, 999))
    return f"s_{index:02d}.png"


def normalize_cover_target(target: str) -> dict[str, Any]:
    key = Path(str(target or "")).stem.lower().replace("-", "_")
    if key in COVER_IMAGE_TARGETS:
        return COVER_IMAGE_TARGETS[key]
    raise ValueError("未知封面类型，请选择 landscape、story 或 portrait。")


def _image_prompt_controls_path(project_id: int) -> Path:
    return storage.project_file(project_id, "image_prompt_controls.json")


def normalize_image_abstraction_level(level: str) -> str:
    key = clean_text(level).lower()
    if key in {"literal", "balanced", "conceptual"}:
        return key
    return DEFAULT_IMAGE_ABSTRACTION_LEVEL


def load_image_prompt_controls(project_id: int) -> dict[str, Any]:
    raw = storage.read_json(_image_prompt_controls_path(project_id), {})
    if not isinstance(raw, dict):
        raw = {}
    scenes = raw.get("scenes")
    covers = raw.get("covers")
    return {
        "scenes": scenes if isinstance(scenes, dict) else {},
        "covers": covers if isinstance(covers, dict) else {},
        "updated_at": raw.get("updated_at"),
    }


def save_image_prompt_control(
    project_id: int,
    kind: str,
    target: str,
    *,
    anchor_key: str = "",
    abstraction_level: str = DEFAULT_IMAGE_ABSTRACTION_LEVEL,
) -> dict[str, Any]:
    controls = load_image_prompt_controls(project_id)
    normalized_kind = clean_text(kind).lower()
    normalized_level = normalize_image_abstraction_level(abstraction_level)
    normalized_anchor = clean_text(anchor_key)
    if normalized_kind == "scene":
        bucket = controls["scenes"]
        control_key = normalize_scene_image_filename(target)
    elif normalized_kind == "cover":
        bucket = controls["covers"]
        control_key = normalize_cover_target(target)["kind"]
    else:
        raise ValueError("未知图片类型，请选择 scene 或 cover。")
    bucket[control_key] = {
        "anchor_key": normalized_anchor,
        "abstraction_level": normalized_level,
    }
    controls["updated_at"] = storage.now_ts()
    storage.write_json(_image_prompt_controls_path(project_id), controls)
    return dict(bucket[control_key])


def image_anchor_options(content: str, mode: str, kind: str) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen_texts: set[str] = set()

    def append_option(key: str, label: str, text: str) -> None:
        cleaned = clean_text(text)
        if not cleaned or cleaned in seen_texts:
            return
        seen_texts.add(cleaned)
        options.append(
            {
                "key": key,
                "label": label,
                "text": cleaned,
                "preview": summarize_scene_text(cleaned, 60),
            }
        )

    if kind == "cover":
        for field, key, label in (
            ("钩子", "meta:hook", "钩子"),
            ("核心观点", "meta:core", "核心观点"),
            ("反常识点", "meta:anti", "反常识点"),
            ("主体", "meta:subject", "主体"),
            ("核心知识点", "meta:knowledge", "核心知识点"),
        ):
            append_option(key, label, extract_bullet_field(content, field))

    dialogue_lines = [strip_dialogue_speaker(item) for item in parse_dialogue_lines(content, mode) if clean_text(item)]
    limit = 24 if kind == "scene" else 12
    for index, line in enumerate(dialogue_lines[:limit], start=1):
        append_option(f"dialogue:{index - 1}", f"口播 {index}", line)

    if kind == "scene" and not options:
        for field, key, label in (
            ("钩子", "meta:hook", "钩子"),
            ("核心观点", "meta:core", "核心观点"),
            ("反常识点", "meta:anti", "反常识点"),
        ):
            append_option(key, label, extract_bullet_field(content, field))
    return options


def recommended_image_anchor_key(project_id: int, content: str, mode: str, kind: str, target: str) -> str:
    options = image_anchor_options(content, mode, kind)
    if kind == "scene":
        filename = normalize_scene_image_filename(target)
        matches = re.findall(r"(\d+)", filename)
        scene_index = int(matches[0]) if matches else 1
        scene_count = len(parse_scene_prompts(content, mode)) or int(storage.scene_status(project_id).get("expected_count", 0) or 0) or 1
        selected_indexes = select_dialogue_scene_anchor_indexes(content, mode, scene_count)
        if selected_indexes and 0 < scene_index <= len(selected_indexes):
            return f"dialogue:{selected_indexes[scene_index - 1]}"
    else:
        for preferred in ("meta:hook", "dialogue:0", "meta:core", "meta:subject"):
            if any(item.get("key") == preferred for item in options):
                return preferred
    return str(options[0].get("key") or "") if options else ""


def resolve_image_anchor_text(options: list[dict[str, str]], anchor_key: str) -> str:
    normalized_key = clean_text(anchor_key)
    for item in options:
        if clean_text(str(item.get("key") or "")) == normalized_key:
            return clean_text(str(item.get("text") or ""))
    return ""


def image_abstraction_clause(kind: str, level: str) -> str:
    normalized_level = normalize_image_abstraction_level(level)
    if kind == "cover":
        clauses = {
            "literal": "封面构图尽量贴着这个锚点里的真实人物、动作、空间和关键物件，不额外堆无关隐喻。",
            "balanced": "封面以真实人物、动作和情绪关系为主，可用少量环境线索增强冲突，但不要盖住主题。",
            "conceptual": "封面允许适度抽象和象征化处理，把情绪压成更强的单帧记忆点，但仍要让人一眼看懂本期主题。",
        }
        return clauses.get(normalized_level, clauses[DEFAULT_IMAGE_ABSTRACTION_LEVEL])
    clauses = {
        "literal": "构图尽量贴着这句口播里的真实人物、动作、空间和物件，不要额外引入无关隐喻或概念装饰。",
        "balanced": "构图以真实人物和动作关系为主，可用少量环境符号强化情绪，但不要盖过本期主题。",
        "conceptual": "允许适度抽象和象征化处理，把情绪和关系压成更强的单帧感，但仍要让人一眼看出和这句口播相关。",
    }
    return clauses.get(normalized_level, clauses[DEFAULT_IMAGE_ABSTRACTION_LEVEL])


def rewrite_image_prompt_with_controls(prompt: str, kind: str, anchor_text: str, abstraction_level: str) -> str:
    clauses = [clean_text(item) for item in split_prompt_clauses(normalize_image_prompt(prompt)) if clean_text(item)]
    filtered: list[str] = []
    for clause in clauses:
        if clause.startswith(("这张图必须对应这句口播", "这张图优先对应这句口播", "封面优先对应开头这句口播", "封面优先对应这个主题锚点")):
            continue
        if clause.startswith(("构图尽量贴着这句口播", "构图以真实人物和动作关系为主", "允许适度抽象和象征化处理", "封面构图尽量贴着这个锚点里的真实人物", "封面以真实人物、动作和情绪关系为主")):
            continue
        filtered.append(clause)
    normalized_anchor = clean_text(anchor_text)
    if normalized_anchor:
        anchor_focus = summarize_scene_text(normalized_anchor, 64 if kind == "scene" else 56)
        if kind == "cover":
            filtered.insert(0, f"封面先抓住这个主题钩子：{anchor_focus}")
        else:
            filtered.insert(0, f"这张图先抓住这个瞬间：{anchor_focus}")
    filtered.append(image_abstraction_clause(kind, abstraction_level))
    return "，".join(dedupe_clauses([item for item in filtered if clean_text(item)]))


def image_prompt(project_id: int, kind: str, target: str, anchor_key: str = "", abstraction_level: str = "") -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    content = storage.get_content(project_id)
    mode = clean_text(project.get("template_mode") or template.get("mode") or "video")
    normalized_kind = clean_text(kind).lower()
    controls = load_image_prompt_controls(project_id)
    options = image_anchor_options(content, mode, normalized_kind)
    if normalized_kind == "scene":
        filename = normalize_scene_image_filename(target)
        prompt_path = storage.project_file(project_id, f"scenes/{filename}").with_suffix(".md")
        matches = re.findall(r"(\d+)", filename)
        scene_index = int(matches[0]) if matches else 1
        spec_prompts = video_spec_scene_prompts(project_id)
        prompt = spec_prompts[scene_index - 1] if 0 < scene_index <= len(spec_prompts) else ""
        if not prompt:
            prompt = str(scene_prompt(project_id, filename).get("prompt") or "").strip()
        if not prompt:
            prompt = storage.read_text(prompt_path).strip()
        control = controls.get("scenes", {}).get(filename, {}) if isinstance(controls.get("scenes"), dict) else {}
        current_anchor_key = clean_text(anchor_key) or clean_text(str(control.get("anchor_key") or "")) or recommended_image_anchor_key(project_id, content, mode, "scene", filename)
        current_level = normalize_image_abstraction_level(abstraction_level or str(control.get("abstraction_level") or DEFAULT_IMAGE_ABSTRACTION_LEVEL))
        final_prompt = rewrite_image_prompt_with_controls(prompt, "scene", resolve_image_anchor_text(options, current_anchor_key), current_level)
        return {
            "kind": "scene",
            "target": filename,
            "prompt": final_prompt,
            "base_prompt": prompt,
            "anchor_key": current_anchor_key,
            "recommended_anchor_key": recommended_image_anchor_key(project_id, content, mode, "scene", filename),
            "anchor_options": options,
            "abstraction_level": current_level,
            "abstraction_options": list(IMAGE_ABSTRACTION_OPTIONS),
        }
    if normalized_kind == "cover":
        cover = normalize_cover_target(target)
        output_path = storage.project_file(project_id, f"covers/{cover['filename']}")
        spec_prompt = video_spec_cover_prompt(project_id, str(cover["kind"]))
        prompt = optimize_visual_generation_prompt(
            spec_prompt or build_content_cover_prompt(project, template, content, str(cover["kind"])),
            template,
            "cover",
        ).strip()
        if not prompt:
            prompt = storage.read_text(output_path.with_suffix(".md")).strip()
        control = controls.get("covers", {}).get(cover["kind"], {}) if isinstance(controls.get("covers"), dict) else {}
        current_anchor_key = clean_text(anchor_key) or clean_text(str(control.get("anchor_key") or "")) or recommended_image_anchor_key(project_id, content, mode, "cover", cover["kind"])
        current_level = normalize_image_abstraction_level(abstraction_level or str(control.get("abstraction_level") or DEFAULT_IMAGE_ABSTRACTION_LEVEL))
        final_prompt = rewrite_image_prompt_with_controls(prompt, "cover", resolve_image_anchor_text(options, current_anchor_key), current_level)
        return {
            "kind": "cover",
            "target": cover["kind"],
            "label": cover["label"],
            "prompt": final_prompt,
            "base_prompt": prompt,
            "anchor_key": current_anchor_key,
            "recommended_anchor_key": recommended_image_anchor_key(project_id, content, mode, "cover", cover["kind"]),
            "anchor_options": options,
            "abstraction_level": current_level,
            "abstraction_options": list(IMAGE_ABSTRACTION_OPTIONS),
        }
    raise ValueError("未知图片类型，请选择 scene 或 cover。")


def _replace_generated_image(tmp_path: Path, output_path: Path) -> None:
    storage.ensure_dir(output_path.parent)
    tmp_path.replace(output_path)
    for suffix in (".md", ".audit.json"):
        tmp_sidecar = tmp_path.with_suffix(suffix)
        if tmp_sidecar.exists():
            tmp_sidecar.replace(output_path.with_suffix(suffix))


def _cleanup_generated_tmp(tmp_path: Path) -> None:
    for path in (tmp_path, tmp_path.with_suffix(".md"), tmp_path.with_suffix(".audit.json")):
        path.unlink(missing_ok=True)


def generate_configured_image_safely(
    prompt: str,
    output_path: Path,
    size: str,
    purpose: str,
    env: dict[str, str],
    log: Callable[[str], None] | None,
    template: dict[str, Any] | None = None,
) -> Path:
    provider_key = resolve_image_provider_queue(env)[0]["key"]
    if provider_key == "chatgpt_handoff":
        return generate_configured_image(prompt, output_path, size, purpose, env, log, template)
    tmp_path = output_path.with_name(f".{output_path.stem}.gen-{storage.now_ms()}.png")
    try:
        result = generate_configured_image(prompt, tmp_path, size, purpose, env, log, template)
        source_path = result if isinstance(result, Path) and result.exists() else tmp_path
        if source_path != tmp_path:
            source_path.replace(tmp_path)
        _replace_generated_image(tmp_path, output_path)
        return output_path
    except Exception:
        _cleanup_generated_tmp(tmp_path)
        raise


def _update_scene_prompt_record(project_id: int, filename: str, source_prompt: str, final_prompt: str, audit: dict[str, Any]) -> None:
    records_path = storage.project_file(project_id, "scenes/scene_prompts.json")
    records = storage.read_json(records_path, [])
    if not isinstance(records, list):
        records = []
    index_matches = re.findall(r"(\d+)", filename)
    index = int(index_matches[0]) if index_matches else len(records) + 1
    updated = False
    for record in records:
        if isinstance(record, dict) and record.get("filename") == filename:
            record.update(
                {
                    "label": record.get("label") or f"场景 {index}",
                    "prompt": final_prompt,
                    "source_prompt": normalize_image_prompt(source_prompt),
                    "audit": {
                        "ok": audit.get("ok", True),
                        "severity": audit.get("severity", "ok"),
                        "attempt": audit.get("attempt", 1),
                        "reasons": audit.get("reasons", []),
                    },
                }
            )
            updated = True
            break
    if not updated:
        records.append(
            {
                "filename": filename,
                "label": f"场景 {index}",
                "prompt": final_prompt,
                "source_prompt": normalize_image_prompt(source_prompt),
                "audit": {
                    "ok": audit.get("ok", True),
                    "severity": audit.get("severity", "ok"),
                    "attempt": audit.get("attempt", 1),
                    "reasons": audit.get("reasons", []),
                },
            }
        )

    def record_index(record: Any) -> int:
        if not isinstance(record, dict):
            return 999
        matches = re.findall(r"(\d+)", str(record.get("filename") or ""))
        return int(matches[0]) if matches else 999

    storage.write_json(records_path, sorted(records, key=record_index))


def regenerate_project_image(
    project_id: int,
    kind: str,
    target: str,
    prompt: str,
    anchor_key: str = "",
    abstraction_level: str = DEFAULT_IMAGE_ABSTRACTION_LEVEL,
) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    env = runtime_env()
    normalized_kind = clean_text(kind).lower()
    saved_control = save_image_prompt_control(
        project_id,
        normalized_kind,
        target,
        anchor_key=anchor_key,
        abstraction_level=abstraction_level,
    )
    source_prompt = normalize_image_prompt(prompt)
    if not source_prompt:
        source_prompt = str(
            image_prompt(
                project_id,
                normalized_kind,
                target,
                anchor_key=anchor_key,
                abstraction_level=abstraction_level,
            ).get("prompt")
            or ""
        )
    if not source_prompt:
        raise ValueError("请先填写重绘提示词。")

    if normalized_kind == "scene":
        filename = normalize_scene_image_filename(target)
        output_path = storage.project_file(project_id, f"scenes/{filename}")
        provider = resolve_image_provider_queue(env)[0]
        if provider["key"] == "chatgpt_handoff":
            handoff = prepare_chatgpt_handoff_request(source_prompt, output_path, SCENE_IMAGE_SIZE, "scene", env, template)
            _update_scene_prompt_record(
                project_id,
                filename,
                source_prompt,
                str(handoff.get("prompt") or source_prompt),
                {"ok": False, "severity": "pending", "attempt": 0, "reasons": ["chatgpt_handoff_pending"]},
            )
            review = mark_image_review_dirty(project_id, f"{filename} 已创建 ChatGPT 接力任务，等待保存图片后确认")
            return {
                "ok": True,
                "needs_handoff": True,
                "kind": "scene",
                "target": filename,
                "path": str(output_path),
                "prompt": handoff.get("prompt") or source_prompt,
                "handoff": handoff,
                "control": saved_control,
                "review": review,
            }
        tmp_path = output_path.with_name(f".{output_path.stem}.regen-{storage.now_ms()}.png")
        try:
            generate_configured_image(source_prompt, tmp_path, SCENE_IMAGE_SIZE, "scene", env, None, template)
            _replace_generated_image(tmp_path, output_path)
        except Exception:
            _cleanup_generated_tmp(tmp_path)
            raise
        final_prompt = read_generated_prompt(output_path, source_prompt)
        audit = read_image_audit(output_path)
        _update_scene_prompt_record(project_id, filename, source_prompt, final_prompt, audit)
        review = mark_image_review_dirty(project_id, f"{filename} 已重绘，等待重新确认")
        return {
            "ok": True,
            "kind": "scene",
            "target": filename,
            "path": str(output_path),
            "prompt": final_prompt,
            "control": saved_control,
            "audit": audit,
            "review": review,
        }

    if normalized_kind == "cover":
        cover = normalize_cover_target(target)
        output_path = storage.project_file(project_id, f"covers/{cover['filename']}")
        provider = resolve_image_provider_queue(env)[0]
        if provider["key"] == "chatgpt_handoff":
            handoff = prepare_chatgpt_handoff_request(source_prompt, output_path, str(cover["size"]), "cover", env, template)
            review = mark_image_review_dirty(project_id, f"{cover['label']} 已创建 ChatGPT 接力任务，等待保存图片后确认")
            return {
                "ok": True,
                "needs_handoff": True,
                "kind": "cover",
                "target": cover["kind"],
                "label": cover["label"],
                "path": str(output_path),
                "prompt": handoff.get("prompt") or source_prompt,
                "handoff": handoff,
                "control": saved_control,
                "review": review,
            }
        tmp_path = output_path.with_name(f".{output_path.stem}.regen-{storage.now_ms()}.png")
        try:
            generate_configured_image(source_prompt, tmp_path, str(cover["size"]), "cover", env, None, template)
            _replace_generated_image(tmp_path, output_path)
        except Exception:
            _cleanup_generated_tmp(tmp_path)
            raise
        final_prompt = read_generated_prompt(output_path, source_prompt)
        audit = read_image_audit(output_path)
        review = mark_image_review_dirty(project_id, f"{cover['label']} 已重绘，等待重新确认")
        return {
            "ok": True,
            "kind": "cover",
            "target": cover["kind"],
            "label": cover["label"],
            "path": str(output_path),
            "prompt": final_prompt,
            "control": saved_control,
            "audit": audit,
            "review": review,
        }

    raise ValueError("未知图片类型，请选择 scene 或 cover。")


def write_svg_card(path: Path, title: str, subtitle: str, accent: str, ratio: tuple[int, int]) -> None:
    width, height = ratio
    title_lines = textwrap.wrap(title, width=16)[:3]
    subtitle_lines = textwrap.wrap(subtitle, width=22)[:5]
    title_svg = "".join(
        f'<tspan x="56" dy="{0 if idx == 0 else 44}">{html.escape(line)}</tspan>'
        for idx, line in enumerate(title_lines)
    )
    subtitle_svg = "".join(
        f'<tspan x="56" dy="{0 if idx == 0 else 28}">{html.escape(line)}</tspan>'
        for idx, line in enumerate(subtitle_lines)
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs>
  <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
    <stop offset="0%" stop-color="#111827" />
    <stop offset="100%" stop-color="{accent}" />
  </linearGradient>
</defs>
<rect width="{width}" height="{height}" rx="28" fill="url(#bg)" />
<rect x="36" y="36" width="{width - 72}" height="{height - 72}" rx="24" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.18)" />
<text x="56" y="108" font-size="34" font-weight="700" fill="#ffffff" font-family="Microsoft YaHei, Arial">{title_svg}</text>
<text x="56" y="{min(height - 120, 260)}" font-size="22" fill="#dbeafe" font-family="Microsoft YaHei, Arial">{subtitle_svg}</text>
<text x="{width - 56}" y="{height - 38}" text-anchor="end" font-size="16" fill="#e5e7eb" font-family="Microsoft YaHei, Arial">Short Video Studio</text>
</svg>
"""
    storage.write_text(path, svg)


def write_wave_file(path: Path, duration: float = 2.2, freq: float = 440.0) -> None:
    sample_rate = 22050
    amplitude = 10000
    total_frames = int(sample_rate * duration)
    storage.ensure_dir(path.parent)
    with wave.open(str(path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for index in range(total_frames):
            value = int(amplitude * math.sin(2.0 * math.pi * freq * index / sample_rate))
            wav_file.writeframes(struct.pack("<h", value))


def write_preview_html(project_id: int, title: str, scenes: list[dict[str, Any]]) -> None:
    slides = "\n".join(
        f"""
        <section class="slide">
          <img src="../scenes/{scene['filename']}" alt="{html.escape(scene['label'])}" />
          <div class="caption">
            <h2>{html.escape(scene['label'])}</h2>
            <p>{html.escape(scene.get('prompt') or '')}</p>
          </div>
        </section>
        """
        for scene in scenes
    )
    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)} · 成片预演</title>
  <style>
    body {{
      margin: 0;
      background: #0f172a;
      color: #fff;
      font-family: "Microsoft YaHei", Arial, sans-serif;
    }}
    .deck {{
      display: grid;
      gap: 18px;
      padding: 24px;
      max-width: 1100px;
      margin: 0 auto;
    }}
    .slide {{
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 20px;
      overflow: hidden;
    }}
    img {{
      display: block;
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      background: #111827;
    }}
    .caption {{
      padding: 16px 20px 22px;
    }}
    h1 {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px 24px 0;
      font-size: 28px;
    }}
    h2 {{
      margin: 0 0 10px;
      font-size: 20px;
    }}
    p {{
      margin: 0;
      color: #cbd5e1;
      line-height: 1.6;
    }}
  </style>
</head>
<body>
  <h1>{html.escape(title)} · 成片预演</h1>
  <main class="deck">{slides}</main>
</body>
</html>
"""
    storage.write_text(storage.project_file(project_id, "releases/final-preview.html"), html_doc)


class ContentRuntime:
    def __init__(self) -> None:
        self.tasks: dict[int, dict[str, Any]] = {}

    def status(self, project_id: int) -> dict[str, Any] | None:
        item = self.tasks.get(project_id)
        if item:
            return item["state"]
        path = storage.project_file(project_id, "content_generate.json")
        if path.exists():
            return storage.read_json(path, None)
        return None

    async def start(self, project: dict[str, Any], template: dict[str, Any], brief: str, tavily_topic: str) -> dict[str, Any]:
        project_id = project["id"]
        await self.cancel(project_id, silent=True)
        state = {
            "status": "running",
            "started_at": storage.now_ts(),
            "stage": "think",
            "stage_started_at": storage.now_ts(),
            "stages": [],
            "cancel_requested": False,
            "provider": "",
            "reference_count": 0,
        }
        self.tasks[project_id] = {"state": state}
        storage.write_json(storage.project_file(project_id, "content_generate.json"), state)
        task = asyncio.create_task(self._run(project, template, brief, tavily_topic))
        self.tasks[project_id]["task"] = task
        return state

    async def cancel(self, project_id: int, silent: bool = False) -> dict[str, Any]:
        item = self.tasks.get(project_id)
        if not item:
            return {"already_done": True}
        item["state"]["cancel_requested"] = True
        task = item.get("task")
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if not silent:
            state = item["state"]
            state["status"] = "cancelled"
            state["finished_at"] = storage.now_ts()
            storage.write_json(storage.project_file(project_id, "content_generate.json"), state)
        self.tasks.pop(project_id, None)
        meta = storage.get_project(project_id)
        meta["content_generating"] = False
        storage.write_project_meta(project_id, meta)
        return {"already_done": False}

    def _push_stage(self, project_id: int, stage: str) -> None:
        state = self.tasks[project_id]["state"]
        state["stage"] = stage
        state["stage_started_at"] = storage.now_ts()
        state["stages"].append({"stage": stage, "started_at": storage.now_ts()})
        storage.write_json(storage.project_file(project_id, "content_generate.json"), state)

    async def _run(self, project: dict[str, Any], template: dict[str, Any], brief: str, tavily_topic: str) -> None:
        project_id = project["id"]
        state = self.tasks[project_id]["state"]
        meta = storage.get_project(project_id)
        meta["content_generating"] = True
        storage.write_project_meta(project_id, meta)
        try:
            self._push_stage(project_id, "think")
            preliminary_strategy = content_strategy_report(project, template, brief, tavily_topic, [])
            storage.write_json(storage.project_file(project_id, "content_strategy.json"), preliminary_strategy)
            await asyncio.sleep(0.15)

            self._push_stage(project_id, "search")
            references: list[dict[str, Any]] = []
            provider = ""
            original_error = ""
            deepseek_error = ""
            context: dict[str, Any] = {}
            deepseek_enabled = bool(clean_text(runtime_env().get("DEEPSEEK_API_KEY", "")))
            state["generator_priority"] = "deepseek-template-first" if deepseek_enabled else "local-fallback"

            if deepseek_enabled:
                context = await asyncio.to_thread(build_reference_context, project, template, brief, tavily_topic)
                references = context.get("references", [])
                if not isinstance(references, list):
                    references = []
                state["reference_count"] = len(references)
                storage.write_json(storage.project_file(project_id, "content_generate.json"), state)

                self._push_stage(project_id, "write")
                try:
                    content = await asyncio.to_thread(render_deepseek_content, project, template, brief, tavily_topic, context)
                    provider = "deepseek"
                except Exception as exc:
                    deepseek_error = str(exc)
                    state["deepseek_error"] = deepseek_error
                    storage.write_json(storage.project_file(project_id, "content_generate.json"), state)

                    self._push_stage(project_id, "original_fallback")
                    try:
                        original_result = await asyncio.to_thread(render_original_content, project, template, brief, tavily_topic)
                        references = original_result.get("references", [])
                        if not isinstance(references, list):
                            references = []
                        state["reference_count"] = len(references)
                        state["original_stages"] = original_result.get("stages", [])
                        storage.write_json(storage.project_file(project_id, "content_generate.json"), state)
                        content = str(original_result["content"])
                        provider = str(original_result.get("provider") or "deepseek-via-original")
                    except Exception as original_exc:
                        original_error = str(original_exc)
                        state["original_error"] = original_error
                        storage.write_json(storage.project_file(project_id, "content_generate.json"), state)
                        content = await asyncio.to_thread(render_fallback_content, project, template, brief, tavily_topic, context)
                        provider = "fallback"
            else:
                state["fallback_reason"] = "DeepSeek API Key 未配置，使用本地兜底生成。"
                storage.write_json(storage.project_file(project_id, "content_generate.json"), state)
                context = await asyncio.to_thread(build_reference_context, project, template, brief, tavily_topic)
                references = context.get("references", [])
                if not isinstance(references, list):
                    references = []
                state["reference_count"] = len(references)
                storage.write_json(storage.project_file(project_id, "content_generate.json"), state)

                self._push_stage(project_id, "write")
                content = await asyncio.to_thread(render_fallback_content, project, template, brief, tavily_topic, context)
                provider = "fallback"

            content = compact_content_meta(content)
            content = refresh_content_image_prompts(project, template, content)
            summary = summarize_content(content, template.get("mode", "video"))
            artifacts = build_content_artifacts(project, template, brief, tavily_topic, references, content)
            storage.save_content(project_id, content)
            storage.save_references(project_id, references)
            storage.save_summary(project_id, summary)
            storage.write_json(storage.project_file(project_id, "content_strategy.json"), artifacts["strategy"])
            storage.write_json(storage.project_file(project_id, "content_audit.json"), artifacts["audit"])
            with contextlib.suppress(Exception):
                save_video_spec(project_id, content)
            storage.save_report(project_id, "topic_score", artifacts["strategy"]["topic_score"])
            storage.save_report(project_id, "viral_doctor", artifacts["audit"]["viral_doctor"])
            storage.save_report(project_id, "title_cover_ab", artifacts["audit"]["title_cover_ab"])
            mark_image_review_dirty(project_id, "content.md 已更新，图片需要重新确认")
            state["provider"] = provider
            state["content_audit_score"] = artifacts["audit"]["score"]
            state["content_audit_verdict"] = artifacts["audit"]["verdict"]
            if deepseek_error:
                state["fallback_reason"] = deepseek_error
            if original_error:
                state["original_fallback_reason"] = original_error
            state["status"] = "succeeded"
            state["finished_at"] = storage.now_ts()
            storage.write_json(storage.project_file(project_id, "content_generate.json"), state)
        except asyncio.CancelledError:
            state["status"] = "cancelled"
            state["finished_at"] = storage.now_ts()
            storage.write_json(storage.project_file(project_id, "content_generate.json"), state)
            raise
        except Exception as exc:
            state["status"] = "failed"
            state["finished_at"] = storage.now_ts()
            state["error"] = str(exc)
            storage.write_json(storage.project_file(project_id, "content_generate.json"), state)
        finally:
            meta = storage.get_project(project_id)
            meta["content_generating"] = False
            storage.write_project_meta(project_id, meta)
            self.tasks.pop(project_id, None)


class JobRuntime:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}

    def latest(self, project_id: int) -> dict[str, Any] | None:
        job = storage.load_latest_job(project_id)
        if job and job.get("running") and job.get("id") not in self.tasks:
            recovered = dict(job)
            recovered["running"] = False
            recovered["finished_at"] = recovered.get("finished_at") or storage.now_ts()
            if recovered.get("status") == "running":
                recovered["status"] = "interrupted"
            log_text = str(recovered.get("log", "") or "").rstrip()
            suffix = "[job] 上一次任务在服务重启前中断，请重新开始生产。"
            recovered["log"] = f"{log_text}\n{suffix}".strip() if log_text else suffix
            storage.save_latest_job(project_id, recovered)
            return recovered
        return job

    async def start(self, project: dict[str, Any], steps: list[str], allow_incomplete_video: bool = False) -> dict[str, Any]:
        project_id = project["id"]
        latest = self.latest(project_id)
        if latest and latest.get("running"):
            raise RuntimeError("当前项目已有任务正在运行。")
        job_id = f"job-{project_id}-{storage.now_ms()}"
        snapshot = {
            "id": job_id,
            "project_id": project_id,
            "steps": steps,
            "status": "running",
            "running": True,
            "started_at": storage.now_ts(),
            "finished_at": None,
            "return_code": None,
            "allow_incomplete_video": allow_incomplete_video,
            "log": "",
            "progress": [],
        }
        storage.save_latest_job(project_id, snapshot)
        task = asyncio.create_task(self._run(project, steps, job_id, allow_incomplete_video))
        self.tasks[job_id] = {"task": task, "project_id": project_id}
        return snapshot

    async def cancel(self, job_id: str) -> dict[str, Any]:
        item = self.tasks.get(job_id)
        if not item:
            return {"already_done": True}
        task = item["task"]
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return {"already_done": False}

    async def _run(self, project: dict[str, Any], steps: list[str], job_id: str, allow_incomplete_video: bool) -> None:
        project_id = project["id"]
        log_lines: list[str] = []
        progress: list[dict[str, Any]] = []
        snapshot = storage.load_latest_job(project_id) or {}
        try:
            summary = storage.get_summary(project_id)
            content = storage.get_content(project_id)
            title = summary.get("publish_title") or summary.get("video_title") or project["topic_name"]
            mode = project.get("template_mode", "video")
            scene_lines = current_scene_prompts(project_id, content, mode, project["topic_name"])

            for step in steps:
                progress.append({"key": step, "status": "running", "started_at": storage.now_ts()})
                self._flush(project_id, snapshot, log_lines, progress, step)
                scene_lines = await self._handle_step(project_id, project, title, step, content, scene_lines, log_lines)
                progress[-1]["status"] = "success"
                progress[-1]["finished_at"] = storage.now_ts()
                self._flush(project_id, snapshot, log_lines, progress, step)

            snapshot["status"] = "succeeded"
            snapshot["running"] = False
            snapshot["return_code"] = 0
            snapshot["finished_at"] = storage.now_ts()
            snapshot["log"] = "\n".join(log_lines)
            snapshot["progress"] = progress
            storage.save_latest_job(project_id, snapshot)
        except asyncio.CancelledError:
            snapshot["status"] = "cancelled"
            snapshot["running"] = False
            snapshot["return_code"] = -1
            snapshot["finished_at"] = storage.now_ts()
            log_lines.append("[job] 用户已请求停止，当前任务已取消。")
            snapshot["log"] = "\n".join(log_lines)
            snapshot["progress"] = progress
            storage.save_latest_job(project_id, snapshot)
            raise
        except Exception as exc:
            snapshot["status"] = "failed"
            snapshot["running"] = False
            snapshot["return_code"] = 1
            snapshot["finished_at"] = storage.now_ts()
            log_lines.append(f"[job] 任务失败：{exc}")
            snapshot["log"] = "\n".join(log_lines)
            snapshot["progress"] = progress
            storage.save_latest_job(project_id, snapshot)
        finally:
            self.tasks.pop(job_id, None)

    def _flush(
        self,
        project_id: int,
        snapshot: dict[str, Any],
        log_lines: list[str],
        progress: list[dict[str, Any]],
        current_step: str,
    ) -> None:
        snapshot["status"] = "running"
        snapshot["running"] = True
        snapshot["current_step"] = current_step
        snapshot["log"] = "\n".join(log_lines)
        snapshot["progress"] = progress
        storage.save_latest_job(project_id, snapshot)

    async def _handle_real_step(
        self,
        project_id: int,
        project: dict[str, Any],
        title: str,
        step: str,
        content: str,
        scene_lines: list[str],
        log_lines: list[str],
    ) -> tuple[bool, list[str]]:
        mode = project.get("template_mode", "video")
        template_key = clean_text(project.get("template", ""))
        template = storage.get_template(template_key) if template_key else {"name": "", "brand_name": ""}
        dialogue_lines = parse_dialogue_lines(content, mode)

        def add(line: str) -> None:
            log_lines.append(line)
            snapshot = storage.load_latest_job(project_id) or {}
            snapshot["log"] = "\n".join(log_lines)
            storage.save_latest_job(project_id, snapshot)

        if step == "audio":
            env = runtime_env()
            output_path = storage.project_file(project_id, "audio/podcast.mp3")
            tts_text = content_tts_text(content, mode, dialogue_lines, scene_lines, project["topic_name"])
            add("[audio] 正在调用豆包播客生成真实音频 podcast.mp3")
            if not env.get("VOLC_TTS_APP_KEY") or not env.get("VOLC_TTS_ACCESS_KEY"):
                raise RuntimeError("VOLC_TTS_APP_KEY / VOLC_TTS_ACCESS_KEY 未配置，无法生成真实配音。")
            result = await asyncio.to_thread(
                run_original_bridge,
                "tts",
                {
                    "text": tts_text,
                    "output_path": str(output_path),
                    "dialogue_lines": bridge_dialogue_payload(dialogue_lines),
                },
                env,
            )
            storage.write_text(
                storage.project_file(project_id, "audio/podcast.txt"),
                (plain_dialogue_text(dialogue_lines) or tts_text or clean_text(content) or project["topic_name"]).strip() + "\n",
            )
            size_mb = float(result.get("size", 0)) / 1048576.0
            add(f"[audio] 豆包播客音频已生成 -> podcast.mp3 ({size_mb:.1f} MB)")
            return True, scene_lines

        if step == "subtitles":
            env = runtime_env()
            audio_path = storage.project_file(project_id, "audio/podcast.mp3")
            srt_path = storage.project_file(project_id, "audio/subtitles.srt")
            timeline_path = storage.project_file(project_id, "audio/scene_timeline.json")
            if not audio_path.exists():
                raise RuntimeError("podcast.mp3 不存在，请先完成配音步骤。")
            scene_lines = current_scene_prompts(project_id, content, mode, project["topic_name"], prefer_timeline=False)
            dialogue_texts = [item["text"] for item in bridge_dialogue_payload(dialogue_lines)] or scene_lines
            add("[subtitles] 正在调用火山 ASR 生成真实字幕")
            if not env.get("VOLC_ASR_APP_KEY") and env.get("VOLC_TTS_APP_KEY"):
                add("[subtitles] 当前未单独填写 ASR 密钥，先回退复用 TTS 密钥识别")
            result = await asyncio.to_thread(
                run_original_bridge,
                "asr",
                {
                    "audio_path": str(audio_path),
                    "srt_output": str(srt_path),
                    "dialogue_lines": dialogue_texts,
                },
                env,
            )
            utterances = result.get("utterances", []) if isinstance(result.get("utterances", []), list) else []
            if not utterances:
                utterances = load_srt_entries(srt_path)
            if not utterances:
                raise RuntimeError("原版 ASR 没有返回可用字幕。")
            audio_duration_ms = max(1000, round(probe_audio_duration(audio_path) * 1000))
            scene_count_info = resolve_project_scene_count(project, content, mode, candidate_count=len(scene_lines), audio_ms=audio_duration_ms)
            desired_scene_count = int(scene_count_info.get("final", len(scene_lines)) or len(scene_lines) or 1)
            scene_lines = normalize_scene_prompt_count(scene_lines, desired_scene_count, project["topic_name"], mode)
            coverage = subtitle_coverage_ratio(utterances, audio_duration_ms)
            add(f"[subtitles] 原版 ASR 已结合脚本上下文识别，当前覆盖 {coverage * 100:.0f}%")
            try:
                timeline_result = await asyncio.to_thread(
                    run_original_bridge,
                    "scene_timeline",
                    {
                        "audio_path": str(audio_path),
                        "srt_path": str(srt_path),
                        "output_path": str(timeline_path),
                        "scene_prompts": scene_lines,
                        "dialogue_lines": dialogue_texts,
                        "cover_duration": TIMELINE_COVER_MS / 1000.0,
                        "outro_duration": TIMELINE_OUTRO_MS / 1000.0,
                        "align_mode": "full",
                        "force": True,
                    },
                    env,
                    600,
                )
                timeline = timeline_result.get("timeline", {}) if isinstance(timeline_result, dict) else {}
                if not isinstance(timeline, dict) or not timeline.get("scenes"):
                    timeline = storage.read_json(timeline_path, {})
                add("[scene_timeline] 已切回原版 scene_timeline 链路")
            except Exception as exc:
                add(f"[scene_timeline] 原版 scene_timeline 调用失败，回退本地时间轴：{exc}")
                timeline = build_scene_timeline_for_scene_count(utterances, scene_lines, desired_scene_count, audio_duration_ms)
                storage.write_text(
                    timeline_path,
                    json.dumps(timeline, ensure_ascii=False, indent=2),
                )
            timeline_scenes = timeline.get("scenes") if isinstance(timeline, dict) else []
            if not isinstance(timeline_scenes, list) or len(timeline_scenes) != desired_scene_count:
                reason = "固定张数" if scene_count_info.get("mode") == "fixed" else "自动张数"
                add(f"[scene_timeline] {reason}要求 {desired_scene_count} 张，正在重切时轴")
                timeline = build_scene_timeline_for_scene_count(utterances, scene_lines, desired_scene_count, audio_duration_ms)
                storage.write_text(
                    timeline_path,
                    json.dumps(timeline, ensure_ascii=False, indent=2),
                )
            if utterances:
                storage.write_text(storage.project_file(project_id, "audio/subtitles.txt"), utterances_to_plain_text(utterances) + "\n")
            aligned_lines = [clean_text(str(item.get("prompt", ""))) for item in timeline.get("scenes", []) if isinstance(item, dict)]
            scene_range = timeline.get("scene_count_range") or {}
            add(
                f"[scene_timeline] 使用对齐后的场景图列表：候选 {len(scene_lines)} 张 -> 最终 {len(aligned_lines)} 张"
            )
            if scene_range:
                add(
                    f"[scene_timeline] 音频时长命中的建议区间：{scene_range.get('min', len(aligned_lines))}-{scene_range.get('max', len(aligned_lines))} 张"
                )
            scene_plan = write_scene_plan(project_id, project, content, timeline, aligned_lines or scene_lines)
            write_srt_entries(srt_path, merge_subtitle_display_entries(utterances))
            sync_project_subtitle_files(project_id)
            add(f"[scene_timeline] 写出 audio/scene_timeline.json，共 {len(aligned_lines)} 段")
            add(f"[scene_plan] 写出 audio/scene_plan.json，共 {scene_plan.get('scene_count', len(aligned_lines))} 镜")
            summary = storage.get_summary(project_id)
            if summary:
                original_scene_count = int(summary.get("scene_count", 0) or 0)
                summary["scene_count_script"] = int(summary.get("scene_count_script", original_scene_count) or original_scene_count)
                summary["scene_count"] = len(aligned_lines)
                summary["scene_count_aligned"] = len(aligned_lines)
                storage.save_summary(project_id, summary)
            add(f"[subtitles] 已生成真实字幕 -> subtitles.srt（{len(utterances)} 条）")
            return True, aligned_lines or scene_lines

        if step in {"images", "images_missing"}:
            env = runtime_env()
            provider = resolve_image_provider_queue(env)[0]
            provider_desc = describe_image_provider_queue(env)
            if not scene_lines:
                scene_lines = current_scene_prompts(project_id, content, mode, project["topic_name"])
            missing_only = step == "images_missing"
            missing_indexes: set[int] = set()
            if missing_only:
                scene_status_payload = storage.scene_status(project_id)
                for item in scene_status_payload.get("missing_items", []):
                    if isinstance(item, dict):
                        try:
                            missing_indexes.add(int(item.get("index", 0) or 0))
                        except Exception:
                            continue
                if not missing_indexes:
                    add("[images] 没有缺失的场景图，跳过补图。")
                    return True, scene_lines
            scene_records = []
            if missing_only:
                existing_records = storage.read_json(storage.project_file(project_id, "scenes/scene_prompts.json"), [])
                scene_records = existing_records if isinstance(existing_records, list) else []
            scene_jobs = [
                (idx, prompt)
                for idx, prompt in enumerate(scene_lines, start=1)
                if not missing_only or idx in missing_indexes
            ]
            if not scene_jobs:
                add("[images] 缺失编号没有可用提示词，请先重建图片提示词或重新生成字幕时间轴。")
                return True, scene_lines
            add(f"[images] 正在调用 {provider['label']} 生成 {len(scene_jobs)} 张场景图")
            add(f"[images] {provider_desc}")
            if provider["key"] in {"apiyi", "third_party"}:
                add("[images] OpenAI 兼容文生图单张通常需要几十秒；已切换为稳态串行生成，逐张完成后再进入下一张")
            if provider["key"] == "chatgpt_handoff":
                add("[images] ChatGPT 接力模式：会逐张打开提示词并等待目标图片文件保存完成")
            if provider["key"] == "chatgpt_web_auto":
                add("[images] ChatGPT 网页自动化：会自动发送提示词、等待图片并保存到项目目录；首次使用需要在弹出浏览器中登录")
            if not missing_only:
                add("[images] 完整重生模式：新图会先生成到临时文件，成功后再替换旧图")
            else:
                add(f"[images] 续跑模式：只补缺失编号 {', '.join(f's_{idx:02d}' for idx in sorted(missing_indexes))}，保留已有图片")
            for idx, prompt in scene_jobs:
                filename = f"s_{idx:02d}.png"
                output_path = storage.project_file(project_id, f"scenes/{filename}")
                add(f"[images] 开始 {idx}/{len(scene_lines)} -> {filename}")
                await asyncio.to_thread(generate_configured_image_safely, prompt, output_path, SCENE_IMAGE_SIZE, "scene", env, add, template)
                final_prompt = read_generated_prompt(output_path, prompt)
                audit = read_image_audit(output_path)
                if audit.get("attempt", 1) > 1:
                    add(f"[images] {filename} 自检后重绘 {audit.get('attempt')} 次")
                if audit.get("severity") == "soft" and audit.get("reasons"):
                    add(f"[images] {filename} 自检提示：{', '.join(str(item) for item in audit.get('reasons', []))}")
                scene_record = {
                    "filename": filename,
                    "label": f"场景 {idx}",
                    "prompt": final_prompt,
                    "source_prompt": normalize_image_prompt(prompt),
                    "audit": {
                        "ok": audit.get("ok", True),
                        "severity": audit.get("severity", "ok"),
                        "attempt": audit.get("attempt", 1),
                        "reasons": audit.get("reasons", []),
                    },
                }
                if missing_only:
                    scene_records = [
                        item
                        for item in scene_records
                        if not (isinstance(item, dict) and item.get("filename") == filename)
                    ]
                scene_records.append(scene_record)
                add(f"[images] 进度 {idx}/{len(scene_lines)} -> {filename}")
            if missing_only:
                scene_records.sort(
                    key=lambda item: int(re.findall(r"(\d+)", str(item.get("filename", "")))[0])
                    if isinstance(item, dict) and re.findall(r"(\d+)", str(item.get("filename", "")))
                    else 999
                )
            storage.write_json(storage.project_file(project_id, "scenes/scene_prompts.json"), scene_records)
            if not missing_only:
                removed = storage.cleanup_extra_scene_outputs(project_id, len(scene_lines))
                if removed:
                    add(f"[images] 已清理 {removed} 个超出当前场景数量的旧文件")
            mark_image_review_dirty(project_id, "场景图已更新，等待人工确认")
            add("[images] 场景图已全部生成" if not missing_only else "[images] 缺失场景图已补齐")
            return True, scene_lines

        if step in {"covers", "covers_missing"}:
            env = runtime_env()
            provider = resolve_image_provider_queue(env)[0]
            provider_desc = describe_image_provider_queue(env)
            landscape_prompt = video_spec_cover_prompt(project_id, "landscape") or build_content_cover_prompt(project, template, content, "landscape")
            story_prompt = video_spec_cover_prompt(project_id, "story") or build_content_cover_prompt(project, template, content, "story")
            portrait_prompt = video_spec_cover_prompt(project_id, "portrait") or build_content_cover_prompt(project, template, content, "portrait")
            missing_only = step == "covers_missing"
            add(f"[covers] 正在调用 {provider['label']} 生成封面图")
            cover_jobs = [
                ("横屏封面", landscape_prompt, storage.project_file(project_id, "covers/cover_landscape.png"), COVER_LANDSCAPE_SIZE),
                ("图文封面", story_prompt, storage.project_file(project_id, "covers/cover_story.png"), COVER_STORY_SIZE),
                ("竖屏封面", portrait_prompt, storage.project_file(project_id, "covers/cover_portrait.png"), COVER_PORTRAIT_SIZE),
            ]
            if missing_only:
                cover_jobs = [item for item in cover_jobs if not item[2].exists()]
                if not cover_jobs:
                    add("[covers] 没有缺失的封面图，跳过补图。")
                    return True, scene_lines
                add("[covers] 续跑模式：只补缺失封面，保留已有封面")
            add(f"[covers] {provider_desc}")
            if provider["key"] in {"apiyi", "third_party"}:
                add("[covers] OpenAI 兼容文生图封面已切换为串行生成")
            if provider["key"] == "chatgpt_handoff":
                add("[covers] ChatGPT 接力模式：会逐张打开提示词并等待目标封面文件保存完成")
            if provider["key"] == "chatgpt_web_auto":
                add("[covers] ChatGPT 网页自动化：会自动发送提示词、等待图片并保存到项目目录；首次使用需要在弹出浏览器中登录")
            for label, prompt, output_path, output_size in cover_jobs:
                add(f"[covers] 开始生成 {label}")
                await asyncio.to_thread(generate_configured_image_safely, prompt, output_path, output_size, "cover", env, add, template)
                audit = read_image_audit(output_path)
                if audit.get("attempt", 1) > 1:
                    add(f"[covers] {label} 自检后重绘 {audit.get('attempt')} 次")
                if audit.get("severity") == "soft" and audit.get("reasons"):
                    add(f"[covers] {label} 自检提示：{', '.join(str(item) for item in audit.get('reasons', []))}")
                add(f"[covers] 已完成 {label}")
            mark_image_review_dirty(project_id, "封面图已重新生成，等待人工确认")
            add("[covers] 横屏、图文、竖屏封面已生成")
            return True, scene_lines

        if step == "video":
            preflight = video_preflight_report(project_id)
            if not preflight.get("passed"):
                for item in preflight.get("blockers", []):
                    if isinstance(item, dict):
                        add(f"[preflight] 阻止：{item.get('where', '')} - {item.get('issue', '')}；建议：{item.get('fix', '')}")
                raise RuntimeError("成片前总检未通过，请先修复阻止项。")
            for item in preflight.get("warnings", []):
                if isinstance(item, dict):
                    add(f"[preflight] 提醒：{item.get('where', '')} - {item.get('issue', '')}")
            add("[preflight] 成片前总检通过")
            audio_path = storage.project_file(project_id, "audio/podcast.mp3")
            subtitle_path = storage.project_file(project_id, "audio/subtitles.srt")
            scene_paths = find_scene_image_paths(project_id)
            output_path = storage.project_file(project_id, "releases/final-video.mp4")
            add("[video] 已关闭转场和镜头运动，改为静态画面直接硬切合成")
            result_path = await asyncio.to_thread(
                compose_final_video,
                project_id,
                title,
                scene_paths,
                audio_path,
                subtitle_path if subtitle_path.exists() else None,
                output_path,
            )
            size_mb = result_path.stat().st_size / 1048576.0 if result_path.exists() else 0.0
            add(f"[video] 已生成 final-video.mp4 ({size_mb:.1f} MB)")
            try:
                report = quality_gate_report(project_id)
                storage.save_report(project_id, "quality_gate", report)
                add(f"[quality] 质量总检完成：{report.get('overall_score', 0)} 分，{report.get('verdict', '')}")
            except Exception as exc:
                add(f"[quality] 质量总检暂未完成：{exc}")
            return True, scene_lines
            template_key = clean_text(project.get("template", ""))
            template = storage.get_template(template_key) if template_key else {"name": "", "brand_name": ""}
            add("[video] 优先调用原版 composer 合成最终 mp4")
            try:
                result_path = await asyncio.to_thread(
                    compose_original_video,
                    project_id,
                    project,
                    template,
                    content,
                    scene_paths,
                    audio_path,
                    subtitle_path if subtitle_path.exists() else None,
                    output_path,
                )
                add("[video] 已切回原版成片链路")
            except Exception as exc:
                add(f"[video] 原版 composer 调用失败，回退本地 ffmpeg：{exc}")
                result_path = await asyncio.to_thread(
                    compose_final_video,
                    project_id,
                    title,
                    scene_paths,
                    audio_path,
                    subtitle_path if subtitle_path.exists() else None,
                    output_path,
                )
            size_mb = result_path.stat().st_size / 1048576.0 if result_path.exists() else 0.0
            add(f"[video] 已生成 final-video.mp4 ({size_mb:.1f} MB)")
            return True, scene_lines

        return False, scene_lines

    async def _handle_step(
        self,
        project_id: int,
        project: dict[str, Any],
        title: str,
        step: str,
        content: str,
        scene_lines: list[str],
        log_lines: list[str],
    ) -> list[str]:
        handled, next_scene_lines = await self._handle_real_step(project_id, project, title, step, content, scene_lines, log_lines)
        if handled:
            return next_scene_lines

        mode = project.get("template_mode", "video")
        dialogue_lines = parse_dialogue_lines(content, mode)
        highlights = parse_highlights(content)

        def add(line: str) -> None:
            log_lines.append(line)
            snapshot = storage.load_latest_job(project_id) or {}
            snapshot["log"] = "\n".join(log_lines)
            storage.save_latest_job(project_id, snapshot)

        if step == "audio":
            add("[audio] 正在生成本地演示口播音频 podcast.wav")
            duration = max(2.2, min(12.0, len(dialogue_lines) * 0.65 or len(scene_lines) * 0.8 or 2.2))
            await asyncio.sleep(0.4)
            write_wave_file(storage.project_file(project_id, "audio/podcast.wav"), duration=duration, freq=440.0)
            storage.write_text(
                storage.project_file(project_id, "audio/podcast.txt"),
                ("\n".join(dialogue_lines) or "\n".join(scene_lines) or clean_text(content) or project["topic_name"]) + "\n",
            )
            add("[audio] 口播音频与稿本文本已写出")
            return scene_lines

        if step == "subtitles":
            add("[subtitles] 正在对齐字幕")
            await asyncio.sleep(0.35)
            scene_lines = current_scene_prompts(project_id, content, mode, project["topic_name"], prefer_timeline=False)
            scene_count_info = resolve_project_scene_count(project, content, mode, candidate_count=len(scene_lines), audio_ms=len(dialogue_lines) * 4000)
            desired_scene_count = int(scene_count_info.get("final", len(scene_lines)) or len(scene_lines) or 1)
            scene_lines = normalize_scene_prompt_count(scene_lines, desired_scene_count, project["topic_name"], mode)
            spoken = dialogue_lines or scene_lines
            fake_utterances = []
            for idx, line in enumerate(spoken[: max(1, desired_scene_count)], start=1):
                fake_utterances.append(
                    {
                        "start_ms": (idx - 1) * 4000,
                        "end_ms": idx * 4000,
                        "text": clean_text(line),
                    }
                )
            timeline = build_scene_timeline_for_scene_count(fake_utterances, scene_lines, desired_scene_count, max(1000, len(fake_utterances) * 4000))
            write_srt_entries(storage.project_file(project_id, "audio/subtitles.srt"), fake_utterances)
            sync_project_subtitle_files(project_id)
            storage.write_text(
                storage.project_file(project_id, "audio/scene_timeline.json"),
                json.dumps(timeline, ensure_ascii=False, indent=2),
            )
            aligned_lines = [clean_text(str(item.get("prompt", ""))) for item in timeline.get("scenes", []) if isinstance(item, dict)]
            summary = storage.get_summary(project_id)
            if summary:
                original_scene_count = int(summary.get("scene_count", 0) or 0)
                summary["scene_count_script"] = int(summary.get("scene_count_script", original_scene_count) or original_scene_count)
                summary["scene_count"] = len(aligned_lines)
                summary["scene_count_aligned"] = len(aligned_lines)
                storage.save_summary(project_id, summary)
            add(
                f"[scene_timeline] 使用对齐后的场景图列表：候选 {len(scene_lines)} 张 -> 最终 {len(aligned_lines)} 张"
            )
            scene_plan = write_scene_plan(project_id, project, content, timeline, aligned_lines or scene_lines)
            add(f"[scene_timeline] 写出 audio/scene_timeline.json，共 {len(aligned_lines)} 段")
            add(f"[scene_plan] 写出 audio/scene_plan.json，共 {scene_plan.get('scene_count', len(aligned_lines))} 镜")
            add("[subtitles] subtitles.srt 与 scene_timeline.json 已生成")
            return aligned_lines or scene_lines

        if step == "images":
            if not scene_lines:
                scene_lines = current_scene_prompts(project_id, content, mode, project["topic_name"])
            add(f"[images] 开始生成 {len(scene_lines)} 张场景图")
            scene_records = []
            removed = storage.cleanup_scene_outputs(project_id)
            if removed:
                add(f"[images] 已清理 {removed} 个旧场景文件")
            for idx, prompt in enumerate(scene_lines, start=1):
                filename = f"s_{idx:02d}.svg"
                label = highlights[idx - 1] if idx - 1 < len(highlights) else f"场景 {idx}"
                write_svg_card(
                    storage.project_file(project_id, f"scenes/{filename}"),
                    label,
                    prompt,
                    "#2563eb" if idx % 2 else "#7c3aed",
                    (1280, 720),
                )
                scene_records.append({"filename": filename, "label": label, "prompt": prompt})
                add(f"[images] 进度 {idx}/{len(scene_lines)} -> {filename}")
                await asyncio.sleep(0.18)
            storage.write_text(
                storage.project_file(project_id, "scenes/scene_prompts.json"),
                json.dumps(scene_records, ensure_ascii=False, indent=2),
            )
            add("[images] 场景图全部完成")
            return scene_lines

        if step == "covers":
            summary = storage.get_summary(project_id)
            cover_title = summary.get("cover_title") or title
            cover_subtitle = summary.get("cover_subtitle") or fallback_cover_subtitle(title)
            add("[covers] 生成横屏和竖屏发布封面")
            await asyncio.sleep(0.35)
            write_svg_card(
                storage.project_file(project_id, "covers/cover_landscape.svg"),
                cover_title,
                cover_subtitle or "16:9 横屏封面",
                "#f97316",
                (1280, 720),
            )
            write_svg_card(
                storage.project_file(project_id, "covers/cover_portrait.svg"),
                cover_title,
                cover_subtitle or "3:4 竖屏封面",
                "#db2777",
                (900, 1200),
            )
            write_svg_card(
                storage.project_file(project_id, "covers/cover_story.svg"),
                cover_title,
                cover_subtitle or "4:3 横图封面",
                "#059669",
                (1200, 900),
            )
            add("[covers] 封面图已生成")
            return

        if step == "article":
            add("[article] 正在生成图文发布稿")
            await asyncio.sleep(0.25)
            lines = parse_dialogue_lines(content, "article") or scene_lines
            article_body = "# 图文发布稿\n\n" + "\n".join(f"- 第 {idx + 1} 段：{line}" for idx, line in enumerate(lines))
            storage.write_text(storage.project_file(project_id, "article/publish-pack.md"), article_body + "\n")
            add("[article] 图文包 markdown 已写出")
            return

        if step == "video":
            add("[video] 正在拼装本地预演成片")
            await asyncio.sleep(0.45)
            scene_records = storage.read_json(storage.project_file(project_id, "scenes/scene_prompts.json"), [])
            scenes = []
            for idx, prompt in enumerate(scene_lines, start=1):
                filename = f"s_{idx:02d}.svg"
                path = storage.project_file(project_id, f"scenes/{filename}")
                if not path.exists():
                    continue
                record = next((item for item in scene_records if item.get("filename") == filename), {})
                scenes.append(
                    {
                        "filename": filename,
                        "label": record.get("label") or f"场景 {idx}",
                        "prompt": record.get("prompt") or prompt,
                    }
                )
            write_preview_html(project_id, title, scenes)
            storage.write_text(
                storage.project_file(project_id, "releases/final-video.txt"),
                "这是当前本地版本的成片占位文件。正式 ffmpeg / 外部模型链路后续可继续替换成真实 mp4。\n",
            )
            add("[video] 已生成 final-preview.html 与 final-video.txt")
            return scene_lines

        add(f"[{step}] 未识别的步骤，已跳过")
        return scene_lines


AUTO_VIDEO_STATE_FILE = storage.CONFIG_ROOT / "auto_video_latest.json"


def _auto_video_state_seed(template_key: str, count: int, tavily_topic: str, steps: list[str], mining_prompt: str = "") -> dict[str, Any]:
    return {
        "id": f"auto-video-{storage.now_ms()}",
        "template_key": template_key,
        "count": count,
        "tavily_topic": tavily_topic,
        "mining_prompt": clean_text(mining_prompt),
        "steps": steps,
        "status": "running",
        "running": True,
        "stage": "init",
        "started_at": storage.now_ts(),
        "finished_at": None,
        "project_id": None,
        "topic": "",
        "topic_candidates": [],
        "queued_topics": [],
        "queue_index": 0,
        "queue_total": count,
        "created_projects": [],
        "log": "",
        "error": "",
        "result": {},
    }


def _safe_json_from_text(text: str) -> dict[str, Any]:
    cleaned = strip_code_fences(text)
    try:
        payload = json.loads(cleaned)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        pass
    match = re.search(r"(?s)\{.*\}", cleaned or "")
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _channel_topic_keywords(template: dict[str, Any]) -> list[str]:
    source = "\n".join(
        [
            str(template.get("key") or ""),
            str(template.get("name") or ""),
            str(template.get("brand_name") or ""),
            str(template.get("target_audience") or ""),
            str(template.get("channel_voice") or ""),
            str(template.get("visual_strategy") or ""),
            str(template.get("forbidden_rules") or ""),
            str(template.get("interaction_goal") or ""),
            str(template.get("topic_mining_hint") or ""),
            str(template.get("release_tags") or ""),
            str(template.get("cover_style") or ""),
            str(template.get("prompt") or "")[:2500],
        ]
    )
    tokens = list(extract_tokens(source))
    ignored = {"content", "markdown", "prompt", "video", "brief", "meta", "16", "9", "3", "4", "cover", "default"}
    ranked = sorted(
        (token for token in tokens if token not in ignored and len(token) >= 2),
        key=lambda item: (-source.count(item), item),
    )
    return ranked[:10]


def _topic_duplicate_penalty(title: str, existing_topics: list[str]) -> float:
    tokens = extract_tokens(title)
    if not tokens:
        return 0.0
    return max((overlap_score(tokens, item) for item in existing_topics), default=0.0)


def _normalize_topic_candidates(raw_candidates: Any, existing_topics: list[str]) -> list[dict[str, Any]]:
    if not isinstance(raw_candidates, list):
        return []
    candidates: list[dict[str, Any]] = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        title = clean_text(str(item.get("title") or item.get("topic") or ""))
        if not title:
            continue
        try:
            score = float(item.get("score") or 4.0)
        except Exception:
            score = 4.0
        duplicate_penalty = _topic_duplicate_penalty(title, existing_topics)
        candidates.append(
            {
                "title": title[:80],
                "brief": clean_text(str(item.get("brief") or item.get("angle") or item.get("summary") or "")),
                "why": clean_text(str(item.get("why") or item.get("reason") or item.get("value") or "")),
                "search_query": clean_text(str(item.get("search_query") or item.get("query") or title)),
                "target_duration": clean_text(str(item.get("target_duration") or item.get("duration") or "3-4分钟")),
                "score": max(0.0, min(5.0, score)),
                "duplicate_penalty": round(duplicate_penalty, 3),
                "rank_score": round(max(0.0, score - duplicate_penalty * 2.2), 3),
                "source": clean_text(str(item.get("source") or "deepseek")),
            }
        )
    candidates.sort(key=lambda item: item.get("rank_score", 0), reverse=True)
    return candidates


def _clean_selected_topic_queue(raw_topics: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_topics, list):
        return []
    queue: list[dict[str, Any]] = []
    for item in raw_topics:
        if not isinstance(item, dict):
            continue
        title = clean_text(str(item.get("title") or item.get("topic") or ""))
        if not title:
            continue
        try:
            score = float(item.get("score") or 4.0)
        except Exception:
            score = 4.0
        queue.append(
            {
                "title": title[:80],
                "brief": clean_text(str(item.get("brief") or item.get("angle") or item.get("summary") or "")),
                "why": clean_text(str(item.get("why") or item.get("reason") or item.get("value") or "")),
                "search_query": clean_text(str(item.get("search_query") or item.get("query") or title)),
                "target_duration": clean_text(str(item.get("target_duration") or item.get("duration") or "3-4分钟")),
                "score": max(0.0, min(5.0, score)),
                "rank_score": max(0.0, min(5.0, score)),
                "source": clean_text(str(item.get("source") or "selected")),
            }
        )
    return queue[:5]


def _fallback_topic_candidates(template: dict[str, Any], existing_topics: list[str]) -> list[dict[str, Any]]:
    brand = clean_text(str(template.get("brand_name") or template.get("name") or template.get("key") or "本频道"))
    prompt_blob = clean_text(str(template.get("prompt") or ""))
    keywords = _channel_topic_keywords(template)
    base = keywords[0] if keywords else brand
    seeds = [
        {
            "title": f"{base}里最容易被忽略的一个坑",
            "brief": "从用户最容易误判的细节切入，做成能直接提醒观众的短视频选题。",
            "why": "有痛点、有提醒价值，也适合做封面钩子。",
        },
        {
            "title": f"{brand}今天最值得讲的一件小事",
            "brief": "围绕频道人设，把近期可讨论的小切口讲成一条完整因果线。",
            "why": "适合保持频道连续更新，不依赖宏大题目。",
        },
        {
            "title": f"很多人以为懂了{base}，其实第一步就错了",
            "brief": "用反常识开头，先拆误区，再给具体判断方法。",
            "why": "标题冲突感强，利于短视频开场留人。",
        },
    ]
    if any(word in prompt_blob for word in ["爸妈", "老人", "中老年", "养老", "客服", "诈骗"]):
        seeds = [
            {
                "title": "爸妈接到“客服扣费电话”，先别急着操作",
                "brief": "围绕老人接到扣费、会员、屏幕共享等电话时的真实反应，拆出正确处理顺序。",
                "why": "强现实痛点，家庭场景明确，容易引发转发。",
            },
            {
                "title": "免费服务突然要你转账，最该先核实什么",
                "brief": "用一个生活化案例，把诈骗话术拆成几个可判断信号。",
                "why": "能给观众可执行的判断方法，适合做系列。",
            },
            {
                "title": "验证码不是数字，是钱袋子的钥匙",
                "brief": "把常见验证码骗局讲成一个有画面感的安全提醒。",
                "why": "比泛泛提醒更形象，封面钩子也更直接。",
            },
        ]
    elif any(word in prompt_blob for word in ["科技", "AI", "华为", "手机", "智能"]):
        seeds = [
            {
                "title": "新功能看着很炫，真正改变体验的是哪一步",
                "brief": "围绕科技产品的新功能，从用户实际场景拆出真正价值。",
                "why": "能避开参数堆砌，讲成用户能听懂的场景。",
            },
            {
                "title": "大家都在问值不值，其实该先看这三个场景",
                "brief": "用三个生活场景判断一个智能产品到底适不适合普通人。",
                "why": "具备消费决策价值，评论区容易讨论。",
            },
            {
                "title": "别只看发布会，真正的差别藏在日常使用里",
                "brief": "把发布会卖点翻译成普通用户的一天，判断是不是噱头。",
                "why": "符合科技频道连续产出的稳定结构。",
            },
        ]
    return _normalize_topic_candidates([{**item, "score": 4.0, "source": "fallback"} for item in seeds], existing_topics)


def mine_channel_topic(template: dict[str, Any], tavily_topic: str = "general", user_prompt: str = "") -> dict[str, Any]:
    template_key = clean_text(str(template.get("key") or ""))
    existing_projects = storage.projects_for_template(template_key) if template_key else []
    existing_topics = [clean_text(str(item.get("topic_name") or "")) for item in existing_projects[:30]]
    keywords = _channel_topic_keywords(template)
    brand = clean_text(str(template.get("brand_name") or template.get("name") or template_key or "本频道"))
    user_prompt = clean_text(user_prompt)
    prompt_hint = user_prompt[:240]
    channel_profile = channel_profile_text(template)
    learning = channel_learning_prompt_block({"id": 0, "template": template_key}, template)
    query = " ".join([brand, prompt_hint, *keywords[:5], "最近 热点 选题 短视频"]).strip()

    references = search_tavily(query, tavily_topic, 8)
    if not references:
        references = search_duckduckgo(query, 6)

    candidates: list[dict[str, Any]] = []
    env = runtime_env()
    api_key = clean_text(env.get("DEEPSEEK_API_KEY", ""))
    if api_key and OpenAI is not None:
        base_url = clean_text(env.get("DEEPSEEK_BASE_URL", "")) or "https://api.deepseek.com"
        model = clean_text(env.get("DEEPSEEK_MODEL", "")) or "deepseek-v4-flash"
        thinking_type = clean_text(env.get("DEEPSEEK_THINKING_TYPE", "")) or "enabled"
        reasoning_effort = clean_text(env.get("DEEPSEEK_REASONING_EFFORT", "")) or "high"
        refs_block = format_reference_block("可参考的公开资料：", references[:8])
        user_prompt_block = f"\n用户额外提示词（必须优先满足）：\n{prompt_hint}\n" if prompt_hint else "\n用户额外提示词：无\n"
        prompt = f"""
你是一个短视频频道的自动选题导演，请严格根据当前频道 prompt.md 挖掘本频道可连续生产的视频主题。

要求：
1. 选题必须服从频道人设、语气、受众、封面风格和内容结构，不能生成通用科普腔。
2. 选题要避开历史主题，优先挑有现实痛点、画面感、传播钩子、可查资料支撑的题。
3. 返回严格 JSON，不要 Markdown，不要解释。
4. 至少给 6 个候选，每个候选包含 title、brief、why、search_query、target_duration、score。
5. 如果用户给了额外提示词，候选 1 必须优先贴合这条提示词；如果完全不适合频道，也要做最接近频道风格的改写，而不是忽略它。

频道信息：
- key: {template_key}
- name: {template.get("name") or ""}
- brand_name: {brand}
- mode: {template.get("mode") or "video"}
- release_tags: {template.get("release_tags") or ""}
- cover_style: {template.get("cover_style") or ""}
- target_audience: {template.get("target_audience") or ""}
- channel_voice: {template.get("channel_voice") or ""}
- visual_strategy: {template.get("visual_strategy") or ""}
- forbidden_rules: {template.get("forbidden_rules") or ""}
- interaction_goal: {template.get("interaction_goal") or ""}
- topic_mining_hint: {template.get("topic_mining_hint") or ""}

频道中枢：
{channel_profile or "未填写结构化频道中枢，以 prompt.md 为准。"}

{learning}

频道 prompt.md：
{str(template.get("prompt") or "")[:5000]}

历史主题：
{json.dumps(existing_topics[:30], ensure_ascii=False)}

{user_prompt_block}

{refs_block}

请返回：
{{
  "candidates": [
    {{
      "title": "短而有钩子的主题名",
      "brief": "本期切入角度和素材组织方式",
      "why": "为什么适合这个频道",
      "search_query": "后续查资料用的搜索词",
      "target_duration": "3-4分钟",
      "score": 4.5
    }}
  ]
}}
""".strip()
        extra_body: dict[str, Any] = {"reasoning_effort": reasoning_effort}
        if thinking_type in {"enabled", "disabled"}:
            extra_body["thinking"] = {"type": thinking_type}
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你只输出严格 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.85,
                max_tokens=3500,
                extra_body=extra_body,
            )
            raw = message_content_to_text(response.choices[0].message.content if response.choices else "")
            payload = _safe_json_from_text(raw)
            candidates = _normalize_topic_candidates(payload.get("candidates"), existing_topics)
        except Exception:
            candidates = []

    if not candidates and prompt_hint:
        first_line = clean_text(re.split(r"[\r\n。！？!?；;]+", prompt_hint, maxsplit=1)[0])
        prompt_title = (first_line or prompt_hint)[:32].strip("，,。；;：: ")
        if prompt_title:
            candidates = _normalize_topic_candidates(
                [
                    {
                        "title": prompt_title,
                        "brief": f"围绕“{prompt_hint[:80]}”切入，按当前频道人设重写成有钩子、有评论空间的短视频选题。",
                        "why": "优先服从这次手动输入的选题方向，同时保持频道受众与表达风格。",
                        "search_query": " ".join(part for part in [brand, prompt_hint[:80]] if part),
                        "target_duration": "3-4分钟",
                        "score": 4.1,
                        "source": "prompt",
                    }
                ],
                existing_topics,
            )

    if not candidates:
        candidates = _fallback_topic_candidates(template, existing_topics)

    if not candidates:
        title = f"{brand}自动选题 {int(storage.now_ts())}"
        candidates = _normalize_topic_candidates([{"title": title, "score": 3.5, "source": "fallback"}], existing_topics)

    picked = candidates[0]
    search_query = clean_text(str(picked.get("search_query") or picked.get("title") or query))
    topic_refs = search_tavily(search_query, tavily_topic, 8) or search_duckduckgo(search_query, 6) or references
    return {
        "picked": picked,
        "candidates": candidates,
        "references": topic_refs,
        "seed_query": query,
        "searched_query": search_query,
        "existing_topics": existing_topics[:30],
        "keywords": keywords,
        "user_prompt": user_prompt,
        "provider": "deepseek" if any(item.get("source") == "deepseek" for item in candidates) else candidates[0].get("source", "fallback"),
    }


def selected_topic_payload(
    selected_topic: dict[str, Any],
    template: dict[str, Any],
    tavily_topic: str = "general",
    user_prompt: str = "",
    queued_topics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    template_key = clean_text(str(template.get("key") or ""))
    existing_projects = storage.projects_for_template(template_key) if template_key else []
    existing_topics = [clean_text(str(item.get("topic_name") or "")) for item in existing_projects[:30]]
    normalized = _clean_selected_topic_queue([selected_topic])
    picked = normalized[0] if normalized else {
        "title": clean_text(str(selected_topic.get("title") or selected_topic.get("topic") or f"{template_key} 自动主题")),
        "brief": clean_text(str(selected_topic.get("brief") or "")),
        "why": clean_text(str(selected_topic.get("why") or "")),
        "search_query": clean_text(str(selected_topic.get("search_query") or selected_topic.get("title") or template_key)),
        "target_duration": clean_text(str(selected_topic.get("target_duration") or "3-4分钟")),
        "score": 4.0,
        "rank_score": 4.0,
        "source": "selected",
    }
    all_candidates = _clean_selected_topic_queue(queued_topics or [selected_topic])
    search_query = clean_text(str(picked.get("search_query") or picked.get("title") or template_key))
    references = search_tavily(search_query, tavily_topic, 8) or search_duckduckgo(search_query, 6)
    return {
        "picked": picked,
        "candidates": all_candidates or [picked],
        "references": references,
        "seed_query": search_query,
        "searched_query": search_query,
        "existing_topics": existing_topics[:30],
        "keywords": _channel_topic_keywords(template),
        "user_prompt": clean_text(user_prompt),
        "provider": picked.get("source") or "selected",
        "selected_by_user": True,
    }


def render_auto_topic_brief(topic_payload: dict[str, Any], template: dict[str, Any], tavily_topic: str) -> str:
    picked = topic_payload.get("picked") if isinstance(topic_payload.get("picked"), dict) else {}
    references = topic_payload.get("references") if isinstance(topic_payload.get("references"), list) else []
    title = clean_text(str(picked.get("title") or "自动挖掘主题"))
    brief = clean_text(str(picked.get("brief") or ""))
    why = clean_text(str(picked.get("why") or ""))
    duration = clean_text(str(picked.get("target_duration") or "3-4分钟"))
    refs_block = "\n".join(
        f"- {item.get('title') or '资料'}：{item.get('snippet') or ''} {item.get('url') or ''}".strip()
        for item in references[:8]
    ) or "- 暂无联网资料，按频道模板和本地历史稿创作。"
    candidates_block = "\n".join(
        f"{idx}. {item.get('title')}（{item.get('score', 0)}分）- {item.get('why') or item.get('brief') or ''}"
        for idx, item in enumerate(topic_payload.get("candidates", [])[:6], start=1)
    )
    return f"""# 自动挖题 brief

## 频道约束
- 频道：{template.get("brand_name") or template.get("name") or template.get("key")}
- 模式：{template.get("mode") or "video"}
- 封面风格：{template.get("cover_style") or "default"}
- 发布标签：{template.get("release_tags") or ""}
- 联网话题：{tavily_topic or "general"}

## 本期选题
- 主题：{title}
- 推荐时长：{duration}
- 选题理由：{why or "贴合频道方向，具备现实痛点和可视化空间。"}
- 内容切入：{brief or "先用强钩子切入，再拆真实场景、误区和可执行判断方法。"}
- 搜索词：{topic_payload.get("searched_query") or title}

## 候选记录
{candidates_block or "1. " + title}

## 参考资料
{refs_block}

## 生产要求
请严格沿用当前频道 prompt.md 的人设、口吻、结构、封面/IP 角标、图片提示词规则和时长要求。
不要把这个频道写成通用科普腔；每张场景图必须跟对应脚本段落和本期素材强绑定。
封面要能体现频道个人 IP 或作者名称，同时标题必须短、清楚、有点击欲。
"""


def render_auto_topic_brief_v2(topic_payload: dict[str, Any], template: dict[str, Any], tavily_topic: str) -> str:
    picked = topic_payload.get("picked") if isinstance(topic_payload.get("picked"), dict) else {}
    references = topic_payload.get("references") if isinstance(topic_payload.get("references"), list) else []
    user_prompt = clean_text(str(topic_payload.get("user_prompt") or ""))
    title = clean_text(str(picked.get("title") or "自动挖掘主题"))
    brief = clean_text(str(picked.get("brief") or ""))
    why = clean_text(str(picked.get("why") or ""))
    duration = clean_text(str(picked.get("target_duration") or "3-4分钟"))
    refs_block = "\n".join(
        f"- {item.get('title') or '资料'}：{item.get('snippet') or ''} {item.get('url') or ''}".strip()
        for item in references[:8]
    ) or "- 暂无联网资料，按频道模板和本地历史继续创作。"
    candidates_block = "\n".join(
        f"{idx}. {item.get('title')}（{item.get('score', 0)}分）- {item.get('why') or item.get('brief') or ''}"
        for idx, item in enumerate(topic_payload.get("candidates", [])[:6], start=1)
    )
    prompt_block = (
        f"\n## 本次手动提示\n- 选题提示词：{user_prompt}\n- 要求：最终主题、文案角度、封面与场景图都要优先贴合这条提示词，再服从频道人设。\n"
        if user_prompt
        else ""
    )
    extra_prompt_requirement = (
        f" 本次还有一条额外提示词：{user_prompt}。整条内容和出图都要围绕它展开，不能忽略。"
        if user_prompt
        else ""
    )
    channel_profile = channel_profile_text(template)
    return f"""# 自动挖题 brief

## 频道约束
- 频道：{template.get("brand_name") or template.get("name") or template.get("key")}
- 模式：{template.get("mode") or "video"}
- 封面风格：{template.get("cover_style") or "default"}
- 发布标签：{template.get("release_tags") or ""}
- 联网话题：{tavily_topic or "general"}
{prompt_block}

## 频道中枢
{channel_profile or "- 未填写结构化频道中枢，按 prompt.md 执行。"}

## 本期选题
- 主题：{title}
- 推荐时长：{duration}
- 选题理由：{why or "贴合频道方向，具备现实痛点和可视化空间。"}
- 内容切入：{brief or "先用强钩子切入，再拆真实场景、误区和可执行判断方法。"}
- 搜索词：{topic_payload.get("searched_query") or title}

## 候选记录
{candidates_block or "1. " + title}

## 参考资料
{refs_block}

## 生产要求
请严格沿用当前频道 prompt.md 的人设、口吻、结构、封面/IP 角标、图片提示词规则和时长要求。
不要把这个频道写成通用科普腔；每张场景图必须跟对应脚本段落和本期素材强绑定。
封面要能体现频道个人 IP 或作者名称，同时标题必须短、清楚、有点击欲。{extra_prompt_requirement}
"""


class AutoVideoRuntime:
    def __init__(self) -> None:
        self.task: asyncio.Task[None] | None = None
        self.state: dict[str, Any] | None = None

    def latest(self) -> dict[str, Any] | None:
        payload = self.state or storage.read_json(AUTO_VIDEO_STATE_FILE, None)
        if not isinstance(payload, dict):
            return None
        if payload.get("running") and (not self.task or self.task.done()):
            recovered = dict(payload)
            recovered["running"] = False
            recovered["finished_at"] = recovered.get("finished_at") or storage.now_ts()
            recovered["status"] = "interrupted" if recovered.get("status") == "running" else recovered.get("status", "interrupted")
            log_text = str(recovered.get("log") or "").rstrip()
            suffix = "[auto] 上一次自动成片任务在服务重启前中断，请重新开始。"
            recovered["log"] = f"{log_text}\n{suffix}".strip() if log_text else suffix
            storage.write_json(AUTO_VIDEO_STATE_FILE, recovered)
            self.state = recovered
            return recovered
        return payload

    async def start(
        self,
        template_key: str,
        *,
        count: int = 1,
        tavily_topic: str = "general",
        mining_prompt: str = "",
        steps: list[str] | None = None,
        auto_confirm_images: bool = True,
        selected_topics: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if self.task and not self.task.done():
            raise RuntimeError("已有自动挖题成片任务正在运行，请等待完成或先取消。")
        template = storage.get_template(template_key)
        selected_queue = _clean_selected_topic_queue(selected_topics or [])
        safe_count = len(selected_queue) if selected_queue else max(1, min(int(count or 1), 5))
        mining_prompt = clean_text(mining_prompt)
        resolved_steps = steps or (
            ["images", "covers", "article"] if template.get("mode") == "article" else ["audio", "subtitles", "images", "covers", "video"]
        )
        state = _auto_video_state_seed(template_key, safe_count, tavily_topic or "general", resolved_steps, mining_prompt)
        state["auto_confirm_images"] = bool(auto_confirm_images)
        state["queued_topics"] = selected_queue
        state["queue_total"] = safe_count
        self.state = state
        self._save()
        self.task = asyncio.create_task(
            self._run(
                template_key,
                safe_count,
                tavily_topic or "general",
                mining_prompt,
                resolved_steps,
                bool(auto_confirm_images),
                selected_queue,
            )
        )
        return state

    async def cancel(self) -> dict[str, Any]:
        if not self.task or self.task.done():
            return {"already_done": True}
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task
        return {"already_done": False}

    def _save(self) -> None:
        if not self.state:
            return
        storage.write_json(AUTO_VIDEO_STATE_FILE, self.state)
        project_id = self.state.get("project_id")
        if project_id:
            storage.write_json(storage.project_file(int(project_id), "auto_video.json"), self.state)

    def _log(self, line: str) -> None:
        if not self.state:
            return
        log = str(self.state.get("log") or "").rstrip()
        self.state["log"] = f"{log}\n{line}".strip() if log else line
        self._save()

    def _stage(self, stage: str) -> None:
        if not self.state:
            return
        self.state["stage"] = stage
        self.state["stage_started_at"] = storage.now_ts()
        self._save()

    async def _run(
        self,
        template_key: str,
        count: int,
        tavily_topic: str,
        mining_prompt: str,
        steps: list[str],
        auto_confirm_images: bool,
        selected_topics: list[dict[str, Any]] | None = None,
    ) -> None:
        assert self.state is not None
        selected_queue = _clean_selected_topic_queue(selected_topics or [])
        try:
            for index in range(1, count + 1):
                template = storage.get_template(template_key)
                self._stage("mine_topic")
                self.state["queue_index"] = index
                self.state["queue_total"] = count
                self._save()
                self._log(f"[auto] {index}/{count} 正在为频道「{template_key}」准备主题")
                if mining_prompt:
                    self._log(f"[auto] 本次选题提示词：{mining_prompt}")
                if index <= len(selected_queue):
                    selected_topic = selected_queue[index - 1]
                    topic_payload = await asyncio.to_thread(
                        selected_topic_payload,
                        selected_topic,
                        template,
                        tavily_topic,
                        mining_prompt,
                        selected_queue,
                    )
                    self._log(f"[auto] 使用已确认候选：{selected_topic.get('title') or ''}")
                else:
                    topic_payload = await asyncio.to_thread(mine_channel_topic, template, tavily_topic, mining_prompt)
                picked = topic_payload.get("picked") if isinstance(topic_payload.get("picked"), dict) else {}
                topic_title = clean_text(str(picked.get("title") or f"{template_key} 自动主题 {index}"))
                self.state["topic"] = topic_title
                self.state["topic_candidates"] = topic_payload.get("candidates", [])[:6]
                self._log(f"[auto] 已选题：{topic_title}")

                self._stage("create_project")
                project = storage.create_project(topic_title, template_key)
                project_id = int(project["id"])
                self.state["project_id"] = project_id
                self.state["created_projects"].append({"id": project_id, "topic_name": topic_title})
                self._save()

                brief = render_auto_topic_brief_v2(topic_payload, template, tavily_topic)
                storage.save_project_settings(project_id, {"tavily_topic": tavily_topic, "auto_topic_prompt": mining_prompt})
                storage.save_brief(project_id, brief)
                storage.write_json(
                    storage.project_file(project_id, "auto_topic.json"),
                    {
                        "topic": topic_title,
                        "user_prompt": mining_prompt,
                        "payload": topic_payload,
                        "brief_path": str(storage.project_file(project_id, "brief.md")),
                        "created_at": storage.now_ts(),
                    },
                )
                self._log(f"[auto] 已创建项目 #{project_id} 并写入 brief.md")

                self._stage("content")
                self._log("[auto] 正在调用现有 content 生成链路")
                content_runtime = ContentRuntime()
                await content_runtime.start(project, template, brief, tavily_topic)
                content_task = content_runtime.tasks.get(project_id, {}).get("task")
                if content_task:
                    await content_task
                content_state = storage.read_json(storage.project_file(project_id, "content_generate.json"), {})
                if content_state.get("status") != "succeeded":
                    raise RuntimeError(str(content_state.get("error") or content_state.get("fallback_reason") or "content.md 生成失败"))
                self._log(f"[auto] content.md 已生成，文本模型：{content_state.get('provider') or content_state.get('generator_priority') or 'unknown'}")

                if auto_confirm_images:
                    save_image_review_status(project_id, required=False, confirmed=False)
                    self._log("[auto] 全自动模式已关闭图片人工确认门槛")

                self._stage("produce")
                self._log(f"[auto] 开始生产流水线：{' -> '.join(steps)}")
                job_runtime = JobRuntime()
                job_snapshot = await job_runtime.start(storage.get_project(project_id), steps, allow_incomplete_video=False)
                job_task = job_runtime.tasks.get(job_snapshot["id"], {}).get("task")
                if job_task:
                    await job_task
                job = storage.load_latest_job(project_id) or {}
                if job.get("status") != "succeeded":
                    log_tail = "\n".join(str(job.get("log") or "").splitlines()[-8:])
                    raise RuntimeError(f"生产流水线失败：{log_tail or job.get('status') or 'unknown'}")

                files = {item["relative_path"]: item for item in storage.list_project_files(project_id)}
                final_video = files.get("releases/final-video.mp4")
                self.state["result"] = {
                    "project_id": project_id,
                    "topic": topic_title,
                    "project_root": str(storage.project_dir(project_id)),
                    "final_video": final_video,
                    "latest_job": job,
                }
                self._log("[auto] 自动挖题成片完成")

            self.state["status"] = "succeeded"
            self.state["running"] = False
            self.state["finished_at"] = storage.now_ts()
            self._save()
        except asyncio.CancelledError:
            self.state["status"] = "cancelled"
            self.state["running"] = False
            self.state["finished_at"] = storage.now_ts()
            self._log("[auto] 用户已取消自动挖题成片任务")
            self._save()
            raise
        except Exception as exc:
            self.state["status"] = "failed"
            self.state["running"] = False
            self.state["finished_at"] = storage.now_ts()
            self.state["error"] = str(exc)
            self._log(f"[auto] 任务失败：{exc}")
            self._save()
