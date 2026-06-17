# Provider 配置

GodotMaker 有两层相互独立的 provider：

1. Coding-agent runtime 负责运行 `/gm-*` 工作流。
2. 图片 / VQA provider 负责生成美术 source 或检查截图。

选择某个 coding-agent runtime 不等于自动选择图片或 VQA provider。两层都通过
`.godotmaker/config.yaml` 配置。

## Coding-agent runtime

- [Claude Code](agent-runtimes/claude-code.md)
- [Codex](agent-runtimes/codex.md)
- [OpenCode](agent-runtimes/opencode.md)

## 图片和 VQA provider

- [native](image-vqa/native.md)
- [codex](image-vqa/codex.md)
- [gemini](image-vqa/gemini.md)
- [openai](image-vqa/openai.md)
- [grok](image-vqa/grok.md)
