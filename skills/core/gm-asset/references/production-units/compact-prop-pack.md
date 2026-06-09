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
6. Select final prop candidates.
7. Write manifest entries.

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
  --background magenta \
  --snap-mode autoslice \
  --component-mode largest
```

Use `--snap-mode grid` only for deliberate equal-cell prop packs.

Select final props with `tools/asset_curation_select.py`.
Create selected-candidate manifest entries with
`tools/asset_curation_manifest_entry.py`.

## Outputs

1. prop source sheet
2. extracted candidates
3. selected final prop assets
4. curation report
5. manifest entry JSON
