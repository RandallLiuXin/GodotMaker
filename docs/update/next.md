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
- Added magenta-background cleanup to `asset_image_finalize.py` for single-image generated assets.
- Added an ASSETS.md update helper so generated-art runs can update rows after each completed production unit.
- Added source-aspect validation to `asset_image_finalize.py` so generated scene references and fixed-viewport backgrounds can fail before resize when the source image has the wrong orientation.
- Added batch mode to the Codex image claim helper so `/gm-asset` can claim only planned image outputs.
- Added authoritative Codex image claim reports for generated-art provider runs.
- Added validation for asset-generation handoff manifests so generated-art runs can detect missing fields and files.
- Added a manifest update helper so generated-art runs can upsert handoff entries through a validated tool.
- Added a layout-guide helper for fixed-grid UI, prop, icon, and action source generation.
- Added a character action processor that turns raw action sheets into normalized frames, transparent sheets, GIF previews, and pipeline metadata.
- Added a character action manifest-entry helper so processed action metadata can produce validated frame-output handoff entries.
- Added a 2D source-sheet processor so generated grids can produce cropped assets and processing reports.
- Added magenta-background and edge-fringe processing support to the 2D source-sheet processor for production-shaped extraction sheets.
- Added action-sheet edge-touch recovery that archives the previous source and repacks autosliced frames into the active source path.
- Added an asset-producer subagent and production-unit entry docs for generated visual asset work.
- Added separate native, Codex, and Gemini image-provider docs for `/gm-asset`.
- Added a first-pass asset curation contract for generated source sheets, canonical selections, and rejected candidates.
- Added a curation selection helper so accepted candidates can be finalized into runtime asset paths.
- Added a curation manifest-entry helper so selected source-sheet candidates can produce validated runtime handoff entries.
- Split the asset generation reference into runtime pipeline and prompt-contract references.
- Added character animation asset contracts for canonical sources, per-action source sheets, processed frame outputs, action processing metadata, and final runtime handoff validation.
- Added a dedicated card-kit production unit so card frames, portrait frames, rarity frames, card slots, and card-game UI assets no longer share the generic UI component path.
- Added runtime asset handoff rules so build and fixgap stages pass generated final assets and metadata to workers while evaluate checks screenshots against scene contracts.

## Changed

- Clarified README preview-feature scope and roadmap priorities for art production, Codex runner fallback, 3D support, and audio generation.
- `/gm-asset` now runs a lightweight user-asset preflight before generation so CLI-driven runs can notice files already placed under `assets/`.
- `/gm-asset` now plans generated art as source, final, and curation artifacts so runs keep clearer asset handoff records.
- `/gm-asset` now acts as an asset-stage manager that dispatches generated visual production units instead of producing raw art in the manager context.
- `asset_sheet_process.py` can now extract the largest connected component from UI, icon, and prop sheets to avoid neighboring-cell fragments.
- `asset_sheet_process.py` can now autoslice separated source sheets before assigning candidates back to grid names.
- `/gm-asset` now routes visual source planning through asset-family pipelines so UI, icon, and prop sheets default to autoslice curation instead of fixed-grid slicing.
- Asset-generation manifests now allow multiple runtime assets to share one source sheet and prompt.
- `/gm-asset` now plans important character and enemy art as canonical references plus one action source per body action, with detached FX generated separately.
- `asset_action_process.py` now exposes a smaller CLI surface built around `body` and `fx` action kinds, rejects edge-touch frames by default, and records body-scale reference checks.
- Worker visual briefs now require final runtime asset paths from ASSETS.md or the manifest and prohibit replacing available assets with placeholders.
- `/gm-asset` now creates a foundation screen reference before parallel visual production when a tag has no visual anchor.
- `/gm-asset` now reads `asset_producer_model` from project config so asset production subagents can run on Sonnet by default.
- `/gm-asset` now keeps ASSETS.md generation params as manifest pointers while storing atlas and animation details in runtime metadata JSON files.
- Claude Code orchestration now starts Codex asset-image subprocesses with full unattended permissions for generated-path reporting.
- `/gm-asset` now treats exhausted image-provider failures as asset-production failures instead of allowing placeholder sources to be marked generated.
- Scaffold and planning now default to 2D project structure instead of asking for unsupported project dimensions.
- Character planning now requires gameplay actors to include character art and action-source assets instead of static-only sprite rows.
- Character UI display assets now use dedicated portrait rows instead of reusing small gameplay runtime sprites.
- GDD display specs now determine pixel/non-pixel mode and target viewport while scaffold keeps a neutral 2D default.
- GDD and asset planning now record gameplay actor screen presence so generated character art is sized for runtime display.
- Evaluate and fixgap now separate E2E test-interface requests from normal gameplay changes.
- Game planning now keeps TileMap terrain deferred and uses sprite-based placement for current playable units.

## Fixed

- (WIP) Rewire Agent prompt/output trace capture to `PreToolUse`/`PostToolUse` because the `SubagentStart` payload has no `prompt` field and silently wrote 0-byte traces.
- Clarified `/gm-asset` asset-producer provider handoff rules.
- `/gm-asset` now commits asset-stage outputs before completion so the clean-workspace stop hook can advance to `/gm-build`.
- Made `asset_action_process.py` write runtime action frames with the final prefix so different characters cannot overwrite shared names like `idle_0.png`.
- `/gm-asset` now requires runtime-ready foreground artifacts for UI, icon, prop, projectile, pickup, and scene-object assets, with atlas or animation metadata when the final output is a sheet.

## Removed

- Removed the legacy `tools/asset_gen.py` helper in favor of the spec-driven asset source generator.
- Removed the legacy asset group report checker and standalone grid slicer from the active asset pipeline.
- Removed stale gm-asset reference pages for scene visual targets and rembg-specific guidance.
- Removed unused rembg and loop-frame helpers from the active toolchain, which also removes the heavy rembg / onnxruntime dependency chain from default tool installation.
