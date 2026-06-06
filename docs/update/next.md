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
- Added validation for asset-generation handoff manifests so generated-art runs can detect missing fields and files.
- Added a manifest update helper so generated-art runs can upsert handoff entries through a validated tool.
- Added a 2D source-sheet processor so generated grids can produce cropped assets and processing reports.

## Changed

- Clarified README preview-feature scope and roadmap priorities for art production, Codex runner fallback, 3D support, and audio generation.
- `/gm-asset` now runs a lightweight user-asset preflight before generation so CLI-driven runs can notice files already placed under `assets/`.
- `/gm-asset` now plans generated art as source, final, and curation artifacts so runs keep clearer asset handoff records.

## Fixed

- (WIP) Rewire Agent prompt/output trace capture to `PreToolUse`/`PostToolUse` because the `SubagentStart` payload has no `prompt` field and silently wrote 0-byte traces.

## Removed

- Removed the legacy `tools/asset_gen.py` helper in favor of the spec-driven asset source generator.
