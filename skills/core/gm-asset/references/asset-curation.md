# Asset Curation Reference

Use this file after source images exist and before ASSETS.md marks runtime
visual assets as `generated`.

## Scope

Use curation for:

1. Splitting generated source sheets into object candidates.
2. Selecting canonical character, enemy, prop, icon, and UI references.
3. Rejecting unsuitable generated sources.
4. Recording accepted final runtime assets.

Do not use curation to change GDD.md, PLAN.md, STRUCTURE.md, SCENES.md, or
STYLE.md.

## When Curation Is Required

Run a curation pass when an asset has any of these shapes or statuses:

1. `production_shape: grid_sheet`
2. `production_shape: action_sheet`
3. `production_shape: frame_sequence`
4. `production_shape: curation_required`
5. `processing_status: needs_curation`
6. `extraction_status: source_sheet`
7. `extraction_status: extracted`
8. A scene reference is being used as the source for runtime objects.

Do not bind an irregular source sheet, UI kit, object atlas, or full scene
reference directly to a gameplay-visible ASSETS.md row.

## Curation Decision States

Use these states in curation records:

1. `candidate`: cropped or identified object is available for review.
2. `selected`: candidate is accepted as a canonical or runtime asset.
3. `variant`: candidate is retained as a style-compatible alternative.
4. `rejected`: candidate or source should not be used.

Use these source-level outcomes:

1. `selected`: final assets were selected from this source.
2. `needs_curation`: candidates exist but final selection is not complete.
3. `needs_regeneration`: source is unsuitable for extraction.
4. `rejected`: source should not be used.

## Extraction Strategy Order

Choose the first strategy that matches the source:

1. Character animation frame sheets and fixed-row sprite sheets: use
   `tools/asset_action_process.py` for character actions or
   `tools/asset_sheet_process.py --snap-mode grid` for non-character fixed
   grids.
2. Strict regular grids where every cell maps to one object: use
   `tools/asset_sheet_process.py --snap-mode grid`.
3. Solid magenta `#FF00FF` background with separated UI, icon, or prop
   objects: use
   `tools/asset_sheet_process.py --background magenta --snap-mode autoslice`.
   Use `--magenta-threshold` and `--magenta-edge-threshold` when generated
   sheets leave visible magenta fringe.
   Use `--component-mode largest` for compact prop packs, icon packs, and UI
   component sheets.
4. Irregular atlas with clear object boxes: write explicit object boxes in the
   curation record and crop with a follow-up tool or manual pass.
5. Crowded, overlapping, inconsistent, or text-heavy source: mark
   `needs_regeneration`.

## Character Action Curation

Process each `character_action_source` before updating ASSETS.md.

1. Use `tools/asset_action_process.py`.
2. Use explicit grid shape and frame names.
3. Use solid `#FF00FF` background processing for magenta sources.
4. Use `kind: body` for body-only character, enemy, NPC, summon, and animated
   prop actions.
5. Use `kind: fx` for projectile, impact, slash, aura, dust, pickup, and
   detached effect sources.
6. Use `align: feet` or `align: bottom` for grounded body actions.
7. Use `align: center` for floating actions and detached FX.
8. Compare later body actions against accepted idle or run metadata.
9. Reject processed outputs with non-empty `edge_touch_frames`.
10. Write frames, transparent delivery grid sheet, GIF, and pipeline metadata.
11. Keep one processing report per action source.
12. Set derived outputs to `character_frame_output` with `derived_from` pointing
    to the action source and `canonical_reference` pointing to the accepted
    canonical asset.

```bash
python tools/asset_action_process.py \
  --source <action_source.png> \
  --out-dir <processed_dir> \
  --grid <COLSxROWS> \
  --names <frame_names> \
  --kind <body|fx> \
  --final-dir <runtime_dir> \
  --final-prefix <asset_id>
```

For later body actions, add `--scale-reference-metadata <pipeline-meta.json>`.

Build the derived `character_frame_output` manifest entry from the action
metadata:

```bash
python tools/asset_action_manifest_entry.py \
  --metadata <processed_dir>/pipeline-meta.json \
  --source-entry <character_action_source_entry.json> \
  --asset-id <frame_output_asset_id> \
  --project-root . \
  --out <frame_output_entry.json>
```

## Curation Record Shape

Write curation reports under `.godotmaker/asset-generation/curation/`:

```json
{
  "version": 1,
  "asset_id": "ui_kit_source",
  "tag": "v0.1.0",
  "source_path": ".godotmaker/asset-generation/sources/ui_kit_source.png",
  "strategy": "transparent_grid",
  "status": "needs_curation",
  "candidates": [
    {
      "candidate_id": "ui_kit_source.action_button",
      "name": "action_button",
      "path": ".godotmaker/asset-generation/curation/ui_kit/action_button.png",
      "state": "candidate",
      "bbox": [0, 0, 96, 48],
      "role": "HUD button",
      "final_path": "assets/ui/action_button.png"
    }
  ],
  "rejected": [
    {
      "candidate_id": "ui_kit_source.empty_04",
      "state": "rejected",
      "reason": "empty_cell"
    }
  ],
  "notes": ""
}
```

## Canonical Selection Rules

1. Select one canonical reference for each player character, enemy family, UI
   family, prop family, and environment family.
2. Use the canonical reference as `canonical_reference` for derivative assets.
3. Use `derived_from` for animation frames, UI states, enemy variants, prop
   variants, and VFX derived from a canonical source.
4. When multiple candidates conflict, select one canonical candidate and mark
   the others `variant` or `rejected`.
5. Record rejected candidates in the curation report.

## Selecting Candidates

Finalize a selected candidate with `tools/asset_curation_select.py`. Provide
the curation report path, candidate id or name, final runtime path, final asset
id, and project root.

```bash
python tools/asset_curation_select.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --final-path <final_path> \
  --asset-id <final_asset_id> \
  --project-root .
```

The tool copies or resizes the candidate into the runtime asset path and updates
the curation report:

1. Candidate `state` becomes `selected`.
2. Candidate `final_path` points to the runtime asset.
3. Report `status` becomes `selected`.
4. Report `selected_count` and `rejected_count` are updated.
5. Report `selected_candidate_ids` lists selected candidates.

## Manifest Integration

For each manifest entry that requires curation:

1. Set `processing_status` to `needs_curation` until final runtime assets are
   selected.
2. Set `extraction_status` to `source_sheet` after the source sheet exists.
3. Set `extraction_status` to `extracted` after candidates are cropped.
4. Set `processing_status` to `processed` or `ready` only after final assets
   are selected and written to their project paths.
5. Set `curation.report_path` to the curation report.
6. Set `curation.status` to the source-level outcome.
7. Set `curation.strategy` to the extraction strategy.
8. Set `curation.selected_count` to the number selected by
   `tools/asset_curation_select.py`.
9. Set `final_path` to the runtime asset produced by selection.

## ASSETS.md Integration

Only update ASSETS.md rows to `generated` when:

1. The row's `File Path` points to a final runtime asset, not a source sheet.
2. The matching manifest entry is `processed` or `ready`.
3. The matching curation report is `selected` or no curation is required.
4. The Visual Asset Contract names the canonical or derived source.

If curation is incomplete, leave the row `MISSING` or mark the source entry as
`needs_curation` in the manifest.
