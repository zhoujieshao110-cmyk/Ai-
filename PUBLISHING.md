# GitHub 发布检查清单

## 1. 不要提交的内容

这些目录和文件已经写入 `.gitignore`：

- `data/config/`：API Key、cookie、ChatGPT 浏览器 profile、授权/校验缓存。
- `data/projects/`：你的真实选题、文案、图片、音频、视频。
- `data/template-products/`：本地导出的频道产物。
- `build/`、`dist/`：打包产物。
- `_analysis/`、`_manual_api_test/`、`_manual_apiyi_official_test/`：本地分析和手工测试材料。
- `*.log`、`*.pid`、`tmp*`、`verify-*`：日志、进程文件和截图。

## 2. 提交前自检

```powershell
git status --short
git status --ignored --short
```

如果已经初始化 Git，可以用下面的命令粗查敏感词：

```powershell
git ls-files | % { Select-String -Path $_ -Pattern "sk-|api[_-]?key|access[_-]?key|secret|cookie|authorization" -SimpleMatch -ErrorAction SilentlyContinue }
```

如果误提交过密钥，先停下来：删除文件不等于从 Git 历史里删除。应立即重置/轮换密钥，再清理提交历史。

## 3. 推荐发布步骤

```powershell
git init
git add .
git status --short
git commit -m "Initial release"
git branch -M main
git remote add origin https://github.com/<your-name>/short-video-studio.git
git push -u origin main
```

## 4. 仓库建议

- 第一次使用 Private 仓库。
- README 只展示功能、安装、配置方式，不贴真实账号或密钥。
- 需要演示素材时，单独准备匿名 demo 项目，不直接用真实 `data/projects`。
- 发布 EXE 时用 GitHub Releases 上传打包文件，不把 `build/` 提交进代码仓库。
