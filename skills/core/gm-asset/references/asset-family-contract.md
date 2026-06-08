# Asset Family Contract

Use this contract when planning generated visual assets. Classify the asset
before writing prompts or choosing output paths.

## Asset Families

| Family | Use for | Primary output |
|--------|---------|----------------|
| `screen_reference` | Full-scene visual target for build/evaluate | `references/scene_{name}.png` |
| `style_reference` | Style anchor that guides later generated assets | `.godotmaker/asset-generation/sources/...` |
| `character_canonical` | Neutral identity reference for a player, NPC, or enemy | source image plus final reference path |
| `character_action_source` | One character action such as idle, run, attack, hurt, death | source sheet or frame sequence |
| `character_frame_output` | Processed frames or delivery grid sheet from one action source | final sprite frames or grid sheet |
| `projectile_fx_source` | Projectile or travelling effect art | source sheet or final sprite |
| `impact_fx_source` | Hit, explosion, spawn, pickup, or impact effect | source sheet or final sprite |
| `compact_prop_pack` | Several compact props or pickups sharing one style | source sheet plus extracted final assets |
| `ui_component_sheet` | Buttons, icons, tabs, counters, badges, HUD pieces | source sheet plus extracted final assets |
| `icon_pack` | Small readable icons with one shared style | source sheet plus extracted final assets |
| `panel_source` | Large UI panel, card frame, dialogue box, or shop slot | source image or sliced final asset |
| `background` | Runtime background or parallax layer | final image |
| `runtime_sprite` | Single final sprite already suitable for gameplay | final image |
| `texture` | Tileable or repeated material | final image |
| `audio` | Sound or music | user-provided file |

## Production Shapes

| Shape | Use for | Required fields |
|-------|---------|-----------------|
| `single_image` | Backgrounds, panels, character canonicals, large props | `source_path`, `final_path` |
| `grid_sheet` | Compact props, icons, small UI components | `source_path`, `rows`, `cols`, `expected_items` |
| `action_sheet` | One character or enemy action | `source_path`, `action`, `frames`, `anchor` |
| `frame_sequence` | Extracted or generated animation frames | `source_path`, `frame_dir`, `fps`, `loop` |
| `delivery_sheet` | Runtime-ready grid sheet assembled from processed frames | `source_path`, `final_path`, `derived_from` |
| `reference_only` | Screen/style references | `source_path` or `final_path`, `contract_summary` |
| `curation_required` | Irregular sheets or references that need human/tool selection | `source_path`, `curation_reason` |

## Processing Status

Use one status per generated visual artifact:

1. `source_only`: generated source exists; no runtime asset has been accepted.
2. `needs_curation`: source exists; extraction, split, or selection is needed.
3. `processed`: source was processed or selected into final runtime assets.
4. `ready`: final asset is ready for project use.
5. `deferred`: asset is intentionally not produced in this tag.
6. `rejected`: generated source should not be used.

## Extraction Status

Use one extraction status per generated visual artifact:

1. `not_required`: no extraction step is needed.
2. `pending`: extraction has not run yet.
3. `source_sheet`: source sheet exists.
4. `extracted`: extraction created candidate outputs.
5. `processed`: final outputs are selected.
6. `needs_curation`: candidate outputs need selection or cleanup.
7. `rejected`: extraction output should not be used.

## Manifest Entry

Write or update `.godotmaker/asset-generation/manifest.json` with entries in
this shape:

```json
{
  "version": 1,
  "assets": [
    {
      "asset_id": "player_idle_delivery",
      "tag": "v0.1.0",
      "family": "character_frame_output",
      "production_shape": "delivery_sheet",
      "runtime_role": "player",
      "source_path": ".godotmaker/asset-generation/sources/player_idle_source.png",
      "final_path": "assets/sprites/player_idle_sheet.png",
      "target_size": null,
      "target_aspect": null,
      "derived_from": "player_idle",
      "canonical_reference": "player_canonical",
      "prompt_path": ".godotmaker/asset-generation/prompts/player_idle.txt",
      "processing_status": "ready",
      "extraction_status": "processed",
      "qc": {
        "action_processing": {
          "frame_count": 4,
          "frame_paths": [
            "assets/sprites/player_idle_01.png",
            "assets/sprites/player_idle_02.png",
            "assets/sprites/player_idle_03.png",
            "assets/sprites/player_idle_04.png"
          ],
          "align": "feet",
          "shared_scale": true,
          "sheet_path": "assets/sprites/player_idle_sheet.png",
          "gif_path": ".godotmaker/asset-generation/processed/player_idle/animation.gif",
          "metadata_path": ".godotmaker/asset-generation/processed/player_idle/pipeline-meta.json",
          "edge_touch_frames": [],
          "scale_reference": {
            "checked": false
          }
        }
      },
      "curation": {
        "status": "selected",
        "strategy": "solid_background_grid",
        "report_path": ".godotmaker/asset-generation/processed/player_idle/curation-report.json",
        "selected_count": 4,
        "rejected_count": 0
      },
      "preview_path": ".godotmaker/asset-generation/processed/player_idle/animation.gif",
      "notes": ""
    }
  ]
}
```

Append entries for new current-tag assets. Preserve prior entries unless the
same current-tag asset is being regenerated.

## Planning Rules

1. Choose `family` before writing the prompt.
2. Choose `production_shape` before calling the provider.
3. Generate canonical references before derivative assets.
4. Generate one body action per action sheet.
5. Generate idle, run, attack, hurt, death, cast, and shoot body actions as
   separate action sources for important characters and enemies.
6. Generate projectiles, muzzle flashes, slash arcs, impacts, dust, and pickup
   effects separately from body animation sheets.
7. Use `character_frame_output` for processed runtime frames or delivery grid
   sheets derived from a `character_action_source`.
8. Use grid sheets only for compact, similarly sized objects.
9. Use `panel_source` for large UI panels and card frames.
10. Mark irregular or mixed sheets as `needs_curation`.
11. Record source, final, prompt, and status in the manifest.
12. Bind gameplay-visible final assets in `ASSETS.md` Visual Asset Contract.
13. Record `target_size` and `target_aspect` for fixed-viewport references,
    backgrounds, and parallax plates.

## Character Frame Output QC

Every `character_frame_output` manifest entry must include
`qc.action_processing` with:

1. `frame_count`
2. `frame_paths`
3. `align`
4. `shared_scale`
5. `sheet_path`
6. `gif_path`
7. `metadata_path`
8. `edge_touch_frames`
9. `scale_reference`

`edge_touch_frames` must be empty before a `character_frame_output` becomes
`ready`. `scale_reference.checked` must be present. The first accepted body
action can set it to `false`; later body actions should compare against the
accepted idle or run metadata.

## Curation Field

Use the optional `curation` object for source sheets, extraction atlases,
irregular references, and selected canonical assets.

Allowed `curation.status` values:

1. `not_required`
2. `pending`
3. `candidate_extracted`
4. `selected`
5. `needs_curation`
6. `needs_regeneration`
7. `rejected`

Allowed `curation.strategy` values:

1. `none`
2. `transparent_grid`
3. `solid_background_grid`
4. `row_column_grid`
5. `explicit_boxes`
6. `manual_selection`
7. `regenerate_source`

Required curation fields:

1. `status`
2. `strategy`
3. `report_path` when `status` is not `not_required`

Set `selected_count` and `rejected_count` when a curation report exists.
