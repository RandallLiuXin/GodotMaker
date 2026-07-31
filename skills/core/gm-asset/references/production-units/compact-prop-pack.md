# Compact Prop Pack Production Unit

Use this unit for small props, pickups, crates, stones, bushes, pots, debris,
small signs, lamps, and compact environmental dressing.

## Inputs

1. Visible scene references or `STYLE.md` seed
2. Prop rows in ASSETS.md
3. Scene or map reference paths
4. Expected prop names and final paths

## Steps

1. Include only compact props in this unit.
2. Use separated objects on solid `#FF00FF` by default.
3. Generate the source through the provider doc.
4. Run `tools/asset_sheet_process.py --snap-mode autoslice`.
5. Use `tools/asset_sheet_process.py --snap-mode grid` only when every prop has
   a deliberate fixed cell.
6. Select final prop PNGs by default.
7. Use a processed prop atlas only when the ASSETS row asks for a pack or atlas.
8. Write runtime atlas metadata when final is a processed atlas.
9. Write stable entry drafts.
10. Mark rows generated only after final prop artifacts are ready.

## Prompt Contract

State:

1. prop list
2. shared environment style
3. consistent lighting and perspective
4. clear spacing around each prop
5. solid `#FF00FF` background
6. no text, labels, UI, or floor plane

Do not include wide, tall, collision-bearing, platform, floor, bridge, ladder,
door, gate, large tree, building, terrain chunk, long hazard, road, rail, pipe,
or tileset-like assets.

## Post-Processing

Extract separated props:

```bash
python tools/asset_sheet_process.py \
  --source <prop_source.png> \
  --out-dir <curation_dir> \
  --names <prop_names> \
  --background magenta \
  --snap-mode autoslice
```

Match `--names` to the separated props in row-major reading order.

Use `--snap-mode grid` only for deliberate equal-cell prop packs.
Use the same autoslice path for one-item pickup, collectable, and small-prop
sources.
Do not use a source pack as an independent final prop artifact.

Select final props with `tools/asset_curation_select.py`.
Build the stable entry draft deterministically:

```bash
python tools/asset_curation_entry_draft.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --asset-id <final_asset_id> \
  --tag <tag> \
  --production-family compact-prop-pack \
  --source-layout single \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<final_asset_id>.json
```

The draft stops at `processing_status: source_ready` with no `godot_artifact`.
Do not hand-write it, and do not add an artifact to make the asset look finished:
the native compiler that produces one is not implemented yet.

For a requested prop atlas:

1. Write a transparent processed atlas under
   `assets/generated/compact-prop-pack/<asset_id>/`.
2. Write runtime atlas metadata with named prop regions beside the final atlas.
3. Draft the entry with `--source-layout region_atlas`.
4. Leave `godot_artifact` absent until the atlas compiler lands.

## Outputs

1. prop source sheet
2. extracted candidates
3. selected final prop PNGs or processed prop atlas
4. runtime atlas metadata when final is an atlas
5. curation report
6. stable entry drafts
