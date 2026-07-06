from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from . import services, storage


SOCIAL_AUTO_UPLOAD_PLATFORMS = [
    {"key": "douyin", "label": "抖音"},
    {"key": "kuaishou", "label": "快手"},
    {"key": "xiaohongshu", "label": "小红书"},
]
SOCIAL_AUTO_UPLOAD_STATE_NAME = "releases/social_auto_upload.json"
SOCIAL_AUTO_UPLOAD_DRAFT_NAME = "releases/social_auto_upload_draft.json"
SOCIAL_AUTO_UPLOAD_ZIP_URL = "https://codeload.github.com/dreammis/social-auto-upload/zip/refs/heads/main"
BROKEN_PATCHRIGHT_HOSTS = {
    "https://npmmirror.com/mirrors/playwright",
}
LOCAL_CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]
ACCOUNT_PROBE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)
AUTO_RELEASE_ENTRY_URLS = {
    "douyin": "https://creator.douyin.com/creator-micro/content/manage",
}
DOUYIN_WORK_LIST_ENDPOINT = "https://creator.douyin.com/janus/douyin/creator/pc/work_list"
DOUYIN_WORK_LIST_PARAMS = {
    "status": 0,
    "count": 20,
    "max_cursor": 0,
    "scene": "star_atlas",
    "device_platform": "android",
    "aid": 1128,
}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_multiline_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", str(line)).strip() for line in str(value or "").splitlines()]
    return "\n".join([line for line in lines if line]).strip()


def _looks_lost_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text):
        return False
    reduced = re.sub(r"[\s\?\uff1f\ufffd\.,，。!！:：;；、'\"“”‘’#\-_/|()\[\]{}<>]+", "", text)
    return reduced == ""


def _with_text_fallback(value: Any, fallback: Any, *, multiline: bool = False) -> str:
    normalizer = clean_multiline_text if multiline else clean_text
    cleaned = normalizer(str(value or ""))
    if cleaned and not _looks_lost_text(cleaned):
        return cleaned
    backup = normalizer(str(fallback or ""))
    return backup or cleaned


def _debug_text(value: Any, limit: int = 120) -> str:
    text = str(value or "")
    if len(text) > limit:
        text = text[:limit] + "..."
    return text.encode("unicode_escape", errors="backslashreplace").decode("ascii")


def runtime_env() -> dict[str, str]:
    env = dict(storage.DEFAULT_ENV)
    env.update(storage.parse_env())
    return env


def _normalized_patchright_host(value: str) -> str:
    host = clean_text(value).rstrip("/")
    if not host or host in BROKEN_PATCHRIGHT_HOSTS:
        return ""
    return host


def _detect_local_chrome() -> str:
    for candidate in LOCAL_CHROME_CANDIDATES:
        if candidate.exists():
            return str(candidate).replace("\\", "/")
    return ""


def workspace_root() -> Path:
    return storage.APP_ROOT.parent


def repo_candidates(env: dict[str, str] | None = None) -> list[Path]:
    env = env or runtime_env()
    configured = clean_text(env.get("SAU_REPO_PATH", ""))
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    roots = [
        workspace_root(),
        workspace_root() / "_refs",
        workspace_root().parent,
        storage.APP_ROOT.parent,
    ]
    for root in roots:
        candidates.extend(
            [
                root / "social-auto-upload",
                root / "social-auto-upload-src",
                root / "_refs" / "social-auto-upload",
                root / "_refs" / "social-auto-upload-src",
            ]
        )
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def detect_repo(env: dict[str, str] | None = None) -> tuple[Path, bool]:
    env = env or runtime_env()
    configured = clean_text(env.get("SAU_REPO_PATH", ""))
    if configured:
        return Path(configured), False
    for candidate in repo_candidates(env):
        if (candidate / "pyproject.toml").exists():
            return candidate, True
    return repo_candidates(env)[0], True


def probe(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or runtime_env()
    repo_path, auto_detected = detect_repo(env)
    uv_bin = clean_text(env.get("SAU_UV_BIN", "")) or "uv"
    uv_available = bool(shutil.which(uv_bin) or Path(uv_bin).exists())
    repo_exists = repo_path.exists()
    pyproject_exists = (repo_path / "pyproject.toml").exists()
    script_exists = (repo_path / "sau_cli.py").exists()
    status = "unconfigured"
    message = "还没有找到 social-auto-upload 仓库；点击“准备环境”会自动下载并安装。"
    if repo_exists and pyproject_exists and uv_available:
        status = "success"
        message = "已找到 social-auto-upload 仓库与 uv，可以在投放页直接准备环境、登录和发布。"
    elif repo_exists and pyproject_exists and not uv_available:
        status = "error"
        message = "已找到仓库，但本机没有可用的 uv 命令。请先安装 uv 或在配置里填写 uv 的绝对路径。"
    elif repo_exists and not pyproject_exists and not script_exists:
        status = "error"
        message = "当前路径不是 social-auto-upload 仓库根目录，请重新填写到包含 pyproject.toml 的目录。"
    elif repo_exists and not pyproject_exists and script_exists:
        status = "warning"
        message = "仓库目录已找到，但缺少 pyproject.toml；建议更新为官方完整仓库后再使用。"
    elif clean_text(env.get("SAU_REPO_PATH", "")):
        status = "error"
        message = "配置中的 social-auto-upload 路径不存在；你可以改成正确路径，或清空后用“准备环境”自动下载。"
    return {
        "status": status,
        "message": message,
        "repo_path": str(repo_path),
        "repo_auto_detected": auto_detected,
        "repo_exists": repo_exists,
        "pyproject_exists": pyproject_exists,
        "script_exists": script_exists,
        "uv_bin": uv_bin,
        "uv_available": uv_available,
        "browser_mode": clean_text(env.get("SAU_BROWSER_MODE", "")) or "headless",
        "xhs_base_url": clean_text(env.get("SAU_XHS_CREATOR_BASE_URL", "")) or "https://creator.xiaohongshu.com",
        "patchright_download_host": _normalized_patchright_host(str(env.get("SAU_PATCHRIGHT_DOWNLOAD_HOST", ""))),
        "local_chrome_path": _detect_local_chrome(),
    }


def _release_description(project: dict[str, Any], template: dict[str, Any], strategy: dict[str, Any], summary: dict[str, Any]) -> str:
    topic = clean_text(project.get("topic_name") or "")
    publish_title = clean_text(summary.get("publish_title") or summary.get("video_title") or topic)
    insights = strategy.get("insights") if isinstance(strategy.get("insights"), dict) else {}
    core = clean_text(str(insights.get("core_viewpoint") or ""))
    hook = clean_text(str(insights.get("interaction_hook") or ""))
    lines = [line for line in [publish_title, core, hook] if line]
    if not lines:
        lines = [topic or clean_text(template.get("name") or template.get("key") or "短片工坊")]
    return "\n".join(lines[:3]).strip()


def _release_tags_csv(raw: str) -> str:
    tokens = re.findall(r"#?([\u4e00-\u9fffA-Za-z0-9_]{2,})", raw or "")
    seen: set[str] = set()
    tags: list[str] = []
    for item in tokens:
        cleaned = clean_text(item).lstrip("#")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        tags.append(cleaned)
    return ",".join(tags[:12])


def _file_info(project_id: int, relative_path: str) -> dict[str, Any] | None:
    path = storage.project_file(project_id, relative_path)
    if not path.exists() or not path.is_file():
        return None
    stat = path.stat()
    return {
        "relative_path": relative_path,
        "name": path.name,
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
        "url": f"/data/projects/{project_id}/{relative_path}",
        "absolute_path": str(path.resolve()),
    }


def latest_login_qrcode(project_id: int, platform: str, account_name: str, env: dict[str, str] | None = None) -> dict[str, Any] | None:
    env = env or runtime_env()
    repo_path, _ = detect_repo(env)
    cookie_dir = repo_path / "cookies"
    if not cookie_dir.exists():
        return None
    normalized_platform = clean_text(platform).lower() or "douyin"
    normalized_alias = clean_text(account_name) or "default"
    candidates = sorted(
        cookie_dir.glob(f"{normalized_platform}_{normalized_alias}_login_qrcode_*.png"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    path = candidates[0]
    stat = path.stat()
    return {
        "name": path.name,
        "absolute_path": str(path.resolve()),
        "modified_at": stat.st_mtime,
        "size": stat.st_size,
        "url": (
            f"/api/projects/{project_id}/release-automation/qrcode"
            f"?platform={normalized_platform}&account_name={normalized_alias}&v={int(stat.st_mtime * 1000)}"
        ),
    }


def _release_draft_defaults(project_id: int, task: dict[str, Any] | None = None) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    summary = storage.get_summary(project_id)
    strategy = storage.read_json(storage.project_file(project_id, "content_strategy.json"), {})
    status = probe()
    default_platform = clean_text(task.get("platform", "")) if task else ""
    default_alias = clean_text(task.get("account_name", "")) if task else ""
    return {
        "platform": default_platform or "douyin",
        "account_name": default_alias or "default",
        "title": clean_text(summary.get("publish_title") or summary.get("video_title") or project.get("topic_name") or ""),
        "description": _release_description(project, template, strategy if isinstance(strategy, dict) else {}, summary if isinstance(summary, dict) else {}),
        "tags": _release_tags_csv(str(template.get("release_tags") or "")),
        "schedule": "",
        "headed": (status.get("browser_mode") == "headed"),
        "debug": False,
    }


def _normalize_release_draft(payload: dict[str, Any] | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(fallback or {})
    incoming = payload or {}
    return {
        "platform": clean_text(str(incoming.get("platform", base.get("platform", "douyin")) or "")) or "douyin",
        "account_name": clean_text(str(incoming.get("account_name", base.get("account_name", "default")) or "")) or "default",
        "title": _with_text_fallback(incoming.get("title", ""), base.get("title", "")),
        "description": _with_text_fallback(incoming.get("description", ""), base.get("description", ""), multiline=True),
        "tags": _with_text_fallback(incoming.get("tags", ""), base.get("tags", "")),
        "schedule": clean_text(str(incoming.get("schedule", base.get("schedule", "")) or "")),
        "headed": bool(incoming.get("headed", base.get("headed", False))),
        "debug": bool(incoming.get("debug", base.get("debug", False))),
    }


def load_draft(project_id: int, task: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = _release_draft_defaults(project_id, task)
    saved = storage.read_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_DRAFT_NAME), {})
    if not isinstance(saved, dict):
        saved = {}
    return _normalize_release_draft(saved, fallback)


def save_draft(project_id: int, payload: dict[str, Any] | None, task: dict[str, Any] | None = None) -> dict[str, Any]:
    current = load_draft(project_id, task)
    normalized = _normalize_release_draft(payload, current)
    storage.write_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_DRAFT_NAME), normalized)
    return normalized


def list_account_aliases(platform: str, env: dict[str, str] | None = None) -> list[str]:
    env = env or runtime_env()
    repo_path, _ = detect_repo(env)
    cookie_dir = repo_path / "cookies"
    normalized_platform = clean_text(platform).lower() or "douyin"
    aliases: set[str] = {"default"}
    if cookie_dir.exists():
        prefix = f"{normalized_platform}_"
        for path in cookie_dir.glob(f"{normalized_platform}_*.json"):
            stem = path.stem
            if not stem.startswith(prefix):
                continue
            alias = clean_text(stem[len(prefix):])
            if alias:
                aliases.add(alias)
    return sorted(aliases, key=lambda item: (item != "default", item.lower()))


def _account_file_path(repo_path: Path, platform: str, account_name: str) -> Path:
    return repo_path / "cookies" / f"{platform}_{account_name}.json"


def _load_storage_state_cookies(account_file: Path) -> dict[str, str]:
    if not account_file.exists():
        return {}
    try:
        payload = json.loads(account_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cookies: dict[str, str] = {}
    for item in payload.get("cookies", []):
        if not isinstance(item, dict):
            continue
        name = clean_text(str(item.get("name", "")))
        if not name:
            continue
        cookies[name] = str(item.get("value", ""))
    return cookies


def _http_json(url: str, cookie_header: str, referer: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": ACCOUNT_PROBE_USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Referer": referer,
            "Cookie": cookie_header,
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read().decode("utf-8", errors="replace")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("账号接口返回了非对象数据")
    return payload


def _deep_find_string(node: Any, keys: tuple[str, ...]) -> str:
    wanted = {item.lower() for item in keys}
    queue: list[Any] = [node]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                key_text = str(key).lower()
                if key_text in wanted and isinstance(value, str):
                    candidate = clean_text(value)
                    if candidate:
                        return candidate
                queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)
    return ""


def _inspect_douyin_account(repo_path: Path, account_name: str) -> dict[str, Any]:
    account_file = _account_file_path(repo_path, "douyin", account_name)
    profile = {
        "platform": "douyin",
        "alias": account_name,
        "cookie_file": str(account_file),
        "cookie_exists": account_file.exists(),
        "status": "missing",
        "message": "还没有找到这个别名对应的抖音 cookie 文件。",
        "display_name": "",
        "account_id": "",
        "checked_at": storage.now_ts(),
        "source": "douyin_creator_api",
    }
    if not account_file.exists():
        return profile

    cookies = _load_storage_state_cookies(account_file)
    if not cookies:
        profile["status"] = "error"
        profile["message"] = "cookie 文件存在，但内容为空或无法读取。"
        return profile

    cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    endpoints = [
        "https://creator.douyin.com/web/api/media/user/info/",
        "https://creator.douyin.com/aweme/v1/creator/pc/user/info/",
        "https://creator.douyin.com/aweme/v1/creator/user/info/",
    ]
    last_message = ""
    for url in endpoints:
        try:
            payload = _http_json(url, cookie_header, "https://creator.douyin.com/")
        except Exception as exc:
            last_message = str(exc)
            continue
        status_code = payload.get("status_code")
        status_msg = clean_text(str(payload.get("status_msg", "")))
        if status_code == 0:
            display_name = _deep_find_string(
                payload,
                ("nickname", "nick_name", "display_name", "author_name", "user_name"),
            )
            account_id = _deep_find_string(
                payload,
                ("douyin_id", "unique_id", "short_id", "sec_uid", "uid", "user_id"),
            )
            profile["status"] = "connected"
            profile["display_name"] = display_name
            profile["account_id"] = account_id
            profile["message"] = "已登录抖音创作者后台。"
            if display_name and account_id:
                profile["message"] = f"已登录：{display_name}（{account_id}）"
            elif display_name:
                profile["message"] = f"已登录：{display_name}"
            elif account_id:
                profile["message"] = f"已登录：{account_id}"
            return profile
        if status_code == 8:
            profile["status"] = "not_logged_in"
            profile["message"] = status_msg or "当前 cookie 对应的抖音账号未登录。"
            return profile
        last_message = status_msg or f"账号接口返回状态码 {status_code}"

    profile["status"] = "error"
    profile["message"] = last_message or "读取抖音账号信息失败。"
    return profile


def inspect_account_profile(platform: str, account_name: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or runtime_env()
    repo_path, _ = detect_repo(env)
    alias = clean_text(account_name) or "default"
    normalized_platform = clean_text(platform).lower() or "douyin"
    base = {
        "platform": normalized_platform,
        "alias": alias,
        "cookie_file": str(_account_file_path(repo_path, normalized_platform, alias)),
        "cookie_exists": _account_file_path(repo_path, normalized_platform, alias).exists(),
        "status": "unsupported",
        "message": "当前平台暂未接入账号昵称识别。",
        "display_name": "",
        "account_id": "",
        "checked_at": storage.now_ts(),
        "source": "",
    }
    if normalized_platform == "douyin":
        return _inspect_douyin_account(repo_path, alias)
    return base


def snapshot(project_id: int) -> dict[str, Any]:
    project = storage.get_project(project_id)
    status = probe()
    task = storage.read_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_STATE_NAME), None)
    if not isinstance(task, dict):
        task = None
    draft = load_draft(project_id, task)
    files = {
        "final_video": _file_info(project_id, "releases/final-video.mp4"),
        "thumbnail_landscape": _file_info(project_id, "covers/cover_landscape.png"),
        "thumbnail_portrait": _file_info(project_id, "covers/cover_portrait.png"),
        "thumbnail_story": _file_info(project_id, "covers/cover_story.png"),
    }
    account_options = list_account_aliases(draft["platform"])
    if draft["account_name"] not in account_options:
        account_options = [draft["account_name"], *account_options]
    account = inspect_account_profile(draft["platform"], draft["account_name"])
    login_qrcode = latest_login_qrcode(project_id, draft["platform"], draft["account_name"])
    if login_qrcode and account.get("status") == "connected":
        task_action = clean_text(str((task or {}).get("action", ""))).lower()
        task_running = bool((task or {}).get("running"))
        if not (task_action == "login" and task_running):
            login_qrcode = None
    published_release = latest_published_release(project_id, task)
    return {
        "project_id": project_id,
        "project_mode": clean_text(project.get("template_mode") or "video"),
        "supported_platforms": SOCIAL_AUTO_UPLOAD_PLATFORMS,
        "probe": status,
        "draft": draft,
        "account_options": account_options,
        "account": account,
        "login_qrcode": login_qrcode,
        "last_published_release": published_release,
        "files": files,
        "task": task,
    }


def _state_seed(project_id: int, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"release-{project_id}-{storage.now_ms()}",
        "project_id": project_id,
        "action": action,
        "platform": clean_text(payload.get("platform", "")),
        "account_name": clean_text(payload.get("account_name", "")) or "default",
        "status": "running",
        "running": True,
        "started_at": storage.now_ts(),
        "finished_at": None,
        "command": "",
        "cwd": "",
        "log": "",
        "error": "",
        "result": {},
    }


def _datetime_local_to_cli(value: str) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    return raw.replace("T", " ")


def _project_files_or_error(project_id: int) -> dict[str, Any]:
    files = snapshot(project_id)["files"]
    if not files.get("final_video"):
        raise RuntimeError("当前项目还没有 final-video.mp4，请先完成成片合成。")
    return files


def _platform_label(platform: str) -> str:
    normalized = clean_text(platform).lower()
    for item in SOCIAL_AUTO_UPLOAD_PLATFORMS:
        if clean_text(str(item.get("key", ""))).lower() == normalized:
            return str(item.get("label") or item.get("key") or normalized)
    return normalized or "social-auto-upload"


def _compare_key(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", clean_text(value).lower())


def _usable_title(value: str) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    return cleaned if _compare_key(cleaned) else ""


def _douyin_work_list_url() -> str:
    return f"{DOUYIN_WORK_LIST_ENDPOINT}?{urllib.parse.urlencode(DOUYIN_WORK_LIST_PARAMS)}"


def _load_douyin_recent_works(repo_path: Path, account_name: str) -> list[dict[str, Any]]:
    account_file = _account_file_path(repo_path, "douyin", account_name)
    cookies = _load_storage_state_cookies(account_file)
    if not cookies:
        return []
    cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    payload = _http_json(_douyin_work_list_url(), cookie_header, AUTO_RELEASE_ENTRY_URLS["douyin"])
    status_code = payload.get("status_code")
    if status_code not in (None, 0):
        raise RuntimeError(clean_text(str(payload.get("status_msg") or f"抖音作品列表接口返回状态码 {status_code}")))
    works = payload.get("aweme_list")
    if isinstance(works, list):
        return [item for item in works if isinstance(item, dict)]
    works = payload.get("items")
    if isinstance(works, list):
        return [item for item in works if isinstance(item, dict)]
    return []


def _douyin_work_title(work: dict[str, Any]) -> str:
    share_info = work.get("share_info") if isinstance(work.get("share_info"), dict) else {}
    next_info = work.get("next_info") if isinstance(work.get("next_info"), dict) else {}
    return clean_text(
        str(
            work.get("item_title")
            or next_info.get("item_title")
            or work.get("description")
            or work.get("desc")
            or share_info.get("share_title")
            or ""
        )
    )


def _score_douyin_work(work: dict[str, Any], target_title: str, finished_at: float) -> tuple[int, float, float]:
    title_key = _compare_key(target_title)
    candidate_keys = [
        _compare_key(_douyin_work_title(work)),
        _compare_key(str(work.get("description") or "")),
        _compare_key(str(work.get("desc") or "")),
    ]
    title_score = 0
    if title_key:
        for candidate in candidate_keys:
            if not candidate:
                continue
            if candidate == title_key:
                title_score = max(title_score, 100)
            elif title_key in candidate or candidate in title_key:
                title_score = max(title_score, 88)
            elif len(title_key) >= 6 and title_key[:6] in candidate:
                title_score = max(title_score, 72)

    created_at = float(work.get("create_time") or 0)
    delta = abs(finished_at - created_at) if finished_at and created_at else float("inf")
    time_score = 0
    if delta <= 300:
        time_score = 50
    elif delta <= 1800:
        time_score = 42
    elif delta <= 7200:
        time_score = 30
    elif delta <= 86400:
        time_score = 12

    status = work.get("status") if isinstance(work.get("status"), dict) else {}
    public_score = 5 if not status.get("is_private") and status.get("allow_share", True) else 0
    return title_score + time_score + public_score, -delta, created_at


def _discover_douyin_release(project_id: int, task: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    repo_path, _ = detect_repo()
    account_name = clean_text(task.get("account_name", "") or payload.get("account_name", "")) or "default"
    project = storage.get_project(project_id)
    summary = storage.get_summary(project_id)
    target_title = clean_text(
        payload.get("title", "")
        or summary.get("publish_title", "")
        or summary.get("video_title", "")
        or project.get("topic_name", "")
    )
    finished_at = float(task.get("finished_at") or storage.now_ts())
    works = _load_douyin_recent_works(repo_path, account_name)
    if not works:
        return None
    best = max(works, key=lambda item: _score_douyin_work(item, target_title, finished_at))
    score, _, _ = _score_douyin_work(best, target_title, finished_at)
    if score <= 0:
        return None

    author = best.get("author") if isinstance(best.get("author"), dict) else {}
    status = best.get("status") if isinstance(best.get("status"), dict) else {}
    share_url = clean_text(str(best.get("share_url") or ""))
    aweme_id = clean_text(str(best.get("aweme_id") or best.get("id") or best.get("item_id") or ""))
    if not share_url and aweme_id:
        share_url = f"https://www.douyin.com/video/{aweme_id}"
    if not share_url:
        return None

    return {
        "url": share_url,
        "title": _douyin_work_title(best) or target_title,
        "description": clean_text(str(best.get("description") or best.get("desc") or "")),
        "published_at": float(best.get("create_time") or finished_at),
        "aweme_id": aweme_id,
        "account_display_name": clean_text(str(author.get("nickname") or "")),
        "account_id": clean_text(
            str(author.get("unique_id") or author.get("short_id") or author.get("sec_uid") or author.get("uid") or "")
        ),
        "is_private": bool(status.get("is_private")),
        "source": "douyin_creator_work_list",
    }


def backfill_release_link(project_id: int, task: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    platform = clean_text(task.get("platform", "") or payload.get("platform", "")).lower()
    fallback_url = AUTO_RELEASE_ENTRY_URLS.get(platform)
    if not fallback_url:
        return None

    account_name = clean_text(task.get("account_name", "") or payload.get("account_name", "")) or "default"
    account = inspect_account_profile(platform, account_name)
    project = storage.get_project(project_id)
    summary = storage.get_summary(project_id)
    discovered: dict[str, Any] | None = None
    if platform == "douyin":
        with contextlib.suppress(Exception):
            discovered = _discover_douyin_release(project_id, task, payload)
    discovered_title = _usable_title((discovered or {}).get("title", ""))
    title = clean_text(
        discovered_title
        or payload.get("title", "")
        or summary.get("publish_title", "")
        or summary.get("video_title", "")
        or project.get("topic_name", "")
    )
    url = clean_text((discovered or {}).get("url", "") or fallback_url)
    finished_at = float((discovered or {}).get("published_at") or task.get("finished_at") or storage.now_ts())
    account_display_name = clean_text((discovered or {}).get("account_display_name", "") or account.get("display_name", ""))
    account_id = clean_text((discovered or {}).get("account_id", "") or account.get("account_id", ""))
    finished_text = datetime.fromtimestamp(finished_at).strftime("%Y-%m-%d %H:%M")
    note_parts = [f"自动发布成功 {finished_text}"]
    if account_display_name:
        note_parts.append(f"账号 {account_display_name}")
    else:
        note_parts.append(f"别名 {account_name}")
    if title:
        note_parts.append(title)
    note = " · ".join(note_parts)

    links = storage.get_release_links(project_id)
    item = next((entry for entry in links if str(entry.get("task_id") or "") == str(task.get("id") or "")), None)
    link_payload = {
        "platform": _platform_label(platform),
        "url": url,
        "entry_url": fallback_url,
        "note": note,
        "title": title,
        "source": clean_text(str((discovered or {}).get("source") or "social_auto_upload")),
        "task_id": task.get("id"),
        "account_name": account_name,
        "account_display_name": account_display_name,
        "account_id": account_id,
        "aweme_id": clean_text(str((discovered or {}).get("aweme_id") or "")),
        "published_at": finished_at,
        "created_at": finished_at,
    }
    if item is None:
        item = {"id": storage.next_release_id(), **link_payload}
        links.append(item)
    else:
        item.update(link_payload)
    storage.save_release_links(project_id, links)
    return item


def latest_published_release(project_id: int, task: dict[str, Any] | None = None) -> dict[str, Any] | None:
    links = storage.get_release_links(project_id)
    if not isinstance(links, list) or not links:
        return None
    task_id = clean_text(str(task.get("id", ""))) if task else ""
    if task_id:
        for item in links:
            if clean_text(str(item.get("task_id", ""))) == task_id:
                return item
    return max(links, key=lambda item: float(item.get("published_at") or item.get("created_at") or 0))


def _download_repo_archive(target_dir: Path) -> Path:
    if target_dir.exists():
        raise RuntimeError(f"目标路径已存在，无法自动下载仓库：{target_dir}")
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sau-bootstrap-", dir=str(target_dir.parent)) as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / "social-auto-upload.zip"
        with urllib.request.urlopen(SOCIAL_AUTO_UPLOAD_ZIP_URL, timeout=120) as response:
            archive_path.write_bytes(response.read())
        extract_root = temp_root / "extract"
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_root)
        repo_root = next(
            (item for item in extract_root.iterdir() if item.is_dir() and (item / "pyproject.toml").exists()),
            None,
        )
        if repo_root is None:
            raise RuntimeError("下载的 social-auto-upload 压缩包结构异常，缺少 pyproject.toml。")
        shutil.move(str(repo_root), str(target_dir))
    if not (target_dir / "pyproject.toml").exists():
        raise RuntimeError("social-auto-upload 仓库下载完成，但目录内容不完整。")
    return target_dir


def _ensure_repo_conf(repo_path: Path) -> Path:
    conf_path = repo_path / "conf.py"
    if conf_path.exists():
        text = conf_path.read_text(encoding="utf-8")
    else:
        template_path = repo_path / "conf.example.py"
        if not template_path.exists():
            raise RuntimeError("social-auto-upload 仓库缺少 conf.example.py，无法自动初始化 conf.py。")
        shutil.copyfile(template_path, conf_path)
        text = conf_path.read_text(encoding="utf-8")
    chrome_path = _detect_local_chrome()
    if chrome_path:
        updated = re.sub(
            r'LOCAL_CHROME_PATH\s*=\s*".*?"',
            f'LOCAL_CHROME_PATH = "{chrome_path}"',
            text,
            count=1,
        )
        if updated != text:
            conf_path.write_text(updated, encoding="utf-8")
    return conf_path


class SocialAutoUploadRuntime:
    def __init__(self) -> None:
        self.task: asyncio.Task[None] | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.state: dict[str, Any] | None = None

    def latest(self, project_id: int) -> dict[str, Any] | None:
        if self.state and int(self.state.get("project_id") or 0) == int(project_id):
            return self.state
        payload = storage.read_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_STATE_NAME), None)
        if not isinstance(payload, dict):
            return None
        if payload.get("running") and (not self.task or self.task.done()):
            payload = dict(payload)
            payload["running"] = False
            payload["status"] = "interrupted"
            payload["finished_at"] = payload.get("finished_at") or storage.now_ts()
            log_text = str(payload.get("log") or "").rstrip()
            suffix = "[release] 上一次自动发布任务在服务重启前中断，请重新发起。"
            payload["log"] = f"{log_text}\n{suffix}".strip() if log_text else suffix
            storage.write_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_STATE_NAME), payload)
        return payload

    async def start(self, project_id: int, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.task and not self.task.done():
            raise RuntimeError("已有自动发布任务正在运行，请等待完成或先取消。")
        storage.get_project(project_id)
        saved_draft = load_draft(project_id)
        if action != "prepare":
            saved_draft = save_draft(project_id, payload)
        self.state = _state_seed(project_id, action, payload)
        self.state["draft"] = saved_draft
        self._save()
        self.task = asyncio.create_task(self._run(project_id, action, payload))
        return self.state

    async def cancel(self) -> dict[str, Any]:
        if self.process and self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.process.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.process.wait(), timeout=10)
        if not self.task or self.task.done():
            return {"already_done": True}
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task
        return {"already_done": False}

    def _save(self) -> None:
        if not self.state:
            return
        project_id = int(self.state.get("project_id") or 0)
        if project_id > 0:
            storage.write_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_STATE_NAME), self.state)

    def _log(self, line: str) -> None:
        if not self.state:
            return
        text = line.replace("\r", "").strip()
        existing = str(self.state.get("log") or "").rstrip()
        self.state["log"] = f"{existing}\n{text}".strip() if existing else text
        self._save()

    def _base_env(self) -> dict[str, str]:
        status = probe()
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        host = _normalized_patchright_host(str(status.get("patchright_download_host") or ""))
        if host:
            env["PLAYWRIGHT_DOWNLOAD_HOST"] = host
        if status.get("xhs_base_url"):
            env["XHS_CREATOR_BASE_URL"] = str(status["xhs_base_url"])
        return env

    def _resolve_commands(self, project_id: int, action: str, payload: dict[str, Any]) -> tuple[Path, list[list[str]]]:
        normalized_payload = _normalize_release_draft(payload, _release_draft_defaults(project_id, self.state or None))
        status = probe()
        repo_path = Path(str(status.get("repo_path") or ""))
        if not repo_path.exists() or not (repo_path / "pyproject.toml").exists():
            raise RuntimeError("没有找到可用的 social-auto-upload 仓库，请先在配置页填写正确路径。")
        uv_bin = str(status.get("uv_bin") or "uv")
        if not (shutil.which(uv_bin) or Path(uv_bin).exists()):
            raise RuntimeError("本机没有可用的 uv 命令，请先安装 uv 或在配置页填写 uv 的绝对路径。")

        platform = clean_text(normalized_payload.get("platform", "")).lower()
        account_name = clean_text(normalized_payload.get("account_name", "")) or "default"
        headed = bool(normalized_payload.get("headed"))
        debug = bool(normalized_payload.get("debug"))

        def browser_args() -> list[str]:
            args: list[str] = []
            args.append("--headed" if headed else "--headless")
            if debug:
                args.append("--debug")
            return args

        if action == "prepare":
            commands = [[uv_bin, "sync"]]
            if not _detect_local_chrome():
                commands.append([uv_bin, "run", "patchright", "install", "chromium"])
            commands.append([uv_bin, "run", "python", "sau_cli.py", "--help"])
            return repo_path, commands

        supported = {item["key"] for item in SOCIAL_AUTO_UPLOAD_PLATFORMS}
        if platform not in supported:
            raise RuntimeError(f"暂不支持平台：{platform or '未填写'}")

        if action == "login":
            login_args = ["--headed"]
            if debug:
                login_args.append("--debug")
            return repo_path, [[uv_bin, "run", "python", "sau_cli.py", platform, "login", "--account", account_name, *login_args]]

        if action == "check":
            return repo_path, []

        if action != "publish":
            raise RuntimeError(f"未知动作：{action}")

        files = _project_files_or_error(project_id)
        final_video = files["final_video"]
        title = clean_text(normalized_payload.get("title", "")) or clean_text(storage.get_project(project_id).get("topic_name") or "")
        description = clean_text(normalized_payload.get("description", ""))
        tags = clean_text(normalized_payload.get("tags", ""))
        schedule = _datetime_local_to_cli(str(normalized_payload.get("schedule", "")))
        command = [
            uv_bin,
            "run",
            "python",
            "sau_cli.py",
            platform,
            "upload-video",
            "--account",
            account_name,
            "--file",
            str(final_video["absolute_path"]),
            "--title",
            title,
            "--desc",
            description,
            *browser_args(),
        ]
        if tags:
            command.extend(["--tags", tags])
        if schedule:
            command.extend(["--schedule", schedule])

        landscape = files.get("thumbnail_landscape")
        portrait = files.get("thumbnail_portrait")
        if platform == "douyin":
            if landscape:
                command.extend(["--thumbnail-landscape", str(landscape["absolute_path"])])
            if portrait:
                command.extend(["--thumbnail-portrait", str(portrait["absolute_path"])])
        else:
            thumbnail = portrait or landscape
            if thumbnail:
                command.extend(["--thumbnail", str(thumbnail["absolute_path"])])
        return repo_path, [command]

    async def _run(self, project_id: int, action: str, payload: dict[str, Any]) -> None:
        assert self.state is not None
        try:
            normalized_payload = _normalize_release_draft(payload, _release_draft_defaults(project_id, self.state))
            self.state["payload"] = normalized_payload
            status = probe()
            repo_path = Path(str(status.get("repo_path") or ""))
            if not repo_path.exists():
                self._log(f"[release] 未找到 social-auto-upload 仓库，正在自动下载到 {repo_path}")
                await asyncio.to_thread(_download_repo_archive, repo_path)
                self._log("[release] social-auto-upload 仓库下载完成")
            if repo_path.exists() and (repo_path / "pyproject.toml").exists() and not (repo_path / "conf.py").exists():
                await asyncio.to_thread(_ensure_repo_conf, repo_path)
                self._log("[release] 已自动创建 social-auto-upload/conf.py")
            elif repo_path.exists() and (repo_path / "pyproject.toml").exists():
                await asyncio.to_thread(_ensure_repo_conf, repo_path)
            if action == "prepare":
                chrome_path = _detect_local_chrome()
                if chrome_path:
                    self._log(f"[release] 已检测到本机 Chrome，准备流程将直接复用：{chrome_path}")
            if action == "login":
                self._log("[release] 登录动作将强制打开可见浏览器，方便扫码。")
            if action == "check":
                platform = clean_text(normalized_payload.get("platform", "")).lower()
                account_name = clean_text(normalized_payload.get("account_name", "")) or "default"
                self.state["cwd"] = str(repo_path)
                self.state["command"] = "inspect_account_profile"
                self._save()
                account = await asyncio.to_thread(inspect_account_profile, platform, account_name)
                self.state["result"] = {"account": account}
                display_name = clean_text(str(account.get("display_name") or account.get("account_id") or ""))
                if account.get("status") == "connected":
                    summary = display_name or clean_text(str(account.get("message") or "已登录"))
                    self._log(f"[release] 账号检测通过: {summary}")
                    self.state["status"] = "succeeded"
                    self.state["running"] = False
                    self.state["finished_at"] = storage.now_ts()
                    self._save()
                    return
                message = clean_text(str(account.get("message") or "")) or "账号未登录或 cookie 已失效。"
                raise RuntimeError(message)
            cwd, commands = self._resolve_commands(project_id, action, normalized_payload)
            if action == "publish":
                self._log(
                    "[release] publish payload"
                    f" title={_debug_text(normalized_payload.get('title', ''))}"
                    f" desc={_debug_text(normalized_payload.get('description', ''))}"
                    f" tags={_debug_text(normalized_payload.get('tags', ''))}"
                )
            self.state["cwd"] = str(cwd)
            self._save()
            for index, command in enumerate(commands, start=1):
                self.state["command"] = subprocess.list2cmdline(command)
                self._save()
                self._log(f"[release] step {index}/{len(commands)} -> {self.state['command']}")
                self.process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(cwd),
                    env=self._base_env(),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                assert self.process.stdout is not None
                while True:
                    line = await self.process.stdout.readline()
                    if not line:
                        break
                    self._log(line.decode("utf-8", errors="replace").rstrip())
                return_code = await self.process.wait()
                self.process = None
                if return_code != 0:
                    raise RuntimeError(f"命令退出码 {return_code}")
            self.state["status"] = "succeeded"
            self.state["running"] = False
            self.state["finished_at"] = storage.now_ts()
            result = dict(snapshot(project_id)["files"])
            if action == "publish":
                published_link = backfill_release_link(project_id, self.state, payload)
                if published_link:
                    result["published_release"] = published_link
                    self._log(f"[release] 已自动回填投放链接: {published_link['url']}")
            self.state["result"] = result
            self._log("[release] 任务执行完成")
            self._save()
        except asyncio.CancelledError:
            self.state["status"] = "cancelled"
            self.state["running"] = False
            self.state["finished_at"] = storage.now_ts()
            self._log("[release] 用户已取消自动发布任务")
            self._save()
            raise
        except Exception as exc:
            self.state["status"] = "failed"
            self.state["running"] = False
            self.state["finished_at"] = storage.now_ts()
            self.state["error"] = str(exc)
            self._log(f"[release] 任务失败：{exc}")
            self._save()
        finally:
            self.process = None
