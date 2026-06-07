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
| 1 | v0.1.0 | player_idle | sprite | 64x64 px | family=runtime_sprite; derived_from=player_canonical | assets/sprites/player_idle.png | MISSING |
| 2 | v0.1.0 | player_run | sprite_sheet | 6 frames | family=character_action_source; action=run; derived_from=player_canonical; curation=.godotmaker/asset-generation/curation/player_run.json | assets/sprites/player_run.png | MISSING |
| 3 | v0.1.0 | enemy_basic | sprite | 64x64 px | family=runtime_sprite; derived_from=enemy_canonical | assets/sprites/enemy_basic.png | MISSING |
| 4 | v0.1.0 | action_button | ui | 96x48 px | family=ui_component_sheet; component=button; selected_candidate=ui_kit.action_button | assets/ui/action_button.png | MISSING |
| 5 | v0.1.0 | background_sky | background | 1280x720 | family=background; shape=single_image | assets/backgrounds/sky.png | MISSING |
| ... | ... | ... | ... | ... | ... | ... | ... |

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
| v0.1.0 | HUD / [v0.1.0-M1] | action button | action_button / assets/ui/action_button.png | 96x48 px target | HUD control | readable touch target at target resolution | derived from UI component sheet |

## 2D Animation Sources

<!-- Source sheets and selected runtime outputs for animated 2D assets. -->

### player_idle_source (tag: v0.1.0)
- **Family:** character_action_source
- **Output:** assets/sprites/player_idle.png
- **Derived from:** player_canonical
- **Action:** idle
- **Frames:** 4
- **FPS:** 8
- **Loop:** true
- **Curation report:** .godotmaker/asset-generation/curation/player_idle.json
- **Selected candidate:** player_idle.idle_loop
- **Processing status:** ready

### {action_source_name} (tag: vX.Y.Z)
- **Family:** character_action_source
- **Output:** ...
- **Derived from:** ...
- **Action:** ...
- **Frames:** ...
- **FPS:** ...
- **Loop:** ...
- **Curation report:** ...
- **Selected candidate:** ...
- **Processing status:** ...

## Visual Curation Records

<!-- Source sheets, extraction atlases, selected candidates, variants, and
     rejected candidates. Keep detailed JSON under
     .godotmaker/asset-generation/curation/. -->

### ui_kit_source (tag: v0.1.0)
- **Source:** .godotmaker/asset-generation/sources/ui_kit_source.png
- **Report:** .godotmaker/asset-generation/curation/ui_kit_source.json
- **Status:** needs_curation
- **Selected:** action_button -> assets/ui/action_button.png
- **Rejected:** empty_04 (empty_cell)

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
- {source_sheet} (v0.1.0): select final runtime sprites and update the asset table
