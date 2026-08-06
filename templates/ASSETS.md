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

Initial visual seed text lives in `STYLE.md`. Generated scene references,
character-bundle identity anchors, and manifest source relationships are the
primary style anchors after they exist.

## Gameplay Actor Asset Rows

For current-tag gameplay actors:

1. Add one runtime row for the actor's final `character-bundle`
   `SpriteFrames` output (for example, `player_animation_runtime`). The row
   name must exactly match the character-bundle request's `asset_id` and
   runtime output name so direct registration can complete it.
2. Keep canonical images, action sheets, source grids, and curation details in
   the character-bundle request, result, and reports. They are provenance and
   production evidence, not Asset Table rows.
3. Add portrait rows when a current-tag character appears in a
   large UI display slot.
   Portrait rows use the supported `background-map` family and its runtime
   path convention.
4. Bind gameplay runtime rows and UI display rows separately in the Visual
   Asset Contract.
5. Set character-bundle action names from current-tag gameplay behavior and
   artifact mappings.
6. Use static single-image rows only for explicitly static, non-gameplay,
   UI-only, locked-preview, statue, or abstract-token roles.

## Asset Table

<!-- Master manifest of all visual assets across all tags. Each row's
     `Tag` is the tag that introduced the asset. A row is one logical asset.
     Runtime Type and Runtime Path are the sole worker handoff: they must name
     the final loadable Godot resource, never a source sheet, atlas, candidate,
     report, or manifest pointer. Reference-only rows use Runtime Type
     `reference`, complete as `source_ready`, and never enter a runtime snapshot.
     Runtime-family source and reference outputs remain result evidence, not
     additional rows. -->

| # | Tag | Name | Type | Size | Generation Params | Runtime Type | Runtime Path | Status |
|---|-----|------|------|------|-------------------|--------------|--------------|--------|
| 1 | v0.1.0 | player_animation_runtime | animation | frame output | family=character-bundle; actions=from_current_tag_behavior | SpriteFrames | res://assets/generated/character-bundle/player_animation_runtime/player_animation_runtime.tres | MISSING |
| 2 | v0.1.0 | player_portrait | portrait | 256x256 px | family=background-map; role=player; source=character-bundle identity anchor | Texture2D | res://assets/generated/background-map/player_portrait/player_portrait.png | MISSING |
| 3 | v0.1.0 | action_button | ui | 96x48 px | family=ui-kit; component=button | Theme | res://assets/generated/ui-kit/action_button/action_button.tres | MISSING |
| 4 | v0.1.0 | background_sky | background | 1280x720 | family=background-map | Texture2D | res://assets/generated/background-map/background_sky/background_sky.png | MISSING |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

## Visual Asset Contract

<!-- Runtime contract for visible assets. Each gameplay-visible object, non-text
     UI element, and scene reference should map to an ASSETS.md row or to
     `procedural`, `UI text`, or `not required this tag`.
     Use `asset_name / assets/...` for concrete asset bindings.
     `Runtime Size` uses concrete px, `% viewport height`, or both.
     Gameplay actors use both `% viewport height` and target px.
     `not required this tag` needs a deferral reason in Readability Requirement. -->

| Tag | Scene / Mechanic | Visible Object | Asset Row / Path | Runtime Size | Visual Role | Readability Requirement | Source |
|-----|------------------|----------------|------------------|--------------|-------------|-------------------------|--------|
| v0.1.0 | Gameplay / [v0.1.0-M1] | player character | player_animation_runtime / assets/generated/character-bundle/player_animation_runtime/player_animation_runtime.tres | 8% viewport height / 58px tall at 1280x720 | controllable player | readable silhouette and current-tag actions visible in frame sequences | derived from character-bundle identity anchor |
| v0.1.0 | Character Select | player portrait | player_portrait / assets/generated/background-map/player_portrait/player_portrait.png | 140x140 px card slot | selectable character identity | readable in UI slots larger than gameplay runtime frames | derived from character-bundle identity anchor |
| v0.1.0 | Main Menu | title text | UI text | viewport-relative | menu identity | readable at target resolution | procedural/UI |
| v0.1.0 | HUD / [v0.1.0-M1] | action button | action_button / assets/generated/ui-kit/action_button/action_button.tres | 96x48 px target | HUD control | readable touch target at target resolution | derived from UI component sheet |

## 2D Animation Sources

<!-- Source sheets and selected runtime outputs for animated 2D assets. -->

### player_animation_runtime (tag: v0.1.0)
- **Family:** character-bundle
- **Output:** assets/generated/character-bundle/player_animation_runtime/player_animation_runtime.tres
- **Identity anchor:** retained in character-bundle result evidence
- **Actions:** current-tag player behavior
- **Frames:** per action metadata
- **FPS:** 8
- **Loop:** per action metadata
- **Curation report:** .godotmaker/asset-generation/curation/player_actions.json
- **Selected candidate:** accepted character action sheet
- **Curation state:** ready

### {animation_runtime_name} (tag: vX.Y.Z)
- **Family:** character-bundle
- **Output:** ...
- **Identity anchor:** ...
- **Actions:** ...
- **Frames:** ...
- **FPS:** ...
- **Loop:** ...
- **Curation report:** ...
- **Selected candidate:** ...
- **Curation state:** ...

## Visual Curation Records

<!-- Source sheets, extraction atlases, selected candidates, variants, and
     rejected candidates. Keep detailed JSON under
     .godotmaker/asset-generation/curation/. -->

### ui_kit_source (tag: v0.1.0)
- **Source:** .godotmaker/asset-generation/sources/ui_kit_source.png
- **Report:** .godotmaker/asset-generation/curation/ui_kit_source.json
- **Status:** needs_curation
- **Selected:** action_button -> assets/generated/ui-kit/action_button/action_button.png
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

- {source_sheet} (v0.1.0): select usable frames or components
- {source_sheet} (v0.1.0): select final runtime sprites and update the asset table
