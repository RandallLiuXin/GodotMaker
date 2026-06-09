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
2. Write a prompt with exact frame count or grid.
3. Generate the source through the provider doc.
4. Process action sources with `tools/asset_action_process.py` using
   `kind: fx`.
5. Finalize single-image effects when no frame extraction is needed.
6. Write manifest entries for final frames, sheets, or single images.

## Prompt Contract

State:

1. effect identity
2. gameplay role
3. frame count or single-image target
4. travel or impact direction
5. solid `#FF00FF` background for extracted sources
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
Finalize single-image effects with `tools/asset_image_finalize.py`.

## Outputs

1. source image
2. processed frames or final image
3. GIF preview when animated
4. processing report
5. manifest entry JSON
