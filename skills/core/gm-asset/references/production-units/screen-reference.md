# Screen Reference Production Unit

Use this unit for full-screen scene references and build/evaluate visual
targets.

## Inputs

1. `STYLE.md` seed or existing visual references
2. Relevant `SCENES.md` scene section
3. Matching current-tag Visual Asset Contract rows
4. Existing user-provided asset summary when available

## Steps

1. Write one prompt per scene reference.
2. Include target size and target aspect.
3. Generate a source image through the provider doc.
4. Finalize with aspect validation, capturing the finalize report.
5. Write one report entry per scene.
6. Build the stable entry draft with `tools/asset_finalize_entry_draft.py`.

## Prompt Contract

Describe:

1. game genre and scene purpose
2. camera/viewpoint
3. gameplay-visible objects
4. approximate layout
5. HUD or UI elements from `SCENES.md`
6. style language from existing visual references or `STYLE.md`
7. target aspect and orientation

Do not add labels, callouts, debug overlays, or extra objects.

## Post-Processing

Finalize accepted scene references:

```bash
python tools/asset_image_finalize.py \
  --source <source_path> \
  --out references/scene_<name>.png \
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
  --production-family screen-reference \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

The draft carries `source_layout.type: reference` at
`processing_status: source_ready` and no `godot_artifact` — a reference is never
a runtime game asset. Do not hand-write it.

## Outputs

1. `.godotmaker/asset-generation/prompts/<asset_id>.txt`
2. `.godotmaker/asset-generation/sources/<asset_id>_source.png`
3. `references/scene_<name>.png`
4. `.godotmaker/asset-generation/reports/<unit_id>.json`
5. stable entry drafts
