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

- Added `tools/asset_family_registry.py` so every public Asset Skill request resolves to one authoritative output contract.

- `/gm-asset` can now plan, dispatch, and register the `tileset` production unit, so a validated `TileSet` reaches a worker as a tile library instead of stopping at the Skill.


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
- Added `tools/asset_atlas_assemble.py` for reproducible fixed-slot physical PNG atlases and region metadata; it rejects implicit packing, trimming, heuristic discovery, invalid bounds, overlap, size mismatches, and missing source PNGs.
- Direct generated-output path contract: deterministic `assets/generated/<asset_type>/<asset_id>/` paths and a reusable `assert_within_output_dir` write guard.
- Added a standalone asset-skill invocation and result contract under `skills/assets/_shared/` with declarative JSON schemas, valid samples, a dependency-free checker, and fail-closed tests (#98).
- Added standalone background-map, platform-strip, and screen-reference Asset Skills with typed runtime and reference-only result contracts.
- Added a shared Godot artifact compiler interface and registry under `skills/assets/_shared/` that routes on the frozen source-layout to artifact-type compatibility set, keeps compiler receipts out of the worker-facing artifact, requires each compiler to actually rebuild an artifact distinct from its source image, serves `Texture2D` through Godot's default import, and fails closed on unregistered or mismatched combinations (#107).
- Added shared direct-output validation under `skills/assets/_shared/` for processed sources, compiled artifacts, a real headless Godot import and `ResourceLoader.load` type match, and type-specific structure checks (#108).
- Added a deterministic `theme_recipe` compiler with a closed JSON schema for Theme colors, font sizes, constants, fonts, icons, StyleBoxes, and type variations; invalid class types, properties, resources, and StyleBox references fail closed before a loadable Theme is written.
- Added a Phantom Camera supporting skill for optional Godot camera addon guidance.

## Changed

- Generated assets now use `ASSETS.md` as the single runtime catalog: each
  logical asset row records its final Godot type and loadable path directly.
  Multi-output asset production registers all declared outputs atomically, and
  workers receive a minimal snapshot derived from those rows instead of a
  separate stable-entry or manifest layer.

- Every public asset route now proves its whole direct-registration chain in ordinary CI, so an advertised route cannot enter main without a validated `ASSETS.md` output.

- A Skill that accepts more than one request shape now declares one registration chain per shape, so a variant whose adapter is missing can no longer hide behind a sibling variant that works.

- Both `platform-strip` strip kinds now have complete registration contracts that turn validated segment deliveries into worker-consumable `ASSETS.md` rows.

- A ui-kit or card-kit now registers every declared runtime output atomically, so its `Theme`, every `StyleBoxTexture`, and every `AtlasTexture` are separately resolvable.
- Multi-output ui-kit, card-kit, and compact-prop-pack deliveries now declare
  every worker-consumable logical output in their request and register all
  matching `ASSETS.md` rows atomically.

- fx-bundle now registers its validated static `Texture2D` or animated
  `SpriteFrames` output directly from the request-selected result variant.

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

- `/gm-build` and `/gm-fixgap` now hand workers `ASSETS.md` runtime snapshots, and workers bind the compiled Godot resource rather than rebuilding it from the source layout.
- A worker may now edit or replace the bound runtime artifact and the project-local scene or script that binds it to fix a concrete integration failure, as a narrow file-ownership exception that outranks the generic "no files outside Deliverables" restriction.
- `/gm-asset` registers each validated request/result output set directly in `ASSETS.md`.
- Generated runtime handoff for gm-build, gm-fixgap, and worker dispatch reads the matching `ASSETS.md` runtime rows.
- An `ASSETS.md` runtime row reaches `generated` only after direct validation and registration, while a finalized screen reference completes at `source_ready` without becoming a worker runtime artifact.
- Asset families without a native compiler and L0-L4 validation path stop at `source_ready`, while a fully validated scene-prop set may register its generated AtlasTexture runtime resources as `ready`.
- `godot_artifact` is written only by a native compiler, so a `grid_sheet` can no longer be published as a `Texture2D` standing in for its unbuilt `SpriteFrames`.
- Direct compiler validation checks each `source_layout.type` against its closed compatible Godot artifact-type set, including `StyleBoxTexture` for `single` and `region_atlas`, so mismatches are rejected before reaching a worker.

## Fixed

- Ensure `/gm-asset` records an asset-stage completion event when its resume check finds no current-tag work.

- A validated background-map registers its `single -> Texture2D` result directly in `ASSETS.md`; registration binds to the image bytes its validation run recorded, so regenerating onto the same output path fails closed.

- An asset production unit now ends the asset stage with one consistent status, so a retried report no longer reads as a failure and a partial result keeps its blockers instead of being recorded as unknown.

- Replaced legacy magenta edge cleanup with PyMatting using a fixed validated trimap.

- Compact prop packs now generate one provider-authored source sheet, normalize each curated prop into its declared atlas slot, and publish independently addressable AtlasTexture resources with repaired L0-L4 validation.

- FX bundle production now separates static autoslice and animated grid paths, preserves provider reference claims, and promotes runtime entries only after L0-L4 validation.
- Card-kit Asset Skills now compile only the Theme, scalable frames, and fixed AtlasTexture regions requested by each asset request, preserving reusable Godot resources without requiring a fixed card layout.

- Character-bundle registers its validated SpriteFrames output directly in the
  matching `ASSETS.md` row; canonical and action sources remain reference
  provenance rather than extra runtime assets.
- Character-bundle validation binds the resolved request, action reports,
  frames, and compiled artifact so a stale result cannot register a later
  regeneration that reused the same output paths.
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
- Reference-only rows are `source_ready`; they never enter a runtime worker snapshot.
- Compiler staging now preserves Godot resource extensions.
- Compiler receipts are now issued only after atomic artifact commits.
- Direct registration requires successful compiler and validation evidence for
  each runtime output before any `ASSETS.md` row changes.
- Theme recipes now accept only fully decoded raster textures and FreeType-loadable TTF/OTF fonts, rejecting truncated or unsupported resource content before a Theme is written.
- Failed native Godot artifact compilation now retains the previous stable artifact and atomically commits a validated replacement only after success.
- Restored `asset_sheet_process.py --snap-mode autoslice` to independent Godot-style region extraction without grid bucketing or cross-region unions; fixed-grid extraction continues to require `--grid`.
- Point generated-asset runtime handoff (gm-build, gm-fixgap, worker dispatch,
  worker agent) at `ASSETS.md` and its deterministic `--snapshot` output (#97).

## Removed

- Removed the last two `gm-asset` production-unit documents, so every asset family now has exactly one authoritative execution contract in its first-class Asset Skill.
- Retired the old `runtime_artifact` generated-asset manifest update, check, and entry-builder tools with no migration, dual-write, or compatibility read.
