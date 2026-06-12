# Asset Planning Reference

Use this file when `/gm-asset` builds current-tag production units before
dispatching `asset-producer`.

## Inputs

Read:

1. `ASSETS.md`
2. `PLAN.md`
3. `STYLE.md` seed
4. `STRUCTURE.md`
5. `SCENES.md`
6. `references/scene_*.png` summaries from analyst reports
7. `references/asset-runtime-pipeline.md`

Do not read image binaries in the manager context.

## Planning Steps

1. Read the current tag from `PLAN.md`.
2. Filter `ASSETS.md` to current-tag `MISSING` rows.
3. Add missing current-tag scene references from `SCENES.md`.
4. Identify current-tag visual anchors.
5. Apply the Visual Anchor Gate.
6. Group generated visual work into production units.
7. Choose one production-unit doc for each unit.
8. Choose one provider doc for each unit.
9. Reserve source, final, prompt, report, and manifest-entry paths.
10. Record dependencies between units.
11. Dispatch independent units in batches of up to 3.
12. Keep bundle work in one production unit.

## Visual Anchor Gate

Current-tag visual anchors are:

1. User-provided image assets accepted as `direct_runtime`.
2. Current-tag `references/scene_*.png` files with matching reports.
3. Current-tag generated `screen-reference` or `style_reference` manifest
   entries whose files exist.
4. Current-tag canonical character or UI reference images whose manifest entries
   are `ready`.

When no visual anchor exists:

1. Plan only one foundation `screen-reference` production unit.
2. Use the primary current-tag scene from `SCENES.md`.
3. Do not dispatch `background-map`, `character-bundle`, `fx-bundle`,
   `ui-kit`, `card-kit`, `compact-prop-pack`, `platform-strip`, or
   `scene-prop-set`.
4. Collect the foundation reference report.
5. Rebuild the production plan.

When at least one visual anchor exists:

1. Put visible anchor paths in every production-unit brief.
2. Dispatch independent units in batches of up to 3.

## Production Unit Selection

Choose the first matching unit.

| Unit | Use when | Do not use for |
| --- | --- | --- |
| `screen-reference` | Missing `references/scene_*.png`, style anchor, or evaluation visual target. | Runtime backgrounds, map bases, parallax plates, final props, or playable scene objects. |
| `character-bundle` | Player, enemy, NPC, summon, boss, character portrait, character bust, character card display image, or recurring creature identity. | Detached projectiles, impact bursts, UI pieces, props, or terrain. |
| `fx-bundle` | Projectile, impact, pickup effect, slash, muzzle, aura, explosion, detached effect sequence, or foreground gameplay sprite with effect behavior. | Character body animation, UI icons, props, or map scenery. |
| `ui-kit` | Buttons, panels, tabs, counters, HUD pieces, map markers, cursors, icons, progress bars, and scalable UI pieces that share one interface style. | Full composite screens, readable text, logos, fonts, card frames, portrait frames, scene backgrounds, or runtime props. |
| `card-kit` | Card frames, portrait frames, rarity frames, card slots, deck slots, card markers, and card-game-specific UI pieces. | Generic HUD controls, character portraits, full composite screens, readable text, logos, fonts, scene backgrounds, or runtime props. |
| `compact-prop-pack` | Small props, collectable pickups, crates, stones, bushes, pots, debris, lamps, and signs that can share one source sheet. | Wide, tall, collision-bearing, platform, floor, bridge, wall, ladder, gate, door, terrain, or tileset assets. |
| `background-map` | Runtime background, map base, parallax plate, fixed battle background, title/splash illustration, or fixed-viewport scenic asset. | Scene references, extracted props, character actors, UI kits, or collision-bearing strips. |
| `platform-strip` | Floors, bridges, platforms, rails, pipes, long hazards, terrain chunks, and collision-aligned horizontal pieces. | Compact props, characters, FX, UI pieces, or full backgrounds. |
| `scene-prop-set` | Final runtime foreground objects derived from a scene, map, or stage reference. | Generic prop packs without a scene reference, backgrounds, UI, characters, FX, or uncut single-image foreground sprites. |

Default font, logo, and wordmark rows to `provided` or `deferred` unless the
user explicitly requested generated image assets.

## Production Unit Entry Points

| Unit | First entry document |
| --- | --- |
| `screen-reference` | `references/production-units/screen-reference.md` |
| `character-bundle` | `references/production-units/character-bundle.md` |
| `fx-bundle` | `references/production-units/fx-bundle.md` |
| `ui-kit` | `references/production-units/ui-kit.md` |
| `card-kit` | `references/production-units/card-kit.md` |
| `compact-prop-pack` | `references/production-units/compact-prop-pack.md` |
| `background-map` | `references/production-units/background-map.md` |
| `platform-strip` | `references/production-units/platform-strip.md` |
| `scene-prop-set` | `references/production-units/scene-prop-set.md` |

## ASSETS Family Routing

| Family | Production unit |
|--------|-----------------|
| `screen_reference` | `screen-reference` |
| `style_reference` | `screen-reference` |
| `character_canonical` | `character-bundle` |
| `character_portrait` | `character-bundle` |
| `character_action_source` | `character-bundle` |
| `character_frame_output` | `character-bundle` |
| `projectile_fx_source` | `fx-bundle` |
| `impact_fx_source` | `fx-bundle` |
| `compact_prop_pack` | `compact-prop-pack` |
| `ui_component_sheet` | `ui-kit` |
| `icon_pack` | `ui-kit` |
| `panel_source` | `ui-kit` |
| `card_component_sheet` | `card-kit` |
| `card_frame_source` | `card-kit` |
| `portrait_frame_source` | `card-kit` |
| `background` | `background-map` |
| `platform_strip` | `platform-strip` |
| `scene_prop_set` | `scene-prop-set` |
| `runtime_sprite` | `compact-prop-pack` |
| `texture` | `background-map` |
| `audio` | no generated production unit |

## Plan Artifact Fields

Record these fields for each generated visual production unit:

1. `unit_id`
2. `unit_doc`
3. `provider`
4. `input_rows`
5. `dependencies`
6. `source_paths`
7. `final_paths`
8. `prompt_paths`
9. `report_path`
10. `manifest_entry_paths`
11. `runtime_artifacts`
12. `metadata_paths`

## Dependency Order

Use this order when units depend on each other:

1. `screen-reference` and style anchors.
2. `background-map`.
3. `character-bundle` canonicals, `ui-kit`, and `card-kit` source sheets.
4. `character-bundle` actions, `fx-bundle`, `compact-prop-pack`,
   `platform-strip`, and `scene-prop-set`.
5. Curation and manifest update.

## Batch Rules

1. Run independent production units in batches of up to 3.
2. Keep one production unit inside one asset-producer brief.
3. Do not split a character bundle across unrelated producers.
4. Do not merge unrelated production units into one brief.
5. Record sequential fallback in the unit report when needed.

## ASSETS.md Updates

Update current-tag rows after producer reports:

1. `generated`: final runtime asset exists and manifest validation passed.
2. `provided`: user-provided file matched the row.
3. `deferred`: unprovided audio or intentionally skipped asset.
4. `MISSING`: source exists but final runtime asset or curation is incomplete.

Update `Generation Params` with:

1. manifest entry pointer

Do not duplicate prompt paths, source paths, runtime artifact, metadata paths,
or curation reports in `ASSETS.md`.

Update the Visual Asset Contract for gameplay-visible final assets.
