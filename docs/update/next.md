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

- Added a recipe-only native TileSet atlas compiler with declared tile semantics and L4 source, tile, alternative, layer, and tile-size verification.
- Added a deterministic SpriteFrames compiler that aggregates explicitly timed normalized action PNGs, rejects missing required actions, and serializes independent frame texture bindings for character bundles and animated FX.
- Added a deterministic StyleBoxTexture compiler for reusable UI borders, with explicit texture regions, nine-slice borders, expand margins, and stretch axes verified through headless Godot.
- Published first-class Asset Skills for Claude Code, Codex, and OpenCode together with their project-local shared compiler, validator, and schema runtime under `.godotmaker/asset-runtime/`.
- Added a fail-closed `asset_runtime_resolver.py` that converts a registered ASSETS.md `manifest_entry` into the minimal ready worker runtime snapshot (#106).
- Added `tools/asset_atlas_assemble.py` for reproducible fixed-slot physical PNG atlases and region metadata; it rejects implicit packing, trimming, heuristic discovery, invalid bounds, overlap, size mismatches, and missing source PNGs.
- v1 generated-asset stable entry and root index schema: `tools/asset_stable_entry.py` (per-asset `production_family` / `source_layout` / minimal `godot_artifact` / `processing_status` entry written to `.godotmaker/asset-generation/entries/<tag>/<asset_id>.json`) and `tools/asset_generation_index.py` (pointer-only root index). Old `runtime_artifact` schema fails closed and must be regenerated through `/gm-asset`; no migration or compatibility read is provided.
- Stable generated-asset output-path contract: deterministic `assets/generated/<production_family>/<asset_id>/` resolver (`tools/asset_output_path.py`), fail-closed stable-entry path validation, and a reusable `assert_within_output_dir` write guard.
- Added a standalone asset-skill invocation and result contract under `skills/assets/_shared/` with declarative JSON schemas, valid samples, a dependency-free checker, and fail-closed tests (#98).
- Added `tools/asset_action_entry_draft.py`, which builds action support metadata and a v1 stable-entry draft while enforcing frame count, empty edge-touch frames, a recorded scale reference, and stable-path containment.
- Added `tools/asset_curation_entry_draft.py`, which builds a v1 stable-entry draft from a selected curation candidate while enforcing candidate selection, unambiguous naming, coherent selection counts, and stable-path containment.
- Added `tools/asset_finalize_entry_draft.py`, which builds a v1 stable-entry draft from an `asset_image_finalize.py` report for screen references, backgrounds, and single card or portrait frames while enforcing aspect validation, asset-label binding, and path containment.
- Added a shared Godot artifact compiler interface and registry under `skills/assets/_shared/` that routes on the frozen source-layout to artifact-type compatibility set, keeps compiler receipts out of the worker-facing artifact, requires each compiler to actually rebuild an artifact distinct from its source image, serves `Texture2D` through Godot's default import, and fails closed on unregistered or mismatched combinations (#107).
- Added the shared L0-L4 asset readiness ladder under `skills/assets/_shared/`, which reaches `ready` only after the stable entry contract, the processed source, the compiled artifact, a real headless Godot import and `ResourceLoader.load` type match, and a registered type-specific structure check all pass (#108).
- Added a deterministic `theme_recipe` compiler with a closed JSON schema for Theme colors, font sizes, constants, fonts, icons, StyleBoxes, and type variations; invalid class types, properties, resources, and StyleBox references fail closed before a loadable Theme is written.

## Changed

- Added deterministic fixed-slot `AtlasTexture` compilation from atlas metadata, with exact region and zero-margin validation through headless Godot.

- `/gm-asset` now registers every generated asset as a v1 stable entry plus a pointer-only root index entry instead of a full-body `runtime_artifact` manifest.
- Generated runtime handoff for gm-build, gm-fixgap, worker dispatch, and ASSETS.md rows now resolves the stable entry behind each root-index pointer.
- An ASSETS.md runtime row reaches `generated` only from a `ready` non-reference stable entry, while a finalized registered screen reference completes its reference row at `source_ready` without becoming a worker runtime artifact.
- `asset_generation_index.py --check-files` verifies that every registered source and artifact still exists, catching an asset deleted after registration.
- Generated runtime assets now stop at `source_ready`: the native compilers are not implemented and `/gm-asset` does not yet run the L0-L4 ladder, so it registers stable entries but produces no worker-consumable runtime asset and leaves generated runtime ASSETS.md rows `MISSING`.
- `godot_artifact` is written only by a native compiler, so a `grid_sheet` can no longer be published as a `Texture2D` standing in for its unbuilt `SpriteFrames`.
- The stable-entry schema now validates each `source_layout.type` against its closed compatible Godot artifact-type set, including `StyleBoxTexture` for `single` and `region_atlas`, so mismatches are rejected before reaching a worker.

## Fixed

- Reference-only stable entries now accept only `pending`, `source_ready`, or `failed`; only registered `source_ready` entries may promote ASSETS.md reference rows.
- Existing reference entries persisted as `compiled` or `ready` must be manually corrected to `source_ready` before root-index validation; no migration or compatibility reader is provided.
- Compiler staging now preserves Godot resource extensions.
- Compiler receipts are now issued only after atomic artifact commits.
- Asset readiness promotion now requires a compiler receipt bound to the compiled entry, while already-ready assets can explicitly revalidate without retaining that receipt.
- Theme recipes now accept only fully decoded raster textures and FreeType-loadable TTF/OTF fonts, rejecting truncated or unsupported resource content before a Theme is written.
- Failed native Godot artifact compilation now retains the previous stable artifact and atomically commits a validated replacement only after success.
- Added the required `--grid` (and `--names`) argument to every production-unit `asset_sheet_process.py` example so the ui-kit, card-kit, compact-prop-pack, fx-bundle, scene-prop-set, and platform-strip commands run as written instead of failing on a missing required argument, and clarified that `--grid` is required in both autoslice and grid snap modes.
- Point generated-asset runtime handoff (gm-build, gm-fixgap, worker dispatch, worker agent) at `.godotmaker/asset-generation/manifest.json` instead of the analyst's `assets/manifest.json` (#97)

## Removed

- Retired the old `runtime_artifact` generated-asset manifest update, check, and entry-builder tools with no migration, dual-write, or compatibility read.
