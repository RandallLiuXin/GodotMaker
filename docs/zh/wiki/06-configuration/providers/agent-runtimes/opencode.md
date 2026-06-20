# OpenCode runtime

当你希望 GodotMaker 的代码和文本阶段通过 DeepSeek 等 OpenCode 模型运行时，
使用 OpenCode runtime。

## 配置步骤

1. 安装 OpenCode。
2. 通过 `opencode auth login` 或 OpenCode TUI 的 `/connect` 流程连接模型 provider。
3. 发布项目：

```bash
python tools/publish.py --agent opencode /path/to/my-game
```

## 项目配置

```yaml
agent: opencode
```

OpenCode 项目使用 `.opencode/skills`、`.opencode/agents`、
`.opencode/templates`、`.opencode/references` 和 `AGENTS.md`。

## 已知工具限制

OpenCode 目前对 `.godotmaker/` 或 `.opencode/` 这类 dot-directory 存在已知
文件发现限制。GodotMaker 会为项目状态文件发布 OpenCode runtime workaround。

- https://github.com/anomalyco/opencode/issues/11691
- https://github.com/anomalyco/opencode/issues/10906

等 OpenCode 能稳定发现 dot-directory 文件后，请删除这段 workaround。

## 角色模型

OpenCode 子 Agent 会继承当前父 OpenCode 会话的模型。`.godotmaker/config.yaml`
中的按角色模型设置，例如 `worker_model` 和 `asset_producer_model`，目前用于
Claude Code 项目，不会覆盖 OpenCode 子 Agent 模型。请用你希望委派角色继承
的模型启动 OpenCode 会话。

## Hooks 和权限

OpenCode 不暴露与 Claude Code 等价的子 Agent 生命周期 payload。因此，
GodotMaker 不把 OpenCode hooks 视为完整的 Claude Code hook parity。

OpenCode adapter 仍会运行主阶段和生命周期 gate，包括阶段前置检查、完成检查、
工作区清洁检查、会话启动和 compaction 指标。已知的子会话读写操作不会再进入
GodotMaker 基于 `agent_id` 的 Python 子 Agent gate，因为 OpenCode 不暴露
同等的子 Agent 身份 payload。

这意味着 OpenCode 当前无法完整复用 Claude Code / Codex 的子 Agent hook
契约。依赖稳定子 Agent 身份的 Worker report 生命周期检查、子 Agent 指标和
Python 读写 gate，在 OpenCode 子会话中会降级。主阶段 gate 仍会通过 OpenCode
adapter 运行。

相关的 OpenCode 上游 issue：

- https://github.com/anomalyco/opencode/issues/15403
- https://github.com/anomalyco/opencode/issues/16626
- https://github.com/anomalyco/opencode/issues/17412
- https://github.com/anomalyco/opencode/issues/12566

子 Agent 的写入边界由 OpenCode 原生的 `.opencode/agents/*.md`
`permission` frontmatter 处理。`reviewer`、`verifier`、`gdd-auditor`
这类只读审查角色会发布为 `permission.edit: deny`；`worker` 这类实现角色
保留完成任务所需的编辑权限。这个边界只覆盖 edit permission；它不是
Claude-style 读取访问 hook 的替代品。

## 图片和 VQA

OpenCode 支持不使用 runtime 原生生图或读图能力。运行完整流水线前，请把这两个字段
设置为 `codex` 或 API-backed provider。

推荐配置：

```yaml
asset_image_model: codex
vqa_model: codex
```

也可以使用 API-backed provider：

```yaml
asset_image_model: gemini:gemini-3.1-flash-image-preview
vqa_model: gemini:gemini-2.5-flash
```

修改后运行 `python tools/check_env.py`。
