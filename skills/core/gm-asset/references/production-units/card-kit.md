# Card Kit Production Unit

Use this unit for card-game-specific visual assets: card frames, portrait
frames, rarity frames, resource badges, card slots, deck slots, and card state
overlays.

## Inputs

1. Visible card or UI references
2. Card-component rows in ASSETS.md
3. Scene references that show card context
4. Required component names and final paths

## Steps

1. Group card assets by frame geometry, rarity language, and resource marker
   style.
2. Generate full card frames and portrait frames as single-frame sources or
   deliberate strip sources.
3. Keep portrait windows and card art windows empty unless ASSETS.md requests
   finished portrait art.
4. Generate badges, slots, and state markers as separated components on
   solid `#FF00FF`.
5. Use the provider doc for every source.
6. Process separated components with `tools/asset_sheet_process.py --snap-mode
   autoslice`.
7. Use `--snap-mode grid` only for deliberate equal-cell badge or slot sheets.
8. Select final component PNGs or write a processed card atlas with runtime
   region metadata.
9. Write stable entry drafts.
10. Mark rows generated only after final card assets and metadata are ready.

## Prompt Contract

State:

1. card asset list
2. shared card style
3. frame geometry and orientation
4. empty portrait windows and card art windows
5. separated reusable pieces
6. clear spacing
7. no readable text or numbers
8. no character portrait unless the row explicitly requests a portrait image
9. no full composite screen
10. solid `#FF00FF` background for extraction sources

## Post-Processing

Large card or portrait frame as a single image:

1. Generate the source at the target aspect.
2. Run `tools/asset_image_finalize.py` with `--require-aspect`,
   `--label <asset_id>`, and `--out assets/generated/card-kit/<asset_id>/<asset_id>.png`,
   redirecting the report to
   `.godotmaker/asset-generation/reports/<asset_id>_finalize.json`.
3. Build the draft from that report:

```bash
python tools/asset_finalize_entry_draft.py \
  --finalize-report .godotmaker/asset-generation/reports/<asset_id>_finalize.json \
  --asset-id <asset_id> \
  --tag <tag> \
  --production-family card-kit \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

Separated card components:

```bash
python tools/asset_sheet_process.py \
  --source <card_source.png> \
  --out-dir <curation_dir> \
  --grid <COLSxROWS> \
  --names <component_names> \
  --background magenta \
  --snap-mode autoslice \
  --component-mode largest
```

`--grid` is required in both snap modes; in autoslice it sets the cell buckets
and per-cell names that detected components are assigned to. Match `--grid` and
`--names` to the card-component layout requested in the prompt.

Use `--snap-mode grid` only for deliberate equal-cell badge or slot layouts.
Do not use a source kit or source frame as an independent final card asset.

Final selected component PNG:

```bash
python tools/asset_curation_select.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --final-path assets/generated/card-kit/<final_asset_id>/<final_asset_id>.png \
  --asset-id <final_asset_id> \
  --project-root .
```

Build the stable entry draft deterministically:

```bash
python tools/asset_curation_entry_draft.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --asset-id <final_asset_id> \
  --tag <tag> \
  --production-family card-kit \
  --source-layout single \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<final_asset_id>.json
```

The draft stops at `processing_status: source_ready` with no `godot_artifact`.
Do not hand-write it, and do not add an artifact to make the asset look finished:
the native compiler that produces one is not implemented yet.

Final processed card atlas:

1. Write a transparent processed atlas under
   `assets/generated/card-kit/<asset_id>/`.
2. Write runtime atlas metadata beside the atlas.
3. Draft the entry with `--source-layout region_atlas`.
4. Leave `godot_artifact` absent until the atlas compiler lands.

## Outputs

1. card kit source
2. finalized single card or portrait frame assets
3. extracted badge, slot, and overlay candidates
4. selected final card PNGs or processed card atlas
5. runtime atlas metadata when final is an atlas
6. curation report when extraction is used
7. stable entry drafts
