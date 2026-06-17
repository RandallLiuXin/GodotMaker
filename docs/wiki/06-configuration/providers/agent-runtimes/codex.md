# Codex runtime

Use Codex when you want GodotMaker to run through Codex skills.

## Setup

1. Install Codex and sign in.
2. Publish the project:

```bash
python tools/publish.py --agent codex /path/to/my-game
```

## Project config

```yaml
agent: codex
```

Codex projects use `.agents/skills`, `.agents/agents`, `.agents/templates`,
`.agents/references`, `.codex/hooks.json`, and `AGENTS.md`.

## Image and VQA

For Codex projects, `native` maps to Codex runtime-native image and vision
capabilities when the active Codex host exposes them. You can also set
`asset_image_model: codex` or `vqa_model: codex` explicitly.
