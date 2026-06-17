# Claude Code runtime

Claude Code 是 GodotMaker 的默认 runtime。

## 配置步骤

1. 安装 Claude Code。
2. 通过 Claude Code CLI 登录。
3. 发布项目：

```bash
python tools/publish.py /path/to/my-game
```

## 项目配置

```yaml
agent: claude-code
```

Claude Code 项目使用 `.claude/skills`、`.claude/agents`、
`.claude/templates` 和 `CLAUDE.md`。

## 图片和 VQA

`native` VQA 使用当前 Claude Code runtime 的图片检查路径。`native` 生图需要
Claude 侧实际提供生图能力。如果不可用，请把 `asset_image_model` 改成 `codex`
或 API-backed provider。
