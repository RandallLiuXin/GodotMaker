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

- v1 generated-asset stable entry and root index schema: `tools/asset_stable_entry.py` (per-asset `production_family` / `source_layout` / minimal `godot_artifact` / `processing_status` entry written to `.godotmaker/asset-generation/entries/<tag>/<asset_id>.json`) and `tools/asset_generation_index.py` (pointer-only root index). Old `runtime_artifact` schema fails closed and must be regenerated through `/gm-asset`; no migration or compatibility read is provided.
- Stable generated-asset output-path contract: deterministic `assets/generated/<production_family>/<asset_id>/` resolver (`tools/asset_output_path.py`), fail-closed stable-entry path validation, and a reusable `assert_within_output_dir` write guard.
- Added a standalone asset-skill invocation and result contract under `skills/assets/_shared/` with declarative JSON schemas, valid samples, a dependency-free checker, and fail-closed tests (#98).

## Changed

- `/gm-asset` now registers every generated asset as a v1 stable entry plus a pointer-only root index entry instead of a full-body `runtime_artifact` manifest.
- Generated runtime handoff for gm-build, gm-fixgap, worker dispatch, and ASSETS.md rows now resolves the stable entry behind each root-index pointer.
- An ASSETS.md row reaches `generated` only from a `ready` non-reference stable entry, so an unfinished or failed asset can no longer look complete to `/gm-build`.
- `asset_generation_index.py --check-files` verifies that every registered source and artifact still exists, catching an asset deleted after registration.

## Fixed

- Added the required `--grid` (and `--names`) argument to every production-unit `asset_sheet_process.py` example so the ui-kit, card-kit, compact-prop-pack, fx-bundle, scene-prop-set, and platform-strip commands run as written instead of failing on a missing required argument, and clarified that `--grid` is required in both autoslice and grid snap modes.
- Point generated-asset runtime handoff (gm-build, gm-fixgap, worker dispatch, worker agent) at `.godotmaker/asset-generation/manifest.json` instead of the analyst's `assets/manifest.json` (#97)

## Removed

- Retired the old `runtime_artifact` generated-asset manifest update, check, and entry-builder tools with no migration, dual-write, or compatibility read.
