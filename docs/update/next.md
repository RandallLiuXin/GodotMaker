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

- `/gm-asset` can now plan, dispatch, and register the `tileset` production unit, so a validated `TileSet` reaches a worker as a tile library instead of stopping at the Skill.

- Added `tools/asset_ui_card_entry_draft.py` and `tools/asset_tileset_entry_draft.py`, the deterministic registration adapters for validated ui-kit/card-kit and tileset deliveries.

- Added `tools/asset_bundle_rows.py`, which declares the ASSETS.md row each bundle output will fill and closes the planned request row it serves as `N/A`.

- Added deterministic marching-squares-15 and blob-47 TileSet profile templates with fixed atlas guides, strict image validation, and native resource compilation.

- Added fail-closed standalone L0-L4 execution for the remaining first-class Asset Skills, with published runners and native Godot resource verification.

- Added a standalone TileSet Asset Skill with an explicit atlas and recipe contract, shared compiler and validation reuse, and an orthogonal-square fixture.
- Added standalone ui-kit and card-kit Asset Skills with closed request contracts and executable L0-L4 validation for Theme, StyleBoxTexture, and AtlasTexture resources.
- Added a recipe-only native TileSet atlas compiler with declared tile semantics and L4 source, tile, alternative, layer, and tile-size verification.
- Added standalone atlas-backed compact-prop-pack and scene-prop-set Skills with deterministic independent AtlasTexture outputs for each declared prop.
- Added a deterministic SpriteFrames compiler that aggregates explicitly timed normalized action PNGs, rejects missing required actions, and serializes independent frame texture bindings for character bundles and animated FX.
- Added standalone character-bundle and fx-bundle skills with fail-closed family validation for explicit animation timing, loop, frame order, and native Godot runtime-output contracts.
- Added fixed 15-cell and 47-cell TileSet profiles with typed requests, deterministic material composition, and optional terrain metadata hand-off.
- Added a deterministic StyleBoxTexture compiler for reusable UI borders, with explicit texture regions, nine-slice borders, expand margins, and stretch axes verified through headless Godot.
- Published first-class Asset Skills for Claude Code, Codex, and OpenCode together with their project-local shared compiler, validator, and schema runtime under `.godotmaker/asset-runtime/`.
- Added a fail-closed `asset_runtime_resolver.py` that converts a registered ASSETS.md `manifest_entry` into the minimal ready worker runtime snapshot (#106).
- Added `tools/asset_atlas_assemble.py` for reproducible fixed-slot physical PNG atlases and region metadata; it rejects implicit packing, trimming, heuristic discovery, invalid bounds, overlap, size mismatches, and missing source PNGs.
- v1 generated-asset stable entry and root index schema: `tools/asset_stable_entry.py` (per-asset `production_family` / `source_layout` / minimal `godot_artifact` / `processing_status` entry written to `.godotmaker/asset-generation/entries/<tag>/<asset_id>.json`) and `tools/asset_generation_index.py` (pointer-only root index). Old `runtime_artifact` schema fails closed and must be regenerated through `/gm-asset`; no migration or compatibility read is provided.
- Stable generated-asset output-path contract: deterministic `assets/generated/<production_family>/<asset_id>/` resolver (`tools/asset_output_path.py`), fail-closed stable-entry path validation, and a reusable `assert_within_output_dir` write guard.
- Added a standalone asset-skill invocation and result contract under `skills/assets/_shared/` with declarative JSON schemas, valid samples, a dependency-free checker, and fail-closed tests (#98).
- Added standalone background-map, platform-strip, and screen-reference Asset Skills with typed runtime and reference-only result contracts.
- Added `tools/asset_action_entry_draft.py`, which builds action support metadata and a v1 stable-entry draft while enforcing frame count, empty edge-touch frames, a recorded scale reference, and stable-path containment.
- Added `tools/asset_curation_entry_draft.py`, which builds a v1 stable-entry draft from a selected curation candidate while enforcing candidate selection, unambiguous naming, coherent selection counts, and stable-path containment.
- Added `tools/asset_finalize_entry_draft.py`, which builds a v1 stable-entry draft from an `asset_image_finalize.py` report for screen references, backgrounds, and single card or portrait frames while enforcing aspect validation, asset-label binding, and path containment.
- Added a shared Godot artifact compiler interface and registry under `skills/assets/_shared/` that routes on the frozen source-layout to artifact-type compatibility set, keeps compiler receipts out of the worker-facing artifact, requires each compiler to actually rebuild an artifact distinct from its source image, serves `Texture2D` through Godot's default import, and fails closed on unregistered or mismatched combinations (#107).
- Added the shared L0-L4 asset readiness ladder under `skills/assets/_shared/`, which reaches `ready` only after the stable entry contract, the processed source, the compiled artifact, a real headless Godot import and `ResourceLoader.load` type match, and a registered type-specific structure check all pass (#108).
- Added a deterministic `theme_recipe` compiler with a closed JSON schema for Theme colors, font sizes, constants, fonts, icons, StyleBoxes, and type variations; invalid class types, properties, resources, and StyleBox references fail closed before a loadable Theme is written.
- Added a Phantom Camera supporting skill for optional Godot camera addon guidance.

## Changed

- A ui-kit or card-kit now registers one ready stable entry per runtime output, so its `Theme`, every `StyleBoxTexture`, and every `AtlasTexture` are separately resolvable instead of unregisterable; `bundle_id` covers these two families alongside `compact-prop-pack`.

- An fx-bundle entry now reaches `ready` by re-running its own entry builder with the passing Skill result, under the same build-fingerprint rule character-bundle uses; static and animated FX previously had no promotion path at all and stopped at `compiled`.

- Workers now own TileMap layout, layers, cell and gameplay object placement, triggers, camera limits, and scene structure, binding a ready `TileSet` as a tile library and repairing what running the map actually shows.

- Reworked `ui-kit` around a flat-first Godot Theme: one fixed eight-patch
  surface atlas expands into reusable button, panel, popup, tooltip, and tab
  StyleBoxTextures, while native StyleBoxFlat/StyleBoxEmpty resources own form,
  progress, slider, scrollbar, focus, and separator treatment. A second sheet
  provides 24 unique icons mapped to 31 stable AtlasTexture runtime names.
- Normalized UI kit nine-slice patches and Theme-bound semantic icons to
  compact runtime sizes while retaining high-resolution reusable action icons.
- Added deterministic StyleBoxTexture modulation and L4 verification so shared
  button-state source patches can produce base, Primary, Secondary, and Danger
  Theme resources without duplicate provider art.
- Added deterministic fixed-slot `AtlasTexture` compilation from atlas metadata, with exact region and zero-margin validation through headless Godot.
- Fixed fixed-slot `AtlasTexture` compilation so multiple stable runtime output
  names can reuse one declared atlas region, and standalone UI validation now
  compiles icon resources before the Theme that binds them.

- `/gm-build` and `/gm-fixgap` now hand workers a resolver-produced minimal `godot_artifact` snapshot instead of hand-copied stable-entry fields, and workers bind the compiled Godot resource rather than rebuilding it from the source layout.
- A worker may now edit or replace the bound runtime artifact and the project-local scene or script that binds it to fix a concrete integration failure, as a narrow file-ownership exception that outranks the generic "no files outside Deliverables" restriction.
- `/gm-asset` now registers every generated asset as a v1 stable entry plus a pointer-only root index entry instead of a full-body `runtime_artifact` manifest.
- Generated runtime handoff for gm-build, gm-fixgap, worker dispatch, and ASSETS.md rows now resolves the stable entry behind each root-index pointer.
- An ASSETS.md runtime row reaches `generated` only from a `ready` non-reference stable entry, while a finalized registered screen reference completes its reference row at `source_ready` without becoming a worker runtime artifact.
- `asset_generation_index.py --check-files` verifies that every registered source and artifact still exists, catching an asset deleted after registration.
- Asset families without a native compiler and L0-L4 validation path stop at `source_ready`, while a fully validated scene-prop set may register its generated AtlasTexture runtime resources as `ready`.
- `godot_artifact` is written only by a native compiler, so a `grid_sheet` can no longer be published as a `Texture2D` standing in for its unbuilt `SpriteFrames`.
- The stable-entry schema now validates each `source_layout.type` against its closed compatible Godot artifact-type set, including `StyleBoxTexture` for `single` and `region_atlas`, so mismatches are rejected before reaching a worker.

## Fixed

- Compact prop packs now generate one provider-authored source sheet, normalize each curated prop into its declared atlas slot, and publish independently addressable AtlasTexture resources with repaired L0-L4 validation.

- FX bundle production now separates static autoslice and animated grid paths, preserves provider reference claims, and promotes runtime entries only after L0-L4 validation.
- Card-kit Asset Skills now compile only the Theme, scalable frames, and fixed AtlasTexture regions requested by each asset request, preserving reusable Godot resources without requiring a fixed card layout.

- Character-bundle stable entries now reach `ready` only after their L0-L4 evidence is handed back to the same deterministic builder, instead of being published straight from the compiler.
- Character-bundle promotion now binds to a build fingerprint of the resolved request, action reports, stable frames, and compiled artifact, so a passing result can no longer promote a later regeneration that reused the same stable paths.
- A character-bundle result now registers exactly one worker-consumable SpriteFrames entry, so a generated canonical is recorded as reference provenance and can no longer ship as a second runtime artifact.
- Character-bundle assets now resolve animation cadence internally, preserve optional canonical references and 256px runtime frames, and regenerate retryable source-image failures before stopping.
- Character-bundle assembly now binds resolved intent, canvas, frame order, timing, loop state, and scale references through SpriteFrames compilation and GIF previews.
- Fixed blob-47 TileSet masks, edge signatures, and isolated-terrain semantics to match Godot's eight peering points.
- Fixed TileSet profile validation to diagnose terrain-corner seam mismatches against the deterministic matching template before compilation.
- Fixed TileSet seam repairs to deterministically compose profile transitions from provider-authored terrain materials instead of accepting flat color patches.

- Fixed deterministic TileSet profiles to compile from published standalone runtimes and emit fixed atlas assembly declarations without agent-authored layout scripts.

- Pre-push checks now isolate temporary Git repositories from the invoking worktree's hook environment.
- Platform-strip assets now retain controlled provider-source claims and validator-produced readiness evidence.
- Platform-strip now requires a fixed cap/repeat/cap grid, slices source cells before per-cell finalization, and validates stable AtlasTexture regions against the real source sheet.
- Background-map now preserves optional reference-image provenance, uses the declared provider without fallback, and deterministically finalizes non-pixel-art Texture2D backgrounds.
- Theme L4 validation now rejects recipe paths outside the declaring asset's stable output directory.
- Published asset validation runners now work after installing GodotMaker into Claude Code, Codex, or OpenCode projects.
- Restored real Godot validation for Theme and TileSet assets, including safe Theme resource paths and imported TileSet atlases.
- Reference-only stable entries now accept only `pending`, `source_ready`, or `failed`; only registered `source_ready` entries may promote ASSETS.md reference rows.
- Existing reference entries persisted as `compiled` or `ready` must be manually corrected to `source_ready` before root-index validation; no migration or compatibility reader is provided.
- Compiler staging now preserves Godot resource extensions.
- Compiler receipts are now issued only after atomic artifact commits.
- Asset readiness promotion now requires a compiler receipt bound to the compiled entry, while already-ready assets can explicitly revalidate without retaining that receipt.
- Theme recipes now accept only fully decoded raster textures and FreeType-loadable TTF/OTF fonts, rejecting truncated or unsupported resource content before a Theme is written.
- Failed native Godot artifact compilation now retains the previous stable artifact and atomically commits a validated replacement only after success.
- Restored `asset_sheet_process.py --snap-mode autoslice` to independent Godot-style region extraction without grid bucketing or cross-region unions; fixed-grid extraction continues to require `--grid`.
- Point generated-asset runtime handoff (gm-build, gm-fixgap, worker dispatch, worker agent) at `.godotmaker/asset-generation/manifest.json` instead of the analyst's `assets/manifest.json` (#97)

## Removed

- Removed the last two `gm-asset` production-unit documents, so every asset family now has exactly one authoritative execution contract in its first-class Asset Skill.
- Retired the old `runtime_artifact` generated-asset manifest update, check, and entry-builder tools with no migration, dual-write, or compatibility read.
