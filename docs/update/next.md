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
- A resized image's untouched original is archived to `assets/origin/` for comparison and debugging.

## Changed

- Clarified source-available licensing language and excluded internal planning notes from the documentation site.
- Scaffold generates and commits Godot `.uid` import metadata in its initial commit so the project tree starts clean for `/gm-build`.
- GDD design audit now focuses on the current release tag and only runs its second pass when the first turns up enough gaps, so simple or already-clear designs aren't over-questioned.
- `/gm-asset` generates Codex images in one `codex exec` call with parallel subagents (one per asset) instead of one serial call per image.

## Fixed

- (WIP) Rewire Agent prompt/output trace capture to `PreToolUse`/`PostToolUse` because the `SubagentStart` payload has no `prompt` field and silently wrote 0-byte traces.
- Resized image assets are scaled proportionally and transparency-padded instead of stretched, so non-square art is no longer squashed.
- Clarified Visual QA handling of normal gameplay captures versus `--debug-collisions` collision-check captures.
- `/gm-build` no longer falls back to slow sequential workers when the tree has uncommitted import artifacts.
- Worker dispatch briefs now explicitly block approval prompts and confirmation pauses during non-interactive pipeline runs.
- Codex image generation copies each subagent's own generated file to a fixed per-asset path instead of the newest file in `generated_images`, which was unsafe once generation runs in parallel.

## Removed
