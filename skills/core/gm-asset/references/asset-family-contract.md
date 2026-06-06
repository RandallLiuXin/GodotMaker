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
      "asset_id": "player_idle",
      "tag": "v0.1.0",
      "family": "character_action_source",
      "production_shape": "action_sheet",
      "runtime_role": "player",
      "source_path": ".godotmaker/asset-generation/sources/player_idle_source.png",
      "final_path": "assets/sprites/player_idle.png",
      "derived_from": "player_canonical",
      "canonical_reference": "player_canonical",
      "prompt_path": ".godotmaker/asset-generation/prompts/player_idle.txt",
      "processing_status": "ready",
      "extraction_status": "processed",
      "qc": {
        "alpha": "ok",
        "edge_touch": "not_checked",
        "readability": "pending_evaluate"
      },
      "preview_path": null,
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
5. Generate projectiles and impacts separately from body animation sheets.
6. Use grid sheets only for compact, similarly sized objects.
7. Use `panel_source` for large UI panels and card frames.
8. Mark irregular or mixed sheets as `needs_curation`.
9. Record source, final, prompt, and status in the manifest.
10. Bind gameplay-visible final assets in `ASSETS.md` Visual Asset Contract.
