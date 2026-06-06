# Assets: {Project Name}

<!-- Cross-tag accumulating asset manifest. Assets are reusable across
     tags — an explosion sprite added in v0.1.0 may still be used in
     v0.5.0, so this file is not split per tag. The `Tag` column on
     every row marks which tag introduced the asset (use the earliest
     tag that needed it; later tweaks keep the original tag).

     /gm-gdd initial mode writes the skeleton.
     /gm-asset every tag appends rows for that tag's new assets and
     refines paths/status; it does not rewrite existing rows. -->

## Visual Style Source

Visual prompt language lives in `STYLE.md`.

## Asset Table

<!-- Master manifest of all visual assets across all tags. Each row's
     `Tag` is the tag that introduced the asset. -->

| # | Tag | Name | Type | Size | Generation Params | File Path | Status |
|---|-----|------|------|------|-------------------|-----------|--------|
| 1 | v0.1.0 | player_canonical | character_canonical | 1K source | family=character_canonical; shape=single_image; prompt=.godotmaker/asset-generation/prompts/player_canonical.txt | .godotmaker/asset-generation/sources/player_canonical_source.png | MISSING |
| 2 | v0.1.0 | player_idle_source | character_action_source | 4 frames | family=character_action_source; shape=action_sheet; derived_from=player_canonical; status=needs_curation | .godotmaker/asset-generation/sources/player_idle_source.png | MISSING |
| 3 | v0.1.0 | player_idle | sprite | 64x64 px | family=runtime_sprite; derived_from=player_idle_source | assets/sprites/player_idle.png | MISSING |
| 4 | v0.1.0 | hud_buttons_source | ui_component_sheet | 2x3 components | family=ui_component_sheet; shape=grid_sheet; status=needs_curation | .godotmaker/asset-generation/sources/hud_buttons_source.png | MISSING |
| 5 | v0.1.0 | background_sky | background | 1280x720 | family=background; shape=single_image; prompt=.godotmaker/asset-generation/prompts/background_sky.txt | assets/backgrounds/sky.png | MISSING |
| ... | ... | ... | ... | ... | ... | ... | ... |

## Asset Production Manifest

<!-- /gm-asset records generated source images, final runtime assets, prompt
     paths, family, production shape, curation status, and lineage in:

     .godotmaker/asset-generation/manifest.json

     Use this manifest to track generated sources, selected final assets,
     prompts, curation status, and lineage.
     Do not hand-edit it unless you are repairing an asset-generation run. -->

## Visual Asset Contract

<!-- Runtime contract for visible assets. Each gameplay-visible object, non-text
     UI element, and scene reference should map to an ASSETS.md row or to
     `procedural`, `UI text`, or `not required this tag`.
     Use `asset_name / assets/...` for concrete asset bindings.
     `not required this tag` needs a deferral reason in Readability Requirement. -->

| Tag | Scene / Mechanic | Visible Object | Asset Row / Path | Runtime Size | Visual Role | Readability Requirement | Source |
|-----|------------------|----------------|------------------|--------------|-------------|-------------------------|--------|
| v0.1.0 | Gameplay / [v0.1.0-M1] | player character | player_idle / assets/sprites/player_idle.png | 64x64 px on screen | controllable player | readable silhouette against gameplay background | derived from player_canonical |
| v0.1.0 | Gameplay / [v0.1.0-M2] | enemy_basic | enemy_basic / assets/sprites/enemy_basic.png | 64x64 px on screen | enemy pressure | readable in normal gameplay captures | canonical |
| v0.1.0 | Main Menu | title text | UI text | viewport-relative | menu identity | readable at target resolution | procedural/UI |
| v0.1.0 | HUD / [v0.1.0-M1] | action button | hud_buttons_source / .godotmaker/asset-generation/sources/hud_buttons_source.png | 96x48 px target | HUD control | final button sprite must be selected before build uses it | needs curation |

## 2D Animation Sources

<!-- Source sheets and selected runtime outputs for animated 2D assets. -->

### player_idle_source (tag: v0.1.0)
- **Family:** character_action_source
- **Source:** .godotmaker/asset-generation/sources/player_idle_source.png
- **Derived from:** player_canonical
- **Action:** idle
- **Frames:** 4
- **FPS:** 8
- **Loop:** true
- **Processing status:** needs_curation
- **Final asset:** assets/sprites/player_idle.png

### {action_source_name} (tag: vX.Y.Z)
- **Family:** character_action_source
- **Source:** ...
- **Derived from:** ...
- **Action:** ...
- **Frames:** ...
- **FPS:** ...
- **Loop:** ...
- **Processing status:** ...
- **Final asset:** ...

## Audio

<!-- Sound effects and music. -->

| # | Tag | Name | Type | Duration | File Path | Status |
|---|-----|------|------|----------|-----------|--------|
| 1 | v0.1.0 | jump_sfx | sfx | 0.3s | assets/audio/jump.wav | MISSING |
| 2 | v0.1.0 | bgm_main | music | loop | assets/audio/bgm_main.ogg | MISSING |
| ... | ... | ... | ... | ... | ... | ... |

## Budget Tracking

<!-- Track generation costs if using paid APIs. Per-asset rows; the
     totals row sums everything across all tags. -->

| Asset | Tag | Tool | Cost | Notes |
|-------|-----|------|------|-------|
| player_idle | v0.1.0 | {image gen API} | $0.00 | |
| **Total** | — | | **$0.00** | |

## Post-Processing Notes

<!-- Any manual steps needed after generation. -->

- {asset} (v0.1.0): needs background removal (rembg)
- {source_sheet} (v0.1.0): select usable frames or components
- {source_sheet} (v0.1.0): select final runtime sprites and update `.godotmaker/asset-generation/manifest.json`
