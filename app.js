const API_BASE = "http://127.0.0.1:8765";

const STEP_DEFS = [
  { key: "audio", label: "配音生成", desc: "生成口播音频与文稿" },
  { key: "subtitles", label: "字幕对齐", desc: "输出字幕与时间轴" },
  { key: "images", label: "分镜出图", desc: "生成场景图与图像计划" },
  { key: "covers", label: "封面出图", desc: "生成横屏、竖屏与图文封面" },
  { key: "images_missing", label: "补缺失场景图", desc: "只生成缺失编号，保留已有图片", defaultChecked: false },
  { key: "covers_missing", label: "补缺失封面", desc: "只生成未生成的封面", defaultChecked: false },
  { key: "article", label: "图文版", desc: "输出图文发布版 markdown" },
  { key: "video", label: "成片合成", desc: "合成最终 mp4 成片并写出发布目录", defaultChecked: false },
];

const IMAGE_PROVIDER_OPTIONS = [
  { value: "auto_no_apiyi", label: "自动选择（不使用第三方接口）" },
  { value: "ark", label: "火山方舟 Seedream" },
  { value: "third_party", label: "第三方 OpenAI 兼容" },
  { value: "chatgpt_web_auto", label: "ChatGPT 网页自动化" },
  { value: "chatgpt_handoff", label: "ChatGPT 网页/桌面接力" },
  { value: "apiyi", label: "API易 / OpenAI 兼容" },
  { value: "auto", label: "自动选择（原逻辑）" },
];

const state = {
  backendOnline: false,
  templates: [],
  projects: [],
  selectedTemplateKey: "",
  currentProject: null,
  currentContent: null,
  currentJob: null,
  currentFiles: null,
  sceneStatus: null,
  imageReview: null,
  projectStatus: null,
  videoSelfCheck: null,
  releaseLinks: [],
  releaseAutomation: null,
  config: null,
  packaging: null,
  ttsPreviews: null,
  activeTab: "content",
  pollTimer: null,
  autoVideo: null,
  autoVideoTimer: null,
  packagingTimer: null,
  autoVideoModalVisible: false,
  autoVideoOpenedProjectId: null,
  autoVideoDrafts: {},
  revealedSecrets: {},
  audioPreview: null,
  editor: {
    projectId: null,
    briefDirty: false,
    contentDirty: false,
    lastBrief: "",
    lastContent: "",
  },
  releaseEditor: {
    projectId: null,
    lastDraft: "",
    saveTimer: null,
  },
};

const els = {
  backendBanner: document.getElementById("backend-banner"),
  backendStatus: document.getElementById("backend-status"),
  workspaceTitle: document.getElementById("workspace-title"),
  workspaceSubtitle: document.getElementById("workspace-subtitle"),
  templateList: document.getElementById("template-list"),
  projectList: document.getElementById("project-list"),
  projectListScope: document.getElementById("project-list-scope"),
  briefInput: document.getElementById("brief-input"),
  contentInput: document.getElementById("content-input"),
  nextToProduceBtn: document.getElementById("next-to-produce-btn"),
  summaryCards: document.getElementById("summary-cards"),
  referenceList: document.getElementById("reference-list"),
  contentGenerateStatus: document.getElementById("content-generate-status"),
  stepList: document.getElementById("step-list"),
  nextToFilesBtn: document.getElementById("next-to-files-btn"),
  jobStatusPill: document.getElementById("job-status-pill"),
  jobProgress: document.getElementById("job-progress"),
  jobLog: document.getElementById("job-log"),
  sceneGrid: document.getElementById("scene-grid"),
  sceneStatusPill: document.getElementById("scene-status-pill"),
  coverGrid: document.getElementById("cover-grid"),
  coverStatusPill: document.getElementById("cover-status-pill"),
  imageReviewRequired: document.getElementById("image-review-required"),
  confirmImagesBtn: document.getElementById("confirm-images-btn"),
  imageReviewPill: document.getElementById("image-review-pill"),
  imageReviewHelper: document.getElementById("image-review-helper"),
  imageProviderSelect: document.getElementById("image-provider-select"),
  imageProviderSaveBtn: document.getElementById("image-provider-save-btn"),
  imageProviderCurrent: document.getElementById("image-provider-current"),
  sceneCountMode: document.getElementById("scene-count-mode"),
  sceneCountFixed: document.getElementById("scene-count-fixed"),
  sceneCountSaveBtn: document.getElementById("scene-count-save-btn"),
  sceneCountCurrent: document.getElementById("scene-count-current"),
  chatgptReloginBtn: document.getElementById("chatgpt-relogin-btn"),
  chatgptLogoutBtn: document.getElementById("chatgpt-logout-btn"),
  projectStatusStrip: document.getElementById("project-status-strip"),
  fileList: document.getElementById("file-list"),
  nextToReleasesBtn: document.getElementById("next-to-releases-btn"),
  videoSelfCheckBtn: document.getElementById("video-self-check-btn"),
  releaseList: document.getElementById("release-list"),
  releaseAutomationSummary: document.getElementById("release-automation-summary"),
  releaseTaskMeta: document.getElementById("release-task-meta"),
  releaseTaskPill: document.getElementById("release-task-pill"),
  releaseAutomationLog: document.getElementById("release-automation-log"),
  configFields: document.getElementById("config-fields"),
  packagingSummary: document.getElementById("packaging-summary"),
  packagingStatusPill: document.getElementById("packaging-status-pill"),
  packagingLog: document.getElementById("packaging-log"),
  startPortableBuildBtn: document.getElementById("start-portable-build-btn"),
  startZipBuildBtn: document.getElementById("start-zip-build-btn"),
  cancelPackagingBtn: document.getElementById("cancel-packaging-btn"),
  refreshPackagingBtn: document.getElementById("refresh-packaging-btn"),
  openPackagingOutputBtn: document.getElementById("open-packaging-output-btn"),
  releasePlatform: document.getElementById("release-platform"),
  releaseUrl: document.getElementById("release-url"),
  releaseNote: document.getElementById("release-note"),
  releaseViews: document.getElementById("release-views"),
  releaseLikes: document.getElementById("release-likes"),
  releaseComments: document.getElementById("release-comments"),
  releaseShares: document.getElementById("release-shares"),
  releaseFavorites: document.getElementById("release-favorites"),
  releaseCompletionRate: document.getElementById("release-completion-rate"),
  releaseAutoPlatform: document.getElementById("release-auto-platform"),
  releaseAutoAccount: document.getElementById("release-auto-account"),
  releaseAutoAccountOptions: document.getElementById("release-auto-account-options"),
  releaseAutoBrowserMode: document.getElementById("release-auto-browser-mode"),
  releaseAutoSchedule: document.getElementById("release-auto-schedule"),
  releaseAutoTitle: document.getElementById("release-auto-title"),
  releaseAutoTags: document.getElementById("release-auto-tags"),
  releaseAutoDescription: document.getElementById("release-auto-description"),
  validateConfigBtn: document.getElementById("validate-config-btn"),
  modal: document.getElementById("modal"),
  modalTitle: document.getElementById("modal-title"),
  modalBody: document.getElementById("modal-body"),
  audioInput: document.getElementById("audio-file-input"),
};

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value * 1000);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatValidationTime(value) {
  if (!value) return "";
  const date = new Date(value * 1000);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatMaybeTimestamp(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return formatDate(value);
  const text = String(value).trim();
  if (!text) return "—";
  if (/^\d+$/.test(text)) return formatDate(Number(text));
  return text;
}

function formatByteSize(value) {
  const size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let current = size;
  let index = 0;
  while (current >= 1024 && index < units.length - 1) {
    current /= 1024;
    index += 1;
  }
  return `${current.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function orphanTemplates() {
  const known = new Set((state.templates || []).map((template) => template.key));
  const groups = new Map();
  for (const project of state.projects || []) {
    if (known.has(project.template)) continue;
    const entry = groups.get(project.template) || {
      key: project.template,
      count: 0,
      latestTopic: project.topic_name,
    };
    entry.count += 1;
    entry.latestTopic = project.topic_name || entry.latestTopic;
    groups.set(project.template, entry);
  }
  return Array.from(groups.values()).sort((a, b) => a.key.localeCompare(b.key, "zh-CN"));
}

function isTemplateLocked(template) {
  return Boolean(template?.builtin_locked);
}

function templateProjectCount(templateKey) {
  return (state.projects || []).filter((project) => project.template === templateKey).length;
}

function hasTemplateOrProjects(templateKey) {
  if (!templateKey) return false;
  return (state.templates || []).some((template) => template.key === templateKey)
    || (state.projects || []).some((project) => project.template === templateKey);
}

function ensureSelectedTemplateKey() {
  if (hasTemplateOrProjects(state.selectedTemplateKey)) return;
  if (state.currentProject?.template) {
    state.selectedTemplateKey = state.currentProject.template;
    return;
  }
  const firstWithProjects = (state.templates || []).find((template) => templateProjectCount(template.key) > 0);
  state.selectedTemplateKey = firstWithProjects?.key || state.templates?.[0]?.key || "";
}

function selectedTemplateKey() {
  ensureSelectedTemplateKey();
  return state.selectedTemplateKey || "";
}

function selectedTemplate() {
  const key = selectedTemplateKey();
  return (state.templates || []).find((template) => template.key === key) || null;
}

function projectsForSelectedTemplate() {
  const key = selectedTemplateKey();
  if (!key) return state.projects || [];
  return (state.projects || []).filter((project) => project.template === key);
}

function adaptPromptChannelName(prompt, baseTemplate, newKey) {
  let result = prompt || "";
  const names = [baseTemplate?.key, baseTemplate?.name, baseTemplate?.brand_name]
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  for (const name of Array.from(new Set(names))) {
    if (name && name !== newKey) {
      result = result.split(name).join(newKey);
    }
  }
  return result;
}

function validateTemplatePromptText(prompt) {
  const cleaned = String(prompt || "").trim();
  const compact = cleaned.replace(/\s+/g, "");
  if (compact.length < 120) {
    return "频道 prompt.md 太短。请至少写清楚频道人设、内容结构、画面风格和禁忌，避免生成退回通用模板。";
  }
  const hints = ["人设", "口吻", "结构", "封面", "场景", "图片", "禁忌", "互动"];
  const matched = hints.filter((hint) => cleaned.includes(hint)).length;
  if (matched < 2) {
    return "频道 prompt.md 缺少频道规则。建议写明人设/口吻、脚本结构、封面与场景图风格、禁忌和互动方式。";
  }
  return "";
}

function resetEditorState(projectId = state.currentProject?.id ?? null, brief = "", content = "") {
  state.editor.projectId = projectId;
  state.editor.briefDirty = false;
  state.editor.contentDirty = false;
  state.editor.lastBrief = brief;
  state.editor.lastContent = content;
  els.briefInput.value = brief;
  els.contentInput.value = content;
}

function syncEditorFromBundle(bundle, { force = false } = {}) {
  const projectId = state.currentProject?.id ?? null;
  const nextBrief = bundle?.brief || "";
  const nextContent = bundle?.content || "";
  const projectChanged = state.editor.projectId !== projectId;

  if (!bundle) {
    if (force || projectChanged || !state.editor.briefDirty) {
      els.briefInput.value = "";
    }
    if (force || projectChanged || !state.editor.contentDirty) {
      els.contentInput.value = "";
    }
    state.editor.projectId = projectId;
    state.editor.lastBrief = "";
    state.editor.lastContent = "";
    if (force || projectChanged) {
      state.editor.briefDirty = false;
      state.editor.contentDirty = false;
    }
    return;
  }

  if (force || projectChanged) {
    resetEditorState(projectId, nextBrief, nextContent);
    return;
  }

  state.editor.lastBrief = nextBrief;
  state.editor.lastContent = nextContent;
  if (!state.editor.briefDirty && document.activeElement !== els.briefInput) {
    els.briefInput.value = nextBrief;
  }
  if (!state.editor.contentDirty && document.activeElement !== els.contentInput) {
    els.contentInput.value = nextContent;
  }
}

function clearCurrentWorkspace() {
  state.currentProject = null;
  state.currentContent = null;
  state.currentJob = null;
  state.currentFiles = null;
  state.sceneStatus = null;
  state.imageReview = null;
  state.projectStatus = null;
  state.videoSelfCheck = null;
  state.releaseLinks = [];
  state.releaseAutomation = null;
  renderContentBundle({ forceEditor: true });
  renderJob();
  renderFiles();
  renderScenes();
  renderImageReview();
  renderProjectStatus();
  renderReleases();
  renderReleaseAutomation();
}

function renderWorkspacePlaceholderForSelectedTemplate() {
  const key = selectedTemplateKey();
  els.workspaceTitle.textContent = "请选择一个主题";
  els.workspaceSubtitle.textContent = key
    ? `${key} · 当前频道还没有打开的主题项目`
    : "请选择左侧频道，再新建或打开一个主题项目";
}

async function selectTemplateProjects(templateKey, { openFirst = true } = {}) {
  state.selectedTemplateKey = templateKey || "";
  const projects = projectsForSelectedTemplate();
  renderTemplates();
  renderProjects();
  const currentVisible = state.currentProject && projects.some((project) => project.id === state.currentProject.id);
  if (openFirst && !currentVisible) {
    if (projects.length) {
      await openProject(projects[0].id);
      return;
    }
    clearCurrentWorkspace();
    renderWorkspacePlaceholderForSelectedTemplate();
    renderProjects();
    renderTemplates();
  }
}

async function deleteTemplateByKey(key) {
  const template = state.templates.find((item) => item.key === key);
  if (isTemplateLocked(template)) {
    window.alert("内置频道模板不能删除。");
    return false;
  }

  const count = templateProjectCount(key);
  const message = count
    ? `确认删除频道模板「${key}」吗？会同时删除该频道下 ${count} 个主题项目、模板目录和产物目录。`
    : `确认删除频道模板「${key}」吗？会删除模板目录和产物目录。`;
  if (!window.confirm(message)) return false;

  const deletingCurrentTemplate = state.currentProject?.template === key;
  await api(`/api/templates/${encodeURIComponent(key)}?delete_projects=${count > 0 ? "true" : "false"}`, {
    method: "DELETE",
  });
  if (deletingCurrentTemplate) {
    clearCurrentWorkspace();
  }
  if (state.selectedTemplateKey === key) {
    state.selectedTemplateKey = "";
  }
  if (!els.modal.classList.contains("hidden")) {
    closeModal();
  }
  await refreshTemplates();
  await refreshProjects();
  return true;
}

function formatBytes(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function versionedProjectUrl(item) {
  const rawUrl = item?.url || "";
  if (!rawUrl) return "";
  const modifiedAt = Number(item?.modified_at || 0);
  if (!Number.isFinite(modifiedAt) || modifiedAt <= 0) return rawUrl;
  const separator = rawUrl.includes("?") ? "&" : "?";
  return `${rawUrl}${separator}v=${Math.floor(modifiedAt * 1000)}`;
}

function findOutputByStem(files, stem) {
  const outputs = files?.outputs || [];
  const suffixes = [".png", ".jpg", ".jpeg", ".webp", ".svg"];
  for (const suffix of suffixes) {
    const match = outputs.find((item) => item.relative_path === `${stem}${suffix}`);
    if (match) return match;
  }
  return null;
}

function findOutputByPath(files, relativePath) {
  return (files?.outputs || []).find((item) => item.relative_path === relativePath) || null;
}

function coverRecords(files) {
  return [
    {
      key: "landscape",
      label: "横屏封面",
      ratio: "16:9",
      image: findOutputByStem(files, "covers/cover_landscape"),
      prompt: findOutputByPath(files, "covers/cover_landscape.md"),
    },
    {
      key: "story",
      label: "图文封面",
      ratio: "4:3",
      image: findOutputByStem(files, "covers/cover_story"),
      prompt: findOutputByPath(files, "covers/cover_story.md"),
    },
    {
      key: "portrait",
      label: "竖屏封面",
      ratio: "3:4",
      image: findOutputByStem(files, "covers/cover_portrait"),
      prompt: findOutputByPath(files, "covers/cover_portrait.md"),
    },
  ];
}

function imageAuditHtml(audit = {}) {
  const severity = audit?.severity || (audit?.ok === false ? "warn" : "ok");
  const reasons = Array.isArray(audit?.reasons) ? audit.reasons.filter(Boolean) : [];
  const provider = audit?.provider_label || audit?.provider || "";
  const label = severity === "hard" ? "需重看" : severity === "soft" ? "轻微提示" : "自检通过";
  return `
    <div class="media-card__audit">
      <span class="pill ${severity === "hard" ? "pill--warn" : ""}">${escapeHtml(label)}</span>
      ${provider ? `<span class="muted">${escapeHtml(provider)}</span>` : ""}
      ${reasons.length ? `<div class="muted">${escapeHtml(reasons.join("、"))}</div>` : ""}
    </div>
  `;
}

function imagePromptPreviewHtml(prompt = "", fallback = "暂无提示词摘要") {
  const text = String(prompt || "").replace(/\s+/g, " ").trim();
  return `<div class="media-card__prompt-preview">${escapeHtml(text ? text.slice(0, 160) : fallback)}</div>`;
}

function sceneCardHtml(item) {
  const promptPreview = item.prompt_preview || item.prompt || "";
  return `
    <article class="media-card media-card--workbench">
      <img src="${API_BASE}${versionedProjectUrl(item)}" alt="${escapeHtml(item.filename)}" />
      <div class="media-card__body">
        <div class="media-card__title-row">
          <strong>${escapeHtml(item.filename)}</strong>
          <span class="pill">使用中</span>
        </div>
        ${imagePromptPreviewHtml(promptPreview)}
        ${imageAuditHtml(item.audit || {})}
        <div class="media-card__actions">
          <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(item))}">打开图片</button>
          ${item.prompt_url ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(item.prompt_url)}">提示词文件</button>` : ""}
          <button class="btn btn--primary" data-regenerate-image-kind="scene" data-regenerate-image-target="${escapeHtml(item.filename)}" data-regenerate-image-label="${escapeHtml(item.filename)}">调整 / 重绘</button>
          <button class="btn btn--danger" data-delete-file="${escapeHtml(item.relative_path || `scenes/${item.filename}`)}">弃用</button>
        </div>
      </div>
    </article>
  `;
}

function missingSceneCardHtml(item) {
  const filename = item.filename || `${item.stem || "s_01"}.png`;
  return `
    <article class="media-card media-card--placeholder media-card--workbench">
      <div class="media-card__preview">
        <div>
          <strong>${escapeHtml(filename)}</strong>
          <div class="muted">缺失 · 可单张补生成</div>
        </div>
      </div>
      <div class="media-card__body">
        <div class="media-card__title-row">
          <strong>${escapeHtml(filename)}</strong>
          <span class="pill pill--warn">缺失</span>
        </div>
        ${imagePromptPreviewHtml("", "点“生成这一张”会按频道、主题和对应口播重新取提示词。")}
        <div class="media-card__actions">
          <button class="btn btn--primary" data-regenerate-image-kind="scene" data-regenerate-image-target="${escapeHtml(filename)}" data-regenerate-image-label="${escapeHtml(filename)}">生成这一张</button>
        </div>
      </div>
    </article>
  `;
}

function coverGalleryCardsHtml(files) {
  return coverRecords(files)
    .map((cover) => {
      if (!cover.image) {
        return `
          <article class="media-card media-card--cover media-card--placeholder">
            <div class="media-card__preview">
              <div>
                <strong>${escapeHtml(cover.label)}</strong>
                <div class="muted">${escapeHtml(cover.ratio)} · 暂未生成</div>
              </div>
            </div>
            <div class="media-card__body">
              <strong>${escapeHtml(cover.label)}</strong>
              <div class="media-card__meta">预计落在 covers/cover_${escapeHtml(cover.key)}.*</div>
              ${imagePromptPreviewHtml("", "点“生成 / 重绘”会按本期标题、钩子和频道风格生成封面提示词。")}
              <div class="media-card__actions">
                <button class="btn btn--ghost" data-regenerate-image-kind="cover" data-regenerate-image-target="${escapeHtml(cover.key)}" data-regenerate-image-label="${escapeHtml(cover.label)}">生成 / 重绘</button>
              </div>
            </div>
          </article>
        `;
      }
      return `
        <article class="media-card media-card--cover">
          <img src="${API_BASE}${versionedProjectUrl(cover.image)}" alt="${escapeHtml(cover.label)}" />
          <div class="media-card__body">
            <div class="media-card__title-row">
              <strong>${escapeHtml(cover.label)} · ${escapeHtml(cover.ratio)}</strong>
              <span class="pill">使用中</span>
            </div>
            <div class="media-card__meta">${escapeHtml(cover.image.absolute_path || cover.image.relative_path || "")}</div>
            ${imagePromptPreviewHtml("", "提示词可在“调整 / 重绘”窗口查看和追加修改。")}
            <div class="media-card__actions">
              <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(cover.image))}">打开图片</button>
              ${cover.prompt ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(cover.prompt))}">查看提示词</button>` : ""}
              <button class="btn btn--primary" data-regenerate-image-kind="cover" data-regenerate-image-target="${escapeHtml(cover.key)}" data-regenerate-image-label="${escapeHtml(cover.label)}">调整 / 重绘</button>
              <button class="btn btn--danger" data-delete-file="${escapeHtml(cover.image.relative_path || `covers/cover_${cover.key}.png`)}">弃用</button>
            </div>
          </div>
        </article>
      `;
    })
    .join("");
}

function coverPreviewHtml(files) {
  const covers = coverRecords(files);
  const generated = covers.filter((item) => item.image).length;
  const coversRoot = files?.project_root ? `${files.project_root}\\covers` : "项目目录\\covers";
  return `
    <article class="file-callout">
      <div>
        <strong>封面文件</strong>
        <div class="muted" style="margin-top:6px;">横屏、图文、竖屏封面都会落到本地 covers 目录，这里直接预览并保留绝对路径。</div>
        <div class="mono-path">${escapeHtml(coversRoot)}</div>
        <div class="muted" style="margin-top:6px;">已生成 ${generated}/${covers.length}</div>
      </div>
      <div class="file-item__actions">
        <button class="btn btn--ghost" data-open-project-subpath="covers">打开封面目录</button>
      </div>
    </article>
    <div class="media-grid media-grid--covers">
      ${coverGalleryCardsHtml(files)}
    </div>
  `;
}

function artifactSummaryHtml(files) {
  const artifacts = files?.artifacts || {};
  const finalVideo = artifacts.final_video || null;
  const finalPreview = artifacts.final_preview || null;
  const releaseNote = artifacts.release_note || null;
  const releasesRoot = files?.releases_root || "";
  if (!finalVideo && !finalPreview && !releaseNote) return "";

  const primary = finalVideo || finalPreview || releaseNote;
  const primaryLabel = finalVideo ? "最终成片（mp4）" : finalPreview ? "成片预演页面" : "成片说明文件";
  const helper = finalVideo
    ? "生产完成后，最终视频会落在这个绝对路径。"
    : "当前这个项目还没有生成 mp4，先给你显示现有的成片相关文件位置。";
  const openButton = finalVideo
    ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(finalVideo))}">打开 mp4</button>`
    : finalPreview
      ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(finalPreview))}">打开预演</button>`
      : `<button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(releaseNote))}">打开说明</button>`;

  return `
    <article class="file-callout">
      <div>
        <strong>${primaryLabel}</strong>
        <div class="muted" style="margin-top:6px;">${helper}</div>
        <div class="mono-path">${escapeHtml(primary.absolute_path || "—")}</div>
        ${releasesRoot ? `<div class="muted" style="margin-top:6px;">发布目录：<span class="mono-inline">${escapeHtml(releasesRoot)}</span></div>` : ""}
      </div>
      <div class="file-item__actions">
        ${openButton}
        <button class="btn btn--ghost" data-open-project-subpath="releases">打开成片目录</button>
      </div>
    </article>
  `;
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" && data?.detail ? data.detail : response.statusText;
    throw new Error(detail || "请求失败");
  }
  return data;
}

function isChatgptLoginError(message = "") {
  const text = String(message || "");
  return [
    "ChatGPT 登录态已失效",
    "重新登录 ChatGPT",
    "没有找到输入框",
    "输入框当前不可编辑",
  ].some((token) => text.includes(token));
}

function renderChatgptReloginButton() {
  if (!els.chatgptReloginBtn) return;
  const loginRequired = isChatgptLoginError(state.currentJob?.log || "");
  els.chatgptReloginBtn.disabled = !state.backendOnline;
  if (els.chatgptLogoutBtn) els.chatgptLogoutBtn.disabled = !state.backendOnline;
  els.chatgptReloginBtn.className = loginRequired ? "btn btn--danger" : "btn btn--ghost";
  els.chatgptReloginBtn.textContent = loginRequired ? "ChatGPT 重新登录后重试" : "重新登录 ChatGPT";
  els.chatgptReloginBtn.title = loginRequired
    ? "检测到生图登录失效，点击会打开可见浏览器登录页。"
    : "如果 ChatGPT 生图提示登录失效，可以点这里重新登录。";
}

async function relaunchChatgptLogin(statusEl = null, sourceButton = null) {
  if (!state.backendOnline) {
    window.alert("请先启动后端。");
    return null;
  }
  const originalLabel = sourceButton ? sourceButton.textContent : "";
  if (sourceButton) {
    sourceButton.disabled = true;
    sourceButton.textContent = "正在打开...";
  }
  let quickWindow = null;
  try {
    quickWindow = window.open("about:blank", "_blank", "noopener,noreferrer");
    if (quickWindow) {
      quickWindow.location.href = "https://chatgpt.com/";
    }
  } catch (error) {
    console.warn("open chatgpt window failed", error);
  }
  if (statusEl) statusEl.textContent = "正在打开 ChatGPT 登录窗口...";
  try {
    const payload = await api("/api/settings/chatgpt-login", { method: "POST" });
    const message = [
      "已打开 ChatGPT 登录窗口，请先完成登录。",
      payload?.profile_dir ? `登录目录：${payload.profile_dir}` : "",
      "登录完成后，回到这里重试当前生图即可。",
    ].filter(Boolean).join(" ");
    if (statusEl) {
      statusEl.textContent = message;
    } else {
      window.alert(message);
    }
    return payload;
  } catch (error) {
    const message = error.message || "打开 ChatGPT 登录窗口失败。";
    if (statusEl) {
      statusEl.textContent = message;
    } else {
      window.alert(message);
    }
    return null;
  } finally {
    if (sourceButton) {
      sourceButton.disabled = false;
      sourceButton.textContent = originalLabel || "重新登录 ChatGPT";
    }
  }
}

async function logoutChatgptLogin(sourceButton = null) {
  if (!state.backendOnline) {
    window.alert("请先启动后端。");
    return null;
  }
  if (!window.confirm("确认退出 ChatGPT 自动化登录吗？这会清空本工具保存的 ChatGPT 浏览器登录状态，下次生图需要重新登录。")) {
    return null;
  }
  const originalLabel = sourceButton ? sourceButton.textContent : "";
  if (sourceButton) {
    sourceButton.disabled = true;
    sourceButton.textContent = "正在退出...";
  }
  try {
    const payload = await api("/api/settings/chatgpt-logout", { method: "POST" });
    window.alert(payload.message || "ChatGPT 登录状态已清空。");
    return payload;
  } catch (error) {
    window.alert(error.message || "退出 ChatGPT 登录失败，请先关闭弹出的 ChatGPT/Chrome 窗口后重试。");
    return null;
  } finally {
    if (sourceButton) {
      sourceButton.disabled = false;
      sourceButton.textContent = originalLabel || "退出 ChatGPT";
    }
  }
}

async function withBusyButton(button, busyText, task) {
  if (!button) {
    return await task();
  }
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = busyText;
  try {
    return await task();
  } finally {
    button.disabled = false;
    button.textContent = originalText || "";
  }
}

function markReleaseAutomationPending(action) {
  const actionLabels = {
    prepare: "准备环境",
    login: "登录账号",
    check: "检测账号",
    publish: "发布视频",
    cancel: "取消任务",
  };
  const label = actionLabels[action] || action;
  const platform = els.releaseAutoPlatform?.selectedOptions?.[0]?.textContent?.trim()
    || els.releaseAutoPlatform?.value?.trim()
    || "-";
  const accountName = els.releaseAutoAccount?.value?.trim() || "default";
  const stamp = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const existingLog = String(els.releaseAutomationLog?.textContent || "").trim();
  const nextLogLine = `[release] ${stamp} 正在发起${label}...`;

  if (els.releaseTaskPill) {
    els.releaseTaskPill.textContent = "starting";
    els.releaseTaskPill.className = "pill";
  }
  if (els.releaseTaskMeta) {
    els.releaseTaskMeta.innerHTML = `
      <div>动作: ${escapeHtml(action)} · 平台: ${escapeHtml(platform)} · 账号: ${escapeHtml(accountName)}</div>
      <div>状态: starting · 运行中: 是</div>
      <div class="muted">请求已经发送到后端，稍后会在这里刷新二维码、登录状态和运行日志。</div>
    `;
  }
  if (els.releaseAutomationLog) {
    els.releaseAutomationLog.textContent = existingLog ? `${existingLog}\n${nextLogLine}` : nextLogLine;
  }
}

function bindReleaseAutomationAction(buttonId, action, busyText, fallbackError) {
  const button = document.getElementById(buttonId);
  button?.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    await withBusyButton(button, busyText, async () => {
      try {
        await runReleaseAutomation(action);
      } catch (error) {
        window.alert(error.message || fallbackError);
      }
    });
  });
}

function ensureProject() {
  if (!state.currentProject) {
    window.alert("请先在左侧选择一个主题项目。");
    return null;
  }
  return state.currentProject;
}

function hasContentDraft() {
  const bundleContent = state.currentContent?.content || "";
  const editorContent = els.contentInput?.value || "";
  return Boolean(bundleContent.trim() || editorContent.trim());
}

function hasFinalVideoArtifact() {
  return Boolean(state.currentFiles?.artifacts?.final_video);
}

function updateWorkflowButtons() {
  if (els.nextToProduceBtn) {
    const ready = Boolean(state.currentProject && hasContentDraft());
    els.nextToProduceBtn.disabled = !ready;
    els.nextToProduceBtn.title = ready ? "跳到生产页继续下一步" : "先生成或保存 content.md";
  }
  if (els.nextToFilesBtn) {
    const ready = Boolean(state.currentProject && state.currentJob?.status === "succeeded" && hasFinalVideoArtifact());
    els.nextToFilesBtn.disabled = !ready;
    els.nextToFilesBtn.title = ready ? "跳到成片页查看输出文件" : "先跑完生产并生成 mp4";
  }
  if (els.nextToReleasesBtn) {
    const ready = Boolean(state.currentProject && hasFinalVideoArtifact());
    els.nextToReleasesBtn.disabled = !ready;
    els.nextToReleasesBtn.title = ready ? "跳到投放页登记链接" : "先生成最终视频";
  }
  if (els.videoSelfCheckBtn) {
    const ready = Boolean(state.currentProject && hasFinalVideoArtifact());
    els.videoSelfCheckBtn.disabled = !ready;
    els.videoSelfCheckBtn.title = ready ? "抽帧检查黑屏、字幕覆盖和时长" : "先生成最终视频";
  }
}

function setBackendOnline(online) {
  state.backendOnline = online;
  els.backendBanner.classList.toggle("hidden", online);
  els.backendStatus.textContent = online ? "后端已连接" : "后端未连接";
  els.backendStatus.className = online ? "pill" : "pill pill--warn";
  renderChatgptReloginButton();
}

function showModal(title, html, afterRender) {
  els.modalTitle.textContent = title;
  els.modalBody.innerHTML = html;
  els.modal.classList.remove("hidden");
  if (afterRender) afterRender(els.modalBody);
}

function closeModal() {
  els.modal.classList.add("hidden");
  els.modalBody.innerHTML = "";
  state.autoVideoModalVisible = false;
}

function setActiveTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `tab-${tab}` || panel.id === "tab-content" && tab === "content");
  });
  if (tab === "releases" && state.currentProject) {
    refreshReleaseAutomation(true).catch((error) => console.warn(error));
  }
  if (tab === "config") {
    refreshPackaging().catch((error) => console.warn(error));
  }
}

function renderTemplates() {
  const orphans = orphanTemplates();
  if (!state.templates.length && !orphans.length) {
    els.templateList.innerHTML = `<div class="muted">暂无模板</div>`;
    return;
  }
  const templateCards = state.templates
    .map((template) => {
      const active = selectedTemplateKey() === template.key ? "is-active" : "";
      const locked = isTemplateLocked(template);
      const projectCount = templateProjectCount(template.key);
      const lockedBadge = locked ? ` <span class="pill">内置</span>` : "";
      const projectHint = projectCount ? ` · ${projectCount} 个主题` : "";
      const editLabel = locked ? "查看" : "查看 / 编辑";
      const deleteButton = locked
        ? ""
        : `<button class="btn btn--ghost btn--danger" data-delete-template="${escapeHtml(template.key)}">删除</button>`;
      return `
        <article class="template-item ${active}">
          <h4>${escapeHtml(template.key)}${lockedBadge}</h4>
          <p>${escapeHtml(template.mode === "article" ? "图文工作流" : "视频工作流")} · 封面风格 ${escapeHtml(template.cover_style || "default")}${escapeHtml(projectHint)}</p>
          <div class="template-item__actions">
            <button class="btn btn--primary" data-select-template="${escapeHtml(template.key)}">主题</button>
            <button class="btn btn--ghost" data-edit-template="${escapeHtml(template.key)}">${editLabel}</button>
            <button class="btn btn--ghost" data-open-template="${escapeHtml(template.key)}">打开目录</button>
            <button class="btn btn--primary" data-auto-video-template="${escapeHtml(template.key)}">自动挖题成片</button>
            <button class="btn btn--ghost" data-open-template-products="${escapeHtml(template.key)}">打开产物</button>
            ${deleteButton}
          </div>
        </article>
      `;
    })
    .join("");
  const orphanCards = orphans
    .map(
      (template) => `
        <article class="template-item">
          <h4>${escapeHtml(template.key)} <span class="pill pill--warn">orphan</span></h4>
          <p>模板目录已经不存在，但还有 ${escapeHtml(String(template.count))} 个历史项目在引用。最近项目：${escapeHtml(template.latestTopic || "未命名")}</p>
          <div class="template-item__actions">
            <button class="btn btn--primary" data-select-template="${escapeHtml(template.key)}">主题</button>
            <button class="btn btn--ghost" data-open-template-products="${escapeHtml(template.key)}">打开产物</button>
            <button class="btn btn--ghost" data-delete-orphan-template="${escapeHtml(template.key)}">清理 orphan</button>
          </div>
        </article>
      `
    )
    .join("");
  els.templateList.innerHTML = templateCards + orphanCards;
}

function renderProjects() {
  const key = selectedTemplateKey();
  const projects = projectsForSelectedTemplate();
  if (els.projectListScope) {
    els.projectListScope.textContent = key
      ? `${key} · ${projects.length} 个主题`
      : `全部频道 · ${(state.projects || []).length} 个主题`;
  }
  if (!state.projects.length) {
    els.projectList.innerHTML = `<div class="muted">还没有主题项目，先点上面的“新建主题”。</div>`;
    return;
  }
  if (!projects.length) {
    els.projectList.innerHTML = `<div class="muted">这个频道还没有主题项目，点“新建主题”会默认创建到当前频道。</div>`;
    return;
  }
  els.projectList.innerHTML = projects
    .map((project) => {
      const active = state.currentProject?.id === project.id ? "is-active" : "";
      return `
        <article class="project-item ${active}">
          <h4>${escapeHtml(project.topic_name)}</h4>
          <p>${escapeHtml(project.template)} · ${escapeHtml(project.template_mode === "article" ? "图文" : "视频")} · 最近状态 ${escapeHtml(project.last_job_status || "idle")}</p>
          <div class="project-item__actions">
            <button class="btn btn--ghost" data-open-project="${project.id}">打开</button>
            <button class="btn btn--ghost" data-delete-project="${project.id}">删除</button>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderSummary(summary) {
  if (!summary || !summary.video_title) {
    els.summaryCards.innerHTML = `<div class="muted">先生成 content.md，这里会显示标题、时长、分镜数、评分等摘要。</div>`;
    return;
  }
  const cards = [
    ["主标题", summary.video_title],
    ["发布标题", summary.publish_title],
    ["预计时长", summary.duration],
    ["场景图数量", summary.scene_count],
    ["台词条数", summary.dialogue_count],
    ["选题评分", summary.topic_score],
  ];
  els.summaryCards.innerHTML = cards
    .map(
      ([label, value]) => `
        <div class="summary-card">
          <strong>${escapeHtml(label)}</strong>
          <span>${escapeHtml(String(value ?? "—"))}</span>
        </div>
      `
    )
    .join("");
}

function renderReferences(references = []) {
  if (!references.length) {
    els.referenceList.innerHTML = `<div class="muted">暂无参考资料</div>`;
    return;
  }
  els.referenceList.innerHTML = references
    .map(
      (ref) => `
        <article class="card card--inner">
          <h4>${escapeHtml(ref.title)}</h4>
          <p>${escapeHtml(ref.snippet || "")}</p>
          <div class="toolbar">
            <span class="pill">${escapeHtml(ref.source || "Web")}</span>
            <button class="btn btn--ghost" data-preview-reference="${Number(ref.index ?? 0)}">预览资料</button>
            <a class="link-btn" href="${escapeHtml(ref.url)}" target="_blank" rel="noreferrer">打开来源</a>
          </div>
        </article>
      `
    )
    .join("");
}

function renderContentBundle({ forceEditor = false } = {}) {
  const bundle = state.currentContent;
  if (!bundle) {
    syncEditorFromBundle(null, { force: forceEditor });
    renderSummary(null);
    renderReferences([]);
    renderSceneCountControls();
    els.contentGenerateStatus.textContent = "状态：空闲";
    updateWorkflowButtons();
    return;
  }
  syncEditorFromBundle(bundle, { force: forceEditor });
  renderSummary(bundle.summary || null);
  renderReferences(bundle.references || []);

  const status = bundle.content_generate?.status || "idle";
  const stage = bundle.content_generate?.stage ? ` · ${bundle.content_generate.stage}` : "";
  const provider = bundle.content_generate?.provider ? ` · ${bundle.content_generate.provider}` : "";
  els.contentGenerateStatus.textContent = `状态：${status}${stage}${provider}`;
  renderSceneCountControls();
  updateWorkflowButtons();
}

function renderSteps() {
  const mode = state.currentProject?.template_mode || "video";
  const visibleSteps = mode === "article"
    ? STEP_DEFS.filter((step) => ["images", "covers", "images_missing", "covers_missing", "article"].includes(step.key))
    : STEP_DEFS;
  els.stepList.innerHTML = visibleSteps
    .map(
      (step) => `
        <label class="step-item">
          <input type="checkbox" data-step="${step.key}" ${step.defaultChecked === false ? "" : "checked"} />
          <div>
            <strong>${escapeHtml(step.label)}</strong>
            <div class="muted">${escapeHtml(step.desc)}</div>
          </div>
        </label>
      `
    )
    .join("");
}

function renderImageReview() {
  if (!els.imageReviewRequired || !els.confirmImagesBtn || !els.imageReviewPill || !els.imageReviewHelper) return;
  const status = state.imageReview;
  if (!state.currentProject) {
    els.imageReviewRequired.checked = true;
    els.confirmImagesBtn.disabled = true;
    els.imageReviewPill.textContent = "待确认";
    els.imageReviewPill.className = "pill pill--warn";
    els.imageReviewHelper.textContent = "先选择一个主题项目。";
    return;
  }
  const required = status?.required !== false;
  const confirmed = Boolean(status?.confirmed);
  const ready = Boolean(status?.ready_to_confirm);
  els.imageReviewRequired.checked = required;
  els.confirmImagesBtn.disabled = !required || !ready;
  if (!required) {
    els.imageReviewPill.textContent = "已关闭";
    els.imageReviewPill.className = "pill";
    els.imageReviewHelper.textContent = "当前允许不经人工确认直接合成视频。";
    return;
  }
  if (confirmed) {
    els.imageReviewPill.textContent = "已确认";
    els.imageReviewPill.className = "pill";
    els.imageReviewHelper.textContent = "当前场景图和封面图已确认，可以进入成片合成。";
    return;
  }
  els.imageReviewPill.textContent = ready ? "待确认" : "图片未齐";
  els.imageReviewPill.className = "pill pill--warn";
  const sceneText = `${status?.scene_generated ?? 0}/${status?.scene_expected ?? 0}`;
  const coverText = `${status?.cover_generated ?? 0}/${status?.cover_expected ?? 3}`;
  els.imageReviewHelper.textContent = ready
    ? "请检查场景图和封面图；不满意可以单张重绘，满意后点击确认。"
    : `确认前需要先生成完整图片：场景图 ${sceneText}，封面图 ${coverText}。`;
}

function statusToneClass(status) {
  if (status === "risk") return "pill--risk";
  if (status === "warn") return "pill--warn";
  return "";
}

function renderProjectStatus() {
  if (!els.projectStatusStrip) return;
  if (!state.currentProject) {
    els.projectStatusStrip.innerHTML = "";
    return;
  }
  const payload = state.projectStatus;
  if (!payload) {
    els.projectStatusStrip.innerHTML = `<div class="muted">项目状态加载中...</div>`;
    return;
  }
  const steps = Array.isArray(payload.steps) ? payload.steps : [];
  els.projectStatusStrip.innerHTML = steps
    .map((item) => {
      const title = [item.detail, item.action].filter(Boolean).join(" · ");
      return `
        <div class="project-status-item" title="${escapeHtml(title)}">
          <span class="pill ${statusToneClass(item.status)}">${escapeHtml(item.status || "ok")}</span>
          <strong>${escapeHtml(item.label || item.key || "")}</strong>
          <span>${escapeHtml(item.detail || "")}</span>
        </div>
      `;
    })
    .join("");
}

function renderJob() {
  const job = state.currentJob;
  if (!job) {
    els.jobStatusPill.textContent = "暂无任务";
    els.jobLog.textContent = "暂无日志";
    els.jobProgress.innerHTML = `<div class="muted">启动任务后，这里会显示每一个步骤的状态。</div>`;
    renderChatgptReloginButton();
    updateWorkflowButtons();
    return;
  }
  els.jobStatusPill.textContent = job.status || "running";
  els.jobStatusPill.className = `pill ${job.status === "succeeded" ? "" : job.status === "cancelled" ? "pill--warn" : ""}`;
  els.jobLog.textContent = job.log || "暂无日志";
  const loginRequired = isChatgptLoginError(job.log || "");
  const progress = job.progress || [];
  const progressHtml = progress.length
    ? progress
        .map(
          (item) => `
            <div class="step-item">
              <div>
                <strong>${escapeHtml(item.key)}</strong>
                <div class="muted">${escapeHtml(item.status)}</div>
              </div>
            </div>
          `
        )
        .join("")
    : `<div class="muted">任务已创建，但还没有进度。</div>`;
  const loginAssistHtml = loginRequired
    ? `
      <article class="file-callout file-callout--compact">
        <div>
          <strong>ChatGPT 生图需要重新登录</strong>
          <div class="muted" style="margin-top:6px;">检测到当前任务卡在 ChatGPT 登录态。点右侧按钮会打开可见浏览器，登录完成后回来重试当前图片即可。</div>
        </div>
        <div class="file-item__actions">
          <button class="btn btn--primary" data-chatgpt-relogin="true">重新登录 ChatGPT</button>
        </div>
      </article>
    `
    : "";
  const finalVideo = state.currentFiles?.artifacts?.final_video || null;
  const outputHtml = job.status === "succeeded" && finalVideo
    ? `
      <article class="file-callout file-callout--compact">
        <strong>最终成片已生成</strong>
        <div class="mono-path">${escapeHtml(finalVideo.absolute_path || "-")}</div>
        <div class="file-item__actions">
          <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(finalVideo))}">打开 mp4</button>
          <button class="btn btn--ghost" data-open-project-subpath="releases">打开成片目录</button>
        </div>
      </article>
    `
    : "";
  els.jobProgress.innerHTML = loginAssistHtml + progressHtml + outputHtml;
  renderChatgptReloginButton();
  updateWorkflowButtons();
}

function renderScenes() {
  const sceneStatus = state.sceneStatus;
  if (!sceneStatus) {
    els.sceneGrid.innerHTML = `<div class="muted">暂无场景图</div>`;
    els.sceneStatusPill.textContent = "未生成";
    return;
  }
  const items = sceneStatus.existing || [];
  const missingItems = sceneStatus.missing_items || [];
  const generatedCount = sceneStatus.generated_count ?? items.length;
  const expectedCount = sceneStatus.expected_count ?? generatedCount;
  const hiddenVariants = sceneStatus.hidden_variants ?? 0;
  els.sceneStatusPill.textContent = sceneStatus.complete
    ? `已完成 ${generatedCount}/${expectedCount}`
    : `已生成 ${generatedCount}/${expectedCount}`;
  const hintHtml = hiddenVariants
    ? `<div class="muted" style="grid-column:1 / -1;">已自动隐藏 ${hiddenVariants} 个旧占位/重复场景文件，仅展示可用于成片的场景图。</div>`
    : "";
  const existingHtml = items.length ? items.map(sceneCardHtml).join("") : "";
  const missingHtml = missingItems.length ? missingItems.map(missingSceneCardHtml).join("") : "";
  els.sceneGrid.innerHTML = `${hintHtml}${existingHtml}${missingHtml}` || `<div class="muted">还没有输出场景图。</div>`;
}

function renderCovers(files) {
  if (!els.coverGrid || !els.coverStatusPill) return;
  if (!files) {
    els.coverStatusPill.textContent = "未生成";
    els.coverGrid.innerHTML = `<div class="muted">暂无封面</div>`;
    return;
  }
  const covers = coverRecords(files);
  const generated = covers.filter((item) => item.image).length;
  els.coverStatusPill.textContent = generated ? `已生成 ${generated}/${covers.length}` : "未生成";
  els.coverGrid.innerHTML = coverGalleryCardsHtml(files);
}

function renderFiles() {
  const files = state.currentFiles;
  if (!files) {
    renderCovers(null);
    els.fileList.innerHTML = `<div class="muted">暂无文件</div>`;
    updateWorkflowButtons();
    return;
  }
  renderCovers(files);
  const items = [...(files.topics || []), ...(files.outputs || [])];
  const callout = artifactSummaryHtml(files);
  const coversHtml = coverPreviewHtml(files);
  if (!items.length) {
    els.fileList.innerHTML = [callout, coversHtml].filter(Boolean).join("") || `<div class="muted">项目里还没有产物。</div>`;
    updateWorkflowButtons();
    return;
  }
  const fileItems = items
    .map(
      (item) => `
        <article class="file-item">
          <div>
            <strong>${escapeHtml(item.relative_path)}</strong>
            <div class="muted">${formatBytes(item.size)} · ${formatDate(item.modified_at)}</div>
            ${item.absolute_path ? `<div class="mono-path mono-path--sm">${escapeHtml(item.absolute_path)}</div>` : ""}
          </div>
          <div class="file-item__actions">
            <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(item))}">打开</button>
            <button class="btn btn--ghost" data-delete-file="${escapeHtml(item.relative_path)}">删除</button>
          </div>
        </article>
      `
    )
    .join("");
  els.fileList.innerHTML = [callout, coversHtml, fileItems].filter(Boolean).join("");
  updateWorkflowButtons();
}

function numericInputValue(input) {
  if (!input) return null;
  const value = String(input.value || "").trim();
  if (!value) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function releaseMetricsPayloadFromFields() {
  return {
    views: numericInputValue(els.releaseViews),
    likes: numericInputValue(els.releaseLikes),
    comments: numericInputValue(els.releaseComments),
    shares: numericInputValue(els.releaseShares),
    favorites: numericInputValue(els.releaseFavorites),
    completion_rate: numericInputValue(els.releaseCompletionRate),
    metrics_notes: "",
  };
}

function clearReleaseMetricFields() {
  [
    els.releaseViews,
    els.releaseLikes,
    els.releaseComments,
    els.releaseShares,
    els.releaseFavorites,
    els.releaseCompletionRate,
  ].forEach((field) => {
    if (field) field.value = "";
  });
}

function releaseMetricsSummary(item) {
  const metrics = item?.metrics || {};
  const views = Number(metrics.views || 0);
  const likes = Number(metrics.likes || 0);
  const comments = Number(metrics.comments || 0);
  const shares = Number(metrics.shares || 0);
  const favorites = Number(metrics.favorites || 0);
  const completion = Number(metrics.completion_rate || 0);
  const engagement = likes + comments + shares + favorites;
  const engagementRate = views > 0 ? ((engagement / views) * 100).toFixed(2) : "0.00";
  return { views, likes, comments, shares, favorites, completion, engagement, engagementRate, notes: metrics.notes || "" };
}

function releaseMetricsInlineHtml(item) {
  const metrics = releaseMetricsSummary(item);
  const hasMetrics = metrics.views || metrics.likes || metrics.comments || metrics.shares || metrics.favorites || metrics.completion;
  if (!hasMetrics) return `<div class="muted">暂无表现数据，发布后可回填。</div>`;
  return `
    <div class="summary-grid summary-grid--compact">
      <div class="summary-card"><strong>播放</strong><span>${escapeHtml(String(metrics.views))}</span></div>
      <div class="summary-card"><strong>互动</strong><span>${escapeHtml(String(metrics.engagement))}</span></div>
      <div class="summary-card"><strong>互动率</strong><span>${escapeHtml(metrics.engagementRate)}%</span></div>
      <div class="summary-card"><strong>完播</strong><span>${escapeHtml(String(metrics.completion || 0))}%</span></div>
    </div>
    ${metrics.notes ? `<div class="muted">反馈：${escapeHtml(metrics.notes)}</div>` : ""}
  `;
}

function renderReleases() {
  const items = [...(state.releaseLinks || [])].sort(
    (a, b) => Number(b.published_at || b.created_at || 0) - Number(a.published_at || a.created_at || 0)
  );
  if (!items.length) {
    els.releaseList.innerHTML = `<div class="muted">暂无投放链接</div>`;
    return;
  }
  els.releaseList.innerHTML = items
    .map(
      (item) => `
        <article class="release-item">
          <h4>${escapeHtml(item.platform)}</h4>
          <p><a class="link-btn" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.url)}</a></p>
          <p>${escapeHtml(item.note || "无备注")}</p>
          ${releaseMetricsInlineHtml(item)}
          <div class="release-item__actions">
            <button class="btn btn--ghost" data-edit-release-metrics="${item.id}">回填数据</button>
            <button class="btn btn--ghost" data-delete-release="${item.id}">删除</button>
          </div>
        </article>
      `
    )
    .join("");
}

function openReleaseMetricsModal(releaseId) {
  const item = (state.releaseLinks || []).find((entry) => Number(entry.id) === Number(releaseId));
  if (!item) return window.alert("没有找到这条投放链接。");
  const metrics = item.metrics || {};
  showModal(
    `回填投放数据 · ${item.platform || ""}`,
    `
      <div class="stack">
        <div class="card card--inner">
          <div class="muted">${escapeHtml(item.url || "")}</div>
          <div>${escapeHtml(item.note || "")}</div>
        </div>
        <div class="form-grid">
          <label>
            <span>播放</span>
            <input id="modal-release-views" type="number" min="0" value="${escapeHtml(String(metrics.views || ""))}" />
          </label>
          <label>
            <span>点赞</span>
            <input id="modal-release-likes" type="number" min="0" value="${escapeHtml(String(metrics.likes || ""))}" />
          </label>
          <label>
            <span>评论</span>
            <input id="modal-release-comments" type="number" min="0" value="${escapeHtml(String(metrics.comments || ""))}" />
          </label>
          <label>
            <span>转发</span>
            <input id="modal-release-shares" type="number" min="0" value="${escapeHtml(String(metrics.shares || ""))}" />
          </label>
          <label>
            <span>收藏</span>
            <input id="modal-release-favorites" type="number" min="0" value="${escapeHtml(String(metrics.favorites || ""))}" />
          </label>
          <label>
            <span>完播率 %</span>
            <input id="modal-release-completion" type="number" min="0" max="100" step="0.1" value="${escapeHtml(String(metrics.completion_rate || ""))}" />
          </label>
          <label class="form-grid__wide">
            <span>复盘备注</span>
            <input id="modal-release-notes" type="text" value="${escapeHtml(metrics.notes || "")}" placeholder="例如：开头留存好，评论集中问价格" />
          </label>
        </div>
        <div class="toolbar">
          <button id="modal-release-metrics-save" class="btn btn--primary">保存回填</button>
          <button class="btn btn--ghost" data-close-modal="true">取消</button>
        </div>
      </div>
    `,
    (body) => {
      body.querySelector("#modal-release-metrics-save")?.addEventListener("click", async () => {
        const project = ensureProject();
        if (!project) return;
        const payload = {
          views: Number(body.querySelector("#modal-release-views")?.value || 0),
          likes: Number(body.querySelector("#modal-release-likes")?.value || 0),
          comments: Number(body.querySelector("#modal-release-comments")?.value || 0),
          shares: Number(body.querySelector("#modal-release-shares")?.value || 0),
          favorites: Number(body.querySelector("#modal-release-favorites")?.value || 0),
          completion_rate: Number(body.querySelector("#modal-release-completion")?.value || 0),
          notes: body.querySelector("#modal-release-notes")?.value?.trim() || "",
        };
        await api(`/api/projects/${project.id}/releases/${releaseId}/metrics`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        await refreshReleases();
        closeModal();
      });
    }
  );
}

function releaseAutomationFormPayload() {
  return {
    platform: els.releaseAutoPlatform?.value?.trim() || "douyin",
    account_name: els.releaseAutoAccount?.value?.trim() || "default",
    title: els.releaseAutoTitle?.value?.trim() || "",
    description: els.releaseAutoDescription?.value?.trim() || "",
    tags: els.releaseAutoTags?.value?.trim() || "",
    schedule: els.releaseAutoSchedule?.value?.trim() || "",
    headed: (els.releaseAutoBrowserMode?.value || "headless") === "headed",
    debug: false,
  };
}

async function persistReleaseAutomationDraft({ refresh = false } = {}) {
  const project = ensureProject();
  if (!project) return;
  await api(`/api/projects/${project.id}/release-automation/draft`, {
    method: "POST",
    body: JSON.stringify(releaseAutomationFormPayload()),
  });
  if (refresh) {
    await Promise.all([refreshReleaseAutomation(true), refreshReleases()]);
  }
}

function scheduleReleaseAutomationDraftSave({ refresh = false, delay = 500 } = {}) {
  const scheduledProjectId = state.currentProject?.id || null;
  if (state.releaseEditor.saveTimer) {
    window.clearTimeout(state.releaseEditor.saveTimer);
  }
  state.releaseEditor.saveTimer = window.setTimeout(async () => {
    state.releaseEditor.saveTimer = null;
    if ((state.currentProject?.id || null) !== scheduledProjectId) return;
    try {
      await persistReleaseAutomationDraft({ refresh });
    } catch (error) {
      console.warn(error);
    }
  }, delay);
}

function syncReleaseAutomationForm(force = false) {
  const payload = state.releaseAutomation;
  if (!payload || !els.releaseAutoPlatform) return;
  const draft = payload.draft || {};
  const draftSignature = JSON.stringify({ projectId: state.currentProject?.id || 0, draft });
  const projectChanged = state.releaseEditor.projectId !== (state.currentProject?.id || null);
  if (!force && !projectChanged && state.releaseEditor.lastDraft === draftSignature) return;
  const platforms = Array.isArray(payload.supported_platforms) ? payload.supported_platforms : [];
  if (platforms.length) {
    els.releaseAutoPlatform.innerHTML = platforms
      .map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label || item.key)}</option>`)
      .join("");
  }
  if (els.releaseAutoAccountOptions) {
    const accountOptions = Array.isArray(payload.account_options) ? payload.account_options : [];
    els.releaseAutoAccountOptions.innerHTML = accountOptions
      .map((item) => `<option value="${escapeHtml(item)}"></option>`)
      .join("");
  }
  els.releaseAutoPlatform.value = draft.platform || els.releaseAutoPlatform.value || platforms[0]?.key || "douyin";
  els.releaseAutoAccount.value = draft.account_name || "default";
  els.releaseAutoBrowserMode.value = draft.headed ? "headed" : "headless";
  els.releaseAutoSchedule.value = draft.schedule || "";
  els.releaseAutoTitle.value = draft.title || "";
  els.releaseAutoTags.value = draft.tags || "";
  els.releaseAutoDescription.value = draft.description || "";
  state.releaseEditor.projectId = state.currentProject?.id || null;
  state.releaseEditor.lastDraft = draftSignature;
}

function renderReleaseAutomation() {
  const payload = state.releaseAutomation;
  if (!payload) {
    if (els.releaseAutomationSummary) els.releaseAutomationSummary.innerHTML = `<div class="muted">自动发布状态尚未加载</div>`;
    if (els.releaseTaskMeta) els.releaseTaskMeta.innerHTML = `<div class="muted">暂无任务</div>`;
    if (els.releaseAutomationLog) els.releaseAutomationLog.textContent = "暂无自动发布任务";
    if (els.releaseTaskPill) {
      els.releaseTaskPill.textContent = "未启动";
      els.releaseTaskPill.className = "pill";
    }
    return;
  }
  const probe = payload.probe || {};
  const files = payload.files || {};
  const task = payload.task || null;
  const publishedRelease = payload.last_published_release || task?.result?.published_release || null;
  const account = payload.account || {};
  const loginQr = payload.login_qrcode || null;
  const accountName = account.display_name || account.account_id || "";
  const accountStatusMap = {
    connected: "已登录",
    not_logged_in: "未登录",
    missing: "未找到 cookie",
    unsupported: "暂未接入识别",
    error: "识别失败",
  };
  const accountStatusLabel = accountStatusMap[account.status] || (account.status || "未知");
  const accountSummary = accountName
    ? `${accountStatusLabel} · ${accountName}`
    : `${accountStatusLabel}${account.message ? ` · ${account.message}` : ""}`;
  const sanitizedLog = (() => {
    const raw = String(task?.log || "暂无自动发布任务");
    const lines = raw.split(/\r?\n/);
    const qrLine = /^[\s\u2580-\u259f\u25a0-\u25ff]+$/;
    let folded = false;
    const kept = [];
    for (const line of lines) {
      const text = line.trim();
      if (text.length > 20 && qrLine.test(text)) {
        folded = true;
        continue;
      }
      kept.push(line);
    }
    if (folded) {
      kept.unshift("[release] 终端字符二维码已折叠，请直接扫上方 PNG 二维码。");
    }
    return kept.join("\n").trim() || "暂无自动发布任务";
  })();
  const fileRow = (label, item) =>
    `<div>${escapeHtml(label)}：${
      item
        ? `<a class="link-btn" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.relative_path || item.name || label)}</a>`
        : `<span class="muted">未找到</span>`
    }</div>`;
  if (els.releaseAutomationSummary) {
    els.releaseAutomationSummary.innerHTML = `
      <div>环境状态：<span class="pill ${probe.status === "success" ? "" : "pill--warn"}">${escapeHtml(probe.status || "idle")}</span></div>
      <div>${escapeHtml(probe.message || "")}</div>
      <div>仓库路径：<span class="mono-inline">${escapeHtml(probe.repo_path || "-")}</span></div>
      <div>uv：<span class="mono-inline">${escapeHtml(probe.uv_bin || "uv")}</span> ${probe.uv_available ? "已找到" : "未找到"}</div>
      ${probe.local_chrome_path ? `<div>本机 Chrome：<span class="mono-inline">${escapeHtml(probe.local_chrome_path)}</span></div>` : ""}
      <div>账号别名：<span class="mono-inline">${escapeHtml(account.alias || (payload.draft || {}).account_name || "default")}</span></div>
      <div>平台账号：${escapeHtml(accountSummary)}</div>
      ${
        loginQr
          ? `
            <div class="release-qr-card">
              <div class="release-qr-card__head">
                <strong>登录二维码</strong>
                <a class="link-btn" href="${escapeHtml(loginQr.url)}" target="_blank" rel="noreferrer">打开大图</a>
              </div>
              <img class="release-qr-card__image" src="${escapeHtml(loginQr.url)}" alt="登录二维码" />
              <div class="muted">直接用抖音 APP 扫描这张图，比终端字符二维码稳定很多。</div>
            </div>
          `
          : ""
      }
      ${fileRow("成片视频", files.final_video)}
      ${fileRow("横屏封面", files.thumbnail_landscape)}
      ${fileRow("竖屏封面", files.thumbnail_portrait)}
      ${
        publishedRelease
          ? `<div>最近回填：<a class="link-btn" href="${escapeHtml(publishedRelease.url || "")}" target="_blank" rel="noreferrer">${escapeHtml(publishedRelease.url || "")}</a></div>`
          : ""
      }
    `;
  }
  if (els.releaseTaskPill) {
    els.releaseTaskPill.textContent = task?.status || "未启动";
    els.releaseTaskPill.className = `pill ${task?.status === "failed" || task?.status === "cancelled" ? "pill--warn" : ""}`.trim();
  }
  if (els.releaseTaskMeta) {
    els.releaseTaskMeta.innerHTML = task
      ? `
          <div>动作：${escapeHtml(task.action || "-")} · 平台：${escapeHtml(task.platform || "-")} · 别名：${escapeHtml(task.account_name || "-")}</div>
          <div>平台账号：${escapeHtml(accountSummary)}</div>
          <div>状态：${escapeHtml(task.status || "-")} · 运行中：${task.running ? "是" : "否"}</div>
          ${
            publishedRelease
              ? `<div>回填链接：<a class="link-btn" href="${escapeHtml(publishedRelease.url || "")}" target="_blank" rel="noreferrer">${escapeHtml(publishedRelease.url || "")}</a></div>`
              : ""
          }
          ${task.command ? `<div>命令：<span class="mono-inline">${escapeHtml(task.command)}</span></div>` : ""}
          ${task.cwd ? `<div>工作目录：<span class="mono-inline">${escapeHtml(task.cwd)}</span></div>` : ""}
          ${task.error ? `<div class="pill pill--warn">${escapeHtml(task.error)}</div>` : ""}
        `
      : `<div class="muted">这里会显示仓库、账号、源文件和最近一次任务状态。</div>`;
  }
  if (els.releaseAutomationLog) {
    els.releaseAutomationLog.textContent = sanitizedLog;
  }
  syncReleaseAutomationForm();
}

function renderConfig() {
  if (!state.config) {
    els.configFields.innerHTML = `<div class="muted">配置尚未加载</div>`;
    return;
  }
  const renderBadge = (label, kind) => `<span class="config-badge config-badge--${kind}">${escapeHtml(label)}</span>`;
  const renderSectionCheck = (section) => {
    const validation = section.validation || {};
    const status = validation.status || "idle";
    const labelMap = {
      idle: "未校验",
      unconfigured: "未配置",
      success: "校验通过",
      warning: "待联调",
      error: "校验失败",
    };
    const toneMap = {
      idle: "optional",
      unconfigured: "optional",
      success: "success",
      warning: "warning",
      error: "error",
    };
    return `
      <div class="config-item__check">
        ${renderBadge(labelMap[status] || status, toneMap[status] || "optional")}
        ${validation.message ? `<div style="margin-top:8px;">${escapeHtml(validation.message)}</div>` : ""}
        ${validation.checked_at ? `<div style="margin-top:6px;">最近校验：${escapeHtml(formatValidationTime(validation.checked_at))}</div>` : ""}
      </div>
    `;
  };
  const renderFieldControl = (field) => {
    const key = escapeHtml(field.key);
    const currentValue = field.value || "";
    const isTtsSpeaker = field.key === "VOLC_TTS_SPEAKER_1" || field.key === "VOLC_TTS_SPEAKER_2";
    if (field.kind === "select") {
      const options = (field.options || [])
        .map((item) => {
          const selected = item.value === currentValue ? "selected" : "";
          return `<option value="${escapeHtml(item.value)}" ${selected}>${escapeHtml(item.label || item.value)}</option>`;
        })
        .join("");
      const selectHtml = `<select data-config-key="${key}">${options}</select>`;
      if (isTtsSpeaker) {
        return `
          <div class="secret-input">
            ${selectHtml}
            <button class="icon-btn" type="button" data-preview-voice-key="${key}" title="试听">听</button>
          </div>
        `;
      }
      return selectHtml;
    }
    if (field.kind === "number") {
      return `<input data-config-key="${key}" type="number" step="any" value="${escapeHtml(currentValue)}" />`;
    }
    if (field.secret) {
      const revealed = !!state.revealedSecrets[field.key];
      return `
        <div class="secret-input">
          <input
            data-config-key="${key}"
            data-secret="true"
            type="${revealed ? "text" : "password"}"
            value=""
            placeholder="${escapeHtml(field.placeholder || "粘贴后写入，留空则不变")}"
          />
          <button class="icon-btn" type="button" data-toggle-secret="${key}" title="${revealed ? "隐藏" : "显示"}">${revealed ? "隐" : "显"}</button>
        </div>
      `;
    }
    return `<input data-config-key="${key}" type="text" value="${escapeHtml(currentValue)}" />`;
  };

  els.configFields.className = "config-layout";
  els.configFields.innerHTML = (state.config.sections || [])
    .map(
      (section) => `
        <section class="config-group">
          <div class="section-head">
            <div>
              <h4>${escapeHtml(section.title)}</h4>
              <p class="config-group__desc">${escapeHtml(section.description || "")}</p>
            </div>
            <div class="toolbar">
              ${section.validator ? `<button class="btn btn--ghost" data-validate-config="${escapeHtml(section.key)}">校验密钥</button>` : ""}
            </div>
          </div>
          ${renderSectionCheck(section)}
          <div class="config-group__fields">
            ${(section.fields || [])
              .map(
                (field) => `
                  <article class="config-item">
                    <div class="config-item__head">
                      <div>
                        <div class="config-item__title">
                          <strong>${escapeHtml(field.label)}</strong>
                          ${renderBadge(field.required ? "必填" : "可选", field.required ? "required" : "optional")}
                          ${field.configured ? renderBadge("已配置", "configured") : ""}
                        </div>
                        <div class="config-item__key">${escapeHtml(field.key)}</div>
                      </div>
                    </div>
                    <div class="config-control">${renderFieldControl(field)}</div>
                    <div class="config-item__help">${escapeHtml(field.help || "")}</div>
                  </article>
                `
              )
              .join("")}
          </div>
        </section>
      `
    )
    .join("");
}

function renderPackaging() {
  if (!els.packagingSummary || !els.packagingLog || !els.packagingStatusPill) return;
  const payload = state.packaging;
  if (!payload) {
    els.packagingSummary.innerHTML = `<div class="muted">导出状态尚未加载</div>`;
    els.packagingLog.textContent = "暂无导出任务";
    els.packagingStatusPill.textContent = "未启动";
    els.packagingStatusPill.className = "pill";
    if (els.startPortableBuildBtn) els.startPortableBuildBtn.disabled = true;
    if (els.startZipBuildBtn) els.startZipBuildBtn.disabled = true;
    if (els.cancelPackagingBtn) els.cancelPackagingBtn.disabled = true;
    if (els.openPackagingOutputBtn) els.openPackagingOutputBtn.disabled = true;
    return;
  }
  const task = payload.task || null;
  const artifacts = payload.artifacts || {};
  const available = !!payload.available;
  const running = !!task?.running;
  const status = task?.status || "idle";
  const statusMap = {
    idle: "未启动",
    running: "导出中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已取消",
  };
  const pathLine = (label, value, target, exists) => `
    <div>
      ${label}：<span class="mono-inline">${escapeHtml(value || "—")}</span>
      ${exists ? `<button class="btn btn--ghost" data-open-packaging-target="${escapeHtml(target)}">打开</button>` : ""}
    </div>
  `;
  els.packagingSummary.innerHTML = `
    <div>${available ? "打包环境已就绪，可直接导出当前桌面版。" : "当前运行环境里没有可用打包脚本，暂时无法导出 EXE。"}</div>
    <div>Python：<span class="mono-inline">${escapeHtml(payload.python_path || "—")}</span></div>
    ${pathLine("输出目录", artifacts.output_root, "output", artifacts.output_exists)}
    ${pathLine("便携目录", artifacts.portable_dir, "portable", artifacts.portable_exists)}
    ${pathLine("EXE 文件", artifacts.exe_path, "exe", false)}
    ${pathLine("ZIP 文件", artifacts.zip_path, "zip", artifacts.zip_exists)}
    ${artifacts.zip_exists ? `<div>ZIP 大小：${escapeHtml(formatByteSize(artifacts.zip_size))}</div>` : ""}
    ${task ? `<div>最近任务：${escapeHtml(task.mode || "portable")} · 开始 ${escapeHtml(formatMaybeTimestamp(task.started_at))}${task.finished_at ? ` · 结束 ${escapeHtml(formatMaybeTimestamp(task.finished_at))}` : ""}</div>` : ""}
    ${task?.error ? `<div class="pill pill--warn">${escapeHtml(task.error)}</div>` : ""}
  `;
  els.packagingLog.textContent = task?.log || "暂无导出任务";
  els.packagingStatusPill.textContent = statusMap[status] || status;
  els.packagingStatusPill.className = `pill ${status === "failed" || status === "cancelled" ? "pill--warn" : ""}`.trim();
  if (els.startPortableBuildBtn) els.startPortableBuildBtn.disabled = !available || running;
  if (els.startZipBuildBtn) els.startZipBuildBtn.disabled = !available || running;
  if (els.cancelPackagingBtn) els.cancelPackagingBtn.disabled = !running;
  if (els.openPackagingOutputBtn) els.openPackagingOutputBtn.disabled = !artifacts.output_exists;
}

async function refreshTemplates() {
  state.templates = await api("/api/templates");
  ensureSelectedTemplateKey();
  renderTemplates();
  renderProjects();
}

async function refreshProjects() {
  state.projects = await api("/api/projects");
  ensureSelectedTemplateKey();
  renderProjects();
  renderTemplates();
  if (!state.currentProject) {
    const firstProject = projectsForSelectedTemplate()[0] || state.projects[0];
    if (firstProject) await openProject(firstProject.id);
  }
}

async function refreshConfig() {
  state.config = await api("/api/settings/secrets");
  renderConfig();
  renderImageProviderSwitch();
}

async function refreshPackaging() {
  state.packaging = await api("/api/settings/packaging");
  renderPackaging();
  if (state.packaging?.task?.running) {
    startPackagingPolling();
  } else {
    stopPackagingPolling();
  }
}

async function refreshTtsPreviews() {
  try {
    state.ttsPreviews = await api("/api/settings/tts-previews");
  } catch (error) {
    console.warn(error);
    state.ttsPreviews = null;
  }
}

async function validateConfigSections(targets = null) {
  await api("/api/settings/secrets/validate", {
    method: "POST",
    body: JSON.stringify({ targets }),
  });
  await refreshConfig();
}

async function refreshAutoVideoStatus({ openCreatedProject = false } = {}) {
  try {
    const payload = await api("/api/auto-video/latest");
    state.autoVideo = payload.task || null;
    if (state.autoVideoModalVisible) {
      renderAutoVideoModal();
    }
    const projectId = Number(state.autoVideo?.project_id || state.autoVideo?.result?.project_id || 0);
    if (openCreatedProject && projectId && state.autoVideoOpenedProjectId !== projectId) {
      state.autoVideoOpenedProjectId = projectId;
      await refreshProjects();
      await openProject(projectId);
    }
    if (!payload.running && state.autoVideoTimer) {
      clearInterval(state.autoVideoTimer);
      state.autoVideoTimer = null;
      await refreshProjects();
      if (projectId) {
        await openProject(projectId);
      }
    }
  } catch (error) {
    console.warn(error);
  }
}

async function refreshFiles() {
  const project = ensureProject();
  if (!project) return;
  state.currentFiles = await api(`/api/projects/${project.id}/files`);
  renderFiles();
}

async function refreshSceneStatus() {
  const project = ensureProject();
  if (!project) return;
  state.sceneStatus = await api(`/api/projects/${project.id}/scene-images/status`);
  renderScenes();
  renderSceneCountControls();
}

async function refreshImageReview() {
  const project = ensureProject();
  if (!project) return;
  state.imageReview = await api(`/api/projects/${project.id}/image-review`);
  renderImageReview();
}

async function refreshProjectStatus() {
  const project = ensureProject();
  if (!project) return;
  state.projectStatus = await api(`/api/projects/${project.id}/status`);
  renderProjectStatus();
}

async function refreshLatestJob() {
  const project = ensureProject();
  if (!project) return;
  const payload = await api(`/api/projects/${project.id}/jobs/latest`);
  state.currentJob = payload.job;
  renderJob();
  if (state.currentJob?.status === "succeeded") {
    await Promise.all([refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshProjectStatus()]);
  }
}

async function refreshReleases() {
  const project = ensureProject();
  if (!project) return;
  state.releaseLinks = await api(`/api/projects/${project.id}/releases`);
  renderReleases();
}

async function refreshReleaseAutomation(forceForm = false) {
  const project = ensureProject();
  if (!project) return;
  state.releaseAutomation = await api(`/api/projects/${project.id}/release-automation`);
  renderReleaseAutomation();
  syncReleaseAutomationForm(forceForm);
}

async function refreshContentBundle(forceEditor = false) {
  const project = ensureProject();
  if (!project) return;
  state.currentContent = await api(`/api/projects/${project.id}/content`);
  renderContentBundle({ forceEditor });
}

async function openProject(projectId) {
  state.currentProject = state.projects.find((item) => item.id === projectId) || await api(`/api/projects/${projectId}`);
  state.selectedTemplateKey = state.currentProject.template || state.selectedTemplateKey;
  renderProjects();
  renderTemplates();
  renderSteps();
  els.workspaceTitle.textContent = state.currentProject.topic_name;
  els.workspaceSubtitle.textContent = `${state.currentProject.template} · ${state.currentProject.template_mode === "article" ? "图文工作流" : "视频工作流"} · 最近状态 ${state.currentProject.last_job_status || "idle"}`;
  await Promise.all([refreshContentBundle(true), refreshFiles(), refreshSceneStatus(), refreshImageReview(), refreshProjectStatus(), refreshLatestJob(), refreshReleases(), refreshReleaseAutomation(true)]);
}

async function checkBackend() {
  try {
    await api("/api/projects");
    setBackendOnline(true);
    return true;
  } catch (error) {
    setBackendOnline(false);
    return false;
  }
}

async function boot() {
  renderSteps();
  updateWorkflowButtons();
  const online = await checkBackend();
  if (!online) return;
  await Promise.all([refreshTemplates(), refreshProjects(), refreshConfig(), refreshPackaging(), refreshTtsPreviews()]);
  await refreshAutoVideoStatus();
  if (state.autoVideo?.running) startAutoVideoPolling();
  if (state.currentProject) {
    await openProject(state.currentProject.id);
  }
  startPolling();
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = window.setInterval(async () => {
    if (!state.backendOnline || !state.currentProject) return;
    try {
      await Promise.all([refreshContentBundle(), refreshLatestJob(), refreshSceneStatus(), refreshFiles(), refreshReleases(), refreshReleaseAutomation()]);
    } catch (error) {
      console.warn(error);
    }
  }, 1500);
}

function startAutoVideoPolling() {
  if (state.autoVideoTimer) clearInterval(state.autoVideoTimer);
  state.autoVideoTimer = window.setInterval(async () => {
    if (!state.backendOnline) return;
    await refreshAutoVideoStatus({ openCreatedProject: true });
  }, 2000);
}

function stopPackagingPolling() {
  if (state.packagingTimer) {
    clearInterval(state.packagingTimer);
    state.packagingTimer = null;
  }
}

function startPackagingPolling() {
  if (state.packagingTimer) clearInterval(state.packagingTimer);
  state.packagingTimer = window.setInterval(async () => {
    if (!state.backendOnline) return;
    try {
      await refreshPackaging();
    } catch (error) {
      console.warn(error);
    }
  }, 2500);
}

function collectConfigValues() {
  const values = {};
  document.querySelectorAll("[data-config-key]").forEach((input) => {
    values[input.dataset.configKey] = input.value;
  });
  return values;
}

function configFieldValue(key, fallback = "") {
  for (const section of state.config?.sections || []) {
    for (const field of section.fields || []) {
      if (field.key === key) return field.value || fallback;
    }
  }
  return fallback;
}

function imageProviderLabel(value) {
  return IMAGE_PROVIDER_OPTIONS.find((item) => item.value === value)?.label || value || "未设置";
}

function renderImageProviderSwitch() {
  if (!els.imageProviderSelect) return;
  const currentValue = configFieldValue("IMAGE_PROVIDER", "auto_no_apiyi");
  els.imageProviderSelect.innerHTML = IMAGE_PROVIDER_OPTIONS.map((item) => {
    const selected = item.value === currentValue ? "selected" : "";
    return `<option value="${escapeHtml(item.value)}" ${selected}>${escapeHtml(item.label)}</option>`;
  }).join("");
  if (els.imageProviderCurrent) {
    els.imageProviderCurrent.textContent = `当前：${imageProviderLabel(currentValue)}`;
  }
}

function renderSceneCountControls() {
  if (!els.sceneCountMode || !els.sceneCountFixed || !els.sceneCountCurrent) return;
  const settings = state.currentContent?.project_settings || {};
  const mode = settings.scene_count_mode === "fixed" ? "fixed" : "auto";
  const fixed = Math.max(1, Math.min(Number(settings.scene_count_fixed || 6), 24));
  if (document.activeElement !== els.sceneCountMode) {
    els.sceneCountMode.value = mode;
  }
  if (document.activeElement !== els.sceneCountFixed) {
    els.sceneCountFixed.value = String(fixed);
  }
  els.sceneCountFixed.disabled = mode !== "fixed";
  const summaryCount = state.currentContent?.summary?.scene_count || state.sceneStatus?.expected_count || "—";
  els.sceneCountCurrent.textContent = mode === "fixed"
    ? `当前：固定 ${fixed} 张`
    : `当前：自动估算，现计划 ${summaryCount} 张`;
}

function stepValues() {
  return Array.from(document.querySelectorAll("[data-step]:checked")).map((el) => el.dataset.step);
}

function reportHtml(title, payload) {
  return `
    <div class="stack">
      <div class="card card--inner">
        <strong>${escapeHtml(title)}</strong>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "内存对象")}</div>
      </div>
      <pre class="json-box">${escapeHtml(JSON.stringify(payload.result, null, 2))}</pre>
    </div>
  `;
}

function qualityGateHtml(payload) {
  const result = payload.result || {};
  const sections = result.sections || {};
  const imageMetrics = sections.images?.metrics || {};
  const visualMetrics = sections.images?.visual?.metrics || {};
  const sectionRows = [
    ["文案", sections.content],
    ["图片", sections.images],
    ["成片", sections.video],
  ];
  const issueHtml = sectionRows
    .flatMap(([label, section]) => (section?.issues || []).map((item) => ({ label, ...item })))
    .slice(0, 16)
    .map(
      (item) => `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(item.label)} · ${escapeHtml(item.where || "")}</strong>
            <span class="pill ${item.level === "risk" ? "pill--warn" : ""}">${escapeHtml(item.level || "info")}</span>
          </div>
          <div>${escapeHtml(item.issue || "")}</div>
          ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
        </article>
      `
    )
    .join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>质量总检</strong>
          <span class="pill">${escapeHtml(String(result.overall_score ?? 0))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "内存对象")}</div>
        <div class="toolbar" style="margin-top:12px;">
          <button class="btn btn--primary" data-quality-repair="image-prompts">重建图片提示词</button>
          <button class="btn btn--ghost" data-quality-refresh="true">重新质检</button>
        </div>
      </div>
      <div class="summary-grid">
        ${sectionRows
          .map(
            ([label, section]) => `
              <div class="summary-card">
                <strong>${escapeHtml(label)}</strong>
                <span>${escapeHtml(String(section?.score ?? "—"))} 分</span>
              </div>
            `
          )
          .join("")}
        <div class="summary-card"><strong>图片吸引力</strong><span>${escapeHtml(String(imageMetrics.avg_image_appeal_score ?? visualMetrics.avg_appeal_score ?? "—"))} 分</span></div>
        <div class="summary-card"><strong>低吸引力图</strong><span>${escapeHtml(String(imageMetrics.low_image_appeal_count ?? visualMetrics.low_appeal_count ?? 0))} 张</span></div>
        <div class="summary-card"><strong>提示词分层</strong><span>${escapeHtml(String(imageMetrics.image_prompt_layer_score ?? "—"))} 分</span></div>
        <div class="summary-card"><strong>弱提示词</strong><span>${escapeHtml(String(imageMetrics.weak_image_prompt_count ?? 0))} 条</span></div>
      </div>
      ${issueHtml || `<div class="muted">没有发现明显风险。</div>`}
      ${
        Array.isArray(result.next_actions) && result.next_actions.length
          ? `<div class="card card--inner"><strong>下一步建议</strong><div class="stack stack--sm">${result.next_actions
              .map((item) => `<div class="muted">- ${escapeHtml(item)}</div>`)
              .join("")}</div></div>`
          : ""
      }
      <details>
        <summary>查看完整 JSON</summary>
        <pre class="json-box">${escapeHtml(JSON.stringify(result, null, 2))}</pre>
      </details>
    </div>
  `;
}

function viralRewriteHtml(result) {
  const before = result.before || {};
  const after = result.after || {};
  const provider = result.provider || "unknown";
  const deepseekError = result.deepseek_error || "";
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>一键总编优化</strong>
          <span class="pill ${provider.includes("failed") ? "pill--warn" : ""}">${escapeHtml(provider)}</span>
        </div>
        <div class="muted">${result.changed ? "content.md 已更新，图片确认状态会重新变为待确认。" : "没有检测到内容变化。"}</div>
        ${deepseekError ? `<div class="pill pill--warn">${escapeHtml(deepseekError)}</div>` : ""}
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>优化前</strong><span>${escapeHtml(String(before.overall_score ?? "—"))} 分</span></div>
        <div class="summary-card"><strong>优化后</strong><span>${escapeHtml(String(after.overall_score ?? "—"))} 分</span></div>
        <div class="summary-card"><strong>开头</strong><span>${escapeHtml(String(after.opening_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>中段</strong><span>${escapeHtml(String(after.retention_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>互动</strong><span>${escapeHtml(String(after.interaction_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>图片提示词</strong><span>${result.changed ? "已重建" : "未变化"}</span></div>
      </div>
      <div class="muted">${escapeHtml(after.verdict || "")}</div>
    </div>
  `;
}

function channelHistoryHtml(payload) {
  const result = payload.result || {};
  const recommendations = Array.isArray(result.recommendations) ? result.recommendations : [];
  const hooks = Array.isArray(result.best_hooks) ? result.best_hooks : [];
  const keywords = Array.isArray(result.top_keywords) ? result.top_keywords : [];
  const weaknesses = Array.isArray(result.common_weaknesses) ? result.common_weaknesses : [];
  const topProjects = Array.isArray(result.top_projects) ? result.top_projects : [];
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>${escapeHtml(result.channel_name || result.template_key || "频道")} · 历史复盘</strong>
          <span class="pill">${escapeHtml(String(result.history_count || 0))} 个项目</span>
        </div>
        <div class="muted">已回填表现数据：${escapeHtml(String(result.with_release_metrics_count || 0))} 个项目</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/channel_history.json")}</div>
      </div>
      <div class="card card--inner">
        <strong>下一条建议</strong>
        <div class="stack stack--sm">
          ${recommendations.length ? recommendations.map((item) => `<div class="muted">- ${escapeHtml(item)}</div>`).join("") : `<div class="muted">历史数据还不够，先继续生产并回填表现。</div>`}
        </div>
      </div>
      <div class="summary-grid">
        ${keywords.slice(0, 6).map((item) => `<div class="summary-card"><strong>${escapeHtml(item.keyword || "")}</strong><span>${escapeHtml(String(item.count || 0))} 次</span></div>`).join("")}
      </div>
      <div class="card card--inner">
        <strong>历史优质开头</strong>
        <div class="stack stack--sm">
          ${hooks.length ? hooks.slice(0, 6).map((item) => `
            <article class="card card--inner">
              <div class="section-head">
                <span>#${escapeHtml(String(item.project_id || ""))} ${escapeHtml(item.topic || "")}</span>
                <span class="pill">开头 ${escapeHtml(String(item.opening_score || 0))}</span>
              </div>
              <div>${escapeHtml(item.hook || "")}</div>
            </article>
          `).join("") : `<div class="muted">还没有可复用的开头样本。</div>`}
        </div>
      </div>
      <div class="card card--inner">
        <strong>常见问题</strong>
        <div class="stack stack--sm">
          ${weaknesses.length ? weaknesses.map((item) => `<div class="muted">- ${escapeHtml(item.issue || "")} · ${escapeHtml(String(item.count || 0))} 次</div>`).join("") : `<div class="muted">暂未统计到重复问题。</div>`}
        </div>
      </div>
      <details>
        <summary>表现较好的历史项目</summary>
        <div class="stack stack--sm">
          ${topProjects.map((item) => `
            <article class="card card--inner">
              <div class="section-head">
                <strong>#${escapeHtml(String(item.project_id || ""))} ${escapeHtml(item.title || item.topic || "")}</strong>
                <span class="pill">${escapeHtml(String(item.performance_score || 0))}</span>
              </div>
              <div class="muted">${escapeHtml(item.hook || "")}</div>
            </article>
          `).join("")}
        </div>
      </details>
    </div>
  `;
}

function optimizationPlanHtml(payload) {
  const result = payload.result || {};
  const summary = result.summary || {};
  const actions = Array.isArray(result.actions) ? result.actions : [];
  const reports = result.reports || {};
  const history = reports.channel_history || {};
  const actionButton = (action) => {
    const type = action.action_type || "";
    const label = escapeHtml(action.label || action.key || "执行");
    if (type === "viral_rewrite") return `<button class="btn btn--primary" data-auto-opt-action="viral-rewrite">${label}</button>`;
    if (type === "repair_image_prompts") return `<button class="btn btn--primary" data-quality-repair="image-prompts">${label}</button>`;
    if (type === "apply_resume_steps") {
      const steps = Array.isArray(action.payload?.steps) ? action.payload.steps.join(",") : "";
      return `<button class="btn btn--primary" data-apply-resume-steps="${escapeHtml(steps)}">${label}</button>`;
    }
    if (type === "release_checklist") return `<button class="btn btn--primary" data-auto-opt-action="release-checklist">${label}</button>`;
    if (type === "open_content") return `<button class="btn btn--ghost" data-auto-opt-action="open-content">${label}</button>`;
    return `<button class="btn btn--ghost" data-auto-opt-action="open-produce">${label}</button>`;
  };
  const actionHtml = actions
    .map((action) => `
      <article class="card card--inner">
        <div class="section-head">
          <strong>${escapeHtml(action.label || action.key || "")}</strong>
          <span class="pill">${escapeHtml(String(action.priority || 0))}</span>
        </div>
        <div class="muted">${escapeHtml(action.reason || "")}</div>
        <div class="toolbar">${actionButton(action)}</div>
      </article>
    `)
    .join("");
  const recs = Array.isArray(history.recommendations) ? history.recommendations : [];
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>智能优化路线</strong>
          <span class="pill ${Number(result.score || 0) < 72 ? "pill--warn" : ""}">${escapeHtml(String(result.score ?? 0))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/creative_optimization_plan.json")}</div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>质量</strong><span>${escapeHtml(String(summary.quality_score || 0))}</span></div>
        <div class="summary-card"><strong>节奏</strong><span>${escapeHtml(String(summary.rhythm_score || 0))}</span></div>
        <div class="summary-card"><strong>图片分层</strong><span>${escapeHtml(String(summary.image_layer_score || 0))}</span></div>
        <div class="summary-card"><strong>历史项目</strong><span>${escapeHtml(String(summary.history_count || 0))}</span></div>
        <div class="summary-card"><strong>投放反馈</strong><span>${escapeHtml(String(summary.release_metrics_count || 0))}</span></div>
        <div class="summary-card"><strong>生产状态</strong><span>${summary.ready_for_release ? "可发布" : summary.ready_for_video ? "可成片" : "待补齐"}</span></div>
      </div>
      <div class="card card--inner">
        <strong>推荐动作</strong>
        <div class="stack stack--sm">${actionHtml || `<div class="muted">当前没有明确动作，按目标继续生产或发布。</div>`}</div>
      </div>
      ${
        recs.length
          ? `<div class="card card--inner"><strong>频道记忆提醒</strong><div class="stack stack--sm">${recs
              .slice(0, 4)
              .map((item) => `<div class="muted">- ${escapeHtml(item)}</div>`)
              .join("")}</div></div>`
          : ""
      }
    </div>
  `;
}

function imagePromptLayersHtml(payload) {
  const result = payload.result || {};
  const metrics = result.metrics || {};
  const issues = Array.isArray(result.issues) ? result.issues : [];
  const entries = Array.isArray(result.entries) ? result.entries : [];
  const issueHtml = issues
    .slice(0, 10)
    .map((item) => `
      <article class="card card--inner">
        <div class="section-head">
          <strong>${escapeHtml(item.where || "图片提示词")}</strong>
          <span class="pill ${statusToneClass(item.level)}">${escapeHtml(item.level || "info")}</span>
        </div>
        <div>${escapeHtml(item.issue || "")}</div>
        ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
      </article>
    `)
    .join("");
  const entryHtml = entries
    .slice(0, 14)
    .map((item) => {
      const layers = item.layers || {};
      const layerLabels = [
        ["channel", "频道"],
        ["topic", "主题"],
        ["script_anchor", "口播"],
        ["subject_action", "主体动作"],
        ["emotion_conflict", "冲突"],
        ["text_rules", "文字"],
        ["safety", "禁忌"],
      ];
      return `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(item.label || item.target || "")}</strong>
            <span class="pill ${Number(item.score || 0) < 72 ? "pill--warn" : ""}">${escapeHtml(String(item.score || 0))} 分</span>
          </div>
          <div class="toolbar toolbar--tight">
            ${layerLabels.map(([key, label]) => `<span class="pill ${layers[key] ? "" : "pill--warn"}">${escapeHtml(label)} ${layers[key] ? "✓" : "缺"}</span>`).join("")}
          </div>
          ${Array.isArray(item.suggestions) && item.suggestions.length ? `<div class="muted">${item.suggestions.map(escapeHtml).join("；")}</div>` : ""}
        </article>
      `;
    })
    .join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>图片提示词分层</strong>
          <span class="pill">${escapeHtml(String(result.score ?? 0))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/image_prompt_layers.json")}</div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>提示词</strong><span>${escapeHtml(String(metrics.prompt_count || 0))}</span></div>
        <div class="summary-card"><strong>场景图</strong><span>${escapeHtml(String(metrics.scene_prompt_count || 0))}</span></div>
        <div class="summary-card"><strong>平均分层</strong><span>${escapeHtml(String(metrics.avg_layer_score || 0))}</span></div>
        <div class="summary-card"><strong>弱提示词</strong><span>${escapeHtml(String(metrics.weak_prompt_count || 0))}</span></div>
      </div>
      ${issueHtml || `<div class="muted">图片提示词分层没有明显风险。</div>`}
      <div class="card card--inner">
        <strong>逐张分层</strong>
        <div class="stack stack--sm">${entryHtml || `<div class="muted">暂无图片提示词。</div>`}</div>
      </div>
      <div class="toolbar">
        <button class="btn btn--primary" data-quality-repair="image-prompts">重建图片提示词</button>
      </div>
    </div>
  `;
}

function rhythmReportHtml(payload) {
  const result = payload.result || {};
  const metrics = result.metrics || {};
  const engagement = result.engagement || {};
  const issues = Array.isArray(result.issues) ? result.issues : [];
  const beats = Array.isArray(result.beats) ? result.beats : [];
  const issueHtml = issues
    .map((item) => `
      <article class="card card--inner">
        <div class="section-head">
          <strong>${escapeHtml(item.where || "节奏")}</strong>
          <span class="pill ${statusToneClass(item.level)}">${escapeHtml(item.level || "info")}</span>
        </div>
        <div>${escapeHtml(item.issue || "")}</div>
        ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
      </article>
    `)
    .join("");
  const beatHtml = beats
    .slice(0, 36)
    .map((item) => `
      <div class="step-item">
        <div>
          <strong>${escapeHtml(String(item.index || ""))}. ${escapeHtml(item.signal || "")}</strong>
          <div class="muted">${escapeHtml(item.text || "")}</div>
        </div>
        <span class="pill">${escapeHtml(String(item.chars || 0))}字</span>
      </div>
    `)
    .join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>脚本/成片节奏体检</strong>
          <span class="pill">${escapeHtml(String(result.score ?? 0))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/script_rhythm.json")}</div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>开头</strong><span>${escapeHtml(String(engagement.opening_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>中段</strong><span>${escapeHtml(String(engagement.retention_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>互动</strong><span>${escapeHtml(String(engagement.interaction_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>推进信号</strong><span>${escapeHtml(String(metrics.push_signal_count || 0))}</span></div>
        <div class="summary-card"><strong>最长平铺</strong><span>${escapeHtml(String(metrics.max_plain_gap || 0))}句</span></div>
        <div class="summary-card"><strong>单图停留</strong><span>${escapeHtml(String(metrics.avg_scene_hold_sec || 0))}秒</span></div>
      </div>
      ${issueHtml || `<div class="muted">节奏没有明显风险。</div>`}
      <details>
        <summary>查看节奏拆解</summary>
        <div class="stack stack--sm">${beatHtml || `<div class="muted">暂无可拆解内容。</div>`}</div>
      </details>
    </div>
  `;
}

function rhythmEnhanceHtml(payload) {
  const result = payload.result || {};
  const edits = result.edits || {};
  const before = result.before || {};
  const after = result.after || {};
  const beforeMetrics = before.metrics || {};
  const afterMetrics = after.metrics || {};
  const afterIssues = Array.isArray(after.issues) ? after.issues : [];
  const issueHtml = afterIssues
    .slice(0, 4)
    .map((item) => `
      <article class="card card--inner">
        <div class="section-head">
          <strong>${escapeHtml(item.where || "节奏")}</strong>
          <span class="pill ${statusToneClass(item.level)}">${escapeHtml(item.level || "info")}</span>
        </div>
        <div>${escapeHtml(item.issue || "")}</div>
        ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
      </article>
    `)
    .join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>节奏增强完成</strong>
          <span class="pill">${escapeHtml(String(before.score ?? "—"))} → ${escapeHtml(String(after.score ?? "—"))} 分</span>
        </div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/script_rhythm_enhance.json")}</div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>拆长句</strong><span>${escapeHtml(String(edits.split_count || 0))}</span></div>
        <div class="summary-card"><strong>补转折</strong><span>${escapeHtml(String(edits.bridge_count || 0))}</span></div>
        <div class="summary-card"><strong>互动句</strong><span>${edits.interaction_added ? "已补" : "无需补"}</span></div>
        <div class="summary-card"><strong>最长平铺</strong><span>${escapeHtml(String(beforeMetrics.max_plain_gap || 0))} → ${escapeHtml(String(afterMetrics.max_plain_gap || 0))}</span></div>
        <div class="summary-card"><strong>长句数</strong><span>${escapeHtml(String(beforeMetrics.long_line_count || 0))} → ${escapeHtml(String(afterMetrics.long_line_count || 0))}</span></div>
      </div>
      ${issueHtml || `<div class="muted">增强后没有明显节奏风险。</div>`}
    </div>
  `;
}

function videoPreflightHtml(payload) {
  const result = payload.result || {};
  const blockers = Array.isArray(result.blockers) ? result.blockers : [];
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  const metrics = result.metrics || {};
  const timelineCount = Number(metrics.timeline_scene_count || 0);
  const sceneGenerated = Number(metrics.scene_generated || 0);
  const needsTimelineRepair = blockers.some((item) => item?.where === "场景时轴")
    || !metrics.timeline_exists
    || (sceneGenerated > 0 && timelineCount !== sceneGenerated);
  const issueText = (item) => `${item?.where || ""} ${item?.issue || ""} ${item?.fix || ""}`;
  const needsSubtitleRepair = blockers.some((item) => /字幕|ASR|语音识别|对齐/.test(issueText(item)));
  const needsImageRepair = blockers.some((item) => /场景图|封面|图片|出图/.test(issueText(item)));
  const actionButtonsFor = (item) => {
    const text = issueText(item);
    const actions = [];
    if (/字幕|ASR|语音识别|对齐/.test(text)) {
      actions.push(`<button class="btn btn--primary" data-preflight-run="subtitles">重做字幕</button>`);
      actions.push(`<button class="btn btn--ghost" data-preflight-run="subtitles,video">重做字幕后继续成片</button>`);
    }
    if (/场景图|图片|出图/.test(text)) {
      actions.push(`<button class="btn btn--primary" data-preflight-run="images_missing">补缺失场景图</button>`);
      actions.push(`<button class="btn btn--ghost" data-preflight-run="images_missing,video">补图后继续成片</button>`);
    }
    if (/封面/.test(text)) {
      actions.push(`<button class="btn btn--primary" data-preflight-run="covers_missing">补缺失封面</button>`);
    }
    return actions.length ? `<div class="toolbar toolbar--compact">${actions.join("")}</div>` : "";
  };
  const issueCards = (items, label) => items
    .map(
      (item) => `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(label)} · ${escapeHtml(item.where || "")}</strong>
            <span class="pill ${label === "阻止项" ? "pill--warn" : ""}">${escapeHtml(item.level || "")}</span>
          </div>
          <div>${escapeHtml(item.issue || "")}</div>
          ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
          ${label === "阻止项" ? actionButtonsFor(item) : ""}
        </article>
      `
    )
    .join("");
  const topActions = [
    needsSubtitleRepair ? `<button class="btn btn--primary" data-preflight-run="subtitles,video">重做字幕后继续成片</button>` : "",
    needsSubtitleRepair ? `<button class="btn btn--ghost" data-preflight-run="subtitles">只重做字幕</button>` : "",
    needsImageRepair ? `<button class="btn btn--ghost" data-preflight-run="images_missing,video">补图后继续成片</button>` : "",
    needsTimelineRepair ? `<button class="btn btn--primary" data-preflight-repair="timeline">重建场景时轴</button>` : "",
    `<button class="btn btn--ghost" data-preflight-refresh="true">重新总检</button>`,
    `<button class="btn btn--ghost" data-apply-resume-steps="${needsSubtitleRepair ? "subtitles,video" : "video"}">返回生产页</button>`,
  ].filter(Boolean).join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>成片前总检</strong>
          <span class="pill ${result.passed ? "" : "pill--warn"}">${result.passed ? "通过" : "未通过"}</span>
        </div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "内存对象")}</div>
        <div class="toolbar">
          ${topActions}
        </div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>音频</strong><span>${escapeHtml(String(metrics.audio_duration_sec ?? 0))} 秒</span></div>
        <div class="summary-card"><strong>字幕覆盖</strong><span>${escapeHtml(String(Math.round((metrics.subtitle_coverage || 0) * 100)))}%</span></div>
        <div class="summary-card"><strong>场景图</strong><span>${escapeHtml(String(metrics.scene_generated ?? 0))}/${escapeHtml(String(metrics.scene_expected ?? 0))}</span></div>
        <div class="summary-card"><strong>时轴段数</strong><span>${escapeHtml(String(metrics.timeline_scene_count ?? 0))}</span></div>
        <div class="summary-card"><strong>时轴语音</strong><span>${escapeHtml(String(metrics.timeline_body_sec ?? metrics.timeline_audio_sec ?? 0))} 秒</span></div>
        <div class="summary-card"><strong>节奏分</strong><span>${escapeHtml(String(metrics.rhythm_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>字幕同步</strong><span>${metrics.root_subtitle_exists ? "已同步" : "未同步"}</span></div>
      </div>
      ${issueCards(blockers, "阻止项")}
      ${issueCards(warnings, "提醒")}
      ${!blockers.length && !warnings.length ? `<div class="muted">没有发现成片前风险。</div>` : ""}
    </div>
  `;
}

function resumePlanHtml(plan) {
  const steps = Array.isArray(plan.recommended_steps) ? plan.recommended_steps : [];
  const reasons = Array.isArray(plan.reasons) ? plan.reasons : [];
  const stepLabels = new Map(STEP_DEFS.map((item) => [item.key, item.label]));
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>续跑建议</strong>
          <span class="pill ${plan.can_resume ? "" : "pill--warn"}">${plan.can_resume ? "可续跑" : "无需续跑"}</span>
        </div>
        <div class="muted">场景图 ${escapeHtml(String(plan.scene_generated ?? 0))}/${escapeHtml(String(plan.scene_expected ?? 0))}，封面 ${escapeHtml(String(plan.cover_generated ?? 0))}/${escapeHtml(String(plan.cover_expected ?? 0))}</div>
      </div>
      <div class="card card--inner">
        <strong>推荐勾选</strong>
        <div class="muted">${steps.length ? steps.map((step) => stepLabels.get(step) || step).join("、") : "当前不需要自动续跑。"}</div>
        ${steps.length ? `<button class="btn btn--primary" data-apply-resume-steps="${escapeHtml(steps.join(","))}">应用到生产步骤</button>` : ""}
      </div>
      ${reasons.map((item) => `<div class="muted">- ${escapeHtml(item)}</div>`).join("")}
    </div>
  `;
}

function videoSelfCheckHtml(payload) {
  const result = payload.result || {};
  const metrics = result.metrics || {};
  const issues = Array.isArray(result.issues) ? result.issues : [];
  const issueHtml = issues
    .map(
      (item) => `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(item.where || "检查项")}</strong>
            <span class="pill ${statusToneClass(item.level)}">${escapeHtml(item.level || "info")}</span>
          </div>
          <div>${escapeHtml(item.issue || "")}</div>
          ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
        </article>
      `
    )
    .join("");
  const contactSheet = result.contact_sheet_url
    ? `
      <a class="self-check-sheet" href="${API_BASE}${escapeHtml(result.contact_sheet_url)}" target="_blank" rel="noreferrer">
        <img src="${API_BASE}${escapeHtml(result.contact_sheet_url)}" alt="成片抽帧联系图" />
      </a>
    `
    : `<div class="muted">暂无抽帧图。</div>`;
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>成片自检</strong>
          <span class="pill ${Number(result.score || 0) >= 72 ? "" : "pill--warn"}">${escapeHtml(String(result.score ?? 0))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/video_self_check.json")}</div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>视频时长</strong><span>${escapeHtml(String(metrics.video_duration_sec ?? 0))} 秒</span></div>
        <div class="summary-card"><strong>音频时长</strong><span>${escapeHtml(String(metrics.audio_duration_sec ?? 0))} 秒</span></div>
        <div class="summary-card"><strong>字幕覆盖</strong><span>${escapeHtml(String(Math.round((metrics.subtitle_coverage || 0) * 100)))}%</span></div>
        <div class="summary-card"><strong>场景时轴</strong><span>${escapeHtml(String(metrics.timeline_scene_count ?? 0))}/${escapeHtml(String(metrics.scene_count ?? 0))}</span></div>
        <div class="summary-card"><strong>抽帧</strong><span>${escapeHtml(String(metrics.sampled_frame_count ?? 0))} 张</span></div>
        <div class="summary-card"><strong>黑屏段</strong><span>${escapeHtml(String(metrics.black_segment_count ?? 0))}</span></div>
      </div>
      <div class="card card--inner">
        <strong>抽帧联系图</strong>
        ${contactSheet}
      </div>
      ${issueHtml || `<div class="muted">没有发现明显黑屏、时长或字幕风险。</div>`}
      <details>
        <summary>查看完整 JSON</summary>
        <pre class="json-box">${escapeHtml(JSON.stringify(result, null, 2))}</pre>
      </details>
    </div>
  `;
}

function releaseChecklistHtml(payload) {
  const result = payload.result || {};
  const checks = Array.isArray(result.checks) ? result.checks : [];
  const checkHtml = checks
    .map(
      (item) => `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(item.label || item.key || "")}</strong>
            <span class="pill ${statusToneClass(item.status)}">${escapeHtml(item.status || "ok")}</span>
          </div>
          <div>${escapeHtml(item.detail || "")}</div>
          ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
        </article>
      `
    )
    .join("");
  const assets = result.publish_assets || {};
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>发布前检查</strong>
          <span class="pill ${result.passed ? "" : "pill--warn"}">${result.passed ? "可发布" : "需处理"}</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/release_checklist.json")}</div>
      </div>
      <div class="card card--inner">
        <strong>发布素材</strong>
        <div class="muted">标题：${escapeHtml(assets.title || "")}</div>
        <div class="muted">标签：${escapeHtml(assets.tags || "")}</div>
      </div>
      ${checkHtml || `<div class="muted">暂无检查项。</div>`}
    </div>
  `;
}

function autoVideoStatusHtml() {
  const task = state.autoVideo || {};
  if (!task.id) {
    return `<div class="muted">暂无自动挖题成片任务。</div>`;
  }
  const projectId = Number(task.project_id || task.result?.project_id || 0);
  const finalVideo = task.result?.final_video || null;
  const miningPrompt = String(task.mining_prompt || "").trim();
  const topicCandidates = Array.isArray(task.topic_candidates) ? task.topic_candidates : [];
  const queueTotal = Number(task.queue_total || task.count || 0);
  const queueIndex = Number(task.queue_index || 0);
  const queueText = queueTotal > 1 ? ` · 队列：${queueIndex || 1}/${queueTotal}` : "";
  const statusClass = task.status === "succeeded" ? "" : task.status === "failed" || task.status === "cancelled" ? "pill--warn" : "";
  const runningActions = task.running
    ? `<button class="btn btn--ghost" data-cancel-auto-video="true">取消任务</button>`
    : "";
  const projectAction = projectId
    ? `<button class="btn btn--primary" data-open-auto-video-project="${projectId}">打开项目 #${projectId}</button>`
    : "";
  const finalAction = finalVideo?.url
    ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(finalVideo))}">打开 final-video.mp4</button>`
    : "";
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>自动挖题成片</strong>
          <span class="pill ${statusClass}">${escapeHtml(task.status || "idle")}</span>
        </div>
        <div class="muted">频道：${escapeHtml(task.template_key || "-")} · 阶段：${escapeHtml(task.stage || "-")}${escapeHtml(queueText)} · 主题：${escapeHtml(task.topic || "-")}</div>
        ${miningPrompt ? `<div class="muted">本次提示词：${escapeHtml(miningPrompt)}</div>` : ""}
        ${
          topicCandidates.length
            ? `<div class="stack stack--sm">${topicCandidates
                .slice(0, 6)
                .map((item, index) => `<div class="muted">${index + 1}. ${escapeHtml(item?.title || "")}${item?.score ? ` · ${escapeHtml(String(item.score))}分` : ""}</div>`)
                .join("")}</div>`
            : ""
        }
        ${task.error ? `<div class="pill pill--warn">${escapeHtml(task.error)}</div>` : ""}
        ${finalVideo?.absolute_path ? `<div class="mono-path">${escapeHtml(finalVideo.absolute_path)}</div>` : ""}
        <div class="toolbar">
          <button class="btn btn--ghost" data-refresh-auto-video="true">刷新状态</button>
          ${projectAction}
          ${finalAction}
          ${runningActions}
        </div>
      </div>
      <pre class="json-box" style="white-space:pre-wrap;max-height:360px;overflow:auto;">${escapeHtml(task.log || "等待任务日志...")}</pre>
    </div>
  `;
}

function renderAutoVideoModal() {
  if (!state.autoVideoModalVisible) return;
  els.modalTitle.textContent = "自动挖题成片";
  els.modalBody.innerHTML = autoVideoStatusHtml();
  els.modal.classList.remove("hidden");
}

function autoVideoDraftForTemplate(key) {
  const latestPrompt = state.autoVideo?.template_key === key ? String(state.autoVideo?.mining_prompt || "") : "";
  const draft = state.autoVideoDrafts[key] || {};
  return {
    miningPrompt: draft.miningPrompt || latestPrompt,
    topicPayload: draft.topicPayload || null,
  };
}

function openAutoVideoStartModal(key) {
  if (!state.backendOnline) return window.alert("请先启动后端。");
  const template = state.templates.find((item) => item.key === key);
  if (!template) return window.alert("没有找到这个频道模板。");
  if (state.autoVideo?.running) {
    state.autoVideoModalVisible = true;
    renderAutoVideoModal();
    return window.alert("当前已有自动挖题任务正在运行，先处理这一个。");
  }
  const draft = autoVideoDraftForTemplate(key);
  showModal(
    `自动挖题成片 · ${template.key}`,
    `
      <div class="stack">
        <div class="muted">先输入这次想挖的方向、关键词、人群或禁忌。可以先挖候选并勾选，也可以直接全自动成片。</div>
        <div class="form-grid">
          <label class="form-grid__wide">
            <span>选题提示词</span>
            <textarea id="modal-auto-video-prompt" class="text-editor text-editor--short" placeholder="例：给爸妈看的反诈提醒，重点围绕免费体检骗局；温和但要有钩子。">${escapeHtml(draft.miningPrompt)}</textarea>
          </label>
          <label>
            <span>候选数量</span>
            <input id="modal-auto-video-count" type="number" min="1" max="12" value="6" />
          </label>
          <label>
            <span>联网话题</span>
            <input id="modal-auto-video-topic" value="general" />
          </label>
        </div>
        <div id="modal-auto-video-candidates" class="stack stack--sm"></div>
        <div class="toolbar">
          <button id="modal-auto-video-mine-btn" class="btn btn--ghost">先挖候选</button>
          <button id="modal-auto-video-start-selected-btn" class="btn btn--primary" disabled>用勾选候选成片</button>
          <button id="modal-auto-video-start-btn" class="btn btn--ghost">直接全自动成片</button>
          <button class="btn btn--ghost" data-close-modal="true">取消</button>
        </div>
      </div>
    `,
    (body) => {
      const promptInput = body.querySelector("#modal-auto-video-prompt");
      const countInput = body.querySelector("#modal-auto-video-count");
      const topicInput = body.querySelector("#modal-auto-video-topic");
      const candidateBox = body.querySelector("#modal-auto-video-candidates");
      const mineButton = body.querySelector("#modal-auto-video-mine-btn");
      const selectedButton = body.querySelector("#modal-auto-video-start-selected-btn");
      const startButton = body.querySelector("#modal-auto-video-start-btn");
      const renderCandidates = (payload) => {
        const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
        if (selectedButton) selectedButton.disabled = !candidates.length;
        if (!candidateBox) return;
        if (!candidates.length) {
          candidateBox.innerHTML = `<div class="muted">还没有候选。点击“先挖候选”后会显示可勾选选题。</div>`;
          return;
        }
        candidateBox.innerHTML = `
          <div class="section-head">
            <strong>候选选题</strong>
            <span class="pill">${escapeHtml(payload.provider || "auto")}</span>
          </div>
          ${candidates
            .map((item, index) => `
              <label class="card card--inner">
                <div class="section-head">
                  <span><input class="auto-topic-check" type="checkbox" data-topic-index="${index}" ${index === 0 ? "checked" : ""} /> ${escapeHtml(item.title || "")}</span>
                  <span class="pill">${escapeHtml(String(item.rank_score || item.score || "-"))}分</span>
                </div>
                ${item.brief ? `<div class="muted">${escapeHtml(item.brief)}</div>` : ""}
                ${item.why ? `<div class="muted">理由：${escapeHtml(item.why)}</div>` : ""}
                ${item.search_query ? `<div class="muted">检索词：${escapeHtml(item.search_query)}</div>` : ""}
              </label>
            `)
            .join("")}
        `;
      };
      renderCandidates(draft.topicPayload);
      mineButton?.addEventListener("click", async () => {
        const miningPrompt = promptInput?.value?.trim() || "";
        const count = Math.max(1, Math.min(Number(countInput?.value || 6), 12));
        const tavilyTopic = topicInput?.value?.trim() || "general";
        state.autoVideoDrafts[key] = { miningPrompt, topicPayload: null };
        await withBusyButton(mineButton, "正在挖候选...", async () => {
          const payload = await api(`/api/templates/${encodeURIComponent(key)}/auto-topics/mine`, {
            method: "POST",
            body: JSON.stringify({
              count,
              tavily_topic: tavilyTopic,
              mining_prompt: miningPrompt,
            }),
          });
          state.autoVideoDrafts[key] = { miningPrompt, topicPayload: payload };
          renderCandidates(payload);
        });
      });
      selectedButton?.addEventListener("click", async () => {
        const miningPrompt = promptInput?.value?.trim() || "";
        const tavilyTopic = topicInput?.value?.trim() || "general";
        const payload = state.autoVideoDrafts[key]?.topicPayload || null;
        const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
        const selectedTopics = Array.from(body.querySelectorAll(".auto-topic-check:checked"))
          .map((input) => candidates[Number(input.dataset.topicIndex)])
          .filter(Boolean);
        if (!selectedTopics.length) {
          window.alert("请先勾选至少一个候选选题。");
          return;
        }
        state.autoVideoDrafts[key] = { miningPrompt, topicPayload: payload };
        await withBusyButton(selectedButton, "正在启动队列...", async () => {
          await startAutoVideoForTemplate(key, { miningPrompt, tavilyTopic, selectedTopics });
        });
      });
      startButton?.addEventListener("click", async () => {
        const miningPrompt = promptInput?.value?.trim() || "";
        const tavilyTopic = topicInput?.value?.trim() || "general";
        state.autoVideoDrafts[key] = { miningPrompt };
        await withBusyButton(startButton, "正在启动...", async () => {
          await startAutoVideoForTemplate(key, { miningPrompt, tavilyTopic });
        });
      });
    }
  );
}

async function startAutoVideoForTemplate(key, { miningPrompt = "", tavilyTopic = "general", autoConfirmImages = true, selectedTopics = [] } = {}) {
  if (!state.backendOnline) return window.alert("请先启动后端。");
  const template = state.templates.find((item) => item.key === key);
  if (!template) return window.alert("没有找到这个频道模板。");
  const selectedQueue = Array.isArray(selectedTopics) ? selectedTopics.filter(Boolean) : [];
  state.autoVideoOpenedProjectId = null;
  state.autoVideo = await api(`/api/templates/${encodeURIComponent(key)}/auto-video`, {
    method: "POST",
    body: JSON.stringify({
      count: selectedQueue.length || 1,
      tavily_topic: tavilyTopic,
      mining_prompt: miningPrompt,
      auto_confirm_images: autoConfirmImages,
      selected_topics: selectedQueue,
    }),
  });
  state.autoVideoModalVisible = true;
  renderAutoVideoModal();
  startAutoVideoPolling();
}

async function openImageRegenerateModal(kind, target, label) {
  const project = ensureProject();
  if (!project) return;
  let promptPayload = { prompt: "" };
  try {
    promptPayload = await api(`/api/projects/${project.id}/image-prompt?kind=${encodeURIComponent(kind)}&target=${encodeURIComponent(target)}`);
  } catch (error) {
    window.alert(error.message || "读取当前提示词失败。");
    return;
  }
  const anchorOptions = Array.isArray(promptPayload.anchor_options) ? promptPayload.anchor_options : [];
  const abstractionOptions = Array.isArray(promptPayload.abstraction_options) && promptPayload.abstraction_options.length
    ? promptPayload.abstraction_options
    : [
        { value: "literal", label: "贴着口播" },
        { value: "balanced", label: "平衡" },
        { value: "conceptual", label: "更抽象" },
      ];
  const recommendedAnchorKey = promptPayload.recommended_anchor_key || "";
  const currentAnchorKey = promptPayload.anchor_key || recommendedAnchorKey || "";
  const currentAbstractionLevel = promptPayload.abstraction_level || "balanced";
  const anchorSelectOptions = [
    `<option value="">自动推荐${recommendedAnchorKey ? "（当前建议）" : ""}</option>`,
    ...anchorOptions.map((item) => {
      const key = item.key || "";
      const selected = key === currentAnchorKey ? "selected" : "";
      return `<option value="${escapeHtml(key)}" ${selected}>${escapeHtml(item.label || key)}</option>`;
    }),
  ].join("");
  const abstractionSelectOptions = abstractionOptions
    .map((item) => {
      const value = item.value || "balanced";
      const selected = value === currentAbstractionLevel ? "selected" : "";
      return `<option value="${escapeHtml(value)}" ${selected}>${escapeHtml(item.label || value)}</option>`;
    })
    .join("");
  showModal(
    `重绘图片 · ${label || target}`,
    `
      <div class="stack">
        <div class="form-grid">
          <label>
            <span>对应口播锚点</span>
            <select id="modal-image-anchor">${anchorSelectOptions}</select>
          </label>
          <label>
            <span>抽象强度</span>
            <select id="modal-image-abstraction">${abstractionSelectOptions}</select>
          </label>
          <div id="modal-image-anchor-preview" class="form-grid__wide muted"></div>
        </div>
        <div class="toolbar">
          <button id="modal-image-sync-prompt" class="btn btn--ghost">按当前控制重写提示词</button>
        </div>
        <label class="form-grid__wide">
          <span>图片提示词</span>
          <textarea id="modal-image-prompt" class="text-editor media-card__prompt">${escapeHtml(promptPayload.prompt || "")}</textarea>
        </label>
        <label class="form-grid__wide">
          <span>追加要求（可选）</span>
          <textarea id="modal-image-extra" class="text-editor text-editor--small" placeholder="例如：人物表情更强、背景更真实、不要手机弹窗、增加反差光影"></textarea>
        </label>
        <div class="muted">频道定气质，主题定方向，锚点决定这一张画哪句口播。你可以改写完整提示词，也可以只写追加要求；重绘成功后会自动把图片确认状态改为待确认。</div>
        <div class="toolbar">
          <button id="modal-image-regenerate" class="btn btn--primary">生成 / 重绘这一张</button>
          <button id="modal-chatgpt-login" class="btn btn--ghost">重新登录 ChatGPT</button>
          <button class="btn btn--ghost" data-close-modal="true">取消</button>
        </div>
        <div id="modal-image-regenerate-status" class="regen-status"></div>
      </div>
    `,
    (body) => {
      const anchorSelect = body.querySelector("#modal-image-anchor");
      const abstractionSelect = body.querySelector("#modal-image-abstraction");
      const promptInput = body.querySelector("#modal-image-prompt");
      const extraInput = body.querySelector("#modal-image-extra");
      const anchorPreview = body.querySelector("#modal-image-anchor-preview");
      const syncButton = body.querySelector("#modal-image-sync-prompt");
      const button = body.querySelector("#modal-image-regenerate");
      const reloginButton = body.querySelector("#modal-chatgpt-login");
      const status = body.querySelector("#modal-image-regenerate-status");
      const findAnchorText = (selectedKey) => {
        const effectiveKey = selectedKey || recommendedAnchorKey || "";
        const match = anchorOptions.find((item) => item.key === effectiveKey);
        return match?.text || "";
      };
      const renderAnchorPreview = () => {
        const selectedText = findAnchorText(anchorSelect.value);
        anchorPreview.textContent = selectedText
          ? `当前锚点：${selectedText}`
          : "当前会自动使用系统为这张图推荐的口播锚点。";
      };
      const refreshSuggestedPrompt = async () => {
        status.textContent = "正在按当前控制重写提示词...";
        try {
          const params = new URLSearchParams({
            kind,
            target,
          });
          if (anchorSelect.value) params.set("anchor_key", anchorSelect.value);
          if (abstractionSelect.value) params.set("abstraction_level", abstractionSelect.value);
          const nextPayload = await api(`/api/projects/${project.id}/image-prompt?${params.toString()}`);
          promptInput.value = nextPayload.prompt || "";
          status.textContent = "提示词已按当前控制更新。";
          renderAnchorPreview();
        } catch (error) {
          status.textContent = "";
          window.alert(error.message || "重写提示词失败。");
        }
      };
      renderAnchorPreview();
      anchorSelect.addEventListener("change", renderAnchorPreview);
      syncButton.addEventListener("click", refreshSuggestedPrompt);
      reloginButton?.addEventListener("click", async () => {
        await relaunchChatgptLogin(status, reloginButton);
      });
      button.addEventListener("click", async () => {
        const extra = extraInput?.value?.trim() || "";
        const prompt = [promptInput.value.trim(), extra ? `补充要求：${extra}` : ""].filter(Boolean).join("\n\n");
        if (!prompt) return window.alert("请先填写图片提示词。");
        button.disabled = true;
        syncButton.disabled = true;
        status.textContent = "正在生成，这一步可能需要几十秒到几分钟...";
        try {
          const result = await api(`/api/projects/${project.id}/images/regenerate`, {
            method: "POST",
            body: JSON.stringify({
              kind,
              target,
              prompt,
              anchor_key: anchorSelect.value,
              abstraction_level: abstractionSelect.value,
            }),
          });
          state.imageReview = result.review || state.imageReview;
          await Promise.all([refreshSceneStatus(), refreshFiles(), refreshImageReview()]);
          if (result.needs_handoff) {
            const handoff = result.handoff || {};
            status.innerHTML = `
              已创建 ChatGPT 接力任务。请在 ChatGPT 生成图片后保存到：<br>
              <span class="mono-inline">${escapeHtml(handoff.output_path || result.path || "")}</span><br>
              保存完成后点“刷新状态”或重新打开生产页查看。
            `;
            return;
          }
          status.textContent = "已重绘完成，请检查图片效果。";
          setTimeout(closeModal, 600);
        } catch (error) {
          const message = error.message || "图片重绘失败。";
          if (isChatgptLoginError(message)) {
            status.textContent = `${message} 请先点击“重新登录 ChatGPT”，登录完成后再重试这一张。`;
          } else {
            status.textContent = "";
            window.alert(message);
          }
        } finally {
          button.disabled = false;
          syncButton.disabled = false;
        }
      });
    }
  );
}

async function runReleaseAutomation(action) {
  const project = ensureProject();
  if (!project) return;
  const pathMap = {
    prepare: `/api/projects/${project.id}/release-automation/prepare`,
    login: `/api/projects/${project.id}/release-automation/login`,
    check: `/api/projects/${project.id}/release-automation/check`,
    publish: `/api/projects/${project.id}/release-automation/publish`,
    cancel: `/api/projects/${project.id}/release-automation/cancel`,
  };
  const path = pathMap[action];
  if (!path) {
    throw new Error(`Unknown release automation action: ${action}`);
  }
  if (action === "publish") {
    const title = els.releaseAutoTitle?.value?.trim() || "";
    if (!title) {
      window.alert("请先填写发布标题。");
      return;
    }
  }
  if (action === "login" && els.releaseAutoBrowserMode && els.releaseAutoBrowserMode.value !== "headed") {
    els.releaseAutoBrowserMode.value = "headed";
  }
  const options = action === "cancel"
    ? { method: "POST" }
    : action === "prepare"
      ? { method: "POST" }
      : { method: "POST", body: JSON.stringify(releaseAutomationFormPayload()) };
  markReleaseAutomationPending(action);
  await api(path, options);
  await refreshReleaseAutomation();
}

function bindEvents() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => setActiveTab(button.dataset.tab));
  });

  els.nextToProduceBtn?.addEventListener("click", () => {
    if (els.nextToProduceBtn.disabled) return;
    setActiveTab("produce");
  });

  els.nextToFilesBtn?.addEventListener("click", () => {
    if (els.nextToFilesBtn.disabled) return;
    setActiveTab("files");
  });

  els.nextToReleasesBtn?.addEventListener("click", () => {
    if (els.nextToReleasesBtn.disabled) return;
    setActiveTab("releases");
  });

  els.modal.addEventListener("click", (event) => {
    if (event.target.dataset.closeModal === "true") closeModal();
  });
  document.getElementById("modal-close-btn").addEventListener("click", closeModal);

  els.briefInput.addEventListener("input", () => {
    state.editor.projectId = state.currentProject?.id ?? null;
    state.editor.briefDirty = els.briefInput.value !== state.editor.lastBrief;
    updateWorkflowButtons();
  });

  els.contentInput.addEventListener("input", () => {
    state.editor.projectId = state.currentProject?.id ?? null;
    state.editor.contentDirty = els.contentInput.value !== state.editor.lastContent;
    updateWorkflowButtons();
  });

  document.getElementById("new-project-btn").addEventListener("click", () => {
    if (!state.backendOnline) return window.alert("请先启动后端。");
    const currentTemplateKey = selectedTemplateKey();
    const templateOptions = state.templates.map((item) => {
      const selected = item.key === currentTemplateKey ? "selected" : "";
      return `<option value="${escapeHtml(item.key)}" ${selected}>${escapeHtml(item.key)}</option>`;
    }).join("");
    showModal(
      "新建主题项目",
      `
        <label><span>主题名</span><input id="modal-project-topic" placeholder="例如：秦始皇陵为什么不敢挖" /></label>
        <label><span>频道模板</span><select id="modal-project-template">${templateOptions}</select></label>
        <div class="toolbar"><button id="modal-project-save" class="btn btn--primary">创建</button></div>
      `,
      (body) => {
        body.querySelector("#modal-project-save").addEventListener("click", async () => {
          const topic = body.querySelector("#modal-project-topic").value.trim();
          const template = body.querySelector("#modal-project-template").value;
          if (!topic) return window.alert("请先填写主题名。");
          const created = await api("/api/projects", { method: "POST", body: JSON.stringify({ topic_name: topic, template }) });
          state.selectedTemplateKey = template;
          closeModal();
          await refreshProjects();
          if (created?.id) await openProject(created.id);
        });
      }
    );
  });

  function openTemplateCreateModal() {
    if (!state.backendOnline) return window.alert("请先启动后端。");
    const baseTemplates = state.templates || [];
    const baseOptions = baseTemplates
      .map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.key)}</option>`)
      .join("");
    const fallbackPrompt = `# 新频道提示词

请把 brief 组织成一份能直接进入生产流程的 content.md。

频道人设：写清楚这个频道是谁在讲、给谁看、口吻是冷静解释、情绪共鸣、商业分析还是生活提醒。
内容结构：开头必须有钩子，中段持续推进信息差，结尾给可执行动作或互动问题。
封面规则：封面要和本期主题、频道名称、作者/个人 IP 强关联，标题短而清楚。
场景图片：必须根据本期主题和对应文案段落生成，不要套固定画风；每张图有主体、动作、情绪和字幕空间。
禁忌：不要空泛说教，不要生成长段不可读文字，不要把不同主题套成同一套画面。`;
    showModal(
      "新建频道模板",
      `
        <label><span>频道名</span><input id="modal-template-key" placeholder="例如：商道人物志" /></label>
        <label><span>基于频道</span><select id="modal-template-base">${baseOptions}</select></label>
        <label><span>模式</span><select id="modal-template-mode"><option value="video">视频</option><option value="article">图文</option></select></label>
        <label><span>发布标签</span><input id="modal-template-tags" placeholder="#知识科普 #涨知识" /></label>
        <label><span>封面风格</span><input id="modal-template-cover-style" placeholder="default / doodle / notebook / forbes" /></label>
        <label><span>目标受众</span><input id="modal-template-audience" placeholder="例如：给爸妈看的生活提醒 / 科技产品用户" /></label>
        <label><span>频道口吻</span><input id="modal-template-voice" placeholder="例如：温和提醒、犀利拆解、朋友式吐槽" /></label>
        <label class="form-grid__wide"><span>视觉策略</span><textarea id="modal-template-visual" class="text-editor text-editor--small" placeholder="这个频道的画面气质、主体、构图、色彩和个人 IP 角标规则"></textarea></label>
        <label class="form-grid__wide"><span>禁忌边界</span><textarea id="modal-template-forbidden" class="text-editor text-editor--small" placeholder="不要出现的语气、题材、画面套路、误导元素或平台风险"></textarea></label>
        <label><span>互动目标</span><input id="modal-template-interaction" placeholder="例如：引导观众讲经历 / 站队 / 补充建议" /></label>
        <label><span>挖题方向</span><input id="modal-template-mining" placeholder="例如：家庭沟通、免费套路、智能设备避坑" /></label>
        <label class="form-grid__wide"><span>prompt.md</span><textarea id="modal-template-prompt" class="text-editor text-editor--short"></textarea></label>
        <div class="toolbar"><button id="modal-template-save" class="btn btn--primary">保存</button></div>
      `,
      (body) => {
        const baseSelect = body.querySelector("#modal-template-base");
        const modeInput = body.querySelector("#modal-template-mode");
        const tagsInput = body.querySelector("#modal-template-tags");
        const styleInput = body.querySelector("#modal-template-cover-style");
        const audienceInput = body.querySelector("#modal-template-audience");
        const voiceInput = body.querySelector("#modal-template-voice");
        const visualInput = body.querySelector("#modal-template-visual");
        const forbiddenInput = body.querySelector("#modal-template-forbidden");
        const interactionInput = body.querySelector("#modal-template-interaction");
        const miningInput = body.querySelector("#modal-template-mining");
        const promptInput = body.querySelector("#modal-template-prompt");
        let promptTouched = false;

        function selectedBase() {
          return baseTemplates.find((item) => item.key === baseSelect.value) || baseTemplates[0] || null;
        }

        function applyBaseTemplate() {
          const base = selectedBase();
          modeInput.value = base?.mode || "video";
          tagsInput.value = base?.release_tags || "";
          styleInput.value = base?.cover_style || "default";
          audienceInput.value = base?.target_audience || "";
          voiceInput.value = base?.channel_voice || "";
          visualInput.value = base?.visual_strategy || "";
          forbiddenInput.value = base?.forbidden_rules || "";
          interactionInput.value = base?.interaction_goal || "";
          miningInput.value = base?.topic_mining_hint || "";
          promptInput.value = base?.prompt?.trim() || fallbackPrompt;
          promptTouched = false;
        }

        baseSelect.addEventListener("change", applyBaseTemplate);
        promptInput.addEventListener("input", () => {
          promptTouched = true;
        });
        applyBaseTemplate();

        body.querySelector("#modal-template-save").addEventListener("click", async () => {
          const key = body.querySelector("#modal-template-key").value.trim();
          if (!key) return window.alert("请先填写频道名。");
          const base = selectedBase();
          const prompt = promptTouched ? promptInput.value : adaptPromptChannelName(promptInput.value, base, key);
          const promptError = validateTemplatePromptText(prompt);
          if (promptError) return window.alert(promptError);
          await api("/api/templates", {
            method: "POST",
            body: JSON.stringify({
              key,
              name: key,
              brand_name: key,
              mode: modeInput.value,
              target_audience: audienceInput.value,
              channel_voice: voiceInput.value,
              visual_strategy: visualInput.value,
              forbidden_rules: forbiddenInput.value,
              interaction_goal: interactionInput.value,
              topic_mining_hint: miningInput.value,
              release_tags: tagsInput.value,
              cover_style: styleInput.value,
              prompt,
            }),
          });
          closeModal();
          await refreshTemplates();
        });
      }
    );
  }

  document.getElementById("new-template-btn").addEventListener("click", openTemplateCreateModal);
  document.getElementById("new-template-inline-btn")?.addEventListener("click", openTemplateCreateModal);

  document.getElementById("open-templates-btn").addEventListener("click", async () => {
    await api("/api/templates/open-root", { method: "POST" });
  });

  document.getElementById("refresh-projects-btn").addEventListener("click", refreshProjects);
  document.getElementById("save-brief-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const brief = els.briefInput.value;
    await api(`/api/projects/${project.id}/brief`, {
      method: "POST",
      body: JSON.stringify({ brief }),
    });
    state.editor.lastBrief = brief;
    state.editor.briefDirty = false;
    if (state.currentContent) {
      state.currentContent.brief = brief;
    }
    await refreshProjects();
  });

  document.getElementById("save-content-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const content = els.contentInput.value;
    await api(`/api/projects/${project.id}/content`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    state.editor.lastContent = content;
    state.editor.contentDirty = false;
    if (state.currentContent) {
      state.currentContent.content = content;
    }
    await refreshContentBundle(true);
    await refreshImageReview();
  });

  document.getElementById("generate-content-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const tavily = state.currentContent?.tavily_topic || project.tavily_topic || "general";
    const brief = els.briefInput.value;
    await api(`/api/projects/${project.id}/content/generate`, {
      method: "POST",
      body: JSON.stringify({ brief, tavily_topic: tavily }),
    });
    state.editor.lastBrief = brief;
    state.editor.briefDirty = false;
    state.editor.contentDirty = false;
    await Promise.all([refreshContentBundle(), refreshImageReview()]);
  });

  document.getElementById("cancel-generate-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    await api(`/api/projects/${project.id}/content/generate/cancel`, { method: "POST" });
    await refreshContentBundle();
  });

  document.getElementById("topic-score-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const payload = await api(`/api/projects/${project.id}/content/tools/topic-score`, {
      method: "POST",
      body: JSON.stringify({ brief: els.briefInput.value }),
    });
    showModal("选题评分", reportHtml("选题评分", payload));
  });

  document.getElementById("viral-doctor-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const payload = await api(`/api/projects/${project.id}/content/tools/viral-doctor`, {
      method: "POST",
      body: JSON.stringify({ content: els.contentInput.value }),
    });
    showModal("脚本体检", reportHtml("脚本体检", payload));
  });

  document.getElementById("viral-rewrite-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (!els.contentInput.value.trim()) return window.alert("请先生成或粘贴 content.md。");
    const button = document.getElementById("viral-rewrite-btn");
    await withBusyButton(button, "正在优化...", async () => {
      const result = await api(`/api/projects/${project.id}/content/tools/viral-rewrite`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      if (result.content) {
        els.contentInput.value = result.content;
        state.editor.lastContent = result.content;
        state.editor.contentDirty = false;
        if (state.currentContent) {
          state.currentContent.content = result.content;
          state.currentContent.summary = result.summary || state.currentContent.summary;
        }
      }
      await Promise.all([refreshContentBundle(true), refreshImageReview(), refreshFiles(), refreshProjectStatus()]);
      showModal("一键总编优化", viralRewriteHtml(result));
    });
  });

  document.getElementById("optimization-plan-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const button = document.getElementById("optimization-plan-btn");
    await withBusyButton(button, "正在规划...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/optimization-plan`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      showModal("优化路线", optimizationPlanHtml(payload));
    });
  });

  document.getElementById("channel-history-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const button = document.getElementById("channel-history-btn");
    await withBusyButton(button, "正在复盘...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/channel-history`, { method: "POST" });
      showModal("频道复盘", channelHistoryHtml(payload));
    });
  });

  document.getElementById("rhythm-check-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const button = document.getElementById("rhythm-check-btn");
    await withBusyButton(button, "正在体检...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/rhythm`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      showModal("节奏体检", rhythmReportHtml(payload));
    });
  });

  document.getElementById("rhythm-enhance-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (!window.confirm("将自动拆长句、补中段转折，并重建图片提示词。继续吗？")) return;
    const button = document.getElementById("rhythm-enhance-btn");
    await withBusyButton(button, "正在增强...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/rhythm-enhance`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      if (payload.content) {
        els.contentInput.value = payload.content;
        state.editor.lastContent = payload.content;
        state.editor.contentDirty = false;
        if (state.currentContent) {
          state.currentContent.content = payload.content;
          state.currentContent.summary = payload.summary || state.currentContent.summary;
        }
      }
      await Promise.all([refreshContentBundle(true), refreshImageReview(), refreshFiles(), refreshProjectStatus()]);
      showModal("节奏增强", rhythmEnhanceHtml(payload));
    });
  });

  document.getElementById("image-layer-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const button = document.getElementById("image-layer-btn");
    await withBusyButton(button, "正在分析...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/image-prompt-layers`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      showModal("图片提示词分层", imagePromptLayersHtml(payload));
    });
  });

  document.getElementById("video-spec-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (!els.contentInput.value.trim()) return window.alert("请先生成或粘贴 content.md。");
    const button = document.getElementById("video-spec-btn");
    await withBusyButton(button, "正在生成...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/video-spec`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      showModal("编导规格", reportHtml("video_spec.json", payload));
      await Promise.all([refreshContentBundle(), refreshFiles(), refreshProjectStatus()]);
    });
  });

  document.getElementById("title-ab-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const payload = await api(`/api/projects/${project.id}/content/tools/title-cover-ab`, {
      method: "POST",
      body: JSON.stringify({ content: els.contentInput.value, count: 6, platform: "douyin" }),
    });
    showModal("标题封面 A/B", reportHtml("标题封面 A/B", payload));
  });

  document.getElementById("quality-gate-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const payload = await api(`/api/projects/${project.id}/quality-gate`, {
      method: "POST",
      body: JSON.stringify({ brief: els.briefInput.value, content: els.contentInput.value }),
    });
    showModal("质量总检", qualityGateHtml(payload));
    await Promise.all([refreshFiles(), refreshProjectStatus()]);
  });

  document.getElementById("run-job-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const steps = stepValues();
    if (!steps.length) return window.alert("请至少勾选一个生产步骤。");
    if (!state.imageReview) await refreshImageReview();
    const reviewRequired = state.imageReview?.required !== false;
    const imageChangingSteps = ["images", "covers", "images_missing", "covers_missing"];
    if (reviewRequired && steps.includes("video")) {
      if (steps.some((step) => imageChangingSteps.includes(step))) {
        return window.alert("当前开启了图片确认关卡：请先只生成场景图/封面图，确认满意后再勾选成片合成。");
      }
      if (!state.imageReview?.confirmed) {
        return window.alert("请先确认当前场景图和封面图，再开始成片合成。");
      }
    }
    if (steps.includes("video") && !steps.some((step) => imageChangingSteps.includes(step))) {
      const preflight = await api(`/api/projects/${project.id}/video-preflight`);
      if (!preflight.result?.passed) {
        showModal("成片前总检未通过", videoPreflightHtml(preflight));
        return;
      }
      const warnings = Array.isArray(preflight.result?.warnings) ? preflight.result.warnings : [];
      if (warnings.length && !window.confirm(`成片前总检有 ${warnings.length} 个提醒，仍然继续合成吗？`)) {
        showModal("成片前总检提醒", videoPreflightHtml(preflight));
        return;
      }
    }
    await api(`/api/projects/${project.id}/jobs`, {
      method: "POST",
      body: JSON.stringify({ steps, allow_incomplete_video: false }),
    });
    await Promise.all([refreshLatestJob(), refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshProjectStatus()]);
  });

  document.getElementById("resume-plan-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const plan = await api(`/api/projects/${project.id}/resume-plan`);
    showModal("续跑建议", resumePlanHtml(plan));
  });

  els.imageProviderSaveBtn?.addEventListener("click", async () => {
    const value = els.imageProviderSelect?.value || "auto_no_apiyi";
    await withBusyButton(els.imageProviderSaveBtn, "正在切换...", async () => {
      const values = { IMAGE_PROVIDER: value };
      if (value === "auto_no_apiyi") {
        values.APIYI_IMAGE_REPLACE_ARK = "false";
      }
      await api("/api/settings/secrets", {
        method: "POST",
        body: JSON.stringify({ values }),
      });
      await refreshConfig();
    });
  });

  els.sceneCountMode?.addEventListener("change", () => {
    const fixedMode = els.sceneCountMode?.value === "fixed";
    if (els.sceneCountFixed) els.sceneCountFixed.disabled = !fixedMode;
    if (els.sceneCountCurrent) {
      els.sceneCountCurrent.textContent = fixedMode ? "待保存：固定张数" : "待保存：自动估算";
    }
  });

  els.sceneCountSaveBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const mode = els.sceneCountMode?.value === "fixed" ? "fixed" : "auto";
    const fixed = Math.max(1, Math.min(Number(els.sceneCountFixed?.value || 6), 24));
    const tavilyTopic = state.currentContent?.project_settings?.tavily_topic || state.currentContent?.tavily_topic || project.tavily_topic || "general";
    await withBusyButton(els.sceneCountSaveBtn, "正在保存...", async () => {
      await api(`/api/projects/${project.id}/project-settings`, {
        method: "POST",
        body: JSON.stringify({
          tavily_topic: tavilyTopic,
          scene_count_mode: mode,
          scene_count_fixed: fixed,
        }),
      });
      await Promise.all([refreshContentBundle(true), refreshSceneStatus(), refreshImageReview(), refreshProjectStatus()]);
    });
  });

  els.imageReviewRequired?.addEventListener("change", async () => {
    const project = ensureProject();
    if (!project) return;
    state.imageReview = await api(`/api/projects/${project.id}/image-review`, {
      method: "POST",
      body: JSON.stringify({ required: els.imageReviewRequired.checked }),
    });
    renderImageReview();
    await refreshProjectStatus();
  });

  els.confirmImagesBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    try {
      state.imageReview = await api(`/api/projects/${project.id}/image-review`, {
        method: "POST",
        body: JSON.stringify({ required: true, confirmed: true }),
      });
      document.querySelectorAll("[data-step]").forEach((checkbox) => {
        if (!(checkbox instanceof HTMLInputElement)) return;
        checkbox.checked = checkbox.dataset.step === "video";
      });
      renderImageReview();
      await refreshProjectStatus();
    } catch (error) {
      window.alert(error.message || "确认图片失败。");
    }
  });

  document.getElementById("cancel-job-btn").addEventListener("click", async () => {
    if (!state.currentJob?.id) return window.alert("当前没有可停止的任务。");
    await api(`/api/jobs/${state.currentJob.id}/cancel`, { method: "POST" });
    await refreshLatestJob();
  });

  document.getElementById("refresh-job-btn").addEventListener("click", async () => {
    await Promise.all([refreshLatestJob(), refreshSceneStatus(), refreshFiles()]);
  });

  els.chatgptReloginBtn?.addEventListener("click", async () => {
    await relaunchChatgptLogin(null, els.chatgptReloginBtn);
  });
  els.chatgptLogoutBtn?.addEventListener("click", async () => {
    await logoutChatgptLogin(els.chatgptLogoutBtn);
  });

  document.getElementById("refresh-files-btn").addEventListener("click", async () => {
    await Promise.all([refreshFiles(), refreshProjectStatus()]);
  });
  els.videoSelfCheckBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    await withBusyButton(els.videoSelfCheckBtn, "正在自检...", async () => {
      const payload = await api(`/api/projects/${project.id}/video-self-check`, { method: "POST" });
      state.videoSelfCheck = payload.result;
      showModal("成片自检", videoSelfCheckHtml(payload));
      await Promise.all([refreshFiles(), refreshProjectStatus()]);
    });
  });
  document.getElementById("refresh-releases-btn").addEventListener("click", refreshReleases);
  document.getElementById("refresh-release-automation-btn")?.addEventListener("click", async () => {
    try {
      await refreshReleaseAutomation(true);
    } catch (error) {
      window.alert(error.message || "刷新自动发布状态失败。");
    }
  });
  document.getElementById("release-checklist-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const button = document.getElementById("release-checklist-btn");
    await withBusyButton(button, "正在检查...", async () => {
      const payload = await api(`/api/projects/${project.id}/release-checklist`, { method: "POST" });
      showModal("发布前检查", releaseChecklistHtml(payload));
      await refreshFiles();
    });
  });
  bindReleaseAutomationAction("prepare-release-automation-btn", "prepare", "正在准备...", "准备自动发布环境失败。");
  bindReleaseAutomationAction("release-auto-login-btn", "login", "正在登录...", "登录账号失败。");
  bindReleaseAutomationAction("release-auto-check-btn", "check", "正在检测...", "检测账号失败。");
  bindReleaseAutomationAction("release-auto-publish-btn", "publish", "正在发布...", "发布视频失败。");
  bindReleaseAutomationAction("release-auto-cancel-btn", "cancel", "正在取消...", "取消发布任务失败。");
  [
    els.releaseAutoTitle,
    els.releaseAutoTags,
    els.releaseAutoDescription,
    els.releaseAutoSchedule,
  ].forEach((field) => {
    field?.addEventListener("input", () => scheduleReleaseAutomationDraftSave());
    field?.addEventListener("change", () => scheduleReleaseAutomationDraftSave());
  });
  [
    els.releaseAutoPlatform,
    els.releaseAutoAccount,
    els.releaseAutoBrowserMode,
  ].forEach((field) => {
    field?.addEventListener("change", () => scheduleReleaseAutomationDraftSave({ refresh: true, delay: 120 }));
  });
  document.getElementById("open-data-folder-btn").addEventListener("click", () => api("/api/settings/open-data-folder"));
  document.getElementById("open-project-folder-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    await api(`/api/projects/${project.id}/open-folder`, { method: "POST" });
  });

  document.getElementById("save-release-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const platform = els.releasePlatform.value.trim();
    const url = els.releaseUrl.value.trim();
    const note = els.releaseNote.value.trim();
    if (!platform || !url) return window.alert("请至少填写平台和链接。");
    await api(`/api/projects/${project.id}/releases`, {
      method: "POST",
      body: JSON.stringify({ platform, url, note, ...releaseMetricsPayloadFromFields() }),
    });
    els.releasePlatform.value = "";
    els.releaseUrl.value = "";
    els.releaseNote.value = "";
    clearReleaseMetricFields();
    await refreshReleases();
  });

  document.getElementById("save-config-btn").addEventListener("click", async () => {
    await api("/api/settings/secrets", {
      method: "POST",
      body: JSON.stringify({ values: collectConfigValues() }),
    });
    await refreshConfig();
    await validateConfigSections();
  });

  els.validateConfigBtn.addEventListener("click", async () => {
    await api("/api/settings/secrets", {
      method: "POST",
      body: JSON.stringify({ values: collectConfigValues() }),
    });
    await validateConfigSections();
  });

  document.getElementById("refresh-config-btn").addEventListener("click", async () => {
    await Promise.all([refreshConfig(), refreshTtsPreviews()]);
  });

  els.refreshPackagingBtn?.addEventListener("click", refreshPackaging);
  els.openPackagingOutputBtn?.addEventListener("click", () => api("/api/settings/packaging/open?target=output", { method: "POST" }));
  els.startPortableBuildBtn?.addEventListener("click", async () => {
    await api("/api/settings/packaging/build", {
      method: "POST",
      body: JSON.stringify({ include_zip: false }),
    });
    await refreshPackaging();
  });
  els.startZipBuildBtn?.addEventListener("click", async () => {
    if (!window.confirm("生成 ZIP 会比便携 EXE 更慢一些，继续吗？")) return;
    await api("/api/settings/packaging/build", {
      method: "POST",
      body: JSON.stringify({ include_zip: true }),
    });
    await refreshPackaging();
  });
  els.cancelPackagingBtn?.addEventListener("click", async () => {
    await api("/api/settings/packaging/cancel", { method: "POST" });
    await refreshPackaging();
  });

  document.getElementById("import-audio-btn").addEventListener("click", () => els.audioInput.click());
  els.audioInput.addEventListener("change", async () => {
    const project = ensureProject();
    if (!project) return;
    const file = els.audioInput.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file, file.name);
    const response = await fetch(`${API_BASE}/api/transcribe-audio`, { method: "POST", body: form });
    const data = await response.json();
    els.briefInput.value = data.text || "";
    state.editor.projectId = state.currentProject?.id ?? null;
    state.editor.briefDirty = els.briefInput.value !== state.editor.lastBrief;
    updateWorkflowButtons();
  });
  document.body.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.dataset.qualityRefresh) {
      const project = ensureProject();
      if (!project) return;
      const payload = await api(`/api/projects/${project.id}/quality-gate`, {
        method: "POST",
        body: JSON.stringify({ brief: els.briefInput.value, content: els.contentInput.value }),
      });
      showModal("质量总检", qualityGateHtml(payload));
      await Promise.all([refreshFiles(), refreshProjectStatus()]);
    }

    if (target.dataset.autoOptAction) {
      const project = ensureProject();
      if (!project) return;
      const action = target.dataset.autoOptAction;
      if (action === "viral-rewrite") {
        if (!els.contentInput.value.trim()) return window.alert("请先生成或粘贴 content.md。");
        await withBusyButton(target, "正在优化...", async () => {
          const result = await api(`/api/projects/${project.id}/content/tools/viral-rewrite`, {
            method: "POST",
            body: JSON.stringify({ content: els.contentInput.value }),
          });
          if (result.content) {
            els.contentInput.value = result.content;
            state.editor.lastContent = result.content;
            state.editor.contentDirty = false;
            if (state.currentContent) {
              state.currentContent.content = result.content;
              state.currentContent.summary = result.summary || state.currentContent.summary;
            }
          }
          await Promise.all([refreshContentBundle(true), refreshImageReview(), refreshFiles(), refreshProjectStatus()]);
          showModal("一键总编优化", viralRewriteHtml(result));
        });
      } else if (action === "release-checklist") {
        const payload = await api(`/api/projects/${project.id}/release-checklist`, { method: "POST" });
        setActiveTab("releases");
        showModal("发布前检查", releaseChecklistHtml(payload));
      } else if (action === "open-content") {
        closeModal();
        setActiveTab("content");
      } else {
        closeModal();
        setActiveTab("produce");
      }
    }

    if (target.dataset.preflightRefresh) {
      const project = ensureProject();
      if (!project) return;
      const payload = await api(`/api/projects/${project.id}/video-preflight`);
      showModal("成片前总检", videoPreflightHtml(payload));
    }

    if (target.dataset.preflightRun) {
      const project = ensureProject();
      if (!project) return;
      const steps = String(target.dataset.preflightRun || "").split(",").map((item) => item.trim()).filter(Boolean);
      if (!steps.length) return;
      if (steps.includes("video")) {
        if (!state.imageReview) await refreshImageReview();
        const reviewRequired = state.imageReview?.required !== false;
        if (reviewRequired && !state.imageReview?.confirmed) {
          return window.alert("请先确认当前场景图和封面图，再继续成片合成。");
        }
      }
      const stepLabels = new Map(STEP_DEFS.map((item) => [item.key, item.label]));
      const label = steps.map((step) => stepLabels.get(step) || step).join(" → ");
      await withBusyButton(target, "正在启动...", async () => {
        await api(`/api/projects/${project.id}/jobs`, {
          method: "POST",
          body: JSON.stringify({ steps, allow_incomplete_video: false }),
        });
        closeModal();
        setActiveTab("produce");
        await Promise.all([refreshLatestJob(), refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshProjectStatus()]);
        window.alert(`已开始：${label}`);
      });
    }

    if (target.dataset.applyResumeSteps) {
      const wanted = new Set(String(target.dataset.applyResumeSteps || "").split(",").filter(Boolean));
      document.querySelectorAll("[data-step]").forEach((checkbox) => {
        if (!(checkbox instanceof HTMLInputElement)) return;
        checkbox.checked = wanted.has(checkbox.dataset.step || "");
      });
      closeModal();
      setActiveTab("produce");
    }

    if (target.dataset.preflightRepair === "timeline") {
      const project = ensureProject();
      if (!project) return;
      await withBusyButton(target, "正在重建...", async () => {
        const result = await api(`/api/projects/${project.id}/video-preflight/repair-timeline`, { method: "POST" });
        await Promise.all([refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshContentBundle(true), refreshProjectStatus()]);
        showModal("成片前总检", videoPreflightHtml({ report_path: result.report_path, result: result.after }));
      });
    }

    if (target.dataset.qualityRepair === "image-prompts") {
      const project = ensureProject();
      if (!project) return;
      if (!window.confirm("将只重建 content.md 里的“图片提示词”区块，正文口播不会改动。继续吗？")) return;
      await withBusyButton(target, "正在重建...", async () => {
        const result = await api(`/api/projects/${project.id}/quality-gate/repair-image-prompts`, {
          method: "POST",
          body: JSON.stringify({ content: els.contentInput.value }),
        });
        if (result.content) {
          els.contentInput.value = result.content;
          state.editor.lastContent = result.content;
          state.editor.contentDirty = false;
          if (state.currentContent) {
            state.currentContent.content = result.content;
            state.currentContent.summary = result.summary || state.currentContent.summary;
          }
        }
        await Promise.all([refreshContentBundle(true), refreshImageReview(), refreshFiles(), refreshProjectStatus()]);
        showModal("质量总检", qualityGateHtml({ report_path: result.report_path, result: result.quality_gate }));
      });
    }

    if (target.dataset.openProject) {
      await openProject(Number(target.dataset.openProject));
    }

    if (target.dataset.selectTemplate) {
      await selectTemplateProjects(target.dataset.selectTemplate);
    }

    if (target.dataset.autoVideoTemplate) {
      openAutoVideoStartModal(target.dataset.autoVideoTemplate);
    }

    if (target.dataset.refreshAutoVideo) {
      await refreshAutoVideoStatus({ openCreatedProject: true });
    }

    if (target.dataset.cancelAutoVideo) {
      await api("/api/auto-video/cancel", { method: "POST" });
      await refreshAutoVideoStatus();
    }

    if (target.dataset.openAutoVideoProject) {
      await refreshProjects();
      await openProject(Number(target.dataset.openAutoVideoProject));
      closeModal();
    }

    if (target.dataset.deleteProject) {
      const projectId = Number(target.dataset.deleteProject);
      if (!window.confirm("确认删除这个主题项目吗？")) return;
      await api(`/api/projects/${projectId}`, { method: "DELETE" });
      clearCurrentWorkspace();
      await refreshProjects();
      if (!projectsForSelectedTemplate().length) {
        renderWorkspacePlaceholderForSelectedTemplate();
      }
    }

    if (target.dataset.editTemplate) {
      const key = target.dataset.editTemplate;
      const template = await api(`/api/templates/${encodeURIComponent(key)}`);
      const locked = isTemplateLocked(template);
      showModal(
        `${locked ? "查看频道" : "编辑频道"} · ${key}`,
        `
          ${locked ? `<div class="banner banner--warn">内置频道由原版模板锁定，只能查看和打开目录；要改它请复制成自建频道。</div>` : ""}
          <label><span>发布标签</span><input id="modal-edit-tags" value="${escapeHtml(template.release_tags || "")}" ${locked ? "disabled" : ""} /></label>
          <label><span>封面风格</span><input id="modal-edit-style" value="${escapeHtml(template.cover_style || "")}" ${locked ? "disabled" : ""} /></label>
          <label><span>目标受众</span><input id="modal-edit-audience" value="${escapeHtml(template.target_audience || "")}" ${locked ? "disabled" : ""} /></label>
          <label><span>频道口吻</span><input id="modal-edit-voice" value="${escapeHtml(template.channel_voice || "")}" ${locked ? "disabled" : ""} /></label>
          <label class="form-grid__wide"><span>视觉策略</span><textarea id="modal-edit-visual" class="text-editor text-editor--small" ${locked ? "readonly" : ""}>${escapeHtml(template.visual_strategy || "")}</textarea></label>
          <label class="form-grid__wide"><span>禁忌边界</span><textarea id="modal-edit-forbidden" class="text-editor text-editor--small" ${locked ? "readonly" : ""}>${escapeHtml(template.forbidden_rules || "")}</textarea></label>
          <label><span>互动目标</span><input id="modal-edit-interaction" value="${escapeHtml(template.interaction_goal || "")}" ${locked ? "disabled" : ""} /></label>
          <label><span>挖题方向</span><input id="modal-edit-mining" value="${escapeHtml(template.topic_mining_hint || "")}" ${locked ? "disabled" : ""} /></label>
          <label class="form-grid__wide"><span>prompt.md</span><textarea id="modal-edit-prompt" class="text-editor text-editor--short" ${locked ? "readonly" : ""}>${escapeHtml(template.prompt || "")}</textarea></label>
          ${locked ? "" : `<div class="toolbar"><button id="modal-edit-save" class="btn btn--primary">保存修改</button><button id="modal-template-delete" class="btn btn--danger">删除频道</button></div>`}
        `,
        (body) => {
          if (locked) return;
          body.querySelector("#modal-edit-save").addEventListener("click", async () => {
            const prompt = body.querySelector("#modal-edit-prompt").value;
            const promptError = validateTemplatePromptText(prompt);
            if (promptError) return window.alert(promptError);
            await api(`/api/templates/${encodeURIComponent(key)}`, {
              method: "PUT",
              body: JSON.stringify({
                ...template,
                key,
                target_audience: body.querySelector("#modal-edit-audience").value,
                channel_voice: body.querySelector("#modal-edit-voice").value,
                visual_strategy: body.querySelector("#modal-edit-visual").value,
                forbidden_rules: body.querySelector("#modal-edit-forbidden").value,
                interaction_goal: body.querySelector("#modal-edit-interaction").value,
                topic_mining_hint: body.querySelector("#modal-edit-mining").value,
                release_tags: body.querySelector("#modal-edit-tags").value,
                cover_style: body.querySelector("#modal-edit-style").value,
                prompt,
              }),
            });
            closeModal();
            await refreshTemplates();
          });
          body.querySelector("#modal-template-delete").addEventListener("click", async () => {
            try {
              await deleteTemplateByKey(key);
            } catch (error) {
              window.alert(error.message || "删除频道失败。");
            }
          });
        }
      );
    }

    if (target.dataset.deleteTemplate) {
      const key = target.dataset.deleteTemplate;
      try {
        await deleteTemplateByKey(key);
      } catch (error) {
        window.alert(error.message || "删除频道失败。");
      }
    }

    if (target.dataset.openTemplate) {
      await api(`/api/templates/${encodeURIComponent(target.dataset.openTemplate)}/open-folder`, { method: "POST" });
    }

    if (target.dataset.openTemplateProducts) {
      await api(`/api/templates/${encodeURIComponent(target.dataset.openTemplateProducts)}/open-products-folder`, { method: "POST" });
    }

    if (target.dataset.deleteOrphanTemplate) {
      const key = target.dataset.deleteOrphanTemplate;
      if (!window.confirm(`确认清理 orphan 模板「${key}」以及它关联的历史项目吗？`)) return;
      const result = await api(`/api/orphan-templates/${encodeURIComponent(key)}`, { method: "DELETE" });
      window.alert(`已清理 ${result.deleted || 0} 个项目。`);
      await Promise.all([refreshProjects(), refreshTemplates()]);
    }

    if (target.dataset.openProjectSubpath) {
      const project = ensureProject();
      if (!project) return;
      await api(`/api/projects/${project.id}/open-folder?subpath=${encodeURIComponent(target.dataset.openProjectSubpath)}`, {
        method: "POST",
      });
    }

    if (target.dataset.openFile) {
      window.open(`${API_BASE}${target.dataset.openFile}`, "_blank", "noopener,noreferrer");
    }

    if (target.dataset.openPackagingTarget) {
      await api(`/api/settings/packaging/open?target=${encodeURIComponent(target.dataset.openPackagingTarget)}`, {
        method: "POST",
      });
    }

    if (target.dataset.chatgptRelogin !== undefined) {
      await relaunchChatgptLogin(null, target);
    }

    if (target.dataset.regenerateImageKind) {
      await openImageRegenerateModal(
        target.dataset.regenerateImageKind,
        target.dataset.regenerateImageTarget || "",
        target.dataset.regenerateImageLabel || target.dataset.regenerateImageTarget || ""
      );
    }

    if (target.dataset.previewReference !== undefined) {
      const project = ensureProject();
      if (!project) return;
      const payload = await api(`/api/projects/${project.id}/content/references/${encodeURIComponent(target.dataset.previewReference)}`);
      const ref = payload.reference || {};
      showModal(
        ref.title || "参考资料预览",
        `
          <div class="stack">
            <div class="card card--inner">
              <div><strong>${escapeHtml(ref.title || "未命名参考")}</strong></div>
              <div class="muted">${escapeHtml(ref.source || "未知来源")}</div>
              ${payload.resolved_path ? `<div class="mono-path mono-path--sm">${escapeHtml(payload.resolved_path)}</div>` : ""}
              ${ref.url ? `<div style="margin-top:8px;"><a class="link-btn" href="${escapeHtml(ref.url)}" target="_blank" rel="noreferrer">打开来源</a></div>` : ""}
            </div>
            <pre class="json-box" style="white-space:pre-wrap;">${escapeHtml(payload.content || "")}</pre>
          </div>
        `
      );
    }

    if (target.dataset.previewVoiceKey) {
      const fieldKey = target.dataset.previewVoiceKey;
      const input = document.querySelector(`[data-config-key="${fieldKey}"]`);
      const voiceType = input?.value?.trim();
      if (!voiceType) {
        window.alert("请先选择一个音色，再试听。");
        return;
      }
      const voices = state.ttsPreviews?.voices || [];
      const entry = voices.find((item) => item.voice_type === voiceType);
      if (!entry?.audio_url) {
        window.alert(`当前音色 ${voiceType} 没有本地试听样音。`);
        return;
      }
      const audioUrl = `${API_BASE}${entry.audio_url}`;
      if (state.audioPreview && state.audioPreview.src === audioUrl && !state.audioPreview.paused) {
        state.audioPreview.pause();
        state.audioPreview.currentTime = 0;
        return;
      }
      if (state.audioPreview) {
        state.audioPreview.pause();
        state.audioPreview.currentTime = 0;
      }
      state.audioPreview = new Audio(audioUrl);
      state.audioPreview.play().catch(() => {
        window.alert("浏览器没有成功播放试听音频，请稍后重试。");
      });
    }

    if (target.dataset.toggleSecret) {
      const key = target.dataset.toggleSecret;
      state.revealedSecrets[key] = !state.revealedSecrets[key];
      renderConfig();
    }

    if (target.dataset.validateConfig) {
      await api("/api/settings/secrets", {
        method: "POST",
        body: JSON.stringify({ values: collectConfigValues() }),
      });
      await validateConfigSections([target.dataset.validateConfig]);
    }

    if (target.dataset.deleteFile) {
      const project = ensureProject();
      if (!project) return;
      if (!window.confirm(`确认删除 ${target.dataset.deleteFile} 吗？`)) return;
      await api(`/api/projects/${project.id}/files?relative_path=${encodeURIComponent(target.dataset.deleteFile)}`, { method: "DELETE" });
      await Promise.all([refreshFiles(), refreshSceneStatus(), refreshImageReview()]);
    }

    if (target.dataset.editReleaseMetrics) {
      openReleaseMetricsModal(Number(target.dataset.editReleaseMetrics));
    }

    if (target.dataset.deleteRelease) {
      const project = ensureProject();
      if (!project) return;
      await api(`/api/projects/${project.id}/releases/${target.dataset.deleteRelease}`, { method: "DELETE" });
      await refreshReleases();
    }
  });
}

bindEvents();
boot();
