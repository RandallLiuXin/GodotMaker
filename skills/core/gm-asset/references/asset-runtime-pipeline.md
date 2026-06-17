# Asset Runtime Pipeline Reference

Use this file for common paths, manager-to-producer handoff, and manifest
registration. Use production-unit docs for prompts, finalization, extraction,
processing, and curation commands.

## Fixed Paths

For each generated visual production unit, reserve:

1. Source images under `.godotmaker/asset-generation/sources/`.
2. Replaced source images under `.godotmaker/asset-generation/sources/history/`.
3. Prompt files under `.godotmaker/asset-generation/prompts/`.
4. Reports under `.godotmaker/asset-generation/reports/`.
5. Curation reports under `.godotmaker/asset-generation/curation/`.
6. Processed previews and derived files under
   `.godotmaker/asset-generation/processed/`.
7. Manifest entry files under
   `.godotmaker/asset-generation/work/manifest-entries/`.
8. Final runtime assets under `assets/`.
9. Scene references under `references/`.

## Provider Docs

Use exactly one provider doc per production unit:

1. `references/providers/native.md`
2. `references/providers/codex.md`
3. `references/providers/gemini.md`
4. `references/providers/openai.md`

## Production Shapes

| Shape | Use for | Required fields |
|-------|---------|-----------------|
| `single_image` | Backgrounds, panels, canonicals, large props | `source_path`, `final_path` |
| `grid_sheet` | Source sheet for compact components or deliberate equal-cell layouts | `source_path`, `expected_items` |
| `action_sheet` | One character or FX action | `source_path`, `action`, `frames`, `anchor` |
| `frame_sequence` | Extracted animation frames | `source_path`, `frame_dir`, `fps`, `loop` |
| `delivery_sheet` | Runtime-ready sheet assembled from processed frames | `source_path`, `final_path`, `derived_from` |
| `reference_only` | Screen/style references | `source_path` or `final_path`, `contract_summary` |
| `curation_required` | Irregular sheets or references needing selection | `source_path`, `curation_reason` |

## Processing Status

1. `source_only`
2. `needs_curation`
3. `processed`
4. `ready`
5. `deferred`
6. `rejected`

## Extraction Status

1. `not_required`
2. `pending`
3. `source_sheet`
4. `extracted`
5. `processed`
6. `needs_curation`
7. `rejected`

## Runtime Artifact Types

Use `runtime_artifact` to describe the ready asset shape:

| Type | Use for | Required manifest data |
|------|---------|------------------------|
| `reference` | Style, screen, and planning references | `final_path` or `source_path`, contract summary |
| `single` | One runtime image | `final_path`, target geometry or extraction data |
| `grid_sheet` | Regular grid sheet for animation, FX, or fixed cells | `final_path`, `qc.action_processing.metadata_path`, frame count |
| `region_atlas` | Irregular UI, icon, prop, strip, or tileset atlas | `final_path`, `qc.atlas_metadata.metadata_path`, region count |

## Manifest Handoff

Each ready entry writes `runtime_artifact` as one of:

1. `reference`
2. `single`
3. `grid_sheet`
4. `region_atlas`

Upsert manifest entries with:

```bash
python tools/asset_generation_manifest_update.py --entry-file <entry.json>
```

Validate the manifest with:

```bash
python tools/asset_generation_manifest_check.py --check-files
```

Producer reports include manifest entry paths. The manager upserts entries and
runs full manifest validation before updating ASSETS.md.

Update matching ASSETS.md rows with:

```bash
python tools/asset_assets_md_update.py --entry-file <entry.json>
```

Manifest entry shape:

```json
{
  "asset_id": "<asset_id>",
  "tag": "<tag>",
  "family": "<family>",
  "production_shape": "<shape>",
  "runtime_role": "<role>",
  "source_path": ".godotmaker/asset-generation/sources/<source>.png",
  "final_path": "assets/<path>.png",
  "target_size": null,
  "target_aspect": null,
  "derived_from": null,
  "canonical_reference": null,
  "prompt_path": ".godotmaker/asset-generation/prompts/<asset_id>.txt",
  "runtime_artifact": "single",
  "processing_status": "ready",
  "extraction_status": "processed",
  "qc": {},
  "curation": {
    "status": "not_required",
    "strategy": "none",
    "report_path": null
  },
  "preview_path": null,
  "notes": ""
}
```

Append entries for new current-tag assets. Preserve prior entries unless the
same current-tag asset is being regenerated.

## Curation Field

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
4. `transparent_autoslice`
5. `solid_background_autoslice`
6. `row_column_grid`
7. `explicit_boxes`
8. `manual_selection`
9. `regenerate_source`

Required curation fields:

1. `status`
2. `strategy`
3. `report_path` when `status` is not `not_required`

## Runtime Ready Gate

Foreground runtime asset families:

1. `projectile_fx_source`
2. `impact_fx_source`
3. `compact_prop_pack`
4. `character_portrait`
5. `ui_component_sheet`
6. `icon_pack`
7. `panel_source`
8. `card_component_sheet`
9. `card_frame_source`
10. `portrait_frame_source`
11. `scene_prop_set`
12. `platform_strip`
13. `runtime_sprite`

When one of these families is `ready`, set `runtime_artifact` to one of:

1. `single`
2. `grid_sheet`
3. `region_atlas`

Ready gate by artifact:

1. `single`: use one runtime-ready image.
2. `grid_sheet`: include action metadata path and frame count.
3. `region_atlas`: include atlas metadata path and region count.
4. `reference`: do not mark ASSETS runtime rows generated from this entry.

Keep detailed runtime metadata under `assets/**/*.json`, not embedded in the
asset-generation manifest.

Atlas manifest summary:

```json
{
  "metadata_path": "assets/ui/main_atlas.json",
  "region_count": 8
}
```

Atlas runtime metadata shape:

```json
{
  "version": 1,
  "runtime_artifact": "region_atlas",
  "atlas_path": "assets/ui/main_atlas.png",
  "regions": [
    {
      "name": "battle_button",
      "rect": [0, 0, 256, 96],
      "pivot": [0.5, 0.5],
      "nine_slice": null
    }
  ]
}
```

Action manifest summary:

```json
{
  "frame_count": 4,
  "metadata_path": "assets/sprites/player_idle.json"
}
```

Action runtime metadata shape:

```json
{
  "version": 1,
  "runtime_artifact": "grid_sheet",
  "sheet_path": "assets/sprites/player_idle.png",
  "frame_count": 4,
  "frame_paths": [
    "assets/sprites/player_idle_01.png"
  ],
  "align": "feet",
  "shared_scale": true,
  "edge_touch_frames": []
}
```

## Production Unit Plan Shape

Use this shape for manager-to-producer handoff:

```json
{
  "unit_id": "<unit_id>",
  "unit_doc": "references/production-units/<unit>.md",
  "provider_doc": "references/providers/<provider>.md",
  "provider": "<asset_image_model>",
  "dependencies": [],
  "items": [
    {
      "asset_id": "<asset_id>",
      "family": "<family>",
      "production_shape": "<shape>",
      "target_size": "<WIDTHxHEIGHT or null>",
      "target_aspect": "<WIDTH:HEIGHT or null>",
      "prompt_path": ".godotmaker/asset-generation/prompts/<asset_id>.txt",
      "source_path": ".godotmaker/asset-generation/sources/<asset_id>_source.png",
      "final_path": "assets/<path>.png",
      "runtime_artifact": "<reference|single|grid_sheet|region_atlas>",
      "manifest_entry_path": ".godotmaker/asset-generation/work/manifest-entries/<asset_id>.json"
    }
  ],
  "report_path": ".godotmaker/asset-generation/reports/<unit_id>.json"
}
```

## Report Shape

Each production unit writes one report:

```json
{
  "ok": true,
  "unit_id": "<unit_id>",
  "provider": "<asset_image_model>",
  "status": "done",
  "sequential_fallback_reason": null,
  "sources": [],
  "finals": [],
  "prompts": [],
  "manifest_entries": [],
  "curation_reports": [],
  "failures": []
}
```
