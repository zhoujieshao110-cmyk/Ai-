from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = Path(os.environ.get("SHORT_VIDEO_STUDIO_APP_ROOT") or SOURCE_ROOT).resolve()
DATA_ROOT = Path(os.environ.get("SHORT_VIDEO_STUDIO_DATA_ROOT") or (APP_ROOT / "data")).resolve()
TEMPLATES_ROOT = DATA_ROOT / "templates"
PROJECTS_ROOT = DATA_ROOT / "projects"
TEMPLATE_PRODUCTS_ROOT = DATA_ROOT / "template-products"
CONFIG_ROOT = DATA_ROOT / "config"
COUNTERS_FILE = DATA_ROOT / "counters.json"
ENV_FILE = CONFIG_ROOT / ".env"
VALIDATION_FILE = CONFIG_ROOT / "validation.json"
UPDATE_MANIFEST_FILE = CONFIG_ROOT / "update_manifest.json"
VERSION_FILE = APP_ROOT.parent / "_analysis" / "awesome_app_install" / "VERSION"


DEFAULT_ENV = {
    "DEEPSEEK_API_KEY": "",
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_MODEL": "deepseek-v4-flash",
    "DEEPSEEK_THINKING_TYPE": "enabled",
    "DEEPSEEK_REASONING_EFFORT": "high",
    "TAVILY_API_KEY": "",
    "TAVILY_TOPIC": "general",
    "TAVILY_MAX_REFERENCES": "20",
    "ARK_API_KEY": "",
    "ARK_IMAGE_MODEL": "doubao-seedream-5-0-260128",
    "ARK_IMAGE_WEB_SEARCH_COVER": "false",
    "ARK_IMAGE_WEB_SEARCH_SCENE": "false",
    "IMAGE_PROVIDER": "auto",
    "APIYI_API_KEY": "",
    "APIYI_BASE_URL": "https://api.apiyi.com",
    "APIYI_IMAGE_REPLACE_ARK": "false",
    "APIYI_IMAGE_MODEL": "gpt-image-2-all",
    "THIRD_PARTY_IMAGE_API_KEY": "",
    "THIRD_PARTY_IMAGE_BASE_URL": "",
    "THIRD_PARTY_IMAGE_MODEL": "gpt-image-2-all",
    "THIRD_PARTY_IMAGE_TIMEOUT_SECONDS": "480",
    "THIRD_PARTY_IMAGE_RETRIES": "3",
    "CHATGPT_IMAGE_OPEN_TARGET": "web",
    "CHATGPT_IMAGE_WEB_URL": "https://chatgpt.com/",
    "CHATGPT_IMAGE_DESKTOP_PATH": "",
    "CHATGPT_IMAGE_AUTO_OPEN": "true",
    "CHATGPT_IMAGE_DELETE_AFTER_SAVE": "true",
    "CHATGPT_IMAGE_WAIT_SECONDS": "900",
    "CHATGPT_IMAGE_BROWSER_PATH": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "CHATGPT_IMAGE_USER_DATA_DIR": "",
    "CHATGPT_IMAGE_HEADLESS": "false",
    "IMAGEAI_PLAYGROUND_URL": "https://imageai.centos.hk/",
    "IMAGEAI_PLAYGROUND_USE_SAVED_SETTINGS": "true",
    "IMAGEAI_PLAYGROUND_DELETE_AFTER_SAVE": "true",
    "IMAGEAI_PLAYGROUND_USER_DATA_DIR": "",
    "IMAGEAI_PLAYGROUND_HEADLESS": "false",
    "IMAGEAI_PLAYGROUND_WAIT_SECONDS": "900",
    "SAU_REPO_PATH": "",
    "SAU_UV_BIN": "uv",
    "SAU_BROWSER_MODE": "headless",
    "SAU_PATCHRIGHT_DOWNLOAD_HOST": "",
    "SAU_XHS_CREATOR_BASE_URL": "https://creator.xiaohongshu.com",
    "VOLC_TTS_APP_KEY": "",
    "VOLC_TTS_ACCESS_KEY": "",
    "VOLC_TTS_RESOURCE_ID": "volc.service_type.10050",
    "VOLC_TTS_SPEAKER_1": "zh_male_dayixiansheng_v2_saturn_bigtts",
    "VOLC_TTS_SPEAKER_2": "zh_female_mizaitongxue_v2_saturn_bigtts",
    "VOLC_TTS_RANDOM_ORDER": "true",
    "VOLC_TTS_ACTION": "0",
    "VOLC_TTS_SPEECH_RATE": "1.0",
    "VOLC_ASR_APP_KEY": "",
    "VOLC_ASR_ACCESS_KEY": "",
    "VOLC_ASR_MODE": "submit",
    "VOLC_ASR_RESOURCE_ID": "volc.seedasr.auc",
    "DEFAULT_TEMPLATE": "单人讲故事",
    "BGM_VOLUME": "0.09",
}


SECRET_KEYS = {
    "DEEPSEEK_API_KEY",
    "TAVILY_API_KEY",
    "ARK_API_KEY",
    "APIYI_API_KEY",
    "THIRD_PARTY_IMAGE_API_KEY",
    "VOLC_TTS_APP_KEY",
    "VOLC_TTS_ACCESS_KEY",
    "VOLC_ASR_APP_KEY",
    "VOLC_ASR_ACCESS_KEY",
}


CONFIG_SECTIONS = [
    {
        "key": "deepseek",
        "title": "DeepSeek 文本生成",
        "description": "用于生成文案 content.md，也可作为结构化内容改写模型。",
        "validator": "deepseek",
        "fields": [
            {
                "key": "DEEPSEEK_API_KEY",
                "label": "DeepSeek API 密钥",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "把 DeepSeek 秘钥粘贴进来，留空则保持原值。",
            },
            {
                "key": "DEEPSEEK_MODEL",
                "label": "DeepSeek 模型",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "默认建议 deepseek-v4-flash，需要时也可以切到更强模型。",
                "options": [
                    {"value": "deepseek-v4-flash", "label": "deepseek-v4-flash"},
                    {"value": "deepseek-v4-pro", "label": "deepseek-v4-pro"},
                    {"value": "deepseek-chat", "label": "deepseek-chat（兼容旧名）"},
                    {"value": "deepseek-reasoner", "label": "deepseek-reasoner（兼容旧名）"},
                ],
            },
            {
                "key": "DEEPSEEK_BASE_URL",
                "label": "DeepSeek Base URL",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "官方地址一般保持 https://api.deepseek.com 即可。",
            },
            {
                "key": "DEEPSEEK_THINKING_TYPE",
                "label": "Thinking 模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "控制是否启用思考模式。",
                "options": [
                    {"value": "enabled", "label": "enabled"},
                    {"value": "disabled", "label": "disabled"},
                ],
            },
            {
                "key": "DEEPSEEK_REASONING_EFFORT",
                "label": "Reasoning 强度",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "官方常用等级为 high / max。",
                "options": [
                    {"value": "low", "label": "low"},
                    {"value": "medium", "label": "medium"},
                    {"value": "high", "label": "high"},
                    {"value": "max", "label": "max"},
                ],
            },
        ],
    },
    {
        "key": "tavily",
        "title": "Tavily 搜索增强",
        "description": "用于联网检索参考资料；不填时仍可走本地演示流程。",
        "validator": "tavily",
        "fields": [
            {
                "key": "TAVILY_API_KEY",
                "label": "Tavily API 密钥",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "联网搜索增强，可选；留空则使用无密钥模式或本地演示流程。",
            },
            {
                "key": "TAVILY_TOPIC",
                "label": "默认检索话题",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "一般用 general 就够了。",
                "options": [
                    {"value": "general", "label": "general"},
                    {"value": "news", "label": "news"},
                    {"value": "finance", "label": "finance"},
                ],
            },
            {
                "key": "TAVILY_MAX_REFERENCES",
                "label": "最大参考条数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "建议 10 到 20。",
            },
        ],
    },
    {
        "key": "ark_image",
        "title": "火山方舟 文生图",
        "description": "用于豆包 Seedream 模型生成场景图与封面图。",
        "validator": "ark_image",
        "fields": [
            {
                "key": "ARK_API_KEY",
                "label": "火山方舟 API 密钥",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "用于豆包 Seedream 文生图，必填。",
            },
            {
                "key": "ARK_IMAGE_MODEL",
                "label": "文生图模型 ID",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "优先使用新版 Seedream 5.0。",
                "options": [
                    {"value": "doubao-seedream-5-0-260128", "label": "doubao-seedream-5-0-260128（官方示例）"},
                    {"value": "doubao-seedream-5.0-lite", "label": "doubao-seedream-5.0-lite（效果好推荐）"},
                    {"value": "doubao-seedream-4.5", "label": "doubao-seedream-4.5（免费额度多）"},
                    {"value": "seedream-5.0", "label": "seedream-5.0（兼容旧写法）"},
                    {"value": "seedream-4.5", "label": "seedream-4.5（兼容旧写法）"},
                ],
            },
            {
                "key": "ARK_IMAGE_WEB_SEARCH_COVER",
                "label": "封面出图联网",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "是否允许封面生成时额外联网检索。",
                "options": [
                    {"value": "false", "label": "关闭"},
                    {"value": "true", "label": "开启"},
                ],
            },
            {
                "key": "ARK_IMAGE_WEB_SEARCH_SCENE",
                "label": "场景出图联网",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "是否允许场景图生成时额外联网检索。",
                "options": [
                    {"value": "false", "label": "关闭"},
                    {"value": "true", "label": "开启"},
                ],
            },
        ],
    },
    {
        "key": "doubao_tts",
        "title": "豆包 TTS 双人播客",
        "description": "播客双人语音合成所需的鉴权 Key 与发言人音色。",
        "validator": "volc_tts",
        "fields": [
            {
                "key": "VOLC_TTS_APP_KEY",
                "label": "豆包 TTS APP Key",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "播客双人语音合成必填。",
            },
            {
                "key": "VOLC_TTS_ACCESS_KEY",
                "label": "豆包 TTS Access Key",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "与 APP Key 配套使用，必填。",
            },
            {
                "key": "VOLC_TTS_SPEAKER_1",
                "label": "TTS 音色 1",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "建议第一个说话人选择偏男性或旁白类音色。",
                "options": [
                    {"value": "zh_male_dayixiansheng_v2_saturn_bigtts", "label": "大仪先生 v2（男声）"},
                    {"value": "zh_female_mizaitongxue_v2_saturn_bigtts", "label": "蜜仔同学 v2（女声）"},
                    {"value": "zh_female_cancan_uranus_bigtts", "label": "灿灿"},
                    {"value": "zh_male_wennuanahuaxu_moon_bigtts", "label": "温暖阿华"},
                ],
            },
            {
                "key": "VOLC_TTS_SPEAKER_2",
                "label": "TTS 音色 2",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "建议第二个说话人和音色 1 拉开差异。",
                "options": [
                    {"value": "zh_female_mizaitongxue_v2_saturn_bigtts", "label": "蜜仔同学 v2（女声）"},
                    {"value": "zh_male_dayixiansheng_v2_saturn_bigtts", "label": "大仪先生 v2（男声）"},
                    {"value": "zh_female_cancan_uranus_bigtts", "label": "灿灿"},
                    {"value": "zh_male_wennuanahuaxu_moon_bigtts", "label": "温暖阿华"},
                ],
            },
            {
                "key": "VOLC_TTS_RANDOM_ORDER",
                "label": "发言人随机起始",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "随机表示每次按音色 1 / 音色 2 轮换起始，固定表示始终从音色 1 开始。",
                "options": [
                    {"value": "true", "label": "发言人随机"},
                    {"value": "false", "label": "发言人固定（每次都按音色 1 -> 音色 2）"},
                ],
            },
            {
                "key": "VOLC_TTS_ACTION",
                "label": "生成类型",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "默认使用总结生成播客。",
                "options": [
                    {"value": "0", "label": "总结生成播客（默认）"},
                    {"value": "3", "label": "一人一句对话"},
                ],
            },
            {
                "key": "VOLC_TTS_SPEECH_RATE",
                "label": "语速",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "1.0 表示默认语速。",
            },
        ],
    },
    {
        "key": "volc_asr",
        "title": "豆包 ASR 语音识别",
        "description": "用于音频转文字与字幕时间轴；优先走火山 ASR，失败时再回退本地兜底。",
        "validator": "volc_asr",
        "fields": [
            {
                "key": "VOLC_ASR_APP_KEY",
                "label": "ASR APP Key",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "用于录音文件识别；留空时默认复用 TTS APP Key。",
            },
            {
                "key": "VOLC_ASR_ACCESS_KEY",
                "label": "ASR Access Key",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "与 ASR APP Key 配套使用；留空时默认复用 TTS Access Key。",
            },
            {
                "key": "VOLC_ASR_MODE",
                "label": "识别模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "默认 submit。",
                "options": [
                    {"value": "submit", "label": "submit"},
                    {"value": "query", "label": "query"},
                ],
            },
            {
                "key": "VOLC_ASR_RESOURCE_ID",
                "label": "资源 ID",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 volc.seedasr.auc。",
            },
        ],
    },
    {
        "key": "image_provider",
        "title": "图片生成入口",
        "description": "选择场景图和封面图使用哪个出图入口；ChatGPT 接力会使用你本机已登录的 ChatGPT 网页或桌面软件。",
        "validator": None,
        "fields": [
            {
                "key": "IMAGE_PROVIDER",
                "label": "图片生成供应商",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "手动选择某个入口时会锁定该入口，失败直接报错；自动选择才会按队列兜底。",
                "options": [
                    {"value": "auto_no_apiyi", "label": "自动选择（不使用第三方接口）"},
                    {"value": "auto", "label": "自动选择（原逻辑）"},
                    {"value": "ark", "label": "火山方舟 Seedream"},
                    {"value": "imageai_playground", "label": "GPT Image Playground 网页"},
                    {"value": "newapi", "label": "NewAPI / OpenAI Image"},
                    {"value": "third_party", "label": "第三方 OpenAI 兼容"},
                    {"value": "apiyi", "label": "API易 / OpenAI 兼容"},
                    {"value": "chatgpt_web_auto", "label": "ChatGPT 网页自动化"},
                    {"value": "chatgpt_handoff", "label": "ChatGPT 网页/桌面接力"},
                ],
            },
            {
                "key": "CHATGPT_IMAGE_BROWSER_PATH",
                "label": "Chrome 路径",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "ChatGPT 网页自动化使用的 Chrome/Edge 路径；默认使用本机 Chrome。",
            },
            {
                "key": "CHATGPT_IMAGE_USER_DATA_DIR",
                "label": "ChatGPT 自动化登录资料夹",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "留空则使用 data/config/chatgpt-browser-profile。第一次运行会打开浏览器，请登录一次 ChatGPT。",
            },
            {
                "key": "CHATGPT_IMAGE_HEADLESS",
                "label": "无头模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "建议保持关闭，便于第一次登录和处理安全验证。",
                "options": [
                    {"value": "false", "label": "关闭（推荐）"},
                    {"value": "true", "label": "开启"},
                ],
            },
            {
                "key": "CHATGPT_IMAGE_OPEN_TARGET",
                "label": "ChatGPT 打开方式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "web 打开 chatgpt.com；desktop 尝试打开本机 ChatGPT 程序；both 会同时打开网页和桌面入口。",
                "options": [
                    {"value": "web", "label": "网页"},
                    {"value": "desktop", "label": "桌面软件"},
                    {"value": "both", "label": "网页 + 桌面软件"},
                ],
            },
            {
                "key": "CHATGPT_IMAGE_WEB_URL",
                "label": "ChatGPT 网页地址",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 https://chatgpt.com/；使用你当前浏览器登录态，不在本地保存账号密码。",
            },
            {
                "key": "CHATGPT_IMAGE_DESKTOP_PATH",
                "label": "ChatGPT 桌面程序路径",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "可填 ChatGPT.exe 的完整路径；留空时仅打开网页。Windows Store 版本可能没有固定 exe 路径。",
            },
            {
                "key": "CHATGPT_IMAGE_AUTO_OPEN",
                "label": "自动打开 ChatGPT",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "开启后，每张图会自动复制提示词并打开 ChatGPT 接力页。",
                "options": [
                    {"value": "true", "label": "开启"},
                    {"value": "false", "label": "关闭，仅生成接力页"},
                ],
            },
            {
                "key": "CHATGPT_IMAGE_DELETE_AFTER_SAVE",
                "label": "生成后删除 ChatGPT 会话",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "开启后，ChatGPT 网页自动化保存图片成功后，会尝试删除本次生成图片的会话，避免左侧历史列表堆积。删除失败不影响图片保存。",
                "options": [
                    {"value": "true", "label": "开启（推荐）"},
                    {"value": "false", "label": "关闭"},
                ],
            },
            {
                "key": "CHATGPT_IMAGE_WAIT_SECONDS",
                "label": "等待保存图片秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "程序会等待目标图片文件出现；建议 600-1800 秒。",
            },
            {
                "key": "IMAGEAI_PLAYGROUND_URL",
                "label": "GPT Image Playground 地址",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 https://imageai.centos.hk/。选择 GPT Image Playground 网页入口时，程序会打开该网站、输入提示词、点击生成并抓取图片。",
            },
            {
                "key": "IMAGEAI_PLAYGROUND_USE_SAVED_SETTINGS",
                "label": "使用网站已保存配置",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "开启后只打开网站并输入提示词，沿用你在 imageai.centos.hk 手动保存的密钥和模型配置；关闭后才会从短片工坊注入第三方 Base URL/API Key。",
                "options": [
                    {"value": "true", "label": "开启（推荐）"},
                    {"value": "false", "label": "关闭，注入短片工坊配置"},
                ],
            },
            {
                "key": "IMAGEAI_PLAYGROUND_DELETE_AFTER_SAVE",
                "label": "生成后清理 Playground 历史",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "开启后，每张图保存到项目目录后会清空 imageai.centos.hk 的本地任务/图片历史，避免网站列表堆积；不会清空网站密钥配置。",
                "options": [
                    {"value": "true", "label": "开启（推荐）"},
                    {"value": "false", "label": "关闭"},
                ],
            },
            {
                "key": "IMAGEAI_PLAYGROUND_USER_DATA_DIR",
                "label": "Playground 浏览器资料夹",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "留空则使用 data/config/imageai-playground-profile。用于保存该网站本地设置，不会保存账号密码。",
            },
            {
                "key": "IMAGEAI_PLAYGROUND_HEADLESS",
                "label": "Playground 无头模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "建议保持关闭，便于观察网站是否正常出图。",
                "options": [
                    {"value": "false", "label": "关闭（推荐）"},
                    {"value": "true", "label": "开启"},
                ],
            },
            {
                "key": "IMAGEAI_PLAYGROUND_WAIT_SECONDS",
                "label": "Playground 等待秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "单张图等待时间，默认 900 秒；网站排队慢时可调到 1800。",
            },
        ],
    },
    {
        "key": "apiyi_image",
        "title": "API易 / OpenAI 兼容文生图",
        "description": "兼容保留的 API易配置，也可填写其它 OpenAI 兼容网关。",
        "validator": "apiyi_image",
        "fields": [
            {
                "key": "APIYI_API_KEY",
                "label": "API易 / 兼容 API 密钥",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "旧配置兼容项。新接入第三方服务，建议填写下面的“第三方 OpenAI 兼容文生图”。",
            },
            {
                "key": "APIYI_BASE_URL",
                "label": "API易 / 兼容 Base URL",
                "required": True,
                "secret": False,
                "kind": "text",
                "help": "API易官方可直接填 https://api.apiyi.com；也支持填 /v1 或完整图片端点，程序会自动归一化。",
            },
            {
                "key": "APIYI_IMAGE_MODEL",
                "label": "图片模型 ID",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "按 API易官方文档，默认使用 gpt-image-2-all。",
            },
            {
                "key": "APIYI_IMAGE_REPLACE_ARK",
                "label": "优先使用 API易出图",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "开启后，场景图和封面图会优先走这里的兼容接口。",
                "options": [
                    {"value": "false", "label": "关闭"},
                    {"value": "true", "label": "开启"},
                ],
            },
        ],
    },
    {
        "key": "third_party_image",
        "title": "第三方 OpenAI 兼容文生图",
        "description": "参考 CookSleep/gpt_image_playground 的 OpenAI 兼容接入方式，支持 NewAPI / One API / 各类中转站图片 API。",
        "validator": "third_party_image",
        "fields": [
            {
                "key": "THIRD_PARTY_IMAGE_API_KEY",
                "label": "第三方 API 密钥",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "填写第三方中转站的 API Key。",
            },
            {
                "key": "THIRD_PARTY_IMAGE_BASE_URL",
                "label": "第三方 Base URL",
                "required": True,
                "secret": False,
                "kind": "text",
                "help": "NewAPI 填你的服务器地址即可，例如 https://你的newapi服务器地址；也可填 /v1 或完整 /v1/images/generations，程序会自动归一化。",
            },
            {
                "key": "THIRD_PARTY_IMAGE_MODEL",
                "label": "图片模型 ID",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "按 NewAPI 渠道支持填写，例如 gpt-image-1、dall-e-3、gpt-image-2-all 或其它中转站图片模型名；不要填 newapi_channel_conn 这类渠道连通性测试名。",
            },
            {
                "key": "THIRD_PARTY_IMAGE_TIMEOUT_SECONDS",
                "label": "单张超时秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 480 秒，慢速中转站可调到 900-1800。",
            },
            {
                "key": "THIRD_PARTY_IMAGE_RETRIES",
                "label": "失败重试次数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 3 次。手动选择第三方入口时只重试该入口，不会切换到 ChatGPT。",
            },
        ],
    },
    {
        "key": "local",
        "title": "本地默认值",
        "description": "不涉及联网鉴权的常用默认值。",
        "validator": None,
        "fields": [
            {
                "key": "DEFAULT_TEMPLATE",
                "label": "默认模板",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "默认创建项目时使用的模板。",
                "options": [
                    {"value": "单人讲故事", "label": "单人讲故事"},
                    {"value": "双人讲故事", "label": "双人讲故事"},
                    {"value": "单人图文", "label": "单人图文"},
                ],
            },
            {
                "key": "BGM_VOLUME",
                "label": "BGM 音量",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 0.09。",
            },
        ],
    },
    {
        "key": "social_auto_upload",
        "title": "自动发布与浏览器配置",
        "description": "对接 dreammis/social-auto-upload，在投放页调用抖音、快手、小红书自动发布。",
        "validator": "social_auto_upload",
        "fields": [
            {
                "key": "SAU_REPO_PATH",
                "label": "social-auto-upload 仓库目录",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "选填。填写 dreammis/social-auto-upload 的本地仓库目录后，投放页会直接调用这套自动发布能力。",
            },
            {
                "key": "SAU_UV_BIN",
                "label": "uv 命令",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "填写 uv 可执行命令或完整路径。默认是 uv；如果系统 PATH 里找不到 uv，就在这里填实际安装位置。",
            },
            {
                "key": "SAU_BROWSER_MODE",
                "label": "浏览器模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "扫码登录、手动确认页面或排查问题时使用 headed；稳定运行时可用 headless。",
                "options": [
                    {"value": "headless", "label": "headless"},
                    {"value": "headed", "label": "headed"},
                ],
            },
            {
                "key": "SAU_PATCHRIGHT_DOWNLOAD_HOST",
                "label": "Patchright 下载镜像",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "可选。如果安装浏览器依赖要走国内镜像，可以填写 npmmirror 等下载源；留空使用默认地址。",
            },
            {
                "key": "SAU_XHS_CREATOR_BASE_URL",
                "label": "小红书创作者后台地址",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认使用 https://creator.xiaohongshu.com。只有在你的环境需要自定义域名或代理地址时才修改。",
            },
        ],
    },
]


def _repair_social_auto_upload_section_text() -> None:
    field_overrides = {
        "SAU_REPO_PATH": {
            "label": "social-auto-upload 仓库目录",
            "help": "选填。填写 dreammis/social-auto-upload 的本地仓库目录后，投放页会直接调用这套自动发布能力。",
        },
        "SAU_UV_BIN": {
            "label": "uv 命令",
            "help": "填写 uv 可执行命令或完整路径。默认是 uv；如果系统 PATH 里找不到 uv，就在这里填实际安装位置。",
        },
        "SAU_BROWSER_MODE": {
            "label": "浏览器模式",
            "help": "默认用 headless。需要扫码登录、手动确认页面或排查问题时，切到 headed 会直接弹出可见浏览器；平时稳定运行可继续用 headless。",
        },
        "SAU_PATCHRIGHT_DOWNLOAD_HOST": {
            "label": "Patchright 下载镜像",
            "help": "可选。如果你希望安装浏览器依赖时走国内镜像，可以填写 npmmirror 等下载源；留空就使用默认地址。",
        },
        "SAU_XHS_CREATOR_BASE_URL": {
            "label": "小红书创作者后台地址",
            "help": "默认使用 https://creator.xiaohongshu.com。只有在你的环境需要自定义域名或代理地址时才修改。",
        },
    }
    for section in CONFIG_SECTIONS:
        if section.get("key") != "social_auto_upload":
            continue
        section["title"] = "自动发布与浏览器配置"
        section["description"] = "如果你要在投放页里直接登录、检测账号并自动发布到抖音或小红书，这里填写 dreammis/social-auto-upload 相关路径与运行参数。"
        for field in section.get("fields", []):
            override = field_overrides.get(str(field.get("key") or ""))
            if override:
                field.update(override)
        break


_repair_social_auto_upload_section_text()


BUILTIN_TEMPLATES = [
    {
        "key": "单人讲故事",
        "manifest": {
            "name": "单人讲故事",
            "brand_name": "单人讲故事",
            "mode": "video",
            "default_disclaimer": "内容基于公开资料整理，仅作知识科普，不构成医疗、投资或法律建议；本视频由 AI 辅助生成。",
            "release_tags": "#知识科普 #冷知识 #涨知识",
            "cover_footnote_line_1": "内容基于公开资料整理",
            "cover_footnote_line_2": "仅作知识科普",
            "cover_style": "doodle",
            "voice_mode": "single",
            "tts_speaker_1": "zh_female_cancan_uranus_bigtts",
            "tts_action": 3,
            "builtin_locked": True,
            "version": "2026.6.17.117",
        },
        "prompt": """# 单人讲故事

你要把输入的 brief 整理成一个适合 3-8 分钟横屏短视频的完整 `content.md`。

要求：
- 用一个会讲故事的朋友口吻，写成单人独白
- 先抛反常识钩子，再讲清起因、转折、结果
- 最后落到现实意义
- 产出时同时给出标题、封面副标题、推荐发布标题、场景清单
- 内容务必适合拆成 6-10 张场景图
""",
    },
    {
        "key": "双人讲故事",
        "manifest": {
            "name": "双人讲故事",
            "brand_name": "双人讲故事",
            "mode": "video",
            "default_disclaimer": "内容基于公开资料整理，仅作知识科普，不构成医疗、投资或法律建议；本视频由 AI 辅助生成。",
            "release_tags": "#知识科普 #双人播客 #故事感",
            "cover_footnote_line_1": "内容基于公开资料整理",
            "cover_footnote_line_2": "仅作知识科普",
            "cover_style": "notebook",
            "voice_mode": "dual",
            "tts_speaker_1": "zh_male_dayixiansheng_v2_saturn_bigtts",
            "tts_speaker_2": "zh_female_mizaitongxue_v2_saturn_bigtts",
            "tts_random_order": True,
            "tts_action": 0,
            "builtin_locked": True,
            "version": "2026.6.17.117",
        },
        "prompt": """# 双人讲故事

把 brief 改写成双人播客式脚本，要求一问一答推进，信息密度高，但不能像主持人口播稿。

要求：
- 两位角色轮流发言
- 开头 15 秒抛出最抓人的问题
- 过程中不断追问和拆解
- 结尾要回扣开头并给出现实用途
- 同时给出标题、封面副标题、推荐发布标题、场景清单
""",
    },
    {
        "key": "单人图文",
        "manifest": {
            "name": "单人图文",
            "brand_name": "单人图文",
            "mode": "article",
            "default_disclaimer": "",
            "release_tags": "图文",
            "cover_style": "forbes",
            "cover_footnote_line_1": "",
            "cover_footnote_line_2": "",
            "builtin_locked": True,
            "version": "2026.6.17.117",
        },
        "prompt": """# 单人图文

把 brief 改写成适合图文平台发布的长图文内容。

要求：
- 保留强钩子标题
- 用 6-9 页卡片式结构讲清楚
- 每页都给出一句适合出图的核心文案
- 最终输出 `content.md` 和图文卡片清单
""",
    },
]


def now_ts() -> float:
    return time.time()


def now_ms() -> int:
    return int(time.time() * 1000)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    _assert_valid_project_write_target(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return default


def write_text(path: Path, content: str) -> None:
    _assert_valid_project_write_target(path)
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    return cleaned[:80] or "未命名"


def is_builtin_template_key(key: str) -> bool:
    builtins = {safe_name(str(item.get("key", ""))) for item in BUILTIN_TEMPLATES}
    return safe_name(key) in builtins


def current_version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8", errors="ignore").strip() or "0.0.0"
    return "0.0.0"


def project_dir(project_id: int) -> Path:
    return PROJECTS_ROOT / str(project_id)


def project_file(project_id: int, relative: str) -> Path:
    return project_dir(project_id) / relative


def _project_root_from_path(path: Path) -> Path | None:
    try:
        absolute_path = path.resolve()
        projects_root = PROJECTS_ROOT.resolve()
        relative = absolute_path.relative_to(projects_root)
    except Exception:
        return None
    if not relative.parts:
        return None
    project_name = relative.parts[0]
    if not project_name.isdigit():
        return None
    return projects_root / project_name


def _assert_valid_project_write_target(path: Path) -> None:
    project_root = _project_root_from_path(path)
    if project_root is None:
        return
    if path.name == "project.json":
        return
    if (project_root / "project.json").exists():
        return
    raise FileNotFoundError(f"project {project_root.name} not found")


def _extract_topic_from_markdown(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip()
        for marker in ("主题：", "主题:", "标题：", "标题:"):
            if marker in line:
                _, _, tail = line.partition(marker)
                candidate = tail.strip()
                if candidate:
                    return candidate
        return line[:120]
    return ""


def _extract_topic_from_scene_timeline(path: Path) -> str:
    payload = read_json(path / "audio/scene_timeline.json", {})
    scenes = payload.get("scenes") if isinstance(payload, dict) else None
    if not isinstance(scenes, list):
        return ""
    for item in scenes:
        if not isinstance(item, dict):
            continue
        for field in ("prompt", "text"):
            value = str(item.get(field) or "").strip()
            if not value:
                continue
            for pattern in (r"[「“\"]([^」”\"\n]{4,80})[」”\"]", r"[《](.{4,80})[》]"):
                match = re.search(pattern, value)
                if match:
                    candidate = match.group(1).strip("：:,.，。 ")
                    if candidate:
                        return candidate
            return value.splitlines()[0].strip()[:120]
    return ""


def _infer_template_key_from_text(text: str) -> str:
    content = str(text or "")
    if not content:
        return ""
    for template in list_templates():
        for candidate in (template.get("key"), template.get("name"), template.get("brand_name")):
            label = str(candidate or "").strip()
            if label and label in content:
                return str(template.get("key") or label)
    return ""


def _fallback_template_key() -> str:
    configured = str(parse_env().get("DEFAULT_TEMPLATE") or "").strip()
    if configured and (TEMPLATES_ROOT / configured).exists():
        return configured
    for template in list_templates():
        if str(template.get("mode") or "video") == "video":
            return str(template.get("key") or "")
    templates = list_templates()
    return str(templates[0].get("key") or "") if templates else ""


def _project_dir_timestamps(path: Path) -> tuple[float, float]:
    created = path.stat().st_ctime
    updated = path.stat().st_mtime
    for child in path.rglob("*"):
        try:
            stat = child.stat()
        except OSError:
            continue
        created = min(created, stat.st_ctime)
        updated = max(updated, stat.st_mtime)
    return created, updated


def _repair_orphan_project_meta(path: Path) -> dict[str, Any] | None:
    if not path.is_dir() or (path / "project.json").exists():
        return None
    if not path.name.isdigit():
        return None

    content_text = read_text(path / "content.md")
    brief_text = read_text(path / "brief.md")
    topic_name = (
        _extract_topic_from_markdown(content_text)
        or _extract_topic_from_markdown(brief_text)
        or _extract_topic_from_scene_timeline(path)
    )
    template_key = _infer_template_key_from_text(content_text) or _infer_template_key_from_text(brief_text)
    if not template_key:
        timeline_text = json.dumps(read_json(path / "audio/scene_timeline.json", {}), ensure_ascii=False)
        template_key = _infer_template_key_from_text(timeline_text) or _fallback_template_key()
    if not topic_name or not template_key:
        return None

    template = get_template(template_key)
    created_at, updated_at = _project_dir_timestamps(path)
    content_state = read_json(path / "content_generate.json", {})
    project_settings = read_json(path / "project_settings.json", {"tavily_topic": "general"})
    meta = {
        "id": int(path.name),
        "topic_name": topic_name,
        "template": template_key,
        "template_mode": template.get("mode", "video"),
        "created_at": created_at,
        "updated_at": updated_at,
        "last_job_status": content_state.get("status") or "idle",
        "content_generating": bool(content_state.get("status") == "running"),
        "tavily_topic": project_settings.get("tavily_topic", "general"),
    }
    write_json(path / "project.json", meta)
    return meta


def _should_delete_orphan_project_dir(path: Path) -> bool:
    if not path.is_dir() or (path / "project.json").exists():
        return False
    meaningful_names = {
        "brief.md",
        "content.md",
        "summary.json",
        "references.json",
        "project_settings.json",
        "release_links.json",
        "auto_topic.json",
        "auto_video.json",
    }
    for child in path.rglob("*"):
        if child.is_dir():
            continue
        if child.name in meaningful_names and read_text(child).strip():
            return False
        if child.suffix.lower() in {".md", ".json"} and child.name not in {"content_generate.json", "image_prompt_controls.json"}:
            if read_text(child).strip():
                return False
    return True


def _cleanup_orphan_project_dir(path: Path) -> None:
    if _should_delete_orphan_project_dir(path):
        shutil.rmtree(path, ignore_errors=True)


def bootstrap() -> None:
    ensure_dir(DATA_ROOT)
    ensure_dir(TEMPLATES_ROOT)
    ensure_dir(PROJECTS_ROOT)
    ensure_dir(TEMPLATE_PRODUCTS_ROOT)
    ensure_dir(CONFIG_ROOT)

    if not COUNTERS_FILE.exists():
        write_json(COUNTERS_FILE, {"project_id": 0, "release_id": 0})

    if not ENV_FILE.exists():
        lines = [f"{key}={value}" for key, value in DEFAULT_ENV.items()]
        write_text(ENV_FILE, "\n".join(lines) + "\n")

    if not VALIDATION_FILE.exists():
        write_json(VALIDATION_FILE, {"sections": {}})

    if not UPDATE_MANIFEST_FILE.exists():
        write_json(
            UPDATE_MANIFEST_FILE,
            {
                "version": current_version(),
                "title": "当前已是本地最新版本",
                "highlights": [
                    "更新信息现在改为读取本地 update_manifest.json。",
                    "把更高版本号和下载地址写进去后，前端会真实提示更新。",
                ],
                "download_url": "",
                "recommend": "optional",
            },
        )

    for item in BUILTIN_TEMPLATES:
        template_root = TEMPLATES_ROOT / item["key"]
        ensure_dir(template_root)
        manifest_path = template_root / "manifest.json"
        prompt_path = template_root / "prompt.md"
        if not manifest_path.exists():
            write_json(manifest_path, item["manifest"])
        else:
            manifest = read_json(manifest_path, {})
            if not manifest.get("builtin_locked"):
                manifest["builtin_locked"] = True
                write_json(manifest_path, manifest)
        if not prompt_path.exists():
            write_text(prompt_path, item["prompt"].strip() + "\n")


def next_counter(name: str) -> int:
    payload = read_json(COUNTERS_FILE, {"project_id": 0, "release_id": 0})
    payload[name] = int(payload.get(name, 0)) + 1
    write_json(COUNTERS_FILE, payload)
    return payload[name]


def list_templates() -> list[dict[str, Any]]:
    def sort_key(path: Path) -> tuple[int, float, str]:
        manifest = read_json(path / "manifest.json", {})
        builtin = 1 if manifest.get("builtin_locked") or is_builtin_template_key(path.name) else 0
        try:
            created_at = path.stat().st_ctime
        except OSError:
            created_at = 0.0
        return (builtin, -created_at, path.name)

    templates: list[dict[str, Any]] = []
    for path in sorted(TEMPLATES_ROOT.iterdir(), key=sort_key):
        if not path.is_dir():
            continue
        templates.append(get_template(path.name))
    return templates


def get_template(key: str) -> dict[str, Any]:
    root = TEMPLATES_ROOT / key
    manifest = read_json(root / "manifest.json", {})
    prompt = read_text(root / "prompt.md")
    return {
        "key": key,
        "name": manifest.get("name", key),
        "brand_name": manifest.get("brand_name", key),
        "mode": manifest.get("mode", "video"),
        "target_audience": manifest.get("target_audience", ""),
        "channel_voice": manifest.get("channel_voice", ""),
        "visual_strategy": manifest.get("visual_strategy", ""),
        "forbidden_rules": manifest.get("forbidden_rules", ""),
        "interaction_goal": manifest.get("interaction_goal", ""),
        "topic_mining_hint": manifest.get("topic_mining_hint", ""),
        "default_disclaimer": manifest.get("default_disclaimer", ""),
        "release_tags": manifest.get("release_tags", ""),
        "cover_footnote_line_1": manifest.get("cover_footnote_line_1", ""),
        "cover_footnote_line_2": manifest.get("cover_footnote_line_2", ""),
        "cover_style": manifest.get("cover_style", "default"),
        "voice_mode": manifest.get("voice_mode", ""),
        "tts_speaker_1": manifest.get("tts_speaker_1", ""),
        "tts_speaker_2": manifest.get("tts_speaker_2", ""),
        "tts_random_order": manifest.get("tts_random_order", ""),
        "tts_action": manifest.get("tts_action", ""),
        "tts_speech_rate": manifest.get("tts_speech_rate", 1.0),
        "builtin_locked": bool(manifest.get("builtin_locked", False) or is_builtin_template_key(key)),
        "generate_cover_landscape": manifest.get("generate_cover_landscape", True),
        "generate_cover_portrait": manifest.get("generate_cover_portrait", True),
        "version": manifest.get("version", ""),
        "prompt": prompt,
    }


def validate_template_prompt(prompt: str) -> str:
    cleaned = str(prompt or "").strip()
    compact = re.sub(r"\s+", "", cleaned)
    if len(compact) < 120:
        raise ValueError("频道 prompt.md 太短。请至少写清楚频道人设、内容结构、画面风格和禁忌，避免生成退回通用模板。")
    required_hints = ("人设", "口吻", "结构", "封面", "场景", "图片", "禁忌", "互动")
    if sum(1 for hint in required_hints if hint in cleaned) < 2:
        raise ValueError("频道 prompt.md 缺少频道规则。建议写明人设/口吻、脚本结构、封面与场景图风格、禁忌和互动方式。")
    return cleaned


def save_template(key: str, payload: dict[str, Any]) -> dict[str, Any]:
    safe_key = safe_name(key)
    existing_manifest = read_json(TEMPLATES_ROOT / safe_key / "manifest.json", {})
    if existing_manifest.get("builtin_locked") or is_builtin_template_key(safe_key):
        raise PermissionError("内置频道模板不能通过工作台编辑。")

    prompt = validate_template_prompt(str(payload.get("prompt", "")))
    root = ensure_dir(TEMPLATES_ROOT / safe_key)
    manifest = {
        "name": payload.get("name", safe_key),
        "brand_name": payload.get("brand_name", safe_key),
        "mode": payload.get("mode", "video"),
        "target_audience": payload.get("target_audience", ""),
        "channel_voice": payload.get("channel_voice", ""),
        "visual_strategy": payload.get("visual_strategy", ""),
        "forbidden_rules": payload.get("forbidden_rules", ""),
        "interaction_goal": payload.get("interaction_goal", ""),
        "topic_mining_hint": payload.get("topic_mining_hint", ""),
        "default_disclaimer": payload.get("default_disclaimer", ""),
        "release_tags": payload.get("release_tags", ""),
        "cover_footnote_line_1": payload.get("cover_footnote_line_1", ""),
        "cover_footnote_line_2": payload.get("cover_footnote_line_2", ""),
        "cover_style": payload.get("cover_style", "default"),
        "voice_mode": payload.get("voice_mode", ""),
        "tts_speaker_1": payload.get("tts_speaker_1", ""),
        "tts_speaker_2": payload.get("tts_speaker_2", ""),
        "tts_random_order": payload.get("tts_random_order", ""),
        "tts_action": payload.get("tts_action", ""),
        "tts_speech_rate": payload.get("tts_speech_rate", 1.0),
        "generate_cover_landscape": payload.get("generate_cover_landscape", True),
        "generate_cover_portrait": payload.get("generate_cover_portrait", True),
        "builtin_locked": False,
        "version": payload.get("version", ""),
    }
    write_json(root / "manifest.json", manifest)
    write_text(root / "prompt.md", prompt + "\n")
    return get_template(safe_key)


def delete_template(template_key: str, delete_projects: bool = False) -> dict[str, Any]:
    safe_key = safe_name(template_key)
    template_root = TEMPLATES_ROOT / safe_key
    if not template_root.exists():
        raise FileNotFoundError(f"频道模板「{template_key}」不存在。")

    manifest = read_json(template_root / "manifest.json", {})
    if manifest.get("builtin_locked") or is_builtin_template_key(safe_key):
        raise PermissionError("内置频道模板不能通过工作台删除。")

    linked_projects = projects_for_template(safe_key)
    if linked_projects and not delete_projects:
        raise ValueError(f"频道模板「{safe_key}」还有 {len(linked_projects)} 个主题项目。")

    deleted_ids: list[int] = []
    if delete_projects:
        for meta in linked_projects:
            project_id = int(meta["id"])
            delete_project(project_id)
            deleted_ids.append(project_id)

    shutil.rmtree(template_root, ignore_errors=True)
    shutil.rmtree(template_products_dir(safe_key), ignore_errors=True)
    return {
        "ok": True,
        "template": safe_key,
        "deleted_projects": len(deleted_ids),
        "project_ids": deleted_ids,
    }


def list_projects() -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    for path in PROJECTS_ROOT.iterdir():
        if not path.is_dir():
            continue
        meta_path = path / "project.json"
        if not meta_path.exists():
            repaired = _repair_orphan_project_meta(path)
            if repaired:
                projects.append(repaired)
            else:
                _cleanup_orphan_project_dir(path)
            continue
        meta = read_json(meta_path, {})
        if isinstance(meta, dict) and meta.get("id"):
            projects.append(meta)
    projects.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
    return projects


def get_project(project_id: int) -> dict[str, Any]:
    meta = read_json(project_file(project_id, "project.json"), {})
    if not meta:
        repaired = _repair_orphan_project_meta(project_dir(project_id))
        if repaired:
            return repaired
    if not meta:
        raise FileNotFoundError(f"project {project_id} not found")
    return meta


def write_project_meta(project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    payload["updated_at"] = now_ts()
    write_json(project_file(project_id, "project.json"), payload)
    return payload


def create_project(topic_name: str, template_key: str) -> dict[str, Any]:
    project_id = next_counter("project_id")
    template = get_template(template_key)
    meta = {
        "id": project_id,
        "topic_name": topic_name.strip(),
        "template": template_key,
        "template_mode": template.get("mode", "video"),
        "created_at": now_ts(),
        "updated_at": now_ts(),
        "last_job_status": "idle",
        "content_generating": False,
        "tavily_topic": "general",
    }
    root = ensure_dir(project_dir(project_id))
    ensure_dir(root / "reports")
    ensure_dir(root / "jobs")
    ensure_dir(root / "audio")
    ensure_dir(root / "scenes")
    ensure_dir(root / "covers")
    ensure_dir(root / "article")
    ensure_dir(root / "releases")
    ensure_dir(root / "uploads")
    write_project_meta(project_id, meta)
    write_text(root / "brief.md", "")
    write_text(root / "content.md", "")
    write_json(root / "references.json", [])
    write_json(root / "summary.json", {})
    write_json(root / "project_settings.json", dict(DEFAULT_PROJECT_SETTINGS))
    write_json(root / "release_links.json", [])
    return meta


def delete_project(project_id: int) -> None:
    shutil.rmtree(project_dir(project_id), ignore_errors=True)


def projects_for_template(template_key: str) -> list[dict[str, Any]]:
    return [meta for meta in list_projects() if meta.get("template") == template_key]


def template_products_dir(template_key: str) -> Path:
    return TEMPLATE_PRODUCTS_ROOT / safe_name(template_key)


def build_template_products_dir(template_key: str) -> Path:
    root = ensure_dir(template_products_dir(template_key))
    for path in root.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)

    projects = projects_for_template(template_key)
    lines = [f"模板：{template_key}", f"项目数量：{len(projects)}", ""]
    for meta in projects:
        project_root = project_dir(meta["id"])
        releases_root = project_root / "releases"
        target = releases_root if releases_root.exists() else project_root
        base_name = f"{meta['id']:04d}-{safe_name(meta['topic_name'])}"
        launcher = root / f"{base_name}.cmd"
        write_text(
            launcher,
            "@echo off\n"
            f'start "" "{target}"\n',
        )
        lines.extend(
            [
                f"[{meta['id']}] {meta['topic_name']}",
                f"项目目录: {project_root}",
                f"成片目录: {releases_root}",
                f"快捷打开: {launcher.name}",
                "",
            ]
        )

    write_text(root / "README.txt", "\n".join(lines).rstrip() + "\n")
    return root


def delete_orphan_template(template_key: str) -> dict[str, Any]:
    template_root = TEMPLATES_ROOT / template_key
    if template_root.exists():
        raise ValueError(f"模板「{template_key}」仍然存在，不能按 orphan 清理。")

    deleted_ids: list[int] = []
    for meta in projects_for_template(template_key):
        delete_project(meta["id"])
        deleted_ids.append(meta["id"])

    shutil.rmtree(template_products_dir(template_key), ignore_errors=True)
    return {"ok": True, "deleted": len(deleted_ids), "project_ids": deleted_ids}


def get_brief(project_id: int) -> str:
    return read_text(project_file(project_id, "brief.md"))


def save_brief(project_id: int, brief: str) -> None:
    write_text(project_file(project_id, "brief.md"), brief)
    meta = get_project(project_id)
    meta["updated_at"] = now_ts()
    write_project_meta(project_id, meta)


def get_content(project_id: int) -> str:
    return read_text(project_file(project_id, "content.md"))


def save_content(project_id: int, content: str) -> None:
    write_text(project_file(project_id, "content.md"), content)
    meta = get_project(project_id)
    meta["updated_at"] = now_ts()
    write_project_meta(project_id, meta)


def get_summary(project_id: int) -> dict[str, Any]:
    summary = read_json(project_file(project_id, "summary.json"), {})
    if not isinstance(summary, dict):
        summary = {}
    timeline_path = project_file(project_id, "audio/scene_timeline.json")
    content_path = project_file(project_id, "content.md")
    timeline_fresh = timeline_path.exists() and (
        not content_path.exists() or timeline_path.stat().st_mtime >= content_path.stat().st_mtime
    )
    if timeline_fresh:
        timeline = read_json(timeline_path, {})
        scenes = timeline.get("scenes") if isinstance(timeline, dict) else None
        if isinstance(scenes, list) and scenes:
            summary["scene_count"] = len(scenes)
            summary["scene_count_aligned"] = len(scenes)
    return summary


def save_summary(project_id: int, summary: dict[str, Any]) -> None:
    write_json(project_file(project_id, "summary.json"), summary)


def get_references(project_id: int) -> list[dict[str, Any]]:
    return read_json(project_file(project_id, "references.json"), [])


def save_references(project_id: int, references: list[dict[str, Any]]) -> None:
    write_json(project_file(project_id, "references.json"), references)


DEFAULT_PROJECT_SETTINGS = {
    "tavily_topic": "general",
    "scene_count_mode": "auto",
    "scene_count_fixed": 6,
}


def normalize_project_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(DEFAULT_PROJECT_SETTINGS)
    if isinstance(settings, dict):
        normalized.update(settings)
    mode = str(normalized.get("scene_count_mode") or "auto").strip().lower()
    if mode not in {"auto", "fixed"}:
        mode = "auto"
    normalized["scene_count_mode"] = mode
    try:
        fixed = int(normalized.get("scene_count_fixed", 6) or 6)
    except Exception:
        fixed = 6
    normalized["scene_count_fixed"] = max(1, min(fixed, 24))
    normalized["tavily_topic"] = str(normalized.get("tavily_topic") or "general").strip() or "general"
    return normalized


def get_project_settings(project_id: int) -> dict[str, Any]:
    return normalize_project_settings(read_json(project_file(project_id, "project_settings.json"), DEFAULT_PROJECT_SETTINGS))


def save_project_settings(project_id: int, settings: dict[str, Any]) -> None:
    current = get_project_settings(project_id)
    current.update(settings)
    current = normalize_project_settings(current)
    write_json(project_file(project_id, "project_settings.json"), current)
    meta = get_project(project_id)
    meta["tavily_topic"] = current.get("tavily_topic", "general")
    write_project_meta(project_id, meta)


def report_path(project_id: int, name: str) -> Path:
    return project_file(project_id, f"reports/{name}.json")


def get_report(project_id: int, name: str) -> dict[str, Any] | None:
    path = report_path(project_id, name)
    if not path.exists():
        return None
    return read_json(path, None)


def save_report(project_id: int, name: str, data: dict[str, Any]) -> Path:
    path = report_path(project_id, name)
    write_json(path, data)
    return path


def get_release_links(project_id: int) -> list[dict[str, Any]]:
    return read_json(project_file(project_id, "release_links.json"), [])


def save_release_links(project_id: int, links: list[dict[str, Any]]) -> None:
    write_json(project_file(project_id, "release_links.json"), links)


def next_release_id() -> int:
    return next_counter("release_id")


def parse_env() -> dict[str, str]:
    values = dict(DEFAULT_ENV)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "已配置，留空则不变"
    return f"已配置 ...{value[-4:]}，留空则不变"


def write_env(values: dict[str, str]) -> None:
    merged = dict(DEFAULT_ENV)
    merged.update(values)
    lines = [f"{key}={merged.get(key, '')}" for key in DEFAULT_ENV]
    write_text(ENV_FILE, "\n".join(lines) + "\n")


def save_env_patch(values: dict[str, str]) -> dict[str, str]:
    current = parse_env()
    merged = dict(current)
    for key in DEFAULT_ENV:
        if key not in values:
            continue
        incoming = values.get(key, "")
        if key in SECRET_KEYS and not incoming:
            continue
        merged[key] = incoming
    write_env(merged)
    return merged


def load_validation_cache() -> dict[str, Any]:
    return read_json(VALIDATION_FILE, {"sections": {}})


def save_validation_cache(cache: dict[str, Any]) -> None:
    write_json(VALIDATION_FILE, cache)


def secrets_payload() -> dict[str, Any]:
    values = parse_env()
    public_values = {key: ("" if key in SECRET_KEYS else values.get(key, "")) for key in DEFAULT_ENV}
    validation = load_validation_cache().get("sections", {})
    metadata = []
    status = {}
    sections = []

    for section in CONFIG_SECTIONS:
        fields = []
        for field in section["fields"]:
            key = field["key"]
            value = values.get(key, DEFAULT_ENV.get(key, ""))
            configured = bool(value)
            payload = {
                "key": key,
                "label": field["label"],
                "required": field["required"],
                "secret": field["secret"],
                "kind": field["kind"],
                "help": field["help"],
                "configured": configured,
                "value": "" if field["secret"] else value,
                "placeholder": mask_secret(value) if field["secret"] and configured else "",
                "options": field.get("options", []),
            }
            fields.append(payload)
            metadata.append({"key": key, "default": DEFAULT_ENV.get(key, ""), "label": field["label"]})
            status[key] = {
                "configured": configured,
                "value": "" if field["secret"] else value,
                "masked": mask_secret(value) if field["secret"] else value,
            }
        sections.append(
            {
                "key": section["key"],
                "title": section["title"],
                "description": section["description"],
                "validator": section["validator"],
                "fields": fields,
                "validation": validation.get(section["key"], {"status": "idle", "message": "尚未校验"}),
            }
        )

    return {
        "values": public_values,
        "keys": list(DEFAULT_ENV.keys()),
        "metadata": metadata,
        "status": status,
        "groups": [{"key": section["key"], "label": section["title"]} for section in CONFIG_SECTIONS],
        "sections": sections,
    }


def content_bundle(project_id: int) -> dict[str, Any]:
    meta = get_project(project_id)
    project_settings = get_project_settings(project_id)
    return {
        "content": get_content(project_id),
        "brief": get_brief(project_id),
        "summary": get_summary(project_id),
        "references": get_references(project_id),
        "content_strategy": read_json(project_file(project_id, "content_strategy.json"), {}),
        "content_audit": read_json(project_file(project_id, "content_audit.json"), {}),
        "video_spec": read_json(project_file(project_id, "video_spec.json"), {}),
        "scene_plan": read_json(project_file(project_id, "audio/scene_plan.json"), {}),
        "tavily_topic": project_settings.get("tavily_topic", "general"),
        "project_settings": project_settings,
        "project": meta,
    }


def list_project_files(project_id: int) -> list[dict[str, Any]]:
    root = project_dir(project_id)
    files: list[dict[str, Any]] = []
    try:
        paths = sorted(root.rglob("*"))
    except FileNotFoundError:
        return files
    for path in paths:
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except FileNotFoundError:
            continue
        rel = path.relative_to(root).as_posix()
        files.append(
            {
                "relative_path": rel,
                "name": path.name,
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
                "url": f"/data/projects/{project_id}/{rel}",
                "absolute_path": str(path.resolve()),
            }
        )
    return files


def scene_status(project_id: int) -> dict[str, Any]:
    summary = get_summary(project_id)
    expected = int(summary.get("scene_count", 0))
    content_path = project_file(project_id, "content.md")
    timeline_path = project_file(project_id, "audio/scene_timeline.json")
    if timeline_path.exists() and (not content_path.exists() or timeline_path.stat().st_mtime >= content_path.stat().st_mtime):
        timeline_payload = read_json(timeline_path, {})
        timeline_scenes = timeline_payload.get("scenes") if isinstance(timeline_payload, dict) else None
        if isinstance(timeline_scenes, list) and timeline_scenes:
            expected = len(timeline_scenes)
    scene_dir = project_file(project_id, "scenes")
    prompt_records = read_json(project_file(project_id, "scenes/scene_prompts.json"), [])
    records_by_filename: dict[str, dict[str, Any]] = {}
    if isinstance(prompt_records, list):
        for record in prompt_records:
            if not isinstance(record, dict):
                continue
            filename = str(record.get("filename") or "").strip()
            if filename:
                records_by_filename[filename] = record
    existing_by_index: dict[int, dict[str, Any]] = {}
    variant_count_by_index: dict[int, int] = {}
    suffix_priority = {".png": 0, ".jpg": 1, ".jpeg": 2, ".webp": 3, ".svg": 4}
    allowed_suffixes = set(suffix_priority)
    if scene_dir.exists():
        for path in sorted(scene_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in allowed_suffixes:
                continue
            if not re.fullmatch(r"s_\d+", path.stem):
                continue
            index = int(re.findall(r"(\d+)", path.stem)[0])
            variant_count_by_index[index] = variant_count_by_index.get(index, 0) + 1
            stat = path.stat()
            rel = f"scenes/{path.name}"
            prompt_path = path.with_suffix(".md")
            audit_path = path.with_suffix(".audit.json")
            record = records_by_filename.get(path.name, {})
            prompt_text = str(record.get("prompt") or "").strip()
            if not prompt_text and prompt_path.exists():
                prompt_text = read_text(prompt_path).strip()
            source_prompt = str(record.get("source_prompt") or "").strip()
            audit = read_json(audit_path, {}) if audit_path.exists() else {}
            if not audit:
                audit = record.get("audit") if isinstance(record.get("audit"), dict) else {}
            compact_prompt = re.sub(r"\s+", " ", prompt_text).strip()
            candidate = {
                "filename": path.name,
                "index": index,
                "url": f"/data/projects/{project_id}/scenes/{path.name}",
                "relative_path": rel,
                "absolute_path": str(path.resolve()),
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
                "prompt": prompt_text,
                "source_prompt": source_prompt,
                "prompt_preview": compact_prompt[:180],
                "prompt_url": f"/data/projects/{project_id}/scenes/{prompt_path.name}" if prompt_path.exists() else "",
                "audit": audit if isinstance(audit, dict) else {},
            }
            current = existing_by_index.get(index)
            if current is None:
                existing_by_index[index] = candidate
                continue
            current_priority = suffix_priority.get(Path(current["filename"]).suffix.lower(), 999)
            candidate_priority = suffix_priority.get(path.suffix.lower(), 999)
            if candidate_priority < current_priority:
                existing_by_index[index] = candidate
    existing = [existing_by_index[index] for index in sorted(existing_by_index)]
    if expected <= 0:
        if isinstance(prompt_records, list) and prompt_records:
            expected = len(prompt_records)
        elif existing:
            expected = max(item["index"] for item in existing)
    existing_indexes = {item["index"] for item in existing}
    missing = [f"s_{idx:02d}" for idx in range(1, expected + 1) if idx not in existing_indexes]
    missing_items = [
        {
            "filename": f"s_{idx:02d}.png",
            "stem": f"s_{idx:02d}",
            "index": idx,
            "expected_path": f"scenes/s_{idx:02d}.png",
        }
        for idx in range(1, expected + 1)
        if idx not in existing_indexes
    ]
    hidden_variants = sum(max(0, count - 1) for count in variant_count_by_index.values())
    return {
        "expected_count": expected,
        "generated_count": len(existing),
        "existing": existing,
        "missing": missing,
        "missing_items": missing_items,
        "hidden_variants": hidden_variants,
        "complete": expected == 0 or not missing,
    }


def cleanup_scene_outputs(project_id: int) -> int:
    scene_dir = project_file(project_id, "scenes")
    if not scene_dir.exists():
        return 0
    removed = 0
    removable_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".md"}
    for path in scene_dir.iterdir():
        if not path.is_file():
            continue
        if re.fullmatch(r"s_\d+\.audit", path.stem) and path.suffix.lower() == ".json":
            path.unlink(missing_ok=True)
            removed += 1
            continue
        if not re.fullmatch(r"s_\d+", path.stem):
            continue
        if path.suffix.lower() not in removable_suffixes:
            continue
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def cleanup_extra_scene_outputs(project_id: int, expected_count: int) -> int:
    scene_dir = project_file(project_id, "scenes")
    if not scene_dir.exists():
        return 0
    expected_count = max(0, int(expected_count or 0))
    removed = 0
    removable_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".md"}
    for path in scene_dir.iterdir():
        if not path.is_file():
            continue
        audit_match = re.fullmatch(r"s_(\d+)\.audit", path.stem)
        if audit_match and path.suffix.lower() == ".json":
            index = int(audit_match.group(1))
            if index > expected_count:
                path.unlink(missing_ok=True)
                removed += 1
            continue
        match = re.fullmatch(r"s_(\d+)", path.stem)
        if not match:
            continue
        if path.suffix.lower() not in removable_suffixes:
            continue
        index = int(match.group(1))
        if index <= expected_count:
            continue
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def latest_job_path(project_id: int) -> Path:
    return project_file(project_id, "jobs/latest.json")


def save_latest_job(project_id: int, payload: dict[str, Any]) -> None:
    write_json(latest_job_path(project_id), payload)
    meta = get_project(project_id)
    meta["last_job_status"] = payload.get("status", "idle")
    write_project_meta(project_id, meta)


def load_latest_job(project_id: int) -> dict[str, Any] | None:
    path = latest_job_path(project_id)
    if not path.exists():
        return None
    return read_json(path, None)
