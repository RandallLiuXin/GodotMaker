# Codex runtime

当你希望 GodotMaker 通过 Codex skills 运行时，使用 Codex runtime。

## 配置步骤

1. 安装 Codex 并登录。
2. 发布项目：

```bash
python tools/publish.py --agent codex /path/to/my-game
```

## 项目配置

```yaml
agent: codex
```

Codex 项目使用 `.agents/skills`、`.agents/agents`、`.agents/templates`、
`.agents/references`、`.codex/hooks.json` 和 `AGENTS.md`。

## 图片和 VQA

对于 Codex 项目，`native` 会映射到当前 Codex 宿主暴露的原生图片和视觉能力。
你也可以显式设置 `asset_image_model: codex` 或 `vqa_model: codex`。
