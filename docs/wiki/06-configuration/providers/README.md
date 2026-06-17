# Provider setup

GodotMaker has two independent provider layers:

1. Coding-agent runtimes run the `/gm-*` workflow.
2. Image/VQA providers generate art sources or inspect screenshots.

Choosing a coding-agent runtime does not automatically choose an image or VQA
provider. Configure both layers in `.godotmaker/config.yaml`.

## Coding-agent runtimes

- [Claude Code](agent-runtimes/claude-code.md)
- [Codex](agent-runtimes/codex.md)
- [OpenCode](agent-runtimes/opencode.md)

## Image and VQA providers

- [native](image-vqa/native.md)
- [codex](image-vqa/codex.md)
- [gemini](image-vqa/gemini.md)
- [openai](image-vqa/openai.md)
- [grok](image-vqa/grok.md)
