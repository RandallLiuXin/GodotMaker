# 项目配置

`.godotmaker/config.yaml` 是每个项目独立的配置文件，用来选择智能体运行时、角色模型、视觉 QA 模型和资源生成模型。它位于游戏项目目录中，因此不同游戏可以使用不同配置。

## 文件如何创建

第一次运行 `python tools/publish.py <project>` 时，发布脚本会把 GodotMaker 默认配置复制到 `.godotmaker/config.yaml`。之后再次发布不会覆盖你的配置；只有 `agent` 字段会更新为当前选择的运行时。

## 常用字段

**`agent`** — 当前项目选择的编码智能体运行时，例如 `claude-code` 或 `codex`。

**`worker_model`** — 编写游戏代码的 Claude 模型。默认是 `sonnet`；需要更强实现推理的游戏可改为 `opus`。

**`verifier_model`**、**`reviewer_model`**、**`analyst_model`**、**`auditor_model`**、**`decomposer_model`** — 验证、审查、图片分析、审计和 GDD 拆分等角色的默认模型。

**`vqa_model`** — 视觉 QA 的主模型选择器。支持 `native`、`codex`、`gemini:<model>` 和 `openai:<model>`。`native` 表示由当前智能体运行时直接检查图片；`codex` 表示由 Codex 提供图片检查能力；API 后端会运行 `visual_qa.py`。

**`vqa_fallback_model`** — 主 VQA 后端不可用时的回退模型。支持 `native`、`codex` 和 `none`。

**`asset_image_model`** — `/gm-asset` 使用的图片生成选择器。支持 `native`、`codex`、`gemini:<model>`、`openai:<model>` 和 `grok:<model>`。`native` 由当前运行时处理；`codex` 由 Codex 原生图片生成处理；API 后端会运行 `tools/asset_source_generate.py --spec <spec.json>`，脚本会拒绝运行时提供方。


默认配置大致如下：

```yaml
agent: claude-code

vqa_model: native
vqa_fallback_model: native

asset_image_model: native

worker_model: sonnet
verifier_model: sonnet
reviewer_model: sonnet
analyst_model: sonnet
auditor_model: sonnet
decomposer_model: sonnet
```

## 运行时原生图片生成

`native` 不是 API 提供方，而是当前智能体运行时提供的能力。

模板默认使用 native 读图和 native 图片生成。

对于 Codex 项目，`asset_image_model: native` 映射到 Codex 原生图片生成，前提是当前宿主暴露了这个能力。对于 Claude Code 项目，`native` 需要 Claude 侧有原生生图工具。没有原生路径时，`/gm-asset` 必须停止并要求你改用 `codex` 或 API 后端。

如果 Claude Code 项目希望使用 Codex 图片生成：

```yaml
asset_image_model: codex
```

这会选择 Codex 作为图片生成 provider。它需要 Codex CLI 位于 PATH 中，不需要图片 API key。

## API Key

带提供方前缀的选择器需要对应 API key：

| Selector | 需要的 key |
|---|---|
| `gemini:<model>` | `GOOGLE_API_KEY` 或 `GEMINI_API_KEY` |
| `openai:<model>` | `OPENAI_API_KEY` |
| `grok:<model>` | `XAI_API_KEY` |

资源生成不会在 key 缺失时静默切换提供方。VQA 只有在显式配置 `vqa_fallback_model` 时才会回退。

## 如何修改配置

打开 `.godotmaker/config.yaml`，修改冒号后的值即可。例如使用 Codex 图片生成：

```yaml
asset_image_model: codex
```

使用 OpenAI API 生成图片：

```yaml
asset_image_model: openai:gpt-image-2
```

下一次运行 `/gm-*` 命令时会读取新配置。已经运行中的命令不会自动感知修改，需要下一次会话或阶段调用才会生效。

## 关于 `.claude/settings.json`

Claude Code 项目还会有 `.claude/settings.json`，它负责注册 GodotMaker hook 脚本。这个文件由框架管理；如果升级后 hook 不再触发，可以运行 `python tools/publish.py --force <project>` 重新发布。
