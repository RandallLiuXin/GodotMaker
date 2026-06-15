# 安装

GodotMaker 能把你的游戏想法变成一个可以运行的 Godot 4 项目。正常路径是 `godotmaker-cli`：它会协助把想法整理成 GDD，然后驱动 Agent 工作流，直到当前设计范围完成构建、测试、评估和修复。

## 前置软件

| 工具 | 最低版本 | GodotMaker 为什么需要它 | 下载地址 |
|------|----------|------------------------|---------|
| Godot | 4.5+ | 编译并运行生成的游戏 | https://godotengine.org/download |
| Git | 2.30+ | 追踪改动并启用隔离 Agent worktree | https://git-scm.com/downloads |
| Node.js | 22+ | 运行 `godotmaker-cli` 和 Godot MCP 工具 | https://nodejs.org |
| Python | 3.10+ | 运行 GodotMaker 辅助脚本和验证工具 | https://python.org/downloads |
| Claude Code 或 Codex | 最新版 | 实现和评估游戏的 Agent runtime | https://claude.ai/code 或 https://openai.com/codex/ |

先安装上面的工具，然后继续。Claude Code 和 Codex 不需要同时安装；选择一个已登录的 Agent runtime 即可。

## 选择 Agent runner

选择 Claude Code：

```bash
godotmaker-cli --agent claude-code
```

选择 Codex：

```bash
godotmaker-cli --agent codex
```

Agent 选择优先级是：启动参数 `--agent`、项目 `.godotmaker/config.yaml`、CLI 全局配置、默认值。

## API Key

GodotMaker 可以根据 `.godotmaker/config.yaml` 使用 runtime 原生图片和视觉能力，或者使用 API 后端 provider。

只有项目选择 API 后端 provider 时，才需要 API key。GodotMaker 本身不提供外部模型服务。如果你希望 Claude Code 项目由 Codex 负责生图，可以设置 `asset_image_model: codex`；这需要 Codex CLI 位于 PATH 中，不需要图片 API key。

| Key | 什么时候需要 | 用途 |
|-----|--------------|------|
| `GOOGLE_API_KEY` 或 `GEMINI_API_KEY` | `vqa_model` 或素材模型使用 `gemini:<model>` | Gemini 视觉 QA 和图片生成 |
| `OPENAI_API_KEY` | `vqa_model` 或素材模型使用 `openai:<model>` | OpenAI 视觉理解和图片生成 |
| `XAI_API_KEY` | 素材图片模型使用 `grok:<model>` | xAI 图片生成 |

### Windows PowerShell

```powershell
[System.Environment]::SetEnvironmentVariable("GOOGLE_API_KEY", "your-key-here", "User")
```

如果需要其他可选 key，替换变量名后重复执行。执行后关闭并重新打开终端。

### macOS 或 Linux

把需要的配置写入 shell profile，然后重启终端：

```bash
export GOOGLE_API_KEY="your-key-here"
# Optional:
# export OPENAI_API_KEY="your-key-here"
# export XAI_API_KEY="your-key-here"
```

## 安装 GodotMaker

安装 CLI：

```bash
npm install -g godotmaker-cli
```

确认 CLI 可用：

```bash
godotmaker-cli --help
```

如果你要开发 GodotMaker 框架本身，或者手动发布框架文件，克隆仓库：

```bash
git clone https://github.com/RandallLiuXin/GodotMaker.git
cd GodotMaker
pip install -r tools/requirements.txt
python tools/check_env.py
```

如果你从未设置过 Git 身份，运行：

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## 环境检查是什么意思

`python tools/check_env.py` 会检查本地工具和已选择的 provider。

- `[PASS]` 表示该项已就绪
- `[WARN]` 表示某个可选功能不可用
- `[FAIL]` 表示所选工作流缺少必需项

开始第一款游戏前，先修复所有 `[FAIL]`。

## 下一步

继续阅读[你的第一款游戏](first-game.md)。
