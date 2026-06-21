# Next Release

> **Contributors:** Every pull request MUST include an entry in this file describing the change.
> When a new version is released, this file will be archived as `vX.Y.Z.md` and a fresh copy will take its place.

## How to add an entry

Append your change under the appropriate category below. Use this format:

```
- Brief description of the change (#PR_NUMBER) — @author
```

If no category fits, add a new one following [Keep a Changelog](https://keepachangelog.com/) conventions.

---

## Added

- Added the initial OpenCode publish target with `.opencode` skills, agents, runtime references, and project instructions.
- Added OpenCode `godot` MCP registration during publish and environment checks for the published `.opencode` runtime tree.
- Added provider setup docs for agent runtimes and image/VQA selectors, including OpenCode image/VQA capability gates.
- Added an OpenCode hook adapter plugin that runs the shared GodotMaker hook contract through OpenCode runtime events.
- Added `/gm-asset` provider routing for OpenAI image generation selectors.

## Changed

- Downgraded OpenCode hook support to root-stage lifecycle gates plus
  OpenCode-native subagent permissions, instead of claiming full Claude
  Code-style subagent hook parity.
- Updated README and wiki first-run docs to use the current `godotmaker-cli` command, runner selection flags, OpenCode setup notes, Node.js requirement, and project config flow.

## Fixed

- Fixed verify/build gates so Godot headless shutdown notes no longer block
  the pipeline, while other Godot diagnostics fail closed.
- Fixed scaffold addon validation so full repository checkouts inside
  `addons/*` are rejected before they can break Godot class scanning.
- Fixed OpenCode subagents so delegated roles inherit the active session model correctly.
- Fixed OpenCode worker deadlocks by publishing explicit external-directory
  permissions for subagents.
- Fixed headless-build and gdUnit guidance so workers read `godot_path` through
  the selected project-local agent config instead of Claude-specific paths.
- Fixed verify static checks so `check_project.py` tool failures are reported as
  tooling errors instead of static-check passes.
- Fixed the API-backed OpenAI image provider so supported reference images are
  all passed to the generation call instead of silently using only the first one.
- Fixed OpenCode session-idle Stop hook handling so Stop hook block decisions
  are sent back to the active session instead of terminating the worker process.
- Fixed OpenCode runtime guidance for dot-directory state files so agents do
  not treat missing Glob results as authoritative for known project metadata.

## Removed
