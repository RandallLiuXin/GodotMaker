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

- Tags are now planned and evaluated as minimal playable units, with runtime proof required for the playable path before evaluation can approve.
- Evaluate completion now validates that every Playable Unit row has a recorded E2E test and non-empty runtime evidence.
- Build workers now receive one game-mechanic function per task instead of system-first work units.
- Visual prompt style guide now gives asset generation a shared visual language.
- Finalize now archives the current tag's E2E tests and screenshots under `docs/tags/<Tag>/evidence/` for later review and debugging.

## Fixed

- (WIP) Rewire Agent prompt/output trace capture to `PreToolUse`/`PostToolUse` because the `SubagentStart` payload has no `prompt` field and silently wrote 0-byte traces.

## Removed
