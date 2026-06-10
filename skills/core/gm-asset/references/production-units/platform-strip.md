# Platform Strip Production Unit

Use this unit for floors, bridges, platforms, rails, pipes, long hazards,
terrain chunks, and collision-aligned horizontal pieces.

## Inputs

1. Visible stage references or `STYLE.md` seed
2. Stage or map references
3. Required segment names
4. Collision or placement notes from ASSETS.md

## Steps

1. Choose one strip shape such as `1x3`, `1x4`, or custom wide cells.
2. Create a layout guide when fixed cells are needed.
3. Generate the source through the provider doc.
4. Process with `tools/asset_sheet_process.py --snap-mode grid`.
5. Choose final segments or a processed strip atlas.
6. Write runtime segment metadata when final is a processed strip atlas.
7. Write manifest entries.

## Prompt Contract

State:

1. segment list
2. left cap, repeat middle, right cap, and optional variant
3. horizontal walkable top edge when applicable
4. consistent y-position across cells
5. solid `#FF00FF` background
6. no actors, UI, text, or labels

Do not use this unit for characters, enemies, NPCs, summons, animated body
assets, or compact props.

## Post-Processing

Process fixed strip cells:

```bash
python tools/asset_sheet_process.py \
  --source <strip_source.png> \
  --out-dir <curation_dir> \
  --background magenta \
  --snap-mode grid \
  --component-mode largest
```

Use one selected final segment per cap, repeat middle, end, slope, or variant.
Use a processed strip atlas only with runtime segment metadata beside the final
atlas.
Write `runtime_artifact: single` in segment PNG manifest entries.
Write `runtime_artifact: region_atlas` in strip atlas manifest entries.

## Outputs

1. strip source
2. final strip segments or processed strip atlas
3. runtime segment metadata when final is an atlas
4. processing report
5. manifest entry JSON
