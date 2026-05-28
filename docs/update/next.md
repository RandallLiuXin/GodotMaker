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
- `/gm-evaluate` now archives each completed run's `e2e/screenshots/` and `.godotmaker/evaluation.json` under `.godotmaker/evaluation-runs/` for iteration-to-iteration visual debugging.

## Changed

## Fixed

- (WIP) Rewire Agent prompt/output trace capture to `PreToolUse`/`PostToolUse` because the `SubagentStart` payload has no `prompt` field and silently wrote 0-byte traces.
- `gecs` and `godot-api` run inline instead of forking a separate skill context, fixing headless builds that could stall when a worker looked up ECS or Godot APIs. (#31)

## Removed
