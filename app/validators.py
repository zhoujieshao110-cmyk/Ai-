from __future__ import annotations

import json
import math
import struct
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any

from . import storage


def _services():
    from . import services

    return services


def _release_automation():
    from . import release_automation

    return release_automation


ARK_MODEL_ALIASES = {
    "seedream-5.0": [
        "seedream-5.0",
        "doubao-seedream-5.0-lite",
        "doubao-seedream-5-0-260128",
    ],
    "doubao-seedream-5-0-260128": [
        "seedream-5.0",
        "doubao-seedream-5.0-lite",
        "doubao-seedream-5-0-260128",
    ],
    "doubao-seedream-5.0-lite": [
        "seedream-5.0",
        "doubao-seedream-5.0-lite",
        "doubao-seedream-5-0-260128",
    ],
    "seedream-4.5": [
        "seedream-4.5",
        "doubao-seedream-4.5",
    ],
    "doubao-seedream-4.5": [
        "seedream-4.5",
        "doubao-seedream-4.5",
    ],
}


def _request_json(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method.upper())
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="ignore")
            return {"status": response.status, "text": text, "ok": True}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="ignore")
        return {"status": exc.code, "text": text, "ok": False}
    except Exception as exc:
        return {"status": None, "text": "", "ok": False, "error": str(exc)}


def _result(section_key: str, status: str, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "section": section_key,
        "status": status,
        "message": message,
        "detail": detail or {},
        "checked_at": time.time(),
    }


def _parse_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text or "{}")
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _contains_domain_route_error(text: str) -> bool:
    haystack = (text or "").lower()
    return "域名解析错误" in (text or "") or "domain" in haystack and "error" in haystack


def _merged_env(values: dict[str, str]) -> dict[str, str]:
    env = dict(storage.DEFAULT_ENV)
    env.update(values)
    if not env.get("VOLC_ASR_APP_KEY"):
        env["VOLC_ASR_APP_KEY"] = env.get("VOLC_TTS_APP_KEY", "")
    if not env.get("VOLC_ASR_ACCESS_KEY"):
        env["VOLC_ASR_ACCESS_KEY"] = env.get("VOLC_TTS_ACCESS_KEY", "")
    return env


def _bridge_error_result(section_key: str, label: str, exc: Exception) -> dict[str, Any]:
    message = str(exc).strip() or f"{label} 校验失败。"
    lower = message.lower()
    auth_markers = ("unauthorized", "forbidden", "auth", "access key", "app key", "permission", "denied")
    soft_markers = ("resource", "speaker", "format", "param", "request", "empty", "invalid")
    if any(marker in lower for marker in auth_markers):
        status = "error"
        summary = f"{label} 密钥无效或没有权限：{message}"
    elif any(marker in lower for marker in soft_markers):
        status = "warning"
        summary = f"{label} 已打到官方接口，但业务参数还需要调整：{message}"
    else:
        status = "error"
        summary = f"{label} 校验失败：{message}"
    return _result(section_key, status, summary, {"error": message})


def _write_test_wave(path: Path, duration_sec: float = 1.6, sample_rate: int = 16000) -> None:
    frames: list[bytes] = []
    total = int(duration_sec * sample_rate)
    for index in range(total):
        t = index / sample_rate
        amplitude = 0.25 if 0.2 <= t <= duration_sec - 0.2 else 0.0
        sample = int(32767 * amplitude * math.sin(2 * math.pi * 440 * t))
        frames.append(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(frames))


def validate_deepseek(values: dict[str, str]) -> dict[str, Any]:
    api_key = values.get("DEEPSEEK_API_KEY", "").strip()
    model = values.get("DEEPSEEK_MODEL", "").strip()
    base_url = (values.get("DEEPSEEK_BASE_URL", "") or "https://api.deepseek.com").rstrip("/")
    if not api_key:
        return _result("deepseek", "unconfigured", "还没有填写 DeepSeek API Key。")

    response = _request_json(
        "GET",
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    if response["status"] == 200:
        payload = _parse_json(response["text"])
        models = [item.get("id", "") for item in payload.get("data", []) if isinstance(item, dict)]
        if model and models and model not in models:
            return _result(
                "deepseek",
                "warning",
                f"DeepSeek 鉴权通过，但当前模型 {model} 不在官方返回列表里。",
                {"models": models[:20]},
            )
        return _result(
            "deepseek",
            "success",
            f"DeepSeek 校验通过，当前模型 {model or '未指定'} 可以使用。",
            {"models": models[:20]},
        )
    if response["status"] in {401, 403}:
        return _result("deepseek", "error", "DeepSeek API Key 无效，官方接口返回了鉴权失败。")
    return _result(
        "deepseek",
        "error",
        f"DeepSeek 校验失败：HTTP {response['status'] or 'ERR'}。",
        {"body": response.get("text", "")[:300], "error": response.get("error", "")},
    )


def validate_tavily(values: dict[str, str]) -> dict[str, Any]:
    api_key = values.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return _result("tavily", "unconfigured", "Tavily API Key 为空，当前会回退到 DuckDuckGo 搜索。")

    response = _request_json(
        "POST",
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        payload={"query": "Short Video Studio validation", "max_results": 1, "search_depth": "basic"},
    )
    if response["status"] == 200:
        return _result("tavily", "success", "Tavily 校验通过，可以联网补充参考资料。")
    if response["status"] in {401, 403}:
        return _result("tavily", "error", "Tavily API Key 无效，官方接口返回了鉴权失败。")
    return _result(
        "tavily",
        "error",
        f"Tavily 校验失败：HTTP {response['status'] or 'ERR'}。",
        {"body": response.get("text", "")[:300], "error": response.get("error", "")},
    )


def validate_ark_image(values: dict[str, str]) -> dict[str, Any]:
    api_key = values.get("ARK_API_KEY", "").strip()
    model = values.get("ARK_IMAGE_MODEL", "").strip()
    if not api_key:
        return _result("ark_image", "unconfigured", "还没有填写火山方舟 API 密钥。")

    response = _request_json(
        "GET",
        "https://ark.cn-beijing.volces.com/api/v3/models",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    if response["status"] == 200:
        payload = _parse_json(response["text"])
        models = [item.get("id", "") for item in payload.get("data", []) if isinstance(item, dict)]
        aliases = set(ARK_MODEL_ALIASES.get(model, [model]))
        fuzzy_matches = [item for item in models if any(alias and alias in item for alias in aliases)]
        if model and models and (model in models or fuzzy_matches):
            actual = model if model in models else fuzzy_matches[0]
            detail = {"models": models[:20]}
            if actual != model:
                detail["matched_model"] = actual
            return _result("ark_image", "success", f"火山方舟校验通过，文生图模型 {actual} 可用。", detail)
        if model and models:
            return _result(
                "ark_image",
                "warning",
                f"方舟鉴权通过，但当前模型 {model} 不在返回列表里。",
                {"models": models[:20], "aliases": sorted(aliases)},
            )
        return _result("ark_image", "success", "火山方舟鉴权通过。", {"models": models[:20]})
    if response["status"] in {401, 403}:
        return _result("ark_image", "error", "火山方舟 API 密钥无效，官方接口返回了鉴权失败。")
    return _result(
        "ark_image",
        "error",
        f"火山方舟校验失败：HTTP {response['status'] or 'ERR'}。",
        {"body": response.get("text", "")[:300], "error": response.get("error", "")},
    )


def validate_apiyi_image(values: dict[str, str]) -> dict[str, Any]:
    api_key = values.get("APIYI_API_KEY", "").strip()
    services = _services()
    base_url = services.normalize_openai_compatible_base_url(values.get("APIYI_BASE_URL", "") or "")
    model = services.resolve_apiyi_image_model(values)
    if not api_key or not base_url:
        return _result("apiyi_image", "unconfigured", "请先填写 OpenAI 兼容 API 密钥和 Base URL。")

    response = _request_json(
        "GET",
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    if response["status"] == 200:
        payload = _parse_json(response["text"])
        models = [item.get("id", "") for item in payload.get("data", []) if isinstance(item, dict)]
        if model and models and model not in models:
            return _result(
                "apiyi_image",
                "warning",
                f"兼容接口已连通，但模型 {model} 不在 /models 返回列表里。",
                {"models": models[:30], "base_url": base_url},
            )
        return _result(
            "apiyi_image",
            "success",
            f"OpenAI 兼容文生图校验通过，当前模型 {model} 可以使用。",
            {"models": models[:30], "base_url": base_url},
        )
    if _contains_domain_route_error(response.get("text", "")):
        return _result(
            "apiyi_image",
            "error",
            "当前 Base URL 返回了“域名解析错误”，说明这条网关地址本身没有正确转发到 OpenAI 兼容接口。",
            {"base_url": base_url},
        )
    if response["status"] in {401, 403}:
        return _result("apiyi_image", "error", "OpenAI 兼容 API 密钥无效，接口返回了鉴权失败。")
    if response["status"] in {404, 405}:
        return _result(
            "apiyi_image",
            "warning",
            "当前服务没有开放 /models 校验接口，无法零成本验证密钥；保存后可以直接试跑场景图或封面图。",
            {"base_url": base_url, "model": model},
        )
    return _result(
        "apiyi_image",
        "error",
        f"OpenAI 兼容文生图校验失败：HTTP {response['status'] or 'ERR'}。",
        {"body": response.get("text", "")[:300], "error": response.get("error", ""), "base_url": base_url},
    )


def validate_volc_tts(values: dict[str, str]) -> dict[str, Any]:
    app_key = values.get("VOLC_TTS_APP_KEY", "").strip()
    access_key = values.get("VOLC_TTS_ACCESS_KEY", "").strip()
    if not app_key or not access_key:
        return _result("doubao_tts", "unconfigured", "豆包 TTS 的 APP Key / Access Key 还没有填完整。")

    env = _merged_env(values)
    services = _services()
    try:
        with tempfile.TemporaryDirectory(prefix="svs-tts-validate-") as temp_dir:
            output_path = Path(temp_dir) / "tts-validate.mp3"
            result = services.run_original_bridge(
                "tts",
                {
                    "text": "你好，我们正在校验豆包双人播客接口。",
                    "output_path": str(output_path),
                    "dialogue_lines": [
                        {"speaker": "speaker_a", "text": "你好，我们正在校验豆包双人播客接口。"},
                        {"speaker": "speaker_b", "text": "如果这一步成功，就说明配音接口已经打通。"},
                    ],
                },
                env,
                timeout=180,
            )
            size = int(result.get("size", 0))
            return _result(
                "doubao_tts",
                "success",
                f"豆包 TTS 校验通过，已成功生成测试音频（{max(1, size // 1024)} KB）。",
                {
                    "size": size,
                    "resource_id": env.get("VOLC_TTS_RESOURCE_ID", ""),
                    "speaker_1": env.get("VOLC_TTS_SPEAKER_1", ""),
                    "speaker_2": env.get("VOLC_TTS_SPEAKER_2", ""),
                },
            )
    except Exception as exc:
        return _bridge_error_result("doubao_tts", "豆包 TTS", exc)


def _prepare_asr_sample(env: dict[str, str], temp_dir: Path) -> tuple[Path, str]:
    services = _services()
    tts_app_key = env.get("VOLC_TTS_APP_KEY", "").strip()
    tts_access_key = env.get("VOLC_TTS_ACCESS_KEY", "").strip()
    if tts_app_key and tts_access_key:
        try:
            audio_path = temp_dir / "asr-sample.mp3"
            services.run_original_bridge(
                "tts",
                {
                    "text": "你好，我们正在校验语音转字幕接口。",
                    "output_path": str(audio_path),
                    "dialogue_lines": [],
                },
                env,
                timeout=180,
            )
            if audio_path.exists() and audio_path.stat().st_size > 0:
                return audio_path, "tts"
        except Exception:
            pass

    audio_path = temp_dir / "asr-sample.wav"
    _write_test_wave(audio_path)
    return audio_path, "wave"


def validate_volc_asr(values: dict[str, str]) -> dict[str, Any]:
    env = _merged_env(values)
    services = _services()
    app_key = env.get("VOLC_ASR_APP_KEY", "").strip()
    access_key = env.get("VOLC_ASR_ACCESS_KEY", "").strip()
    reused_tts = not values.get("VOLC_ASR_APP_KEY", "").strip() and not values.get("VOLC_ASR_ACCESS_KEY", "").strip()
    if not app_key or not access_key:
        return _result("volc_asr", "unconfigured", "火山 ASR 的 APP Key / Access Key 还没有配置。")

    try:
        with tempfile.TemporaryDirectory(prefix="svs-asr-validate-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            audio_path, source = _prepare_asr_sample(env, temp_dir)
            srt_path = temp_dir / "asr-validate.srt"
            result = services.run_original_bridge(
                "asr",
                {
                    "audio_path": str(audio_path),
                    "srt_output": str(srt_path),
                    "dialogue_lines": ["你好，我们正在校验语音转字幕接口。"],
                },
                env,
                timeout=300,
            )
            utterances = result.get("utterances", []) if isinstance(result.get("utterances"), list) else []
            prefix = "火山 ASR 校验通过"
            if reused_tts:
                prefix += "（当前复用了 TTS 密钥）"
            if utterances:
                return _result(
                    "volc_asr",
                    "success",
                    f"{prefix}，已成功返回 {len(utterances)} 条识别结果。",
                    {
                        "mode": env.get("VOLC_ASR_MODE", ""),
                        "resource_id": env.get("VOLC_ASR_RESOURCE_ID", ""),
                        "sample_source": source,
                        "utterance_count": len(utterances),
                    },
                )
            return _result(
                "volc_asr",
                "success",
                f"{prefix}，接口已经打通，只是这次测试音频没有识别出可用文本。",
                {
                    "mode": env.get("VOLC_ASR_MODE", ""),
                    "resource_id": env.get("VOLC_ASR_RESOURCE_ID", ""),
                    "sample_source": source,
                    "utterance_count": 0,
                },
            )
    except Exception as exc:
        return _bridge_error_result("volc_asr", "火山 ASR", exc)


def validate_social_auto_upload(values: dict[str, str]) -> dict[str, Any]:
    env = dict(storage.DEFAULT_ENV)
    env.update(values)
    release_automation = _release_automation()
    status = release_automation.probe(env)
    return _result(
        "social_auto_upload",
        str(status.get("status") or "idle"),
        str(status.get("message") or "自动投放发布状态未知。"),
        status,
    )


SECTION_VALIDATORS = {
    "deepseek": validate_deepseek,
    "tavily": validate_tavily,
    "ark_image": validate_ark_image,
    "apiyi_image": validate_apiyi_image,
    "doubao_tts": validate_volc_tts,
    "volc_asr": validate_volc_asr,
    "social_auto_upload": validate_social_auto_upload,
}


def validate_sections(values: dict[str, str], targets: list[str] | None = None) -> dict[str, Any]:
    selected = targets or list(SECTION_VALIDATORS.keys())
    results: dict[str, Any] = {}
    cache = storage.load_validation_cache()
    cache_sections = cache.get("sections", {})
    for section_key in selected:
        validator = SECTION_VALIDATORS.get(section_key)
        if not validator:
            continue
        result = validator(values)
        results[section_key] = result
        cache_sections[section_key] = result
    cache["sections"] = cache_sections
    storage.save_validation_cache(cache)
    return {"sections": results}
