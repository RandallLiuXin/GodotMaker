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

- Updated README and wiki first-run docs to use the current `godotmaker-cli` command, runner selection flags, Node.js requirement, and project config flow.

## Fixed

- Fixed OpenCode subagents so delegated roles inherit the active session model correctly.
- Fixed the API-backed OpenAI image provider so supported reference images are
  all passed to the generation call instead of silently using only the first one.

## Removed
