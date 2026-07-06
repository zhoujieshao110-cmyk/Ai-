from __future__ import annotations

import asyncio
import contextlib
import importlib
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import storage, validators


storage.bootstrap()

app = FastAPI(title="Short Video Studio Clone", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class LazyModule:
    def __init__(self, module_name: str):
        self.module_name = module_name
        self._module: Any | None = None

    def get(self) -> Any:
        if self._module is None:
            self._module = importlib.import_module(f".{self.module_name}", __package__)
        return self._module

    def __getattr__(self, name: str) -> Any:
        return getattr(self.get(), name)


class LazyRuntime:
    def __init__(self, module_name: str, class_name: str):
        self.module_name = module_name
        self.class_name = class_name
        self._instance: Any | None = None

    def get(self) -> Any:
        if self._instance is None:
            module = importlib.import_module(f".{self.module_name}", __package__)
            self._instance = getattr(module, self.class_name)()
        return self._instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self.get(), name)

    @property
    def loaded(self) -> bool:
        return self._instance is not None


services = LazyModule("services")
release_automation = LazyModule("release_automation")
package_builder = LazyModule("package_builder")
content_runtime = LazyRuntime("services", "ContentRuntime")
job_runtime = LazyRuntime("services", "JobRuntime")
auto_video_runtime = LazyRuntime("services", "AutoVideoRuntime")
release_runtime = LazyRuntime("release_automation", "SocialAutoUploadRuntime")
packaging_runtime = LazyRuntime("package_builder", "PackagingRuntime")


def tts_previews_static_root() -> Path:
    original = storage.APP_ROOT.parent / "_analysis" / "awesome_app_install" / "_internal" / "web" / "static" / "tts-previews"
    if original.exists():
        return original
    fallback = storage.DATA_ROOT / "tts-previews"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


class TemplatePayload(BaseModel):
    key: str
    name: str | None = None
    brand_name: str | None = None
    mode: str = "video"
    target_audience: str = ""
    channel_voice: str = ""
    visual_strategy: str = ""
    forbidden_rules: str = ""
    interaction_goal: str = ""
    topic_mining_hint: str = ""
    default_disclaimer: str = ""
    release_tags: str = ""
    cover_footnote_line_1: str = ""
    cover_footnote_line_2: str = ""
    cover_style: str = "default"
    voice_mode: str = ""
    tts_speaker_1: str = ""
    tts_speaker_2: str = ""
    tts_random_order: str | bool = ""
    tts_action: str | int = ""
    tts_speech_rate: float = 1.0
    generate_cover_landscape: bool = True
    generate_cover_portrait: bool = True
    prompt: str = ""
    version: str = ""


class ProjectCreatePayload(BaseModel):
    topic_name: str
    template: str


class TextPayload(BaseModel):
    brief: str | None = None
    content: str | None = None


class ProjectSettingsPayload(BaseModel):
    tavily_topic: str = "general"
    scene_count_mode: str = "auto"
    scene_count_fixed: int = 6


class ContentGeneratePayload(BaseModel):
    brief: str
    tavily_topic: str = "general"


class ToolPayload(BaseModel):
    brief: str | None = None
    content: str | None = None
    platform: str | None = None
    count: int = 6


class JobPayload(BaseModel):
    steps: list[str]
    allow_incomplete_video: bool = False


class AutoVideoPayload(BaseModel):
    count: int = 1
    tavily_topic: str = "general"
    mining_prompt: str = ""
    steps: list[str] | None = None
    auto_confirm_images: bool = True
    selected_topics: list[dict[str, Any]] | None = None


class AutoTopicMinePayload(BaseModel):
    count: int = 6
    tavily_topic: str = "general"
    mining_prompt: str = ""


class ImageReviewPayload(BaseModel):
    required: bool | None = None
    confirmed: bool | None = None


class ImageRegeneratePayload(BaseModel):
    kind: str
    target: str
    prompt: str = ""
    anchor_key: str = ""
    abstraction_level: str = "balanced"


class ReleasePayload(BaseModel):
    platform: str
    url: str
    note: str = ""
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    favorites: int | None = None
    completion_rate: float | None = None
    metrics_notes: str = ""


class ReleaseUpdatePayload(BaseModel):
    platform: str | None = None
    url: str | None = None
    note: str | None = None


class ReleaseMetricsPayload(BaseModel):
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    favorites: int | None = None
    completion_rate: float | None = None
    notes: str = ""


class ReleaseAutomationPayload(BaseModel):
    platform: str = "douyin"
    account_name: str = "default"
    title: str = ""
    description: str = ""
    tags: str = ""
    schedule: str = ""
    headed: bool = False
    debug: bool = False


class SecretsPayload(BaseModel):
    values: dict[str, str]


class SecretsValidatePayload(BaseModel):
    targets: list[str] | None = None


class PackagingBuildPayload(BaseModel):
    include_zip: bool = False


def ensure_project(project_id: int) -> dict[str, Any]:
    try:
        return storage.get_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def open_in_explorer(path: Path) -> dict[str, Any]:
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        return {"ok": True, "path": str(path)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"无法打开目录：{exc}") from exc


def open_path(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            raise FileNotFoundError(path)
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        return {"ok": True, "path": str(path)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"路径不存在：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"无法打开路径：{exc}") from exc


@app.get("/api/templates")
def api_templates() -> list[dict[str, Any]]:
    return storage.list_templates()


@app.post("/api/templates")
def api_create_template(payload: TemplatePayload) -> dict[str, Any]:
    try:
        return storage.save_template(payload.key, payload.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/templates/{key}")
def api_get_template(key: str) -> dict[str, Any]:
    return storage.get_template(key)


@app.put("/api/templates/{key}")
def api_update_template(key: str, payload: TemplatePayload) -> dict[str, Any]:
    try:
        return storage.save_template(key, payload.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/templates/{key}")
def api_delete_template(key: str, delete_projects: bool = False) -> dict[str, Any]:
    try:
        return storage.delete_template(key, delete_projects=delete_projects)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/templates/open-root")
def api_open_templates_root() -> dict[str, Any]:
    return open_in_explorer(storage.TEMPLATES_ROOT)


@app.post("/api/templates/{key}/open-folder")
def api_open_template_folder(key: str) -> dict[str, Any]:
    return open_in_explorer(storage.TEMPLATES_ROOT / key)


@app.post("/api/templates/{key}/open-products-folder")
def api_open_template_products_folder(key: str) -> dict[str, Any]:
    return open_in_explorer(storage.build_template_products_dir(key))


@app.post("/api/templates/{key}/auto-topics/mine")
async def api_mine_template_auto_topics(key: str, payload: AutoTopicMinePayload | None = None) -> dict[str, Any]:
    payload = payload or AutoTopicMinePayload()
    try:
        template = storage.get_template(key)
        result = await asyncio.to_thread(
            services.mine_channel_topic,
            template,
            payload.tavily_topic,
            payload.mining_prompt,
        )
        limit = max(1, min(int(payload.count or 6), 12))
        candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
        result["candidates"] = candidates[:limit]
        result["template_key"] = key
        result["count"] = len(result["candidates"])
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/templates/{key}/auto-video")
async def api_start_template_auto_video(key: str, payload: AutoVideoPayload | None = None) -> dict[str, Any]:
    payload = payload or AutoVideoPayload()
    try:
        storage.get_template(key)
        return await auto_video_runtime.start(
            key,
            count=payload.count,
            tavily_topic=payload.tavily_topic,
            mining_prompt=payload.mining_prompt,
            steps=payload.steps,
            auto_confirm_images=payload.auto_confirm_images,
            selected_topics=payload.selected_topics,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/auto-video/latest")
def api_latest_auto_video() -> dict[str, Any]:
    task = auto_video_runtime.latest()
    return {"task": task, "running": bool(task and task.get("running"))}


@app.post("/api/auto-video/cancel")
async def api_cancel_auto_video() -> dict[str, Any]:
    return await auto_video_runtime.cancel()


@app.delete("/api/orphan-templates/{key}")
def api_delete_orphan_template(key: str) -> dict[str, Any]:
    try:
        return storage.delete_orphan_template(key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects")
def api_projects(template: str | None = None) -> list[dict[str, Any]]:
    if template:
        return storage.projects_for_template(template)
    return storage.list_projects()


@app.post("/api/projects")
def api_create_project(payload: ProjectCreatePayload) -> dict[str, Any]:
    if not payload.topic_name.strip():
        raise HTTPException(status_code=400, detail="topic_name 不能为空")
    return storage.create_project(payload.topic_name, payload.template)


@app.get("/api/projects/{project_id}")
def api_get_project(project_id: int) -> dict[str, Any]:
    return ensure_project(project_id)


@app.delete("/api/projects/{project_id}")
def api_delete_project(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    storage.delete_project(project_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/content")
def api_project_content(project_id: int) -> dict[str, Any]:
    project = ensure_project(project_id)
    bundle = storage.content_bundle(project_id)
    content = str(bundle.get("content") or "")
    if content.strip():
        summary = services.summarize_content(content, project.get("template_mode", "video"))
        if summary != bundle.get("summary"):
            storage.save_summary(project_id, summary)
            bundle["summary"] = summary
    bundle["content_generate"] = content_runtime.status(project_id)
    return bundle


@app.get("/api/projects/{project_id}/content/references/{index}")
def api_project_reference(project_id: int, index: int) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.read_reference_preview(project_id, index)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail="reference not found") from exc


@app.post("/api/projects/{project_id}/brief")
def api_save_brief(project_id: int, payload: TextPayload) -> dict[str, Any]:
    ensure_project(project_id)
    storage.save_brief(project_id, payload.brief or "")
    return {"ok": True}


@app.post("/api/projects/{project_id}/content")
def api_save_content(project_id: int, payload: TextPayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    template = storage.get_template(project["template"])
    brief = storage.get_brief(project_id)
    references = storage.get_references(project_id)
    tavily_topic = storage.get_project_settings(project_id).get("tavily_topic", "general")
    storage.save_content(project_id, payload.content or "")
    summary = services.summarize_content(payload.content or "", project.get("template_mode", "video"))
    storage.save_summary(project_id, summary)
    artifacts = services.build_content_artifacts(project, template, brief, tavily_topic, references, payload.content or "")
    storage.write_json(storage.project_file(project_id, "content_strategy.json"), artifacts["strategy"])
    storage.write_json(storage.project_file(project_id, "content_audit.json"), artifacts["audit"])
    with contextlib.suppress(Exception):
        services.save_video_spec(project_id, payload.content or "")
    storage.save_report(project_id, "topic_score", artifacts["strategy"]["topic_score"])
    storage.save_report(project_id, "viral_doctor", artifacts["audit"]["viral_doctor"])
    storage.save_report(project_id, "title_cover_ab", artifacts["audit"]["title_cover_ab"])
    services.mark_image_review_dirty(project_id, "content.md 已手动修改，图片需要重新确认")
    return {"ok": True}


@app.post("/api/projects/{project_id}/project-settings")
def api_save_project_settings(project_id: int, payload: ProjectSettingsPayload) -> dict[str, Any]:
    ensure_project(project_id)
    storage.save_project_settings(project_id, payload.model_dump())
    result: dict[str, Any] | None = None
    if storage.get_content(project_id).strip():
        with contextlib.suppress(Exception):
            result = services.repair_image_prompt_section(project_id)
    return {
        "ok": True,
        "project_settings": storage.get_project_settings(project_id),
        "repair": result,
    }


@app.post("/api/projects/{project_id}/content/generate")
async def api_generate_content(project_id: int, payload: ContentGeneratePayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    template = storage.get_template(project["template"])
    storage.save_brief(project_id, payload.brief)
    storage.save_project_settings(project_id, {"tavily_topic": payload.tavily_topic})
    services.mark_image_review_dirty(project_id, "正在重新生成 content.md，图片需要重新确认")
    state = await content_runtime.start(project, template, payload.brief, payload.tavily_topic)
    return state


@app.get("/api/projects/{project_id}/content/generate/status")
def api_content_generate_status(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return content_runtime.status(project_id) or {"status": "idle"}


@app.post("/api/projects/{project_id}/content/generate/cancel")
async def api_cancel_content_generate(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return await content_runtime.cancel(project_id)


@app.post("/api/projects/{project_id}/content/tools/topic-score")
def api_topic_score(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    result = services.topic_score_report(project, payload.brief or storage.get_brief(project_id))
    path = storage.save_report(project_id, "topic_score", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/content/tools/topic-score")
def api_get_topic_score(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    report = storage.get_report(project_id, "topic_score")
    if not report:
        raise HTTPException(status_code=404, detail="暂无选题评分")
    return {"report_path": str(storage.report_path(project_id, "topic_score")), "result": report}


@app.post("/api/projects/{project_id}/content/tools/viral-doctor")
def api_viral_doctor(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    result = services.viral_doctor_report(project, payload.content or storage.get_content(project_id))
    path = storage.save_report(project_id, "viral_doctor", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/content/tools/viral-doctor")
def api_get_viral_doctor(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    report = storage.get_report(project_id, "viral_doctor")
    if not report:
        raise HTTPException(status_code=404, detail="暂无脚本体检报告")
    return {"report_path": str(storage.report_path(project_id, "viral_doctor")), "result": report}


@app.post("/api/projects/{project_id}/content/tools/viral-rewrite")
def api_viral_rewrite(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.optimize_project_content(project_id, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/content/tools/channel-history")
def api_channel_history(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.channel_history_report(project_id)
    path = storage.save_report(project_id, "channel_history", result)
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/content/tools/optimization-plan")
def api_creative_optimization_plan(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.creative_optimization_plan(project_id, payload.content)
    path = storage.save_report(project_id, "creative_optimization_plan", result)
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/content/tools/image-prompt-layers")
def api_image_prompt_layers(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.image_prompt_layer_report(project_id, payload.content)
    path = storage.save_report(project_id, "image_prompt_layers", result)
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/content/tools/video-spec")
def api_video_spec(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        result = services.save_video_spec(project_id, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = storage.project_file(project_id, "video_spec.json")
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/content/tools/rhythm")
def api_script_rhythm(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.script_rhythm_report(project_id, payload.content)
    path = storage.save_report(project_id, "script_rhythm", result)
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/content/tools/rhythm-enhance")
def api_script_rhythm_enhance(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.enhance_content_rhythm(project_id, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/content/tools/title-cover-ab")
def api_title_cover_ab(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    result = services.title_cover_ab_report(project, payload.content or storage.get_content(project_id), payload.count)
    path = storage.save_report(project_id, "title_cover_ab", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/content/tools/title-cover-ab")
def api_get_title_cover_ab(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    report = storage.get_report(project_id, "title_cover_ab")
    if not report:
        raise HTTPException(status_code=404, detail="暂无标题封面方案")
    return {"report_path": str(storage.report_path(project_id, "title_cover_ab")), "result": report}


@app.post("/api/projects/{project_id}/quality-gate")
def api_quality_gate(project_id: int, payload: TextPayload | None = None) -> dict[str, Any]:
    ensure_project(project_id)
    payload = payload or TextPayload()
    result = services.quality_gate_report(project_id, brief=payload.brief, content=payload.content)
    path = storage.save_report(project_id, "quality_gate", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/quality-gate")
def api_get_quality_gate(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    report = storage.get_report(project_id, "quality_gate")
    if not report:
        raise HTTPException(status_code=404, detail="暂无质量总检报告")
    return {"report_path": str(storage.report_path(project_id, "quality_gate")), "result": report}


@app.post("/api/projects/{project_id}/quality-gate/repair-image-prompts")
def api_repair_quality_image_prompts(project_id: int, payload: TextPayload | None = None) -> dict[str, Any]:
    ensure_project(project_id)
    payload = payload or TextPayload()
    result = services.repair_image_prompt_section(project_id, content=payload.content)
    return result


@app.get("/api/projects/{project_id}/scene-prompt")
def api_scene_prompt(project_id: int, filename: str) -> dict[str, Any]:
    ensure_project(project_id)
    return services.scene_prompt(project_id, filename)


@app.get("/api/projects/{project_id}/image-prompt")
def api_image_prompt(
    project_id: int,
    kind: str,
    target: str,
    anchor_key: str = "",
    abstraction_level: str = "",
) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.image_prompt(project_id, kind, target, anchor_key=anchor_key, abstraction_level=abstraction_level)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/image-review")
def api_image_review(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return services.image_review_status(project_id)


@app.get("/api/projects/{project_id}/status")
def api_project_status(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return services.project_status_report(project_id)


@app.get("/api/projects/{project_id}/video-preflight")
def api_video_preflight(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.video_preflight_report(project_id)
    path = storage.save_report(project_id, "video_preflight", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/resume-plan")
def api_resume_plan(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return services.production_resume_plan(project_id)


@app.post("/api/projects/{project_id}/video-preflight/repair-timeline")
def api_repair_video_preflight_timeline(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        result = services.repair_scene_timeline(project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = storage.save_report(project_id, "video_preflight", result["after"])
    return {"report_path": str(path), **result}


@app.post("/api/projects/{project_id}/video-self-check")
def api_video_self_check(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.run_video_self_check(project_id)
    return {"report_path": str(storage.report_path(project_id, "video_self_check")), "result": result}


@app.post("/api/projects/{project_id}/image-review")
def api_save_image_review(project_id: int, payload: ImageReviewPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.save_image_review_status(project_id, required=payload.required, confirmed=payload.confirmed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/images/regenerate")
async def api_regenerate_project_image(project_id: int, payload: ImageRegeneratePayload) -> dict[str, Any]:
    ensure_project(project_id)
    latest = job_runtime.latest(project_id)
    if latest and latest.get("running"):
        raise HTTPException(status_code=409, detail="当前项目有生产任务正在运行，请先停止或等待完成后再重绘图片。")
    try:
        return await asyncio.to_thread(
            services.regenerate_project_image,
            project_id,
            payload.kind,
            payload.target,
            payload.prompt,
            payload.anchor_key,
            payload.abstraction_level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/scene-images/status")
def api_scene_images_status(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return storage.scene_status(project_id)


@app.post("/api/projects/{project_id}/jobs")
async def api_start_job(project_id: int, payload: JobPayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    try:
        return await job_runtime.start(project, payload.steps, payload.allow_incomplete_video)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/jobs/latest")
def api_latest_job(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    job = job_runtime.latest(project_id)
    return {"job": job, "running": bool(job and job.get("running")), "log_available": bool(job)}


@app.post("/api/jobs/{job_id}/cancel")
async def api_cancel_job(job_id: str) -> dict[str, Any]:
    return await job_runtime.cancel(job_id)


@app.get("/api/projects/{project_id}/files")
def api_project_files(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    files = storage.list_project_files(project_id)
    topics = [
        item
        for item in files
        if item["relative_path"]
        in {
            "brief.md",
            "content.md",
            "summary.json",
            "references.json",
            "content_strategy.json",
            "content_audit.json",
            "video_spec.json",
            "reports/quality_gate.json",
            "audio/scene_plan.json",
        }
    ]
    outputs = [item for item in files if item not in topics]
    lookup = {item["relative_path"]: item for item in files}
    return {
        "project_root": str(storage.project_dir(project_id)),
        "releases_root": str(storage.project_file(project_id, "releases")),
        "topics": topics,
        "outputs": outputs,
        "artifacts": {
            "final_video": lookup.get("releases/final-video.mp4"),
            "final_preview": lookup.get("releases/final-preview.html"),
            "release_note": lookup.get("releases/final-video.txt"),
            "video_spec": lookup.get("video_spec.json"),
            "scene_plan": lookup.get("audio/scene_plan.json"),
        },
    }


@app.delete("/api/projects/{project_id}/files")
def api_delete_file(project_id: int, relative_path: str) -> dict[str, Any]:
    ensure_project(project_id)
    path = storage.project_file(project_id, relative_path)
    if path.exists():
        path.unlink()
    return {"ok": True}


@app.post("/api/projects/{project_id}/files/batch-delete")
def api_batch_delete(project_id: int, payload: dict[str, list[str]]) -> dict[str, Any]:
    ensure_project(project_id)
    for relative in payload.get("relative_paths", []):
        path = storage.project_file(project_id, relative)
        if path.exists() and path.is_file():
            path.unlink()
    return {"ok": True}


@app.post("/api/projects/{project_id}/uploads")
async def api_upload_files(project_id: int, files: list[UploadFile] = File(...), slot: str = "uploads") -> dict[str, Any]:
    ensure_project(project_id)
    saved = []
    for item in files:
        filename = storage.safe_name(item.filename or "upload.bin")
        path = storage.project_file(project_id, f"{slot}/{filename}")
        storage.ensure_dir(path.parent)
        path.write_bytes(await item.read())
        saved.append(filename)
    return {"saved": saved}


@app.post("/api/projects/{project_id}/open-folder")
def api_open_project_folder(project_id: int, subpath: str | None = None) -> dict[str, Any]:
    ensure_project(project_id)
    target = storage.project_dir(project_id)
    if subpath:
        target = target / subpath
    return open_in_explorer(target)


@app.get("/api/projects/{project_id}/releases")
def api_release_links(project_id: int) -> list[dict[str, Any]]:
    ensure_project(project_id)
    return storage.get_release_links(project_id)


@app.post("/api/projects/{project_id}/releases")
def api_create_release_link(project_id: int, payload: ReleasePayload) -> dict[str, Any]:
    ensure_project(project_id)
    links = storage.get_release_links(project_id)
    metrics_payload = {
        "views": payload.views,
        "likes": payload.likes,
        "comments": payload.comments,
        "shares": payload.shares,
        "favorites": payload.favorites,
        "completion_rate": payload.completion_rate,
        "notes": payload.metrics_notes,
    }
    item = {
        "id": storage.next_release_id(),
        "platform": payload.platform,
        "url": payload.url,
        "note": payload.note,
        "created_at": storage.now_ts(),
    }
    if any(value not in (None, "", 0) for value in metrics_payload.values()):
        item["metrics"] = services.normalize_release_metrics(metrics_payload)
    links.append(item)
    storage.save_release_links(project_id, links)
    return item


@app.patch("/api/projects/{project_id}/releases/{release_id}")
def api_update_release_link(project_id: int, release_id: int, payload: ReleaseUpdatePayload) -> dict[str, Any]:
    ensure_project(project_id)
    links = storage.get_release_links(project_id)
    for item in links:
        if item["id"] == release_id:
            if payload.platform is not None:
                item["platform"] = payload.platform
            if payload.url is not None:
                item["url"] = payload.url
            if payload.note is not None:
                item["note"] = payload.note
            storage.save_release_links(project_id, links)
            return item
    raise HTTPException(status_code=404, detail="release not found")


@app.put("/api/projects/{project_id}/releases/{release_id}/metrics")
def api_update_release_metrics(project_id: int, release_id: int, payload: ReleaseMetricsPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.update_release_metrics(project_id, release_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/projects/{project_id}/releases/{release_id}")
def api_delete_release_link(project_id: int, release_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    links = [item for item in storage.get_release_links(project_id) if item["id"] != release_id]
    storage.save_release_links(project_id, links)
    return {"ok": True}


@app.post("/api/projects/{project_id}/releases/replay")
def api_release_replay(project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_project(project_id)
    return {"ok": True, "saved": payload}


@app.get("/api/projects/{project_id}/release-automation")
def api_release_automation(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    payload = release_automation.snapshot(project_id)
    payload["task"] = release_runtime.latest(project_id)
    return payload


@app.post("/api/projects/{project_id}/release-automation/draft")
def api_release_automation_draft(project_id: int, payload: ReleaseAutomationPayload) -> dict[str, Any]:
    ensure_project(project_id)
    return {"draft": release_automation.save_draft(project_id, payload.model_dump())}


@app.get("/api/projects/{project_id}/release-automation/qrcode")
def api_release_automation_qrcode(project_id: int, platform: str = "douyin", account_name: str = "default") -> FileResponse:
    ensure_project(project_id)
    qrcode = release_automation.latest_login_qrcode(project_id, platform, account_name)
    if not qrcode:
        raise HTTPException(status_code=404, detail="二维码文件不存在")
    path = Path(str(qrcode.get("absolute_path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="二维码文件不存在")
    return FileResponse(path, media_type="image/png", filename=path.name)


@app.post("/api/projects/{project_id}/release-automation/prepare")
async def api_release_prepare(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await release_runtime.start(project_id, "prepare", {})
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/release-checklist")
def api_release_checklist(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.release_checklist_report(project_id)
    path = storage.save_report(project_id, "release_checklist", result)
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/release-automation/login")
async def api_release_login(project_id: int, payload: ReleaseAutomationPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await release_runtime.start(project_id, "login", payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/release-automation/check")
async def api_release_check(project_id: int, payload: ReleaseAutomationPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await release_runtime.start(project_id, "check", payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/release-automation/publish")
async def api_release_publish(project_id: int, payload: ReleaseAutomationPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await release_runtime.start(project_id, "publish", payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/release-automation/cancel")
async def api_release_cancel(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return await release_runtime.cancel()


@app.get("/api/settings/open-data-folder")
def api_open_data_folder() -> dict[str, Any]:
    return open_in_explorer(storage.DATA_ROOT)


@app.get("/api/settings/data-location")
def api_data_location() -> dict[str, Any]:
    return {"path": str(storage.DATA_ROOT)}


@app.get("/api/settings/data-location/status")
def api_data_location_status() -> dict[str, Any]:
    return {"path": str(storage.DATA_ROOT), "migrating": False}


@app.post("/api/settings/data-location/migrate")
def api_migrate_data_location(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "target": payload.get("target"), "note": "本地演示版固定使用 data 目录。"}


@app.get("/api/settings/secrets")
def api_secrets() -> dict[str, Any]:
    return storage.secrets_payload()


@app.post("/api/settings/secrets")
def api_save_secrets(payload: SecretsPayload) -> dict[str, Any]:
    storage.save_env_patch(payload.values)
    return storage.secrets_payload()


@app.post("/api/settings/secrets/validate")
def api_validate_secrets(payload: SecretsValidatePayload) -> dict[str, Any]:
    values = storage.parse_env()
    return validators.validate_sections(values, payload.targets)


@app.post("/api/settings/chatgpt-login")
def api_open_chatgpt_login() -> dict[str, Any]:
    try:
        return services.open_chatgpt_login_window(services.runtime_env())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/chatgpt-logout")
def api_clear_chatgpt_login() -> dict[str, Any]:
    try:
        return services.clear_chatgpt_login_state(services.runtime_env())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings/tts-previews")
def api_tts_previews() -> dict[str, Any]:
    return services.tts_preview_manifest()


@app.get("/api/settings/packaging")
def api_packaging_status() -> dict[str, Any]:
    return packaging_runtime.latest()


@app.post("/api/settings/packaging/build")
def api_packaging_build(payload: PackagingBuildPayload | None = None) -> dict[str, Any]:
    payload = payload or PackagingBuildPayload()
    try:
        return packaging_runtime.start(include_zip=payload.include_zip)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/settings/packaging/cancel")
def api_packaging_cancel() -> dict[str, Any]:
    return packaging_runtime.cancel()


@app.post("/api/settings/packaging/open")
def api_packaging_open(target: str = "output") -> dict[str, Any]:
    try:
        path = packaging_runtime.open_target(target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"打包产物不存在：{exc}") from exc
    return open_path(path)


@app.post("/api/transcribe-audio")
async def api_transcribe_audio(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "upload.wav").suffix or ".wav"
    temp_path = storage.CONFIG_ROOT / f"transcribe-upload-{storage.now_ms()}{suffix}"
    temp_path.write_bytes(await file.read())
    try:
        text = await asyncio.to_thread(services.transcribe_audio_to_text, temp_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"音频转写失败：{exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)

    if not text.strip():
        raise HTTPException(status_code=400, detail="没有识别到有效语音内容，请换一段更清晰的音频再试。")
    return {"text": text}


@app.get("/")
def api_root() -> JSONResponse:
    return JSONResponse(
        {
            "name": "Short Video Studio Clone",
            "message": "前端页面可直接打开 http://127.0.0.1:8765/studio/ ，后端运行在 http://127.0.0.1:8765",
            "data_root": str(storage.DATA_ROOT),
        }
    )


app.mount("/data", StaticFiles(directory=storage.DATA_ROOT), name="data")
app.mount("/static/tts-previews", StaticFiles(directory=tts_previews_static_root()), name="tts-previews")
app.mount("/studio", StaticFiles(directory=storage.APP_ROOT, html=True), name="studio")


@app.on_event("shutdown")
async def _cleanup() -> None:
    if content_runtime.loaded:
        for project_id in list(content_runtime.tasks):
            with contextlib.suppress(Exception):
                await content_runtime.cancel(project_id, silent=True)
    if job_runtime.loaded:
        for job_id, item in list(job_runtime.tasks.items()):
            task = item["task"]
            task.cancel()
            with contextlib.suppress(Exception):
                await task
    if release_runtime.loaded:
        with contextlib.suppress(Exception):
            await release_runtime.cancel()
