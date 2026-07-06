# 短片工坊 Short Video Studio

一个本地短视频生产工作台：从频道模板、选题、brief、脚本生成，到配音、字幕、场景图、封面、成片合成和投放发布管理。

## 主要功能

- 频道模板：不同垂类、人设、视觉风格和提示词独立管理。
- 主题项目：项目会跟随频道读取，避免不同频道主题混在一起。
- 文案生成：支持 DeepSeek 生成 content.md，并可做选题评分、脚本体检、节奏增强、质量总检。
- 图片生产：支持火山方舟、APIYI/OpenAI 兼容、ChatGPT 网页自动化等入口。
- 音频字幕：支持豆包/火山 TTS 和 ASR 字幕对齐。
- 成片合成：按语音时长、字幕和场景图生成最终视频。
- 投放发布：可对接 social-auto-upload，管理抖音、快手、小红书发布流程。

## 快速启动

推荐 Windows + Python 3.10。

```powershell
cd C:\path\to\short-video-studio
py -3.10 -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run.bat
```

启动后打开：

```text
http://127.0.0.1:8765/studio/
```

停止服务：

```powershell
.\stop.bat
```

## 配置

应用会读取本地配置文件：

```text
data/config/.env
```

可以复制 `.env.example`：

```powershell
New-Item -ItemType Directory -Force data\config
Copy-Item .env.example data\config\.env
```

也可以直接在应用里的“配置”页面填写。不要把 `data/config/.env`、cookie、登录缓存或授权文件提交到 GitHub。

## 数据目录

默认数据写在：

```text
data/
```

其中：

- `data/templates/`：频道模板示例，可以随代码发布。
- `data/projects/`：你的选题、文案、图片、音频、视频产物，默认不提交。
- `data/config/`：密钥、登录态、校验缓存，默认不提交。
- `data/template-products/`：本地导出的频道产物索引，默认不提交。

## 发布到 GitHub

建议第一次先建私有仓库，确认没有敏感信息后再公开。

```powershell
git init
git add .
git commit -m "Initial release"
git branch -M main
git remote add origin https://github.com/<your-name>/short-video-studio.git
git push -u origin main
```

提交前建议检查：

```powershell
git status --short
git status --ignored --short
```

确认没有提交 `data/config/`、`data/projects/`、`build/`、日志、截图、视频和音频产物。

## 注意

本项目会调用第三方模型、TTS、ASR、图片生成和发布平台。公开仓库时只发布代码和模板，不发布账号、密钥、cookie、授权文件、私有素材和生成成片。

特别鸣谢
谢谢！
<a href="https://linux.do/" >LINUX DO</a>
