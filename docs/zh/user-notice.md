# 用户须知

GodotMaker 会自动做什么、哪些内容留在本地、哪些内容可能被发送到外部服务。

## 本地项目所有权

GodotMaker 会在你的机器上创建一个普通 Godot 项目。生成的项目不会托管在 GodotMaker 平台上，也不会被锁进专有编辑器或运行时。

你可以像处理任何 Godot 项目一样打开、编辑、版本管理、导出和发布生成的游戏。

用 GodotMaker 创建的游戏、项目源码、素材、截图、报告、导出产物和其他输出都不是 GodotMaker，也不属于 Licensed Work。它们归创建者所有，但仍需遵守第三方引擎、素材、模型 provider、runtime 或依赖项可能适用的条款。

## 发布脚本自动行为

发布脚本（`tools/publish.py`）会在你的游戏项目目录中执行本地初始化操作。如果你熟悉这些工具，也可以自行管理；脚本会跳过已经完成的步骤。

### Git 仓库初始化

**会发生什么：** 如果你的项目目录没有 `.git/` 文件夹，发布脚本会运行 `git init` 并创建一个初始空提交。

**为什么：** GodotMaker 使用隔离 git worktree 运行 Agent Worker。Git worktree 要求至少存在一个提交。

这与把代码推送到 GitHub 或任何远端服务器无关。这个提交只存在于本地，用来启用 Worker 基础设施。

**如果我已经有 git 仓库怎么办？** 脚本会检测 `.git/` 并跳过 `git init`。如果已经存在提交，也会跳过。你的现有历史不会被改写。

## Agent Runtime 数据

GodotMaker 是一个编排框架。它依赖你选择的 Agent runtime，例如 Claude Code 或 Codex，来读取项目文件、编写代码、运行工具和评估结果。

根据 runtime 和设置不同，以下内容可能对该 runtime 可见：

- 你的游戏想法、GDD 和规划文档
- 生成项目中的源码和测试
- 命令输出和工具日志
- 用于视觉 QA 的截图
- 发送给实现、验证、评审、评估或分析 Agent 的 prompt 和指令

请查看你使用的 Agent runtime 的隐私、留存和计费条款。GodotMaker 不控制这些外部政策。

## 可选 API Provider

当项目配置选择 API 后端模型时，GodotMaker 可以调用外部 provider。

可能的 provider 包括：

- Gemini，通过 `GOOGLE_API_KEY` 或 `GEMINI_API_KEY`
- OpenAI，通过 `OPENAI_API_KEY`
- xAI Grok，通过 `XAI_API_KEY`

根据所选功能不同，请求内容可能包含 prompt、素材描述、截图、参考图或生成出的素材数据。API 使用可能由 provider 计费。

如果你不希望某个 provider 接收项目数据，不要配置该 provider 的模型或 API key。

## Runtime 原生图片和视觉路径

有些配置会使用 runtime 原生图片或视觉能力，而不是直接配置 API key。在这种情况下，图片或截图数据会由当前 Agent runtime 处理，而不是由 GodotMaker 的 Python API client 处理。

这可以减少单独 API 配置，但不代表数据只留在本地。该 runtime 自己的数据政策仍然适用。

## Secrets

不要把 API key、访问 token 或私有凭据提交到你的游戏项目或 GodotMaker 仓库。

推荐存放方式：

- 用环境变量存放 API key
- 用 gitignored 的本地 runtime 配置存放机器相关路径
- 用 GitHub repository secrets 存放 CI 或发布自动化所需密钥
