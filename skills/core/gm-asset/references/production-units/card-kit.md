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
9. Write manifest entries.
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
2. Run `tools/asset_image_finalize.py` with the required target geometry.
3. Write `runtime_artifact: single` in the manifest entry.

Separated card components:

```bash
python tools/asset_sheet_process.py \
  --source <card_source.png> \
  --out-dir <curation_dir> \
  --background magenta \
  --snap-mode autoslice \
  --component-mode largest
```

Use `--snap-mode grid` only for deliberate equal-cell badge or slot layouts.
Do not use a source kit or source frame as an independent final card asset.

Final selected component PNG:

```bash
python tools/asset_curation_select.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --final-path <final_path> \
  --asset-id <final_asset_id> \
  --project-root .
```

Create selected-candidate manifest entries with
`tools/asset_curation_manifest_entry.py`.

Final processed card atlas:

1. Write a transparent processed atlas to the final path.
2. Write runtime atlas metadata beside the atlas.
3. Write `runtime_artifact: region_atlas` in the manifest entry.
4. Write `qc.atlas_metadata.metadata_path` and `region_count` in the manifest
   entry.

## Outputs

1. card kit source
2. finalized single card or portrait frame assets
3. extracted badge, slot, and overlay candidates
4. selected final card PNGs or processed card atlas
5. runtime atlas metadata when final is an atlas
6. curation report when extraction is used
7. manifest entry JSON
