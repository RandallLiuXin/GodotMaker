# FX Bundle Production Unit

Use this unit for projectiles, impacts, explosions, pickup effects, muzzle
flashes, slash arcs, aura loops, dust, and detached effects.

## Inputs

1. Visible related references or `STYLE.md` seed
2. Current-tag ASSETS.md rows
3. Related character or gameplay reference paths
4. Required effect timing or state

## Steps

1. Choose one coherent effect action per source.
2. Write a prompt with exact frame count, grid, or one-item source.
3. Generate the source through the provider doc.
4. Process action sources with `tools/asset_action_process.py` using
   `kind: fx`.
5. Process single projectiles, pickups, and one-frame effects with
   `tools/asset_sheet_process.py --snap-mode autoslice`.
6. Use action metadata for animated frames or delivery sheets.
7. Use selected transparent PNGs for one-frame foreground effects.
8. Write manifest entries.

## Prompt Contract

State:

1. effect identity
2. gameplay role
3. frame count or single-image target
4. travel or impact direction
5. separated foreground effect on solid `#FF00FF`
6. consistent scale
7. no text or UI

## Post-Processing

Process animated FX sources:

```bash
python tools/asset_action_process.py \
  --source <fx_source.png> \
  --out-dir <processed_dir> \
  --grid <COLSxROWS> \
  --names <frame_names> \
  --kind fx \
  --final-dir <runtime_dir> \
  --final-prefix <asset_id>
```

When `--final-dir` is used, `--final-prefix` is required. The tool writes
runtime frame files as `<final-prefix>_<frame-name>.png` unless the frame name
already starts with `<final-prefix>_`.

Use `align: center` for floating effects, projectiles, and detached FX.

Process one-frame foreground effects:

```bash
python tools/asset_sheet_process.py \
  --source <fx_source.png> \
  --out-dir <curation_dir> \
  --background magenta \
  --snap-mode autoslice \
  --component-mode largest
```

Select one-frame foreground effects with `tools/asset_curation_select.py`.
Write `runtime_artifact: single` in selected one-frame manifest entries.
Write `runtime_artifact: grid_sheet` in animated FX manifest entries.
Do not use a source sheet as an independent final effect.

## Outputs

1. source image
2. processed frames, delivery sheet, or selected foreground image
3. GIF preview when animated
4. processing report
5. action metadata for animated FX
6. manifest entry JSON
