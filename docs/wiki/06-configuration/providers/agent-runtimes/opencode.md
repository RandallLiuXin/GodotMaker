# OpenCode runtime

Use OpenCode when you want GodotMaker's code/text stages to run through
OpenCode models such as DeepSeek.

## Setup

1. Install OpenCode.
2. Connect your model provider with OpenCode, for example through
   `opencode auth login` or the OpenCode TUI `/connect` flow.
3. Publish the project:

```bash
python tools/publish.py --agent opencode /path/to/my-game
```

## Project config

```yaml
agent: opencode
```

OpenCode projects use `.opencode/skills`, `.opencode/agents`,
`.opencode/templates`, `.opencode/references`, and `AGENTS.md`.

## Image and VQA

OpenCode support does not use runtime-native image generation or image
inspection. Set both fields to `codex` or API-backed providers before running
the full pipeline.

Recommended options:

```yaml
asset_image_model: codex
vqa_model: codex
```

or API-backed providers:

```yaml
asset_image_model: gemini:gemini-3.1-flash-image-preview
vqa_model: gemini:gemini-2.5-flash
```

Run `python tools/check_env.py` after changing these fields.
