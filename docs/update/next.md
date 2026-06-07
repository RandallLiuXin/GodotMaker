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
- Added magenta-background and edge-fringe processing support to the 2D source-sheet processor for production-shaped extraction sheets.
- Added a first-pass asset curation contract for generated source sheets, canonical selections, and rejected candidates.
- Added a curation selection helper so accepted candidates can be finalized into runtime asset paths.
- Split the asset generation reference into runtime pipeline and prompt-contract references.

## Changed

- Clarified README preview-feature scope and roadmap priorities for art production, Codex runner fallback, 3D support, and audio generation.
- `/gm-asset` now runs a lightweight user-asset preflight before generation so CLI-driven runs can notice files already placed under `assets/`.
- `/gm-asset` now plans generated art as source, final, and curation artifacts so runs keep clearer asset handoff records.
- Reframed `rembg_matting.py` as an optional curation utility instead of a primary asset-generation path.
- `asset_sheet_process.py` can now extract the largest connected component from UI, icon, and prop sheets to avoid neighboring-cell fragments.
- `asset_sheet_process.py` can now autoslice separated source sheets before assigning candidates back to grid names.

## Fixed

- (WIP) Rewire Agent prompt/output trace capture to `PreToolUse`/`PostToolUse` because the `SubagentStart` payload has no `prompt` field and silently wrote 0-byte traces.

## Removed

- Removed the legacy `tools/asset_gen.py` helper in favor of the spec-driven asset source generator.
- Removed the legacy asset group report checker and standalone grid slicer from the active asset pipeline.
