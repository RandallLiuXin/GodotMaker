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

## Known tool limitation

OpenCode currently has a known file-discovery limitation for dot-directories
such as `.godotmaker/` or `.opencode/`. GodotMaker publishes an OpenCode
runtime workaround for project state files.

- https://github.com/anomalyco/opencode/issues/11691
- https://github.com/anomalyco/opencode/issues/10906

Remove the workaround once OpenCode reliably discovers dot-directory files.

## Role models

OpenCode subagents inherit the active parent OpenCode session model. The
per-role model settings in `.godotmaker/config.yaml`, such as `worker_model`
and `asset_producer_model`, currently apply to Claude Code projects and do not
override OpenCode subagent models. Start the OpenCode session with the model you
want delegated roles to use.

## Hooks and permissions

OpenCode does not expose the same subagent lifecycle payloads as Claude Code.
GodotMaker therefore does not treat OpenCode hooks as full Claude Code hook
parity.

The OpenCode adapter still runs root-stage and lifecycle gates, including
stage prerequisites, completion checks, clean-workspace checks, session start,
and compaction metrics. Known child-session read/write operations are not
passed through GodotMaker's `agent_id`-based Python subagent gates because
OpenCode does not expose the same subagent identity payload.

This means OpenCode cannot currently reuse the full Claude Code / Codex
subagent hook contract. Worker report lifecycle checks, subagent metrics, and
Python read/write gates that depend on a stable subagent identity are degraded
for OpenCode child sessions. Root-stage gates still run through the OpenCode
adapter.

Related upstream OpenCode issues:

- https://github.com/anomalyco/opencode/issues/15403
- https://github.com/anomalyco/opencode/issues/16626
- https://github.com/anomalyco/opencode/issues/17412
- https://github.com/anomalyco/opencode/issues/12566

Subagent write boundaries are handled by OpenCode-native
`.opencode/agents/*.md` `permission` frontmatter. Read-only review-style
agents such as `reviewer`, `verifier`, and `gdd-auditor` are published with
`permission.edit: deny`; implementation agents such as `worker` keep the edit
permissions they need to do their assigned work. This only covers edit
permissions; it is not a replacement for Claude-style read-access hooks.

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
