# Claude Code runtime

Use Claude Code when you want the default GodotMaker runtime.

## Setup

1. Install Claude Code.
2. Sign in through the Claude Code CLI.
3. Publish the project:

```bash
python tools/publish.py /path/to/my-game
```

## Project config

```yaml
agent: claude-code
```

Claude Code projects use `.claude/skills`, `.claude/agents`,
`.claude/templates`, and `CLAUDE.md`.

## Image and VQA

`native` VQA uses the active Claude Code runtime's image-inspection path.
`native` image generation requires a Claude-side image-generation capability.
If that is unavailable, set `asset_image_model` to `codex` or an API-backed
provider.
