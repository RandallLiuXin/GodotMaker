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
| 1 | v0.1.0 | player_idle | sprite | 32x32 | {prompt or tool params} | assets/sprites/player_idle.png | pending |
| 2 | v0.1.0 | player_walk | spritesheet | 128x32 (4 frames) | {prompt or tool params} | assets/sprites/player_walk.png | pending |
| 3 | v0.1.0 | enemy_basic | sprite | 32x32 | {prompt or tool params} | assets/sprites/enemy_basic.png | pending |
| 4 | v0.1.0 | background_sky | background | 1280x720 | {prompt or tool params} | assets/backgrounds/sky.png | pending |
| ... | ... | ... | ... | ... | ... | ... | ... |

## Visual Asset Contract

<!-- Runtime contract for visible assets. Each gameplay-visible object, non-text
     UI element, and scene reference should map to an ASSETS.md row or to
     `procedural`, `UI text`, or `not required this tag`.
     Use `asset_name / assets/...` for concrete asset bindings.
     `not required this tag` needs a deferral reason in Readability Requirement. -->

| Tag | Scene / Mechanic | Visible Object | Asset Row / Path | Runtime Size | Visual Role | Readability Requirement | Source |
|-----|------------------|----------------|------------------|--------------|-------------|-------------------------|--------|
| v0.1.0 | Gameplay / [v0.1.0-M1] | player character | player_idle / assets/sprites/player_idle.png | 32x32 px on screen | controllable player | readable silhouette against gameplay background | anchor |
| v0.1.0 | Gameplay / [v0.1.0-M2] | enemy_basic | enemy_basic / assets/sprites/enemy_basic.png | 32x32 px on screen | enemy pressure | readable in normal gameplay captures | derivative of player/style anchor |
| v0.1.0 | Main Menu | title text | UI text | viewport-relative | menu identity | readable at target resolution | procedural/UI |

## Animated Sprites

<!-- Spritesheet breakdown for animated assets. -->

### player_walk (tag: v0.1.0)
- **File:** assets/sprites/player_walk.png
- **Frame size:** 32x32
- **Frames:** 4
- **FPS:** 8
- **Loop:** true
- **Directions:** {down, left, right, up} or {single}

### {animation_name} (tag: vX.Y.Z)
- **File:** ...
- **Frame size:** ...
- **Frames:** ...
- **FPS:** ...
- **Loop:** ...
- **Directions:** ...

## 3D Models

<!-- Only for 3D projects. Omit section for 2D. -->

| # | Tag | Name | Format | Poly Budget | Generation Tool | File Path | Status |
|---|-----|------|--------|-------------|-----------------|-----------|--------|
| 1 | v0.1.0 | player_model | .glb | ~2000 tris | {tripo3d / manual} | assets/models/player.glb | pending |
| ... | ... | ... | ... | ... | ... | ... | ... |

## Audio

<!-- Sound effects and music. -->

| # | Tag | Name | Type | Duration | File Path | Status |
|---|-----|------|------|----------|-----------|--------|
| 1 | v0.1.0 | jump_sfx | sfx | 0.3s | assets/audio/jump.wav | pending |
| 2 | v0.1.0 | bgm_main | music | loop | assets/audio/bgm_main.ogg | pending |
| ... | ... | ... | ... | ... | ... | ... |

## Budget Tracking

<!-- Track generation costs if using paid APIs. Per-asset rows; the
     totals row sums everything across all tags. -->

| Asset | Tag | Tool | Cost | Notes |
|-------|-----|------|------|-------|
| player_idle | v0.1.0 | {image gen API} | $0.00 | |
| player_model | v0.1.0 | tripo3d | $0.00 | |
| **Total** | — | | **$0.00** | |

## Post-Processing Notes

<!-- Any manual steps needed after generation. -->

- {asset} (v0.1.0): needs background removal (rembg)
- {spritesheet} (v0.1.0): needs grid slicing (grid_slice.py)
- {model} (v0.1.0): needs scale adjustment to match game units
