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

## Manifest Handoff

Upsert manifest entries with:

```bash
python tools/asset_generation_manifest_update.py --entry-file <entry.json>
```

Validate the manifest with:

```bash
python tools/asset_generation_manifest_check.py --check-files
```

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
