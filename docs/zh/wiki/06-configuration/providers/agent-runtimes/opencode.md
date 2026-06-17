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
