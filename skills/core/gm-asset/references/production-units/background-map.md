# Background Map Production Unit

Use this unit for backgrounds, map bases, parallax plates, and fixed-viewport
scenic assets.

## Inputs

1. Visible scene references or `STYLE.md` seed
2. `SCENES.md`
3. Current-tag ASSETS.md rows
4. Target size and target aspect

## Steps

1. Write one prompt per background or plate.
2. Include fixed viewport, target aspect, and composition.
3. Generate source images through the provider doc.
4. Finalize with aspect validation when target size is fixed.
5. Write `runtime_artifact: single` in the manifest entry.
6. Write manifest entries.

## Prompt Contract

State:

1. scene role
2. viewpoint
3. target aspect and orientation
4. background or parallax layer responsibility
5. style language from visible references or `STYLE.md`

Do not include gameplay actors, pickups, hazards, UI, labels, or text.

## Post-Processing

Finalize accepted backgrounds and plates:

```bash
python tools/asset_image_finalize.py \
  --source <source_path> \
  --out <final_path> \
  --label <asset_id> \
  --require-aspect <WIDTH:HEIGHT> \
  --resize <WIDTHxHEIGHT>
```

If aspect validation fails, leave the production unit incomplete.

## Outputs

1. source image
2. final background or plate
3. prompt file
4. provider/finalize report
5. manifest entry JSON
