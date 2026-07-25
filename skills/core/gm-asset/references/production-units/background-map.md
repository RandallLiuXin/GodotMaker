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
4. Finalize with aspect validation, writing the result under
   `assets/generated/background-map/<asset_id>/` and capturing the report.
5. Build the stable entry draft with `tools/asset_finalize_entry_draft.py`.

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
  --out assets/generated/background-map/<asset_id>/<asset_id>.png \
  --label <asset_id> \
  --require-aspect <WIDTH:HEIGHT> \
  --resize <WIDTHxHEIGHT> \
  > .godotmaker/asset-generation/reports/<asset_id>_finalize.json
```

`--label <asset_id>` and `--require-aspect` are both required: the draft builder
reads that report and refuses a run that skipped aspect validation or belongs to
a different asset.

If aspect validation fails, leave the production unit incomplete.

Build the stable entry draft from the captured report:

```bash
python tools/asset_finalize_entry_draft.py \
  --finalize-report .godotmaker/asset-generation/reports/<asset_id>_finalize.json \
  --asset-id <asset_id> \
  --tag <tag> \
  --production-family background-map \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

The draft carries `source_layout.type: single` at
`processing_status: source_ready` and no `godot_artifact`. Do not hand-write it.

## Outputs

1. source image
2. final background or plate
3. prompt file
4. provider/finalize report
5. stable entry drafts
