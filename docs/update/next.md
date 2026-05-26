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

- (WIP) Diagnostic log at `.godotmaker/log_agent_tool_debug.log` that records every phase of `log_agent_tool.py` so the next failure mode is localizable from artifacts.

## Changed

- README status notes now mark Codex runner support and AI-generated art as preview features and link to the roadmap.
- Visual QA now follows configured `vqa_model` / `vqa_fallback_model` backend selection and shares one criteria prompt across runtime-native and API-backed paths.
- gm-asset references now separate planning, provider contracts, tool usage, recipes, and post-processing rules.
- gm-asset generation now documents fixed-path batch reports for active Codex art assets and scene references.

## Fixed

- (WIP) Rewire Agent prompt/output trace capture to `PreToolUse`/`PostToolUse` because the `SubagentStart` payload has no `prompt` field and silently wrote 0-byte traces.
- Codex image generation now claims the exact `ImageGenerationEnd.saved_path` before finalizing project assets.

## Removed
